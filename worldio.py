"""worldio.py -- THE WORLD'S STATE, WRITTEN AND READ.

Serialising a village and its people, the world cache on disk, and the
functions that put a save back onto a laid-out world. Extracted from main.py
so the engine stays thin; the shapes are decided here and nowhere else.
"""

from __future__ import annotations

import os

import persist
from village import village_center


_STATE_SKIP = {"id", "name", "village", "home_house", "home_door",
               "bond_partner", "workplace", "refuge", "social_target",
               "guards", "patrol", "npcs", "houses", "workplaces", "mayor",
               "king", "registry", "rng", "_rng", "image", "_atlas", "rect",
               "sight_rect", "slots", "board", "gate_t",
               # DAY MARKERS ARE NOT STATE. Each one guards "the books have
               # been done today" INSIDE A RUNNING PROCESS; saved, they say the
               # day is done before it has begun. A reload mid-day therefore
               # paid no wages, no mint and no service pay -- and the day's
               # tally of what a town spent came back with it.
               "_day", "_log_day", "_phase", "_last_phase", "_seeded",
               "wage_day", "market_day", "duty_day", "court_day", "_court_day",
               "_tax_day", "_mayor_day", "_crown_day", "_mint_day",
               "_agent_day", "_service_day", "_paid_today", "_vote_day",
               "_births", "_crown_base", "_share_timer", "_market_timer",
               "_meet_timer", "_farm_timer", "_log_day"}


# What actually changes between saves. Everything else on a person -- his
# trade, his pack, his grades, his skills, every flag -- is the bulk, and it
# is the same from one save to the next. Rebuilding it for two thousand people
# every time cost 194 ms on its own.
_VOLATILE = ("x", "y", "coins", "hunger", "health")
_BULK: dict = {}


def _bulk(n) -> dict:
    out = {}
    for key, value in vars(n).items():
        if key in _STATE_SKIP or key in _VOLATILE or not _simple(value):
            continue
        out[key] = list(value) if isinstance(value, tuple) else value
    return out


def _simple(value) -> bool:
    return (value is None or isinstance(value, (bool, int, float, str))
            or (isinstance(value, (list, tuple))
                and all(v is None or isinstance(v, (bool, int, float, str))
                        for v in value))
            or (isinstance(value, dict)
                and all(isinstance(k, str) and (v is None or
                         isinstance(v, (bool, int, float, str)))
                        for k, v in value.items())))


def _plain(obj) -> dict:
    """EVERY simple field an object has.

    Not a hand-picked dozen: every number, flag, string and little dictionary
    on him -- his hunger, his wear, his loans, his tool orders, his barrel of
    wort, whether he is asleep or indoors. Anything pointing at another object
    is stored separately, by id or by index, because an object is not a
    number. Written this way a new field is saved the day it is added.
    """
    out = {}
    for key, value in vars(obj).items():
        if key in _STATE_SKIP or not _simple(value):
            continue
        out[key] = list(value) if isinstance(value, tuple) else value
    return out


def _restore(obj, blob) -> None:
    for key, value in (blob or {}).items():
        if key in _STATE_SKIP:
            continue
        try:
            setattr(obj, key, value)
        except Exception:
            pass


def village_to_data(v) -> dict:
    """One settlement's full state, in the shape world_from_data expects."""
    people = []
    for n in v.npcs:
        house = None
        if getattr(n, "home_house", None) is not None:
            try:
                house = v.houses.index(n.home_house)
            except ValueError:
                house = None
        work = None
        if getattr(n, "workplace", None) is not None:
            try:
                work = v.workplaces.index(n.workplace)
            except ValueError:
                work = None
        ref = getattr(n, "refuge", None)
        sig = (n.job, n.alive, getattr(n, "ranged", False),
               len(n.stock), len(n.grade), sum(n.stock.values()),
               len(getattr(n, "tool_orders", ()) or ()),
               getattr(n, "levied", False), getattr(n, "defender", False),
               getattr(n, "is_mayor", False))
        got = _BULK.get(id(n))
        if got is None or got[0] != sig:
            got = (sig, _bulk(n))
            _BULK[id(n)] = got
        state = dict(got[1])
        state["x"] = n.x
        state["y"] = n.y
        state["coins"] = n.coins
        state["hunger"] = n.hunger
        state["health"] = n.health
        people.append({
            "id": n.id, "state": state, "house": house, "work": work,
            # skills are an object, not a number: a life's practice has
            # to be carried across by hand.
            "skills": [n.skills.farming, n.skills.movement,
                       n.skills.axe, n.skills.shooting],
            "village": ("%d,%d" % (n.village.gx, n.village.gy)
                        if getattr(n, "village", None) is not None else None),
            "bond": getattr(getattr(n, "bond_partner", None), "id", None),
            "refuge": ("%d,%d" % (ref.gx, ref.gy) if ref is not None else None),
        })
    houses = [{"warmth": float(getattr(h, "warmth", 1.0)),
               "door_broken": bool(getattr(h, "door_broken", False)),
               "occupants": [getattr(o, "id", None) for o in
                             getattr(h, "occupants", ())]}
              for h in v.houses]
    return {
        "gx": v.gx, "gy": v.gy,
        "state": _plain(v),
        "houses": houses,
        "workers": [getattr(w.worker, "id", None) for w in v.workplaces],
        "mayor": getattr(getattr(v, "mayor", None), "id", None),
        "king": getattr(getattr(v, "king", None), "id", None),
        "people": people,
    }


def world_to_data(villages) -> list:
    """The whole world's state, people and all, in a shape a load can use."""
    return [village_to_data(v) for v in villages._cache.values()]


_WORLD_CACHE_VERSION = 5        # bump when the shape of a VILLAGE changes...
# ...or the shape of the WORLD. The cache is keyed by seed alone, so a change
# to the spacing would otherwise load a world laid out to the OLD distances
# while every rule in the game used the new ones.


# THE WORLD'S SHAPE HAS A VERSION, AND IT BELONGS IN THE FILENAME.
#
# The cache is the BUILT world -- every plot, every garden tile already planted,
# every bench already standing. Changing the rules of what a village may contain
# does not change a world that was built before the rules, and the game happily
# loaded the old one: gardens still half tobacco, benches still there, all of it
# looking exactly like the change had never been made. Bump this and the old
# cache is simply not found, so the world is laid out again to the new law.
WORLD_VERSION = 2


def _world_cache_path(seed: int) -> str:
    return os.path.join(persist.DIR,
                        "world_%d_v%d.pkl" % (int(seed), WORLD_VERSION))


def load_cached_world(seed: int):
    """The whole built world, read back instead of laid out again.

    Laying out 36 villages costs about 1.8 s, and every house, plot, fence,
    road and villager in them. The seed decides all of it, so the first launch
    writes the built object graph to disk and every launch after that reads it
    back. Houses keep their sprites out of the file (a Surface cannot be
    pickled) and draw them again the first time they are wanted.
    """
    import pickle
    target = _world_cache_path(seed)
    if not os.path.exists(target):
        return None
    try:
        with open(target, "rb") as fh:
            blob = pickle.load(fh)
    except Exception as exc:
        print("world cache unreadable (%r) -- laying the world out again" % (exc,))
        return None
    if not isinstance(blob, dict) or blob.get("version") != _WORLD_CACHE_VERSION:
        return None
    villages = blob.get("villages")
    if villages is None or getattr(villages, "seed", None) != seed:
        return None
    if not getattr(villages, "_cache", None):
        # AN EMPTY WORLD IS NOT A CACHE. A partial write left a 150-byte file
        # with no towns in it, and this loaded it gladly -- so the game ran on
        # an empty world and every man in it was a stranger to the register.
        print("world cache holds no villages -- laying the world out again")
        return None
    return villages


def save_cached_world(villages, seed: int) -> None:
    """Write the freshly laid out world, so it is never laid out twice."""
    import pickle
    target = _world_cache_path(seed)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        blob = {"version": _WORLD_CACHE_VERSION, "villages": villages}
        tmp = target + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(blob, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, target)
    except Exception as exc:
        print("could not cache the world (%r)" % (exc,))


def world_from_data(villages, blob) -> None:
    """Put every bit of it back."""
    if not blob:
        return
    by_id = {}
    for v in villages._cache.values():
        for n in v.npcs:
            by_id[n.id] = n
    for rec in blob:
        # A LOOKUP, NEVER A BUILD. The world is laid out from its seed; a save
        # only overlays the state of towns that exist. This called get(), which
        # CONSTRUCTS a town that is not there -- so a save from the era of the
        # town-building bug restored three hundred and sixty towns that had
        # never been part of the world, and eighteen thousand people with them.
        v = villages._cache.get((rec["gx"], rec["gy"]))
        if v is None:
            # A FROZEN SETTLEMENT. Its cell is not built (the player is far
            # from it), so its state waits in _frozen until get() rebuilds the
            # cell and overlays this record.
            try:
                villages._frozen[(int(rec["gx"]), int(rec["gy"]))] = rec
            except Exception:
                pass
            continue
        _restore(v, rec.get("state"))
        # WHERE A TOWN IS, IS NOT STATE. `_restore` copied x and y off the save,
        # and a save written in another world put every village twenty-two
        # kilometres from the position the lattice reports -- so its fence,
        # gates, guards and culling were all computed for a place the town was
        # not. The seed decides where a town stands; a save only decides what
        # has happened to it since.
        _c = village_center(v.gx, v.gy, villages.seed)
        v.x, v.y = float(_c[0]), float(_c[1])
        for i, hb in enumerate(rec.get("houses", [])):
            if i >= len(v.houses):
                break
            house = v.houses[i]
            house.warmth = float(hb["warmth"])
            house.door_broken = bool(hb["door_broken"])
        keep = set()
        for p in rec["people"]:
            n = by_id.get(p["id"])
            if n is None:
                # A SAVE CANNOT INVENT A CITIZEN. The people come from the
                # world cache, which is laid out from the seed; a save is an
                # overlay of their state and knows nothing the world does not
                # already hold. This branch used to CREATE a villager for any
                # record it could not match -- so a save written while the
                # town-building bug was live came back with 36,595 people who
                # had never existed, invented at load, and the world walked
                # every one of them for ever.
                continue
            _restore(n, p.get("state"))
            if p.get("skills"):
                (n.skills.farming, n.skills.movement,
                 n.skills.axe, n.skills.shooting) = p["skills"]
            # ...and the things that are not numbers: his house, his post,
            # his plot, his partner, the village he belongs to.
            if p.get("house") is not None and p["house"] < len(v.houses):
                n.home_house = v.houses[p["house"]]
            if p.get("work") is not None and p["work"] < len(v.workplaces):
                n.workplace = v.workplaces[p["work"]]
            if p.get("village"):
                vgx, vgy = (int(t) for t in p["village"].split(","))
                n.village = villages.get(vgx, vgy)
            else:
                n.village = v
            if p.get("refuge"):
                rgx, rgy = (int(t) for t in p["refuge"].split(","))
                n.refuge = villages.get(rgx, rgy)
            if n not in v.npcs:
                v.npcs.append(n)
            keep.add(p["id"])
        for n in list(v.npcs):                # gone: dead, or marched away
            if n.id not in keep:
                v.npcs.remove(n)
        for i, wid in enumerate(rec.get("workers", [])):
            if i < len(v.workplaces):
                v.workplaces[i].worker = by_id.get(wid) if wid else None
        for i, hb in enumerate(rec.get("houses", [])):
            if i < len(v.houses):
                v.houses[i].occupants = [by_id[o] for o in hb["occupants"]
                                         if o in by_id]
        # A RESTORE MUST NOT UNSEAT A MAYOR IT NEVER KNEW ABOUT. The village
        # chose its own mayor at creation; the record only carries one if a
        # save was written after a town had a mayor. Assigning None when the key is
        # missing threw the government of EVERY town in the world away on
        # load, and left only the one town whose id happened to be in the file
        # still holding a chain -- 1 mayor in 33, which is what the survey
        # found. Same for the King: a capital does not lose its crown because
        # an older save did not mention it.
        _m = by_id.get(rec["mayor"]) if rec.get("mayor") else None
        if _m is not None and getattr(_m, "alive", False):
            v.mayor = _m
        _k = by_id.get(rec["king"]) if rec.get("king") else None
        if _k is not None and getattr(_k, "alive", False):
            v.king = _k
        if v.mayor is not None:
            v.mayor.plaza = (v.x, v.y)
        for n in v.npcs:                      # partners, once everyone is in
            pid = next((p["bond"] for p in rec["people"]
                        if p["id"] == n.id), None)
            if pid:
                n.bond_partner = by_id.get(pid)


