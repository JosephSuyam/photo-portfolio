---
name: run-tests
description: Run the project's Full check (ruff, mypy, pytest, TypeScript typecheck, Playwright) and report results. Use to verify any change before calling it done.
---

# Run tests

Run the **Full check** below. From the repo root, run each step separately with the Bash tool, all of them even if one fails, so every problem is reported at once:

1. `uv run ruff check .`
2. `uv run mypy src`
3. `uv run pytest -q`
4. `npm run typecheck`
5. `npm run test:e2e` (about 30s; builds a fixture site and serves it on port 8123, so port 8000 and a running `portfolio serve` are unaffected). Filter `[WebServer]` lines out of the output.

If `uv` or `npm` is missing, or `node_modules/` is absent, report that step as SKIPPED with the reason. Never install anything yourself.

## Report
```
ruff:       PASS | FAIL (<n> errors)
mypy:       PASS | FAIL (<n> errors)
pytest:     PASS (<n> passed) | FAIL (<n> failed, <n> passed)
typescript: PASS | FAIL (<n> errors) | SKIPPED (<reason>)
e2e:        PASS (<n> passed, <n> skipped) | FAIL (<n> failed) | SKIPPED (<reason>)
```
Then, for each failure, the relevant error lines (not the full log). Playwright's "skipped" count is expected: desktop-only and mobile-only specs skip on the other project. This skill only reports; it does not fix anything. Never claim a pass you did not see.
