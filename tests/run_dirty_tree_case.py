"""T12: an agent edit must not destroy uncommitted human work.

Scenario, in a scratch repository:

  1. commit a baseline;
  2. the human makes an uncommitted edit in `sections/introduction.tex`;
  3. the agent (scripted, deterministic) edits a *different paragraph* in the
     same file and appends a sentence to `sections/conclusion.tex`;
  4. assert that the human's sentence is still present in the working tree, that
     both changes appear in `git diff`, and that the guardrail still runs on the
     combined diff.

This tests the tooling and the recorded procedure. It cannot test that a model
will obey `AGENTS.md`; it tests that the tooling gives it no excuse not to.

Exit codes
    0  passes
    2  the human change was lost or the diff does not contain both edits
    3  could not set up
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ["main.tex", "references.bib", ".latexmkrc", "sections", "tools"]

HUMAN_OLD = "Prior systems treat this decision as a scheduling problem"
HUMAN_NEW = "Earlier systems treat this decision purely as a scheduling problem"
AGENT_OLD = "The policy is intentionally simple, because our goal is a reproducible baseline"
AGENT_NEW = "The policy stays deliberately simple, because our goal is a reproducible baseline"
AGENT_ADD = "We report every number below as a property of the synthetic workload only."


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="dirty-tree-"))
    repo = work / "paper"
    try:
        repo.mkdir()
        for item in COPY:
            src, dst = ROOT / item, repo / item
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)

        git(repo, "init", "-q")
        git(repo, "config", "user.email", "selftest@example.invalid")
        git(repo, "config", "user.name", "selftest")
        git(repo, "add", "-A")
        if git(repo, "commit", "-qm", "baseline").returncode != 0:
            print("could not commit baseline", file=sys.stderr)
            return 3

        intro = repo / "sections" / "introduction.tex"
        conclusion = repo / "sections" / "conclusion.tex"

        # --- step 2: the human edits, and does not commit ---------------------
        text = intro.read_text(encoding="utf-8")
        if HUMAN_OLD not in text:
            print("human anchor missing", file=sys.stderr)
            return 3
        intro.write_text(text.replace(HUMAN_OLD, HUMAN_NEW, 1), encoding="utf-8")

        dirty = git(repo, "status", "--porcelain").stdout.strip()
        print(f"step 2: human edit uncommitted -> {dirty!r}")
        if "introduction.tex" not in dirty:
            print("FAIL: the human edit is not visible to git status")
            return 2

        # --- step 3: the agent edits the same file, another paragraph --------
        text = intro.read_text(encoding="utf-8")
        if AGENT_OLD not in text:
            print("agent anchor missing", file=sys.stderr)
            return 3
        text = text.replace(AGENT_OLD, AGENT_NEW, 1)
        intro.write_text(text, encoding="utf-8")
        conclusion.write_text(
            conclusion.read_text(encoding="utf-8").rstrip() + "\n\n" + AGENT_ADD + "\n",
            encoding="utf-8",
        )

        # --- step 4: assert both survive ------------------------------------
        diff = git(repo, "diff", "--", "sections").stdout
        checks = {
            "human edit survives in file": HUMAN_NEW in intro.read_text(encoding="utf-8"),
            "human edit appears in diff": HUMAN_NEW in diff,
            "agent edit appears in diff": AGENT_NEW in diff,
            "agent addition appears in diff": AGENT_ADD in diff,
            # The original wording must appear only as a removed (-) line.
            "human edit was not reverted": not any(
                line.startswith("+") and HUMAN_OLD in line and HUMAN_NEW not in line
                for line in diff.splitlines()
            ),
        }
        for name, ok in checks.items():
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

        proc = subprocess.run(
            [sys.executable, "-I", "tools/check_invariants.py", "--base", "HEAD"],
            cwd=repo, capture_output=True, text=True,
        )
        guard_ok = proc.returncode == 0
        print(f"  [{'PASS' if guard_ok else 'FAIL'}] guardrail runs on the combined "
              f"diff (exit {proc.returncode})")
        if not guard_ok:
            print(proc.stdout)

        ok = all(checks.values()) and guard_ok
        print("\n" + ("PASS: uncommitted human work survived an agent edit"
                      if ok else "FAIL: human work or a diff is missing"))
        return 0 if ok else 2
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
