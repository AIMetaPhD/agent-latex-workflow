#!/usr/bin/env python3
"""Assert that a build log has no unresolved references and no LaTeX warnings.

A naive `grep undefined` matches `Package: rerunfilecheck ... Rerun checks`, so
this script anchors on the forms LaTeX actually emits:

    LaTeX Warning: Citation `x' on page 1 undefined on input line 12.
    LaTeX Warning: There were undefined references.
    LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.

Exit codes
    0  clean: no undefined reference, no LaTeX warning, no overfull box
    2  findings, printed
    3  the log is missing (build did not run)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "build" / "main.log"

PATTERNS = [
    ("undefined-citation", re.compile(r"Citation `[^']*' .*undefined")),
    ("undefined-reference", re.compile(r"Reference `[^']*' .*undefined")),
    ("undefined-summary", re.compile(r"There were undefined references")),
    ("rerun-needed", re.compile(r"Label\(s\) may have changed")),
    ("latex-warning", re.compile(r"^LaTeX Warning:", re.MULTILINE)),
    ("package-warning", re.compile(r"^Package \S+ Warning:", re.MULTILINE)),
    ("overfull-box", re.compile(r"^Overfull \\[hv]box")),
    ("error", re.compile(r"^! ", re.MULTILINE)),
]


def main() -> int:
    if not LOG.exists():
        print(f"missing build log: {LOG}", file=sys.stderr)
        return 3
    text = LOG.read_text(encoding="utf-8", errors="replace")
    found = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            line = text[: m.start()].count("\n") + 1
            snippet = text.splitlines()[line - 1].strip()
            found.append((name, line, snippet))
    if not found:
        pages = re.search(r"Output written on .*?\((\d+) pages?", text)
        print(f"build log clean: no undefined references, no LaTeX warnings, no overfull boxes")
        if pages:
            print(f"pages: {pages.group(1)}")
        return 0
    print(f"{len(found)} finding(s) in {LOG}:")
    for name, line, snippet in found:
        print(f"  [{name}] line {line}: {snippet[:120]}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
