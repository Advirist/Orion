from settings.config import CLIENT
from settings.config import MODEL_NAME, NUM_CTX
from tools import TOOLS
from .context import prepare_history

def get_response(history: list):
    """
    Streams a reply from the model. Returns (full_content, tool_calls).
    Connection errors and timeouts are deliberately NOT caught here: they propagate to
    orion.py, which counts consecutive failures and exits after too many.
    Only Ctrl+C is handled here, since that's a user choice rather than a failure.
    """
    try:
        #prepare_history swaps stale live-data results for a short note; history itself is untouched
        stream = CLIENT.chat(MODEL_NAME, messages=prepare_history(history), tools=TOOLS,
                             stream=True, options={'num_ctx': NUM_CTX}, think=False)

        full_content = ""
        accumulated_tool_calls = []

        for chunk in stream:
            piece = chunk['message']

            if piece.get('content'):
                print(piece['content'], end='', flush=True)
                full_content += piece['content']

            if piece.get('tool_calls'):
                accumulated_tool_calls.extend(tool_call.model_dump() for tool_call in piece['tool_calls'])

        print()
        return full_content, accumulated_tool_calls

    except KeyboardInterrupt:
        print("\n[Response cancelled]")
        return "", []