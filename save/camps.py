"""camps.py -- the native settlements: people, jobs, fields, ledgers, animals.

This is the spine of the game, and the part the old save never wrote at all.
A camp's chunk is self-contained: its own state, its people, every assignment,
its orchards and its livestock.  Camps are rebuilt at the positions and seeds
recorded in the manifest, so a reload lays out the same fireplace on the same
ground, then overlays the saved state on it.
"""

from __future__ import annotations

import math

from . import codec
from . import context as _context
from . import people as people_mod
from . import store

JOB_LISTS = ("workers", "loggers", "artisans", "researchers", "doctors",
             "miners", "smiths", "weavers", "spicemen", "gunsmiths",
             "unemployed", "farmers", "warriors", "handlers")

SKIP = {
    "g", "fireplace", "people", "people_count", "animals",
    "orchard_state", "_breeding", "_breeding_people",
    "farm_tiles", "orchard_tiles", "ledger_lots", "_save_uid", "_save_key", "_saved",
    "farmers", "warriors", "handlers", "workers", "loggers", "artisans",
    "researchers", "doctors", "miners", "smiths", "weavers", "spicemen",
    "gunsmiths", "unemployed",
}


def registry_key(key) -> str:
    """A JSON-safe name for a native_settlements key."""
    if key == "home":
        return "home"
    if isinstance(key, tuple):
        if len(key) == 2 and key[0] == "starter":
            return "starter:%d" % int(key[1])
        if len(key) == 2:
            return "cell:%d:%d" % (int(key[0]), int(key[1]))
    return "other:%s" % (key,)


def unregistry_key(key: str):
    if key == "home":
        return "home"
    if key.startswith("starter:"):
        return ("starter", int(key.split(":", 1)[1]))
    if key.startswith("cell:"):
        _, gx, gy = key.split(":")
        return (int(gx), int(gy))
    return key


def _camp_people(camp) -> list:
    seen = set()
    out = []
    pool = []
    for name in JOB_LISTS:
        value = getattr(camp, name, None)
        if isinstance(value, list):
            pool.extend(value)
    if isinstance(getattr(camp, "people", None), list):
        pool.extend(camp.people)
    for n in pool:
        if id(n) in seen:
            continue
        seen.add(id(n))
        out.append(n)
    return out


def snapshot(camp, key) -> tuple[dict, dict]:
    uid = codec.uid(camp, "camp")
    persons = _camp_people(camp)
    lists = {}
    for name in JOB_LISTS:
        value = getattr(camp, name, None)
        if isinstance(value, list):
            lists[name] = [codec.uid(n, "person") for n in value]
    # A CONQUERED CAMP'S POOL IS A LIST; AN UNCONQUERED ONE'S IS A COUNT.
    # The pool drives breeding and is not one of the job rosters above.
    if isinstance(getattr(camp, "people", None), list):
        lists["people"] = [codec.uid(n, "person") for n in camp.people]

    state = codec.dump_fields(camp, skip=SKIP, label="Camp")
    state.pop("people", None)
    if isinstance(getattr(camp, "people", None), int):
        state["people_count"] = int(camp.people)

    farm_tiles = []
    for (ctx_, cty_), tiles in (getattr(camp, "farm_tiles", {}) or {}).items():
        farm_tiles.append([int(ctx_), int(cty_),
                           [[int(t[0]), int(t[1]), str(t[2])] for t in tiles]])
    orchard_tiles = []
    for (ctx_, cty_), tiles in (getattr(camp, "orchard_tiles", {}) or {}).items():
        orchard_tiles.append([int(ctx_), int(cty_),
                              [[int(t[0]), int(t[1])] for t in tiles]])

    orchard = {}
    for (tx, ty), st in (getattr(camp, "orchard_state", {}) or {}).items():
        tree = (st or {}).get("tree")
        orchard["%d,%d" % (int(tx), int(ty))] = {
            "tree": codec.idref(tree, "tree"),
            "target_r": float((st or {}).get("target_r", 72.0)),
            "planted_at": float((st or {}).get("planted_at", 0.0)),
        }

    lots = []
    for item, grades in (getattr(camp, "ledger_lots", {}) or {}).items():
        for grade, count in (grades or {}).items():
            lots.append([str(item), int(grade), int(count)])

    breeding = getattr(camp, "_breeding", None)
    if breeding:
        breeding = {"a": codec.idref(breeding.get("a"), "animal"),
                    "b": codec.idref(breeding.get("b"), "animal"),
                    "t": float(breeding.get("t", 0.0))}
    breeding_people = getattr(camp, "_breeding_people", None)
    if breeding_people:
        breeding_people = {"a": codec.idref(breeding_people.get("a"), "person"),
                           "b": codec.idref(breeding_people.get("b"), "person"),
                           "t": float(breeding_people.get("t", 0.0))}

    meta = {
        "uid": uid,
        "key": registry_key(key),
        "kind": ("home" if key == "home"
                 else "starter" if getattr(camp, "starter", False)
                 else "cell" if getattr(camp, "cell", None) else "other"),
        "x": float(getattr(camp, "x", 0.0)),
        "y": float(getattr(camp, "y", 0.0)),
        "seed": int(getattr(camp, "seed", 0)),
        "cell": (list(camp.cell) if getattr(camp, "cell", None) else None),
        "starter": bool(getattr(camp, "starter", False)),
        "chunk": "camps/%s.json" % uid.replace(":", "_"),
    }
    body = {
        "state": state,
        "farm_tiles": farm_tiles,
        "orchard_tiles": orchard_tiles,
        "orchard_state": orchard,
        "ledger_lots": lots,
        "breeding": breeding,
        "breeding_people": breeding_people,
        "lists": lists,
        "people": [people_mod.snapshot(n) for n in persons],
        "animals": [codec.uid(a, "animal")
                    for a in (getattr(camp, "animals", ()) or ())],
    }
    return meta, body


# -- prepare: build the camp shells, before the state is applied -------------
def prepare(g, manifest: dict, chunks: dict, ctx: "_context.Context") -> None:
    import native as native_mod
    import world as world_mod

    saved = manifest.get("camps") or []
    for meta in saved:
        key = unregistry_key(meta["key"])
        if key in g.native_settlements:
            continue
        try:
            # A SAVED CAMP IS REBUILT, NOT FOUNDED: keep the orchard trees
            # and stumps the terrain provider has just restored.
            camp = native_mod.build(g, float(meta["x"]), float(meta["y"]),
                                    int(meta["seed"]),
                                    clear_planted=False, clear_stumps=False)
        except Exception as exc:
            store.log("camp prepare FAILED %s: %r" % (meta.get("key"), exc))
            continue
        codec.set_uid(camp, meta.get("uid"))
        camp._save_key = meta["key"]
        camp.cell = tuple(meta["cell"]) if meta.get("cell") else None
        camp.starter = bool(meta.get("starter", False))
        g.native_settlements[key] = camp
        if key == "home":
            g.native_settlement = camp
        if meta.get("uid"):
            ctx.camps[meta["uid"]] = camp

    # A world that has never had a home camp gets one at the old landing.
    if "home" not in g.native_settlements:
        try:
            nseed = (int(g.world.seed) ^ 0x7E7E) & 0xFFFFFFFF
            hx = world_mod.coast_x(g.player.y, g.world.seed) - 300 * 32.0
            camp = native_mod.build(g, hx, g.player.y, nseed)
            camp.cell = None
            g.native_settlements["home"] = camp
            g.native_settlement = camp
            ctx.camps[codec.uid(camp, "camp")] = camp
        except Exception:
            pass

    # And every lattice camp inside the simulated distance that the save has
    # never seen is generated now, exactly as a fresh world would generate it.
    try:
        native_mod.ensure_near(g, g.player.x, g.player.y,
                               native_mod.NATIVE_RADIUS)
    except Exception:
        pass
    # Starter camps are four special camps with their own seeds; a save from
    # this build has them, a new game builds them in the caller.
    if not any(getattr(s, "starter", False)
               for s in g.native_settlements.values()):
        try:
            native_mod.spawn_starter_camps(g)
        except Exception:
            pass


# -- apply the saved state ---------------------------------------------------
def _restore_people_breeding(camp, ev, ctx) -> None:
    a = ctx.people.get(ev.get("a") or "")
    b = ctx.people.get(ev.get("b") or "")
    if a is not None and b is not None:
        camp._breeding_people = {"a": a, "b": b,
                                "t": float(ev.get("t", 0.0))}
    else:
        camp._breeding_people = None


def apply(g, manifest: dict, chunks: dict, ctx: "_context.Context") -> None:
    saved = manifest.get("camps") or []
    by_key = {registry_key(k): v for k, v in g.native_settlements.items()}
    for meta in saved:
        camp = ctx.camps.get(meta.get("uid") or "")
        if camp is None:
            camp = by_key.get(meta.get("key"))
        if camp is None:
            continue
        body = chunks.get(meta.get("chunk") or "") or {}
        codec.set_uid(camp, meta.get("uid"))
        camp._save_key = meta.get("key")
        camp.cell = tuple(meta["cell"]) if meta.get("cell") else None
        camp.starter = bool(meta.get("starter", False))
        if not hasattr(camp, "farm_tiles"):
            camp.farm_tiles = {}
        if not hasattr(camp, "orchard_tiles"):
            camp.orchard_tiles = {}
        if not hasattr(camp, "orchard_state"):
            camp.orchard_state = {}

        codec.load_fields(camp, body.get("state"), skip=SKIP)
        if "people_count" in body.get("state", {}):
            try:
                camp.people = int(body["state"]["people_count"])
            except Exception:
                pass

        camp.farm_tiles = {
            (int(rec[0]), int(rec[1])): [(int(t[0]), int(t[1]), str(t[2]))
                                         for t in (rec[2] or ())]
            for rec in (body.get("farm_tiles") or ())
        }
        camp.orchard_tiles = {
            (int(rec[0]), int(rec[1])): [(int(t[0]), int(t[1]))
                                         for t in (rec[2] or ())]
            for rec in (body.get("orchard_tiles") or ())
        }
        camp.ledger_lots = {}
        for item, grade, count in (body.get("ledger_lots") or ()):
            camp.ledger_lots.setdefault(str(item), {})[int(grade)] = int(count)

        # The people: match the deterministic camp's own people first, create
        # only the ones the rebuilt camp did not produce (babies, survivors).
        pool = _camp_people(camp) + list(getattr(g, "_native_people", ()) or ())
        restored = []
        seen = set()
        for rec in body.get("people", ()) or ():
            ident = rec.get("uid")
            n = ctx.people.get(ident or "")
            if n is None:
                for cand in pool:
                    if ident and getattr(cand, "_save_uid", None) == ident:
                        n = cand
                        break
                    # An id is only a fallback, and only inside this camp:
                    # `conquered_0` is reused by every camp that spawns one.
                    if (rec.get("id")
                            and getattr(cand, "id", None) == rec.get("id")
                            and getattr(cand, "native_camp", None) is camp):
                        n = cand
                        break
            if n is None:
                n = people_mod.create(rec, camp, ctx)
            else:
                people_mod.restore(n, rec, ctx)
                ctx.people[ident or codec.uid(n, "person")] = n
            n.native_camp = camp
            restored.append(n)
            seen.add(id(n))

        # The camp's own lists are authoritative.
        for name, uids in (body.get("lists") or {}).items():
            try:
                setattr(camp, name, [ctx.people[u] for u in uids
                                     if u in ctx.people])
            except Exception:
                pass
        if isinstance(getattr(camp, "people", None), list) or body.get("lists"):
            if "people" in (body.get("lists") or {}):
                camp.people = [ctx.people[u] for u in body["lists"]["people"]
                               if u in ctx.people]
        camp.animals = [ctx.animals[u] for u in (body.get("animals") or ())
                        if u in ctx.animals]

        # Orchard trees are hand-planted trees; terrain restored them already.
        camp.orchard_state = {}
        for key, st in (body.get("orchard_state") or {}).items():
            tree = ctx.planted_trees.get(st.get("tree") or "")
            if tree is None:
                continue
            try:
                tx, ty = (int(v) for v in key.split(","))
            except Exception:
                continue
            camp.orchard_state[(tx, ty)] = {
                "tree": tree,
                "target_r": float(st.get("target_r", 72.0)),
                "planted_at": float(st.get("planted_at", 0.0)),
            }

        for attr in ("breeding", "breeding_people"):
            ev = body.get(attr)
            if not ev:
                continue
            if attr == "breeding_people":
                # Partners may belong to a camp that has not been processed
                # yet; resolve after every camp's people are in the context.
                ctx.later(lambda _c=camp, _e=ev: _restore_people_breeding(_c, _e, ctx))
                continue
            a = (ctx.animals.get(ev.get("a") or "")
                 or ctx.people.get(ev.get("a") or ""))
            b = (ctx.animals.get(ev.get("b") or "")
                 or ctx.people.get(ev.get("b") or ""))
            if a is not None and b is not None:
                setattr(camp, "_" + attr, {"a": a, "b": b,
                                          "t": float(ev.get("t", 0.0))})
            else:
                setattr(camp, "_" + attr, None)

        if getattr(camp, "conquered", False):
            for n in restored:
                n.nation = getattr(camp, "nation", None)
                n.team = ("nation", getattr(camp, "nation", None))
                n.conquered = True

    # REBUILD THE REGISTERS THE ENGINE ACTUALLY WALKS.
    live = []
    seen = set()
    for key, camp in list(g.native_settlements.items()):
        people = None
        if isinstance(getattr(camp, "people", None), list):
            people = list(camp.people)
        if people is None:
            people = _camp_people(camp)
        for n in people:
            if id(n) in seen:
                continue
            seen.add(id(n))
            live.append(n)
    g._native_people[:] = live
    if getattr(g, "_observe_npcs", None) is not None:
        g._observe_npcs[:] = list(live)
