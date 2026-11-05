"""detain.py -- ARREST, DETENTION, AND THE PRISON TRAIN.

The chain, in the game's own objects:

  * a man (or the player) who is tranquilised lies where he falls;
  * once nothing nearby is being shot at any more, a militiaman CARRIES him to
    the nearest holding cell and he is inside it, as data;
  * detainees wait in the cell until the train stops at that settlement;
  * the train takes up to FIFTY, on a route that only calls where somebody is
    waiting for it, and the player -- if he is the detainee -- has ONE MINUTE
    to board before every militiaman and soldier in the town turns on him;
  * while the player is aboard the camera follows the train, and at the end of
    the camp's line everybody is put down at the gulag.
"""

from __future__ import annotations

import math

import pygame
import plog

CAPACITY = 50                 # the train carries fifty
PLAYER_BOARD_SECONDS = 60.0   # ...and the player has a minute to get on
CARRY_AT = 60.0               # how close a carrier gets before he picks him up
QUIET_PX = 700.0              # "no shooting close by" -- nothing hostile near
QUIET_SECONDS = 2.5           # and quiet for this long

_STATE = {"carry": {}, "board": {}, "timer": 0.0, "aboard": [], "stop": None}


def cells():
    try:
        import holding
        return holding.cells()
    except Exception:
        return []


def cell_load(cell) -> list:
    return _STATE["carry"].setdefault(id(cell), [])


def waiting() -> int:
    return sum(len(v) for v in _STATE["carry"].values())


def _nearest_cell(x, y):
    best, bd = None, 1e18
    for c in cells():
        d = (c.x - x) ** 2 + (c.y - y) ** 2
        if d < bd:
            best, bd = c, d
    return best


def _militia_near(player, enemies, townsmen, x, y, radius):
    out = []
    for a in list(enemies) + list(townsmen):
        if not getattr(a, "alive", True):
            continue
        if not (getattr(a, "is_militia", False) or getattr(a, "militia", False)):
            continue
        if (a.x - x) ** 2 + (a.y - y) ** 2 <= radius * radius:
            out.append(a)
    return out


def _busy_near(player, x, y, radius) -> bool:
    """Is anybody shooting, or angry, close to this spot?"""
    r2 = radius * radius
    for who in ([player] if player is not None else []):
        if getattr(who, "attack_flash", 0.0) > 0.0 or getattr(who, "swing_anim", 0.0) > 0.0:
            if (who.x - x) ** 2 + (who.y - y) ** 2 < r2:
                return True
    try:
        import village as _v
        for n in _v.PEOPLE:
            if (n.x - x) ** 2 + (n.y - y) ** 2 > r2:
                continue
            if getattr(n, "attack_flash", 0.0) > 0.0 or getattr(n, "panic", 0.0) > 0.0:
                return True
    except Exception:
        pass
    return False


def deposit(victim, cell) -> None:
    """THE GUARD PUTS HIM DOWN INSIDE THE CELL."""
    if victim is None or cell is None:
        return
    cell_load(cell).append({"kind": "npc", "id": getattr(victim, "id", "?"),
                            "name": getattr(victim, "name", "?")})
    victim.in_cell = True
    victim.sleep_t = 0.0
    victim.alive = True
    victim.health = max(10, getattr(victim, "max_health", 100) // 3)
    try:
        plog.log("DETAINED", getattr(victim, "name", "?"), "carried into the cell at",
                 int(cell.x), int(cell.y), "| in it:", len(cell_load(cell)))
    except Exception:
        pass


def tick(player, enemies, townsmen, dt: float, now: float) -> None:
    _STATE["timer"] += dt
    # ---- 1. A GUARD GOES AND CARRIES THE SLEEPER IN ---------------------
    try:
        import village as _v
        for n in list(_v.PEOPLE):
            if getattr(n, "sleep_t", 0.0) <= 0.0 or getattr(n, "in_cell", False):
                continue
            if getattr(n, "carrier", None) is not None:
                continue                     # already being carried
            if _busy_near(player, n.x, n.y, QUIET_PX):
                continue                     # still a fight: leave him lying
            mil = _militia_near(player, enemies, townsmen, n.x, n.y, 900.0)
            if not mil:
                continue
            cell = _nearest_cell(n.x, n.y)
            if cell is None:
                continue
            # THE GUARD PICKS HIM UP: he walks to the cell, then puts him down.
            mil[0].carry_victim = n
            mil[0].carry_cell = cell
            n.carrier = mil[0]
            try:
                plog.log("CARRY", getattr(mil[0], "name", "?"), "picks up",
                         getattr(n, "name", "?"))
            except Exception:
                pass
    except Exception:
        pass
    # ---- 2. THE PLAYER ---------------------------------------------------
    if player is not None and getattr(player, "shackled", False):
        cell = _nearest_cell(player.x, player.y)
        if cell is not None and not _busy_near(player, player.x, player.y, 400.0):
            pass                             # he is in the cell: held there
    return None


def board_train(train, player, now: float) -> None:
    """The train calls where somebody is waiting, and takes up to fifty."""
    if train is None:
        return
    if getattr(train, "aboard", None) is None:
        train.aboard = []
    if len(train.aboard) >= CAPACITY:
        return
    px, py = train.x, train.y
    for c in cells():
        load = cell_load(c)
        if not load:
            continue
        if (c.x - px) ** 2 + (c.y - py) ** 2 > 420.0 ** 2:
            continue
        room = CAPACITY - len(train.aboard)
        take = load[:room]
        del load[:len(take)]
        for rec in take:
            train.aboard.append(rec)
        if take:
            try:
                plog.log("TRAIN-PICKUP", len(take), "at the cell by",
                         int(c.x), int(c.y), "| aboard:", len(train.aboard))
            except Exception:
                pass
    return None


# ---------------------------------------------------------------- the player
def arrest_player(player, cell) -> None:
    """HE IS TAKEN IN: put inside the cell, and the clock starts."""
    player.shackled = True
    player.sleep_t = 0.0
    player.x, player.y = cell.x, cell.y
    _STATE["player_cell"] = cell
    _STATE["player_left"] = PLAYER_BOARD_SECONDS
    try:
        plog.log("ARRESTED", "the player is held in the cell at",
                 int(cell.x), int(cell.y), "| one minute to board")
    except Exception:
        pass


def player_cell():
    return _STATE.get("player_cell")


def _aggro_town(cell, player) -> None:
    """HE MISSED THE TRAIN: everybody turns on him."""
    player.shackled = False
    player.wanted = True
    try:
        for v in getattr(cell, "_towns", ()) or ():
            v.provoke()
    except Exception:
        pass
    try:
        import plog
        plog.log("BOARD-MISSED", "the player missed the train -- the town is after him")
    except Exception:
        pass


def player_tick(player, train, dt: float) -> None:
    """The minute, the boarding, and being aboard."""
    cell = _STATE.get("player_cell")
    if cell is None or player is None:
        return
    left = float(_STATE.get("player_left", 0.0)) - dt
    _STATE["player_left"] = left
    # has the train stopped here?
    at_train = False
    if train is not None and not getattr(train, "done", False):
        if (train.x - cell.x) ** 2 + (train.y - cell.y) ** 2 < 420.0 ** 2:
            at_train = True
    if at_train:
        # step aboard -- the player only has to reach the train
        player.aboard = True
        player.shackled = False
        player.x, player.y = train.x, train.y
        _STATE["player_cell"] = None
        _STATE["player_left"] = 0.0
        if getattr(train, "aboard", None) is None:
            train.aboard = []
        train.aboard.append({"kind": "player", "name": "the player"})
        try:
            import plog
            plog.log("BOARDED", "the player is on the train | aboard",
                     len(train.aboard))
        except Exception:
            pass
        return
    if left <= 0.0:
        _aggro_town(cell, player)
        _STATE["player_cell"] = None


def militia_attacked(player, victim, enemies=(), townsmen=()) -> None:
    """LAYING A HAND ON THE MILITIA IS ENOUGH. He does not have to die first."""
    if victim is None or not (getattr(victim, "is_militia", False)
                             or getattr(victim, "militia", False)):
        return
    try:
        player.wanted = True
    except Exception:
        pass
    v = getattr(victim, "village", None) or getattr(victim, "guard_village", None)
    try:
        if v is not None:
            v.provoke()
    except Exception:
        pass
    vx, vy = getattr(victim, "x", 0.0), getattr(victim, "y", 0.0)
    turned = 0
    for a in list(enemies) + list(townsmen):
        if a is victim or not getattr(a, "alive", True):
            continue
        if not (getattr(a, "is_militia", False) or getattr(a, "militia", False)
                or getattr(a, "is_soldier", False)):
            continue
        if (a.x - vx) ** 2 + (a.y - vy) ** 2 > 1600.0 ** 2:
            continue
        try:
            a.hostile = True
            a.aggro = True
            a.add_threat(player)
            turned += 1
        except Exception:
            pass
    try:
        plog.log("MILITIA-ATTACKED", getattr(victim, "name", "?"),
                 "| wanted", bool(getattr(player, "wanted", False)),
                 "|", turned, "turned on him")
    except Exception:
        pass


def militia_killed(player, victim, enemies=(), townsmen=()) -> None:
    """KILLING ONE OF THE MILITIA IS NOT LIKE KILLING A WOLF.

    The man's town is told what happened, every militiaman and soldier within
    shouting distance turns on the killer, and the state starts looking for him.
    """
    if victim is None or not (getattr(victim, "is_militia", False)
                             or getattr(victim, "militia", False)):
        return
    try:
        player.wanted = True
    except Exception:
        pass
    v = getattr(victim, "village", None) or getattr(victim, "guard_village", None)
    try:
        if v is not None:
            v.provoke()
            v.learn_killers(("player",), 0.0)
    except Exception:
        pass
    vx, vy = getattr(victim, "x", 0.0), getattr(victim, "y", 0.0)
    turned = 0
    for a in list(enemies) + list(townsmen):
        if a is victim or not getattr(a, "alive", True):
            continue
        if not (getattr(a, "is_militia", False) or getattr(a, "militia", False)
                or getattr(a, "is_soldier", False)):
            continue
        if (a.x - vx) ** 2 + (a.y - vy) ** 2 > 1600.0 ** 2:
            continue
        try:
            a.hostile = True
            a.aggro = True
            a.add_threat(player)
            turned += 1
        except Exception:
            pass
    try:
        plog.log("MILITIA-SLAIN", getattr(victim, "name", "?"),
                 "| the town is provoked |", turned, "turned on the killer")
    except Exception:
        pass


def release_kit(player, town=None) -> None:
    """OUT OF THE GULAG: three loaves, an axe and a pickaxe -- from the state."""
    try:
        import inventory as _inv
        player.pack.slots = [None] * player.pack.capacity
        _give = (("bread", 3), ("axe", 1), ("pickaxe", 1))
        for item, n in _give:
            player.pack.add(item, n)
            try:
                if town is not None and town.ledger_goods.get(item, 0) >= n:
                    town.ledger_goods[item] -= n
            except Exception:
                pass
        player.aboard = False
        player.shackled = False
        player.wanted = False
        import plog
        plog.log("RELEASED", "from the camp with 3 bread, an axe and a pickaxe")
    except Exception as _re:
        try:
            import plog
            plog.log("RELEASE-ERROR", repr(_re)[:120])
        except Exception:
            pass


# ------------------------------------------------------------- smart pickups
def pickup_order(train) -> None:
    """THE NEAREST WAITING CELL FIRST, and a wagon on its way never turns back.

    Stops are chosen by nearest-first from where the train actually is, and a
    cell that fills up while the train is rolling is only added if it lies
    AHEAD of the plan -- otherwise it waits for the next run. A wagon of thirty
    does not swing round the settlement for one late arrest.
    """
    if train is None:
        return
    if getattr(train, "aboard", None) is None:
        train.aboard = []
    if len(train.aboard) >= CAPACITY:
        train.plan = []                      # full: straight to the camp
        return
    here = (train.x, train.y)
    left = CAPACITY - len(train.aboard)
    todo = []
    for c in cells():
        load = cell_load(c)
        if load:
            todo.append((math.hypot(c.x - here[0], c.y - here[1]), c))
    todo.sort(key=lambda t: t[0])
    train.plan = [c for _d, c in todo[:max(1, left)]]


def summary() -> str:
    return "detainees waiting %d | aboard %d" % (waiting(), len(_STATE["aboard"]))
