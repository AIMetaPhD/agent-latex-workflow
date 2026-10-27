---
name: paper-edit
description: Make a scoped, reviewable edit to the paper's LaTeX source — polish language, restructure, or add text the author asked for — then build, diff and report. Use when the user asks to change the paper's text.
license: MIT
---

# Skill: paper-edit

A scoped edit to the paper, with a build, a diff and a change record.
The contract is [`AGENTS.md`](../../AGENTS.md); this file is the procedure.

## 0. Preconditions (do these, every time)

1. Read `AGENTS.md`.
2. Run and keep the output of:

   ```bash
   git status --short --branch
   git log --oneline -5
   git rev-parse HEAD
   ```

3. Classify the task with the table in `AGENTS.md` §3 (polish / structural /
   content / mechanical). If you cannot classify it, ask.
4. State the scope: the exact files you will touch. Nothing else gets touched.

If the target files have uncommitted changes, record the diff first:

```bash
git diff -- <files>
```

You may edit on top of it. You may not revert it.

## 1. Branch

```bash
git switch -c agent/$(date +%Y%m%d)-<slug>
```

If you are already on an `agent/` branch for the same task, stay on it.
Never branch from or commit to `main` without being told to.

## 2. Edit

- Only the files in your declared scope.
- In prose, **one sentence per line** for the sentences you write or rewrite.
- Do not reflow untouched paragraphs, do not reorder labels, do not renumber.
- Read-only regions (`AGENTS.md` §4) stay untouched in *polish* mode.

If you are in *polish* mode and the only way to finish the task is to touch a
read-only region, stop and ask. Do not touch it and mention it afterwards.

## 3. Build

```bash
latexmk
```

Exit non-zero: read `build/main.log`, fix from the **first** error, and do not
report success. Warnings are reported, not hidden:

```bash
grep -nE "^(LaTeX Warning|Package .* Warning|Overfull|Underfull|!)" build/main.log
grep -nE "undefined|Citation .* undefined" build/main.log
```

## 4. Guardrail

```bash
python tools/check_invariants.py --base HEAD --mode polish --fail-on risk
```

- Exit `0` → `PASS`, quoted with its summary line.
- Exit `2` → `FAIL`: a read-only region changed. **Stop.** Show the findings and
  ask the author to approve or revert. Do not commit.
- Exit `3` → `NOT_VERIFIED`: the checker hit a file it could not parse. Report
  the reason and say the edit was not verified, rather than claiming it is safe.

The guardrail's limits are in `docs/guardrail.md`. Read them before quoting it.

## 5. Diff and record

```bash
git diff --check
git diff --stat
git diff
```

Write the `Agent change record` from `AGENTS.md` §8. Paste the real numbers from
the commands above; never estimate them.

## 6. Commit (only if asked)

```bash
git add <the files in scope>
git commit -F - <<'EOF'
<type>: <what changed in the paper, not in the process>

Agent change record
-------------------
...
EOF
```

Then stop. Do not push, do not open a PR, do not tag. Those are the author's
decisions (`AGENTS.md` §9).

## Failure modes seen in practice

| Symptom | What it means |
|---|---|
| build passes, guardrail `FAIL` on `numbers` | you changed a value; revert or get approval |
| `NOT_VERIFIED` on a macro-heavy file | checker cannot see through it; review by hand and say so |
| diff touches files you did not declare | you drifted; revert those hunks |
