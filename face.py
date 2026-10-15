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

import pygame

EYE = (34, 27, 24)          # near-black, so it reads at one pixel
MOUTH = (128, 82, 66)       # a shade darker than any skin tone

# Where the features sit on the head, as a fraction of its radius.
EYE_SIDE = 0.42             # half the distance between the eyes
EYE_UP = 0.06               # eyes sit just above the middle
EYE_LOOK = 0.30             # how far the pair shifts toward the facing
MOUTH_DOWN = 0.46           # the mouth, below the eyes


def draw(screen, hx: float, hy: float, r: int, fx: float = 0.0,
         fy: float = 0.0) -> None:
    """A face on a head of radius r centred at (hx, hy).

    Never raises and never draws on a head too small to hold it: a
    three-pixel skull with eyes on it is a smudge, not a person.
    """
    try:
        r = int(r)
        if r < 3:
            return
        # the pair of eyes, shifted toward the facing
        ex = hx + fx * r * EYE_LOOK
        ey = hy - r * EYE_UP + fy * r * EYE_LOOK
        sep = max(1, int(round(r * EYE_SIDE)))
        er = 1 if r < 7 else max(1, int(round(r * 0.17)))
        ix, iy = int(round(ex)), int(round(ey))
        pygame.draw.circle(screen, EYE, (ix - sep, iy), er)
        pygame.draw.circle(screen, EYE, (ix + sep, iy), er)
        # and the mouth
        if r >= 4:
            my = int(round(hy + r * MOUTH_DOWN))
            half = max(1, int(round(r * 0.30)))
            pygame.draw.line(screen, MOUTH, (ix - half, my), (ix + half, my), 1)
    except Exception:
        pass


if __name__ == "__main__":
    # A quick look at the geometry, for a five-pixel head facing four ways.
    for f in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
        r = 5
        ex = f[0] * r * EYE_LOOK
        ey = -r * EYE_UP + f[1] * r * EYE_LOOK
        sep = max(1, int(round(r * EYE_SIDE)))
        print("facing %-12s  eyes at (%.1f,%.1f) sep %d   mouth y %.1f"
              % (str(f), ex, ey, sep, r * MOUTH_DOWN))
