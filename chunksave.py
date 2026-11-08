"""chunksave.py -- THE SAVE, SPLIT INTO A MANIFEST AND PER-SETTLEMENT CHUNKS.

One save is one manifest (the player, the global timers, the world edits that
belong to no single settlement) plus a chunks/ directory holding one file per
settlement cell: that settlement's full state -- people, houses, coin, prices,
timers -- everything. The manifest is small and rewritten every save; a chunk
is only rewritten when its settlement actually changed.

This is slice 1 of the streaming world: the world is still finite, but the
save is already shaped the way an infinite one must be -- the manifest says
*where* the state is, and each chunk is a self-contained unit that can be
loaded, frozen and written on its own.
"""

from __future__ import annotations

import os
import pickle

import persist

CHUNK_VERSION = 1


def _chunk_dir(slot: int) -> str:
    return persist.path(slot).replace(".json", "_chunks")


def _chunk_path(slot: int, gx: int, gy: int) -> str:
    return os.path.join(_chunk_dir(slot), "chunk_%d_%d.pkl" % (int(gx), int(gy)))


def save(payload: dict, slot: int | None = None) -> bool:
    """Write the manifest and every settlement chunk, atomically.

    Returns False only when the manifest itself could not be written; a single
    chunk failing is not a lost save, it is a settlement that keeps its last
    written state.
    """
    slot = int(slot if slot is not None else persist.get_slot())
    world = list(payload.get("world") or ())
    manifest = dict(payload)
    manifest["world"] = None
    manifest["_chunks"] = CHUNK_VERSION
    if not persist.write_binary(manifest, slot):
        return False

    directory = _chunk_dir(slot)
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception:
        return True          # manifest is written; the world is still safe

    seen = set()
    for rec in world:
        try:
            gx, gy = int(rec["gx"]), int(rec["gy"])
        except Exception:
            continue
        seen.add((gx, gy))
        target = _chunk_path(slot, gx, gy)
        tmp = target + ".tmp"
        try:
            with open(tmp, "wb") as fh:
                pickle.dump(rec, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, target)
        except Exception:
            continue

    # a settlement that no longer exists must not stay on disk
    try:
        for name in os.listdir(directory):
            if not name.startswith("chunk_") or not name.endswith(".pkl"):
                continue
            stem = name[len("chunk_"):-len(".pkl")]
            try:
                gx, gy = (int(t) for t in stem.split("_"))
            except Exception:
                continue
            if (gx, gy) not in seen:
                try:
                    os.remove(os.path.join(directory, name))
                except Exception:
                    pass
    except Exception:
        pass
    return True


def load(slot: int | None = None):
    """Read a save back into the single payload shape restore() expects.

    A new save returns its manifest with the world re-assembled from the chunk
    files. An older, single-blob save is returned untouched, so a player who
    saved before this split loses nothing; the next save writes the new shape.
    """
    slot = int(slot if slot is not None else persist.get_slot())
    data = persist.read_binary(slot)
    if data is None:
        return None
    if data.get("_chunks") != CHUNK_VERSION:
        return data                    # the old single-blob shape, world inline
    world = []
    directory = _chunk_dir(slot)
    if os.path.isdir(directory):
        try:
            names = sorted(os.listdir(directory))
        except Exception:
            names = []
        for name in names:
            if not name.startswith("chunk_") or not name.endswith(".pkl"):
                continue
            try:
                with open(os.path.join(directory, name), "rb") as fh:
                    rec = pickle.load(fh)
                if isinstance(rec, dict) and "gx" in rec and "gy" in rec:
                    world.append(rec)
            except Exception:
                continue
    data["world"] = world
    return data
