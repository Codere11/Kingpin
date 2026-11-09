"""THE PLAYER'S OWN SETTLEMENT: conquered people and the fields they work.

`g.field_designations` is a list of dicts, one per designated field::

    {"rect": pygame.Rect (grid-aligned, world px), "kind": crop kind}

The player's camp object holds the same fields in the shape the farming
machinery already knows (`farm_plots` + `farm_tiles`), rebuilt by `sync_camp`
every time a field is added, deleted, or its crop type is changed.
"""
import math

import crop


def next_kind(kind: str) -> str:
    """The crop a field cycles to on the next click (bread is the base)."""
    ks = crop.FIELD_KINDS
    try:
        i = ks.index(kind)
    except ValueError:
        return ks[0]
    return ks[(i + 1) % len(ks)]


def make_camp(g) -> object:
    """The conquered camp: plain store/ledger + farm handles, no village."""
    camp = type("PlayerCamp", (), {
        "name": "Settlement",
        "x": float(getattr(g.player, "x", 0.0)),
        "y": float(getattr(g.player, "y", 0.0)),
        "farm_plots": [],          # [(ctx, cty, kind)] one entry per field
        "farm_tiles": {},          # (ctx, cty) -> [(tx, ty, kind)]
        "ledger_goods": {"bread": 20},
        "ledger_lots": {},
        "ledger_grade": {},
        "_day": 0,
        "is_hub": False,
        "native": True,
        "conquered": True,
        "g": g,                    # so a worker can clear trees/blocks/plants
        "workers": [],             # the conquered NPCs who farm these fields
    })()
    return camp


def sync_camp(g) -> None:
    """Rebuild the camp's farming handles from the current designations.

    One field = one plot = one worker (the same rule as the native camps).
    """
    camp = getattr(g, "player_camp", None)
    if camp is None:
        return
    plots = []
    tiles = {}
    for fd in g.field_designations:
        r = fd["rect"]
        kind = fd["kind"]
        ctx = int((r.x + r.w / 2.0) // 32)
        cty = int((r.y + r.h / 2.0) // 32)
        tx0 = int(r.x // 32)
        ty0 = int(r.y // 32)
        tx1 = int((r.x + r.w) // 32)
        ty1 = int((r.y + r.h) // 32)
        tl = []
        for tx in range(tx0, tx1):
            for ty in range(ty0, ty1):
                tl.append((tx, ty, kind))
        plots.append((ctx, cty, kind))
        tiles[(ctx, cty)] = tl
    camp.farm_plots = plots
    camp.farm_tiles = tiles
    for i, n in enumerate(camp.workers):
        n.farm_plot = i if i < len(plots) else None


def spawn_conquered(g, n: int = 3) -> None:
    """Three conquered farmers beside the player, his own field hands."""
    import biomes
    import village as village_mod
    camp = getattr(g, "player_camp", None)
    if camp is None:
        return
    if camp.workers:                     # already here
        return
    px, py = float(g.player.x), float(g.player.y)
    seed = int(getattr(g.world, "seed", 1))
    temp = float(biomes.temperature(px, py, seed))
    hum = float(biomes.humidity(px, py, seed))
    _s = seed ^ 0xC0FFEE
    for i in range(n):
        # inland (west) of the player, in a loose line: the coast runs
        # north-south right beside the spawn, so east would be the sea.
        fx = px - 90.0 - i * 45.0
        fy = py + (i - 1) * 55.0
        npc = village_mod.NPC(fx, fy, _s ^ (i * 2654435761),
                              name="Conquered %d" % (i + 1),
                              npc_id="conquered_%d" % i, role="Farmer")
        npc.native = True
        npc.native_role = "farmer"
        npc.conquered = True
        npc.job = "farmer"
        npc.native_camp = camp
        npc.stock["bread"] = 60
        npc.stock["shovel"] = 1
        npc.tool_uses = 100
        npc.speed = npc.rng.uniform(95.0, 115.0)
        npc.wear = biomes.npc_wear(temp, hum)
        npc.home = (npc.x, npc.y)
        camp.workers.append(npc)
        if npc not in getattr(g, "_observe_npcs", ()):
            g._observe_npcs.append(npc)
        _np = getattr(g, "_native_people", None)
        if _np is None:
            _np = []
            g._native_people = _np
        if npc not in _np:
            _np.append(npc)
    sync_camp(g)
