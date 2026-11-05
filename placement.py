"""placement.py -- THE BUILD MENU'S GEOMETRY AND RULES.

Where the ghost goes, whether it may go there, and the things of his a click
can take down. Extracted from main.py.
"""

from __future__ import annotations

import pygame
import stall as stall_mod


def placement_pos(player, inside_house, inside_mine, cam_x, cam_y,
                  wmouse_x, wmouse_y):
    """The room is 1:1 indoors; the world is ZOOM'd outdoors."""
    if inside_house is not None or (inside_mine is not None
                                    and getattr(inside_mine, "kind", "") == "house"):
        mx, my = pygame.mouse.get_pos()
    else:
        mx, my = wmouse_x, wmouse_y
    return (round((cam_x + mx) / 8.0) * 8.0,
            round((cam_y + my) / 8.0) * 8.0)


def can_place(rect, sight, player, inside_house, built_houses,
              visible_villages, trees) -> bool:
    if inside_house is not None:
        return inside_house.interior.can_place_workshop(rect)
    if sight.collidepoint(player.x, player.y):
        return False
    for house in built_houses:
        if sight.colliderect(house.sight_rect):
            return False
    for village in visible_villages:
        for house in village.houses:
            if sight.colliderect(house.sight_rect):
                return False
    for tree in trees.near(rect.centerx, rect.centery, 170.0):
        if not tree.felled and rect.inflate(16, 16).colliderect(tree.trunk_rect):
            return False
    return True


def own_things(built_plots, placed_work, built_gates, built_fences, built_houses):
    """Everything of HIS a click could take down, smallest first."""
    out = []
    for _r in built_plots:
        out.append((_r, "plot", _r))
    for _wp in placed_work:
        out.append((_wp.rect, "station", _wp))
    for _r in built_gates:
        out.append((_r, "gate", _r))
    for _r in built_fences:
        out.append((_r, "fence", _r))
    for _h in built_houses:
        out.append((_h.rect, "house", _h))
    return out


def demolish_at(wx, wy, player, built_plots, built_gates, built_fences,
                built_houses, placed_work, mark_dirty, inventory, stall_mod) -> str:
    """ONE CLICK TAKES ONE THING OF HIS DOWN -- the smallest under it."""
    hits = [(r.w * r.h, kind, r, obj) for (r, kind, obj) in
            own_things(built_plots, placed_work, built_gates, built_fences,
                       built_houses)
            if r.collidepoint(wx, wy)]
    if not hits:
        return ""
    hits.sort(key=lambda h: h[0])
    _area, kind, rect, obj = hits[0]
    if kind == "plot":
        if rect in built_plots:
            built_plots.remove(rect)
        if isinstance(getattr(player, "plots", None), set):
            player.plots.discard(tuple(rect.topleft))
        mark_dirty()
        return "Plot cleared"
    if kind == "station":
        if obj in placed_work:
            placed_work.remove(obj)
        if obj in (getattr(player, "workplaces", ()) or ()):
            player.workplaces.remove(obj)
        if getattr(obj, "is_stall", False):
            _back = int(getattr(obj, "coins", 0) or 0)
            for _s in list(getattr(obj, "stock", None).slots
                           if getattr(obj, "stock", None) else ()):
                if _s is not None:
                    inventory.add(_s.defn.id, _s.count, _s.quality)
            if _back:
                inventory.add("coin", _back)
            if obj in stall_mod.stalls_of(player):
                stall_mod.stalls_of(player).remove(obj)
            for _n in (getattr(player, "workers", ()) or ()):
                if getattr(_n, "to_market", False):
                    _n.to_market = False
            mark_dirty()
            return "Stall taken down -- goods and %d coin returned" % _back
        mark_dirty()
        return "Stations taken down"
    if kind == "gate" and rect in built_gates:
        built_gates.remove(rect)
        mark_dirty()
        return "Gate taken down"
    if kind == "fence" and rect in built_fences:
        built_fences.remove(rect)
        mark_dirty()
        return "Fence taken down"
    if kind == "house" and obj in built_houses:
        built_houses.remove(obj)
        mark_dirty()
        return "House taken down"
    return ""


def salary_chest(built_houses, hubs, hub_world):
    """WHERE THE MEN ARE PAID FROM: a chest in a house of his, in his hub."""
    for _h in built_houses:
        _in = getattr(_h, "interior", None)
        if _in is None or getattr(_in, "chest", None) is None:
            continue
        if hubs.in_player_hub(_h.rect, hub_world.hubs):
            return _in.chest
    return None


def hub_stall(player, stall_mod):
    """THE PLAYER'S STALL: the one in his own hub, or his only one."""
    try:
        _mine = stall_mod.in_hub(player, getattr(player, "hub", None))
        if _mine is not None:
            return _mine
        _all = stall_mod.stalls_of(player)
        return _all[0] if _all else None
    except Exception:
        return None
