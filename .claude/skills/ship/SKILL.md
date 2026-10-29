---
name: ship
description: Push the current feature branch, open a pull request into develop, wait for CI, and merge it when green. Use only when the user says /ship, "ship it", or asks to open a PR or merge a finished branch through GitHub.
argument-hint: [PR title]
---

# Ship

Invoking this skill is the user's approval to push this branch, open its PR into `develop`, and merge it after CI passes. It never targets `main`, never force-pushes, and never deploys.

1. **Preflight** (stop and report on any failure):
   - `gh auth status`. Not logged in: tell the user to run `gh auth login` themselves (it is interactive).
   - The current branch is not `main` or `develop`, and `git status --short` shows no uncommitted changes to tracked files. Ask about anything unrelated instead of committing it.
   - `uv run ruff check . && uv run ruff format --check . && uv run mypy src` is green.
   - `git fetch origin develop`. If the branch is behind `origin/develop`, ask before merging or rebasing it.
2. **Push:** `git push -u origin HEAD`.
3. **PR:** reuse the branch's PR only if `gh pr view --json number,url,state` reports `OPEN`; otherwise `gh pr create --base develop --title "<title>" --body-file .tmp/pr-body.md`.
   - Title: `$ARGUMENTS` if given; otherwise the branch's commit subject (one commit) or a conventional summary of its commits.
   - Body (write it with the Write tool): Result, What changed, How it was verified. No trailers unless the session gives attribution lines.
4. **CI:** run `gh pr checks <number> --watch --fail-fast` in the background (Playwright makes CI take minutes) and wait for its notification.
   - "no checks reported" right after creating the PR means CI hasn't registered yet: wait about 30 seconds and retry once before treating it as a failure.
   - Red: report the failing check names and the decisive lines of `gh run view <run-id> --log-failed`, then stop without merging. The orchestrator hands the failure to `debugger` and ships again after the fix.
5. **Merge:** `gh pr merge <number> --merge --delete-branch`, then `git switch develop && git pull --ff-only`.
6. **Report:** PR URL, result per CI check, the merge commit, and that `main` and deploy were not touched.
