# Muse hand-off — what to run, in what order, and what to write down

You are the independent QA. Nothing in `tests/SELFTEST.md` counts as your
evidence. Run the cases yourself and write your own verdicts into
`tests/MUSE_TEST_REPORT.md`.

## 0. What you need

- A clone of this repository at the commit you are testing (`git rev-parse HEAD`).
- Git ≥ 2.23, TeX Live ≥ 2023 with `latexmk`, `bibtex`, `latexdiff`,
  `latexpand`; Python ≥ 3.10 (standard library only); optionally `pdftotext`.
- A real host. A GitHub runner is not a substitute for “it works on the user's
  computer”; say which one you used.

Check the tools first:

```bash
git --version && latexmk -v && latexdiff --version && latexpand --version && python --version
```

## 1. Fast path (about two minutes)

```bash
python -I tests/run_all.py
```

This runs the eight self-test cases and writes `tests/results/selftest-run.md`.
**Do not copy that file into your report.** Use it only to see whether your
environment behaves like the implementer's. Your evidence is what *you* ran.

## 2. The cases that matter, one by one

Each of these is a separate claim. Run them independently; a failure in one does
not excuse another.

### T01 — from scratch, no API key

```bash
latexmk -C && latexmk && ls -l build/main.pdf
python -I tests/check_build_log.py
```

PASS requires: exit 0, a PDF with **4 pages**, and `check_build_log.py` exit 0.
A PDF that exists but has `[?]` citations is a FAIL.

### T03 — the PDF diff must show a change inside a sub-file

```bash
python -I tests/run_pdf_diff_case.py
```

PASS requires: `latexdiff` produced `\DIF` markers, `latexmk` exited 0, and the
changed sentence was found by `pdftotext`. The script does all three and prints
its JSON report. Then **open the produced `main-diff.pdf` yourself** — the text
check is necessary, not sufficient.

### T04 — tampering is flagged

```bash
python -I tests/run_guardrail_scenarios.py
```

PASS requires 11/11. Read the printed findings and confirm the *reason* is
right, not just the exit code: `92.4 → 92.8` must be reported as `numbers`, a
cite-key change as `citations`, `t_r → 2t_r` as `formulas`.

Then probe the boundary yourself — these are the cases the implementer says are
**not** covered, and you should confirm they are honestly reported, not silently
passed:

```bash
# a. reorder two sentences (meaning changes, tokens do not)
# b. swap two numbers between sentences
# c. add a sentence inside a custom environment the tool does not know
```

For each, record whether you got `PASS`, `FAIL` or `NOT_VERIFIED`, and whether
that matches `docs/guardrail.md`.

### T06 — malicious archives

```bash
python -I tests/make_malicious_zips.py
for z in tests/fixtures/archives/*.zip; do python -I tools/zip_inspect.py "$z"; done
```

PASS requires: `clean.zip` → exit 0; each of `traversal`, `absolute`, `symlink`,
`case-collision`, `bomb`, `executable-config`, `credentials` → exit 2 with the
right category. Also confirm **nothing was extracted**: the fixture directory
should contain only the `.zip` files afterwards.

### T07 — review pack

```bash
latexmk
python -I tools/pdf_diff.py --base HEAD --target HEAD --expect "" --out /tmp/rp
python -I tools/review_pack.py --out /tmp/rp --pdf build/main.pdf \
    --diff /tmp/rp/main-diff.pdf --summary README.md
```

Open `/tmp/rp/MANIFEST.md`. PASS requires: it names the commit, says whether the
tree was dirty, lists each file with a size and hash, and states what it does
**not** contain.

### T12 — uncommitted human work

```bash
python -I tests/run_dirty_tree_case.py
```

PASS requires all six checks to say PASS. Then do it by hand once: edit a
sentence, do **not** commit, ask your agent to polish a *different* paragraph,
and confirm your sentence is still there afterwards.

### T13 / T15 — honesty and privacy

```bash
python -I tools/publish_audit.py --deny "<your name>" --deny "<your institution>"
grep -rn "academically safe\|zero risk\|fully verified" --include="*.md" --include="*.py" .
```

PASS requires: the audit is clean, and the grep finds no over-claim. A single
sentence anywhere claiming that a green build means the science is correct is a
FAIL.

### T09 / T10 — CI

Only meaningful once the repository is pushed. Check:

- the run builds `build/main.pdf` and the artifact matches that path;
- `permissions: contents: read`;
- a pull request from a fork is **skipped** (open one from another account, or
  read the `if:` condition and say you verified it statically).

If the repository is not pushed yet, write `NOT_RUN` and say why.

### T11 — macOS

If you have a Mac: repeat T01, T03 and T06 there and record `sw_vers`,
`latexmk -v`, and the result. If not, write `BLOCKED`. A Linux result does not
count for macOS.

## 3. Adversarial cases worth trying (not in the matrix)

1. A `sections/` file with a **UTF-8 BOM** — does the build and the guardrail
   still work?
2. A path with a **space** and a **Chinese character** in it.
3. Delete `latexmk` from `PATH` and run `tests/run_all.py` — it must fail
   loudly, not report a pass.
4. A `.bib` file with a duplicate key — what does the build log say, and does
   the guardrail notice?
5. Run `tools/pdf_diff.py` with `--base` equal to `--target` — it should report
   zero `\DIF` markers and a warning, not a convincing empty diff.

## 4. Your report

Write `tests/MUSE_TEST_REPORT.md` with:

- your environment (OS and version, tool versions, host type);
- the commit SHA you tested;
- one row per case with `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN`, the exact
  command, the exit code and the key output;
- every failure with a reproduction;
- the residual risks you found that the implementer did not list;
- a final line: `READY_FOR_USER_APPROVAL` or `NOT_READY`.

You may not approve publication. That is the user's decision.
