"""social_life.py -- the quiet life of a conquered camp.

One small social/economic pulse per camp every 30-60 seconds: a farmer shares
food, a worker buys a meal or a drink from the camp store, or two people talk.
It runs on camp timers, never per NPC per frame.
"""

from __future__ import annotations

import math

import economy
import mood
import relationships


def _people(camp):
    seen = set()
    out = []
    for attr in ("farmers", "warriors", "handlers", "workers", "loggers",
                 "artisans", "researchers", "doctors", "traders", "miners",
                 "smiths", "weavers", "spicemen", "gunsmiths", "unemployed"):
        for p in (getattr(camp, attr, ()) or ()):
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            out.append(p)
    pool = getattr(camp, "people", None)
    if isinstance(pool, list):
        for p in pool:
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            out.append(p)
    return out


def _near(g, a, b, reach=260.0):
    try:
        return math.hypot(a.x - b.x, a.y - b.y) <= reach
    except Exception:
        return False


def _bubble(who, kind, text=None):
    try:
        import comm
        comm.spawn_cloud(who.x, who.y, kind, text=text)
    except Exception:
        pass


def _pay(buyer, seller, item, price, camp, g, now, kind="gift"):
    """Move one item and its price between two people / the camp store."""
    if buyer is None or item is None:
        return False
    if price > 0 and float(getattr(buyer, "coins", 0.0)) < price:
        return False
    have = int((getattr(seller, "stock", {}) or {}).get(item, 0)) if seller else 0
    if seller is not None and have <= 0:
        return False
    if seller is None:
        store = getattr(camp, "ledger_goods", None)
        if not isinstance(store, dict) or int(store.get(item, 0)) <= 0:
            return False
        store[item] = int(store[item]) - 1
    else:
        seller.stock[item] = have - 1
    buyer.stock[item] = int((getattr(buyer, "stock", {}) or {}).get(item, 0)) + 1
    if price > 0 and float(getattr(buyer, "coins", 0)) >= price:
        buyer.coins = float(buyer.coins) - price
        if seller is not None:
            seller.coins = float(getattr(seller, "coins", 0.0)) + price
        else:
            camp.ledger_coins = float(getattr(camp, "ledger_coins", 0.0)) + price
    if seller is not None:
        relationships.observe(buyer, seller, kind, now, g,
                              detail="%s %s" % (kind, item))
    mood.add_thought(buyer, "fed" if item in economy.FOOD else "luxury",
                     3.0 if item in economy.FOOD else 5.0, now, 300.0)
    _bubble(seller or buyer, "need" if item in economy.FOOD else "praise",
            text=item.replace("_", " "))
    try:
        import playlog
        playlog.record(g, "social", action=kind,
                       actor=getattr(seller, "name", "camp"),
                       target=getattr(buyer, "name", "?"), item=item)
    except Exception:
        pass
    return True


def _pulse(g, camp, now):
    people = _people(camp)
    if len(people) < 2:
        return
    rng = getattr(g, "_social_rng", None)
    if rng is None:
        import random
        rng = g._social_rng = random.Random(int(getattr(getattr(g, "world", None), "seed", 1)) ^ 0x50C1A1)
    rng.shuffle(people)
    hungry = [p for p in people if float(getattr(p, "hunger", 0.0)) >= economy.EAT_AT]
    # 1. A hungry person with coin buys food from the camp store.
    for p in hungry:
        if float(getattr(p, "coins", 0.0)) < 1.0:
            continue
        store = getattr(camp, "ledger_goods", None)
        if isinstance(store, dict):
            for item in economy.FOOD:
                if int(store.get(item, 0)) > 0:
                    if _pay(p, None, item, 1.0, camp, g, now, "shared_food"):
                        return
    # 2. A hungry person is fed by someone who has food.
    for p in hungry:
        for q in people:
            if q is p:
                continue
            stock = getattr(q, "stock", {}) or {}
            for item in economy.FOOD:
                if int(stock.get(item, 0)) > 0:
                    if _pay(p, q, item, 0.0, camp, g, now, "shared_food"):
                        return
    # 3. Buy a drink / smoke from someone who has one.
    lux = ("beer", "liqueur", "mezcal", "cigar", "dried_mushroom")
    for buyer in people:
        if float(getattr(buyer, "coins", 0.0)) < 1.0:
            continue
        for seller in people:
            if seller is buyer:
                continue
            stock = getattr(seller, "stock", {}) or {}
            for item in lux:
                if int(stock.get(item, 0)) > 0 and float(getattr(seller, "coins", 0.0)) >= 0:
                    if _pay(buyer, seller, item, 1.0, camp, g, now, "shared_drink"):
                        return
    # 4. Otherwise, two nearby people simply talk.
    for a in people:
        for b in people:
            if a is b or not _near(g, a, b):
                continue
            try:
                import comm
                got = comm.npc_try_chat(a, [b], now)
                if got is not None:
                    try:
                        import playlog
                        playlog.record(g, "social", action="chat",
                                       actor=getattr(a, "name", "?"),
                                       target=getattr(b, "name", "?"))
                    except Exception:
                        pass
                    return
            except Exception:
                continue


def tick(g, dt):
    rng = getattr(g, "_social_rng", None)
    if rng is None:
        import random
        rng = g._social_rng = random.Random(int(getattr(getattr(g, "world", None), "seed", 1)) ^ 0x50C1A1)
    now = float(getattr(g, "now", 0.0))
    for camp in (getattr(g, "native_settlements", {}) or {}).values():
        if not getattr(camp, "conquered", False):
            continue
        if getattr(camp, "_social_t", None) is None:
            camp._social_t = rng.uniform(0.0, 45.0)
        camp._social_t = float(camp._social_t) - float(dt)
        if camp._social_t > 0.0:
            continue
        camp._social_t = rng.uniform(35.0, 60.0)
        try:
            _pulse(g, camp, now)
        except Exception:
            pass
