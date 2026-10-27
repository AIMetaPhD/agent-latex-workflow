# ADR: Local Companion UI (v0.3.1)

Status: accepted for implementation
Date: 2026-10-27

## Context

v0.2 ships a template a developer can use: README, `AGENTS.md`, skills, tools,
CI. The feedback that produced v0.3.1 is that a researcher who opens the folder
does not know **what to install, how to compile, which editor to open, or what
to ask an agent**. A README cannot answer that interactively.

v0.3.1 adds an optional Local Companion UI. It is a guided control panel for the
repository it sits in. It is not an editor, not a Git client, not a SaaS, and it
never calls a model API.

## Stage 0 audit (what actually exists, verified 2026-10-27)

| Module | Real interface (checked, not assumed) | Reused by the UI |
|---|---|---|
| build | `latexmk` reads `.latexmkrc`: `$pdf_mode=1`, `$out_dir='build'`, `$aux_dir='build'`, `bibtex_use=2` | **yes** — runs `latexmk` with no overriding flags |
| guardrail | `python tools/check_invariants.py --base REF [--target REF] [--mode …] [--format json]` | **yes** — JSON mode, `--target HEAD` for a read-only summary |
| ZIP preflight | `python tools/zip_inspect.py ARCHIVE [--json]` | **no** — P0 has no upload; shown as a manual step only |
| review pack | `python tools/review_pack.py --out … --pdf …` | **no** — P0 does not build review packs; documented only |
| PDF diff | `python tools/pdf_diff.py --base … --target … --expect …` | **no** — P0 scope |
| protocol | `AGENTS.md`, `skills/*/SKILL.md` | **yes** — the prompt builder quotes them |
| CI | `.github/workflows/latex.yml` | untouched |

There is **no** `check --guard-invariants` command; the project owner's note was
right to flag that assumption. The real entry point is the script above.

Build command used by the UI, verified on this host:

```
latexmk                      # in the repository root, exit code is the result
```

Artifacts land in `build/main.pdf`, `build/main.log`, `build/main.blg`.

## Decision

A single-file-thin Python server (`ui/server.py`) with static assets
(`ui/index.html`, `ui/style.css`, `ui/app.js`), standard library only.

### Why stdlib `ThreadingHTTPServer`

The three things a UI must do at once are: answer status polls, serve a PDF, and
wait on a build. `ThreadingHTTPServer` gives each request a thread, so a build
never blocks a poll. `HTTPServer` (single-threaded) would deadlock the page for
the length of a compile.

### Why not a framework, npm, or a bundler

A researcher installing this on a Windows laptop should not need Node. Every
dependency is a support burden and an attack surface. The UI is three static
files and ~700 lines of Python; a framework would add more install failure modes
than it removes.

### Why a fixed project root

The server binds the repository it lives in, resolved from `__file__`, never from
the shell CWD and never from a request parameter. This removes an entire class
of vulnerability: there is no API that names a path, so there is no path
traversal to defend against in the API layer. It also matches the product: one
paper, one workbench.

### Session bootstrap

The launch URL carries a random token in the **fragment** (`#t=…`), which the
browser does not send to the server. The page posts it to `/api/bootstrap`; the
server checks it, sets `HttpOnly; SameSite=Strict; Path=/` session cookie, and
the script clears the fragment. Rationale:

- a token in the query string would land in the access log and in `Referer`;
- a token in a cookie set by a URL parameter would be forgeable by any page that
  can navigate the browser to `127.0.0.1`;
- the fragment is invisible to the server until the page chooses to send it, and
  the page can only read it if it is the same origin that received it.

Access logging is **disabled** for the bootstrap request and for the session
cookie value; the server logs method, path and status only.

### Listen address and Host checking

Bind `127.0.0.1` only. Every request — static, API, PDF — must carry a `Host`
that matches `127.0.0.1:<actual port>` exactly. This defeats DNS rebinding: an
attacker's domain that resolves to `127.0.0.1` still sends `Host: evil.example`,
which is rejected.

### Mutating requests

`POST /api/build`, `/api/bootstrap` and `/api/open-vscode` require:

1. a valid session cookie,
2. an `Origin` header exactly equal to `http://127.0.0.1:<port>`,
3. the correct method.

No CORS headers are ever emitted, so a cross-origin page cannot read responses
even if it can send a request.

### Subprocess policy

- fixed argument arrays, `shell=False`, `cwd=` the project root;
- an allowlist of exactly two commands: `latexmk`, and `code` (optional);
- timeout (default 300 s, overridable with `--build-timeout` for tests);
- on timeout: `taskkill /F /T /PID` on Windows, `os.killpg` on POSIX, then a
  verification that the process is gone.

### Concurrency

One build at a time, guarded by a lock. A second request returns `409` with the
current job's id, so the page can attach to the running build instead of
starting a second `latexmk` — two `latexmk` processes in one `build/` directory
corrupt each other's aux files.

### Log capture

`latexmk` output is captured into a bounded buffer (256 KiB default) that keeps
the **head and the tail**: the head has the first error, the tail has the summary.
A naive "keep the last N bytes" loses the first error, which is the one that
matters.

### Rendering

All dynamic text (log lines, file names, branch names, Git output) is inserted
with `textContent` or `createTextNode`, never `innerHTML`. A build log is
attacker-influenced if the paper is (a `\typeout{}` can print anything), so the
log is treated as untrusted data.

## Threat model

| Threat | Control | Residual risk |
|---|---|---|
| Another local process reads the UI | session cookie + fragment token | a process that can read the browser's memory or the command line of the launcher can get in; the UI has no secrets of its own |
| A web page in the browser reaches `127.0.0.1:8765` | Host check (rebinding), no CORS, SameSite=Strict cookie, Origin check on POST | an already-open same-origin tab is, by definition, the UI |
| Path traversal to read arbitrary files | no path parameter exists; PDF is a fixed file | a symlink at `build/main.pdf` would be followed — see limitation below |
| Command injection through a build request | no request field reaches a command line; fixed argv | a malicious `.latexmkrc` executes Perl. **The UI does not protect against that**; it is the same risk as running `latexmk` by hand, and the UI says so |
| XSS through the log | `textContent` only, strict CSP with no `unsafe-inline` | none known |
| Data leaving the machine | no external requests, no CDN, no model API | the researcher's own agent may send context elsewhere; the UI states this distinction |
| Denial of service on the local machine | single build lock, log cap, timeout | a large paper legitimately takes minutes |

## Deliberately not done in P0

- No ZIP upload, extraction or write: the migration path stays a documented
  manual procedure, and `tools/zip_inspect.py` stays a CLI the user runs.
- No Git write operations of any kind. The panel is read-only by construction:
  the allowlist has no `git` entry.
- No file manager button, no multi-project switching, no arbitrary directory.
- No PDF diff viewer, no review-pack builder, no LaTeX editor, no chat.
- No external fonts, styles, scripts or images. The page is self-contained.

## Known limitations (stated, not hidden)

1. A symlink placed at `build/main.pdf` would be served. The fix (resolve and
   verify the real path stays inside `build/`) is in `serve_pdf`; it is checked
   against `os.path.realpath`. If the resolved path escapes `build/`, the
   request is refused. *(Verified by `tests/test_ui_security.py`.)*
2. Build output is parsed with regular expressions for "first error". A LaTeX
   error LaTeX does not print in the usual form is not highlighted; the full log
   is always available.
3. The UI cannot tell whether the paper is scientifically correct, and says so.
4. On Windows, `taskkill` is used for the tree. If the process has already
   exited, the command fails harmlessly.
5. macOS is not tested in this environment (`BLOCKED`); the POSIX code path is
   exercised by the test suite but not on a real Mac.
