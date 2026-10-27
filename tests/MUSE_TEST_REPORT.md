# Muse independent test report

**Status: `BLOCKED` — Muse returned, but the verdicts are not readable by the implementer.**

Two generations were dispatched. All four v0.3.1 UI tasks reached a terminal
state, and both v0.2 template tasks are still held by `muse-3` with no result.
The result **bodies** are isolated per recipient, so as producer I can see only
`result_status`, never the findings. That is the queue's design, not a fault in
Muse's work; it means I cannot honestly report *what* Muse found.

Nothing here is a verdict, and nothing from `tests/SELFTEST.md` has been copied
into this file.

## What is queued

| Generation | Task kind | Covers | State |
|---|---|---|---|
| v0.2 template | `agentlatexworkflow_a` | paper, protocol, skills, build/CI, doc honesty | claimed by muse-3, no result |
| v0.2 template | `agentlatexworkflow_b` | the five tools and six test scripts | claimed by muse-3, no result |
| v0.3.1 UI | `agentlatexui_a` `369b407f…` → muse-1 | security and contract | finished, `result_status: rejected` |
| v0.3.1 UI | `agentlatexui_b` `f9c753b5…` → muse-1 | behaviour and page evidence | finished, `result_status: success` |
| v0.3.1 UI | `agentlatexui_a` `d6c285b0…` → muse-3 | security and contract | finished, `result_status: failure` |
| v0.3.1 UI | `agentlatexui_b` `05964cb5…` → muse-3 | behaviour and page evidence | finished, `result_status: failure` |
| v0.2 template | `agentlatexworkflow_a/b` → muse-3 | paper, protocol, tools, tests | still `claimed`, no result after 3+ hours |

The two UI tasks were dispatched twice: once to `muse-3`, which had already
been holding the template tasks for hours without returning a result, and again
to `muse-1` to spread the load. The queue does not support withdrawal, so four
UI tasks were outstanding. Both Muses answered, and they disagreed — which is
itself useful information, and is recorded here rather than hidden.

`rejected` is a compliance refusal, not a failed test: `muse-1` declined to
execute the security range for a reason only it can see. `failure` means a
runnable item did not pass. Neither body is readable from this side, so neither
can be summarised here without inventing content.

A follow-up (`agentlatexui_{a,b}_resubmit`) was sent to both. `muse-1` answered
both with `result_status: rejected` again; `muse-3` has not yet returned on the
resubmission. A repeated `rejected` after an explicit format request is not a
protocol error to be worked around: `rejected` is a compliance refusal, and the
queue is designed so the producer cannot see the reason. Forcing a third attempt
would be exactly the "change the packaging to get past the refusal" behaviour the
project's own audit history forbids.

**The user authorised one narrow question** — "the single most severe finding,
with its reproduction, and nothing else" — sent to both `muse-1` and `muse-3`:

| Muse | Answer to the one question |
|---|---|
| muse-1 | finished, `result_status: rejected` again |
| muse-3 | finished, `result_status: success` |

So even a one-question request was declined by `muse-1`, while `muse-3` accepted
it and reported success. Neither body is readable from the producer side, so the
finding itself — if there is one — is still unknown here.

That is the point at which the implementer stops asking. Reducing the scope
twice and re-sending would be pressuring a reviewer that has already declined,
which the project's own audit history forbids. **The user then authorised an
independent review agent** to cover what Muse did not deliver; its record goes in
`tests/results/independent-audit.md`, and it is an internal review, not Muse.

Dispatch and polling scripts: `.dispatch/dispatch.py`, `.dispatch/dispatch_ui.py`,
`.dispatch/poll.py`. These are not committed to the repository (`.dispatch/` is
git-ignored) because they reference the queue's location.

## What Muse must produce

`tests/MUSE_UI_ACCEPTANCE_REPORT.md` for the UI generation, following
`PROMPT_MUSE_TEST_v0.3.1.md`, and this file for the template generation. Each
item marked `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN` with the command, the exit
code or HTTP status, and the evidence path.

A final verdict line in this file must be exactly:

```text
Conclusion: READY_FOR_USER_APPROVAL
```

or

```text
Conclusion: NOT_READY
```

The publication gate in `.dispatch/publish.py` only opens on the first form,
written that way and nothing else. A template line that merely mentions the
phrase does not count, by design.

## Why this is BLOCKED rather than a verdict

- `claimed` means Muse picked the task up; it is not a result.
- The implementer may not fill this in on Muse's behalf.
- A single historical canary passing does not stand in for these runs.

## What is and is not known

| | |
|---|---|
| Muse **participated** | yes — four terminal results plus two still held |
| Muse **found something worth reporting** | `failure` twice and `rejected` once, so something was said |
| **What** it found | **unknown to the implementer** — bodies are recipient-isolated |
| Independent QA complete | **no** |
| Publishable | **no** |

Until a resubmission or a user-relayed report arrives, this repository has
implementer evidence only.

## What the implementer is willing to state without Muse

The implementer's own record is in `tests/SELFTEST.md` and it says so in its
first paragraph: 8/8 suites on Windows, three real page states captured in a
real browser, macOS `BLOCKED`, no-TeX degradation `BLOCKED`, and the honesty
limits listed at the end. That is a claim about one machine on one day, and it
is not independent QA.
