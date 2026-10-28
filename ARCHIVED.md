# ARCHIVED — this direction was wrong

**This repository is a failure archive.** It is kept so the next attempt does not
repeat the same mistakes, not because it is a usable product.

## What happened

The v0.3.1 specification asked for a "Local Companion UI": an environment
checker, a compile button, a PDF preview, a prompt generator and a read-only Git
panel. It was implemented, and it is technically sound — 11 test suites pass, a
security audit found 7 defects which were all fixed and re-verified, and the
page was captured in a real browser in three states.

The user tried it and said: *"none of it matches my expectations, not one bit."*

They were right. What they wanted was a **local, AI-powered Overleaf**: source on
the left, PDF on the right, an API key field, and a model that edits the paper in
place. What the specification explicitly forbade was:

> **P0 explicitly not doing**
> - a built-in LaTeX editor or chat window
> - any Shell command interface, **model API**, external CDN

The specification and the requirement were opposites, not merely different.

## What is still worth keeping

The build layer and the security layer are reusable and tested:

| Asset | Why it is worth keeping |
|---|---|
| `ui/server.py` → `BuildManager` | asynchronous compile, bounded log with head+tail, Win32 Job Object so a timed-out build leaves no orphan process |
| `ui/server.py` → `Handler` | Host/Origin/session gates, CSP, no CORS, 31 security tests |
| `tools/check_invariants.py` | read-only-region guardrail — useful as a rail when an AI edits |
| `tools/pdf_diff.py` | multi-file PDF diff that works on Windows (where `latexdiff-vc --git` does not) |
| `tests/capture_ui.py` | real Chrome over the DevTools protocol, no Selenium dependency |
| `tests/test_ui_robustness.py` | regression tests for seven real defects |

The frontend should be rewritten. The 1190-line server's security and build
layers should be lifted, not rebuilt.

## What the next attempt must not repeat

1. Do not make "environment check" the first thing a user sees. They do not care
   about their environment; they care about writing.
2. Do not ship a product called *Agent-first* with no model in it.
3. Do not write acceptance criteria that are all technical. The first one should
   be: *a stranger goes from double-click to seeing their own edit in a PDF in
   under three minutes, without reading documentation.*
4. Do not put the API key question last. Where the key is stored decides the
   whole security model.

## Concrete traps already paid for

- `latexdiff-vc --git` fails on Windows: Perl hands `git archive | ( cd … ; tar -xf - )`
  to `cmd.exe`, which has no subshell.
- `wmic` was removed in Windows 11 24H2; any process query using it fails
  silently and looks like "clean".
- `taskkill /T` walks the tree once; a grandchild spawned later becomes an
  orphan. A Win32 Job Object is the only race-free answer.
- Answering without reading the request body makes Windows reset the connection,
  so the client never sees the status code.
- Probing eight tools synchronously costs ~20 s; it must run in the background.
- Running test suites concurrently starves each other's subprocesses and
  produces false failures.

## Status of the other work in this repository

The v0.2 part — the paper template, `AGENTS.md`, the skills, the toolchain and
CI — was not part of the failure. It is independent of the UI and can be reused
as-is.

Independent QA by Muse never closed: the queue's result bodies are isolated per
recipient, so the implementer could only see `result_status` (`rejected`,
`success`, `failure`, `failure`) and never the findings. That is recorded
honestly in `tests/MUSE_TEST_REPORT.md`.

See `HANDOFF_TO_CHATGPT_2026-10-28.md` in the parent folder for the full
post-mortem and the questions the next specification must answer.
