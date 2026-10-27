---
name: paper-review
description: Review a change to the paper — compare two git refs, produce a human-readable summary and a PDF diff or a fallback, and pack it for a non-technical co-author. Use when the user asks to review, compare, or send changes to a supervisor.
license: MIT
---

# Skill: paper-review

Produce something a co-author who does not use Git can read.
The contract is [`AGENTS.md`](../../AGENTS.md).

## 0. Pin the two refs

Never compare "the working tree" implicitly. Name both sides:

```bash
git rev-parse <old-ref> <new-ref>
git status --short          # uncommitted work must be reported, never dropped
git diff --stat <old-ref>..<new-ref>
```

Record both SHAs in the output. If the working tree is dirty, say which files are
not part of the comparison.

## 1. Source diff

```bash
git diff <old-ref>..<new-ref> -- '*.tex' '*.bib'
```

Summarise in prose: what changed, file by file, in the author's vocabulary.
Group by section, not by file, when a section spans files.

## 2. Guardrail

```bash
python tools/check_invariants.py --base <old-ref> --mode polish \
  --target <new-ref> --fail-on risk
```

Report `PASS` / `FAIL` / `NOT_VERIFIED` verbatim, with the finding lines. A
`FAIL` means numbers, citations, labels or the author block changed; that is the
first thing the author must see, not a footnote.

## 3. PDF diff

A PDF diff over multiple files usually needs a flattened source. Follow
[`docs/pdf-diff.md`](../../docs/pdf-diff.md). The short version:

```bash
latexdiff-vc --git --flatten --force -r <old-ref> --pdf <new-ref> -- main.tex
```

Then **verify the result actually shows the change**:

```bash
pdftotext build/main-diff.pdf - | grep -c "<a sentence you changed>"
```

A PDF that merely exists is not a PDF diff. If `latexdiff` fails, or the text
extraction does not contain the change, record:

- the exact command,
- the exact error,
- the plain-text `git diff` as the fallback,

and mark the PDF diff `FAILED — fallback attached`. Never present a stale or
empty diff as success.

## 4. Review pack

```bash
python tools/review_pack.py --out dist/review-pack \
  --pdf build/main.pdf --diff build/main-diff.pdf \
  --summary review-summary.md
```

The script only copies files that already exist and writes `MANIFEST.md`. It
does not build. If a diff PDF is missing, pass `--note "reason"` and the
manifest records the fallback.

## 5. Hand-off message

Produce `review-summary.md` in plain language:

- what changed (two or three sentences, no LaTeX),
- what to look at (page or section),
- what is at risk (unchanged numbers, unresolved warnings),
- what the author must decide.

No jargon, no file paths unless the reader asked for them.

## Limits you must state

You are not a peer reviewer. You did not verify the science, the references, or
the journal's style rules. Say that in one line at the end of the summary.
