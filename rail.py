"""rail.py -- THE REPUBLIC'S RAILWAY.

ONE LINE PER GATE, TO THE NEAREST GATE OF THE NEAREST TOWN.

* A settlement has up to four gates. One or two of them are railheads -- never
  more than two per town, always at least one -- and each railhead runs to the
  GATE of whichever other settlement is nearest to it. So every line starts and
  ends at an opening in a fence, and a line never runs into a wall.
* Mutual pairs are one line, not two: A-to-B and B-to-A are the same track.
* THE CORRIDOR IS CLEAR GROUND. Trees and wild plants ask `blocked()` before
  they exist, so nothing grows on the permanent way, and nothing ever grows
  there later: the line is decided by the towns, and the towns are decided by
  the seed.
* Drawn as dark ballast, heavy sleepers and two bright steel rails, on the
  ground under everything that stands on it.
"""

from __future__ import annotations

import math

import pygame

# TWO IRON LINES, WITH PLANKS UNDER THEM. No ballast bed, no fat rails: the
# permanent way is 10 px between the rails, planks 16 px long lying at a right
# angle every 9 px and sticking out past both rails, and two 1-px iron lines
# with a dark shadow under each.
RAIL = (198, 202, 208)
RAIL_SHADOW = (120, 124, 130)
WOOD = (112, 84, 54)
WOOD_DARK = (64, 46, 28)
GAUGE = 7.0                # half the distance between the rails
PLANK_HALF = 13.0          # planks stick out this far each side
PLANK_EVERY = 12.0
CLEAR = 20.0               # nothing grows this close to the centre line

_SEGS: list = []           # [(x1, y1, x2, y2, bbox)]
_KEY = [None]
_DEG = [None]


LANE = 52.0          # how far outside the wall the track runs past a town


def _lane_rect(village):
    fr = getattr(village, "fence_rect", None)
    if fr is None:
        return None
    return fr.inflate(int(LANE * 2), int(LANE * 2))


def _gate_on_lane(village, side, gx, gy):
    """The gate's point pushed out to the fence lane."""
    lr = _lane_rect(village)
    if lr is None:
        return (gx, gy)
    if side == 0:
        return (float(gx), float(lr.top))
    if side == 2:
        return (float(gx), float(lr.bottom))
    if side == 1:
        return (float(lr.right), float(gy))
    return (float(lr.left), float(gy))


def _corridor(village, gate, toward):
    """OUT FROM THE GATE AND ALONG THE OUTSIDE OF THE FENCE, to a corner.

    The track hugs the town's wall on its OUTER side and leaves from the corner
    facing where it is going -- it never crosses the fence and never takes a
    short cut over the town.
    """
    lr = _lane_rect(village)
    if lr is None:
        return [(gate[1], gate[2])]
    corners = [(lr.left, lr.top), (lr.right, lr.top),
               (lr.right, lr.bottom), (lr.left, lr.bottom)]
    corner = min(corners, key=lambda c: (c[0] - toward[0]) ** 2
                 + (c[1] - toward[1]) ** 2)
    side, gx, gy = gate
    start = (float(gx), float(gy))
    lane = _gate_on_lane(village, side, gx, gy)
    # slide along the lane to the corner: one bend, always outside the wall
    if side in (0, 2):
        bend = (corner[0], lane[1])
    else:
        bend = (lane[0], corner[1])
    out = [start, lane]
    if bend != lane:
        out.append(bend)
    if corner != bend:
        out.append(corner)
    return out


def fence_gate(village, toward):
    """The (side, x, y) gate of that town facing `toward`."""
    try:
        import fence
        return fence.nearest_gate(village, toward[0], toward[1])
    except Exception:
        return (0, float(getattr(village, "x", 0.0)),
                float(getattr(village, "y", 0.0)))


def _gate_of(village, toward):
    """The gate on the side of town that faces `toward`."""
    try:
        import fence
        side, gx, gy = fence.nearest_gate(village, toward[0], toward[1])
        ox, oy = fence.OUTWARD[side]
        return (gx + ox * 12.0, gy + oy * 12.0)
    except Exception:
        return (float(getattr(village, "x", toward[0])),
                float(getattr(village, "y", toward[1])))


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    """Do two closed segments cross each other? (Touching ends do not count.)"""
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def build(towns) -> None:
    """ONE NETWORK. A ring round every town, and legs to each town's two nearest.

    * Every settlement gets a **ring of track on the OUTSIDE of its fence**, at
      the lane -- so all four of its gates are on the same railway, and the
      track visibly follows the walls instead of cutting across the town.
    * Each town is joined to its **two nearest settlements**, gate to gate: out
      of the gate, along the lane to the corner facing the neighbour, the long
      leg, then round the neighbour's lane to its gate.
    * The camp gets its spur, as before.
    """
    _SEGS.clear()
    _DEG[0] = None
    towns = [v for v in towns if not getattr(v, "is_hub", False)]
    if len(towns) < 2:
        return
    pos = [(float(v.x), float(v.y), v) for v in towns]

    def seg(a, b):
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        if ax > 150.0 or bx > 150.0:
            return        # no track into the sea (coast never exceeds x=150)
        if abs(ax - bx) < 0.6 and abs(ay - by) < 0.6:
            return
        _SEGS.append((ax, ay, bx, by,
                      pygame.Rect(int(min(ax, bx)) - 30, int(min(ay, by)) - 30,
                                  int(abs(ax - bx)) + 60,
                                  int(abs(ay - by)) + 60)))

    # -- the ring round each town, outside its fence ------------------------
    for x, y, v in pos:
        lr = _lane_rect(v)
        if lr is None:
            continue
        ring = [(lr.left, lr.top), (lr.right, lr.top),
                (lr.right, lr.bottom), (lr.left, lr.bottom)]
        for k in range(4):
            seg(ring[k], ring[(k + 1) % 4])

    # -- legs to the two nearest, gate to gate ------------------------------
    seen = set()
    deg = [0] * len(pos)
    for i, (x, y, v) in enumerate(pos):
        order = sorted((j for j in range(len(pos)) if j != i),
                       key=lambda j: (pos[j][0] - x) ** 2 + (pos[j][1] - y) ** 2)
        for j in order[:2]:
            a, b = (i, j) if i < j else (j, i)
            if (a, b) in seen:
                continue
            seen.add((a, b))
            tx, ty = pos[j][0], pos[j][1]
            ci = _corridor(v, fence_gate(v, (tx, ty)), (tx, ty))
            cj = _corridor(pos[j][2], fence_gate(pos[j][2], (x, y)), (x, y))
            pts = ci + list(reversed(cj))
            for k in range(len(pts) - 1):
                seg(pts[k], pts[k + 1])
            deg[i] += 1
            deg[j] += 1

    # -- the camp's spur ----------------------------------------------------
    try:
        import gulag as _gulag
        gx, gy = _gulag.middle()
        gate = _gulag.gate_point()
        near = min(range(len(pos)), key=lambda k: (pos[k][0] - gate[0]) ** 2
                   + (pos[k][1] - gate[1]) ** 2)
        ci = _corridor(pos[near][2], fence_gate(pos[near][2], gate), gate)
        for k in range(len(ci) - 1):
            seg(ci[k], ci[k + 1])
        seg(ci[-1], gate)
        seg(gate, (gx, gy))
        deg[near] += 1
    except Exception:
        pass

    _KEY[0] = (len(towns), round(pos[0][0], 1), round(pos[0][1], 1))
    _DEG[0] = deg


def ensure(towns) -> None:
    towns = [v for v in towns if not getattr(v, "is_hub", False)]
    if not towns:
        return
    key = (len(towns), round(towns[0].x, 1), round(towns[0].y, 1))
    if _KEY[0] != key:
        build(towns)


def dist(x: float, y: float) -> float:
    """How far this point is from the nearest RAIL, centre to centre."""
    best = 1e18
    for (ax, ay, bx, by, bb) in _SEGS:
        if not (bb.x - 300 <= x <= bb.x + bb.w + 300
                and bb.y - 300 <= y <= bb.y + bb.h + 300):
            continue
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L < 1e-9:
            d = math.hypot(x - ax, y - ay)
        else:
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
            d = math.hypot(x - (ax + dx * t), y - (ay + dy * t))
        if d < best:
            best = d
    return best if best < 1e17 else 999999.0      # no rail near at all


def blocked(x: float, y: float, pad: float = CLEAR) -> bool:
    """Is this point on the permanent way? Plants and trees ask this.

    THE BOUNDING BOX FIRST. Every tile near the line asks this question --
    wild plants, tree cells -- and walking the 47 segments each time was the
    stutter next to the camp, where the long spur runs. A point outside a
    segment's box cannot be near it, so most of the work is one rect test.
    """
    for x1, y1, x2, y2, _box in _SEGS:
        if not _box.inflate(pad * 2, pad * 2).collidepoint(x, y):
            continue
        dx, dy = x2 - x1, y2 - y1
        ln2 = dx * dx + dy * dy
        if ln2 <= 1e-9:
            if math.hypot(x - x1, y - y1) <= pad:
                return True
            continue
        t = ((x - x1) * dx + (y - y1) * dy) / ln2
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        if math.hypot(x - (x1 + dx * t), y - (y1 + dy * t)) <= pad:
            return True
    return False


def _track(screen, x1, y1, x2, y2, cx, cy) -> None:
    ax, ay = x1 - cx, y1 - cy
    bx, by = x2 - cx, y2 - cy
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy) or 1.0
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux                       # across the line
    # THE PLANKS FIRST, UNDER THE RAILS
    steps = int(ln // PLANK_EVERY)
    for i in range(steps + 1):
        t = i * PLANK_EVERY / ln
        mx, my = ax + dx * t, ay + dy * t
        ex, ey = px * PLANK_HALF, py * PLANK_HALF
        pygame.draw.line(screen, WOOD_DARK, (int(mx + ex), int(my + ey)),
                         (int(mx - ex), int(my - ey)), 6)
        pygame.draw.line(screen, WOOD, (int(mx + ex), int(my + ey)),
                         (int(mx - ex), int(my - ey)), 3)
    # ...THEN THE TWO IRON LINES
    for sgn in (-1, 1):
        ox, oy = px * GAUGE * sgn, py * GAUGE * sgn
        pygame.draw.line(screen, RAIL_SHADOW, (int(ax + ox), int(ay + oy + 2)),
                         (int(bx + ox), int(by + oy + 2)), 4)
        pygame.draw.line(screen, RAIL, (int(ax + ox), int(ay + oy)),
                         (int(bx + ox), int(by + oy)), 3)


def _clip(ax, ay, bx, by, view):
    """THE PART OF A LINE THAT IS ON SCREEN (Liang-Barsky).

    A spur to the camp is half a million pixels long, and laying its sleepers
    ran to tens of thousands of draw calls a frame whether they were on the
    screen or not -- which is the stutter next to the camp. Only the visible
    stretch is drawn now.
    """
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p_, q_ in ((-dx, ax - view.left), (dx, view.right - ax),
                   (-dy, ay - view.top), (dy, view.bottom - ay)):
        if p_ == 0:
            if q_ < 0:
                return None
            continue
        r = q_ / p_
        if p_ < 0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    return (ax + dx * t0, ay + dy * t0, ax + dx * t1, ay + dy * t1)


def draw(screen, cam_x: float, cam_y: float, vw: float, vh: float) -> None:
    view = pygame.Rect(int(cam_x) - 40, int(cam_y) - 40, int(vw) + 80, int(vh) + 80)
    for x1, y1, x2, y2, box in _SEGS:
        if not view.colliderect(box):
            continue
        cut = _clip(x1, y1, x2, y2, view)
        if cut is None:
            continue
        _track(screen, cut[0], cut[1], cut[2], cut[3], cam_x, cam_y)


def degrees() -> list:
    return list(_DEG[0] or ())


def crossings() -> int:
    n = 0
    for i in range(len(_SEGS)):
        for j in range(i + 1, len(_SEGS)):
            a, b = _SEGS[i], _SEGS[j]
            if _segments_cross((a[0], a[1]), (a[2], a[3]), (b[0], b[1]), (b[2], b[3])):
                n += 1
    return n


def tour() -> list:
    """A ROUTE OVER EVERY PIECE OF TRACK, following the rails.

    Depth-first over the segment graph: down one line, back up it where there is
    no way on, and out of the next -- so the engine visits the whole network
    without ever leaving the rails. Ends when every segment has been run.
    """
    if not _SEGS:
        return []
    def node(x, y):
        return (int(round(x / 24.0)), int(round(y / 24.0)))
    adj = {}
    for idx, (x1, y1, x2, y2, _b) in enumerate(_SEGS):
        a, b = node(x1, y1), node(x2, y2)
        adj.setdefault(a, []).append((idx, b, (x1, y1), (x2, y2)))
        adj.setdefault(b, []).append((idx, a, (x2, y2), (x1, y1)))
    used = set()
    path = []

    def walk(cur):
        """Down a line, and BACK UP IT when there is no way on.

        This is where the train left the rails before: the route jumped from
        the end of one branch straight to the start of the next, and the engine
        flew across country between them -- which is what it was hitting trees
        with. Backtracking appends the return leg, so every metre of the route
        is a metre of track.
        """
        for idx, nxt, p1, p2 in adj.get(cur, ()):
            if idx in used:
                continue
            used.add(idx)
            if not path or (abs(path[-1][0] - p1[0]) > 0.5
                            or abs(path[-1][1] - p1[1]) > 0.5):
                path.append(p1)
            path.append(p2)
            walk(nxt)
            path.append(p1)          # ...and back up the same rails

    start = node(*_SEGS[0][:2])
    walk(start)
    return path


def count() -> tuple:
    return len(_SEGS), sum(math.hypot(s[0] - s[2], s[1] - s[3]) for s in _SEGS)


# ---------------------------------------------------------------- shortest way
def _nearest_on_segs(px: float, py: float):
    """(segment index, closest point on it) -- the nearest piece of track."""
    best, bd, bpt = -1, 1e18, (px, py)
    for i, (ax, ay, bx, by, bb) in enumerate(_SEGS):
        if not (bb.x - 200 <= px <= bb.x + bb.w + 200
                and bb.y - 200 <= py <= bb.y + bb.h + 200):
            continue
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L < 1e-9:
            d = math.hypot(px - ax, py - ay)
            pt = (ax, ay)
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
            pt = (ax + dx * t, ay + dy * t)
            d = math.hypot(px - pt[0], py - pt[1])
        if d < bd:
            best, bd, bpt = i, d, pt
    return best, bpt


def _end(i: int, e: int):
    ax, ay, bx, by, _bb = _SEGS[i]
    return (ax, ay) if e == 0 else (bx, by)


def graph_path(x: float, y: float, tx: float, ty: float) -> list:
    """THE SHORTEST WAY ALONG THE TRACK from (x, y) to (tx, ty).

    Breadth-first over whole SEGMENTS. A segment meets another where their
    ends coincide; the walk from one to the next is along the sleepers, end to
    end. (An earlier version walked snapped NODE keys instead, and a key that
    no segment ended on had no edges at all -- so the engine was handed a
    straight line across the country and duly flew off the rails.)
    """
    if not _SEGS:
        return [(x, y), (tx, ty)]
    from collections import defaultdict, deque

    s0, p0 = _nearest_on_segs(x, y)
    s1, p1 = _nearest_on_segs(tx, ty)
    if s0 < 0 or s1 < 0:
        return [(x, y), (tx, ty)]
    if s0 == s1:
        return [p0, p1]

    at: dict = defaultdict(list)
    for i in range(len(_SEGS)):
        for e in (0, 1):
            ex, ey = _end(i, e)
            # the SAME 24 px node the tour walks: two lines that meet
            # are joined within a cell, not to the last decimal of a float
            at[(round(ex / 24.0), round(ey / 24.0))].append((i, e))
    conn: dict = defaultdict(list)
    for _k, lst in at.items():
        if len(lst) < 2:
            continue
        for a in lst:
            for b in lst:
                if a[0] != b[0]:
                    conn[a[0]].append((b[0], a[1], b[1]))

    # IF THE POINT STANDS ON A FRAGMENT, USE THE TRACK THAT IS CONNECTED.
    def _comp_of(start_i):
        seen_ = {start_i}
        dq_ = deque([start_i])
        while dq_:
            i_ = dq_.popleft()
            for (j_, _ei, _ej) in conn.get(i_, ()):
                if j_ not in seen_:
                    seen_.add(j_)
                    dq_.append(j_)
        return seen_

    reach = _comp_of(s1)
    if s0 not in reach:
        best_i, best_d, best_pt = -1, 1e18, None
        for i_ in reach:
            _ax, _ay, _bx, _by, _bb = _SEGS[i_]
            _dx, _dy = _bx - _ax, _by - _ay
            _L = _dx * _dx + _dy * _dy
            if _L < 1e-9:
                _pt = (_ax, _ay)
            else:
                _t = max(0.0, min(1.0, ((x - _ax) * _dx + (y - _ay) * _dy) / _L))
                _pt = (_ax + _dx * _t, _ay + _dy * _t)
            _d = math.hypot(x - _pt[0], y - _pt[1])
            if _d < best_d:
                best_i, best_d, best_pt = i_, _d, _pt
        if best_i >= 0:
            s0, p0 = best_i, best_pt

    prev = {s0: None}
    dq = deque([s0])
    while dq:
        i = dq.popleft()
        if i == s1:
            break
        for (j, ei, ej) in conn.get(i, ()):
            if j in prev:
                continue
            prev[j] = (i, ei, ej)
            dq.append(j)
    if s1 not in prev:
        return [(x, y), (tx, ty)]

    # THE WALK, AS DIRECTED SEGMENTS: enter j at one end, leave by the other.
    order = []
    j = s1
    _guard = 0
    while prev.get(j) is not None and _guard < 100000:
        order.append(j)
        j = prev[j][0]
        _guard += 1
    order.append(s0)
    order.reverse()

    pts = [p0]
    for idx, seg in enumerate(order):
        if idx > 0:
            entry = prev[seg][2]                 # entered `seg` at this end
            e_pt = _end(seg, entry)
            if math.hypot(pts[-1][0] - e_pt[0], pts[-1][1] - e_pt[1]) > 0.5:
                pts.append(e_pt)
        if idx < len(order) - 1:
            exit_end = prev[order[idx + 1]][1]   # ...and leave by this one
            pts.append(_end(seg, exit_end))
        else:
            pts.append(p1)
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 0.5:
            out.append(p)
    return out


def path_length(pts) -> float:
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return total
