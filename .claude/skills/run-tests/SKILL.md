---
name: run-tests
description: Run the project's full check (ruff, mypy, pytest) and report results. Use to verify any change before calling it done.
---

# Run tests

From the repo root, run each step with the Bash tool. Run all three even if one fails, so every
problem is reported at once:

1. `uv run ruff check .`
2. `uv run mypy src`
3. `uv run pytest -q`

If `uv` is not found, stop and report that it must be installed. Do not install it yourself.

## Report
```
ruff:   PASS | FAIL (<n> errors)
mypy:   PASS | FAIL (<n> errors)
pytest: PASS (<n> passed) | FAIL (<n> failed, <n> passed)
```
Then, for each failure, the relevant error lines (not the full log). This skill only reports;
it does not fix anything. Never claim a pass you did not see.
