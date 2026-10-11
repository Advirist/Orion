import difflib
import hashlib
from datetime import datetime
from ._common import (
    resolve_in_playground, to_relative, is_safe_entry,
    parse_int, truncate, TEXT_EXTENSIONS
)

MAX_TREE_DEPTH = 6
MAX_TREE_ENTRIES = 300
MAX_LINE_COUNT_BYTES = 20 * 1024 * 1024
MAX_DIFF_FILE_BYTES = 2 * 1024 * 1024
MAX_HASH_FILE_BYTES = 50 * 1024 * 1024
MAX_FILES_SCANNED = 5000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "directory_tree",
            "description": "Shows the nested folder structure of a directory inside the sandboxed playground as an indented tree, including subfolders. Use this to get an overview of how files are organized; use list_directory for just one level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to start from, relative to the playground root. Defaults to '.' (the playground root)."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "How many folder levels deep to show, from 1 to 6. Defaults to 3."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_stats",
            "description": "Reports details about a single file or folder in the sandboxed playground: its size in bytes, when it was last modified, and its line count if it's a text file. Does not show the file's contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file or folder, relative to the playground root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_diff",
            "description": "Compares two text files in the sandboxed playground and shows the lines that differ, in unified diff format (lines starting with '-' are only in the first file, '+' only in the second). Reports if the files are identical.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_a": {
                        "type": "string",
                        "description": "First file to compare, relative to the playground root."
                    },
                    "path_b": {
                        "type": "string",
                        "description": "Second file to compare, relative to the playground root."
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "How many unchanged lines to show around each change, from 0 to 10. Defaults to 3."
                    }
                },
                "required": ["path_a", "path_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_duplicates",
            "description": "Finds files with exactly identical contents anywhere within a directory of the sandboxed playground (searching subfolders too), even if their names differ. Only reports duplicates; it never deletes anything.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to search, relative to the playground root. Defaults to '.' (the whole playground)."
                    },
                    "min_size": {
                        "type": "integer",
                        "description": "Ignore files smaller than this many bytes. Defaults to 1, which skips empty files."
                    }
                },
                "required": []
            }
        }
    },
]


#Tool to show nested folder structure
def directory_tree(path='.', max_depth=3):
    root, err = resolve_in_playground(path)
    if err:
        return err
    if not root.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Provide a directory path."
        }

    max_depth, err = parse_int(max_depth, 'max_depth')
    if err:
        return err
    max_depth = max(1, min(max_depth, MAX_TREE_DEPTH))

    lines = [f"{to_relative(root)}/"]
    state = {"count": 0, "truncated": False}

    #walks one directory at a time, indenting by depth, folders listed before files
    def walk(directory, depth):
        if depth > max_depth or state["truncated"]:
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            lines.append("  " * depth + "[permission denied]")
            return

        for child in children:
            if state["count"] >= MAX_TREE_ENTRIES:
                state["truncated"] = True
                return
            if not is_safe_entry(child):
                continue
            state["count"] += 1
            if child.is_dir():
                lines.append("  " * depth + child.name + "/")
                walk(child, depth + 1)
            else:
                lines.append("  " * depth + child.name)

    walk(root, 1)

    message = f"Listed {state['count']} entries, up to {max_depth} level(s) deep."
    if state["truncated"]:
        message += f" Stopped at {MAX_TREE_ENTRIES} entries; try a subfolder or a smaller max_depth to see the rest."

    return {
        "success": True,
        "path": to_relative(root),
        "tree": "\n".join(lines),
        "entry_count": state["count"],
        "truncated": state["truncated"],
        "message": message
    }


#Tool to report size, modified time, and line count
def file_stats(path):
    resolved, err = resolve_in_playground(path)
    if err:
        return err

    try:
        stat = resolved.stat()
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to read details of '{path}'."
        }

    rel = to_relative(resolved)
    result = {
        "success": True,
        "path": rel,
        "last_modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec='seconds'),
    }

    if resolved.is_dir():
        result["type"] = "directory"
        try:
            result["item_count"] = sum(1 for _ in resolved.iterdir())
        except PermissionError:
            result["item_count"] = None
        result["message"] = f"'{rel}' is a directory containing {result['item_count']} item(s)."
        return result

    result["type"] = "file"
    result["size_bytes"] = stat.st_size

    #line counting only for known text types, and only if the file isn't huge
    result["line_count"] = None
    if resolved.suffix.lower() in TEXT_EXTENSIONS and stat.st_size <= MAX_LINE_COUNT_BYTES:
        try:
            with open(resolved, 'r', encoding='utf-8') as file:
                result["line_count"] = sum(1 for _ in file)
        except (UnicodeDecodeError, PermissionError):
            pass

    result["message"] = f"Retrieved details for '{rel}'."
    return result


#Tool to compare two text files line by line
def file_diff(path_a, path_b, context_lines=3):
    files = []
    for raw_path in (path_a, path_b):
        resolved, err = resolve_in_playground(raw_path)
        if err:
            return err
        if not resolved.is_file():
            return {
                "success": False,
                "error": "not_a_file",
                "message": f"'{raw_path}' is not a file. Both paths must point to files."
            }
        if resolved.stat().st_size > MAX_DIFF_FILE_BYTES:
            return {
                "success": False,
                "error": "file_too_large",
                "message": f"'{raw_path}' is larger than {MAX_DIFF_FILE_BYTES // (1024 * 1024)} MB and is too big to compare."
            }
        try:
            text = resolved.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return {
                "success": False,
                "error": "not_text_file",
                "message": f"'{raw_path}' does not appear to be a text file, so it can't be compared line by line."
            }
        files.append((to_relative(resolved), text))

    context_lines, err = parse_int(context_lines, 'context_lines')
    if err:
        return err
    context_lines = max(0, min(context_lines, 10))

    (name_a, text_a), (name_b, text_b) = files
    diff_lines = difflib.unified_diff(
        text_a.splitlines(), text_b.splitlines(),
        fromfile=name_a, tofile=name_b, n=context_lines, lineterm=''
    )
    diff_text = "\n".join(diff_lines)

    if not diff_text:
        return {
            "success": True,
            "identical": True,
            "diff": "",
            "message": f"'{name_a}' and '{name_b}' have identical contents."
        }

    diff_text, truncated = truncate(diff_text)
    message = f"'{name_a}' and '{name_b}' differ."
    if truncated:
        message += " The diff was long and has been cut off."

    return {
        "success": True,
        "identical": False,
        "diff": diff_text,
        "truncated": truncated,
        "message": message
    }


def _sha256(file_path):
    #reads in chunks so large files never need to fit in memory at once
    digest = hashlib.sha256()
    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


#Tool to find files with identical contents
def find_duplicates(path='.', min_size=1):
    root, err = resolve_in_playground(path)
    if err:
        return err
    if not root.is_dir():
        return {
            "success": False,
            "error": "not_a_directory",
            "message": f"'{path}' is a file, not a directory. Provide a directory to search."
        }

    min_size, err = parse_int(min_size, 'min_size')
    if err:
        return err
    min_size = max(0, min_size)

    #step 1: group by size. Files with different sizes can't be identical, so this
    #avoids hashing every single file.
    by_size = {}
    scanned = 0
    skipped_large = 0
    scan_limited = False
    for entry in root.rglob('*'):
        if scanned >= MAX_FILES_SCANNED:
            scan_limited = True
            break
        if not entry.is_file() or not is_safe_entry(entry):
            continue
        scanned += 1
        size = entry.stat().st_size
        if size < min_size:
            continue
        if size > MAX_HASH_FILE_BYTES:
            skipped_large += 1
            continue
        by_size.setdefault(size, []).append(entry)

    #step 2: only hash files that share a size with at least one other file
    groups = []
    for size, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        by_hash = {}
        for entry in candidates:
            try:
                by_hash.setdefault(_sha256(entry), []).append(to_relative(entry))
            except OSError:
                continue
        for paths in by_hash.values():
            if len(paths) > 1:
                groups.append({"size_bytes": size, "files": sorted(paths)})

    if not groups:
        message = f"Scanned {scanned} file(s) and found no duplicates."
    else:
        message = f"Scanned {scanned} file(s) and found {len(groups)} group(s) of duplicate files."
    if skipped_large:
        message += f" Skipped {skipped_large} file(s) over {MAX_HASH_FILE_BYTES // (1024 * 1024)} MB."
    if scan_limited:
        message += f" Stopped after {MAX_FILES_SCANNED} files; search a smaller folder for a complete result."

    return {
        "success": True,
        "files_scanned": scanned,
        "duplicate_groups": groups,
        "message": message
    }


TOOL_REGISTRY = {
    "directory_tree": {'function': directory_tree, 'mutating': False},
    "file_stats": {'function': file_stats, 'mutating': False},
    "file_diff": {'function': file_diff, 'mutating': False},
    "find_duplicates": {'function': find_duplicates, 'mutating': False},
}
