#!/usr/bin/env python3
"""Produce a PDF diff between two git revisions of a multi-file LaTeX paper.

Why this exists rather than `latexdiff-vc --git`: on Windows that wrapper fails.
Its `checkout_dir` runs

    git archive --format=tar $rev | ( cd $dirname ; tar -xf -)

through Perl's `system`, which on Windows hands the string to `cmd.exe`. cmd.exe
has no `( ... )` subshell and no `;`, so it prints "The system cannot find the
path specified" and exits 2 before any diff is produced. The workaround inside
this script is not clever: check the old revision out with `git archive`
directly, flatten both sides with `latexpand`, and call `latexdiff` on the two
flattened files. Those three tools behave the same on Windows, macOS and Linux.

`--flatten` is not optional for a multi-file paper: without it latexdiff only
sees `\\input{sections/...}` and reports no change at all.

Exit codes
    0  diff PDF built and the change was found in the extracted text
    2  diff PDF built, but the expected phrase was not found (suspect a no-op)
    3  could not build (latexdiff, latexpand or latexmk failed); reason printed

Usage
    python -I tools/pdf_diff.py --base <old-ref> --target <new-ref> \\
        --expect "the sentence that changed" --out dist/review-pack
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None, shell: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, shell=shell, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def git_archive(ref: str, dest: Path) -> None:
    """Extract `ref` into `dest` without a shell subshell."""
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(
        ["git", "archive", "--format=tar", ref],
        cwd=ROOT, capture_output=True,
    )
    if tar.returncode != 0:
        raise RuntimeError("git archive failed: " + tar.stderr.decode("utf-8", "replace"))
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(dest)],
        input=tar.stdout, capture_output=True,
    )
    if extract.returncode != 0:
        raise RuntimeError("tar failed: " + extract.stderr.decode("utf-8", "replace"))


def flatten(src_dir: Path, main: str, dest: Path) -> None:
    proc = run(["latexpand", main, "--fatal"], cwd=src_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            "latexpand failed in " + str(src_dir) + ": " + (proc.stderr or proc.stdout).strip()
        )
    dest.write_text(proc.stdout, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Multi-file PDF diff between two git revisions.")
    ap.add_argument("--base", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--main", default="main.tex")
    ap.add_argument("--expect", default="", help="text that must appear in the diff output")
    ap.add_argument("--out", default="dist/review-pack")
    ap.add_argument("--keep-tex", action="store_true", help="also keep the flattened sources")
    args = ap.parse_args(argv)

    work = Path(tempfile.mkdtemp(prefix="pdf-diff-"))
    report: dict[str, object] = {
        "base": args.base, "target": args.target, "main": args.main,
        "tool_versions": {},
        "steps": [],
    }
    try:
        for tool, cmd in (("latexdiff", ["latexdiff", "--version"]),
                          ("latexpand", ["latexpand", "--version"]),
                          ("latexmk", ["latexmk", "-v"])):
            proc = run(cmd)
            first = (proc.stdout or proc.stderr).splitlines()
            report["tool_versions"][tool] = first[0] if first else "unknown"

        old_dir, new_dir = work / "old", work / "new"
        git_archive(args.base, old_dir)
        git_archive(args.target, new_dir)

        flat_old, flat_new = work / "old-flat.tex", work / "new-flat.tex"
        flatten(old_dir, args.main, flat_old)
        flatten(new_dir, args.main, flat_new)
        report["steps"].append({
            "step": "flatten",
            "old_lines": len(flat_old.read_text(encoding="utf-8").splitlines()),
            "new_lines": len(flat_new.read_text(encoding="utf-8").splitlines()),
        })

        diff_tex = work / "main-diff.tex"
        proc = run(["latexdiff", str(flat_old), str(flat_new)])
        if proc.returncode != 0 or not proc.stdout:
            raise RuntimeError("latexdiff failed: " + (proc.stderr or "empty output").strip())
        diff_tex.write_text(proc.stdout, encoding="utf-8")
        markers = proc.stdout.count("DIFadd") + proc.stdout.count("DIFdel")
        report["steps"].append({"step": "latexdiff", "dif_markers": markers})
        if markers == 0:
            report["warning"] = "latexdiff produced no DIF markers; the two revisions may be identical"

        # Build with the project's own .latexmkrc next to it so fonts and biblio
        # resolve exactly as they do for the real paper.
        build_dir = work / "build"
        build_dir.mkdir()
        shutil.copy2(ROOT / ".latexmkrc", build_dir / ".latexmkrc")
        for extra in ("references.bib",):
            if (ROOT / extra).exists():
                shutil.copy2(ROOT / extra, build_dir / extra)
        shutil.copy2(diff_tex, build_dir / "main-diff.tex")
        proc = run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main-diff.tex"],
                   cwd=build_dir)
        report["steps"].append({"step": "latexmk", "exit": proc.returncode})
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr)[-1500:]
            raise RuntimeError("latexmk failed on the diff:\n" + tail)

        pdf = build_dir / "build" / "main-diff.pdf"
        if not pdf.exists():
            pdf = build_dir / "main-diff.pdf"
        if not pdf.exists():
            searched = "\n  ".join(str(p) for p in build_dir.rglob("*.pdf"))
            raise RuntimeError(
                "latexmk reported success but main-diff.pdf is missing; PDFs found:\n  "
                + (searched or "(none)")
            )

        text_check: dict[str, object] = {"expect": args.expect}
        status = 0
        if args.expect:
            pdftotext = shutil.which("pdftotext")
            if pdftotext is None:
                text_check["note"] = "pdftotext not installed; change not verified in the PDF text"
                status = 2
            else:
                proc = run([pdftotext, str(pdf), "-"])
                plain = proc.stdout
                # A rendered diff interleaves deleted and inserted characters,
                # so a sentence can appear with separators. Compare on letters.
                squashed = "".join(ch for ch in plain if ch.isalnum()).lower()
                needle = "".join(ch for ch in args.expect if ch.isalnum()).lower()
                text_check["found"] = needle in squashed
                text_check["pdftotext_exit"] = proc.returncode
                if not text_check["found"]:
                    status = 2
        report["text_check"] = text_check

        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, out / "main-diff.pdf")
        if args.keep_tex:
            shutil.copy2(diff_tex, out / "main-diff.tex")
            shutil.copy2(flat_old, out / "old-flat.tex")
            shutil.copy2(flat_new, out / "new-flat.tex")
        report["pdf"] = str(out / "main-diff.pdf")
        report["pdf_bytes"] = pdf.stat().st_size
        report["status"] = "OK" if status == 0 else "UNVERIFIED"
        print(json.dumps(report, indent=2))
        return status
    except Exception as exc:  # noqa: BLE001 - the reason is the output
        report["status"] = "FAILED"
        report["error"] = str(exc)
        print(json.dumps(report, indent=2))
        return 3
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
