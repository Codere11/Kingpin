"""map.py -- the world map, with a real zoom and a real pan.

A MAP IS A WINDOW ON THE WORLD, NOT A PICTURE OF IT. The old one drew the whole
world once at ninety-six blocks a side and could do nothing else: no closer, no
further, no looking somewhere else. This one keeps a view -- a centre and a
half-extent -- and you move the view instead of the world.

    W A S D  or the arrows   pan
    Q / E    or - / =        zoom out / in
    C                        come back to yourself
    mouse wheel              zoom under the pointer
    M                        close

One thumbnail of the whole world is made once, at WORLD_PX a side, and the view
is a scaled sub-rectangle of it. Zooming is therefore free -- the ground never
has to be sampled again -- and nearest-neighbour keeps the blocks hard, which is
what this map has always looked like.
"""

from __future__ import annotations

import math

import numpy as np
import pygame

import biomes
import hubs

# A HUNDRED SQUARES OF "MOSTLY TRUE". The chart used to be a 320 x 320
# picture of the whole world -- a hundred thousand noise samples, built inside
# the first draw, which froze the game for seconds behind "charting the
# country...". A map is read at a glance: twelve squares a side, each the
# average of a few samples inside it, is instant to build and tells the player
# more than a blur of individual pixels ever did.
WORLD_PX = 12
GRID = WORLD_PX
SAMPLES = 3             # 3 x 3 samples per square, averaged

WAYPOINT = (238, 202, 96)
HUB_COLOUR = (198, 72, 60)
YOU = (246, 246, 240)
FRAME = (150, 116, 70)
PAPER = (26, 23, 20)
EDGE = (12, 10, 9)
DARK = (18, 16, 14)

# THE CHART COVERS THE WHOLE COUNTRY. The settlements run out to about a
# hundred and fifty thousand from the middle and this was a hundred thousand,
# so a map "of every town" quietly left two in five of them off the paper.
WORLD_HALF = 675000.0
MIN_HALF = 1200.0        # the closest you may zoom: about two villages wide
MAX_HALF = WORLD_HALF * 1.35

ZOOM_STEP = 1.16         # per notch: smooth, and you can always get back
PAN_RATE = 0.25          # a full screen in about four seconds, at any zoom

_CACHE: dict = {}
_THREADS: dict = {}
_VIEW = {"cx": -WORLD_HALF / 2.0, "cy": 0.0, "half": WORLD_HALF}

CHART_PX = 280            # cells across the chart -- fine enough to pin markers to biomes
CHART_SAMPLES = 1         # one sample per cell: the chart classifies, not blends
CHART_KEEP = 12           # charts remembered, then the oldest is dropped

# biome surface classes
CLS_SNOW, CLS_DESERT, CLS_FOREST, CLS_OCEAN = 0, 1, 2, 3
OCEAN_RGB = (16, 38, 74)
PAPER_RGB = (47, 45, 41)
BORDER_RGB = (8, 8, 10)


def _tree_icon(surf: pygame.Surface, x: int, y: int, snow: bool = False) -> None:
    """A tiny tree: green, or a snow-covered one in white."""
    canopy = (232, 238, 244) if snow else (58, 118, 66)
    pygame.draw.rect(surf, (96, 76, 58), (x, y + 1, 2, 3))
    pygame.draw.polygon(surf, canopy, [(x - 3, y + 1), (x + 4, y + 1),
                                       (x, y - 3)])


def _cactus_icon(surf: pygame.Surface, x: int, y: int) -> None:
    """A tiny saguaro, for the desert."""
    col = (72, 148, 84)
    pygame.draw.rect(surf, col, (x, y - 3, 2, 5))
    pygame.draw.rect(surf, col, (x - 2, y - 1, 2, 1))
    pygame.draw.rect(surf, col, (x - 2, y - 2, 1, 2))
    pygame.draw.rect(surf, col, (x + 2, y - 1, 2, 1))
    pygame.draw.rect(surf, col, (x + 3, y - 2, 1, 2))


def _campfire(screen: pygame.Surface, px: int, py: int) -> None:
    """A campfire mark: crossed logs under a little flame."""
    pygame.draw.line(screen, (104, 72, 44), (px - 6, py + 5), (px + 6, py - 5), 2)
    pygame.draw.line(screen, (104, 72, 44), (px - 6, py - 5), (px + 6, py + 5), 2)
    pygame.draw.polygon(screen, (250, 150, 50), [(px, py - 7), (px - 4, py - 1),
                                                 (px + 4, py - 1)])
    pygame.draw.polygon(screen, (255, 224, 100), [(px, py - 5), (px - 2, py - 1),
                                                  (px + 2, py - 1)])


def _chart(world, cx: float, cy: float, half: float):
    """THE GROUND UNDER THE CURRENT VIEW, sampled for THIS zoom.

    It used to be one 12 x 12 thumbnail of the whole world, scaled up, so
    zooming in showed twelve enormous squares -- half a country of one green.
    The chart is now cut from the view itself: 56 x 56 cells covering exactly
    what the paper is showing, four noise samples averaged into each, and it is
    RE-MADE whenever the view moves or the zoom changes.
    """
    # THE KEY MUST CHANGE WHEN THE ZOOM DOES. It was quantised by the cell
    # size, and the cell size itself is proportional to the zoom -- so every
    # zoom level produced the SAME key, the cache handed back the same chart,
    # and the map was frozen while the paper zoomed. The zoom is quantised on
    # its own logarithmic grid now (one entry per notch), and the centre to a
    # quarter of a cell, so panning inside a cell does not re-chart.
    cell = (2.0 * float(half)) / CHART_PX
    zoom_i = int(round(math.log(max(1.0, float(half))) / math.log(ZOOM_STEP)))
    # KEYED ON THE EXACT CENTRE (to the pixel), so the terrain never lags a
    # quantised step behind the markers -- they both move by the same cx, cy.
    key = (int(getattr(world, "seed", 0)),
           round(float(cx), 2),
           round(float(cy), 2),
           zoom_i, CHART_PX)
    got = _CACHE.get(key)
    if got is not None:
        return got
    n = CHART_PX
    x0, y0 = cx - half, cy - half
    step = (2.0 * half) / n
    coords = x0 + np.arange(n, dtype=np.float32) * step
    gx, gy = np.meshgrid(coords, coords)
    seed = int(getattr(world, "seed", 0))
    try:
        temps = np.asarray(biomes.temperature(gx, gy, seed))
        hums = np.asarray(biomes.humidity(gx, gy, seed))
    except Exception:
        temps = np.full((n, n), 0.5, dtype=np.float32)
        hums = np.full((n, n), 0.5, dtype=np.float32)
    # THE COAST, DARK BLUE SEA, and the three big biomes: snow, desert, and
    # regular forest. Everything is classified per cell, then drawn sparse and
    # old-school: paper ground, black biome borders, tiny icons and grass lines.
    import world as _world
    _coast = _world.coast_x(gy, seed)
    _ocean = gx > _coast
    cls = np.where(_ocean, CLS_OCEAN,
                   np.where(temps < 0.32, CLS_SNOW,
                            np.where((temps > 0.62) & (hums < 0.34), CLS_DESERT,
                                     CLS_FOREST))).astype(np.int8)
    surf = pygame.Surface((n, n))
    for j in range(n):
        for i in range(n):
            surf.set_at((i, j), OCEAN_RGB if cls[j, i] == CLS_OCEAN else PAPER_RGB)
    # BOLD BLACK BORDERS where one biome meets another (and at the shore).
    for j in range(n):
        for i in range(n):
            k = cls[j, i]
            if i + 1 < n and cls[j, i + 1] != k:
                surf.set_at((i, j), BORDER_RGB)
                surf.set_at((i + 1, j), BORDER_RGB)
            if j + 1 < n and cls[j + 1, i] != k:
                surf.set_at((i, j), BORDER_RGB)
                surf.set_at((i, j + 1), BORDER_RGB)
    # SPARSE MINI LINES: grass-green, sand-yellow, or snow-white strokes.
    for j in range(1, n, 3):
        for i in range(1, n, 3):
            k = cls[j, i]
            if k == CLS_SNOW:
                pygame.draw.line(surf, (238, 242, 248), (i, j), (i + 2, j), 1)
            elif k == CLS_DESERT:
                pygame.draw.line(surf, (222, 196, 120), (i, j), (i + 2, j), 1)
            elif k == CLS_FOREST:
                pygame.draw.line(surf, (110, 168, 92), (i, j), (i + 2, j), 1)
    # AND THE SPARSER ICONS: tree, cactus, snow tree.
    for j in range(4, n, 9):
        for i in range(4, n, 9):
            k = cls[j, i]
            if k == CLS_SNOW:
                _tree_icon(surf, i, j, snow=True)
            elif k == CLS_DESERT:
                _cactus_icon(surf, i, j)
            elif k == CLS_FOREST:
                _tree_icon(surf, i, j, snow=False)
    # CAMP MARKERS ARE BAKED INTO THE SAME SURFACE AS THE TERRAIN, so a camp
    # and the tree behind it are one image and can never drift apart.
    try:
        import native as _native
        _ns = _native.NATIVE_SPACING
        _gx0 = int(math.floor((cx - half) / _ns))
        _gx1 = int(math.floor((cx + half) / _ns))
        _gy0 = int(math.floor((cy - half) / _ns))
        _gy1 = int(math.floor((cy + half) / _ns))
        for _gy in range(_gy0, _gy1 + 1):
            for _gx in range(_gx0, _gx1 + 1):
                if _gx >= 0:
                    continue
                _wx, _wy = _native.native_center(_gx, _gy, seed)
                _pi = int((_wx - x0) / step)
                _pj = int((_wy - y0) / step)
                if 0 <= _pi < n and 0 <= _pj < n:
                    surf.set_at((_pi, _pj), (250, 150, 50))
                    if _pi + 1 < n:
                        surf.set_at((_pi + 1, _pj), (250, 150, 50))
                    if _pj + 1 < n:
                        surf.set_at((_pi, _pj + 1), (250, 150, 50))
    except Exception:
        pass
    if len(_CACHE) >= CHART_KEEP:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = surf
    return surf


PAPER_N = 1024                # the one fixed map image is this many pixels across
_PAPER = None                 # (key, surface) -- rendered once, panned/zoomed over


def _paper(world, seed: int):
    """ONE fixed map image: terrain and camps pinned to their world x,y.
    Built once per world (behind the loading screen), then simply shown."""
    global _PAPER
    _key = (int(seed),)
    if _PAPER is not None and _PAPER[0] == _key:
        return _PAPER[1]
    N = PAPER_N
    half = WORLD_HALF
    # The noise is the expensive part, so classify at half resolution and blow
    # it up to full size with a 2x nearest-neighbour: at the size this map is
    # shown the seam is invisible, and it turns a second of fbm into a blink.
    SN = N // 2
    sstep = (2.0 * half) / SN
    xs = -half + (np.arange(SN, dtype=np.float32) + 0.5) * sstep
    gx, gy = np.meshgrid(xs, xs)
    try:
        temps = np.asarray(biomes.temperature(gx, gy, seed), np.float32)
        hums = np.asarray(biomes.humidity(gx, gy, seed), np.float32)
        import world as _world
        _coast = _world.coast_x(gy, seed)
    except Exception:
        temps = np.full((SN, SN), 0.5, np.float32)
        hums = np.full((SN, SN), 0.5, np.float32)
        _coast = np.full((SN, SN), half + 1.0, np.float32)
    _ocean = gx > _coast
    _land = ~_ocean
    _snow = _land & (temps < 0.32)
    _desert = _land & (temps > 0.62) & (hums < 0.34)
    _forest = _land & ~_snow & ~_desert
    # THE OLD-SCHOOL CHART LOOK: dark paper land, blue sea, black borders,
    # and the biomes told apart by their sparse lines and little icons.
    cls_s = np.where(_ocean, 3,
                     np.where(_snow, 0, np.where(_desert, 1, 2))).astype(np.int8)
    cls = np.repeat(np.repeat(cls_s, 2, axis=0), 2, axis=1)
    _ocean_f = cls == 3
    rgb = np.empty((N, N, 3), np.uint8)
    rgb[:] = PAPER_RGB
    rgb[_ocean_f] = OCEAN_RGB
    # black borders where one class meets another (the shore included).
    _bx = cls[:, 1:] != cls[:, :-1]
    _by = cls[1:, :] != cls[:-1, :]
    _bord = np.zeros((N, N), bool)
    _bord[:, :-1] |= _bx
    _bord[:, 1:] |= _bx
    _bord[:-1, :] |= _by
    _bord[1:, :] |= _by
    rgb[_bord] = BORDER_RGB
    surf = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
    # SPARSE GRASS LINES, exactly as the old chart drew them.
    for j in range(1, N, 3):
        for i in range(1, N, 3):
            k = cls[j, i]
            if k == 0:
                pygame.draw.line(surf, (238, 242, 248), (i, j), (i + 2, j), 1)
            elif k == 1:
                pygame.draw.line(surf, (222, 196, 120), (i, j), (i + 2, j), 1)
            elif k == 2:
                pygame.draw.line(surf, (110, 168, 92), (i, j), (i + 2, j), 1)
    # AND THE SPARSER ICONS: tree, cactus, snow tree.
    for j in range(4, N, 9):
        for i in range(4, N, 9):
            k = cls[j, i]
            if k == 0:
                _tree_icon(surf, i, j, snow=True)
            elif k == 1:
                _cactus_icon(surf, i, j)
            elif k == 2:
                _tree_icon(surf, i, j, snow=False)
    try:
        import native as _native
        _ns = _native.NATIVE_SPACING
        fstep = (2.0 * half) / N
        _gx0 = int(math.floor(-half / _ns))
        _gx1 = int(math.floor(half / _ns))
        _gy0 = int(math.floor(-half / _ns))
        _gy1 = int(math.floor(half / _ns))
        for _gy in range(_gy0, _gy1 + 1):
            for _gx in range(_gx0, _gx1 + 1):
                if _gx >= 0:
                    continue
                _wx, _wy = _native.native_center(_gx, _gy, seed)
                _px = int((_wx + half) / fstep)
                _py = int((_wy + half) / fstep)
                if 0 <= _px < N and 0 <= _py < N:
                    pygame.draw.line(surf, (104, 72, 44), (_px - 5, _py + 4), (_px + 5, _py - 4), 2)
                    pygame.draw.line(surf, (104, 72, 44), (_px - 5, _py - 4), (_px + 5, _py + 4), 2)
                    pygame.draw.circle(surf, (250, 150, 50), (_px, _py), 3)
                    pygame.draw.circle(surf, (255, 224, 100), (_px, _py - 1), 1)
    except Exception:
        pass
    _PAPER = (_key, surf)
    return surf


def prewarm(world) -> None:
    """Draw the whole map once, behind the loading screen, so pressing M just
    shows it -- the player never waits for the map on its first open."""
    try:
        _paper(world, int(getattr(world, "seed", 0)))
    except Exception:
        pass


def reset() -> None:
    """Back to the whole world, centred on the land (the sea is a sliver east)."""
    _VIEW["cx"], _VIEW["cy"] = -WORLD_HALF / 2.0, 0.0
    _VIEW["half"] = WORLD_HALF


def _clamp_view() -> None:
    half = _VIEW["half"]
    lim = max(0.0, WORLD_HALF - half)
    _VIEW["cx"] = max(-lim, min(lim, _VIEW["cx"]))
    _VIEW["cy"] = max(-lim, min(lim, _VIEW["cy"]))


def _zoom(factor: float, ax: float = 0.0, ay: float = 0.0) -> None:
    """Zoom about a world point, so the ground under it stays put.

    The half-extent is snapped to the notch grid (WORLD_HALF x ZOOM_STEP**n), so
    the chart is one per notch -- a chart built for one half is never stretched
    over another, which is what made the map distort when zooming back out.
    """
    before = _VIEW["half"]
    target = max(MIN_HALF, min(MAX_HALF, before / factor))
    n = round(math.log(target / WORLD_HALF) / math.log(ZOOM_STEP))
    snapped = max(MIN_HALF, min(MAX_HALF, WORLD_HALF * (ZOOM_STEP ** n)))
    scale = snapped / before
    _VIEW["half"] = snapped
    _VIEW["cx"] = ax + (_VIEW["cx"] - ax) * scale
    _VIEW["cy"] = ay + (_VIEW["cy"] - ay) * scale
    _clamp_view()


def handle_input(dt: float, player, mouse_pos=None, wheel: int = 0) -> None:
    """Pan and zoom. Called every frame the map is open. The pan runs on
    real frame time, never the simulation clock, so fast-forward cannot make
    the paper fling itself across the country."""
    dt = max(0.0, min(float(dt), 0.05))
    keys = pygame.key.get_pressed()
    half = _VIEW["half"]
    speed = half * PAN_RATE * dt
    dx = dy = 0.0
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        dx -= speed
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        dx += speed
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        dy -= speed
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        dy += speed
    _VIEW["cx"] += dx
    _VIEW["cy"] += dy
    if keys[pygame.K_q] or keys[pygame.K_MINUS] or keys[pygame.K_KP_MINUS]:
        _zoom(1.0 / ZOOM_STEP ** (dt * 60.0 / 6.0))
    if keys[pygame.K_e] or keys[pygame.K_EQUALS] or keys[pygame.K_KP_PLUS]:
        _zoom(ZOOM_STEP ** (dt * 60.0 / 6.0))
    if keys[pygame.K_c]:
        _VIEW["cx"], _VIEW["cy"] = player.x, player.y
    if wheel:
        _zoom(ZOOM_STEP ** wheel)
    _clamp_view()


def draw(screen, world, player, home, hub_list, half: float = WORLD_HALF,
         settlements=(), natives=()) -> None:
    """The world as far as the view reaches: EVERY town and EVERY hub on it.

    The map used to pin exactly two places -- the nearest town and the nearest
    hut -- which made it useless for the one question a map answers: where is
    everything. Every settlement in the view is drawn now, and every hub,
    including the hold the player himself has staked.
    """
    vw, vh = screen.get_size()
    size = max(160, min(vw - 80, vh - 110))
    x0 = (vw - size) // 2
    y0 = (vh - size) // 2 + 8

    shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 190))
    screen.blit(shade, (0, 0))
    pygame.draw.rect(screen, EDGE, (x0 - 8, y0 - 8, size + 16, size + 16),
                     border_radius=6)
    pygame.draw.rect(screen, PAPER, (x0, y0, size, size))
    pygame.draw.rect(screen, FRAME, (x0 - 8, y0 - 8, size + 16, size + 16), 2,
                     border_radius=6)

    view_half = _VIEW["half"]
    cx, cy = _VIEW["cx"], _VIEW["cy"]
    # ONE FIXED IMAGE keyed to world x,y, already built behind the loading
    # screen. The camera picks a rectangle of it; terrain and camps are all in
    # that image, so they can never disagree about where anything is.
    paper = _paper(world, int(getattr(world, "seed", 0)))
    if view_half < WORLD_HALF:
        _scale = PAPER_N / (2.0 * WORLD_HALF)
        _sx = int((cx - view_half + WORLD_HALF) * _scale)
        _sy = int((cy - view_half + WORLD_HALF) * _scale)
        _sw = max(1, int((2.0 * view_half) * _scale))
        _sx = max(0, min(PAPER_N - _sw, _sx))
        _sy = max(0, min(PAPER_N - _sw, _sy))
        _sub = paper.subsurface(pygame.Rect(_sx, _sy, _sw, _sw))
        screen.blit(pygame.transform.scale(_sub, (size, size)), (x0, y0))
    else:
        # ZOOMED OUT PAST THE WORLD: show the whole image, centred, on dark
        # paper -- never a blank screen, and never a subsurface bigger than
        # the surface it was cut from.
        _ps = max(1, int(size * WORLD_HALF / view_half))
        _off = (size - _ps) // 2
        screen.blit(pygame.transform.scale(paper, (_ps, _ps)),
                    (x0 + _off, y0 + _off))
        pygame.draw.rect(screen, PAPER, (x0, y0, size, _off))
        pygame.draw.rect(screen, PAPER, (x0, y0 + _off + _ps, size,
                                         size - _off - _ps))
        pygame.draw.rect(screen, PAPER, (x0, y0, _off, size))
        pygame.draw.rect(screen, PAPER, (x0 + _off + _ps, y0,
                                         size - _off - _ps, size))

    def w2s(wx: float, wy: float):
        if view_half < WORLD_HALF:
            return (x0 + (wx - (cx - view_half)) / (2.0 * view_half) * size,
                    y0 + (wy - (cy - view_half)) / (2.0 * view_half) * size)
        _ps = max(1, int(size * WORLD_HALF / view_half))
        _off = (size - _ps) // 2
        return (x0 + _off + (wx + WORLD_HALF) / (2.0 * WORLD_HALF) * _ps,
                y0 + _off + (wy + WORLD_HALF) / (2.0 * WORLD_HALF) * _ps)

    label_font = pygame.font.SysFont("dejavusansmono", max(11, vh // 44), bold=True)
    # Off-lattice camps (starter camps and the home camp), pinned to the same
    # world->screen transform as the fixed image.
    for _n in natives or ():
        _px, _py = w2s(getattr(_n, "x", 0.0), getattr(_n, "y", 0.0))
        if x0 - 2 <= _px <= x0 + size + 2 and y0 - 2 <= _py <= y0 + size + 2:
            _campfire(screen, int(_px), int(_py))
    # HIM -- the yellow dot is baked into the paper; this is the ring + label.
    px, py = w2s(player.x, player.y)
    inside = (x0 <= px <= x0 + size and y0 <= py <= y0 + size)
    if not inside:
        px = max(x0 + 12, min(x0 + size - 12, px))
        py = max(y0 + 12, min(y0 + size - 12, py))
    pygame.draw.circle(screen, (8, 8, 10), (int(px), int(py)), 11)
    pygame.draw.circle(screen, YOU, (int(px), int(py)), 9)
    pygame.draw.circle(screen, (28, 28, 34), (int(px), int(py)), 6)
    pygame.draw.circle(screen, (250, 232, 140), (int(px), int(py)), 3)
    if not inside:
        me = label_font.render("YOU", True, (250, 232, 140))
        screen.blit(me, (px + 13, py - me.get_height() // 2))

    font = pygame.font.SysFont("dejavusansmono", max(11, vh // 46), bold=True)
    small = pygame.font.SysFont("dejavusansmono", max(9, vh // 60))
    title = font.render("THE COUNTRY", True, WAYPOINT)
    screen.blit(title, (x0, y0 - title.get_height() - 12))
    # HOW CLOSE YOU ARE, in kilometres, and the keys
    km = int(round(view_half / 100.0))
    hint = small.render("%d km across   -   WASD pan,  Q/E zoom,  C centre,  M close"
                        % km, True, (196, 190, 176))
    screen.blit(hint, (x0 + size - hint.get_width(), y0 + size + 14))
