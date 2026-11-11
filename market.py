"""market.py -- THE FREE MARKET: the homeland buys manufactured goods.

Only manufactured products are sellable -- raw leaf, food, wood, seeds and
tools are not -- and hide joins them once Animals is researched. Every good is
anchored at a mid (B) grade price; the grade shifts the price +-5% per step
off B. Demand moves the anchor once a day:

    sold <  100 that day  ->  price x1.05, up to the good's cap
    sold == 100           ->  no change
    sold >  100 that day  ->  price x0.90 for every full 100 sold, down to the
                              good's floor

The two inventories are the player's pack and the ship's hold; the goods are
sold out of the hold.
"""
import economy
import quality

# good -> (anchor, floor, cap) for the MID-GRADE price band
GOODS = {
    "cigar": (10.0, 3.0, 30.0),
    "dried_mushroom": (10.0, 3.0, 30.0),
    "beer": (10.0, 3.0, 30.0),
    "liqueur": (10.0, 3.0, 30.0),
    "mezcal": (10.0, 3.0, 30.0),
    "hide": (30.0, 15.0, 50.0),
    "iron_bar": (100.0, 60.0, 150.0),
}

MID_GRADE = 4          # B, the middle of F..SSS (0..8)
GRADE_STEP = 0.05      # +-5% per grade off B
THRESHOLD = 100        # units a day that keep the price still
HISTORY = 40           # how many daily prices the chart remembers


def spec(good: str):
    """(anchor, floor, cap) for a good."""
    return GOODS.get(good, (10.0, 3.0, 30.0))


def sellable(g):
    """What the homeland will buy right now: hide once Animals is done, iron
    bars once Ironworking is done."""
    out = ["cigar", "dried_mushroom", "beer", "liqueur", "mezcal"]
    try:
        import research
        if research.state(g, "animals") == "done":
            out.append("hide")
        if research.state(g, "ironworking") == "done":
            out.append("iron_bar")
    except Exception:
        pass
    return out


def grade_mult(grade: int) -> float:
    """+-5% per grade step off B (grade 4)."""
    return 1.0 + GRADE_STEP * (int(grade) - MID_GRADE)


def unit_price(base: float, grade: int) -> float:
    """Coin for one unit of a good at this anchor price and grade."""
    return base * grade_mult(grade)


def init(g) -> None:
    g.market = {
        "base": {good: spec(good)[0] for good in GOODS},
        "sold_today": {good: 0 for good in GOODS},
        "day": int(getattr(g, "now", 0.0) / economy.DAY_LENGTH),
        "history": {good: [spec(good)[0]] for good in GOODS},
    }


def record_sale(g, good: str, count: int) -> None:
    """Count today's sale for the daily demand tick."""
    m = getattr(g, "market", None)
    if m is None:
        return
    m["sold_today"][good] = m["sold_today"].get(good, 0) + int(count)


def sell_value(g, good: str, count: int, grade: int) -> float:
    """Coin for selling count units at this grade (the sale is recorded)."""
    if good not in sellable(g):
        return 0.0
    record_sale(g, good, count)
    base = getattr(g, "market", {}).get("base", {}).get(good, spec(good)[0])
    return unit_price(base, grade) * int(count)


def tick(g) -> None:
    """Once a day, move every anchor price by what actually sold."""
    m = getattr(g, "market", None)
    if m is None:
        return
    day = int(g.now / economy.DAY_LENGTH)
    if day <= m.get("day", -1):
        return
    m["day"] = day
    for good in GOODS:
        _anchor, floor, cap = spec(good)
        sold = int(m["sold_today"].get(good, 0))
        base = float(m["base"].get(good, _anchor))
        if sold < THRESHOLD:
            base = min(cap, base * 1.05)
        elif sold > THRESHOLD:
            drops = sold // THRESHOLD      # every full 100 sold = one -10%
            for _ in range(drops):
                base = max(floor, base * 0.90)
                if base <= floor + 1e-6:
                    break
        m["base"][good] = base
        m["sold_today"][good] = 0
        hist = m["history"].setdefault(good, [])
        hist.append(base)
        if len(hist) > HISTORY:
            del hist[:len(hist) - HISTORY]
