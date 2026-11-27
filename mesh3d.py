"""mesh3d.py -- a tiny low-poly software renderer for the first-person view.

It is deliberately small: enough geometry to make trees, houses, workbenches
and held items read as objects in space, not painted cards.  It does not own
game state and it does not decide what is solid.

The near ground is still a textured image from view3d; this module adds the
world above it, depth-sorted far-to-near, with simple sun shading and fog.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pygame

# Keep in step with view3d.  The internal frame is small; scaling up is the
# point.
IW, IH = 280, 158
FOCAL = IW / (2.0 * math.tan(math.radians(78.0) * 0.5))
NEAR = 18.0
DRAW_DIST = 5200.0
EYE_Z = 56.0

_LIGHT = (-0.38, -0.42, 0.82)
_LLEN = math.sqrt(sum(v * v for v in _LIGHT))
_LIGHT = tuple(v / _LLEN for v in _LIGHT)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    n = math.sqrt(_dot(v, v))
    if n < 1e-8:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _rot_z(p, cx, cy, a):
    c, s = math.cos(a), math.sin(a)
    x, y = p[0] - cx, p[1] - cy
    return (cx + x * c - y * s, cy + x * s + y * c, p[2])


def _shade(color, normal, depth, night=False):
    d = abs(_dot(normal, _LIGHT))
    f = 0.48 + 0.62 * d
    r, g, b = color[:3]
    r, g, b = r * f, g * f, b * f
    if night:
        r, g, b = r * 0.58, g * 0.62, b * 0.72
    fog = max(0.0, min(0.66, (depth - 1200.0) / 5200.0))
    fr, fg, fb = (42, 48, 62) if night else (188, 194, 186)
    r = r * (1.0 - fog) + fr * fog
    g = g * (1.0 - fog) + fg * fog
    b = b * (1.0 - fog) + fb * fog
    return (max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))))


def _box(cx, cy, z, w, d, h, color, rot=0.0):
    """Six quads, in world coordinates, with the base at z."""
    hw, hd = w * 0.5, d * 0.5
    b = [(-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0)]
    t = [(x, y, h) for (x, y, _z) in b]
    pts = [(cx + x, cy + y, z + zz) for (x, y, zz) in b + t]
    if rot:
        pts = [_rot_z(p, cx, cy, rot) for p in pts]
    quads = [
        (0, 1, 2, 3), (7, 6, 5, 4),
        (0, 4, 5, 1), (1, 5, 6, 2),
        (2, 6, 7, 3), (3, 7, 4, 0),
    ]
    return [(tuple(pts[i] for i in q), color) for q in quads]


def _cylinder(cx, cy, z, r, h, sides, color, rot=0.0, top=True):
    out = []
    a0 = rot
    ring0 = []
    ring1 = []
    for i in range(sides):
        a = a0 + i * (2.0 * math.pi / sides)
        x, y = math.cos(a) * r, math.sin(a) * r
        ring0.append((cx + x, cy + y, z))
        ring1.append((cx + x, cy + y, z + h))
    for i in range(sides):
        j = (i + 1) % sides
        out.append(((ring0[i], ring0[j], ring1[j], ring1[i]), color))
    if top:
        out.append((tuple(reversed(ring1)), color))
    return out


def _octa(cx, cy, cz, rx, ry, rz, color):
    p = [(cx, cy, cz + rz), (cx + rx, cy, cz), (cx, cy + ry, cz),
         (cx - rx, cy, cz), (cx, cy - ry, cz), (cx, cy, cz - rz)]
    # 0 top, 1 east, 2 south, 3 west, 4 north, 5 bottom
    faces = ((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
             (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4))
    return [(tuple(p[i] for i in f), color) for f in faces]


def _cone(cx, cy, z, r, h, sides, color, rot=0.0):
    apex = (cx, cy, z + h)
    base = []
    for i in range(sides):
        a = rot + i * (2.0 * math.pi / sides)
        base.append((cx + math.cos(a) * r, cy + math.sin(a) * r, z))
    out = []
    for i in range(sides):
        out.append(((base[i], base[(i + 1) % sides], apex), color))
    out.append((tuple(reversed(base)), color))
    return out


def _roof(cx, cy, z, w, d, h, color, rot=0.0):
    hw, hd = w * 0.5, d * 0.5
    b = [(-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0)]
    # a simple gabled roof: ridge runs along x
    ridge0 = (0.0, -hd, h)
    ridge1 = (0.0, hd, h)
    pts = [(cx + x, cy + y, z + zz) for (x, y, zz) in b]
    r0 = (cx + ridge0[0], cy + ridge0[1], z + ridge0[2])
    r1 = (cx + ridge1[0], cy + ridge1[1], z + ridge1[2])
    if rot:
        pts = [_rot_z(p, cx, cy, rot) for p in pts]
        r0 = _rot_z(r0, cx, cy, rot)
        r1 = _rot_z(r1, cx, cy, rot)
    return [
        ((pts[0], pts[1], r0), color),
        ((pts[2], pts[3], r1), color),
        ((pts[1], pts[2], r1, r0), color),
        ((pts[3], pts[0], r0, r1), color),
    ]


class Scene:
    """Projected geometry plus billboards, sorted far-to-near."""

    def __init__(self, fwd, right, up, ex, ey, night=False):
        self.fwd = fwd
        self.right = right
        self.up = up
        self.ex = float(ex)
        self.ey = float(ey)
        self.night = bool(night)
        self.ops = []
        self.ground_ops = []

    def _cam(self, p):
        dx, dy, dz = p[0] - self.ex, p[1] - self.ey, p[2] - EYE_Z
        return (self.right[0] * dx + self.right[1] * dy + self.right[2] * dz,
                self.up[0] * dx + self.up[1] * dy + self.up[2] * dz,
                self.fwd[0] * dx + self.fwd[1] * dy + self.fwd[2] * dz)

    def _clip(self, pts):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            ina, inb = a[2] >= NEAR, b[2] >= NEAR
            if ina:
                out.append(a)
            if ina != inb:
                t = (NEAR - a[2]) / (b[2] - a[2])
                out.append((a[0] + (b[0] - a[0]) * t,
                            a[1] + (b[1] - a[1]) * t, NEAR))
        return out

    def _project(self, p):
        if p[2] <= 0.01:
            return None
        # pygame's polygon path is unhappy with numpy scalars; keep the
        # projection in plain Python floats.
        return (float(IW * 0.5 + FOCAL * p[0] / p[2]),
                float(IH * 0.5 - FOCAL * p[1] / p[2]))

    def add_face(self, world_pts, color, ground=False, outline=None, layer=0):
        if len(world_pts) < 3:
            return
        # normal from the original world points
        n = _norm(_cross(_sub(world_pts[1], world_pts[0]),
                         _sub(world_pts[2], world_pts[0])))
        cam = [self._cam(p) for p in world_pts]
        cz = sum(p[2] for p in cam) / len(cam)
        if cz > DRAW_DIST or max(p[2] for p in cam) < NEAR:
            return
        cl = self._clip(cam)
        if len(cl) < 3:
            return
        pts = [self._project(p) for p in cl]
        pts = [p for p in pts if p is not None]
        if len(pts) < 3:
            return
        # skip degenerate slivers
        area = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            area += x0 * y1 - x1 * y0
        if abs(area) < 1.5:
            return
        # A face very close to the eye can project to enormous screen
        # coordinates.  pygame will grind on those; the visible part is just
        # a wall filling the frame, which the sky/ground already supplies.
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if min(xs) > IW + 60 or max(xs) < -60 or \
                min(ys) > IH + 60 or max(ys) < -60:
            return
        if max(abs(v) for v in xs + ys) > 12000.0:
            return
        op = (cz, "face", pts, _shade(color, n, cz, self.night), outline)
        if ground:
            # Ground layers are drawn in explicit layers before depth:
            # natural terrain first, then exact worked tiles, then target.
            self.ground_ops.append((layer,) + op)
        else:
            self.ops.append(op)

    def add_shadow(self, x, y, rx, ry=None):
        """A soft flat footprint, so a billboard actor sits on the ground."""
        if ry is None:
            ry = rx * 0.52
        n = 10
        pts = []
        for i in range(n):
            a = i * (2.0 * math.pi / n)
            pts.append((x + math.cos(a) * rx, y + math.sin(a) * ry, 0.32))
        self.add_face(pts, (34, 47, 32), ground=True, layer=1)

    def add_sprite(self, image, x, y, world_h=50.0, ax=None, ay=None):
        return self.add_float_sprite(image, x, y, 0.0, world_h, ax, ay)

    def add_float_sprite(self, image, x, y, z, world_h=50.0, ax=None, ay=None):
        base = self._cam((x, y, z))
        top = self._cam((x, y, z + world_h))
        if base[2] <= NEAR or top[2] <= NEAR:
            return
        sx = float(IW * 0.5 + FOCAL * base[0] / base[2])
        sy = float(IH * 0.5 - FOCAL * base[1] / base[2])
        tx = float(IW * 0.5 + FOCAL * top[0] / top[2])
        ty = float(IH * 0.5 - FOCAL * top[1] / top[2])
        sh = abs(sy - ty)
        if sh < 1.0 or base[2] > DRAW_DIST:
            return
        if ax is None:
            ax = image.get_width() * 0.5
        if ay is None:
            ay = image.get_height()
        scale = sh / float(max(1, image.get_height()))
        dw = max(1, int(image.get_width() * scale))
        dh = max(1, int(image.get_height() * scale))
        if sx < -dw or sx > IW + dw or sy < -dh or sy > IH + 80:
            return
        self.ops.append((base[2], "sprite", image, sx, sy, dw, dh,
                         ax * scale, ay * scale))

    def draw(self, screen):
        # Worked ground is a surface under everything else, even when a
        # crop/character is at almost the same depth.
        self.ground_ops.sort(key=lambda op: (op[0], -op[1]))
        for op in self.ground_ops:
            _layer, _d, _k, pts, color, outline = op
            pygame.draw.polygon(screen, color, pts)
            if outline is not None:
                pygame.draw.polygon(screen, outline, pts, 1)
        self.ops.sort(key=lambda op: op[0], reverse=True)
        for op in self.ops:
            if op[1] == "face":
                _d, _k, pts, color, outline = op
                pygame.draw.polygon(screen, color, pts)
                if outline is not None:
                    pygame.draw.polygon(screen, outline, pts, 1)
            else:
                _d, _k, image, sx, sy, dw, dh, ax, ay = op
                try:
                    pic = pygame.transform.scale(image, (dw, dh))
                    screen.blit(pic, (int(sx - ax), int(sy - ay)))
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# world geometry
# ---------------------------------------------------------------------------
def _cache(g):
    c = getattr(g, "_v3_mesh_cache", None)
    if not isinstance(c, dict):
        c = g._v3_mesh_cache = {}
    return c


def _add_faces(scene, faces):
    for pts, color in faces:
        scene.add_face(pts, color)


def _tree_faces(t):
    x, y = float(t.x), float(t.y)
    if getattr(t, "felled", False):
        return _cylinder(x, y, 0.0, max(3.0, t.canopy_r * 0.10),
                          max(8.0, t.canopy_r * 0.25), 6, (112, 82, 52))
    r = max(8.0, float(getattr(t, "canopy_r", 20.0)))
    h = max(42.0, r * 2.15)
    species = getattr(t, "species", "broadleaf")
    rng = random.Random(int(x * 17 + y * 31) & 0xFFFFFFFF)
    trunk_r = max(2.8, r * 0.075)
    trunk_h = h * 0.62
    if species == "cactus":
        green = (46, 112, 58)
        dark = (28, 74, 42)
        faces = _box(x, y, 0.0, trunk_r * 1.8, trunk_r * 1.8, trunk_h * 1.10, green)
        for k in range(3):
            ang = k * 2.0 * math.pi / 3.0 + 0.4
            ox, oy = math.cos(ang) * trunk_r * 1.7, math.sin(ang) * trunk_r * 1.7
            faces += _box(x + ox, y + oy, trunk_h * 0.35,
                          trunk_r * 0.9, trunk_r * 0.9, trunk_h * 0.55, dark, ang)
        return faces
    if species in ("palm", "banana_palm", "cocoa_palm"):
        wood = (112, 82, 52) if species != "blackwood" else (50, 40, 34)
        faces = _cylinder(x, y, 0.0, trunk_r, h * 0.86, 6, wood)
        leaf = (50, 118, 54) if species != "cocoa_palm" else (62, 88, 46)
        for k in range(7):
            a = k * (2.0 * math.pi / 7.0) + 0.3
            lx, ly = x + math.cos(a) * r * 0.45, y + math.sin(a) * r * 0.45
            ex_, ey_ = x + math.cos(a) * r * 1.15, y + math.sin(a) * r * 1.15
            faces.append((((x, y, h * 0.80), (lx, ly, h * 0.94),
                           (ex_, ey_, h * 0.55), (x + math.cos(a) * 3,
                                                  y + math.sin(a) * 3,
                                                  h * 0.72)), leaf))
            # a second leaf surface gives the frond volume
            faces.append((((x, y, h * 0.78), (ex_, ey_, h * 0.53),
                           (lx, ly, h * 0.86)), leaf))
        if species == "cocoa_palm":
            for k in range(3):
                a = k * 2.0 + 1.0
                faces += _octa(x + math.cos(a) * 5, y + math.sin(a) * 5,
                               h * 0.62, 4, 4, 5, (128, 74, 38))
        return faces
    if species in ("conifer",):
        faces = _cylinder(x, y, 0.0, trunk_r, h * 0.72, 6, (92, 66, 42))
        for k, (rr, zz, hh) in enumerate(((r * 0.86, 0.20, 0.50),
                                          (r * 0.68, 0.42, 0.43),
                                          (r * 0.48, 0.62, 0.34))):
            faces += _cone(x, y, h * zz, rr, h * hh, 7, (34, 86, 48))
        return faces
    # broadleaf / blackwood / ironwood
    if species == "blackwood":
        wood, leaf = (36, 30, 28), (34, 44, 38)
        leaf2 = (46, 58, 46)
    elif species == "ironwood":
        wood, leaf = (94, 84, 74), (54, 82, 60)
        leaf2 = (70, 96, 72)
    else:
        wood, leaf = (104, 72, 44), (44, 100, 50)
        leaf2 = (64, 126, 58)
    faces = _cylinder(x, y, 0.0, trunk_r, trunk_h, 6, wood)
    # a few low-poly crowns, not one perfect ball
    for k in range(4):
        a = k * 1.7 + rng.uniform(-0.25, 0.25)
        rr = r * rng.uniform(0.44, 0.64)
        ox = math.cos(a) * r * rng.uniform(0.18, 0.42)
        oy = math.sin(a) * r * rng.uniform(0.18, 0.42)
        cz = h * (0.62 + 0.12 * k)
        faces += _octa(x + ox, y + oy, cz, rr, rr * 0.86, rr * 0.93,
                       leaf if k % 2 == 0 else leaf2)
    return faces


def add_tree(scene, g, t):
    if math.hypot(float(t.x) - scene.ex, float(t.y) - scene.ey) > DRAW_DIST:
        return
    key = ("tree", id(t), bool(getattr(t, "felled", False)))
    c = _cache(g)
    faces = c.get(key)
    if faces is None:
        faces = _tree_faces(t)
        c[key] = faces
    now = float(getattr(g, "now", 0.0))
    if getattr(t, "felled", False):
        _add_faces(scene, faces)
        return
    # The canopy bends with the local breeze and shakes when the axe lands.
    # Only the upper part moves; the trunk stays planted.
    try:
        import wind
        sx, sy = wind.sway(float(t.x), float(t.y), 1.0)
    except Exception:
        sx = sy = 0.0
    hit = float(getattr(t, "hit_until", 0.0)) - now
    hit = max(0.0, min(1.0, hit / 0.5))
    height = max(42.0, float(getattr(t, "canopy_r", 20.0)) * 2.15)
    for pts, color in faces:
        moved = []
        for (x, y, z) in pts:
            f = max(0.0, min(1.0, z / height))
            dx = sx * f * 1.5
            dy = sy * f * 1.5
            if hit > 0.0:
                dx += math.sin(now * 72.0 + z * 0.11) * 11.0 * hit * f
                dy += math.sin(now * 91.0 + z * 0.07) * 4.0 * hit * f
            moved.append((x + dx, y + dy, z))
        scene.add_face(moved, color)


def _house_faces(h):
    x, y = float(h.x), float(h.y)
    w = float(getattr(h, "rect", None).w if getattr(h, "rect", None) is not None
              else getattr(h, "w", 100))
    d = float(getattr(h, "rect", None).h if getattr(h, "rect", None) is not None
              else getattr(h, "h", 90))
    fx, fy = getattr(h, "facing", (0.0, 1.0))
    rot = math.atan2(fy, fx) - math.pi / 2.0
    wall_h = max(36.0, min(76.0, 0.42 * min(w, d) + 28.0))
    wall = (196, 174, 138)
    trim = (112, 88, 62)
    roof = (132, 66, 52)
    if getattr(h, "government", False):
        wall = (174, 174, 166)
        roof = (86, 92, 102)
    faces = []
    # walls: four thin slabs around a hollow footprint
    t = 6.0
    faces += _box(x, y - d * 0.5 + t * 0.5, 0, w, t, wall_h, wall, rot)
    faces += _box(x, y + d * 0.5 - t * 0.5, 0, w, t, wall_h, wall, rot)
    faces += _box(x - w * 0.5 + t * 0.5, y, 0, t, d, wall_h, wall, rot)
    faces += _box(x + w * 0.5 - t * 0.5, y, 0, t, d, wall_h, wall, rot)
    # floor band / trim
    faces += _box(x, y, 0, w + 2, d + 2, 4, trim, rot)
    # roof
    faces += _roof(x, y, wall_h, w + 12, d + 12, max(18.0, wall_h * 0.55),
                   roof, rot)
    # door and windows are shallow dark faces on the front
    front_y = y + d * 0.5 + 0.8
    faces += _box(x, front_y, 2, max(10.0, w * 0.14), 1.5,
                  min(30.0, wall_h * 0.58), (62, 44, 30), rot)
    for sx, sz in ((-0.30, 0.48), (0.30, 0.48)):
        wx = x + sx * w
        faces += _box(wx, front_y, wall_h * sz, max(8.0, w * 0.12), 1.5,
                      max(7.0, wall_h * 0.18), (92, 120, 132), rot)
    return faces


def add_house(scene, g, h):
    if math.hypot(float(h.x) - scene.ex, float(h.y) - scene.ey) > DRAW_DIST:
        return
    key = ("house", id(h), getattr(h, "w", 0), getattr(h, "h", 0),
           getattr(h, "facing", (0, 1)), getattr(h, "government", False))
    c = _cache(g)
    faces = c.get(key)
    if faces is None:
        faces = _house_faces(h)
        c[key] = faces
    _add_faces(scene, faces)


def _work_faces(wp):
    x, y = float(wp.x), float(wp.y)
    w = float(getattr(wp, "w", 64))
    d = float(getattr(wp, "h", 64))
    kind = getattr(wp, "kind", "workshop")
    wood = (134, 92, 56)
    wood_d = (72, 48, 30)
    metal = (104, 108, 116)
    faces = []
    # A FIREPLACE IS A FIRE, NOT A BENCH.  The generic work table used to be
    # built before the kind-specific parts, which put a brown wooden slab and
    # legs on top of every campfire.
    if kind == "fireplace":
        for k in range(9):
            a = k * math.pi * 2.0 / 9.0
            faces += _box(x + math.cos(a) * w * 0.30,
                          y + math.sin(a) * d * 0.30,
                          0, 8, 8, 9, (108, 104, 98), a)
        return faces
    top_h = 24.0
    # legs and table, small enough to read from a first-person distance
    lw = max(3.0, w * 0.08)
    for ox in (-0.36, 0.36):
        for oy in (-0.36, 0.36):
            faces += _box(x + ox * w, y + oy * d, 0, lw, lw, top_h, wood_d)
    faces += _box(x, y, top_h - 4, w * 0.78, d * 0.72, 5, wood)
    if kind in ("lab", "brewery", "research", "smith"):
        # bottles / barrels / a heavy anvil
        if kind in ("lab", "research"):
            faces += _cylinder(x - w * 0.18, y, top_h, 4, 13, 6, (150, 196, 176))
            faces += _cylinder(x + w * 0.10, y + 3, top_h, 4, 9, 6, (186, 148, 82))
        elif kind == "brewery":
            faces += _cylinder(x, y, 0, w * 0.22, top_h * 0.9, 8, (108, 72, 42))
            faces += _cylinder(x, y, top_h * 0.9, w * 0.22, 4, 8, (70, 48, 30))
        else:
            faces += _box(x, y, top_h, w * 0.26, d * 0.18, 9, metal)
    elif kind in ("dummy", "target"):
        faces += _box(x, y, top_h, 6, 6, max(28.0, d * 0.65), wood_d)
        faces += _box(x, y, top_h + 18, w * 0.42, 5, 5, wood)
    elif kind in ("barracks", "mine", "medicine_hut"):
        faces += _box(x, y, 0, w * 0.72, d * 0.72, 34, wood_d)
        faces += _roof(x, y, 34, w * 0.86, d * 0.86, 17,
                       (90, 66, 48) if kind != "medicine_hut" else (132, 108, 74))
    elif kind in ("weaver", "spice"):
        faces += _box(x, y, top_h, w * 0.42, 3, 16, wood_d)
        faces += _box(x, y, top_h + 8, w * 0.36, 3, 3, (198, 184, 152))
    return faces


def add_workplace(scene, g, wp):
    if math.hypot(float(wp.x) - scene.ex, float(wp.y) - scene.ey) > DRAW_DIST:
        return
    key = ("work", id(wp), getattr(wp, "kind", ""), getattr(wp, "w", 0),
           getattr(wp, "h", 0))
    c = _cache(g)
    faces = c.get(key)
    if faces is None:
        faces = _work_faces(wp)
        c[key] = faces
    _add_faces(scene, faces)


# ---------------------------------------------------------------------------
# crops
# ---------------------------------------------------------------------------
def _crop_sprite(g, kind, elapsed, biome, blight):
    import crop
    stage = crop.stage(max(0.0, elapsed))
    key = (kind, stage, biome, bool(blight))
    cache = getattr(g, "_v3_crop_cache", None)
    if not isinstance(cache, dict):
        cache = g._v3_crop_cache = {}
    got = cache.get(key)
    if got is not None:
        return got
    surf = pygame.Surface((64, 92), pygame.SRCALPHA)
    t = stage * crop.PHASE_SECONDS + 0.01
    try:
        crop.draw_crop(surf, 32, 84, kind, t, 0.0, 0.0, biome, blight)
    except Exception:
        # A crop whose art failed must still be visible as a small green card.
        pygame.draw.rect(surf, (60, 110, 54), (26, 40, 12, 44), border_radius=4)
    cache[key] = surf
    return surf


def add_crops(scene, g, radius=1400.0):
    try:
        import crop
        plants = crop.visible_plants(g.world, scene.ex - radius, scene.ey - radius,
                                     radius * 2.0, radius * 2.0, pad=120)
    except Exception:
        return
    for x, y, planted_at, kind, biome, blight in plants:
        if math.hypot(x - scene.ex, y - scene.ey) > radius:
            continue
        elapsed = float(getattr(g, "now", 0.0)) - float(planted_at or g.now)
        img = _crop_sprite(g, kind, elapsed, biome, blight)
        # The crop card is small and anchored at the soil.
        scene.add_sprite(img, x, y, 44.0, ax=32.0, ay=84.0)



# ---------------------------------------------------------------------------
# worked ground, built blocks, fire
# ---------------------------------------------------------------------------
def _tile_colour(g, tx, ty):
    """One fixed colour per world tile, not one per screen pixel."""
    cache = getattr(g, "_v3_tile_colours", None)
    if not isinstance(cache, dict):
        cache = g._v3_tile_colours = {}
    ver = int(getattr(getattr(g, "ground", None), "_version", 0) or 0)
    key = (ver, tx, ty)
    got = cache.get(key)
    if got is not None:
        return got
    col = None
    try:
        chunk = 256
        cx, cy = int(tx * 32 // chunk), int(ty * 32 // chunk)
        lx = int(tx * 32 - cx * chunk) & 255
        ly = int(ty * 32 - cy * chunk) & 255
        surf = g.ground.get(cx, cy)
        if surf is not None:
            col = surf.get_at((lx, ly))[:3]
        else:
            col = g.ground._coarse_color(cx, cy)
    except Exception:
        col = None
    if col is None:
        try:
            import biomes
            t = float(g.world.temperature(tx * 32 + 16, ty * 32 + 16))
            h = float(g.world.humidity(tx * 32 + 16, ty * 32 + 16))
            dark, lite, _spec, _dens = biomes.mix(t, h)
            col = tuple(int((dark[i] + lite[i]) * 0.5) for i in range(3))
        except Exception:
            col = (70, 104, 58)
    # NO PER-BLOCK COLOUR JITTER.  The variation was reading as a dark grid
    # line between every natural block; the ground colour should come from
    # the world and neighbouring blocks should be allowed to blend.
    cache[key] = col
    if len(cache) > 24000:
        cache.clear()
        cache[key] = col
    return col


def _ground_state(g, tx, ty):
    try:
        plot = g.world.plot_at(tx, ty)
    except Exception:
        plot = None
    if plot is None:
        return ("natural",)
    kind = getattr(plot, "kind", "")
    if kind in ("grass", "", None):
        return ("natural",)
    return (kind, getattr(plot, "planted_at", None) is not None)


def _edge_strips(scene, x0, y0, x1, y1, z, color, width=0.9, layer=1):
    """Four thin world quads around a tile, instead of filling its outline."""
    w = width
    scene.add_face(((x0, y0, z), (x1, y0, z),
                    (x1, y0 + w, z), (x0, y0 + w, z)), color, ground=True, layer=layer)
    scene.add_face(((x0, y1 - w, z), (x1, y1 - w, z),
                    (x1, y1, z), (x0, y1, z)), color, ground=True, layer=layer)
    scene.add_face(((x0, y0, z), (x0 + w, y0, z),
                    (x0 + w, y1, z), (x0, y1, z)), color, ground=True, layer=layer)
    scene.add_face(((x1 - w, y0, z), (x1, y0, z),
                    (x1, y1, z), (x1 - w, y1, z)), color, ground=True, layer=layer)


def add_ground_target(scene, g):
    """The block under the crosshair gets a bright visible edge."""
    if scene.fwd[2] >= -1e-4:
        return
    t = -EYE_Z / scene.fwd[2]
    if t < 0.0 or t > 2600.0:
        return
    wx = scene.ex + scene.fwd[0] * t
    wy = scene.ey + scene.fwd[1] * t
    tx, ty = int(wx // 32), int(wy // 32)
    cx, cy = tx * 32.0 + 16.0, ty * 32.0 + 16.0
    z = 0.96
    _edge_strips(scene, cx - 15.2, cy - 15.2, cx + 15.2, cy + 15.2,
                 z, (255, 235, 142), 1.4, layer=2)


def _add_natural_layer(scene, g, size, min_dist, max_dist):
    """A coarse block layer for the middle/far ground, so the horizon is
    ground rather than a fog wall, without four thousand tiny near blocks."""
    tx0 = int(math.floor((scene.ex - max_dist) / size))
    tx1 = int(math.ceil((scene.ex + max_dist) / size))
    ty0 = int(math.floor((scene.ey - max_dist) / size))
    ty1 = int(math.ceil((scene.ey + max_dist) / size))
    half = size * 0.5
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            wx, wy = tx * size + half, ty * size + half
            d = math.hypot(wx - scene.ex, wy - scene.ey)
            if d < min_dist or d > max_dist:
                continue
            _dx, _dy = wx - scene.ex, wy - scene.ey
            cz = scene.fwd[0] * _dx + scene.fwd[1] * _dy
            if cz < -half * 2.0:
                continue
            side = scene.right[0] * _dx + scene.right[1] * _dy
            if abs(side) > max(half * 1.6, cz * 2.3):
                continue
            top = _tile_colour(g, int(wx // 32), int(wy // 32))
            x0, x1 = wx - half, wx + half
            y0, y1 = wy - half, wy + half
            scene.add_face(((x0, y0, 0.58), (x1, y0, 0.58),
                            (x1, y1, 0.58), (x0, y1, 0.58)),
                           top, ground=True)


def add_ground_blocks(scene, g, radius=420.0):
    """The ground as actual square blocks, not a perspective image.

    Natural ground uses 2x2-tile blocks so the first-person view does not pay
    for four thousand tiny polygons.  Worked tiles are drawn on top as exact
    1x1 blocks, so a tilled square is still one square and its state is
    independent of the camera.
    """
    # A wide coarse layer first; the near 64-block layer and exact worked
    # tiles are drawn over it.
    _add_natural_layer(scene, g, 256.0, 350.0, 3000.0)
    size = 64.0
    tx0 = int(math.floor((scene.ex - radius) / size))
    tx1 = int(math.ceil((scene.ex + radius) / size))
    ty0 = int(math.floor((scene.ey - radius) / size))
    ty1 = int(math.ceil((scene.ey + radius) / size))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            wx, wy = tx * size + 32.0, ty * size + 32.0
            if math.hypot(wx - scene.ex, wy - scene.ey) > radius:
                continue
            _dx, _dy = wx - scene.ex, wy - scene.ey
            _cz = scene.fwd[0] * _dx + scene.fwd[1] * _dy
            if _cz < -64.0:
                continue
            _side = scene.right[0] * _dx + scene.right[1] * _dy
            if abs(_side) > max(100.0, _cz * 1.85):
                continue
            top = _tile_colour(g, tx * 2, ty * 2)
            edge = tuple(int(v * 0.58) for v in top)
            z = 0.65
            x0, x1 = wx - 32.0, wx + 32.0
            y0, y1 = wy - 32.0, wy + 32.0
            scene.add_face(((x0, y0, z), (x1, y0, z),
                            (x1, y1, z), (x0, y1, z)),
                           top, ground=True)
    # Exact worked squares on top of the coarse natural blocks.
    try:
        ptx0 = int((scene.ex - radius) // 32)
        ptx1 = int((scene.ex + radius) // 32)
        pty0 = int((scene.ey - radius) // 32)
        pty1 = int((scene.ey + radius) // 32)
        plots = g.world.plots_in_tile_range(ptx0, pty0, ptx1, pty1)
    except Exception:
        plots = ()
    for (tx, ty), plot in plots:
        kind = getattr(plot, "kind", "")
        if kind in ("grass", "", None):
            continue
        wx, wy = tx * 32.0 + 16.0, ty * 32.0 + 16.0
        if math.hypot(wx - scene.ex, wy - scene.ey) > radius:
            continue
        planted = getattr(plot, "planted_at", None) is not None
        top = (76, 52, 32) if planted else (132, 101, 66)
        edge = (42, 28, 18)
        z = 0.74
        x0, x1 = wx - 16.0, wx + 16.0
        y0, y1 = wy - 16.0, wy + 16.0
        scene.add_face(((x0, y0, z), (x1, y0, z),
                        (x1, y1, z), (x0, y1, z)),
                       top, ground=True, layer=1)
        mine = _ground_state(g, tx, ty)
        ex0, ey0 = wx - 16.0, wy - 16.0
        ex1, ey1 = wx + 16.0, wy + 16.0
        if _ground_state(g, tx, ty - 1) != mine:
            scene.add_face(((ex0, ey0, z + 0.12), (ex1, ey0, z + 0.12),
                            (ex1, ey0 + 0.9, z + 0.12),
                            (ex0, ey0 + 0.9, z + 0.12)), edge, ground=True, layer=1)
        if _ground_state(g, tx, ty + 1) != mine:
            scene.add_face(((ex0, ey1 - 0.9, z + 0.12), (ex1, ey1 - 0.9, z + 0.12),
                            (ex1, ey1, z + 0.12), (ex0, ey1, z + 0.12)),
                           edge, ground=True, layer=1)
        if _ground_state(g, tx - 1, ty) != mine:
            scene.add_face(((ex0, ey0, z + 0.12), (ex0 + 0.9, ey0, z + 0.12),
                            (ex0 + 0.9, ey1, z + 0.12),
                            (ex0, ey1, z + 0.12)), edge, ground=True, layer=1)
        if _ground_state(g, tx + 1, ty) != mine:
            scene.add_face(((ex1 - 0.9, ey0, z + 0.12), (ex1, ey0, z + 0.12),
                            (ex1, ey1, z + 0.12), (ex1 - 0.9, ey1, z + 0.12)),
                           edge, ground=True, layer=1)
        for k in range(4):
            yy = y0 + 4.0 + k * 7.0
            scene.add_face(((x0 + 1.5, yy, z + 0.06),
                            (x1 - 1.5, yy, z + 0.06),
                            (x1 - 1.5, yy + 1.2, z + 0.06),
                            (x0 + 1.5, yy + 1.2, z + 0.06)),
                           (52, 34, 20), ground=True, layer=1)


def add_plot_tiles(scene, g, radius=1300.0):
    """Draw the actual worked squares as fixed world quads.

    The ground image is sampled from the old 2D surfaces; near a tilled field
    that sampling can shimmer as the view turns.  A worked tile is a real,
    persistent thing, so it gets a real, persistent face here.  This is also
    what makes a field read as a field from across the settlement.
    """
    try:
        tx = int((scene.ex - radius) // 32)
        ty = int((scene.ey - radius) // 32)
        tx1 = int((scene.ex + radius) // 32)
        ty1 = int((scene.ey + radius) // 32)
        plots = g.world.plots_in_tile_range(tx, ty, tx1, ty1)
    except Exception:
        return
    spoil = (84, 58, 36)
    fertile = (104, 72, 42)
    for (ptx, pty), plot in plots:
        kind = getattr(plot, "kind", "")
        if kind in ("grass", "", None):
            continue
        wx = ptx * 32.0 + 16.0
        wy = pty * 32.0 + 16.0
        if math.hypot(wx - scene.ex, wy - scene.ey) > radius:
            continue
        soil = fertile if kind in ("fertile", "plant", "wheat", "berries",
                                   "mushroom", "agave", "cactus", "cotton",
                                   "chili", "hardberry", "pipeleaf", "banana",
                                   "cocoa", "honeyflower", "highflower") else spoil
        z = 0.45
        x0, x1 = wx - 16.0, wx + 16.0
        y0, y1 = wy - 16.0, wy + 16.0
        scene.add_face(((x0, y0, z), (x1, y0, z),
                        (x1, y1, z), (x0, y1, z)), soil, ground=True)
        # Four dark furrows.  These are world-fixed, so they stay put while
        # the camera turns.
        for k in range(4):
            yy = y0 + 4.0 + k * 7.4
            scene.add_face(((x0 + 1.5, yy, z + 0.15), (x1 - 1.5, yy, z + 0.15),
                            (x1 - 1.5, yy + 1.4, z + 0.15),
                            (x0 + 1.5, yy + 1.4, z + 0.15)),
                           (56, 38, 24) if soil == spoil else (74, 48, 28),
                           ground=True)


def _bed_faces(tx, ty):
    x = tx * 32.0 + 16.0
    y = ty * 32.0 + 16.0
    wood = (118, 78, 44)
    sheet = (246, 246, 242)
    pillow = (255, 255, 252)
    blanket = (226, 226, 222)
    faces = []
    faces += _box(x, y, 1.0, 29, 29, 3.0, wood)
    faces += _box(x, y, 3.5, 27, 27, 2.0, sheet)
    faces += _box(x - 7.5, y, 5.3, 10, 24, 3.0, pillow)
    faces += _box(x + 4.0, y, 5.2, 13, 24, 2.2, blanket)
    faces += _box(x + 4.0, y, 7.2, 13, 24, 1.0, (198, 198, 194))
    return faces


def add_built_blocks(scene, g, radius=1600.0):
    """Bedrolls, planks, doors and hide panels placed on the ground."""
    blocks = getattr(g, "built_blocks", None) or {}
    if not blocks:
        return
    tile = 32.0
    for (tx, ty), kind in list(blocks.items()):
        x = tx * tile + tile * 0.5
        y = ty * tile + tile * 0.5
        if math.hypot(x - scene.ex, y - scene.ey) > radius:
            continue
        if kind == "bed":
            _add_faces(scene, _bed_faces(tx, ty))
            continue
        col = {"wood": (118, 78, 44), "ironwood": (104, 106, 106),
               "tropical_wood": (218, 214, 198), "hide": (124, 86, 54),
               "door": (126, 82, 46)}.get(kind, (118, 78, 44))
        if kind == "door":
            # A thin door leaf, open enough to read as a doorway.
            _add_faces(scene, _box(x, y, 0.0, 28, 2.5, 48, col))
            _add_faces(scene, _box(x + 11.5, y - 1.0, 24, 1.5, 3.5, 3,
                                   (216, 190, 100)))
        else:
            h = 30.0 if kind != "hide" else 20.0
            _add_faces(scene, _box(x, y, 0.0, 30, 30, h, col))
            # a lighter top lip makes adjacent blocks read separately
            _add_faces(scene, _box(x, y, h, 30.5, 30.5, 1.5,
                                   tuple(min(255, int(c * 1.22)) for c in col)))


def add_fire(scene, wp, now):
    """A living campfire: logs, embers and three licking flame tongues."""
    x, y = float(wp.x), float(wp.y)
    phase = float(now) * 7.0 + x * 0.013 + y * 0.017
    # NO LOGS ON TOP.  A fireplace is a fire, not a pile of brown boxes:
    # a low ember bed and a large, living flame.
    _add_faces(scene, _box(x, y, 0.4, 20, 20, 2.0, (196, 56, 18)))
    for k in range(5):
        a = phase * (0.72 + k * 0.13) + k * 1.71
        sway = math.sin(a) * 7.0
        h = 30.0 + 18.0 * (0.5 + 0.5 * math.sin(a * 1.65 + k))
        w = 10.0 - k * 0.8
        cx = x + (-11.0 + k * 5.5) + sway * 0.4
        cy = y + math.cos(a * 0.8) * 4.0
        z = 2.0 + k * 0.8
        base = ((cx - w, cy - w * 0.55, z), (cx + w, cy - w * 0.55, z),
                (cx + w * 0.5, cy + w * 0.7, z),
                (cx - w * 0.5, cy + w * 0.7, z))
        tip = (cx + sway * 0.5, cy + math.sin(a * 1.3) * 3.0, z + h)
        scene.add_face((base[0], base[1], tip), (255, 198, 70))
        scene.add_face((base[1], base[2], tip), (255, 126, 26))
        scene.add_face((base[2], base[3], tip), (250, 62, 14))
        scene.add_face((base[3], base[0], tip), (255, 238, 150))
    # a warm pool at the base, not a wooden platform
    scene.add_face(((x - 18, y - 18, 0.7), (x + 18, y - 18, 0.7),
                    (x + 18, y + 18, 0.7), (x - 18, y + 18, 0.7)),
                   (186, 64, 20))


# ---------------------------------------------------------------------------
# projectiles and muzzle flashes
# ---------------------------------------------------------------------------
_PROJECTILE_CACHE: dict = {}


def _projectile_image(arrow=False, owner="player"):
    key = ("arrow" if arrow else "bullet", owner)
    got = _PROJECTILE_CACHE.get(key)
    if got is not None:
        return got
    if arrow:
        s = pygame.Surface((28, 8), pygame.SRCALPHA)
        pygame.draw.line(s, (112, 76, 44), (1, 4), (24, 4), 3)
        pygame.draw.line(s, (238, 236, 222), (24, 1), (28, 4), 2)
        pygame.draw.line(s, (238, 236, 222), (24, 7), (28, 4), 2)
        pygame.draw.line(s, (220, 218, 204), (2, 1), (8, 4), 1)
        pygame.draw.line(s, (220, 218, 204), (2, 7), (8, 4), 1)
    else:
        s = pygame.Surface((18, 8), pygame.SRCALPHA)
        col = (255, 212, 92) if owner == "player" else (255, 112, 66)
        for i, a in ((0, 20), (1, 50), (2, 95)):
            gs = pygame.Surface((18, 8), pygame.SRCALPHA)
            pygame.draw.ellipse(gs, (*col, a), (i, i, 18 - i * 2, 8 - i * 2))
            s.blit(gs, (0, 0))
        pygame.draw.line(s, (255, 252, 220), (5, 4), (15, 4), 2)
    _PROJECTILE_CACHE[key] = s
    return s


def add_projectiles(scene, g):
    combat = getattr(g, "combat", None)
    if combat is None:
        return
    try:
        for b in list(getattr(combat, "bullets", ()) or ()):
            img = _projectile_image(bool(getattr(b, "arrow", False)),
                                    getattr(b, "owner", "player"))
            scene.add_float_sprite(img, float(b.x), float(b.y), 44.0,
                                   8.0, ax=img.get_width() * 0.5,
                                   ay=img.get_height() * 0.5)
        for x, y, _ang, ttl, owner in list(getattr(combat, "flashes", ()) or ()):
            k = max(0.0, min(1.0, float(ttl) / 0.07))
            if k <= 0.0:
                continue
            rad = int(4 + 14 * k)
            img = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            col = (255, 224, 120) if owner == "player" else (255, 142, 80)
            for r, a in ((rad, 45), (max(2, rad - 3), 100),
                         (max(1, rad - 7), 220)):
                pygame.draw.circle(img, (*col, a), (rad, rad), r)
            scene.add_float_sprite(img, float(x), float(y), 55.0,
                                   float(rad * 2),
                                   ax=rad, ay=rad)
        for x, y, _vx, _vy, life, colour in list(getattr(combat, "impacts", ()) or ()):
            sz = max(2, int(2 + 5 * float(life)))
            img = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(img, tuple(colour), (sz, sz), sz)
            scene.add_float_sprite(img, float(x), float(y), 34.0,
                                   float(sz * 2), ax=sz, ay=sz)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# scene assembly
# ---------------------------------------------------------------------------
def build_scene(g, fwd, right, up, ex, ey):
    scene = Scene(fwd, right, up, ex, ey, bool(getattr(g, "night", False)))
    # trees -- nearest first, with a cap; the wider list is for collision too
    trees = list(getattr(g, "view3d_trees", ()) or getattr(g, "view_trees", ()) or ())
    trees = [t for t in trees
             if not getattr(t, "felled", False)
             or True]                        # stumps are visible too
    trees.sort(key=lambda t: (float(t.x) - ex) ** 2 + (float(t.y) - ey) ** 2)
    for t in trees[:140]:
        d = math.hypot(float(t.x) - ex, float(t.y) - ey)
        # DETAIL NEAR, A CHEAP CARD FAR AWAY.  Full low-poly trees are
        # expensive; a distant tree is two dozen pixels tall, so its old
        # sprite is both faster and just as readable.
        if d <= 700.0:
            add_tree(scene, g, t)
        elif d <= 2200.0:
            try:
                img, _at = t.blit_world()
                scene.add_sprite(img, float(t.x), float(t.y),
                                 float(img.get_height()),
                                 ax=float(getattr(t, "sx", img.get_width() / 2)),
                                 ay=float(getattr(t, "sy", img.get_height())))
            except Exception:
                pass
    houses = []
    for v in getattr(g, "visible_villages", ()) or ():
        houses.extend(getattr(v, "houses", ()) or ())
    houses.extend(getattr(g, "built_houses", ()) or ())
    for h in houses:
        add_house(scene, g, h)
    works = []
    for v in getattr(g, "visible_villages", ()) or ():
        works.extend(getattr(v, "workplaces", ()) or ())
    works.extend(getattr(g, "placed_work", ()) or ())
    for wp in works:
        add_workplace(scene, g, wp)
        if getattr(wp, "kind", "") == "fireplace":
            add_fire(scene, wp, float(getattr(g, "now", 0.0)))
    add_ground_blocks(scene, g)
    add_built_blocks(scene, g)
    add_crops(scene, g)
    add_ground_target(scene, g)
    add_projectiles(scene, g)
    return scene


# ---------------------------------------------------------------------------
# first-person hands / held item, in camera space
# ---------------------------------------------------------------------------
def _vm_box(cx, cy, cz, w, h, d, color):
    hw, hh, hd = w * 0.5, h * 0.5, d * 0.5
    b = [(cx - hw, cy - hh, cz - hd), (cx + hw, cy - hh, cz - hd),
         (cx + hw, cy - hh, cz + hd), (cx - hw, cy - hh, cz + hd)]
    t = [(x, cy + hh, z) for (x, _y, z) in b]
    p = b + t
    faces = [(p[0], p[1], p[2], p[3]), (p[7], p[6], p[5], p[4]),
             (p[0], p[4], p[5], p[1]), (p[1], p[5], p[6], p[2]),
             (p[2], p[6], p[7], p[3]), (p[3], p[7], p[4], p[0])]
    return [(f, color) for f in faces]


def _vm_cyl(cx, cy, cz, r, h, sides, color):
    out = []
    ring0, ring1 = [], []
    for i in range(sides):
        a = i * 2.0 * math.pi / sides
        x, y = math.cos(a) * r, math.sin(a) * r
        ring0.append((cx + x, cy + y, cz))
        ring1.append((cx + x, cy + y, cz + h))
    for i in range(sides):
        j = (i + 1) % sides
        out.append(((ring0[i], ring0[j], ring1[j], ring1[i]), color))
    out.append((tuple(reversed(ring1)), color))
    return out


def _vm_prism(outline, z0, z1, color):
    """Extrude a 2-D camera-space outline along z, with front/back/sides."""
    out = []
    n = len(outline)
    front = tuple((x, y, z1) for (x, y) in outline)
    back = tuple((x, y, z0) for (x, y) in outline)
    out.append((front, color))
    out.append((tuple(reversed(back)), color))
    for i in range(n):
        j = (i + 1) % n
        side = ((outline[i][0], outline[i][1], z0),
                (outline[j][0], outline[j][1], z0),
                (outline[j][0], outline[j][1], z1),
                (outline[i][0], outline[i][1], z1))
        out.append((side, color))
    return out


def _rot_x(p, cy, cz, a):
    c, s = math.cos(a), math.sin(a)
    y, z = p[1] - cy, p[2] - cz
    return (p[0], cy + y * c - z * s, cz + y * s + z * c)


def _rot_z(p, cx, cy, a):
    c, s = math.cos(a), math.sin(a)
    x, y = p[0] - cx, p[1] - cy
    return (cx + x * c - y * s, cy + x * s + y * c, p[2])


def _item_faces(item_id, empty=False, bow_charge=0.0):
    if empty or not item_id:
        return _vm_box(14, -24, 55, 10, 16, 10, (184, 132, 94)) + \
               _vm_box(-2, -29, 55, 8, 13, 10, (174, 122, 86))
    if item_id in ("axe", "pickaxe", "shovel"):
        wood, metal = (124, 82, 46), (176, 182, 190)
        if item_id == "axe":
            # A heavier, more deliberate axe: wrapped grip, eye, poll and a
            # broad curved bit.  It is its own shape, not a rotated icon.
            out = _vm_box(0, -18, 55, 5.0, 58, 5.0, wood)
            for gy in (4, -5, -14):
                out += _vm_box(0, gy, 55, 5.6, 2.0, 5.3, (70, 44, 28))
            out += _vm_box(0, -2, 55, 11, 12, 11, (190, 132, 92))
            out += _vm_box(0, -45, 55, 9, 13, 9, metal)
            # the poll (back of the head)
            out += _vm_box(-8, -45, 55, 7, 10, 7, (146, 152, 160))
            # the bit, extruded as a real blade profile
            blade = [(3, -51), (18, -49), (26, -39), (22, -30),
                     (12, -27), (4, -33)]
            out += _vm_prism(blade, 51.0, 59.0, (194, 200, 208))
            edge = [(21, -39), (26, -39), (22, -30), (18, -31)]
            out += _vm_prism(edge, 50.5, 59.5, (238, 240, 244))
            out += _vm_box(0, -37, 55, 5, 3, 5, (96, 100, 108))
            return out
        out = _vm_box(0, -18, 55, 3.5, 40, 3.5, wood)
        out += _vm_box(0, -2, 55, 9, 10, 9, (190, 132, 92))
        if item_id == "pickaxe":
            out += _vm_box(0, -40, 55, 25, 4, 4, metal)
            out += _vm_box(-11, -38, 55, 4, 8, 4, metal)
            out += _vm_box(11, -38, 55, 4, 8, 4, metal)
        else:
            out += _vm_box(0, -40, 55, 13, 10, 3, metal)
        return out
    if item_id == "bow":
        # A bent wooden bow with a pale string and a wrapped grip.
        limb_r = [(5, -4, 55), (10, -18, 55), (13, -32, 55),
                  (12, -46, 55), (7, -56, 55)]
        limb_l = [(-x, y, z) for (x, y, z) in reversed(limb_r)]
        out = _vm_prism([(x, y) for (x, y, _z) in limb_r], 52.0, 58.0,
                        (112, 74, 42))
        out += _vm_prism([(x, y) for (x, y, _z) in limb_l], 52.0, 58.0,
                         (112, 74, 42))
        out += _vm_box(0, -9, 55, 7, 8, 7, (160, 112, 68))
        out += _vm_box(0, -1, 55, 9, 9, 9, (190, 132, 92))
        out += _vm_box(0, -55, 55, 1, 48, 1.2, (224, 224, 210))
        pull = max(0.0, min(1.0, float(bow_charge) / 1.1))
        if pull > 0.02:
            # The nock and arrow slide back as the string is drawn.
            nx = -7.0 - 15.0 * pull
            out += _vm_box(nx, -30.0, 55, 20, 1.8, 1.8, (156, 106, 60))
            out += _vm_box(nx - 13.0, -30.0, 55, 5, 4.5, 3.0, (226, 228, 232))
            out += _vm_box(nx + 10.0, -30.0, 55, 1.2, 9.0, 1.2, (220, 218, 198))
        return out
    if item_id in ("musket", "rifle", "double_shot", "shotgun"):
        wood, metal = (98, 62, 36), (142, 146, 154)
        if item_id == "musket":
            out = _vm_box(0, -14, 56, 8, 9, 30, wood)
            out += _vm_box(0, -15, 76, 4, 4, 40, metal)
            out += _vm_box(0, -21, 67, 2, 3, 8, metal)
            out += _vm_box(0, -3, 57, 9, 10, 9, (176, 120, 82))
        elif item_id == "double_shot":
            out = _vm_box(0, -14, 56, 10, 9, 26, wood)
            out += _vm_box(-4, -15, 73, 4, 4, 38, metal)
            out += _vm_box(4, -15, 73, 4, 4, 38, metal)
            out += _vm_box(0, -21, 66, 3, 3, 8, metal)
            out += _vm_box(0, -3, 57, 9, 10, 9, (176, 120, 82))
        else:
            out = _vm_box(0, -14, 56, 7, 8, 34, wood)
            out += _vm_box(0, -15, 78, 3.5, 3.5, 48, metal)
            out += _vm_box(0, -22, 70, 2, 3, 9, metal)
            out += _vm_box(0, -4, 57, 8, 9, 9, (176, 120, 82))
        return out
    if item_id in ("bottle", "beer", "liqueur", "mezcal", "steelka",
                   "banana_liqueur", "braggot", "chocolate_stout",
                   "steel_ale", "steelworm", "bananale", "melomel",
                   "cactus_mead"):
        col = (124, 74, 46)
        if item_id in ("liqueur", "banana_liqueur"):
            col = (126, 50, 78)
        return _vm_cyl(0, -16, 56, 7, 22, 8, col) + \
               _vm_box(0, -2, 56, 10, 10, 10, (186, 130, 90))
    # A generic object: still a solid, shaded object in the hand.
    return _vm_box(0, -20, 56, 15, 22, 12, (128, 112, 82)) + \
           _vm_box(0, -2, 56, 9, 10, 9, (190, 132, 92))


_BOW_TEX_CACHE: dict = {}


def _bow_texture(pull: float):
    """A low-resolution side-view bow texture: stick left, string right."""
    key = int(max(0.0, min(1.0, pull)) * 10.0)
    got = _BOW_TEX_CACHE.get(key)
    if got is not None:
        return got
    s = pygame.Surface((64, 96), pygame.SRCALPHA)
    curve = [(33, 5), (22, 15), (15, 28), (12, 48), (15, 68),
             (22, 81), (33, 91)]
    pygame.draw.lines(s, (54, 32, 18), False, curve, 8)
    pygame.draw.lines(s, (128, 83, 43), False, curve, 5)
    pygame.draw.lines(s, (174, 116, 60), False, curve, 2)
    pygame.draw.circle(s, (54, 32, 18), curve[0], 5)
    pygame.draw.circle(s, (54, 32, 18), curve[-1], 5)
    # grip on the stick
    pygame.draw.rect(s, (78, 48, 26), (14, 38, 14, 12))
    pygame.draw.rect(s, (152, 100, 52), (16, 40, 10, 8))
    # string: tip -> nock -> tip, nock pulled right as the bow is charged
    nx = 38 + 9 * pull
    pygame.draw.line(s, (222, 220, 200), (33, 5), (int(nx), 48), 2)
    pygame.draw.line(s, (222, 220, 200), (int(nx), 48), (33, 91), 2)
    # arrow pointing forward/right
    pygame.draw.line(s, (92, 60, 32), (int(nx), 48), (62, 48), 4)
    pygame.draw.line(s, (154, 104, 58), (int(nx), 48), (62, 48), 2)
    pygame.draw.polygon(s, (218, 224, 232), [(62, 48), (54, 43), (54, 53)])
    pygame.draw.line(s, (224, 220, 204), (int(nx), 48), (int(nx) - 6, 44), 2)
    pygame.draw.line(s, (224, 220, 204), (int(nx), 48), (int(nx) - 6, 52), 2)
    # hand at the grip
    pygame.draw.rect(s, (188, 130, 90), (26, 43, 12, 12), border_radius=3)
    pygame.draw.rect(s, (120, 78, 50), (26, 43, 12, 12), 1, border_radius=3)
    _BOW_TEX_CACHE[key] = s
    return s


_BOW_ARROW_PIXELS = None


def _bow_arrow_pixels():
    """A deliberately chunky pixel arrow, not a smooth vector/icon."""
    global _BOW_ARROW_PIXELS
    if _BOW_ARROW_PIXELS is not None:
        return _BOW_ARROW_PIXELS
    s = pygame.Surface((48, 12), pygame.SRCALPHA)
    # shaft
    pygame.draw.rect(s, (104, 68, 36), (7, 5, 33, 3))
    pygame.draw.rect(s, (174, 122, 66), (9, 5, 28, 1))
    # fletching: two feather blocks at the tail
    pygame.draw.rect(s, (238, 236, 222), (1, 2, 10, 3))
    pygame.draw.rect(s, (238, 236, 222), (1, 7, 10, 3))
    pygame.draw.rect(s, (204, 202, 190), (1, 4, 8, 1))
    pygame.draw.rect(s, (204, 202, 190), (1, 7, 8, 1))
    # dark separations keep the fletching readable at low resolution
    pygame.draw.line(s, (110, 72, 42), (8, 2), (8, 4), 1)
    pygame.draw.line(s, (110, 72, 42), (8, 7), (8, 10), 1)
    # chunky metal head
    pygame.draw.polygon(s, (214, 220, 228),
                        [(37, 2), (47, 5), (47, 7), (37, 10)])
    pygame.draw.polygon(s, (244, 246, 248),
                        [(40, 4), (47, 5), (47, 7), (40, 8)], 1)
    _BOW_ARROW_PIXELS = s
    return s


_AXE_TEX = None


def _axe_texture():
    """Low-resolution side-view axe, for a Minecraft-like 3D item plane."""
    global _AXE_TEX
    if _AXE_TEX is not None:
        return _AXE_TEX
    s = pygame.Surface((64, 96), pygame.SRCALPHA)
    wood_d, wood, wood_l = (62, 40, 24), (122, 82, 44), (176, 118, 62)
    steel_d, steel, edge = (78, 84, 92), (168, 176, 186), (236, 240, 244)
    # diagonal handle (bottom-right to top-left)
    pygame.draw.line(s, wood_d, (47, 91), (27, 26), 9)
    pygame.draw.line(s, wood, (47, 91), (27, 26), 6)
    pygame.draw.line(s, wood_l, (45, 88), (30, 36), 2)
    # grip wraps
    for k in range(3):
        yy = 68 + k * 7
        pygame.draw.line(s, (70, 44, 26), (42 - k * 2, yy), (50 - k * 2, yy + 1), 2)
    # chunky eye / poll
    pygame.draw.rect(s, steel_d, (21, 18, 18, 16), border_radius=2)
    pygame.draw.rect(s, steel, (23, 20, 14, 12), border_radius=1)
    # curved blade profile
    blade = [(23, 10), (13, 13), (5, 22), (7, 33), (17, 35),
             (27, 31), (30, 24)]
    pygame.draw.polygon(s, steel_d, blade)
    pygame.draw.polygon(s, steel, [(x + 1, y + 1) for (x, y) in blade])
    pygame.draw.polygon(s, edge, [(17, 14), (8, 22), (10, 31), (17, 32)])
    # dark outline pixels / eye hole
    pygame.draw.polygon(s, (45, 42, 42), [(23, 10), (13, 13), (5, 22),
                                          (7, 33), (17, 35), (27, 31),
                                          (30, 24)], 1)
    pygame.draw.circle(s, (36, 34, 32), (29, 25), 3)
    _AXE_TEX = s
    return s


_AXE_SURF_CACHE: dict = {}


def _homography(src, dst):
    """Map source rectangle corners to destination corners."""
    A = []
    b = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    h = np.linalg.solve(np.asarray(A, np.float64), np.asarray(b, np.float64))
    return np.array([[h[0], h[1], h[2]],
                     [h[3], h[4], h[5]],
                     [h[6], h[7], 1.0]], dtype=np.float64)


def _axe_item_surface(w: int, h: int):
    """A true perspective-mapped pixel axe item surface, cached per size."""
    key = (int(w), int(h))
    got = _AXE_SURF_CACHE.get(key)
    if got is not None:
        return got
    # Only the head and upper half of the handle are on screen at rest.
    full = _axe_texture()
    tex = full.subsurface((0, 0, full.get_width(),
                           max(1, int(full.get_height() * 0.62))))
    tw, th = tex.get_size()
    # Large in the right third, angled forward/away from the camera.
    focal = min(w, h) / (2.0 * math.tan(math.radians(78.0) * 0.5))
    base = (0.70, -0.10, 0.85)
    yaw = 0.50
    ca, sa = math.cos(yaw), math.sin(yaw)

    def proj(lx, ly):
        x, z = lx * ca, -lx * sa
        x += base[0]
        y = base[1] + ly
        z += base[2]
        return (w * 0.5 + focal * x / z,
                h * 0.5 - focal * y / z)

    tl = proj(-0.25, 0.42)
    tr = proj(0.25, 0.42)
    br = proj(0.25, -0.42)
    bl = proj(-0.25, -0.42)
    minx, maxx = int(math.floor(min(q[0] for q in (tl, tr, br, bl)))), \
        int(math.ceil(max(q[0] for q in (tl, tr, br, bl))))
    miny, maxy = int(math.floor(min(q[1] for q in (tl, tr, br, bl)))), \
        int(math.ceil(max(q[1] for q in (tl, tr, br, bl))))
    dw, dh = max(1, maxx - minx + 1), max(1, maxy - miny + 1)
    # inverse homography: destination pixel -> source texture pixel
    H = _homography([(0, 0), (tw, 0), (tw, th), (0, th)],
                    [tl, tr, br, bl])
    Hi = np.linalg.inv(H)
    xs = np.arange(minx, maxx + 1, dtype=np.float64)
    ys = np.arange(miny, maxy + 1, dtype=np.float64)
    X, Y = np.meshgrid(xs, ys)
    den = Hi[2, 0] * X + Hi[2, 1] * Y + Hi[2, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        u = (Hi[0, 0] * X + Hi[0, 1] * Y + Hi[0, 2]) / den
        v = (Hi[1, 0] * X + Hi[1, 1] * Y + Hi[1, 2]) / den
    mask = (den > 1e-9) & (u >= 0) & (u < tw) & (v >= 0) & (v < th)
    arr3 = pygame.surfarray.array3d(tex)
    alpha = pygame.surfarray.array_alpha(tex)
    rgba = np.zeros((tw, th, 4), dtype=np.uint8)
    rgba[..., :3] = arr3
    rgba[..., 3] = alpha
    sx = np.clip(u.astype(np.int32), 0, tw - 1)
    sy = np.clip(v.astype(np.int32), 0, th - 1)
    out = np.zeros((dh, dw, 4), dtype=np.uint8)
    vals = rgba[sx, sy]
    out[mask] = vals[mask]
    # pygame surfarray is x-major
    surf = pygame.Surface((dw, dh), pygame.SRCALPHA)
    surfarr = pygame.surfarray.pixels3d(surf)
    surfa = pygame.surfarray.pixels_alpha(surf)
    surfarr[:] = out[..., :3].swapaxes(0, 1)
    surfa[:] = out[..., 3].swapaxes(0, 1)
    del surfarr, surfa
    _AXE_SURF_CACHE[key] = (surf, minx, miny, swing_pivot(tl, tr, br, bl))
    return _AXE_SURF_CACHE[key]


def swing_pivot(tl, tr, br, bl):
    return (br[0], br[1])


def _draw_axe_viewmodel(g, screen) -> None:
    """Draw a proper perspective-mapped pixel axe; no card, no shadow box."""
    w, h = screen.get_size()
    try:
        surf, ox, oy, pivot = _axe_item_surface(w, h)
    except Exception:
        return
    try:
        swing = float(getattr(g.player, "swing_progress", 0.0) or 0.0)
    except Exception:
        swing = 0.0
    if swing > 0.0:
        # Keep the swing: rotate the cached item about its lower-right grip.
        ang = -0.35 + 1.6 * swing
        piv = (pivot[0] - ox, pivot[1] - oy)
        surf = pygame.transform.rotate(surf, math.degrees(ang))
        # Rotating changes the size; anchor the lower-right grip loosely.
        rect = surf.get_rect()
        rect.bottomright = (int(pivot[0]) + 8, int(pivot[1]) + 14)
        screen.blit(surf, rect)
    else:
        screen.blit(surf, (ox, oy))


def _draw_bow_viewmodel(g, screen) -> None:
    """The approved chunky 3D bow stick, string, and late-spawned arrow."""
    w, h = screen.get_size()
    pull = max(0.0, min(1.0, float(getattr(g, "_v3_bow_charge", 0.0)) / 1.1))
    if pull <= 0.001:
        # The approved rest image: old sparse blocks, one dolly step closer.
        pts = []
        n = 15
        dolly = 0.34          # twice as close to the eyes as before
        for i in range(n):
            t = i / (n - 1.0) * 2.0 - 1.0
            bulge = 1.0 - t * t
            x = 0.48 - 0.19 * bulge
            y = t * 0.52
            z = (1.85 + 0.10 * (t * t)) * dolly
            pts.append((x, y, z))
        legacy = True
        step = 0.035
    else:
        # The approved drawn image: more blocks as the curve stretches,
        # continuous underlay, no per-block gaps.
        def _at(t):
            bulge = 1.0 - t * t
            x = 0.48 - 0.19 * bulge
            y = t * 0.52
            tip_pull = 0.10 - 1.40 * pull
            z = 1.85 + tip_pull * (t * t)
            return (x, y, z)
        dense = [_at(-1.0 + 2.0 * i / 4000.0) for i in range(4001)]
        pts = [dense[0]]
        last = dense[0]
        step = 0.035
        for p in dense[1:]:
            d = math.sqrt((p[0] - last[0]) ** 2 +
                          (p[1] - last[1]) ** 2 +
                          (p[2] - last[2]) ** 2)
            if d >= step:
                pts.append(p)
                last = p
        if pts[-1] != dense[-1]:
            pts.append(dense[-1])
        legacy = False
    fov = math.radians(125.0)
    focal = min(w, h) / (2.0 * math.tan(fov * 0.5))

    def proj(p):
        if p[2] <= 0.01:
            return None
        return (w * 0.5 + focal * p[0] / p[2],
                h * 0.5 - focal * p[1] / p[2])

    pts2 = [proj(p) for p in pts]
    if not legacy and len(pts2) >= 2:
        pygame.draw.lines(screen, (52, 32, 18), False, pts2, 38)
        pygame.draw.lines(screen, (126, 82, 44), False, pts2, 28)
        pygame.draw.lines(screen, (176, 118, 62), False, pts2, 8)

    ops = []
    for i, p in enumerate(pts):
        end_cube = i == 0 or i == len(pts) - 1
        if legacy:
            sx = sy = 0.095 if end_cube else 0.072
            sz = 0.085 if end_cube else 0.065
        else:
            sx = sy = 0.105 if end_cube else 0.085
            sz = 0.095 if end_cube else 0.075
        base = (126, 82, 44) if i % 2 else (142, 94, 50)
        for face in _bow_cube_faces(p[0], p[1], p[2], sx, sy, sz, base):
            n = _norm(_cross(_sub(face[1], face[0]), _sub(face[2], face[0])))
            d = abs(_dot(n, _LIGHT))
            shade = 0.50 + 0.58 * d
            col = tuple(max(0, min(255, int(v * shade))) for v in base)
            poly = [proj(q) for q in face]
            if any(q is None for q in poly):
                continue
            ops.append((sum(q[2] for q in face) / 4.0, poly, col))
    ops.sort(key=lambda op: op[0], reverse=True)
    for _z, poly, col in ops:
        pygame.draw.polygon(screen, col, poly)
        if legacy:
            pygame.draw.polygon(screen, (42, 28, 16), poly, 1)

    # THE STRING: connects the top and bottom tips of the stick and stays
    # visible in both states.  Draw it over the wood.
    if pts2 and pts2[0] is not None and pts2[-1] is not None:
        t2, b2 = pts2[0], pts2[-1]
        pygame.draw.line(screen, (42, 32, 22),
                         (int(t2[0]), int(t2[1])),
                         (int(b2[0]), int(b2[1])), 4)
        pygame.draw.line(screen, (236, 232, 214),
                         (int(t2[0]), int(t2[1])),
                         (int(b2[0]), int(b2[1])), 2)

    # THE ARROW: only once the draw is nearly finished.  Feathers sit at the
    # middle of the string; the head sits at the middle of the stick.
    if not legacy and pull >= 0.78 and len(pts) >= 3:
        top = pts[0]
        bot = pts[-1]
        smid = ((top[0] + bot[0]) * 0.5,
                (top[1] + bot[1]) * 0.5,
                (top[2] + bot[2]) * 0.5)
        bowmid = pts[len(pts) // 2]
        a = proj(smid)
        b = proj(bowmid)
        if a is not None and b is not None:
            ax, ay = a
            bx, by = b
            dx, dy = bx - ax, by - ay
            length = max(28, int(math.hypot(dx, dy)))
            ang = math.degrees(math.atan2(dy, dx))
            img = _bow_arrow_pixels()
            img = pygame.transform.scale(img, (length, max(8, length // 4)))
            img = pygame.transform.rotate(img, -ang)
            rect = img.get_rect(center=(int((ax + bx) * 0.5),
                                       int((ay + by) * 0.5)))
            screen.blit(img, rect)


def draw_viewmodel(g, screen) -> None:
    stack = None
    try:
        stack = g.inventory.selected_stack()
    except Exception:
        pass
    item_id = stack.defn.id if stack is not None else ""
    if item_id == "bow":
        _draw_bow_viewmodel(g, screen)
        return
    if item_id == "axe":
        _draw_axe_viewmodel(g, screen)
        return
    faces = _item_faces(item_id, empty=stack is None,
                         bow_charge=float(getattr(g, "_v3_bow_charge", 0.0)))
    p = g.player
    try:
        swing = float(getattr(p, "swing_progress", 0.0) or 0.0)
    except Exception:
        swing = 0.0
    moving = bool(getattr(p, "moving", False))
    now = pygame.time.get_ticks() / 1000.0
    bobx = math.sin(now * 8.0) * (2.5 if moving else 0.8)
    boby = abs(math.cos(now * 8.0)) * (3.0 if moving else 1.0)
    try:
        boby += float(getattr(g, "v3d_pitch", 0.0)) * 15.0
    except Exception:
        pass
    ang = (-0.38 + 1.75 * swing) if swing > 0.0 else 0.0
    if item_id in ("musket", "rifle", "double_shot", "shotgun", "bow"):
        try:
            if float(getattr(p, "gun_cd", 0.0)) > 0.0:
                boby += 4.0
        except Exception:
            pass
    piv_y, piv_z = -14.0, 55.0
    transformed = []
    for pts, color in faces:
        q = []
        for (x, y, z) in pts:
            y += boby
            x += bobx
            if ang:
                y, z = (piv_y + (y - piv_y) * math.cos(ang)
                        - (z - piv_z) * math.sin(ang),
                        piv_z + (y - piv_y) * math.sin(ang)
                        + (z - piv_z) * math.cos(ang))
            q.append((x, y, z))
        transformed.append((q, color))
    w, h = screen.get_size()
    # A readable first-person model: local 3D coordinates, large in the
    # lower-right, with the same flat-shaded lighting as the world.  This is
    # not a perspective camera of its own; it is a presentation space whose
    # only job is to keep the object in frame and in the hand.
    scale = min(w, h) / 180.0
    if item_id in ("axe", "pickaxe", "shovel"):
        scale *= 1.30
    cx = w * 0.72
    cy = h * 0.80
    ops = []
    for pts, color in transformed:
        n = _norm(_cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0])))
        d = abs(_dot(n, _LIGHT))
        f = 0.48 + 0.64 * d
        c = tuple(max(0, min(255, int(v * f))) for v in color[:3])
        ca = sa = 0.0
        if item_id == "axe":
            ca, sa = math.cos(-0.34), math.sin(-0.34)
        proj = []
        for (x, y, _z) in pts:
            if item_id == "axe":
                # Minecraft holds the axe across the body with the head to
                # the left of the grip; mirror the model so ours reads the
                # same way instead of sticking its blade out to the right.
                x = -x
            if ca or sa:
                qx = x * ca - y * sa
                qy = x * sa + y * ca
            else:
                qx, qy = x, y
            proj.append((cx + qx * scale, cy + (qy + 20.0) * scale))
        z = sum(v[2] for v in pts) / len(pts)
        ops.append((z, proj, c))
    ops.sort(key=lambda op: op[0], reverse=True)
    for _z, pts, color in ops:
        pygame.draw.polygon(screen, color, pts)
        if _z > 53:                         # a faint rim on the closest faces
            pygame.draw.polygon(screen, (34, 28, 22), pts, 1)
    if item_id in ("musket", "double_shot", "rifle", "shotgun"):
        try:
            if float(getattr(p, "gun_cd", 0.0)) > 0.0:
                mx, my = int(cx - 12), int(cy - 42 + boby)
                for rr, col in ((26, (255, 196, 60)), (16, (255, 238, 150)),
                                (7, (255, 255, 236))):
                    pygame.draw.circle(screen, col, (mx, my), int(rr * 0.7))
                pygame.draw.line(screen, (255, 244, 190),
                                 (mx - 25, my), (mx + 25, my), 3)
        except Exception:
            pass
