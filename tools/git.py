from settings.config import PROJ_DIR
import subprocess
from storage.errors import subprocess_log_error

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Runs 'git status' on the Orion project's own repository (not the sandboxed playground) and reports which files are staged, modified, or untracked. This is a read-only inspection command — it does not change anything.",
            "parameters": {
                "type": "object",
                "properties": {},
                'required' : []
            },
        }
    },
]

def git_status():
    try:
        content = subprocess.run(['git', 'status'], cwd=PROJ_DIR, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return {
            'success': False,
            'error': 'git_not_found',
            'message': "git does not appear to be installed or is not on the system PATH. Let the user know git isn't available."
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'timeout_error',
            'message': "The git status command took too long to respond and was cancelled. You can let the user know, or try again."
        }

    return_code = content.returncode
    stdout = content.stdout
    stderr = content.stderr

    if return_code != 0:
        message = f"git status failed (exit code {return_code}): {stderr.strip() or 'no error output was provided.'}"
        error = 'git_command_failed'
        subprocess_log_error(stdout, stderr, error, message)
        return {
            'success': False,
            'error': error,
            'message': message,
            'output': {'stdout': stdout, 'stderr': stderr}
        }

    return {
        'success': True,
        'message': "Retrieved the current git status of the Orion project repository.",
        'output': {'stdout': stdout, 'stderr': stderr}
    }

TOOL_REGISTRY = {
    "git_status": {'function': git_status, 'mutating': False},
}