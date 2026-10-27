#!/usr/bin/env bash
# Launch the Local Companion UI on macOS by double-clicking this file.
# Resolves the project root from this script's location.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done

fail() {
  cat >&2 <<EOF

  $1

  Install Python 3.10 or newer, then double-click this file again:
      brew install python
      https://www.python.org/downloads/

EOF
  # Keep the Terminal window open so the message is readable.
  read -r -p "  Press Return to close this window. " _ || true
  exit 1
}

[ -n "$PY" ] || fail "Python 3.10 or newer was not found."

echo "Starting the paper workbench from $ROOT ..."
"$PY" "$ROOT/ui/server.py" "$@" || fail "The workbench stopped with an error (see above)."
