---
name: orchestrate
description: Hand a task to the orchestrator agent, which drives it end to end through the project workflow (implementation, lint/type check, preview, review, commits) and reports one summary. Use when the user says /orchestrate or "orchestrate" in a session that isn't already running as the orchestrator.
argument-hint: <task in plain words>
---

# Orchestrate

Task: $ARGUMENTS

If the task is empty, ask for it. If this session already runs as the `orchestrator` agent (`claude --agent orchestrator`), just do the task following your own instructions.

Otherwise launch the `orchestrator` agent with the task verbatim, plus anything from this conversation it needs (branch, earlier decisions, the user's answers), and tell the user in one line that it's running.

When it reports:
- **Questions at the top:** ask the user (AskUserQuestion with its options), then resume the same orchestrator with SendMessage and the answers. Don't answer for the user.
- **Done:** relay its summary to the user as is (Result, What changed, How it was verified, Decisions and open items, next step). Don't redo its work or claim checks it didn't report.
