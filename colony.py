"""THE PLAYER'S OWN SETTLEMENT: conquered people and the ground they work.

`g.field_designations` is a list of dicts, one per designation::

    {"rect": Rect, "type": "field",    "kind": crop}    a crop field
    {"rect": Rect, "type": "orchard"}                    a tree orchard

The camp object keeps two sets of farming handles:

  * fields   -> `farm_plots` + `farm_tiles`  (worked by farmers)
  * orchards -> `orchard_plots` + `orchard_tiles` + `orchard_state`
                (worked by loggers)

`sync_camp` rebuilds all of them from the designations every time a field or
orchard is added, deleted, resized or has its crop changed.
"""
import math

import crop
import economy


def next_kind(kind: str) -> str:
    """The crop a field cycles to on the next click (bread is the base)."""
    ks = crop.FIELD_KINDS
    try:
        i = ks.index(kind)
    except ValueError:
        return ks[0]
    return ks[(i + 1) % len(ks)]


def make_camp(g) -> object:
    """The conquered camp: plain store/ledger + field/orchard handles."""
    camp = type("PlayerCamp", (), {
        "name": "Settlement",
        "x": float(getattr(g.player, "x", 0.0)),
        "y": float(getattr(g.player, "y", 0.0)),
        "farm_plots": [],          # [(ctx, cty, kind)] one entry per field
        "farm_tiles": {},          # (ctx, cty) -> [(tx, ty, kind)]
        "orchard_plots": [],       # [(ctx, cty)] one entry per orchard
        "orchard_tiles": {},       # (ctx, cty) -> [(tx, ty)]
        "orchard_state": {},       # (tx, ty) -> {"tree": Tree, "target_r": float}
        "ledger_goods": {"bread": 20},
        "ledger_lots": {},
        "ledger_grade": {},
        "_day": 0,
        "is_hub": False,
        "native": True,
        "conquered": True,
        "g": g,                    # so a worker can clear trees/blocks/plants
        "workers": [],             # the conquered FARMERS
        "loggers": [],             # the conquered LOGGERS
        "unemployed": [],          # conquered, not assigned to a job
        "people": [],              # every conquered person (the pool)
        "animals": [],             # the conquered livestock (horses, bison)
        "_breeding": None,          # the active breeding event
        "_last_breed_day": -1,      # one birth per day
    })()
    return camp


def _tiles_of(rect, kind=None):
    """Every 1x1 tile of a grid-aligned rect, with the centre tile first."""
    tx0 = int(rect.x // 32)
    ty0 = int(rect.y // 32)
    tx1 = int((rect.x + rect.w) // 32)
    ty1 = int((rect.y + rect.h) // 32)
    ctx = int((rect.x + rect.w / 2.0) // 32)
    cty = int((rect.y + rect.h / 2.0) // 32)
    tiles = [(tx, ty) for ty in range(ty0, ty1) for tx in range(tx0, tx1)]
    return (ctx, cty), tiles


def sync_camp(g) -> None:
    """Rebuild the camp's farming handles from the current designations.

    One field = one farmer; one orchard = one logger. Extra workers idle.
    """
    camp = getattr(g, "player_camp", None)
    if camp is None:
        return
    plots = []
    tiles = {}
    orchards = []
    orchard_tiles = {}
    for fd in g.field_designations:
        r = fd["rect"]
        if fd.get("type") == "orchard":
            (ctx, cty), tl = _tiles_of(r)
            orchards.append((ctx, cty))
            orchard_tiles[(ctx, cty)] = tl
        else:
            kind = fd.get("kind", "wheat")
            (ctx, cty), tl = _tiles_of(r, kind)
            plots.append((ctx, cty, kind))
            tiles[(ctx, cty)] = [(tx, ty, kind) for (tx, ty) in tl]
    camp.farm_plots = plots
    camp.farm_tiles = tiles
    camp.orchard_plots = orchards
    camp.orchard_tiles = orchard_tiles
    # prune orchard trees that are no longer inside a designated orchard
    keep_tiles = {t for tl in orchard_tiles.values() for t in tl}
    for key in [k for k in camp.orchard_state if k not in keep_tiles]:
        _drop_tree(camp, key)
    # ONE WORKER, ONE PLOT
    for i, n in enumerate(camp.workers):
        n.farm_plot = i if i < len(plots) else None
    for i, n in enumerate(camp.loggers):
        n.orchard_plot = i if i < len(orchards) else None


def tick_breeding(g, dt: float) -> None:
    """The livestock multiply: one baby a day, but only while there are more
    food boxes than animals (one box = one animal). The parents need to be
    fully fed, and they face each other with hearts before the newborn comes."""
    pc = getattr(g, "player_camp", None)
    if pc is None:
        return
    boxes = getattr(g, "built_foodboxes", None) or ()
    if not boxes:
        return
    animals = [a for a in (getattr(pc, "animals", ()) or ())
               if getattr(a, "alive", True)]
    capacity = len(boxes)
    # AN ACTIVE BREEDING EVENT: run its clock, then the newborn arrives.
    ev = getattr(pc, "_breeding", None)
    if ev is not None:
        a, b = ev["a"], ev["b"]
        if not (getattr(a, "alive", True) and getattr(b, "alive", True)):
            _end_breeding(pc)
            return
        ev["t"] -= dt
        if ev["t"] <= 0.0:
            _end_breeding(pc)
            _spawn_baby(g, a, b)
        return
    # NO ROOM: one food box feeds exactly one animal.
    if len(animals) >= capacity:
        return
    # ONE BIRTH PER DAY.
    day = int(g.now / economy.DAY_LENGTH)
    if day <= getattr(pc, "_last_breed_day", -1):
        return
    adults = [a for a in animals if not getattr(a, "baby", False)]
    fed = [a for a in adults if getattr(a, "hunger", 0.0) < economy.EAT_AT]
    if len(fed) < 2:
        return
    a, b = fed[0], fed[1]
    a.breeding = True
    a.breed_partner = b
    b.breeding = True
    b.breed_partner = a
    pc._breeding = {"a": a, "b": b, "t": 2.0}
    pc._last_breed_day = day


def _end_breeding(pc) -> None:
    ev = getattr(pc, "_breeding", None)
    if ev is not None:
        for x in (ev["a"], ev["b"]):
            x.breeding = False
            x.breed_partner = None
    pc._breeding = None


def _spawn_baby(g, a, b) -> None:
    """A newborn of the parents' kind, small, growing up over a day."""
    pc = getattr(g, "player_camp", None)
    if pc is None:
        return
    import creatures as _creatures
    mx, my = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
    if type(a).__name__ == "Horse":
        baby = _creatures.Horse(mx, my, getattr(a, "coat", "brown"))
        if baby not in getattr(g, "horses", ()):
            g.horses.append(baby)
    else:
        baby = _creatures.Bison(mx, my)
        if baby not in getattr(g, "enemies", ()):
            g.enemies.append(baby)
    baby.baby = True
    baby.born_at = float(getattr(g, "now", 0.0))
    baby.tamed = True
    baby.conquered = True
    baby.g = g
    baby.home = (mx, my)
    if baby not in pc.animals:
        pc.animals.append(baby)
    try:
        g.toast("A new %s is born." % ("foal" if type(a).__name__ == "Horse" else "calf"))
    except Exception:
        pass


def conquer_camp(g, native_camp) -> None:
    """All of a native camp's warriors are dead: the camp is the player's now.
    Its farmers join his pool of conquered people; the sign-post (or a plain
    default) decides how many of them farm, log, or go unemployed."""
    if getattr(native_camp, "conquered", False):
        return
    native_camp.conquered = True
    pc = getattr(g, "player_camp", None)
    if pc is None:
        return
    for n in (getattr(native_camp, "farmers", ()) or ()):
        if not getattr(n, "alive", True):
            continue
        n.conquered = True
        n.native_camp = pc
        n._log_tree = None
        n.orchard_plot = None
        n.farm_plot = None
        n.stock["wheat_seed"] = n.stock.get("wheat_seed", 0) + 3
        if n not in pc.people:
            pc.people.append(n)
    # THE LIVESTOCK ARE HIS TOO: a conquered horse carries goods to the ship.
    for a in (getattr(native_camp, "animals", ()) or ()):
        if getattr(a, "alive", True):
            a.conquered = True
            a.g = g
            if a not in getattr(pc, "animals", ()):
                pc.animals.append(a)
    try:
        sync_jobs(g)
    except Exception:
        pass
    try:
        g.toast("The settlement is yours.")
    except Exception:
        pass


def sync_jobs(g) -> None:
    """Reassign every conquered person from the sign-post's counts: the first
    N farm, the next M log, the rest are unemployed. With no sign-post, all of
    them farm. Then plots are handed out one to a worker."""
    camp = getattr(g, "player_camp", None)
    if camp is None:
        return
    people = list(getattr(camp, "people", ()) or ())
    sign = None
    for s in getattr(g, "built_signs", ()) or ():
        sign = s
        break
    n_farmer = int(getattr(sign, "farmers", 0) or 0) if sign is not None else len(people)
    n_logger = int(getattr(sign, "loggers", 0) or 0) if sign is not None else 0
    camp.workers = []
    camp.loggers = []
    camp.unemployed = []
    for i, n in enumerate(people):
        n.orchard_plot = None
        n.farm_plot = None
        if i < n_farmer:
            n.native_role = "farmer"
            n.job = "farmer"
            camp.workers.append(n)
        elif i < n_farmer + n_logger:
            n.native_role = "logger"
            n.job = "logger"
            camp.loggers.append(n)
        else:
            n.native_role = "unemployed"
            n.job = None
            camp.unemployed.append(n)
    sync_camp(g)


def _drop_tree(camp, key) -> None:
    """Remove an orchard tree from the world and the state (no stump)."""
    st = camp.orchard_state.pop(key, None)
    tree = st.get("tree") if st else None
    if tree is None:
        return
    g = getattr(camp, "g", None)
    trees = getattr(g, "trees", None)
    planted = getattr(trees, "_planted", None) if trees is not None else None
    if planted is not None:
        try:
            planted.remove(tree)
        except ValueError:
            pass


def spawn_conquered(g, farmers: int = 3, loggers: int = 2) -> None:
    """Conquered field hands beside the player: farmers for fields, loggers
    for orchards."""
    import biomes
    import village as village_mod
    camp = getattr(g, "player_camp", None)
    if camp is None:
        return
    if camp.workers or camp.loggers:       # already here
        return
    px, py = float(g.player.x), float(g.player.y)
    seed = int(getattr(g.world, "seed", 1))
    temp = float(biomes.temperature(px, py, seed))
    hum = float(biomes.humidity(px, py, seed))
    _s = seed ^ 0xC0FFEE
    # inland (west) of the player, in a loose line: the coast runs north-south
    # right beside the spawn, so east would be the sea.
    for i in range(farmers):
        fx = px - 90.0 - i * 45.0
        fy = py + (i - 1) * 55.0
        n = village_mod.NPC(fx, fy, _s ^ (i * 2654435761),
                            name="Conquered %d" % (i + 1),
                            npc_id="conquered_%d" % i, role="Farmer")
        n.native = True
        n.native_role = "farmer"
        n.conquered = True
        n.job = "farmer"
        n.native_camp = camp
        n.stock["bread"] = 60
        n.stock["shovel"] = 1
        n.stock["wheat_seed"] = 5        # to sow his first field
        n.tool_uses = 100
        n.speed = n.rng.uniform(95.0, 115.0)
        n.wear = biomes.npc_wear(temp, hum)
        n.home = (n.x, n.y)
        camp.workers.append(n)
        if n not in getattr(g, "_observe_npcs", ()):
            g._observe_npcs.append(n)
        _np = getattr(g, "_native_people", None)
        if _np is None:
            _np = []
            g._native_people = _np
        if n not in _np:
            _np.append(n)
    for i in range(loggers):
        fx = px - 90.0 - (farmers + i) * 45.0
        fy = py + (i - 1) * 55.0
        n = village_mod.NPC(fx, fy, _s ^ ((1000 + i) * 2654435761),
                            name="Logger %d" % (i + 1),
                            npc_id="conquered_log_%d" % i, role="Logger")
        n.native = True
        n.native_role = "logger"
        n.conquered = True
        n.job = "logger"
        n.native_camp = camp
        n.orchard_plot = None
        n.stock["bread"] = 60
        n.stock["axe"] = 1
        n.tool_uses = 100
        n.speed = n.rng.uniform(95.0, 115.0)
        n.wear = biomes.npc_wear(temp, hum)
        n.home = (n.x, n.y)
        camp.loggers.append(n)
        if n not in getattr(g, "_observe_npcs", ()):
            g._observe_npcs.append(n)
        _np = getattr(g, "_native_people", None)
        if _np is None:
            _np = []
            g._native_people = _np
        if n not in _np:
            _np.append(n)
    sync_camp(g)
