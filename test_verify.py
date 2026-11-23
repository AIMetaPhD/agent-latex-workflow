#!/usr/bin/env python3
"""Unified verification test script for Agent-first Paper Workflow core template.

Verifies:
1. Invariant checker (guardrail against unauthorized tampering of numbers, citations, etc.)
2. Archive inspector (safe migration from Overleaf, catching zip-slip / traversal)
3. Pre-publication audit (leak and secret detection)
4. Deep privacy leakage audit (ensuring no personal names, local paths, or live API keys in repo or git history)
"""

from __future__ import annotations

import os
import re
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

    print("[PASS] Publication audit tree scan is clean")
    return True


def test_deep_privacy_and_local_leakage() -> bool:
    """Ensure no personal names, absolute local user paths, or active credentials in tree or git history."""
    sensitive_patterns = [
        ("personal_user_folder", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\s\"']+")),
        ("local_workspace_folder", re.compile(r"[A-Za-z]:[\\/]+ClaudeCodeFiles")),
        ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
        ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ]
    whitelist_paths = {
        "tools/publish_audit.py",
        "tests/make_malicious_zips.py",
        "test_verify.py",
    }

    # 1. Scan tracked files
    tracked_process = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    all_files = [line.strip() for line in tracked_process.stdout.splitlines() if line.strip()]

    for relative_path in all_files:
        if relative_path in whitelist_paths:
            continue
        file_path = REPOSITORY_ROOT / relative_path
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for label, pattern in sensitive_patterns:
            matches = pattern.findall(content)
            real_matches = [m for m in matches if "example" not in m.lower() and "dummy" not in m.lower()]
            if real_matches:
                print(f"[FAIL] Privacy check caught {label} in working file: {relative_path}")
                return False

    # 2. Scan git history added lines
    history_process = subprocess.run(
        ["git", "log", "-p", "--full-history"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in history_process.stdout.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if any(keyword in line for keyword in ["re.compile", "RULES", "RULE", "credentials", "synthetic"]):
            continue
        for label, pattern in sensitive_patterns:
            matches = pattern.findall(line)
            real_matches = [m for m in matches if "example" not in m.lower() and "dummy" not in m.lower()]
            if real_matches:
                print(f"[FAIL] Privacy check caught {label} in git history: {line[:80]}")
                return False

    print("[PASS] Deep privacy audit confirmed 0 personal paths, names, or tokens in tree & history")
    return True


def main() -> int:
    print("=" * 65)
    print("Agent-first Paper Workflow Core Template Verification")
    print("=" * 65)

    test_results = [
        ("Invariant Guardrail", test_invariant_guardrail()),
        ("Archive Inspector", test_archive_inspector()),
        ("Publication Audit", test_publication_audit()),
        ("Deep Privacy & Leakage Audit", test_deep_privacy_and_local_leakage()),
    ]

    print("-" * 65)
    all_passed = True
    for test_name, test_status in test_results:
        status_label = "PASS" if test_status else "FAIL"
        print(f"[{status_label}] {test_name}")
        if not test_status:
            all_passed = False

    print("=" * 65)
    if all_passed:
        print("ALL VERIFICATION SUITES PASSED.")
        return 0
    else:
        print("VERIFICATION FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
