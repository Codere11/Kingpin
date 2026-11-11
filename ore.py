"""Iron ore chunks.

Distribution is driven by a low-frequency noise field, so there are rich veins
here and nothing at all for miles there; within a rich area the chunks are
still sparse. Everything is deterministic from the world seed -- only the
chunks the player has mined are stored.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pygame

from noise import fbm
from village import (SPACING, VILLAGE_SCALE, village_center,
                     village_clearance)

CELL = 260                       # one chunk is possible per cell
JIT = 66                         # position jitter within a cell
FIELD_SCALE = 0.00030            # low-frequency iron regions
FIELD_CUT = 0.62                 # only above this does iron grow at all
CHANCE_IN_FIELD = 0.17           # fraction of cells in a rich area with a chunk (halved)
VILLAGE_CLEAR = 520.0 * VILLAGE_SCALE + 260.0
STRIKES = 80                     # hits to mine a chunk out, one ore per hit
VARIANTS = 5


def _hash(cx, cy, seed):
    h = (cx * 73856093) ^ (cy * 19349663) ^ (seed * 2654435761)
    h &= 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h


class OreSprites:
    """Pre-rendered rock chunks with iron flecks in them."""

    def __init__(self) -> None:
        self._cache: dict[int, pygame.Surface] = {}

    def get(self, variant: int) -> pygame.Surface:
        img = self._cache.get(variant)
        if img is not None:
            return img
        rng = random.Random(0x1200 + variant * 7919)
        pad = 8
        w, h = 52, 46
        surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        cx, cy = w / 2 + pad, h / 2 + pad
        base = (120, 120, 128)
        body = []
        n = rng.randint(7, 9)
        for i in range(n):
            a = math.tau * i / n
            rad = (w * 0.42) * rng.uniform(0.72, 1.0)
            body.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad * 0.82))
        pygame.draw.polygon(surf, (32, 30, 34), body)               # shadow
        inner = [(px, py - 4) for px, py in body]
        pygame.draw.polygon(surf, base, inner)
        pygame.draw.polygon(surf, (74, 74, 84), inner, 2)
        top = [(px, py - 5) for px, py in inner if py < cy]
        if len(top) >= 3:
            pygame.draw.polygon(surf, (146, 146, 154), top)
        for _ in range(rng.randint(4, 7)):                          # iron flecks
            fx = cx + rng.uniform(-w * 0.30, w * 0.30)
            fy = cy + rng.uniform(-h * 0.26, h * 0.26)
            rr = rng.uniform(2.6, 4.4)
            pygame.draw.circle(surf, (168, 96, 52), (int(fx), int(fy)), int(rr))
            pygame.draw.circle(surf, (214, 150, 88), (int(fx), int(fy)), int(rr * 0.55))
        self._cache[variant] = surf
        return surf


class Chunk:
    __slots__ = ("x", "y", "cell", "variant", "strikes", "mined", "rect")

    def __init__(self, x, y, cell, variant):
        self.x = x
        self.y = y
        self.cell = cell
        self.variant = variant
        self.strikes = 0
        self.mined = False
        self.rect = pygame.Rect(int(x - 17), int(y - 15), 34, 30)

    @property
    def radius(self):
        return 17


class OreField:
    def __init__(self, seed: int = 20240501) -> None:
        self.seed = seed
        self.mined: set[tuple[int, int]] = set()
        self._sprites = OreSprites()
        self._presence: dict[tuple[int, int], object] = {}
        self._cache: dict[tuple[int, int], Chunk | None] = {}

    def _village_distance(self, x, y):
        """Distance to the nearest village's cleared SQUARE -- the same rule
        the village, its fence, its trees and its wolves all use."""
        return village_clearance(x, y, self.seed)

    def _position(self, cx, cy):
        key = (cx, cy)
        if key in self._presence:
            return self._presence[key]
        code = _hash(cx, cy, self.seed)
        rng = random.Random(code)
        x = cx * CELL + CELL / 2.0 + rng.uniform(-JIT, JIT)
        y = cy * CELL + CELL / 2.0 + rng.uniform(-JIT, JIT)
        # IRON LIVES IN THE SNOW ALONE: the plains and the desert have none.
        try:
            import biomes as _bio
            if _bio.temperature(x, y, self.seed) >= 0.32:
                self._presence[key] = None
                return None
        except Exception:
            pass
        field = float(fbm(np.float32(x * FIELD_SCALE), np.float32(y * FIELD_SCALE),
                          self.seed + 3, octaves=3))
        if field < FIELD_CUT:
            self._presence[key] = None
            return None
        if rng.random() >= CHANCE_IN_FIELD:
            self._presence[key] = None
            return None
        if self._village_distance(x, y) < 0.0:
            self._presence[key] = None
            return None
        result = (x, y, code, rng.randrange(VARIANTS))
        self._presence[key] = result
        return result

    def chunk(self, cx, cy) -> Chunk | None:
        key = (cx, cy)
        if key in self._cache:
            return self._cache[key]
        here = self._position(cx, cy)
        if here is None:
            self._cache[key] = None
            return None
        x, y, _code, variant = here
        # NO IRON IN THE CAMP, AND NONE ON THE PERMANENT WAY.
        try:
            import gulag
            if gulag.inside(x, y, 120.0):
                self._cache[key] = None
                return None
        except Exception:
            pass
        try:
            import rail
            if rail.blocked(x, y, 34.0):
                self._cache[key] = None
                return None
        except Exception:
            pass
        chunk = Chunk(x, y, key, variant)
        if key in self.mined:
            chunk.mined = True
        self._cache[key] = chunk
        return chunk

    # -- queries ------------------------------------------------------------
    def visible(self, cam_x: float, cam_y: float, vw: int, vh: int,
                margin: float = 70.0):
        x0 = int(math.floor((cam_x - margin) / CELL))
        x1 = int(math.floor((cam_x + vw + margin) / CELL))
        y0 = int(math.floor((cam_y - margin) / CELL))
        y1 = int(math.floor((cam_y + vh + margin) / CELL))
        out = []
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                chunk = self.chunk(cx, cy)
                if chunk is not None and not chunk.mined:
                    out.append(chunk)
        return out

    def near(self, x: float, y: float, radius: float):
        x0 = int(math.floor((x - radius) / CELL))
        x1 = int(math.floor((x + radius) / CELL))
        y0 = int(math.floor((y - radius) / CELL))
        y1 = int(math.floor((y + radius) / CELL))
        out = []
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                chunk = self.chunk(cx, cy)
                if chunk is not None and not chunk.mined:
                    if math.hypot(chunk.x - x, chunk.y - y) <= radius + 20.0:
                        out.append(chunk)
        return out

    def draw(self, screen, cam_x, cam_y, chunk) -> None:
        img = self._sprites.get(chunk.variant)
        screen.blit(img, (chunk.x - cam_x - img.get_width() / 2,
                          chunk.y - cam_y - img.get_height() * 0.72))
