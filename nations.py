"""ONE state, three capitals.

There is no longer any such thing as a rival nation. One government rules the
whole map: `nation_index()` answers 0 everywhere, `count()` is 1, and the only
political facts left are WHERE the state keeps its seats -- a Main Capital and
two Regional Capitals -- and how far a man is from them.

The three capital SITES are kept deliberately. They are three real places on the
map, they are the biggest towns, and they are the three things worth taking.

Villages are no longer their own nation: every village belongs to one of a
handful of nations, decided by a *warped* Voronoi partition of the map, so the
borders are organic and wavy rather than straight lines. The same function is
used at runtime (who owns this village / soldier) and to paint the map, so the
politics on screen match the politics in play.
"""

from __future__ import annotations

import math

import numpy as np

from noise import value_noise

# ONE NAME AND ONE COLOUR. The colours were three flags; there is one flag now,
# and it is the colour of the thing that took the map.
NAMES = ["Ashmark"]
COLORS = [(142, 46, 40)]

# WHICH CAPITAL IS THE SEAT. The other two are regional: real capitals, real
# governors, no throne.
MAIN_CAPITAL = 0

# THE CORNERS, NOT THE MIDDLE. Three capitals sat in a triangle around the
# centre of a world that runs from -100,000 to +100,000, so every kingdom's
# heartland was crammed into the same few thousand yards and the far edges
# belonged to whoever happened to be nearest. Pushed out to the corners, each
# nation owns a real quarter of the map, its capital is as far from its
# rivals as the world allows, and a conquest has somewhere to march TO.
CAPITALS = [(-84000.0, -84000.0), (84000.0, -84000.0),
            (0.0, 84000.0)]        # two far corners and the far south, so
            # three Voronoi cells tile the square evenly instead of two
            # taking everything and the third a wedge.
WEIGHTS = [1.2, 1.2, 0.75]         # bigger weight => bigger territory.
# Tuned against the new corner capitals: the two northern kingdoms meet in the
# middle and the southern one takes the rest, and these weights split the map
# 33% / 33% / 33%. It was 28 / 29 / 43 with the old triangle, which is not a
# balance, it is a kingdom that starts the game a third bigger than its rivals.


def count() -> int:
    """One government."""
    return 1


def name(index: int) -> str:
    return NAMES[int(index) % len(NAMES)]


def color(index: int):
    return COLORS[int(index) % len(COLORS)]


def capital(index: int):
    return CAPITALS[int(index) % len(CAPITALS)]


_CAPITAL_CELLS: dict = {}


def _capital_cells(spacing: float):
    """The three capital cells, worked out ONCE.

    Finding a capital means asking the Voronoi who owns each of eighty-one
    cells, which is fine three times and ruinous three hundred thousand times:
    the tree generator asks about every cell in the world, and it turned a
    twenty-second load into a freeze. The answer never changes, so it is
    computed once and then looked up.
    """
    got = _CAPITAL_CELLS.get(spacing)
    if got is not None:
        return got
    found = {}
    for idx in range(count()):
        kx, ky = capital(idx)
        kgx = int(kx / spacing - 0.5)
        kgy = int(ky / spacing - 0.5)
        best = None
        for ax in range(kgx - 4, kgx + 5):
            for ay in range(kgy - 4, kgy + 5):
                px, py = (ax + 0.5) * spacing, (ay + 0.5) * spacing
                if nation_index(px, py) != idx:
                    continue
                d = (px - kx) ** 2 + (py - ky) ** 2
                if best is None or d < best[0]:
                    best = (d, ax, ay)
        if best is not None:
            found[(best[1], best[2])] = idx
    _CAPITAL_CELLS[spacing] = found
    return found


def is_capital_cell(gx: int, gy: int, spacing: float) -> bool:
    """Is this village cell its nation's capital? Same answer as ever."""
    return (gx, gy) in _capital_cells(spacing)


def _warp(x, y):
    """Push points around with smooth noise so borders are natural, not straight."""
    n1 = value_noise(x * 0.00016 + 11.0, y * 0.00016 - 7.0, 501)
    n2 = value_noise(x * 0.00016 - 3.0, y * 0.00016 + 5.0, 733)
    return x + (n1 - 0.5) * 17000.0, y + (n2 - 0.5) * 17000.0


def nation_index(x: float, y: float) -> int:
    """The one state owns everything. Kept as a function because a hundred
    callers ask who owns a man, and the answer is the same everywhere."""
    return 0


def is_main_capital(x: float, y: float) -> bool:
    """The seat. There is one throne, and this is where it is."""
    cx, cy = CAPITALS[MAIN_CAPITAL]
    return math.hypot(float(x) - cx, float(y) - cy) < 4000.0


def overlay(xgrid: np.ndarray, ygrid: np.ndarray) -> np.ndarray:
    """One colour over the whole map. There are no borders left to paint."""
    best = np.zeros(xgrid.shape, dtype=np.int8)
    best_d = np.full(xgrid.shape, 1e18, dtype=np.float32)
    return best
