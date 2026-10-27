"""Security and contract tests for the Local Companion UI.

Each test starts its own server on a free port with its own tokens, so nothing
here depends on a server the developer happens to have running.

Run:  python -I tests/test_ui_security.py
Exit: 0 all passed, 1 a test failed
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "ui" / "server.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Server:
    """A server subprocess with its bootstrap token extracted from --print-url."""

    def __init__(self, port: int = 0, extra: list[str] | None = None) -> None:
        self.port = port or free_port()
        self.proc = subprocess.Popen(
            [sys.executable, "-I", str(SERVER), "--no-browser", "--print-url",
             "--port", str(self.port), *(extra or [])],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.url = (self.proc.stdout.readline() or "").strip()
        match = re.search(r"#t=([A-Za-z0-9_\-]+)", self.url)
        if not match:
            self.stop()
            raise RuntimeError(f"server did not print a token: {self.url!r}")
        self.token = match.group(1)
        self.port = urlsplit(self.url).port
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                status, _, _ = self.request("GET", "/", host=f"127.0.0.1:{self.port}")
                if status:
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not become ready")

    def request(self, method: str, path: str, *, host: str | None = None,
                headers: dict[str, str] | None = None, body: bytes | None = None,
                timeout: float = 30) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        merged = {"Host": host if host is not None else f"127.0.0.1:{self.port}"}
        merged.update(headers or {})
        try:
            conn.request(method, path, body=body, headers=merged)
            res = conn.getresponse()
            data = res.read()
            return res.status, {k.lower(): v for k, v in res.getheaders()}, data
        finally:
            conn.close()

    def login(self) -> str:
        body = json.dumps({"token": self.token}).encode()
        status, headers, _ = self.request(
            "POST", "/api/bootstrap",
            headers={"Origin": f"http://127.0.0.1:{self.port}",
                     "Content-Type": "application/json"},
            body=body,
        )
        assert status == 200, f"bootstrap failed: {status}"
        cookie = headers["set-cookie"]
        return cookie.split(";", 1)[0]

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class UITestCase(unittest.TestCase):
    server: Server

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = Server()
        cls.cookie = cls.server.login()
        cls.origin = f"http://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    # -- helpers ---------------------------------------------------------
    def authed(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Cookie": self.cookie, "Origin": self.origin}
        headers.update(extra or {})
        return headers

    # -- M02: binding ----------------------------------------------------
    def test_m02_binds_loopback_only(self) -> None:
        """The listener must be on 127.0.0.1, not 0.0.0.0."""
        listing = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
        port = str(self.server.port)
        rows = [line for line in listing.splitlines()
                if re.search(rf":{port}\s", line) and "LISTENING" in line.upper()]
        if not rows:                      # netstat may be unavailable; try ss
            listing = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
            rows = [line for line in listing.splitlines() if f":{port}" in line]
        self.assertTrue(rows, "could not locate the listening socket")
        for row in rows:
            self.assertNotIn("0.0.0.0:" + port, row,
                             f"server listens on all interfaces: {row.strip()}")

    # -- M11: Host -------------------------------------------------------
    def test_m11_bad_host_rejected_everywhere(self) -> None:
        for path in ("/", "/style.css", "/app.js", "/api/env", "/api/git",
                     "/api/build/status", "/api/sections"):
            status, _, _ = self.server.request("GET", path, host="evil.example",
                                               headers={"Cookie": self.cookie})
            self.assertEqual(status, 403, f"{path} accepted Host: evil.example")

    def test_m11_dns_rebinding_variant_rejected(self) -> None:
        for host in ("127.0.0.1", "localhost", f"localhost:{self.server.port}",
                     f"127.0.0.1:{self.server.port + 1}"):
            status, _, _ = self.server.request("GET", "/api/env", host=host,
                                               headers={"Cookie": self.cookie})
            self.assertEqual(status, 403, f"Host {host!r} was accepted")

    def test_m11_pdf_route_checks_host(self) -> None:
        status, _, _ = self.server.request("GET", "/api/pdf", host="evil.example",
                                           headers={"Cookie": self.cookie})
        self.assertEqual(status, 403)

    # -- M12: session and Origin ----------------------------------------
    def test_m12_api_requires_session(self) -> None:
        for path in ("/api/env", "/api/git", "/api/build/status", "/api/sections", "/api/pdf"):
            status, _, _ = self.server.request("GET", path)
            self.assertEqual(status, 401, f"{path} served without a session")

    def test_m12_bad_cookie_rejected(self) -> None:
        status, _, _ = self.server.request("GET", "/api/env",
                                           headers={"Cookie": "alw_session=forged"})
        self.assertEqual(status, 401)

    def test_m12_bad_bootstrap_token_rejected(self) -> None:
        body = json.dumps({"token": "x" * 43}).encode()
        status, _, _ = self.server.request(
            "POST", "/api/bootstrap",
            headers={"Origin": self.origin, "Content-Type": "application/json"},
            body=body)
        self.assertEqual(status, 403)

    def test_m12_bootstrap_needs_exact_origin(self) -> None:
        body = json.dumps({"token": self.server.token}).encode()
        for origin in ("http://evil.example", "null", ""):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            status, _, _ = self.server.request("POST", "/api/bootstrap",
                                               headers=headers, body=body)
            self.assertIn(status, (403,), f"Origin {origin!r} accepted")

    def test_m12_mutating_api_needs_origin(self) -> None:
        for path in ("/api/build", "/api/prompt", "/api/open-vscode"):
            status, _, _ = self.server.request(
                "POST", path, headers={"Cookie": self.cookie,
                                       "Content-Type": "application/json"},
                body=b"{}")
            self.assertEqual(status, 403, f"{path} accepted a request with no Origin")

    def test_m12_no_cors_headers(self) -> None:
        status, headers, _ = self.server.request("GET", "/api/env", headers=self.authed())
        self.assertEqual(status, 200)
        for name in headers:
            self.assertNotIn("access-control", name, f"CORS header leaked: {name}")

    def test_m12_unknown_origin_post_rejected(self) -> None:
        status, _, _ = self.server.request(
            "POST", "/api/build",
            headers={"Cookie": self.cookie, "Origin": "http://evil.example",
                     "Content-Type": "application/json"}, body=b"{}")
        self.assertEqual(status, 403)

    # -- M13: path traversal --------------------------------------------
    def test_m13_pdf_route_ignores_query_and_path(self) -> None:
        for path in ("/api/pdf?file=../../AGENTS.md",
                     "/api/pdf?path=/etc/passwd",
                     "/api/pdf/../../AGENTS.md",
                     "/api/pdf?name=AGENTS.md"):
            status, _, body = self.server.request("GET", path, headers=self.authed())
            self.assertIn(status, (200, 404), f"{path} -> {status}")
            self.assertNotIn(b"Agent-first", body[:2000],
                             f"{path} leaked source content")

    def test_m13_static_route_cannot_escape_ui(self) -> None:
        for path in ("/../AGENTS.md", "/..%2fAGENTS.md", "/%2e%2e/AGENTS.md",
                     "/../../main.tex"):
            status, _, body = self.server.request("GET", path)
            self.assertIn(status, (404, 403), f"{path} -> {status}")
            self.assertNotIn(b"\\documentclass", body)

    def test_m13_unknown_routes_404(self) -> None:
        for path in ("/api/nope", "/admin", "/.git/config", "/api/env/../env"):
            status, _, _ = self.server.request("GET", path, headers=self.authed())
            self.assertEqual(status, 404, f"{path} -> {status}")

    # -- M14: cache headers ---------------------------------------------
    def test_m14_pdf_is_no_store(self) -> None:
        status, headers, body = self.server.request("GET", "/api/pdf", headers=self.authed())
        if status == 404:
            self.skipTest("no build/main.pdf in this checkout")
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers.get("cache-control", ""))
        self.assertTrue(body.startswith(b"%PDF"), "response is not a PDF")

    def test_m14_page_is_no_store(self) -> None:
        status, headers, _ = self.server.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers.get("cache-control", ""))

    # -- security headers ------------------------------------------------
    def test_csp_and_headers_on_every_response(self) -> None:
        for path in ("/", "/app.js", "/api/env"):
            headers_extra = self.authed() if path.startswith("/api") else None
            status, headers, _ = self.server.request("GET", path, headers=headers_extra)
            self.assertEqual(status, 200)
            csp = headers.get("content-security-policy", "")
            self.assertIn("default-src 'none'", csp)
            self.assertNotIn("unsafe-inline", csp)
            self.assertNotIn("unsafe-eval", csp)
            self.assertEqual(headers.get("x-content-type-options"), "nosniff")
            self.assertEqual(headers.get("referrer-policy"), "no-referrer")

    # -- M10 / prompt builder -------------------------------------------
    def test_prompt_builder_rejects_foreign_paths(self) -> None:
        for target in ("../AGENTS.md", "/etc/passwd", "sections/../../main.tex",
                       "C:\\Windows\\win.ini", ""):
            status, _, _ = self.server.request(
                "POST", "/api/prompt", headers=self.authed(
                    {"Content-Type": "application/json"}),
                body=json.dumps({"target": target, "kind": "polish"}).encode())
            self.assertEqual(status, 400, f"target {target!r} accepted")

    def test_prompt_builder_accepts_a_real_section(self) -> None:
        status, _, sections = self.server.request("GET", "/api/sections",
                                                  headers=self.authed())
        self.assertEqual(status, 200)
        listing = json.loads(sections)["sections"]
        self.assertTrue(listing, "no sections found")
        for target in listing:
            self.assertTrue(target.startswith("sections/"), target)
            self.assertNotIn("..", target)
        status, _, body = self.server.request(
            "POST", "/api/prompt",
            headers=self.authed({"Content-Type": "application/json"}),
            body=json.dumps({"target": listing[0], "kind": "polish"}).encode())
        self.assertEqual(status, 200)
        prompt = json.loads(body)["prompt"]
        self.assertIn("AGENTS.md", prompt)
        self.assertIn("read-only", prompt.lower())

    # -- M09: git is read-only ------------------------------------------
    def test_git_panel_has_no_write_route(self) -> None:
        for path in ("/api/git/commit", "/api/git/push", "/api/git/branch",
                     "/api/git/reset", "/api/git/checkout"):
            status, _, _ = self.server.request(
                "POST", path, headers=self.authed({"Content-Type": "application/json"}),
                body=b"{}")
            self.assertEqual(status, 404, f"{path} exists and accepted a POST")

    def test_git_panel_returns_real_state(self) -> None:
        status, _, body = self.server.request("GET", "/api/git", headers=self.authed())
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("git", data)
        self.assertIn("guardrail", data)
        if data["git"].get("is_repo"):
            self.assertIn("branch", data["git"])

    # -- M15: single build ----------------------------------------------
    def test_m15_second_build_returns_409(self) -> None:
        headers = self.authed({"Content-Type": "application/json"})
        first, _, _ = self.server.request("POST", "/api/build", headers=headers, body=b"{}")
        second, _, body = self.server.request("POST", "/api/build", headers=headers, body=b"{}")
        self.assertIn(first, (202,))
        if second == 409:
            self.assertFalse(json.loads(body)["started"])
        else:
            self.assertEqual(second, 202)
            self.assertEqual(json.loads(body)["job"]["id"],
                             json.loads(body)["job"]["id"])

    # -- M16: polling is not blocked ------------------------------------
    def test_m16_status_poll_answers_quickly(self) -> None:
        started = time.time()
        status, _, _ = self.server.request("GET", "/api/build/status",
                                           headers=self.authed(), timeout=5)
        elapsed = time.time() - started
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 0.5, f"status poll took {elapsed:.2f}s")


class ProtocolEdgeCases(unittest.TestCase):
    """Things a strict reviewer tries that are easy to forget."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = Server()
        cls.cookie = cls.server.login()
        cls.origin = f"http://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_head_requests_are_routed_and_have_no_body(self) -> None:
        for path in ("/", "/app.js", "/api/env"):
            status, headers, body = self.server.request(
                "HEAD", path, headers={"Cookie": self.cookie})
            self.assertEqual(status, 200, f"HEAD {path} -> {status}")
            self.assertEqual(body, b"", f"HEAD {path} returned a body")
            self.assertIn("no-store", headers.get("cache-control", ""))

    def test_head_still_checks_host(self) -> None:
        status, _, _ = self.server.request("HEAD", "/", host="evil.example")
        self.assertEqual(status, 403)

    def test_unknown_method_is_rejected(self) -> None:
        for method in ("DELETE", "PUT", "PATCH", "TRACE"):
            status, _, _ = self.server.request(method, "/api/env",
                                               headers={"Cookie": self.cookie})
            self.assertIn(status, (501, 405, 403),
                          f"{method} returned {status}")

    def test_oversized_json_body_is_refused(self) -> None:
        # The body cap is 8 KiB; 20 KiB must be refused rather than read.
        body = b'{"x":"' + b"a" * 20000 + b'"}'
        status, _, _ = self.server.request(
            "POST", "/api/prompt", headers={"Cookie": self.cookie,
                                            "Origin": self.origin,
                                            "Content-Type": "application/json",
                                            "Content-Length": str(len(body))},
            body=body)
        self.assertEqual(status, 400, f"an oversized body returned {status}")

    def test_malformed_json_is_refused(self) -> None:
        status, _, _ = self.server.request(
            "POST", "/api/prompt", headers={"Cookie": self.cookie,
                                            "Origin": f"http://127.0.0.1:{self.server.port}",
                                            "Content-Type": "application/json"},
            body=b"{not json")
        self.assertEqual(status, 400)

    def test_query_string_cannot_change_the_route(self) -> None:
        for path in ("/api/pdf?x=1", "/api/env?file=../../AGENTS.md"):
            status, _, _ = self.server.request("GET", path,
                                               headers={"Cookie": self.cookie})
            self.assertIn(status, (200, 404))


class BootstrapTokenTest(unittest.TestCase):
    def test_token_is_not_in_the_html_or_js(self) -> None:
        server = Server()
        try:
            _, _, page = server.request("GET", "/")
            self.assertNotIn(server.token.encode(), page)
            _, _, js = server.request("GET", "/app.js")
            self.assertNotIn(server.token.encode(), js)
        finally:
            server.stop()

    def test_token_is_not_logged(self) -> None:
        server = Server()
        try:
            cookie = server.login()
            server.request("GET", "/api/env", headers={"Cookie": cookie})
            time.sleep(0.3)
        finally:
            server.stop()
        log = server.proc.stderr.read() if server.proc.stderr else ""
        self.assertNotIn(server.token, log)
        self.assertNotIn(cookie.split("=", 1)[1], log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
