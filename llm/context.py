import json
from tools import VOLATILE_TOOLS

STALE_NOTE = json.dumps({
    "stale": True,
    "message": "This earlier reading was removed because live data goes out of date. "
               "Call the tool again if you need current information."
})


def prepare_history(history):
    """
    Returns the copy of the conversation that is actually sent to the model.
    The saved history (and history.json) is never modified, so the full record is kept.

    Tool results that describe live state (battery, memory, git status, directory listings...)
    from BEFORE Jose's most recent message are replaced with a short stale note. Results from
    the current turn are left untouched, because the model needs them to answer.

    Older history files don't record which tool produced a result, so the tool's name is
    recovered from the assistant message that requested it (results arrive in the same order
    as the requests). That keeps existing history.json files working with no migration.
    """
    last_user = max((i for i, m in enumerate(history) if m.get('role') == 'user'), default=-1)

    prepared = []
    requested_names = []
    for i, message in enumerate(history):
        role = message.get('role')

        if role == 'assistant':
            requested_names = [
                (call.get('function') or {}).get('name')
                for call in (message.get('tool_calls') or [])
            ]

        elif role == 'tool':
            from_request = requested_names.pop(0) if requested_names else None
            tool_name = message.get('tool_name') or from_request
            if i < last_user and tool_name in VOLATILE_TOOLS:
                message = {**message, 'content': STALE_NOTE}

        prepared.append(message)
    return prepared