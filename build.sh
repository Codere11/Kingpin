#!/usr/bin/env bash
#
# Build the standalone SettleWest app. Fast rebuilds.
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

# THE SAVE ROUND-TRIP IS PART OF THE BUILD.  A save that writes a file but
# does not bring the world back is worse than no save at all, so the build
# refuses to produce an executable that cannot save and load itself.
echo "Checking the save round-trip..."
"$VENV/bin/python" tools/save_selftest.py make > /tmp/kingpin-save-make.log 2>&1 || { echo "  SAVE SELFTEST (make) FAILED"; tail -20 /tmp/kingpin-save-make.log; exit 1; }
"$VENV/bin/python" tools/save_selftest.py verify > /tmp/kingpin-save-verify.log 2>&1 || { echo "  SAVE SELFTEST (verify) FAILED"; tail -20 /tmp/kingpin-save-verify.log; exit 1; }

# THE NPC FOUNDATION IS PURE AND FAST TO CHECK.  If the type table, the job
# multipliers or the mood arithmetic drift, fail before spending a build.
echo "Checking persona and mood..."
"$VENV/bin/python" tools/persona_selftest.py > /tmp/kingpin-persona.log 2>&1 || { echo "  PERSONA SELFTEST FAILED"; tail -20 /tmp/kingpin-persona.log; exit 1; }
"$VENV/bin/python" tools/player_selftest.py > /tmp/kingpin-player.log 2>&1 || { echo "  PLAYER MIND SELFTEST FAILED"; tail -20 /tmp/kingpin-player.log; exit 1; }
"$VENV/bin/python" tools/relationships_selftest.py > /tmp/kingpin-rel.log 2>&1 || { echo "  RELATIONSHIPS SELFTEST FAILED"; tail -20 /tmp/kingpin-rel.log; exit 1; }
"$VENV/bin/python" tools/trader_selftest.py > /tmp/kingpin-trader.log 2>&1 || { echo "  TRADER SELFTEST FAILED"; tail -20 /tmp/kingpin-trader.log; exit 1; }
"$VENV/bin/python" tools/card_selftest.py > /tmp/kingpin-card.log 2>&1 || { echo "  CARD SELFTEST FAILED"; tail -20 /tmp/kingpin-card.log; exit 1; }
"$VENV/bin/python" tools/doctor_selftest.py > /tmp/kingpin-doctor.log 2>&1 || { echo "  DOCTOR SELFTEST FAILED"; tail -20 /tmp/kingpin-doctor.log; exit 1; }
"$VENV/bin/python" tools/major_break_selftest.py > /tmp/kingpin-major-break.log 2>&1 || { echo "  MAJOR BREAK SELFTEST FAILED"; tail -20 /tmp/kingpin-major-break.log; exit 1; }

echo "Building..."
rm -rf "$DIST" SettleWest.spec __pycache__

# Bundle every PNG asset beside the executable, absolute so PyInstaller's
# workpath/specpath never shadows the glob.
DATA_ARGS=()
for _png in *.png; do
    [ -e "$_png" ] && DATA_ARGS+=(--add-data "$PWD/$_png:.")
done
# AND EVERY SOUND EFFECT, into its own Sounds/ folder inside the bundle.
for _snd in Sounds/*.ogg; do
    [ -e "$_snd" ] && DATA_ARGS+=(--add-data "$PWD/$_snd:Sounds")
done

"$VENV/bin/pyinstaller" \
    --noconfirm \
    --onedir \
    --windowed \
    --name SettleWest \
    --workpath "$WORK" \
    --specpath "$WORK" \
    --distpath "$DIST" \
    --exclude-module tkinter \
    --exclude-module unittest \
    --exclude-module pydoc \
    --exclude-module doctest \
    --hidden-import persona \
    --hidden-import mood \
    --hidden-import doctor \
    --hidden-import needs \
    --hidden-import incidents \
    --hidden-import relationships \
    --hidden-import playlog \
    --hidden-import social_life \
    --hidden-import events \
    --hidden-import wind \
    --hidden-import conversation \
    --hidden-import antics \
    --hidden-import wolfart \
    --hidden-import rabbitart \
    --hidden-import horseart \
    --hidden-import bisonart \
    "${DATA_ARGS[@]}" \
    main.py 2>&1 | tail -1

# Executable at the top level, with its runtime bundle next to it.
rm -rf _internal
mv "$DIST/SettleWest/SettleWest" ./SettleWest
mv "$DIST/SettleWest/_internal" ./_internal
rm -rf "$DIST"

echo "Built $(pwd)/SettleWest"
