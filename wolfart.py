"""wolfart.py -- a proper wolf, drawn in eight directions.

The old wolf was three circles and a line.  This module builds a small,
anti-aliased sprite frame from a 3-D-ish wolf skeleton: torso, neck, head,
ears, four legs and a brush tail.  The same skeleton is projected from eight
45-degree views, with a gait cycle driven by how far the animal has moved.

Frames are cached.  Drawing a wolf is then one blit, not a pile of polygons
per frame.
"""

from __future__ import annotations

import math

import pygame


# Screen-space facing for the eight 45-degree directions.  World y points
# down, so 0 is east and 1 is south-east.
DIRS = (
    (1.0, 0.0),
    (0.70710678, 0.70710678),
    (0.0, 1.0),
    (-0.70710678, 0.70710678),
    (-1.0, 0.0),
    (-0.70710678, -0.70710678),
    (0.0, -1.0),
    (0.70710678, -0.70710678),
)

SS = 3                    # supersampling for soft edges
FW, FH = 88, 64           # final frame size
AX, AY = 44, 38           # anchor inside the frame

PALETTES = {
    "wolf": {
        "coat": (96, 96, 104), "coat2": (122, 120, 126),
        "back": (53, 56, 64), "belly": (198, 194, 184),
        "leg": (70, 70, 78), "paw": (43, 43, 49),
        "ear": (78, 78, 86), "inner": (146, 112, 104),
        "eye": (224, 178, 58), "nose": (27, 25, 28),
        "mouth": (126, 54, 54), "tooth": (238, 232, 212),
        "spot": (68, 68, 76),
    },
    "white_wolf": {
        "coat": (220, 224, 230), "coat2": (240, 242, 246),
        "back": (146, 154, 168), "belly": (250, 250, 248),
        "leg": (176, 182, 192), "paw": (126, 134, 148),
        "ear": (190, 196, 208), "inner": (206, 162, 158),
        "eye": (112, 168, 196), "nose": (53, 56, 64),
        "mouth": (146, 72, 76), "tooth": (255, 250, 236),
        "spot": (182, 188, 198),
    },
    "hyena": {
        "coat": (154, 126, 86), "coat2": (186, 158, 112),
        "back": (86, 64, 42), "belly": (218, 198, 158),
        "leg": (104, 82, 54), "paw": (66, 50, 34),
        "ear": (112, 88, 60), "inner": (158, 112, 94),
        "eye": (48, 34, 18), "nose": (35, 28, 20),
        "mouth": (128, 58, 60), "tooth": (246, 238, 218),
        "spot": (84, 66, 48),
    },
}


class _Painter:
    def __init__(self, surf, fx, fy, zoom, frame, palette, hit=False, lunge=False):
        self.s = surf
        self.fx, self.fy = fx, fy
        self.px, self.py = -fy, fx
        self.zoom = zoom
        self.phase = frame * (2.0 * math.pi / 8.0)
        self.c = palette
        self.hit = hit
        self.lunge = lunge
        # A side-on wolf is long; a head-on one is foreshortened and broad.
        self.su = 0.46 + 0.54 * abs(fx)
        self.sv = 0.64 + 0.36 * abs(fy)
        # The near side is the side toward the camera (the lower screen side).
        self.near = 1.0

    def col(self, key):
        if self.hit:
            # Keep the dark shape language readable while the wolf flashes:
            # a flat white blob hid the legs, muzzle and ears completely.
            if key in ("back", "paw", "nose", "mouth", "spot"):
                return (126, 124, 120)
            if key == "eye":
                return (96, 76, 30)
            return (246, 244, 238)
        return self.c[key]

    def p(self, u, v, z):
        x = u * self.fx * self.su + v * self.px * self.sv
        y = u * self.fy * self.su + v * self.py * self.sv - z
        return (int(round((AX + x * self.zoom) * SS)),
                int(round((AY + y * self.zoom) * SS)))

    def w(self, width):
        return max(1, int(round(width * self.zoom * SS)))

    def poly(self, pts, color, outline=None, ow=1.0):
        if len(pts) < 3:
            return
        pygame.draw.polygon(self.s, color, pts)
        if outline is not None:
            pygame.draw.polygon(self.s, outline, pts, self.w(ow))

    def line(self, a, b, color, width):
        pygame.draw.line(self.s, color, a, b, self.w(width))

    def dot(self, u, v, z, r, color):
        cx, cy = self.p(u, v, z)
        rr = max(1, int(round(r * self.zoom * SS)))
        pygame.draw.circle(self.s, color, (cx, cy), rr)

    def oval(self, u, v, z, ru, rv, color, outline=None):
        pts = []
        for i in range(18):
            t = i * (2.0 * math.pi / 18.0)
            pts.append(self.p(u + math.cos(t) * ru,
                              v + math.sin(t) * rv, z))
        self.poly(pts, color, outline)

    def fur(self, u0, v0, u1, v1, z0, z1, color, width=1.0):
        self.line(self.p(u0, v0, z0), self.p(u1, v1, z1), color, width)

    # -- body ---------------------------------------------------------------
    def body_rings(self):
        # (u, half-width, top z, bottom z)
        rings = [
            (-18.0, 3.0, 4.8, 0.0),
            (-16.0, 7.2, 7.2, -0.8),
            (-11.0, 9.0, 8.6, -1.2),
            (-3.0, 8.7, 9.2, -1.2),
            (5.0, 9.0, 10.1, -0.7),
            (11.0, 6.0, 11.2, 0.8),
        ]
        if self.lunge:
            rings = [(u * 1.10, w, zt, zb) for (u, w, zt, zb) in rings]
        return rings

    def draw_tail(self):
        # A brush tail: several overlapping tapered masses, curving with the
        # gait.  It is drawn behind the body, so the body hides its root.
        sway = math.sin(self.phase * 0.55) * 4.0
        lift = math.cos(self.phase * 0.55) * 1.5
        base = (-16.0, 0.0, 7.0)
        pts = []
        for i in range(9):
            t = i / 8.0
            u = -16.0 - 16.0 * t
            v = sway * (t ** 1.4)
            z = 7.0 - 6.0 * t + lift * t
            pts.append((u, v, z))
        for i in range(len(pts) - 1):
            u0, v0, z0 = pts[i]
            u1, v1, z1 = pts[i + 1]
            r = 2.2 + 3.8 * math.sin(math.pi * (i / 8.0))
            self.oval((u0 + u1) * 0.5, (v0 + v1) * 0.5,
                      (z0 + z1) * 0.5, r, r * 0.72,
                      self.col("coat2"))
        # dark tip
        u, v, z = pts[-1]
        self.oval(u, v, z, 3.2, 2.2, self.col("back"))

    def legs(self):
        # hip u, side v, phase offset, thickness
        legs = [
            (-12.0, -5.2, 0.0, 2.1),
            (-12.0, 5.2, math.pi, 2.1),
            (7.0, -4.8, math.pi, 2.2),
            (7.0, 4.8, 0.0, 2.2),
        ]
        for (hu, hv, off, thick) in legs:
            swing = math.sin(self.phase + off) * 3.2
            lift = max(0.0, math.cos(self.phase + off)) * 2.2
            if self.lunge and hu > 0.0:
                swing = 5.0
                lift = 0.4
            hip = self.p(hu, hv, 1.0)
            knee = self.p(hu + swing * 0.55, hv, -3.2 + lift * 0.45)
            paw = self.p(hu + swing, hv, -7.0 + lift)
            # upper leg is a little thicker; lower leg tapers to the paw
            self.line(hip, knee, self.col("leg"), thick)
            self.line(knee, paw, self.col("leg"), max(1.0, thick * 0.72))
            self.oval(hu + swing, hv, -7.1 + lift, 2.0, 1.15,
                      self.col("paw"))

    def body(self):
        rings = self.body_rings()
        top_l = [self.p(u, -w, zt) for (u, w, zt, zb) in rings]
        top_r = [self.p(u, w, zt) for (u, w, zt, zb) in rings]
        bot_r = [self.p(u, w, zb) for (u, w, zt, zb) in rings]
        bot_l = [self.p(u, -w, zb) for (u, w, zt, zb) in rings]
        outline = top_l + top_r[::-1] + bot_r + bot_l[::-1]
        self.poly(outline, self.col("coat"), self.col("back"), 1.2)
        # back band
        self.poly(top_l + top_r[::-1], self.col("back"))
        # belly band
        self.poly(bot_l + bot_r[::-1], self.col("belly"))
        # shoulder and haunch masses
        self.oval(6.0, 0.0, 5.0, 6.5, 7.4, self.col("coat2"))
        self.oval(-12.0, 0.0, 4.2, 5.8, 7.0, self.col("coat2"))
        # chest ruff, a few pointed tufts
        for v in (-4.0, -1.5, 1.5, 4.0):
            self.poly([self.p(10.0, v - 1.2, 3.5),
                       self.p(13.2, v, 1.8),
                       self.p(10.0, v + 1.2, 3.5)],
                      self.col("belly"))
        # fur strokes
        for i in range(5):
            u = -13.0 + i * 4.1
            z = 7.8 - abs(u + 3.0) * 0.10
            self.fur(u, -6.0, u - 2.0, -3.4, z, z - 1.0,
                     self.col("back"), 1.0)
        if self.c is PALETTES["hyena"]:
            for (u, v, z) in ((-11, -2, 7), (-7, 3, 8), (-2, -4, 8),
                              (2, 2, 8), (6, -2, 7), (-14, 3, 6)):
                self.dot(u, v, z, 1.25, self.col("spot"))

    # -- neck and head ------------------------------------------------------
    def head(self):
        front = self.fy > 0.18
        back = self.fy < -0.18
        # neck rises from the shoulders to the skull
        self.poly([self.p(8.0, -5.5, 8.0), self.p(8.0, 5.5, 8.0),
                   self.p(17.0, 4.2, 12.0), self.p(17.0, -4.2, 12.0)],
                  self.col("coat"), self.col("back"), 1.0)
        # ears first so the skull overlaps their bases
        ear_shift = math.sin(self.phase * 1.3) * 0.35
        if self.lunge:
            ear_shift += 1.5
        for side in (-1.0, 1.0):
            base_a = self.p(17.0 + ear_shift, side * 4.6, 14.0)
            base_b = self.p(19.8 + ear_shift, side * 5.6, 13.8)
            tip = self.p(18.0 + ear_shift, side * 5.4, 20.0)
            self.poly([base_a, base_b, tip], self.col("ear"),
                      self.col("back"), 1.0)
            inner = self.p(18.4 + ear_shift, side * 5.1, 15.1)
            self.poly([base_a, base_b, inner], self.col("inner"))
        # skull
        self.oval(20.0, 0.0, 11.0, 6.2, 5.2,
                  self.col("coat"), self.col("back"))
        self.oval(18.2, 0.0, 12.0, 3.2, 3.6, self.col("coat2"))
        if not back:
            # muzzle, lower jaw and nose
            muzzle_z = 9.3
            self.poly([self.p(23.0, -3.4, 10.3),
                       self.p(29.0, -2.0, 8.0),
                       self.p(30.2, 0.0, 8.0),
                       self.p(29.0, 2.0, 8.0),
                       self.p(23.0, 3.4, 10.3)],
                      self.col("coat2"), self.col("back"), 1.0)
            if self.lunge:
                # open jaws: lower jaw drops, teeth show
                self.poly([self.p(23.0, -3.2, 9.0),
                           self.p(29.0, -2.0, 6.8),
                           self.p(28.2, 2.0, 6.2),
                           self.p(23.0, 3.2, 9.0)],
                          self.col("mouth"), self.col("back"), 1.0)
                for t in (24.8, 26.4, 28.0):
                    self.poly([self.p(t, -1.9, 9.2),
                               self.p(t + 0.5, -0.5, 8.1),
                               self.p(t + 0.6, 0.6, 8.1)], self.col("tooth"))
                    self.poly([self.p(t, 1.9, 9.2),
                               self.p(t + 0.5, 0.5, 8.1),
                               self.p(t + 0.6, -0.6, 8.1)], self.col("tooth"))
            else:
                self.line(self.p(27.6, 0.0, 8.2),
                          self.p(24.0, 0.0, 8.9),
                          self.col("mouth"), 0.9)
            self.dot(30.2, 0.0, 8.2, 1.6, self.col("nose"))
            # eyes: both on a face-on view, one on a profile
            if front:
                eyes = (-3.3, 3.3)
            elif back:
                eyes = ()
            else:
                eyes = ((3.2,) if self.fx >= 0.0 else (-3.2,))
            for v in eyes:
                self.oval(23.2, v, 12.0, 1.55, 1.45,
                          self.col("eye"), self.col("back"))
                self.dot(23.7, v, 12.0, 0.72, (20, 16, 14))
                self.dot(23.1, v - 0.4, 12.3, 0.42, (250, 246, 228))
        else:
            # from behind: ears and the dark nape, no face
            self.oval(18.5, 0.0, 12.0, 4.2, 4.4, self.col("coat2"))
            self.line(self.p(18.0, -3.0, 13.0), self.p(18.0, 3.0, 13.0),
                      self.col("back"), 1.0)

    def details(self):
        # A tiny warm glint along the back and a few guard hairs.
        for i in range(4):
            u = -9.0 + i * 4.2
            self.fur(u, -4.0, u + 1.8, -2.0, 8.0, 7.4,
                     self.col("coat2"), 0.8)

    def render(self):
        self.draw_tail()
        self.legs()
        self.body()
        self.head()
        self.details()


_cache: dict = {}


def _palette(species: str):
    return PALETTES.get(species, PALETTES["wolf"])


def frame(species: str, direction: int, step: int, zoom: float,
          hit: bool = False, lunge: bool = False):
    key = (species, direction, step, round(zoom, 2), bool(hit), bool(lunge))
    got = _cache.get(key)
    if got is not None:
        return got
    fx, fy = DIRS[direction % 8]
    big = pygame.Surface((FW * SS, FH * SS), pygame.SRCALPHA)
    _Painter(big, fx, fy, zoom, step, _palette(species), hit, lunge).render()
    small = pygame.transform.smoothscale(big, (FW, FH))
    _cache[key] = small
    return small


_shadows: dict = {}


def shadow(zoom: float = 1.0):
    key = round(zoom, 2)
    got = _shadows.get(key)
    if got is not None:
        return got
    w, h = int(36 * zoom), int(13 * zoom)
    s = pygame.Surface((max(2, w), max(2, h)), pygame.SRCALPHA)
    for i, a in ((0, 40), (1, 34), (2, 24)):
        rr = (w - i * 5, h - i * 2)
        if rr[0] <= 0 or rr[1] <= 0:
            continue
        pygame.draw.ellipse(s, (12, 10, 8, a),
                            ((w - rr[0]) // 2, (h - rr[1]) // 2,
                             rr[0], rr[1]))
    _shadows[key] = s
    return s
