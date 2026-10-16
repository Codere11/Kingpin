"""terrain.py -- how far UP the ground is.

THE THIRD AXIS. Everything in this game has been flat: a man's position is
(x, y) and the world has one storey. This is the height of the ground, and it is
deliberately a SEPARATE FIELD rather than something cooked into the tiles --
`world.tile_kind()` says what the ground is made of, and this says how high it
is, and neither has to know about the other.

A MOUNTAIN HAS THREE PARTS, and getting any one of them wrong gives you
something that is not a mountain:

    WHERE   a very slow field that says whether this part of the world is
            mountain country at all. This is what makes RANGES -- long chains
            that run across the map -- instead of lumps sprinkled about.

    HOW     RIDGED noise: 1 - |2n-1|, which folds value noise about its middle
    TALL    so the flattest part of the noise becomes a CREASE. That crease is
            a ridge, and a field of them is a field of spurs and saddles. Plain
            noise gives rolling blobs, which read as hills.

    SHAPE   stacked octaves, each narrower and weaker than the last, so the
            massif has structure at every scale -- the whole thing, its
            shoulders, its gullies, the rubble on its flanks.

THE ONE HARD RULE: THE GROUND MUST STAY WALKABLE. `step_ok` lets a man go up
ONE metre, and he moves about 0.7 world pixels in a frame -- so if the field can
climb more than a metre in less than a metre of ground he can meet a face he
cannot pass and be stuck against it. The octaves are therefore built with a
bounded slope: every one of them climbs by less than a metre in ten pixels, and
six of them together stay under about a metre in three even where they line up.
Measured over the whole field, never once per frame.
"""

from __future__ import annotations

import numpy as np

from noise import fbm, value_noise

SEED = 20240501

# HOW TALL THE TALLEST SUMMIT IN THE WORLD IS. The field almost never reaches
# it -- that needs every octave at its crest at once -- so this is the SCALE,
# and the real peaks come out around four fifths of it. Set by measurement
# against a real world, not by hope.
MAX_M = 620.0

# WHERE THE RANGES ARE. One feature is about 62,000 world pixels across, so a
# chain runs for tens of thousands of pixels -- several days' walk -- and the
# towns, which sit 55,000 apart, each get their own piece of one.
RANGE_SCALE = 0.0000160
MASK_LO = 0.80            # below this it is lowland, and flat
MASK_HI = 0.74            # above this it is mountain, and as tall as it gets

# HOW STEEP THE SIDE OF A RANGE IS, and it varies: the band over which the
# ground climbs from lowland to mountain is between these, chosen by its own
# slow field. 0.035 is a cliff -- six hundred metres in about two thousand
# pixels, a twenty-eight per cent grade, which is a wall you look down. 0.175
# is the long shoulder you walk up.
MASK_BAND_MIN = 0.035
MASK_BAND_MAX = 0.175
CLIFF_SCALE = 0.0000210   # which ranges are cliffs, and on which side
# Chosen against the real field, over 120 km square: 12.6% of the world is
# above 100 m, 6.3% above 300, 1.5% above 450. A third of the world above
# 300 m was the first attempt, and a world that is a third mountain is not a
# world with mountains in it.

# HOW THE MASSIF IS BUILT. The widest octave is 20,000 px from crest to crest
# and the narrowest 625, which is twenty tiles -- big enough to see the grain of
# a slope, small enough that it is not noise on the screen.
BASE_LAM = 8000.0
OCTAVES = 6
GAIN = 0.62               # each octave this much weaker than the one before
LACUNARITY = 0.5          # ...and half the wavelength

# HOW FINELY THE FIELD IS SAMPLED FOR THE GROUND. Nothing in it is finer than
# a few hundred pixels and it is smooth everywhere, so asking it every single
# pixel was paying sixty times over for the same number. Two pixels, bilinear.
BLOCK_STEP = 4

# THE PHASE. A range has to be standing near the spawn or the world looks empty
# from where the player starts, and which range that is depends only on the
# seed, and these were FOUND by scanning every phase on a 2.5 km grid against
# two rules: THE START MUST BE FLAT (a man who spawns on a mountainside has no
# lowland to leave) and A REAL PEAK MUST BE WITHIN A SHORT WALK. This one gives
# a spawn at 22 metres and the first ground above 450 metres just 7,500 pixels
# away -- three minutes east. Fifty-one phases out of six hundred and twenty-
# five passed; this is the one where the mountain is closest.
OX = 55000.0
OY = 37500.0


def _mask(X, Y):
    """How much mountain there is here: 0 in the lowlands, 1 on the ranges.

    AND IT IS NOT THE SAME STEEPNESS EVERYWHERE. How wide the band is over
    which a range rises is set by another slow field, so in one place the
    ground lifts away over a kilometre and in the next the same range comes up
    as a WALL: a cliff face on one side and a long walkable shoulder on the
    other. That is what a real range looks like, and it is also the only shape
    that gives the thing worth having -- a man on top of it looking straight
    down at the ground he would have to walk a kilometre to reach.
    """
    m = fbm((X + OX) * RANGE_SCALE, (Y + OY) * RANGE_SCALE, SEED + 7, octaves=2)
    band = fbm((X + OX) * CLIFF_SCALE, (Y + OY) * CLIFF_SCALE, SEED + 91, octaves=2)
    band = MASK_BAND_MIN + (MASK_BAND_MAX - MASK_BAND_MIN) * band
    e = (m - MASK_LO) / band
    e = np.clip(e, 0.0, 1.0)
    return e * e * (3.0 - 2.0 * e)        # smoothstep: foothills, or a cliff


def _shape(X, Y):
    """The mountain's own shape, 0..1, ridged, with structure at every scale."""
    total = 0.0
    amp = 1.0
    lam = BASE_LAM
    norm = 0.0
    for i in range(OCTAVES):
        n = value_noise((X + OX) / lam, (Y + OY) / lam, SEED + 31 + i * 17)
        total = total + amp * (1.0 - np.abs(2.0 * n - 1.0))
        norm += amp
        amp *= GAIN
        lam *= LACUNARITY
    return total / norm


def height_array(X, Y):
    """The height field over numpy grids -- one pass, whatever the size.

    This is the whole reason a higher viewpoint costs nothing: the ground is
    sampled on a GRID whose size never changes, and only the SPAN the grid
    covers grows with height.

    WHOLE METRES. The field underneath is smooth and continuous, and it has to
    be -- but every step DOWN is drawn with a dark lip, and a lip is found by
    asking whether the ground five pixels away is at a different height. In
    continuous metres that is true at EVERY pixel and the whole mountain comes
    out dark. In whole metres it is true only where the ground actually steps,
    which is what a staircase is.
    """
    X = np.asarray(X, np.float32)
    Y = np.asarray(Y, np.float32)
    return np.floor(MAX_M * _mask(X, Y) * _shape(X, Y)).astype(np.float32)


def height_at(x: float, y: float) -> int:
    """How many metres up the ground is at (x, y). Zero is sea level.

    Scalar, and on the frame path -- only the player ever asks it, three or four
    times a frame, so it is allowed to be a plain noise evaluation.
    """
    x = np.float32(x)
    y = np.float32(y)
    m = fbm((x + OX) * RANGE_SCALE, (y + OY) * RANGE_SCALE, SEED + 7, octaves=2)
    b = float(fbm((x + OX) * CLIFF_SCALE, (y + OY) * CLIFF_SCALE, SEED + 91,
                  octaves=2))
    e = (float(m) - MASK_LO) / (MASK_BAND_MIN
                                + (MASK_BAND_MAX - MASK_BAND_MIN) * b)
    e = 0.0 if e < 0.0 else (1.0 if e > 1.0 else e)
    e = e * e * (3.0 - 2.0 * e)
    if e <= 0.0:
        return 0
    total = 0.0
    amp = 1.0
    lam = BASE_LAM
    norm = 0.0
    for i in range(OCTAVES):
        n = float(value_noise((x + OX) / lam, (y + OY) / lam,
                              SEED + 31 + i * 17))
        total += amp * (1.0 - abs(2.0 * n - 1.0))
        norm += amp
        amp *= GAIN
        lam *= LACUNARITY
    return int(MAX_M * e * (total / norm))


def slope_at(x: float, y: float) -> int:
    """How many metres the ground rises in the tile ahead -- the step he faces.

    +1 is a step he can walk up, +2 is one he cannot, and negative is a drop he
    is welcome to take.
    """
    return height_at(x, y)


# AS HIGH AS HE MAY STEP IN ONE MOVE. It was one metre, and one metre is
# wrong, because a MOVE is not a metre: walking covers four pixels a frame and
# sprinting covers seven, and on ground that climbs a metre every two pixels
# that is two or three metres of climb inside a single step -- so he would be
# stopped dead on a slope he could plainly walk up. Measured, on the massif, it
# was happening.
#
# Three metres, and the number is not arbitrary: HE CAN JUMP TWO AND A HALF. A
# man who can jump onto a ledge can walk onto it, and the rule is now the one
# he would expect -- if it is walkable, it is jumpable, and if it is jumpable,
# it is walkable.
STEP_UP_M = 2.5          # the knee: what he can get over with no run at all
SLOPE_MAX = 0.75         # and the grade he can keep his feet on, metre per metre


def step_ok(z: int, x: float, y: float, airborne: bool,
            dist: float = 0.0) -> bool:
    """May he move to (x, y) from height z, having come `dist` pixels?

    A WALL IS A WALL AND A SLOPE IS NOT, and the difference is DISTANCE. A
    fixed allowance cannot tell them apart: walking covers four pixels a frame
    and sprinting covers seven, so on ground that climbs a metre every two
    pixels a sprint crosses three metres in one step where a walk crosses one
    -- and the sprinter was stopped dead on a slope the walker strolled up.

    So the allowance is the grade he can stand on, times how far he moved, plus
    the knee he can get over from a standstill. Sprinting SIXTY PER CENT FASTER
    now buys sixty per cent more climb in the same step, which is the whole
    point of sprinting, and a two-metre ledge is still a wall because no
    distance of walking along the ground gets you up it.
    """
    h = height_at(x, y)
    if h <= z + STEP_UP_M + SLOPE_MAX * dist:
        return True
    return airborne
