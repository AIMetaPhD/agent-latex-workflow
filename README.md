> **ARCHIVED — this direction was wrong.** This repository is a failure archive,
> kept so the next attempt does not repeat the same mistakes. It is not a usable
> product. See [ARCHIVED.md](ARCHIVED.md) for what happened, what is still worth
> reusing, and the traps already paid for.
>
> The v0.2 part (paper template, `AGENTS.md`, skills, toolchain, CI) was not part
> of the failure and can be reused.

# Agent-first Paper Workflow

English | [简体中文](README.zh-CN.md)

**Git is the record. The agent does the mechanical work. You decide what is true.**

A GitHub template for a **private** paper repository that a coding agent
(Claude Code, Codex, Cursor) can edit safely, and that a co-author who does not
use Git can review as a PDF.

This is not an editor, not a LaTeX compiler, not a SaaS product and not a new
CLI. It is a small set of files: a template paper, one contract (`AGENTS.md`),
three skills, two GitHub Actions steps and four single-purpose scripts whose
limits are written down.

```
your paper repo (private)
├── AGENTS.md            the only contract an agent reads
├── CLAUDE.md            points at AGENTS.md; no second copy of the rules
├── skills/              paper-edit, paper-review, paper-release
├── main.tex + sections/ the paper (a synthetic sample ships with it)
├── .latexmkrc           build config; it is Perl, so it is code
├── .github/workflows/   build on trusted branches only
└── tools/               pdf diff, archive inspection, review pack, audit
```

## Why

Overleaf forces a manual sync for everyone who shares a project, and it has no
reviewable history an agent can work against. A private Git repository fixes the
history problem but makes the co-author's life harder — unless the agent turns
each change into a PDF and a summary.

The gap this template fills is not “AI writes LaTeX”. Several projects do that
well (see [docs/competitor-audit.md](docs/competitor-audit.md)). The gap is the
**safety and review loop around a real, existing paper**: an agent that stays in
its lane, a diff a supervisor can read, and a build that cannot quietly execute
somebody else's code.

## Quickstart (Windows, macOS, Linux)

Requirements: Git, a TeX distribution with `latexmk` and `bibtex` (TeX Live or
MiKTeX), and Python 3.10+ for the local workbench. **No API key is needed to
build the paper**, and no Python package needs to be installed.

### 1. Open the workbench (the interactive way)

Double-click the launcher for your system:

| System | File |
|---|---|
| Windows | `start-ui.bat` |
| macOS | `start-ui.command` |
| Linux | `start-ui.sh` |

A browser opens at `http://127.0.0.1:8765/` with three numbered steps:
**Environment** (what is installed and what is missing), **Build** (one button,
real log, first error highlighted), **Preview** (the latest PDF and a button to
open the folder in VS Code). Then the Agent prompt builder and a read-only Git
panel.

The launcher finds the project from its own location, so it works from any
working directory. It looks for Python, not for a TeX install: without TeX the
workbench still starts and the build button is disabled with an explanation.

### 2. Compile from the command line (Advanced)

```bash
latexmk                                   # builds build/main.pdf
```

Then replace the sample: edit `sections/*.tex`, `main.tex` and
`references.bib`. The sample is deliberately synthetic, so nothing in it is
anybody's unpublished work.

On Windows, `latexmk` runs under TeX Live's Perl. If `latexmk` is not on
`PATH`, use the full path to `latexmk.exe` from your TeX installation.

Port, browser and build timeout can be set on the command line:

```bash
python ui/server.py --port 8765 --no-browser --print-url --build-timeout 120
```


## Workflow

| You want | You say to the agent | What you get |
|---|---|---|
| polish a paragraph | “use paper-edit, polish §2.2, language only” | branch, edit, build, guardrail, change record |
| see what changed | “use paper-review, compare main with agent/…” | summary, PDF diff, review pack |
| send it to a co-author | “pack the review” | `dist/review-pack/` with PDF, diff, manifest |
| freeze a submission | “use paper-release, stage submission” | snapshot with commit, PDF hash, environment |

The agent works on `agent/<date>-<slug>`, never on `main`, and never pushes.

## What is enforced, and what is not

| Check | Tool | Enforced |
|---|---|---|
| the paper still compiles | `latexmk` | yes, exit code |
| numbers / formulas / citations / labels / authors unchanged in a polish task | `tools/check_invariants.py` | yes, exit `2` blocks |
| no personal data or credentials before publishing | `tools/publish_audit.py` | yes, exit `2` blocks |
| a ZIP does not escape the destination | `tools/zip_inspect.py` | yes, refuses to advise extraction |
| the PDF diff really shows the change | `tools/pdf_diff.py` | yes, text extraction check |
| **the science is correct** | — | **no, never claimed** |
| **the references are real** | — | **no; the guardrail checks keys, not accuracy** |

Read [docs/guardrail.md](docs/guardrail.md) before quoting the guardrail in a
report. It has a known set of misses.

## Security model in one paragraph

`.latexmkrc` is Perl and runs with your permissions; `latex-action`'s
`pre_compile` is arbitrary bash. CI therefore builds **trusted branches only**,
never a fork's pull request, with `contents: read`, no secrets and no
`-shell-escape`. That removes one class of risk; it does not make an untrusted
document safe. Details and the residual risks: [docs/security.md](docs/security.md).

## Migrating an existing Overleaf project

Do not unzip into the repository. Follow
[docs/migrate-from-overleaf.md](docs/migrate-from-overleaf.md): keep the
original ZIP and a baseline PDF, inspect the archive with
`tools/zip_inspect.py`, copy files in by hand, and commit the baseline before
the agent touches anything.

## Reviewing without Git

[docs/collaborate-without-git.md](docs/collaborate-without-git.md): what goes
into a review pack, what the co-author should look at, and what the pack
deliberately does not claim.

## The local workbench

`start-ui.bat` (Windows), `start-ui.command` (macOS) or `start-ui.sh` (Linux)
opens a page in your browser that covers the five things a new user actually
needs. It is a control panel for this repository, not an editor.

| Panel | What it does | What it refuses to do |
|---|---|---|
| Environment | checks Git, Python, latexmk, the LaTeX engine, BibTeX, Perl, and optionally VS Code and latexdiff; says what is missing, why, and the official install command | never installs anything for you |
| Build | runs `latexmk` in the background, shows real state, exit code, duration, log tail and the first error | never runs two builds at once; never a custom command |
| Preview | serves `build/main.pdf` with `no-store`, opens the project in VS Code when it is installed | never reads any other file |
| Agent prompt | builds a scoped task for Claude Code / Codex from `sections/*.tex` | never calls a model, never sends anything |
| Git | shows branch, `git status --porcelain`, `git diff --stat` and the guardrail | no commit, branch, checkout, reset or push, ever |

Security: it binds `127.0.0.1` only, checks the `Host` header on every request
(so DNS rebinding cannot reach it), requires a session cookie whose token
arrives in the URL fragment rather than in the query string or a log, checks the
`Origin` header on anything that changes state, and emits no CORS headers. The
build is a fixed command with a timeout and a bounded log. The full threat model
and what is deliberately absent is in [docs/UI-ADR.md](docs/UI-ADR.md).

**What leaves your machine: nothing.** No model API, no telemetry, no external
fonts, scripts or images. If you then hand a generated prompt to an agent, that
tool decides what to send, under its own policy — the two are separate.

## Requirements

| | Minimum | Verified here |
|---|---|---|
| Python | 3.10+ (standard library only) | 3.13.9 |
| Git | 2.23 (`git switch`) | 2.55.0 on Windows |
| TeX Live | 2023, `latexmk` ≥ 4.7 | TeX Live 2025, `latexmk` 4.86a |
| `latexdiff` + `latexpand` | any recent | `latexdiff` 1.3.4, `latexpand` 1.7.2 |
| Python (tools only) | 3.10, standard library | 3.13.9 |
| `pdftotext` (diff check) | optional | present via Poppler |

`xelatex` and `lualatex` are supported by TeX Live but this template is only
tested with `pdflatex`. If you need them, change `$pdf_mode` in `.latexmkrc` and
verify the fonts yourself — the sample does not exercise them.

## FAQ

**Do I have to use VS Code?** No. Any editor works; LaTeX Workshop is just the
most convenient way to get build-on-save.

**Can an agent write new science?** It can write text you ask for. It must not
invent results, references or numbers; `AGENTS.md` §4 makes those regions
read-only unless you say otherwise.

**Does the guardrail prove my paper is unchanged?** No. It reports changed
tokens in named categories. A reordered sentence or a swapped context keeps
every token and changes the meaning.

**Do I need an API key?** No. Nothing here calls a model. Your agent brings its
own.

## Limits

- The sample paper's numbers are invented; do not cite them.
- Only `pdflatex` is tested. IEEEtran is compatible but not shipped, because
  the class file has its own licence; keep the publisher's own files in your
  private repository.
- Cross-platform status is recorded honestly in
  [tests/SELFTEST.md](tests/SELFTEST.md): Windows is verified on the recording
  machine, macOS is `BLOCKED`, Linux CI is the runner only.
- The tools are maintenance surface. Four scripts exist because each closes a
  gap that an installed tool does not, and each is documented with its limits.

## License

MIT. Third-party components are used, not vendored — see
[docs/competitor-audit.md](docs/competitor-audit.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Credits and prior work

Respect is due to the projects this one deliberately does not duplicate:
[paper-lab](https://github.com/JoseAntonioNuevo/paper-lab),
[latex-paper-skills](https://github.com/yunshenwuchuxun/latex-paper-skills),
[paperops](https://github.com/giacomolanciano/paperops),
[alfred](https://github.com/dreadnode/alfred),
[PaperKit](https://github.com/peternicholls/PaperKit), and
[`xu-cheng/latex-action`](https://github.com/xu-cheng/latex-action), which does
the compiling in CI.
