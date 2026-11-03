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

CHART_PX = 56            # cells across the chart
CHART_SAMPLES = 4        # 4 x 4 noise samples per cell, averaged
CHART_KEEP = 12          # charts remembered, then the oldest is dropped


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
    n = CHART_PX * CHART_SAMPLES
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
    surf = pygame.Surface((CHART_PX, CHART_PX))
    for j in range(CHART_PX):
        for i in range(CHART_PX):
            bt = float(temps[j * CHART_SAMPLES:(j + 1) * CHART_SAMPLES,
                              i * CHART_SAMPLES:(i + 1) * CHART_SAMPLES].mean())
            bh = float(hums[j * CHART_SAMPLES:(j + 1) * CHART_SAMPLES,
                             i * CHART_SAMPLES:(i + 1) * CHART_SAMPLES].mean())
            try:
                c = biomes.mix(bt, bh)[0]
            except Exception:
                c = (52, 62, 44)
            surf.set_at((i, j), (int(c[0]), int(c[1]), int(c[2])))
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
    """Zoom about a world point, so the ground under it stays put."""
    before = _VIEW["half"]
    _VIEW["half"] = max(MIN_HALF, min(MAX_HALF, before / factor))
    scale = _VIEW["half"] / before
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
         settlements=()) -> None:
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
        screen.blit(pygame.transform.smoothscale(chart, (size, size)), (x0, y0))
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

    # ---- THE GULAG, AT THE TOP-RIGHT OF THE WASTE -----------------------
    try:
        import gulag as _gulag
        gx, gy = _gulag.middle()
        if (cx - view_half) <= gx <= (cx + view_half) and (cy - view_half) <= gy <= (cy + view_half):
            ax, ay = (x0 + int((gx - (cx - view_half)) / (2.0 * view_half) * size),
                      y0 + int((gy - (cy - view_half)) / (2.0 * view_half) * size))
            r = max(4, size // 90)
            pygame.draw.rect(screen, (28, 26, 24), (ax - r, ay - r, r * 2, r * 2))
            pygame.draw.rect(screen, (206, 62, 48), (ax - r, ay - r, r * 2, r * 2), 2)
            pygame.draw.line(screen, (206, 62, 48), (ax - r // 2, ay - r // 2),
                             (ax + r // 2, ay + r // 2), 2)
            pygame.draw.line(screen, (206, 62, 48), (ax + r // 2, ay - r // 2),
                             (ax - r // 2, ay + r // 2), 2)
            lbl = small_charting.render("GULAG", True, (226, 96, 78))
            screen.blit(lbl, (ax - lbl.get_width() // 2, ay + r + 3))
    except Exception:
        pass

    # ---- EVERY SETTLEMENT, AND EVERY HUB ------------------------------
    # A dot is not enough to tell a town from a camp from a man's own yard, so
    # each has its own mark and its own colour, and a name when there is room
    # for it on the paper. Nothing is edge-pinned but the things that matter
    # to him: the map is the country, not a compass.
    taken: list = []

    def mark(wx, wy, colour, label, kind):
        px, py = at(wx, wy)
        if not (x0 - 2 <= px <= x0 + size + 2 and y0 - 2 <= py <= y0 + size + 2):
            return
        r = 7 if kind == "settlement" else 6
        if kind == "settlement":
            pygame.draw.rect(screen, EDGE, (px - r - 1, py - r - 1,
                                           2 * r + 3, 2 * r + 3),
                             border_radius=2)
            pygame.draw.rect(screen, colour, (px - r, py - r, 2 * r, 2 * r),
                             border_radius=2)
            pygame.draw.rect(screen, (250, 248, 240),
                             (px - r, py - r, 2 * r, 2 * r), 1, border_radius=2)
        else:
            pts = [(px, py - r - 2), (px + r + 2, py), (px, py + r + 2),
                   (px - r - 2, py)]
            pygame.draw.polygon(screen, EDGE, pts)
            inner = [(px, py - r), (px + r, py), (px, py + r), (px - r, py)]
            pygame.draw.polygon(screen, colour, inner)
            pygame.draw.polygon(screen, (250, 248, 240), inner, 1)
        if not label:
            return
        txt = small_font.render(label, True, (250, 248, 240))
        shade = small_font.render(label, True, (10, 9, 8))
        for tx, ty in ((px + r + 5, py - txt.get_height() // 2),
                       (px - r - 5 - txt.get_width(), py - txt.get_height() // 2),
                       (px - txt.get_width() // 2, py - r - 4 - txt.get_height()),
                       (px - txt.get_width() // 2, py + r + 4)):
            rect = pygame.Rect(tx, ty, txt.get_width(), txt.get_height())
            if (rect.left < x0 or rect.right > x0 + size
                    or rect.top < y0 or rect.bottom > y0 + size):
                continue
            if any(rect.colliderect(other) for other in taken):
                continue
            taken.append(rect)
            screen.blit(shade, (tx + 1, ty + 1))
            screen.blit(txt, (tx, ty))
            break

    small_font = pygame.font.SysFont("dejavusansmono", max(9, vh // 62),
                                     bold=True)
    for _v in settlements or ():
        mark(_v.x, _v.y, (214, 198, 156), _v.name.split()[0], "settlement")
    for _h in hub_list or ():
        _mine = getattr(_h, "is_player_hub", False)
        _lab = (getattr(_h, "name", "hold") if _mine else "camp")
        mark(_h.x, _h.y, (236, 206, 120) if _mine else (176, 122, 200),
             _lab.split()[0] if _mine else "camp", "hub")
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
