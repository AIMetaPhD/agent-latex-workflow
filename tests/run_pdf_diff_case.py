"""Self-contained multi-file PDF diff case.

Copies the sample into a scratch git repository, commits a baseline, edits a
sentence inside `sections/method.tex` (a sub-file pulled in with \\input), then
runs tools/pdf_diff.py against the two commits and asserts that the changed
sentence appears in the extracted PDF text.

This exists so the PDF diff can be reproduced by anyone -- including an
independent tester -- without relying on branches in this repository's history.

Exit codes
    0  the diff PDF was built and the change is visible in its text
    2  the diff ran but the change was not found
    3  the case could not be set up (missing tool, failed copy)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = [
    "main.tex", "references.bib", ".latexmkrc", "sections", "tools",
]
OLD = "When \\eqref{eq:admit} fails, the request stays queued at node $i$."
NEW = ("When \\eqref{eq:admit} fails, the request is left in the local queue at node $i$ "
       "and retried after the next measurement.")
EXPECT = "is left in the local queue"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def main() -> int:
    for tool in ("git", "latexmk", "latexpand", "latexdiff"):
        if shutil.which(tool) is None:
            print(f"cannot run: {tool} is not installed", file=sys.stderr)
            return 3

    work = Path(tempfile.mkdtemp(prefix="pdf-diff-case-"))
    repo = work / "paper"
    try:
        repo.mkdir()
        for item in COPY:
            src, dst = ROOT / item, repo / item
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        git(repo, "init", "-q")
        git(repo, "config", "user.email", "selftest@example.invalid")
        git(repo, "config", "user.name", "selftest")
        git(repo, "add", "-A")
        base = git(repo, "commit", "-qm", "baseline")
        if base.returncode != 0:
            print("could not commit the baseline: " + base.stderr, file=sys.stderr)
            return 3

        method = repo / "sections" / "method.tex"
        text = method.read_text(encoding="utf-8")
        if OLD not in text:
            print("the anchor sentence is missing from sections/method.tex",
                  file=sys.stderr)
            return 3
        method.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "edit: one sentence in a sub-file")

        proc = subprocess.run(
            [sys.executable, "-I", "tools/pdf_diff.py",
             "--base", "HEAD~1", "--target", "HEAD",
             "--expect", EXPECT, "--out", "dist/review-pack"],
            cwd=repo, capture_output=True, text=True,
        )
        print(proc.stdout.strip() or proc.stderr.strip())
        if proc.returncode == 0:
            print("\nPASS: the diff PDF renders the change made inside sections/method.tex")
        else:
            print(f"\nFAIL: tools/pdf_diff.py exited {proc.returncode}")
        return proc.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
