"""horseart.py -- a horse in eight 45-degree views.

The old horse was a PNG rotated to face a direction.  This is a projected
horse skeleton: barrel, chest and rump, long neck, head, mane, flowing tail,
four legs and hooves.  It walks with a diagonal gait and is cached as
anti-aliased frames.
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
FW, FH = 104, 84
AX, AY = 52, 56

PALETTES = {
    "brown": {
        "coat": (126, 88, 56), "coat2": (164, 120, 76),
        "dark": (76, 52, 34), "belly": (178, 146, 106),
        "mane": (58, 38, 26), "muzzle": (92, 62, 44),
        "hoof": (42, 34, 28), "sock": (206, 190, 164),
        "eye": (24, 16, 10), "nose": (30, 22, 16),
        "saddle": (104, 54, 44),
    },
    "black": {
        "coat": (58, 58, 64), "coat2": (86, 86, 94),
        "dark": (28, 28, 34), "belly": (78, 76, 80),
        "mane": (22, 21, 24), "muzzle": (46, 44, 48),
        "hoof": (18, 18, 22), "sock": (196, 192, 184),
        "eye": (16, 12, 10), "nose": (12, 10, 12),
        "saddle": (94, 48, 44),
    },
    "white": {
        "coat": (232, 230, 222), "coat2": (248, 246, 238),
        "dark": (168, 166, 158), "belly": (255, 255, 250),
        "mane": (202, 200, 192), "muzzle": (194, 180, 172),
        "hoof": (88, 84, 76), "sock": (255, 255, 250),
        "eye": (38, 26, 22), "nose": (82, 64, 62),
        "saddle": (112, 60, 50),
    },
    "palomino": {
        "coat": (196, 152, 78), "coat2": (224, 182, 104),
        "dark": (132, 94, 48), "belly": (234, 202, 138),
        "mane": (238, 218, 160), "muzzle": (176, 132, 80),
        "hoof": (62, 50, 38), "sock": (240, 224, 194),
        "eye": (40, 26, 14), "nose": (52, 36, 24),
        "saddle": (116, 62, 48),
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
        self.su = 0.46 + 0.54 * abs(fx)
        self.sv = 0.68 + 0.32 * abs(fy)
        self.bob = math.sin(self.phase * 2.0) * 0.55
        self.front = fy > 0.18
        self.back = fy < -0.18

    def col(self, key):
        if self.hit:
            if key in ("dark", "hoof", "eye", "nose", "mane"):
                return (116, 112, 106)
            if key == "saddle":
                return (160, 124, 110)
            return (248, 246, 240)
        return self.c[key]

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

    def stroke(self, u0, v0, u1, v1, z0, z1, color, width=0.8):
        self.line(self.p(u0, v0, z0), self.p(u1, v1, z1), color, width)

    def tail(self):
        # long, loose hair: thin at the dock, broad and split at the ends
        sway = math.sin(self.phase * 0.55) * 3.0
        pts = []
        for i in range(10):
            t = i / 9.0
            u = -21.0 - 15.0 * t
            v = sway * (t ** 1.4)
            z = 20.0 - 27.0 * t
            pts.append((u, v, z))
        for i in range(len(pts) - 1):
            u0, v0, z0 = pts[i]
            u1, v1, z1 = pts[i + 1]
            r = 1.8 + 2.6 * math.sin(math.pi * (i / 9.0))
            self.oval((u0 + u1) * 0.5, (v0 + v1) * 0.5,
                      (z0 + z1) * 0.5, r, r * 0.65,
                      self.col("mane" if i % 2 else "dark"))
        for side in (-1.0, 1.0):
            for j in (2, 4, 6):
                u, v, z = pts[j]
                self.tuft((u + 0.5, v + side * 1.4, z),
                          (u - 1.2, v + side * 2.2, z - 1.0),
                          (u - 2.6, v + side * 3.0, z - 2.0),
                          self.col("mane"))
        # dock
        self.oval(-21.0, 0.0, 20.0, 3.0, 2.2, self.col("mane"))

    def legs(self):
        # hip u, side, phase offset, thickness, hind
        legs = ((-13.0, -5.0, 0.0, 3.1, True),
                (-13.0, 5.0, math.pi, 3.1, True),
                (8.0, -4.4, math.pi, 2.4, False),
                (8.0, 4.4, 0.0, 2.4, False))
        for (hu, hv, off, thick, hind) in legs:
            sw = math.sin(self.phase + off) * (3.8 if hind else 3.2)
            lift = max(0.0, math.cos(self.phase + off)) * 2.0
            hip = self.p(hu, hv, 12.0)
            knee = self.p(hu + sw * 0.35, hv, 2.0 + lift * 0.25)
            fetlock = self.p(hu + sw * 0.75, hv, -6.0 + lift)
            hoof = self.p(hu + sw, hv, -10.0 + lift)
            self.line(hip, knee, self.col("coat"), thick)
            self.line(knee, fetlock, self.col("coat2"), max(1.7, thick * 0.74))
            self.line(fetlock, hoof, self.col("dark"), max(1.4, thick * 0.52))
            # white sock / hoof
            self.line(fetlock, hoof, self.col("sock"), max(1.0, thick * 0.36))
            self.oval(hu + sw, hv, -10.1 + lift, 2.2, 1.2, self.col("hoof"))
            # hind thigh
            if hind:
                self.oval(hu, hv, 8.0, 5.4, 4.2, self.col("coat2"))
            # a little feathering at the knee
            self.tuft((hu + sw * 0.3, hv - 1.0, 2.5 + lift),
                      (hu + sw * 0.3, hv + 1.0, 2.5 + lift),
                      (hu + sw * 0.8, hv + (3.0 if hv > 0 else -3.0),
                       1.2 + lift), self.col("coat2"))

    def body(self):
        # barrel, deep chest, rounded rump
        self.oval(0.0, 0.0, 14.0, 16.0, 7.6, self.col("coat"),
                  self.col("dark"))
        self.oval(-11.0, 0.0, 13.0, 8.4, 7.2, self.col("coat2"))
        self.oval(10.0, 0.0, 14.0, 7.2, 6.5, self.col("coat"))
        self.oval(0.0, 0.0, 9.5, 13.0, 5.4, self.col("belly"))
        # saddle blanket: these horses carry packs and riders
        self.oval(-1.0, 0.0, 19.0, 7.2, 6.4, self.col("saddle"))
        self.line(self.p(-7.0, -4.8, 19.0), self.p(5.0, -4.8, 19.0),
                  self.col("coat2"), 0.8)
        # back and rump guard hairs
        for i, (u, w, z) in enumerate(((-17, 4.2, 17.0), (-12, 6.2, 20.0),
                                        (-6, 6.8, 23.0), (1, 6.4, 22.0))):
            self.tuft((u - 1.2, -w * 0.25, z),
                      (u + 1.2, w * 0.25, z),
                      (u - 1.0, 0.0, z + 1.4 + (i % 2) * 0.7),
                      self.col("dark" if i % 2 else "coat"))
        for u, side in ((-18, -1), (-13, 1), (-4, -1), (4, 1)):
            self.tuft((u + 0.8, side * 7.0, 12.0),
                      (u - 1.2, side * 7.8, 11.0),
                      (u - 2.6, side * 8.8, 9.6), self.col("coat2"))

    def head(self):
        # neck: long and slightly arched
        self.poly([self.p(11.0, -5.0, 16.0), self.p(11.0, 5.0, 16.0),
                   self.p(24.0, 3.6, 28.0), self.p(24.0, -3.6, 28.0)],
                  self.col("coat"), self.col("dark"), 1.0)
        # mane runs up the neck and over the forehead
        for side in (-1.0, 1.0):
            for j, (u, z, ln) in enumerate(((13, 19, 2.0), (17, 22, 2.6),
                                             (21, 26, 2.3), (25, 30, 1.8))):
                self.tuft((u, side * 3.2, z), (u + 1.2, side * 3.8, z + 0.4),
                          (u - 1.2, side * 4.4, z - ln),
                          self.col("mane" if j % 2 else "dark"))
        # ears
        ear_shift = math.sin(self.phase * 1.3) * 0.3
        for side in (-1.0, 1.0):
            a = self.p(27.0 + ear_shift, side * 3.1, 31.0)
            b = self.p(29.2 + ear_shift, side * 3.9, 30.7)
            tip = self.p(27.0 + ear_shift, side * 3.7, 38.0)
            self.poly([a, b, tip], self.col("coat2"), self.col("dark"), 0.9)
            inner = self.p(27.8 + ear_shift, side * 3.5, 32.2)
            self.poly([a, b, inner], self.col("mane"))
        # skull and long face
        self.oval(28.0, 0.0, 27.0, 7.0, 4.8, self.col("coat"),
                  self.col("dark"))
        self.poly([self.p(32.0, -3.0, 26.0), self.p(39.0, -1.4, 22.0),
                   self.p(40.2, 0.0, 21.6), self.p(39.0, 1.4, 22.0),
                   self.p(32.0, 3.0, 26.0)],
                  self.col("muzzle"), self.col("dark"), 0.9)
        self.oval(39.0, 0.0, 21.6, 1.4, 0.9, self.col("nose"))
        self.line(self.p(37.5, 0.0, 21.8), self.p(32.5, 0.0, 23.3),
                  self.col("dark"), 0.7)
        if not self.back:
            if self.front:
                eyes = (-2.8, 2.8)
            else:
                eyes = ((2.8,) if self.fx >= 0.0 else (-2.8,))
            for v in eyes:
                self.oval(31.0, v, 28.0, 1.35, 1.15,
                          (34, 22, 18), (16, 10, 10))
                self.oval(31.0, v, 28.0, 0.78, 0.70, self.col("eye"))
                self.dot(31.2, v, 28.0, 0.20, (4, 3, 3))
                self.dot(30.7, v - 0.25, 28.3, 0.22, (255, 244, 220))
            # nostrils and mouth
            self.dot(38.7, -0.85, 21.8, 0.30, self.col("nose"))
            self.dot(38.7, 0.85, 21.8, 0.30, self.col("nose"))
            self.line(self.p(39.0, 0.0, 21.2), self.p(35.8, 0.0, 20.8),
                      self.col("dark"), 0.55)
            # forelock
            self.tuft((27.0, -1.4, 30.0), (29.0, 1.2, 30.2),
                      (26.0, 0.2, 34.0), self.col("mane"))
            # facial blaze on the darker coats
            if self.c["coat"][0] < 180:
                self.line(self.p(30.0, 0.0, 31.0), self.p(37.0, 0.0, 22.2),
                          self.col("sock"), 0.9)
        else:
            # rear view: ears, nape and a broad rump
            self.oval(23.5, 0.0, 28.0, 4.0, 3.8, self.col("coat2"))
            self.line(self.p(23.0, -3.0, 29.0), self.p(23.0, 3.0, 29.0),
                      self.col("dark"), 0.8)

    def details(self):
        # a few loose hairs where the coat catches the light
        for i in range(4):
            self.stroke(-8.0 + i * 4.5, -5.0, -6.0 + i * 4.5, -3.2,
                        17.0, 16.0, self.col("coat2"), 0.55)

    def render(self):
        self.tail()
        self.legs()
        self.body()
        self.head()
        self.details()


_cache: dict = {}


def _palette(coat: str):
    return PALETTES.get(coat, PALETTES["brown"])


def frame(coat: str, direction: int, step: int, zoom: float,
          hit: bool = False):
    key = (coat, direction, step, round(zoom, 2), bool(hit))
    got = _cache.get(key)
    if got is not None:
        return got
    fx, fy = DIRS[direction % 8]
    big = pygame.Surface((FW * SS, FH * SS), pygame.SRCALPHA)
    _P(big, fx, fy, zoom, step, _palette(coat), hit).render()
    small = pygame.transform.smoothscale(big, (FW, FH))
    _cache[key] = small
    return small


_shadows: dict = {}


def shadow(zoom: float = 1.0):
    key = round(zoom, 2)
    got = _shadows.get(key)
    if got is not None:
        return got
    w, h = max(2, int(54 * zoom)), max(2, int(18 * zoom))
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for i, a in ((0, 38), (1, 30), (2, 20)):
        rr = (w - i * 8, h - i * 3)
        if rr[0] <= 0 or rr[1] <= 0:
            continue
        pygame.draw.ellipse(s, (12, 10, 8, a),
                            ((w - rr[0]) // 2, (h - rr[1]) // 2,
                             rr[0], rr[1]))
    _shadows[key] = s
    return s
