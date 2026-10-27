# Self-test record — maintainer run

This is the **implementer's** own test record. It is not independent QA.
The independent record belongs in `tests/MUSE_TEST_REPORT.md`, and the two must
not be conflated.

- **UTC:** 2026-10-27 (this run)
- **Commit under test:** `git rev-parse HEAD` at run time
- **Host:** Windows 11 Pro 10.0.26200, AMD64, local machine (not a runner)
- **Python:** 3.13.9 (Anaconda)
- **Browser used for page evidence:** Chrome, headless, driven over the DevTools
  WebSocket protocol by `tests/capture_ui.py` (no Selenium/Playwright/pip)
- **Reproduce:** `python -I tests/run_all_tests.py` (serially — see the note
  below about concurrency)

## Environment

| Tool | Version |
|---|---|
| Git | 2.55.0.windows.4 |
| latexmk | 4.86a |
| pdflatex | pdfTeX 3.141592653-2.6-1.40.27, TeX Live 2025 |
| bibtex | 0.99d |
| latexdiff | 1.3.4 |
| latexpand | 1.7.2 |
| pdftotext | Poppler (Git for Windows) |

## Matrix

Status vocabulary: `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN`.

### v0.2 template

| ID | Scenario | Result | Evidence |
|---|---|---|---|
| T01 | From-scratch build, no API key | **PASS** | `latexmk` exit 0, 4 pages, no warnings |
| T01b | Log clean of undefined refs / warnings | **PASS** | `tests/check_build_log.py` exit 0 |
| T02/T04 | Guardrail scenarios | **PASS** | `tests/run_guardrail_scenarios.py` 11/11 |
| T03 | Multi-file PDF diff | **PASS** | 63 `\DIF` markers, text check passed |
| T06 | Malicious archives | **PASS** | 8 fixtures, correct exit code per class |
| T12 | Uncommitted human work survives | **PASS** | `tests/run_dirty_tree_case.py`, 6 assertions |
| T15 | Publication audit | **PASS** | `tools/publish_audit.py` clean, tree and history |

### v0.3.1 Local Companion UI

| ID | Scenario | Result | Evidence |
|---|---|---|---|
| M01 | Launcher locates the project, not the CWD | **PASS** | `start-ui.bat`/`.sh` resolve from `${BASH_SOURCE[0]}` / `%~dp0`; server resolves `ROOT` from `__file__` |
| M02 | Binds 127.0.0.1 only | **PASS** | `test_m02_binds_loopback_only` (netstat) |
| M03 | No npm/Docker/pip/API-key dependency | **PASS** | stdlib imports only; no `requirements.txt` |
| M04 | Dependency detection | **PASS** | 8 probes with versions in `state-1-ready.png` |
| M05 | Real build succeeds, PDF opens | **PASS** | `test_m05…`, PDF `%PDF`, 268 KB |
| M06 | No-TeX degradation | **PASS** | `tests/test_no_tex_degradation.py`: server starts with a Python-only PATH, `can_build=false`, blocking reasons listed, other panels answer |
| M07 | Syntax error → non-zero, useful log | **PASS** | banner names `sections/method.tex:59` |
| M07b | Undefined citation reported | **PASS** | `test_m07_undefined_citation_is_reported` |
| M08 | VS Code bridge, with and without | **PARTIAL** | probe now reports "found but cannot start without a shell" instead of leaking an exception; the "opens the right folder" path needs an interactive launch |
| M09 | Git read-only, no auto-init | **PASS** | `test_git_panel_has_no_write_route` |
| M10 | Prompt builder lists only repo paths | **PASS** | `test_prompt_builder_rejects_foreign_paths` |
| M11 | Bad Host rejected on every route | **PASS** | 4 tests, including DNS-rebinding variants |
| M12 | Session / Origin / token / no CORS | **PASS** | 7 tests |
| M13 | PDF route cannot traverse | **PASS** | 3 tests |
| M14 | `no-store` on page and PDF | **PASS** | 2 tests |
| M15 | Single build, second returns 409 | **PASS** | `test_m15_second_build_returns_409` |
| M16 | Status poll under 500 ms | **PASS** | `test_m16_status_poll_answers_quickly` |
| M17 | Timeout cleans the process tree | **PASS** | `test_m17…` (Windows `taskkill /T /F`) |
| M18 | Log bounded, head and tail kept | **PASS** | `test_m18…` (20 000 lines → under 256 KiB) |
| M19 | No external resource | **PASS (static)** | CSP `default-src 'none'`, no external URL in the three files; network-level check not run |
| M20 | Three real page states | **PASS** | `tests/results/ui-evidence/state-{1,2,3}.png` |
| M21 | Narrow viewport | **PASS** | `state-4-narrow.png` at 390 px |
| M22 | Docs match behaviour | **PARTIAL** | rewritten by the implementer; a stranger's read-through is not done |
| M23 | No silent ZIP upload | **PASS** | no upload route exists; `test_m13_unknown_routes_404` covers the shape |
| M24 | No public push/release/profile edit | **PASS** | nothing published; `.dispatch/publish.py` refuses without explicit gates |

## Defects found during this round, and their fixes

| Defect | Root cause | Fix |
|---|---|---|
| `first_problem` reported a natbib warning on a clean build | an early LaTeX pass legitimately says "citation undefined" before bibtex runs | now read from latexmk's **final** `Latex failed to resolve …` summary |
| The API returned invalid JSON when the log contained a non-UTF-8 byte | `ensure_ascii=False` wrote a lone surrogate | `ensure_ascii=True` |
| `code` probe printed `FileNotFoundError: [WinError 2]` to the user | Windows `code` is a `.cmd` shim, which `subprocess` cannot launch without a shell | probe reports "found but cannot be started without a shell" |
| The page footer leaked the user's home directory | `project_root` was rendered | footer now shows the folder name only |
| Environment probe took ~22 s and made the panel look broken | eight subprocesses per page load | memoised for the server's lifetime |
| A UI test failed only when suites ran concurrently | three suites each spawned eight probe processes on Windows | `tests/run_all_tests.py` runs them in series |
| `latexmk` ignores a `pdflatex.bat` placed earlier on PATH | latexmk resolves engines to absolute paths | the timeout/log tests point `$pdflatex` in `.latexmkrc` instead |
| The audit flagged its own browser list | Windows drive paths in a discovery list | block waiver `publish-audit:allow … / allow-end` |
| The page stayed on "Checking what is installed…" forever | the background scan landed, but the frontend's poll never started: `renderEnv` returned `false` while scanning, so `if (scanning)` was always false | `renderEnv` returns `true` while scanning and the page polls `/api/env` until it resolves |
| The Environment panel blocked the first paint for up to 22 s | the scan ran synchronously on the first request | the scan runs in a background thread; the first response returns `{"scanning": true}` immediately |
| `HEAD /` returned 501 | `BaseHTTPRequestHandler` has no default `do_HEAD` | `do_HEAD` routes through the same gates as `GET` |

## What this record does not establish

- That the science is right. Nothing here checks that.
- That macOS or Linux work. Both `BLOCKED` / `NOT_RUN`.
- That the build runs on a machine with no TeX installed.
- That a stranger can follow the quickstart unaided.
- That the UI is safe against a determined local attacker with the user's own
  privileges; the threat model in `docs/UI-ADR.md` lists what is and is not
  defended.
