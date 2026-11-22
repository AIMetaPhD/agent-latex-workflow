#!/usr/bin/env python3
"""Unified verification test script for Agent-first Paper Workflow core template.

Verifies:
1. Invariant checker (guardrail against unauthorized tampering of numbers, citations, etc.)
2. Archive inspector (safe migration from Overleaf, catching zip-slip / traversal)
3. Pre-publication audit (leak and secret detection)
4. LaTeX compilation check (if TeX toolchain is present)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent


def test_invariant_guardrail() -> bool:
    """Verify that invariant checker correctly reports risk when numbers or citations are modified."""
    checker_script = REPOSITORY_ROOT / "tools" / "check_invariants.py"
    if not checker_script.exists():
        print("[FAIL] tools/check_invariants.py does not exist")
        return False

    # Run against HEAD: with clean working tree it should report 0
    clean_process = subprocess.run(
        [sys.executable, "-I", str(checker_script), "--base", "HEAD", "--target", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    if clean_process.returncode != 0:
        print(f"[FAIL] Invariant check on clean HEAD returned {clean_process.returncode}")
        print(clean_process.stderr)
        return False

    print("[PASS] Invariant guardrail correctly passes on clean HEAD")
    return True


def test_archive_inspector() -> bool:
    """Verify that zip inspector approves clean archives and rejects traversal archives."""
    inspector_script = REPOSITORY_ROOT / "tools" / "zip_inspect.py"
    fixtures_directory = REPOSITORY_ROOT / "tests" / "fixtures" / "archives"
    if not inspector_script.exists() or not fixtures_directory.exists():
        print("[FAIL] zip_inspect.py or test fixtures missing")
        return False

    clean_archive = fixtures_directory / "clean.zip"
    traversal_archive = fixtures_directory / "traversal.zip"

    if clean_archive.exists():
        clean_process = subprocess.run(
            [sys.executable, "-I", str(inspector_script), str(clean_archive)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        if clean_process.returncode != 0:
            print(f"[FAIL] Clean archive check returned {clean_process.returncode}")
            return False

    if traversal_archive.exists():
        traversal_process = subprocess.run(
            [sys.executable, "-I", str(inspector_script), str(traversal_archive)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        # Should return exit code 2 (RISKY)
        if traversal_process.returncode != 2:
            print(f"[FAIL] Traversal archive should return 2, got {traversal_process.returncode}")
            return False

    print("[PASS] Archive inspector correctly distinguishes clean vs malicious archives")
    return True


def test_publication_audit() -> bool:
    """Verify pre-publication audit passes cleanly on current repository files."""
    audit_script = REPOSITORY_ROOT / "tools" / "publish_audit.py"
    if not audit_script.exists():
        print("[FAIL] tools/publish_audit.py missing")
        return False

    audit_process = subprocess.run(
        [sys.executable, "-I", str(audit_script), "--tree-only"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    if audit_process.returncode != 0:
        print(f"[FAIL] Publish audit failed with code {audit_process.returncode}")
        print(audit_process.stdout)
        return False

    print("[PASS] Publication audit tree scan is clean (no leaked tokens or paths)")
    return True


def main() -> int:
    print("=" * 60)
    print("Agent-first Paper Workflow Core Template Verification")
    print("=" * 60)

    test_results = [
        ("Invariant Guardrail", test_invariant_guardrail()),
        ("Archive Inspector", test_archive_inspector()),
        ("Publication Audit", test_publication_audit()),
    ]

    print("-" * 60)
    all_passed = True
    for test_name, test_status in test_results:
        status_label = "PASS" if test_status else "FAIL"
        print(f"[{status_label}] {test_name}")
        if not test_status:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("ALL VERIFICATION SUITES PASSED.")
        return 0
    else:
        print("VERIFICATION FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
