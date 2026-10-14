"""Local grid pathfinding for characters.

A small navigation grid is built around the action (the camera region). Every
solid thing goes in: house walls, tree trunks, and village fences (with their
gates and any gaps chopped in them). Characters then A* around all of it.

Grids are rebuilt a few times a second; each character caches its own path and
re-plans only when its goal moves or its path goes stale.
"""

from __future__ import annotations

import heapq
import math

CELL = 48

_NEIGHBOURS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
               (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))


class NavGrid:
    def __init__(self, x0: float, y0: float, cols: int, rows: int,
                 blocked: bytearray, time: float = 0.0) -> None:
        self.x0 = x0
        self.y0 = y0
        self.cols = cols
        self.rows = rows
        self.blocked = blocked
        self.time = time
        self.generation = 0

    def blocked_at(self, cx: int, cy: int) -> bool:
        if cx < 0 or cy < 0 or cx >= self.cols or cy >= self.rows:
            return True
        return bool(self.blocked[cy * self.cols + cx])

    def to_cell(self, x: float, y: float):
        return (int((x - self.x0) // CELL), int((y - self.y0) // CELL))

    def centre(self, cx: int, cy: int):
        return (self.x0 + (cx + 0.5) * CELL, self.y0 + (cy + 0.5) * CELL)

    def free_near(self, cx: int, cy: int):
        """Nearest unblocked cell (spiral outwards), or None."""
        if not self.blocked_at(cx, cy):
            return cx, cy
        for radius in range(1, 8):
            for ox in range(-radius, radius + 1):
                for oy in range(-radius, radius + 1):
                    if max(abs(ox), abs(oy)) != radius:
                        continue
                    if not self.blocked_at(cx + ox, cy + oy):
                        return cx + ox, cy + oy
        return None


def _mark(blocked, cols, rows, x0, y0, rect) -> None:
    cx0 = max(0, int((rect.left - x0) // CELL))
    cx1 = min(cols - 1, int((rect.right - x0) // CELL))
    cy0 = max(0, int((rect.top - y0) // CELL))
    cy1 = min(rows - 1, int((rect.bottom - y0) // CELL))
    for cy in range(cy0, cy1 + 1):
        base = cy * cols
        for cx in range(cx0, cx1 + 1):
            blocked[base + cx] = 1


def build(x0: float, y0: float, cols: int, rows: int, rects, fences,
          time: float = 0.0) -> NavGrid:
    blocked = bytearray(cols * rows)
    for rect in rects:
        _mark(blocked, cols, rows, x0, y0, rect)
    for v in fences:
        radius = v.fence_radius
        cx0 = max(0, int((v.x - radius - CELL - x0) // CELL))
        cx1 = min(cols - 1, int((v.x + radius + CELL - x0) // CELL))
        cy0 = max(0, int((v.y - radius - CELL - y0) // CELL))
        cy1 = min(rows - 1, int((v.y + radius + CELL - y0) // CELL))
        for cy in range(cy0, cy1 + 1):
            wy = y0 + (cy + 0.5) * CELL
            base = cy * cols
            for cx in range(cx0, cx1 + 1):
                wx = x0 + (cx + 0.5) * CELL
                dx, dy = wx - v.x, wy - v.y
                if abs(math.hypot(dx, dy) - radius) < CELL * 0.65:
                    if not _passable(v, math.atan2(dy, dx)):
                        blocked[base + cx] = 1
    return NavGrid(x0, y0, cols, rows, blocked, time)


def _passable(v, angle: float) -> bool:
    """Wider than the real gate so a path fits through it comfortably."""
    from fence import _angdiff
    if _angdiff(angle, v.gate_angle) <= v.gate_half * 1.5:
        return True
    for ca, ch in v.fence_breaks:
        if _angdiff(angle, ca) <= ch * 1.3:
            return True
    return False


def astar(nav: NavGrid, start, goal, limit: int = 9000):
    start = nav.free_near(*start)
    goal = nav.free_near(*goal)
    if start is None or goal is None:
        return None
    cols, rows = nav.cols, nav.rows
    blocked = nav.blocked
    start_i = start[1] * cols + start[0]
    goal_i = goal[1] * cols + goal[0]
    if start_i == goal_i:
        return [start]
    inf = float("inf")
    cost = [inf] * (cols * rows)
    came = [-1] * (cols * rows)
    cost[start_i] = 0.0
    gx, gy = goal
    heap = [(0.0, 0.0, start_i)]
    visited = 0
    while heap:
        _f, _h, ci = heapq.heappop(heap)
        if ci == goal_i:
            break
        cg = cost[ci]
        visited += 1
        if visited > limit:
            return None
        cx = ci % cols
        cy = ci // cols
        for ox, oy, w in _NEIGHBOURS:
            nx, ny = cx + ox, cy + oy
            if nx < 0 or ny < 0 or nx >= cols or ny >= rows:
                continue
            ni = ny * cols + nx
            if blocked[ni]:
                continue
            if ox and oy and (blocked[cy * cols + nx] or blocked[ny * cols + cx]):
                continue                       # do not cut corners
            ng = cg + w
            if ng < cost[ni]:
                cost[ni] = ng
                came[ni] = ci
                h = math.hypot(gx - nx, gy - ny)
                heapq.heappush(heap, (ng + h, h, ni))
    if came[goal_i] == -1:
        return None
    path = []
    ci = goal_i
    while ci != -1:
        path.append((ci % cols, ci // cols))
        ci = came[ci]
    path.reverse()
    return path


def line_clear(nav: NavGrid, x: float, y: float, gx: float, gy: float) -> bool:
    """True if the straight segment does not cross any blocked cell."""
    dx, dy = gx - x, gy - y
    dist = math.hypot(dx, dy)
    steps = int(dist / (CELL * 0.5)) + 1
    for i in range(steps + 1):
        t = i / steps
        cx, cy = nav.to_cell(x + dx * t, y + dy * t)
        if cx < 0 or cy < 0 or cx >= nav.cols or cy >= nav.rows:
            continue                     # beyond the grid: assume it is clear
        if nav.blocked_at(cx, cy):
            return False
    return True


def steer(entity, nav: NavGrid, gx: float, gy: float):
    """Unit direction for ``entity`` to head toward (gx, gy), around obstacles."""
    now = nav.time
    if getattr(entity, "_nav_gen", None) != nav.generation:
        entity._nav_gen = nav.generation
        entity._nav_time = -99.0
    stale = (getattr(entity, "_nav_goal", None) is None
             or math.hypot(entity._nav_goal[0] - gx, entity._nav_goal[1] - gy) > 48.0
             or now - getattr(entity, "_nav_time", -99.0) > 0.7)
    if stale:
        if line_clear(nav, entity.x, entity.y, gx, gy):
            entity._nav_path = None          # straight shot: no search needed
        else:
            start = nav.to_cell(entity.x, entity.y)
            goal = nav.to_cell(gx, gy)
            entity._nav_path = astar(nav, start, goal)
        entity._nav_goal = (gx, gy)
        entity._nav_time = now

    path = getattr(entity, "_nav_path", None)
    if path:
        while len(path) > 1:
            wx, wy = nav.centre(*path[0])
            if math.hypot(entity.x - wx, entity.y - wy) < CELL * 0.75:
                path.pop(0)
            else:
                break
        # Smooth: aim for the furthest waypoint with a clear straight line.
        best = 0
        for i in range(1, min(len(path), 6)):
            wx, wy = nav.centre(*path[i])
            if line_clear(nav, entity.x, entity.y, wx, wy):
                best = i
            else:
                break
        if best:
            del path[:best]
        wx, wy = nav.centre(*path[0])
        ddx, ddy = wx - entity.x, wy - entity.y
        dist = math.hypot(ddx, ddy)
        if dist > 1e-6:
            return ddx / dist, ddy / dist

    ddx, ddy = gx - entity.x, gy - entity.y
    dist = math.hypot(ddx, ddy) or 1.0
    return ddx / dist, ddy / dist
