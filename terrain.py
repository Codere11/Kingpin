"""terrain.py -- how far UP the ground is.

THE THIRD AXIS. Everything in this game has been flat: a man's position is
(x, y) and the world has one storey. This is the floor above and the floor
below, and it is deliberately a SEPARATE FIELD rather than something cooked
into the tiles -- `world.tile_kind()` says what the ground is made of, and this
says how high it is, and neither has to know about the other.

FOR NOW THERE IS ONE MOUNTAIN, a square staircase just east of the spawn, and
it exists to be looked at. Real mountains want real noise; a staircase wants
six lines of arithmetic and tells you immediately whether the idea is any good.

WHY A SQUARE. Because a step has to be WALKABLE and a square step is exactly
one tile wide all the way round, which makes "one metre up" a thing you can
count off with your feet. A cone would give you fractional steps everywhere and
you could not tell a metre from a slope.
"""

from __future__ import annotations

import numpy as np

# THE STAIRCASE, just east of the spawn at (0, 0).
MOUNT_X = 430.0          # its centre
MOUNT_Y = -210.0
MOUNT_TOP = 9            # how many metres up the middle is
STEP = 40.0              # how much ground one metre of climb takes

# ONE METRE OF HEIGHT, IN WORLD PIXELS, when you look down at it. A tile is
# 32 px, so a metre is a bit more than a tile.
METRE = 32.0


def height_at(x: float, y: float) -> int:
    """How many metres up the ground is at (x, y). Zero is the flat world."""
    dx = abs(float(x) - MOUNT_X)
    dy = abs(float(y) - MOUNT_Y)
    d = dx if dx > dy else dy                 # a square, so a step is a step
    up = MOUNT_TOP - int(d / STEP)
    return up if up > 0 else 0


def height_array(X, Y):
    """The same thing over numpy grids -- one op, whatever the size of the view.

    This is the whole reason a higher viewpoint costs nothing: the ground is
    sampled on a GRID whose size never changes, and only the SPAN the grid
    covers grows with height.
    """
    dx = np.abs(np.asarray(X, np.float32) - MOUNT_X)
    dy = np.abs(np.asarray(Y, np.float32) - MOUNT_Y)
    d = np.maximum(dx, dy)
    up = MOUNT_TOP - np.floor(d / STEP)
    return np.maximum(0.0, up).astype(np.float32)


def slope_at(x: float, y: float) -> int:
    """How many metres the ground rises in the tile ahead -- the step he faces.

    +1 is a step he can walk up, +2 is one he cannot, and negative is a drop he
    is welcome to take.
    """
    return height_at(x, y)


def step_ok(z: int, x: float, y: float, airborne: bool) -> bool:
    """May he move to (x, y) from height z?

    ONE METRE UP, OR JUMP IT. Everything else is legal: any drop, any distance
    along a level, and one step at a time -- but a two-metre wall is a wall
    until his feet leave the ground.
    """
    h = height_at(x, y)
    if h <= z + 1:
        return True
    return airborne
