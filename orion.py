from settings.config import CLIENT
import json
from tools import call_tool
from storage.history import history_load, history_save
from settings.prompts import SYSTEM_PROMPT
from llm.model_client import get_response
from llm.verifier import lie_detector
from settings.config import MODEL_NAME, NUM_CTX
from storage.errors import log_error_from_verifier
from voice.voice_io import listen, speak

MAX_RETRIES = 3

#Loads history from past sessions
speak_bool = False
history = history_load()

if isinstance(history, list) and history:
    if history[0].get("role") == "system":
        history[0] = {'role': 'system', 'content': SYSTEM_PROMPT}
    else:
        history.insert(0, {'role': 'system', 'content': SYSTEM_PROMPT})

session_bool = True

#first user input to start session off checks if wants to use voice or not
try:
    user_in = input("Press Enter to start recording, type to not use voice: ")
    user_in, speak_bool = listen(user_in)
except KeyboardInterrupt:
    print("\n[Exiting]")
    session_bool = False
    user_in = '/e'

if user_in.strip() == '/e': #ends session if user types /e
    session_bool = False
else:
    #adds first user input to history
    history.append({'role': 'user', 'content': user_in})
    history_save(history)

#While loop to keep the session going until user types /e
tool_results_for_lie_detector = []
consecutive_failures = 0 #counts back-to-back failed model calls, reset by any success
while session_bool:

    try:
        full_content, tool_calls = get_response(history)
        consecutive_failures = 0
    except KeyboardInterrupt:
        print("\n[Response cancelled — returning to prompt]")
        continue
    except Exception as e:
        consecutive_failures += 1
        print(f"\n[Error getting response (attempt {consecutive_failures} of {MAX_RETRIES}): {e}]")
        if consecutive_failures >= MAX_RETRIES:
            print("[Cannot reach the model server after multiple attempts — check that your desktop is on and Tailscale is connected. Exiting.]")
            break
        continue

    # Check if the model wants to call a tool instead of just replying
    if tool_calls:

        # Log the assistant's tool-call request itself into history
        history.append({'role': 'assistant', 'content': full_content, 'tool_calls': tool_calls})

        for tool_call in tool_calls:
            name = tool_call['function']['name']
            arguments = tool_call['function']['arguments']

            print(f'\n[Orion wants to call: {name}({arguments})]')
            try:
                result = call_tool(name, arguments)
            except Exception as e:
                result = {"success": False, "error": "tool_crashed", "message": str(e)}

            #recorded even when the tool crashed, so the verifier sees every result from this turn
            tool_results_for_lie_detector.append(result)
            print(f'[Tool call result: {result}]')

            # Tool results go back in as their own message, role='tool'
            history.append({
                'role': 'tool',
                'tool_name': name,
                'content': json.dumps(result)
            })

        history_save(history)
        continue  # loop back to the model WITHOUT asking user for input —
                  # the model needs to see the tool result before it can respond

    #prompt if model messes up and lie detector catches it
    CORRECTION_PROMPT = f"""Your previous response did not accurately reflect the actual tool result.

                            Tool result: {tool_results_for_lie_detector}

                            Your response: "{full_content}"

                            This response claims or implies an outcome that the tool result does not support. 
                            Reconsider what actually happened based only on the tool result above, and respond 
                            to the user again, accurately this time."""

    #checks if tool was called by assistant then is checked with the lie detector
    if tool_results_for_lie_detector:
        lie_detector_result, lie_detector_reason = lie_detector(tool_results_for_lie_detector, full_content)
        #if lie is detected tells model and makes it try again
        if not lie_detector_result:
            print(f'\n[Verifier flagged this response as inaccurate: {lie_detector_reason}]')
            print(f'[Original response: "{full_content}"]')
            log_error_from_verifier(tool_results_for_lie_detector, full_content, lie_detector_reason)
            try:
                full_content = CLIENT.chat(
                    MODEL_NAME,
                    messages=[{'role': 'system', 'content': CORRECTION_PROMPT}],
                    options={'num_ctx': NUM_CTX}
                )['message']['content']
                print(f'[Corrected response: "{full_content}"]')
            except Exception as e:
                #if the correction call fails, the original response is kept rather than crashing
                print(f"[Correction attempt failed ({e}) — keeping the original response.]")

    tool_results_for_lie_detector = []

    #an empty reply (e.g. after Ctrl+C mid-response) is neither spoken nor saved to history
    if full_content:
        if speak_bool:
            speak(full_content)
        history.append({'role': 'assistant', 'content': full_content})
        history_save(history)

    #asks the user for input and adds it to the history
    if speak_bool:
        try:
            user_in, speak_bool = listen('')
        except KeyboardInterrupt:
            print("\n[Exiting]")
            break
    else:
        try:
            user_in = input("Press Enter to start recording, type to not use voice: ")
            user_in, speak_bool = listen(user_in)
        except KeyboardInterrupt:
            print("\n[Exiting]")
            break

    if user_in.strip() == '/e': #ends session if user types /e
        break

    history.append({'role': 'user', 'content': user_in})
    history_save(history) #saves the history to a json file