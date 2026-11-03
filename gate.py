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

import math
import random

import fence
import plog

CONTRABAND = ("tobacco", "cigar", "beer", "liqueur", "mezcal",
              "dried_mushroom", "red_mushroom", "agave",
              "wheat_wort", "berry_wort", "agave_wort")

SEARCH_RANGE = 260.0        # he will come this far to look at you
SEARCH_SECONDS = 10.0
STANDOFF = 46.0             # he stops here: close enough to look, not to push
BREAK_RANGE = 420.0         # run this far and it is a flight, not a search
CATCH_BASE = 0.55           # of the men carrying contraband, this many are found

# THE MOMENT HE FINDS SOMETHING. He does not start shooting into the man's
# chest with a hand in his pack -- he makes room and THEN fires. Half a second
# between the player being told ("5 found. Run.") and the first round.
CAUGHT_DELAY = 0.5
CAUGHT_BACKOFF = 34.0       # the space he puts between them first
_CAUGHT = {"on": False, "t": 0.0, "guard": None, "town": None,
           "units": 0, "shot": False}

_STATE = {"guard": None, "t": 0.0, "town": None}
_RETURNING = []             # soldiers walking back to their post: usually empty
_LAST_GUARD = [None]        # the man who did the last search, kept across reset()
_VISITORS = {}              # (town, traveller) -> seconds at that gate


def _post_of(g):
    return getattr(g, "gate_post", None) or getattr(g, "home", None)


def reset() -> None:
    _STATE["guard"] = None
    _STATE["t"] = 0.0
    _STATE["town"] = None


def begin_caught(player, town, units: int, guard=None) -> None:
    """HE HAS FOUND SOMETHING. Back off, then shoot."""
    g = guard or _STATE.get("guard") or _LAST_GUARD[0]
    _CAUGHT.update(on=True, t=0.0, guard=g, town=town, units=int(units),
                   shot=False)
    if g is not None:
        try:
            # THE FUSE IS HIS OWN ATTACK CLOCK: however his combat code is
            # driven, the earliest round he can fire is CAUGHT_DELAY from now.
            g.attack_cd = max(float(getattr(g, "attack_cd", 0.0)), CAUGHT_DELAY)
            g.fire_cd = max(float(getattr(g, "fire_cd", 0.0)), CAUGHT_DELAY)
        except Exception:
            pass
    try:
        plog.log("CAUGHT-FOUND", getattr(town, "name", "?"), units,
                 "unit(s) | the guard makes space and fires in",
                 CAUGHT_DELAY, "s")
    except Exception:
        pass


def tick_caught(dt: float, player) -> str | None:
    """The half second between the find and the shot. Returns "shot" once."""
    if not _CAUGHT["on"]:
        return None
    _CAUGHT["t"] = float(_CAUGHT["t"]) + float(dt)
    g = _CAUGHT["guard"]
    t = float(_CAUGHT["t"])
    if g is not None and getattr(g, "alive", True):
        dx, dy = player.x - g.x, player.y - g.y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        if d < STANDOFF + CAUGHT_BACKOFF - 1.0 and d > 1.0:
            # ONE clean step back. A nudge lost the argument with his own feet
            # (he walked forward again in the same frame); a step does not.
            step = min(CAUGHT_BACKOFF, STANDOFF + CAUGHT_BACKOFF - d)
            g.x -= ux * step
            g.y -= uy * step
            plog.log("CAUGHT-SPACE", getattr(g, "name", "?"), "stepped back",
                     int(step), "px")
        try:
            # HE IS LOOKING AT THE MAN HE JUST SEARCHED. Without this his own
            # update refuses to fire: squad and guard code want the target in
            # the narrow arc he happens to be facing, and after a search that
            # arc is anywhere.
            g.facing = (ux, uy)
            g.view_angle = math.radians(170.0)
            g.aware = True
            g.aware_timer = 30.0
            g.target = (g.x, g.y)
            g.hostile = True
            g.aggro = True
            g.attack_cd = max(float(getattr(g, "attack_cd", 0.0)),
                              CAUGHT_DELAY - t)
            g.fire_cd = max(float(getattr(g, "fire_cd", 0.0)),
                            CAUGHT_DELAY - t)
        except Exception:
            pass
    if t >= CAUGHT_DELAY and not _CAUGHT["shot"]:
        _CAUGHT["shot"] = True
        if g is not None:
            try:
                g.attack_cd = 0.0            # the round goes now
                g.fire_cd = 0.0
                g.aggro = True
                g.hostile = True
                g.aware = True
                g.aware_timer = 30.0
                _d = math.hypot(player.x - g.x, player.y - g.y) or 1.0
                g.facing = ((player.x - g.x) / _d, (player.y - g.y) / _d)
            except Exception:
                pass
        _CAUGHT["watch"] = 1.5
        _LAST_GUARD[0] = g
        try:
            plog.log("CAUGHT-SHOT", "the guard fires at",
                     getattr(_CAUGHT["town"], "name", "?"),
                     "after", round(t, 2), "s and",
                     int(math.hypot(player.x - (g.x if g else player.x),
                                    player.y - (g.y if g else player.y))), "px")
        except Exception:
            pass
        return "shot"
    return None


def fire_shot(player, combat) -> bool:
    """THE ROUND, from the guard's own gun. Returns True if one left.

    It is fired here and not left to whichever loop happens to be walking him:
    the man who did the search is a town's soldier, and not every town's
    soldiers are simulated by the frame the player is in.
    """
    g = _CAUGHT["guard"] or _LAST_GUARD[0]
    if g is None or combat is None:
        return False
    dx, dy = player.x - g.x, player.y - g.y
    d = math.hypot(dx, dy) or 1.0
    try:
        if not g._round_ready():
            return False
        angle = math.atan2(dy, dx) + random.uniform(-0.03, 0.03)
        mx = g.x + dx / d * 16.0
        my = g.y + dy / d * 16.0
        g._shoot(combat, mx, my, angle, d + 120.0, 80, 80)
        g.attack_flash = 0.35
        plog.log("CAUGHT-SHOT", "the guard fired from", int(d), "px",
                 "| mag now", getattr(g, "mag", None))
        return True
    except Exception as exc:
        try:
            plog.log("CAUGHT-SHOT-ERR", repr(exc))
        except Exception:
            pass
        return False


def caught_over() -> None:
    _CAUGHT.update(on=False, t=0.0, guard=None, town=None, units=0, shot=False)


def progress() -> float:
    """0 to 1: the bar under the guard's feet."""
    if _STATE["guard"] is None:
        return 0.0
    return max(0.0, min(1.0, _STATE["t"] / SEARCH_SECONDS))


def guard_of():
    return _STATE["guard"]


PASS_SLACK = 600.0      # how far past the wall a pass stops working


def pass_expired(player, town, slack: float = PASS_SLACK) -> bool:
    """HAS HE GONE AWAY? A pass lasts while he is at the gate.

    It used to be spent the instant he stepped outside the wall, so walking
    out and back in put him through the search again -- three times a minute
    at one gate. He is a stranger again only when he is out of the town's
    reach, and never before: a pass that worked from anywhere would be a way
    to walk contraband in unnoticed.
    """
    if town is None:
        return True
    d = math.hypot(player.x - town.x, player.y - town.y)
    return d > float(getattr(town, "radius", 0.0)) + float(slack)


def is_service(man) -> bool:
    """THE SERVICE IS NOT SEARCHED FOR LONG.

    An agent goes through the search like anybody else -- always, every
    crossing -- but what is found in his pack is not found: he is waved
    through, nothing is written against him, and the town does not turn.
    """
    return bool(getattr(man, "secret_police", False)
                or getattr(man, "secret_police_chief", False))


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


# THE THRESHOLD A MAN CANNOT WALK THROUGH. Thirty items is a certainty for a
# beginner; three hundred is the same certainty for a master. Everything
# between is the straight line.
CAUGHT_AT_ZERO = 30.0
CAUGHT_AT_MAX = 300.0


# A TRIP CARRIES A FIFTH OF WHAT HIS SKILL WOULD LET HIM RISK. A beginner
# risks six of the thirty that would certainly catch him; a master risks sixty
# of his three hundred. Nobody risks everything on one cart.
RISK_PER_TRIP = 0.2


def caravan_load(skill: float) -> int:
    """What a trader of this skill carries per trip, in whole items.

    Rounded, not truncated, and floored at one -- a 0.2 x 30 of 6.000000001
    must not become 5, and a 60.000000001 must not become 61.
    """
    raw = RISK_PER_TRIP * caught_threshold(skill)
    n = int(round(raw + 1e-9))
    return max(1, n)


def caught_threshold(skill: float) -> float:
    k = max(0.0, min(10.0, float(skill))) / 10.0
    return CAUGHT_AT_ZERO + (CAUGHT_AT_MAX - CAUGHT_AT_ZERO) * k


def _roll(units: int, skill: float) -> bool:
    """Caught in proportion to what he carries against what his skill allows.

    30 of contraband at smuggling 0 is a certainty; 300 at smuggling 10 is a
    certainty; half of each is a coin toss.
    """
    if units <= 0:
        return False
    chance = min(1.0, float(units) / caught_threshold(skill))
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
    _LAST_GUARD[0] = g if g is not None else _STATE.get("guard")
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
    if not getattr(town, "_gate_logged", False):
        town._gate_logged = True
        try:
            _trav = sum(1 for n in town.npcs if n.alive and (
                getattr(n, "village", None) is not town
                or getattr(n, "refuge", None) is not None
                or getattr(n, "trade_state", "none") != "none"))
            plog.log("GATE-INIT", getattr(town, "name", "?"),
                     "guards", len(squad or ()), "men", len(town.npcs),
                     "travellers", _trav,
                     "fence", tuple(getattr(town, "fence_rect", (0, 0, 0, 0))))
        except Exception:
            pass
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
        # NOBODY IS SEARCHED LEAVING. The gate on the way out is a doorway,
        # not a checkpoint (Pivot.md: "the way in is searched, the way out is
        # free") -- and searching a man on every step he takes in and out of
        # the wall put the same man in the queue three times a minute.
        if not inside:
            continue
        if n is town.search_now or n in town.search_queue:
            continue
        town.search_queue.append(n)
        try:
            plog.log("CROSSING", getattr(town, "name", "?"),
                     getattr(n, "name", "?"),
                     "units", units_on(n),
                     "way", "in" if inside else "out")
        except Exception:
            pass

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
            _slot = (34.0 + 26.0 * _i)
            _tx = _g[1] + _ox * _slot
            _ty = _g[2] + _oy * _slot
            _w.target = (_tx, _ty)
            if ((_w.x - _tx) ** 2 + (_w.y - _ty) ** 2) < 22.0 ** 2:
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
    _caught = _roll(units, float(getattr(cur, "smuggling", 0.0)))
    try:
        plog.log("SEARCH", getattr(town, "name", "?"),
                 getattr(cur, "name", "?"), "units", units,
                 "result", "CAUGHT" if _caught else "clean")
    except Exception:
        pass
    if _caught:
        if is_service(cur):
            # FOUND WITH THE GOODS, AND WAVED THROUGH. No aggro, no charge,
            # no mark on him.
            try:
                plog.log("SEARCH", getattr(town, "name", "?"),
                         getattr(cur, "name", "?"), "units", units,
                         "result", "WAVED (service)")
            except Exception:
                pass
            return ("clean", cur, units)
        cur.wanted = True
        return ("caught", cur, units)
    return ("clean", cur, units)


def search_visitor(dt: float, town, who):
    """A TRADER AT A TOWN'S GATE: ten seconds by the guard, one roll.

    Returns "caught", "clean", or None (still being looked at). Called once a
    frame by whoever is walking the man to the gate -- it does nothing else.
    """
    squad = getattr(town, "patrol", None)
    if not squad:
        return "clean"                     # no guard on the gate
    g = squad[0]
    if not getattr(g, "alive", True):
        return "clean"
    key = (id(town), id(who))
    t = _VISITORS.get(key, 0.0) + dt
    _VISITORS[key] = t
    if t < SEARCH_SECONDS:
        return None
    _VISITORS.pop(key, None)
    units = units_on(who)
    caught = _roll(units, float(getattr(who, "smuggling", 0.0)))
    if caught and is_service(who):
        # A CART THAT BELONGS TO THE SERVICE IS LOOKED AT EVERY TIME, and
        # waved through every time -- goods and all.
        try:
            plog.log("SEARCH", getattr(town, "name", "?"),
                     getattr(who, "name", "?"), "units", units,
                     "result", "WAVED (service)", "at", "gate")
        except Exception:
            pass
        return "clean"
    try:
        plog.log("SEARCH", getattr(town, "name", "?"),
                 getattr(who, "name", "?"), "units", units,
                 "result", "CAUGHT" if caught else "clean", "at", "gate")
    except Exception:
        pass
    return "caught" if caught else "clean"
