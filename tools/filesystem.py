import os
from pathlib import Path
from config import TESTING_DIR

#Tool to list directorys
def list_directory(path):
    #checks for absolute path if it is sends an error becasue absolute paths arent allowed
    if Path(path).is_absolute():
        return {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Only paths relative to the playground root are allowed. Try '.' for the root, or a relative subfolder name."
        }

    #combines and resolves paths to make it easy to verify if path is safe
    relative_path = Path(path)
    combined_path = TESTING_DIR / relative_path
    resolved_path = combined_path.resolve()

    #checks containment FIRST, before touching the filesystem at all,
    #so we never even check existence on a path outside the playground
    if not resolved_path.is_relative_to(TESTING_DIR):
        return {
            "success": False,
            "error": "outside_playground",
            "message": f"'{path}' resolves outside the allowed playground directory. You can only list directories inside the playground."
        }

    #checks if path actually exists on disk
    if not resolved_path.exists():
        return {
            "success": False,
            "error": "not_found",
            "message": f"'{path}' does not exist inside the playground."
        }

    #checks if path is a directory not a file
    if not resolved_path.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Use a directory path to list its contents."
        }

    #tries to actually list the directory contents
    try:
        contents = os.listdir(resolved_path)
        return {
            "success": True,
            #uses relative_to so we dont leak full absolute filesystem path back to model
            "path": str(resolved_path.relative_to(TESTING_DIR)),
            "contents": contents
        }
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to read '{path}'."
        }

#Schema to define tools to assistant
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists directory contents within the user's sandboxed playground directory (a restricted testing folder used during development). Attempts to access paths outside the playground will be rejected with an error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path" : {
                        "type" : "string",
                        "description" : "The directory path to list, relative to the playground root. Defaults to the current directory '.' if not specified by the user. Absolute paths are not allowed."
                    }
                },
                "required": []
            }
        }
    },
]

TOOL_REGISTRY = {
    "list_directory": list_directory,
    }