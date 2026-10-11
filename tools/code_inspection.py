import ast
import re
from importlib import metadata
from settings.config import PROJ_DIR
from ._common import (
    resolve_in_playground, to_relative, is_safe_entry,
    parse_bool, TEXT_EXTENSIONS
)

MAX_SCAN_FILE_BYTES = 2 * 1024 * 1024
MAX_TODO_RESULTS = 200
TODO_PATTERN = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b[:\s-]*(.*)')
#matches lines like "numpy==2.5.4", "requests>=2.0", "piper-tts"
REQUIREMENT_PATTERN = re.compile(
    r'^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)\s*(?:\[[^\]]*\])?\s*(?:(==|>=|<=|~=|!=|>|<)\s*([^\s;#,]+))?'
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lint_file",
            "description": "Checks a Python (.py) file in the sandboxed playground for syntax errors and reports the line and reason for the first one found. It only parses the code; it never runs it, and it cannot detect logic bugs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the .py file, relative to the playground root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dependencies",
            "description": "Compares the Orion project's requirements.txt against the packages actually installed in Orion's Python environment, and reports any that are missing or installed at a different version than required.",
            "parameters": {
                "type": "object",
                "properties": {
                    "show_all": {
                        "type": "boolean",
                        "description": "If true, list every dependency. If false (default), only list ones with problems."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "todo_scanner",
            "description": "Searches text and code files in the sandboxed playground (including subfolders) for TODO, FIXME, HACK, and XXX comments, and lists each one with its file and line number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or folder to scan, relative to the playground root. Defaults to '.' (the whole playground)."
                    }
                },
                "required": []
            }
        }
    },
]


#Tool to syntax-check a Python file without executing it
def lint_file(path):
    resolved, err = resolve_in_playground(path)
    if err:
        return err
    if not resolved.is_file():
        return {
            "success": False,
            "error": "not_a_file",
            "message": f"'{path}' is not a file. Provide the path to a .py file."
        }
    if resolved.suffix.lower() != '.py':
        return {
            "success": False,
            "error": "unsupported_file_type",
            "message": f"'{path}' is not a Python file. Only .py files can be syntax-checked."
        }

    try:
        source = resolved.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return {
            "success": False,
            "error": "not_text_file",
            "message": f"'{path}' could not be read as text."
        }

    rel = to_relative(resolved)

    #ast.parse only builds a syntax tree from the text. Nothing in the file is ever executed.
    try:
        ast.parse(source, filename=rel)
    except SyntaxError as e:
        #finding a syntax error means the check worked, so success stays True
        return {
            "success": True,
            "valid": False,
            "path": rel,
            "line": e.lineno,
            "column": e.offset,
            "error_message": e.msg,
            "code": (e.text or '').strip(),
            "message": f"'{rel}' has a syntax error on line {e.lineno}: {e.msg}."
        }
    except ValueError as e:
        return {
            "success": False,
            "error": "unparseable_file",
            "message": f"'{rel}' could not be parsed: {e}"
        }

    return {
        "success": True,
        "valid": True,
        "path": rel,
        "message": f"'{rel}' has no syntax errors. This only checks syntax, not whether the code works correctly."
    }


#Tool to compare requirements.txt against what's actually installed
def list_dependencies(show_all=False):
    show_all, err = parse_bool(show_all, 'show_all')
    if err:
        return err

    #fixed file, no model-supplied path: same reasoning as git_status for leaving the sandbox
    requirements_file = PROJ_DIR / 'requirements.txt'
    if not requirements_file.is_file():
        return {
            "success": False,
            "error": "not_found",
            "message": "No requirements.txt was found at the Orion project root."
        }

    entries = []
    for raw_line in requirements_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('#', 1)[0].strip()
        #skip blank lines and pip options like '-r other.txt' or '-e .'
        if not line or line.startswith('-'):
            continue
        match = REQUIREMENT_PATTERN.match(line)
        if not match:
            continue
        name, operator, required_version = match.group(1), match.group(2), match.group(3)

        try:
            installed_version = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed_version = None

        if installed_version is None:
            status = "missing"
        elif operator == '==' and installed_version != required_version:
            status = "version_mismatch"
        else:
            status = "ok"

        entries.append({
            "name": name,
            "required": f"{operator}{required_version}" if operator else "any",
            "installed": installed_version,
            "status": status
        })

    problems = [e for e in entries if e["status"] != "ok"]
    message = f"Checked {len(entries)} dependencies: {len(problems)} with problems."

    return {
        "success": True,
        "total": len(entries),
        "problem_count": len(problems),
        "dependencies": entries if show_all else problems,
        "message": message
    }


#Tool to collect TODO/FIXME-style comments
def todo_scanner(path='.'):
    root, err = resolve_in_playground(path)
    if err:
        return err

    targets = [root] if root.is_file() else root.rglob('*')
    results = []
    truncated = False

    for entry in targets:
        if not entry.is_file() or not is_safe_entry(entry):
            continue
        if entry.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if entry.stat().st_size > MAX_SCAN_FILE_BYTES:
            continue
        try:
            with open(entry, 'r', encoding='utf-8') as file:
                for line_number, line in enumerate(file, start=1):
                    match = TODO_PATTERN.search(line)
                    if match:
                        results.append({
                            "file": to_relative(entry),
                            "line": line_number,
                            "tag": match.group(1),
                            "text": match.group(2).strip()[:200]
                        })
                        if len(results) >= MAX_TODO_RESULTS:
                            truncated = True
                            break
        except (UnicodeDecodeError, PermissionError):
            continue
        if truncated:
            break

    if not results:
        message = "No TODO, FIXME, HACK, or XXX comments were found."
    else:
        message = f"Found {len(results)} comment(s)."
        if truncated:
            message += f" Stopped at {MAX_TODO_RESULTS}; scan a smaller folder to see the rest."

    return {
        "success": True,
        "count": len(results),
        "items": results,
        "truncated": truncated,
        "message": message
    }


TOOL_REGISTRY = {
    "lint_file": {'function': lint_file, 'mutating': False},
    "list_dependencies": {'function': list_dependencies, 'mutating': False},
    "todo_scanner": {'function': todo_scanner, 'mutating': False},
}
