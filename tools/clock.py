from datetime import datetime

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "current_datetime",
            "description": "Reports the current local date, time, day of the week, and timezone on this machine. Use this whenever the date or time matters, rather than guessing.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]


def current_datetime():
    now = datetime.now().astimezone()
    date_text = f"{now:%A, %B} {now.day}, {now.year}"
    #'%I' zero-pads the hour (03:45 PM), so the leading zero is stripped for readability
    time_text = now.strftime('%I:%M %p').lstrip('0')
    return {
        "success": True,
        "iso": now.isoformat(timespec='seconds'),
        "date": date_text,
        "time": time_text,
        "timezone": now.tzname(),
        "message": f"It is {time_text} on {date_text} ({now.tzname()})."
    }


TOOL_REGISTRY = {
    "current_datetime": {'function': current_datetime, 'mutating': False},
}
