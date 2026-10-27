"""Regression tests for the defects found by the independent audit.

Each test reproduces one finding from `tests/results/independent-audit.md` and
asserts it is fixed. They run against throwaway copies, so a deliberately
broken `build/main.pdf` never touches the real sample.

Defect map:
    D1  a non-ASCII bootstrap token used to kill the handler thread
    D2  a symlinked build/main.pdf used to raise before the escape check
    D3  a timed-out build could leave an orphaned grandchild running
    D4  an exception while finalising left the job "running" forever
    D5  server-side exceptions used to print full tracebacks to stderr
    D7  a large body on a bodyless POST used to abort the connection

Run:  python -I tests/test_ui_robustness.py
Exit: 0 all passed, 1 a failure
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ["ui", "tools", "main.tex", "references.bib", ".latexmkrc", "sections"]


def make_copy() -> Path:
    work = Path(tempfile.mkdtemp(prefix="ui-robust-"))
    for item in COPY:
        src, dst = ROOT / item, work / item
        if src.exists():
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return work


class Server:
    def __init__(self, project: Path, timeout: int = 300) -> None:
        self.project = project
        self.proc = subprocess.Popen(
            [sys.executable, "-I", str(project / "ui" / "server.py"),
             "--no-browser", "--print-url", "--port", "0",
             "--build-timeout", str(timeout)],
            cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        url = (self.proc.stdout.readline() or "").strip()
        m = re.search(r"127\.0\.0\.1:(\d+)/#t=([A-Za-z0-9_\-]+)", url)
        if not m:
            self.stop()
            raise RuntimeError(f"server did not start: {url!r}")
        self.port, self.token = int(m.group(1)), m.group(2)
        self.origin = f"http://127.0.0.1:{self.port}"
        self.cookie = self.login()

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None,
                timeout: float = 30) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        merged = {"Host": f"127.0.0.1:{self.port}"}
        merged.update(headers or {})
        try:
            conn.request(method, path, body=body, headers=merged)
            res = conn.getresponse()
            return res.status, {k.lower(): v for k, v in res.getheaders()}, res.read()
        finally:
            conn.close()

    def login(self) -> str:
        status, headers, _ = self.request(
            "POST", "/api/bootstrap",
            body=json.dumps({"token": self.token}).encode(),
            headers={"Origin": self.origin, "Content-Type": "application/json"})
        if status != 200:
            raise RuntimeError(f"bootstrap failed: {status}")
        return headers["set-cookie"].split(";", 1)[0]

    def authed(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Cookie": self.cookie, "Origin": self.origin}
        headers.update(extra or {})
        return headers

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def stderr_text(self) -> str:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            pass
        try:
            return self.proc.stderr.read() or ""
        except (OSError, ValueError):
            return ""


class D1NonAsciiToken(unittest.TestCase):
    """A hostile token must get 403, not drop the connection."""

    def test_d1_non_ascii_token_is_refused_cleanly(self) -> None:
        project = make_copy()
        server = Server(project)
        try:
            for token in ("tést", "🦊", "a" * 5000, "\x00\x01"):
                status, _, body = server.request(
                    "POST", "/api/bootstrap",
                    body=json.dumps({"token": token}).encode(),
                    headers={"Origin": server.origin,
                             "Content-Type": "application/json"})
                self.assertEqual(status, 403, f"token {token!r} -> {status}")
                self.assertIn(b"invalid bootstrap token", body)
            # The server must still work afterwards.
            status, _, _ = server.request("GET", "/api/env",
                                          headers={"Cookie": server.cookie})
            self.assertEqual(status, 200)
            log = server.stderr_text()
            self.assertNotIn("Traceback", log, "a traceback reached stderr")
        finally:
            server.stop()
            shutil.rmtree(project, ignore_errors=True)


class D2SymlinkPdf(unittest.TestCase):
    """A link at build/main.pdf must be refused, never followed."""

    def _make_link(self, project: Path) -> str:
        """Create a link at build/main.pdf. Returns how, or "" on failure.

        A true symlink needs admin rights or Developer Mode on Windows. A
        directory junction does not, and it exercises the same escape path:
        `main.pdf` resolving to a directory outside `build/`.
        """
        build = project / "build"
        build.mkdir(exist_ok=True)
        link = build / "main.pdf"
        if link.exists() or link.is_symlink():
            link.unlink()
        try:
            os.symlink("../../AGENTS.md", link)
            return "symlink"
        except (OSError, NotImplementedError):
            pass
        if os.name == "nt":
            target = project / "sections"
            proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                  capture_output=True, text=True)
            if proc.returncode == 0 and link.exists():
                return "junction"
        return ""

    def test_d2_symlinked_pdf_is_refused(self) -> None:
        project = make_copy()
        (project / "AGENTS.md").write_text("secret sentinel SECRET_AGENTS\n",
                                           encoding="utf-8")
        kind = self._make_link(project)
        if not kind:
            shutil.rmtree(project, ignore_errors=True)
            self.skipTest("this account can create neither a symlink nor a junction")
        print(f"  link kind: {kind}")
        server = Server(project)
        try:
            status, _, body = server.request("GET", "/api/pdf",
                                             headers=server.authed())
            self.assertIn(status, (403, 404), f"{kind}ed pdf -> {status}")
            self.assertNotIn(b"SECRET_AGENTS", body, "the link target was served")
            self.assertNotIn(b"\\section", body, "content from sections/ leaked")
            log = server.stderr_text()
            self.assertNotIn("Traceback", log)
        finally:
            server.stop()
            shutil.rmtree(project, ignore_errors=True)


class D3TreeKill(unittest.TestCase):
    """A timed-out build must leave no descendant behind."""

    def test_d3_no_orphan_survives_a_timeout(self) -> None:
        project = make_copy()
        engine = project / "alw-hang.sh"
        engine.write_text("#!/bin/sh\nsh -c 'sleep 120'\necho NEVER\n", encoding="utf-8")
        (project / ".latexmkrc").write_text(
            "$pdf_mode = 1;\n$out_dir = 'build';\n$aux_dir = 'build';\n"
            "$pdflatex = 'sh alw-hang.sh %O %S';\n$bibtex_use = 0;\n",
            encoding="utf-8")
        server = Server(project, timeout=4)
        try:
            status, _, _ = server.request("POST", "/api/build", body=b"{}",
                                          headers=server.authed(
                                              {"Content-Type": "application/json"}))
            self.assertEqual(status, 202)
            deadline = time.time() + 90
            job = None
            while time.time() < deadline:
                _, _, body = server.request("GET", "/api/build/status",
                                            headers=server.authed())
                job = json.loads(body)["job"]
                if job and job["state"] == "finished":
                    break
                time.sleep(0.5)
            self.assertIsNotNone(job, "the build never finished")
            self.assertTrue(job["timed_out"])
            time.sleep(3)
            listing = (subprocess.run(["tasklist"], capture_output=True, text=True).stdout
                       if os.name == "nt" else
                       subprocess.run(["ps", "-eo", "args"], capture_output=True,
                                      text=True).stdout).lower()
            self.assertNotIn("alw-hang.sh", listing,
                             "a descendant of the timed-out build is still running")
        finally:
            server.stop()
            shutil.rmtree(project, ignore_errors=True)


class D4NoPermanentLockout(unittest.TestCase):
    """A finished build must never leave the job stuck in `running`."""

    def test_d4_job_always_reaches_finished(self) -> None:
        project = make_copy()
        server = Server(project, timeout=120)
        try:
            status, _, _ = server.request("POST", "/api/build", body=b"{}",
                                          headers=server.authed(
                                              {"Content-Type": "application/json"}))
            self.assertEqual(status, 202)
            deadline = time.time() + 240
            while time.time() < deadline:
                _, _, body = server.request("GET", "/api/build/status",
                                            headers=server.authed())
                job = json.loads(body)["job"]
                if job and job["state"] == "finished":
                    break
                time.sleep(1)
            self.assertEqual(job["state"], "finished", "the job never finished")
            # And a second build must be accepted again.
            status, _, _ = server.request("POST", "/api/build", body=b"{}",
                                          headers=server.authed(
                                              {"Content-Type": "application/json"}))
            self.assertEqual(status, 202, "the build lock did not release")
        finally:
            server.stop()
            shutil.rmtree(project, ignore_errors=True)


class D5NoTracebacks(unittest.TestCase):
    """Nothing a client sends may put a traceback on stderr."""

    def test_d5_fuzzing_produces_no_traceback(self) -> None:
        project = make_copy()
        server = Server(project)
        payloads = [
            b'{"token": "t\xc3\xa9st"}',
            b'{"token": [1,2,3]}',
            b'{"token": null}',
            b"not json at all",
            b'{"target": {"a": 1}, "kind": []}',
            b"[" * 500,
        ]
        try:
            for path in ("/api/bootstrap", "/api/prompt"):
                for payload in payloads:
                    try:
                        server.request("POST", path, body=payload,
                                       headers=server.authed(
                                           {"Content-Type": "application/json"}),
                                       timeout=10)
                    except (OSError, http.client.HTTPException):
                        pass            # a dropped connection is itself a finding below
            # Raw socket garbage.
            for junk in (b"GET / HTTP/9.9\r\n\r\n", b"POST /api/env\r\n\r\n",
                         b"\x00\x01\x02\r\n\r\n"):
                try:
                    with socket.create_connection(("127.0.0.1", server.port), timeout=5) as s:
                        s.sendall(junk)
                        s.recv(1024)
                except OSError:
                    pass
            log = server.stderr_text()
            self.assertNotIn("Traceback", log,
                             f"a traceback reached stderr:\n{log[-1500:]}")
        finally:
            server.stop()
            shutil.rmtree(project, ignore_errors=True)


class D7LargeBody(unittest.TestCase):
    """A body on a bodyless POST must not abort the connection."""

    def test_d7_large_body_is_handled(self) -> None:
        project = make_copy()
        server = Server(project)
        try:
            big = b'{"x":"' + b"a" * (1024 * 1024) + b'"}'
            status, _, body = server.request(
                "POST", "/api/build", body=big,
                headers=server.authed({"Content-Type": "application/json"}),
                timeout=30)
            # Either it is accepted and drained, or it is refused cleanly --
            # but the client must get an HTTP status either way.
            self.assertIn(status, (202, 400, 409, 413), f"status {status}")
            status, _, _ = server.request("GET", "/api/build/status",
                                          headers=server.authed())
            self.assertEqual(status, 200, "the server stopped answering")
        finally:
            server.stop()
            shutil.rmtree(project, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
