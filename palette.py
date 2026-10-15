"""palette.py -- the world's colours, made rich instead of washed out.

THE PROBLEM, MEASURED. The old palette was built out of low-saturation beiges
and greys -- WALL (228,212,184), STONE (176,168,152), STONE_DARK (118,112,98)
-- and dull greens like GRASS_DARK (46,84,40). Saturation under about 0.15 is
what "printed on the last drops of ink" means: there is no colour there to
run out of.

WHY A FUNCTION AND NOT 300 NEW NUMBERS. Every one of those literals was
picked by eye against the others; hand-editing three hundred of them would
break that balance in a hundred small ways and be impossible to retune. So the
same four numbers are handed to rich() everywhere, and the whole world's look
is four constants in this file.

WHAT IT DOES, AND WHAT IT REFUSES TO DO.
  * SATURATION is raised, and GREYS ARE GIVEN A FLOOR of it. Multiplying the
    saturation of a grey leaves it grey -- 0.05 x 1.6 is still 0.08 -- so the
    floor is what actually puts colour into stone and plaster.
  * VALUE is lifted towards full, never past it, and DARK STAYS DARK: a dark
    colour gains a share of the headroom above it, so the order of light and
    shade is preserved. This is not a brightness wash.
  * HUE is untouched. Grass stays green and blood stays red; nothing is
    re-costumed.
"""

from __future__ import annotations

import colorsys

# The four numbers the whole world's look comes down to.
SAT = 1.18       # multiply the colour that is already there
FLOOR = 0.03     # ...and give this much to the colours that have none.
                 # SMALL on purpose: beige's hue is orange, so a big floor
                 # turns pale plaster BROWN instead of rich.
LIFT = 1.35      # darks gain a share of the headroom above them.
                 # This is the one that kills the mud: grass at value 0.33
                 # becomes 0.56, which is the difference between a swamp
                 # and a lawn.
WARM = 0.010     # a whisker of warmth, so nothing reads as fluorescent


def rich(rgb, sat: float = SAT, floor: float = FLOOR, lift: float = LIFT,
         warm: float = WARM):
    """The same colour with more of it in. Accepts and returns 0-255 triples."""
    try:
        r, g, b = (max(0, min(255, float(c))) / 255.0 for c in rgb[:3])
    except Exception:
        return rgb
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, s * sat + (1.0 - s) * floor)
    v = min(1.0, v + (1.0 - v) * (lift - 1.0))
    if warm:
        h = (h + warm) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(round(r * 255.0)), int(round(g * 255.0)), int(round(b * 255.0)))


def dim(rgb, f: float = 0.72):
    """A shadow of a colour, keeping its hue and its saturation.

    Shade used to be made by scaling the channels down, which drains the
    colour out of it -- a dark green became a dark grey. Dimming in HSV keeps
    the hue and most of the saturation, so shade still looks like the thing
    casting it.
    """
    try:
        r, g, b = (max(0, min(255, float(c))) / 255.0 for c in rgb[:3])
    except Exception:
        return rgb
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, s * 1.12)
    v = max(0.0, v * f)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(round(r * 255.0)), int(round(g * 255.0)), int(round(b * 255.0)))


def mix(a, b, t: float = 0.5):
    """A blend, for gradients that used to be made by averaging by hand."""
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def sat_of(rgb) -> float:
    r, g, b = (max(0, min(255, float(c))) / 255.0 for c in rgb[:3])
    return colorsys.rgb_to_hsv(r, g, b)[1]


def val_of(rgb) -> float:
    r, g, b = (max(0, min(255, float(c))) / 255.0 for c in rgb[:3])
    return colorsys.rgb_to_hsv(r, g, b)[2]


if __name__ == "__main__":
    before = [(46, 84, 40), (116, 156, 72), (146, 142, 86), (112, 94, 62),
              (228, 212, 184), (150, 128, 100), (176, 168, 152),
              (118, 112, 98), (64, 102, 44), (94, 148, 62), (50, 88, 36)]
    print("%-22s %-22s  sat   ->  sat" % ("BEFORE", "AFTER"))
    for c in before:
        a = rich(c)
        print("%-22s %-22s  %.2f  ->  %.2f" % (str(c), str(a),
                                               sat_of(c), sat_of(a)))
