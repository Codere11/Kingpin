"""terrain.py -- what the player changed on the ground.

Plots and their planting times, tile overrides, wild plants picked or eaten,
felled trees (stumps) and hand-planted trees, and iron chunks mined or partly
struck.  Everything is grouped by an 8192-pixel world region, so an autosave
only rewrites the regions that changed.
"""

from __future__ import annotations

from . import codec
from . import context as _context

TILE = 32.0


def _region(regions: dict, x: float, y: float) -> dict:
    key = codec.region_key(x, y)
    got = regions.get(key)
    if got is None:
        got = {"plots": [], "tiles": [], "wild_removed": [],
               "wild_eaten": [], "wild_forced": [],
               "stumps": [], "planted": [], "ore": []}
        regions[key] = got
    return got


def snapshot(g) -> dict:
    regions: dict[str, dict] = {}
    snapshot_base(g, regions)
    add_wild(regions, wild_items(g))
    return regions


def snapshot_base(g, regions: dict) -> None:
    """Everything except the dense wild-eaten map (see add_wild)."""
    world = g.world
    with world._lock:
        plots = list(world.plots.items())
        overrides = list(world._overrides.items())
    for (tx, ty), plot in plots:
        rec = _region(regions, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
        rec["plots"].append([int(tx), int(ty), str(plot.kind),
                             None if plot.planted_at is None
                             else float(plot.planted_at),
                             None if plot.grow is None else float(plot.grow)])
    for (tx, ty), kind in overrides:
        rec = _region(regions, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
        rec["tiles"].append([int(tx), int(ty), str(kind)])
    for (tx, ty) in list(world.wild_removed):
        rec = _region(regions, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
        rec["wild_removed"].append([int(tx), int(ty)])
    for (tx, ty), value in list(getattr(world, "wild_forced", {}).items()):
        rec = _region(regions, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
        rec["wild_forced"].append([int(tx), int(ty), codec.tidy(value)])

    trees = g.trees
    planted = set()
    for t in list(getattr(trees, "_planted", ()) or ()):
        planted.add(id(t))
        rec = _region(regions, t.x, t.y)
        rec["planted"].append({
            "uid": codec.uid(t, "tree"),
            "x": float(t.x), "y": float(t.y),
            "r": float(t.canopy_r),
            "variant": int(getattr(t, "variant", 0)),
            "flip": bool(getattr(t, "flip", False)),
            "species": getattr(t, "species", "conifer"),
            "snowy": bool(getattr(t, "snowy", True)),
            "felled": bool(getattr(t, "felled", False)),
            "felled_at": float(getattr(t, "felled_at", 0.0)),
            "strikes": int(getattr(t, "strikes", 0)),
        })
    for t in list(getattr(trees, "_stumps", ()) or ()):
        if id(t) in planted:
            continue
        rec = _region(regions, t.x, t.y)
        rec["stumps"].append([float(t.x), float(t.y),
                              float(getattr(t, "felled_at", 0.0))])

    ore = g.ore_field
    cell = getattr(__import__("ore"), "CELL", 260)
    cache = getattr(ore, "_cache", {}) or {}
    done = set()
    for (cx, cy) in list(ore.mined):
        done.add((cx, cy))
        chunk = cache.get((cx, cy))
        strikes = int(getattr(chunk, "strikes", 0)) if chunk is not None else 0
        rec = _region(regions, int(cx) * cell, int(cy) * cell)
        rec["ore"].append([int(cx), int(cy), strikes])
    for (cx, cy), chunk in list(cache.items()):
        if chunk is None or (cx, cy) in done:
            continue
        if int(getattr(chunk, "strikes", 0)) <= 0:
            continue
        rec = _region(regions, chunk.x, chunk.y)
        rec["ore"].append([int(cx), int(cy), int(chunk.strikes)])


def wild_items(g) -> dict:
    """A stable copy of the dense wild-eaten map, for batched snapshot.

    A dict copy is a C-level operation; turning 185,000 items into Python
    tuples first was the 30 ms hitch.
    """
    # PERMANENT CLEARING IS DERIVED, NOT STATE.  A camp's ring and a placed
    # block mark every tile `inf`; both are re-applied on load (native.build
    # and built_blocks).  Only the finite regrowth clocks of wild plants the
    # player actually picked need to be written.
    return {k: v for k, v in (g.world.wild_eaten or {}).items()
            if v != float("inf")}


def add_wild(regions: dict, items, start: int = 0, count: int = 1 << 60) -> int:
    """Add a batch of wild-eaten tiles; return the next index to process."""
    if isinstance(items, dict):
        items = list(items.items())
    end = min(len(items), start + count)
    for (tx, ty), when in items[start:end]:
        rec = _region(regions, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
        rec["wild_eaten"].append([int(tx), int(ty), float(when)])
    return end


def add_wild_iter(regions: dict, items, count: int) -> bool:
    """Process up to `count` entries from an iterator; False when exhausted."""
    for _ in range(count):
        try:
            (tx, ty), when = next(items)
        except StopIteration:
            return False
        rec = _region(regions, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
        rec["wild_eaten"].append([int(tx), int(ty), float(when)])
    return True


def emit(regions: dict, chunks: dict) -> None:
    for key, payload in regions.items():
        chunks["terrain/%s.json" % key] = payload

def apply(g, regions: dict, ctx: "_context.Context | None" = None) -> None:
    world = g.world
    with world._lock:
        world.plots.clear()
        world._overrides.clear()
        world.wild_removed.clear()
        world.wild_eaten.clear()
        try:
            world.wild_cleared.clear()
        except Exception:
            pass
        try:
            world.wild_forced.clear()
        except Exception:
            pass
        world._kind_cache.clear()
    g.trees._stumps[:] = []
    try:
        g.trees._planted[:] = []
    except Exception:
        g.trees._planted = []
    g.ore_field.mined.clear()

    planted = []
    for payload in (regions or {}).values():
        for rec in payload.get("plots", ()) or ():
            world.set_plot(int(rec[0]), int(rec[1]), str(rec[2]),
                           None if rec[3] is None else float(rec[3]),
                           None if len(rec) < 5 or rec[4] is None
                           else float(rec[4]))
        for rec in payload.get("tiles", ()) or ():
            world.set_tile(int(rec[0]), int(rec[1]), str(rec[2]))
        for rec in payload.get("wild_removed", ()) or ():
            world.wild_removed.add((int(rec[0]), int(rec[1])))
        for rec in payload.get("wild_eaten", ()) or ():
            world.wild_eaten[(int(rec[0]), int(rec[1]))] = float(rec[2])
        for rec in payload.get("wild_forced", ()) or ():
            try:
                world.wild_forced[(int(rec[0]), int(rec[1]))] = tuple(rec[2])
            except Exception:
                pass
        for rec in payload.get("planted", ()) or ():
            t = _restore_planted(g, rec)
            if t is not None:
                planted.append(t)
        for rec in payload.get("stumps", ()) or ():
            _restore_stump(g, float(rec[0]), float(rec[1]), float(rec[2]))
        for rec in payload.get("ore", ()) or ():
            _restore_ore(g, int(rec[0]), int(rec[1]), int(rec[2]))

    # The permanent clearing under the player's own blocks is derived from
    # the blocks themselves; the camp rings are re-marked by native.build.
    for (tx, ty) in (getattr(g, "built_blocks", {}) or {}):
        world.wild_cleared.add((int(tx), int(ty)))

    if ctx is not None:
        for t in planted:
            uid = getattr(t, "_save_uid", None)
            if uid:
                ctx.planted_trees[str(uid)] = t


def _restore_planted(g, rec: dict):
    try:
        t = g.trees.plant(float(rec["x"]), float(rec["y"]),
                          float(rec.get("r", 74.0)),
                          int(rec.get("variant", 0)),
                          rec.get("species", "conifer"),
                          bool(rec.get("snowy", True)))
        codec.set_uid(t, rec.get("uid"))
        if "flip" in rec:
            t.flip = bool(rec["flip"])
        t.canopy_r = float(rec.get("r", t.canopy_r))
        t.strikes = int(rec.get("strikes", 0))
        t.felled = bool(rec.get("felled", False))
        t.felled_at = float(rec.get("felled_at", 0.0))
        if getattr(t, "felled", False):
            g.trees.remember_stump(t)
        return t
    except Exception:
        return None


def _restore_stump(g, x: float, y: float, when: float) -> None:
    try:
        t = next((c for c in g.trees.near(x, y, 60.0)
                  if abs(c.x - x) < 1.0 and abs(c.y - y) < 1.0), None)
        if t is not None and not getattr(t, "felled", False):
            t.felled = True
            t.felled_at = when
            g.trees.remember_stump(t)
    except Exception:
        pass


def _restore_ore(g, cx: int, cy: int, strikes: int) -> None:
    g.ore_field.mined.add((cx, cy))
    if strikes <= 0:
        return
    try:
        chunk = g.ore_field.chunk(cx, cy)
        if chunk is not None:
            chunk.strikes = int(strikes)
            if strikes >= 80:
                chunk.mined = True
    except Exception:
        pass
