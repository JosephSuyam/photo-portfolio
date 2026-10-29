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
# `commit` as git's subcommand, after any global options (-C <dir>, -c <key=value>, --flags)
GIT_COMMIT = re.compile(r"\bgit(?:\s+(?:-[Cc]\s+\S+|--?[\w-]+(?:=\S+)?))*\s+commit(?![\w.-])")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")

# Merges into main and deploys need the user's confirmation ("ask"), even in auto mode.
GIT_MERGE = re.compile(r"\bgit\b[^;&|\n]*\bmerge(?![\w-])")
GIT_PUSH = re.compile(r"\bgit\b[^;&|\n]*\bpush\b")
SWITCH_TO_MAIN = re.compile(r"\bgit\b[^;&|\n]*\b(switch|checkout)\s+main(?![\w/-])")
PUSH_TO_MAIN = re.compile(r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*[\s:/]main(?![\w/-])")
PUSH_ALL = re.compile(r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*\s--(all|mirror)\b")
GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b([^;&|\n]*)")
DEPLOY = re.compile(r"\bgh\s+workflow\s+run\b[^;&|\n]*\bdeploy|\bvercel\b[^;&|\n]*\bdeploy\b")
PROTECTED_BRANCHES = {"main", "develop"}

# Service-account keys are named <project>-<12 hex>.json; .gitignore is broader on purpose.
SECRET_IN_COMMAND = re.compile(
    r"\.env(?!\.example)(?![\w-])|service-account[^\s'\"]*\.json|-[0-9a-f]{12}\.json|\.pem(?![\w-])"
)
SECRET_NAME = re.compile(r"^\.env(\..+)?$|^service-account.*\.json$|-[0-9a-f]{12}\.json$|\.pem$")
ALLOWED_NAMES = {".env.example"}
# Printing the environment or the credentials variable would show the key's path.
ENV_DUMP = re.compile(
    r"\$\{?GOOGLE_APPLICATION_CREDENTIALS|\$env:GOOGLE_APPLICATION_CREDENTIALS"
    r"|\b(printenv|environ|getenv)\b[^;&|\n]*GOOGLE_APPLICATION_CREDENTIALS"
    r"|(?:^|[;&|(]\s*)(printenv|env|set|export\s+-p)\s*(?=$|[;&|)])"
    r"|\b(Get-ChildItem|gci|dir|ls)\s+env:",
    re.IGNORECASE | re.MULTILINE,
)

# shortcut: relative-path deletes only (not $PWD/dist or redirects); extend on a real miss
DELETE_BUILD_OUTPUT = re.compile(
    r"\b(rm|rmdir|rd|del|Remove-Item)\b[^;&|\n]*(?:^|[\s'\"])(?:\.[/\\])?(dist|\.cache)(?=$|[\s'\"/\\])"
)
BUILD_OUTPUT_DIRS = ("dist", ".cache")

MESSAGE_HINT = (
    " If this only matched message text, write the text to .tmp/ and pass it with"
    " `git commit -F <file>` or `gh ... --body-file <file>`"
)
PATH_KEYS = ("file_path", "notebook_path", "path", "glob")
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def key_path() -> Path | None:
    value = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    return Path(value).expanduser().resolve() if value else None


def git(cwd: str, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, check=False
        )
    except OSError:
        return None


def current_branch(cwd: str) -> str:
    result = git(cwd, "branch", "--show-current")
    return result.stdout.strip() if result else ""


def merge_in_progress(cwd: str) -> bool:
    result = git(cwd, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    return result is not None and result.returncode == 0


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
        return "commands must not touch .env or the service-account key." + MESSAGE_HINT
    if ENV_DUMP.search(command):
        return "printing the environment would show the service-account key's path." + MESSAGE_HINT
    if DELETE_BUILD_OUTPUT.search(command):
        return (
            "never hand-delete dist/ or .cache/; `portfolio build`/`sync` manage them."
            + MESSAGE_HINT
        )
    return None


def pr_base(merge_args: str, cwd: str) -> str | None:
    # shortcut: only a PR number or URL is read as the selector, else gh uses the current branch
    selector = re.findall(r"(?<!\S)(\d+|https://\S+)(?!\S)", merge_args)[:1]
    command = ["gh", "pr", "view", *selector, "--json", "baseRefName", "-q", ".baseRefName"]
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, check=False, timeout=20
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def needs_confirmation(command: str, cwd: str) -> str | None:
    unquoted = QUOTED.sub("''", command)
    git_merge = GIT_MERGE.search(unquoted)
    git_push = GIT_PUSH.search(unquoted)
    if git_merge or git_push:
        on_main = current_branch(cwd) == "main"
        if git_merge and (on_main or SWITCH_TO_MAIN.search(unquoted)):
            return "this merges into main"
        if git_push and (on_main or PUSH_TO_MAIN.search(unquoted)):
            return "this pushes to main, which deploys the site"
        if PUSH_ALL.search(unquoted):
            return "this pushes all branches, including main, which deploys the site"
    gh_merge = GH_PR_MERGE.search(unquoted)
    if gh_merge and pr_base(gh_merge.group(1), cwd) in (None, "main"):
        return "this merges a PR into main (or its base could not be checked)"
    if DEPLOY.search(unquoted):
        return "this deploys the site"
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
    payload = json.loads(sys.stdin.buffer.read())
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    if not isinstance(tool_input, dict):
        return 0
    tool = payload.get("tool_name", "")
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
    confirm = needs_confirmation(command, cwd) if isinstance(command, str) else None
    if confirm:
        decision = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"Needs your confirmation: {confirm}.",
        }
        print(json.dumps({"hookSpecificOutput": decision}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
