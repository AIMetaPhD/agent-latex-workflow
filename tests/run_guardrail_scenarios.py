"""Scenario matrix for tools/check_invariants.py.

Runs each failure injection against a scratch copy of the sample, so the real
working tree is never touched.  Writes tests/results/guardrail-scenarios.txt.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = [
    "sections/abstract.tex", "sections/introduction.tex", "sections/method.tex",
    "sections/results.tex", "sections/conclusion.tex", "main.tex",
    "references.bib",
]


def patch(base: Path, rel: str, old: str, new: str) -> None:
    p = base / rel
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {rel}: {old!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def run_case(name: str, edits, mode: str = "polish", expect_exit: int = 2):
    tmp = Path(tempfile.mkdtemp(prefix="guardrail-"))
    try:
        for rel in SAMPLE + ["tools/check_invariants.py"]:
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "-c", "user.email=t@example.invalid",
                        "-c", "user.name=t", "commit", "-qm", "base"],
                       cwd=tmp, check=True)
        for rel, old, new in edits:
            patch(tmp, rel, old, new)
        proc = subprocess.run(
            [sys.executable, "-I", "tools/check_invariants.py",
             "--base", "HEAD", "--mode", mode],
            cwd=tmp, capture_output=True, text=True,
        )
        ok = proc.returncode == expect_exit
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: exit {proc.returncode} "
              f"(expected {expect_exit})")
        for line in proc.stdout.splitlines():
            if any(k in line for k in ("RISK", "REVIEW", "GUARDRAIL", "could not parse")):
                print("       " + line.strip())
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = [
    ("S0 clean tree, nothing changed", [], "polish", 0),
    ("S1 one measurement 92.4 -> 92.8", [
        ("sections/abstract.tex", r"92.4\%", r"92.8\%")], "polish", 2),
    ("S2 citation key smith2024 -> smith2025", [
        ("sections/introduction.tex", r"\cite{smith2024}", r"\cite{smith2025}")], "polish", 2),
    ("S3 equation constant t_r -> 2t_r", [
        ("sections/method.tex", r"(1-\gamma)\,\bigl(D_r - t_r\bigr)",
         r"(1-\gamma)\,\bigl(D_r - 2t_r\bigr)")], "polish", 2),
    ("S4 label eq:admit -> eq:adm", [
        ("sections/method.tex", r"\label{eq:admit}", r"\label{eq:adm}"),
        ("sections/method.tex", r"\eqref{eq:admit}", r"\eqref{eq:adm}")], "polish", 2),
    ("S5 author block rewritten", [
        ("main.tex", "Anonymous Sample Author", "Jane Q. Realperson")], "polish", 2),
    ("S6 language-only rewrite", [
        ("sections/introduction.tex", "Queueing is cheap", "Queueing is inexpensive")], "polish", 0),
    ("S7 bibliography key renamed", [
        ("references.bib", "@article{lee2025,", "@article{lee2025x,")], "polish", 2),
    ("S8 measurement, content mode (review, not block)", [
        ("sections/abstract.tex", r"92.4\%", r"92.8\%")], "content", 0),
    ("S9 two table cells changed", [
        ("sections/results.tex", r"71.0\%", r"71.4\%"),
        ("sections/results.tex", r"63.5\%", r"63.9\%")], "polish", 2),
    ("S10 figure include target changed", [
        ("sections/results.tex", r"\begin{table}[t]", r"\begin{table}[!t]")], "polish", 0),
]


def main() -> int:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} scenarios behaved as expected")
    out = ROOT / "tests" / "results"
    out.mkdir(parents=True, exist_ok=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
