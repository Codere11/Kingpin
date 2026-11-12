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


def next_kind(kind: str, t: float, h: float) -> str:
    """The crop a field cycles to on the next click. Only what actually grows
    in that biome is offered -- no tobacco out of the snow, no agave in the
    temperate lands."""
    ks = crop.growable_kinds(t, h)
    if not ks:
        return "wheat"
    try:
        i = ks.index(kind)
    except ValueError:
        return ks[0]
    return ks[(i + 1) % len(ks)]


def first_kind(t: float, h: float) -> str:
    """The crop a brand-new field starts on: the biome's food crop."""
    ks = crop.growable_kinds(t, h)
    return ks[0] if ks else "wheat"


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
        "artisans": [],            # the conquered ARTISANS (on benches)
        "researchers": [],         # the conquered RESEARCHERS (at the bench)
        "miners": [],              # the conquered MINERS (iron in the snow)
        "smiths": [],              # the conquered SMITHS (iron bars at the forge)
        "weavers": [],             # the conquered WEAVERS (cotton to cloth at the loom)
        "gunsmiths": [],            # the conquered GUNSMITHS (guns at the forge)
        "unemployed": [],          # conquered, not assigned to a job
        "people": [],              # every conquered person (the pool)
        "animals": [],             # the conquered livestock (horses, bison)
        "_breeding": None,          # the active animal breeding event
        "_last_breed_day": -1,      # one animal birth per day
        "_breeding_people": None,   # the active people breeding event
        "_last_people_breed_day": -1,   # one baby per day
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


_BABY_NAMES = ("Awan", "Kiona", "Takoda", "Yuma", "Chenoa", "Migina",
               "Ohanzee", "Sikya", "Winona", "Elan", "Kohana", "Mato",
               "Nokomis", "Shilah", "Hania", "Kanti", "Lakota", "Mika",
               "Nita", "Onawa", "Peta", "Sakari", "Tala", "Uzumati")


def count_bedrolls(g) -> int:
    """Bedrolls within 500 blocks of the nearest fireplace (or the player).
    That count is the population's upper limit."""
    bb = getattr(g, "built_blocks", None) or {}
    ref = (float(getattr(g.player, "x", 0.0)), float(getattr(g.player, "y", 0.0)))
    for wp in getattr(g, "placed_work", ()) or ():
        if getattr(wp, "kind", "") == "fireplace":
            ref = (float(wp.x), float(wp.y))
            break
    n = 0
    for (tx, ty), kind in bb.items():
        if kind != "bed":
            continue
        wx = tx * 32 + 16.0
        wy = ty * 32 + 16.0
        if math.hypot(wx - ref[0], wy - ref[1]) <= 500 * 32:
            n += 1
    return n


def tick_people_breeding(g, dt: float) -> None:
    """People breed like the livestock: one baby a day, but only while there
    are more bedrolls than people. The parents face each other, eyes as hearts,
    and a baby is born between them that grows up over a day."""
    pc = getattr(g, "player_camp", None)
    if pc is None:
        return
    bedrolls = count_bedrolls(g)
    if bedrolls <= 0:
        return
    people = [p for p in (getattr(pc, "people", ()) or ())
              if getattr(p, "alive", True)]
    ev = getattr(pc, "_breeding_people", None)
    if ev is not None:
        a, b = ev["a"], ev["b"]
        if not (getattr(a, "alive", True) and getattr(b, "alive", True)):
            _end_people_breeding(pc)
            return
        ev["t"] -= dt
        if ev["t"] <= 0.0:
            _end_people_breeding(pc)
            _spawn_human_baby(g, a, b)
        return
    if len(people) >= bedrolls:
        return
    day = int(g.now / economy.DAY_LENGTH)
    if day <= getattr(pc, "_last_people_breed_day", -1):
        return
    adults = [p for p in people if not getattr(p, "baby", False)]
    fed = [p for p in adults if getattr(p, "hunger", 0.0) < economy.EAT_AT]
    if len(fed) < 2:
        return
    a, b = fed[0], fed[1]
    a.breeding = True
    a.breed_partner = b
    b.breeding = True
    b.breed_partner = a
    pc._breeding_people = {"a": a, "b": b, "t": 2.0}
    pc._last_people_breed_day = day


def _end_people_breeding(pc) -> None:
    ev = getattr(pc, "_breeding_people", None)
    if ev is not None:
        for x in (ev["a"], ev["b"]):
            x.breeding = False
            x.breed_partner = None
    pc._breeding_people = None


def _spawn_human_baby(g, a, b) -> None:
    """A newborn person, small, growing up over a day, with a name."""
    import random as _random
    import biomes as _bio
    import village as village_mod
    pc = getattr(g, "player_camp", None)
    if pc is None:
        return
    mx, my = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
    seed = (int(getattr(g.world, "seed", 1)) ^ int(float(getattr(g, "now", 0.0)) * 1000)
            ^ id(a)) & 0xFFFFFFFF
    baby = village_mod.NPC(mx, my, seed, name=_random.choice(_BABY_NAMES),
                           npc_id="baby_%d_%d" % (int(mx), int(my)), role="Child")
    baby.native = True
    baby.conquered = True
    baby.native_role = "unemployed"
    baby.native_camp = pc
    baby.baby = True
    baby.born_at = float(getattr(g, "now", 0.0))
    baby.home = (mx, my)
    baby.stock["bread"] = 20
    baby.speed = baby.rng.uniform(80.0, 100.0)
    try:
        _t = float(_bio.temperature(mx, my, int(getattr(g.world, "seed", 1))))
        _h = float(_bio.humidity(mx, my, int(getattr(g.world, "seed", 1))))
        baby.wear = _bio.npc_wear(_t, _h)
    except Exception:
        pass
    if baby not in pc.people:
        pc.people.append(baby)
    if baby not in getattr(g, "_observe_npcs", ()):
        g._observe_npcs.append(baby)
    _np = getattr(g, "_native_people", None)
    if _np is None:
        _np = []
        g._native_people = _np
    if baby not in _np:
        _np.append(baby)
    try:
        g.toast("A baby is born.")
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
        # A starter seed for every crop this biome grows, so his first field
        # can be anything -- chili and cotton included, not only wheat.
        try:
            import biomes as _biomes
            _seed0 = int(getattr(g.world, "seed", 1))
            _t = float(_biomes.temperature(native_camp.x, native_camp.y, _seed0))
            _h = float(_biomes.humidity(native_camp.x, native_camp.y, _seed0))
            for _k in crop.growable_kinds(_t, _h):
                _s = crop.CROP_SEED.get(_k)
                if _s:
                    n.stock[_s] = int(n.stock.get(_s, 0)) + 3
        except Exception:
            n.stock["wheat_seed"] = int(n.stock.get("wheat_seed", 0)) + 3
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
    # THE PLAYER NAMES HIS NEW SETTLEMENT: "Settlement 1", "Settlement 2",
    # and so on are the placeholders he can keep or type over.
    try:
        g.conquered_count = int(getattr(g, "conquered_count", 0)) + 1
        g.naming_camp = native_camp
        g.naming_text = ""
        g.naming_placeholder = "Settlement %d" % int(g.conquered_count)
        g.naming_open = True
    except Exception:
        pass


def sync_jobs(g) -> None:
    """Reassign every conquered person from the sign-post's counts: the first
    N farm, the next M log, the rest are unemployed. With no sign-post, all of
    them farm. Then plots are handed out one to a worker, and any bench with a
    chosen product takes an artisan from the unemployed pool."""
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
    n_artisan = int(getattr(sign, "artisans", 0) or 0) if sign is not None else 0
    n_researcher = int(getattr(sign, "researchers", 0) or 0) if sign is not None else 0
    n_miner = int(getattr(sign, "miners", 0) or 0) if sign is not None else 0
    n_smith = int(getattr(sign, "smiths", 0) or 0) if sign is not None else 0
    n_weaver = int(getattr(sign, "weavers", 0) or 0) if sign is not None else 0
    n_gunsmith = int(getattr(sign, "gunsmiths", 0) or 0) if sign is not None else 0
    camp.workers = []
    camp.loggers = []
    camp.artisans = []
    camp.researchers = []
    camp.miners = []
    camp.smiths = []
    camp.weavers = []
    camp.gunsmiths = []
    camp.unemployed = []
    for i, n in enumerate(people):
        n.orchard_plot = None
        n.farm_plot = None
        n.artisan_bench = None
        if i < n_farmer:
            n.native_role = "farmer"
            n.job = "farmer"
            camp.workers.append(n)
        elif i < n_farmer + n_logger:
            n.native_role = "logger"
            n.job = "logger"
            camp.loggers.append(n)
        elif i < n_farmer + n_logger + n_artisan:
            n.native_role = "artisan"
            n.job = "artisan"
            camp.artisans.append(n)
        elif i < n_farmer + n_logger + n_artisan + n_researcher:
            n.native_role = "researcher"
            n.job = "researcher"
            camp.researchers.append(n)
        elif i < n_farmer + n_logger + n_artisan + n_researcher + n_miner:
            n.native_role = "miner"
            n.job = "miner"
            camp.miners.append(n)
        elif i < n_farmer + n_logger + n_artisan + n_researcher + n_miner + n_smith:
            n.native_role = "smith"
            n.job = "smith"
            if getattr(n, "smith_product", None) is None:
                n.smith_product = "iron_bar"   # default: smelt ore into bars
            camp.smiths.append(n)
        elif i < n_farmer + n_logger + n_artisan + n_researcher + n_miner + n_smith + n_weaver:
            n.native_role = "weaver"
            n.job = "weaver"
            camp.weavers.append(n)
        elif i < n_farmer + n_logger + n_artisan + n_researcher + n_miner + n_smith + n_weaver + n_gunsmith:
            n.native_role = "gunsmith"
            n.job = "gunsmith"
            n.gunsmith_product = "musket"   # default: the only gun he can start with
            camp.gunsmiths.append(n)
        else:
            n.native_role = "unemployed"
            n.job = None
            camp.unemployed.append(n)
    sync_artisans(g)
    sync_camp(g)


def sync_artisans(g) -> None:
    """Pair each artisan (assigned on the sign-post) with a bench that has a
    chosen product. Benches with no product stay empty; artisans with no
    bench idle until one is built."""
    camp = getattr(g, "player_camp", None)
    if camp is None:
        return
    benches = [wp for wp in getattr(g, "placed_work", ()) or ()
               if getattr(wp, "kind", None) == "lab" and getattr(wp, "product", None)]
    for wp in benches:
        wp.artisan = None
    pool = list(getattr(camp, "artisans", ()) or ())
    for wp in benches:
        u = next((n for n in pool if getattr(n, "artisan_bench", None) is None), None)
        if u is None:
            break
        u.artisan_bench = wp
        wp.artisan = u


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
