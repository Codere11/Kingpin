"""schema.py -- the save contract, its version, and its migrations.

A save is a plain-data document, not a pickled object graph.  Every change to
the shape of that document bumps SCHEMA_VERSION and gets a migration, so an
old file is either brought forward deliberately or refused with a clear log
line -- never silently half-read.

WORLD_VERSION is separate and belongs to the generated world.  It changes when
the layout rules change (camp spacing, field sizes, camp contents).  A save
whose world was laid out by different rules is refused: the state in it is
keyed by positions that no longer mean the same thing.
"""

from __future__ import annotations

FORMAT = "settlewest-save"

# The state document.  Bump for any change to a key's meaning or shape.
SCHEMA_VERSION = 2

# The generated world's layout contract.  Bump when native.build / world
# geometry changes enough that saved positions would point at different ground.
WORLD_VERSION = 3

GAME_VERSION = "settlewest-1"


class SaveError(Exception):
    """A save could not be read, or is not a save this build can use."""


def _migrate_1_to_2(manifest: dict) -> dict:
    """Schema 2 adds NPC mind fields and built-object condition.

    The fields are additive and every reader has a class default, so there is
    no data to rewrite here.  The version bump records that a writer from this
    build may include them.
    """
    out = dict(manifest)
    out["schema"] = 2
    return out


_MIGRATIONS: dict[int, object] = {
    1: _migrate_1_to_2,
}


def migrate(manifest: dict) -> dict:
    """Bring a manifest up to SCHEMA_VERSION, one version at a time."""
    version = int(manifest.get("schema", 0))
    if version == SCHEMA_VERSION:
        return manifest
    if version > SCHEMA_VERSION:
        raise SaveError(
            "save is from a newer build (schema %d, this build reads %d)"
            % (version, SCHEMA_VERSION))
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SaveError("no migration from save schema %d" % version)
        manifest = step(manifest)
        version = int(manifest.get("schema", version + 1))
    return manifest


def validate(manifest: dict) -> None:
    if not isinstance(manifest, dict):
        raise SaveError("save manifest is not a dictionary")
    if manifest.get("format") != FORMAT:
        raise SaveError("not a SettleWest save (format %r)"
                        % (manifest.get("format"),))
    if int(manifest.get("world_version", -1)) != WORLD_VERSION:
        raise SaveError(
            "save world layout v%s does not match this build's v%d"
            % (manifest.get("world_version"), WORLD_VERSION))
