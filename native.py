"""native.py -- NATIVE SETTLEMENTS: bedrolls and fields around a fireplace.

A native settlement is the one kind of settlement the new world has. It is a
fire in the middle, a ring of bedrolls, and fields of food and leaf laid out
past the bedrolls -- and nothing of the old world: no fence, no roads, no
gates, no searches. Just the people.

The bedrolls are real blocks, exactly as the player would lay them: one white
1x1 bedroll per person's place.
"""
from __future__ import annotations

import math
import random

import biomes
import crop
import industry
import village as village_mod
from world import TILE, coast_x


# a native camp is a small place: they sit about this far apart, shaken by a
# little jitter, and are generated this far around the player
NATIVE_SPACING = 20000.0      # ~20 km between camps, at full density
NATIVE_JITTER = 0.45          # fraction of the spacing, either way -- scattered
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
          "Mato", "Nokomis", "Odakota", "Shilah", "Hania", "Kanti",
          "Lakota", "Mika", "Nita", "Onawa", "Peta", "Sakari",
          "Tala", "Uzumati", "Wakanda", "Yansa", "Ahiga", "Chaska",
          "Dakota", "Enapay", "Honovi", "Istas", "Kitchi", "Lomasi",
          "Mona", "Nodin", "Ojinjintka", "Paytah", "Sahale", "Tahatan")


def spawn_starter_camps(g) -> list:
    """The first four camps, scattered at random around the spawn in its
    biome -- not on a ring."""
    reg = getattr(g, "native_settlements", None)
    if reg is None:
        reg = {}
        g.native_settlements = reg
    for _s in reg.values():
        if getattr(_s, "starter", False):
            return []
    px, py = float(g.player.x), float(g.player.y)
    seed = int(getattr(g.world, "seed", 1))
    rng = random.Random(seed ^ 0xB10C5)
    made = []
    for _ in range(600):
        if len(made) >= 4:
            break
        ang = rng.uniform(0.0, 2.0 * math.pi)
        r = rng.uniform(18000.0, 55000.0)
        cx = px + math.cos(ang) * r
        cy = py + math.sin(ang) * r
        if cx > coast_x(cy, seed):        # the ocean holds no camp
            continue
        if any(math.hypot(cx - s.x, cy - s.y) < 12000.0 for s in made):
            continue
        _seed = ((int(cx) * 73856093) ^ (int(cy) * 19349663)
                 ^ (seed * 2654435761)) & 0xFFFFFFFF
        ns = build(g, cx, cy, _seed)
        ns.starter = True
        ns.cell = None
        reg[("starter", len(made))] = ns
        made.append(ns)
    return made


def camp_positions(px: float, py: float, radius: float, seed: int) -> list:
    """Every native-camp POSITION within `radius` of (px, py), straight from
    the lattice. Markers only -- no settlement is built here. The full
    settlement (people, fields, trees) is built lazily by ensure_near when the
    player walks up to it."""
    out = []
    x0 = int(math.floor((px - radius) / NATIVE_SPACING))
    x1 = int(math.floor((px + radius) / NATIVE_SPACING))
    y0 = int(math.floor((py - radius) / NATIVE_SPACING))
    y1 = int(math.floor((py + radius) / NATIVE_SPACING))
    for gy in range(y0, y1 + 1):
        for gx in range(x0, x1 + 1):
            if gx >= 0:
                continue
            cx, cy = native_center(gx, gy, seed)
            if math.hypot(cx - px, cy - py) <= radius:
                out.append((cx, cy, gx, gy))
    return out


def native_center(gx: int, gy: int, seed: int):
    """A native camp's centre: a 20 km lattice, shaken by jitter."""
    code = (gx * 73856093) ^ (gy * 19349663) ^ (seed * 2654435761)
    rng = random.Random(code & 0xFFFFFFFF)
    jx = rng.uniform(-NATIVE_SPACING * NATIVE_JITTER, NATIVE_SPACING * NATIVE_JITTER)
    jy = rng.uniform(-NATIVE_SPACING * NATIVE_JITTER, NATIVE_SPACING * NATIVE_JITTER)
    return (gx + 0.5) * NATIVE_SPACING + jx, (gy + 0.5) * NATIVE_SPACING + jy


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
    # THE TWO SOLDIERS: one stays with the axe, the other takes the bow once
    # the war escalates.
    n_warriors = 2
    n_farmers = people - n_warriors
    n_teepees = -(-people // PER_TEEPEE)      # ceil, two to a bedroll

    # -- the bedroll ring ----------------------------------------------------
    # the same count and the same spacing as before, so the camp keeps its
    # shape; each bedroll is a single white 1x1 block now.
    chord = 7 * TILE
    ring = max(8.0, chord / max(0.001, 2.0 * math.sin(math.pi / n_teepees))
               / TILE)
    tp_centers = []
    for i in range(n_teepees):
        ang = i * 2.0 * math.pi / n_teepees
        tp_centers.append((cx + math.cos(ang) * ring * TILE,
                           cy + math.sin(ang) * ring * TILE))

    # -- the fields, past the bedrolls -------------------------------------
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
        max_r = max(max_r, math.hypot(wx - cx, wy - cy) + TILE / 2.0)
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

    # -- the bedrolls, one real block each ---------------------------------
    for (wx, wy) in tp_centers:
        tx = int(math.floor(wx / TILE))
        ty = int(math.floor(wy / TILE))
        g.built_blocks[(tx, ty)] = "bed"

    # -- the fields, already growing ----------------------------------------
    field_centres_tiles = []
    farm_plots = []
    farm_tiles = {}
    for (wx, wy, kind) in field_centers:
        ctx = int(math.floor(wx / TILE))
        cty = int(math.floor(wy / TILE))
        span = 2 if kind == food_kind else 1
        tiles = []
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
                tiles.append((ctx + dx, cty + dy, kind))
        field_centres_tiles.append((ctx, cty, kind))
        farm_plots.append((ctx, cty, kind))
        farm_tiles[(ctx, cty)] = tiles

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
        # a farmer starts right beside his assigned field, so he is working
        # within a second of the game starting, not walking 700 px to it
        _fi = i % max(1, len(farm_plots))
        _fx, _fy, _fk = (farm_plots[_fi] if farm_plots
                         else (int(cx // TILE), int(cy // TILE), food_kind))
        fx = _fx * TILE + TILE / 2.0 + rng.uniform(-48, 48)
        fy = _fy * TILE + TILE / 2.0 + rng.uniform(-48, 48)
        n = village_mod.NPC(fx, fy,
                            _s ^ (i * 2654435761),
                            name=_name_pool[i % len(_name_pool)],
                            npc_id="native_f_%d_%d" % (int(cx), i), role="Farmer")
        n.job = "farmer"
        n.native = True
        n.native_role = "farmer"
        n.stock[food_item] = 60
        n.stock["shovel"] = 1
        n.tool_uses = 100
        n.home = (n.x, n.y)
        n.speed = rng.uniform(95.0, 115.0)
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
        n.weapon = "bow" if _warrior_is_bow(g, i) else "axe"
        n.native = True
        n.native_role = "warrior"
        n.stock[food_item] = 60
        # A WARRIOR IS A SOLDIER: full wind, and half a lifetime's martial
        # skill already behind him.
        n.stamina = n.max_stamina
        n.skills.axe = 0.5
        n.skills.shooting = 0.5
        _alarms = int(getattr(g, "war_alarms", 0))
        if _alarms >= 4:
            _mount_warrior(n)
        elif _alarms >= 3:
            _max_out(n)
        n.home = (n.x, n.y)
        n.speed = rng.uniform(60.0, 90.0)
        n._orbit = ang
        n.wear = biomes.npc_wear(temp, hum)
        warriors.append(n)
        g._observe_npcs.append(n)

    # -- TAMED ANIMALS -------------------------------------------------------
    # A settlement in two keeps livestock: 25% horses, 25% buffaloes, and half
    # of all settlements keep none. They sleep on their own spots beside the
    # fields, never run from people, and a handler feeds them.
    animals = []
    # EXACTLY HALF of settlements keep livestock: 25% horses, 25% buffaloes,
    # and the other half none. A hash of the settlement's seed -- not a draw
    # from the camp's shared rng stream -- so it stays a clean 25/25/50.
    _h = seed
    _h ^= _h >> 13
    _h = (_h * 1274126177) & 0xFFFFFFFF
    _h ^= _h >> 16
    _roll = _h % 4
    if _roll in (0, 1):
        try:
            import creatures as _creatures
        except Exception:
            _creatures = None
        _is_horse = _roll == 0
        for i in range(rng.randint(2, 4)):
            ang = rng.uniform(0.0, 2.0 * math.pi)
            rr = field_ring + rng.uniform(-TILE * 3.0, TILE * 2.0)
            ax = cx + math.cos(ang) * rr
            ay = cy + math.sin(ang) * rr
            if _creatures is None:
                break
            if _is_horse:
                a = _creatures.Horse(ax, ay, rng.choice(('brown', 'black',
                                                         'white', 'palomino')))
                a.tamed = True
                a.g = g
                a.home = (ax, ay)
                if a not in getattr(g, "horses", ()):
                    g.horses.append(a)
            else:
                a = _creatures.Bison(ax, ay)
                a.tamed = True
                a.g = g
                a.home = (ax, ay)
                if a not in getattr(g, "enemies", ()):
                    g.enemies.append(a)
            animals.append(a)

    # the settlement, for anything that needs to find it later
    settlement = type("NativeSettlement", (), {
        "name": "Native settlement",
        "x": cx, "y": cy, "seed": seed,
        "people": people, "farmers": farmers, "warriors": warriors,
        "animals": animals, "handlers": [],
        "fireplace": fire, "bedrolls": tp_centers,
        "fields": field_centres_tiles,
        "food_kind": food_kind, "leaf_kind": leaf_kind,
        "clearance": clearance,
        # food plots AND leaf plots, and a plain store/ledger to hold the crop
        "farm_plots": farm_plots,
        "farm_tiles": farm_tiles,
        "ledger_goods": {food_item: 20},
        "ledger_lots": {},
        "ledger_grade": {},
        "_day": 0,
        "is_hub": False,
        "field_claims": {},
        "native": True,
        "g": g,          # the frame handle, for clearing trees/blocks/plants
    })()
    # They stay in the people register, so they are lived: they walk, work,
    # eat, and can fight. Each farmer has his own food plot to tend -- the
    # game's own _work_field decides what to do on it.
    for _n in farmers + warriors:
        _n.native_camp = settlement
    for _i, _n in enumerate(farmers):
        # ONE FIELD, ONE WORKER: the first farmers each take a plot, the rest
        # have no post and go idle (they chill and wander).
        _n.farm_plot = _i if _i < len(farm_plots) else None
    # A SETTLEMENT WITH LIVESTOCK KEEPS ONE HANDLER TO FEED THEM.
    if animals:
        hx = cx + rng.uniform(-TILE * 3.0, TILE * 3.0)
        hy = cy + rng.uniform(-TILE * 3.0, TILE * 3.0)
        hn = village_mod.NPC(hx, hy, _s ^ ((6000 + 1) * 2654435761),
                             name=_name_pool[(n_farmers + n_warriors) % len(_name_pool)],
                             npc_id="native_ah_%d" % int(cx), role="Animal Handler")
        hn.native = True
        hn.native_role = "animal_handler"
        hn.job = "animal_handler"
        hn.native_camp = settlement
        hn.stock[food_item] = 60
        hn.home = (hn.x, hn.y)
        hn.speed = rng.uniform(95.0, 115.0)
        hn.wear = biomes.npc_wear(temp, hum)
        settlement.handlers.append(hn)
        g._observe_npcs.append(hn)
    # The frame owns these people and walks them itself, whatever the worker
    # lanes are doing: they are not villagers of any town, so no lane claims
    # them.
    _np = getattr(g, "_native_people", None)
    if _np is None:
        _np = []
        g._native_people = _np
    for _n in farmers + warriors + settlement.handlers:
        if _n not in _np:
            _np.append(_n)
    return settlement


def _warrior_is_bow(g, i: int) -> bool:
    """Whether warrior i (0 = the first) carries a bow at this escalation.
    One alarm arms the second man; two alarms arm both of them."""
    alarms = int(getattr(g, "war_alarms", 0))
    if alarms >= 2:
        return True
    return alarms >= 1 and i == 1


def _max_out(w) -> None:
    """Third alarm: an axe warrior at the top of his craft, in hide armor
    that doubles his health."""
    if getattr(w, "hide_armor", False):
        return
    w.weapon = "axe"
    w.skills.axe = 1.0
    w.skills.shooting = 1.0
    w.stamina = float(getattr(w, "max_stamina", 30.0))
    w.hide_armor = True
    try:
        import stats as _stats
        w.max_health = int(round(_stats.body_for(w) * 2.0))
    except Exception:
        w.max_health = int(round(getattr(w, "max_health", 115) * 2.0))
    w.health = w.max_health


def _mount_warrior(w) -> None:
    """Fourth alarm: a maxed-out fighter rides a horse, in hide armor, with a
    bow. The horse is his legs -- double the stride -- and the bow keeps him
    at range."""
    _max_out(w)
    w.weapon = "bow"
    w.mounted = True
    w.base_speed = 150.0
    w.speed = 150.0


def _role_warriors(s, g) -> None:
    """Arm a settlement's warriors for the current alarm count: one alarm
    gives the second man a bow, two give both bows, three maxes both of them
    out as axe fighters in hide armour."""
    alarms = int(getattr(g, "war_alarms", 0))
    ws = getattr(s, "warriors", ()) or ()
    for i, w in enumerate(ws):
        if not getattr(w, "alive", True):
            continue
        if alarms >= 4:
            _mount_warrior(w)
        elif alarms >= 3:
            _max_out(w)
        else:
            w.weapon = "bow" if _warrior_is_bow(g, i) else "axe"


def escalate_war(g, exclude=None) -> None:
    """Each smoke alarm arms every OTHER settlement one step further. The
    camp that raised the alarm keeps its current weapons -- the player is
    standing in it, so its defence must not change mid-fight."""
    g.war_alarms = int(getattr(g, "war_alarms", 0)) + 1
    for s in getattr(g, "native_settlements", {}).values():
        if s is exclude:
            continue
        _role_warriors(s, g)


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


# -- NATIVE RAIDS ------------------------------------------------------------
# Once the Army is researched, the unconquered fight back. War parties march
# on the player's conquered settlements in this order:
#   1) settle on a settlement WITH soldiers -- avoid it
#   2) attack a conquered settlement without soldiers
#   3) if every settlement has soldiers, group up and hit the weakest, or a
#      cargo horse out on a run.

RAID_INTERVAL = 150.0        # seconds between raids, once Army is done
RAID_RADIUS = 700.0          # how near a soldier counts as defending the spot


def _conquered_camps(g):
    return [s for s in getattr(g, "native_settlements", {}).values()
            if getattr(s, "conquered", False)]


def _soldiers_near(g, x: float, y: float) -> int:
    n = 0
    for s in getattr(g, "_native_people", ()) or ():
        if (getattr(s, "alive", True)
                and getattr(s, "native_role", "") == "soldier"
                and (s.x - x) ** 2 + (s.y - y) ** 2 <= RAID_RADIUS * RAID_RADIUS):
            n += 1
    return n


def _cargo_horses(g):
    out = []
    for h in getattr(g, "horses", ()) or ():
        if (getattr(h, "conquered", False) and getattr(h, "alive", True)
                and (getattr(h, "delivering", False)
                     or getattr(h, "returning", False)
                     or getattr(h, "route", None) is not None)):
            out.append(h)
    return out


def _send_raiders(g, tx: float, ty: float, count: int = 3) -> None:
    """March a handful of warriors from unconquered settlements on (tx, ty)."""
    n = 0
    for s in getattr(g, "native_settlements", {}).values():
        if getattr(s, "conquered", False):
            continue
        for w in getattr(s, "warriors", ()) or ():
            if not getattr(w, "alive", True) or getattr(w, "raiding", False):
                continue
            w.raiding = True
            w.raid_target = (float(tx), float(ty))
            n += 1
            if n >= count:
                return
    if n == 0:
        # nothing left alive: no raid can form
        return


def _launch_raid(g) -> None:
    """Choose a target by the priority order and send the warriors."""
    pc = getattr(g, "player_camp", None)
    targets = []       # (obj, x, y, soldier_count)
    for c in _conquered_camps(g):
        targets.append((c, float(getattr(c, "x", 0.0)), float(getattr(c, "y", 0.0)),
                        _soldiers_near(g, getattr(c, "x", 0.0), getattr(c, "y", 0.0))))
    if pc is not None:
        px, py = float(getattr(pc, "x", 0.0)), float(getattr(pc, "y", 0.0))
        targets.append((pc, px, py, _soldiers_near(g, px, py)))
    if not targets:
        return
    player = getattr(g, "player", None)
    pdist = (lambda t: ((t[1] - player.x) ** 2 + (t[2] - player.y) ** 2)
             if player is not None else 0.0)
    # 1) attack a soldierless conquered settlement (nearest to the player)
    soldierless = [t for t in targets if t[3] == 0]
    if soldierless:
        t = min(soldierless, key=pdist)
        _send_raiders(g, t[1], t[2])
        return
    # 3) all have soldiers: hit a cargo horse out on a run, else the weakest
    horses = _cargo_horses(g)
    if horses:
        h = min(horses, key=lambda hh: ((hh.x - (player.x if player else 0.0)) ** 2
                                        + (hh.y - (player.y if player else 0.0)) ** 2))
        _send_raiders(g, h.x, h.y)
        return
    t = min(targets, key=lambda t: t[3])
    _send_raiders(g, t[1], t[2])


def tick_raids(g, dt: float) -> None:
    """The native counteroffensive: only once Army is researched."""
    try:
        import research
        if research.state(g, "army") != "done":
            return
    except Exception:
        return
    t = float(getattr(g, "_raid_timer", RAID_INTERVAL)) - float(dt)
    if t > 0.0:
        g._raid_timer = t
        return
    g._raid_timer = float(RAID_INTERVAL)
    try:
        _launch_raid(g)
    except Exception:
        pass
