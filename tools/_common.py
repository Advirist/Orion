"""Shared helpers used by multiple tool modules.

Every tool that takes a path or a number from the model goes through these,
so the safety checks live in exactly one place instead of being copy-pasted.
"""
from pathlib import Path
from settings.config import TESTING_DIR

MAX_OUTPUT_CHARS = 12000
TEXT_EXTENSIONS = {'.txt', '.py', '.md', '.json', '.csv', '.java'}


def resolve_in_playground(path, must_exist=True):
    """
    Turns a model-supplied relative path into a resolved Path inside the playground.
    Returns (resolved_path, None) on success, or (None, error_dict) on failure, so callers do:
        resolved, err = resolve_in_playground(path)
        if err:
            return err
    """
    if not isinstance(path, str) or not path.strip():
        return None, {
            "success": False,
            "error": "invalid_path",
            "message": "A non-empty path relative to the playground root is required."
        }

    if Path(path).is_absolute():
        return None, {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Only paths relative to the playground root are allowed. Try '.' for the root."
        }

    resolved = (TESTING_DIR / path).resolve()

    #containment is checked before touching the filesystem at all
    if not resolved.is_relative_to(TESTING_DIR):
        return None, {
            "success": False,
            "error": "outside_playground",
            "message": f"'{path}' resolves outside the allowed playground directory."
        }

    if must_exist and not resolved.exists():
        return None, {
            "success": False,
            "error": "not_found",
            "message": f"'{path}' does not exist inside the playground."
        }

    return resolved, None


def to_relative(resolved_path):
    """Converts a resolved path back to a playground-relative string so absolute paths never reach the model."""
    return str(resolved_path.relative_to(TESTING_DIR))


def is_safe_entry(entry):
    """
    Used when walking directories recursively. A symlink inside the playground could
    point anywhere on the system, so symlinks are skipped and every discovered path is
    re-checked for containment.
    """
    if entry.is_symlink():
        return False
    return entry.resolve().is_relative_to(TESTING_DIR)


def parse_int(value, name):
    """Models sometimes send numbers as strings. Accepts '5' but rejects 'five'."""
    if isinstance(value, bool):
        return None, _invalid(name, value, "a whole number")
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, _invalid(name, value, "a whole number")


def parse_bool(value, name):
    """Accepts real booleans plus the strings 'true'/'false', since models aren't always consistent."""
    if isinstance(value, bool):
        return value, None
    if isinstance(value, int) and value in (0, 1):
        return bool(value), None
    if isinstance(value, str) and value.strip().lower() in ('true', 'false'):
        return value.strip().lower() == 'true', None
    return None, _invalid(name, value, "true or false")


def truncate(text, limit=MAX_OUTPUT_CHARS):
    """Caps long output so one tool call can't flood the model's context window."""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _invalid(name, value, expected):
    return {
        "success": False,
        "error": "invalid_argument",
        "message": f"'{name}' must be {expected}, but got '{value}'."
    }
