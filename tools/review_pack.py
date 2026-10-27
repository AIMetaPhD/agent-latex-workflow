#!/usr/bin/env python3
"""Assemble a review pack for a co-author who does not use Git or TeX.

This script copies files that already exist. It does not build, does not parse
LaTeX, does not rewrite Git history and does not call a model. If an input is
missing it records that in MANIFEST.md instead of inventing an output.

Two modes:

  review pack (default)
      main.pdf + optional diff PDF + optional summary -> <out>/ + MANIFEST.md

  snapshot
      main.pdf + tracked source at the current commit + SNAPSHOT.md
      The snapshot records the commit, the PDF hash and the build environment
      so a submission can be reproduced later.

Exit codes
    0  written
    2  a required input is missing (the manifest records what was written)
    4  refusing: the snapshot would capture a dirty working tree

Usage
    python -I tools/review_pack.py --out dist/review-pack \\
        --pdf build/main.pdf --diff dist/main-diff.pdf --summary review-summary.md

    python -I tools/review_pack.py --snapshot dist/snapshots/submission \\
        --pdf build/main.pdf --stage submission
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def tool_version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return "not installed"
    text = (proc.stdout or proc.stderr).strip().splitlines()
    for line in text:
        if any(ch.isdigit() for ch in line):
            return line.strip()
    return text[0].strip() if text else "unknown"


def build_review_pack(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    status = 0
    lines = ["# Review pack", ""]
    lines.append(f"Generated: {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC")
    lines.append("")

    try:
        lines.append(f"Commit: `{git('rev-parse', 'HEAD')}` on `{git('rev-parse', '--abbrev-ref', 'HEAD')}`")
    except RuntimeError as exc:
        lines.append(f"Commit: unavailable ({exc})")

    dirty = git("status", "--porcelain")
    lines.append("Working tree at pack time: " + ("**dirty** — the files below may not match the commit" if dirty else "clean"))
    last = git("log", "-1", "--pretty=%s")
    lines.append(f"Last commit: {last}")
    lines.append("")

    def take(label: str, src: str | None, required: bool) -> None:
        nonlocal status
        if not src:
            lines.append(f"- {label}: **not supplied**")
            if required:
                status = 2
            return
        src_path = Path(src)
        if not src_path.is_absolute():
            src_path = ROOT / src_path
        if not src_path.exists():
            lines.append(f"- {label}: **missing at `{src}`**")
            if required:
                status = 2
            return
        dst = out / src_path.name
        shutil.copy2(src_path, dst)
        lines.append(f"- {label}: `{dst.name}` ({dst.stat().st_size} bytes, sha256 `{sha256(dst)[:16]}…`)")

    lines.append("## Files")
    take("Clean PDF", args.pdf, True)
    take("Diff PDF", args.diff, False)
    take("Change summary", args.summary, False)

    lines.append("")
    lines.append("## For the reader")
    lines.append("")
    if args.diff:
        lines.append("Open the diff PDF to see the changes marked in the margin.")
    else:
        lines.append("No diff PDF was supplied. The change summary below is the readable record;")
        lines.append("ask for a plain-text diff if you need to see the source changes.")
    if args.note:
        lines.append("")
        lines.append("Note: " + args.note)
    lines.append("")
    lines.append("## What this pack does not contain")
    lines.append("")
    lines.append("- A judgement on whether the science is right.")
    lines.append("- A guarantee that the PDF matches the commit if the tree was dirty.")
    lines.append("- Any source file that was not explicitly supplied.")

    (out / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return status


def build_snapshot(args: argparse.Namespace) -> int:
    out = Path(args.snapshot)
    if git("status", "--porcelain"):
        print("REFUSING: the working tree is dirty. A snapshot of a dirty tree cannot be "
              "reproduced. Commit or stash first.", file=sys.stderr)
        return 4

    pdf = Path(args.pdf)
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    if not pdf.exists():
        print(f"REFUSING: no PDF at {pdf}. Run `latexmk` first.", file=sys.stderr)
        return 2

    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf, out / "main.pdf")
    digest = sha256(out / "main.pdf")

    commit = git("rev-parse", "HEAD")
    archive = out / "source.tar.gz"
    proc = subprocess.run(
        ["git", "archive", "--format=tar.gz", "--prefix", f"source-{commit[:12]}/", "-o", str(archive), commit],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print("ERROR: git archive failed: " + proc.stderr.strip(), file=sys.stderr)
        return 2

    record = {
        "stage": args.stage,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree": "clean",
        "pdf": {"name": "main.pdf", "bytes": (out / "main.pdf").stat().st_size, "sha256": digest},
        "source": {"name": archive.name, "sha256": sha256(archive)},
        "build": {
            "command": "latexmk",
            "engine": "pdflatex",
            "versions": {
                "latexmk": tool_version(["latexmk", "-v"]),
                "pdflatex": tool_version(["pdflatex", "--version"]),
                "bibtex": tool_version(["bibtex", "--version"]),
                "git": tool_version(["git", "--version"]),
            },
        },
        "requested_by": args.requested_by,
    }
    (out / "SNAPSHOT.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    md = [
        f"# Snapshot — {args.stage}",
        "",
        f"- Generated: {record['generated_utc']}",
        f"- Commit: `{commit}` on `{record['branch']}`",
        f"- Working tree: clean",
        f"- PDF: `main.pdf`, {record['pdf']['bytes']} bytes",
        f"- PDF SHA256: `{digest}`",
        f"- Source archive: `{archive.name}`",
        f"- Build: `latexmk` (pdflatex), latexmk {record['build']['versions']['latexmk']}",
        f"- Requested by: {args.requested_by}",
        "",
        "## Not done by this snapshot",
        "",
        "No git tag was created, nothing was pushed, and nothing was uploaded.",
        "The double-blind checklist in `skills/paper-release/SKILL.md` is a manual step.",
    ]
    (out / "SNAPSHOT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Copy built artifacts into a review pack or snapshot.")
    ap.add_argument("--out", help="review pack directory (default dist/review-pack)")
    ap.add_argument("--snapshot", help="snapshot directory instead of a review pack")
    ap.add_argument("--pdf")
    ap.add_argument("--diff")
    ap.add_argument("--summary")
    ap.add_argument("--note", default="")
    ap.add_argument("--stage", choices=("submission", "revision", "camera-ready"),
                    default="submission")
    ap.add_argument("--requested-by", default="the author")
    args = ap.parse_args(argv)

    if args.snapshot:
        if not args.pdf:
            ap.error("--snapshot requires --pdf")
        return build_snapshot(args)
    if not args.out:
        args.out = "dist/review-pack"
    if not args.pdf:
        ap.error("--pdf is required")
    return build_review_pack(args)


if __name__ == "__main__":
    sys.exit(main())
