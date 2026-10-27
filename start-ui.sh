#!/usr/bin/env bash
# Launch the Local Companion UI on Linux.
# Resolves the project root from this script's location, not the current
# directory.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  cat >&2 <<'EOF'

  Python 3.10 or newer was not found.

  Install it with one of these, then run this script again:
      sudo apt install python3          # Debian/Ubuntu
      sudo dnf install python3          # Fedora
      https://www.python.org/downloads/

EOF
  exit 1
fi

echo "Starting the paper workbench from $ROOT ..."
exec "$PY" "$ROOT/ui/server.py" "$@"
