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
    "coat": (108, 72, 46), "coat2": (144, 100, 62),
    "dark": (56, 37, 25), "belly": (166, 122, 78),
    "shag": (80, 52, 34), "hump": (154, 105, 64),
    "horn": (224, 208, 176), "horn_d": (156, 132, 98),
    "hoof": (36, 27, 21), "eye": (12, 9, 7),
    "nose": (30, 21, 17), "beard": (65, 43, 30),
    "dust": (172, 142, 98),
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
        legs = ((-12.0, -6.0, 0.0, 3.8, True),
                (-12.0, 6.0, math.pi, 3.8, True),
                (9.0, -5.6, math.pi, 3.5, False),
                (9.0, 5.6, 0.0, 3.5, False))
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
            self.oval(hu + sw, hv, -9.6 + lift, 2.8, 1.55, self.col("hoof"))
            if hind:
                self.oval(hu, hv, 7.5, 5.4, 4.6, self.col("coat2"))

    def body(self):
        # A buffalo is a round barrel with a mountain of shoulder on top.
        # Keep the mass broad and the edge broken by long hanging fur.
        self.oval(-2.0, 0.0, 15.0, 16.5, 13.0, self.col("coat"),
                  self.col("dark"))
        self.oval(-14.0, 0.0, 14.0, 8.8, 10.8, self.col("coat2"))
        self.oval(7.0, 0.0, 23.0, 10.0, 11.5, self.col("hump"))
        self.oval(0.0, 0.0, 9.0, 14.0, 8.8, self.col("belly"))
        self.oval(10.5, 0.0, 14.0, 7.2, 9.0, self.col("coat2"))
        # long skirt of hair under the barrel
        for u in range(-18, 15, 2):
            self.tuft((u - 1.0, -6.0, 5.7),
                      (u + 1.0, 6.0, 5.7),
                      (u - 0.7, 0.0, -0.3 - (u % 3) * 0.28),
                      self.col("shag" if (u // 2) % 2 else "beard"))
        # shaggy shoulder mantle
        for i, (u, w, z) in enumerate(((1, 8.0, 27.0), (6, 8.5, 30.0),
                                        (11, 7.2, 28.5), (-3, 7.6, 25.0))):
            self.tuft((u - 1.6, -w * 0.32, z),
                      (u + 1.6, w * 0.32, z),
                      (u - 1.8, 0.0, z + 1.8 + (i % 2) * 0.8),
                      self.col("shag" if i % 2 else "dark"))
        for u, side in ((-17, -1), (-13, 1), (-7, -1), (0, 1),
                        (7, -1), (13, 1)):
            self.tuft((u + 0.8, side * 8.0, 15.0),
                      (u - 1.2, side * 9.0, 13.0),
                      (u - 2.8, side * 10.0, 10.5), self.col("shag"))
        # loose fur strokes over the flank
        for i in range(8):
            u = -15.0 + i * 3.8
            self.stroke(u, -7.0, u - 2.0, -4.5,
                        16.0 - abs(u + 3.0) * 0.12,
                        15.0 - abs(u + 3.0) * 0.12,
                        self.col("coat2" if i % 2 else "shag"), 0.55)

    def head(self):
        lowered = 1.6 if self.charge else 0.0
        # low, broad neck flowing into the shoulder mountain
        self.poly([self.p(7.0, -6.0, 18.0), self.p(7.0, 6.0, 18.0),
                   self.p(20.0, 5.0, 14.0 - lowered),
                   self.p(20.0, -5.0, 14.0 - lowered)],
                  self.col("coat"), self.col("dark"), 1.0)
        # shaggy neck and beard
        for side in (-1.0, 1.0):
            for j, (u, z, ln) in enumerate(((8, 19, 3.0), (12, 17, 3.5),
                                             (16, 15, 3.0), (19, 13, 2.0))):
                self.tuft((u, side * 4.8, z), (u + 1.2, side * 5.6, z),
                          (u - 1.8, side * 7.0, z - ln),
                          self.col("beard" if j % 2 else "shag"))
        # head and long muzzle
        hz = 12.5 - lowered
        self.oval(21.5, 0.0, hz, 7.6, 6.4, self.col("coat"),
                  self.col("dark"))
        self.oval(27.0, 0.0, hz - 2.2, 4.8, 4.2, self.col("coat2"))
        self.oval(30.0, 0.0, hz - 3.0, 1.9, 1.55, self.col("nose"))
        self.line(self.p(29.7, 0.0, hz - 3.5),
                  self.p(24.0, 0.0, hz - 2.8), self.col("dark"), 0.7)
        # beard hanging from the jaw
        for u, side in ((23, -2.8), (25, -1.0), (25, 1.0), (23, 2.8)):
            self.tuft((u, side, hz - 3.0), (u - 1.8, side, hz - 4.6),
                      (u - 3.4, side * 1.3, hz - 8.2), self.col("beard"))
        # ears
        for side in (-1.0, 1.0):
            self.tuft((19.8, side * 4.4, hz + 2.4),
                      (22.0, side * 5.4, hz + 2.0),
                      (21.0, side * 6.2, hz + 5.2), self.col("coat2"))
        # horns: thick, pale, curved out and forward
        if not self.baby:
            for side in (-1.0, 1.0):
                pts = ((20.5, side * 4.4, hz + 4.6),
                       (22.0, side * 7.6, hz + 6.5),
                       (25.0, side * 9.2, hz + 6.0),
                       (27.5, side * 8.2, hz + 3.5))
                for j in range(len(pts) - 1):
                    a = self.p(*pts[j])
                    b = self.p(*pts[j + 1])
                    self.line(a, b, self.col("horn_d"), 4.0 - j * 0.55)
                    self.line(a, b, self.col("horn"), 1.6 - j * 0.22)
                self.dot(pts[-1][0], pts[-1][1], pts[-1][2],
                         1.15, self.col("horn_d"))
        else:
            for side in (-1.0, 1.0):
                self.tuft((21.0, side * 4.2, hz + 2.8),
                          (22.2, side * 4.8, hz + 2.5),
                          (21.5, side * 5.4, hz + 4.4), self.col("horn_d"))
        if not self.back:
            if self.front:
                eyes = (-3.2, 3.2)
            else:
                eyes = ((3.2,) if self.fx >= 0.0 else (-3.2,))
            for v in eyes:
                self.oval(23.2, v, hz + 1.2, 1.35, 1.15,
                          (30, 19, 14), (16, 10, 8))
                self.oval(23.2, v, hz + 1.2, 0.78, 0.70, self.col("eye"))
                self.dot(23.4, v, hz + 1.2, 0.20, (2, 2, 2))
                self.dot(22.8, v - 0.25, hz + 1.5, 0.22, (244, 234, 208))
            self.dot(29.6, -0.8, hz - 3.0, 0.30, self.col("nose"))
            self.dot(29.6, 0.8, hz - 3.0, 0.30, self.col("nose"))
            self.line(self.p(29.5, 0.0, hz - 4.0),
                      self.p(26.0, 0.0, hz - 4.5), self.col("dark"), 0.6)
            # a shaggy forehead tuft between the horns
            self.tuft((19.0, -2.2, hz + 4.2), (21.0, 2.2, hz + 4.4),
                      (18.2, 0.0, hz + 7.0), self.col("shag"))
        else:
            self.oval(21.5, 0.0, hz, 5.8, 4.6, self.col("coat2"))
            self.line(self.p(20.0, -4.0, hz + 2.0),
                      self.p(20.0, 4.0, hz + 2.0), self.col("dark"), 0.9)

    def details(self):
        # layered locks over the hump and flank, so the coat reads as fur
        # rather than one smooth brown oval.
        for i in range(10):
            u = -15.0 + i * 3.1
            z = 18.0 - abs(u + 2.0) * 0.10
            self.stroke(u, -6.5, u - 1.8, -3.8, z, z - 1.3,
                        self.col("coat2" if i % 2 else "shag"), 0.55)
        for i in range(5):
            u = 0.5 + i * 2.2
            self.stroke(u, -4.8, u + 0.8, -2.2,
                        25.5 - i * 0.7, 24.6 - i * 0.7,
                        self.col("shag" if i % 2 else "coat2"), 0.55)
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
