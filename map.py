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
PAN_RATE = 0.85          # a full screen a second, at any zoom

_CACHE: dict = {}
_THREADS: dict = {}
_VIEW = {"cx": 0.0, "cy": 0.0, "half": WORLD_HALF}

CHART_PX = 140            # cells across the chart
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
    key = (int(getattr(world, "seed", 0)),
           int(float(cx) // max(1.0, cell * 0.25)),
           int(float(cy) // max(1.0, cell * 0.25)),
           zoom_i, CHART_PX)
    got = _CACHE.get(key)
    if got is not None:
        return got
    n = CHART_PX
    x0, y0 = cx - half, cy - half
    step = (2.0 * half) / n
    coords = x0 + (np.arange(n, dtype=np.float32) + 0.5) * step
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
    if len(_CACHE) >= CHART_KEEP:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = surf
    return surf


def reset() -> None:
    """Back to the whole world, centred where it has always been."""
    _VIEW["cx"], _VIEW["cy"] = 0.0, 0.0
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
    """Pan and zoom. Called every frame the map is open."""
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
    chart = _chart(world, cx, cy, view_half)
    if chart is None:
        charting = small_charting.render("charting the country…", True,
                                         (206, 198, 176))
        screen.blit(charting, (x0 + size // 2 - charting.get_width() // 2,
                               y0 + size // 2 - charting.get_height() // 2))
    else:
        screen.blit(pygame.transform.scale(chart, (size, size)), (x0, y0))
    # BEYOND THE WORLD IS NOT DARK, IT IS UNCHARTED. The paper shows through.
    if view_half > WORLD_HALF:
        inset = int((view_half - WORLD_HALF) / (2.0 * view_half) * size)
        for r in ((x0, y0, size, inset), (x0, y0 + size - inset, size, inset),
                  (x0, y0, inset, size), (x0 + size - inset, y0, inset, size)):
            pygame.draw.rect(screen, PAPER, r)

    def at(wx: float, wy: float):
        return (x0 + int((wx - (cx - view_half)) / (2.0 * view_half) * size),
                y0 + int((wy - (cy - view_half)) / (2.0 * view_half) * size))

    label_font = pygame.font.SysFont("dejavusansmono", max(11, vh // 44), bold=True)

    # ---- NATIVE CAMPS AND THE PLAYER ------------------------------
    # Old Soviet settlements, hubs and the gulag are gone from the paper; what
    # remains is the country itself -- biome legend, native campfires, and him.
    taken: list = []

    small_font = pygame.font.SysFont("dejavusansmono", max(9, vh // 62),
                                     bold=True)
    for _n in natives or ():
        _px, _py = at(_n.x, _n.y)
        if x0 - 2 <= _px <= x0 + size + 2 and y0 - 2 <= _py <= y0 + size + 2:
            _campfire(screen, int(_px), int(_py))
            _lbl = small_font.render("camp", True, (250, 248, 240))
            _sd = small_font.render("camp", True, (10, 9, 8))
            for _tx, _ty in ((_px + 9, _py - _lbl.get_height() // 2),
                             (_px - 9 - _lbl.get_width(), _py - _lbl.get_height() // 2),
                             (_px - _lbl.get_width() // 2, _py - 16),
                             (_px - _lbl.get_width() // 2, _py + 10)):
                _r = pygame.Rect(_tx, _ty, _lbl.get_width(), _lbl.get_height())
                if (_r.left < x0 or _r.right > x0 + size
                        or _r.top < y0 or _r.bottom > y0 + size):
                    continue
                if any(_r.colliderect(o) for o in taken):
                    continue
                taken.append(_r)
                screen.blit(_sd, (_tx + 1, _ty + 1))
                screen.blit(_lbl, (_tx, _ty))
                break
    # HIM, last and on top -- AND NEVER LOST OFF THE EDGE. A map you cannot
    # find yourself on is not a map; when the view has left him he is pinned
    # to the frame with a bright ring, so pressing C is only a convenience.
    px, py = at(player.x, player.y)
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
