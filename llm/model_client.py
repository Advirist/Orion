from settings.config import CLIENT
from settings.config import MODEL_NAME, NUM_CTX
from tools import TOOLS
from .context import prepare_history


def stream_reply(history: list):
    """
    Streams one reply from the model as a series of events, with no printing:

        {'type': 'text', 'text': '...'}                              one per piece of text, as it arrives
        {'type': 'done', 'content': '...', 'tool_calls': [...]}      last event: the whole reply

    Connection errors, timeouts and Ctrl+C are NOT caught here. They propagate to whoever is
    reading the stream (engine.py), which decides what to do about them.
    """
    #prepare_history swaps stale live-data results for a short note; history itself is untouched
    stream = CLIENT.chat(MODEL_NAME, messages=prepare_history(history), tools=TOOLS,
                         stream=True, options={'num_ctx': NUM_CTX}, think=False)

    full_content = ""
    accumulated_tool_calls = []

    for chunk in stream:
        piece = chunk['message']

        if piece.get('content'):
            full_content += piece['content']
            yield {'type': 'text', 'text': piece['content']}

        if piece.get('tool_calls'):
            accumulated_tool_calls.extend(tool_call.model_dump() for tool_call in piece['tool_calls'])

    yield {'type': 'done', 'content': full_content, 'tool_calls': accumulated_tool_calls}


def get_response(history: list):
    """
    The original console-style call: prints the reply as it streams and returns
    (full_content, tool_calls). Kept so older scripts keep working; new code should
    use stream_reply (or, better, engine.Engine).
    """
    try:
        full_content, tool_calls = "", []
        for event in stream_reply(history):
            if event['type'] == 'text':
                print(event['text'], end='', flush=True)
            else:
                full_content, tool_calls = event['content'], event['tool_calls']
        print()
        return full_content, tool_calls
    except KeyboardInterrupt:
        print("\n[Response cancelled]")
        return "", []


def correct_reply(tool_results: list, flawed_reply: str) -> str:
    """
    Asks the model to answer again after the verifier found its reply didn't match the tool
    results. Returns the new reply text. Errors propagate to the caller.
    """
    prompt = (
        "Your previous response did not accurately reflect the actual tool result.\n\n"
        f"Tool result: {tool_results}\n\n"
        f'Your response: "{flawed_reply}"\n\n'
        "This response claims or implies an outcome that the tool result does not support. "
        "Reconsider what actually happened based only on the tool result above, and respond "
        "to the user again, accurately this time."
    )
    response = CLIENT.chat(MODEL_NAME, messages=[{'role': 'system', 'content': prompt}],
                           options={'num_ctx': NUM_CTX})
    return response['message']['content']