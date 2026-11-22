"""systems.py -- the player's progress outside his body.

Research, the free market's prices and history, the ship's hold, the compass,
and which camps are his.  These are small dictionaries, but losing them lost
the entire progression spine; they are written explicitly.
"""

from __future__ import annotations

from . import codec
from . import context as _context


def snapshot(g) -> dict:
    cards = getattr(g, "research_cards", None)
    market = getattr(g, "market", None)
    compass = getattr(g, "compass_state", None)
    return {
        "research": {
            "cards": dict(cards) if isinstance(cards, dict) else {},
            "active": getattr(g, "research_active", None),
            "points": float(getattr(g, "research_points", 0.0)),
        },
        "market": codec.tidy(market) if isinstance(market, dict) else {},
        "ship_hold": codec.inventory_to_data(getattr(g, "ship_hold", None)),
        "compass": {
            "home": (list(compass.home) if compass is not None
                     and compass.home is not None else None),
            "mode": getattr(compass, "mode", None) if compass is not None else None,
        },
        "player_camps": [codec.uid(c, "camp")
                         for c in (getattr(g, "player_camps", ()) or ())],
        "player_camp": codec.idref(getattr(g, "player_camp", None), "camp"),
        "riding": codec.idref(getattr(g, "riding", None), "animal"),
    }


def apply(g, data, ctx: "_context.Context") -> None:
    data = data or {}
    research = data.get("research") or {}
    cards = research.get("cards") or {}
    if isinstance(getattr(g, "research_cards", None), dict):
        g.research_cards.clear()
        g.research_cards.update(cards)
    else:
        g.research_cards = dict(cards)
    g.research_active = research.get("active")
    g.research_points = float(research.get("points", 0.0))

    market = data.get("market") or {}
    if isinstance(getattr(g, "market", None), dict):
        g.market.clear()
        g.market.update(market)
    else:
        g.market = dict(market)

    codec.inventory_restore(getattr(g, "ship_hold", None), data.get("ship_hold"))

    compass = data.get("compass") or {}
    if getattr(g, "compass_state", None) is not None:
        home = compass.get("home")
        g.compass_state.home = tuple(home) if home else None
        g.compass_state.mode = compass.get("mode")

    camps = []
    for uid in data.get("player_camps") or ():
        camp = ctx.camps.get(uid)
        if camp is not None:
            camps.append(camp)
    if isinstance(getattr(g, "player_camps", None), list):
        g.player_camps[:] = camps
    else:
        g.player_camps = camps
    g.player_camp = (ctx.camps.get(data.get("player_camp") or "")
                     or (camps[0] if camps else None))

    ride = ctx.animals.get(data.get("riding") or "")
    if ride is not None:
        ctx.later(lambda: _ride(g, ride))


def _ride(g, horse) -> None:
    try:
        g.riding = horse
    except Exception:
        pass
