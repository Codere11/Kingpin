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

WHITE = (246, 246, 250)     # NEUTRAL-COOL, not warm. It was (243,240,234),
                            # a warm off-white, and against warm tan skin
                            # (216,172,132) a warm white reads as CREAM -- the
                            # eye looked yellow. A cool white is the contrast.
EYE = (38, 30, 26)          # the pupil, near-black so it reads at one pixel
BROW = (96, 66, 46)         # a shade under the hair
NOSE = (182, 144, 110)   # LIGHTER than the head's outline (150,112,82),
                            # which it was the same colour as -- an invisible nose
MOUTH = (128, 82, 66)
TONGUE = (198, 104, 112)     # the working face's whole point
LID = None                  # filled with the skin at draw time

# Where the features sit, as a fraction of the head's radius.
EYE_SIDE = 0.50             # half the distance between the eyes, of r
EYE_UP = 0.20               # the eye line, above the middle
EYE_LOOK = 0.22             # how far the pair shifts toward the facing
BROW_LIFT = 0.34
MOUTH_DOWN = 0.42
NOSE_DOWN = 0.18
WHITE_R = 0.28              # the eye white, of r
PUPIL_R = 0.15


# ---------------------------------------------------------------------------
# DRAWN ONCE, THEN BLITTED.
#
# A face is a dozen circles and lines. Ten of those per man per frame, a
# hundred men on screen at fifty frames, is fifty thousand draw calls a second
# to produce the SAME PICTURE for everyone facing the same way. So a face is
# rendered once per (radius, direction, mood) -- at most a few dozen small
# surfaces -- and drawing a face thereafter is one blit.
_CACHE: dict = {}
DIRS = 8


def sprite(r: int, dir_i: int, mood: str = "normal"):
    """The face for this head size, direction and mood, made once and kept."""
    key = (r, dir_i, mood)
    got = _CACHE.get(key)
    if got is not None:
        return got
    pad = 3
    size = 2 * r + 2 * pad + 1
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    a = dir_i * (2.0 * math.pi / DIRS)
    _render(surf, float(c), float(c), r, math.cos(a), math.sin(a), mood)
    _CACHE[key] = surf
    return surf


def _render(screen, hx: float, hy: float, r: int, fx: float, fy: float,
            mood: str = "normal", skin=(216, 172, 132)) -> None:
    """The face itself, into any surface, centred on (hx, hy).

    KEPT DELIBERATELY BOLD. At a head of radius eight an eye is four pixels
    across, and a ring around a four-pixel white reads as a pair of GLASSES --
    which is what the first version looked like. So: a white disc, a dark
    pupil in it, and nothing else around it.
    """
    ex = hx + fx * r * EYE_LOOK
    ey = hy - r * EYE_UP + fy * r * EYE_LOOK
    sep = max(3, int(round(r * EYE_SIDE)))
    wr = max(2, int(round(r * WHITE_R)))
    pr = max(1, int(round(r * PUPIL_R)))
    ix, iy = int(round(ex)), int(round(ey))
    focusing = (mood == "focus")

    # THE EYES.
    lid = max(1, int(round(wr * 1.1))) if focusing else 0
    for sgn in (-1, 1):
        cx = ix + sgn * sep
        pygame.draw.circle(screen, WHITE, (cx, iy), wr)
        if focusing:
            # A SLIT, AND THEN THE PUPIL ON TOP OF IT. The lid comes FIRST so
            # that it cuts the white down to a band, and the pupil is drawn
            # after so the man is still looking at something -- drawn the
            # other way round the slit was blank and the face went dead.
            # Sized to the EYE, not the head.
            pygame.draw.rect(screen, skin,
                             (cx - wr, iy - wr, wr * 2 + 1, lid))
        # AND THE PUPIL SITS IN THE MIDDLE OF WHAT IS LEFT. Without the push
        # down it landed on the lid, with the white underneath it, and the man
        # looked like he was rolling his eyes upward at the ceiling.
        pygame.draw.circle(screen, EYE,
                           (cx + int(round(fx * wr * 0.45)),
                            iy + lid // 2 + int(round(fy * wr * 0.45))), pr)

    # THE BROWS. Level, or pulled down and in for the working face.
    by = int(round(iy - wr - r * (0.10 if focusing else 0.20)))
    bw = max(1, int(round(r * 0.20)))
    tw = max(1, r // 6)
    for sgn in (-1, 1):
        cx = ix + sgn * sep
        if focusing:
            pygame.draw.line(screen, BROW, (cx + sgn * bw, by - tw),
                             (cx - sgn * bw, by + tw), tw)
        else:
            pygame.draw.line(screen, BROW, (cx - bw, by), (cx + bw, by), tw)

    # THE NOSE.
    if r >= 6:
        pygame.draw.line(screen, NOSE, (ix, iy + wr),
                         (ix, int(round(hy + r * NOSE_DOWN))), 1)

    # THE MOUTH.
    my = int(round(hy + r * MOUTH_DOWN))
    hw = max(1, int(round(r * (0.16 if focusing else 0.26))))
    pygame.draw.line(screen, MOUTH, (ix - hw, my), (ix + hw, my), max(1, r // 8))

    # AND THE TONGUE, OUT OF THE CORNER OF IT.
    if focusing:
        # A SIMPLE V, HANGING FROM THE MOUTH LINE DOWNWARD. It was a disc
        # centred a pixel BELOW the mouth, which put its top edge a pixel
        # ABOVE the mouth -- so the tongue looked like it grew out of the
        # man's upper lip. The flat top of the V now sits exactly on the
        # mouth line and only the point goes below it.
        tw = max(1, r // 10)                   # half its width at the mouth
        th = max(2, r // 5)                    # how far down it hangs
        # JUST OUTSIDE THE CORNER, NOT ON IT. Sitting on the corner it covered
        # two thirds of the mouth and the mouth disappeared -- which is what
        # made it read as a lizard's tongue rather than a man's.
        tx = ix + hw + tw
        pygame.draw.polygon(screen, TONGUE,
                            ((tx - tw, my), (tx + tw, my), (tx, my + th)))


def draw(screen, hx: float, hy: float, r: int, fx: float = 0.0,
         fy: float = 0.0, mood: str = "normal", skin=(216, 172, 132)) -> None:
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
        surf = sprite(r, d, mood)
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
