"""water.py -- rain falls on the mountain and runs downhill, and where enough
of it has run together there is a river.

THIS IS NOT A DRAWN RIVER. A river is not a stripe painted across the map: it
is the place the water has decided to go, and the only way to know where that
is is to let it go there. So the height field is sampled on a grid, every cell
is given the one neighbour it drains into -- the lowest of its eight -- and then
the cells are walked in order from the highest down, each one handing its own
water plus everything that has reached it to the cell below. Whatever a cell is
carrying at the end is all the ground above it, and that number is the river.

    a cell carrying 1        is a hillside with nothing above it
    a cell carrying 400      is a gully
    a cell carrying 20000    is a river, and it is as wide as it is because
                             everything up the mountain is draining through it

AND IT COSTS NOTHING TO KEEP. The whole thing is a pure function of the seed,
the same as the terrain and the biomes, so a region is worked out once, the
first time the player comes near it, and never again.
"""

from __future__ import annotations

import numpy as np
import pygame

import terrain

CELL = 32.0             # the grid the water is worked out on, in world pixels
REGION = 128            # cells a side -- 4,096 world pixels, about seven screens
MARGIN = 16             # cells of skirt, so the flow entering from outside the
                        # region is real and not invented at the edge

# WHAT COUNTS AS A RIVER. The accumulation is the number of cells draining
# through, so a threshold of 60 is ground with sixty tiles of hillside above it.
RIVER_MIN = 300.0
# AND HOW WIDE. Radius in world pixels = RIVER_K * sqrt(accumulation), capped --
# a river that has collected the whole massif is ten tiles across and no wider,
# because past that it is not a river, it is a lake, and a lake wants drawing
# differently.
RIVER_K = 0.55
RIVER_MAX_W = 160.0     # pixels across, i.e. five tiles
RIVER_MIN_W = 7.0

_REGIONS: dict = {}


def _receivers(H):
    """For every cell, the index of the neighbour it drains into, or -1.

    THE LOWEST OF EIGHT, and nothing cleverer. Channels do not need to be
    resolved exactly: what makes a river look like a river is that it is WIDE
    where a lot of ground is above it, and that comes from the accumulation,
    not from precision in any one cell.
    """
    h, w = H.shape
    best = np.full((h, w), np.inf, np.float32)
    recv = np.full((h, w), -1, np.int32)
    idx = np.arange(h * w, dtype=np.int32).reshape(h, w)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            ny0, ny1 = max(0, dy), h + min(0, dy)
            nx0, nx1 = max(0, dx), w + min(0, dx)
            sy0, sy1 = max(0, -dy), h + min(0, -dy)
            sx0, sx1 = max(0, -dx), w + min(0, -dx)
            nb = H[sy0:sy1, sx0:sx1]
            nidx = idx[sy0:sy1, sx0:sx1]
            here = best[ny0:ny1, nx0:nx1]
            lo = nb < here
            here[lo] = nb[lo]
            recv[ny0:ny1, nx0:nx1][lo] = nidx[lo]
    # A CELL THAT DRAINS INTO SOMETHING HIGHER IS NOT DRAINING ANYWHERE. It
    # happens at the bottom of a hollow, and the water simply stays there --
    # which is a pond, and ponds are correct.
    flat = recv >= 0
    hi = np.zeros_like(flat)
    rows, cols = np.nonzero(flat)
    hi[rows, cols] = H[(recv[rows, cols] // w), (recv[rows, cols] % w)] >= H[rows, cols]
    recv[hi] = -1
    return recv


def _accumulate(H, recv):
    """Rain on every cell, and hand it all downhill, from the top down."""
    # PLAIN PYTHON LISTS, NOT NUMPY SCALARS, and it is not a small thing: every
    # acc[r] += acc[i] through numpy is a call into C for one float, and there
    # are fifty-seven thousand of them. As lists this is fifteen times faster --
    # 111 ms a region became 7, and a region is a hitch the player feels.
    n = H.size
    acc = [1.0] * n
    recv_l = recv.reshape(-1).tolist()
    for i in np.argsort(H.reshape(-1))[::-1].tolist():   # highest ground first
        r = recv_l[i]
        if r >= 0:
            acc[r] += acc[i]
    return np.array(acc, np.float32).reshape(H.shape)


def region(rx: int, ry: int) -> dict:
    """The rivers of one region. Worked out once, then it is just numbers."""
    got = _REGIONS.get((rx, ry))
    if got is not None:
        return got
    x0 = rx * REGION * CELL
    y0 = ry * REGION * CELL
    n = REGION + 2 * MARGIN
    g = (np.arange(n, dtype=np.float32) - MARGIN) * CELL + CELL * 0.5
    X, Y = np.meshgrid(x0 + g, y0 + g)
    H = terrain.height_array(X, Y)
    recv = _receivers(H)
    acc = _accumulate(H, recv)
    # the inner region only -- the skirt was there to give the edges real flow
    sl = (slice(MARGIN, MARGIN + REGION), slice(MARGIN, MARGIN + REGION))
    acc = acc[sl]
    recv_l = recv[sl]
    river = acc >= RIVER_MIN
    # how wide, in world pixels, and which way the water is going
    width = np.clip(RIVER_K * np.sqrt(np.maximum(acc, 1.0)) * 4.0,
                    RIVER_MIN_W, RIVER_MAX_W)
    wx = np.zeros_like(acc)
    wy = np.zeros_like(acc)
    rows, cols = np.nonzero(river & (recv_l >= 0))
    if len(rows):
        rr = recv_l[rows, cols]
        wx[rows, cols] = (rr % (REGION + 2 * MARGIN)) - (cols + MARGIN)
        wy[rows, cols] = (rr // (REGION + 2 * MARGIN)) - (rows + MARGIN)
        ln = np.hypot(wx[rows, cols], wy[rows, cols])
        ln[ln == 0] = 1.0
        wx[rows, cols] /= ln
        wy[rows, cols] /= ln
    got = {"x0": x0, "y0": y0, "acc": acc, "river": river,
           "width": width, "fx": wx, "fy": wy,
           "cx": np.nonzero(river)[1], "cy": np.nonzero(river)[0]}
    # a cap, so a long walk does not keep every region of the world in memory
    if len(_REGIONS) > 48:
        _REGIONS.clear()
    _REGIONS[(rx, ry)] = got
    return got


def river_at(x: float, y: float):
    """Is this ground water? How wide, and which way does it run?"""
    rx = int(np.floor(x / (REGION * CELL)))
    ry = int(np.floor(y / (REGION * CELL)))
    reg = region(rx, ry)
    cx = int((x - reg["x0"]) / CELL)
    cy = int((y - reg["y0"]) / CELL)
    if 0 <= cx < REGION and 0 <= cy < REGION and reg["river"][cy, cx]:
        return reg["width"][cy, cx], reg["fx"][cy, cx], reg["fy"][cy, cx]
    return 0.0, 0.0, 0.0


# ---- and drawing it -------------------------------------------------------
#
# HIGH CONTRAST, because a river has to read as water at a glance and the
# ground it runs over is every colour there is. Deep blue body, a clean bright
# edge, and white foam -- and the foam MOVES, which is the whole difference
# between a river and a blue stripe.
DEEP = (14, 40, 104)
BODY = (26, 86, 186)
EDGE = (96, 176, 244)
FOAM = (244, 252, 255)

FOAM_SPEED = 0.55       # how fast the foam travels, in cells a second


FOAM_LEN = 190.0        # how far apart the foam blobs are along the river


def draw(screen: pygame.Surface, cam_x: float, cam_y: float, vw: int, vh: int,
         now: float) -> None:
    """The rivers in view, drawn as a RIBBON and not as a row of dots.

    Every cell draws a thick line to the cell it drains into. A circle at every
    cell leaves a checkerboard -- the grid is thirty-two pixels and a small
    river is sixteen across, so the discs do not meet and the water comes out
    as a pattern of squares. A line to the next cell ALWAYS joins up, and the
    width is the river's own, so the thing tapers downstream the way water
    does.
    """
    span = REGION * CELL
    rx0 = int(np.floor(cam_x / span))
    rx1 = int(np.floor((cam_x + vw) / span))
    ry0 = int(np.floor(cam_y / span))
    ry1 = int(np.floor((cam_y + vh) / span))
    for ry in range(ry0, ry1 + 1):
        for rx in range(rx0, rx1 + 1):
            reg = region(rx, ry)
            if not reg["cx"].size:
                continue
            xs = reg["x0"] + (reg["cx"] + 0.5) * CELL - cam_x
            ys = reg["y0"] + (reg["cy"] + 0.5) * CELL - cam_y
            keep = ((xs > -230) & (xs < vw + 230) & (ys > -230) & (ys < vh + 230))
            if not keep.any():
                continue
            for k in np.nonzero(keep)[0].tolist():
                cy_, cx_ = reg["cy"][k], reg["cx"][k]
                sx = float(xs[k]); sy = float(ys[k])
                w = float(reg["width"][cy_, cx_])
                fx = float(reg["fx"][cy_, cx_]); fy = float(reg["fy"][cy_, cx_])
                ex = sx + fx * CELL; ey = sy + fy * CELL
                # A LINE AND A DISC AT EACH END. The line joins the cells, the
                # disc rounds the joint -- a wide river's segments are shorter
                # than it is wide, so the lines alone come out as a row of
                # overlapping squares and the bank looks like a staircase.
                thick = max(1, int(w))
                half = max(1, thick // 2)
                pygame.draw.line(screen, DEEP, (sx, sy), (ex, ey), thick + 2)
                pygame.draw.circle(screen, DEEP, (int(sx), int(sy)), half + 1)
                if thick > 3:
                    pygame.draw.line(screen, BODY, (sx, sy), (ex, ey), thick - 2)
                    pygame.draw.circle(screen, BODY, (int(sx), int(sy)), half - 1)
                    r5 = max(1, thick // 5)
                    pygame.draw.line(screen, EDGE, (sx, sy - thick * 0.45),
                                     (ex, ey - thick * 0.45), r5)
                # THE FOAM'S PLACE IS ITS DISTANCE DOWNSTREAM, measured along
                # the flow. Cells further along the river are further through
                # the run, so the blobs travel instead of blinking in place.
                ph = (now * FOAM_SPEED + (sx * fx + sy * fy) / FOAM_LEN) % 1.0
                t = ph * 0.9 + 0.05
                px = sx + (ex - sx) * t
                py = sy + (ey - sy) * t
                pygame.draw.circle(screen, FOAM, (int(px), int(py)),
                                   max(1, int(w * 0.20)))
                pygame.draw.circle(screen, FOAM, (int(px - fx * 7), int(py - fy * 7)),
                                   max(1, int(w * 0.12)))
