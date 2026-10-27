---
name: paper-release
description: Prepare an auditable snapshot of the paper for submission, revision or camera-ready — commit SHA, PDF hash, build environment, and a double-blind checklist — without publishing anything. Use when the user asks to freeze, snapshot, tag or prepare a submission.
license: MIT
---

# Skill: paper-release

A snapshot is a **record**, not a publication. This skill produces the record and
stops. Tagging, pushing and publishing need the author's explicit words
(`AGENTS.md` §9).

## 0. Refuse to start unless

- the working tree is clean (`git status --porcelain` is empty) — a snapshot of
  a dirty tree is not reproducible;
- `latexmk` exits `0` **from a clean build**:

  ```bash
  latexmk -C
  latexmk
  ```

- the author has named the stage: `submission`, `revision` or `camera-ready`.

If any of those is missing, say which one and stop.

## 1. Record

```bash
python tools/review_pack.py --snapshot dist/snapshots/<stage> \
  --pdf build/main.pdf --stage <stage>
```

The snapshot directory gets:

- `SNAPSHOT.md` — stage, UTC time, `git rev-parse HEAD`, branch, dirty flag,
  SHA256 of the PDF, TeX/`latexmk`/`bibtex` versions, engine, the exact build
  command, and the person who asked;
- `main.pdf` — the built PDF;
- `source.tar.gz` — the tracked source at that commit (`git archive`), so the
  snapshot can be rebuilt without the full history.

Verify the hash yourself after writing it; do not copy a hash from a log.

## 2. Double-blind checklist (manual, always)

Write `BLIND-CHECK.md` next to the snapshot and go through every line **by hand**:

- [ ] author names, affiliations, emails in `main.tex`
- [ ] `\thanks`, funding, grant numbers, acknowledgements
- [ ] PDF metadata (`pdfinfo build/main.pdf` — `Author`, `Title`, `Creator`)
- [ ] self-citations phrased in the third person
- [ ] repository URLs, dataset URLs, internal hostnames in the text
- [ ] supplementary material and its filenames
- [ ] hidden files shipped with the archive (`.git`, `.DS_Store`, editor backups)
- [ ] figure metadata (EXIF, embedded author fields)
- [ ] comments in the source (`%` lines) that name people or venues

Automation cannot certify this. State that the checklist was done manually, by
whom, and on which date.

## 3. What you must not do

- Do not create a git tag. Propose the tag name (`paper-<stage>-<YYYYMMDD>`) and
  wait.
- Do not push anything, anywhere.
- Do not upload the PDF to a conference system, preprint server or cloud drive.
- Do not conflate this snapshot with a release of the **tool** this repository
  came from; they version independently.

## 4. Report

```text
Snapshot   : dist/snapshots/<stage>/SNAPSHOT.md
Commit     : <sha>
PDF SHA256 : <hash, recomputed>
Blind check: manual, <n> items, <m> open
Tag        : NOT CREATED (awaiting author)
Publication: NOT PERFORMED
```
