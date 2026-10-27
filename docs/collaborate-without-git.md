# Reviewing a paper without Git or TeX

Your co-author needs three things and none of them is a repository: the current
PDF, a PDF that shows what changed, and a short explanation in plain language.

## What to send

```
review-pack/
├── MANIFEST.md        what is in the pack, which commit it came from, what is missing
├── main.pdf           the paper as it is now
├── main-diff.pdf      the same PDF with changes marked (if one could be built)
└── <summary>.md       two or three sentences of plain language
```

Build it on your side:

```bash
latexmk                                                      # current PDF
python -I tools/pdf_diff.py --base main --target HEAD \
    --expect "<a sentence you changed>" --out dist/review-pack
python -I tools/review_pack.py --out dist/review-pack \
    --pdf build/main.pdf --diff dist/review-pack/main-diff.pdf \
    --summary review-summary.md
```

Send the directory as a ZIP. The co-author opens `main.pdf` and
`main-diff.pdf` in any PDF viewer and reads `MANIFEST.md` in any text editor.

## What the co-author should look at, in order

1. `MANIFEST.md` — one line telling them whether the PDF matches the commit.
   If it says *dirty*, the PDF may not match, and they should ask for a rebuild.
2. `main-diff.pdf` — deleted text is struck through, added text is underlined,
   usually in two colours. It is a print-out of a `latexdiff`, so a moved
   paragraph can look like a deletion plus an addition.
3. `main.pdf` — the result, for reading the argument rather than the change.

## Writing the summary

The summary is the part a model often gets wrong, so write it yourself or check
it line by line. Good:

> Section 2.2 now says what happens when the admission test fails: the request
> stays local and is retried after the next measurement. No numbers, equations,
> citations or author details changed. Please check that "retried after the next
> measurement" matches what the implementation actually does.

Bad:

> Improved clarity and flow in the methods section, minor wording adjustments.

The second says nothing the co-author can check. Name the section, name the
change, name the one thing you are unsure about.

## When the diff PDF cannot be built

Common on a first migration, on heavy macros, or on a paper with a custom class.
Then:

- still send `main.pdf` and the summary;
- add the plain-text diff (`git diff base..HEAD -- '*.tex'`) as `changes.diff`,
  and say in the manifest that it is source, not typeset;
- never send an empty or stale `main-diff.pdf`. A missing diff is a known state;
  a wrong one wastes the reviewer's time.

`tools/pdf_diff.py` exits `3` with the reason when it cannot build. Put that
reason in the manifest via `--note`.

## What the pack does not contain

- A peer review. Nobody checked whether the experiment is right.
- A proof that the PDF matches the commit, if the tree was dirty.
- Anything the person building it did not supply.

Say these three things out loud the first time you send a pack. A co-author who
knows the limits reads it more carefully, not less.

## Replies

Ask for comments **on the diff PDF page numbers**, not on source lines. That is
the one vocabulary both of you share when they do not use Git.
