"""The three nations of the world.

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

NAMES = ["Crowlands", "Ashmark", "Redreach"]
COLORS = [(176, 60, 54), (58, 92, 178), (96, 142, 76)]

CAPITALS = [(-52000.0, -38000.0), (54000.0, -30000.0),
            (4000.0, 56000.0)]     # scaled with the world: three kingdoms
            # still cover the whole of it, and no town is left stateless.
WEIGHTS = [1.02, 1.10, 0.94]        # bigger weight => bigger territory


def count() -> int:
    return len(CAPITALS)


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
    wx, wy = _warp(float(x), float(y))
    best, best_d = 0, 1e18
    for i, (cx, cy) in enumerate(CAPITALS):
        d = ((float(wx) - cx) ** 2 + (float(wy) - cy) ** 2) / (WEIGHTS[i] ** 2)
        if d < best_d:
            best_d, best = d, i
    return best


def overlay(xgrid: np.ndarray, ygrid: np.ndarray) -> np.ndarray:
    """Per-pixel nation index for the whole grid (for map tinting)."""
    wx, wy = _warp(xgrid, ygrid)
    best = np.zeros(xgrid.shape, dtype=np.int8)
    best_d = np.full(xgrid.shape, 1e18, dtype=np.float32)
    for i, (cx, cy) in enumerate(CAPITALS):
        d = ((wx - cx) ** 2 + (wy - cy) ** 2) / (WEIGHTS[i] ** 2)
        closer = d < best_d
        best_d = np.where(closer, d, best_d)
        best = np.where(closer, np.int8(i), best)
    return best
