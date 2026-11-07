#!/usr/bin/env bash
#
# Build the standalone GetWorld app. Fast rebuilds.
#
#   ./build.sh
#
# Speed choices:
#   * --onedir instead of --onefile. Onefile re-compresses the whole ~120 MB
#     bundle on every build, which is the slow part. Onedir just links files.
#   * The PyInstaller work directory and dist directory live in /tmp, so they
#     persist between builds and act as a cache, and the project stays clean.
#   * No --collect-all pygame: PyInstaller's pygame hook already bundles the
#     SDL libraries, so collecting the entire package is wasted time.
#   * The venv is reused; pip is a no-op when everything is already installed.
#
set -euo pipefail

cd "$(dirname "$0")"

VENV="${KINGPIN_VENV:-$HOME/.kingpin-buildenv}"
WORK="${KINGPIN_BUILD:-$HOME/.kingpin-build}"
DIST="$HOME/.kingpin-dist"
PYTHON="${PYTHON:-python3}"

if [ ! -x "$VENV/bin/python" ]; then
    echo "Creating build venv at $VENV"
    "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" -q install pygame-ce numpy pyinstaller cython

echo "Compiling hot modules..."
# Cython compiles village.py, economy.py and skills.py to C extensions, and
# village.pxd / economy.pxd are what makes it worth doing: they declare the
# man's fields as C struct members and type economy.needs(npc) so that every
# npc.hunger inside it is a struct read instead of a dictionary lookup.
# Measured 80.2 -> 61.0 ms p50. If it fails the game still runs as plain
# Python -- just slower -- so a compile failure must not break the build.
if ! "$VENV/bin/cythonize" -i -3 village.py economy.py skills.py > /tmp/kingpin-cython.log 2>&1; then
    echo "  CYTHONIZE FAILED. The compiled modules would be STALE and would"
    echo "  silently shadow the .py files -- every change to village.py,"
    echo "  economy.py or skills.py would be ignored by the game. Refusing."
    tail -5 /tmp/kingpin-cython.log
    exit 1
    tail -5 /tmp/kingpin-cython.log
fi

echo "Building..."
rm -rf "$DIST" GetWorld.spec __pycache__

"$VENV/bin/pyinstaller" \
    --noconfirm \
    --onedir \
    --windowed \
    --name GetWorld \
    --workpath "$WORK" \
    --specpath "$WORK" \
    --distpath "$DIST" \
    --exclude-module tkinter \
    --exclude-module unittest \
    --exclude-module pydoc \
    --exclude-module doctest \
    main.py 2>&1 | tail -1

# Executable at the top level, with its runtime bundle next to it.
rm -rf _internal
mv "$DIST/GetWorld/GetWorld" ./GetWorld
mv "$DIST/GetWorld/_internal" ./_internal
rm -rf "$DIST"

echo "Built $(pwd)/GetWorld"
