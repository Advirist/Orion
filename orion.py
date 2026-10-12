"""
The terminal front end for Orion: asks for input (typed or spoken), shows what the engine
reports, and speaks replies in voice mode. The conversation logic itself lives in engine.py.
"""
from engine import Engine
from storage.history import history_load, history_save
from voice.voice_io import listen, speak


def read_user_input(speak_bool):
    """
    Asks for the next message. Returns (text, speak_bool).
    After a voice message Orion keeps listening; after a typed one it asks again how you want to answer.
    Ctrl+C at the prompt means "exit".
    """
    try:
        if speak_bool:
            return listen('')
        typed = input("Press Enter to start recording, type to not use voice: ")
        return listen(typed)
    except KeyboardInterrupt:
        print("\n[Exiting]")
        return '/e', False


def show_turn(engine, user_text, speak_bool):
    """
    Runs one turn and shows every event on screen, speaking the final reply in voice mode.
    Returns False if Orion gave up on reaching the model (the program should then exit).
    """
    keep_running = True
    try:
        for event in engine.respond(user_text):
            kind = event['type']

            if kind == 'text':
                print(event['text'], end='', flush=True)
            elif kind == 'text_end':
                print()
            elif kind == 'tool_call':
                print(f"\n[Orion wants to call: {event['name']}({event['arguments']})]")
            elif kind == 'tool_result':
                print(f"[Tool call result: {event['result']}]")
            elif kind == 'model_error':
                print(f"\n[Error getting response (attempt {event['attempt']} of {event['max_attempts']}): {event['error']}]")
            elif kind == 'gave_up':
                print("[Cannot reach the model server after multiple attempts — check that your desktop is on and Tailscale is connected. Exiting.]")
                keep_running = False
            elif kind == 'tool_limit':
                print(f"\n[{event['message']}]")
            elif kind == 'verifier_flag':
                print(f"\n[Verifier flagged this response as inaccurate: {event['reason']}]")
                print(f"[Original response: \"{event['original']}\"]")
            elif kind == 'corrected':
                print(f"[Corrected response: \"{event['text']}\"]")
            elif kind == 'correction_failed':
                print(f"[Correction attempt failed ({event['error']}) — keeping the original response.]")
            elif kind == 'warning':
                print(f"[Warning: {event['message']}]")
            elif kind == 'reply':
                if speak_bool:
                    speak(event['text'])
    except KeyboardInterrupt:
        print("\n[Response cancelled — returning to prompt]")
    return keep_running


def main():
    engine = Engine(history_load(), history_save)
    speak_bool = False

    while True:
        user_text, speak_bool = read_user_input(speak_bool)
        if user_text.strip() == '/e':      #ends the session
            break
        if not show_turn(engine, user_text, speak_bool):
            break


if __name__ == "__main__":
    main()