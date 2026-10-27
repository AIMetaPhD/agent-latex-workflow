"""Build behaviour tests for the Local Companion UI (M05, M07, M17, M18).

Each test runs in a throwaway copy of the repository, so a deliberately broken
paper never touches the real sample. The copy contains the UI, the tools and the
minimal LaTeX project.

Run:  python -I tests/test_ui_build.py
Exit: 0 all passed, 1 a test failed
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
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ["ui", "tools", "main.tex", "references.bib", ".latexmkrc", "sections"]

CRLF = chr(13) + chr(10)
NL = chr(10)


def make_copy() -> Path:
    work = Path(tempfile.mkdtemp(prefix="ui-build-"))
    for item in COPY:
        src, dst = ROOT / item, work / item
        if not src.exists():
            continue
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return work


class Harness:
    """Drive the server's HTTP API the way the browser does."""

    def __init__(self, project: Path, timeout: int = 300,
                 env: dict[str, str] | None = None) -> None:
        self.project = project
        self.proc = subprocess.Popen(
            [sys.executable, "-I", str(project / "ui" / "server.py"),
             "--no-browser", "--print-url", "--port", "0",
             "--build-timeout", str(timeout)],
            cwd=str(project), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        url = (self.proc.stdout.readline() or "").strip()
        m = re.search(r"127\.0\.0\.1:(\d+)/#t=([A-Za-z0-9_\-]+)", url)
        if not m:
            self.stop()
            raise RuntimeError(f"server did not start: {url!r}")
        self.port = int(m.group(1))
        self.token = m.group(2)
        self.origin = f"http://127.0.0.1:{self.port}"
        self.cookie = self.login()

    def _req(self, method: str, path: str, body: bytes | None = None,
             extra: dict[str, str] | None = None) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        headers.update(extra or {})
        try:
            conn.request(method, path, body=body, headers=headers)
            res = conn.getresponse()
            return res.status, res.read()
        finally:
            conn.close()

    def login(self) -> str:
        body = json.dumps({"token": self.token}).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("POST", "/api/bootstrap", body=body,
                         headers={"Host": f"127.0.0.1:{self.port}",
                                  "Origin": self.origin,
                                  "Content-Type": "application/json"})
            res = conn.getresponse()
            res.read()
            return res.getheader("Set-Cookie").split(";", 1)[0]
        finally:
            conn.close()

    def get(self, path: str) -> tuple[int, bytes]:
        return self._req("GET", path, extra={"Cookie": self.cookie})

    def post(self, path: str, payload: dict | None = None) -> tuple[int, bytes]:
        return self._req("POST", path, body=json.dumps(payload or {}).encode(),
                         extra={"Cookie": self.cookie, "Origin": self.origin,
                                "Content-Type": "application/json"})

    def wait_for_build(self, limit: float = 400) -> dict:
        deadline = time.time() + limit
        while time.time() < deadline:
            status, body = self.get("/api/build/status")
            if status == 200:
                job = json.loads(body).get("job")
                if job and job["state"] == "finished":
                    return job
            time.sleep(0.4)
        raise AssertionError("build did not finish in time")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = make_copy()
        self.server = None

    def tearDown(self) -> None:
        if self.server:
            self.server.stop()
        shutil.rmtree(self.project, ignore_errors=True)

    # -- M05 -------------------------------------------------------------
    def test_m05_successful_build_produces_a_pdf(self) -> None:
        self.server = Harness(self.project)
        status, _ = self.server.post("/api/build")
        self.assertEqual(status, 202)
        job = self.server.wait_for_build()
        self.assertEqual(job["exit_code"], 0, job["log"][-1500:])
        self.assertIsNone(job["problem"], "a clean build reported a problem")
        pdf = self.project / "build" / "main.pdf"
        self.assertTrue(pdf.exists(), "no build/main.pdf")
        self.assertGreater(pdf.stat().st_size, 10_000)
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))

        status, body = self.server.get("/api/pdf")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"%PDF"))

    # -- M07 -------------------------------------------------------------
    def test_m07_syntax_error_fails_with_a_useful_log(self) -> None:
        section = self.project / "sections" / "method.tex"
        section.write_text(section.read_text(encoding="utf-8") +
                           chr(10) + "\\undefinedmacroforatest" + chr(10), encoding="utf-8")
        self.server = Harness(self.project)
        self.server.post("/api/build")
        job = self.server.wait_for_build()
        self.assertNotEqual(job["exit_code"], 0, "a broken document compiled")
        self.assertIsNotNone(job["problem"], "no problem was extracted from the log")
        self.assertEqual(job["problem"]["kind"], "error",
                         "a fatal error must not be reported as a mere warning")
        self.assertIn("method.tex", job["problem"]["line"],
                      "the headline does not say which file failed")
        self.assertIn("undefined control sequence", job["problem"]["line"].lower())
        # The macro name is on the preceding log line, not in the headline;
        # the full log must still contain it so the user can find it.
        self.assertIn("undefinedmacroforatest", job["log"])

    def test_m07_undefined_citation_is_reported(self) -> None:
        section = self.project / "sections" / "results.tex"
        section.write_text(section.read_text(encoding="utf-8") +
                           chr(10) + "See \\cite{nonexistentkey2024}." + chr(10),
                           encoding="utf-8")
        self.server = Harness(self.project)
        self.server.post("/api/build")
        job = self.server.wait_for_build()
        self.assertIn("nonexistentkey2024", job["log"])
        self.assertIsNotNone(job["problem"],
                             "an unresolved citation produced no problem banner")
        self.assertEqual(job["problem"]["kind"], "undefined-reference")
        self.assertIn("nonexistentkey2024", job["problem"]["line"])

    # -- M17 -------------------------------------------------------------
    def _hanging_engine(self) -> None:
        """Point .latexmkrc at a compiler that never returns.

        latexmk resolves its engines to absolute paths inside the TeX
        distribution, so shadowing PATH does not work. The build command is
        defined by .latexmkrc, so that is the honest place to make it hang.
        """
        # A short ASCII path without spaces: latexmk passes the command through a
        # shell, and a temp path containing a space or a non-ASCII character
        # breaks the invocation for reasons unrelated to what is being tested.
        # A POSIX shell script on every platform: latexmk runs its engine
        # command through a shell, and on Windows a .bat launched that way
        # loses the child's stdout, which is part of what this test asserts.
        # `sh` is started by latexmk through cmd.exe, which has no MSYS path
        # mapping, so the script is referenced by a bare relative name from the
        # project root (latexmk's cwd) rather than by an absolute path.
        engine = self.project / "alw-hang.sh"
        engine.write_text(
            "#!/bin/sh" + NL + "echo fake-engine-started" + NL +
            "sleep 120" + NL, encoding="utf-8")
        command = "sh alw-hang.sh"
        (self.project / ".latexmkrc").write_text(
            "$pdf_mode = 1;" + NL +
            "$out_dir = 'build';" + NL +
            "$aux_dir = 'build';" + NL +
            f"$pdflatex = '{command} %O %S';" + NL +
            "$bibtex_use = 0;" + NL, encoding="utf-8")

    def test_m17_timeout_kills_the_process_tree(self) -> None:
        """A build that cannot finish is stopped and leaves nothing behind."""
        self._hanging_engine()
        self.server = Harness(self.project, timeout=8)
        started = time.time()
        status, _ = self.server.post("/api/build")
        self.assertEqual(status, 202)
        job = self.server.wait_for_build(limit=120)
        elapsed = time.time() - started

        self.assertTrue(job["timed_out"], "the build was not stopped")
        self.assertIn("fake-engine-started", job["log"])
        self.assertLess(elapsed, 60, f"timeout fired late ({elapsed:.0f}s)")

        time.sleep(2)
        listing = (subprocess.run(["tasklist"], capture_output=True, text=True).stdout
                   if os.name == "nt" else
                   subprocess.run(["ps", "-eo", "args"], capture_output=True,
                                  text=True).stdout).lower()
        needle = "hang.bat" if os.name == "nt" else "hang.sh"
        self.assertNotIn(needle, listing, "the engine survived the timeout kill")

        status, _ = self.server.post("/api/build")
        self.assertEqual(status, 202, "the build lock was not released after a timeout")

    # -- M18 -------------------------------------------------------------
    def test_m18_log_is_bounded_and_keeps_head_and_tail(self) -> None:
        """A chatty build must not grow the log without bound."""
        noisy = self.project / "alw-chatty.sh"
        noisy.write_text("#!/bin/sh" + NL +
                         "i=1" + NL +
                         "while [ $i -le 20000 ]; do echo \"line $i " + "a" * 50 +
                         "\"; i=$((i+1)); done" + NL +
                         "echo LAST-LINE-MARKER" + NL, encoding="utf-8")
        command = "sh alw-chatty.sh"
        (self.project / ".latexmkrc").write_text(
            "$pdf_mode = 1;" + NL +
            "$out_dir = 'build';" + NL +
            "$aux_dir = 'build';" + NL +
            f"$pdflatex = '{command} %O %S';" + NL +
            "$bibtex_use = 0;" + NL, encoding="utf-8")

        self.server = Harness(self.project)
        self.server.post("/api/build")
        job = self.server.wait_for_build(limit=180)

        size = len(job["log"].encode("utf-8"))
        self.assertLess(size, 300 * 1024,
                        f"log is {size} bytes; the 256 KiB cap did not hold")
        self.assertIn("line 1 ", job["log"], "the head of the log was dropped")
        self.assertIn("LAST-LINE-MARKER", job["log"], "the tail of the log was dropped")
        self.assertIn("omitted", job["log"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
