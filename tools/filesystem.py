import os
from pathlib import Path
from config import TESTING_DIR

#Tool to list directorys
def list_directory(path = '.'):
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

def read_file(path : str, offset : int = 0, max_char : int = 12000):
    


    if Path(path).is_absolute():
        return {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Only paths relative to the playground root are allowed. Try '.' for the root, or a relative subfolder name."
        }
    
    relative_path = Path(path)
    combined_path = TESTING_DIR / relative_path
    resolved_path = combined_path.resolve()

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
    if resolved_path.is_dir():
        return {
            "success": False,
            "error": "not_a_file",
            "message": f"'{path}' is a directory, not a file. Use a file path to read its contents."
        }
    
    ALLOWED_EXTENSIONS = {'.txt', '.py', '.md', '.json', '.csv', '.java'}
    if resolved_path.suffix not in ALLOWED_EXTENSIONS:
        return {"success": False, "error": "unsupported_file_type", "message": f"'{path}' has an unsupported file type. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}

    try:
        file_contents = resolved_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return {"success": False, "error": "not_text_file", "message": f"'{path}' does not appear to be a text file and cannot be read."}

    file_chunk = file_contents[offset:offset + max_char]
    if len(file_contents) - offset > len(file_chunk):
        return {
            'success': True,
            'message' : f'file is bigger than {max_char} characters if you wish to read more call tool again with offset = {offset + len(file_chunk)}',
            'contents' : file_chunk
        }
    return {
            'success': True,
            'contents' : file_chunk
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
    {
    "type": "function",
    "function": {
            "name": "read_file",
            "description": "Reads the text contents of a file within the user's sandboxed playground directory, starting at a given character offset. If the file is larger than what's returned, the result will indicate more content remains — call again with a larger offset to continue reading. Absolute paths are not allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to read, relative to the playground root."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "The character position to start reading from. Defaults to 0 (start of file)."
                    },
                    "max_char": {
                        "type": "integer",
                        "description": "Maximum number of characters to return in this read. Defaults to 12000."
                    }
                },
                "required": ["path"]
            }
        }
    }
]

TOOL_REGISTRY = {
    "list_directory": list_directory,
    "read_file" : read_file,

    }