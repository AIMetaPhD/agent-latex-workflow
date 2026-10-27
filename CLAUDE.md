# CLAUDE.md

The rules for working in this repository live in **[AGENTS.md](AGENTS.md)**.
That file is the single source of truth for every agent, including Claude Code.
There is deliberately no second copy of the rules here, because two copies drift.

Read `AGENTS.md` before doing anything else.

## Claude Code specifics

- The three workflows are skills and load automatically when relevant:
  `skills/paper-edit/`, `skills/paper-review/`, `skills/paper-release/`.
- If a skill is not loaded, ask for it by name ("use paper-edit") or read the
  matching `SKILL.md` and follow it as instructions.
- Commit messages end with the `Agent change record` block from `AGENTS.md` §8.

## Other agents (Codex, Cursor, Copilot, …)

Those tools do not always read `skills/`. Paste this into your prompt:

```text
Read AGENTS.md and follow it as the contract for this task.
Then read skills/<paper-edit|paper-review|paper-release>/SKILL.md and follow it.
Do not edit files outside the scope you declare, and do not push or publish.
```
