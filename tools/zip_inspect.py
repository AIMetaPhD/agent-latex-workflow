#!/usr/bin/env python3
"""Inspect an archive for the hazards that matter when migrating a paper.

This tool never extracts, never follows a link and never executes anything from
the archive. It reads the central directory, reports what it finds, and stops.

The hazards it looks for, and why each one matters for an Overleaf export:

  path traversal      ../ entries that would write outside the destination
  absolute path       /etc/... or C:\\... entries
  symbolic link       a link can point anywhere on the disk once extracted
  case collision      README.tex / readme.tex: one silently replaces the other
                      on Windows and macOS
  expansion bomb      a small archive that expands to an enormous tree
  executable config   .latexmkrc, Makefile, *.sh: these run commands when the
                      project is built, so importing them is running code
  non-UTF-8 names     mojibake that breaks \\input and file references

Exit codes
    0  CLEAN       nothing in the categories checked
    2  RISKY       at least one blocking finding; do not auto-extract
    3  UNREADABLE  the archive could not be parsed

Usage
    python -I tools/zip_inspect.py path/to/overleaf-export.zip
    python -I tools/zip_inspect.py archive.zip --json
    python -I tools/zip_inspect.py archive.zip --max-ratio 200 --max-bytes 500000000
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

EXECUTABLE_CONFIG = {
    ".latexmkrc": "latexmk runs this file as Perl",
    "latexmkrc": "latexmk runs this file as Perl",
    "Makefile": "make executes its recipes",
    "makefile": "make executes its recipes",
}
EXECUTABLE_SUFFIXES = {
    ".sh": "shell script",
    ".bat": "batch script",
    ".cmd": "batch script",
    ".ps1": "PowerShell script",
    ".py": "Python script",
    ".pl": "Perl script",
}

# Extensions that are *expected* in a LaTeX project and should not be flagged
# merely for existing. Executable ones are reported regardless.
SENSITIVE_NAME_HINTS = (".env", "id_rsa", "id_ed25519", "credentials", ".netrc", ".git-credentials")
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


@dataclass
class Finding:
    severity: str          # "block" | "review" | "info"
    category: str
    entry: str
    detail: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "category": self.category,
                "entry": self.entry, "detail": self.detail}


@dataclass
class Report:
    archive: str = ""
    entries: int = 0
    total_uncompressed: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]


def inspect(path: Path, max_ratio: float, max_bytes: int) -> Report:
    report = Report(archive=str(path))
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise RuntimeError(f"cannot read archive: {exc}") from exc

    with zf:
        infos = zf.infolist()
        report.entries = len(infos)
        report.total_uncompressed = sum(i.file_size for i in infos)

        seen_casefold: dict[str, str] = {}
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue

            # --- path shape -------------------------------------------------
            pure = PurePosixPath(name.replace("\\", "/"))
            if pure.is_absolute() or (len(pure.parts) > 0 and pure.parts[0].endswith(":")):
                report.findings.append(Finding(
                    "block", "absolute-path", name,
                    "entry would write to an absolute location"))
            if ".." in pure.parts:
                report.findings.append(Finding(
                    "block", "path-traversal", name,
                    "entry escapes the destination directory"))

            # --- symlinks ---------------------------------------------------
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                report.findings.append(Finding(
                    "block", "symlink", name,
                    "symbolic link; its target is outside this inspection"))

            # --- case collisions -------------------------------------------
            key = name.casefold()
            if key in seen_casefold and seen_casefold[key] != name:
                report.findings.append(Finding(
                    "block", "case-collision", name,
                    f"differs only by case from {seen_casefold[key]!r}"))
            else:
                seen_casefold[key] = name

            # --- compression ratio -----------------------------------------
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_ratio and info.file_size > 1_000_000:
                    report.findings.append(Finding(
                        "block", "expansion-bomb", name,
                        f"{info.file_size} bytes from {info.compress_size} "
                        f"(ratio {ratio:.0f}:1, limit {max_ratio:.0f}:1)"))

            # --- executable build configuration ----------------------------
            base = pure.name
            if base in EXECUTABLE_CONFIG:
                report.findings.append(Finding(
                    "block", "executable-config", name, EXECUTABLE_CONFIG[base]))
            elif pure.suffix.lower() in EXECUTABLE_SUFFIXES:
                report.findings.append(Finding(
                    "review", "executable-script", name,
                    EXECUTABLE_SUFFIXES[pure.suffix.lower()] + "; read it before running anything"))

            # --- credentials -------------------------------------------------
            lowered = base.lower()
            if lowered in SENSITIVE_NAME_HINTS or lowered.endswith(SECRET_SUFFIXES):
                report.findings.append(Finding(
                    "block", "credential-looking-file", name,
                    "name suggests a secret; never commit it to a repository"))

            # --- encoding ----------------------------------------------------
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                report.findings.append(Finding(
                    "review", "non-utf8-name", name,
                    "filename is not valid UTF-8; \\input may fail"))

        if report.total_uncompressed > max_bytes:
            report.findings.append(Finding(
                "block", "size-limit", "<archive>",
                f"expands to {report.total_uncompressed} bytes, limit {max_bytes}"))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Inspect a ZIP for migration hazards. Never extracts.")
    ap.add_argument("archive", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-ratio", type=float, default=100.0,
                    help="block single entries above this compression ratio (default 100)")
    ap.add_argument("--max-bytes", type=int, default=500_000_000,
                    help="block archives expanding beyond this many bytes (default 500 MB)")
    args = ap.parse_args(argv)

    if not args.archive.exists():
        print(f"ERROR: no such file: {args.archive}", file=sys.stderr)
        return 3
    try:
        report = inspect(args.archive, args.max_ratio, args.max_bytes)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    status = "RISKY" if report.blocking else "CLEAN"
    code = 2 if report.blocking else 0

    if args.json:
        print(json.dumps({
            "archive": report.archive,
            "entries": report.entries,
            "total_uncompressed": report.total_uncompressed,
            "status": status,
            "findings": [f.as_dict() for f in report.findings],
            "note": "inspection only; nothing was extracted or executed",
        }, indent=2))
        return code

    print(f"archive : {report.archive}")
    print(f"entries : {report.entries}  uncompressed: {report.total_uncompressed} bytes")
    print()
    if not report.findings:
        print("no hazard found in the categories checked")
    for f in report.findings:
        print(f"  [{f.severity.upper():6}] {f.category:24} {f.entry}: {f.detail}")
    print()
    print("Nothing was extracted and nothing was executed.")
    print(f"ZIP INSPECTION: {status}")
    if report.blocking:
        print("Do not auto-extract. Follow docs/migrate-from-overleaf.md and")
        print("copy the files you have inspected by hand.")
    return code


if __name__ == "__main__":
    sys.exit(main())
