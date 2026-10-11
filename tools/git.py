import re
import subprocess
from pathlib import Path
from settings.config import PROJ_DIR
from storage.errors import subprocess_log_error
from ._common import parse_int, parse_bool, truncate

GIT_TIMEOUT_SECONDS = 30
MAX_LOG_ENTRIES = 50
MAX_BLAME_LINES = 200

#Allowed commit references: HEAD, HEAD~N, or a hex commit hash (short or full).
#Anything else (branch names, ranges, anything starting with '-') is rejected
#rather than handed to git, so the model can't sneak extra flags in.
COMMIT_REF_PATTERN = re.compile(r'^(HEAD(~\d{1,3})?|[0-9a-fA-F]{4,40})$')

REPO_ROOT = PROJ_DIR.resolve()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Runs 'git status' on the Orion project's own repository (not the sandboxed playground) and reports which files are staged, modified, or untracked. Read-only.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Shows recent commit history of the Orion project repository, one commit per line: short hash | date | author | message. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_count": {
                        "type": "integer",
                        "description": "How many recent commits to show, from 1 to 50. Defaults to 10."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Shows uncommitted changes (work not yet committed). It does NOT show past commits; use git_show for those.",
            "parameters": {
                "type": "object",
                "properties": {
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show staged changes instead of unstaged ones. Defaults to false."
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional file or folder, relative to the repository root (e.g. 'orion.py'), to limit the diff to."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "Lists local branches of the Orion project repository, marking the current branch with '*' and showing each branch's latest commit. Read-only.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_show",
            "description": "Shows a past commit: author, date, message, and changed files. Use this for any question about ‘my last commit’ or an earlier one. Set include_patch to true for the full line-by-line changes. Defaults to the latest commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commit": {
                        "type": "string",
                        "description": "Which commit to show: 'HEAD' for the latest, 'HEAD~1' for the one before it (up to HEAD~999), or a commit hash like 'a1b2c3d' from git_log. Defaults to 'HEAD'."
                    },
                    "include_patch": {
                        "type": "boolean",
                        "description": "If true, include the full line-by-line changes, not just the list of changed files. Defaults to false."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_blame",
            "description": "Shows, for each line of a file in the Orion project repository, which commit and author last changed it and when. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File to inspect, relative to the repository root (e.g. 'tools/git.py')."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional first line to include (1-based)."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional last line to include. At most 200 lines are shown per call."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_stash_list",
            "description": "Lists any stashed (temporarily saved, uncommitted) changes in the Orion project repository. Read-only.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]


#runs one git command and converts the result into the standard tool-result shape
def _run_git(args, success_message, empty_message):
    try:
        result = subprocess.run(
            ['git', *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS
        )
    except FileNotFoundError:
        return {
            "success": False,
            "error": "git_not_found",
            "message": "git does not appear to be installed or is not on the system PATH. Let the user know git isn't available."
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "timeout_error",
            "message": f"'git {args[0]}' took longer than {GIT_TIMEOUT_SECONDS} seconds and was cancelled."
        }

    if result.returncode != 0:
        message = f"git {args[0]} failed (exit code {result.returncode}): {result.stderr.strip() or 'no error output was provided.'}"
        subprocess_log_error(result.stdout, result.stderr, 'git_command_failed', message)
        return {"success": False, "error": "git_command_failed", "message": message}

    if not result.stdout.strip():
        return {"success": True, "output": "", "truncated": False, "message": empty_message}

    output, truncated = truncate(result.stdout)
    if truncated:
        success_message += " The output was long and has been cut off."
    return {"success": True, "output": output, "truncated": truncated, "message": success_message}


#validates a model-supplied path so it stays inside the repository
def _validate_repo_path(path):
    if not isinstance(path, str) or not path.strip():
        return None, {
            "success": False,
            "error": "invalid_path",
            "message": "A non-empty file path relative to the repository root is required."
        }
    if path.startswith('-'):
        return None, {
            "success": False,
            "error": "invalid_path",
            "message": f"'{path}' is not a valid path. Paths may not start with '-'."
        }
    if Path(path).is_absolute():
        return None, {
            "success": False,
            "error": "absolute_path_rejected",
            "message": f"'{path}' is an absolute path. Use a path relative to the repository root, like 'orion.py'."
        }
    resolved = (REPO_ROOT / path).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        return None, {
            "success": False,
            "error": "outside_repository",
            "message": f"'{path}' resolves outside the Orion repository."
        }
    return str(resolved.relative_to(REPO_ROOT)), None


def git_status():
    return _run_git(
        ['status'],
        "Retrieved the current git status of the Orion project repository.",
        "git status returned no output."
    )


def git_log(max_count=10):
    max_count, err = parse_int(max_count, 'max_count')
    if err:
        return err
    max_count = max(1, min(max_count, MAX_LOG_ENTRIES))
    return _run_git(
        ['log', f'--max-count={max_count}', '--date=short', '--pretty=format:%h | %ad | %an | %s'],
        f"Retrieved the last {max_count} commit(s), newest first.",
        "This repository has no commits yet."
    )


def git_diff(staged=False, path=None):
    staged, err = parse_bool(staged, 'staged')
    if err:
        return err

    args = ['diff', '--no-color']
    if staged:
        args.append('--staged')

    if path:
        rel_path, err = _validate_repo_path(path)
        if err:
            return err
        #'--' tells git everything after it is a path, never an option
        args += ['--', rel_path]

    which = "staged" if staged else "unstaged"
    scope = f" in '{path}'" if path else ""
    return _run_git(
        args,
        f"Retrieved {which} changes{scope}.",
        f"There are no {which} changes{scope}."
    )


def git_branch():
    return _run_git(
        ['branch', '-vv', '--no-color'],
        "Retrieved local branches. The current branch is marked with '*'.",
        "No branches were found."
    )


def git_show(commit='HEAD', include_patch=False):
    if not isinstance(commit, str) or not COMMIT_REF_PATTERN.match(commit.strip()):
        return {
            "success": False,
            "error": "invalid_commit",
            "message": f"'{commit}' is not an accepted commit reference. Use 'HEAD', 'HEAD~N', or a commit hash from git_log."
        }
    include_patch, err = parse_bool(include_patch, 'include_patch')
    if err:
        return err

    commit = commit.strip()
    args = ['show', '--no-color', '--date=short']
    if not include_patch:
        args.append('--stat')
    args.append(commit)

    return _run_git(
        args,
        f"Retrieved details for commit '{commit}'.",
        f"git show returned no output for '{commit}'."
    )


def git_blame(path, start_line=None, end_line=None):
    rel_path, err = _validate_repo_path(path)
    if err:
        return err

    args = ['blame', '--date=short']

    if start_line is not None or end_line is not None:
        start, err = parse_int(start_line if start_line is not None else 1, 'start_line')
        if err:
            return err
        end, err = parse_int(end_line if end_line is not None else start + MAX_BLAME_LINES - 1, 'end_line')
        if err:
            return err
        if start < 1 or end < start:
            return {
                "success": False,
                "error": "invalid_line_range",
                "message": f"Line range {start}-{end} is invalid. start_line must be at least 1 and no greater than end_line."
            }
        end = min(end, start + MAX_BLAME_LINES - 1)
        args += ['-L', f'{start},{end}']

    args += ['--', rel_path]
    return _run_git(
        args,
        f"Retrieved line-by-line history for '{rel_path}'.",
        f"git blame returned no output for '{rel_path}'."
    )


def git_stash_list():
    return _run_git(
        ['stash', 'list'],
        "Retrieved the list of stashed changes.",
        "There are no stashed changes."
    )


TOOL_REGISTRY = {
    "git_status": {'function': git_status, 'mutating': False},
    "git_log": {'function': git_log, 'mutating': False},
    "git_diff": {'function': git_diff, 'mutating': False},
    "git_branch": {'function': git_branch, 'mutating': False},
    "git_show": {'function': git_show, 'mutating': False},
    "git_blame": {'function': git_blame, 'mutating': False},
    "git_stash_list": {'function': git_stash_list, 'mutating': False},
}
