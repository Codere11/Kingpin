"""animals.py -- horses, bison, wolves and rabbits.

Only the live creatures the game actually walks are written.  A horse's saddle
bags, a conquered horse's route, a camp's livestock and a newborn's age all
survive; the class-level herds are rebuilt on load instead of being saved.
"""

from __future__ import annotations

from . import codec
from . import context as _context

SKIP = {
    "g", "pack", "uid", "refs", "save_class", "route", "breed_partner", "escort_soldier",
    "knows", "known_since", "news", "_tier_epoch", "_shadow",
    "hit_flash", "drip_timer", "flee_timer", "graze_timer", "lunge_cd",
    "fire_cd", "hop_timer", "strafe_timer", "phase", "bleed",
    "reload_timer", "aware_timer", "pause", "_rects", "_fences",
    "_player", "_soldiers", "_blood", "_target", "_colliders", "knows",
    "witness_to", "news",
}


def snapshot(a) -> dict:
    data = codec.dump_fields(a, skip=SKIP, label=type(a).__name__)
    data["uid"] = codec.uid(a, "animal")
    data["save_class"] = type(a).__name__
    data["pack"] = codec.inventory_to_data(getattr(a, "pack", None))
    data["refs"] = {
        "breed": codec.idref(getattr(a, "breed_partner", None), "animal"),
        "escort": codec.idref(getattr(a, "escort_soldier", None), "animal"),
    }
    route = getattr(a, "route", None)
    if isinstance(route, dict):
        def _route_ref(obj):
            if isinstance(obj, str):
                return obj
            return codec.idref(obj, "camp")
        data["route"] = {
            "origin": _route_ref(route.get("origin")),
            "dest": _route_ref(route.get("dest")),
            "item_a": route.get("item_a"),
            "item_b": route.get("item_b"),
            "amount": route.get("amount"),
        }
    return data


def _make(kind: str, x: float, y: float, rec: dict):
    import creatures
    if kind == "Horse":
        return creatures.Horse(x, y, rec.get("coat", "brown"))
    if kind == "Bison":
        return creatures.Bison(x, y)
    if kind == "Wolf":
        return creatures.Wolf(x, y, rec.get("species", "wolf"))
    if kind == "Rabbit":
        return creatures.Rabbit(x, y, rec.get("fur", "grey"))
    return None


def restore(rec: dict, ctx: "_context.Context"):
    kind = rec.get("save_class", "")
    obj = _make(kind, float(rec.get("x", 0.0)), float(rec.get("y", 0.0)), rec)
    if obj is None:
        return None
    codec.set_uid(obj, rec.get("uid"))
    codec.load_fields(obj, rec, skip=SKIP)
    if rec.get("pack"):
        inv = getattr(obj, "pack", None)
        if inv is None:
            from inventory import Inventory
            inv = obj.pack = Inventory(32)
        codec.inventory_restore(inv, rec["pack"])
    refs = rec.get("refs") or {}
    ctx.animals[rec["uid"]] = obj
    ctx.later(lambda: _resolve(obj, refs, ctx))
    route = rec.get("route")
    if route:
        ctx.later(lambda: _resolve_route(obj, route, ctx))
    return obj


def _resolve_route(obj, route: dict, ctx: "_context.Context") -> None:
    origin = route.get("origin")
    dest = route.get("dest")
    if origin != "ship":
        origin = ctx.camps.get(origin or "")
    if dest != "ship":
        dest = ctx.camps.get(dest or "")
    if origin is None or dest is None:
        obj.route = None
        return
    obj.route = {
        "origin": origin, "dest": dest,
        "item_a": route.get("item_a"),
        "item_b": route.get("item_b"),
        "amount": route.get("amount"),
    }


def _resolve(obj, refs: dict, ctx: "_context.Context") -> None:
    breed = (ctx.animals.get(refs.get("breed") or "")
             or ctx.people.get(refs.get("breed") or ""))
    if breed is not None:
        obj.breed_partner = breed
    esc = ctx.animals.get(refs.get("escort") or "")
    if esc is not None:
        obj.escort_soldier = esc


def snapshot_all(g) -> list:
    out = []
    seen = set()
    for src in (getattr(g, "horses", ()), getattr(g, "enemies", ()),
                getattr(g, "rabbits", ())):
        for a in list(src or ()):
            if type(a).__name__ not in ("Horse", "Bison", "Wolf", "Rabbit"):
                continue          # a legacy Soldier/Patrol is not the game
            key = id(a)
            if key in seen:
                continue
            seen.add(key)
            out.append(snapshot(a))
    return out


def restore_all(g, records, ctx: "_context.Context") -> None:
    import creatures
    # Keep the list objects: world.enemies and other handles point at them.
    g.horses[:] = []
    g.enemies[:] = []
    g.rabbits[:] = []
    creatures.Horse.HORSES[:] = []
    try:
        creatures.Bison.BISONS[:] = []
    except Exception:
        pass
    for rec in records or ():
        obj = restore(rec, ctx)
        if obj is None:
            continue
        kind = rec.get("save_class")
        if kind == "Horse":
            g.horses.append(obj)
        elif kind == "Rabbit":
            g.rabbits.append(obj)
        else:
            g.enemies.append(obj)
        try:
            obj.g = g
        except Exception:
            pass
    try:
        creatures.Horse.HORSES[:] = [h for h in g.horses
                                     if getattr(h, "alive", True)]
    except Exception:
        pass
