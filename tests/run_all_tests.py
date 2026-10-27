"""Run every test suite in series and record a single result line each.

The suites are run one at a time on purpose. Each one starts its own server
subprocesses, and several suites running concurrently on a Windows host starve
each other's environment probes -- a test that passes alone then fails for a
reason that has nothing to do with the product. Running them in series costs a
few seconds and removes that whole class of false alarm.

Run:  python -I tests/run_all_tests.py
Exit: 0 all suites passed, 1 at least one failed
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUITES = [
    ("build log checker", ["tests/check_build_log.py"]),
    ("guardrail scenarios", ["tests/run_guardrail_scenarios.py"]),
    ("PDF diff case", ["tests/run_pdf_diff_case.py"]),
    ("dirty tree case", ["tests/run_dirty_tree_case.py"]),
    ("archive inspector fixtures", ["tests/make_malicious_zips.py"]),
    ("publication audit", ["tools/publish_audit.py"]),
    ("root resolution from foreign cwd", ["tests/test_root_resolution.py"]),
    ("no-TeX degradation", ["tests/test_no_tex_degradation.py"]),
    ("UI robustness (audit regressions)", ["tests/test_ui_robustness.py"]),
    ("UI security", ["tests/test_ui_security.py"]),
    ("UI build behaviour", ["tests/test_ui_build.py"]),
]


def main() -> int:
    results = []
    for name, argv in SUITES:
        started = time.time()
        proc = subprocess.run([sys.executable, "-I", *argv], cwd=ROOT)
        elapsed = time.time() - started
        results.append((name, proc.returncode, elapsed))
        status = "PASS" if proc.returncode == 0 else "FAIL"
        print(f"[{status}] {name:26} exit {proc.returncode:>3}  {elapsed:5.1f}s", flush=True)

    failed = [r for r in results if r[1] != 0]
    print(f"\n{len(results) - len(failed)}/{len(results)} suites passed")
    for name, code, _ in failed:
        print(f"  failed: {name} (exit {code})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
