# Competitor and licence audit — Gate 0

**Verified at** 2026-10-26T18:45Z – 19:05Z (UTC), from a Windows 11 host with
`git 2.55.0`, `gh 2.89.0` and network access to `api.github.com` and
`gitlab.com`. Every SHA below came from the API at that time; nothing here is
copied from a badge or a README.

**Method.** Repository metadata, the default-branch tree, the licence *file*
(decoded, not the badge) and the latest commit were read through the GitHub and
GitLab APIs. Three projects were then actually exercised on this machine
(§“Hands-on trials”). Where a claim could not be tested it is marked
`UNVERIFIED` with the reason.

## Summary table

| Project | Commit / tag verified | Licence (from the file) | Last commit | Verdict for this project |
|---|---|---|---|---|
| [paper-lab](https://github.com/JoseAntonioNuevo/paper-lab) | `d584183` (main) | MIT, `LICENSE` blob `d1277d8` | 2026-09-02 | **Closest prior art.** macOS + Homebrew + Zed + Skim. Not reusable as-is on Windows. Study, do not fork. |
| [paperops](https://github.com/giacomolanciano/paperops) | `2160fc6` (master) | MIT, blob `bc197f2` | 2023-08-05 | Useful *patterns* (Overleaf `.latexmkrc`, make targets). Dormant; `make` required. |
| [alfred](https://github.com/dreadnode/alfred) | `ca19062` (main), tag `v0.5.0` | MIT, blob `0c1f1ef` | 2026-09-02 | Heavy: FastAPI + React web UI + `uv` + model provider. Out of scope (we do no UI, no backend). |
| [PaperKit](https://github.com/peternicholls/PaperKit) | `70d9a39` (master), tag `alpha-1.3.3` | MIT, blob `e1ab160` | 2026-06-19 | 312 MB tree, Python deps, own CLI. Too large to depend on for a template. |
| [latex-paper-skills](https://github.com/yunshenwuchuxun/latex-paper-skills) | `7965fbc` (main), tag `v0.1.0` | MIT, blob `934335c` | 2026-10-14 | **Overlaps most directly** (agent skills for LaTeX). Installed successfully here — see trial. Integrate/point to it rather than duplicate. |
| [latex-action](https://github.com/xu-cheng/latex-action) | `edc9ed6` (master), tag `4.1.0` | MIT, blob `cbc5be0` | 2026-07-30 | **Depend on it.** Pinned SHA `6549dc21effb2730855a1281407ecfcececc6c1b` (tag `4.1.0`). |
| [latex-diff-action](https://github.com/tawalaya/latex-diff-action) | `1ba2fef` (master) | MIT, blob `2c282a8` | **2020-07-30** | Unmaintained (last push 2021-07-01). Do not depend. Docker-only. |
| [git-latexdiff](https://gitlab.com/git-latexdiff/git-latexdiff) | `8a55444` (master) | **Not SPDX** — `COPYING` is a permissive “copying and distribution … without royalty” notice, alternatively 2-clause-BSD | 2026-06-25 | Works, but **not installed here**. Our PDF diff does not require it (§ pdf-diff). |

## Per-project evidence

### 1. paper-lab — MIT — `d584183810cf32bb0e377d40f04e65fc1eb90656`

- Tree: `AGENTS.md`, `CLAUDE.md`, `Makefile`, `bin/{paper,lib/common.sh}`,
  `prompts/`, `template/` (with `template/AGENTS.md`, `template/latexmkrc`,
  `template/.github/workflows/pdf.yml`), `zed/`, `install.sh`.
- `AGENTS.md` is a genuine precedent for the “one contract file” idea: it states
  `CLAUDE.md` is a symlink to `AGENTS.md`, never a separate copy. Our
  `CLAUDE.md`-points-to-`AGENTS.md` decision is the same conclusion reached
  independently; we do not copy its text.
- `template/AGENTS.md` contains a concrete rule set (no `\ref` in favour of
  `\cref`, no figures outside a generator script, no invented BibTeX entries).
  Useful as a checklist, not as a dependency.
- **Hands-on:** `bash install.sh` (dry-run) exits after `Homebrew is not
  installed; install it before continuing`. `bash bin/paper --help` prints its
  subcommand list on Windows. So the CLI is portable shell, but the *installer*
  is macOS-gated (Homebrew casks: Zed, Skim, MacTeX).
- **Verdict:** closest prior art; its constraints (Zed, Skim, macOS, `uv` figure
  pipeline) conflict with the target “VS Code / Codex / Claude Code on Windows
  and macOS”. Reference it in the README; do not fork it.

### 2. paperops — MIT — `2160fc63bf898b88080189db979eac069326a9b0`

- Tree: a real paper repository (`main.tex`, `intro.tex`, `experiments.tex`,
  `img/`, `biblio.bib`) plus `.bibtoolrsc*`, `scripts/`, `Makefile`,
  `.latexmkrc`, `.devcontainer.json`, one workflow `.github/workflows/build.yml`.
- `.latexmkrc` is an Overleaf-exported config: it sets `$pdf_mode`, `$bibtex_use`,
  and defines `glo2gls`, `nlo2nls`, `rtex_to_tex` (knitr via `Rscript`),
  `mf_to_tfm`, `asy`, `mpost`, `chktex`. **It is a working example of exactly
  the risk we document**: a `.latexmkrc` that calls `system()` on many external
  programs. Our guidance (“`.latexmkrc` is Perl; treat it as code”) is grounded
  in this file.
- `Makefile` calls `latexmk` with `--shell-escape`, and `make config` runs
  `git config --local core.fileMode false` and `chmod` over the tree.
- `.github/workflows/build.yml` is `workflow_dispatch` only, builds in a
  devcontainer and uploads `main.pdf`. Last commit 2023.
- **Hands-on:** `make` is **not installed** on this Windows host, so the
  documented entry point cannot run. Running `latexmk` directly on the cloned
  tree would execute the third-party `.latexmkrc`, so it was **not run**
  (`BLOCKED`: would execute unreviewed Perl from an external repository; the
  audit did not require it).
- **Verdict:** source of battle-tested Overleaf `.latexmkrc` idioms; nothing to
  depend on. Cite it in `docs/migrate-from-overleaf.md`.

### 3. alfred — MIT — `ca19062cc48d2683f9c53e1dc2128b7f82935f69`, tag `v0.5.0`

- Tree includes `ui/` (FastAPI backend + React front end), `capabilities/`,
  `templates/` (14 conference kits), `pyproject.toml` with `fastapi`,
  `uvicorn`, `websockets`, `dreadnode`, `rigging`, `duckduckgo-search`,
  `tavily-python`.
- `AGENT.md` describes `paper.yaml` as the source of truth for paper structure
  and `section/` as the ordered section files.
- **Hands-on:** `uv` is not installed here, so the documented launcher cannot
  run. **Not installed** — it requires a model provider and starts a web server.
- **Verdict:** out of scope by design (no UI, no SaaS backend, no required
  model API). Its existence is evidence that “agentic LaTeX” is a crowded space,
  which is why this project stays a template + protocol rather than a product.

### 4. PaperKit — MIT — `70d9a39a50f04975a7a1d9e8df6872278c74b4ca`, tag `alpha-1.3.3`

- Tree is 312 MB (`size` field): `Docs/`, `latex/`, `open-agents/`, `.paperkit/`,
  `specs/`, `tests/`, `scripts/`, plus `.codex/`, `.copilot/`, `.specify/`,
  `.vscode/`. `requirements.txt` needs `pyyaml`, `jsonschema`, `numpy`,
  `matplotlib`, `colormath`.
- Its install path is `curl … | bash` into `~/paperkit`, then `./paperkit init`
  and `./paperkit generate` to emit IDE-specific agent files.
- **Hands-on:** not installed. `curl | bash` from an external repository is
  outside what this audit should execute unattended, and the Python dependency
  set is far beyond “no pip requirements”.
- **Verdict:** a different product (multi-IDE generator with its own CLI). Do
  not depend; do not vendor. Mentioned only as prior art.

### 5. latex-paper-skills — MIT — `7965fbc06cd2c34ef7a0a3a566c089f4757c3de5`, tag `v0.1.0`

- 270 stars, 23 forks, actively maintained (2026-10-14), MIT, with
  `THIRD_PARTY_NOTICES.md`.
- Ships eight skills under `skills/latex-paper-skills/references/skills/`
  (`paper-from-zero`, `arxiv-paper-writer`, `empirical-paper-writer`,
  `latex-rhythm-refiner`, `results-backfill`, `collaborating-with-gemini`,
  `collaborating-with-claude`, `check-collaborators`), published to npm as
  `latex-paper-skills@0.1.0`.
- **Hands-on trial (recorded):** `node v24.12.0` (satisfies `>=22.20.0`);
  `npx --yes latex-paper-skills@0.1.0 --agent claude-code --copy --yes` in an
  empty git repo printed `Installed 1 skill … .claude\skills\latex-paper-skills`
  and exited `0`; the skill's front-matter is valid (`name`, `description`,
  `license: MIT`). The package manager also warns: *“Review skills before use;
  they run with full agent permissions.”*
- **Verdict:** it overlaps our *writing* skills and is more mature at that job
  (literature, citation verification, gated writing loops). It does **not**
  cover what this project actually exists for: a reviewable Git diff, a bounded
  read-only-region guardrail, PDF diff for a non-Git co-author, migration of an
  existing Overleaf project, and the publication gates. Recommendation: link to
  it from the README as a complement; do not copy its skills.

### 6. xu-cheng/latex-action — MIT — `edc9ed6a54876207fe7bae248873d99560dd9ead`, tag `4.1.0`

- `action.yml` is a **composite** action: it sets `INPUT_*` env vars and runs
  `action.sh`. `action.sh` does `docker run --rm … ghcr.io/xu-cheng/texlive-alpine:latest`
  (or `texlive-historic-alpine:<year>` for a pinned TeX Live year), passing the
  repo through as a volume and the `GITHUB_*` env.
- Inputs relevant to us: `root_file` (required), `working_directory`,
  `compiler` (default `latexmk`), `args`
  (default `-pdf -file-line-error -halt-on-error -interaction=nonstopmode`),
  `pre_compile`, `post_compile`, `latexmk_shell_escape` (default `false`),
  `latexmk_use_xelatex`, `latexmk_use_lualatex`, `texlive_version`.
- **Pinned SHA used in our workflow:** `6549dc21effb2730855a1281407ecfcececc6c1b`
  (the `4.1.0` tag object resolved to that commit on 2026-10-26).
- **Verdict:** depend on it, pinned. Note for our own docs: `pre_compile` /
  `post_compile` are **arbitrary bash**, which is why our workflow must never
  run on an untrusted fork PR.

### 7. tawalaya/latex-diff-action — MIT — `1ba2fefec425d434a923e599b9954b8399001d05`

- `action.yml` is `using: docker`, with `compile_diff`, `with_stats`,
  `pre_compile`, `post_compile`, `latexmk_shell_escape`.
- `entrypoint.sh` reads 13 positional args and wraps `git-latexdiff`.
- **Last commit 2020-07-30; last push 2021-07-01.** Not maintained.
- **Verdict:** do not depend. Its existence confirms that “diff PDF in CI” is
  an established need; we implement the local path instead.

### 8. git-latexdiff (GitLab) — **not SPDX-licensed** — `8a554443d821b6161c4b076f0ebc2e9a69c6cb21`

- `COPYING` reads: “Copying and distribution of git-latexdiff and its testsuite,
  with or without modification, are permitted in any medium without royalty
  provided the copyright notice and this notice are preserved… Alternatively,
  you may distribute … under the terms of the BSD licence” (2-clause BSD text
  follows).
- Tree: `git-latexdiff`, `Makefile`, `README.md`, `tests/`, `windows_install.cmd`.
- The README states it is **not** a git subcommand until installed, and that it
  prefers `latexpand` over `latexdiff --flatten` for multi-file sources.
- **Hands-on:** `git latexdiff --help` → `git: 'latexdiff' is not a git command`.
  So it is **not installed** here, and this project does not claim it works.
- **Verdict:** permissive but non-SPDX licence; a real dependency would need the
  notice preserved. We avoid it: `tools/pdf_diff.py` reaches the same result with
  `git archive` + `latexpand` + `latexdiff`, all of which are installed.

## Naming and namespace check

- `AIMetaPhD` is a **GitHub User account** (type `User`, created 2017-09-13,
  8 public repos), not an organisation. `AIMetaPhD/agent-latex-workflow` does
  **not** exist (API 404 at 2026-10-26T18:52Z).
- Name search `agent-latex-workflow in:name` → **0** repositories. Broad search
  for `agent-latex-workflow` returns 49 loosely related repos, none with that
  name.
- `agent-latex-workflow` is free on npm (404) and PyPI (404). This project
  publishes to neither, but the name does not collide.
- Crowded neighbourhood worth knowing: `appautomaton/latex-arxiv-SKILL` (469★),
  `Calix-L/awesome-latex-skills` (184★), `yunshenwuchuxun/latex-paper-skills`
  (270★). **The differentiator is not “agent + LaTeX”; it is the review and
  safety protocol around a private paper repository.**

## Decision: Reuse > Integrate > Build

| Need | Decision | Why |
|---|---|---|
| compile | reuse `latexmk` + `.latexmkrc` | installed everywhere TeX is; no wrapper |
| CI compile | depend on `xu-cheng/latex-action` @ pinned SHA | maintained, composite, no secrets needed |
| source diff | reuse `git diff` | already the source of truth |
| multi-file PDF diff | **build a thin script** (`tools/pdf_diff.py`) | `latexdiff-vc --git` fails on Windows (proved below); the script is 3 subprocess calls, not a new differ |
| diff engine | reuse `latexdiff`, `latexpand` | installed with TeX Live |
| archive safety | **build** (`tools/zip_inspect.py`) | nothing installed reports Zip Slip / symlink / case collision without extracting; `unzip -l` alone cannot see `external_attr` symlinks |
| review pack | **build** (`tools/review_pack.py`) | single-purpose file copy + manifest; explicitly not a CLI |
| read-only guardrail | **build** (`tools/check_invariants.py`) | no existing tool reports LaTeX read-only-region drift with exit codes; must state its limits |
| publication audit | **build** (`tools/publish_audit.py`) | `gitleaks`/`trufflehog` are not installed and would be a new dependency; our rules are repo-specific (host paths, deny-listed names, manuscript markers) |
| writing/literature skills | **do not build** | `latex-paper-skills` does it better; link to it |

Nothing here copies third-party source code. The `.latexmkrc` in this repository
was written for it. `docs/pdf-diff.md` documents why `git-latexdiff` is not used.

## Claims that stay UNVERIFIED

| Claim | Status | Reason |
|---|---|---|
| alfred’s launcher works on Windows | `UNVERIFIED` | `uv` not installed; requires a model provider |
| PaperKit installs cleanly on Windows | `UNVERIFIED` | `curl \| bash` installer not executed |
| paperops builds end-to-end | `UNVERIFIED` | `make` absent; its `.latexmkrc` runs `system()` on R, qpdf, asy, mpost |
| git-latexdiff produces correct diffs | `UNVERIFIED` | not installed |
| latex-diff-action still works with current runners | `UNVERIFIED`, likely no | last commit 2020 |
