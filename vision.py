"""Field-of-view / vision cone with occlusion.

The player sees clearly in front, worse toward the edges of the field of view,
and nothing behind. Houses -- and anything else passed in as an occluder --
cast real shadows: for every rectangle edge facing away from the eye, a shadow
quad is projected away from the eye and darkened.

The mask is computed at reduced resolution and smoothly upscaled.
"""

from __future__ import annotations

import math

import numpy as np
import pygame

from physics import segment_rect_hit

QUANT = 2.0                # vision eye bucket, in screen px

# HEIGHT IS AN ADVANTAGE, and it is the whole reason to climb a mountain.
# Higher ground sees further, and it sees OVER things that are in the way:
# from a ridge you look down on the wood and pick out who is in it, while the
# man in the wood is looking at a wall of trees.
SIGHT_PER_M = 0.004        # each metre above sea level is this much more reach
SIGHT_MAX = 3.0            # and it stops at three times the flat range
SEE_OVER_M = 10.0          # this far above a man, the trees between you go away

EDGE_VISIBILITY = 0.12
OUTSIDE_FADE = 0.12
SOFT_ALPHA = 60                      # dimming caused by leaves


def _smoothstep(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Vision:
    def __init__(self, cone_deg: float = 175.0, max_dist: float = 560.0,
                 downscale: int = 8, fine_downscale: int = 4,
                 fine_radius: int = 192) -> None:
        self.cone_deg = cone_deg
        self.max_dist = max_dist
        self.downscale = downscale
        # What is closest to the eye is what you can actually see, so that is
        # what gets the resolution. The whole screen is masked coarsely; a box
        # around the player is masked finely and laid over it. Outside the box
        # the coarse mask takes over, feathered, so there is no seam.
        self.fine_downscale = fine_downscale
        self.fine_radius = fine_radius
        self._size: tuple[int, int] | None = None
        self._bx = self._by = None
        self._small: pygame.Surface | None = None
        self._out: pygame.Surface | None = None
        self._shadow: pygame.Surface | None = None
        self._soft: pygame.Surface | None = None
        self._fsmall: pygame.Surface | None = None
        self._fout: pygame.Surface | None = None
        self._fshadow: pygame.Surface | None = None
        self._fsoft: pygame.Surface | None = None
        self._fbox = None
        self._fbx = self._fby = None
        self._cone_cache: dict = {}      # slot -> (key, alpha array)
        self._fcone = None               # the fine pass' own cached cone
        self._key = None

    def _prepare(self, w: int, h: int) -> None:
        if self._size == (w, h):
            return
        s = self.downscale
        mw, mh = max(1, w // s), max(1, h // s)
        xs = np.arange(mw, dtype=np.float32) * s + s / 2.0
        ys = np.arange(mh, dtype=np.float32) * s + s / 2.0
        self._bx, self._by = np.meshgrid(xs, ys)
        self._small = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._out = pygame.Surface((w, h), pygame.SRCALPHA)
        self._shadow = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._soft = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._size = (w, h)
        self._cone_cache.clear()    # a new grid size: no cached cone fits it

    # -- shadows ------------------------------------------------------------
    @staticmethod
    def _project(ex, ey, px, py, length):
        dx, dy = px - ex, py - ey
        d = math.hypot(dx, dy) or 1.0
        return (px + dx / d * length, py + dy / d * length)

    def _shadow_polygons(self, ex, ey, rects):
        length = self.max_dist * 1.35
        polygons = []
        for rect in rects:
            # Anything further away than the shadow's own length is standing in
            # darkness already -- the mask is fully opaque out there, so its
            # shadow cannot change a single pixel. Most of a village is further
            # from the player than he can see, and every one of those houses
            # was being projected and drawn every frame for nothing.
            nx = max(rect.left - ex, 0.0, ex - rect.right)
            ny = max(rect.top - ey, 0.0, ey - rect.bottom)
            if nx * nx + ny * ny > length * length:
                continue
            edges = (
                ((rect.left, rect.top), (rect.right, rect.top), 0.0, -1.0),
                ((rect.right, rect.bottom), (rect.left, rect.bottom), 0.0, 1.0),
                ((rect.left, rect.bottom), (rect.left, rect.top), -1.0, 0.0),
                ((rect.right, rect.top), (rect.right, rect.bottom), 1.0, 0.0),
            )
            for p1, p2, nx, ny in edges:
                mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
                if nx * (ex - mx) + ny * (ey - my) >= 0.0:
                    continue                       # this edge faces the eye
                polygons.append([
                    p1, p2,
                    self._project(ex, ey, p2[0], p2[1], length),
                    self._project(ex, ey, p1[0], p1[1], length),
                ])
        return polygons

    # -- mask ---------------------------------------------------------------
    def build(self, w: int, h: int, eye_x: float, eye_y: float, facing: float,
              occluders=None, soft_occluders=None,
              max_dist_scale: float = 1.0) -> pygame.Surface:
        # Bucket the eye to a quarter of a vision block (2 screen px) and the
        # aim to ~0.6 of a degree. The mask is rebuilt for one representative
        # position per bucket, so a walking player reuses it for several frames
        # instead of rebuilding 14,400 pixels plus two shadow layers every time
        # the camera moves two pixels. Worst case, the cone edge is out by one
        # pixel.
        eye_x = round(eye_x / QUANT) * QUANT
        eye_y = round(eye_y / QUANT) * QUANT
        # The aim is bucketed to ~6 degrees -- a twentieth of the cone's width,
        # so the edge is imperceptibly early or late, but a moving mouse stops
        # rebuilding the mask on every single frame.
        key = (w, h, eye_x, eye_y,
               round(facing, 1) % 6.2832,
               0 if not occluders else len(occluders),
               0 if not soft_occluders else len(soft_occluders),
               # ONE DEGREE, not a tenth. The cone narrows by 55 degrees over
               # a night, so it moves about a tenth of a degree a frame -- and
               # a tenth-degree key therefore changed EVERY frame, which meant
               # the mask was rebuilt from scratch 60 times a second: fourteen
               # thousand pixels of arctangent plus two shadow layers, ~28 ms,
               # for a change nobody can see. A degree holds for ten seconds.
               round(max_dist_scale, 2), round(self.cone_deg, 0))
        if key == self._key and self._out is not None:
            return self._out
        self._key = key
        self._prepare(w, h)

        max_dist = max(70.0, self.max_dist * max_dist_scale)

        alpha = self._cone("coarse", w, h, self._bx, self._by, eye_x, eye_y,
                           facing, max_dist)

        inv = 1.0 / self.downscale
        if occluders:
            self._shadow.fill((0, 0, 0, 0))
            for poly in self._shadow_polygons(eye_x, eye_y, occluders):
                pygame.draw.polygon(self._shadow, (0, 0, 0, 255),
                                    [(p[0] * inv, p[1] * inv) for p in poly])
            hard = pygame.surfarray.array_alpha(self._shadow).T.astype(np.float32)
            alpha = np.maximum(alpha, hard)

        if soft_occluders:
            self._soft.fill((0, 0, 0, 0))
            for poly in self._shadow_polygons(eye_x, eye_y, soft_occluders):
                pygame.draw.polygon(self._soft, (0, 0, 0, SOFT_ALPHA),
                                    [(p[0] * inv, p[1] * inv) for p in poly])
            soft = pygame.surfarray.array_alpha(self._soft).T.astype(np.float32)
            alpha = np.maximum(alpha, soft)

        pixels = pygame.surfarray.pixels_alpha(self._small)
        pixels[:] = alpha.astype(np.uint8).T
        del pixels
        # The guard caught TypeError; pygame raises ValueError when the
        # destination surface is the wrong size, so the recovery that would
        # have allocated a correct one never ran -- and the error closed the
        # game. Catch what it actually raises. Nothing else about this is
        # touched: the allocation happens only when pygame asks for it.
        try:
            pygame.transform.smoothscale(self._small, (w, h), self._out)
        except (TypeError, ValueError):
            self._out = pygame.transform.smoothscale(self._small, (w, h))
        self._fine_pass(w, h, eye_x, eye_y, facing, max_dist,
                        occluders, soft_occluders)
        return self._out

    def _cone(self, slot: str, w: int, h: int, bx, by,
              eye_x: float, eye_y: float, facing: float, max_dist: float):
        """The cone for one grid, cached against what it ACTUALLY depends on.

        The cone is built from the eye, the facing, the distance and the night
        factor. It does not depend on the occluders at all -- but it shared a
        rebuild with the shadow layer, and the occluder COUNT is part of the
        mask's cache key. So as houses came into range on the walk up to a
        village the key changed, the whole mask was rebuilt, and the cone was
        recomputed for an answer identical to the one already in hand: 10.5 ms
        of a measured 35 ms hitch, every time, for nothing.

        Measured, not reasoned: the hitch frames read build 14.0, fine 10.9,
        cone 10.5 -- and only the shadows had any reason to change.

        The caller must not write into what this returns: np.maximum() makes a
        new array, and that is what keeps the cache honest.
        """
        # BUCKET IT THE WAY THE MASK'S OWN KEY DOES. Rounding cone_deg to two
        # decimals here defeated the whole point: main sets cone_deg from the
        # night EVERY frame, so a fine key changed every frame and the cone was
        # never reused -- the identical mistake the mask's key already carries a
        # comment about ("a tenth-degree key therefore changed EVERY frame").
        key = (int(w), int(h), round(eye_x, 2), round(eye_y, 2),
               round(facing, 1), round(max_dist, 1), round(self.cone_deg, 0))
        hit = self._cone_cache.get(slot)
        if hit is not None and hit[0] == key:
            return hit[1]
        alpha = self._cone_alpha(bx, by, eye_x, eye_y, facing, max_dist)
        self._cone_cache[slot] = (key, alpha)
        return alpha

    def _cone_alpha(self, bx, by, eye_x, eye_y, facing, max_dist):
        """The cone and its falloff, for whatever grid it is asked about."""
        dx = bx - eye_x
        dy = by - eye_y
        dist = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)
        delta = np.abs(((ang - facing + math.pi) % (2.0 * math.pi)) - math.pi)
        half = np.radians(self.cone_deg / 2.0)
        h_ratio = delta / half
        inside = 1.0 - (1.0 - EDGE_VISIBILITY) * _smoothstep(h_ratio, 0.40, 1.0)
        outside = EDGE_VISIBILITY * (1.0 - _smoothstep(h_ratio, 1.0,
                                                       1.0 + OUTSIDE_FADE))
        angular = np.where(h_ratio <= 1.0, inside, outside)
        radial = 1.0 - 0.75 * _smoothstep(dist / max_dist, 0.45, 1.0)
        alpha = (1.0 - angular * radial) * 255.0
        alpha[dist >= max_dist] = 255.0
        return alpha

    def _fine_pass(self, w, h, eye_x, eye_y, facing, max_dist,
                   occluders, soft_occluders) -> None:
        """Mask a box around the player at three times the resolution.

        The whole screen is masked at 1/8, which softens every shadow edge by
        eight pixels. What you are standing next to is exactly what you can
        see, so it gets its own fine pass; past the box the coarse mask takes
        over, faded out at the rim so the join is invisible.
        """
        if self.fine_radius <= 0:
            return
        r = self.fine_radius
        bx0 = max(0, min(w - 2 * r, int(eye_x) - r))
        by0 = max(0, min(h - 2 * r, int(eye_y) - r))
        bw = min(2 * r, w - bx0)
        bh = min(2 * r, h - by0)
        fs = self.fine_downscale
        mw, mh = max(1, bw // fs), max(1, bh // fs)
        if self._fbox != (mw, mh):
            xs = np.arange(mw, dtype=np.float32) * fs + bx0 + fs / 2.0
            ys = np.arange(mh, dtype=np.float32) * fs + by0 + fs / 2.0
            self._fbx, self._fby = np.meshgrid(xs, ys)
            self._fsmall = pygame.Surface((mw, mh), pygame.SRCALPHA)
            self._fout = pygame.Surface((bw, bh), pygame.SRCALPHA)
            self._fshadow = pygame.Surface((mw, mh), pygame.SRCALPHA)
            self._fsoft = pygame.Surface((mw, mh), pygame.SRCALPHA)
            self._fbox = (mw, mh)
        alpha = self._cone("fine", mw, mh, self._fbx, self._fby, eye_x, eye_y,
                           facing, max_dist)
        inv = 1.0 / fs
        if occluders:
            self._fshadow.fill((0, 0, 0, 0))
            for poly in self._shadow_polygons(eye_x, eye_y, occluders):
                pygame.draw.polygon(self._fshadow, (0, 0, 0, 255),
                                    [((p[0] - bx0) * inv, (p[1] - by0) * inv)
                                     for p in poly])
            hard = pygame.surfarray.array_alpha(self._fshadow).T.astype(np.float32)
            alpha = np.maximum(alpha, hard)
        if soft_occluders:
            self._fsoft.fill((0, 0, 0, 0))
            for poly in self._shadow_polygons(eye_x, eye_y, soft_occluders):
                pygame.draw.polygon(self._fsoft, (0, 0, 0, SOFT_ALPHA),
                                    [((p[0] - bx0) * inv, (p[1] - by0) * inv)
                                     for p in poly])
            soft = pygame.surfarray.array_alpha(self._fsoft).T.astype(np.float32)
            alpha = np.maximum(alpha, soft)
        # fade the fine pass out at its rim so it meets the coarse one cleanly
        u = np.abs(np.arange(mw, dtype=np.float32) / max(1, mw - 1) * 2.0 - 1.0)
        v = np.abs(np.arange(mh, dtype=np.float32) / max(1, mh - 1) * 2.0 - 1.0)
        edge = np.maximum(u[None, :], v[:, None])
        ramp = np.clip((1.0 - edge) / 0.30, 0.0, 1.0)
        ramp = ramp * ramp * (3.0 - 2.0 * ramp)
        alpha *= ramp
        px = pygame.surfarray.pixels_alpha(self._fsmall)
        px[:] = alpha.astype(np.uint8).T
        del px
        # The same two-token bug as the coarse pass. _fout is allocated when
        # the MASK size changes, but the box is the fine radius CLIPPED to the
        # view, so its size can move without the mask following -- leaving a
        # stale destination. Catch ValueError, which is what pygame raises.
        try:
            pygame.transform.smoothscale(self._fsmall, (bw, bh), self._fout)
        except (TypeError, ValueError):
            self._fout = pygame.transform.smoothscale(self._fsmall, (bw, bh))
        self._out.blit(self._fout, (bx0, by0),
                       special_flags=pygame.BLEND_RGBA_MAX)

    # -- point visibility ---------------------------------------------------
    def is_visible(self, eye_x: float, eye_y: float, facing: float,
                   tx: float, ty: float, edge: float = 0.9,
                   occluders=None, eye_z: float = None,
                   target_z: float = None) -> bool:
        # HOW MUCH HIGHER HE IS THAN WHAT HE IS LOOKING AT, which is the only
        # thing height changes about seeing.
        adv = 0.0
        if eye_z is not None and target_z is not None:
            adv = float(eye_z) - float(target_z)
        reach = self.max_dist
        if adv > 0.0:
            reach *= 1.0 + min(SIGHT_MAX - 1.0, adv * SIGHT_PER_M)
        dx, dy = tx - eye_x, ty - eye_y
        if math.hypot(dx, dy) > reach:
            return False
        delta = abs(((math.atan2(dy, dx) - facing + math.pi) % (2.0 * math.pi)) - math.pi)
        if delta > math.radians(self.cone_deg / 2.0) * edge:
            return False
        # AND THE TREES STOP MATTERING once he is well above them. Standing on
        # a ridge there is no canopy in the way at all -- there is nothing
        # between him and the ground below but air.
        if occluders and adv < SEE_OVER_M:
            for rect in occluders:
                if segment_rect_hit(eye_x, eye_y, tx, ty, rect):
                    return False
        return True
