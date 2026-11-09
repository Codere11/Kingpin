"""native.py -- NATIVE SETTLEMENTS: teepees and fields around a fireplace.

A native settlement is the one kind of settlement the new world has. It is a
fire in the middle, a ring of hide teepees, and fields of food and leaf laid
out past the teepees -- and nothing of the old world: no fence, no roads, no
gates, no searches. Just the people.

The teepees are real blocks, exactly as the player would lay them: a 5x5 of
hide for the walls, a wood block in the middle for the pole, and the door left
empty.
"""
from __future__ import annotations

import math
import random

import biomes
import crop
import industry
import village as village_mod
from world import TILE


# a native camp is a small place: they sit about this far apart, shaken by a
# little jitter, and are generated this far around the player
NATIVE_SPACING = 20000.0      # ~20 km between camps
NATIVE_JITTER = 0.22          # fraction of the spacing, either way
NATIVE_RADIUS = 40000.0       # generate camps within this of the player

# a teepee sleeps this many people
PER_TEEPEE = 2

# every native settlement keeps this much clear ground beyond its own layout,
# measured in whole tiles -- the user's "+30 blocks".
CLEAR_BLOCKS = 30

# the three food fields and (up to) two leaf fields
MIN_FOOD_FIELDS = 3
MIN_LEAF_FIELDS = 1
MAX_LEAF_FIELDS = 2

_NAMES = ("Awan", "Kiona", "Takoda", "Yuma", "Nashoba", "Chenoa",
          "Migina", "Ohanzee", "Sikya", "Winona", "Elan", "Kohana",
          "Mato", "Nokomis", "Odakota", "Shilah")


def native_center(gx: int, gy: int, seed: int):
    """A native camp's centre: a 20 km lattice, shaken by jitter."""
    code = (gx * 73856093) ^ (gy * 19349663) ^ (seed * 2654435761)
    rng = random.Random(code & 0xFFFFFFFF)
    jx = rng.uniform(-NATIVE_SPACING * NATIVE_JITTER, NATIVE_SPACING * NATIVE_JITTER)
    jy = rng.uniform(-NATIVE_SPACING * NATIVE_JITTER, NATIVE_SPACING * NATIVE_JITTER)
    return (gx + 0.5) * NATIVE_SPACING + jx, (gy + 0.5) * NATIVE_SPACING + jy


def teepee_blocks(tx: int, ty: int) -> dict:
    """The blocks of one teepee, laid out with (tx, ty) as its top-left.

    A 5x5 square: the outer ring is hide, the middle block is wood (the
    pole), and the middle of the south wall is the door -- empty, like the
    rest of the interior.
    """
    out = {}
    for dx in range(5):
        for dy in range(5):
            on_wall = dx == 0 or dx == 4 or dy == 0 or dy == 4
            if on_wall:
                if (dx, dy) == (2, 4):
                    continue                    # the door
                out[(tx + dx, ty + dy)] = "hide"
            elif (dx, dy) == (2, 2):
                out[(tx + dx, ty + dy)] = "wood"   # the centre pole
    return out


def _clear_trees(g, cx: float, cy: float, radius: float) -> None:
    trees = getattr(g, "trees", None)
    if trees is None:
        return
    try:
        import trees as _trees
        cell = getattr(_trees, "CELL", 180)
        x0 = int(math.floor((cx - radius) / cell))
        x1 = int(math.floor((cx + radius) / cell))
        y0 = int(math.floor((cy - radius) / cell))
        y1 = int(math.floor((cy + radius) / cell))
        for gy in range(y0, y1 + 1):
            for gx in range(x0, x1 + 1):
                # mark the cell bare WITHOUT generating its tree -- a camp needs
                # clear ground, and laying out hundreds of trees just to remove
                # them is the slow part of founding one.
                trees._cache[(gx, gy)] = None
                trees._presence[(gx, gy)] = None
        for t in list(getattr(trees, "_stumps", ())):
            if math.hypot(t.x - cx, t.y - cy) <= radius:
                try:
                    trees._stumps.remove(t)
                except Exception:
                    pass
        for t in list(getattr(trees, "_planted", ())):
            if math.hypot(t.x - cx, t.y - cy) <= radius:
                try:
                    trees._planted.remove(t)
                except Exception:
                    pass
    except Exception:
        pass


def _clear_wild(g, cx: float, cy: float, radius: float) -> None:
    """No wild plant in the settlement's ground: every tile inside the ring is
    marked eaten for ever, so nothing forages back up through the fields."""
    try:
        world = g.world
        steps = int(radius / TILE) + 2
        ctx = int(math.floor(cx / TILE))
        cty = int(math.floor(cy / TILE))
        for dty in range(-steps, steps + 1):
            for dtx in range(-steps, steps + 1):
                tx = ctx + dtx
                ty = cty + dty
                wx = tx * TILE + TILE / 2.0
                wy = ty * TILE + TILE / 2.0
                if math.hypot(wx - cx, wy - cy) <= radius:
                    world.wild_eaten[(tx, ty)] = float("inf")
    except Exception:
        pass


def _clear_ore(g, cx: float, cy: float, radius: float) -> None:
    """No iron chunk inside the settlement: ore cells within the ring are
    erased from the field's presence and cache, so none ever renders."""
    ore = getattr(g, "ore_field", None)
    if ore is None:
        return
    try:
        import ore as _ore
        cell = getattr(_ore, "CELL", 260)
        x0 = int(math.floor((cx - radius) / cell))
        x1 = int(math.floor((cx + radius) / cell))
        y0 = int(math.floor((cy - radius) / cell))
        y1 = int(math.floor((cy + radius) / cell))
        for gy in range(y0, y1 + 1):
            for gx in range(x0, x1 + 1):
                # mark the cell empty WITHOUT generating its chunk
                ore._cache[(gx, gy)] = None
                ore._presence[(gx, gy)] = None
                ore.mined.add((gx, gy))
    except Exception:
        pass


def build(g, cx: float, cy: float, seed: int):
    """Lay a whole native settlement around (cx, cy) and return it.

    The settlement object keeps its own positions and people so the game can
    find them later; the actual blocks, plots, fireplace and NPCs are put into
    the world's own structures (built_blocks, world.plots, placed_work, and
    the people register).
    """
    rng = random.Random(seed & 0xFFFFFFFF)
    world = g.world
    now = float(getattr(g, "now", 0.0))

    temp = float(biomes.temperature(cx, cy, world.seed))
    hum = float(biomes.humidity(cx, cy, world.seed))
    food_kind, leaf_kind = biomes.crop_kinds(temp, hum)
    food_item = crop.FOOD_ITEM.get(food_kind, "bread")

    people = rng.randint(10, 15)
    n_warriors = max(2, int(round(people * 0.2)))
    n_farmers = people - n_warriors
    n_teepees = -(-people // PER_TEEPEE)      # ceil, two to a teepee

    # -- the teepee ring -----------------------------------------------------
    # spaced so a 5x5 (160 px) teepee never touches its neighbour, even after
    # the block anchoring rounds each teepee up to half a tile towards the
    # other. Seven tiles of chord and a floor of eight give clear lanes
    # between teepees whatever the headcount.
    chord = 7 * TILE
    ring = max(8.0, chord / max(0.001, 2.0 * math.sin(math.pi / n_teepees))
               / TILE)
    tp_centers = []
    for i in range(n_teepees):
        ang = i * 2.0 * math.pi / n_teepees
        tp_centers.append((cx + math.cos(ang) * ring * TILE,
                           cy + math.sin(ang) * ring * TILE))

    # -- the fields, past the teepees ---------------------------------------
    n_leaf = rng.randint(MIN_LEAF_FIELDS, MAX_LEAF_FIELDS)
    field_ring = (ring + 7.0) * TILE
    # FIELDS FACE INLAND (west), never east into the ocean: the coast runs
    # north-south just beside the spawn, so food and leaf lie in the half of
    # the ring that points away from the sea.
    food_angles = [math.radians(120.0), math.radians(180.0),
                   math.radians(240.0)]
    leaf_angles = [math.radians(90.0 + 180.0 * i) for i in range(n_leaf)]
    field_centers = []          # (x, y, kind)
    for ang in food_angles:
        field_centers.append((cx + math.cos(ang) * field_ring,
                              cy + math.sin(ang) * field_ring, food_kind))
    for ang in leaf_angles:
        field_centers.append((cx + math.cos(ang) * field_ring,
                              cy + math.sin(ang) * field_ring, leaf_kind))

    # -- MEASURE the layout, then clear that plus 30 blocks -----------------
    max_r = math.hypot(TILE, TILE)          # the fireplace itself
    for (wx, wy) in tp_centers:
        max_r = max(max_r, math.hypot(wx - cx, wy - cy) + 5 * TILE / 2.0)
    for (wx, wy, kind) in field_centers:
        half = (5 * TILE / 2.0) if kind == food_kind else (3 * TILE / 2.0)
        max_r = max(max_r, math.hypot(wx - cx, wy - cy) + half)
    clearance = max_r + CLEAR_BLOCKS * TILE
    _clear_trees(g, cx, cy, clearance)
    _clear_wild(g, cx, cy, clearance)
    _clear_ore(g, cx, cy, clearance)

    # -- the fireplace at the middle ----------------------------------------
    fire = industry.Workplace("fireplace", cx, cy, seed ^ 0xF1A)
    fire.native = True                      # a camp's fire, not the player's
    g.placed_work.append(fire)

    # -- the teepees, real blocks -------------------------------------------
    for (wx, wy) in tp_centers:
        tx = int(math.floor(wx / TILE)) - 2
        ty = int(math.floor(wy / TILE)) - 2
        for (tx2, ty2), kind in teepee_blocks(tx, ty).items():
            g.built_blocks[(tx2, ty2)] = kind

    # -- the fields, already growing ----------------------------------------
    field_centres_tiles = []
    for (wx, wy, kind) in field_centers:
        ctx = int(math.floor(wx / TILE))
        cty = int(math.floor(wy / TILE))
        span = 2 if kind == food_kind else 1
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                # never plant into the sea; the coast can wander in at a corner
                try:
                    if world.tile_kind(ctx + dx, cty + dy) == "ocean":
                        continue
                except Exception:
                    pass
                age = crop.GROW_SECONDS * rng.uniform(0.50, 1.05)
                world.set_plot(ctx + dx, cty + dy, kind, now - age)
        field_centres_tiles.append((ctx, cty, kind))

    # (The ground is rebuilt ONCE after every camp is placed -- see the caller
    # -- not per camp, which would clear and regenerate the world's chunks for
    # each settlement.)

    # -- the people ---------------------------------------------------------
    farmers = []
    warriors = []
    _name_pool = list(_NAMES)
    rng.shuffle(_name_pool)                 # each camp gets its own names
    _s = seed ^ 0x6E17
    for i in range(n_farmers):
        # a farmer stands between the teepees and his fields, and walks out to
        # work them
        ang = rng.uniform(0.0, 2.0 * math.pi)
        mid = (ring + 5.0) * TILE
        fx, fy = cx + math.cos(ang) * mid, cy + math.sin(ang) * mid
        n = village_mod.NPC(fx + rng.uniform(-40, 40),
                            fy + rng.uniform(-40, 40),
                            _s ^ (i * 2654435761),
                            name=_name_pool[i % len(_name_pool)],
                            npc_id="native_f_%d_%d" % (int(cx), i), role="Farmer")
        n.job = "farmer"
        n.native = True
        n.native_role = "farmer"
        n.stock[food_item] = 60
        n.home = (n.x, n.y)
        n.speed = rng.uniform(55.0, 80.0)
        n.wear = biomes.npc_wear(temp, hum)
        farmers.append(n)
        g._observe_npcs.append(n)             # drawn with the natives
    for i in range(n_warriors):
        # a warrior patrols a ring around the fire, watching out
        ang = rng.uniform(0.0, 2.0 * math.pi)
        wx = cx + math.cos(ang) * (TILE * 2.5)
        wy = cy + math.sin(ang) * (TILE * 2.5)
        n = village_mod.NPC(wx, wy, _s ^ ((i + 1000) * 2654435761),
                            name=_name_pool[(n_farmers + i) % len(_name_pool)],
                            npc_id="native_w_%d_%d" % (int(cx), i), role="Warrior")
        n.defender = True
        n.weapon = "axe"
        n.native = True
        n.native_role = "warrior"
        n.stock[food_item] = 60
        n.home = (n.x, n.y)
        n.speed = rng.uniform(60.0, 90.0)
        n._orbit = ang
        n.wear = biomes.npc_wear(temp, hum)
        warriors.append(n)
        g._observe_npcs.append(n)

    # the settlement, for anything that needs to find it later
    settlement = type("NativeSettlement", (), {
        "name": "Native settlement",
        "x": cx, "y": cy, "seed": seed,
        "people": people, "farmers": farmers, "warriors": warriors,
        "fireplace": fire, "teepees": tp_centers,
        "fields": field_centres_tiles,
        "food_kind": food_kind, "leaf_kind": leaf_kind,
        "clearance": clearance,
        "native": True,
    })()
    # They stay in the people register, so they are lived: they walk, work,
    # eat, and can fight. Tie each to his camp and give the farmers a field.
    for _n in farmers + warriors:
        _n.native_camp = settlement
        if _n.native_role == "farmer":
            _n._pick_field()
    return settlement


def ensure_near(g, px: float, py: float, radius: float = NATIVE_RADIUS):
    """Build a native settlement on every 20 km cell within `radius` of the
    player, once each. Returns the settlements made this call.

    The world is native now: as he walks west, camps of teepees and fields
    appear, about twenty kilometres apart, each a little off its lattice point.
    """
    reg = getattr(g, "native_settlements", None)
    if reg is None:
        reg = {}
        g.native_settlements = reg
    made = []
    _home = getattr(g, "native_settlement", None)
    x0 = int(math.floor((px - radius) / NATIVE_SPACING))
    x1 = int(math.floor((px + radius) / NATIVE_SPACING))
    y0 = int(math.floor((py - radius) / NATIVE_SPACING))
    y1 = int(math.floor((py + radius) / NATIVE_SPACING))
    for gy in range(y0, y1 + 1):
        for gx in range(x0, x1 + 1):
            if gx >= 0:
                continue                    # the ocean holds no camp
            if (gx, gy) in reg:
                continue
            cx, cy = native_center(gx, gy, g.world.seed)
            if math.hypot(cx - px, cy - py) > radius:
                continue
            # the home camp already stands on its own ground: do not build
            # another camp right on top of it
            if _home is not None and math.hypot(cx - _home.x, cy - _home.y) < NATIVE_SPACING * 0.4:
                continue
            _seed = ((gx * 73856093) ^ (gy * 19349663)
                     ^ (int(g.world.seed) * 2654435761)) & 0xFFFFFFFF
            ns = build(g, cx, cy, _seed)
            ns.cell = (gx, gy)
            reg[(gx, gy)] = ns
            made.append(ns)
    return made
