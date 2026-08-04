from settings.config import CLIENT
from settings.config import MODEL_NAME
from tools import TOOLS

def get_response(history: str):
    try:
        stream = CLIENT.chat(MODEL_NAME, messages=history, tools=TOOLS, stream=True)

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
    except Exception as e:
        print(f"\n[Error communicating with model: {e}]")
        return "", []