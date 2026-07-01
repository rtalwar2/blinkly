#!/usr/bin/env bash
# Launch Blinkly from its virtual environment.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x ".venv/bin/python" ]; then
  echo "Virtual environment not found. Run ./install.sh first." >&2
  exit 1
fi

exec .venv/bin/python blinkly.py "$@"
