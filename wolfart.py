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
        "eye": (254, 26, 18), "eye_glow": (255, 16, 10),
        "eye_hot": (255, 88, 38), "brow": (38, 36, 42),
        "nose": (27, 25, 28), "mouth": (126, 54, 54),
        "tooth": (238, 232, 212), "spot": (68, 68, 76),
    },
    "white_wolf": {
        "coat": (220, 224, 230), "coat2": (240, 242, 246),
        "back": (146, 154, 168), "belly": (250, 250, 248),
        "leg": (176, 182, 192), "paw": (126, 134, 148),
        "ear": (190, 196, 208), "inner": (206, 162, 158),
        "eye": (254, 26, 18), "eye_glow": (255, 16, 10),
        "eye_hot": (255, 88, 38), "brow": (92, 96, 106),
        "nose": (53, 56, 64), "mouth": (146, 72, 76),
        "tooth": (255, 250, 236), "spot": (182, 188, 198),
    },
    "hyena": {
        "coat": (154, 126, 86), "coat2": (186, 158, 112),
        "back": (86, 64, 42), "belly": (218, 198, 158),
        "leg": (104, 82, 54), "paw": (66, 50, 34),
        "ear": (112, 88, 60), "inner": (158, 112, 94),
        "eye": (254, 26, 18), "eye_glow": (255, 16, 10),
        "eye_hot": (255, 88, 38), "brow": (62, 46, 30),
        "nose": (35, 28, 20), "mouth": (128, 58, 60),
        "tooth": (246, 238, 218), "spot": (84, 66, 48),
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
            if key in ("eye", "eye_glow", "eye_hot"):
                return (255, 34, 24)
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

    def glow(self, u, v, z, r, color):
        """A small additive halo -- the eye light spills onto the fur."""
        cx, cy = self.p(u, v, z)
        radius = max(2, int(round(r * 3.0 * self.zoom * SS)))
        gs = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        for rr, alpha in ((r * 2.75, 20), (r * 2.0, 34),
                          (r * 1.45, 58), (r, 92)):
            pygame.draw.circle(gs, (*color, int(alpha)),
                               (radius + 1, radius + 1),
                               max(1, int(round(rr * self.zoom * SS))))
        self.s.blit(gs, (cx - radius - 1, cy - radius - 1),
                    special_flags=pygame.BLEND_RGBA_ADD)

    def tuft(self, base_a, base_b, tip, color):
        self.poly([self.p(*base_a), self.p(*base_b), self.p(*tip)], color)

    def fur(self, u0, v0, u1, v1, z0, z1, color, width=1.0):
        self.line(self.p(u0, v0, z0), self.p(u1, v1, z1), color, width)

    # -- body ---------------------------------------------------------------
    def body_rings(self):
        # (u, half-width, top z, bottom z)
        rings = [
            (-19.0, 2.2, 4.2, 0.5),
            (-17.0, 5.4, 6.4, 0.2),
            (-13.0, 6.9, 7.8, -0.5),
            (-6.0, 7.3, 8.6, -0.7),
            (1.0, 7.7, 9.3, -0.5),
            (7.0, 6.4, 10.0, 0.2),
            (12.0, 4.4, 10.6, 1.0),
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
        # guard-hair spikes around the brush: a tail should not read as a
        # smooth sausage.
        for i in range(1, len(pts) - 1):
            u, v, z = pts[i]
            r = 2.2 + 3.8 * math.sin(math.pi * (i / 8.0))
            for side in (-1.0, 1.0):
                self.tuft((u + 0.6, v + side * r * 0.55, z),
                          (u - 1.8, v + side * r * 0.65, z - 0.4),
                          (u - 2.8, v + side * r * 1.20, z - 0.8),
                          self.col("coat2" if i % 2 else "coat"))
        # dark tip
        u, v, z = pts[-1]
        self.oval(u, v, z, 3.2, 2.2, self.col("back"))
        for side in (-1.0, 1.0):
            self.tuft((u + 0.5, side * 1.8, z + 0.4),
                      (u - 1.0, side * 2.2, z - 0.6),
                      (u - 3.2, side * 3.0, z - 1.6), self.col("back"))

    def legs(self):
        # hip u, side v, phase offset, thickness
        legs = [
            (-13.0, -4.6, 0.0, 1.65),
            (-13.0, 4.6, math.pi, 1.65),
            (7.0, -4.3, math.pi, 1.75),
            (7.0, 4.3, 0.0, 1.75),
        ]
        for (hu, hv, off, thick) in legs:
            swing = math.sin(self.phase + off) * 3.2
            lift = max(0.0, math.cos(self.phase + off)) * 2.2
            if self.lunge and hu > 0.0:
                swing = 5.0
                lift = 0.4
            hip = self.p(hu, hv, 1.0)
            knee = self.p(hu + swing * 0.55, hv, -3.5 + lift * 0.45)
            paw = self.p(hu + swing, hv, -7.6 + lift)
            # upper leg is a little thicker; lower leg tapers to the paw
            self.line(hip, knee, self.col("leg"), thick)
            self.line(knee, paw, self.col("leg"), max(1.0, thick * 0.72))
            self.oval(hu + swing, hv, -7.7 + lift, 1.75, 1.0,
                      self.col("paw"))
            # a few hairs at the hock and elbow
            self.tuft((hu + swing * 0.4, hv - 0.8, -3.2 + lift),
                      (hu + swing * 0.4, hv + 0.8, -3.2 + lift),
                      (hu + swing * 0.8, hv + (2.3 if hv > 0 else -2.3),
                       -4.2 + lift), self.col("coat2"))

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
        # shoulder and haunch masses, kept narrow for a running silhouette
        self.oval(6.0, 0.0, 5.0, 5.5, 6.2, self.col("coat2"))
        self.oval(-13.0, 0.0, 4.2, 4.8, 6.0, self.col("coat2"))
        # chest ruff: longer, uneven points, not four neat petals
        for v, dz in ((-4.1, 1.0), (-1.7, 1.8), (1.5, 1.4), (4.0, 0.5)):
            self.poly([self.p(9.6, v - 1.3, 3.6),
                       self.p(13.8, v, 1.2 + dz),
                       self.p(9.6, v + 1.3, 3.6)],
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

    def body_fur(self):
        """Jagged guard hairs along back, belly and flanks.

        The base body is still a clean projected form; this is the coat that
        breaks its edge.  Drawn after the body so the tips remain visible.
        """
        rings = self.body_rings()
        # dorsal hackles
        for i in range(1, len(rings) - 1):
            u, w, zt, zb = rings[i]
            nxt = rings[i + 1][0]
            sway = math.sin(self.phase * 1.4 + i) * 0.35
            self.tuft((u - 1.0, -w * 0.20, zt - 0.2),
                      (nxt + 0.4, w * 0.20, zt - 0.2),
                      (u - 1.8 + sway, 0.0, zt + 1.6 + (i % 2) * 0.55),
                      self.col("back" if i % 2 else "coat2"))
        # belly fringe, lighter and shorter
        for i in range(1, len(rings) - 1):
            u, w, zt, zb = rings[i]
            nxt = rings[i + 1][0]
            self.tuft((u - 0.8, -w * 0.55, zb + 0.2),
                      (nxt + 0.4, w * 0.55, zb + 0.2),
                      (u - 1.4, 0.0, zb - 1.5 - (i % 2) * 0.45),
                      self.col("belly"))
        # flank and rump tufts, pointing backward
        for u, side in ((-16, -1), (-15, 1), (-11, -1), (-10, 1),
                        (-5, -1), (-4, 1), (2, -1), (3, 1)):
            w = 6.8 if u < -8 else 7.4
            z = 5.2 if u < -8 else 6.3
            self.tuft((u + 0.8, side * w * 0.82, z),
                      (u - 1.2, side * w * 0.92, z - 0.7),
                      (u - 3.0, side * (w + 1.4), z - 1.2),
                      self.col("coat" if (u % 2) else "coat2"))

    # -- neck and head ------------------------------------------------------
    def head(self):
        front = self.fy > 0.18
        back = self.fy < -0.18
        # narrow neck rising from the shoulders
        self.poly([self.p(9.0, -4.4, 8.2), self.p(9.0, 4.4, 8.2),
                   self.p(17.0, 3.5, 12.2), self.p(17.0, -3.5, 12.2)],
                  self.col("coat"), self.col("back"), 1.0)
        # Neck ruff: long, uneven guard hairs hanging off both sides.
        for side in (-1.0, 1.0):
            for j, (u, z, ln) in enumerate(((10.0, 9.0, 2.6),
                                             (12.2, 9.7, 3.4),
                                             (14.4, 10.4, 2.8),
                                             (16.2, 11.1, 1.8))):
                self.tuft((u, side * 4.2, z),
                          (u + 1.1, side * 4.6, z + 0.2),
                          (u - 1.4, side * (4.8 + ln * 0.35),
                           z - ln), self.col("coat2" if j % 2 else "coat"))
        # ears first so the skull overlaps their bases
        ear_shift = math.sin(self.phase * 1.3) * 0.35
        if self.lunge:
            ear_shift += 1.5
        for side in (-1.0, 1.0):
            base_a = self.p(17.2 + ear_shift, side * 4.3, 14.0)
            base_b = self.p(20.0 + ear_shift, side * 5.2, 13.7)
            tip = self.p(18.4 + ear_shift, side * 5.1, 20.3)
            self.poly([base_a, base_b, tip], self.col("ear"),
                      self.col("back"), 1.0)
            inner = self.p(18.7 + ear_shift, side * 4.9, 15.2)
            self.poly([base_a, base_b, inner], self.col("inner"))
            # fur leaking over the ear rim
            self.tuft((18.0 + ear_shift, side * 4.4, 16.0),
                      (18.5 + ear_shift, side * 4.9, 17.0),
                      (17.2 + ear_shift, side * 5.6, 19.2),
                      self.col("coat2"))
        # skull, slightly narrower than the old one
        self.oval(20.0, 0.0, 11.2, 5.6, 4.6,
                  self.col("coat"), self.col("back"))
        self.oval(18.3, 0.0, 12.0, 2.9, 3.2, self.col("coat2"))
        # cheek ruffs, always visible: the face should look framed in fur
        for side in (-1.0, 1.0):
            self.tuft((20.8, side * 3.4, 10.0),
                      (19.3, side * 5.7, 9.0),
                      (17.5, side * 5.0, 10.8), self.col("coat2"))
            self.tuft((21.8, side * 2.8, 9.2),
                      (22.8, side * 4.0, 8.5),
                      (20.6, side * 4.8, 7.8), self.col("coat"))
        if not back:
            # dark facial mask / brow, then the long muzzle
            for v in ((-2.9, 2.9) if front else ((2.9,) if self.fx >= 0 else (-2.9,))):
                self.poly([self.p(20.8, v - 1.9, 13.0),
                           self.p(24.8, v - 2.5, 12.0),
                           self.p(25.2, v + 1.5, 11.8),
                           self.p(21.2, v + 1.8, 12.8)],
                          self.col("brow"))
            self.poly([self.p(22.6, -2.9, 10.2),
                       self.p(30.8, -1.35, 8.0),
                       self.p(31.4, 0.0, 7.9),
                       self.p(30.8, 1.35, 8.0),
                       self.p(22.6, 2.9, 10.2)],
                      self.col("coat2"), self.col("back"), 0.9)
            # bridge of the nose
            self.line(self.p(21.0, 0.0, 13.0), self.p(29.4, 0.0, 9.4),
                      self.col("belly"), 0.9)
            if self.lunge:
                self.poly([self.p(22.4, -2.9, 9.4),
                           self.p(30.2, -1.3, 6.4),
                           self.p(29.4, 1.3, 5.8),
                           self.p(22.4, 2.9, 9.4)],
                          self.col("mouth"), self.col("back"), 1.0)
                # tongue and teeth
                self.poly([self.p(23.4, -1.8, 8.1),
                           self.p(29.0, -0.8, 6.3),
                           self.p(29.2, 0.8, 6.3),
                           self.p(23.4, 1.8, 8.1)], (154, 58, 58))
                for t in (24.3, 25.8, 27.3, 28.8):
                    self.poly([self.p(t, -1.7, 9.1),
                               self.p(t + 0.45, -0.4, 8.1),
                               self.p(t + 0.5, 0.5, 8.1)], self.col("tooth"))
                    self.poly([self.p(t, 1.7, 9.1),
                               self.p(t + 0.45, 0.4, 8.1),
                               self.p(t + 0.5, -0.5, 8.1)], self.col("tooth"))
                # snarl creases
                for v in (-1.9, 1.9):
                    self.line(self.p(25.0, v, 10.0), self.p(27.5, v, 9.2),
                              self.col("brow"), 0.65)
            else:
                self.line(self.p(29.8, 0.0, 8.0), self.p(24.0, 0.0, 8.7),
                          self.col("mouth"), 0.9)
                self.line(self.p(24.2, 0.0, 8.7), self.p(23.3, 0.0, 8.1),
                          self.col("brow"), 0.7)
            # nose, nostrils and a wet highlight
            self.oval(31.4, 0.0, 8.0, 1.45, 1.05, self.col("nose"))
            self.dot(31.8, 0.0, 8.25, 0.32, (118, 110, 108))
            self.dot(30.9, -0.55, 8.15, 0.30, (8, 7, 9))
            self.dot(30.9, 0.55, 8.15, 0.30, (8, 7, 9))
            # whiskers, thin and pale
            for side in (-1.0, 1.0):
                for (du, dv, dz) in ((4.0, 2.2, -0.4),
                                      (4.6, 3.7, 0.1),
                                      (3.6, 4.8, 0.6)):
                    self.line(self.p(30.0, side * 1.3, 8.2),
                              self.p(30.0 + du, side * dv, 8.2 + dz),
                              self.col("belly"), 0.35)
            # red eyes with a halo.  Both front-on, one from the side.
            if front:
                eyes = (-2.9, 2.9)
            elif back:
                eyes = ()
            else:
                eyes = ((2.9,) if self.fx >= 0.0 else (-2.9,))
            for v in eyes:
                # The glow is the eye, not a red cloud painted around it.
                # A dark socket, a hot red iris, a black slit and one white
                # catchlight -- all inside the lid.
                self.oval(23.1, v, 12.1, 2.35, 1.95,
                          (32, 10, 10), (12, 7, 8))
                self.oval(23.1, v, 12.1, 1.95, 1.60,
                          self.col("eye"), (118, 12, 8))
                self.oval(23.35, v, 12.1, 1.10, 1.10,
                          self.col("eye_hot"))
                self.dot(23.58, v, 12.1, 0.46, (22, 4, 4))
                self.dot(23.15, v - 0.34, 12.32, 0.24, (255, 242, 218))
            # forehead fur breaks up the smooth skull
            for v in (-2.2, 0.0, 2.2):
                self.tuft((20.0, v - 0.7, 13.5), (20.6, v + 0.7, 13.5),
                          (18.8, v, 15.0), self.col("coat2"))
        else:
            # from behind: broad nape, ears, no face
            self.oval(18.7, 0.0, 12.0, 4.0, 4.0, self.col("coat2"))
            for side in (-1.0, 1.0):
                self.tuft((18.0, side * 2.8, 12.2),
                          (16.5, side * 4.0, 10.6),
                          (14.8, side * 3.4, 8.8), self.col("coat"))
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
        self.body_fur()
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
