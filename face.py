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
MAW = (104, 42, 42)         # an open, shouting mouth -- the war face
LIP = (176, 96, 92)         # one pixel of lip, all the way round it
SOCKET = (170, 124, 94)     # the hollow a starving man's eye sits down in
SCAR = (172, 96, 84)        # a line of it across the face
BEARD = (26, 20, 18)        # the bottom third of the face, black
LENS = (168, 132, 56)       # a monocle's brass rim -- darker than the
                            # skin AND than the white it rings, or it
                            # vanishes into one of them
PAD = 3                     # the margin the face sprite leaves round a head
CROWN = (226, 184, 78)      # gold, and worn on top of everything
CROWN_D = (146, 108, 30)    # the darker gold it is edged in
TOOTH = (238, 236, 228)     # two of them, at the top of it
LID = None                  # filled with the skin at draw time

# Where the features sit, as a fraction of the head's radius.
EYE_SIDE = 0.50             # half the distance between the eyes, of r
EYE_UP = 0.20               # the eye line, above the middle
EYE_LOOK = 0.22             # how far the pair shifts toward the facing
BROW_LIFT = 0.34
MOUTH_DOWN = 0.42
NOSE_DOWN = 0.18
WORK_SECONDS = 0.8          # how long a work action shows on the face
VET_BROW = 0.25             # a QUARTER of the way up both combat skills and
                            # he keeps ONE brow cocked for the rest of his life
VET_BEARD = 0.50            # half way: the beard
VET_SCAR = 0.75             # past three quarters: the scar
STARVED_HUNGER = 80.0       # ...and the one face that is a STATE, not an
                            # event: at this hunger he is starving, and that
                            # is the only thing about him worth drawing.
SLY_SECONDS = 1.5           # ...and how long a completed trade does. Long
                            # enough that a trader working a route keeps the
                            # smirk up between deals instead of blinking it.
HURT_SECONDS = 1.2          # ...and how long a blow LANDING on him does.
                            # IT MUST EQUAL WAR_SECONDS: the two are compared
                            # to see which happened more recently, and that
                            # comparison means nothing at unequal lengths.
WAR_SECONDS = 1.2           # ...and how long a blow does. Longer than the
                            # slowest swing (a villager's, at 1.0s) so the war
                            # face stays ON through a fight instead of strobing
                            # between swings, and drops just after it ends.
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


def sprite(r: int, dir_i: int, mood: str = "normal", vet: int = 0):
    """The face for this head size, direction, mood and rank, made once."""
    key = (r, dir_i, mood, vet)
    got = _CACHE.get(key)
    if got is not None:
        return got
    size = 2 * r + 2 * PAD + 1
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    a = dir_i * (2.0 * math.pi / DIRS)
    _render(surf, float(c), float(c), r, math.cos(a), math.sin(a), mood, vet=vet)
    # CLIPPED TO THE HEAD IT IS DRAWN ON.
    #
    # Nothing the face draws may fall outside the circle the caller draws under
    # it, or a feature floats in the air beside a man's head. This was not a
    # veteran bug and not a scar bug: the right BROW's outer tip sat at (19,5),
    # which is 100 from a centre whose radius is eight -- on EVERY face, in
    # every direction, because the eye line shifts toward the facing and takes
    # the brows with it. The war face had eight such pixels, eye ones included.
    #
    # Only the pixels OUTSIDE the circle are touched, row by row, so this costs
    # a few hundred set_at calls once per cached sprite and nothing per frame.
    rr = r * r
    for _y in range(size):
        _dy = _y - c
        _rem = rr - _dy * _dy
        if _rem < 0:
            _lo, _hi = 0, size - 1
        else:
            _w = math.sqrt(_rem)
            _lo = int(math.ceil(c - _w))
            _hi = int(math.floor(c + _w))
        for _x in range(0, max(0, _lo)):
            surf.set_at((_x, _y), (0, 0, 0, 0))
        for _x in range(min(size, _hi + 1), size):
            surf.set_at((_x, _y), (0, 0, 0, 0))
    _CACHE[key] = surf
    return surf


def _render(screen, hx: float, hy: float, r: int, fx: float, fy: float,
            mood: str = "normal", skin=(216, 172, 132),
            vet: int = 0) -> None:
    """The face itself, into any surface, centred on (hx, hy).

    THREE MOODS, ONE GEOMETRY.

      normal   level brows, round eyes, a flat mouth
      focus    brows pulled down and IN, eyes narrowed to a slit with the
               pupil still in it, a small pressed mouth, the tongue out --
               a man trying to be precise
      angry    brows driven down STEEPLY and drawn thick, the eye pressed to a
               harder slit, and the mouth actually OPEN, because a flat line
               is a scowl and a mouth that has come open is a man shouting

    KEPT DELIBERATELY BOLD. At a head of radius eight an eye is four pixels
    across, and a ring around a four-pixel white reads as a pair of GLASSES --
    which is what the first version looked like.
    """
    # THE EYE LINE BELONGS TO THE HEAD. ONLY THE PUPILS LOOK.
    #
    # Everything used to shift toward the facing -- whites, brows and all --
    # which slid the whole face a pixel or two to one side of the skull it is
    # painted on. Turning east pushed the outer end of the right brow clean off
    # the side of the head, and clipping it back left a two-pixel stub where
    # the left brow still had five. A face that changes shape when a man turns
    # is a worse lie than a face that does not follow him quite so much, and
    # the pupils moving inside the whites is what reads as looking anyway.
    sep = max(3, int(round(r * EYE_SIDE)))
    wr = max(2, int(round(r * WHITE_R)))
    pr = max(1, int(round(r * PUPIL_R)))
    ix, iy = int(round(hx)), int(round(hy - r * EYE_UP))
    focusing = (mood == "focus")
    angry = (mood == "angry")
    hurt = (mood == "hurt")
    sly = (mood == "sly")

    # -- WHAT A FIGHTER EARNS, AND THE ORDER IT GOES ON IN -----------------
    #
    #   1  the beard   the bottom third of the face, filled
    #   2  the scar    OVER the beard, and UNDER the eye
    #   3  the face    so the scar never splits the eye it crosses
    #
    # NOT A MOOD. These are drawn on top of whatever he is doing -- angry,
    # hurt, starving -- because they are what he has BECOME, and a veteran
    # does not lose his beard when somebody hits him. Only the BROW is not
    # here: it is part of the face, so it is drawn with the brows below.
    if vet >= 2:
        hc, vc = int(round(hx)), int(round(hy))
        for dy in range(3, r + 1):
            y = vc + dy
            hw = int(math.sqrt(max(0.0, r * r - dy * dy)))
            pygame.draw.line(screen, BEARD, (hc - hw, y), (hc + hw, y), 1)

    # THE ONE BROW, COCKED DOWN, FOR THE REST OF HIS LIFE. Taken from the war
    # face sign for sign, and used by every mood's brow block below.
    def _war_brow(cx, sgn) -> None:
        _bw = max(1, int(round(r * 0.26)))
        _tw = max(2, r // 5)
        _by = int(round(iy - wr - r * 0.04))
        pygame.draw.line(screen, BROW, (cx + sgn * _bw, _by - _tw),
                         (cx - sgn * _bw, _by + _tw), _tw)

    if vet >= 3:
        # Walked a row at a time and CLIPPED TO THE HEAD: drawn as one line it
        # ended at (18,17), which is 85 from the centre of a head whose radius
        # is 8, so its last three pixels floated off the side of his face.
        hc, vc = int(round(hx)), int(round(hy))
        _cx = ix + sep
        sx0, sx1 = _cx - max(1, r // 6), _cx + max(1, r // 6)
        sy0, sy1 = iy - wr - 1, vc + r - 2
        steps = max(1, abs(sy1 - sy0))
        for _i in range(steps + 1):
            _t = _i / float(steps)
            _x = int(round(sx0 + (sx1 - sx0) * _t))
            _y = int(round(sy0 + (sy1 - sy0) * _t))
            if (_x - hc) ** 2 + (_y - vc) ** 2 <= r * r:
                pygame.draw.line(screen, SCAR, (_x, _y), (_x, _y), 1)

    if mood == "starved":
        # THE STARVED FACE. The ONLY mood that is a state rather than an event,
        # and it OVERRIDES EVERY OTHER ONE -- a man this hungry is not angry,
        # or busy, or pleased with himself, whether he is swinging an axe or
        # standing still.
        #
        # THE EYES DO NOT MOVE. The first cut shifted them down and painted a
        # socket the size of the whole eye over them, which covered half the
        # upper face -- a mask, or a pair of sunglasses. What reads is the
        # HOLLOWS: a line of shadow under each eye where the fat used to be,
        # brows hanging at the outer ends, and a mouth turned down.
        for sgn in (-1, 1):
            cx = ix + sgn * sep
            pygame.draw.circle(screen, WHITE, (cx, iy), wr)
            pygame.draw.circle(screen, EYE,
                               (cx + int(round(fx * wr * 0.55)),
                                iy + int(round(fy * wr * 0.55))), pr)
        # THE HOLLOW: a short line of shadow under each eye. SHORT, because
        # the nose runs down between them -- a long one on each side joined up
        # with it and the three of them read as a moustache.
        for sgn in (-1, 1):
            cx = ix + sgn * sep
            pygame.draw.line(screen, SOCKET, (cx - wr + 1, iy + wr + 1),
                             (cx + wr - 1, iy + wr + 1), 1)
        # THE BROWS HANG: outer end low, inner end up. The exact reverse of the
        # war face, which is the same line read the other way.
        by = int(round(iy - wr - r * 0.20))
        bw = max(1, int(round(r * 0.20)))
        tw = max(1, r // 6)
        for sgn in (-1, 1):
            cx = ix + sgn * sep
            if vet >= 1 and sgn < 0:
                _war_brow(cx, sgn)          # the one he earned, even starving
            else:
                pygame.draw.line(screen, BROW, (cx + sgn * bw, by + tw),
                                 (cx - sgn * bw, by - tw), tw)
        if r >= 6:
            pygame.draw.line(screen, NOSE, (ix, iy + wr),
                             (ix, int(round(hy + r * NOSE_DOWN))), 1)
        # THE MOUTH TURNED DOWN, and wide -- the corners go below the middle.
        m_y = int(round(hy + r * MOUTH_DOWN))
        hw = max(1, int(round(r * 0.34)))
        pygame.draw.line(screen, MOUTH, (ix - hw, m_y + 1), (ix, m_y), 1)
        pygame.draw.line(screen, MOUTH, (ix, m_y), (ix + hw, m_y + 1), 1)
        return

    war = angry or hurt

    # THE EYES, AND HOW FAR THE LID COMES DOWN.
    if angry or sly:
        lid = max(1, int(round(wr * 1.45)))     # the brow is pressing it shut
    elif focusing:
        lid = max(1, int(round(wr * 1.1)))
    else:
        lid = 0
    if hurt:
        # CLENCHED SHUT: two strokes meeting at a point, and the point turns
        # INWARD, so the pair reads as >< -- the face a man pulls when the blow
        # lands. No white and no pupil: there is nothing to see with.
        cw = max(1, int(round(r * 0.20)))
        ch = max(1, int(round(r * 0.20)))
        for sgn in (-1, 1):
            cx = ix + sgn * sep
            tip = (cx - sgn * cw, iy)
            pygame.draw.line(screen, EYE, (cx + sgn * cw, iy - ch), tip, 1)
            pygame.draw.line(screen, EYE, (cx + sgn * cw, iy + ch), tip, 1)
    for sgn in (() if hurt else (-1, 1)):
        cx = ix + sgn * sep
        pygame.draw.circle(screen, WHITE, (cx, iy), wr)
        if lid:
            # A SLIT, AND THEN THE PUPIL ON TOP OF IT. The lid comes FIRST so
            # that it cuts the white down to a band, and the pupil is drawn
            # after so the man is still looking at something -- drawn the
            # other way round the slit was blank and the face went dead.
            # Sized to the EYE, not the head.
            pygame.draw.rect(screen, skin, (cx - wr, iy - wr, wr * 2 + 1, lid))
        # AND THE PUPIL SITS IN THE MIDDLE OF WHAT IS LEFT.
        pygame.draw.circle(screen, EYE,
                           (cx + int(round(fx * wr * 0.45)),
                            iy + lid // 2 + int(round(fy * wr * 0.45))), pr)

    # THE BROWS. One style for the mood -- and ONE OF THEM IS THE WAR BROW'S
    # if he has earned it, which is why this is a style and not four copies.
    if war or sly:
        bstyle = "war"
    elif focusing:
        bstyle = "in"
    else:
        bstyle = "level"
    for sgn in (-1, 1):
        cx = ix + sgn * sep
        if vet >= 1 and sgn < 0:
            _war_brow(cx, sgn)
            continue
        if bstyle == "war":
            # A HARD STEEP V, AND THICK. The inner end comes down almost level
            # with the eye and the outer end rides high; the stroke is two or
            # three pixels because at this size a hairline reads as a smudge.
            _war_brow(cx, sgn)
        elif bstyle == "in":
            by = int(round(iy - wr - r * 0.10))
            bw = max(1, int(round(r * 0.20)))
            tw = max(1, r // 6)
            pygame.draw.line(screen, BROW, (cx + sgn * bw, by - tw),
                             (cx - sgn * bw, by + tw), tw)
        else:
            by = int(round(iy - wr - r * 0.20))
            bw = max(1, int(round(r * 0.20)))
            tw = max(1, r // 6)
            pygame.draw.line(screen, BROW, (cx - bw, by), (cx + bw, by), tw)

    # THE NOSE.
    if r >= 6:
        pygame.draw.line(screen, NOSE, (ix, iy + wr),
                         (ix, int(round(hy + r * NOSE_DOWN))), 1)

    my = int(round(hy + r * MOUTH_DOWN))

    if war:
        # THE MOUTH IS OPEN. Not a line, not a grimace -- an ellipse, dark
        # inside, with two teeth at the top of it. It is the difference
        # between a man who is cross and a man who is coming for you.
        # BIGGER, AND SQUARE RATHER THAN ROUND. An ellipse at this size reads
        # as a little round hole; a wide rectangle with the corners barely
        # taken off reads as a jaw that has come open. It sits one pixel lower
        # than the other mouths so it does not grow into the nose.
        mw = max(2, int(round(r * 0.38)))
        mh = max(1, int(round(r * 0.22)))
        top = my - mh + 1
        rad = max(1, r // 8)
        mouth = (ix - mw, top, mw * 2 + 1, mh * 2 + 1)
        pygame.draw.rect(screen, MAW, mouth, border_radius=rad)
        if r >= 6:
            # TWO TEETH, EVENLY EITHER SIDE OF THE MIDDLE, AND INSIDE THE LIPS.
            # They sit one pixel in from each end because the lip line is drawn
            # over the outer ring afterwards, and a tooth on that ring would be
            # painted out by it. (The very first cut had one tooth at the far
            # left edge and one just right of centre -- a snaggletooth.)
            tw2 = max(1, mw - 1)
            ty = top + 1
            pygame.draw.rect(screen, TOOTH, (ix - tw2, ty, tw2, 1))
            pygame.draw.rect(screen, TOOTH, (ix + 1, ty, tw2, 1))
        # THE LIPS: ONE PIXEL OF THEM, RIGHT ROUND THE OPENING. Drawn last so
        # it takes the outer ring of the jaw for itself -- a mouth with no
        # edge to it is a hole, and a hole is not a war face.
        pygame.draw.rect(screen, LIP, mouth, 1, border_radius=rad)
        return

    if sly:
        # A WIDE, OPEN, SLEAZY GRIN.
        #
        # The first cut was a thin curved line and it read as a man holding
        # something in -- constipated, not sly. A grin is OPEN, and what makes
        # it a SMILE rather than a shout is that the corners ride UP while the
        # middle hangs DOWN.
        #
        # Built as tapering rows, one per line, because the shape IS the
        # curve -- pygame's polygon fill rounds outward at this size, which is
        # how the tongue came out three times the size I asked for.
        w = max(4, int(round(r * 0.55)))       # 4 at r=8: nine pixels across
        h = max(3, int(round(r * 0.38)))       # and three rows deep
        for i in range(h):
            t = i / float(h)
            half = w - int(round(t * w * 0.8))
            if half < 1:
                half = 1
            y = my + i
            pygame.draw.line(screen, MAW, (ix - half, y), (ix + half, y), 1)
        # ALL THE TEETH, in a row across the top of the opening -- set in one
        # pixel from each end, so the corners stay dark and the grin reads as
        # a mouth rather than a white bar.
        for dx in range(-(w - 2), w - 1):
            pygame.draw.line(screen, TOOTH, (ix + dx, my + 1),
                             (ix + dx, my + 1), 1)
        # AND ONE CORNER CURLED HIGHER THAN THE OTHER. A symmetrical grin is
        # merely friendly; it is the lopsided one that is up to something.
        pygame.draw.line(screen, MAW, (ix + w - 2, my - 1), (ix + w, my - 1), 1)
        return

    # THE MOUTH.
    hw = max(1, int(round(r * (0.16 if focusing else 0.26))))
    pygame.draw.line(screen, MOUTH, (ix - hw, my), (ix + hw, my), max(1, r // 8))

    # AND THE TONGUE, OUT OF THE CORNER OF IT -- one pixel across, three deep.
    if focusing:
        depth = max(3, r * 3 // 8)
        x0 = ix + hw
        pygame.draw.line(screen, TONGUE, (x0, my), (x0, my + depth - 1), 1)


def vet_tier(melee: float, ranged: float) -> int:
    """How far up the combat ladder he is, 0 to 3.

    MELEE AND RANGED TOGETHER, averaged, so a man has to be good at BOTH to
    reach the top rung. A one-eyed axeman stays at the eyebrow for ever.

        0    nothing
        1    a quarter        one brow, cocked down like the war face's
        2    half             ...and the beard
        3    past three       ...and the scar

    The marks are permanent once earned: they are what he has BECOME, so they
    are drawn UNDER whatever face he is wearing rather than being a mood.
    """
    k = (melee + ranged) * 0.5
    if k >= VET_SCAR:
        return 3
    if k >= VET_BEARD:
        return 2
    if k >= VET_BROW:
        return 1
    return 0


def eye_of(hx: float, hy: float, r: int):
    """WHERE THE FACE PUTS THE EYES, in screen coordinates.

    Returned as (centre_x, eye_y, separation), so an accessory can sit on an
    eye without re-deriving the arithmetic and drifting off it. draw() blits
    the sprite at int(hx) - width//2, which puts its centre pixel on int(hx),
    and the eyes are EYE_UP of the radius above that -- the same numbers
    _render uses, in one place, so they cannot disagree.
    """
    c = (2 * r + 2 * PAD + 1) // 2                 # the sprite's centre == the head's
    iy_local = int(round(c - r * EYE_UP))
    return (int(hx), int(hy) + (iy_local - c),
            max(3, int(round(r * EYE_SIDE))))


def monocle(screen, hx: float, hy: float, r: int) -> None:
    """A monocle, on ONE eye, drawn by whoever draws the head.

    Same terms as the crown: an accessory, not a mood, and it does not alter
    the face -- but where a crown sits on the skull, a monocle sits ON AN EYE,
    so it is laid over the face rather than beside it, and its rim does cross
    the brow above. That is what a monocle does.
    """
    ex, ey, sep = eye_of(hx, hy, r)
    cx = ex + sep                                  # the eye on his right
    rad = max(2, int(round(r * WHITE_R)) + 1)
    # ONE RING, PLACED BY HAND. pygame's circle OUTLINE is not a ring at this
    # size: at radius 3 it includes (cx+1, ey+1), which is exactly where the
    # pupil sits when a man faces north-east -- so a brass pixel landed IN his
    # eye. Sixteen points at a fixed distance is a ring, and stays one.
    seen = set()
    for _i in range(16):
        _a = _i * math.pi / 8.0
        _px = cx + int(round(math.cos(_a) * rad))
        _py = ey + int(round(math.sin(_a) * rad))
        if (_px, _py) not in seen:
            seen.add((_px, _py))
            pygame.draw.line(screen, LENS, (_px, _py), (_px, _py), 1)
    # and the chain, off the lower outer edge of the rim, hanging toward the jaw
    xs, ys = cx + rad - 1, ey + rad - 1
    pygame.draw.line(screen, LENS, (xs, ys),
                     (xs + max(1, r // 5), ys + max(2, int(round(r * 0.6)))), 1)


def crown(screen, hx: float, hy: float, r: int) -> None:
    """A crown, ON THE HEAD, drawn by whoever draws the head.

    NOT PART OF THE FACE, and that is the whole point of it being here rather
    than in _render. The face is CLIPPED TO THE HEAD -- nothing it draws may
    fall outside the circle -- so a crown built inside the face would have its
    band and its points cut off, which is all of a crown there is.

    And it is not a mood either. It is drawn OVER whatever face he is wearing
    and it does not alter a pixel of it: a king who is attacking, being hit,
    starving, working, smirking, or carrying every combat mark there is still
    wears the same crown on the same head.
    """
    # int(), NOT int(round()) -- draw() blits the face at int(hx) - width//2,
    # which puts the face's centre pixel on int(hx). Rounding here instead put
    # the crown on int(round(hx)), and those are different numbers whenever the
    # fraction is a half or more: walking on a diagonal, the crown slid a pixel
    # off the head and took two pixels of the starving man's brow with it.
    hx = int(hx)
    hy = int(hy)
    w = max(3, int(round(r * 0.62)))       # half its width: 5 at r=8, 11 across
    bh = max(2, r // 4)
    # THE BAND SITS ON THE HEAD'S TOP ROW, AND NO LOWER. It was a pixel lower
    # at first, which was fine for every face except a starving one: the
    # starved brows HANG, so their outer ends reach a row higher than the
    # resting ones, and the crown took two pixels off them. Measured: every
    # other mood and rank 0 covered, starving 2.
    bottom = hy - r
    top = bottom - bh
    # the band
    pygame.draw.rect(screen, CROWN, (hx - w, top, w * 2 + 1, bh))
    # three points, the middle one taller
    ph = max(2, r // 3)
    for px in (-w + 1, 0, w - 1):
        h = ph + (1 if px == 0 else 0)
        pygame.draw.polygon(screen, CROWN,
                            ((hx + px - max(1, r // 6), top),
                             (hx + px + max(1, r // 6), top),
                             (hx + px, top - h)))
    # and a darker edge, so it does not melt into the man's hair
    pygame.draw.line(screen, CROWN_D, (hx - w, bottom), (hx + w, bottom), 1)
    pygame.draw.line(screen, CROWN_D, (hx - w, top), (hx - w, bottom), 1)
    pygame.draw.line(screen, CROWN_D, (hx + w, top), (hx + w, bottom), 1)


def mood_of(hurt_flash: float, attack_flash: float,
            work_flash: float = 0.0, sly_flash: float = 0.0,
            starved: bool = False) -> str:
    """Which face a man is wearing, from the timers he is carrying.

    THE MOST RECENT EVENT WINS. Every one of these runs down at the same rate,
    so the one with the most left is the one that happened last: a man who has
    just been hit grimaces even though he swung a moment ago, and a man who
    lands a blow on top of a hit is snarling again. Equal goes to the hurt,
    because the blow that LANDED is the one he felt.
    """
    if starved:
        # FIRST, AND ABOVE EVERYTHING, because it is a state and not an
        # event: a starving man does not stop being starving mid-swing.
        return "starved"
    if hurt_flash > 0.0 and hurt_flash >= attack_flash:
        return "hurt"
    if attack_flash > 0.0:
        return "angry"
    # A DEAL BEATS A JOB -- but not a blow. Being shot at is more important
    # than being pleased with yourself.
    if sly_flash > 0.0:
        return "sly"
    if work_flash > 0.0:
        return "focus"
    return "normal"


def warm(radii=(8, 9), dirs=DIRS,
         moods=("normal", "focus", "angry", "hurt", "sly",
                  "starved")) -> int:
    """Build every face the game can ask for BEFORE the first frame.

    A cache miss in the middle of a frame is twelve draw calls where the frame
    was expecting one blit, so they are all built before the first frame: the
    drawing path is a dict lookup and a blit and nothing else, ever.

    ONLY THE HEADS IN PLAY. Every call in the game asks for radius 8 (a
    villager, a soldier) or 9 (the player) -- see the three face.draw() sites.
    Warming 4..12 was 1728 faces and 379 ms of startup for nine sizes nobody
    ever asks for; two sizes and four rungs is 384 faces.

    Anything else still works: it is built the first time it is asked for, and
    costs one frame's worth of draw calls once.
    """
    n = 0
    for r in radii:
        for d in range(dirs):
            for m in moods:
                for v in (0, 1, 2, 3):        # every rung of the ladder
                    sprite(r, d, m, v)
                    n += 1
    return n


def draw(screen, hx: float, hy: float, r: int, fx: float = 0.0,
         fy: float = 0.0, mood: str = "normal", skin=(216, 172, 132),
         vet: int = 0) -> None:
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
        surf = sprite(r, d, mood, vet)
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


# EVERY FACE THE GAME CAN ASK FOR, MADE NOW. Deleting this line only means the
# first man to face a new way pays for his own face once.
WARMED = warm()
