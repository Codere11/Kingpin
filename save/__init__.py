"""save -- the game's state, written as plain data and read back.

Public entry points:

    load_manifest(slot)            the small manifest, before the world is built
    initial_seed(slot)             the seed for a world about to be made
    load_all(slot)                 (manifest, chunks) for a restore
    restore(g, manifest, chunks)   put the state onto a freshly built world
    request(g, reason)             ask for a lazy save (snapshot spread over frames)
    tick(g)                        advance a lazy save by one frame's budget
    save_now(g, reason)            finish and write synchronously (exit/tests)
    summary(slot), delete(slot), new_game(slot, seed), exists(slot)

The snapshot is composed from a handful of explicit providers, each of which
returns plain dictionaries.  Nothing is pickled.  Nothing in the file is a
live object, an id() or a list index.
"""

from __future__ import annotations

import collections
import time
import threading

from . import animals, audit, built, camps, codec, meta, player, store, systems
from . import terrain
from .context import Context
from .schema import (FORMAT, GAME_VERSION, SCHEMA_VERSION, WORLD_VERSION,
                     SaveError)

# Re-export the store's small, stable surface.
exists = store.exists
summary = store.summary
delete = store.delete
new_game = store.new_game
initial_seed = store.initial_seed
load_manifest = store.load_manifest
load_all = store.load_all

# The old format's files are moved out of the way once, at import, so the
# title screen never shows them and the disk is not carrying 500 MB of dead
# world caches beside a new save.
try:
    store.migrate_legacy()
except Exception:
    pass


class SnapshotJob:
    """One save being composed, a few milliseconds of work per frame."""

    def __init__(self, g, reason: str = "auto") -> None:
        self.g = g
        self.reason = reason
        self.parts: dict = {}
        self.chunks: dict[str, object] = {}
        self.camp_metas: list = []
        self.steps = collections.deque()
        self.started = time.perf_counter()
        self.steps.append(("meta", self._meta))
        self.steps.append(("player", self._player))
        self.steps.append(("systems", self._systems))
        self.steps.append(("built", self._built))
        self.steps.append(("terrain", self._terrain))
        self.steps.append(("animals", self._animals))
        self._camps = list(getattr(g, "native_settlements", {}).items())
        for key, camp in self._camps:
            self.steps.append(("camp", lambda _k=key, _c=camp: self._camp(_c, _k)))

    # -- steps -------------------------------------------------------------
    def _meta(self) -> None:
        self.parts["meta"] = meta.snapshot(self.g)

    def _player(self) -> None:
        self.parts["player"] = player.snapshot(self.g)

    def _systems(self) -> None:
        self.parts["systems"] = systems.snapshot(self.g)

    def _built(self) -> None:
        self.chunks["built.json"] = built.snapshot(self.g)

    def _terrain(self) -> None:
        # The dense wild-eaten map can be hundreds of thousands of tiles;
        # it is processed in batches across frames, not in one step.
        self._terrain_regions: dict = {}
        terrain.snapshot_base(self.g, self._terrain_regions)
        self._wild_items = terrain.wild_items(self.g)
        self._wild_iter = iter(self._wild_items.items())
        self.steps.appendleft(("terrain_emit", self._terrain_emit))
        self.steps.appendleft(("terrain_wild", self._terrain_wild))

    def _terrain_wild(self) -> None:
        more = terrain.add_wild_iter(self._terrain_regions,
                                     self._wild_iter, 3000)
        if more:
            self.steps.appendleft(("terrain_wild", self._terrain_wild))

    def _terrain_emit(self) -> None:
        terrain.emit(self._terrain_regions, self.chunks)
        self._terrain_regions = None
        self._wild_items = None

    def _animals(self) -> None:
        self.chunks["animals.json"] = animals.snapshot_all(self.g)

    def _camp(self, camp, key) -> None:
        try:
            meta_rec, body = camps.snapshot(camp, key)
        except Exception as exc:
            store.log("camp snapshot FAILED %r: %r" % (key, exc))
            return
        self.camp_metas.append(meta_rec)
        self.chunks[meta_rec["chunk"]] = body

    # -- running -----------------------------------------------------------
    def step(self, budget: float) -> bool:
        deadline = time.perf_counter() + max(0.0, budget)
        while self.steps:
            _name, fn = self.steps.popleft()
            _t0 = time.perf_counter()
            try:
                fn()
            except Exception as exc:
                store.log("snapshot step %s FAILED: %r" % (_name, exc))
            _ms = (time.perf_counter() - _t0) * 1000.0
            if _ms >= 8.0:
                store.log("slow snapshot step %s: %.1f ms" % (_name, _ms))
            if budget < 1e9 and time.perf_counter() >= deadline:
                break
        return not self.steps

    def finish(self) -> None:
        self.step(1e9)

    def compose(self) -> dict:
        m = self.parts.get("meta") or {}
        built_data = self.chunks.get("built.json") or {}
        coins = _coins(self.parts.get("player") or {}, self.parts.get("systems") or {},
                       built_data)
        manifest = {
            "format": FORMAT,
            "schema": SCHEMA_VERSION,
            "game_version": GAME_VERSION,
            "world_version": WORLD_VERSION,
            "seed": int(m.get("seed", 20240501)),
            "spawn": m.get("spawn"),
            "ship": m.get("ship"),
            "now": m.get("now", 0.0),
            "kills": m.get("kills", 0),
            "war_alarms": m.get("war_alarms", 0),
            "conquered_count": m.get("conquered_count", 0),
            "player": self.parts.get("player") or {},
            "systems": self.parts.get("systems") or {},
            "camps": self.camp_metas,
            "summary": {
                "houses": len(built_data.get("houses") or ()),
                "coins": int(coins),
                "camps": len(self.camp_metas),
                "people": sum(len((c.get("people") or ()))
                              for rel, c in self.chunks.items()
                              if rel.startswith("camps/")),
            },
            "timing": {
                "snapshot_ms": (time.perf_counter() - self.started) * 1000.0,
                "reason": self.reason,
            },
        }
        return manifest


def _coins(player_data: dict, systems_data: dict, built_data: dict) -> int:
    total = 0
    for inv in (player_data.get("inventory"), systems_data.get("ship_hold")):
        total += _inv_coins(inv)
    for house in built_data.get("houses") or ():
        total += _inv_coins(house.get("chest"))
    for chest in built_data.get("chests") or ():
        total += _inv_coins(chest.get("inventory"))
    return total


def _inv_coins(inv) -> int:
    total = 0
    for stack in (inv or {}).get("slots") or ():
        if stack and stack[0] == "coin":
            try:
                total += int(stack[1])
            except Exception:
                pass
    return total


# -- lazy save scheduling ----------------------------------------------------
_state = {
    "job": None,
    "writer": None,
    "pending": False,
    "last": 0.0,
}


def request(g, reason: str = "auto", force: bool = False) -> None:
    """Ask for a save.  It is composed over the next frames, written off-thread."""
    st = _state
    if st["job"] is not None or st["writer"] is not None:
        st["pending"] = True
        return
    now = time.monotonic()
    if not force and now - float(st["last"] or 0.0) < 1.0:
        st["pending"] = True
        return
    st["last"] = now
    st["job"] = SnapshotJob(g, reason)


def _write_job(slot: int, job: SnapshotJob) -> None:
    try:
        store.save_all(slot, job.compose(), job.chunks)
    except Exception as exc:
        store.log("SAVE FAILED: %r" % (exc,))


def _start_writer(slot: int, job: SnapshotJob) -> None:
    th = threading.Thread(target=_write_job, args=(slot, job), daemon=True)
    _state["writer"] = th
    th.start()


def tick(g) -> None:
    """One frame's slice of a lazy save.  Call at the end of the frame."""
    st = _state
    writer = st["writer"]
    if writer is not None and not writer.is_alive():
        st["writer"] = None
        if st["pending"] and st["job"] is None:
            st["pending"] = False
            request(g, "queued", force=True)
    job = st["job"]
    if job is not None:
        done = job.step(0.004)
        if done:
            st["job"] = None
            _start_writer(getattr(g, "slot", 0), job)
            return
    if (st["job"] is None and st["writer"] is None
            and st["pending"]):
        st["pending"] = False
        request(g, "pending", force=True)


def save_now(g, reason: str = "exit") -> None:
    """Finish whatever is in flight and write it synchronously."""
    st = _state
    job = st["job"]
    if job is not None:
        job.finish()
        st["job"] = None
        _write_job(getattr(g, "slot", 0), job)
    writer = st["writer"]
    if writer is not None:
        try:
            writer.join(timeout=10.0)
        except Exception:
            pass
        st["writer"] = None
    if st["pending"] or (job is None and writer is None):
        fresh = SnapshotJob(g, reason)
        fresh.finish()
        _write_job(getattr(g, "slot", 0), fresh)
    st["pending"] = False
    st["last"] = time.monotonic()


# -- restore -----------------------------------------------------------------
def restore(g, manifest: dict, chunks: dict) -> Context:
    """Put a loaded save onto the freshly built world.

    Order matters: the built world and the terrain are restored first, then
    the native camps are rebuilt at their saved positions, then the saved
    people and their references are resolved, then the player is placed.
    """
    ctx = Context()
    meta.apply(g, manifest)
    built.restore(g, chunks.get("built.json"), ctx)
    terrain.apply(g, _terrain_chunks(chunks), ctx)
    camps.prepare(g, manifest, chunks, ctx)
    animals.restore_all(g, chunks.get("animals.json"), ctx)
    camps.apply(g, manifest, chunks, ctx)
    player.apply(g, manifest.get("player"), ctx)
    systems.apply(g, manifest.get("systems"), ctx)
    built.finalize(g, ctx)
    ctx.resolve()
    audit.report(g, {
        "camps": len(manifest.get("camps") or ()),
        "people": sum(1 for _ in getattr(g, "_native_people", ())),
        "animals": len(getattr(g, "horses", ())) + len(getattr(g, "enemies", ())),
        "houses": len(getattr(g, "built_houses", ())),
        "chunks": len(chunks),
    })
    return ctx


def world_position(manifest: dict):
    """Where the player was, in world space, for building the ground."""
    loc = ((manifest or {}).get("player") or {}).get("location") or {}
    world = loc.get("world")
    if world and len(world) >= 2:
        return float(world[0]), float(world[1])
    return float(loc.get("x", 0.0)), float(loc.get("y", 0.0))


def _terrain_chunks(chunks: dict) -> dict:
    out = {}
    for rel, payload in (chunks or {}).items():
        if not rel.startswith("terrain/"):
            continue
        name = rel[len("terrain/"):]
        if name.endswith(".json"):
            name = name[:-5]
        out[name] = payload
    return out
