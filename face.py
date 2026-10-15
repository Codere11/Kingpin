"""face.py -- one face, for everybody, for now.

THE HEADS ARE DIFFERENT SIZES, so the face is drawn to the head rather than to
a fixed size: a villager's skull is five pixels across and the player's six, a
fur hat sits on an eight-pixel one and an indigo wrap on another. One call,
one look, scaled.

THE EYES FOLLOW THE FACING. A man walking north looks north; the eyes shift a
little way toward wherever he is headed, which is most of what makes a small
sprite read as looking at something rather than as a hole that sees.

ONE EXPRESSION, as asked. When there are more -- tired, frightened, hungry,
pleased -- they belong here, and every man in the world gets them at once.
"""

from __future__ import annotations

import math

import pygame

WHITE = (243, 240, 234)     # the eye
EYE = (38, 30, 26)          # the pupil, near-black so it reads at one pixel
BROW = (96, 66, 46)         # a shade under the hair
NOSE = (182, 144, 110)   # LIGHTER than the head's outline (150,112,82),
                            # which it was the same colour as -- an invisible nose
MOUTH = (128, 82, 66)

# Where the features sit, as a fraction of the head's radius.
EYE_SIDE = 0.40             # half the distance between the eyes
EYE_UP = 0.18               # the eye line, above the middle
EYE_LOOK = 0.22             # how far the pair shifts toward the facing
BROW_LIFT = 0.22
MOUTH_DOWN = 0.46
NOSE_DOWN = 0.16


# ---------------------------------------------------------------------------
# DRAWN ONCE, THEN BLITTED.
#
# A face is about a dozen circles and lines. Ten of those per man per frame,
# a hundred men on screen at fifty frames, is fifty thousand draw calls a
# second to produce the SAME PICTURE for every man facing the same way. So a
# face is rendered once per (radius, of eight directions) -- twenty-four small
# surfaces at most -- and drawing a face thereafter is one blit.
_CACHE: dict = {}
DIRS = 8


def sprite(r: int, dir_i: int):
    """The face for this head size and direction, made once and kept."""
    key = (r, dir_i)
    got = _CACHE.get(key)
    if got is not None:
        return got
    pad = 3
    size = 2 * r + 2 * pad + 1
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    a = dir_i * (2.0 * math.pi / DIRS)
    _render(surf, float(c), float(c), r, math.cos(a), math.sin(a))
    _CACHE[key] = surf
    return surf


def _render(screen, hx: float, hy: float, r: int, fx: float, fy: float) -> None:
    """The face itself, into any surface, centred on (hx, hy)."""
    ex = hx + fx * r * EYE_LOOK
    ey = hy - r * EYE_UP + fy * r * EYE_LOOK
    sep = max(2, int(round(r * EYE_SIDE)))
    wr = max(2, int(round(r * 0.26)))
    ix, iy = int(round(ex)), int(round(ey))
    pygame.draw.circle(screen, WHITE, (ix - sep, iy), wr)
    pygame.draw.circle(screen, WHITE, (ix + sep, iy), wr)
    pygame.draw.circle(screen, BROW, (ix - sep, iy), wr, 1)
    pygame.draw.circle(screen, BROW, (ix + sep, iy), wr, 1)
    pr = max(1, int(round(wr * 0.62)))
    px = int(round(ex + fx * wr * 0.55))
    py = int(round(ey + fy * wr * 0.55))
    pygame.draw.circle(screen, EYE, (px - sep, py), pr)
    pygame.draw.circle(screen, EYE, (px + sep, py), pr)
    by = int(round(ey - wr - r * BROW_LIFT))
    bw = max(1, int(round(r * 0.20)))
    tw = max(1, r // 7)
    pygame.draw.line(screen, BROW, (ix - sep - bw, by), (ix - sep + bw, by), tw)
    pygame.draw.line(screen, BROW, (ix + sep - bw, by), (ix + sep + bw, by), tw)
    if r >= 7:
        pygame.draw.line(screen, NOSE, (ix, int(round(ey + wr * 0.7))),
                         (ix, int(round(hy + r * NOSE_DOWN))), 1)
    if r >= 5:
        my = int(round(hy + r * MOUTH_DOWN))
        hw = max(1, int(round(r * 0.32)))
        pygame.draw.line(screen, MOUTH, (ix - hw, my), (ix + hw, my),
                         max(1, r // 8))


def draw(screen, hx: float, hy: float, r: int, fx: float = 0.0,
         fy: float = 0.0) -> None:
    """A face on a head of radius r centred at (hx, hy). One blit after the
    first time, and never raises: a face must not be able to stop a frame."""
    try:
        r = int(r)
        if r < 4:
            return
        if fx or fy:
            d = int(round(math.atan2(fy, fx) / (2.0 * math.pi / DIRS))) % DIRS
        else:
            d = 0
        surf = sprite(r, d)
        screen.blit(surf, (int(hx) - surf.get_width() // 2,
                           int(hy) - surf.get_height() // 2))
    except Exception:
        pass


if __name__ == "__main__":
    print("cached faces after warming 3 sizes x 8 ways:")
    for rr in (5, 6, 8):
        for dd in range(DIRS):
            sprite(rr, dd)
    print("   surfaces:", len(_CACHE))
