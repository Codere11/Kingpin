"""social_life.py -- the quiet life of a conquered camp.

One small social pulse per camp every 35-60 seconds.  People exchange real
goods with each other, share food, or talk.  There is no camp store, no hidden
ledger market and no internal coin economy.
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


def _near(a, b, reach=260.0):
    try:
        return math.hypot(a.x - b.x, a.y - b.y) <= reach
    except Exception:
        return False


def _bubble(who, kind, text=None):
    try:
        import comm
        comm.spawn_cloud(who.x, who.y, kind, text=text, speaker=who)
    except Exception:
        pass


def _exchange(buyer, seller, item, camp, g, now, kind="gift"):
    """Move one real item between two people.  No coin changes hands."""
    if buyer is None or seller is None or item is None:
        return False
    stock = getattr(seller, "stock", None)
    if not isinstance(stock, dict) or int(stock.get(item, 0)) <= 0:
        return False
    try:
        accepted = relationships.share_reaction(
            buyer, seller, kind, now, g, item=item)
    except Exception:
        accepted = True
    if not accepted:
        return True
    stock[item] = int(stock[item]) - 1
    buyer.stock[item] = int((getattr(buyer, "stock", {}) or {}).get(item, 0)) + 1
    # FIRST TASTE: a luxury handed to someone who has never tried it is
    # consumed now.  That is what creates the first craving; before this, the
    # product is not a need at all.
    if item in economy.LUXURY and not economy.has_tried(buyer, item):
        try:
            buyer.stock[item] = max(0, int(buyer.stock.get(item, 0)) - 1)
            import mind as _mind
            _mind.consume(buyer, item, now)
        except Exception:
            pass
    mood.add_thought(buyer, "fed" if item in economy.FOOD else "luxury",
                     3.0 if item in economy.FOOD else 5.0, now, 300.0)
    _bubble(seller, "need" if item in economy.FOOD else "praise",
            text=item.replace("_", " "))
    try:
        import playlog
        playlog.record(g, "social", action=kind,
                       actor=getattr(seller, "name", "?"),
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
        rng = g._social_rng = random.Random(
            int(getattr(getattr(g, "world", None), "seed", 1)) ^ 0x50C1A1)
    rng.shuffle(people)

    hungry = [p for p in people if float(getattr(p, "hunger", 0.0)) >= economy.EAT_AT]
    # 1. A hungry person is fed by someone who has food.
    for p in hungry:
        for q in people:
            if q is p:
                continue
            stock = getattr(q, "stock", {}) or {}
            for item in economy.FOOD:
                if int(stock.get(item, 0)) > 0:
                    if _exchange(p, q, item, camp, g, now, "shared_food"):
                        return
    # 2. Random barter: one person has a spare luxury/tool, another gets it.
    barter = ("beer", "liqueur", "mezcal", "cigar", "dried_mushroom",
              "bread", "berries", "cactus_fruit", "axe", "shovel")
    for seller in people:
        stock = getattr(seller, "stock", {}) or {}
        for item in barter:
            if int(stock.get(item, 0)) <= 0:
                continue
            for buyer in people:
                if buyer is seller:
                    continue
                _kind = "shared_food" if item in economy.FOOD else "shared_drink"
                if _exchange(buyer, seller, item, camp, g, now, _kind):
                    return
    # 3. Otherwise, ask for a proper walk-up conversation.  The conversation
    # manager handles the approach, the single active slot and the talk timer.
    for a in people:
        for b in people:
            if a is b:
                continue
            try:
                import conversation
                if conversation.request_npc(g, a, b, now):
                    return
            except Exception:
                continue


def tick(g, dt):
    rng = getattr(g, "_social_rng", None)
    if rng is None:
        import random
        rng = g._social_rng = random.Random(
            int(getattr(getattr(g, "world", None), "seed", 1)) ^ 0x50C1A1)
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
