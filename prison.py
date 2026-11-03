"""prison.py -- THE CAMP'S PEOPLE.

A man inside the camp is a PRISONER: a new trade, no wage, three loaves and
tools, and ninety-five parts of every hundred of his labour taken by the state
the moment it is made. The camp is a hellhole on purpose -- the resettlement
campaign exists to feed it.

And the perimeter is real: a prisoner who comes too near the fence is shot
where he stands and left there.
"""

from __future__ import annotations

import math

import plog

PERIM = 120.0            # how close to the fence a prisoner may come
SKIM = 0.95              # the state's cut
KIT = (("bread", 3), ("axe", 1), ("pickaxe", 1))
SKIM_EVERY = 8.0
GUARD_BREAD = 2          # loaves a camp warder draws a day
DAY = 600.0

_STATE = {"mark": set(), "prisoners": [], "skim_t": 0.0, "day_t": 0.0,
          "day": 0, "ledger": {}, "skimmed": 0, "shot": 0, "made": 0}


def _camp():
    try:
        import gulag
        return gulag.walls()
    except Exception:
        return []


def rect():
    ws = _camp()
    if not ws:
        return None
    xs = [w.x for w in ws] + [w.x + w.w for w in ws]
    ys = [w.y for w in ws] + [w.y + w.h for w in ws]
    return (min(xs), min(ys), max(xs), max(ys))


def inside(x: float, y: float) -> bool:
    r = rect()
    if r is None:
        return False
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


def near_perimeter(x: float, y: float) -> bool:
    r = rect()
    if r is None:
        return False
    d = min(x - r[0], r[2] - x, y - r[1], r[3] - y)
    return 0.0 <= d <= PERIM


def _give_kit(npc) -> None:
    """THREE LOAVES, AN AXE AND A PICKAXE -- the state's issue, checked."""
    try:
        if getattr(npc, "bag", None) is None:
            import inventory
            npc.bag = inventory.Inventory(32)
        for item, n in KIT:
            have = 0
            for _m in ("count_of", "count"):
                try:
                    have = int(getattr(npc.bag, _m)(item) or 0)
                    break
                except Exception:
                    continue
            if have < n:
                npc.bag.add(item, n - have)
    except Exception as _ke:
        try:
            import plog
            plog.log("KIT-ERROR", repr(_ke)[:100])
        except Exception:
            pass


def make_prisoner(npc, now: float = 0.0) -> bool:
    """A TRADE OF HIS OWN, NO WAGE, AND THE STATE'S TOOLS."""
    if npc is None or getattr(npc, "prisoner", False):
        return False
    npc.prisoner = True
    npc.job = "prisoner"
    npc.wage = 0
    npc.paid = 0
    npc.pay_day = 0
    npc.asleep = False
    npc.on_duty = False
    _give_kit(npc)
    if id(npc) not in _STATE["mark"]:
        _STATE["mark"].add(id(npc))
        _STATE["prisoners"].append(npc)
        _STATE["made"] += 1
        try:
            plog.log("PRISONER", getattr(npc, "name", "?"),
                     "entered the camp | job prisoner | 3 bread, axe, pickaxe")
        except Exception:
            pass
    return True


def _state_ledger(npc):
    """The government's books: the nearest settlement's, else the country's."""
    try:
        import village as _v
        best, bd = None, 1e18
        for v in getattr(_v, "VILLAGES", ()) or ():
            d = (v.x - npc.x) ** 2 + (v.y - npc.y) ** 2
            if d < bd:
                best, bd = v, d
        if best is not None and hasattr(best, "ledger_goods"):
            return best.ledger_goods
    except Exception:
        pass
    return _STATE["ledger"]


def skim(npc) -> int:
    """NINETY-FIVE PARTS IN A HUNDRED, OUT OF HIS PACK AND INTO THE BOOKS."""
    bag = getattr(npc, "bag", None)
    if bag is None:
        return 0
    took = 0
    led = _state_ledger(npc)
    try:
        slots = list(getattr(bag, "slots", ()))
    except Exception:
        return 0
    _keep = {i for i, _n in KIT}      # his ration and his tools are his
    for st in slots:
        if st is None:
            continue
        n = int(getattr(st, "count", 0) or 0)
        if n <= 0:
            continue
        _defn = getattr(st, "defn", None)
        if getattr(_defn, "id", None) in _keep:
            continue
        give = int(n * SKIM)        # floor: one axe is not confiscated
        if give <= 0:
            continue
        give = min(give, n)
        st.count = n - give
        _defn = getattr(st, "defn", None)
        name = getattr(_defn, "id", None) or getattr(_defn, "item_id", None) or "?"
        led[name] = led.get(name, 0) + give
        _STATE["ledger"][name] = _STATE["ledger"].get(name, 0) + give
        took += give
    try:
        bag.pack() if hasattr(bag, "pack") else None
    except Exception:
        pass
    _STATE["skimmed"] += took
    return took


def _nearest_warder(enemies, x, y):
    best, bd = None, 1e18
    for e in enemies or ():
        if not getattr(e, "gulag", False) or not getattr(e, "alive", True):
            continue
        d = (e.x - x) ** 2 + (e.y - y) ** 2
        if d < bd:
            best, bd = e, d
    return best, math.sqrt(bd) if bd < 1e17 else -1.0


def tick(player, enemies, townsmen, dt: float, now: float = 0.0,
         combat=None) -> None:
    _STATE["skim_t"] += dt
    _STATE["day_t"] += dt

    # -- the camp roll: anyone inside is a prisoner, given a trade ----------
    if _STATE["skim_t"] >= 2.0:
        _STATE["skim_t"] = 0.0
        alive = []
        for npc in _STATE["prisoners"]:
            if getattr(npc, "alive", True) and inside(getattr(npc, "x", 0.0),
                                                      getattr(npc, "y", 0.0)):
                alive.append(npc)
        _STATE["prisoners"] = alive
        for npc in townsmen or ():
            if not getattr(npc, "alive", True):
                continue
            x, y = getattr(npc, "x", 0.0), getattr(npc, "y", 0.0)
            if inside(x, y):
                make_prisoner(npc, now)

    # -- the state takes its cut -------------------------------------------
    if _STATE["skim_t"] >= SKIM_EVERY:
        pass
    # (skim runs on its own clock, below)
    _STATE.setdefault("cut_t", 0.0)
    _STATE["cut_t"] += dt
    if _STATE["cut_t"] >= SKIM_EVERY:
        _STATE["cut_t"] = 0.0
        tot = 0
        for npc in _STATE["prisoners"]:
            if getattr(npc, "alive", True):
                tot += skim(npc)
        if tot:
            try:
                plog.log("SKIM", tot, "goods taken from the prisoners |",
                         "state total", sum(_STATE["ledger"].values()))
            except Exception:
                pass

    # -- the perimeter ------------------------------------------------------
    for npc in _STATE["prisoners"]:
        if not getattr(npc, "alive", True):
            continue
        if not near_perimeter(getattr(npc, "x", 0.0), getattr(npc, "y", 0.0)):
            continue
        w, d = _nearest_warder(enemies, npc.x, npc.y)
        if w is None or d > 1800.0:
            continue
        _STATE["shot"] += 1
        _fired = False
        # A REAL ROUND, FROM THE WARDER'S OWN RIFLE: the frame's bullet loop
        # carries it into the man, exactly as it would for any other target.
        if combat is not None:
            try:
                import guns as _guns
                _ang = math.atan2(npc.y - w.y, npc.x - w.x)
                combat.fire(w.x, w.y, _ang, max(1.0, d + 40.0),
                            owner="enemy",
                            damage=_guns.DAMAGE[_guns.RIFLE],
                            team=getattr(w, "nation", None),
                            shooter=w, dart=False)
                _fired = True
            except Exception as _fe:
                try:
                    plog.log("PERIM-FIRE-ERR", repr(_fe)[:100])
                except Exception:
                    pass
        if not _fired:
            try:
                import lanes_mp
                lanes_mp._W.damage(npc, 9999)
            except Exception:
                try:
                    npc.take_damage(9999)
                except Exception:
                    npc.alive = False
        try:
            plog.log("PERIMETER-SHOT", getattr(npc, "name", "?"),
                     "came within", int(d), "px of a warder,", int(PERIM),
                     "px of the fence | left where he fell")
        except Exception:
            pass

    # -- a warder's bread ---------------------------------------------------
    if _STATE["day_t"] >= DAY:
        _STATE["day_t"] = 0.0
        _STATE["day"] += 1
        fed = 0
        for e in enemies or ():
            if not getattr(e, "gulag", False):
                continue
            try:
                if getattr(e, "bag", None) is None:
                    import inventory as _inv
                    e.bag = _inv.Inventory(24)
                e.bag.add("bread", GUARD_BREAD)
                fed += 1
            except Exception:
                pass
        if fed:
            try:
                plog.log("WARDER-BREAD", fed, "camp warders drew",
                         GUARD_BREAD, "loaves | day", _STATE["day"])
            except Exception:
                pass


def prisoners() -> list:
    return list(_STATE["prisoners"])


def skimmed() -> int:
    return _STATE["skimmed"]


def shot() -> int:
    return _STATE["shot"]


def ledger() -> dict:
    return dict(_STATE["ledger"])
