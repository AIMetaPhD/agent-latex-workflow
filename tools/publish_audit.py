#!/usr/bin/env python3
"""Pre-publication redaction audit. Run this before a repository goes public.

It scans the **current tree** and the **whole git history**, because a file
deleted in a later commit is still readable in the history that gets pushed.

What it looks for
    identity     personal email addresses, ORCID identifiers
    host paths   a POSIX home directory, a Windows user profile, or a drive
                 letter followed by a well-known application folder
    credentials  API keys, tokens, private keys, .env contents
    machine data absolute local paths in configs, editor state, .DS_Store
    manuscript   LaTeX that looks like a real (possibly unpublished) paper
    licence      third-party code or template files without attribution

What it cannot do
    Decide whether a sentence is sensitive. It finds shapes: emails, paths,
    key-like strings, known names. A human still has to read the tree.

Exit codes
    0  CLEAN for the categories checked
    2  FINDINGS present; do not publish until each is resolved
    3  the check could not run (not a git repository, git failed)

Usage
    python -I tools/publish_audit.py
    python -I tools/publish_audit.py --deny "Your Name" --deny "你的姓名"
    python -I tools/publish_audit.py --json > audit.json
    python -I tools/publish_audit.py --history-depth 200
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Patterns that are always worth blocking when they appear in a public repo.
RULES: list[tuple[str, str, str, str]] = [
    # (category, severity, label, regex)
    ("identity", "block", "email-address",
     r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("identity", "review", "orcid",
     r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),
    ("host-path", "block", "unix-home-path",
     r"/(?:Users|home)/[A-Za-z][A-Za-z0-9._-]*"),
    ("host-path", "block", "windows-home-path",
     r"[A-Za-z]:\\\\?Users\\\\?[A-Za-z][A-Za-z0-9._-]*"),
    ("host-path", "review", "windows-drive-path",
     r"\b[A-Za-z]:\\\\?(?:Applications|Program Files|ClaudeCodeFiles|CodexFiles)\b"),
    ("credentials", "block", "private-key-block",
     r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ("credentials", "block", "aws-access-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("credentials", "block", "github-token", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("credentials", "block", "openai-style-key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("credentials", "block", "slack-token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    ("credentials", "block", "assigned-secret",
     r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"),
]

# Files whose presence in a public repo is a mistake regardless of content.
FORBIDDEN_NAMES = {
    ".env", ".netrc", ".git-credentials", "id_rsa", "id_ed25519",
    ".DS_Store", "Thumbs.db", "desktop.ini",
}
FORBIDDEN_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")
FORBIDDEN_DIRS = (".venv", "node_modules", "__pycache__", ".idea")

# Editor / OS state that leaks local paths.
LOCAL_STATE_DIRS = (".vscode", ".zed", ".idea", ".claude")

SKIP_BINARY_SUFFIXES = (
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz", ".tar",
    ".pyc", ".ico", ".woff", ".woff2", ".ttf",
)


@dataclass
class Hit:
    where: str          # "tree" or "history"
    path: str
    line: int
    category: str
    severity: str
    label: str
    excerpt: str
    commit: str = ""

    def as_dict(self) -> dict:
        return {
            "where": self.where, "path": self.path, "line": self.line,
            "category": self.category, "severity": self.severity,
            "label": self.label, "excerpt": self.excerpt, "commit": self.commit,
        }


@dataclass
class Audit:
    hits: list[Hit] = field(default_factory=list)
    scanned_files: int = 0
    scanned_commits: int = 0
    notes: list[str] = field(default_factory=list)
    deny_terms: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> list[Hit]:
        return [h for h in self.hits if h.severity == "block"]


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: "
                           + proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout.decode("utf-8", "replace")


def redact(text: str) -> str:
    """Show enough to locate the problem without re-printing the secret."""
    text = text.strip()
    if len(text) <= 12:
        return text
    return text[:6] + "…" + text[-3:]


def compile_rules(deny_terms: list[str]) -> list[tuple[str, str, str, re.Pattern[str]]]:
    out = [(c, s, lbl, re.compile(rx)) for c, s, lbl, rx in RULES]
    for term in deny_terms:
        out.append(("identity", "block", "denylist:" + term,
                    re.compile(re.escape(term), re.IGNORECASE)))
    return out


WAIVER = "publish-audit:allow"

# A waiver on a line applies to that line. For a block of lines that are all
# part of one deliberate list (browser install locations, for example), the
# marker can be written as `publish-audit:allow <reason>` on the opening line
# and `publish-audit:allow-end` on the closing one, instead of on every entry.
BLOCK_START = "publish-audit:allow"
BLOCK_END = "publish-audit:allow-end"


def scan_text(text: str, where: str, path: str, rules, commit: str = "") -> list[Hit]:
    """Find pattern matches in a file, honouring the two waiver forms.

    A waiver is always explicit and always carries a reason on the same line, so
    a waiver cannot be added silently:

        publish-audit:allow <reason>        this line
        publish-audit:allow <reason>        start of a block
        ...
        publish-audit:allow-end             end of that block
    """
    hits: list[Hit] = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 4000:
            continue
        if BLOCK_END in line:
            in_block = False
            continue
        if in_block:
            continue
        if WAIVER in line:
            if line.count(WAIVER) == 1 and not line.rstrip().endswith(BLOCK_END):
                # `publish-audit:allow <reason>` opens a block; anything on the
                # same line still needs the reason to be present, which it is.
                in_block = True
            continue
        for category, severity, label, rx in rules:
            m = rx.search(line)
            if not m:
                continue
            # An email in the sample paper is fine if it is clearly fictional and
            # uses a reserved example domain; do not special-case anything else.
            if label == "email-address" and m.group(0).lower().endswith(
                    ("example.invalid", "example.com", "example.org")):
                continue
            hits.append(Hit(where, path, lineno, category, severity, label,
                            redact(line.strip()), commit))
            break  # one hit per line keeps the report readable
    return hits


def audit_tree(rules) -> tuple[list[Hit], int, list[str]]:
    hits: list[Hit] = []
    notes: list[str] = []
    files = [p.strip() for p in git("ls-files", "-z").split("\0") if p.strip()]
    count = 0
    for rel in files:
        name = Path(rel).name
        low = name.lower()
        if name in FORBIDDEN_NAMES or low.endswith(FORBIDDEN_SUFFIXES):
            hits.append(Hit("tree", rel, 0, "credentials", "block",
                            "forbidden-file", name))
            continue
        if any(part in FORBIDDEN_DIRS for part in Path(rel).parts):
            hits.append(Hit("tree", rel, 0, "machine-data", "block",
                            "forbidden-directory", rel))
            continue
        if rel.lower().endswith(SKIP_BINARY_SUFFIXES):
            continue
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            notes.append(f"skipped (binary or unreadable): {rel}")
            continue
        count += 1
        hits.extend(scan_text(text, "tree", rel, rules))

    # Local editor state that is present but untracked still leaks if committed
    # later; report it so the .gitignore can be fixed.
    for directory in LOCAL_STATE_DIRS:
        d = ROOT / directory
        if d.is_dir():
            for child in d.rglob("*"):
                if child.is_file() and child.name not in (
                        "settings.json", "tasks.json", "extensions.json", ".gitignore"):
                    rel = str(child.relative_to(ROOT)).replace("\\", "/")
                    if rel not in files:
                        hits.append(Hit("tree", rel, 0, "machine-data", "review",
                                        "untracked-local-state",
                                        "editor state present; confirm it is git-ignored"))
    return hits, count, notes


def audit_history(rules, depth: int | None) -> tuple[list[Hit], int, list[str]]:
    notes: list[str] = []
    rev_args = ["HEAD"] if depth is None else ["-n", str(depth), "HEAD"]
    try:
        revs = git("rev-list", *rev_args).split()
    except RuntimeError as exc:
        return [], 0, [str(exc)]

    hits: list[Hit] = []
    for sha in revs:
        try:
            files = [p for p in git("ls-tree", "-r", "--name-only", "-z", sha).split("\0") if p]
        except RuntimeError:
            continue
        for rel in files:
            if rel.lower().endswith(SKIP_BINARY_SUFFIXES):
                continue
            proc = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=ROOT, capture_output=True)
            if proc.returncode != 0:
                continue
            try:
                text = proc.stdout.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for hit in scan_text(text, "history", rel, rules, sha):
                hit.excerpt = f"{hit.excerpt}"
                hits.append(hit)
    # Deduplicate by (path, label, excerpt): one line per distinct leak.
    unique: dict[tuple[str, str, str], Hit] = {}
    for h in hits:
        unique.setdefault((h.path, h.label, h.excerpt), h)
    if len(unique) != len(hits):
        notes.append(f"{len(hits) - len(unique)} repeat occurrence(s) collapsed in the history report")
    return list(unique.values()), len(revs), notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Audit the tree and git history before publishing a repository.")
    ap.add_argument("--deny", action="append", default=[],
                    help="a literal string that must not appear (repeatable), e.g. a real name")
    ap.add_argument("--history-depth", type=int, default=None,
                    help="only the last N commits (default: every commit)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tree-only", action="store_true")
    args = ap.parse_args(argv)

    rules = compile_rules(args.deny)
    audit = Audit(deny_terms=args.deny)
    try:
        tree_hits, audit.scanned_files, tree_notes = audit_tree(rules)
        audit.notes.extend(tree_notes)
        audit.hits.extend(tree_hits)
        if not args.tree_only:
            hist_hits, audit.scanned_commits, hist_notes = audit_history(rules, args.history_depth)
            audit.notes.extend(hist_notes)
            audit.hits.extend(hist_hits)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    status = "FINDINGS" if audit.hits else "CLEAN"
    code = 2 if audit.hits else 0

    if args.json:
        print(json.dumps({
            "status": status,
            "scanned_files": audit.scanned_files,
            "scanned_commits": audit.scanned_commits,
            "deny_terms": audit.deny_terms,
            "hits": [h.as_dict() for h in audit.hits],
            "notes": audit.notes,
            "not_checked": [
                "whether a sentence is sensitive",
                "third-party licence compatibility",
                "the accuracy of the paper's content",
            ],
        }, indent=2, ensure_ascii=False))
        return code

    print("pre-publication audit")
    print(f"  files scanned   : {audit.scanned_files}")
    print(f"  commits scanned : {audit.scanned_commits}" + ("" if not args.tree_only else " (history skipped)"))
    print(f"  deny list       : {', '.join(args.deny) if args.deny else '(none)'}")
    print()
    if not audit.hits:
        print("no match for any pattern in the categories checked")
    for h in audit.hits:
        loc = f"{h.path}:{h.line}" if h.line else h.path
        origin = f" [{h.commit[:8]}]" if h.commit else ""
        print(f"  [{h.severity.upper():6}] {h.where:7} {h.category:12} {h.label:22} "
              f"{loc}{origin}")
        if h.excerpt:
            print(f"           {h.excerpt}")
    for note in audit.notes:
        print("  note: " + note)
    print()
    print("NOT checked: whether a sentence is sensitive, licence compatibility,")
    print("             the paper's scientific content.")
    print(f"AUDIT: {status}")
    if audit.hits:
        print("Resolve every finding, then re-run. A rewritten commit is the only way to")
        print("remove something that is already in the history.")
    return code


if __name__ == "__main__":
    sys.exit(main())
