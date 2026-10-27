"""Repository self-test. Records evidence to tests/results/.

Every case runs a real command and records the command, the exit code and the
relevant output. Nothing is asserted from memory.

Usage
    python -I tests/run_all.py            # everything the host can run
    python -I tests/run_all.py --quick    # skip the slow cases
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests" / "results"


def tool_version(cmd: list[str]) -> str:
    exe = shutil.which(cmd[0])
    if exe is None:
        return f"{cmd[0]}: NOT INSTALLED"
    try:
        proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return f"{cmd[0]}: timed out"
    text = (proc.stdout or proc.stderr).strip().splitlines()
    for line in text:
        if re.search(r"\d+\.\d+", line) and "Initial Win CP" not in line:
            return line.strip()
    return text[0].strip() if text else f"{cmd[0]}: (no version output)"


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout, errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the slow latexdiff case")
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    env = {
        "utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "cwd": str(ROOT),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "tools": {name: tool_version(cmd) for name, cmd in {
            "git": ["git", "--version"],
            "latexmk": ["latexmk", "-v"],
            "pdflatex": ["pdflatex", "--version"],
            "bibtex": ["bibtex", "--version"],
            "latexdiff": ["latexdiff", "--version"],
            "latexpand": ["latexpand", "--version"],
            "pdftotext": ["pdftotext", "-v"],
            "perl": ["perl", "-v"],
        }.items()},
    }

    cases: list[tuple[str, list[list[str]], int]] = [
        ("T01 build from scratch",
         [["latexmk", "-C"], ["latexmk"]], 0),
        ("T01b no undefined references, no LaTeX warnings",
         [["python", "-I", "tests/check_build_log.py"]], 0),
        ("T02 guardrail scenarios",
         [["python", "-I", "tests/run_guardrail_scenarios.py"]], 0),
        # Deterministic: compares HEAD with itself, so the result does not depend
        # on whether the developer happens to have uncommitted work. The dirty
        # working tree is covered on purpose by T12.
        ("T03 guardrail no-op between identical refs",
         [["python", "-I", "tools/check_invariants.py", "--base", "HEAD",
           "--target", "HEAD"]], 0),
        ("T05 zip inspection fixtures (regenerate)",
         [["python", "-I", "tests/make_malicious_zips.py"]], 0),
        ("T12 uncommitted human work survives an agent edit",
         [["python", "-I", "tests/run_dirty_tree_case.py"]], 0),
        ("T13 publication audit",
         [["python", "-I", "tools/publish_audit.py"]], 0),
    ]
    if not args.quick:
        cases.append(("T03b multi-file PDF diff (self-contained fixture)",
                      [["python", "-I", "tests/run_pdf_diff_case.py"]], 0))

    lines = ["# Self-test record", ""]
    lines.append(f"- UTC: {env['utc']}")
    lines.append(f"- Host: {env['os']} / {env['machine']}")
    lines.append(f"- Python: {env['python']}")
    lines.append(f"- Git HEAD: `{env['git_head']}`")
    lines.append("")
    lines.append("## Tool versions")
    lines.append("")
    for name, version in env["tools"].items():
        lines.append(f"- `{name}`: {version}")
    lines.append("")
    lines.append("## Cases")
    lines.append("")

    failures = 0
    for name, commands, expected in cases:
        statuses = []
        outputs = []
        for cmd in commands:
            try:
                code, out = run(cmd)
            except Exception as exc:  # noqa: BLE001
                code, out = 99, f"could not run: {exc}"
            statuses.append(code)
            outputs.append(out)
        ok = all(code == expected for code in statuses)
        failures += 0 if ok else 1
        verdict = "PASS" if ok else "FAIL"
        lines.append(f"### {name} — {verdict}")
        lines.append("")
        lines.append(f"- commands: `{'` then `'.join(' '.join(c) for c in commands)}`")
        lines.append(f"- exit codes: {statuses} (expected {expected})")
        lines.append("")
        lines.append("```text")
        tail = (outputs[-1] or "").strip().splitlines()[-14:]
        lines.extend(tail)
        lines.append("```")
        lines.append("")

    lines.append("## Not covered by this run")
    lines.append("")
    lines.append("- macOS: no such host was available (`BLOCKED`).")
    lines.append("- Linux: only GitHub Actions can run it; not executed locally (`NOT_RUN`).")
    lines.append("- Muse independent QA: no channel configured (`BLOCKED`), see MUSE_HANDOFF.md.")
    lines.append("- Scientific correctness and reference accuracy: not machine-checkable.")

    report = RESULTS / "selftest-run.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "environment.json").write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"\nwritten: {report}")
    print(f"{len(cases) - failures}/{len(cases)} cases passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
