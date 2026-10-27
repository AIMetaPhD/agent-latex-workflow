# Migrate an existing Overleaf project

The goal is a private repository that builds the same PDF as Overleaf, with the
original project untouched. Do this **before** an agent edits anything.

## 0. Keep the original

1. In Overleaf: *Menu → Download → Source* (a ZIP), and separately
   *Download → PDF*.
2. Store both outside the repository, e.g. `~/papers/<project>/archive/`.
3. Record the date and the Overleaf project name in `migration-log.md` inside
   your new repository. The ZIP is the fallback for everything below.

Do **not** unzip into the new repository. Do not `git add` the ZIP.

## 1. Inspect the archive

```bash
python -I tools/zip_inspect.py ~/papers/<project>/archive/overleaf.zip
```

Exit `0` (`CLEAN`) means none of the listed hazards are present. Exit `2`
(`RISKY`) means at least one: path traversal, an absolute path, a symlink, a
case collision, an expansion bomb, an executable build config, or a
credential-looking file.

The inspector never extracts and never runs anything. If it reports
`executable-config` (`.latexmkrc`, `Makefile`), read that file before you build:
it is the difference between a document and a program.

## 2. Choose the main file and the engine

Overleaf's main file is in *Menu → Settings → Main document*. Copy that name.
The engine (`pdfLaTeX`, `XeLaTeX`, `LuaLaTeX`) is in the same menu.

| Engine | What to change |
|---|---|
| pdfLaTeX | nothing; this template already uses `pdflatex` |
| XeLaTeX | `$pdf_mode = 5;` and `$xelatex = 'xelatex …'` in `.latexmkrc` — **not tested by this template** |
| LuaLaTeX | `$pdf_mode = 4;` and `$lualatex = …` — **not tested** |

Record the engine in `migration-log.md`. A font that exists on Overleaf may be
missing locally; that is a build failure, not a reason to change the paper.

## 3. Copy files in by hand

Extract the archive **to a scratch directory outside the repository**, then copy
only what the paper needs:

```bash
mkdir -p ~/papers/<project>/scratch
cd ~/papers/<project>/scratch
unzip ~/papers/<project>/archive/overleaf.zip
# read the tree before copying anything
find . -maxdepth 2 -type f | head -50
```

Copy into the repository: `*.tex`, `*.bib`, `*.cls`, `*.sty`, `figures/`,
`images/`. Do **not** copy:

- `.latexmkrc` from Overleaf, unless you have read it (it often calls `system()`);
- `output.pdf`, `*.aux`, `*.log`, `latexmkrc`-generated clutter;
- anything under a name the inspector flagged;
- any `.git` directory (it would fight yours).

If a `.cls` or `.sty` came from a publisher, keep it: it is your project's
dependency, and its licence travels with the paper, not with this template.

## 4. Commit the baseline before touching content

```bash
git add -A
git commit -m "import: baseline from Overleaf export <date>, engine pdflatex"
latexmk                      # must succeed, or fix the build before going on
cp build/main.pdf ~/papers/<project>/archive/baseline.pdf
sha256sum build/main.pdf >> migration-log.md
```

A baseline PDF plus a commit SHA is what makes every later diff meaningful. Do
not let an agent rewrite text before this commit exists.

## 5. First guarded edit

```bash
git switch -c agent/<date>-first-pass
```

Then follow `skills/paper-edit/SKILL.md`. Because the baseline commit exists, the
guardrail has something honest to compare against, and the review pack has a
before and an after.

## Troubleshooting

| Symptom | Usual cause | Fix |
|---|---|---|
| `! LaTeX Error: File 'X.sty' not found` | package not in your TeX install | install it (`tlmgr install X`) or ask whether the paper needs it |
| citations render as `[?]` | `bibtex` not run, or `.bib` path changed | check `\bibliography{…}`; run `latexmk` again |
| fonts look different from Overleaf | Overleaf uses XeLaTeX with system fonts | record it; this template does not test XeLaTeX |
| `main.tex` has `\input{../shared/…}` | Overleaf project had a sibling folder | copy the sibling folder too, or the build breaks |
| PDF is 1 page | the wrong main file was chosen | set the main file explicitly in `.latexmkrc` / the VS Code recipe |

## What not to do

- Do not delete the Overleaf project. It is your backup until the repository has
  a tag you trust.
- Do not "clean up" the LaTeX while importing. A migration commit should change
  **no** content, so that later diffs are readable.
- Do not push the repository anywhere public before
  `python -I tools/publish_audit.py` returns clean.
