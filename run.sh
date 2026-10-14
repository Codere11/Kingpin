#!/usr/bin/env bash
#
# Run Kingpin straight from source -- no build, starts in about a second.
# Use this while iterating; only run ./build.sh when you want the standalone app.
#
set -euo pipefail
cd "$(dirname "$0")"

VENV="${KINGPIN_VENV:-/tmp/kingpin-venv}"
if [ ! -x "$VENV/bin/python" ]; then
    echo "Setting up $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" -q install pygame-ce numpy
fi
exec "$VENV/bin/python" main.py
