"""placement.py -- THE BUILD MENU'S GEOMETRY AND RULES.

Where the ghost goes, whether it may go there, and the things of his a click
can take down. Extracted from main.py.
"""

from __future__ import annotations

import pygame
import hubs
import nemesis
import plog
from interior import (BARREL_H, BARREL_W, BREW_H, BREW_W, LAB_H, LAB_W, WORKSHOP_H, WORKSHOP_W)
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


def placement_box(x, y, placing, fence_horizontal, player, build_w, build_h):
    """THE RECT THE GHOST SHOWS for the thing he is placing."""
    _sizes = {"lab": (96, 66), "brewery": (116, 78),
              "smith": (122, 110), "mine": (136, 112),
              "stall": (96, 64)}
    if placing in _sizes:
        _w, _h = _sizes[placing]
        rect = pygame.Rect(int(x - _w / 2), int(y - _h / 2), _w, _h)
        return (0.0, -1.0), rect, rect.inflate(70, 70)
    if placing == "plot":
        rect = pygame.Rect(int(x - 40), int(y - 40), 80, 80)
        return (0.0, -1.0), rect, rect.inflate(8, 8)
    if placing == "demolish":
        rect = pygame.Rect(int(x - 12), int(y - 12), 24, 24)
        return (0.0, -1.0), rect, rect
    if placing in ("fence", "gate"):
        w, h = (60, 16) if placing == "gate" else (140, 16)
        if not fence_horizontal:
            w, h = h, w
        rect = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
        return (0.0, -1.0), rect, rect.inflate(10, 10)
    if placing == "workshop":
        rect = pygame.Rect(int(x - WORKSHOP_W / 2), int(y - WORKSHOP_H / 2),
                           WORKSHOP_W, WORKSHOP_H)
        return (0.0, -1.0), rect, rect.inflate(16, 16)
    if placing == "lab_table":
        rect = pygame.Rect(int(x - LAB_W / 2), int(y - LAB_H / 2), LAB_W, LAB_H)
        return (0.0, -1.0), rect, rect.inflate(16, 16)
    if placing == "brew_table":
        rect = pygame.Rect(int(x - BREW_W / 2), int(y - BREW_H / 2), BREW_W, BREW_H)
        return (0.0, -1.0), rect, rect.inflate(16, 16)
    if placing == "barrel":
        rect = pygame.Rect(int(x - BARREL_W / 2), int(y - BARREL_H / 2),
                           BARREL_W, BARREL_H)
        return (0.0, -1.0), rect, rect.inflate(12, 12)
    dx, dy = player.x - x, player.y - y
    if abs(dx) >= abs(dy):
        facing = (1.0 if dx > 0 else -1.0, 0.0)
    else:
        facing = (0.0, 1.0 if dy > 0 else -1.0)
    if facing[0] != 0.0:
        half_x, half_y = build_h / 2.0, build_w / 2.0
    else:
        half_x, half_y = build_w / 2.0, build_h / 2.0
    rect = pygame.Rect(x - half_x, y - half_y, half_x * 2, half_y * 2)
    return facing, rect, rect.inflate(28, 28)


def commit_plot(placing, plot_start, placement_pos, toast, hubs, villages,
               hub_world, player, built_plots, mark_dirty, nemesis, plog):

    """A PLOT IS A RECTANGLE HE DRAWS: no cost, no bench, just ground."""
    start = plot_start[0]
    plot_start[0] = None
    if start is None:
        return placing
    x2, y2 = placement_pos()
    x1, y1 = start
    rect = pygame.Rect(int(min(x1, x2)), int(min(y1, y2)),
                       int(abs(x2 - x1)), int(abs(y2 - y1)))
    if rect.w < 32 or rect.h < 32:
        toast("Too small for a plot")
        return placing
    if not hubs.land_ok(rect, villages.villages, hub_world.hubs,
                       player.x, player.y):
        toast("Not your land -- the wild, or your own hub")
        return placing
    built_plots.append(rect)
    if not isinstance(getattr(player, "plots", None), set):
        player.plots = set()
    player.plots.add(tuple(rect.topleft))
    player.yard_plots = [tuple(_r) for _r in built_plots]
    mark_dirty()
    if hubs.in_player_hub(rect, hub_world.hubs):
        toast("Plot staked on your own ground")
    else:
        _h = hub_world.add_player_hub(player, rect.inflate(120, 120).copy(),
                                      [], [])
        if _h is not None:
            nemesis.PLACES.append(_h)
            player.work_post = (_h.x, _h.y + 40)
            player.hub = _h
            plog.log("PHASE-HUB", _h.name, "at",
                     "%d,%d" % (int(_h.x), int(_h.y)),
                     "post", player.work_post)
            toast("Plot staked -- this is your hub now:   %s" % _h.name)
        else:
            toast("Plot staked")
    placing = None
    pygame.mouse.set_visible(False)
    return placing
