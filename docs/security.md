# Security model and residual risk

This file states what is defended, what is not, and what would be dishonest to
claim. It is deliberately short on reassurance.

## 1. The build is code execution

`latexmk` reads `.latexmkrc`, which is **Perl**. That file can call `system()`,
read files and open sockets with the permissions of whoever ran the build. A
real example is in the wild: `paperops`' exported Overleaf `.latexmkrc` defines
`glo2gls`, `rtex_to_tex`, `mf_to_tfm`, `asy`, `mpost` and a `chktex` hook, each
of which shells out to another program.

**Rule:** never run `latexmk` in a checkout whose `.latexmkrc` you have not read.
An agent that is asked to "just build it" on a downloaded project must read the
config first and say so.

## 2. `-shell-escape`

Disabled here: `.latexmkrc` sets no `$latexmk_shell_escape`, and the CI action's
`latexmk_shell_escape` is left at its default `false`.

That closes one door. It does **not** make an untrusted document safe:

- `\input`/`\include` can read files outside the project directory and print
  them into the PDF.
- Some packages read arbitrary local files without shell escape.
- A resource-exhaustion document (deep recursion, huge `\loop`) can still take
  the build down.
- `.latexmkrc`, `Makefile`, `pre_compile`, `post_compile` and any wrapper script
  are unaffected by the flag entirely.

Write “reduced the attack surface”, never “safe”.

## 3. CI

`.github/workflows/latex.yml`:

| Property | Setting | Why |
|---|---|---|
| Trigger | `push` to `main` / `agent/**`, `pull_request` to `main`, manual | routine builds stay on trusted refs |
| Fork PRs | **skipped** (`if:` on head repo, plus an explicit failing step) | a fork's `.latexmkrc` is arbitrary Perl written by a stranger |
| Token | `permissions: contents: read` | nothing here needs to write |
| Secrets | none | there is no secret to protect or leak |
| Checkout | `persist-credentials: false` | the token is not left in `.git/config` for later steps |
| Shell escape | off | see §2 |
| Action pinning | `xl`/`xu-cheng/latex-action` pinned to `6549dc2…` (4.1.0); `checkout` and `upload-artifact` pinned to commit SHAs | a moved tag would silently change what runs |
| TeX Live | `texlive_version: 2025` | reproducible engine, and it is the version tested locally |
| Network | the build container can reach the network | **not** restricted; a malicious class file could phone home |

Consequence: an external contributor cannot get CI to run their code. A
maintainer who wants to test a fork must copy the branch into this repository
first, which makes the trust decision explicit and visible in the log.

## 4. Archives

`tools/zip_inspect.py` reads the ZIP central directory **without extracting** and
reports: path traversal, absolute paths, symlinks (`external_attr` mode
`0o120000`), case collisions, expansion bombs, executable build config,
credential-looking filenames and non-UTF-8 names.

What it cannot do: see inside an encrypted archive, judge whether a `.tex` file
is malicious, or decide that a clean-looking project is safe. A `CLEAN` result
means “none of the listed hazards are present”, nothing more.

## 5. What goes into a public repository

`tools/publish_audit.py` scans the working tree **and the git history** for
personal email addresses, home-directory paths, private-key blocks, provider
tokens, credential-looking assignments, forbidden filenames and an optional
deny list of literal strings (real names, institutions).

A file deleted in a later commit is still in the history that gets pushed. The
audit therefore reads history, not just `HEAD`. If something sensitive is found
there, the only remedy is to rewrite the history before the first push — which
is why the audit runs before the repository is created, not after.

Limits: it matches shapes. It cannot tell that a paragraph identifies a person,
and it does not check third-party licence compatibility.

## 6. What this project asks of an agent

From `AGENTS.md` §9–§10, in short: no push, no publish, no release, no force
push, no history rewrite, no branch deletion without the author's explicit
words; never commit credentials or another person's manuscript; never import an
archive by extracting it.

These are instructions, not sandboxes. An agent with shell access can ignore
them. The guardrail and the publication audit exist so that the *common*
mistakes are caught mechanically, and the protocol exists so that the remaining
ones are the author's decision.
