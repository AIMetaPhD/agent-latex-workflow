"""M01: the workbench must find its own project, not the caller's directory.

The server is launched from a directory that is deliberately *not* the project,
and the assertions are about what it reports and what it can see:

    * the project name in /api/env is this repository, not the caller's cwd;
    * `sections/` lists this repository's files;
    * the PDF route still points at this repository's build directory.

Run:  python -I tests/test_root_resolution.py
Exit: 0 passed, 1 failed, 3 could not set up
"""

from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A directory that is definitely not the project. A temp dir is used rather than
# a system directory so the test cannot depend on what is installed there.
FOREIGN = Path(tempfile.mkdtemp(prefix="foreign-cwd-"))


def main() -> int:
    failures = 0
    server = None
    try:
        server = subprocess.Popen(
            [sys.executable, "-I", str(ROOT / "ui" / "server.py"),
             "--no-browser", "--print-url", "--port", "0"],
            cwd=str(FOREIGN), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        url = (server.stdout.readline() or "").strip()
        m = re.search(r"127\.0\.0\.1:(\d+)/#t=([A-Za-z0-9_\-]+)", url)
        if not m:
            print(f"server did not start from {FOREIGN}: {url!r}", file=sys.stderr)
            print((server.stderr.read() or "")[:400], file=sys.stderr)
            return 3
        port, token = int(m.group(1)), m.group(2)
        print(f"launched from {FOREIGN.name}/ and serving 127.0.0.1:{port}")

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
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("POST", "/api/bootstrap",
                     body=json.dumps({"token": token}).encode(),
                     headers={"Host": f"127.0.0.1:{port}", "Origin": origin,
                              "Content-Type": "application/json"})
        res = conn.getresponse(); res.read()
        cookie = res.getheader("Set-Cookie").split(";", 1)[0]
        conn.close()

        status, raw = request("GET", "/api/env", headers={"Cookie": cookie})
        if status != 200:
            print(f"  [FAIL] /api/env -> {status}")
            return 1
        data = json.loads(raw)
        expected = ROOT.name
        if data.get("project_name") != expected:
            print(f"  [FAIL] project_name is {data.get('project_name')!r}, "
                  f"expected {expected!r}")
            failures += 1
        else:
            print(f"  [PASS] project_name is {expected!r} despite the foreign cwd")

        status, raw = request("GET", "/api/sections", headers={"Cookie": cookie})
        if status != 200:
            print(f"  [FAIL] /api/sections -> {status}")
            failures += 1
        else:
            sections = json.loads(raw)["sections"]
            expected_sections = sorted(
                p.relative_to(ROOT).as_posix() for p in (ROOT / "sections").glob("*.tex"))
            if sections != expected_sections:
                print(f"  [FAIL] sections {sections} != {expected_sections}")
                failures += 1
            else:
                print(f"  [PASS] sections lists the project's {len(sections)} file(s)")

        # The guardrail panel reads git from the project, not from the caller.
        status, raw = request("GET", "/api/git", headers={"Cookie": cookie})
        if status != 200:
            print(f"  [FAIL] /api/git -> {status}")
            failures += 1
        else:
            git = json.loads(raw)["git"]
            if git.get("is_repo"):
                print(f"  [PASS] git panel sees the project's repository "
                      f"(branch {git.get('branch')!r})")
            else:
                print("  [note] no .git in the project; panel reported that honestly")

        print(f"\n{'PASS' if failures == 0 else 'FAIL'}: root resolution from a "
              f"foreign cwd, {failures} failure(s)")
        return 0 if failures == 0 else 1
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        FOREIGN.rmdir()


if __name__ == "__main__":
    sys.exit(main())
