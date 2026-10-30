---
name: ship
description: Run the Full check, push the current feature branch, open a pull request into develop, merge it, and watch CI on develop. Use only when the user says /ship, "ship it", or asks to open a PR or merge a finished branch through GitHub.
argument-hint: [PR title]
---

# Ship

Invoking this skill is the user's approval to push this branch, open its PR into `develop`, and merge it after the local Full check passes. CI runs only on pushes to `develop` and `main`, not on feature branches or their PRs, so the Full check is the merge gate. It never targets `main`, never force-pushes, and never deploys.

1. **Preflight** (stop and report on any failure):
   - `gh auth status`. Not logged in: tell the user to run `gh auth login` themselves (it is interactive).
   - The current branch is not `main` or `develop`, and `git status --short` shows no uncommitted changes to tracked files. Ask about anything unrelated instead of committing it.
   - `git fetch origin develop`. If the branch is behind `origin/develop`, ask before merging or rebasing it.
   - The `run-tests` Full check (the same steps as CI) is green, so CI is not blocked. Any FAIL or SKIPPED: stop before pushing.
2. **Push:** `git push -u origin HEAD`.
3. **PR:** reuse the branch's PR only if `gh pr view --json number,url,state` reports `OPEN`; otherwise `gh pr create --base develop --title "<title>" --body-file .tmp/pr-body.md`.
   - Title: `$ARGUMENTS` if given; otherwise the branch's commit subject (one commit) or a conventional summary of its commits.
   - Body (write it with the Write tool): Result, What changed, How it was verified. No trailers unless the session gives attribution lines.
4. **Merge:** `gh pr merge <number> --merge --delete-branch`, then `git switch develop && git pull --ff-only`.
5. **CI on develop:** find the run for the merge commit with `gh run list --branch develop --commit <sha> --json databaseId` (it can take about 30 seconds to appear; retry once), then `gh run watch <run-id> --exit-status` in the background (Playwright makes CI take minutes) and wait for its notification.
   - Red: report the failing check names and the decisive lines of `gh run view <run-id> --log-failed`. The orchestrator hands the failure to `debugger` and ships the fix on a new branch.
6. **Report:** PR URL, the merge commit, the CI result on `develop`, and that `main` and deploy were not touched.
