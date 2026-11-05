"""placement.py -- THE BUILD MENU'S GEOMETRY AND RULES.

Where the ghost goes, whether it may go there, and the things of his a click
can take down. Extracted from main.py.
"""

from __future__ import annotations

import pygame


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
