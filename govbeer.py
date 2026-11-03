"""govbeer.py -- GOVERMENTSKOYE, the cheap state beer.

The resettlement line brings people; the same engine brings drink. Every
settlement the train comes to has thirty crates of E-grade government beer set
down on the platform, into the GOVERNMENT LEDGER -- and there it is sold to
whoever has the coin, at exactly what an E-grade beer fetches.

It is not contraband. It is the state's own bottle, and nobody is arrested for
carrying the state's own bottle.
"""

from __future__ import annotations

import plog

ITEM = "govbeer"
NAME = "Govermentskoye"
GRADE = 1                 # E, on the F..SSS scale: sold as an E beer
PER_STOP = 30
STOP_PX = 260.0           # how close the engine comes to count as a stop
COOLDOWN = 900.0          # one delivery a town a quarter of an hour

_STATE = {"last": {}, "delivered": 0, "crates": 0, "stops": 0}


def deliver(town, now: float = 0.0) -> int:
    """THIRTY CRATES ON THE PLATFORM, into the government's own store."""
    if town is None:
        return 0
    n = PER_STOP
    town.ledger_goods[ITEM] = int(town.ledger_goods.get(ITEM, 0)) + n
    try:
        grades = getattr(town, "ledger_grade", None)
        if isinstance(grades, dict):
            grades[ITEM] = GRADE          # sold exactly as an E beer
    except Exception:
        pass
    try:
        town.gov_beer = int(getattr(town, "gov_beer", 0)) + n
    except Exception:
        pass
    _STATE["delivered"] += 1
    _STATE["crates"] += n
    _STATE["stops"] += 1
    try:
        plog.log("GOVBEER", NAME, n, "crates into the ledger of",
                 getattr(town, "name", "?"),
                 "| grade E | ledger now",
                 int(town.ledger_goods.get(ITEM, 0)))
    except Exception:
        pass
    return n


def tick(train, villages, dt: float, now: float = 0.0) -> int:
    """THE TRAIN STOPS, AND THE BEER COMES OFF IT."""
    if train is None or getattr(train, "done", False):
        return 0
    if not villages:
        return 0
    made = 0
    for town in villages:
        if getattr(town, "is_hub", False):
            continue
        key = id(town)
        last = _STATE["last"].get(key)
        if last is not None and now - last < COOLDOWN:
            continue
        gates = None
        try:
            import fence
            gates = fence.gate_list(town)
        except Exception:
            gates = None
        near = False
        if gates:
            for _side, gx, gy in gates:
                if (train.x - gx) ** 2 + (train.y - gy) ** 2 <= STOP_PX ** 2:
                    near = True
                    break
        else:
            if (train.x - town.x) ** 2 + (train.y - town.y) ** 2 <= 1400.0 ** 2:
                near = True
        if not near:
            continue
        _STATE["last"][key] = now
        made += deliver(town, now)
    return made


def name() -> str:
    return NAME


def crates() -> int:
    return _STATE["crates"]


def stops() -> int:
    return _STATE["stops"]
