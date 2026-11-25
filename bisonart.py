"""bisonart.py -- a shaggy buffalo in eight 45-degree views.

The old bison was a stack of circles.  This one has the heavy shoulder hump,
low head, short powerful legs, curved horns, beard, tail tuft and a coat
broken into shaggy locks.  It walks with a distance-driven gait and is cached
as anti-aliased frames.
"""

from __future__ import annotations

import math

import pygame


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

SS = 3
FW, FH = 108, 88
AX, AY = 54, 58

PALETTE = {
    "coat": (92, 62, 40), "coat2": (116, 80, 50),
    "dark": (50, 34, 24), "belly": (134, 98, 62),
    "shag": (66, 44, 30), "hump": (128, 88, 54),
    "horn": (218, 200, 166), "horn_d": (150, 128, 96),
    "hoof": (34, 26, 20), "eye": (12, 9, 7),
    "nose": (28, 20, 16), "beard": (58, 40, 28),
    "dust": (154, 126, 88),
}


class _P:
    def __init__(self, surf, fx, fy, zoom, step, hit=False,
                 charge=False, baby=False):
        self.s = surf
        self.fx, self.fy = fx, fy
        self.px, self.py = -fy, fx
        self.zoom = zoom
        self.phase = step * (2.0 * math.pi / 8.0)
        self.hit = hit
        self.charge = charge
        self.baby = baby
        self.su = 0.45 + 0.55 * abs(fx)
        self.sv = 0.70 + 0.30 * abs(fy)
        self.bob = math.sin(self.phase * 2.0) * 0.42
        self.front = fy > 0.18
        self.back = fy < -0.18

    def col(self, key):
        if self.hit:
            if key in ("dark", "hoof", "eye", "nose", "shag", "beard"):
                return (118, 112, 104)
            if key in ("horn", "horn_d"):
                return (236, 228, 206)
            return (248, 244, 236)
        return PALETTE[key]

    def p(self, u, v, z):
        x = u * self.fx * self.su + v * self.px * self.sv
        y = u * self.fy * self.su + v * self.py * self.sv - (z + self.bob)
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
        pygame.draw.circle(self.s, color, (cx, cy),
                           max(1, int(round(r * self.zoom * SS))))

    def oval(self, u, v, z, ru, rv, color, outline=None):
        pts = []
        for i in range(20):
            t = i * (2.0 * math.pi / 20.0)
            pts.append(self.p(u + math.cos(t) * ru,
                              v + math.sin(t) * rv, z))
        self.poly(pts, color, outline)

    def tuft(self, a, b, tip, color):
        self.poly([self.p(*a), self.p(*b), self.p(*tip)], color)

    def stroke(self, u0, v0, u1, v1, z0, z1, color, width=0.7):
        self.line(self.p(u0, v0, z0), self.p(u1, v1, z1), color, width)

    def tail(self):
        sway = math.sin(self.phase * 0.7) * 2.4
        # thin tail, then a dark tuft
        pts = []
        for i in range(7):
            t = i / 6.0
            pts.append((-22.0 - t * 9.0, sway * t, 17.0 - t * 17.0))
        for i in range(len(pts) - 1):
            self.line(self.p(*pts[i]), self.p(*pts[i + 1]),
                      self.col("dark"), 1.6)
        u, v, z = pts[-1]
        for side in (-1.0, 1.0):
            self.tuft((u + 0.8, side * 1.6, z + 1.4),
                      (u - 1.0, side * 1.8, z),
                      (u - 2.0, side * 2.8, z - 3.4), self.col("shag"))
        self.oval(u - 1.0, v, z - 2.2, 2.6, 2.3, self.col("beard"))

    def legs(self):
        legs = ((-12.0, -5.6, 0.0, 3.3, True),
                (-12.0, 5.6, math.pi, 3.3, True),
                (10.0, -5.2, math.pi, 3.0, False),
                (10.0, 5.2, 0.0, 3.0, False))
        for (hu, hv, off, thick, hind) in legs:
            sw = math.sin(self.phase + off) * (2.8 if hind else 2.4)
            lift = max(0.0, math.cos(self.phase + off)) * 1.2
            if self.charge:
                sw = 3.4 if hind else 2.8
            hip = self.p(hu, hv, 10.0)
            knee = self.p(hu + sw * 0.35, hv, 2.0 + lift * 0.3)
            hoof = self.p(hu + sw, hv, -9.5 + lift)
            self.line(hip, knee, self.col("coat"), thick)
            self.line(knee, hoof, self.col("shag"), max(1.8, thick * 0.65))
            self.oval(hu + sw, hv, -9.6 + lift, 2.4, 1.35, self.col("hoof"))
            if hind:
                self.oval(hu, hv, 7.5, 5.4, 4.6, self.col("coat2"))

    def body(self):
        # barrel, low rump and the enormous shoulder hump
        self.oval(-3.0, 0.0, 13.0, 17.0, 9.0, self.col("coat"),
                  self.col("dark"))
        self.oval(-14.0, 0.0, 12.0, 7.6, 8.0, self.col("coat2"))
        self.oval(7.0, 0.0, 21.0, 9.5, 8.0, self.col("hump"))
        self.oval(0.0, 0.0, 8.0, 13.0, 6.2, self.col("belly"))
        # shaggy shoulder mantle
        for i, (u, w, z) in enumerate(((2, 7.0, 26.0), (7, 7.2, 29.0),
                                        (12, 6.0, 27.0), (-2, 6.8, 23.0))):
            self.tuft((u - 1.3, -w * 0.30, z),
                      (u + 1.3, w * 0.30, z),
                      (u - 1.6, 0.0, z + 1.5 + (i % 2) * 0.7),
                      self.col("shag" if i % 2 else "dark"))
        for u, side in ((-16, -1), (-11, 1), (0, -1), (8, 1), (13, -1)):
            self.tuft((u + 0.8, side * 7.5, 15.0),
                      (u - 1.0, side * 8.2, 13.6),
                      (u - 2.8, side * 9.2, 11.0), self.col("shag"))
        # belly fringe
        for u in (-12, -6, 0, 6):
            self.tuft((u - 1.0, -4.0, 5.0), (u + 1.0, 4.0, 5.0),
                      (u - 0.8, 0.0, 3.0), self.col("coat2"))

    def head(self):
        lowered = 2.8 if self.charge else 0.0
        # low neck, broad skull
        self.poly([self.p(8.0, -5.5, 17.0), self.p(8.0, 5.5, 17.0),
                   self.p(20.0, 4.4, 12.5 - lowered),
                   self.p(20.0, -4.4, 12.5 - lowered)],
                  self.col("coat"), self.col("dark"), 1.0)
        # shaggy neck/beard
        for side in (-1.0, 1.0):
            for j, (u, z, ln) in enumerate(((9, 17, 2.6), (13, 15, 3.2),
                                             (17, 13.5, 2.8))):
                self.tuft((u, side * 4.5, z), (u + 1.0, side * 5.2, z),
                          (u - 1.3, side * 6.4, z - ln),
                          self.col("beard" if j % 2 else "shag"))
        # head and muzzle
        hz = 11.0 - lowered
        self.oval(22.0, 0.0, hz, 6.5, 4.8, self.col("coat"),
                  self.col("dark"))
        self.oval(26.5, 0.0, hz - 2.4, 4.2, 3.2, self.col("coat2"))
        self.oval(29.5, 0.0, hz - 3.0, 1.5, 1.2, self.col("nose"))
        self.line(self.p(29.0, 0.0, hz - 3.5),
                  self.p(24.0, 0.0, hz - 2.8), self.col("dark"), 0.6)
        # beard under the jaw
        for u, side in ((23, -2.2), (25, 0.0), (23, 2.2)):
            self.tuft((u, side, hz - 3.0), (u - 1.6, side, hz - 4.4),
                      (u - 3.2, side * 1.2, hz - 8.0), self.col("beard"))
        # ears, small and low
        for side in (-1.0, 1.0):
            self.tuft((20.0, side * 4.0, hz + 2.2),
                      (22.0, side * 4.8, hz + 1.8),
                      (21.0, side * 5.4, hz + 5.0), self.col("coat2"))
        # horns: sweeping out, forward and down
        if not self.baby:
            for side in (-1.0, 1.0):
                pts = ((21.0, side * 4.0, hz + 4.2),
                       (22.5, side * 6.5, hz + 5.5),
                       (24.8, side * 8.0, hz + 4.8),
                       (26.0, side * 7.2, hz + 2.8))
                for j in range(len(pts) - 1):
                    a = self.p(*pts[j])
                    b = self.p(*pts[j + 1])
                    self.line(a, b, self.col("horn_d"), 3.2 - j * 0.45)
                    self.line(a, b, self.col("horn"), 1.25 - j * 0.18)
                self.dot(pts[-1][0], pts[-1][1], pts[-1][2],
                         0.9, self.col("horn_d"))
        else:
            for side in (-1.0, 1.0):
                self.tuft((21.2, side * 3.8, hz + 2.8),
                          (22.2, side * 4.1, hz + 2.6),
                          (21.5, side * 4.6, hz + 4.4), self.col("horn_d"))
        if not self.back:
            # eyes: both from the front, one in profile
            if self.front:
                eyes = (-2.8, 2.8)
            else:
                eyes = ((2.8,) if self.fx >= 0.0 else (-2.8,))
            for v in eyes:
                self.oval(24.0, v, hz + 1.1, 1.15, 1.0,
                          (28, 18, 14), (15, 10, 8))
                self.oval(24.0, v, hz + 1.1, 0.68, 0.62, self.col("eye"))
                self.dot(24.2, v, hz + 1.1, 0.18, (2, 2, 2))
                self.dot(23.7, v - 0.22, hz + 1.4, 0.18, (240, 232, 210))
            # nostrils
            self.dot(29.1, -0.65, hz - 3.0, 0.23, self.col("nose"))
            self.dot(29.1, 0.65, hz - 3.0, 0.23, self.col("nose"))
            # mouth line
            self.line(self.p(29.0, 0.0, hz - 4.0),
                      self.p(26.0, 0.0, hz - 4.4), self.col("dark"), 0.55)
        else:
            # rear view: rump, tail and horns
            self.oval(22.0, 0.0, hz, 5.2, 4.0, self.col("coat2"))
            self.line(self.p(21.0, -3.5, hz + 2.0),
                      self.p(21.0, 3.5, hz + 2.0), self.col("dark"), 0.8)

    def details(self):
        # dust and loose hair along the hump
        for i in range(5):
            self.stroke(0.0 + i * 3.0, -5.0, 1.0 + i * 3.0, -3.0,
                        24.0 - i * 0.8, 23.0 - i * 0.8,
                        self.col("coat2"), 0.5)
        if self.charge:
            # a little dust at the hooves
            for side in (-1.0, 1.0):
                self.dot(-8.0 + side * 5.0, side * 3.0, -8.0, 1.4,
                         self.col("dust"))

    def render(self):
        self.tail()
        self.legs()
        self.body()
        self.head()
        self.details()


_cache: dict = {}


def frame(direction: int, step: int, zoom: float, hit: bool = False,
          charge: bool = False, baby: bool = False):
    key = (direction, step, round(zoom, 2), bool(hit), bool(charge), bool(baby))
    got = _cache.get(key)
    if got is not None:
        return got
    fx, fy = DIRS[direction % 8]
    big = pygame.Surface((FW * SS, FH * SS), pygame.SRCALPHA)
    _P(big, fx, fy, zoom, step, hit, charge, baby).render()
    small = pygame.transform.smoothscale(big, (FW, FH))
    _cache[key] = small
    return small


_shadows: dict = {}


def shadow(zoom: float = 1.0):
    key = round(zoom, 2)
    got = _shadows.get(key)
    if got is not None:
        return got
    w, h = max(2, int(54 * zoom)), max(2, int(20 * zoom))
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for i, a in ((0, 42), (1, 34), (2, 22)):
        rr = (w - i * 8, h - i * 3)
        if rr[0] <= 0 or rr[1] <= 0:
            continue
        pygame.draw.ellipse(s, (12, 10, 8, a),
                            ((w - rr[0]) // 2, (h - rr[1]) // 2,
                             rr[0], rr[1]))
    _shadows[key] = s
    return s
