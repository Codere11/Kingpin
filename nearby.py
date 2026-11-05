"""nearby.py -- WHAT THE PLAYER IS STANDING AT, AND HIS HARVEST SHARE.

The board, the stall, the village workplace, the resale price at the nearest
town, and the fifth of a harvest he owes the village. Extracted from main.py.
"""

from __future__ import annotations

import math

import economy
import stall as stall_mod


def near_board(player, visible_villages, reach: float):
    for v in visible_villages:
        if math.hypot(player.x - v.board.centerx,
                      player.y - v.board.centery) < reach + 26.0:
            return v
    return None


def near_stall(player):
    """The stall he is standing at -- the building, not its middle."""
    for _st in stall_mod.stalls_of(player):
        if _st.rect.inflate(150, 150).collidepoint(player.x, player.y):
            return _st
    return None


def near_workplace(player, placed_work, visible_villages):
    """Whichever village workplace the player is at, if any."""
    for _wp in placed_work:
        if _wp.rect.inflate(170, 170).collidepoint(player.x, player.y):
            return _wp
    for _v in visible_villages:
        for _wp in _v.workplaces:
            if _wp.rect.inflate(170, 170).collidepoint(player.x, player.y):
                return _wp
    try:
        import gulag as _g
        _p = _g.prison()
        if _p is not None and _p.rect.inflate(170, 170).collidepoint(player.x,
                                                                  player.y):
            return _p
    except Exception:
        pass
    return None


def town_price_for(player, visible_villages, item, grade) -> int:
    """WHAT A CART COULD RESELL THIS LOT FOR AT THE NEAREST TOWN."""
    try:
        _best, _bd = None, 1e18
        for _v in visible_villages:
            if getattr(_v, "is_hub", False):
                continue
            _d = (_v.x - player.x) ** 2 + (_v.y - player.y) ** 2
            if _d < _bd:
                _best, _bd = _v, _d
        if _best is None:
            return 0
        return int(economy.prospect(_best, item, int(grade)))
    except Exception:
        return 0


def pay_share(item: str, gained: int, player, inventory, toast) -> int:
    """THE PLAYER PAYS WHAT EVERYBODY ELSE PAYS: A FIFTH, IN KIND.

    Taken out of the pack he has just filled, at the moment he fills it, to
    the village that gave him his post. No post and no village means nothing
    is owed: an unemployed man works for himself.
    """
    town = getattr(player, "settled_at", None)
    if town is None or gained <= 0 or not getattr(player, "job", None):
        return 0
    if not (item in economy.TAXED_OUTPUT or item == "wood"
            or item in economy.FOOD):
        return 0
    frac = getattr(player, "_tax_frac", 0.0) + gained * economy.HARVEST_TAX
    tax = int(frac)
    player._tax_frac = frac - tax
    if tax <= 0:
        return 0
    take = min(tax, int(inventory.count_of(item)))
    if take <= 0:
        return 0
    inventory.consume(item, take)
    economy.store_add(town, item, take)
    toast("The village's share   -%d %s" % (take, item))
    return take
