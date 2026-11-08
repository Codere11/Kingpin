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
# THE OLD MAN OF THE REPUBLIC. Iron grey, swept back off the forehead, and a
# moustache thick enough to be the first thing anybody remembers about him.
HAIR_GREY = (150, 152, 156)
HAIR_GREY_LIGHT = (186, 188, 192)
MOUSTACHE = (176, 178, 182)
MOUSTACHE_DARK = (132, 134, 138)
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

# -- NATIVE HAIR, FEATHER AND WAR PAINT (the republic is a native one) ------
NAT_HAIR = (30, 20, 14)        # long black hair
NAT_HAIR_SH = (58, 40, 26)     # a shine strand
NAT_FEATHER = (240, 240, 244)  # the white feather vane
NAT_FEATHER_TIP = (196, 40, 36)  # its red tip
NAT_QUILL = (110, 84, 56)      # the quill
NAT_PAINT = (188, 40, 30)      # war paint across the eyes

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
STARVED_SATIETY = 20.0      # THE SAME LINE, FROM THE OTHER END. A villager
                            # carries `hunger`, which rises; the PLAYER carries
                            # `hunger`, which is SATIETY and falls. Passing the
                            # player's straight into STARVED_HUNGER gave him the
                            # starved face at FULL BELLY (100 >= 80) and took it
                            # off him as he starved.
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
    sleeping = (mood == "sleep")

    if mood == "dead":
        # THE DEAD FACE. The same head as ever -- ONE X across the middle,
        # where the eyes were, and his tongue out. No brows, no pupils, no
        # looking: nothing in it is alive.
        # A PROPER X. Two strokes, two pixels thick, square (as wide as it is
        # tall), crossing in a solid block at the middle of the face and ending
        # a pixel inside the head's rim. A one-pixel X on a head this small
        # pinches to nothing at the crossing and its ends read as whiskers; a
        # flat one reads as goggles. This is the ratio that reads.
        _h = max(3, r // 2)                      # half-size: 4 at r=8 -> 10x10
        _lim = (r - 1) * (r - 1)

        def _stroke(_sx, _sy) -> None:
            for _i in range(-_h, _h + 1):
                for _j in (0, 1):                # the second row: thickness
                    _px = ix + _i * _sx
                    _py = iy + _i * _sy + _j
                    if (_px - ix) ** 2 + (_py - iy) ** 2 <= _lim:
                        screen.set_at((_px, _py), EYE)

        _stroke(1, 1)
        _stroke(1, -1)
        my = int(round(hy + r * MOUTH_DOWN))
        pygame.draw.line(screen, MOUTH, (ix - max(2, r // 3), my),
                         (ix + max(2, r // 3), my), 1)
        # the tongue, hanging out of it
        pygame.draw.ellipse(screen, TONGUE,
                            (ix - 2, my, max(4, r // 2), max(4, int(r * 0.7))))
        return

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
    if sleeping:
        # EYES CLOSED: one calm line where each eye is, and nothing looking.
        for sgn in (-1, 1):
            cx = ix + sgn * sep
            pygame.draw.line(screen, EYE, (cx - wr, iy), (cx + wr, iy), 1)
    else:
        for sgn in (() if hurt else (-1, 1)):
            cx = ix + sgn * sep
            pygame.draw.circle(screen, WHITE, (cx, iy), wr)
            if lid:
                # A SLIT, AND THEN THE PUPIL ON TOP OF IT. The lid comes FIRST
                # so that it cuts the white down to a band, and the pupil is
                # drawn after so the man is still looking at something -- drawn
                # the other way round the slit was blank and the face went dead.
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


# -- the top hat ------------------------------------------------------------
# A FELT BLACK with a little colour in it, so it reads against the ground
# rather than as a hole in it, and a band, which is the only thing that says
# "hat" rather than "tall rectangle".
HAT_BRIM = (22, 18, 20)
HAT_BODY = (40, 34, 36)
HAT_TOP = (58, 50, 54)         # the crown catches a little light
HAT_BAND = (150, 40, 44)
HAT_GLINT = (86, 76, 80)       # one bright column down the left of the crown


def tophat(screen, hx: float, hy: float, r: int) -> None:
    """A TOP HAT, worn by the mayor.

    It replaces the monocle, and it goes ON rather than UNDER. The monocle was
    under the face because its rim would otherwise cut across an eye; a hat is
    above the head and covers nothing but the head's own top row, so there is
    nothing underneath it to lose.

    Same terms as the crown: an accessory, not a mood. It is drawn AFTER
    whatever face he is wearing and does not alter a pixel of it -- a mayor who
    is attacking, being hit, starving, working or smirking wears the same hat.

    AND IT SITS ON THE HEAD, WHICH MEANS THE HEAD'S TOP IS `hy - r`. The brim
    overlaps that row by one pixel, because a hat resting a full pixel above
    the skull looks like it is floating, and at seventeen pixels across
    everything has to be argued for.
    """
    # int(), NOT int(round()) -- draw() blits the face at int(hx) - width // 2,
    # so int(hx) is the column the face's centre pixel lands on. Rounding put
    # the crown a pixel off the head; the same rule applies here.
    hx = int(hx)
    hy = int(hy)
    bottom = hy - r                         # the head's top row
    brim_half = max(3, int(round(r * 0.95)) + 2)
    body_half = max(2, int(round(r * 0.60)))
    body_h = max(3, int(round(r * 1.15)))
    brim_y = bottom - 1                     # one pixel down, over the skull
    body_y = brim_y - body_h
    # THE CROWN OF THE HAT
    pygame.draw.rect(screen, HAT_BODY, (hx - body_half, body_y,
                                        body_half * 2 + 1, body_h + 1))
    pygame.draw.line(screen, HAT_TOP, (hx - body_half, body_y),
                     (hx + body_half, body_y), 1)
    # one bright column down the left, which is what gives it a direction
    pygame.draw.line(screen, HAT_GLINT, (hx - body_half + 1, body_y + 1),
                     (hx - body_half + 1, body_y + body_h - 2), 1)
    # THE BAND, two rows above the brim
    band_y = brim_y - max(1, body_h // 5)
    pygame.draw.line(screen, HAT_BAND, (hx - body_half, band_y),
                     (hx + body_half, band_y), max(1, body_h // 6))
    # AND THE BRIM, wider than the head is, two rows and over its top
    pygame.draw.rect(screen, HAT_BRIM, (hx - brim_half, brim_y,
                                        brim_half * 2 + 1, 2))


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


CAP_BAND = (58, 62, 52)          # the cap's band: dark olive
CAP_CROWN = (74, 80, 66)         # ...the crown, a shade lighter on top
CAP_DARK = (34, 36, 30)          # its edge, and the peak
STAR_RED = (176, 34, 30)         # the star, and nothing else in the world is red
STAR_LIGHT = (214, 62, 52)
# THE DICTATOR'S CAP IS THE REPUBLIC'S OWN RED. Same cap, same star -- the
# colour is the rank.
# THE MILITIA'S CAP IS DARK BLUE, and the star on it is the same star.
CAP_NAVY_BAND = (34, 46, 92)
CAP_NAVY_CROWN = (44, 58, 112)
CAP_NAVY_DARK = (20, 26, 54)
CAP_RED_BAND = (150, 30, 28)
CAP_RED_CROWN = (176, 42, 36)
CAP_RED_DARK = (92, 18, 18)
STAR_GOLD = (232, 196, 84)


def _star(screen, cx: float, cy: float, r_out: float,
          colour=STAR_RED, colour2=STAR_LIGHT) -> None:
    """A FIVE-POINTED STAR, big enough to be unmistakable at four pixels."""
    import math as _m
    pts = []
    for i in range(10):
        ang = -_m.pi / 2.0 + i * _m.pi / 5.0
        r = r_out if i % 2 == 0 else r_out * 0.45
        pts.append((cx + _m.cos(ang) * r, cy + _m.sin(ang) * r + 0.4))
    pygame.draw.polygon(screen, colour, pts)
    pygame.draw.polygon(screen, colour2, pts, 1)


def cap(screen, hx: float, hy: float, r: int, fx: float = 0.0,
        fy: float = 0.0, red: bool = False, blue: bool = False) -> None:
    """A PEAKED CAP OF THE REPUBLIC, WITH THE STAR ON THE FRONT.

    It sits ON the skull: the crown and band above the eye line, the black peak
    jutting out over the brow, and the red star on the band in front -- high
    enough that it never covers an eye.
    """
    try:
        r = int(r)
        hx, hy = float(hx), float(hy)
        n = (fx * fx + fy * fy) ** 0.5 or 1.0
        ux = fx / n
        if red:
            band_col, crown_col, dark_col = CAP_RED_BAND, CAP_RED_CROWN, CAP_RED_DARK
        elif blue:
            band_col, crown_col, dark_col = CAP_NAVY_BAND, CAP_NAVY_CROWN, CAP_NAVY_DARK
        else:
            band_col, crown_col, dark_col = CAP_BAND, CAP_CROWN, CAP_DARK
        band_top = hy - r * 0.95
        band_h = max(3, int(round(r * 0.45)))
        half = r + 1
        # crown, flared, above the band
        crown = pygame.Rect(int(hx - half - 1), int(band_top - r * 0.62),
                            int((half + 1) * 2), int(r * 0.75))
        pygame.draw.ellipse(screen, crown_col, crown)
        pygame.draw.ellipse(screen, dark_col, crown, 1)
        # the band
        band = pygame.Rect(int(hx - half), int(band_top), int(half * 2), band_h)
        pygame.draw.rect(screen, band_col, band)
        pygame.draw.rect(screen, dark_col, band, 1)
        # the peak: a dark line under the band, forward of it
        py = band.bottom - 1
        pygame.draw.line(screen, dark_col, (int(hx - half + 1), py),
                         (int(hx + half - 1), py), 1)
        pygame.draw.line(screen, dark_col,
                         (int(hx - half + 2 + ux * 2), py + 1),
                         (int(hx + half - 2 + ux * 2), py + 1), 1)
        # THE STAR, ON THE FRONT OF THE BAND -- above the eyes, never on them
        sx = hx + ux * half * 0.55
        sy = band_top + band_h * 0.5
        if red:
            _star(screen, sx, sy, max(1.9, r * 0.26), STAR_GOLD, (255, 232, 140))
        else:
            _star(screen, sx, sy, max(1.9, r * 0.26))
    except Exception:
        pass


def moustache(screen, hx: float, hy: float, r: int) -> None:
    """STALIN'S MOUSTACHE: a broad walrus, thicker at the wings than the middle.

    It starts under the nose, runs wider than the mouth on both sides, and the
    ends hang below the line of the lip. Drawn in two greys so the thickness
    reads at eight pixels of head.
    """
    try:
        r = int(r)
        hx, hy = int(round(hx)), int(round(hy))
        half = max(4, int(round(r * 0.85)))
        top = hy + max(1, int(round(r * 0.10)))
        # ONE SOLID MASS: every column is drawn from its own top down to a flat
        # bottom, so the wings hang lower than the middle and there is no hole
        # in it -- a moustache with a gap in the middle is a moustache with a
        # hole in it.
        for i in range(-half, half + 1):
            droop = int(round(0.32 * abs(i)))
            px = hx + i
            pygame.draw.line(screen, MOUSTACHE, (px, top + droop),
                             (px, top + 2 + droop))
        # a dark edge along the underside, so it sits on the lip as a shape
        for i in range(-half, half + 1):
            droop = int(round(0.32 * abs(i)))
            pygame.draw.line(screen, MOUSTACHE_DARK,
                             (hx + i, top + 2 + droop), (hx + i, top + 2 + droop))
    except Exception:
        pass


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


def hair(screen, hx: float, hy: float, r: int) -> None:
    """Long black hair framing the head, and only a little below the face.
    Drawn BEFORE the head skin and face, so it frames them rather than
    covering them -- and it never runs down the body."""
    try:
        r = int(r)
        hx, hy = float(hx), float(hy)
        # a thick halo of long hair around the top, sides and just below the jaw
        pygame.draw.circle(screen, NAT_HAIR, (int(hx), int(hy - r * 0.05)), r + 4)
        # a short fringe under the jaw -- slightly below the face, not the body
        pygame.draw.rect(screen, NAT_HAIR,
                         (int(hx - r), int(hy + r * 0.55),
                          int(2 * r), int(r * 0.7)), border_radius=3)
        # a shine strand over the crown
        pygame.draw.arc(screen, NAT_HAIR_SH,
                        (int(hx - r), int(hy - r - 2), int(2 * r), int(2 * r)),
                        math.pi, math.pi * 1.55, 2)
    except Exception:
        pass


def feather(screen, hx: float, hy: float, r: int,
            fx: float = 0.0, fy: float = 0.0) -> None:
    """A single styled feather PINNED to the back-left of the head. It does
    not turn with the facing -- the eyes do that; the feather stays fixed."""
    try:
        r = int(r)
        hx, hy = float(hx), float(hy)
        bx = hx - r * 0.45          # fixed base, back-left of the crown
        by = hy - r * 0.72
        qx = bx - r * 1.05          # fixed tip, out to the back-left
        qy = by - r * 0.45
        pygame.draw.line(screen, NAT_QUILL, (int(bx), int(by)), (int(qx), int(qy)), 1)
        pygame.draw.line(screen, NAT_FEATHER, (int(bx), int(by) - 1),
                         (int(qx), int(qy) - 1), 2)
        pygame.draw.line(screen, NAT_FEATHER, (int(bx), int(by) + 1),
                         (int(qx), int(qy) + 1), 2)
        pygame.draw.line(screen, NAT_FEATHER_TIP, (int(qx), int(qy)),
                         (int(qx - r * 0.35), int(qy - r * 0.15)), 2)
    except Exception:
        pass


def war_paint(screen, hx: float, hy: float, r: int,
              fx: float = 0.0, fy: float = 0.0) -> None:
    """A thin stripe of red war paint across the eye area. The eyes stay
    visible ON TOP of it, so the paint never crosses them."""
    try:
        r = int(r)
        hx, hy = float(hx), float(hy)
        sep = max(3, int(round(r * EYE_SIDE)))
        wr = max(2, int(round(r * WHITE_R)))
        pr = max(1, int(round(r * PUPIL_R)))
        ix, iy = int(round(hx)), int(round(hy - r * EYE_UP))
        hw = int(r * 0.55)
        pygame.draw.line(screen, NAT_PAINT, (ix - hw, iy), (ix + hw, iy), 3)
        # the eyes on top, so the stripe reads as paint AROUND them, not over
        for sgn in (-1, 1):
            cx = ix + sgn * sep
            pygame.draw.circle(screen, WHITE, (cx, iy), wr)
            pygame.draw.circle(screen, EYE,
                               (cx + int(round(fx * wr * 0.55)),
                                iy + int(round(fy * wr * 0.55))), pr)
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
