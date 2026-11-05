"""placement.py -- THE BUILD MENU'S GEOMETRY AND RULES.

Where the ghost goes, whether it may go there, and the things of his a click
can take down. Extracted from main.py.
"""

from __future__ import annotations

import pygame
from village import House, ROOFS
import industry
import fence
import math
import random
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


def try_place(g):
    placing = g.placing

    x, y = g.placement_pos()
    if placing == "demolish":
        _wm = g.cam_x + (pygame.mouse.get_pos()[0] / g.zoom)
        _wm2 = g.cam_y + (pygame.mouse.get_pos()[1] / g.zoom)
        _said = g.demolish_at(_wm, _wm2)
        g.toast(_said or "Nothing of yours there")
        placing = None
        pygame.mouse.set_visible(False)
        return
    if placing == "plot":
        return                      # a plot is drawn, not clicked (see below)
    facing, rect, sight = g.placement_box(x, y)
    if placing in ("fence", "gate"):
        if not g.can_place(rect, sight):
            g.toast("Can't build there")
            return
        if not hubs.land_ok(rect, g.villages.g.villages, g.hub_world.hubs,
                           g.player.x, g.player.y):
            g.toast("Not your land -- the wild, or your own hub")
            return
        cost = 30 if placing == "gate" else 10
        name = "Gate" if placing == "gate" else "Fence"
        if not g.test_mode:
            if g.inventory.count_of("wood") < cost:
                g.toast(f"Need {cost} wood")
                placing = None
                pygame.mouse.set_visible(False)
                return
            g.inventory.consume("wood", cost)
        (g.built_gates if placing == "gate" else g.built_fences).append(rect)
        # A YARD HE HAS CLOSED IN THE WILD IS HIS HUB. Checked each time he
        # sets a piece down -- the flood fill is a few thousand cells and it
        # only ever runs while he is building.
        try:
            _yard, _ring = fence.enclosure(g.built_fences + g.built_gates,
                                           g.player.x, g.player.y)
            if _yard is not None:
                _wild = True
                for _v in (list(g.villages.g.villages)
                           + list(getattr(g.hub_world, "hubs", ()))):
                    _fr = getattr(_v, "fence_rect", None)
                    if _fr is not None and _fr.colliderect(
                            _yard.inflate(600, 600)):
                        _wild = False
                        break
                if _wild:
                    _h = g.hub_world.add_player_hub(g.player, _yard, _ring,
                                                  g.built_gates)
                    if _h is not None:
                        nemesis.PLACES.append(_h)
                        g.toast("This is your hub now:   %s" % _h.name)
                        plog.log("HUB", "fenced", _h.name, "at",
                                 "%d,%d" % (int(_h.x), int(_h.y)),
                                 "%dx%d" % (_yard.w, _yard.h))
        except Exception as _he:
            plog.log("HUB-ERROR", repr(_he)[:200])
        g.mark_dirty()
        g.toast(f"{name} built" if g.test_mode else f"{name} built   -{cost} wood")
        placing = None
        pygame.mouse.set_visible(False)
        return
    if placing == "stall":
        # A STALL STANDS IN HIS HUB AND NOWHERE ELSE. The land question is
        # asked first, so a man who tries to put one in the open is told
        # why and does not lose the timber.
        if not hubs.in_player_hub(rect, g.hub_world.hubs):
            g.toast("A stall must stand inside your own hub")
            placing = None
            pygame.mouse.set_visible(False)
            return
        if not g.can_place(rect, sight):
            g.toast("No clear ground here")
            return
        _hub = next((h for h in g.hub_world.hubs
                     if getattr(h, "is_player_hub", False)
                     and h.fence_rect.colliderect(rect)), None)
        if _hub is None:
            g.toast("A stall must stand inside your own hub")
            placing = None
            pygame.mouse.set_visible(False)
            return
        if stall_mod.in_hub(g.player, _hub) is not None:
            g.toast("You already have a stall in this hub")
            placing = None
            pygame.mouse.set_visible(False)
            return
        _cost = g.build_materials("stall")
        if not g.test_mode:
            for _it, _q in _cost.items():
                if g.inventory.count_of(_it) < _q:
                    g.toast("Need %d %s" % (_q, _it))
                    placing = None
                    pygame.mouse.set_visible(False)
                    return
            for _it, _q in _cost.items():
                g.inventory.consume(_it, _q)
        _st = stall_mod.add(g.player, _hub, x, y)
        if _st is None:
            g.toast("A stall must stand inside your own hub")
            placing = None
            pygame.mouse.set_visible(False)
            return
        g.placed_work.append(_st)
        g.mark_dirty()
        g.toast("Market stall built   -%d wood" % int(_cost.get("wood", 0)))
        placing = None
        pygame.mouse.set_visible(False)
        return
    if placing in ("lab", "brewery", "smith", "mine", "dummy", "target"):
        _wp = industry.Workplace(placing, x, y, random.randrange(1 << 30))
        if not hubs.land_ok(_wp.rect, g.villages.g.villages, g.hub_world.hubs,
                           g.player.x, g.player.y):
            g.toast("Not your land -- the wild, or your own hub")
            return
        if not g.can_place(_wp.rect, _wp.rect.inflate(70, 70)):
            g.toast("No clear ground here")
            return
        _cost = g.build_materials(placing)
        if not g.test_mode:
            for _it, _q in _cost.items():
                if g.inventory.count_of(_it) < _q:
                    g.toast("Need %d %s" % (_q, _it))
                    placing = None
                    pygame.mouse.set_visible(False)
                    return
            for _it, _q in _cost.items():
                g.inventory.consume(_it, _q)
        _wp.worker = None
        _wp.owner = g.player
        g.placed_work.append(_wp)
        if not isinstance(getattr(g.player, "workplaces", None), list):
            g.player.workplaces = []
        g.player.workplaces.append(_wp)          # he can put a man to it
        g.mark_dirty()
        _land = hubs.in_player_hub(_wp.rect, g.hub_world.hubs)
        if not _land:
            # THE WILD IS HIS NOW. A bench, a forge or a shaft on open
            # ground is a claim: the yard around it is his hub.
            _yard = _wp.rect.inflate(320, 320).copy()
            _h = g.hub_world.add_player_hub(g.player, _yard, [], [])
            if _h is not None:
                nemesis.PLACES.append(_h)
                g.player.work_post = (_h.x, _h.y + 40)
                g.player.hub = _h
                plog.log("PHASE-HUB", _h.name, "at",
                         "%d,%d" % (int(_h.x), int(_h.y)),
                         "post", g.player.work_post)
                g.toast("Built -- this is your hub now:   %s" % _h.name)
            else:
                g.toast("Built")
        else:
            g.toast("Built on your own ground")
        placing = None
        pygame.mouse.set_visible(False)
        return
    if placing in ("brew_table", "barrel"):
        name = "Brewing table" if placing == "brew_table" else "Barrel"
        if g.inside_house is None:
            g.toast("%s can only be built inside a house" % name)
        elif not (g.inside_house.interior.can_place_brew(rect)
                  if placing == "brew_table"
                  else g.inside_house.interior.can_place_barrel(rect)):
            g.toast("No clear floor space here")
            return
        elif not g.test_mode and g.inventory.count_of("wood") < g.build_cost(placing):
            g.toast("Need %d wood" % g.build_cost(placing))
        else:
            if not g.test_mode:
                g.inventory.consume("wood", g.build_cost(placing))
            if placing == "brew_table":
                g.inside_house.interior.place_brew(x, y)
            else:
                g.inside_house.interior.place_barrel(x, y)
            g.mark_dirty()
            g.toast("%s built" % name if g.test_mode
                  else "%s built   -%d wood" % (name, g.build_cost(placing)))
        placing = None
        pygame.mouse.set_visible(False)
        return
    if placing == "lab_table":
        if g.inside_house is None:
            g.toast("A lab table can only be built inside a house")
        elif not g.inside_house.interior.can_place_lab(rect):
            g.toast("No clear floor space here")
            return
        elif not g.test_mode and g.inventory.count_of("wood") < g.build_cost("lab_table"):
            g.toast("Need %d wood" % g.build_cost("lab_table"))
        else:
            if not g.test_mode:
                g.inventory.consume("wood", g.build_cost("lab_table"))
            g.inside_house.interior.place_lab(x, y)
            g.mark_dirty()
            g.toast("Lab table built" if g.test_mode
                  else "Lab table built   -%d wood" % g.build_cost("lab_table"))
        placing = None
        pygame.mouse.set_visible(False)
        return
    if placing == "workshop":
        if g.inside_house is None:
            g.toast("Workshops can only be built inside a house")
        elif not g.inside_house.interior.can_place_workshop(rect):
            g.toast("No clear floor space here")
            return
        elif not g.test_mode and g.inventory.count_of("wood") < g.build_cost("workshop"):
            g.toast(f"Need {g.build_cost('workshop')} wood")
        else:
            if not g.test_mode:
                g.inventory.consume("wood", g.build_cost("workshop"))
            g.inside_house.interior.place_workshop(x, y)
            g.mark_dirty()
            g.toast("Workshop built" if g.test_mode
                  else f"Workshop built   -{g.build_cost('workshop')} wood")
        placing = None
        pygame.mouse.set_visible(False)
        return
    if not g.can_place(rect, sight):
        g.toast("Can't build there")
        return
    if not g.test_mode:
        if g.inventory.count_of("wood") < g.build_house_cost:
            g.toast(f"Need {g.build_house_cost} wood")
            placing = None
            pygame.mouse.set_visible(False)
            return
        g.inventory.consume("wood", g.build_house_cost)
    seed = random.randint(0, 2 ** 31)
    house = House(x, y, g.build_w, g.build_h, random.choice(ROOFS), facing, seed)
    house.build_seed = seed
    house.interior_seed = random.randint(0, 2 ** 31)
    house.interior = Interior(house.interior_seed, tuple(house.facing))
    house.enterable = True
    g.built_houses.append(house)
    g.mark_dirty()
    g.toast(f"House built   -{g.build_house_cost} wood")
    placing = None
    pygame.mouse.set_visible(False)
    return placing



def draw_placing(g):

    if g.placing is None:
        return
    _amx, _amy = g.wmouse_x, g.wmouse_y      # the world mouse, indoors too
    aim_dx = (g.cam_x + _amx) - g.player.x
    aim_dy = (g.cam_y + _amy) - g.player.y
    length = math.hypot(aim_dx, aim_dy) or 1.0
    g.player.facing = (aim_dx / length, aim_dy / length)
    px_, py_ = g.placement_pos()
    _facing, box, sight = g.placement_box(px_, py_)
    ok = g.can_place(box, sight)
    colour = (126, 224, 148) if ok else (226, 96, 84)
    rr = pygame.Rect(box.x - g.cam_x, box.y - g.cam_y, box.w, box.h)
    sr = pygame.Rect(sight.x - g.cam_x, sight.y - g.cam_y, sight.w, sight.h)
    fill = pygame.Surface(rr.size, pygame.SRCALPHA)
    fill.fill((colour[0], colour[1], colour[2], 48))
    g.screen.blit(fill, rr.topleft)
    pygame.draw.rect(g.screen, colour, sr, 2)
    pygame.draw.rect(g.screen, colour, rr, 2)
    hint_text = "Click to place   ·   right-click to cancel"
    if g.placing in ("fence", "gate"):
        hint_text = "Click to place   ·   R to rotate   ·   right-click to cancel"
    elif g.placing == "plot":
        hint_text = "Drag a rectangle   ·   right-click to cancel"
    elif g.placing == "demolish":
        hint_text = "Click a thing of yours to take it down   ·   right-click to cancel"
    if g.placing == "plot" and g.plot_start[0] is not None:
        # THE RECTANGLE HE IS DRAWING, live under the mouse.
        _sx, _sy = g.plot_start[0]
        _ex, _ey = px_, py_
        _drag = pygame.Rect(int(min(_sx, _ex)), int(min(_sy, _ey)),
                            int(abs(_ex - _sx)), int(abs(_ey - _sy)))
        _ok = hubs.land_ok(_drag, g.villages.g.villages, g.hub_world.hubs,
                           g.player.x, g.player.y)
        _col = (126, 224, 148) if _ok else (226, 96, 84)
        _dr = pygame.Rect(_drag.x - g.cam_x, _drag.y - g.cam_y,
                          _drag.w, _drag.h)
        _df = pygame.Surface((max(1, _dr.w), max(1, _dr.h)), pygame.SRCALPHA)
        _df.fill((_col[0], _col[1], _col[2], 48))
        g.screen.blit(_df, _dr.topleft)
        pygame.draw.rect(g.screen, _col, _dr, 2)
    hint = g.font.render(hint_text, True, (236, 236, 240))
    g.screen.blit(hint, (g.vw // 2 - hint.get_width() // 2, int(g.vh * 0.82)))

# -- house interiors ----------------------------------------------------


def tile_is_mine(tx, ty, player, built_houses, built_fences, player_hunted,
                 tile, fence):
    """True for land inside the player's own fenced homestead."""
    _p = getattr(player, "farm_plot", None)
    _town = getattr(player, "settled_at", None)
    if _p is not None and _town is not None:
        try:
            _ctx, _cty, _k = _town.farm_plots[_p]
            if (_ctx, _cty) == (tx, ty):
                return True
        except Exception:
            pass
    if not built_houses or not built_fences:
        return False
    if player_hunted():
        return False
    x = tx * tile + tile / 2.0
    y = ty * tile + tile / 2.0
    for rect in fence.homesteads(built_fences, built_houses):
        if rect.collidepoint(x, y):
            return True
    return False
