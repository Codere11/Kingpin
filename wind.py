"""wind.py -- a local, player-centred breeze.

It is deliberately a visual effect, not weather simulation: a gust travels
around the player, bends tobacco/berry/cotton plants, and makes the tree
canopies shiver.  Nothing outside the player's little patch of ground is
touched.
"""

from __future__ import annotations

import math

import pygame

RADIUS = 620.0
_TIME = 0.0
_DIR = 0.25
_STRENGTH = 0.6
_PLAYER = (0.0, 0.0)
_BOOST = 0.0


def boost(seconds=15.0):
    global _BOOST
    _BOOST = max(float(_BOOST), float(seconds))


def tick(g, dt):
    global _TIME, _DIR, _STRENGTH, _PLAYER, _BOOST
    _TIME += float(dt)
    _BOOST = max(0.0, _BOOST - float(dt))
    # A slow shifting gust: not a constant conveyor belt.
    _DIR = 0.35 + 0.55 * math.sin(_TIME * 0.13) + 0.22 * math.sin(_TIME * 0.47)
    _STRENGTH = (0.42 + 0.24 * math.sin(_TIME * 0.61)
                 + 0.14 * math.sin(_TIME * 1.73)
                 + (0.45 if _BOOST > 0.0 else 0.0))
    p = getattr(g, "player", None)
    if p is not None:
        _PLAYER = (float(getattr(p, "x", 0.0)), float(getattr(p, "y", 0.0)))


def local_strength(x, y):
    px, py = _PLAYER
    d = math.hypot(float(x) - px, float(y) - py)
    if d >= RADIUS:
        return 0.0
    return max(0.0, 1.0 - d / RADIUS) ** 1.4


def sway(x, y, height=1.0):
    """(dx, dy) in screen/world pixels for a plant at x,y."""
    s = local_strength(x, y)
    if s <= 0.0:
        return 0.0, 0.0
    phase = _TIME * 2.7 + float(x) * 0.017 + float(y) * 0.011
    wave = math.sin(phase)
    side = math.cos(phase * 0.73)
    amount = 5.0 * s * float(height) * _STRENGTH
    return (math.cos(_DIR) * wave * amount
            + math.cos(_DIR + math.pi / 2.0) * side * amount * 0.35,
            math.sin(_DIR) * wave * amount * 0.35
            + math.sin(_DIR + math.pi / 2.0) * side * amount * 0.2)


def tree_angle(x, y):
    """Small canopy lean, in pygame degrees, around the trunk base."""
    s = local_strength(x, y)
    if s <= 0.0:
        return 0.0
    phase = _TIME * 2.2 + x * 0.012 + y * 0.009
    lean = (math.sin(phase) + 0.35 * math.sin(phase * 2.1)) * (1.5 * s * _STRENGTH)
    return math.degrees(_DIR) * 0.10 + lean


def draw_leaves(screen, x, y, cam_x, cam_y, radius=40.0):
    """Falling leaf flecks below a swaying canopy."""
    s = local_strength(x, y)
    if s <= 0.0:
        return
    sx, sy = x - cam_x, y - cam_y
    dx, dy = sway(x, y, 1.0)
    for i in range(7):
        phase = _TIME * 0.9 + i * 0.73 + x * 0.004 + y * 0.003
        fall = (phase * 0.55 + i * 0.17) % 1.0
        side = math.sin(phase * 1.7 + i) * radius * 0.48
        bx = (sx + side + dx * 1.8
              + math.cos(_DIR) * fall * (18.0 + i * 2.0))
        by = (sy - radius * 0.72 + fall * radius * 1.35
              + dy * 0.5 + math.sin(phase) * 4.0)
        col = (110, 164, 88) if i % 3 else (80, 136, 68)
        pygame.draw.ellipse(screen, col, (int(bx - 3), int(by - 2), 6, 4))
        pygame.draw.line(screen, (62, 106, 54),
                         (int(bx - 3), int(by)), (int(bx + 3), int(by + 1)), 1)


def draw(g, screen):
    """A few faint gust streaks near the player, never across the whole map."""
    p = getattr(g, "player", None)
    if p is None:
        return
    s = local_strength(p.x, p.y)
    if s <= 0.0:
        return
    sx, sy = p.x - g.cam_x, p.y - g.cam_y
    # Only a small surface around the player: a full-screen alpha allocation
    # every frame is exactly the kind of hidden cost that kills FPS.
    size = 300
    cx = cy = size // 2
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(9):
        phase = _TIME * 1.6 + i * 0.9
        r = 32 + i * 13
        bx = cx + math.cos(_DIR + phase * 0.2) * r
        by = cy + math.sin(_DIR + phase * 0.2) * r * 0.55 - 8
        ex = bx + math.cos(_DIR) * (18 + 8 * math.sin(phase))
        ey = by + math.sin(_DIR) * (5 + 3 * math.sin(phase))
        pygame.draw.line(layer, (210, 226, 244, int(35 * s)),
                         (bx, by), (ex, ey), 1)
    screen.blit(layer, (int(sx - cx), int(sy - cy)))
