"""gate.py -- THE SEARCH AT THE GATE, and nothing else.

One guard, one man, ten seconds, one roll. Written from scratch, because the
version that grew inside `Village.update` reached into wages, taxes, the tithe,
the election, the court, the garrison and the market -- and froze the game for
forty-six seconds to look in somebody's pack.

IN FULL:

    close to a guard  ->  he walks to you, and ten seconds start
    ten seconds       ->  one roll against what you carry
    caught            ->  the town turns on you
    clean             ->  you are waved through
    stepping over a wall without being waved through -> the town turns on you

The only state is one dictionary. The only per-frame work is a distance, a
timer, and -- when nothing is running -- one pass over the guards of towns near
the player. No town books, no line-of-sight, no queue for the player.
"""

from __future__ import annotations

import random

import fence

CONTRABAND = ("tobacco", "cigar", "beer", "liqueur", "mezcal",
              "dried_mushroom", "red_mushroom", "agave",
              "wheat_wort", "berry_wort", "agave_wort")

SEARCH_RANGE = 260.0        # he will come this far to look at you
SEARCH_SECONDS = 10.0
STANDOFF = 46.0             # he stops here: close enough to look, not to push
BREAK_RANGE = 420.0         # run this far and it is a flight, not a search
CATCH_BASE = 0.55           # of the men carrying contraband, this many are found

_STATE = {"guard": None, "t": 0.0, "town": None}
_RETURNING = []             # soldiers walking back to their post: usually empty


def _post_of(g):
    return getattr(g, "gate_post", None) or getattr(g, "home", None)


def reset() -> None:
    _STATE["guard"] = None
    _STATE["t"] = 0.0
    _STATE["town"] = None


def progress() -> float:
    """0 to 1: the bar under the guard's feet."""
    if _STATE["guard"] is None:
        return 0.0
    return max(0.0, min(1.0, _STATE["t"] / SEARCH_SECONDS))


def guard_of():
    return _STATE["guard"]


def units_on(carrier, inventory=None) -> int:
    """What he is carrying that the state forbids."""
    if inventory is not None:
        try:
            return sum(int(inventory.count_of(i)) for i in CONTRABAND)
        except Exception:
            return 0
    stock = getattr(carrier, "stock", None)
    if isinstance(stock, dict):
        return sum(int(stock.get(i, 0)) for i in CONTRABAND)
    return 0


def _roll(units: int, skill: float) -> bool:
    if units <= 0:
        return False
    chance = (min(1.0, units / 100.0) * CATCH_BASE
              * (1.0 - 0.09 * max(0.0, min(10.0, skill))))
    return random.random() < chance


def nearest_guard(player, towns):
    """The closest living guard of a settlement -- never a hub's."""
    best, bd = None, SEARCH_RANGE * SEARCH_RANGE
    for v in towns:
        if getattr(v, "is_hub", False):
            continue
        for s in (getattr(v, "patrol", ()) or ()):
            if not getattr(s, "alive", True):
                continue
            d = (player.x - s.x) ** 2 + (player.y - s.y) ** 2
            if d < bd:
                best, bd = s, d
    return best


def tick(dt: float, player, towns, inventory=None):
    """The player's search. Returns ("caught"|"clean", town, units) or None."""
    # A SOLDIER WHO HAS FINISHED WALKS BACK TO HIS POST. Nothing else drives
    # this, so it lives here: a handful of men, and usually none at all.
    if _RETURNING:
        for _g in list(_RETURNING):
            if not getattr(_g, "alive", True):
                _RETURNING.remove(_g)
                continue
            _post = _post_of(_g)
            if _post is None:
                _RETURNING.remove(_g)
                continue
            if ((_g.x - _post[0]) ** 2 + (_g.y - _post[1]) ** 2) < 26.0 ** 2:
                _g.target = (_post[0], _post[1])
                _g.idle_timer = 1.0e9          # back on duty: he stands
                _RETURNING.remove(_g)
            else:
                _g.idle_timer = 0.0            # walking
                _g.target = (_post[0], _post[1])
    g = _STATE["guard"]
    if g is not None and not getattr(g, "alive", True):
        reset()
        g = None

    if g is None:
        if getattr(player, "waved_by", None) is not None:
            return None                      # already let through
        g = nearest_guard(player, towns)
        if g is None:
            return None                      # nobody near: no work at all
        _STATE["guard"] = g
        _STATE["t"] = 0.0
        _STATE["town"] = getattr(g, "gate_village", None)

    # HE COMES TO YOU -- AND STOPS AT ARM'S LENGTH. Walking into the man he is
    # searching shoved him across the road, which is not a search.
    _d2 = (player.x - g.x) ** 2 + (player.y - g.y) ** 2
    try:
        g.pause = 0.0
        g.idle_timer = 0.0
        if _d2 > STANDOFF * STANDOFF:
            g.target = (player.x, player.y)          # still closing
        else:
            g.target = (g.x, g.y)                    # close enough: stand still
    except Exception:
        pass

    # RUNNING AWAY IS A CRIME, NOT A NO-OP. Walking off used to cancel the
    # search quietly. Break away from a guard who is looking at you and he
    # treats it as flight: he turns hostile and the town is told.
    if _d2 > BREAK_RANGE * BREAK_RANGE:
        town = _STATE["town"]
        reset()
        try:
            g.hostile = True
            g.aggro = True
        except Exception:
            pass
        return ("fled", town, 0)

    _STATE["t"] = float(_STATE["t"]) + dt
    if _STATE["t"] < SEARCH_SECONDS:
        return None

    town = _STATE["town"]
    reset()
    player.waved_by = town
    units = units_on(player, inventory)
    skill = float(getattr(player, "smuggling", 0.0))
    if _roll(units, skill):
        return ("caught", town, units)
    if units > 0:
        player.smuggling = min(10.0, skill + 0.06 + units * 0.001)
    # A CLEAN SEARCH IS NOT A CRIME: the soldier goes back and stands at his
    # gate again.
    if g is not None and not getattr(g, "hostile", False):
        _RETURNING.append(g)
    return ("clean", town, units)


def tick_town(dt: float, town):
    """The same thing for a town's own men: one at a time, on the crossing."""
    if getattr(town, "is_hub", False):
        return None
    squad = getattr(town, "patrol", None)
    if not squad:
        return None
    guard = squad[0]
    if not getattr(guard, "alive", True):
        town.search_now, town.search_t = None, 0.0
        return None
    r = getattr(town, "fence_rect", None)
    if r is None:
        return None
    if not isinstance(getattr(town, "search_queue", None), list):
        town.search_queue = []

    # WHO JUST STEPPED OVER THE WALL. That is the only trigger.
    for n in town.npcs:
        if not n.alive or getattr(n, "village", None) is town:
            continue
        inside = r.collidepoint(n.x, n.y)
        was = getattr(n, "was_inside", None)
        n.was_inside = inside
        if was is None or was == inside:
            continue
        if n is town.search_now or n in town.search_queue:
            continue
        town.search_queue.append(n)

    if town.search_now is None and town.search_queue:
        town.search_now = town.search_queue.pop(0)
        town.search_t = 0.0
    cur = town.search_now

    # THEY WAIT IN FRONT OF THE GATE, IN ORDER. Everyone in the line -- the man
    # being searched and the men behind him -- walks to a place just outside
    # the gate and STANDS THERE until his turn comes, and then he goes on about
    # his business. Before this they were stopped wherever they happened to be,
    # in the middle of the road, which is not a queue at the gate.
    _line = ([cur] if cur is not None else []) + list(town.search_queue)
    for _i, _w in enumerate(_line):
        if not getattr(_w, "alive", True):
            continue
        try:
            _g = fence.nearest_gate(town, _w.x, _w.y)
            _ox, _oy = fence.OUTWARD[_g[0]]
            _slot = (44.0 + 30.0 * _i)
            _tx = _g[1] + _ox * _slot
            _ty = _g[2] + _oy * _slot
            _w.target = (_tx, _ty)
            if ((_w.x - _tx) ** 2 + (_w.y - _ty) ** 2) < 34.0 ** 2:
                _w.pause = max(float(getattr(_w, "pause", 0.0)), 0.25)   # he stands
            else:
                _w.pause = 0.0                                           # he walks
        except Exception:
            pass

    if cur is None:
        return None
    if getattr(cur, "pause", 0.0) <= 0.0:
        return None                    # still walking to the gate: not yet
    town.search_t = float(getattr(town, "search_t", 0.0)) + dt
    if town.search_t < SEARCH_SECONDS:
        return None
    town.search_now, town.search_t = None, 0.0
    units = units_on(cur)
    if _roll(units, float(getattr(cur, "smuggling", 0.0))):
        cur.wanted = True
        return ("caught", cur, units)
    return ("clean", cur, units)
