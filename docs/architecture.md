# Architecture

## The bet

A paper repository only needs a handful of things to be agent-operable:

1. **one contract** that every agent reads, with no drifted second copy;
2. **native tools** for the parts that are already solved (Git, `latexmk`,
   `latexdiff`, GitHub Actions);
3. **a small number of checks with written limits**, for the parts that are not.

Everything else — a CLI, a web UI, a plugin, a scheduler — is a product, and
this project is not one.

## Files and who owns them

| Path | Owner | An agent may |
|---|---|---|
| `main.tex`, `sections/*.tex`, `references.bib` | the author | edit within the declared scope |
| `AGENTS.md` | the project | read; propose changes, never silently rename a rule |
| `CLAUDE.md` | the project | read; it only points at `AGENTS.md` |
| `skills/*/SKILL.md` | the project | read; these are procedures, not rules |
| `.latexmkrc` | the project | read before building; changes need a human |
| `tools/*.py` | the project | run; changes count as `build-config` risk |
| `build/` | nobody | never write, never commit |
| `dist/` | the agent | write review packs and snapshots |

## Flow of one edit

```
task
 │
 ├─ 1. precondition   git status, log, HEAD; classify the task; declare scope
 │
 ├─ 2. branch         agent/<date>-<slug>       (never main)
 │
 ├─ 3. edit           only the declared files; one sentence per line in prose
 │
 ├─ 4. build          latexmk → build/main.pdf  (exit code is the gate)
 │
 ├─ 5. guardrail      check_invariants.py       (2 = stop, 3 = say so)
 │
 ├─ 6. record         diff --check, diff --stat, diff, change record
 │
 └─ 7. hand-off       commit on the branch; push/PR/release need the author
```

Steps 4 and 5 are independent: a build can pass while the guardrail fails, and
that combination is exactly the dangerous one — the paper compiles and the
numbers changed.

## Flow of a review

```
two refs ──► git diff ────────► source summary
        └──► pdf_diff.py ─────► main-diff.pdf ──► review_pack.py ──► dist/review-pack/
                                   │                    │
                          latex archive +            MANIFEST.md
                          latexpand + latexdiff      (what is missing)

snapshot ──► review_pack.py --snapshot ──► SNAPSHOT.{md,json} + source.tar.gz
```

## Why each tool exists

| Tool | The gap it fills | Why not an existing tool |
|---|---|---|
| `check_invariants.py` | “did a language edit touch a number?” | no LaTeX-aware invariant checker with exit codes; `chktex` checks style, `latexdiff` shows everything |
| `pdf_diff.py` | multi-file PDF diff on Windows | `latexdiff-vc --git` constructs a shell pipeline that `cmd.exe` cannot parse (proved in `docs/pdf-diff.md`) |
| `zip_inspect.py` | hazards *before* extraction | `unzip -l` lists names only; it cannot see `external_attr` symlinks, compression ratios or case collisions |
| `review_pack.py` | a folder a non-Git reader can open | it is a `copy` plus a manifest; deliberately not a packager with options |
| `publish_audit.py` | nothing personal in the history | `gitleaks`/`trufflehog` are additional dependencies and are not installed; the rules here are repository-specific |

Each is a hundred to three hundred lines and each says, in its docstring and in
`docs/`, what it does not check.

## What was deliberately not built

- a `paper` CLI: `paper-lab` already has one and it is macOS-bound;
- a build wrapper: `latexmk` with `.latexmkrc` is the interface;
- a template registry / conference packs: `alfred` and PaperKit do that;
- writing or literature skills: `latex-paper-skills` does that better;
- a web UI or a server: out of scope by the project plan;
- a citation verifier: it would need network access and a source of truth, and
  claiming it verifies references is exactly the over-claim this project avoids.

## Extension points

- **A new check** becomes a new category in `POLICY` and a feature extractor in
  `check_invariants.py`. It must state its misses in `docs/guardrail.md`.
- **A new agent host** only needs to read `AGENTS.md`; if it does not read
  `skills/`, paste the snippet from `CLAUDE.md` §“Other agents”.
- **A different engine** (XeLaTeX) is a `.latexmkrc` change plus real testing;
  this template does not claim it works until someone records it in
  `tests/SELFTEST.md`.
