"""Rectangular village fences.

A village fence is a hollow rectangle of wall with two gates, on opposite
walls -- one to come in by and one to leave by, which is what makes a rout
possible. It is made of solid wall *rects* (so normal collision handles it)
with a gap at each gate and any place an axe has chopped a hole.
"""

from __future__ import annotations

import math

import pygame

T = 16                      # wall thickness
GATE_W = 170.0              # gate opening width
BREAK_PX = 90.0             # how much a single axe chop opens up
MARGIN = 110.0              # fence sits this far outside the village radius

# side ids: 0 top, 1 right, 2 bottom, 3 left
_NEIGHBOURS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def install(village, rng) -> None:
    half = village.radius + MARGIN
    village.fence_rect = pygame.Rect(int(village.x - half), int(village.y - half),
                                     int(2 * half), int(2 * half))
    village.gate_side = rng.randrange(4)
    village.gate_side2 = (village.gate_side + 2) % 4      # the opposite wall
    for side, name in ((village.gate_side, "gate_off"),
                       (village.gate_side2, "gate_off2")):
        span = (village.fence_rect.w if side in (0, 2)
                else village.fence_rect.h)
        setattr(village, name, rng.uniform(-span * 0.34, span * 0.34))
    village.fence_gaps: list[tuple[int, float, float]] = []   # (side, centre, half)
    gx, gy = gate_world(village)
    village.gate_t = perimeter_param(village.fence_rect, gx, gy)
    rebuild(village)


OUTWARD = {0: (0.0, -1.0), 1: (1.0, 0.0), 2: (0.0, 1.0), 3: (-1.0, 0.0)}


def gate_list(village):
    """Both gates, as (side, x, y). Two opposite walls, always.

    It read `village.gate_side` and `village.gate_off` straight off the object.
    A settlement restored from the world cache never runs __init__, so those
    can be missing -- and the AttributeError was swallowed by every caller,
    which is why a town near the player reported a patrol of ZERO men and no
    guard ever appeared at its gate.
    """
    r = getattr(village, "fence_rect", None)
    if r is None:
        return []
    out = []
    for side, off in ((getattr(village, "gate_side", 0),
                       getattr(village, "gate_off", 0.0)),
                      (getattr(village, "gate_side2",
                              (getattr(village, "gate_side", 0) + 2) % 4),
                       getattr(village, "gate_off2", 0.0))):
        if side == 0:
            out.append((side, village.x + off, r.top))
        elif side == 2:
            out.append((side, village.x + off, r.bottom))
        elif side == 1:
            out.append((side, r.right, village.y + off))
        else:
            out.append((side, r.left, village.y + off))
    return out


def nearest_gate(village, x, y):
    return min(gate_list(village),
               key=lambda g: (g[1] - x) ** 2 + (g[2] - y) ** 2)


def gate_world(village):
    gate = gate_list(village)[0]
    return gate[1], gate[2]


def gate_outward(village):
    return OUTWARD[village.gate_side]


def _gaps_on(village, side):
    gaps = []
    for gside, gx, gy in gate_list(village):
        if gside == side:
            c = gx if side in (0, 2) else gy
            gaps.append((c - GATE_W / 2, c + GATE_W / 2))
    for s, c, hw in village.fence_gaps:
        if s == side:
            gaps.append((c - hw, c + hw))
    return sorted(gaps)


def _side_rects(village, side):
    r = village.fence_rect
    a, b = (r.left, r.right) if side in (0, 2) else (r.top, r.bottom)
    out, cur = [], a
    for g0, g1 in _gaps_on(village, side):
        g0, g1 = max(a, g0), min(b, g1)
        if g0 > cur:
            out.append((cur, g0))
        cur = max(cur, g1)
    if cur < b:
        out.append((cur, b))
    rects = []
    for s0, s1 in out:
        if s1 - s0 < 3:
            continue
        if side == 0:
            rects.append(pygame.Rect(int(s0), r.top, int(s1 - s0), T))
        elif side == 2:
            rects.append(pygame.Rect(int(s0), r.bottom - T, int(s1 - s0), T))
        elif side == 1:
            rects.append(pygame.Rect(r.right - T, int(s0), T, int(s1 - s0)))
        else:
            rects.append(pygame.Rect(r.left, int(s0), T, int(s1 - s0)))
    return rects


def rebuild(village) -> None:
    walls = []
    for side in range(4):
        walls.extend(_side_rects(village, side))
    village.fence_walls = walls


def perimeter_param(r, x, y) -> float:
    cx = min(max(x, r.left), r.right)
    cy = min(max(y, r.top), r.bottom)
    dl, dr = cx - r.left, r.right - cx
    dt, db = cy - r.top, r.bottom - cy
    m = min(dl, dr, dt, db)
    L = 2.0 * (r.w + r.h)
    if m == dt:
        return (cx - r.left) / L
    if m == dr:
        return (r.w + (cy - r.top)) / L
    if m == db:
        return (r.w + r.h + (r.right - cx)) / L
    return (2.0 * r.w + r.h + (r.bottom - cy)) / L


def perimeter_point(r, t):
    L = 2.0 * (r.w + r.h)
    d = (t % 1.0) * L
    if d < r.w:
        return r.left + d, r.top, 0.0, -1.0
    d -= r.w
    if d < r.h:
        return r.right, r.top + d, 1.0, 0.0
    d -= r.h
    if d < r.w:
        return r.right - d, r.bottom, 0.0, 1.0
    d -= r.w
    return r.left, r.bottom - d, -1.0, 0.0


def _norm(dx, dy):
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def cross_dir(village, x, y, tx, ty):
    """Direction to take when a fence must be crossed, else None."""
    r = village.fence_rect
    inside = r.collidepoint(x, y)
    target_inside = r.collidepoint(tx, ty)
    if inside == target_inside:
        return None
    gside, gx, gy = nearest_gate(village, x, y)
    ox, oy = OUTWARD[gside]
    aligned = (abs(x - gx) <= GATE_W * 0.65 if gside in (0, 2)
               else abs(y - gy) <= GATE_W * 0.65)
    if aligned:
        if inside:
            return _norm(gx + ox * 100.0 - x, gy + oy * 100.0 - y)
        return _norm(gx - ox * 100.0 - x, gy - oy * 100.0 - y)
    t_ent = perimeter_param(r, x, y)
    delta = ((perimeter_param(r, gx, gy) - t_ent + 0.5) % 1.0) - 0.5
    sign = 1.0 if delta > 0.0 else -1.0
    px, py, nx, ny = perimeter_point(r, (t_ent + sign * 0.03) % 1.0)
    m = 58.0
    if inside:
        px, py = px - nx * m, py - ny * m
    else:
        px, py = px + nx * m, py + ny * m
    return _norm(px - x, py - y)


def chop(village, x, y, reach=70.0) -> bool:
    """Open a gap in the nearest wall, if one is within reach."""
    r = village.fence_rect
    near = min(abs(x - r.left), abs(x - r.right),
               abs(y - r.top), abs(y - r.bottom))
    if near > reach:
        return False
    dl, dr = abs(x - r.left), abs(x - r.right)
    dt, db = abs(y - r.top), abs(y - r.bottom)
    side = min((dt, 0), (dr, 1), (db, 2), (dl, 3))[1]
    centre = x if side in (0, 2) else y
    village.fence_gaps.append((side, centre, BREAK_PX / 2.0))
    rebuild(village)
    return True


def draw(screen: pygame.Surface, cam_x: float, cam_y: float, village,
         view=None) -> None:
    for rect in getattr(village, "fence_walls", ()):
        if view is not None and not view.colliderect(rect):
            continue
        draw_segment(screen, cam_x, cam_y, rect)
    # gate posts, lighter, so both openings are obvious
    for gside, gx, gy in gate_list(village):
        for along in (-GATE_W / 2.0, GATE_W / 2.0):
            if gside in (0, 2):
                px, py = gx + along, gy
            else:
                px, py = gx, gy + along
            sx, sy = px - cam_x, py - cam_y
            pygame.draw.rect(screen, (58, 40, 26), (sx - 5, sy - 12, 10, 24))
            pygame.draw.rect(screen, (206, 160, 96), (sx - 3, sy - 10, 6, 20))


def draw_segment(screen, cam_x, cam_y, rect) -> None:
    r = pygame.Rect(rect.x - cam_x, rect.y - cam_y, rect.w, rect.h)
    pygame.draw.rect(screen, (150, 108, 64), r)
    pygame.draw.rect(screen, (92, 62, 36), r, 1)
    if r.w >= r.h:
        for px in range(r.left, r.right, 26):
            pygame.draw.line(screen, (92, 62, 36), (px, r.top), (px, r.bottom), 1)
    else:
        for py in range(r.top, r.bottom, 26):
            pygame.draw.line(screen, (92, 62, 36), (r.left, py), (r.right, py), 1)


def draw_gate(screen, cam_x, cam_y, rect) -> None:
    """A built gate: two light posts and a lintel, unlike a plain fence run."""
    r = pygame.Rect(rect.x - cam_x, rect.y - cam_y, rect.w, rect.h)
    pygame.draw.rect(screen, (120, 86, 52), r)
    pygame.draw.rect(screen, (92, 62, 36), r, 1)
    if r.w >= r.h:
        for px in (r.left + 3, r.right - 9):
            pygame.draw.rect(screen, (58, 40, 26), (px, r.top - 6, 6, r.h + 12))
            pygame.draw.rect(screen, (206, 160, 96), (px + 1, r.top - 4, 4, r.h + 8))
    else:
        for py in (r.top + 3, r.bottom - 9):
            pygame.draw.rect(screen, (58, 40, 26), (r.left - 6, py, r.w + 12, 6))
            pygame.draw.rect(screen, (206, 160, 96), (r.left - 4, py + 1, r.w + 8, 4))


def homesteads(fences, houses):
    """Interiors of closed rectangles of player-built fence that enclose one of
    the player's own houses -- his private land. Returns a list of Rect."""
    if not fences or not houses:
        return []
    remaining = list(fences)
    comps = []
    while remaining:
        comp = [remaining.pop()]
        grew = True
        while grew:                              # gather fences that touch
            grew = False
            for rect in list(remaining):
                if any(c.inflate(6, 6).colliderect(rect) for c in comp):
                    comp.append(rect)
                    remaining.remove(rect)
                    grew = True
        comps.append(comp)
    out = []
    for comp in comps:
        xs = [r.centerx for r in comp]
        ys = [r.centery for r in comp]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if x1 - x0 < 60 or y1 - y0 < 60:
            continue                             # too small to be a plot
        pts = []
        step = 6
        for x in range(x0, x1 + 1, step):        # walk the centre-line rectangle
            pts.append((x, y0))
            pts.append((x, y1))
        for y in range(y0, y1 + 1, step):
            pts.append((x0, y))
            pts.append((x1, y))
        covered = sum(1 for p in pts
                      if any(r.inflate(4, 4).collidepoint(p) for r in comp))
        if covered < len(pts) * 0.9:
            continue                             # not a full rectangle (a gap)
        if not any(x0 < h.x < x1 and y0 < h.y < y1 for h in houses):
            continue                             # no house inside
        out.append(pygame.Rect(x0, y0, x1 - x0, y1 - y0))
    return out
