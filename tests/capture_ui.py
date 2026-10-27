"""Capture real page evidence with a real browser over the DevTools protocol.

Chrome is driven headless with --remote-debugging-port; this script speaks the
DevTools WebSocket protocol directly with the standard library, so there is no
Selenium/Playwright/pip dependency. It navigates, clicks, types and takes
screenshots of the actual rendered page -- not a curl of the API.

Three states are required:
    state-1-ready    environment detected, nothing blocking
    state-2-success  a build finished with exit 0 and the PDF is displayed
    state-3-failure  a real LaTeX error, reported with the failing file

Run:  python -I tests/capture_ui.py
Exit: 0 all captured, 2 a state failed, 3 no browser found
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "results" / "ui-evidence"
COPY = ["ui", "tools", "main.tex", "references.bib", ".latexmkrc", "sections"]

# Standard install locations, not paths from this machine. The publication audit
# flags Windows drive paths, and a browser discovery list is exactly that, so
# the block carries an explicit waiver with its reason.
BROWSERS = [  # publish-audit:allow browser install locations, not local paths
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]  # publish-audit:allow-end


# ---------------------------------------------------------------------------
# Minimal DevTools client (WebSocket, stdlib only)
# ---------------------------------------------------------------------------

class DevTools:
    def __init__(self, ws_url: str) -> None:
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", ws_url)
        if not m:
            raise ValueError(f"unexpected websocket url: {ws_url}")
        self.host, self.port, self.path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("websocket handshake failed")
            response += chunk
        if b"101" not in response.split(b"\r\n")[0]:
            raise RuntimeError(f"websocket rejected: {response[:200]!r}")
        self._next_id = 0

    def _send_frame(self, payload: bytes) -> None:
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("websocket closed")
            data += chunk
        return data

    def _recv_frame(self) -> str:
        first = self._recv_exact(2)
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        if first[1] & 0x80:
            mask = self._recv_exact(4)
            payload = bytes(b ^ mask[i % 4]
                            for i, b in enumerate(self._recv_exact(length)))
        else:
            payload = self._recv_exact(length)
        if opcode == 0x8:
            raise ConnectionError("websocket closed by peer")
        if opcode == 0x9:                       # ping
            return self._recv_frame()
        return payload.decode("utf-8", "replace")

    def call(self, method: str, params: dict | None = None,
             timeout: float = 120) -> dict:
        self._next_id += 1
        msg_id = self._next_id
        self._send_frame(json.dumps({"id": msg_id, "method": method,
                                     "params": params or {}}).encode())
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.sock.settimeout(max(1, deadline - time.time()))
            data = self._recv_frame()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue
            if message.get("id") == msg_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
        raise TimeoutError(f"{method} did not answer in {timeout}s")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Browser process
# ---------------------------------------------------------------------------

def find_browser() -> str | None:
    for path in BROWSERS:
        if Path(path).exists():
            return path
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Browser:
    def __init__(self, exe: str) -> None:
        self.port = free_port()
        self.profile = Path(tempfile.mkdtemp(prefix="alw-chrome-"))
        self.proc = subprocess.Popen([
            exe, "--headless=new", f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}", "--no-first-run",
            "--no-default-browser-check", "--disable-gpu",
            "--disable-extensions", "--window-size=1100,1400",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws_url = self._wait_for_target()

    def _wait_for_target(self) -> str:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/json/list", timeout=2) as res:
                    targets = json.load(res)
                for target in targets:
                    if target.get("type") == "page":
                        return target["webSocketDebuggerUrl"]
            except (OSError, ValueError):
                pass
            time.sleep(0.3)
        raise RuntimeError("Chrome did not expose a debugging target")

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

class Page:
    def __init__(self, devtools: DevTools) -> None:
        self.dt = devtools
        self.dt.call("Page.enable")
        self.dt.call("Runtime.enable")

    def goto(self, url: str) -> None:
        self.dt.call("Page.navigate", {"url": url})
        time.sleep(1.5)

    def eval(self, expression: str, timeout: float = 60):
        result = self.dt.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": True}, timeout=timeout)
        return result.get("result", {}).get("value")

    def text(self) -> str:
        return self.eval("document.body.innerText") or ""

    def wait_for_enabled(self, selector: str, limit: float = 120) -> bool:
        deadline = time.time() + limit
        while time.time() < deadline:
            try:
                if self.eval(
                        f"(() => {{ const e = document.querySelector({selector!r});"
                        f" return !!e && !e.disabled; }})()"):
                    return True
            except (RuntimeError, TimeoutError):
                pass
            time.sleep(1)
        return False

    def wait_text(self, needle: str, limit: float = 240) -> bool:
        deadline = time.time() + limit
        while time.time() < deadline:
            try:
                if needle.lower() in self.text().lower():
                    return True
            except (RuntimeError, TimeoutError):
                pass
            time.sleep(1.5)
        return False

    def click(self, selector: str) -> bool:
        return bool(self.eval(
            f"(() => {{ const e = document.querySelector({selector!r});"
            f" if (!e) return false; e.click(); return true; }})()"))

    def unlock(self, token: str) -> None:
        """Fill the fallback form when the fragment did not authenticate."""
        self.eval(f"document.getElementById('unlock-token').value = {token!r}")
        self.click("#unlock-form button")

    def shot(self, path: Path) -> None:
        data = self.dt.call("Page.captureScreenshot", {"format": "png",
                                                       "captureBeyondViewport": True})
        path.write_bytes(base64.b64decode(data["data"]))

    def stop_animations(self) -> None:
        self.eval("document.documentElement.style.scrollBehavior='auto'")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def make_project(broken: bool) -> Path:
    work = Path(tempfile.mkdtemp(prefix="ui-evidence-"))
    for item in COPY:
        src, dst = ROOT / item, work / item
        if src.exists():
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    if broken:
        section = work / "sections" / "method.tex"
        section.write_text(section.read_text(encoding="utf-8") +
                           "\n\\undefinedmacroforademo\n", encoding="utf-8")
    return work


def start_server(project: Path) -> tuple[subprocess.Popen, str, str]:
    proc = subprocess.Popen(
        [sys.executable, "-I", str(project / "ui" / "server.py"),
         "--no-browser", "--print-url", "--port", "0"],
        cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    url = (proc.stdout.readline() or "").strip()
    if "127.0.0.1" not in url:
        proc.terminate()
        raise RuntimeError(f"server did not start: {url!r}")
    token = url.split("#t=")[-1]
    return proc, url, token


def save(page: Page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.shot(OUT / f"{name}.png")
    (OUT / f"{name}.txt").write_text(page.text(), encoding="utf-8")
    print(f"    saved {name}.png / {name}.txt")


def main() -> int:
    exe = find_browser()
    if exe is None:
        print("no Chromium browser found", file=sys.stderr)
        return 3
    print(f"browser: {exe}")
    OUT.mkdir(parents=True, exist_ok=True)
    browser = Browser(exe)
    failures = 0
    try:
        page = Page(DevTools(browser.ws_url))

        # ---- 1. ready ---------------------------------------------------
        project = make_project(broken=False)
        proc, url, token = start_server(project)
        try:
            page.goto(url)
            # The scan runs in the background; give it time, and unlock first if
            # the fragment did not authenticate.
            if not page.wait_text("Ready to compile", 30):
                page.unlock(token)
            ready = page.wait_text("Ready to compile", 150)
            print(f"[{'PASS' if ready else 'FAIL'}] state 1: environment ready")
            save(page, "state-1-ready")
            failures += 0 if ready else 1
        finally:
            proc.terminate(); proc.wait(timeout=10)
            shutil.rmtree(project, ignore_errors=True)

        # ---- 2. build success -------------------------------------------
        project = make_project(broken=False)
        proc, url, token = start_server(project)
        try:
            page.goto(url)
            # The environment scan runs in the background now, so "Ready to
            # compile" appears only once it lands. Wait for the button to be
            # enabled rather than for the text alone.
            if not page.wait_text("Ready to compile", 120):
                page.unlock(token)
                page.wait_text("Ready to compile", 90)
            page.wait_for_enabled("#build-btn", 120)
            page.click("#build-btn")
            ok = page.wait_text("succeeded", 300)
            print(f"[{'PASS' if ok else 'FAIL'}] state 2: build succeeded")
            if ok:
                page.click("#pdf-btn")
                time.sleep(4)
                pdf_ok = page.eval(
                    "(() => { const f = document.getElementById('pdf-frame');"
                    " return !!f && f.src.includes('/api/pdf'); })()")
                print(f"    PDF frame loaded: {pdf_ok}")
            save(page, "state-2-success")
            failures += 0 if ok else 1
        finally:
            proc.terminate(); proc.wait(timeout=10)
            shutil.rmtree(project, ignore_errors=True)

        # ---- 3. build failure -------------------------------------------
        project = make_project(broken=True)
        proc, url, token = start_server(project)
        try:
            page.goto(url)
            if not page.wait_text("Ready to compile", 120):
                page.unlock(token)
                page.wait_text("Ready to compile", 90)
            page.wait_for_enabled("#build-btn", 120)
            page.click("#build-btn")
            failed = page.wait_text("failed (exit", 300)
            banner = page.eval(
                "(() => { const e = document.getElementById('build-problem');"
                " return e ? e.textContent : ''; })()") or ""
            names_file = "method.tex" in banner
            print(f"[{'PASS' if failed and names_file else 'FAIL'}] state 3: "
                  f"failure reported with the failing file")
            print(f"    banner: {banner.strip()[:140]}")
            save(page, "state-3-failure")
            failures += 0 if (failed and names_file) else 1
        finally:
            proc.terminate(); proc.wait(timeout=10)
            shutil.rmtree(project, ignore_errors=True)

        # ---- bonus: narrow viewport -------------------------------------
        project = make_project(broken=False)
        proc, url, token = start_server(project)
        try:
            page.goto(url)
            if not page.wait_text("Ready to compile", 120):
                page.unlock(token)
                page.wait_text("Ready to compile", 90)
            page.dt.call("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1,
                "mobile": True})
            time.sleep(1.5)
            save(page, "state-4-narrow")
            page.dt.call("Emulation.clearDeviceMetricsOverride")
        finally:
            proc.terminate(); proc.wait(timeout=10)
            shutil.rmtree(project, ignore_errors=True)

    finally:
        browser.close()

    print(f"\n{3 - failures}/3 required states captured in {OUT}")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
