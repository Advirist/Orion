import psutil

TOOLS = [
    {
    "type": "function",
    "function": {
        "name": "cpu_memory_status",
        "description": "Reports the current CPU usage percentage and memory (RAM) usage of the system, including both the percentage used and the amount used versus total available, in gigabytes.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
},
]
def cpu_memory_status():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        memory_used_gb = round(memory.used / (1024 ** 3), 1)
        memory_total_gb = round(memory.total / (1024 ** 3), 1)

        return {
            "success": True,
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": memory_used_gb,
            "memory_total_gb": memory_total_gb
        }
    except Exception as e:
        return {
            "success": False,
            "error": "unexpected_error",
            "message": str(e)
        }

TOOL_REGISTRY = {
    "cpu_memory_status": {'function': cpu_memory_status, 'mutating': False},
}