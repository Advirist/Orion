from settings.prompts import SYSTEM_PROMPT
from llm.model_client import stream_reply, correct_reply
from tools import call_tool
import json
from llm.verifier import lie_detector
from storage.errors import log_error_from_verifier

class Engine:
    def __init__(self, history, save_history=None, model=stream_reply, run_tool = call_tool, max_tool_rounds = 8, 
                 max_retries = 3, verify=lie_detector, correct=correct_reply, log_mismatch=log_error_from_verifier):
        if not history:
            history.append({'role': 'system', 'content': SYSTEM_PROMPT})
        elif history[0].get("role") == "system":
            history[0] = {'role': 'system', 'content': SYSTEM_PROMPT}
        else:
            history.insert(0, {'role': 'system', 'content': SYSTEM_PROMPT})
        
        self.history = history
        self.save_history = save_history
        self.model = model
        self.run_tool = run_tool
        self.max_tool_rounds = max_tool_rounds
        self.max_retries = max_retries
        self.verify = verify
        self.correct = correct
        self.log_mismatch = log_mismatch

    def respond(self, user_text):
        if not user_text or not user_text.strip():
            yield {'type': 'done'}
            return
        
        self.history.append({'role':'user','content': user_text})
        if self.save_history:
            self.save_history(self.history)

        tool_count = 0
        failures = 0
        tool_results = []

        while True:
            content = ''
            tool_calls = []
            try: 
                for event in self.model(self.history):
                    if event['type'] == 'text':
                        yield event
                    elif event['type'] == 'done':
                        content = event['content']
                        tool_calls = event['tool_calls']

            except Exception as error:
                failures += 1
                yield {'type': 'model_error', 'attempt': failures, 'max_attempts': self.max_retries, 'error': str(error)}
                if failures >= self.max_retries:
                    yield {'type': 'gave_up', 'message': f"The model did not respond after {self.max_retries} attempts."}
                    yield {'type': 'done'}
                    return
                continue
            failures = 0
            if content:
                yield {'type': 'text_end', 'text': content}


            if not tool_calls:
                break
            tool_count += 1
            if tool_count > self.max_tool_rounds:
                yield {'type': 'tool_limit', 'message': f"Stopped: the model asked for tools more than {self.max_tool_rounds} times in one turn."}
                yield {'type': 'done'}
                return
            self.history.append({'role' : 'assistant', 'content' : content, 'tool_calls' : tool_calls})
            for call in tool_calls:
                
                name = call['function']['name']
                arguments = call['function']['arguments']

                yield {'type': 'tool_call', 'name': name, 'arguments' : arguments}
                try:
                    result = self.run_tool(name, arguments)
                except Exception as e:
                    result = {"success": False, "error": "tool_crashed", "message": str(e)}
                tool_results.append(result)
                self.history.append({'role': 'tool', 'tool_name': name, 'content': json.dumps(result, default=str)})
                yield {'type': 'tool_result', 'name': name, 'result' : result}
            

        if content:
            reply = content
            if tool_results:
                try:
                    accurate, reason = self.verify(tool_results, reply)
                except Exception as error:
                    accurate, reason = True, ''
                    yield {'type': 'warning', 'message': f"The verifier could not run: {error}"}

                if not accurate:
                    yield {'type': 'verifier_flag', 'reason': reason, 'original': reply}
                    try:
                        self.log_mismatch(tool_results, reply, reason)
                    except Exception as error:
                        yield {'type': 'warning', 'message': f"The mismatch could not be logged: {error}"}
                    try:
                        corrected = self.correct(tool_results, reply)
                        if not corrected or not corrected.strip():
                            raise ValueError("the model returned an empty correction")
                        reply = corrected
                        yield {'type': 'corrected', 'text': reply}
                    except Exception as error:
                        yield {'type': 'correction_failed', 'error': str(error)}

            if reply:
                self.history.append({'role' : 'assistant', 'content' : reply})
                if self.save_history:
                    self.save_history(self.history)
                yield {'type': 'reply', 'text': reply}
        yield {'type': 'done'}