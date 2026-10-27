# Third-party notices

This repository **contains no third-party source code**. The files in
`sections/`, `main.tex`, `.latexmkrc` and `tools/` were written for it. What
follows is the list of external components it *depends on* at run time, with the
licence evidence gathered in `docs/competitor-audit.md`.

## Depended on, not vendored

| Component | Used for | Licence | Evidence |
|---|---|---|---|
| [`xu-cheng/latex-action`](https://github.com/xu-cheng/latex-action) pinned to `6549dc21effb2730855a1281407ecfcececc6c1b` (4.1.0) | compiling in GitHub Actions | MIT | `LICENSE` blob `cbc5be0dff007f1224ef4ac02fdf7b914aed9779`, verified 2026-10-26 |
| `actions/checkout` pinned to `11d5960a326750d5838078e36cf38b85af677262` (v4) | CI checkout | MIT | GitHub-maintained action |
| `actions/upload-artifact` pinned to `ea165f8d65b6e75b540449e92b4886f43607fa02` (v4) | CI artifact upload | MIT | GitHub-maintained action |
| `latexmk` | build driver | GPL-2.0-or-later | installed with TeX Live; invoked, not distributed |
| `latexdiff` | typeset diff | GPL-2.0-or-later (Perl) | installed with TeX Live; invoked |
| `latexpand` | flattening `\input` | LPPL / GPL as distributed by TeX Live | installed with TeX Live; invoked |
| `bibtex` | bibliography | part of TeX Live | invoked |
| `pdftotext` (Poppler) | verifying a diff PDF's text | GPL-2.0 | optional; invoked |
| `TeX Live` / the `article` class | typesetting the sample | LPPL | the sample uses the standard `article` class only |

Because these are **invoked as programs** and not copied into this repository,
their licences do not relicense this repository; they apply to the installed
tools. If you redistribute a *bundled* environment (for example a Docker image
containing TeX Live), the licence obligations of those components apply to that
image.

## Referenced but not used

These projects were audited and deliberately **not** used (see the per-project
verdicts in `docs/competitor-audit.md`): `paper-lab`, `paperops`, `alfred`,
`PaperKit`, `latex-paper-skills`, `tawalaya/latex-diff-action`,
`git-latexdiff`.

`git-latexdiff` deserves a note because it is the obvious alternative for the
PDF diff. Its `COPYING` is **not an SPDX licence**: it grants copying and
distribution “without royalty provided the copyright notice and this notice are
preserved”, alternatively under a 2-clause BSD text. Adopting it as a dependency
would require preserving that notice. This repository does not use it; the
equivalent path (`git archive` + `latexpand` + `latexdiff`) is implemented in
`tools/pdf_diff.py`, and none of its code was consulted while writing that file.

## Not included on purpose

The sample paper uses the standard `article` class. Publisher classes such as
`IEEEtran` are not shipped here, because they carry their own licence and belong
to the paper's project, not to a template. Keep the publisher's files in your
private repository.

## If you add a dependency

1. Check the licence **file**, not the badge.
2. Prefer invoking a tool over copying its source.
3. If you copy code, add the notice here and in the file header, and state the
   licence in the README.
