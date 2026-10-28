"""Run every test suite in series and record one result line each.

The suites run one at a time on purpose. Each starts its own server subprocesses,
and several suites running concurrently on a Windows host starve each other's
environment probes -- a test that passes alone then fails for a reason that has
nothing to do with the product.

Each suite also gets its own log file, with stdout and stderr kept apart. When
they share one pipe, unittest's verbose output (stderr) interleaves with the
runner's summary lines (stdout) and a failure becomes very hard to read.

Run:  python -I tests/run_all_tests.py
Exit: 0 all suites passed, 1 at least one failed
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests" / "results"

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
    RESULTS.mkdir(parents=True, exist_ok=True)
    results = []
    for index, (name, argv) in enumerate(SUITES, 1):
        started = time.time()
        stdout_path = RESULTS / f"suite-{index:02d}.out.log"
        stderr_path = RESULTS / f"suite-{index:02d}.err.log"
        with stdout_path.open("w", encoding="utf-8", errors="replace") as out, \
             stderr_path.open("w", encoding="utf-8", errors="replace") as err:
            proc = subprocess.run([sys.executable, "-I", *argv], cwd=ROOT,
                                  stdout=out, stderr=err)
        elapsed = time.time() - started
        results.append((name, proc.returncode, elapsed, stderr_path))
        status = "PASS" if proc.returncode == 0 else "FAIL"
        print(f"[{status}] {name:36} exit {proc.returncode:>3}  {elapsed:5.1f}s  "
              f"log: {stderr_path.name}", flush=True)

    failed = [r for r in results if r[1] != 0]
    print(f"\n{len(results) - len(failed)}/{len(results)} suites passed")
    for name, code, _, log in failed:
        print(f"  failed: {name} (exit {code}) — see {log}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
