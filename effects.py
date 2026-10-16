"""Screen-space damage feedback.

Instead of a flat red overlay, damage grows a network of blood veins creeping
in from the screen edges. They spread further, thicken, and pump harder and
faster the closer the player is to death. A restrained red tint sits under
them.

Also home to the little off-screen-enemy alert icon.
"""

from __future__ import annotations

import math
import random

import numpy as np

import terrain
import pygame


class DamageVignette:
    def __init__(self, downscale: int = 8) -> None:
        self.downscale = downscale
        self._size: tuple[int, int] | None = None
        self._alpha = None
        self._small: pygame.Surface | None = None
        self._out: pygame.Surface | None = None
        self._veins: list = []

    # -- one-time geometry --------------------------------------------------
    def _prepare(self, w: int, h: int) -> None:
        if self._size == (w, h):
            return
        s = self.downscale
        mw, mh = max(1, w // s), max(1, h // s)
        ys, xs = np.mgrid[0:mh, 0:mw]
        dx = (xs + 0.5 - mw / 2.0) / (mw / 2.0)
        dy = (ys + 0.5 - mh / 2.0) / (mh / 2.0)
        dist = np.sqrt(dx * dx + dy * dy) / math.sqrt(2.0)
        radial = np.clip((dist - 0.35) / 0.62, 0.0, 1.0) ** 1.4
        falloff = 0.55 + 0.45 * radial
        self._alpha = (falloff * 255.0).astype(np.uint8)
        self._small = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._small.fill((152, 0, 0, 0))
        self._out = pygame.Surface((w, h), pygame.SRCALPHA)
        self._veins = self._make_veins(w, h)
        self._size = (w, h)

    def _make_veins(self, w: int, h: int) -> list:
        rng = random.Random(9173)
        veins = []
        cx, cy = w / 2.0, h / 2.0
        diagonal = math.hypot(w, h)
        for _ in range(13):
            edge = rng.randrange(4)
            if edge == 0:
                x, y = rng.uniform(0.0, w), -12.0
            elif edge == 1:
                x, y = w + 12.0, rng.uniform(0.0, h)
            elif edge == 2:
                x, y = rng.uniform(0.0, w), h + 12.0
            else:
                x, y = -12.0, rng.uniform(0.0, h)
            angle = math.atan2(cy - y, cx - x) + rng.uniform(-0.55, 0.55)
            points = [(x, y)]
            target = rng.uniform(0.34, 0.62) * diagonal
            travelled = 0.0
            while travelled < target:
                angle += rng.uniform(-0.5, 0.5)
                nx = x + math.cos(angle) * 18.0
                ny = y + math.sin(angle) * 18.0
                points.append((nx, ny))
                travelled += math.hypot(nx - x, ny - y)
                x, y = nx, ny
            cumulative = [0.0]
            for i in range(1, len(points)):
                cumulative.append(cumulative[-1] + math.hypot(
                    points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]))
            start = rng.uniform(0.0, 0.74)          # damage level at which it appears
            veins.append((points, cumulative, start))
        return veins

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface, damage: float, now: float,
             hit_flash: float) -> None:
        w, h = screen.get_size()
        self._prepare(w, h)
        damage = max(0.0, min(1.0, damage))

        pulse = 0.5 + 0.5 * math.sin(now * (3.0 + 11.0 * damage))
        strength = 0.50 * damage * (0.45 + 0.55 * pulse) + 0.45 * hit_flash
        strength = max(0.0, min(1.0, strength))
        if strength > 0.002:
            alpha = (self._alpha.astype(np.float32) * strength).astype(np.uint8)
            pixels = pygame.surfarray.pixels_alpha(self._small)
            pixels[:] = alpha.T
            del pixels
            try:
                pygame.transform.smoothscale(self._small, (w, h), self._out)
            except TypeError:
                self._out = pygame.transform.smoothscale(self._small, (w, h))
            screen.blit(self._out, (0, 0))

        self._draw_veins(screen, damage, now, hit_flash)

    def _draw_veins(self, screen: pygame.Surface, damage: float,
                    now: float, hit_flash: float) -> None:
        intensity = min(1.0, damage + 0.5 * hit_flash)
        if intensity <= 0.02:
            return
        phase = now * (4.0 + 13.0 * intensity)     # pumps faster when worse

        for points, cumulative, start in self._veins:
            if intensity <= start:
                continue
            span = 1.0 - start
            reach = (intensity - start) / span
            reach = min(1.0, reach + 0.05 * math.sin(phase * 0.7 + start * 9.0))
            if reach <= 0.0:
                continue
            total = cumulative[-1]
            max_dist = reach * total
            for j in range(len(points) - 1):
                if cumulative[j] >= max_dist:
                    break
                x0, y0 = points[j]
                x1, y1 = points[j + 1]
                if cumulative[j + 1] > max_dist:
                    t = (max_dist - cumulative[j]) / (cumulative[j + 1] - cumulative[j])
                    x1 = x0 + (x1 - x0) * t
                    y1 = y0 + (y1 - y0) * t
                s = cumulative[j] / total
                wave = max(0.0, math.sin(phase - s * 7.0)) ** 2

                thickness = 1.0 + 3.0 * intensity + (1.5 + 4.0 * intensity) * wave
                hot = 0.3 + 0.7 * wave
                glow = (int(20 + 70 * hot), int(4 * hot), int(2 + 8 * hot))
                core = (int(40 * intensity + 150 * hot), int(14 * hot), int(18 * hot))
                pygame.draw.line(screen, glow, (x0, y0), (x1, y1), max(1, int(thickness)))
                pygame.draw.line(screen, core, (x0, y0), (x1, y1),
                                 max(1, int(thickness * 0.5)))


LEVEL_GOLD = (250, 216, 128)


# THE SOFT COPY IS MADE AT THIS FRACTION of the frame and scaled back up. How
# far down it goes IS how soft it is -- see radial_blur.
_BLUR_DOWN = 12


# HOW MUCH BIGGER THE GROUND GETS FOR BEING HIGHER UP. A fortieth of a metre
# per metre: TEN METRES OF CLIMB DRAWS THE GROUND A QUARTER LARGER, forty metres
# draws it double, and there it stops. At eight thousandths this was 1.00 to
# 1.05 across a whole screen -- correct, and invisible, which is the same as not
# having it.
#
# IT IS A SIZE, AND ONLY A SIZE. No shadow, no shading, no line -- the ground
# you are walking on gets BIGGER as you climb and SMALLER as you drop into a
# valley, and that is the whole language. It is the one cue that cannot be
# misread: nothing else in the picture says which way is up as plainly as the
# world being nearer the camera.
_WARP_K = 0.025     # -> effects._scale
_WARP_MIN = 0.62              # the far floor, and so how big the frame must be
_WARP_MAX = 2.00              # the summit draws twice the size


def _scale(z, h, k=_WARP_K):
    """How big ground at height h draws, seen by a camera at height z.

    ONE law, used by the warp and by the cursor, so the world the pointer is
    over is the world the pointer is over.

        s = 1 + (h - z) * k      clamped

    Higher than him draws BIGGER (nearer the camera), lower draws smaller, and
    his own level is one to one. Clamped at both ends: without a floor the far
    valley would shrink to nothing, and without a ceiling the summit would run
    away with the picture entirely.
    """
    return np.clip(1.0 + (np.asarray(h, np.float32) - z) * k, _WARP_MIN, _WARP_MAX)


def height_offset(X: float, Y: float, px: float, py: float, z: float,
                  k: float = _WARP_K):
    """THE WORLD UNDER A POINT ON THE SCREEN, at a height.

    height_warp moves ground to where it APPEARS; this is the other way, and it
    is what a cursor needs: the ground under the pointer is packed in toward
    him, so the plain screen-to-world sum puts the world in the wrong place --
    the further the ground is below him, the worse the error.
    """
    s = 1.0
    dx = X
    dy = Y
    for _ in range(4):
        dx = X / s
        dy = Y / s
        h = terrain.height_array(px + dx, py + dy)
        s = _scale(z, h, k)
    # PLAIN FLOATS, NOT NUMPY SCALARS. This feeds the aim, the aim feeds
    # player.facing, and pygame will not accept a numpy scalar as half of a
    # point -- it raises "points must be number pairs" from deep inside a draw
    # call, which is a long way from the numpy scalar that caused it.
    return float(dx), float(dy)


BLOCK = 32.0        # the world's block, the same one the tiles and the ground use


def height_warp(frame: pygame.Surface, px: float, py: float, z: float,
                out_size, k: float = _WARP_K) -> pygame.Surface:
    """EVERY BLOCK DRAWN AT ITS OWN SIZE, IN ITS OWN PLACE.

    THE WORLD IS ALREADY DIVIDED INTO BLOCKS, so this does not need to move
    anything about: a block stays exactly where it is, in its own cell, and
    only the ground INSIDE it is drawn bigger or smaller, about the block's
    own centre.

        source = block_centre + (pixel - block_centre) / s

    Nothing moves sideways, nothing tears, and neighbouring blocks still meet
    edge to edge -- because each one fills its own cell whatever size its
    contents are.

    WHAT WENT WRONG BEFORE. The same scale was applied RADIALLY, about the
    player: every pixel was pushed toward or away from him by its own distance,
    so a block near the middle of the screen and a block at the edge of it
    moved by different amounts and the grid came apart at the seams. Bent, and
    then broken. The scale was never the problem -- it was being applied from
    the player instead of from the block.

    A block higher than the camera draws its ground bigger, a block lower draws
    it smaller, and a block at his own level is untouched.
    """
    fw, fh = frame.get_size()
    ow, oh = int(out_size[0]), int(out_size[1])
    out = frame.subsurface(((fw - ow) // 2, (fh - oh) // 2, ow, oh)).copy()
    X, Y = np.meshgrid(np.arange(ow, dtype=np.float32) - ow * 0.5,
                       np.arange(oh, dtype=np.float32) - oh * 0.5, indexing="ij")
    # WHICH BLOCK IS EACH PIXEL IN, and where is that block's centre on screen
    bx = np.floor((px + X) / BLOCK).astype(np.int32)
    by = np.floor((py + Y) / BLOCK).astype(np.int32)
    bcx = bx.astype(np.float32) * BLOCK + BLOCK * 0.5 - px
    bcy = by.astype(np.float32) * BLOCK + BLOCK * 0.5 - py
    # THE HEIGHT IS ASKED ONCE PER BLOCK, NOT ONCE PER PIXEL. There are a
    # hundred and eighty blocks in view and a hundred and eighty thousand
    # pixels, and the field costs the same either way.
    bx0 = int(bx.min()); by0 = int(by.min())
    nbx = int(bx.max()) - bx0 + 1
    nby = int(by.max()) - by0 + 1
    gx = (np.arange(nbx, dtype=np.float32) + bx0 + 0.5) * BLOCK - px
    gy = (np.arange(nby, dtype=np.float32) + by0 + 0.5) * BLOCK - py
    GX, GY = np.meshgrid(gx, gy, indexing="ij")
    sc = _scale(z, terrain.height_array(px + GX, py + GY), k)
    sc = sc[bx - bx0, by - by0]
    # AND THE BLOCK'S CONTENTS SCALE ABOUT THE BLOCK'S OWN CENTRE.
    dx = bcx + (X - bcx) / sc
    dy = bcy + (Y - bcy) / sc
    flat = np.flatnonzero((np.abs(sc - 1.0) > 0.004).ravel())
    if flat.size == 0:
        return out
    src = pygame.surfarray.pixels3d(frame)
    sx = np.clip((dx.ravel()[flat] + fw * 0.5).astype(np.int32), 0, fw - 1)
    sy = np.clip((dy.ravel()[flat] + fh * 0.5).astype(np.int32), 0, fh - 1)
    got = src[sx, sy]
    del src
    dst = pygame.surfarray.pixels3d(out)
    dst[flat // oh, flat % oh] = got
    del dst
    return out


def radial_blur(surface: pygame.Surface, zoom: float) -> None:
    """THE FURTHER FROM HIM, THE SOFTER -- and how soft scales with the pull-back.

    zoom is how much MORE WORLD the frame is covering than it would at ground
    level: 1.0 on the flat, 1.99 at nine metres. Everything on screen has been
    squeezed by that factor, so everything is a little softer than it was --
    that IS the blur, and it comes for free from scaling the frame down.

    What this adds is a GRADIENT, so it is not one flat wash. The middle of the
    frame is the ground he would have seen from the ground -- 1/zoom of the
    half-width -- and it stays SHARP. Beyond that is ground he can only see
    because he climbed, and it goes soft, all the way to fully soft at the edge.

        z=1   zoom 1.11   the middle 90% of the frame is sharp
        z=4   zoom 1.44   the middle 69%
        z=9   zoom 1.99   the middle 50%

    So it reads as distance rather than as fog: what is under his feet is crisp
    and what he is looking at from a hilltop is not.
    """
    if zoom <= 1.001:
        return
    w, h = surface.get_size()
    st = 4                         # a coarse mask; it varies smoothly
    mw = max(2, w // st)
    mh = max(2, h // st)
    xs = (np.arange(mw, dtype=np.float32) + 0.5) * st
    ys = (np.arange(mh, dtype=np.float32) + 0.5) * st
    # a SQUARE radius, so the sharp region is the shape of the frame and not a
    # circle floating in the middle of it
    px = np.abs(xs - w * 0.5) / (w * 0.5)
    py = np.abs(ys - h * 0.5) / (h * 0.5)
    p = np.maximum(px[None, :], py[:, None])
    near = 1.0 / zoom
    t = np.clip((p - near) / max(1e-3, 1.0 - near), 0.0, 1.0)
    if not t.any():
        return
    soft = pygame.Surface((w, h), pygame.SRCALPHA)
    soft.blit(pygame.transform.smoothscale(
        pygame.transform.smoothscale(surface, (max(2, w // _BLUR_DOWN),
                                               max(2, h // _BLUR_DOWN))),
        (w, h)), (0, 0))
    mask = pygame.Surface((mw, mh), pygame.SRCALPHA)
    alpha = pygame.surfarray.pixels_alpha(mask)
    alpha[:, :] = (255.0 * t ** 1.2).astype(np.uint8).T
    del alpha
    if (mw, mh) != (w, h):
        mask = pygame.transform.smoothscale(mask, (w, h))
    soft.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(soft, (0, 0))


def draw_level_up(screen: pygame.Surface, sx: float, sy: float,
                  t: float) -> None:
    """A SHINE ACROSS THE BODY. t runs 0 -> 1 over the life of the flash.

    He lights up for a moment, three rings go out from him at their own pace,
    and eight sparks come off the body and rise. Built into a pad-sized surface
    and blitted, like the cigar and the bottle in village._draw_use_fx, because
    it needs real alpha and pygame's draw calls do not blend on their own.
    """
    p = max(0.0, min(1.0, t))
    # AN OVERALL FADE, or the sparks WRAP: their own clock runs 1.4x and is
    # taken modulo 1, so at the very end they come round again and the man
    # keeps twinkling for ever. Everything is multiplied by this.
    fade = 1.0 - p
    pad = 56
    surf = pygame.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
    cx = cy = pad
    # THE BODY ITSELF, for the first third of it.
    if p < 0.35:
        a = int(155 * (1.0 - p / 0.35) * fade)
        pygame.draw.circle(surf, (255, 250, 224, a), (cx, cy), 13)
    # THREE RINGS, each a little behind the last.
    for i in range(3):
        k = p * 1.25 + i * 0.28
        if k >= 1.0:
            continue
        a = int(150 * (1.0 - k) * fade)
        if a > 0:
            pygame.draw.circle(surf, LEVEL_GOLD + (a,), (cx, cy),
                               int(8 + k * 36), 2)
    # AND EIGHT SPARKS, rising off him.
    for i in range(8):
        k = (p * 1.4 + i * 0.13) % 1.0
        a = int(210 * (1.0 - k) * fade)
        if a <= 0:
            continue
        ang = i * 0.7853981634
        rr = 6.0 + k * 22.0
        x = cx + int(math.cos(ang) * rr)
        y = cy + int(math.sin(ang) * rr * 0.6) - int(k * 15.0)
        pygame.draw.circle(surf, (255, 252, 232, a),
                           (x, y), max(1, 2 - int(k * 2)))
    screen.blit(surf, (int(sx) - pad, int(sy) - pad))


def draw_alert(screen: pygame.Surface, sx: float, sy: float,
               now: float, phase: float) -> None:
    """A small, hand-drawn looking '!' over someone the player cannot see."""
    cycle = (now * 1.35 + phase * 0.37) % 1.0
    if not (cycle < 0.16 or 0.28 <= cycle < 0.44):   # irregular double-blink
        return
    bob = math.sin(now * 6.0 + phase) * 1.6
    jitter = math.sin(now * 9.0 + phase * 2.3) * 1.4
    top_x = sx + jitter
    top_y = sy - 32.0 + bob
    bot_x, bot_y = top_x - 1.6, top_y + 13.0

    points = [(top_x - 2.0, top_y), (top_x + 2.0, top_y),
              (bot_x + 3.3, bot_y), (bot_x - 3.3, bot_y)]
    pygame.draw.polygon(screen, (247, 228, 164), points)
    pygame.draw.polygon(screen, (58, 40, 22), points, 2)
    pygame.draw.circle(screen, (247, 228, 164), (int(top_x), int(top_y + 19)), 2)
    pygame.draw.circle(screen, (58, 40, 22), (int(top_x), int(top_y + 19)), 2, 1)
