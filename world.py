"""World model and ground rendering.

Design
------
The world is logically a grid of tiles (``TILE`` px each) so gameplay systems
can later query "what is at tile (tx, ty)?". But the *visual* ground is NOT
drawn per tile. It is a continuous noise field sampled in world space, so
neighbouring pixels always relate to each other and there is no repeating unit
to spot. Scattered detail (tufts, flowers, pebbles) lives on a separate
deterministic lattice, independent of the tile grid, and freely crosses tile
and chunk borders.

Performance
-----------
The smooth colour fields are generated at low resolution (they are low
frequency, so nothing visible is lost) and smoothly upscaled once per chunk.
Crisp per-pixel texture is added by multiplying in a small precomputed grain
texture -- high-frequency grain repeating is imperceptible, unlike repeating
*structure*. Scatter supplies the readable detail.
"""

from __future__ import annotations

import math
import queue
import random
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
import pygame
from palette import rich, dim

import biomes
from noise import _hash, fbm, value_noise

# --- world geometry ---------------------------------------------------------
TILE = 32            # logical tile size, used by gameplay, not by the visuals
CHUNK = 256          # ground chunk size in pixels
GEN = 32             # smooth colour fields are generated at GEN x GEN
PAD = 1              # extra low-res samples so chunk borders interpolate cleanly
GRAIN = 256          # full-res grain texture size (== CHUNK)
SCATTER_CELL = 64    # one scatter lattice cell; 1-3 details are placed inside
SCATTER_CHUNK = 256  # scatter is baked into chunk surfaces and blitted

# --- palette ----------------------------------------------------------------
GRASS_DARK = rich((46, 84, 40))
GRASS_LITE = rich((116, 156, 72))
GRASS_DRY = rich((146, 142, 86))
GRASS_DIRT = rich((112, 94, 62))

# --- THE COLONIAL COAST -----------------------------------------------------
# Land to the WEST, endless impassable ocean to the EAST, and a sand beach
# between. The coastline is fBm noise, so it reads as a natural coast with
# bays and headlands -- never a straight ruler line.
COAST_X = 0.0            # the beach sits on the world's x=0 meridian
SAND_W = 110.0           # beach width in pixels
WATER = (30, 88, 146)                            # the strong blue water overlay
WATER_ALPHA = 170                                # ...painted over the sea floor
SAND = np.array((202, 178, 130), np.float32)    # warm pixel sand (beach AND sea floor)
ALGAE = (86, 205, 96)                            # bright green algae, under the water


# The coastline is static, yet the engine and the ship both asked for it
# EVERY frame (a scalar fbm each) and every spawn roll asked again. Memoise
# scalar answers; arrays (tree blocks) pass straight through.
_COAST_MEMO: dict = {}


def coast_x(y, seed):
    """The shoreline x for a given world y. fBm value noise (scalars and
    arrays alike) so the coast wiggles naturally with bays and headlands.
    A scalar in gives a plain float out (so it never poisons pygame.Rect)."""
    if getattr(y, "ndim", 0) == 0:
        key = (round(float(y), 1), seed)
        got = _COAST_MEMO.get(key)
        if got is not None:
            return got
    yy = np.asarray(y, np.float32) * 0.008
    n = fbm(np.float32(0.0), yy, seed + 77, octaves=3)
    r = COAST_X + (n - 0.5) * 300.0
    out = float(r) if getattr(r, "ndim", 0) == 0 else r
    if getattr(y, "ndim", 0) == 0:
        if len(_COAST_MEMO) < 200000:
            _COAST_MEMO[key] = out
    return out


# plot kinds that count as worked / planted soil (must match crop.py)
_WORKED = ("dirt", "fertile", "plant", "wheat", "berries", "mushroom",
           "agave", "cactus", "cotton")
_PLANTED = ("fertile", "plant", "wheat", "berries", "mushroom", "agave",
            "cactus", "cotton")


def _smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass
class Plot:
    """A tile the player has worked: dug soil, watered soil, or a crop."""
    kind: str                       # "dirt" | "fertile" | "plant"
    planted_at: float | None = None
    grow: float | None = None       # seconds to ripen, set by the planter's skill


class World:
    """Logical world data. Terrain is procedural and seeded, but tile kinds can
    be overridden later (roads, floors, placed objects)."""

    def __init__(self, seed: int = 20240501) -> None:
        self.seed = seed
        self._overrides: dict[tuple[int, int], str] = {}
        self.plots: dict[tuple[int, int], Plot] = {}
        self.ground = None                                # set by main once built
        self.wild_removed: set[tuple[int, int]] = set()   # picked wild plants (legacy)
        self.wild_eaten: dict[tuple[int, int], float] = {}  # tile -> time it grows back
        self.wild_forced: dict[tuple[int, int], tuple] = {}  # hand-placed wild plants
        self._kind_cache: dict[tuple[int, int], str] = {}    # terrain, once
        self.wild_cells: dict = {}                        # wild-plant cache
        self._lock = threading.Lock()                     # guards plots/overrides

    def temperature(self, x, y):
        """Slow cold->hot field in [0, 1]."""
        return biomes.temperature(x, y, self.seed)

    def humidity(self, x, y):
        """Slow dry->wet field in [0, 1]."""
        return biomes.humidity(x, y, self.seed)

    def tile_kind(self, tx: int, ty: int) -> str:
        """Logical tile type for gameplay/interaction. Cached: the terrain is
        static, and this samples a noise field."""
        with self._lock:
            plot = self.plots.get((tx, ty))
            if plot is not None:
                return "fertile" if plot.kind in _PLANTED else "dirt"
            override = self._overrides.get((tx, ty))
            if override is not None:
                return override
            # the coast overrides the noise: ocean east, sand on the beach
            _wx = tx * TILE + TILE / 2.0
            _wy = ty * TILE + TILE / 2.0
            _c = coast_x(_wy, self.seed)
            if _wx > _c:
                return "ocean"
            if _wx > _c - SAND_W:
                return "sand"
            key = (tx, ty)
            got = self._kind_cache.get(key)
            if got is not None:
                return got
        h = float(biomes.humidity(np.float32(tx * TILE + TILE / 2),
                                  np.float32(ty * TILE + TILE / 2), self.seed))
        got = "dry" if h < 0.24 else "grass"       # bare sand in the desert
        with self._lock:
            self._kind_cache[key] = got
        return got

    def set_tile(self, tx: int, ty: int, kind: str) -> None:
        with self._lock:
            self._overrides[(tx, ty)] = kind

    # -- player-worked soil -------------------------------------------------
    def plot_at(self, tx: int, ty: int) -> Plot | None:
        with self._lock:
            return self.plots.get((tx, ty))

    def set_plot(self, tx: int, ty: int, kind: str,
                 planted_at: float | None = None,
                 grow: float | None = None) -> None:
        with self._lock:
            self.plots[(tx, ty)] = Plot(kind, planted_at, grow)

    def plot_keys(self):
        with self._lock:
            return list(self.plots.keys())

    def plots_in_tile_range(self, tx0: int, ty0: int, tx1: int, ty1: int):
        with self._lock:
            return [((tx, ty), plot) for (tx, ty), plot in self.plots.items()
                    if tx0 <= tx <= tx1 and ty0 <= ty <= ty1]


class GroundRenderer:
    """Generates and caches ground chunk surfaces, and draws the visible ones."""

    def __init__(self, world: World, max_cached: int = 420) -> None:
        self.world = world
        self.max_cached = max_cached
        self._cache: OrderedDict[tuple[int, int], pygame.Surface] = OrderedDict()
        self._coarse: dict[tuple[int, int], tuple[int, int, int]] = {}
        self._step = CHUNK / GEN
        self._nx = GEN + 2 * PAD
        # low-res sample centres, including one padded sample each side
        self._gx = (np.arange(self._nx, dtype=np.float32) - PAD) * self._step + self._step / 2
        self._grains = self._make_grains()
        # -- background generator -------------------------------------------
        # Chunks are built on a worker thread so no frame ever stalls waiting
        # for terrain. The frame draws whatever is ready and a flat colour
        # placeholder for the rest, and the worker fills the cache behind it.
        self._lock = threading.Lock()
        self._jobs: "queue.PriorityQueue" = queue.PriorityQueue()
        self._queued: set = set()
        self._margin = 3
        self._cam = (0.0, 0.0)          # latest camera centre (for stale jobs)
        self._stop = False
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _worker_loop(self) -> None:
        while not self._stop:
            try:
                _tier, _d2, cx, cy = self._jobs.get(timeout=0.25)
            except queue.Empty:
                continue
            key = (cx, cy)
            with self._lock:
                if key in self._cache:
                    self._queued.discard(key)
                    continue
                cam = self._cam
            midx = cx * CHUNK + CHUNK / 2.0
            midy = cy * CHUNK + CHUNK / 2.0
            if ((midx - cam[0]) ** 2 + (midy - cam[1]) ** 2) > 2400.0 ** 2:
                with self._lock:          # player moved on: drop the stale job
                    self._queued.discard(key)
                continue
            try:
                surf = self._generate(cx, cy)
            except Exception as exc:
                sys.stderr.write("KINGPIN chunk %r failed: %r\n" % (key, exc))
                surf = None
            with self._lock:
                self._queued.discard(key)
                if surf is not None:
                    self._cache[key] = surf
                    self._cache.move_to_end(key)
                    while len(self._cache) > self.max_cached:
                        self._cache.popitem(last=False)

    def request(self, cx: int, cy: int, d2: float = 0.0, tier: int = 0) -> bool:
        """Ask the worker to build a chunk (no-op if cached or already queued).

        TIER IS THE PRIORITY: 0 = on screen right now, 1 = the near margin the
        player is walking toward, 2 = background (farmer-tilled tiles nobody is
        watching). On-screen ground is always built first.
        """
        key = (cx, cy)
        with self._lock:
            if key in self._cache or key in self._queued:
                return False
            self._queued.add(key)
        self._jobs.put((tier, d2, cx, cy))
        return True

    def get(self, cx: int, cy: int):
        """The finished chunk surface, or None if not built yet (never builds)."""
        key = (cx, cy)
        with self._lock:
            surf = self._cache.get(key)
            if surf is not None:
                self._cache.move_to_end(key)
            return surf

    # -- full-res grain -----------------------------------------------------
    def _make_grains(self) -> list[pygame.Surface]:
        """Subtle multiplicative grain textures (plus flips) chosen per chunk."""
        variants: list[pygame.Surface] = []
        for i in range(4):
            rng = np.random.default_rng(self.world.seed + 1000 + i)
            base = rng.integers(0, 256, size=(GRAIN, GRAIN), dtype=np.uint8)
            vals = (228 + (base % 28)).astype(np.uint8)  # 228..255 -> ~0.89..1.0
            arr = np.repeat(vals[:, :, None], 3, axis=2)
            surf = pygame.surfarray.make_surface(arr.swapaxes(0, 1))
            variants.append(surf)
            variants.append(pygame.transform.flip(surf, True, False))
        return variants

    # -- chunk generation ---------------------------------------------------
    def chunk_surface(self, cx: int, cy: int) -> pygame.Surface:
        surf = self.get(cx, cy)
        if surf is not None:
            return surf
        surf = self._generate(cx, cy)
        with self._lock:
            self._cache[(cx, cy)] = surf
            self._cache.move_to_end((cx, cy))
            while len(self._cache) > self.max_cached:
                self._cache.popitem(last=False)
        return surf

    def _generate(self, cx: int, cy: int) -> pygame.Surface:
        seed = self.world.seed
        X, Y = np.meshgrid(cx * CHUNK + self._gx, cy * CHUNK + self._gx)

        climate = self.world.temperature(X, Y)
        hum = self.world.humidity(X, Y)
        warp = (climate - 0.5) * 260.0
        clump = fbm((X + warp) * 0.018, (Y + warp) * 0.018, seed + 2, octaves=2)

        dark = biomes.blend_array("dark", climate, hum)
        lite = biomes.blend_array("lite", climate, hum)
        mixv = np.clip(0.44 + 0.56 * clump, 0.0, 1.0)[..., None]
        col = dark * (1.0 - mixv) + lite * mixv
        col = col * (0.90 + 0.18 * clump)[..., None]

        # THE COAST: paint the ocean and the beach over the land noise. East
        # of the shoreline is water (deeper + darker far out, with wave crests
        # and a foam line at the shore); the strip west of it is sand.
        _yy = Y[:, 0]
        _coast = coast_x(_yy, seed)
        _ocean = X > _coast[:, None]
        _sand = (~_ocean) & (X > (_coast[:, None] - SAND_W))
        if _ocean.any():
            # THE SEA FLOOR IS THE SAME SAND AS THE BEACH. The water is a
            # strong blue overlay painted later, over this sand and the algae
            # on it -- so the sea reads as shallow water, not flat blue.
            _sd = (0.92 + 0.14 * np.sin(X * 0.05 + Y * 0.03 + seed * 0.7))[..., None]
            col[_ocean] = (SAND[None, None, :] * _sd)[_ocean]
        if _sand.any():
            _sv = (0.93 + 0.12 * np.sin(X * 0.05 + Y * 0.03 + seed * 0.5))[..., None]
            col[_sand] = (SAND[None, None, :] * _sv)[_sand]

        # Player-made soil edits: dug dirt, then watered (fertile) dirt. Each
        # tile paints a soft blob, and blobs merge naturally where they overlap.
        radius = TILE * 0.95
        tx0 = int(math.floor((cx * CHUNK - radius) / TILE))
        tx1 = int(math.floor((cx * CHUNK + CHUNK + radius) / TILE))
        ty0 = int(math.floor((cy * CHUNK - radius) / TILE))
        ty1 = int(math.floor((cy * CHUNK + CHUNK + radius) / TILE))
        dirt_cov = fert_cov = None
        for (ptx, pty), plot in self.world.plots_in_tile_range(tx0, ty0, tx1, ty1):
            pcx = ptx * TILE + TILE / 2.0
            pcy = pty * TILE + TILE / 2.0
            cov = 1.0 - _smoothstep(np.hypot(X - pcx, Y - pcy) / radius, 0.55, 1.0)
            if plot.kind in _WORKED:
                dirt_cov = cov if dirt_cov is None else np.maximum(dirt_cov, cov)
            if plot.kind in _PLANTED:
                fert_cov = cov if fert_cov is None else np.maximum(fert_cov, cov)
        if dirt_cov is not None:
            soil = np.array((126, 100, 66), np.float32) * (0.82 + 0.36 * clump)[..., None]
            col = col * (1.0 - dirt_cov[..., None]) + soil * dirt_cov[..., None]
        if fert_cov is not None:
            rich = np.array((72, 52, 34), np.float32) * (0.90 + 0.20 * clump)[..., None]
            col = col * (1.0 - fert_cov[..., None]) + rich * fert_cov[..., None]

        np.clip(col, 0, 255, out=col)
        small = pygame.surfarray.make_surface(col.astype(np.uint8).swapaxes(0, 1))
        big = pygame.transform.smoothscale(small, (self._nx * int(self._step),
                                                   self._nx * int(self._step)))
        surf = big.subsurface(pygame.Rect(int(self._step), int(self._step), CHUNK, CHUNK))

        # crisp per-pixel grain, chosen per chunk so it does not phase-align
        h = (cx * 73856093) ^ (cy * 19349663) ^ seed
        grain = self._grains[(h & 0x7FFFFFFF) % len(self._grains)]
        surf.blit(grain, (0, 0), special_flags=pygame.BLEND_MULT)
        sc = getattr(self, "scatter", None)
        if sc is not None:                  # grass is baked in, generated once
            sc.render_into(surf, cx, cy)
        self._draw_algae(surf, cx, cy)
        self._draw_roads(surf, cx, cy)
        # ...AND THE PLAYER'S OWN WORK, PAINTED CRISP. Everything above is
        # computed on a coarse grid and smooth-scaled, which nobody notices in
        # noise -- but it turned a freshly tilled tile into a blur, because the
        # soil is the one sharp thing on the ground. So the worked tiles are
        # laid on again at full resolution, after the scaling.
        ox, oy = cx * CHUNK, cy * CHUNK
        for (ptx, pty), plot in self.world.plots_in_tile_range(
                ox // TILE - 1, oy // TILE - 1,
                (ox + CHUNK) // TILE + 1, (oy + CHUNK) // TILE + 1):
            sx = ptx * TILE - ox + TILE // 2
            sy = pty * TILE - oy + TILE // 2
            if not (-TILE <= sx <= CHUNK + TILE and -TILE <= sy <= CHUNK + TILE):
                continue
            if plot.kind in _PLANTED:
                base, edge = (86, 62, 40), (58, 40, 26)
            else:
                base, edge = (134, 106, 70), (104, 80, 52)
            r = pygame.Rect(sx - TILE // 2 + 2, sy - TILE // 2 + 2,
                            TILE - 4, TILE - 4)
            pygame.draw.rect(surf, edge, r.inflate(2, 2), border_radius=6)
            pygame.draw.rect(surf, base, r, border_radius=6)
            # a few furrows, so dug earth reads as dug
            for k in range(3):
                yy = r.top + 5 + k * max(3, (r.h - 10) // 3)
                pygame.draw.line(surf, edge, (r.left + 3, yy), (r.right - 3, yy), 1)
        # THE WATER ITSELF: a strong blue overlay over the sea floor (the sand
        # and the algae on it), following the coast. Painted last so it tints
        # everything in the sea and nothing on the land.
        _ox = np.arange(CHUNK, dtype=np.float32) + cx * CHUNK
        _oy = np.arange(CHUNK, dtype=np.float32) + cy * CHUNK
        _Xf, _Yf = np.meshgrid(_ox, _oy)
        _sea = _Xf > coast_x(_Yf, seed)
        if _sea.any():
            _ov = np.zeros((CHUNK, CHUNK, 4), np.uint8)
            _ov[..., 0] = WATER[0]
            _ov[..., 1] = WATER[1]
            _ov[..., 2] = WATER[2]
            _ov[..., 3] = np.where(_sea, WATER_ALPHA, 0)
            _ovs = pygame.image.frombuffer(_ov.tobytes(), (CHUNK, CHUNK), "RGBA")
            surf.blit(_ovs, (0, 0))
        return surf

    def _stone(self, surf, x, y, rng, dense=False):
        r = rng.randint(3, 7) if not dense else rng.randint(4, 9)
        shade = rng.randint(118, 172)
        pygame.draw.ellipse(surf, (shade, shade - 8, shade - 18),
                            (x - r, y - r * 0.7, r * 2, r * 1.4))
        pygame.draw.ellipse(surf, (shade + 42, shade + 36, shade + 24),
                            (x - r * 0.5, y - r * 0.4, r, r * 0.8))

    def _draw_algae(self, surf, cx, cy):
        """Bright green algae on the sea floor: scatter-like tufts, but much
        less frequent, and only where there is water."""
        seed = self.world.seed
        rng = random.Random((cx * 73856093) ^ (cy * 19349663) ^ seed)
        for _ in range(9):
            x = rng.randint(0, CHUNK - 4)
            y = rng.randint(0, CHUNK - 6)
            wx = cx * CHUNK + x
            wy = cy * CHUNK + y
            if wx <= coast_x(wy, seed):      # only out in the ocean
                continue
            for k in range(rng.randint(2, 3)):
                yy = y + k * 3
                if yy < CHUNK - 3:
                    pygame.draw.line(surf, ALGAE,
                                     (x + (k & 1), yy), (x + 2 + (k & 1), yy + 2), 1)

    def _draw_roads(self, surf, cx, cy):
        """Road/plaza stones, pre-baked per village and looked up by chunk."""
        vill = getattr(self, "villages_v", None)
        if vill is None:
            return
        ox, oy = cx * CHUNK, cy * CHUNK
        nearby = vill.visible(ox - 220.0, oy - 220.0, CHUNK + 440, CHUNK + 440)
        for v in nearby:
            for (x, y, r, shade) in v.stone_chunks().get((cx, cy), ()):
                sx, sy = x - ox, y - oy
                pygame.draw.ellipse(surf, (shade, shade - 8, shade - 18),
                                    (sx - r, sy - r * 0.7, r * 2, r * 1.4))
                pygame.draw.ellipse(surf, (shade + 42, shade + 36, shade + 24),
                                    (sx - r * 0.5, sy - r * 0.4, r, r * 0.8))

    def _coarse_color(self, cx: int, cy: int) -> tuple[int, int, int]:
        """Cheap plausible fill for a not-yet-generated chunk (no black pops).
        The ocean and the beach get their REAL colour even before the chunk is
        built, so the sea is never a black or green gap under the ship."""
        cached = self._coarse.get((cx, cy))
        if cached is not None:
            return cached
        mx = cx * CHUNK + CHUNK / 2.0
        my = cy * CHUNK + CHUNK / 2.0
        _c = coast_x(my, self.world.seed)
        if mx > _c:
            col = tuple(int(v) for v in WATER)
        elif mx > _c - SAND_W:
            col = tuple(int(v) for v in SAND)
        else:
            t = float(self.world.temperature(np.float32(mx), np.float32(my)))
            h = float(self.world.humidity(np.float32(mx), np.float32(my)))
            dark, lite, _spec, _dens = biomes.mix(t, h)
            col = (int((dark[0] + lite[0]) * 0.5),
                   int((dark[1] + lite[1]) * 0.5),
                   int((dark[2] + lite[2]) * 0.5))
        self._coarse[(cx, cy)] = col
        return col

    def invalidate_tile(self, tx: int, ty: int,
                        immediate: bool = True) -> None:
        """Rebuild exactly the ground that just changed.

        IMMEDIATE IS FOR THE PLAYER. Building the chunk here, in the frame that
        changed it, is what stops the screen falling back to a coarse blur when
        a man digs a tile -- and for the handful of tiles a player touches it is
        nothing.

        IT IS NOT FOR THE FARMERS. A hundred and sixty of them till, water,
        plant and reap, and every action invalidates a tile: 32 chunk rebuilds
        a second, and _generate is a full 256x256 chunk of fbm, temperature,
        humidity and numpy clip -- ALL OF IT INSIDE A FRAME. That is where the
        frame went. Their ground is queued to the worker thread instead, which
        is what the thread is for, and nobody is watching the field they are
        standing in.
        """
        self._version = getattr(self, "_version", 0) + 1   # so the layer re-composes
        cx = (tx * TILE) // CHUNK
        cy = (ty * TILE) // CHUNK
        pxc = tx * TILE + TILE / 2.0
        pyc = ty * TILE + TILE / 2.0
        radius = TILE * 0.95
        touched = []
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                kx, ky = cx + ox, cy + oy
                left, top = kx * CHUNK, ky * CHUNK
                nx = min(max(pxc, left), left + CHUNK)
                ny = min(max(pyc, top), top + CHUNK)
                if (nx - pxc) ** 2 + (ny - pyc) ** 2 <= radius * radius:
                    touched.append((kx, ky))
        for key in touched:
            self._cache.pop(key, None)
            self._coarse.pop(key, None)
        if not immediate:
            # the worker thread will rebuild these; the frame keeps its time.
            # TIER 2: these are the fields the farmers are standing in, and
            # nobody is watching -- on-screen ground always jumps the queue.
            for key in touched:
                if key in self._queued:
                    continue
                self._queued.add(key)
                self._jobs.put((2, 0.0, key[0], key[1]))
            sc = getattr(self, "scatter", None)
            if sc is not None:
                sc.invalidate_tile(tx, ty)
            return
        for key in touched:                     # built now, not queued
            try:
                surf = self._generate(key[0], key[1])
            except Exception:
                continue
            with self._lock:
                self._cache[key] = surf
                self._cache.move_to_end(key)
        sc = getattr(self, "scatter", None)
        if sc is not None:
            sc.invalidate_tile(tx, ty)

    def refresh_around(self, x: float, y: float, vw: int, vh: int) -> None:
        """Build the ground under the player NOW -- for loading a save, when
        every worked tile in the world has just changed at once."""
        self._version = getattr(self, "_version", 0) + 1
        self._cache.clear()
        self._coarse.clear()
        for cx, cy in self.visible_chunks(x - vw / 2.0, y - vh / 2.0, vw, vh):
            with self._lock:
                try:
                    self._cache[(cx, cy)] = self._generate(cx, cy)
                except Exception:
                    pass

    # -- visibility / streaming --------------------------------------------
    def visible_chunks(self, cam_x: float, cam_y: float, vw: int, vh: int,
                       margin: int = 0):
        m = margin * CHUNK
        x0 = int(math.floor((cam_x - m) / CHUNK))
        y0 = int(math.floor((cam_y - m) / CHUNK))
        x1 = int(math.floor((cam_x + vw + m) / CHUNK))
        y1 = int(math.floor((cam_y + vh + m) / CHUNK))
        center = ((cam_x + vw / 2) / CHUNK, (cam_y + vh / 2) / CHUNK)
        chunks = [(cx, cy) for cy in range(y0, y1 + 1) for cx in range(x0, x1 + 1)]
        chunks.sort(key=lambda c: (c[0] - center[0]) ** 2 + (c[1] - center[1]) ** 2)
        return chunks

    def ensure_visible(self, cam_x: float, cam_y: float, vw: int, vh: int,
                       margin: int = 2) -> None:
        """Generate every chunk in view (plus a margin) before it is drawn,
        so nothing ever pops in or shows a placeholder."""
        for cx, cy in self.visible_chunks(cam_x, cam_y, vw, vh, margin=margin):
            if (cx, cy) not in self._cache:
                self.chunk_surface(cx, cy)

    def update(self, budget: int, cam_x: float, cam_y: float, vw: int, vh: int,
               margin: int = 3) -> int:
        """Queue up to ``budget`` missing chunks for the worker, ON SCREEN FIRST.

        Whatever the player is looking at (tier 0) is queued before the near
        ring he might walk into (tier 1), so a fast pan or march never shows a
        coarse blur while the worker is busy three chunks ahead of him."""
        ccx = cam_x + vw / 2.0
        ccy = cam_y + vh / 2.0
        with self._lock:
            self._cam = (ccx, ccy)
            if len(self._queued) > 80:         # worker is behind: stop adding
                return 0

            def _gap(c):
                dx = c[0] * CHUNK + CHUNK / 2.0 - ccx
                dy = c[1] * CHUNK + CHUNK / 2.0 - ccy
                return dx * dx + dy * dy

            onscreen = [c for c in self.visible_chunks(cam_x, cam_y, vw, vh, margin=0)
                        if c not in self._cache and c not in self._queued]
            onscreen.sort(key=_gap)
            ring = [c for c in self.visible_chunks(cam_x, cam_y, vw, vh, margin=margin)
                    if c not in self._cache and c not in self._queued]
            _ons = set(onscreen)
            ring = [c for c in ring if c not in _ons]
            ring.sort(key=_gap)
            self._margin = margin
        _n = 0
        for cx, cy in onscreen[:budget]:
            if self.request(cx, cy, 0.0, 0):
                _n += 1
        for cx, cy in ring[:max(0, budget - _n)]:
            if self.request(cx, cy, 0.0, 1):
                _n += 1
        return _n

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             vw: int, vh: int) -> None:
        for cx, cy in self.visible_chunks(cam_x, cam_y, vw, vh):
            sx = int(round(cx * CHUNK - cam_x))
            sy = int(round(cy * CHUNK - cam_y))
            surf = self.get(cx, cy)
            if surf is None:
                # ON SCREEN MEANS BUILT NOW, in this very frame, before
                # anything else draws. The StaticLayer bakes this into its
                # cached region, so a coarse placeholder left here would sit
                # on screen for as long as the region is reused -- the
                # "sprint and the ground never fills in" bug. The worker only
                # ever builds the ring ahead of the camera.
                try:
                    surf = self.chunk_surface(cx, cy)
                except Exception:
                    surf = None
            if surf is None:
                screen.fill(self._coarse_color(cx, cy), (sx, sy, CHUNK, CHUNK))
                self.request(cx, cy, 0.0, 0)     # last resort, if generation failed
            else:
                screen.blit(surf, (sx, sy))


class StaticLayer:
    """The ground and everything scattered on it, composed ONCE per region.

    Nothing down there moves, so re-blitting twenty chunks a frame to produce
    the same picture was pure waste. Composed for a region half a screen larger
    than the view, blitted as one surface, recomposed only when the player
    walks out of that region.
    """

    def __init__(self, ground, scatter, margin: float = 0.5) -> None:
        self.ground = ground
        self.scatter = scatter
        self.margin = margin
        self.rect = None
        self.surf = None
        self.version = None
        # MORE THAN ONE REGION KEPT. One cached region meant that walking out
        # of it recomposed the ground and the scatter from scratch -- which is
        # the hitch you feel when you come somewhere new, the camp gate most of
        # all, because every region round it is new.
        self.keep = 1
        self._regions = {}

    def warm(self, x: float, y: float, vw: float, vh: float) -> None:
        """COMPOSE A REGION NOW, so walking into it does not cost a frame."""
        m_x = int(vw * self.margin)
        m_y = int(vh * self.margin)
        need = pygame.Rect(int(x) - m_x, int(y) - m_y, int(vw) + 2 * m_x,
                           int(vh) + 2 * m_y)
        key = (need.x, need.y, need.w, need.h)
        if key in self._regions:
            return
        surf = pygame.Surface((need.w, need.h))
        self.ground.draw(surf, need.x, need.y, need.w, need.h)
        self.scatter.draw(surf, need.x, need.y, need.w, need.h)
        # ...and make it the live region, so the frame it is for is free
        self.surf = surf
        self.rect = need
        self.version = getattr(self.ground, "_version", 0)

    def draw(self, screen, cam_x, cam_y, vw, vh, statics_fn=None,
             entity_band=None) -> None:
        m_x = int(vw * self.margin)
        m_y = int(vh * self.margin)
        need = pygame.Rect(int(cam_x) - m_x, int(cam_y) - m_y,
                           vw + 2 * m_x, vh + 2 * m_y)
        ver = getattr(self.ground, "_version", 0)
        if (self.rect is None or self.version != ver
                or not self.rect.contains(pygame.Rect(int(cam_x), int(cam_y), vw, vh))):
            if self.surf is None or self.surf.get_size() != (need.w, need.h):
                self.surf = pygame.Surface((need.w, need.h))
            self.rect = need
            self.version = ver
            self.ground.draw(self.surf, need.x, need.y, need.w, need.h)
            self.scatter.draw(self.surf, need.x, need.y, need.w, need.h)
        screen.blit(self.surf, (self.rect.x - cam_x, self.rect.y - cam_y))


class Scatter:
    """Deterministic grass tufts / flowers / pebbles drawn over the ground."""

    def __init__(self, seed: int = 20240501, world: "World | None" = None) -> None:
        self.seed = seed
        self.world = world
        self.tufts: list[pygame.Surface] = []
        self.flowers: list[pygame.Surface] = []
        self.pebbles: list[pygame.Surface] = []
        self.snow: list[pygame.Surface] = []
        self.sand: list[pygame.Surface] = []
        self._surf: dict = {}          # scatter cell -> (snow factor, sand factor)
        self._chunks: dict = {}
        self._order: list = []
        self._build_sprites()

    def _build_sprites(self) -> None:
        rng = random.Random(self.seed * 7919)
        tuft_colors = [
            (58, 96, 44), (76, 120, 50), (94, 136, 58),
            (48, 84, 38), (110, 146, 66), (66, 104, 46),
        ]
        for i in range(14):
            w, h = rng.randint(9, 17), rng.randint(9, 17)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(surf, (24, 42, 22, 55), (w * 0.12, h - 4, w * 0.76, 4))
            color = tuft_colors[i % len(tuft_colors)]
            for _ in range(rng.randint(4, 8)):
                bx = w * 0.5 + (rng.random() - 0.5) * w * 0.55
                tx = bx + (rng.random() - 0.5) * 5
                ty = h * (0.10 + rng.random() * 0.38)
                pygame.draw.line(surf, color, (bx, h - 2), (tx, ty), 1)
            self.tufts.append(surf)

        for color in [(236, 236, 220), (244, 214, 96), (216, 128, 180), (230, 150, 120)]:
            w, h = 8, 10
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.line(surf, (70, 110, 48), (w // 2, h - 1), (w // 2, 4), 1)
            pygame.draw.circle(surf, color, (w // 2, 4), 2)
            self.flowers.append(surf)

        for i in range(3):
            w = h = rng.randint(5, 8)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            shade = 118 + i * 20
            pygame.draw.ellipse(surf, (shade, shade, shade + 8), (0, 2, w, h - 2))
            pygame.draw.ellipse(surf, (shade + 30, shade + 30, shade + 34),
                                (1, 2, w * 0.5, (h - 2) * 0.5))
            self.pebbles.append(surf)

        for _ in range(7):                          # snow mounds
            w, h = rng.randint(12, 22), rng.randint(7, 12)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(surf, (196, 206, 222, 120), (0, h * 0.3, w, h * 0.7))
            pygame.draw.ellipse(surf, (233, 240, 250), (1, h * 0.14, w - 2, h * 0.62))
            pygame.draw.ellipse(surf, (250, 252, 255), (2, h * 0.08, w * 0.6, h * 0.42))
            self.snow.append(surf)

        for _ in range(6):                          # sand grains / grit
            w = h = rng.randint(4, 8)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            tan = 196 + rng.randint(0, 40)
            pygame.draw.ellipse(surf, (tan, tan - 26, tan - 82), (0, 1, w, h - 1))
            pygame.draw.ellipse(surf, (min(255, tan + 22), tan - 6, tan - 54),
                                (1, 1, w * 0.5, (h - 1) * 0.5))
            self.sand.append(surf)

    def _rand(self, cx: int, cy: int, i: int, salt: int) -> float:
        h = (cx * 73856093) ^ (cy * 19349663) ^ (i * 83492791) \
            ^ (salt * 2654435761) ^ (self.seed * 40503)
        h &= 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        h ^= h >> 16
        return (h & 0xFFFFFF) / 0x1000000

    def invalidate_tile(self, tx: int, ty: int) -> None:
        pass

    def render_into(self, surf: pygame.Surface, ccx: int, ccy: int) -> None:
        """Bake this chunk's grass/flower/pebble sprites into a ground chunk."""
        cell = SCATTER_CELL
        ox, oy = ccx * CHUNK, ccy * CHUNK
        x0 = int(math.floor(ox / cell))
        y0 = int(math.floor(oy / cell))
        x1 = int(math.floor((ox + CHUNK) / cell))
        y1 = int(math.floor((oy + CHUNK) / cell))
        n_tufts = len(self.tufts)
        if self.world is not None:
            # One vectorised biome lookup for the whole block (instead of a
            # scalar fBm call per cell), cached per cell.
            need = [(cx, cy) for cy in range(y0, y1 + 1)
                    for cx in range(x0, x1 + 1) if (cx, cy) not in self._surf]
            if need:
                if len(self._surf) > 200000:
                    self._surf.clear()
                cxs = np.array([(cx + 0.5) * cell for cx, _cy in need], np.float32)
                cys = np.array([(cy + 0.5) * cell for _cx, cy in need], np.float32)
                tt = self.world.temperature(cxs, cys)
                hh = self.world.humidity(cxs, cys)
                sf = biomes.snow_factor_array(tt, hh)
                df = biomes.sand_factor_array(tt, hh)
                for i, key in enumerate(need):
                    self._surf[key] = (float(sf[i]), float(df[i]))
        tilled: set = set()
        if self.world is not None:
            # ONLY THE TILES THIS CHUNK CAN TOUCH. This walked EVERY PLOT IN
            # THE WORLD -- plot_keys() across two hundred kilometres -- and
            # inserted a 3x3 neighbourhood for every one of them, so a single
            # chunk of ground performed hundreds of thousands of set inserts to
            # answer a question about itself. Every tuft it is placing lies
            # inside this chunk, so the only plots that can matter are the ones
            # beside it.
            plot_at = self.world.plot_at
            tx0 = int(math.floor(ox / TILE)) - 1
            tx1 = int(math.floor((ox + CHUNK) / TILE)) + 1
            ty0 = int(math.floor(oy / TILE)) - 1
            ty1 = int(math.floor((oy + CHUNK) / TILE)) + 1
            for ttx in range(tx0, tx1 + 1):
                for tty in range(ty0, ty1 + 1):
                    if plot_at(ttx, tty) is not None:
                        for dx in (-1, 0, 1):
                            for dy in (-1, 0, 1):
                                tilled.add((ttx + dx, tty + dy))
        blit = surf.blit
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                snowf, sandf = self._surf.get((cx, cy), (0.0, 0.0))
                count = 1 + int(self._rand(cx, cy, 0, 1) * 2.6)
                for i in range(count):
                    wx = (cx + self._rand(cx, cy, i, 2)) * cell
                    wy = (cy + self._rand(cx, cy, i, 3)) * cell
                    if wx > coast_x(wy, self.seed):
                        continue        # the ocean grows seaweed, not grass
                    if tilled:
                        ttx = int(math.floor(wx / TILE))
                        tty = int(math.floor(wy / TILE))
                        if (ttx, tty) in tilled:
                            continue
                    pick = self._rand(cx, cy, i, 4)
                    if pick < snowf:
                        if self._rand(cx, cy, i, 7) < 0.78:
                            sprite = self.snow[int(self._rand(cx, cy, i, 5)
                                                   * len(self.snow))]
                        else:
                            sprite = self.pebbles[int(self._rand(cx, cy, i, 5)
                                                      * len(self.pebbles))]
                    elif pick < snowf + sandf:
                        if self._rand(cx, cy, i, 7) < 0.72:
                            sprite = self.sand[int(self._rand(cx, cy, i, 5)
                                                   * len(self.sand))]
                        else:
                            sprite = self.pebbles[int(self._rand(cx, cy, i, 5)
                                                      * len(self.pebbles))]
                    elif pick < 0.72:
                        sprite = self.tufts[int(self._rand(cx, cy, i, 5) * n_tufts)]
                    elif pick < 0.87:
                        sprite = self.flowers[int(self._rand(cx, cy, i, 5)
                                                  * len(self.flowers))]
                    elif pick < 0.96:
                        sprite = self.pebbles[int(self._rand(cx, cy, i, 5)
                                                  * len(self.pebbles))]
                    else:
                        sprite = self.tufts[int(self._rand(cx, cy, i, 6) * n_tufts)]
                    blit(sprite, (int(round(wx - ox - sprite.get_width() * 0.5)),
                                  int(round(wy - oy - sprite.get_height() * 0.9))))

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             vw: int, vh: int) -> None:
        pass
