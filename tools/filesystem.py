from pathlib import Path
from datetime import datetime, timedelta, timezone
from settings.config import TESTING_DIR
from ._common import (
    resolve_in_playground, to_relative, is_safe_entry,
    parse_int, TEXT_EXTENSIONS, MAX_OUTPUT_CHARS
)

MAX_LIST_ENTRIES = 500
MAX_READ_CHARS = MAX_OUTPUT_CHARS          #most characters read_file returns per call
MAX_READ_FILE_BYTES = 20 * 1024 * 1024     #read_file refuses text files bigger than this
MAX_SEARCH_RESULTS = 200
MAX_ENTRIES_SCANNED = 20000                #search_files stops walking after this many entries
MAX_DAYS = 36500                           #about 100 years; keeps timedelta from overflowing

#Schema to define tools to assistant
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists what is directly inside one directory of the user's sandboxed playground, with folders and files reported separately. Does not look inside subfolders; use directory_tree for that. Attempts to access paths outside the playground will be rejected with an error.",
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
            "description": "Reads the text contents of a file within the user's sandboxed playground directory, starting at a given character offset, up to 12000 characters per call. If the file is larger than what's returned, the result will indicate more content remains — call again with a larger offset to continue reading. Absolute paths are not allowed.",
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
                        "description": "Maximum number of characters to return in this read, up to 12000. Defaults to 12000."
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
            "description": "Recursively searches for files within the user's sandboxed playground directory (including all subfolders), matching any combination of the given criteria. At least one criterion must be provided. Returns at most 200 matches. This tool only finds files — it does not read or modify their contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_pattern": {
                        "type": "string",
                        "description": "A file name to match, either exact (e.g. 'notes.txt') or with wildcards (e.g. '*.py' for all Python files, 'test_*' for names starting with 'test_'). Matches file names only, not folder paths. Defaults to matching all files if not specified."
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


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


#Tool to list directories
def list_directory(path='.'):
    #an empty path means the playground root; the shared helper handles absolute paths,
    #containment, and existence checks
    resolved, err = resolve_in_playground(path or '.')
    if err:
        return err

    #checks that the path is a directory, not a file
    if not resolved.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Provide a directory path to list its contents."
        }

    folders, files = [], []
    skipped_links = 0
    truncated = False
    try:
        for entry in sorted(resolved.iterdir(), key=lambda p: p.name.lower()):
            #symbolic links can point anywhere on the system, so they are never followed or listed
            if entry.is_symlink():
                skipped_links += 1
                continue
            if len(folders) + len(files) >= MAX_LIST_ENTRIES:
                truncated = True
                break
            (folders if entry.is_dir() else files).append(entry.name)
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to read the contents of '{path}'."
        }

    message = f"Found {_plural(len(folders), 'folder')} and {_plural(len(files), 'file')}."
    if skipped_links:
        message += f" {_plural(skipped_links, 'symbolic link')} not shown."
    if truncated:
        message += f" Stopped after {MAX_LIST_ENTRIES} entries; the directory has more."

    return {
        "success": True,
        #relative path, so the full absolute filesystem path is never leaked back to the model
        "path": to_relative(resolved),
        "folders": folders,
        "files": files,
        "truncated": truncated,
        "message": message
    }


#Tool to read files
def read_file(path: str, offset: int = 0, max_char: int = MAX_READ_CHARS):
    resolved, err = resolve_in_playground(path)
    if err:
        return err

    #checks that the path is a file, not a directory
    if resolved.is_dir():
        return {
            "success": False,
            "error": "not_a_file",
            "message": f"'{path}' is a directory, not a file. Provide a file path to read its contents."
        }

    #rejects file types that aren't expected to be plain text
    if resolved.suffix.lower() not in TEXT_EXTENSIONS:
        return {
            "success": False,
            "error": "unsupported_file_type",
            "message": f"'{path}' has an unsupported file type. Allowed types: {', '.join(sorted(TEXT_EXTENSIONS))}."
        }

    #models sometimes send numbers as text, so these are parsed rather than trusted
    offset, err = parse_int(offset, 'offset')
    if err:
        return err
    max_char, err = parse_int(max_char, 'max_char')
    if err:
        return err
    offset = max(0, offset)
    max_char = max(1, min(max_char, MAX_READ_CHARS))

    try:
        if resolved.stat().st_size > MAX_READ_FILE_BYTES:
            return {
                "success": False,
                "error": "file_too_large",
                "message": f"'{path}' is larger than {MAX_READ_FILE_BYTES // (1024 * 1024)} MB and is too big to read."
            }
        file_contents = resolved.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        #backstop in case a file with an allowed extension still isn't valid text
        return {
            "success": False,
            "error": "not_text_file",
            "message": f"'{path}' does not appear to be a text file and cannot be read."
        }
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to read '{path}'."
        }

    total = len(file_contents)
    if total == 0:
        return {"success": True, "contents": "", "message": f"'{path}' is empty."}
    if offset >= total:
        return {
            "success": True,
            "contents": "",
            "message": f"offset {offset} is past the end of '{path}', which is {total} characters long."
        }

    #returns the requested slice of the file, and reports whether more content remains
    file_chunk = file_contents[offset:offset + max_char]
    end = offset + len(file_chunk)
    if end < total:
        return {
            "success": True,
            "message": f"Returned characters {offset} to {end} of {total}. To continue reading, call this tool again with offset={end}.",
            "contents": file_chunk
        }
    return {
        "success": True,
        "message": "Read the whole file." if offset == 0 else "Reached the end of the file.",
        "contents": file_chunk
    }


#asks until the user answers yes or no
def _confirm(prompt):
    while True:
        answer = input(prompt).strip().lower()
        if answer in ('yes', 'no'):
            return answer == 'yes'
        print("Please enter 'yes' or 'no'.")


#Tool to write files (currently switched off: its schema and registry entry are commented out)
def write_file(path: str, filename: str, file_content: str):
    resolved, err = resolve_in_playground(path, must_exist=False)
    if err:
        return err

    #checks that the target directory actually exists (directories are not auto-created)
    if not resolved.exists():
        return {
            "success": False,
            "error": "not_found",
            "message": f"The directory '{path}' does not exist inside the playground. Create it first, or choose an existing directory."
        }

    #checks that the target is a directory, not a file
    if not resolved.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Provide a directory path to write the file into."
        }

    #the filename must be a plain name, never a path: 'path' was checked above, but a filename
    #like '../../x.txt' would otherwise step back out of the playground
    if (not isinstance(filename, str) or not filename.strip()
            or filename in ('.', '..') or Path(filename).name != filename):
        return {
            "success": False,
            "error": "invalid_filename",
            "message": f"'{filename}' is not a valid file name. Give just a name like 'notes.txt', with no folders in it."
        }
    if not isinstance(file_content, str):
        return {
            "success": False,
            "error": "invalid_argument",
            "message": "file_content must be text."
        }

    file_path = resolved / filename

    #never write through a symbolic link, which could point outside the playground
    if file_path.is_symlink() or not file_path.resolve().is_relative_to(TESTING_DIR):
        return {
            "success": False,
            "error": "outside_playground",
            "message": f"'{filename}' resolves outside the allowed playground directory. Files can only be written inside the playground."
        }

    #asks for explicit confirmation before creating or overwriting
    if file_path.exists():
        confirmed = _confirm(f"'{filename}' already exists in '{path}'. Overwrite it? (yes/no): ")
        action, done = "overwrite", "overwritten"
    else:
        confirmed = _confirm(f"Create new file '{filename}' in '{path}'? (yes/no): ")
        action, done = "create", "created"

    if not confirmed:
        return {
            "success": False,
            "error": "user_cancelled",
            "message": f"The user declined to {action} '{filename}'. Let them know and ask how they'd like to proceed."
        }

    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(file_content)
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to {action} '{filename}'. Let the user know and ask them to clarify how they'd like to proceed."
        }
    return {
        "success": True,
        "message": f"'{filename}' was {done} successfully."
    }


#Tool to search for files by name, size, type, or modification time
def search_files(name_pattern: str = '*', min_size: int = None, max_size: int = None, file_type: str = None, modified_within_days: int = None):
    name_pattern = name_pattern or '*'

    #the pattern matches file NAMES only. A pattern containing a folder path (like '../*.txt')
    #would make the search walk outside the playground.
    if (not isinstance(name_pattern, str) or '/' in name_pattern or '\\' in name_pattern
            or name_pattern in ('.', '..')):
        return {
            "success": False,
            "error": "invalid_pattern",
            "message": f"'{name_pattern}' is not a valid file name pattern. Patterns match file names only, not folder paths; use directory_tree to browse folders."
        }

    #models sometimes send numbers as text, so these are parsed rather than trusted
    if min_size is not None:
        min_size, err = parse_int(min_size, 'min_size')
        if err:
            return err
    if max_size is not None:
        max_size, err = parse_int(max_size, 'max_size')
        if err:
            return err
    cutoff = None
    if modified_within_days is not None:
        modified_within_days, err = parse_int(modified_within_days, 'modified_within_days')
        if err:
            return err
        modified_within_days = max(0, min(modified_within_days, MAX_DAYS))
        cutoff = datetime.now(timezone.utc) - timedelta(days=modified_within_days)

    #the extension is normalized once, so 'py', '.py' and '.PY' all work
    normalized_type = None
    if file_type is not None:
        if not isinstance(file_type, str) or not file_type.strip().lstrip('.'):
            return {
                "success": False,
                "error": "invalid_argument",
                "message": f"'file_type' must be a file extension like 'py', but got '{file_type}'."
            }
        normalized_type = f".{file_type.strip().lower().lstrip('.')}"

    if (min_size is None and max_size is None and normalized_type is None
            and cutoff is None and name_pattern == '*'):
        return {
            "success": False,
            "error": "no_input",
            "message": "No search criteria were given. Provide a file name or pattern, or at least one of: min_size, max_size, file_type, modified_within_days."
        }

    results = []
    scanned = 0
    truncated = False
    scan_limited = False
    for item in TESTING_DIR.rglob(name_pattern):
        scanned += 1
        if scanned > MAX_ENTRIES_SCANNED:
            scan_limited = True
            break
        #symlinks and anything resolving outside the playground are skipped before being examined
        if not is_safe_entry(item) or not item.is_file():
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        if min_size is not None and stat.st_size < min_size:
            continue
        if max_size is not None and stat.st_size > max_size:
            continue
        if normalized_type is not None and item.suffix.lower() != normalized_type:
            continue
        if cutoff is not None and datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc) < cutoff:
            continue
        if len(results) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        results.append(to_relative(item))

    if not results:
        message = "No files matched your search criteria."
    else:
        message = f"Found {_plural(len(results), 'file')}."
    if truncated:
        message += f" Showing only the first {MAX_SEARCH_RESULTS} matches; narrow the search to see others."
    if scan_limited:
        message += f" The search stopped after examining {MAX_ENTRIES_SCANNED} entries."

    return {
        "success": True,
        "count": len(results),
        "matches": sorted(results),
        "truncated": truncated or scan_limited,
        "message": message
    }


TOOL_REGISTRY = {
    "list_directory": {'function': list_directory, 'mutating': False},
    "read_file": {'function': read_file, 'mutating': False},
    #"write_file": {'function': write_file, 'mutating': False},
    "search_files": {'function': search_files, 'mutating': False},
}