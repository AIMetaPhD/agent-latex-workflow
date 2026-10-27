"""M06: with no TeX on PATH, the workbench must still start and disable the build.

A PATH is built that contains Python but no TeX, and the server is started with
it. The assertions are about the *reported* state, which is what the page shows:

    * every TeX tool is reported missing, with a reason and an install command;
    * `can_build` is false, so the UI disables the build button;
    * the server itself still answers, and the other panels still work.

Run:  python -I tests/test_no_tex_degradation.py
Exit: 0 passed, 1 failed, 3 could not set up
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ["ui", "tools", "main.tex", "references.bib", ".latexmkrc", "sections"]

# Only what the workbench actually builds with. xelatex/lualatex/biber are not
# used by the default .latexmkrc, so a missing one is not a blocked build -- and
# asserting otherwise would make the test wrong, not the product.
TEX_TOOLS = ("latexmk", "pdflatex", "bibtex", "perl")
OPTIONAL_TOOLS = ("latexdiff", "code")


def make_copy() -> Path:
    work = Path(tempfile.mkdtemp(prefix="no-tex-"))
    for item in COPY:
        src, dst = ROOT / item, work / item
        if src.exists():
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return work


def main() -> int:
    project = make_copy()
    server = None
    try:
        python_dir = Path(sys.executable).parent
        env = {
            "PATH": str(python_dir) + os.pathsep + os.environ.get("SYSTEMROOT", "")
                    + os.sep + "System32",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "PYTHONIOENCODING": "utf-8",
        }
        server = subprocess.Popen(
            [sys.executable, "-I", str(project / "ui" / "server.py"),
             "--no-browser", "--print-url", "--port", "0"],
            cwd=str(project), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        url = (server.stdout.readline() or "").strip()
        m = re.search(r"127\.0\.0\.1:(\d+)/#t=([A-Za-z0-9_\-]+)", url)
        if not m:
            print(f"server did not start without TeX: {url!r}", file=sys.stderr)
            print((server.stderr.read() or "")[:600], file=sys.stderr)
            return 3
        port, token = int(m.group(1)), m.group(2)
        print(f"server started without TeX on 127.0.0.1:{port}")

        def request(method: str, path: str, body: bytes | None = None,
                    headers: dict[str, str] | None = None) -> tuple[int, bytes]:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            merged = {"Host": f"127.0.0.1:{port}"}
            merged.update(headers or {})
            try:
                conn.request(method, path, body=body, headers=merged)
                res = conn.getresponse()
                return res.status, res.read()
            finally:
                conn.close()

        origin = f"http://127.0.0.1:{port}"
        status, raw = request("POST", "/api/bootstrap",
                              body=json.dumps({"token": token}).encode(),
                              headers={"Origin": origin,
                                       "Content-Type": "application/json"})
        if status != 200:
            print(f"bootstrap failed: {status}", file=sys.stderr)
            return 1
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("POST", "/api/bootstrap", body=json.dumps({"token": token}).encode(),
                     headers={"Host": f"127.0.0.1:{port}", "Origin": origin,
                              "Content-Type": "application/json"})
        res = conn.getresponse(); res.read()
        cookie = res.getheader("Set-Cookie").split(";", 1)[0]
        conn.close()

        # The first /api/env starts a background scan and returns immediately
        # with {"scanning": true}; poll until the result lands.
        data = None
        for attempt in range(40):
            status, raw = request("GET", "/api/env", headers={"Cookie": cookie})
            if status != 200:
                print(f"/api/env failed: {status}", file=sys.stderr)
                return 1
            payload = json.loads(raw)
            if not payload.get("scanning"):
                data = payload
                print(f"environment scan completed after {attempt + 1} poll(s)")
                break
            time.sleep(1)
        if data is None:
            print("  [FAIL] the environment scan never completed", file=sys.stderr)
            return 1
        items = {i["id"]: i for i in data["items"]}

        failures = 0
        for tool in list(TEX_TOOLS) + list(OPTIONAL_TOOLS):
            item = items.get(tool)
            if item is None:
                print(f"  [FAIL] {tool} is not probed at all")
                failures += 1
                continue
            if item["present"]:
                print(f"  [FAIL] {tool} reported present although it is not on PATH")
                failures += 1
                continue
            if not item["install"].strip():
                print(f"  [FAIL] {tool} missing but no install command given")
                failures += 1
                continue
            if not item["url"].startswith("https://"):
                print(f"  [FAIL] {tool} missing but no official link given")
                failures += 1
            if tool in TEX_TOOLS and not item["required"]:
                print(f"  [FAIL] {tool} is needed to build but is marked optional")
                failures += 1
            if tool in OPTIONAL_TOOLS and item["required"]:
                print(f"  [FAIL] {tool} is optional but is marked required")
                failures += 1
            print(f"  [PASS] {tool}: missing, install command and link present")

        if data["can_build"]:
            print("  [FAIL] can_build is true with no TeX: the UI would let a build "
                  "start that cannot succeed")
            failures += 1
        else:
            print("  [PASS] can_build is false: the build button stays disabled")

        if not data["blocking"]:
            print("  [FAIL] nothing listed as blocking, so the explanation is empty")
            failures += 1
        else:
            print(f"  [PASS] blocking: {', '.join(data['blocking'])}")

        # The other panels must still answer: no TeX does not mean a dead page.
        status, _ = request("GET", "/api/git", headers={"Cookie": cookie})
        if status != 200:
            print(f"  [FAIL] /api/git returned {status} without TeX")
            failures += 1
        else:
            print("  [PASS] the Git panel still answers")

        status, _ = request("GET", "/api/sections", headers={"Cookie": cookie})
        if status != 200:
            print(f"  [FAIL] /api/sections returned {status} without TeX")
            failures += 1
        else:
            print("  [PASS] the prompt builder still lists sections")

        print(f"\n{'PASS' if failures == 0 else 'FAIL'}: "
              f"{failures} failure(s) in the no-TeX degradation path")
        return 0 if failures == 0 else 1
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(project, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
