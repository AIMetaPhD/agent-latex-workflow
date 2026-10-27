#!/usr/bin/env python3
"""Local Companion UI for an agent-first paper repository.

A guided control panel for the repository this file lives in. It is not an
editor, not a Git client, and it never calls a model API. Read docs/UI-ADR.md
for the architecture, the threat model and what is deliberately absent.

Standard library only: Python 3.10+.

    python ui/server.py                 # opens a browser at 127.0.0.1:8765
    python ui/server.py --no-browser    # do not open a browser
    python ui/server.py --print-url     # print the URL and nothing else
    python ui/server.py --port 9000     # prefer a specific port
    python ui/server.py --build-timeout 30

Security properties (each is asserted by tests/test_ui_security.py):

  * binds 127.0.0.1 only;
  * every request must carry a Host that matches 127.0.0.1:<actual port>;
  * every API needs a session cookie; mutating APIs also need an exact Origin;
  * the session token travels in the URL fragment and is never logged;
  * no CORS headers are emitted;
  * subprocesses use a fixed argv, shell=False, a fixed cwd and a timeout;
  * the PDF route serves one fixed file and refuses a path that escapes build/;
  * the build log is bounded and rendered with textContent on the client.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"
BUILD_DIR = ROOT / "build"
PDF_PATH = BUILD_DIR / "main.pdf"
LOG_PATH = BUILD_DIR / "main.log"

SESSION_COOKIE = "alw_session"


def _digest_equal(candidate: str, expected: str) -> bool:
    """Constant-time compare that cannot raise on hostile input.

    `secrets.compare_digest(str, str)` raises TypeError when either side has a
    non-ASCII character. The candidate comes straight from a request body, so a
    `{"token": "tést"}` would kill the handler thread and drop the connection
    with no HTTP status. Comparing bytes removes that failure mode; the length
    check first is cheap and leaks nothing useful (both strings are opaque
    tokens, not secrets an attacker can grind against).
    """
    a = candidate.encode("utf-8", "surrogatepass")
    b = expected.encode("utf-8", "surrogatepass")
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)
MAX_LOG_BYTES = 256 * 1024          # head + tail retention, see _BoundedLog
DEFAULT_BUILD_TIMEOUT = 300
POLL_HINT_MS = 500

CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


# ---------------------------------------------------------------------------
# Environment probe
# ---------------------------------------------------------------------------

DEPENDENCIES = [
    # (id, label, kind, probe argv, required, purpose, install, url)
    ("git", "Git", "binary", ["git", "--version"], True,
     "Exact change history; every review and every agent edit depends on it.",
     "winget install --id Git.Git -e",
     "https://git-scm.com/downloads"),
    ("python", "Python 3.10+", "python", None, True,
     "Runs this workbench and the repository tools.",
     "winget install --id Python.Python.3.12 -e",
     "https://www.python.org/downloads/"),
    ("latexmk", "latexmk", "binary", ["latexmk", "-v"], True,
     "The build driver. It reads .latexmkrc, so it is the only build command.",
     "Install TeX Live (full), which includes latexmk.",
     "https://www.tug.org/texlive/"),
    ("pdflatex", "pdfLaTeX engine", "binary", ["pdflatex", "--version"], True,
     "Typesets the document. Without it no PDF is produced.",
     "Install TeX Live (full).",
     "https://www.tug.org/texlive/"),
    ("bibtex", "BibTeX", "binary", ["bibtex", "-version"], True,
     "Resolves references.bib. Without it citations render as [?].",
     "Install TeX Live (full).",
     "https://www.tug.org/texlive/"),
    ("perl", "Perl", "binary", ["perl", "-v"], True,
     "latexmk is a Perl program. On Windows, TeX Live installs its own Perl.",
     "TeX Live ships one; otherwise install Strawberry Perl.",
     "https://strawberryperl.com/"),
    ("code", "VS Code", "binary", ["code", "--version"], False,
     "Optional editor. The UI opens the project in it when available.",
     "winget install --id Microsoft.VisualStudioCode -e",
     "https://code.visualstudio.com/"),
    ("latexdiff", "latexdiff", "binary", ["latexdiff", "--version"], False,
     "Optional: typeset diff for a co-author who does not read LaTeX.",
     "tlmgr install latexdiff",
     "https://ctan.org/pkg/latexdiff"),
]


def _probe(argv: list[str], timeout: float = 20.0) -> tuple[bool, str]:
    """Is this tool usable? Return (present, one line of detail).

    `shutil.which` finds `code` on Windows only as `code.cmd`, which
    `subprocess` cannot execute without a shell -- and the UI never uses a
    shell. So a launch failure means "not usable from here", not an exception
    to show the user.
    """
    exe = shutil.which(argv[0])
    if exe is None:
        return False, ""
    try:
        proc = subprocess.run([exe, *argv[1:]], capture_output=True, text=True,
                              timeout=timeout, shell=False, cwd=str(ROOT))
    except (OSError, subprocess.SubprocessError):
        # Found on PATH but not launchable as-is (a .cmd shim is the usual
        # case). The tool exists, so report it as found but unusable.
        return False, f"found at {exe}, but it cannot be started without a shell"
    text = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    first = next((line for line in text if line.strip()), "")
    return proc.returncode == 0 or bool(text), first[:160]


_PROBE_CACHE: dict | None = None
_PROBE_THREAD: threading.Thread | None = None
_PROBE_LOCK = threading.Lock()


def _scan_once() -> dict:
    """Run every probe. Takes a few seconds: each entry starts a process."""
    items = []
    for dep_id, label, kind, argv, required, purpose, install, url in DEPENDENCIES:
        if kind == "python":
            version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            ok = sys.version_info >= (3, 10)
            detail = f"Python {version}"
        else:
            ok, detail = _probe(argv or [])
        items.append({
            "id": dep_id,
            "label": label,
            "present": bool(ok),
            "required": required,
            "detail": detail,
            "purpose": purpose,
            "install": install,
            "url": url,
        })
    blocking = [i["label"] for i in items if i["required"] and not i["present"]]
    return {
        "items": items,
        "blocking": blocking,
        "can_build": not blocking,
        "project_name": ROOT.name,
        "platform": sys.platform,
    }


def environment_report() -> dict:
    """Return the cached scan, starting one in the background if needed.

    The first call does not block on eight subprocesses: a cold scan takes up to
    ~20 s on Windows, and a page that waits that long looks broken. The page
    polls `/api/env`, so it picks the result up as soon as the scan lands.
    """
    global _PROBE_CACHE, _PROBE_THREAD
    with _PROBE_LOCK:
        cached = _PROBE_CACHE
        if cached is None and (_PROBE_THREAD is None or not _PROBE_THREAD.is_alive()):
            _PROBE_THREAD = threading.Thread(target=_scan_into_cache, daemon=True)
            _PROBE_THREAD.start()
    if cached is None:
        return {"scanning": True, "items": [], "blocking": [], "can_build": None,
                "project_name": ROOT.name, "platform": sys.platform}
    return dict(cached)


def _scan_into_cache() -> None:
    global _PROBE_CACHE
    result = _scan_once()
    with _PROBE_LOCK:
        _PROBE_CACHE = result


# ---------------------------------------------------------------------------
# Bounded log: keep the head (first error) and the tail (the summary)
# ---------------------------------------------------------------------------

class _BoundedLog:
    """Keeps the first and the last half of a size budget.

    Keeping only the tail would drop the first LaTeX error, which is the one
    that explains the rest. Keeping only the head would drop the summary.
    """

    def __init__(self, limit: int = MAX_LOG_BYTES) -> None:
        self.limit = limit
        self.head_budget = limit // 2
        self.tail_budget = limit - self.head_budget
        self._head: list[str] = []
        self._head_size = 0
        self._tail: deque[str] = deque()
        self._tail_size = 0
        self.dropped = 0
        self._lock = threading.Lock()

    def write(self, line: str) -> None:
        size = len(line)
        with self._lock:
            if self._head_size + size <= self.head_budget:
                self._head.append(line)
                self._head_size += size
                return
            self._tail.append(line)
            self._tail_size += size
            while self._tail_size > self.tail_budget and len(self._tail) > 1:
                self._tail_size -= len(self._tail.popleft())
                self.dropped += 1

    def text(self) -> str:
        with self._lock:
            body = "".join(self._head) + "".join(self._tail)
        if self.dropped:
            body += f"\n[... {self.dropped} line(s) omitted to bound the log at " \
                    f"{self.limit} bytes ...]\n"
        return body


# A fatal error takes precedence over a warning. latexmk runs several passes,
# and an early pass legitimately reports "citation undefined" before bibtex has
# produced the .bbl. Leading with that would hide the error that actually
# stopped the build.
FATAL_RE = re.compile(
    r"^(?:! |! LaTeX Error:|! Package .* Error:|.*:\d+: )"
    r"|^Latexmk: .*(?:error|failed)",
    re.IGNORECASE,
)
UNDEFINED_RE = re.compile(
    r"(?:Citation|Reference) `[^']*' .*undefined|There were undefined references")


# latexmk prints this only after its final pass, and only when something is
# still unresolved. An earlier pass that says "Citation undefined" before
# bibtex ran does NOT produce it, which is what makes it the honest signal.
UNRESOLVED_SUMMARY_RE = re.compile(r"Latex failed to resolve \d+ (?:citation|reference)")


def first_problem(log_text: str, exit_code: int | None) -> dict | None:
    """The first fatal error, else a reference that never resolved.

    Two different sources are used on purpose:

      * a fatal error is read from the LaTeX log (``! ...`` / ``file:line:``);
      * an unresolved citation or reference is read from latexmk's own final
        summary, because the LaTeX log contains the same warning on every early
        pass -- including builds that go on to succeed. Using the log alone
        would either flag every clean build or hide every real one.
    """
    for line in log_text.splitlines():
        stripped = line.strip()
        if stripped and FATAL_RE.match(stripped):
            return {"kind": "error", "line": stripped[:300]}

    lines = log_text.splitlines()
    for index, line in enumerate(lines):
        if UNRESOLVED_SUMMARY_RE.search(line):
            # The summary header is followed by the offending citations.
            detail = line.strip()
            for follow in lines[index + 1:index + 4]:
                if follow.strip().startswith(("Citation", "Reference")):
                    detail = follow.strip()
                    break
            return {"kind": "undefined-reference", "line": detail[:300]}
    return None


# ---------------------------------------------------------------------------
# Build job
# ---------------------------------------------------------------------------

class BuildManager:
    """Runs at most one `latexmk` at a time, in the background."""

    def __init__(self, timeout: int) -> None:
        self.timeout = timeout
        self._lock = threading.Lock()
        self._job: dict | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._counter = 0

    def current(self) -> dict | None:
        with self._lock:
            return dict(self._job) if self._job else None

    # A job that has been "running" for longer than the timeout plus this much
    # slack is treated as dead. Without it, any unforeseen wedge leaves the
    # Compile button disabled for the rest of the server's life.
    STALE_SLACK_SECONDS = 120

    def start(self) -> tuple[dict, bool]:
        """Return (job, started). If a build is running, started is False."""
        with self._lock:
            if self._job and self._job["state"] == "running":
                age = time.time() - self._job["started_at"]
                if age <= self.timeout + self.STALE_SLACK_SECONDS:
                    return dict(self._job), False
                # Stale: mark it finished so this request can start a new one.
                self._job.update({
                    "state": "finished",
                    "exit_code": None,
                    "finished_at": time.time(),
                    "duration_s": round(age, 1),
                    "timed_out": True,
                    "problem": {"kind": "error",
                                "line": "the previous build stopped responding and was "
                                        "marked stale; the next build may run"},
                })
            self._counter += 1
            job = {
                "id": f"b{self._counter}-{int(time.time())}",
                "state": "running",
                "exit_code": None,
                "started_at": time.time(),
                "finished_at": None,
                "duration_s": None,
                "log": "",
                "problem": None,
                "timed_out": False,
            }
            self._job = job
        thread = threading.Thread(target=self._run, args=(job["id"],), daemon=True)
        thread.start()
        return dict(job), True

    def _run(self, job_id: str) -> None:
        log = _BoundedLog()
        started = time.time()
        argv = ["latexmk"]           # .latexmkrc supplies every flag
        timed_out = False
        code: int | None = None
        try:
            self._proc = subprocess.Popen(
                argv, cwd=str(ROOT), shell=False, text=True, encoding="utf-8",
                errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
            )
            assert self._proc.stdout is not None
            reader = threading.Thread(
                target=self._drain, args=(self._proc.stdout, log), daemon=True)
            reader.start()
            try:
                code = self._proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill_tree(self._proc)
                code = -1
            reader.join(timeout=5)
        except FileNotFoundError:
            log.write("latexmk: command not found. Install TeX Live (see Environment).\n")
            code = 127
        except OSError as exc:
            log.write(f"could not start latexmk: {exc}\n")
            code = 126
        finally:
            self._proc = None

        finished = time.time()
        text = log.text()

        # Finalising must not be able to fail. If it did, the job would stay
        # `running` for the life of the process and every later build would be
        # refused with 409 -- a permanent lockout with no way out from the UI.
        pdf_mtime: float | None = None
        try:
            if PDF_PATH.exists() and not PDF_PATH.is_symlink():
                pdf_mtime = PDF_PATH.stat().st_mtime
        except OSError:
            pdf_mtime = None

        try:
            problem = first_problem(text, code)
        except Exception:                                   # noqa: BLE001
            problem = None

        with self._lock:
            if self._job and self._job["id"] == job_id:
                self._job.update({
                    "state": "finished",
                    "exit_code": code,
                    "finished_at": finished,
                    "duration_s": round(finished - started, 1),
                    "log": text,
                    "problem": problem,
                    "timed_out": timed_out,
                    "pdf_mtime": pdf_mtime,
                })

    @staticmethod
    def _drain(stream, log: _BoundedLog) -> None:
        try:
            for line in stream:
                log.write(line)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> bool:
        """Kill the whole tree and verify it is gone. Returns True when clean.

        `taskkill /T` walks the tree at the moment it runs. A grandchild that
        the shell spawns a fraction of a second later survives it -- an orphan
        with a dead parent that no later call will ever reach. So the kill is
        repeated a few times, and each round asks the OS whether anything from
        the tree is still running.
        """
        if proc.poll() is not None:
            return True
        for _ in range(3):
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               shell=False, capture_output=True)
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        proc.kill()
                    except OSError:
                        pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            if not BuildManager._tree_alive(proc.pid):
                return True
            time.sleep(0.4)
        return not BuildManager._tree_alive(proc.pid)

    @staticmethod
    def _tree_alive(root_pid: int) -> bool:
        """True if any descendant of `root_pid` is still running.

        `taskkill /T` can miss a grandchild spawned after it walked the tree,
        so the parent link is walked explicitly. On Windows the query lists
        every process with its parent; on POSIX it uses `ps` and `ppid`.
        """
        if os.name == "nt":
            try:
                out = subprocess.run(["wmic", "process", "get",
                                      "ProcessId,ParentProcessId", "/format:csv"],
                                     capture_output=True, text=True, timeout=15,
                                     shell=False).stdout
            except (OSError, subprocess.SubprocessError):
                return False
            children: dict[int, list[int]] = {}
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3 or not parts[2].isdigit():
                    continue
                pid = int(parts[2])
                ppid = int(parts[1]) if parts[1].isdigit() else -1
                children.setdefault(ppid, []).append(pid)
            stack = list(children.get(root_pid, []))
            seen: set[int] = set()
            while stack:
                pid = stack.pop()
                if pid in seen:
                    continue
                seen.add(pid)
                stack.extend(children.get(pid, []))
            return bool(seen)
        try:
            out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True,
                                 text=True, timeout=15, shell=False).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        pairs = []
        for line in out.splitlines():
            bits = line.split()
            if len(bits) == 2 and bits[0].isdigit() and bits[1].isdigit():
                pairs.append((int(bits[0]), int(bits[1])))
        children: dict[int, list[int]] = {}
        for pid, ppid in pairs:
            children.setdefault(ppid, []).append(pid)
        stack = list(children.get(root_pid, []))
        seen: set[int] = set()
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            stack.extend(children.get(pid, []))
        return bool(seen)


# ---------------------------------------------------------------------------
# Read-only Git and guardrail
# ---------------------------------------------------------------------------

def git_read(*args: str) -> tuple[bool, str]:
    """Run a read-only git command. The argv is fixed by the caller."""
    try:
        proc = subprocess.run(["git", *args], cwd=str(ROOT), shell=False,
                              capture_output=True, text=True, timeout=20,
                              encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def git_panel() -> dict:
    if not (ROOT / ".git").exists():
        return {"is_repo": False,
                "note": "This folder is not a Git repository. The panel does not "
                        "run `git init` for you; that is your decision."}
    ok_branch, branch = git_read("rev-parse", "--abbrev-ref", "HEAD")
    ok_status, status = git_read("status", "--porcelain")
    ok_stat, stat = git_read("diff", "--stat")
    ok_head, head = git_read("log", "-1", "--pretty=%h %s")
    return {
        "is_repo": True,
        "branch": branch if ok_branch else "",
        "status": status.splitlines() if ok_status and status else [],
        "diff_stat": stat.splitlines() if ok_stat and stat else [],
        "head": head if ok_head else "",
    }


def guardrail_panel() -> dict:
    """Read-only guardrail summary between HEAD and the working tree."""
    script = ROOT / "tools" / "check_invariants.py"
    if not script.exists():
        return {"available": False, "note": "tools/check_invariants.py not found"}
    if not (ROOT / ".git").exists():
        return {"available": False, "note": "guardrail needs a Git repository"}
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(script), "--base", "HEAD",
             "--target", "HEAD", "--format", "json"],
            cwd=str(ROOT), shell=False, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "note": f"{type(exc).__name__}: {exc}"}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"available": False, "note": "guardrail produced no JSON",
                "exit": proc.returncode}
    return {"available": True, "exit": proc.returncode,
            "status": data.get("status"), "findings": data.get("findings", []),
            "not_checked": data.get("not_checked", [])}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

TASK_KINDS = {
    "polish": {
        "label": "Polish the language (no scientific change)",
        "body": ("Polish the language of {target} only. Do not change any number, "
                 "unit, formula, citation key, label, figure or table data, or the "
                 "author block. One sentence per line for text you rewrite. Do not "
                 "reflow paragraphs you did not touch."),
    },
    "review": {
        "label": "Review the change",
        "body": ("Review the change to {target} against `main`. Produce a prose "
                 "summary, a PDF diff or an explicit failure report, and a review "
                 "pack. Stop and ask if a read-only region changed."),
    },
    "summary": {
        "label": "Summary for a co-author",
        "body": ("Write a short, plain-language summary of the changes to {target} "
                 "for a co-author who does not use Git. Name the section, name the "
                 "change, and state one thing you are unsure about."),
    },
    "precheck": {
        "label": "Pre-submission check",
        "body": ("Run the pre-submission checks on {target} and the repository: "
                 "build, warnings, guardrail, and the double-blind checklist in "
                 "skills/paper-release/SKILL.md. Report what you could not verify."),
    },
}


def list_sections() -> list[str]:
    """Relative paths of sections/*.tex, sorted. Never accepts a path argument."""
    sections = ROOT / "sections"
    if not sections.is_dir():
        return []
    out = []
    for path in sorted(sections.glob("*.tex")):
        try:
            rel = path.resolve().relative_to(ROOT.resolve())
        except ValueError:
            continue                    # a symlink pointing outside the repo
        out.append(rel.as_posix())
    return out


def build_prompt(target: str, kind: str) -> dict:
    if target not in list_sections():
        raise ValueError("target is not one of the repository's section files")
    if kind not in TASK_KINDS:
        raise ValueError("unknown task kind")
    task = TASK_KINDS[kind]
    text = (
        "Read AGENTS.md and follow it as the contract for this task.\n"
        f"Then read skills/paper-edit/SKILL.md if the task is an edit, or "
        f"skills/paper-review/SKILL.md if it is a review.\n\n"
        f"Scope: {target} only. Declare the files you will touch before touching them.\n\n"
        f"Task: {task['body'].format(target=target)}\n\n"
        "Read-only regions (do not change without my explicit approval): numbers, "
        "units, formulas, citation keys, labels, figure and table data, the author "
        "block. If the task forces a change there, stop and ask.\n\n"
        "When done: run `latexmk`, then "
        "`python tools/check_invariants.py --base HEAD`, then give me the change "
        "record from AGENTS.md section 8. Do not commit, push or publish."
    )
    return {"target": target, "kind": kind, "label": task["label"], "prompt": text}


# ---------------------------------------------------------------------------
# Editor bridge
# ---------------------------------------------------------------------------

def open_vscode() -> dict:
    exe = shutil.which("code")
    if exe is None:
        return {"opened": False,
                "note": "VS Code is not on PATH. Open this folder manually:",
                "path": str(ROOT)}
    try:
        proc = subprocess.run([exe, "."], cwd=str(ROOT), shell=False, timeout=20,
                              capture_output=True)
    except (OSError, subprocess.SubprocessError):
        # `code` is usually a .cmd shim on Windows and cannot be started
        # without a shell. Point the user at the folder instead of failing.
        return {"opened": False,
                "note": "VS Code was found but cannot be launched from here. "
                        "Open this folder manually:",
                "path": str(ROOT)}
    if proc.returncode != 0:
        return {"opened": False,
                "note": "VS Code exited with an error. Open this folder manually:",
                "path": str(ROOT)}
    return {"opened": True, "path": str(ROOT)}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "AgentPaperUI/0.3.1"
    protocol_version = "HTTP/1.1"

    # -- infrastructure ----------------------------------------------------
    @property
    def state(self) -> "AppState":
        return self.server.state           # type: ignore[attr-defined]

    def handle_one_request(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Catch anything a handler raises and answer 500 instead of vanishing.

        Without this, an exception inside `do_GET`/`do_POST` closes the socket
        with no status at all, and `socketserver` prints a full traceback --
        including internal paths -- to the same stderr that is supposed to carry
        only method and path. A local tool must not show a stack trace to a
        researcher.
        """
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:                                   # noqa: BLE001
            sys.stderr.write(f"[{self.log_date_time_string()}] "
                             f"{self.command} {self.path.split('?')[0]} -> 500 "
                             f"(internal error, details suppressed)\n")
            try:
                self._fail(HTTPStatus.INTERNAL_SERVER_ERROR,
                           "internal error; see the console for one line only")
            except OSError:
                pass
            self.close_connection = True

    def log_message(self, fmt: str, *args) -> None:
        # Never log query strings or headers: the bootstrap token must not
        # reach a log file. Method and path are enough to debug.
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.command} "
                         f"{self.path.split('?')[0]}\n")

    def _send(self, status: int, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict,
              extra: dict[str, str] | None = None) -> None:
        # `ensure_ascii=True` is deliberate: a build log is decoded with
        # errors="replace" but can still contain characters (or lone surrogates
        # from a Windows console codepage) that produce an invalid JSON escape
        # when written raw. Escaping every non-ASCII character keeps the body
        # valid JSON for any client, at a small size cost.
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra)

    def _fail(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    # -- security gates ----------------------------------------------------
    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        return host == self.state.expected_host

    def _session_ok(self) -> bool:
        raw = self.headers.get("Cookie")
        if not raw:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return False
        morsel = cookie.get(SESSION_COOKIE)
        return bool(morsel) and _digest_equal(morsel.value, self.state.session_token)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin", "")
        return origin == self.state.expected_origin

    def _guard(self, *, session: bool, origin: bool) -> bool:
        if not self._host_ok():
            self._fail(HTTPStatus.FORBIDDEN, "bad Host header")
            return False
        if session and not self._session_ok():
            self._fail(HTTPStatus.UNAUTHORIZED, "no valid session")
            return False
        if origin and not self._origin_ok():
            self._fail(HTTPStatus.FORBIDDEN, "bad Origin header")
            return False
        return True

    def _read_json(self, limit: int = 8192) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > limit:
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # -- routing -----------------------------------------------------------
    def do_HEAD(self) -> None:           # noqa: N802 - BaseHTTPRequestHandler API
        # Same routing and same gates as GET, without a body: a health check or a
        # browser preflight must not get a 501, and must not get a body either.
        self.do_GET()

    def do_GET(self) -> None:            # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if not self._host_ok():
            self._fail(HTTPStatus.FORBIDDEN, "bad Host header")
            return

        if path in ("/", "/index.html", "/style.css", "/app.js"):
            self._serve_static(path)
            return

        if path == "/api/session":
            self._json(HTTPStatus.OK, {"has_session": self._session_ok()})
            return

        if path == "/api/env":
            if not self._guard(session=True, origin=False):
                return
            self._json(HTTPStatus.OK, environment_report())
            return

        if path == "/api/build/status":
            if not self._guard(session=True, origin=False):
                return
            job = self.state.builds.current()
            self._json(HTTPStatus.OK, {"job": job})
            return

        if path == "/api/git":
            if not self._guard(session=True, origin=False):
                return
            self._json(HTTPStatus.OK, {"git": git_panel(), "guardrail": guardrail_panel()})
            return

        if path == "/api/sections":
            if not self._guard(session=True, origin=False):
                return
            self._json(HTTPStatus.OK, {"sections": list_sections(),
                                       "kinds": {k: v["label"] for k, v in TASK_KINDS.items()}})
            return

        if path == "/api/pdf":
            if not self._guard(session=True, origin=False):
                return
            self._serve_pdf()
            return

        self._fail(HTTPStatus.NOT_FOUND, "no such route")

    def do_POST(self) -> None:           # noqa: N802
        path = urlparse(self.path).path
        if not self._host_ok():
            self._fail(HTTPStatus.FORBIDDEN, "bad Host header")
            return

        if path == "/api/bootstrap":
            self._handle_bootstrap()
            return

        if path == "/api/build":
            if not self._guard(session=True, origin=True):
                return
            job, started = self.state.builds.start()
            status = HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT
            self._json(status, {"job": job, "started": started,
                                "note": None if started else
                                "a build is already running; this is its job"})
            return

        if path == "/api/open-vscode":
            if not self._guard(session=True, origin=True):
                return
            self._json(HTTPStatus.OK, open_vscode())
            return

        if path == "/api/prompt":
            if not self._guard(session=True, origin=True):
                return
            data = self._read_json()
            if data is None:
                self._fail(HTTPStatus.BAD_REQUEST, "bad JSON body")
                return
            try:
                result = build_prompt(str(data.get("target", "")), str(data.get("kind", "")))
            except ValueError as exc:
                self._fail(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, result)
            return

        self._fail(HTTPStatus.NOT_FOUND, "no such route")

    # -- handlers ----------------------------------------------------------
    def _serve_static(self, path: str) -> None:
        name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        target = (UI_DIR / name).resolve()
        if UI_DIR.resolve() not in target.parents and target != UI_DIR.resolve():
            self._fail(HTTPStatus.NOT_FOUND, "not found")
            return
        if not target.is_file():
            self._fail(HTTPStatus.NOT_FOUND, "not found")
            return
        ctype = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8"}.get(
                     target.suffix, "application/octet-stream")
        self._send(HTTPStatus.OK, target.read_bytes(), ctype)

    def _serve_pdf(self) -> None:
        # Every filesystem call here can raise on a hostile or broken
        # `build/main.pdf` (a symlink or junction whose target this account may
        # not stat raises OSError from `exists()`, before any check can run).
        # Refuse the link outright rather than trying to follow it.
        try:
            if PDF_PATH.is_symlink():
                self._fail(HTTPStatus.FORBIDDEN,
                           "build/main.pdf is a link; the workbench serves only a real file")
                return
            if not PDF_PATH.exists():
                self._fail(HTTPStatus.NOT_FOUND,
                           "build/main.pdf does not exist yet; run a build")
                return
            real = PDF_PATH.resolve(strict=True)
            build_root = BUILD_DIR.resolve()
            if build_root not in real.parents:
                self._fail(HTTPStatus.FORBIDDEN, "main.pdf resolves outside build/")
                return
            data = real.read_bytes()
        except OSError as exc:
            self._fail(HTTPStatus.FORBIDDEN,
                       f"build/main.pdf could not be read safely ({exc.__class__.__name__})")
            return
        self._send(HTTPStatus.OK, data, "application/pdf")

    def _handle_bootstrap(self) -> None:
        if not self._origin_ok():
            self._fail(HTTPStatus.FORBIDDEN, "bad Origin header")
            return
        data = self._read_json()
        if data is None:
            self._fail(HTTPStatus.BAD_REQUEST, "bad JSON body")
            return
        token = str(data.get("token", ""))
        if not _digest_equal(token, self.state.bootstrap_token):
            self._fail(HTTPStatus.FORBIDDEN, "invalid bootstrap token")
            return
        cookie = (f"{SESSION_COOKIE}={self.state.session_token}; HttpOnly; "
                  f"SameSite=Strict; Path=/; Max-Age=86400")
        self._json(HTTPStatus.OK, {"ok": True, "poll_ms": POLL_HINT_MS},
                   {"Set-Cookie": cookie})


class AppState:
    def __init__(self, port: int, build_timeout: int) -> None:
        self.expected_host = f"127.0.0.1:{port}"
        self.expected_origin = f"http://127.0.0.1:{port}"
        self.bootstrap_token = secrets.token_urlsafe(32)
        self.session_token = secrets.token_urlsafe(32)
        self.builds = BuildManager(build_timeout)


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, state: AppState) -> None:
        super().__init__(address, Handler)
        self.state = state

    def handle_error(self, request, client_address) -> None:
        """One line, never a traceback.

        `socketserver`'s default prints the full stack, which both defeats the
        "method and path only" logging promise and hands the user a wall of red
        text they cannot act on. The exception type and one location are kept,
        because that is what makes a bug report possible.
        """
        import sys as _sys
        exc = _sys.exc_info()[1]
        where = "unknown"
        tb = _sys.exc_info()[2]
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
        if tb is not None:
            where = f"{tb.tb_frame.f_code.co_filename.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]}:{tb.tb_lineno}"
        sys.stderr.write(f"[server] request failed at {where}: "
                         f"{type(exc).__name__} (traceback suppressed)\n")


def make_server(port: int, build_timeout: int) -> AppServer:
    """Bind the first usable port: the requested one, else any free port."""
    ports = [port, 0] if port else [0]
    last: OSError | None = None
    for candidate in ports:
        try:
            probe = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
        except OSError as exc:
            last = exc
            continue
        actual = probe.server_address[1]
        probe.server_close()
        state = AppState(actual, build_timeout)
        return AppServer(("127.0.0.1", actual), state)
    raise SystemExit(f"could not bind a local port: {last}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Local Companion UI for this paper repository.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--print-url", action="store_true")
    ap.add_argument("--build-timeout", type=int, default=DEFAULT_BUILD_TIMEOUT)
    ap.add_argument("--serve-only", action="store_true",
                    help="print the URL and token for automated tests")
    args = ap.parse_args(argv)

    server = make_server(args.port, args.build_timeout)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/#t={server.state.bootstrap_token}"

    if args.print_url:
        print(url, flush=True)
    else:
        print(f"Agent-first Paper Workflow — local workbench", flush=True)
        print(f"  project : {ROOT}", flush=True)
        print(f"  url     : http://127.0.0.1:{port}/", flush=True)
        print("  The session token is in the URL fragment and is never logged.",
              flush=True)
        print("  Press Ctrl+C to stop.", flush=True)

    if not args.no_browser and not args.print_url and not args.serve_only:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
