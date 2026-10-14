"""Scarce wild wheat and tobacco, scattered across the open world.

Everything is derived deterministically from the world seed, so nothing needs
to be stored except the set of plants the player has already picked
(World.wild_removed).  Wild plants can be taken at any stage -- the older the
plant, the more it gives.
"""

from __future__ import annotations

import random

import biomes
import crop
import items
import quality
from world import TILE

DENSITY = 4          # eligible tiles in a thousand (~0.4%)
REGEN = crop.GROW_SECONDS   # a wild plant comes back on the sown crop's clock

_NOW = 0.0
_WORLD = None


def set_time(t: float) -> None:
    global _NOW
    _NOW = t


def set_world(w) -> None:
    global _WORLD
    _WORLD = w


def taken(world, tx: int, ty: int) -> bool:
    """True while a picked plant has not yet grown back. Wild food returns to
    the same spot on the same clock as a sown crop -- no tilling, no seed, no
    tending. Otherwise every foraged meal permanently eats the world."""
    when = world.wild_eaten.get((tx, ty))
    if when is None:
        return False
    if _NOW >= when:
        del world.wild_eaten[(tx, ty)]        # it is back
        return False
    return True
STAGES = 4           # growth stages 0..3
CELL = 16            # tiles per wild-plant cache cell (512 px)


def _hash(tx: int, ty: int, seed: int) -> int:
    h = (tx * 73856093) ^ (ty * 19349663) ^ (seed * 2654435761)
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h


_PLANT: dict = {}          # (world, tx, ty) -> (kind, stage) or None
def _plant(world, tx: int, ty: int):
    """What grows on this tile, if anything -- CACHED.

    Terrain noise is expensive and a village of foragers asks about the same
    tile hundreds of times a day. This is per-tile and permanent, so it is
    computed once and remembered.
    """
    key = (id(world), tx, ty)
    if key in _PLANT:
        return _PLANT[key]
    got = None
    h = _hash(tx, ty, world.seed)
    if h % 1000 < DENSITY and world.tile_kind(tx, ty) == "grass":
        x = tx * TILE + TILE / 2.0
        y = ty * TILE + TILE / 2.0
        food, leaf = biomes.crop_kinds(float(biomes.temperature(x, y, world.seed)),
                                       float(biomes.humidity(x, y, world.seed)))
        got = (leaf if (h >> 8) & 1 else food, (h >> 4) % STAGES)
    _PLANT[key] = got
    return got


def at(world, tx: int, ty: int, villages=None):
    """(kind, stage) for a wild plant on this tile right now, or None."""
    if taken(world, tx, ty):
        return None
    got = _plant(world, tx, ty)
    if got is None:
        return None
    if villages is not None:
        x = tx * TILE + TILE / 2.0
        y = ty * TILE + TILE / 2.0
        for v in villages:
            if v.fence_rect.collidepoint(x, y):
                return None                         # not inside a village
    return got


def _cell(world, cx: int, cy: int):
    """Wild plants in one 16x16-tile cell, computed once and cached."""
    key = (cx, cy)
    cached = world.wild_cells.get(key)
    if cached is not None:
        return cached
    cached = []
    for ty in range(cy * CELL, cy * CELL + CELL):
        for tx in range(cx * CELL, cx * CELL + CELL):
            h = _hash(tx, ty, world.seed)
            if h % 1000 >= DENSITY:
                continue
            if world.tile_kind(tx, ty) != "grass":
                continue
            wx = tx * TILE + TILE / 2.0
            wy = ty * TILE + TILE / 2.0
            food, leaf = biomes.crop_kinds(
                float(biomes.temperature(wx, wy, world.seed)),
                float(biomes.humidity(wx, wy, world.seed)))
            kind = leaf if (h >> 8) & 1 else food
            cached.append((tx, ty, kind, (h >> 4) % STAGES))
    world.wild_cells[key] = cached
    return cached


def visible(world, villages, cam_x: float, cam_y: float,
            vw: int, vh: int, pad: int = 64):
    """(world_x, world_y, kind, stage) for on-screen wild plants."""
    x0 = int((cam_x - pad) // TILE)
    y0 = int((cam_y - pad) // TILE)
    x1 = int((cam_x + vw + pad) // TILE)
    y1 = int((cam_y + vh + pad) // TILE)
    out = []
    for cy in range(y0 // CELL, y1 // CELL + 1):
        for cx in range(x0 // CELL, x1 // CELL + 1):
            for tx, ty, kind, stage in _cell(world, cx, cy):
                if not (x0 <= tx <= x1 and y0 <= ty <= y1):
                    continue
                if taken(world, tx, ty):
                    continue
                x = tx * TILE + TILE / 2.0
                y = ty * TILE + TILE / 2.0
                if villages is not None:
                    if any(v.fence_rect.collidepoint(x, y) for v in villages):
                        continue
                out.append((x, y, kind, stage))
    return out


def harvest(world, tx: int, ty: int, kind: str, stage: int,
            inventory, toast, share=None) -> None:
    """``share`` is called with (item, amount) for the crop -- see main.pay_share."""
    if kind in crop.FOOD_KINDS:
        item = crop.FOOD_ITEM[kind]
        if kind == "wheat":
            amount = random.randint(1, 3)
        elif kind == "berries":
            amount = random.randint(2, 5)
        else:
            amount = random.randint(1, 2)
        seeds = 1 + (1 if stage >= 2 else 0)
        inventory.add(item, amount)
        if share is not None:
            share(item, amount)
        seed = crop.CROP_SEED.get(kind)
        if seed is not None:
            inventory.add(seed, seeds)
        toast("Gathered %d %s and %d %s"
              % (amount, items.get(item).name.lower(), seeds,
                 items.get(seed).name.lower() if seed else "seeds"))
    else:
        item = crop.LEAF_ITEM[kind]
        amount = 1 + stage + (1 if random.random() < 0.5 else 0)
        inventory.add(item, amount, 0)
        if share is not None:
            share(item, amount)
        seed = crop.CROP_SEED.get(kind)
        if seed is not None:
            inventory.add(seed, 1)
            # SAY SO. The food crops have always named their seed in the
            # message; the leaf ones handed one over without a word, so a
            # player could pick tobacco all day and believe the only way to get
            # seed was to rob a village.
            toast("Gathered %d wild %s and a %s"
                  % (amount, items.get(item).name.lower(),
                     items.get(seed).name.lower()))
        else:
            toast("Gathered %d wild %s" % (amount, items.get(item).name.lower()))
    world.wild_eaten[(tx, ty)] = _NOW + REGEN      # back in one crop cycle


def _nearest(world, x: float, y: float, radius: float):
    """(tx, ty, kind) of the closest standing wild plant, or None.

    Tests the TILES in reach -- not whole cache cells. Computing a 16x16 cell
    to find the single plant inside it costs 256 hashes and a noise sample, and
    a village full of foragers walked through hundreds of cells a minute. That
    was most of the simulation's slowdown.
    """
    if world is None:
        return None
    tx0 = int((x - radius) // TILE)
    tx1 = int((x + radius) // TILE)
    ty0 = int((y - radius) // TILE)
    ty1 = int((y + radius) // TILE)
    best = None
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            h = _hash(tx, ty, world.seed)
            if h % 1000 >= DENSITY:
                continue                            # cheap reject first
            found = at(world, tx, ty)
            if found is None:
                continue
            px, py = tx * TILE + TILE / 2.0, ty * TILE + TILE / 2.0
            d = (px - x) ** 2 + (py - y) ** 2
            if d > radius * radius:
                continue
            if best is None or d < best[0]:
                best = (d, tx, ty, found[0])
    if best is None:
        return None
    return best[1], best[2], best[3]


def forage(world, x: float, y: float, radius: float = 420.0):
    """Eat the nearest ripe wild plant within reach. Returns the item name, or
    None if the ground here is bare. A traveller lives off the land."""
    found = _nearest(world, x, y, radius)
    if found is None:
        return None
    tx, ty, kind = found
    world.wild_eaten[(tx, ty)] = _NOW + REGEN
    return crop.FOOD_ITEM.get(kind) or crop.LEAF_ITEM.get(kind)


def forage_npc(world, npc, radius: float = 230.0):
    """A woodcutter picks whatever is growing beside the stump.

    Wild food goes straight into his larder -- so he stops buying every meal --
    and wild leaf goes into his pocket at HIS OWN grade, the same as a farmer's
    crop. The hand learns by reaping, so a logger's leaf gets better with the
    years, and the farmers have somebody to compete with.
    """
    found = _nearest(world, npc.x, npc.y, radius)
    if found is None:
        return None
    tx, ty, kind = found
    world.wild_eaten[(tx, ty)] = _NOW + REGEN
    if kind in crop.LEAF_KINDS:
        item = crop.LEAF_ITEM.get(kind)
        if item is None:
            return None
        amount = 1 + random.randint(0, 2)
        grade = npc.skills.leaf_grade(getattr(npc, "quality_cap", 8))
        held = npc.stock.get(item, 0)
        npc.grade[item] = quality.merge(npc.grade.get(item, grade), held, grade, amount)
        npc.stock[item] = held + amount
    else:
        item = crop.FOOD_ITEM.get(kind)
        if item is None:
            return None
        npc.stock[item] = npc.stock.get(item, 0) + random.randint(1, 3)
    npc.skills.gain_farming(0.02)      # the same slow climb a farmer makes
    return item
