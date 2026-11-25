"""rabbitart.py -- a small, soft rabbit in eight 45-degree views.

The old rabbit was a circle, a line and two ears.  This one has a projected
body, a puff tail, long ears with pink insides, four feet, whiskers and a
hop cycle.  The sprite is drawn supersampled and cached, like the wolf.
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
RW, RH = 54, 54
AX, AY = 27, 37

PALETTES = {
    "grey": {
        "coat": (202, 194, 184), "coat2": (226, 219, 208),
        "dark": (112, 106, 102), "belly": (244, 239, 230),
        "ear": (188, 174, 164), "inner": (206, 150, 148),
        "eye": (30, 22, 18), "nose": (190, 116, 112),
        "line": (100, 88, 84), "tooth": (250, 246, 232),
    },
    "brown": {
        "coat": (154, 116, 76), "coat2": (184, 145, 96),
        "dark": (94, 68, 44), "belly": (218, 190, 150),
        "ear": (139, 102, 68), "inner": (188, 128, 120),
        "eye": (36, 22, 15), "nose": (164, 94, 86),
        "line": (82, 58, 38), "tooth": (248, 238, 218),
    },
    "yellow": {
        "coat": (222, 198, 112), "coat2": (242, 222, 148),
        "dark": (146, 118, 58), "belly": (250, 238, 190),
        "ear": (204, 176, 100), "inner": (218, 154, 142),
        "eye": (42, 28, 14), "nose": (190, 114, 106),
        "line": (132, 102, 48), "tooth": (255, 248, 222),
    },
    "white": {
        "coat": (240, 241, 245), "coat2": (252, 251, 250),
        "dark": (172, 178, 188), "belly": (255, 255, 252),
        "ear": (226, 223, 226), "inner": (226, 166, 164),
        "eye": (38, 26, 24), "nose": (206, 132, 130),
        "line": (168, 168, 176), "tooth": (255, 255, 244),
    },
}


class _P:
    def __init__(self, surf, fx, fy, zoom, step, palette, hit=False):
        self.s = surf
        self.fx, self.fy = fx, fy
        self.px, self.py = -fy, fx
        self.zoom = zoom
        self.phase = step * (2.0 * math.pi / 8.0)
        self.c = palette
        self.hit = hit
        self.su = 0.50 + 0.50 * abs(fx)
        self.sv = 0.72 + 0.28 * abs(fy)
        self.hop = max(0.0, math.sin(self.phase)) * 3.3
        self.front = fy > 0.18
        self.back = fy < -0.18

    def col(self, key):
        if self.hit:
            if key in ("dark", "line", "nose", "eye"):
                return (118, 112, 108)
            return (249, 246, 240)
        return self.c[key]

    def p(self, u, v, z):
        x = u * self.fx * self.su + v * self.px * self.sv
        y = u * self.fy * self.su + v * self.py * self.sv - (z + self.hop)
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
        for i in range(18):
            t = i * (2.0 * math.pi / 18.0)
            pts.append(self.p(u + math.cos(t) * ru,
                              v + math.sin(t) * rv, z))
        self.poly(pts, color, outline)

    def tuft(self, a, b, tip, color):
        self.poly([self.p(*a), self.p(*b), self.p(*tip)], color)

    def stroke(self, u0, v0, u1, v1, z0, z1, color, width=0.8):
        self.line(self.p(u0, v0, z0), self.p(u1, v1, z1), color, width)

    def tail(self):
        # A puff, not a line.  Four overlapping locks make a soft white bob.
        sway = math.sin(self.phase * 0.7) * 1.0
        for i in range(5):
            self.oval(-13.2 + (i % 2) * 0.8, sway * 0.3,
                      4.7 + (i % 3) * 0.8, 2.9, 2.5,
                      self.col("belly" if i % 2 else "coat2"))
        for side in (-1.0, 1.0):
            self.tuft((-13.0, side * 1.8, 5.0), (-14.8, side * 2.1, 4.2),
                      (-16.0, side * 3.1, 3.4), self.col("belly"))
        # a few darker strands at the root
        self.stroke(-11.8, 0.0, -13.0, 1.7, 5.4, 4.6,
                    self.col("dark"), 0.65)

    def legs(self):
        # hind leg: hip u, side, phase offset, thickness
        legs = ((-7.0, -3.8, 0.0, 2.9, True),
                (-7.0, 3.8, math.pi, 2.9, True),
                (7.0, -3.2, math.pi, 1.6, False),
                (7.0, 3.2, 0.0, 1.6, False))
        for (hu, hv, off, thick, hind) in legs:
            sw = math.sin(self.phase + off) * (2.7 if hind else 1.8)
            lift = max(0.0, math.cos(self.phase + off)) * 1.6
            if self.hop > 0.4:
                sw = 2.2 if hind else 1.2
                lift = 1.0
            hip = self.p(hu, hv, 3.0)
            knee = self.p(hu + sw * 0.45, hv, -0.2 + lift * 0.5)
            foot = self.p(hu + sw, hv, -3.2 + lift)
            self.line(hip, knee, self.col("coat"), thick)
            self.line(knee, foot, self.col("coat2"), max(1.0, thick * 0.5))
            self.oval(hu + sw, hv, -3.35 + lift, 2.2 if hind else 1.6,
                      1.15, self.col("belly"))
            if hind:
                self.oval(hu, hv, 2.4, 3.2, 2.6, self.col("coat2"))

    def body(self):
        # low, rounded back and a deep haunch; the head sits forward
        self.oval(-2.0, 0.0, 5.4, 8.7, 6.0, self.col("coat"),
                  self.col("dark"))
        self.oval(-7.5, 0.0, 4.5, 5.2, 5.2, self.col("coat2"))
        self.oval(3.6, 0.0, 5.0, 4.8, 5.0, self.col("coat"))
        self.oval(0.0, 0.0, 2.6, 7.2, 4.8, self.col("belly"))
        # soft fur tufts along the back and rump
        for i, (u, w, z) in enumerate(((-11, 4.8, 8.2), (-7, 5.5, 9.4),
                                        (-3, 5.8, 9.8), (2, 5.0, 9.2))):
            self.tuft((u - 1.0, -w * 0.28, z),
                      (u + 1.0, w * 0.28, z),
                      (u - 1.2, 0.0, z + 1.5 + (i % 2) * 0.6),
                      self.col("coat2" if i % 2 else "dark"))
        for u, side in ((-10, -1), (-5, 1), (1, -1), (4, 1)):
            self.tuft((u + 0.8, side * 4.5, 4.3),
                      (u - 1.2, side * 5.4, 3.7),
                      (u - 2.4, side * 6.0, 2.8), self.col("coat2"))
        for i in range(3):
            self.stroke(-7.0 + i * 4.4, -4.0, -6.0 + i * 4.4, -2.5,
                        7.3, 6.6, self.col("dark"), 0.55)

    def head(self):
        # ears first, hinged behind the skull; they flop with the hop
        flop = math.sin(self.phase * 1.4) * 0.55
        for side in (-1.0, 1.0):
            base_a = self.p(10.3, side * 2.3, 11.4)
            base_b = self.p(12.3, side * 3.1, 11.1)
            tip = self.p(8.4 + flop, side * 3.9, 24.0)
            self.poly([base_a, base_b, tip], self.col("ear"),
                      self.col("dark"), 0.8)
            inner = self.p(10.2 + flop, side * 2.7, 13.0)
            self.poly([base_a, base_b, inner], self.col("inner"))
            # little fur wisps at the ear base
            self.tuft((10.7, side * 2.5, 11.8),
                      (11.8, side * 3.1, 11.4),
                      (9.4, side * 4.0, 13.2), self.col("coat2"))
        # head / cheeks
        self.oval(12.2, 0.0, 8.4, 5.0, 4.4, self.col("coat"),
                  self.col("dark"))
        for side in (-1.0, 1.0):
            self.tuft((13.4, side * 3.4, 8.0),
                      (12.2, side * 5.1, 7.3),
                      (10.3, side * 4.6, 8.7), self.col("coat2"))
        # muzzle and nose
        self.oval(16.4, 0.0, 6.9, 2.6, 2.1, self.col("coat2"))
        self.oval(18.1, 0.0, 6.9, 1.0, 0.8, self.col("nose"))
        self.dot(18.3, 0.0, 7.1, 0.27, (80, 40, 38))
        if not self.back:
            # mouth
            self.line(self.p(18.0, 0.0, 6.5), self.p(16.1, 0.0, 6.0),
                      self.col("line"), 0.55)
            self.line(self.p(16.1, 0.0, 6.0), self.p(15.2, 0.0, 6.4),
                      self.col("line"), 0.45)
            # eyes: both face-on, one in profile
            if self.front:
                eyes = (-2.4, 2.4)
            else:
                eyes = ((2.4,) if self.fx >= 0.0 else (-2.4,))
            for v in eyes:
                self.oval(13.6, v, 9.2, 1.45, 1.35,
                          (35, 24, 22), (18, 12, 12))
                self.oval(13.6, v, 9.2, 0.88, 0.82, self.col("eye"))
                self.dot(13.8, v, 9.2, 0.23, (6, 4, 4))
                self.dot(13.3, v - 0.30, 9.5, 0.25, (255, 244, 226))
            # whiskers
            for side in (-1.0, 1.0):
                for du, dv, dz in ((3.4, 2.1, -0.2),
                                    (4.0, 3.4, 0.2),
                                    (3.2, 4.4, 0.5)):
                    self.line(self.p(17.8, side * 0.7, 6.8),
                              self.p(17.8 + du, side * dv, 6.8 + dz),
                              self.col("belly"), 0.3)
        else:
            # rear view: round rump, ears and tail only
            for side in (-1.0, 1.0):
                self.tuft((11.8, side * 2.8, 11.0),
                          (10.0, side * 4.0, 9.4),
                          (8.2, side * 3.4, 7.6), self.col("coat2"))

    def details(self):
        # tiny fur breaks around the head and feet
        for i in range(4):
            self.stroke(8.0 + i * 2.4, -3.2, 9.0 + i * 2.4, -2.1,
                        10.0, 9.4, self.col("coat2"), 0.55)

    def render(self):
        self.tail()
        self.legs()
        self.body()
        self.head()
        self.details()


_cache: dict = {}


def _palette(fur: str):
    return PALETTES.get(fur, PALETTES["grey"])


def frame(fur: str, direction: int, step: int, zoom: float,
          hit: bool = False):
    key = (fur, direction, step, round(zoom, 2), bool(hit))
    got = _cache.get(key)
    if got is not None:
        return got
    fx, fy = DIRS[direction % 8]
    big = pygame.Surface((RW * SS, RH * SS), pygame.SRCALPHA)
    _P(big, fx, fy, zoom, step, _palette(fur), hit).render()
    small = pygame.transform.smoothscale(big, (RW, RH))
    _cache[key] = small
    return small


_shadows: dict = {}


def shadow(zoom: float = 1.0):
    key = round(zoom, 2)
    got = _shadows.get(key)
    if got is not None:
        return got
    w, h = max(2, int(21 * zoom)), max(2, int(8 * zoom))
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for i, a in ((0, 34), (1, 28), (2, 18)):
        rr = (w - i * 3, h - i * 2)
        if rr[0] <= 0 or rr[1] <= 0:
            continue
        pygame.draw.ellipse(s, (12, 10, 8, a),
                            ((w - rr[0]) // 2, (h - rr[1]) // 2,
                             rr[0], rr[1]))
    _shadows[key] = s
    return s
