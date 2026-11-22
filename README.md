# Agent-first Paper Workflow

English | [简体中文](README.zh-CN.md)

**Git is the record. The agent does the mechanical work. You decide what is true.**

A clean, reproducible GitHub template for a **private** LaTeX paper repository that any coding agent (Claude Code, Codex, Cursor, VS Code Copilot) can edit safely, and that a supervisor or co-author who does not use Git can review as a PDF.

This is not an editor, not a LaTeX compiler, not a SaaS product, and not a custom CLI. It is an agent-operable template: a synthetic sample paper, a strict contract (`AGENTS.md`), three targeted skills, CI workflows, and four single-purpose audit/verification tools whose limits are explicitly documented.

```
your paper repo (private)
├── AGENTS.md            the single contract an agent reads
├── CLAUDE.md            points at AGENTS.md; no drifting rules
├── skills/              paper-edit, paper-review, paper-release
├── main.tex + sections/ multi-file synthetic paper (compilable out of the box)
├── .latexmkrc           build config (isolated build/, no-shell-escape)
├── .github/workflows/   clean CI build on trusted branches
└── tools/               pdf diff, archive inspection, review pack, publication audit
```

## Why

Overleaf forces manual sync, lacks fine-grained history, and does not provide an isolated workspace for AI agents. A private Git repository fixes the version history problem, but makes review difficult for collaborators who do not use Git — unless the agent automatically packages each milestone into a clean PDF and a plain-language summary.

The gap this template fills is not "generating LaTeX code". Several projects already draft content (see [docs/competitor-audit.md](docs/competitor-audit.md)). The gap is the **safety, guardrails, and review loop around a real academic manuscript**:
- an agent that stays in its lane without corrupting numbers, formulas, or citations;
- a clear Git diff and PDF diff a supervisor can read;
- a build setup that never quietly executes arbitrary code.

## Quickstart

### Prerequisites

- **Git** (≥ 2.23)
- **TeX distribution** with `latexmk` and `bibtex` (TeX Live or MiKTeX)
- **Python** (≥ 3.10, standard library only — no `pip install` required)

No external API keys are required to build or manage the paper.

### 1. Initialize from Template

Click **Use this template** on GitHub to create your own **private** repository, then clone it locally:

```bash
git clone <your-private-repo-url>
cd <your-repo>
```

### 2. Verify Local Build

Compile the synthetic paper using native `latexmk`:

```bash
latexmk
```

The compiled PDF will be generated cleanly at `build/main.pdf`.

### 3. Edit Your Paper

Replace the synthetic sample with your own manuscript:
- Preamble and structure: `main.tex`
- Section prose: `sections/*.tex`
- Bibliography: `references.bib`

## Agent Workflow

When asking an agent (Claude Code, Codex, Cursor, etc.) to collaborate, instruct it to follow `AGENTS.md`:

| Goal | Instruction to Agent | Output |
|---|---|---|
| Polish prose | "Follow `AGENTS.md` and `skills/paper-edit`, polish §2.2, language only" | Isolated branch, prose edit, clean build, guardrail check, change record |
| Review changes | "Follow `skills/paper-review`, compare `main` with `agent/...`" | Markdown summary, multi-file PDF diff, review pack |
| Send to co-author | "Pack the review artifacts" | `dist/review-pack/` containing clean PDF, diff, and summary |
| Submission snapshot | "Follow `skills/paper-release`, stage submission snapshot" | Immutable tag with commit SHA, PDF checksum, and environment note |

Agents work on dedicated branches (`agent/<date>-<slug>`), never commit directly to `main`, and never force-push.

## What is Enforced, and What is Not

| Check | Tool | Enforced |
|---|---|---|
| The paper still compiles | `latexmk` | Yes, exit code 0 |
| Numbers, formulas, citation keys, labels, authors unchanged during polish | `tools/check_invariants.py` | Yes, exit code 2 blocks delivery |
| No secrets, tokens, or local machine paths committed | `tools/publish_audit.py` | Yes, exit code 2 blocks publication |
| Archive import does not escape directory (Zip Slip) | `tools/zip_inspect.py` | Yes, refuses dangerous extraction |
| Multi-file PDF diff accurately highlights changes | `tools/pdf_diff.py` | Yes, verified text extraction |
| **Scientific correctness** | — | **No, never claimed; author remains responsible** |
| **Reference factual truth** | — | **No; guardrail verifies key preservation, not validity** |

For guardrail limitations and coverage boundaries, see [docs/guardrail.md](docs/guardrail.md).

## Security Model

`.latexmkrc` is executed as Perl code; CI steps can run arbitrary scripts. Therefore:
- CI builds **trusted internal branches only** (`contents: read`), never untrusted external pull requests.
- Shell escape (`-shell-escape`) is strictly disabled in `.latexmkrc`.
- No sensitive credentials or secrets are accessible in build steps.
- Detailed threat analysis: [docs/security.md](docs/security.md).

## Overleaf Migration

Do not extract unknown archives directly into the working tree. Follow [docs/migrate-from-overleaf.md](docs/migrate-from-overleaf.md):
1. Keep the exported `.zip` and baseline PDF as ground truth.
2. Inspect the archive using `python tools/zip_inspect.py <export.zip>`.
3. Safely copy files into the repository and commit the baseline before enabling agent edits.

## Collaborating Without Git

See [docs/collaborate-without-git.md](docs/collaborate-without-git.md) for how review packs allow non-technical co-authors and supervisors to review revisions via standard PDF readers and plain-text change summaries.

## Verification

To verify that all template guardrails, archive inspection, and audit tools pass locally on your machine:

```bash
python test_verify.py
```

## License

MIT License. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
