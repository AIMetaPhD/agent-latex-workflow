#!/usr/bin/env python3
"""Bounded guardrail: did an edit touch something it should not have?

This compares two revisions of a LaTeX project and reports which *read-only
regions* changed: numbers, formulas, citation keys, labels, figure targets, the
bibliography, the author block, and build configuration.

It is deliberately narrow.  It answers "did these tokens change?", which is a
useful signal.  It does NOT answer "is the science still right?" -- a reordered
sentence, a duplicated number or a swapped context leaves every token count
intact while changing the meaning.  Read docs/guardrail.md before quoting this
tool in a report.

Exit codes
    0   PASS          no blocking change found in the categories checked
    2   FAIL          a read-only region changed (see findings)
    3   NOT_VERIFIED  a file could not be parsed; the check did not cover it

Usage
    python -I tools/check_invariants.py --base HEAD --mode polish
    python -I tools/check_invariants.py --base main --target agent/x --mode polish
    python -I tools/check_invariants.py --base HEAD --mode content --format json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

SOURCE_SUFFIXES = (".tex", ".bib", ".cls", ".sty")
CONFIG_PREFIXES = (".github/", "tools/", "tests/")
CONFIG_NAMES = (".latexmkrc", "latexmkrc", "Makefile", "makefile", "GNUmakefile")

VERBATIM_ENVS = ("verbatim", "verbatim*", "Verbatim", "lstlisting", "minted", "comment")
MATH_ENVS = (
    "equation", "equation*", "align", "align*", "flalign", "flalign*",
    "gather", "gather*", "multline", "multline*", "eqnarray", "eqnarray*",
    "displaymath", "math",
)

# category -> (severity in polish, severity in structural, severity in content)
# "risk" blocks the run, "review" must be listed for a human, None cannot occur.
POLICY = {
    "numbers":      ("risk",   "risk",   "review"),
    "formulas":     ("risk",   "risk",   "review"),
    "citations":    ("risk",   "risk",   "risk"),
    "bibliography": ("risk",   "risk",   "risk"),
    "labels":       ("risk",   "review", "review"),
    "references":   ("risk",   "review", "review"),
    "figures":      ("risk",   "risk",   "review"),
    "authors":      ("risk",   "risk",   "risk"),
    "build-config": ("risk",   "risk",   "risk"),
}

CATEGORY_ORDER = list(POLICY)

NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])")
CITE_RE = re.compile(r"\\(?:[A-Za-z]*cite[A-Za-z]*|nocite)\*?(?:\[[^\]]*\])*\{([^}]*)\}")
LABEL_RE = re.compile(r"\\label\{([^}]*)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|cref|Cref|autoref|pageref|nameref)\{([^}]*)\}")
GRAPHIC_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}")
AUTHOR_RE = re.compile(r"\\author\s*\{")
THANKS_RE = re.compile(r"\\thanks\s*\{")
ACK_RE = re.compile(r"\\(?:begin|section\*?|chapter\*?)\s*\{?\s*[Aa]cknowledg", re.MULTILINE)


# --------------------------------------------------------------------------
# Git access
# --------------------------------------------------------------------------


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: " + proc.stderr.decode("utf-8", "replace")
        )
    return proc.stdout.decode("utf-8", "replace")


def changed_files(base: str, target: str | None) -> list[str]:
    spec = [base] if target is None else [base, target]
    out = git("diff", "--name-only", "-z", *spec)
    return [p for p in out.split("\0") if p]


def read_at(ref: str, path: str) -> str | None:
    proc = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True)
    if proc.returncode != 0:
        return None
    if b"\0" in proc.stdout[:4096]:
        raise ValueError("binary")
    return proc.stdout.decode("utf-8")


def read_worktree(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\0" in raw[:4096]:
        raise ValueError("binary")
    return raw.decode("utf-8")


# --------------------------------------------------------------------------
# LaTeX parsing (small, and honest about where it gives up)
# --------------------------------------------------------------------------


class ParseError(Exception):
    pass


def skip_control_sequence(text: str, i: int) -> int:
    """Return the index just past the control sequence whose backslash is at `i`.

    A backslash followed by a letter starts a command name (`\\gamma`, `\\cite`),
    and the whole name is skipped.  Anything else is a control symbol and is
    exactly two characters.  The distinction matters: in `\\\\$x$` the two
    backslashes are a line break, so the `$` still opens maths.  Treating every
    backslash as "skip two characters" reads it as an escaped dollar and loses
    the formula, which is exactly what happened before this helper existed.
    """
    j = i + 1
    if j >= len(text):
        return j
    if text[j].isalpha():
        while j < len(text) and text[j].isalpha():
            j += 1
        if j < len(text) and text[j] == "*":
            j += 1
        return j
    return j + 1


def strip_comments(text: str) -> str:
    """Remove `%` comments, leaving `\\%` escapes intact."""
    out_lines = []
    for line in text.splitlines():
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "\\":
                i = skip_control_sequence(line, i)
                continue
            if ch == "%":
                cut = i
                break
            i += 1
        out_lines.append(line[:cut])
    return "\n".join(out_lines)


def remove_verbatim(text: str) -> str:
    for env in VERBATIM_ENVS:
        pattern = re.compile(
            r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}",
            re.DOTALL,
        )
        text = pattern.sub(lambda m: "\\begin{" + env + "}...\\end{" + env + "}", text)
    return text


def matching_brace(text: str, start: int) -> int:
    """Index just past the brace that closes the one at `start`; -1 if unbalanced."""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def macro_bodies(text: str, pattern: re.Pattern[str]) -> list[str]:
    bodies = []
    for m in pattern.finditer(text):
        end = matching_brace(text, m.end() - 1)
        if end < 0:
            raise ParseError("unbalanced braces after " + m.group(0).strip())
        bodies.append(text[m.end():end - 1])
    return bodies


def extract_math(text: str) -> tuple[list[str], str]:
    """Return (math bodies, text with math removed).

    Raises ParseError when the delimiters do not balance, because a silently
    wrong split would under-report formula changes -- a false PASS is worse than
    an honest NOT_VERIFIED.  The order of the branches is load-bearing:
    `\\begin` is a control word, so environments are matched first; `\\[` and
    `\\(` are control symbols, so they are matched before the generic skip.
    """
    bodies: list[str] = []
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        # 1. display maths environments
        if text.startswith("\\begin{", i):
            m = re.match(r"\\begin\{([^}]+)\}", text[i:])
            env = m.group(1) if m else ""
            if env in MATH_ENVS:
                end_tag = "\\end{" + env + "}"
                j = text.find(end_tag, i)
                if j < 0:
                    raise ParseError(f"unclosed environment {env}")
                body = text[i + len(m.group(0)):j]
                # \label and \tag are bookkeeping, not maths: a renamed label
                # belongs under `labels`, not under `formulas`.
                body = re.sub(r"\\(?:label|tag)\*?\{[^}]*\}", " ", body)
                bodies.append(" ".join(body.split()))
                i = j + len(end_tag)
                continue
            out.append(text[i:i + len(m.group(0))])
            i += len(m.group(0))
            continue
        # 2. \[ ... \] and \( ... \)
        if text.startswith("\\[", i):
            j = text.find("\\]", i + 2)
            if j < 0:
                raise ParseError("unclosed \\[")
            bodies.append(" ".join(text[i + 2:j].split()))
            i = j + 2
            continue
        if text.startswith("\\(", i):
            j = text.find("\\)", i + 2)
            if j < 0:
                raise ParseError("unclosed \\(")
            bodies.append(" ".join(text[i + 2:j].split()))
            i = j + 2
            continue
        # 3. a backslash starting a control symbol
        if text[i] == "\\" and i + 1 < n and not text[i + 1].isalpha():
            if text[i + 1] == "$":          # \$ : a literal dollar, not maths
                i += 2
                continue
            if text[i + 1] == "\\":         # \\ : a line break, protects nothing
                i += 2
                continue
            out.append(text[i:i + 2])
            i += 2
            continue
        # 4. a command name such as \gamma: it cannot open or close maths
        if text[i] == "\\" and i + 1 < n:
            out.append(" ")
            i = skip_control_sequence(text, i)
            continue
        # 5. inline maths with $ or $$
        if text[i] == "$":
            delim = "$$" if text.startswith("$$", i) else "$"
            j = i + len(delim)
            while j < n:
                if text[j] == "\\":
                    j = skip_control_sequence(text, j)
                    continue
                if text.startswith(delim, j):
                    break
                j += 1
            if j >= n:
                raise ParseError("unbalanced $ delimiter")
            bodies.append(" ".join(text[i + len(delim):j].split()))
            i = j + len(delim)
            continue
        out.append(text[i])
        i += 1
    return bodies, "".join(out)


@dataclass
class Features:
    numbers: Counter = field(default_factory=Counter)
    formulas: Counter = field(default_factory=Counter)
    citations: Counter = field(default_factory=Counter)
    labels: Counter = field(default_factory=Counter)
    references: Counter = field(default_factory=Counter)
    figures: Counter = field(default_factory=Counter)
    authors: Counter = field(default_factory=Counter)
    unparsed: list[str] = field(default_factory=list)


def extract_tex(text: str) -> Features:
    feats = Features()
    if ACK_RE.search(text):
        feats.authors["<acknowledgements>"] += 1
    for body in macro_bodies(text, AUTHOR_RE) + macro_bodies(text, THANKS_RE):
        feats.authors[" ".join(body.split())] += 1

    clean = remove_verbatim(strip_comments(text))

    for key in CITE_RE.findall(clean):
        for part in key.split(","):
            part = part.strip()
            if part:
                feats.citations[part] += 1
    for name in LABEL_RE.findall(clean):
        feats.labels[name.strip()] += 1
    for name in REF_RE.findall(clean):
        feats.references[name.strip()] += 1
    for name in GRAPHIC_RE.findall(clean):
        feats.figures[name.strip()] += 1

    try:
        math, rest = extract_math(clean)
    except ParseError as exc:
        feats.unparsed.append(str(exc))
        math, rest = [], clean

    for body in math:
        feats.formulas[body] += 1

    # Numbers are compared outside math, cite and label arguments, so that
    # renumbering a label is not mistaken for a changed measurement.
    rest = CITE_RE.sub(" ", rest)
    rest = LABEL_RE.sub(" ", rest)
    rest = REF_RE.sub(" ", rest)
    rest = re.sub(r"\\[A-Za-z@]+\*?", " ", rest)
    for token in NUMBER_RE.findall(rest):
        feats.numbers[token] += 1
    return feats


BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{([^,]+),", re.IGNORECASE)


def extract_bib(text: str) -> Features:
    feats = Features()
    clean = strip_comments(text)
    for kind, key in BIB_ENTRY_RE.findall(clean):
        feats.citations[f"{key.strip()} ({kind.lower()})"] += 1
    return feats


def extract(path: str, text: str) -> Features:
    if path.endswith(".bib"):
        return extract_bib(text)
    return extract_tex(text)


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


@dataclass
class Finding:
    path: str
    category: str
    severity: str
    detail: str

    def as_dict(self) -> dict:
        return {"path": self.path, "category": self.category,
                "severity": self.severity, "detail": self.detail}


def counter_diff(old: Counter, new: Counter) -> tuple[list[str], list[str]]:
    return sorted((new - old).elements()), sorted((old - new).elements())


FEATURE_ATTR = {
    "numbers": "numbers",
    "formulas": "formulas",
    "citations": "citations",
    "labels": "labels",
    "references": "references",
    "figures": "figures",
    "authors": "authors",
}


def compare(path: str, old: Features | None, new: Features | None, mode: str) -> list[Finding]:
    findings: list[Finding] = []
    for category, attr in FEATURE_ATTR.items():
        old_c = getattr(old, attr) if old else Counter()
        new_c = getattr(new, attr) if new else Counter()
        added, removed = counter_diff(old_c, new_c)
        if not added and not removed:
            continue
        severity = POLICY[category][("polish", "structural", "content").index(mode)]
        parts = []
        if added:
            parts.append("added " + ", ".join(short(added)))
        if removed:
            parts.append("removed " + ", ".join(short(removed)))
        findings.append(Finding(path, category, severity, "; ".join(parts)))
    return findings


def short(items: list[str], limit: int = 6) -> list[str]:
    items = [it if len(it) <= 48 else it[:45] + "..." for it in items]
    if len(items) <= limit:
        return items
    return items[:limit] + [f"... (+{len(items) - limit} more)"]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Report read-only-region changes between two revisions of a LaTeX project.",
        epilog="Exit codes: 0 PASS, 2 FAIL, 3 NOT_VERIFIED.",
    )
    ap.add_argument("--base", required=True, help="git ref to compare against")
    ap.add_argument("--target", default=None, help="git ref to compare; default: working tree")
    ap.add_argument("--mode", choices=("polish", "structural", "content"), default="polish")
    ap.add_argument("--fail-on", choices=("risk", "none"), default="risk")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    try:
        paths = changed_files(args.base, args.target)
    except RuntimeError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 3

    findings: list[Finding] = []
    unverified: list[str] = []
    checked: list[str] = []
    skipped: list[str] = []

    for path in paths:
        is_source = path.endswith(SOURCE_SUFFIXES)
        is_config = path in CONFIG_NAMES or path.startswith(CONFIG_PREFIXES)
        if not (is_source or is_config):
            skipped.append(path)
            continue
        if is_config:
            findings.append(Finding(path, "build-config", POLICY["build-config"][
                ("polish", "structural", "content").index(args.mode)],
                "executable configuration changed"))
            checked.append(path)
            continue

        try:
            old_text = read_at(args.base, path)
        except (ValueError, UnicodeDecodeError):
            unverified.append(path + " (base copy is binary or not UTF-8)")
            continue
        try:
            new_text = read_worktree(path) if args.target is None else read_at(args.target, path)
        except (ValueError, UnicodeDecodeError):
            unverified.append(path + " (new copy is binary or not UTF-8)")
            continue

        old_feats = new_feats = None
        if old_text is not None:
            try:
                old_feats = extract(path, old_text)
            except ParseError as exc:
                unverified.append(f"{path} (base: {exc})")
                continue
        if new_text is not None:
            try:
                new_feats = extract(path, new_text)
            except ParseError as exc:
                unverified.append(f"{path} (new: {exc})")
                continue

        checked.append(path)
        for side, feats in (("base", old_feats), ("new", new_feats)):
            if feats and feats.unparsed:
                unverified.append(f"{path} ({side}: {feats.unparsed[0]})")

        # A .bib file contributes citations and a bibliography category.
        if path.endswith(".bib"):
            old_entries = getattr(old_feats, "citations", Counter()) if old_feats else Counter()
            new_entries = getattr(new_feats, "citations", Counter()) if new_feats else Counter()
            added, removed = counter_diff(old_entries, new_entries)
            if added or removed:
                parts = []
                if added:
                    parts.append("added " + ", ".join(short(added)))
                if removed:
                    parts.append("removed " + ", ".join(short(removed)))
                findings.append(Finding(path, "bibliography", POLICY["bibliography"][
                    ("polish", "structural", "content").index(args.mode)], "; ".join(parts)))
            continue

        findings.extend(compare(path, old_feats, new_feats, args.mode))

    blocking = [f for f in findings if f.severity == "risk"]
    if unverified:
        status = "NOT_VERIFIED"
        code = 3
        if blocking:
            status, code = "FAIL", 2
    elif blocking and args.fail_on == "risk":
        status, code = "FAIL", 2
    else:
        status = "PASS"
        code = 0

    if args.format == "json":
        print(json.dumps({
            "status": status,
            "mode": args.mode,
            "base": args.base,
            "target": args.target or "worktree",
            "checked": checked,
            "skipped": skipped,
            "not_verified": unverified,
            "findings": [f.as_dict() for f in findings],
            "not_checked": [
                "scientific correctness",
                "reference accuracy",
                "sentence meaning and ordering",
                "journal style compliance",
            ],
        }, indent=2))
        return code

    target_desc = args.target or "working tree"
    print(f"guardrail: {args.base} -> {target_desc}  (mode: {args.mode})")
    print(f"checked {len(checked)} file(s); skipped {len(skipped)} non-source file(s)")
    for path in skipped:
        print(f"  skipped: {path}")
    if not findings:
        print("no read-only-region change detected in the categories checked")
    for f in findings:
        print(f"  [{f.severity.upper():6}] {f.category:12} {f.path}: {f.detail}")
    if unverified:
        print("could not parse (not covered by this check):")
        for item in unverified:
            print("  " + item)
    print()
    print("categories checked : " + ", ".join(CATEGORY_ORDER))
    print("NOT checked        : scientific correctness, reference accuracy, "
          "sentence meaning, journal style")
    print(f"GUARDRAIL: {status}")
    return code


if __name__ == "__main__":
    sys.exit(main())
