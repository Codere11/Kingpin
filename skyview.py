"""skyview.py -- what the ground looks like from up here.

THE RULE THIS IMPLEMENTS, in the words it was asked for:

    displaying 100 1x1 blocks at z=100 fits the same screen amount as one 1x1
    block at z=0, and requires the same proportional compute

So the picture is ALWAYS composed into the same fixed grid -- 320 by 180 --
whatever height he is at. Only the SPAN that grid covers grows: one more metre
of height shows one more metre of ground each way, so the top of the staircase
looks at nearly twice the world the bottom does, through the same 57,600
samples. More world through the same grid IS the blur, so asking for it to be
blurred and asking for it to be cheap are the same request -- there is no
filter here at all, only resolution.

WHY IT IS BAKED RATHER THAN SAMPLED. The first cut did the honest thing and
sampled temperature and humidity across the grid every frame: 105 ms of it,
six frames a second, because fbm is expensive and 57,600 samples is a lot of
it. But NONE OF THIS TERRAIN MOVES. So it is baked into tiles -- 64 by 64
samples, 6 world pixels apart, cached -- and the per-frame work is a handful of
blits and two smoothscales, which is nothing. A tile is built once and paid for
by every frame that sees it afterwards, and at most BUDGET of them are built in
any one frame so going up a mountain never hitches.

(the same shape as ground.GroundRenderer, for the same reason.)
"""

from __future__ import annotations

import math

import numpy as np
import pygame

import biomes
import terrain

GRID_W = 320                 # the picture is always this big...
GRID_H = 180                 # ...whatever it covers
COARSE = 6.0                 # world pixels between samples in a baked tile
TILE_S = 64                  # samples a side of one tile
TILE_PX = COARSE * TILE_S    # so a tile covers 384 world pixels
BUDGET = 2                   # new tiles per frame, so nothing hitches
SPAN0 = 760.0                # world pixels across the view at ground level

# The colour a tile shows for the frame or two before it is baked.
_PENDING = (48, 52, 44)


class SkyView:
    """The ground below, from however high he is."""

    def __init__(self, world) -> None:
        self.world = world
        self._tiles: dict = {}
        self._xs = np.arange(TILE_S, dtype=np.float32) * COARSE + COARSE * 0.5
        self._ys = self._xs
        self.tiles_baked = 0
        self.last_tiles = 0

    def span_at(self, z: float) -> float:
        """How much ground is across the view at height z.

        ONE METRE UP, ONE METRE MORE EACH WAY: the flat span plus two metres
        for every metre climbed.
        """
        return SPAN0 + 2.0 * max(0.0, float(z)) * terrain.METRE

    # -- the baked ground ---------------------------------------------------
    def _bake(self, tx: int, ty: int) -> pygame.Surface:
        x0 = tx * TILE_PX
        y0 = ty * TILE_PX
        X, Y = np.meshgrid(x0 + self._xs, y0 + self._ys)
        t = self.world.temperature(X, Y)
        h = self.world.humidity(X, Y)
        warp = (t - 0.5) * 260.0
        clump = biomes.fbm((X + warp) * 0.018, (Y + warp) * 0.018,
                           self.world.seed + 2, octaves=2)
        dark = biomes.blend_array("dark", t, h)
        lite = biomes.blend_array("lite", t, h)
        mixv = np.clip(0.44 + 0.56 * clump, 0.0, 1.0)[..., None]
        col = dark * (1.0 - mixv) + lite * mixv
        col = col * (0.90 + 0.18 * clump)[..., None]

        # THE HEIGHT, the only reason any of this exists. Higher ground is
        # brighter and every step down gets a dark lip -- a staircase seen from
        # directly above with no shading is a flat square of colour.
        hz = terrain.height_array(X, Y)
        # ASYMPTOTIC, NOT MULTIPLIED. Times-1.085 is bright and climbs to a
        # clip at nine metres, where the whole summit flattens into one white
        # square -- measured at (254,254,151), the very top of the range. This
        # approaches white and never reaches it, so every step keeps its edge.
        col = col + (255.0 - col) * np.minimum(1.0, hz * 0.10)[..., None]
        drop = terrain.height_array(X, Y - COARSE * 1.5)
        col[drop != hz] *= 0.52
        arr = np.clip(col, 0.0, 255.0).astype(np.uint8)
        # make_surface wants [x][y][rgb]; everything above is [y][x][rgb].
        surf = pygame.surfarray.make_surface(arr.transpose(1, 0, 2))
        self._tiles[(tx, ty)] = surf
        self.tiles_baked += 1
        return surf

    def prebake(self, cx: float, cy: float, z: float) -> None:
        """Bake everything the view will need, before it is ever drawn.

        For the frame or two after a jump there is nothing behind him yet, and
        a placeholder square in the middle of a jump is worse than a slow one.
        """
        span = self.span_at(z)
        left = int(math.floor((cx - span * 0.5) / TILE_PX))
        top = int(math.floor((cy - span * 0.5) / TILE_PX))
        right = int(math.floor((cx + span * 0.5) / TILE_PX))
        bottom = int(math.floor((cy + span * 0.5) / TILE_PX))
        for ty in range(top, bottom + 1):
            for tx in range(left, right + 1):
                if (tx, ty) not in self._tiles:
                    self._bake(tx, ty)

    # -- the per-frame work -------------------------------------------------
    def render(self, cx: float, cy: float, z: float,
               size) -> pygame.Surface:
        span = self.span_at(z)
        # ALIGNED TO THE TILE GRID, so tiles butt together exactly and no seam
        # shows. The view shifts by less than one sample doing it.
        left = math.floor((cx - span * 0.5) / COARSE) * COARSE
        top = math.floor((cy - span * 0.5) / COARSE) * COARSE
        nw = int(math.ceil(span / COARSE)) + 2
        nh = int(math.ceil(span / COARSE)) + 2
        sheet = pygame.Surface((nw, nh))
        sheet.fill(_PENDING)

        tx0 = int(left // TILE_PX)
        ty0 = int(top // TILE_PX)
        tx1 = int((left + span) // TILE_PX)
        ty1 = int((top + span) // TILE_PX)
        made = 0
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                surf = self._tiles.get((tx, ty))
                if surf is None:
                    if made >= BUDGET:
                        continue              # next frame; it is a placeholder
                    surf = self._bake(tx, ty)
                    made += 1
                dx = int((tx * TILE_PX - left) / COARSE)
                dy = int((ty * TILE_PX - top) / COARSE)
                sheet.blit(surf, (dx, dy))
        self.last_tiles = made
        # BOTH SCALES ARE THE PICTURE, not a filter over it: the sheet is
        # span/COARSE samples across and the screen is 1280, so the number of
        # screen pixels one sample covers IS the blur, and it grows with height.
        small = pygame.transform.smoothscale(sheet, (GRID_W, GRID_H))
        return pygame.transform.smoothscale(small, size)
