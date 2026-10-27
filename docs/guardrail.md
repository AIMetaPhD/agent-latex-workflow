# The guardrail, and what it does not do

`tools/check_invariants.py` compares two revisions of the paper and reports
whether a **read-only region** changed. It is the only mechanism in this
repository that can block a commit on a semantic ground, so its limits matter
more than its features.

## What it compares

| Category | Extracted from | Blocks in `polish` |
|---|---|---|
| `numbers` | digits outside maths, comments, `\cite`, `\label`, `\ref` | yes |
| `formulas` | `$…$`, `$$…$$`, `\(…\)`, `\[…\]` and 13 maths environments | yes |
| `citations` | every `\cite*{…}` key (comma lists split) | yes |
| `bibliography` | `@type{key,` entries in `.bib` | yes |
| `labels` | `\label{…}` | yes |
| `references` | `\ref`, `\eqref`, `\cref`, `\Cref`, `\autoref`, `\pageref`, `\nameref` | yes |
| `figures` | `\includegraphics{…}` targets | yes |
| `authors` | `\author{…}`, `\thanks{…}`, an acknowledgements environment/section | yes |
| `build-config` | `.latexmkrc`, `Makefile`, anything under `tools/` or `.github/` | yes |

Text inside `verbatim`, `Verbatim`, `lstlisting`, `minted` and `comment`
environments is masked before extraction, and `%` comments are removed — with
`\%` correctly left alone.

## Exit codes

| Code | Meaning | What the agent must do |
|---|---|---|
| `0` | `PASS` | quote the summary line and continue |
| `2` | `FAIL` | **stop.** Show the findings; do not commit; ask the author |
| `3` | `NOT_VERIFIED` | say which file could not be parsed; do not claim safety |

`3` is a success of the tool, not a failure of the paper: a file it cannot parse
is a file it did not check, and saying so is more useful than a false `PASS`.

## Known misses — read this before trusting a PASS

1. **Reordering.** Moving a sentence changes meaning and changes no token.
2. **Context swaps.** “92.4% on dataset A, 71.0% on B” → swapped numbers keeps
   the multiset of tokens only if the same values appear; even then the
   *position* is ignored, because the tool compares multisets, not positions.
3. **Duplication and deletion of identical values.** Two `92.4` become one
   `92.4`: a multiset comparison sees it, a set comparison would not — the tool
   uses multisets for this reason, but it still cannot say *which* one went.
4. **Semantic drift without token drift.** “reduces latency” → “does not reduce
   latency” changes one word; if that word repeats elsewhere, the count can be
   preserved only in contrived cases, but the tool would not explain it.
5. **Maths it cannot parse.** A custom environment not in `MATH_ENVS`, or a
   macro that takes a `$` as an argument, can break the scanner. That raises
   `ParseError` → exit `3`, never a silent pass.
6. **Numbers inside maths are reported as formulas, not numbers.** `\gamma=0.2`
   is a formula change; that is intended, but it means the `numbers` category is
   not a complete inventory of digits.
7. **BibTeX accuracy.** The tool checks that keys exist and are referenced. It
   cannot check that `smith2024` is a real paper, that the year is right, or that
   the entry matches the PDF.
8. **Anything outside `.tex`, `.bib`, `.cls`, `.sty`.** A figure's binary
   content, a CSV of results, a `.sty` macro body — the first two are skipped
   entirely; `.sty` is parsed as LaTeX and may land in exit `3`.

## The inverse error

The tool can also **over-report**. Renaming a label rewrites `\label` and
`\eqref`, which shows up in both `labels` and `references` (correct) and, before
the current implementation, also in `formulas` (wrong — fixed by stripping
`\label`/`\tag` from maths bodies). A legitimate content edit in `content` mode
downgrades `numbers` and `formulas` to `REVIEW`, which does not block; that is a
deliberate trade, and it means `content` mode is **not** protection.

## What to say in a report

> Guardrail: PASS — 2 files, categories numbers/formulas/citations/labels/
> references/figures/authors/build-config. Not checked: scientific correctness,
> reference accuracy, sentence meaning.

Never: “the paper is unchanged”, “no risk”, “academically safe”.

## Regression evidence

`tests/run_guardrail_scenarios.py` builds eleven cases in a scratch copy of the
repository and asserts the exit code for each:

| Case | Expected |
|---|---|
| clean tree | `0` |
| `92.4%` → `92.8%` | `2` |
| `\cite{smith2024}` → `\cite{smith2025}` | `2` |
| equation `t_r` → `2t_r` | `2` |
| label rename + its `\eqref` | `2` |
| author block rewritten | `2` |
| language-only rewrite | `0` |
| `.bib` key renamed | `2` |
| number changed in `content` mode | `0` with `REVIEW` |
| two table cells changed | `2` |
| table placement `[t]` → `[!t]` | `0` |

The recorded run is in `tests/guardrail-scenarios.log`.
