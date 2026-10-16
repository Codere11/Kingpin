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
from noise import fbm
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


def _hash(cx, cy, seed):
    h = (cx * 73856093) ^ (cy * 19349663) ^ (seed * 2654435761)
    h &= 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h


class TreeSprites:
    """Shared, pre-rendered tree sprites."""

    def __init__(self) -> None:
        self._cache: dict[tuple[int, int, bool], tuple] = {}
        self._scaled: dict[tuple, tuple] = {}     # rescaled, shared
        self._stump = None

    def stump(self):
        if self._stump is None:
            r, pad = 17, 5
            w = h = r * 2 + pad * 2
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            cx, cy = w / 2.0, h - pad
            pygame.draw.ellipse(surf, (12, 24, 12, 70), (cx - 20, cy - 7, 40, 14))
            pygame.draw.ellipse(surf, (112, 78, 46), (cx - r, cy - r * 0.85, r * 2, r * 1.7))
            pygame.draw.ellipse(surf, (70, 46, 26), (cx - r, cy - r * 0.85, r * 2, r * 1.7), 2)
            pygame.draw.ellipse(surf, (188, 152, 106), (cx - r * 0.7, cy - r * 0.6, r * 1.4, r * 1.2))
            pygame.draw.ellipse(surf, (150, 118, 80), (cx - r * 0.35, cy - r * 0.3, r * 0.7, r * 0.6))
            pygame.draw.line(surf, (150, 118, 80), (cx, cy - r * 0.55), (cx + r * 0.55, cy + r * 0.1), 2)
            self._stump = (surf, cx, cy)
        return self._stump

    def get(self, species: str, size_class: int, variant: int, flip: bool,
            snowy: bool = False, radius: float = None):
        key = (species, size_class, variant, flip, snowy)
        sprite = self._cache.get(key)
        if sprite is None:
            sprite = self._render(species, size_class, variant, snowy)
            if flip:
                surface, ax, ay = sprite
                sprite = (pygame.transform.flip(surface, True, False), ax, ay)
            self._cache[key] = sprite
        if radius is None:
            return sprite
        scale = radius / SIZES[size_class]
        if abs(scale - 1.0) <= 0.02:
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
        return got

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
            return self._broadleaf(radius, rng, variant, JUNGLE_PALETTE, 1.45, snowy)
        return self._broadleaf(radius, rng, variant, PALETTE, 1.0, snowy)

    def _broadleaf(self, radius, rng, variant, palette, height, snowy=False):
        trunk_h = radius * 1.5 * height
        trunk_w = max(13, int(radius * 0.26))
        base_w = trunk_w * 1.7
        pad = 10
        w = radius * 2 + pad * 2
        h = int(trunk_h + radius) + pad * 2
        ax = w / 2.0
        ay = h - pad
        cx, cy = ax, ay - trunk_h

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        shadow_w, shadow_h = radius * 1.4, radius * 0.52
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - shadow_w / 2, ay - shadow_h / 2 + 5, shadow_w, shadow_h))

        trunk = [(cx - base_w / 2, ay + 3), (cx + base_w / 2, ay + 3),
                 (cx + trunk_w * 0.45, cy + 4), (cx - trunk_w * 0.45, cy + 4)]
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
        alpha = CANOPY_ALPHA
        pygame.draw.circle(canopy, _rgba(_darken(base, 22), alpha),
                           (int(cx), int(cy)), radius)
        for _ in range(rng.randint(22, 30)):
            angle = rng.uniform(0.0, 2.0 * math.pi)
            dist = rng.uniform(0.0, radius * 0.62)
            bx = cx + math.cos(angle) * dist
            by = cy + math.sin(angle) * dist
            br = rng.uniform(radius * 0.34, radius * 0.55)
            light = 0.5 - (bx - cx) / (2.6 * radius) - (by - cy) / (2.6 * radius)
            pygame.draw.circle(canopy, _rgba(_shade(base, light), alpha),
                               (int(bx), int(by)), int(br))
        for _ in range(9):
            angle = rng.uniform(math.pi * 0.75, math.pi * 1.55)
            dist = rng.uniform(0.0, radius * 0.7)
            hx = cx + math.cos(angle) * dist
            hy = cy + math.sin(angle) * dist
            pygame.draw.circle(canopy, _rgba(_lighten(base, 30), alpha),
                               (int(hx), int(hy)), rng.randint(3, 7))
        for _ in range(12):
            angle = rng.uniform(0.0, 2.0 * math.pi)
            dist = rng.uniform(0.0, radius * 0.72)
            gx = cx + math.cos(angle) * dist
            gy = cy + math.sin(angle) * dist
            pygame.draw.ellipse(canopy, _rgba(_darken(base, 34), alpha),
                                (gx - 5, gy - 3, 10, 6))
        pygame.draw.circle(canopy, _rgba(_darken(base, 46), min(255, alpha + 20)),
                           (int(cx), int(cy)), radius, 3)
        surf.blit(canopy, (0, 0))
        if snowy:                               # a dusting on the upper canopy
            for _ in range(rng.randint(10, 16)):
                a = rng.uniform(math.pi * 1.02, math.pi * 1.98)
                d = rng.uniform(0.0, radius * 0.74)
                bx = cx + math.cos(a) * d
                by = cy + math.sin(a) * d
                pygame.draw.circle(surf, (236, 243, 252), (int(bx), int(by)),
                                   rng.randint(5, 10))
        return surf, ax, ay

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
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.6, ay - radius * 0.2, radius * 1.2, radius * 0.4))
        base = CONIFER[variant % len(CONIFER)]
        trunk_w = max(9, int(radius * 0.22))
        pygame.draw.polygon(surf, (78, 54, 38),
                            [(cx - trunk_w / 2, ay + 3), (cx + trunk_w / 2, ay + 3),
                             (cx + trunk_w * 0.32, ay - trunk_h * 0.6),
                             (cx - trunk_w * 0.32, ay - trunk_h * 0.6)])
        for i in range(4):                      # stacked skirts
            f = i / 3.0
            lw = radius * (1.0 - 0.60 * f)
            ly = ay - trunk_h * (0.16 + 0.72 * f)
            lh = radius * (0.85 - 0.26 * f)
            pts = [(cx - lw, ly), (cx + lw, ly), (cx, ly - lh)]
            pygame.draw.polygon(surf, _shade(base, 0.30 - 0.62 * f), pts)
            pygame.draw.polygon(surf, _darken(base, 34), pts, 2)
        pygame.draw.circle(surf, _lighten(base, 26), (int(cx), int(ay - trunk_h)), 3)
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
                pygame.draw.polygon(surf, (235, 242, 251), cap)
        return surf, ax, ay

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
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.5, ay - radius * 0.16, radius, radius * 0.34))
        tw = max(7, int(radius * 0.18))
        trunk = [(cx - tw * 1.4, ay + 3), (cx + tw * 1.4, ay + 3),
                 (cx + tw * 0.55, ay - trunk_h), (cx - tw * 0.55, ay - trunk_h)]
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
        pygame.draw.ellipse(surf, (12, 24, 12, 70),
                            (cx - radius * 0.8, ay - radius * 0.18, radius * 1.6, radius * 0.36))
        wood = (92, 68, 46)
        tw = max(7, int(radius * 0.17))
        pygame.draw.polygon(surf, wood,
                            [(cx - tw * 1.3, ay + 3), (cx + tw * 1.3, ay + 3),
                             (cx + tw * 0.5, ay - trunk_h), (cx - tw * 0.5, ay - trunk_h)])
        cy0 = ay - trunk_h
        for side in (-1.0, 1.0):                # two spreading limbs
            pygame.draw.line(surf, wood, (cx, cy0 + radius * 0.18),
                             (cx + side * radius * 0.75, cy0 - radius * 0.22),
                             max(3, int(radius * 0.09)))
        canopy = pygame.Surface((w, h), pygame.SRCALPHA)
        cw, ch = radius * 1.9, radius * 0.72
        top = cy0 - radius * 0.5
        pygame.draw.ellipse(canopy, _rgba(_darken(base, 20), CANOPY_ALPHA),
                            (cx - cw / 2, top, cw, ch))
        for _ in range(rng.randint(12, 18)):
            bx = cx + rng.uniform(-cw / 2, cw / 2) * 0.9
            by = top + ch / 2 + rng.uniform(-ch / 2, ch / 2) * 0.8
            r = rng.uniform(radius * 0.22, radius * 0.36)
            pygame.draw.circle(canopy, _rgba(_shade(base, rng.uniform(-0.3, 0.5)),
                                             CANOPY_ALPHA), (int(bx), int(by)), int(r))
        pygame.draw.ellipse(canopy, _rgba(_darken(base, 40), min(255, CANOPY_ALPHA + 20)),
                            (cx - cw / 2, top, cw, ch), 2)
        surf.blit(canopy, (0, 0))
        return surf, ax, ay

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
                 "strikes", "felled", "felled_at", "species", "size_class",
                 "variant", "flip", "snowy", "_atlas")

    def __init__(self, x, y, radius, variant, flip, atlas, species="broadleaf",
                 snowy=False):
        self.x = x
        self.y = y
        self.canopy_r = radius
        self.strikes = 0
        self.felled = False
        self.felled_at = 0.0

        trunk_w = max(10, int(radius * 0.24))
        # Only the base of the trunk is solid, so you can walk under the leaves.
        self.trunk_rect = pygame.Rect(x - trunk_w / 2, y - trunk_w * 0.6,
                                      trunk_w, trunk_w * 1.5)

        self._atlas = atlas
        self.species = species
        self.variant = variant
        self.flip = flip
        self.snowy = snowy
        self.size_class = min(range(len(SIZES)), key=lambda i: abs(SIZES[i] - radius))
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
        screen.blit(image, (self.x - cam_x - sx, self.y - cam_y - sy))


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

    def update(self, now: float) -> None:
        """Put the woods back: any stump older than REGROW_SECONDS sprouts."""
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
        code = _hash(cx, cy, self.seed)
        rng = random.Random(code)
        x = cx * CELL + CELL / 2.0 + rng.uniform(-JIT, JIT)
        y = cy * CELL + CELL / 2.0 + rng.uniform(-JIT, JIT)
        temp = float(biomes.temperature(x, y, self.seed))
        hum = float(biomes.humidity(x, y, self.seed))
        clump = self._clump(x, y)
        _dark, _lite, spec, dens = biomes.mix(temp, hum)
        density = dens * (0.45 + 0.75 * clump)      # biome density, patchy
        beyond = self._village_clearance(x, y)
        if beyond < FADE_BAND:
            density *= _smoothstep(beyond, 0.0, FADE_BAND)
        if rng.random() >= density * SPAWN:
            self._presence[key] = None
            return None
        species = biomes.pick_species(spec, rng)
        result = (x, y, code, species, temp < 0.30)
        self._presence[key] = result
        return result

    def tree(self, cx: int, cy: int) -> Tree | None:
        key = (cx, cy)
        if key in self._cache:
            return self._cache[key]
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
