# AGENTS.md — the single source of truth for agents working on this paper

This file is the contract for **any** coding agent (Claude Code, Codex, Cursor, …)
that edits this repository. `CLAUDE.md` only points here; it is not a second copy
of the rules. If you are an agent and you have not read this file end to end,
stop and read it before touching a single file.

The paper in `sections/` is a **synthetic sample**. It is not anybody's research.
Replace it with your own content; the rules below still apply.

---

## 1. What this repository is

- `main.tex` — preamble and the order of sections.
- `sections/*.tex` — the prose. This is where writing happens.
- `references.bib` — the bibliography.
- `.latexmkrc` — build configuration; **this file is Perl and executes code**.
- `build/` — generated output. Never edit it, never commit it.
- `tools/` — two small, single-purpose helpers (see §7). They are not a CLI.
- `tests/` — recorded test evidence and the local test runner.

The scientific content is the author's. The agent's job is the **mechanical and
editorial** part: branches, edits, builds, diffs, summaries, review packs.
The agent does not get to decide what is true.

---

## 2. Before you edit anything

Run these four commands and read the output. Do not skip them because the task
"looks small".

```bash
git status --short --branch
git log --oneline -5
git diff --stat            # uncommitted work by a human
git rev-parse HEAD         # record this SHA in your report
```

Then:

1. **Declare the scope.** Write down, before editing, the exact list of files you
   intend to touch and why. If a file is not on that list, you do not touch it.
2. **Stop if the working tree is dirty in those files.** Uncommitted changes are
   human work. You may build on top of them, but you may never discard, stash,
   reformat or overwrite them. If your edit would conflict, stop and report.
3. **Work on a branch.** `agent/<YYYYMMDD>-<short-slug>`. Never commit to `main`.

---

## 3. Modes of work

Every task is one of these. Say which one you are doing before you start.

| Mode | May change | Must not change |
|---|---|---|
| **polish** (language only) | wording in prose files | any number, formula, citation key, figure, table value, claim, author block |
| **structural** (move / split / retitle sections) | file layout, headings, cross-reference targets | scientific content |
| **content** (new text the author asked for) | prose as instructed | anything the author did not ask for |
| **mechanical** (build, export, review pack) | `dist/` output only | all source files |

If the task is ambiguous between *polish* and *content*, treat it as **polish**
and ask before adding a claim the author did not write.

---

## 4. Read-only regions

Unless the task explicitly authorises them, these are read-only — a change here
is a scientific change and needs the author's approval:

- Numbers and units: `92.4\%`, `2~GiB`, p-values, sample sizes, anything in a
  table or in an `equation`.
- Every `\cite{...}` key, and every entry in `references.bib`.
- `\label{...}` names, and the targets of `\ref` / `\eqref` / `\cref`.
- Figure and table data, captions that state a result, and `\includegraphics`
  targets.
- The author block: names, affiliations, emails, acknowledgements, funding.

If a polish task forces a change in one of these regions, **stop and ask**. Do
not "fix" a number because it looks wrong to you.

---

## 5. Writing rules

- **One sentence per line** in prose you add or rewrite. This makes diffs small
  and reviewable. Do **not** re-flow existing files wholesale; do not apply it
  inside `equation`, `align`, `tabular`, `tikzpicture` or long macro definitions.
- Never reformat a file you were not asked to touch, even to "tidy" it.
- Never reorder `\label` targets or renumber equations by editing by hand — let
  LaTeX do it.
- Keep the sample's honesty markers intact: if text says a result is synthetic,
  it stays that way.

---

## 6. Definition of done for an edit

All of the following, in this order, with the output kept for your report:

```bash
latexmk                     # must exit 0
latexmk -g -interaction=nonstopmode main.tex 2>&1 | grep -E "Warning|Overfull" || true
git diff --check            # whitespace errors
git diff --stat
git diff
```

Then produce the change record described in §8. **A build that exits 0 is not a
statement that the science is correct**, and a citation-key set that is
unchanged is not a proof that the citations are right. Say so in the report.

---

## 7. Tools that already exist — do not re-implement them

| Need | Use | Not this |
|---|---|---|
| compile | `latexmk` (reads `.latexmkrc`) | a custom build script |
| source diff | `git diff` | a custom differ |
| PDF diff | `latexdiff-vc --git` (see `docs/pdf-diff.md`) | a custom LaTeX parser |
| flatten multi-file source | `latexpand` | a custom `\input` resolver |
| citation check | `bibtex` warnings in `build/main.blg` | a custom BibTeX parser |

Two single-purpose scripts exist in `tools/`, and nothing else may be added
there without the author's approval:

- `tools/review_pack.py` — copies **already-built** artifacts into
  `dist/review-pack/` and writes a manifest. It never compiles.
- `tools/zip_inspect.py` — **inspects** an archive without extracting it and
  reports risks. It never extracts and never runs anything from the archive.

---

## 8. The change record (required output)

Every non-trivial edit ends with a block like this, in your reply and in the
commit message body:

```text
Agent change record
-------------------
Base commit : <sha before>
Branch      : agent/<date>-<slug>
Files       : <list>
Build       : latexmk exit <code>; <n> warnings (see build/main.log)
Diff check  : git diff --check <clean|N issues>
Semantic risk (read-only regions touched):
  numbers   : <none | list>
  citations : <none | list>
  labels    : <none | list>
  authors   : <none | list>
Guardrail   : <PASS | FAIL | NOT_VERIFIED> — scope: <what it checked>
Not checked : scientific correctness, reference accuracy, journal style
```

`Guardrail: FAIL` means a read-only region changed. In that case you do not
commit; you stop and ask for approval.

---

## 9. Git and publication gates

| Action | Who may authorise |
|---|---|
| edit on an `agent/` branch, build locally | the agent, freely |
| commit on the `agent/` branch | the agent, if the guardrail passed and the author asked for a commit |
| **merge to `main`** | the author |
| **`git push`** (including to a private remote) | the author, per push |
| **open a PR** | the author |
| **create a repository** | the author |
| **publish / make public / release / tag** | the author, explicitly, in words |
| `git push --force`, `git reset --hard`, history rewrite, deleting a branch | the author, in words, per instance |

Never run `git push --force`, never rewrite history, never delete a branch or a
file you did not create, and never touch the author block without being asked.

---

## 10. Security boundaries

- `.latexmkrc` and any `pre_compile` / `post_compile` hook are **code**. Do not
  run a build in a checkout whose build configuration you have not read, and do
  not add shell invocations to `.latexmkrc`.
- Do not enable `-shell-escape`. That reduces one class of risk; it does not make
  an untrusted document safe. Say "reduced", never "safe".
- Never import an archive by extracting it into the repository. Use
  `tools/zip_inspect.py` first, and follow `docs/migrate-from-overleaf.md`.
- Never commit credentials, personal data, or another person's unpublished
  manuscript. `tests/fixtures/` and `docs/` may only contain synthetic data.

---

## 11. When you are unsure

Say so. `NOT_VERIFIED` and `BLOCKED` are valid, expected outcomes; a fabricated
`PASS` is not. Report what you ran, what it printed, and what you could not test.
