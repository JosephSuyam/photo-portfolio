---
name: orchestrate
description: Take a task in plain words and run it end to end by delegating to the project agents (test-writer, implementer, debugger, code-reviewer, doc-writer) and skills (run-tests, preview-site), then report one summary. Use when the user says /orchestrate, "orchestrate", or hands over a task to be driven through the whole workflow.
argument-hint: <task in plain words>
---

# Orchestrate

Task: $ARGUMENTS

You are the orchestrator in the main session (subagents can't delegate, so this runs here).
You plan, delegate, verify, and summarize; agents do the noisy work. CLAUDE.md is the source
of truth for commands, rules, "Done means", and the summary format. If the task is empty,
ask for it.

## 1. Intake
- Restate the task in one sentence and classify it: **feature**, **bug**, **UI/design**,
  **docs-only**, or **question** (just answer it; no agents).
- Read only what you need to decide. Ask with AskUserQuestion only for real forks (what to
  build, which option); pick conventional defaults yourself and say so in the summary.
- **UI/design with no agreed look:** build throwaway mockups first (`.tmp/concepts/`, real
  synced photos, served with `reel.server.make_preview_server` on 8124), screenshot desktop
  and phone, show them, and wait for the user's choice before touching `src/`.
- Branch: continue the current feature branch if the task extends it; otherwise
  `git switch -c <type>/<slug>` from the current branch (never commit on `main`/`develop`).

## 2. Spec (3+ files, a public interface, or more than one agent)
Write `.tmp/<slug>-spec.md`: behavior, exact markup/selectors/function names, examples with
expected values, edge cases, and what stays unchanged. It's the contract every agent gets.

## 3. Build: tests first, in parallel
- **feature / UI:** start `test-writer` in the background on the spec (tests must fail for
  the right reason against current code). Implement meanwhile: small edits yourself,
  larger ones via `implementer`. Bash heredocs with nested quotes break on this machine;
  write patch scripts with the Write tool into `.tmp/`.
- **bug:** `debugger` first: reproduce with a failing test, root-cause, minimal fix.
- **docs-only:** `doc-writer`, then skip to step 6.
- Every agent prompt carries: goal, spec path, files in scope, constraints (test-writer
  never edits `src/`; nobody touches port 8000; Playwright runs only on 8123 and only one
  run at a time), what is changing in parallel, and the report format (changes per file,
  results with counts, ambiguities).

## 4. Verify
- Run the `run-tests` skill (Full check). Failures: send them to `debugger` with test
  names, output, and your hypothesis; re-run the Full check after.
- UI changes: `preview-site` (real photos when `.env` exists), both themes, desktop and
  phone; look at every screenshot. A dim photo in a fresh screenshot is usually the
  fade-in; recheck after a second before calling it a bug.

## 5. Review and docs (in parallel)
- `code-reviewer` in the background; tell it not to run Playwright while you do.
- `doc-writer` in the background for README, `docs/`, CHANGELOG when behavior, config,
  conventions, or CLI changed.
- Fix every blocking and should-fix finding: `src/` items yourself or via `implementer`;
  test gaps by resuming the same `test-writer` with SendMessage (it keeps its context;
  don't spawn a fresh one). Nits: fix the cheap ones, list the rest.
- Agents may not edit CLAUDE.md or skills. Apply a one-line CLAUDE.md fact change yourself
  only when the user asked for markdown to be kept current; otherwise propose it.

## 6. Finish
- Final Full check, actually run and green (paste counts). Never weaken a test to pass.
- `git status`; commit atomically with conventional messages (usually `feat`, `test`,
  `docs`), add new untracked files explicitly, leave unrelated work (e.g. `.vscode/`) out.
- Ask before: deleting files, installing dependencies, merging, pushing, deploying.
- Stop any server you started on 8124; leave 8000 running.
- End with the CLAUDE.md summary: Result, What changed (table), How it was verified,
  Decisions and open items, and the next step as a question.

## Notes
- Untracked new files don't show in `git diff`; tell agents to read them directly.
- A background agent's results arrive as a notification; don't predict or poll them.
- Keep the user posted with one line when a phase starts or an agent reports.
