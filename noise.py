"""Deterministic value-noise / fBm used to generate terrain.

Everything here is a pure function of (coordinates, seed), so the same world
seed always produces exactly the same terrain. This is what lets the world be
"infinite" while remaining reproducible.
"""

from __future__ import annotations

import numpy as np


def _hash(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Hash integer lattice coordinates to floats in [0, 1)."""
    with np.errstate(over="ignore"):
        h = ix.astype(np.int64) * np.int64(374761393)
        h += iy.astype(np.int64) * np.int64(668265263)
        h += np.int64(seed) * np.int64(1013904223)
        h = (h ^ (h >> np.int64(13))) * np.int64(1274126177)
        h = h ^ (h >> np.int64(16))
        return (h & np.int64(0xFFFFFF)).astype(np.float32) / np.float32(0x1000000)


def value_noise(x, y, seed: int = 0):
    """Smooth value noise: bilinear interpolation of hashed lattice values."""
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    xf = (x - x0).astype(np.float32)
    yf = (y - y0).astype(np.float32)

    # smoothstep so gradients are continuous across cell borders
    u = xf * xf * (3.0 - 2.0 * xf)
    v = yf * yf * (3.0 - 2.0 * yf)

    a = _hash(x0, y0, seed)
    b = _hash(x0 + 1, y0, seed)
    c = _hash(x0, y0 + 1, seed)
    d = _hash(x0 + 1, y0 + 1, seed)

    top = a + (b - a) * u
    bot = c + (d - c) * u
    return top + (bot - top) * v


def fbm(x, y, seed: int = 0, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5):
    """Fractal Brownian motion: stacked value noise, normalised to [0, 1]."""
    total = np.zeros(np.broadcast(x, y).shape, dtype=np.float32)
    amp = 1.0
    freq = 1.0
    norm = 0.0
    for i in range(octaves):
        total += amp * value_noise(x * freq, y * freq, seed + i * 131)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm
