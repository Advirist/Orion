import os
from pathlib import Path
from settings.config import TESTING_DIR
import fnmatch
from datetime import datetime, timedelta, timezone

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
                    "path": {
                        "type": "string",
                        "description": "The directory path to list, relative to the playground root. Defaults to the current directory '.' if not specified by the user. Absolute paths are not allowed."
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
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "write_file",
    #         "description": "Writes text content to a file within the user's sandboxed playground directory. This always replaces the file's entire contents — it does not append. If the target file already exists, the user will be asked to confirm before it is overwritten, and its previous contents will be permanently lost. To add to an existing file rather than replace it, first read the file's current contents, then call this tool with file_content set to the old content plus the new content combined. The target directory must already exist. Absolute paths are not allowed.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "path": {
    #                     "type": "string",
    #                     "description": "The directory the file should be written into, relative to the playground root. This directory must already exist; use '.' for the playground root itself."
    #                 },
    #                 "filename": {
    #                     "type": "string",
    #                     "description": "The name of the file to write, including its extension (e.g. 'notes.txt')."
    #                 },
    #                 "file_content": {
    #                     "type": "string",
    #                     "description": "The full text content to write into the file. This replaces anything already in the file — it is not appended. If you want to preserve existing content, include it here along with the new content."
    #                 }
    #             },
    #             "required": ["path", "filename", "file_content"]
    #         }
    #     }
    # },
    {
    "type": "function",
    "function": {
        "name": "search_files",
        "description": "Recursively searches for files within the user's sandboxed playground directory (including all subfolders), matching any combination of the given criteria. At least one criterion must be provided. This tool only finds files — it does not read or modify their contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_pattern": {
                    "type": "string",
                    "description": "A filename to match, either exact (e.g. 'notes.txt') or with wildcards (e.g. '*.py' for all Python files, 'test_*' for names starting with 'test_'). Defaults to matching all files if not specified."
                },
                "min_size": {
                    "type": "integer",
                    "description": "Minimum file size in bytes. Files smaller than this are excluded. Optional."
                },
                "max_size": {
                    "type": "integer",
                    "description": "Maximum file size in bytes. Files larger than this are excluded. Optional."
                },
                "file_type": {
                    "type": "string",
                    "description": "File extension to match, with or without a leading dot (e.g. 'py' or '.py'). Optional."
                },
                "modified_within_days": {
                    "type": "integer",
                    "description": "Only include files modified within this many days of now (e.g. 7 for the past week). Optional."
                }
            },
            "required": []
        }
    }
},
]

#Tool to list directories
def list_directory(path='.'):
    #rejects absolute paths, since only paths relative to the playground root are allowed
    if Path(path).is_absolute():
        return {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Only paths relative to the playground root are allowed. Try '.' for the root, or a relative subfolder name."
        }

    #combines and resolves the path so containment can be verified
    relative_path = Path(path)
    combined_path = TESTING_DIR / relative_path
    resolved_path = combined_path.resolve()

    #checks containment FIRST, before touching the filesystem at all,
    #so we never even check existence on a path outside the playground
    if not resolved_path.is_relative_to(TESTING_DIR):
        return {
            "success": False,
            "error": "outside_playground",
            "message": f"'{path}' resolves outside the allowed playground directory. Only paths inside the playground can be listed."
        }

    #checks if the path actually exists on disk
    if not resolved_path.exists():
        return {
            "success": False,
            "error": "not_found",
            "message": f"'{path}' does not exist inside the playground."
        }

    #checks that the path is a directory, not a file
    if not resolved_path.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Provide a directory path to list its contents."
        }

    #attempts to list the directory's contents
    try:
        contents = os.listdir(resolved_path)
        return {
            "success": True,
            #uses relative_to so the full absolute filesystem path is never leaked back to the model
            "path": str(resolved_path.relative_to(TESTING_DIR)),
            "contents": contents
        }
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to read the contents of '{path}'."
        }

#Tool to read files
def read_file(path: str, offset: int = 0, max_char: int = 12000):

    #rejects absolute paths, since only paths relative to the playground root are allowed
    if Path(path).is_absolute():
        return {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Only paths relative to the playground root are allowed. Try '.' for the root, or a relative subfolder name."
        }

    #combines and resolves the path so containment can be verified
    relative_path = Path(path)
    combined_path = TESTING_DIR / relative_path
    resolved_path = combined_path.resolve()

    #checks containment FIRST, before touching the filesystem at all
    if not resolved_path.is_relative_to(TESTING_DIR):
        return {
            "success": False,
            "error": "outside_playground",
            "message": f"'{path}' resolves outside the allowed playground directory. Only files inside the playground can be read."
        }

    #checks if the path actually exists on disk
    if not resolved_path.exists():
        return {
            "success": False,
            "error": "not_found",
            "message": f"'{path}' does not exist inside the playground."
        }

    #checks that the path is a file, not a directory
    if resolved_path.is_dir():
        return {
            "success": False,
            "error": "not_a_file",
            "message": f"'{path}' is a directory, not a file. Provide a file path to read its contents."
        }

    #rejects file types that aren't expected to be plain text
    ALLOWED_EXTENSIONS = {'.txt', '.py', '.md', '.json', '.csv', '.java'}
    if resolved_path.suffix not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "error": "unsupported_file_type",
            "message": f"'{path}' has an unsupported file type. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        }

    #backstop in case a file with an allowed extension still isn't valid text
    try:
        file_contents = resolved_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return {
            "success": False,
            "error": "not_text_file",
            "message": f"'{path}' does not appear to be a text file and cannot be read."
        }

    #returns the requested slice of the file, and reports whether more content remains
    file_chunk = file_contents[offset:offset + max_char]
    if len(file_contents) - offset > len(file_chunk):
        return {
            "success": True,
            "message": f"This file is larger than {max_char} characters. To continue reading, call this tool again with offset={offset + len(file_chunk)}.",
            "contents": file_chunk
        }
    return {
        "success": True,
        "contents": file_chunk
    }

#Tool to write files
def write_file(path: str, filename: str, file_content: str):

    #rejects absolute paths, since only paths relative to the playground root are allowed
    if Path(path).is_absolute():
        return {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Only paths relative to the playground root are allowed. Try '.' for the root, or a relative subfolder name."
        }

    #combines and resolves the path so containment can be verified
    relative_path = Path(path)
    combined_path = TESTING_DIR / relative_path
    resolved_path = combined_path.resolve()

    #checks containment FIRST, before touching the filesystem at all
    if not resolved_path.is_relative_to(TESTING_DIR):
        return {
            "success": False,
            "error": "outside_playground",
            "message": f"'{path}' resolves outside the allowed playground directory. Files can only be written inside the playground."
        }

    #checks that the target directory actually exists (directories are not auto-created)
    if not resolved_path.exists():
        return {
            "success": False,
            "error": "not_found",
            "message": f"The directory '{path}' does not exist inside the playground. Create it first, or choose an existing directory."
        }

    #checks that the target is a directory, not a file
    if not resolved_path.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Provide a directory path to write the file into."
        }

    file_path = resolved_path / filename

    #if the file already exists, ask for explicit confirmation before overwriting it
    if file_path.exists():
        while True:
            user_confirmation = input(f"'{filename}' already exists in '{path}'. Overwrite it? (yes/no): ")
            if user_confirmation.lower() == 'yes':
                try:
                    with open(file_path, 'w') as file:
                        file.write(file_content)
                    return {
                        "success": True,
                        "message": f"'{filename}' was overwritten successfully."
                    }
                except PermissionError:
                    return {
                        "success": False,
                        "error": "permission_denied",
                        "message": f"Permission denied when trying to write to '{filename}'. Let the user know and ask them to clarify how they'd like to proceed."
                    }
            elif user_confirmation.lower() == 'no':
                return {
                    "success": False,
                    "error": "user_cancelled",
                    "message": f"The user declined to overwrite '{filename}'. Let them know and ask how they'd like to proceed."
                }
            else:
                print("Please enter 'yes' or 'no'.")

    #file doesn't exist yet — confirm before creating it
    while True:
        user_confirmation = input(f"Create new file '{filename}' in '{path}'? (yes/no): ")
        if user_confirmation.lower() == 'yes':
            try:
                with open(file_path, 'w') as file:
                    file.write(file_content)
                return {
                    "success": True,
                    "message": f"'{filename}' was created successfully."
                }
            except PermissionError:
                return {
                    "success": False,
                    "error": "permission_denied",
                    "message": f"Permission denied when trying to create '{filename}'. Let the user know and ask them to clarify how they'd like to proceed."
                }
        elif user_confirmation.lower() == 'no':
            return {
                "success": False,
                "error": "user_cancelled",
                "message": f"The user declined to create '{filename}'. Let them know and ask how they'd like to proceed."
            }
        else:
            print("Please enter 'yes' or 'no'.")

def search_files(name_pattern : str = '*', min_size : int = None, max_size : int = None, file_type : str = None, modified_within_days : int = None):

    def is_modified_recently(file: Path, days: int) -> bool:
        last_modified_time = file.stat().st_mtime
        
        file_datetime = datetime.fromtimestamp(last_modified_time, tz=timezone.utc)
        
        current_datetime = datetime.now(timezone.utc)
        
        threshold_datetime = current_datetime - timedelta(days=days)
        
        return file_datetime >= threshold_datetime

    criteria = (min_size, max_size, file_type, modified_within_days)
    
    if all(v is None for v in criteria) and name_pattern == '*':
        return {
            "success" : False,
            "error" : "no_input",
            "message" : "You provided no input on what kind of file you were looking for you must provide at least one parameter to find a file"
            }
    results = []
    dir = TESTING_DIR
    for item in dir.rglob(name_pattern):
        if item.is_file():
            if min_size is not None and item.stat().st_size < min_size:
                continue
            if max_size is not None and item.stat().st_size > max_size:
                continue
            if file_type is not None:
                normalized_type = f".{file_type.lower().lstrip('.')}"
                if item.suffix != normalized_type:
                    continue
            if modified_within_days is not None and not is_modified_recently(item, modified_within_days):
                continue
            results.append(str(item.relative_to(TESTING_DIR)))

    return {
        "success": True,
        "count": len(results),
        "matches": results,
        "message": "No files matched your search criteria." if not results else f"Found {len(results)} file{'s' if len(results) != 1 else ''}."
    }

TOOL_REGISTRY = {
    "list_directory": {'function': list_directory, 'mutating': False},
    "read_file": {'function': read_file, 'mutating': False},
    #"write_file": {'function': write_file, 'mutating': False},
    "search_files": {'function': search_files, 'mutating': False},
}
