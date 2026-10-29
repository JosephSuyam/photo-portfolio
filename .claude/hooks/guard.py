"""PreToolUse guard: enforces the CLAUDE.md Safety rules for git, secrets, and build output.

Reads the hook payload from stdin. Exit 2 blocks the tool call and shows stderr to Claude.
Messages never echo the service-account key's path.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

GIT_BLOCKLIST = [
    (
        re.compile(
            r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*(\s--force\b|\s--force-with-lease\b|\s-[a-zA-Z]*f\b|\s\+\S)"
        ),
        "force-push rewrites remote history; ask the user to run it",
    ),
    (
        re.compile(r"\bgit\b[^;&|\n]*\breset\b[^;&|\n]*\s--hard\b"),
        "git reset --hard discards uncommitted work in the main checkout",
    ),
    (
        re.compile(r"\bgit\b[^;&|\n]*\bcheckout\b[^;&|\n]*\s--\s+\.(?=\s|$)"),
        "git checkout -- . discards uncommitted work in the main checkout",
    ),
    (
        re.compile(r"\bgit\b[^;&|\n]*\bclean\b[^;&|\n]*\s-[a-zA-Z]*f"),
        "git clean -f deletes untracked files; ask the user first",
    ),
]
GIT_COMMIT = re.compile(r"\bgit\b[^;&|\n]*\bcommit\b")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
PROTECTED_BRANCHES = {"main", "develop"}

# Mirrors the secret patterns in .gitignore.
SECRET_IN_COMMAND = re.compile(
    r"\.env(?!\.example)(?![\w-])|service-account[^\s'\"]*\.json|-[0-9a-f]{4}[^\s'\"/\\]*\.json|\.pem(?![\w-])"
)
SECRET_NAME = re.compile(r"^\.env(\..+)?$|^service-account.*\.json$|-[0-9a-f]{4}.*\.json$|\.pem$")
ALLOWED_NAMES = {".env.example"}

# shortcut: relative-path deletes only (not $PWD/dist or redirects); extend on a real miss
DELETE_BUILD_OUTPUT = re.compile(
    r"\b(rm|rmdir|rd|del|Remove-Item)\b[^;&|\n]*(?:^|[\s'\"])(?:\./)?(dist|\.cache)(?=$|[\s'\"/\\])"
)
BUILD_OUTPUT_DIRS = ("dist", ".cache")

PATH_KEYS = ("file_path", "notebook_path", "path", "glob")
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def key_path() -> Path | None:
    value = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    return Path(value).expanduser().resolve() if value else None


def current_branch(cwd: str) -> str:
    result = subprocess.run(
        ["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def merge_in_progress(cwd: str) -> bool:
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def check_command(command: str, cwd: str) -> str | None:
    # Git rules skip quoted text so commit messages that mention them don't trigger a block.
    unquoted = QUOTED.sub("''", command)
    for pattern, reason in GIT_BLOCKLIST:
        if pattern.search(unquoted):
            return reason
    if GIT_COMMIT.search(unquoted):
        branch = current_branch(cwd)
        if branch in PROTECTED_BRANCHES and not merge_in_progress(cwd):
            return f"no commits on {branch}; run `git switch -c <type>/<slug>` on its own first"
    key = key_path()
    if SECRET_IN_COMMAND.search(command) or (key and key.name in command):
        return "commands must not touch .env or the service-account key"
    if DELETE_BUILD_OUTPUT.search(command):
        return "never hand-delete dist/ or .cache/; `portfolio build`/`sync` manage them"
    return None


def check_path(tool: str, raw: str, project: Path) -> str | None:
    path = (project / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    key = key_path()
    if (SECRET_NAME.search(path.name) and path.name not in ALLOWED_NAMES) or (key and path == key):
        return "access to .env or the service-account key is blocked"
    if tool in EDIT_TOOLS and path.is_relative_to(project):
        top = path.relative_to(project).parts[:1]
        if top and top[0] in BUILD_OUTPUT_DIRS:
            return "never hand-edit dist/ or .cache/; `portfolio build`/`sync` manage them"
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd).resolve()

    reason = None
    command = tool_input.get("command")
    if isinstance(command, str):
        reason = check_command(command, cwd)
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if reason is None and isinstance(value, str) and value:
            reason = check_path(tool, value, project)

    if reason:
        print(f"Blocked by .claude/hooks/guard.py: {reason}.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
