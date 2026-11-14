"""Local obstacle avoidance -- no grid, no search.

The character always wants to walk in a straight line at its goal. Each frame it
probes a short distance ahead:

* if a house or tree is in the way, it heads for the nearest clear corner of it
  (the "way out") and then resumes the straight line;
* if a village fence is in the way, it heads for the gate (the only way out of
  the ring) and then resumes the straight line.

It is O(obstacles in view) per character -- no pathfinding tables, no A*.
"""

from __future__ import annotations

import math

import fence

LOOK = 120.0


def _ray_rect(px, py, ux, uy, length, rect, rad):
    """Distance along the ray to a rect (grown by ``rad``), or None."""
    tmin, tmax = 0.0, length
    for p, d, lo, hi in ((px, ux, rect.left - rad, rect.right + rad),
                         (py, uy, rect.top - rad, rect.bottom + rad)):
        if abs(d) < 1e-9:
            if p < lo or p > hi:
                return None
        else:
            t1, t2 = (lo - p) / d, (hi - p) / d
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > tmin:
                tmin = t1
            if t2 < tmax:
                tmax = t2
            if tmin > tmax:
                return None
    return tmin


def _seg_circle(px, py, gx, gy, cx, cy, radius):
    """First intersection of a segment with a circle, or None."""
    dx, dy = gx - px, gy - py
    fx, fy = px - cx, py - cy
    a = dx * dx + dy * dy
    if a < 1e-9:
        return None
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None
    sq = math.sqrt(disc)
    for t in ((-b - sq) / (2.0 * a), (-b + sq) / (2.0 * a)):
        if 0.0 <= t <= 1.0:
            return px + dx * t, py + dy * t
    return None


def _needs_gate(px, py, gx, gy, v):
    """True if going from here to the goal means passing the ring, off-gate."""
    R = v.fence_radius
    d = math.hypot(px - v.x, py - v.y)
    dg = math.hypot(gx - v.x, gy - v.y)
    if (d < R) == (dg < R):
        return False
    hit = _seg_circle(px, py, gx, gy, v.x, v.y, R)
    if hit is None:
        return False
    return not fence.passable(v, math.atan2(hit[1] - v.y, hit[0] - v.x))


def _gate_steer(entity, px, py, v):
    """Circle to the gate, then walk straight through it to the far side."""
    cx, cy = v.x, v.y
    R = v.fence_radius
    d = math.hypot(px - cx, py - cy) or 1.0
    inside = getattr(entity, "_fence_inside", d < R)
    gx_pt = cx + math.cos(v.gate_angle) * (R + 95.0 if inside else R - 95.0)
    gy_pt = cy + math.sin(v.gate_angle) * (R + 95.0 if inside else R - 95.0)
    ang = math.atan2(py - cy, px - cx)
    delta = ((v.gate_angle - ang + math.pi) % (2.0 * math.pi)) - math.pi
    if abs(delta) <= v.gate_half * 1.6:        # lined up: straight through the gate
        ddx, ddy = gx_pt - px, gy_pt - py
        dd = math.hypot(ddx, ddy) or 1.0
        return ddx / dd, ddy / dd
    sign = 1.0 if delta > 0.0 else -1.0
    radial = ((px - cx) / d, (py - cy) / d)
    tangent = (-radial[1] * sign, radial[0] * sign)
    want = R - 70.0 if inside else R + 70.0
    corr = max(-1.0, min(1.0, (want - d) / 60.0))
    ux = tangent[0] + radial[0] * corr
    uy = tangent[1] + radial[1] * corr
    n = math.hypot(ux, uy) or 1.0
    return ux / n, uy / n


def _around_corner(entity, px, py, ux, uy, gx, gy, rect, rad):
    """Head for the cheapest clear corner of a blocking rect.

    The cheapest corner is picked every frame (the old "stick to the corner"
    hysteresis locked a man into circling a rect for ever, so it is gone). If
    the man is already standing ON that corner, the goal is still behind the
    rect -- so he heads for the adjacent corner nearer the goal, walking
    AROUND the rect instead of orbiting the corner point.
    """
    corners = ((rect.left - rad, rect.top - rad),
               (rect.right + rad, rect.top - rad),
               (rect.left - rad, rect.bottom + rad),
               (rect.right + rad, rect.bottom + rad))
    best_i = 0
    best_cost = 1e18
    for i, (cx, cy) in enumerate(corners):
        cdx, cdy = cx - px, cy - py
        cdist = math.hypot(cdx, cdy)
        if cdist < 1e-3:
            continue
        a1 = math.acos(max(-1.0, min(1.0, (ux * cdx + uy * cdy) / cdist)))
        gdx, gdy = gx - cx, gy - cy
        gdist = math.hypot(gdx, gdy) or 1.0
        a2 = math.acos(max(-1.0, min(1.0, (cdx * gdx + cdy * gdy) / (cdist * gdist))))
        cost = a1 + a2
        # NO HYSTERESIS. "Keep going round the same way" was meant to stop a
        # man dithering between two corners; what it actually did was lock him
        # into whichever side he first took, so a man whose true best corner
        # was the other one circled for ever. The cheapest corner, every time.
        if cost < best_cost:
            best_cost = cost
            best_i = i
    cx, cy = corners[best_i]
    entity._avoid_corner = (cx, cy)
    entity._avoid_side = 1
    entity._avoid_n = 16
    # SLIDE PAST, NOT ORBIT. A goal just the other side of the rect (a man to
    # feed standing by the bench just placed between you and him) left the
    # straight line still blocked AFTER the corner was reached -- and the man
    # reversed toward the same corner and back, ten times a second, going
    # nowhere. Standing on the corner now heads for the adjacent corner that
    # lies nearer the goal, so he walks AROUND the rect instead of into its
    # corner point and back out.
    if math.hypot(px - cx, py - cy) < rad + 10.0:
        adj = ((1, 2), (0, 3), (0, 3), (1, 2))[best_i]
        nx, ny = corners[adj[0]]
        if (corners[adj[1]][0] - gx) ** 2 + (corners[adj[1]][1] - gy) ** 2 \
                < (nx - gx) ** 2 + (ny - gy) ** 2:
            nx, ny = corners[adj[1]]
        cx, cy = nx, ny
    ox, oy = cx - rect.centerx, cy - rect.centery
    on = math.hypot(ox, oy) or 1.0
    tx, ty = cx + ox / on * 12.0, cy + oy / on * 12.0
    dx, dy = tx - px, ty - py
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def _same_side_dir(px, py, gx, gy, v):
    """When both ends are on the same side, walk around the ring, not through it."""
    R = v.fence_radius
    d = math.hypot(px - v.x, py - v.y) or 1.0
    dg = math.hypot(gx - v.x, gy - v.y)
    if (d < R) != (dg < R):
        return None
    hit = _seg_circle(px, py, gx, gy, v.x, v.y, R)
    if hit is None:
        return None
    ang = math.atan2(py - v.y, px - v.x)
    goal_ang = math.atan2(gy - v.y, gx - v.x)
    delta = ((goal_ang - ang + math.pi) % (2.0 * math.pi)) - math.pi
    sign = 1.0 if delta > 0.0 else -1.0
    radial = ((px - v.x) / d, (py - v.y) / d)
    tangent = (-radial[1] * sign, radial[0] * sign)
    want = R + 70.0 if d > R else R - 70.0
    corr = max(-1.0, min(1.0, (want - d) / 60.0))
    ux = tangent[0] + radial[0] * corr
    uy = tangent[1] + radial[1] * corr
    n = math.hypot(ux, uy) or 1.0
    return ux / n, uy / n


def steer(entity, gx, gy, rects=(), villages=(), look: float = LOOK):
    """Unit direction for ``entity`` toward (gx, gy), dodging what is in front."""
    px, py = entity.x, entity.y
    vx, vy = gx - px, gy - py
    dist = math.hypot(vx, vy)
    if dist < 1e-6:
        return 0.0, 0.0
    ux, uy = vx / dist, vy / dist
    rad = getattr(entity, "radius", 12)
    if hasattr(rects, "near"):             # spatial index: only what is near the path
        rects = rects.near(px, py, look + rad + 8)

    best_dir = None
    best_d = 1e18
    for w in villages:                     # fences first: use the gate
        if not hasattr(w, "fence_rect"):
            continue
        cd = fence.cross_dir(w, px, py, gx, gy, pad=90.0)
        if cd is None:
            continue
        # A marching man aims at HIS rally point outside the gate, not at the
        # middle of the opening. Same gate, spread stream, no pile-up.
        rally = getattr(entity, "rally_off", None)
        if rally is not None:
            side, gxw, gyw = fence.nearest_gate(w, px, py)
            ox, oy = fence.OUTWARD[side]
            lat, dep = rally
            rx = gxw + ox * dep - oy * lat
            ry = gyw + oy * dep + ox * lat
            rdx, rdy = rx - px, ry - py
            rn = math.hypot(rdx, rdy) or 1.0
            cd = (rdx / rn, rdy / rn)
        rect = w.fence_rect
        cx = min(max(px, rect.left), rect.right)
        cy = min(max(py, rect.top), rect.bottom)
        d = math.hypot(px - cx, py - cy)
        if d < best_d:
            best_d = d
            best_dir = cd
    if best_dir is not None:
        # THE GATE DIRECTION IS NOT EXEMPT FROM WALLS. `cross_dir` aims along
        # the inside of the fence at the opening -- and the houses, benches and
        # boards of a town are exactly where that path runs. Returning it
        # untouched walked men into a house, and the next frame aimed them back
        # at the fence: a tight orbit on the spot, measured as three samples
        # 3,951 / 3,956 / 3,954 px from the goal over eighty seconds.
        gx2, gy2 = best_dir
        gl = 90.0 + rad
        if hasattr(rects, "near"):
            near_ = rects.near(px, py, gl)
        else:
            near_ = rects
        best_rect = None
        best_t = gl
        for rect in near_:
            if (rect.left > px + gl or rect.right < px - gl
                    or rect.top > py + gl or rect.bottom < py - gl):
                continue
            t = _ray_rect(px, py, gx2, gy2, gl, rect, rad)
            if t is not None and t < best_t:
                best_t = t
                best_rect = rect
        if best_rect is not None:
            return _around_corner(entity, px, py, gx2, gy2, gx2, gy2,
                                  best_rect, rad)
        return best_dir
    best_rect = None
    best_t = look
    for rect in rects:
        if (rect.left > px + look + rad or rect.right < px - look - rad
                or rect.top > py + look + rad or rect.bottom < py - look - rad):
            continue                        # broadphase
        t = _ray_rect(px, py, ux, uy, look, rect, rad)
        if t is not None and t < best_t:
            best_t = t
            best_rect = rect
    if best_rect is not None:
        return _around_corner(entity, px, py, ux, uy, gx, gy, best_rect, rad)
    return ux, uy
