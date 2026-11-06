"""socio.py -- MOOD FROM MONEY, once a day, spread over the last minutes.

A man's mood leans on how much coin he holds against the world's median:
less than the median drags him down (at most -10), more lifts him (at most
+10). It is evaluated once at the end of each day for everybody, then applied
lazily over the next ~180 seconds so a thousand men do not all settle at once.
"""
import economy

_median = 0.0
_pending = []
_index = 0
_budget = 0.0
_day = -1
_SPREAD = 180.0          # seconds to settle everybody after the day turns


def _offset(coins, median):
    if median <= 0.0:
        return 0.0
    ratio = coins / median
    off = (ratio - 1.0) * 10.0
    return max(-10.0, min(10.0, off))


def tick(people, now, dt):
    global _median, _pending, _index, _budget, _day
    day = int(now / economy.DAY_LENGTH)
    if day != _day:
        _day = day
        coins = sorted(float(getattr(n, "coins", 0.0) or 0.0)
                       for n in people if getattr(n, "alive", True))
        if coins:
            k = len(coins)
            _median = coins[k // 2] if k % 2 else (coins[k // 2 - 1] + coins[k // 2]) / 2.0
        else:
            _median = 0.0
        _pending = []
        for p in people:
            if not getattr(p, "alive", True):
                continue
            p._soc_off_new = _offset(float(getattr(p, "coins", 0.0) or 0.0), _median)
            _pending.append(p)
        _index = 0
        _budget = 0.0
    if not _pending:
        return
    _budget += len(_pending) * dt / _SPREAD
    count = int(_budget)
    if count <= 0:
        return
    _budget -= count
    for _ in range(count):
        if _index >= len(_pending):
            _pending = []
            break
        p = _pending[_index]
        _index += 1
        old = float(getattr(p, "_soc_off", 0.0))
        new = float(getattr(p, "_soc_off_new", 0.0))
        p.mood = max(0.0, min(100.0, float(getattr(p, "mood", 50.0)) + (new - old)))
        p._soc_off = new
