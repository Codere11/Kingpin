"""Forests / jungle.

Trees are placed on a jittered lattice. Each tree's canopy radius is derived
from the distance to its nearest neighbouring tree, so canopies can touch but
can never overlap. Dense woods therefore grow smaller crowns and open ground
grows large ones.

The trunk (a narrow base) is solid and blocks sight; the leaves are
semi-transparent and only lightly shorten how far you can see.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pygame

import biomes
import nations
import wind
from noise import fbm
from world import coast_x
from village import (SPACING, VILLAGE_SCALE, village_center,
                     village_clearance, village_radius)

CELL = 180
PREFETCH = 7             # tree cells grown ahead of the player, each way
JIT = 18                             # position jitter within a cell
SIZES = [24, 36, 48, 60, 72, 84, 96, 108, 120]   # sprite size classes
VARIANTS = 8
SPAWN = 1.0                          # global density multiplier
R_MIN = 34.0
R_MAX = 120.0
CANOPY_ALPHA = 205                   # leaves are semi-transparent
_NOW = 0.0
VILLAGE_RADIUS = 430.0 * VILLAGE_SCALE           # a village's own ground
VILLAGE_CLEAR = 520.0 * VILLAGE_SCALE + 320.0    # no trees inside a village (+margin)
VILLAGE_FADE = VILLAGE_CLEAR + 900.0
FADE_BAND = VILLAGE_FADE - VILLAGE_CLEAR         # how far the thinning reaches
CLEAR_MARGIN = VILLAGE_CLEAR - VILLAGE_RADIUS    # clear ground beyond the fence

PALETTE = [(46, 88, 44), (56, 98, 50), (40, 78, 40), (62, 104, 54),
           (52, 92, 46), (70, 112, 58), (44, 84, 52), (60, 100, 62)]
JUNGLE_PALETTE = [(30, 76, 44), (38, 88, 50), (24, 66, 38), (46, 96, 54),
                  (34, 82, 46), (52, 104, 58)]
CONIFER = [(34, 66, 44), (42, 78, 50), (28, 58, 38), (48, 86, 54)]
BARE = [(104, 84, 62), (120, 98, 74), (88, 70, 52)]
ACACIA = [(104, 124, 58), (118, 138, 66), (92, 112, 50)]
CACTUS = [(74, 124, 66), (88, 142, 76), (62, 108, 56)]
IRONWOOD = [(92, 92, 90), (112, 112, 108), (76, 76, 74), (128, 126, 120),
            (100, 100, 96), (84, 84, 82)]


def _smoothstep(x, a, b):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _lighten(color, amount):
    return tuple(min(255, c + amount) for c in color)


def _darken(color, amount):
    return tuple(max(0, c - amount) for c in color)


def _shade(color, t):
    amount = int(max(-0.5, min(0.6, t)) * 52)
    return tuple(max(0, min(255, c + amount)) for c in color)


def _rgba(color, alpha):
    return (color[0], color[1], color[2], alpha)


def _trunk_factor(variant: int) -> float:
    """Deterministic 3x-5x thinning, varied by tree variant."""
    return 3.0 + float((int(variant) * 7) % 9) / 4.0


def _trunk_shape(cx, ay, top_y, base_w, top_w, rng, radius,
                 bend=None, wiggle=None, phase=None):
    """A slightly leaning, gently wavy trunk instead of a straight plank."""
    n = 7
    if bend is None:
        bend = rng.uniform(-0.055, 0.055) * radius
    if wiggle is None:
        wiggle = rng.uniform(0.0, 0.014) * radius
    if phase is None:
        phase = rng.uniform(0.0, 2.0 * math.pi)
    left, right = [], []
    for i in range(n + 1):
        t = i / float(n)
        y = ay + (top_y - ay) * t
        w = base_w * (1.0 - t) + top_w * t
        off = bend * math.sin(math.pi * t) + wiggle * math.sin(math.pi * 3.0 * t + phase)
        left.append((cx + off - w / 2.0, y))
        right.append((cx + off + w / 2.0, y))
    return left + list(reversed(right))


def _hash(cx, cy, seed):
    h = (cx * 73856093) ^ (cy * 19349663) ^ (seed * 2654435761)
    h &= 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h


class _FastRNG:
    """A deterministic xorshift RNG, ~100x cheaper to seed than random.Random.

    The tree generator creates one RNG per cell (hundreds of thousands of
    them at load), and `random.Random(code)` pays for a full Mersenne-Twister
    seed every time. Only `uniform` and `random` are needed here, and a tree's
    exact jitter is background noise nobody can tell apart."""
    __slots__ = ("_s",)

    def __init__(self, code: int) -> None:
        self._s = (int(code) ^ 0x9E3779B9) & 0xFFFFFFFF

    def _next(self) -> float:
        s = self._s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self._s = s & 0xFFFFFFFF
        return (s & 0xFFFFFFFF) / 4294967296.0

    def random(self) -> float:
        return self._next()

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._next()


class TreeSprites:
    """Shared, pre-rendered tree sprites."""

    def __init__(self) -> None:
        self._cache: dict[tuple[int, int, bool], tuple] = {}
        self._scaled: dict[tuple, tuple] = {}     # rescaled, shared
        self._splits: dict[tuple, tuple] = {}     # static base, moving green canopy
        self._exact: dict[tuple, tuple] = {}      # rendered trunk and canopy, unscaled
        self._branch_geo: dict[tuple, tuple] = {}
        self._static_branch: dict[tuple, object] = {}
        self._stump = None

    def stump(self):
        if self._stump is None:
            # A third of the old stump size.
            k = 1.0 / 3.0
            r, pad = 17 * k, 5 * k
            w = h = max(8, int(r * 2 + pad * 2))
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            cx, cy = w / 2.0, h - pad
            pygame.draw.ellipse(surf, (12, 24, 12, 70),
                                (cx - 20 * k, cy - 7 * k, 40 * k, 14 * k))
            pygame.draw.ellipse(surf, (112, 78, 46),
                                (cx - r, cy - r * 0.85, r * 2, r * 1.7))
            pygame.draw.ellipse(surf, (70, 46, 26),
                                (cx - r, cy - r * 0.85, r * 2, r * 1.7), 1)
            pygame.draw.ellipse(surf, (188, 152, 106),
                                (cx - r * 0.7, cy - r * 0.6, r * 1.4, r * 1.2))
            pygame.draw.line(surf, (150, 118, 80),
                             (cx, cy - r * 0.55), (cx + r * 0.55, cy + r * 0.1), 1)
            self._stump = (surf, cx, cy)
        return self._stump

    def get(self, species: str, size_class: int, variant: int, flip: bool,
            snowy: bool = False, radius: float = None):
        key = (species, size_class, variant, flip, snowy)
        sprite = self._cache.get(key)
        if sprite is None:
            raw = self._render(species, size_class, variant, snowy)
            if len(raw) == 5:
                combined, base, canopy, ax, ay = raw
                if flip:
                    combined = pygame.transform.flip(combined, True, False)
                    base = pygame.transform.flip(base, True, False)
                    canopy = pygame.transform.flip(canopy, True, False)
                self._exact[key] = (base, canopy)
                sprite = (combined, ax, ay)
            else:
                sprite = raw
                if flip:
                    surface, ax, ay = sprite
                    sprite = (pygame.transform.flip(surface, True, False), ax, ay)
            self._cache[key] = sprite
        if radius is None:
            return sprite
        scale = radius / SIZES[size_class]
        rkey = (species, size_class, variant, flip, snowy, round(float(radius), 1))
        if abs(scale - 1.0) <= 0.02:
            exact = self._exact.get(key)
            if exact is not None and rkey not in self._splits:
                self._splits[rkey] = exact
            return sprite
        # Every tree used to rescale a sprite of its own for its exact radius:
        # seventeen thousand near-identical surfaces, and the better part of a
        # gigabyte of memory. Quantise the scale and share them.
        step = max(1, int(round(scale * 12))) / 12.0
        skey = (species, size_class, variant, flip, snowy, step)
        got = self._scaled.get(skey)
        if got is None:
            surface, ax, ay = sprite
            w = max(1, int(surface.get_width() * step))
            h = max(1, int(surface.get_height() * step))
            got = (pygame.transform.smoothscale(surface, (w, h)),
                   ax * step, ay * step)
            self._scaled[skey] = got
            exact = self._exact.get(key)
        exact = self._exact.get(key)
        if exact is not None and rkey not in self._splits:
            base, canopy = exact
            bw = max(1, int(base.get_width() * step))
            bh = max(1, int(base.get_height() * step))
            self._splits[rkey] = (
                pygame.transform.smoothscale(base, (bw, bh)),
                pygame.transform.smoothscale(canopy, (bw, bh)))
        return got

    def split(self, species: str, size_class: int, variant: int, flip: bool,
              snowy: bool, radius: float, image):
        """Separate the green leaves from trunk/branches/shadow.

        The whole tree must never move: only pixels that actually look green
        are cut onto the canopy layer.  Cached per sprite, so this happens
        once, not every frame.
        """
        if species in ("bare", "cactus"):
            return image, None
        key = (species, size_class, variant, flip, snowy, round(float(radius), 1))
        got = self._splits.get(key)
        if got is not None:
            return got
        base_key = (species, size_class, variant, flip, snowy)
        exact = self._exact.get(base_key)
        if exact is not None:
            self._splits[key] = exact
            return exact
        w, h = image.get_size()
        rgb = pygame.surfarray.array3d(image)
        alpha = pygame.surfarray.array_alpha(image)
        r = rgb[:, :, 0].astype(np.int16)
        g = rgb[:, :, 1].astype(np.int16)
        b = rgb[:, :, 2].astype(np.int16)
        green = ((alpha > 0) & (g >= 42) & (g > r + 12) & (g > b + 10))
        def _surface(keep):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.surfarray.blit_array(surf, rgb)
            pa = pygame.surfarray.pixels_alpha(surf)
            pa[:] = np.where(keep, alpha, 0)
            del pa
            return surf
        base = _surface(~green)
        canopy = _surface(green)
        self._splits[key] = (base, canopy)
        return base, canopy

    def _render(self, species: str, size_class: int, variant: int,
                snowy: bool = False):
        radius = SIZES[size_class]
        rng = random.Random((size_class * 7919) ^ (variant * 104729)
                            ^ (abs(hash(species)) & 0xFFFF) ^ (0x5EED ^ (1 if snowy else 0)))
        if species == "conifer":
            return self._conifer(radius, rng, variant, snowy)
        if species == "bare":
            return self._bare(radius, rng, variant, snowy)
        if species == "acacia":
            return self._acacia(radius, rng, variant)
        if species == "cactus":
            return self._cactus(radius, rng, variant)
        if species == "jungle":
            return self._broadleaf(radius, rng, variant, JUNGLE_PALETTE, 1.45,
                                   snowy, "jungle")
        if species == "ironwood":
            return self._broadleaf(radius, rng, variant, IRONWOOD, 1.0,
                                   snowy, "ironwood")
        return self._broadleaf(radius, rng, variant, PALETTE, 1.0, snowy,
                               "broadleaf")

    @staticmethod
    def _leaf_cluster(layer, x, y, size, rng, base, light=0.0):
        """A handful of individual leaves, never one solid green disc."""
        for j in range(3):
            ox = rng.uniform(-size * 0.55, size * 0.55)
            oy = rng.uniform(-size * 0.42, size * 0.42)
            rr = rng.uniform(size * 0.35, size * 0.62)
            col = _shade(base, light + rng.uniform(-0.35, 0.35))
            rect = (int(x + ox - rr), int(y + oy - rr * 0.62),
                    max(2, int(rr * 2.0)), max(2, int(rr * 1.25)))
            pygame.draw.ellipse(layer, _rgba(col, CANOPY_ALPHA), rect)
            pygame.draw.ellipse(layer, _rgba(_darken(col, 25), 180), rect, 1)

    def _make_branch_geo(self, cx, cy, ay, trunk_w, radius, rng, variant, color,
                         species, bend=0.0, wiggle=0.0, phase=0.0, top_y=None):
        """Build vector branches and leaf particles attached to them."""
        segs = []
        leaves = []
        if top_y is None:
            top_y = cy + 4
        def trunk_off(y):
            t = max(0.0, min(1.0, (ay - y) / max(1.0, ay - top_y)))
            return (bend * math.sin(math.pi * t)
                    + wiggle * math.sin(math.pi * 3.0 * t + phase))
        def rec(x0, y0, ang, length, width, depth, ax, ay0):
            width = max(1, int(width))
            ex = x0 + math.cos(ang) * length
            ey = y0 + math.sin(ang) * length * 0.78
            d0 = math.hypot(x0 - ax, y0 - ay0)
            d1 = math.hypot(ex - ax, ey - ay0)
            span = max(1.0, radius * 0.95)
            w0 = min(1.0, d0 / span)
            w1 = min(1.0, d1 / span)
            segs.append((x0, y0, ex, ey, width, w0, w1))
            # Leaves grow from the branch itself, not a painted canopy.
            if rng.random() < 0.42:
                t = rng.uniform(0.48, 0.98)
                lx = x0 + (ex - x0) * t
                ly = y0 + (ey - y0) * t
                leaves.append((lx, ly, radius * rng.uniform(0.028, 0.050),
                               w0 + (w1 - w0) * t,
                               _shade(color, rng.uniform(-0.30, 0.28))))
            if depth <= 0:
                if rng.random() < 0.25:
                    # bare twig fork
                    a = ang + rng.uniform(-0.7, 0.7)
                    tx = ex + math.cos(a) * length * 0.42
                    ty = ey + math.sin(a) * length * 0.35
                    segs.append((ex, ey, tx, ty, 1,
                                 min(1.0, math.hypot(ex - ax, ey - ay0) / span),
                                 min(1.0, math.hypot(tx - ax, ty - ay0) / span)))
                return
            for j in range(2 + (variant % 2)):
                ang2 = rng.uniform(0.0, 2.0 * math.pi)
                rr = length * rng.uniform(0.08, 0.22)
                leaves.append((ex + math.cos(ang2) * rr,
                               ey + math.sin(ang2) * rr,
                               radius * rng.uniform(0.030, 0.055),
                               w1,
                               _shade(color, rng.uniform(-0.32, 0.30))))
            forks = 2 + (1 if rng.random() < 0.25 else 0)
            for k in range(forks):
                spread = (k - (forks - 1) / 2.0) * rng.uniform(0.42, 0.72)
                rec(ex, ey, ang + spread + rng.uniform(-0.12, 0.12),
                    length * rng.uniform(0.48, 0.66),
                    max(1, int(width * 0.58)), depth - 1, ax, ay0)
        # Eight to eleven limbs leave the trunk at different heights.
        count = 8 + (variant % 4)
        for i in range(count):
            t = rng.uniform(0.18, 0.94)
            y0 = ay + (top_y - ay) * t
            x0 = cx + trunk_off(y0) + rng.uniform(-trunk_w * 0.20, trunk_w * 0.20)
            ang = (rng.uniform(-2.95, -1.65) if i % 2 == 0
                   else rng.uniform(-1.50, -0.18))
            rec(x0, y0, ang, radius * rng.uniform(0.36, 0.72),
                max(2, int(radius * rng.uniform(0.040, 0.062))),
                2 + (variant % 2), x0, y0)
        # THE APEX ALWAYS GROWS: a central leader and two short top sprays,
        # so the trunk never ends as a bare stick with leaves floating above.
        top_y0 = top_y
        top_x0 = cx + trunk_off(top_y0)
        top_angles = (-math.pi / 2.0 - 0.42, -math.pi / 2.0 + 0.42,
                      -math.pi / 2.0)
        for i, ang in enumerate(top_angles):
            if i == 2 and variant % 3 == 0:
                continue
            rec(top_x0, top_y0, ang + rng.uniform(-0.08, 0.08),
                radius * rng.uniform(0.28, 0.46),
                max(2, int(radius * 0.045)), 1, top_x0, top_y0)
        key = (str(species), round(float(radius), 2), int(variant))
        self._branch_geo[key] = (segs, leaves, radius * 2.0 + 20.0)
        return segs

    def branch_geo(self, radius, variant, species):
        return self._branch_geo.get((str(species), round(float(radius), 2),
                                     int(variant)))

    def static_branch(self, species, size_class, variant, flip, radius, image):
        """Cache the unbent branch/leaf layer for trees outside the wind."""
        key = (str(species), int(size_class), int(variant), bool(flip),
               round(float(radius), 1))
        got = self._static_branch.get(key)
        if got is not None:
            return got
        surf = pygame.Surface(image.get_size(), pygame.SRCALPHA)
        geo = self._branch_geo.get((str(species), round(float(SIZES[size_class]), 2),
                                    int(variant)))
        if geo is not None:
            segs, leaves, gw = geo
            scale = float(radius) / float(SIZES[size_class])
            for x0, y0, x1, y1, width, _w0, _w1 in segs:
                if flip:
                    x0, x1 = gw - x0, gw - x1
                pygame.draw.line(surf, (48, 32, 20),
                                 (x0 * scale, y0 * scale), (x1 * scale, y1 * scale),
                                 max(1, int(width * scale) + 1))
                if width >= 3:
                    pygame.draw.line(surf, (100, 72, 46),
                                     (x0 * scale, y0 * scale), (x1 * scale, y1 * scale),
                                     max(1, int(width * scale) - 1))
            for lx, ly, size, _lw, col in leaves:
                if flip:
                    lx = gw - lx
                r = max(1, int(size * scale))
                pygame.draw.ellipse(surf, col,
                                    (int(lx * scale - r), int(ly * scale - r * 0.65),
                                     max(2, r * 2), max(2, int(r * 1.3))))
        self._static_branch[key] = surf
        return surf

    def _broadleaf(self, radius, rng, variant, palette, height, snowy=False,
                   species="broadleaf"):
        trunk_h = radius * 1.5 * height
        thin = _trunk_factor(variant)
        trunk_w = max(3, int(radius * 0.26 / thin))
        base_w = max(4, int(trunk_w * 1.45))
        pad = 10
        w = radius * 2 + pad * 2
        h = int(trunk_h + radius) + pad * 2
        ax = w / 2.0
        ay = h - pad
        cx, cy = ax, ay - trunk_h

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        shadow_w, shadow_h = radius * 1.4 / thin, radius * 0.52 / thin
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - shadow_w / 2, ay - shadow_h / 2 + 5, shadow_w, shadow_h))

        bend = rng.uniform(-0.055, 0.055) * radius
        wiggle = rng.uniform(0.0, 0.014) * radius
        phase = rng.uniform(0.0, 2.0 * math.pi)
        trunk = _trunk_shape(cx, ay + 3, cy + 4, base_w, trunk_w * 0.90,
                             rng, radius, bend, wiggle, phase)
        pygame.draw.polygon(surf, (82, 58, 40), trunk)
        pygame.draw.polygon(surf, (46, 30, 18), trunk, 2)
        pygame.draw.polygon(surf, (72, 50, 32),
                            [(cx - base_w / 2, ay + 3), (cx - base_w / 2 - 7, ay + 7),
                             (cx - base_w / 2 + 3, ay - 3)])
        pygame.draw.polygon(surf, (72, 50, 32),
                            [(cx + base_w / 2, ay + 3), (cx + base_w / 2 + 7, ay + 7),
                             (cx + base_w / 2 - 3, ay - 3)])
        for i in range(3):
            xx = cx + (i - 1) * trunk_w * 0.3
            pygame.draw.line(surf, (58, 40, 26), (xx, ay), (xx, cy + 6), 2)
        pygame.draw.line(surf, (108, 80, 54),
                         (cx - trunk_w * 0.42, ay - 2), (cx - trunk_w * 0.3, cy + 8), 2)

        canopy = pygame.Surface((w, h), pygame.SRCALPHA)
        base = palette[variant % len(palette)]
        self._make_branch_geo(cx, cy, ay, trunk_w, radius, rng, variant, base,
                              species, bend, wiggle, phase)
        if snowy:                               # a dusting on the upper canopy
            for _ in range(rng.randint(10, 16)):
                a = rng.uniform(math.pi * 1.02, math.pi * 1.98)
                d = rng.uniform(0.0, radius * 0.74)
                bx = cx + math.cos(a) * d
                by = cy + math.sin(a) * d
                pygame.draw.circle(canopy, (236, 243, 252), (int(bx), int(by)),
                                   rng.randint(5, 10))
        combined = surf.copy()
        combined.blit(canopy, (0, 0))
        return combined, surf, canopy, ax, ay

    # -- other species ------------------------------------------------------
    def _conifer(self, radius, rng, variant, snowy=False):
        trunk_h = radius * 1.9
        pad = 10
        w = int(radius * 2 + pad * 2)
        h = int(trunk_h + radius * 0.9) + pad * 2
        ax = w / 2.0
        ay = h - pad
        cx = ax
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        thin = _trunk_factor(variant)
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.6 / thin, ay - radius * 0.2 / thin,
                             radius * 1.2 / thin, radius * 0.4 / thin))
        base = CONIFER[variant % len(CONIFER)]
        trunk_w = max(2, int(radius * 0.22 / _trunk_factor(variant)))
        pygame.draw.polygon(surf, (78, 54, 38),
                            _trunk_shape(cx, ay + 3, ay - trunk_h * 0.6,
                                         trunk_w, trunk_w * 0.64, rng, radius))
        canopy = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(4):                      # stacked needle skirts
            f = i / 3.0
            lw = radius * (1.0 - 0.60 * f)
            ly = ay - trunk_h * (0.16 + 0.72 * f)
            lh = radius * (0.85 - 0.26 * f)
            # A sparse row of needle clusters follows each skirt instead of a
            # filled triangle; the silhouette stays conical but reads as leaves.
            n = max(12, int(28 * radius / 72.0 * (1.0 - f * 0.35)))
            for j in range(n):
                u = (j + rng.uniform(-0.35, 0.35)) / max(1, n)
                bx = cx + (u * 2.0 - 1.0) * lw
                by = ly - (1.0 - abs(u * 2.0 - 1.0)) * lh + rng.uniform(-3.0, 3.0)
                # A needle cluster grows from a twig, never floats unsupported.
                pygame.draw.line(canopy, _darken(base, 28),
                                 (cx, ly), (bx, by), 1)
                TreeSprites._leaf_cluster(canopy, bx, by,
                                           radius * rng.uniform(0.035, 0.060),
                                           rng, base, 0.25 - f * 0.45)
            pygame.draw.line(canopy, _darken(base, 34),
                             (cx - lw, ly), (cx + lw, ly), 1)
        pygame.draw.circle(canopy, _lighten(base, 26), (int(cx), int(ay - trunk_h)), 3)
        if snowy:                               # snow settled on each skirt
            for i in range(4):
                f = i / 3.0
                lw = radius * (1.0 - 0.60 * f)
                ly = ay - trunk_h * (0.16 + 0.72 * f)
                lh = radius * (0.85 - 0.26 * f)
                cap = [(cx - lw * 0.86, ly - 1), (cx, ly - lh),
                       (cx + lw * 0.86, ly - 1),
                       (cx + lw * 0.40, ly - lh * 0.44),
                       (cx - lw * 0.40, ly - lh * 0.44)]
                pygame.draw.polygon(canopy, (235, 242, 251), cap)
        combined = surf.copy()
        combined.blit(canopy, (0, 0))
        return combined, surf, canopy, ax, ay

    def _bare(self, radius, rng, variant, snowy=False):
        trunk_h = radius * 1.6
        pad = 10
        w = int(radius * 2 + pad * 2)
        h = int(trunk_h + radius * 0.5) + pad * 2
        ax = w / 2.0
        ay = h - pad
        cx = ax
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        base = BARE[variant % len(BARE)]
        thin = _trunk_factor(variant)
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.5 / thin, ay - radius * 0.16 / thin,
                             radius / thin, radius * 0.34 / thin))
        tw = max(2, int(radius * 0.18 / thin))
        trunk = _trunk_shape(cx, ay + 3, ay - trunk_h,
                             tw * 2.8, tw * 1.10, rng, radius)
        pygame.draw.polygon(surf, base, trunk)
        pygame.draw.polygon(surf, _darken(base, 34), trunk, 2)
        for _ in range(rng.randint(5, 8)):      # skeletal branches
            t = rng.uniform(0.35, 0.98)
            by = ay - trunk_h * t
            ln = radius * rng.uniform(0.35, 0.8)
            ang = rng.uniform(-2.6, -0.5) if rng.random() < 0.5 else rng.uniform(0.5, 2.6)
            ex = cx + math.cos(ang) * ln
            ey = by + math.sin(ang) * ln * 0.7
            wdt = max(2, int(radius * 0.06))
            pygame.draw.line(surf, _darken(base, 18), (cx, by), (ex, ey), wdt)
            if snowy:                           # frost on top of the limb
                pygame.draw.line(surf, (240, 246, 252), (cx, by - 2), (ex, ey - 2),
                                 max(1, wdt - 1))
        return surf, ax, ay

    def _acacia(self, radius, rng, variant):
        trunk_h = radius * 1.7
        pad = 10
        w = int(radius * 2.1 + pad * 2)
        h = int(trunk_h + radius * 1.0) + pad * 2
        ax = w / 2.0
        ay = h - pad
        cx = ax
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        base = ACACIA[variant % len(ACACIA)]
        thin = _trunk_factor(variant)
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.8 / thin, ay - radius * 0.18 / thin,
                             radius * 1.6 / thin, radius * 0.36 / thin))
        wood = (92, 68, 46)
        tw = max(2, int(radius * 0.17 / thin))
        bend = rng.uniform(-0.055, 0.055) * radius
        wiggle = rng.uniform(0.0, 0.014) * radius
        phase = rng.uniform(0.0, 2.0 * math.pi)
        pygame.draw.polygon(surf, wood,
                            _trunk_shape(cx, ay + 3, ay - trunk_h,
                                         tw * 2.6, tw * 1.0, rng, radius,
                                         bend, wiggle, phase))
        cy0 = ay - trunk_h
        # The old pair of static spreading limbs lived on the trunk layer and
        # looked like two frozen top branches.  All acacia limbs now come from
        # the dynamic branch geometry below.
        canopy = pygame.Surface((w, h), pygame.SRCALPHA)
        # Acacia leaves are particles on the limbs too, not a painted umbrella.
        self._make_branch_geo(cx, cy0, ay, tw, radius, rng, variant, base,
                              "acacia", bend, wiggle, phase, cy0)
        combined = surf.copy()
        combined.blit(canopy, (0, 0))
        return combined, surf, canopy, ax, ay

    def _cactus(self, radius, rng, variant):
        pad = 10
        w = int(radius * 1.8 + pad * 2)
        h = int(radius * 2.2 + pad * 2)
        ax = w / 2.0
        ay = h - pad
        cx = ax
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        base = CACTUS[variant % len(CACTUS)]
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.5, ay - radius * 0.16, radius, radius * 0.32))
        bw = max(11, int(radius * 0.34))
        bh = radius * 1.7

        def column(x0, y0, cw, chh):
            pygame.draw.rect(surf, base, (int(x0), int(y0), int(cw), int(chh)),
                             border_radius=int(cw * 0.5))
            pygame.draw.rect(surf, _darken(base, 34),
                             (int(x0), int(y0), int(cw), int(chh)), 2,
                             border_radius=int(cw * 0.5))
            for i in (-1, 1):
                xx = x0 + cw * (0.5 + i * 0.24)
                pygame.draw.line(surf, _lighten(base, 18), (xx, y0 + cw * 0.5),
                                 (xx, y0 + chh - 3), 1)

        column(cx - bw / 2, ay - bh, bw, bh)
        for side in (-1, 1):
            if rng.random() < 0.6:
                aw = bw * 0.72
                y0 = ay - bh * rng.uniform(0.42, 0.68)
                x0 = cx + side * (bw * 0.5 + aw * 0.45)
                column(x0 - aw / 2, y0 - bh * 0.34, aw, bh * 0.34)
                pygame.draw.rect(surf, base,
                                 (int(min(cx, x0)), int(y0 - aw * 0.5),
                                  int(abs(x0 - cx) + aw * 0.5), int(aw)),
                                 border_radius=int(aw * 0.5))
        return surf, ax, ay


REGROW_SECONDS = 180.0     # a stump puts up a new tree in three minutes


class Tree:
    # A tree is a DATA POINT: where it stands, how big it is, what it looks
    # like. Its sprite is fetched from the shared atlas only when somebody is
    # actually looking at it. Seventeen thousand trees used to hold seventeen
    # thousand sprites between them.
    __slots__ = ("x", "y", "canopy_r", "trunk_rect", "sx", "sy",
                 "strikes", "strikes_needed", "felled", "felled_at",
                 "species", "size_class",
                 "variant", "flip", "snowy", "_atlas", "_save_uid",
                 "hit_until")

    def __init__(self, x, y, radius, variant, flip, atlas, species="broadleaf",
                 snowy=False):
        self.x = x
        self.y = y
        self.canopy_r = radius
        self.strikes = 0
        self.felled = False
        self.felled_at = 0.0
        self.hit_until = 0.0

        trunk_w = max(3, int(radius * 0.24 / _trunk_factor(variant)))
        # Only the base of the trunk is solid, so you can walk under the leaves.
        self.trunk_rect = pygame.Rect(x - trunk_w / 2, y - trunk_w * 0.6,
                                      trunk_w, trunk_w * 1.5)

        self._atlas = atlas
        self.species = species
        self.variant = variant
        self.flip = flip
        self.snowy = snowy
        self.size_class = min(range(len(SIZES)), key=lambda i: abs(SIZES[i] - radius))
        # IRONWOOD IS TWICE THE TREE: the same axe takes twice the swings.
        self.strikes_needed = 6 if species == "ironwood" else 3
        _img, ax, ay = atlas.get(species, self.size_class, variant, flip, snowy)
        self.sx, self.sy = ax, ay

    def blit_world(self, stump=None):
        """(surface, (world_x, world_y)) -- where this tree would be blitted,
        in world coordinates, so the band layer can bake it at its own leisure."""
        if self.felled and stump is not None:
            image, sx, sy = stump
        else:
            image, sx, sy = self._atlas.get(self.species, self.size_class,
                                            self.variant, self.flip, self.snowy,
                                            self.canopy_r)
        return image, (self.x - sx, self.y - sy)

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             stump=None) -> None:
        if self.felled and stump is not None:
            image, sx, sy = stump
        else:
            image, sx, sy = self._atlas.get(self.species, self.size_class,
                                            self.variant, self.flip, self.snowy,
                                            self.canopy_r)
        bx = self.x - cam_x
        by = self.y - cam_y
        if self.felled:
            screen.blit(image, (bx - sx, by - sy))
            return
        # MOVE ONLY THE GREEN PIXELS.  The trunk, branches, outline and
        # ground shadow stay exactly where they are; the leaf layer alone
        # drifts in the wind.  There is no horizontal cut across the tree.
        wx, wy = wind.sway(self.x, self.y, 1.0)
        wx *= 3.2
        wy *= 1.5
        if self.hit_until > _NOW:
            left = max(0.0, (self.hit_until - _NOW) / 0.5)
            wx += math.sin(_NOW * 72.0) * 9.0 * left
            wy += math.sin(_NOW * 91.0) * 2.5 * left
        base, canopy = self._atlas.split(
            self.species, self.size_class, self.variant, self.flip,
            self.snowy, self.canopy_r, image)
        screen.blit(base, (bx - sx, by - sy))
        if canopy is not None:
            screen.blit(canopy, (bx - sx + wx, by - sy + wy))
        # Dynamic branches/leaves only inside the local wind field; every
        # tree outside it uses one cached static branch layer.  This prevents
        # the whole visible forest paying for animation it cannot show.
        ox, oy = bx - sx, by - sy
        if wind.local_strength(self.x, self.y) > 0.0:
            geo = self._atlas.branch_geo(SIZES[self.size_class], self.variant,
                                          self.species)
            if geo is not None and self.species not in ("bare", "cactus", "conifer"):
                segs, leaves, gw = geo
                scale = self.canopy_r / float(SIZES[self.size_class])
                for x0, y0, x1, y1, width, w0, w1 in segs:
                    if self.flip:
                        x0, x1 = gw - x0, gw - x1
                    p0 = (ox + x0 * scale + wx * w0, oy + y0 * scale + wy * w0)
                    p1 = (ox + x1 * scale + wx * w1, oy + y1 * scale + wy * w1)
                    pygame.draw.line(screen, (48, 32, 20), p0, p1,
                                     max(1, int(width * scale) + 1))
                    if width >= 3:
                        pygame.draw.line(screen, (100, 72, 46), p0, p1,
                                         max(1, int(width * scale) - 1))
                for lx, ly, size, lw, col in leaves:
                    if self.flip:
                        lx = gw - lx
                    px = ox + lx * scale + wx * lw
                    py = oy + ly * scale + wy * lw
                    r = max(1, int(size * scale))
                    pygame.draw.ellipse(screen, col,
                                        (int(px - r), int(py - r * 0.65),
                                         max(2, r * 2), max(2, int(r * 1.3))))
        else:
            static = self._atlas.static_branch(self.species, self.size_class,
                                                self.variant, self.flip,
                                                self.canopy_r, image)
            screen.blit(static, (ox, oy))
        wind.draw_leaves(screen, self.x, self.y, cam_x, cam_y,
                         self.canopy_r)


class Trees:
    def __init__(self, seed: int = 20240501) -> None:
        self.seed = seed
        self._cache: dict[tuple[int, int], Tree | None] = {}
        self._presence: dict[tuple[int, int], tuple | None] = {}
        self._atlas = TreeSprites()
        self._stumps: list[Tree] = []      # felled, waiting to grow back

    # -- felling and regrowth ------------------------------------------------
    def fell(self, tree, now: float) -> None:
        """Drop a tree. It leaves a stump and grows back in three minutes."""
        tree.felled = True
        tree.felled_at = now
        tree.strikes = 0
        self._stumps.append(tree)

    def stumps(self) -> list:
        """The felled trees waiting to come back -- what a save must keep."""
        return [t for t in self._stumps if getattr(t, "felled", False)]

    def remember_stump(self, tree) -> None:
        """A tree that was already a stump when the world was loaded."""
        if tree is None or not getattr(tree, "felled", False):
            return
        if tree not in self._stumps:
            self._stumps.append(tree)

    def update(self, now: float) -> None:
        """Put the woods back: any stump older than REGROW_SECONDS sprouts."""
        global _NOW
        _NOW = float(now)
        if not self._stumps:
            return
        still = []
        for tree in self._stumps:
            if now - tree.felled_at >= REGROW_SECONDS:
                tree.felled = False
                tree.strikes = 0
            else:
                still.append(tree)
        self._stumps = still

    # -- generation ---------------------------------------------------------
    def _village_clearance(self, x: float, y: float) -> float:
        """How far BEYOND a village's treeless ground this point stands.

        A capital is twice the village, so it keeps twice the ground clear.
        The village's own size decides it -- the same rule as the village
        itself uses, so a capital clears exactly as much ground as it stands on.
        """
        return village_clearance(x, y, self.seed)

    _CLUMP: dict = {}

    def _clump(self, x: float, y: float) -> float:
        """The clumping noise, memoised: it is static and every tree cell asks
        for it, and a cell that has already been worked out asks again."""
        key = (x, y)
        got = self._CLUMP.get(key)
        if got is None:
            got = float(fbm(np.float32(x * 0.0045), np.float32(y * 0.0045),
                            self.seed + 2, octaves=3))
            if len(self._CLUMP) < 400000:
                self._CLUMP[key] = got
        return got

    def _position(self, cx: int, cy: int):
        """Where a tree would stand in this cell, or None if there is none."""
        key = (cx, cy)
        if key in self._presence:
            return self._presence[key]
        self._precompute_block(cx, cy)
        return self._presence.get(key)

    _PRE = 32

    def _precompute_block(self, cx: int, cy: int) -> None:
        """Generate a whole _PRE x _PRE block of tree cells at once.

        The expensive part of every tree cell is four scalar noise calls
        (coast, temperature, humidity, clump) -- each a few numpy fbm octaves,
        each paid per cell. One cell costs ~1 ms of numpy-overhead; a block is
        one vectorised call per noise field, so 256 cells cost about the same
        as one. The cheap per-cell work (hash, rng, species) stays a loop, in
        the same order as the old `_position`, so the world is identical."""
        x0 = (cx // self._PRE) * self._PRE
        y0 = (cy // self._PRE) * self._PRE
        x1 = x0 + self._PRE - 1
        y1 = y0 + self._PRE - 1
        cells = [(ix, iy) for iy in range(y0, y1 + 1) for ix in range(x0, x1 + 1)
                 if (ix, iy) not in self._presence]
        if not cells:
            return
        rows = []
        for ix, iy in cells:
            code = _hash(ix, iy, self.seed)
            rng = _FastRNG(code)
            x = ix * CELL + CELL / 2.0 + rng.uniform(-JIT, JIT)
            y = iy * CELL + CELL / 2.0 + rng.uniform(-JIT, JIT)
            rows.append((ix, iy, code, rng, x, y))
        ax = np.array([r[4] for r in rows], np.float32)
        ay = np.array([r[5] for r in rows], np.float32)
        temps = np.asarray(biomes.temperature(ax, ay, self.seed), np.float32).ravel()
        hums = np.asarray(biomes.humidity(ax, ay, self.seed), np.float32).ravel()
        coasts = np.asarray(coast_x(ay, self.seed), np.float32).ravel()
        clumps = np.asarray(fbm(ax * 0.0045, ay * 0.0045, self.seed + 2,
                                octaves=3), np.float32).ravel()
        for k, (ix, iy, code, rng, x, y) in enumerate(rows):
            t = float(temps[k])
            h = float(hums[k])
            if x > float(coasts[k]):
                self._presence[(ix, iy)] = None
                continue
            if biomes.is_barren(x, y):
                # BARREN ROCKS: thin, hard ironwood.  No climate forest here.
                if rng.random() >= 0.14:
                    self._presence[(ix, iy)] = None
                    continue
                self._presence[(ix, iy)] = (x, y, code, "ironwood", False)
                continue
            _dark, _lite, spec, dens = biomes.mix(t, h)
            density = dens * (0.45 + 0.75 * float(clumps[k]))
            beyond = self._village_clearance(x, y)
            if beyond < FADE_BAND:
                density *= _smoothstep(beyond, 0.0, FADE_BAND)
            if rng.random() >= density * SPAWN:
                self._presence[(ix, iy)] = None
                continue
            species = biomes.pick_species(spec, rng)
            self._presence[(ix, iy)] = (x, y, code, species, t < 0.30)

    def tree(self, cx: int, cy: int) -> Tree | None:
        key = (cx, cy)
        if key in self._cache:
            got = self._cache[key]
            return got
        here = self._position(cx, cy)
        if here is None:
            self._cache[key] = None
            return None
        x, y, code, species, snowy = here

        # Nearest neighbouring tree: the 8 cells around this one are enough,
        # because two trees two cells apart (>= ~324 px) can never overlap
        # (max crown radius is 120).
        nearest = 1e18
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                if ox == 0 and oy == 0:
                    continue
                other = self._position(cx + ox, cy + oy)
                if other is not None:
                    nearest = min(nearest, math.hypot(other[0] - x, other[1] - y))
        # Half the distance to the nearest neighbour => canopies touch, never
        # overlap. Then add variation: mostly big crowns, a few smaller ones.
        base = R_MAX if nearest > 1e17 else min(R_MAX, nearest * 0.5)
        rng = random.Random(code ^ 0x5EED)
        roll = rng.random()
        if roll < 0.75:
            factor = rng.uniform(0.90, 1.0)
        elif roll < 0.93:
            factor = rng.uniform(0.72, 0.90)
        else:
            factor = rng.uniform(0.45, 0.72)
        radius = max(R_MIN, min(R_MAX, base * factor))

        result = Tree(x, y, radius, rng.randrange(VARIANTS), rng.random() < 0.5,
                      self._atlas, species, snowy)
        self._cache[key] = result
        return result

    # -- queries ------------------------------------------------------------
    def plant(self, x: float, y: float, radius: float = 74.0,
              variant: int = 0, species: str = "conifer",
              snowy: bool = True) -> "Tree":
        """A TREE PUT THERE BY HAND, in the game's own tree list.

        It has a trunk you cannot walk through, it stands in `visible()` and
        `near()` like any other, and an axe fells it like any other. This is how
        the camp's fifty are planted: real trees, in rows, not painted pines.
        """
        t = Tree(x, y, radius, variant % 4, bool(variant & 1), self._atlas,
                 species, snowy)
        if not hasattr(self, "_planted") or self._planted is None:
            self._planted = []
        self._planted.append(t)
        return t

    def _planted_near(self, x0, y0, x1, y1):
        out = []
        for t in getattr(self, "_planted", ()) or ():
            if x0 <= t.x <= x1 and y0 <= t.y <= y1:
                out.append(t)
        return out

    def visible(self, cam_x: float, cam_y: float, vw: int, vh: int,
                margin: float = 95.0) -> list[Tree]:
        x0 = int(math.floor((cam_x - margin) / CELL))
        x1 = int(math.floor((cam_x + vw + margin) / CELL))
        y0 = int(math.floor((cam_y - margin) / CELL))
        y1 = int(math.floor((cam_y + vh + margin) / CELL))
        out = []
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                tree = self.tree(cx, cy)
                if tree is not None:
                    out.append(tree)
        out.extend(self._planted_near(cam_x - margin, cam_y - margin,
                                      cam_x + vw + margin, cam_y + vh + margin))
        return out

    def near(self, x: float, y: float, radius: float) -> list[Tree]:
        x0 = int(math.floor((x - radius) / CELL))
        x1 = int(math.floor((x + radius) / CELL))
        y0 = int(math.floor((y - radius) / CELL))
        y1 = int(math.floor((y + radius) / CELL))
        out = []
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                tree = self.tree(cx, cy)
                if tree is not None:
                    if math.hypot(tree.x - x, tree.y - y) <= radius + tree.canopy_r:
                        out.append(tree)
        # ...AND THE PLANTED ONES. `near()` is what the axe asks, and it only
        # walked the procedural cells, so the camp's fifty trees were real,
        # solid, drawn -- and impossible to chop.
        for t in getattr(self, "_planted", ()) or ():
            if math.hypot(t.x - x, t.y - y) <= radius + t.canopy_r:
                out.append(t)
        return out

    def foliage(self, x: float, y: float) -> float:
        factor = 0.0
        for tree in self.near(x, y, 70.0):
            if tree.felled:
                continue
            d = math.hypot(tree.x - x, tree.y - y)
            if d < tree.canopy_r:
                factor = max(factor, 1.0 - d / tree.canopy_r)
        return min(1.0, factor)

    def stump(self):
        return self._atlas.stump()
