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


def draw(screen, hx, hy, r: int, fx: float = 0.0, fy: float = 0.0) -> None:
    """A face on a head of radius r centred at (hx, hy).

    EYES WITH WHITES AND PUPILS, BROWS, A NOSE AND A MOUTH, all scaled from r
    so the same call dresses a villager and the player. The PUPILS shift
    toward the facing while the whites stay put, which is what makes a man
    read as looking at something.
    """
    try:
        r = int(r)
        if r < 4:
            return
        ex = hx + fx * r * EYE_LOOK
        ey = hy - r * EYE_UP + fy * r * EYE_LOOK
        sep = max(2, int(round(r * EYE_SIDE)))
        wr = max(2, int(round(r * 0.26)))          # eye-white radius
        ix, iy = int(round(ex)), int(round(ey))
        # the whites
        pygame.draw.circle(screen, WHITE, (ix - sep, iy), wr)
        pygame.draw.circle(screen, WHITE, (ix + sep, iy), wr)
        pygame.draw.circle(screen, BROW, (ix - sep, iy), wr, 1)
        pygame.draw.circle(screen, BROW, (ix + sep, iy), wr, 1)
        # the pupils, looking where he is walking
        pr = max(1, int(round(wr * 0.62)))
        px = int(round(ex + fx * wr * 0.55))
        py = int(round(ey + fy * wr * 0.55))
        pygame.draw.circle(screen, EYE, (px - sep, py), pr)
        pygame.draw.circle(screen, EYE, (px + sep, py), pr)
        # brows
        by = int(round(ey - wr - r * BROW_LIFT))
        bw = max(1, int(round(r * 0.20)))
        tw = max(1, r // 7)
        pygame.draw.line(screen, BROW, (ix - sep - bw, by), (ix - sep + bw, by), tw)
        pygame.draw.line(screen, BROW, (ix + sep - bw, by), (ix + sep + bw, by), tw)
        # nose
        if r >= 7:
            ny0 = int(round(ey + wr * 0.7))
            ny1 = int(round(hy + r * NOSE_DOWN))
            pygame.draw.line(screen, NOSE, (ix, ny0), (ix, ny1), 1)
        # mouth
        if r >= 5:
            my = int(round(hy + r * MOUTH_DOWN))
            hw = max(1, int(round(r * 0.32)))
            pygame.draw.line(screen, MOUTH, (ix - hw, my), (ix + hw, my),
                             max(1, r // 8))
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
