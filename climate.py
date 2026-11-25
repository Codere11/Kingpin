"""climate.py -- shelter from the weather around a camp fireplace.

Cold and heat are real for conquered people.  A fire alone is not enough:
the fire has to be enclosed by walls, with a door, before it keeps the night
out.  The test is a small flood fill over the 1x1 block grid, cached until the
built blocks change.
"""

from __future__ import annotations

from world import TILE


def _fire_tile(g, camp):
    fire = getattr(camp, "fireplace", None)
    if fire is None:
        best = None
        bd = 1e18
        cx = float(getattr(camp, "x", 0.0))
        cy = float(getattr(camp, "y", 0.0))
        for wp in (getattr(g, "placed_work", ()) or ()):
            if getattr(wp, "kind", "") != "fireplace":
                continue
            d = (float(wp.x) - cx) ** 2 + (float(wp.y) - cy) ** 2
            if d < bd:
                bd, best = d, wp
        fire = best
    if fire is None:
        return None
    try:
        return (int(float(fire.x) // TILE), int(float(fire.y) // TILE))
    except Exception:
        return None


def room(g, camp):
    """The enclosed floor cells around this camp's fireplace, or None.

    Walls and doors stop the flood; beds do not.  The room must have at least
    four wall pieces and one door.  Results are cached on the camp and keyed
    by the block version/size.
    """
    if camp is None or not getattr(camp, "conquered", False):
        return None
    start = _fire_tile(g, camp)
    if start is None:
        return None
    blocks = getattr(g, "built_blocks", None) or {}
    ver = 0
    try:
        ver = int(g._BUILD_VER[0])
    except Exception:
        ver = 0
    key = (start, ver, len(blocks))
    old = getattr(camp, "_climate_room_key", None)
    if old == key:
        return getattr(camp, "_climate_room", None)
    if start in blocks:
        camp._climate_room_key = key
        camp._climate_room = None
        return None
    seen = set()
    q = [start]
    walls = set()
    doors = set()
    while q:
        tx, ty = q.pop()
        if (tx, ty) in seen:
            continue
        seen.add((tx, ty))
        if len(seen) > 400:
            camp._climate_room_key = key
            camp._climate_room = None
            return None
        for nx, ny in ((tx + 1, ty), (tx - 1, ty),
                       (tx, ty + 1), (tx, ty - 1)):
            if (nx, ny) in seen:
                continue
            kind = blocks.get((nx, ny))
            if kind is None or kind == "bed":
                q.append((nx, ny))
            elif kind == "door":
                doors.add((nx, ny))
            else:
                walls.add((nx, ny))
    if len(walls) >= 4 and doors:
        room_cells = seen
    else:
        room_cells = None
    camp._climate_room_key = key
    camp._climate_room = room_cells
    return room_cells


def inside(g, camp, x, y, margin=0.0):
    cells = room(g, camp)
    if not cells:
        return False
    tx = int(float(x) // TILE)
    ty = int(float(y) // TILE)
    return (tx, ty) in cells


def bed_inside(g, camp, bed):
    """True when this bedroll's square is inside the walled fireplace room."""
    if bed is None:
        return False
    try:
        tx, ty = int(bed[0]), int(bed[1])
    except Exception:
        return False
    cells = room(g, camp)
    return bool(cells and (tx, ty) in cells)
