"""store.py -- the save on disk: one manifest, many gzip chunks.

Layout::

    saves/slot_0/
        save.json            small, atomic, checksummed manifest
        save.prev.json       the manifest that was replaced last time
        new_game.json        the seed chosen at the title screen, before play
        chunks/
            built.json
            animals.json
            camps/<camp uid>.json
            terrain/<region>.json

Chunks are written first and the manifest last, so a crash halfway through
leaves the previous manifest (and its chunks) intact.  A chunk whose bytes did
not change is not rewritten: the manifest carries its hash, and the store
compares before touching the disk.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import time

import persist
from . import codec
from .schema import FORMAT, SCHEMA_VERSION, SaveError, migrate, validate

SLOTS = persist.SLOTS


def base_dir() -> str:
    return persist.DIR_TEST if persist.is_test() else persist.DIR


def slot_dir(slot: int) -> str:
    return os.path.join(base_dir(), "slot_%d" % int(slot))


def manifest_path(slot: int) -> str:
    return os.path.join(slot_dir(slot), "save.json")


def previous_path(slot: int) -> str:
    return os.path.join(slot_dir(slot), "save.prev.json")


def new_game_path(slot: int) -> str:
    return os.path.join(slot_dir(slot), "new_game.json")


def log_path() -> str:
    return os.path.join(base_dir(), "save.log")


def chunk_path(slot: int, rel: str) -> str:
    return os.path.join(slot_dir(slot), "chunks", *rel.split("/"))


def log(text: str) -> None:
    try:
        os.makedirs(base_dir(), exist_ok=True)
        with open(log_path(), "a") as fh:
            fh.write("%s  %s\n"
                     % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      default=codec.json_default).encode("utf-8")


def _checksum(body: dict) -> str:
    return hashlib.sha1(_canonical(body)).hexdigest()


def _write_atomic(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _write_json(path: str, obj) -> None:
    _write_atomic(path, (json.dumps(obj, indent=1, sort_keys=True,
                                    default=codec.json_default)
                         + "\n").encode("utf-8"))


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_manifest_raw(slot: int):
    path = manifest_path(slot)
    if not os.path.exists(path):
        return None
    try:
        doc = _read_json(path)
    except Exception as exc:
        raise SaveError("save manifest is unreadable: %r" % (exc,))
    if not isinstance(doc, dict):
        raise SaveError("save manifest is not a dictionary")
    return doc


# -- legacy -----------------------------------------------------------------
_MIGRATED: set[str] = set()


def migrate_legacy() -> None:
    """Move the pre-rewrite save system's files out of the way, once.

    The old format wrote a pickle into save_0.json and kept per-village
    chunks and world caches beside it.  None of it can be read by this build,
    and leaving it in saves/ makes a *new* save look like a *broken* one.  It
    is moved, not deleted, to saves/_legacy/ so it can still be recovered.
    """
    root = base_dir()
    if root in _MIGRATED:
        return
    _MIGRATED.add(root)
    legacy = os.path.join(root, "_legacy")
    try:
        os.makedirs(legacy, exist_ok=True)
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isdir(path):
                if (name.startswith("save_") and name.endswith("_chunks")):
                    try:
                        shutil.move(path, os.path.join(legacy, name))
                        log("legacy: moved %s" % name)
                    except Exception:
                        pass
                continue
            if name.startswith("world_") and name.endswith(".pkl"):
                pass
            elif name.startswith("save_") and name.endswith(".json"):
                pass
            else:
                continue
            try:
                shutil.move(path, os.path.join(legacy, name))
                log("legacy: moved %s" % name)
            except Exception:
                pass
    except Exception:
        pass


# -- manifest ---------------------------------------------------------------
def load_manifest(slot: int) -> dict | None:
    """Read and verify the manifest.  None means the slot is empty."""
    migrate_legacy()
    doc = _read_manifest_raw(slot)
    if doc is None:
        return None
    if doc.get("format") != FORMAT:
        # The old format is deliberately dropped.  Treat the slot as empty so
        # a new game can be started; never try to half-read it.
        log("slot %d holds an old save (dropped)" % int(slot))
        return None
    stored = doc.get("checksum")
    body = dict(doc)
    body.pop("checksum", None)
    if stored and stored != _checksum(body):
        raise SaveError("save checksum mismatch -- file is damaged")
    doc = migrate(doc)
    validate(doc)
    return doc


def read_manifest_quiet(slot: int) -> dict | None:
    """For the menu: never raise over a bad slot, just show it as empty."""
    try:
        return load_manifest(slot)
    except Exception as exc:
        log("summary: slot %d unreadable: %r" % (int(slot), exc))
        return None


def write_manifest(slot: int, manifest: dict) -> None:
    body = dict(manifest)
    body.pop("checksum", None)
    body["checksum"] = _checksum(body)
    path = manifest_path(slot)
    old = previous_path(slot)
    if os.path.exists(path):
        try:
            shutil.copy2(path, old)
        except Exception:
            pass
    _write_json(path, body)


# -- chunks -----------------------------------------------------------------
def write_chunks(slot: int, chunks: dict[str, object],
                 previous: dict | None, generation: int) -> dict:
    """Write changed chunks into this save generation; reuse unchanged paths.

    A chunk is identified by its logical name (``built.json``).  If its bytes
    match the previous manifest's hash, the new manifest points at the SAME
    file, so nothing is rewritten.  If they differ, the new bytes go to a new
    path under ``g<generation>/``.  The old manifest keeps pointing at the old
    file until the new manifest is safely on disk; that is what makes a crash
    between the two harmless.
    """
    prev_table = (previous or {}).get("chunks") or {}
    table: dict[str, dict] = {}
    for logical in sorted(chunks):
        data = chunks[logical]
        raw = _canonical(data)
        digest = hashlib.sha1(raw).hexdigest()
        old = prev_table.get(logical) or {}
        old_path = old.get("path")
        if (old.get("sha1") == digest and old_path
                and os.path.exists(chunk_path(slot, old_path))):
            table[logical] = {"path": old_path, "sha1": digest,
                              "size": old.get("size")}
            continue
        rel = "g%d/%s" % (int(generation), logical)
        blob = gzip.compress(raw, compresslevel=6, mtime=0)
        _write_atomic(chunk_path(slot, rel), blob)
        table[logical] = {"path": rel, "sha1": digest, "size": len(blob)}
    return table

def _clean_chunks(slot: int, table: dict, previous_table: dict) -> None:
    """Remove chunk files no longer referenced by this save or its predecessor."""
    directory = os.path.join(slot_dir(slot), "chunks")
    if not os.path.isdir(directory):
        return
    keep = set()
    for source in (table, previous_table):
        for meta in (source or {}).values():
            path = (meta or {}).get("path")
            if path:
                keep.add(os.path.normpath(chunk_path(slot, path)))
    for root, _dirs, names in os.walk(directory):
        for name in names:
            if name.endswith(".tmp"):
                continue
            path = os.path.normpath(os.path.join(root, name))
            if path not in keep:
                try:
                    os.remove(path)
                except Exception:
                    pass


def _clean_empty_dirs(slot: int) -> None:
    directory = os.path.join(slot_dir(slot), "chunks")
    if not os.path.isdir(directory):
        return
    for root, dirs, names in os.walk(directory, topdown=False):
        if root == directory:
            continue
        if not dirs and not names:
            try:
                os.rmdir(root)
            except Exception:
                pass

def read_chunks(slot: int, manifest: dict) -> dict[str, object]:
    out: dict[str, object] = {}
    for logical, meta in (manifest.get("chunks") or {}).items():
        rel = (meta or {}).get("path") or logical
        path = chunk_path(slot, rel)
        try:
            with gzip.open(path, "rb") as fh:
                raw = fh.read()
        except Exception as exc:
            raise SaveError("missing save chunk %s: %r" % (logical, exc))
        digest = hashlib.sha1(raw).hexdigest()
        if meta.get("sha1") and digest != meta["sha1"]:
            raise SaveError("save chunk %s is damaged" % logical)
        try:
            out[logical] = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise SaveError("save chunk %s is unreadable: %r" % (logical, exc))
    return out


# -- public -----------------------------------------------------------------
def exists(slot: int) -> bool:
    return (os.path.exists(manifest_path(slot))
            or os.path.exists(new_game_path(slot)))


def new_game(slot: int, seed: int) -> None:
    os.makedirs(slot_dir(slot), exist_ok=True)
    _write_json(new_game_path(slot), {"seed": int(seed)})


def initial_seed(slot: int) -> int:
    """The seed for a world that is about to be built."""
    try:
        doc = load_manifest(slot)
        if doc is not None:
            return int(doc["seed"])
    except Exception as exc:
        log("seed: manifest unreadable: %r" % (exc,))
    try:
        doc = _read_json(new_game_path(slot))
        return int(doc.get("seed", 20240501))
    except Exception:
        return 20240501


def summary(slot: int):
    """(exists, houses, coins) for the title screen."""
    if not exists(slot):
        return (False, 0, 0)
    doc = read_manifest_quiet(slot)
    if doc is None:
        # A seed has been chosen but no game has been saved yet: still show
        # the slot as a new game, not as an existing one with zero coins.
        return (False, 0, 0)
    got = doc.get("summary") or {}
    return (True, int(got.get("houses", 0)), int(got.get("coins", 0)))


def delete(slot: int) -> bool:
    path = slot_dir(slot)
    if not os.path.isdir(path):
        log("delete: slot %d is empty" % int(slot))
        return False
    try:
        shutil.rmtree(path)
        log("delete: removed slot %d" % int(slot))
        return True
    except Exception as exc:
        log("delete: slot %d failed: %r" % (int(slot), exc))
        return False


def save_all(slot: int, manifest: dict, chunks: dict[str, object]) -> None:
    """Write chunks, then the manifest.  Caller supplies plain data only."""
    os.makedirs(slot_dir(slot), exist_ok=True)
    previous = None
    try:
        previous = _read_manifest_raw(slot)
    except Exception:
        previous = None
    generation = int((previous or {}).get("generation", 0)) + 1
    table = write_chunks(slot, chunks, previous, generation)
    manifest = dict(manifest)
    manifest["chunks"] = table
    manifest["generation"] = generation
    manifest["format"] = FORMAT
    manifest["schema"] = SCHEMA_VERSION
    manifest["saved_at"] = time.time()
    write_manifest(slot, manifest)
    _clean_chunks(slot, table, (previous or {}).get("chunks") or {})
    _clean_empty_dirs(slot)
    try:
        extra = manifest.get("timing") or {}
        log("saved slot %d: %d chunks, %d camps, %.0f ms snapshot"
            % (int(slot), len(table), len(manifest.get("camps") or []),
               float(extra.get("snapshot_ms", 0.0))))
    except Exception:
        pass


def load_all(slot: int):
    manifest = load_manifest(slot)
    if manifest is None:
        return None
    chunks = read_chunks(slot, manifest)
    return manifest, chunks
