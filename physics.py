"""Small 2D collision helpers (circle vs. rectangle)."""

from __future__ import annotations

import math

import pygame


def resolve_circle_rect(x: float, y: float, r: float, rect: pygame.Rect):
    """Push a circle out of a rectangle if it overlaps. Returns (x, y)."""
    cx = min(max(x, rect.left), rect.right)
    cy = min(max(y, rect.top), rect.bottom)
    dx, dy = x - cx, y - cy
    d2 = dx * dx + dy * dy
    if d2 > r * r:
        return x, y
    if d2 > 1e-9:
        d = math.sqrt(d2)
        push = r - d
        return x + dx / d * push, y + dy / d * push
    # centre is inside: push out through the nearest side
    left, right = x - rect.left, rect.right - x
    top, bottom = y - rect.top, rect.bottom - y
    smallest = min(left, right, top, bottom)
    if smallest == left:
        return rect.left - r, y
    if smallest == right:
        return rect.right + r, y
    if smallest == top:
        return x, rect.top - r
    return x, rect.bottom + r


def resolve_circle_rects(x: float, y: float, r: float,
                         rects) -> tuple[float, float]:
    for rect in rects:
        if (rect.right < x - r or rect.left > x + r
                or rect.bottom < y - r or rect.top > y + r):
            continue                        # broadphase: nowhere near
        x, y = resolve_circle_rect(x, y, r, rect)
    return x, y


def resolve_circle_pair(a, b, spacing: float = 0.0) -> None:
    """Push two circles apart by half the overlap each (plus personal space)."""
    dx, dy = b.x - a.x, b.y - a.y
    d2 = dx * dx + dy * dy
    rr = a.radius + b.radius + spacing
    if d2 >= rr * rr:
        return
    if d2 < 1e-9:
        a.x -= 0.5
        b.x += 0.5
        return
    d = math.sqrt(d2)
    overlap = (rr - d) * 0.5
    ux, uy = dx / d, dy / d
    a.x -= ux * overlap
    a.y -= uy * overlap
    b.x += ux * overlap
    b.y += uy * overlap


def resolve_circle_pairs(entities, spacing: float = 0.0) -> None:
    """Separate every pair of characters so nobody stands inside anybody."""
    n = len(entities)
    if n < 2:
        return
    cell = max(48.0, spacing + 4.0 * max(getattr(e, "radius", 12) for e in entities))
    buckets: dict = {}
    for e in entities:
        buckets.setdefault((int(e.x // cell), int(e.y // cell)), []).append(e)
    for e in entities:
        cx, cy = int(e.x // cell), int(e.y // cell)
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for other in buckets.get((cx + ox, cy + oy), ()):
                    if id(other) <= id(e):
                        continue
                    resolve_circle_pair(e, other, spacing)


class TeamGrid:
    """Buckets moving characters so one fighter only looks at what is near it.

    Without this, every soldier compared itself against every other soldier
    every frame -- four hundred men meant a hundred and sixty thousand
    distance checks a tick, and the battle crawled. The nearest target is
    always a local one, so looking only nearby gives the same answer for a
    fraction of the work.
    """

    __slots__ = ("cell", "buckets", "_cache")

    def __init__(self, cell: float = 200.0) -> None:
        self.cell = cell
        self.buckets: dict = {}
        self._cache: dict = {}

    def build(self, entities) -> None:
        self.buckets.clear()
        self._cache.clear()
        cell = self.cell
        for e in entities:
            self.buckets.setdefault((int(e.x // cell), int(e.y // cell)),
                                    []).append(e)

    def near(self, x: float, y: float, r: float) -> list:
        """Everyone within ``r``, assembled from the cells that box touches.

        Men standing in the same cell are looking at the same neighbourhood,
        so the list is built once per cell and handed to all of them. Doing it
        per man meant four hundred list builds and a hundred and sixty thousand
        appends a frame just to say who was nearby.
        """
        cell = self.cell
        x0, x1 = int((x - r) // cell), int((x + r) // cell)
        y0, y1 = int((y - r) // cell), int((y + r) // cell)
        key = (x0, y0, x1, y1)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        if x0 == x1 and y0 == y1:
            out = self.buckets.get((x0, y0), [])
        else:
            out = []
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    bucket = self.buckets.get((cx, cy))
                    if bucket:
                        out.extend(bucket)
        self._cache[key] = out
        return out


class StaticGrid:
    """Buckets static rectangles so a character only sees the ones nearby."""

    __slots__ = ("cell", "buckets")

    def __init__(self, cell: float = 72.0) -> None:
        self.cell = cell
        self.buckets: dict = {}

    def add(self, rect) -> None:
        cell = self.cell
        x0, x1 = int(rect.left // cell), int(rect.right // cell)
        y0, y1 = int(rect.top // cell), int(rect.bottom // cell)
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                self.buckets.setdefault((cx, cy), []).append(rect)

    def near(self, x: float, y: float, r: float):
        cell = self.cell
        x0, x1 = int((x - r) // cell), int((x + r) // cell)
        y0, y1 = int((y - r) // cell), int((y + r) // cell)
        if x0 == x1 and y0 == y1:
            return self.buckets.get((x0, y0), ())
        seen = set()
        out = []
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                for rect in self.buckets.get((cx, cy), ()):
                    key = id(rect)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(rect)
        return out


def resolve_circle_out_of(mover, obstacles) -> None:
    """Push one character fully out of each obstacle character (mover moves)."""
    for other in obstacles:
        dx, dy = mover.x - other.x, mover.y - other.y
        d2 = dx * dx + dy * dy
        rr = mover.radius + other.radius
        if d2 >= rr * rr:
            continue
        if d2 < 1e-9:
            mover.x += rr
            continue
        d = math.sqrt(d2)
        push = rr - d
        mover.x += dx / d * push
        mover.y += dy / d * push


def segment_rect_hit(x0: float, y0: float, x1: float, y1: float,
                     rect: pygame.Rect) -> bool:
    """True if the segment (x0,y0)-(x1,y1) crosses the rectangle."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rect.left), (dx, rect.right - x0),
                 (-dy, y0 - rect.top), (dy, rect.bottom - y0)):
        if p == 0.0:
            if q < 0.0:
                return False
        else:
            t = q / p
            if p < 0.0:
                if t > t1:
                    return False
                if t > t0:
                    t0 = t
            else:
                if t < t0:
                    return False
                if t < t1:
                    t1 = t
    return True


def avoid_direction(x: float, y: float, dx: float, dy: float, r: float,
                    rects, lookahead: float = 56.0):
    """Steer around nearby rectangles: the smallest turn that stays clear.

    Good enough to walk around a tree or a house corner without a real
    pathfinder. Returns a unit direction (dx, dy unchanged if nothing is hit).
    """
    if not rects:
        return dx, dy
    if hasattr(rects, "near"):
        rects = rects.near(x, y, lookahead + r + 8)
    base = math.atan2(dy, dx)
    for delta in (0.0, 0.45, -0.45, 0.9, -0.9, 1.35, -1.35, 1.9, -1.9, 2.5, -2.5):
        a = base + delta
        ux, uy = math.cos(a), math.sin(a)
        ex, ey = x + ux * lookahead, y + uy * lookahead
        clear = True
        for rect in rects:
            if (rect.right + r < x - lookahead or rect.left - r > x + lookahead
                    or rect.bottom + r < y - lookahead
                    or rect.top - r > y + lookahead):
                continue                    # broadphase
            if segment_rect_hit(x, y, ex, ey, rect.inflate(r * 2, r * 2)):
                clear = False
                break
        if clear:
            return ux, uy
    return dx, dy
