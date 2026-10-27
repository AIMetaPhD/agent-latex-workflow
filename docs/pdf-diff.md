# PDF diff for a multi-file paper

`git diff` shows the source. A co-author who does not read LaTeX needs the PDF.
This page records what actually works, on which tool versions, and what to do
when it does not.

## Tool versions used for the recorded evidence

| Tool | Version | Notes |
|---|---|---|
| `latexdiff` | 1.3.4 (Perl v5.42.2) | from TeX Live 2025 |
| `latexdiff-vc` | ships with `latexdiff` | wrapper around git |
| `latexpand` | v1.7.2 | flattens `\input` before diffing |
| `latexmk` | 4.86a | |

`git-latexdiff` is **not installed** here. It is a third-party script
(simplified BSD, GitLab: `git-latexdiff/git-latexdiff`) and it is not a git
subcommand until its `Makefile` install step is run. This project does not
vendor it; see “Alternatives” below.

## The command

Multi-file papers must be flattened, or `latexdiff` only sees `\input{...}`
lines and reports no change at all:

```bash
latexdiff-vc --git --flatten --force --pdf -r <old-ref> <new-ref> -- main.tex
```

- `--git` — resolve `old-ref` / `new-ref` through git.
- `--flatten` — run `latexpand` so `sections/*.tex` are inlined.
- `--force` — overwrite an existing `main-diff.pdf`.
- `--pdf` — compile the diff.

Output lands next to the source as `main-diff.pdf`. The `.latexmkrc`
`$out_dir = 'build'` does not redirect it; check both locations and record
where it actually is:

```bash
ls -l main-diff.pdf build/main-diff.pdf 2>/dev/null
```

## Verify it is a real diff

A file named `main-diff.pdf` proves nothing. Check that the changed sentence
appears in the extracted text and that the diff markup is present:

```bash
pdftotext main-diff.pdf - | grep -c "<a phrase you changed>"
pdftotext main-diff.pdf - | grep -c "DIFadd\|DIFdel"   # may be 0 if markers are styles
```

The reliable check is `grep` for the new sentence, plus opening the PDF once and
looking at the red/blue markup. Record both.

## When it fails

| Symptom | Cause | What to report |
|---|---|---|
| `main-diff.pdf` identical in size to `main.pdf` | `--flatten` missing | FAILED, re-run with `--flatten` |
| `latexpand` error about `\import` | unsupported include form | FAILED + file and macro name |
| diff compiles but shows no colour | preamble hides `DIF` macros | note it, fall back to text diff |
| diff exits non-zero on a macro | `latexdiff` cannot parse a custom macro | FAILED + the macro |

In every failure case the review pack must carry the plain-text `git diff` and a
one-line reason. A missing diff is acceptable; a fake one is not.

## Alternatives considered

- `latexdiff-vc` without `--flatten` — only works for single-file papers.
- `git-latexdiff` — does the same job with `latexpand`; not installed here, so
  this project does not claim it works.
- `tawalaya/latex-diff-action` — a Docker GitHub Action wrapping the same tools;
  last commit 2021-07-30, so it is not a dependency.

## Evidence recorded in this repository

`tests/results/pdf-diff.md` records the exact commands, exit codes and the text
extraction check for the multi-file case (`sections/method.tex`).
