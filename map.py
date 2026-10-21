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

import pygame

import biomes
import hubs

WORLD_PX = 320          # the one thumbnail: the whole world at 320 x 320
GRID = WORLD_PX

WAYPOINT = (238, 202, 96)
HUB_COLOUR = (198, 72, 60)
YOU = (246, 246, 240)
FRAME = (150, 116, 70)
PAPER = (26, 23, 20)
EDGE = (12, 10, 9)
DARK = (18, 16, 14)

WORLD_HALF = 100000.0
MIN_HALF = 1200.0        # the closest you may zoom: about two villages wide
MAX_HALF = WORLD_HALF * 1.35

ZOOM_STEP = 1.16         # per notch: smooth, and you can always get back
PAN_RATE = 0.85          # a full screen a second, at any zoom

_CACHE: dict = {}
_VIEW = {"cx": 0.0, "cy": 0.0, "half": WORLD_HALF}


def _thumb(world) -> pygame.Surface:
    """The whole world, WORLD_PX a side, made once and kept."""
    key = (world.seed, WORLD_PX)
    got = _CACHE.get(key)
    if got is not None:
        return got
    surf = pygame.Surface((WORLD_PX, WORLD_PX))
    step = (2.0 * WORLD_HALF) / WORLD_PX
    for j in range(WORLD_PX):
        wy = -WORLD_HALF + (j + 0.5) * step
        for i in range(WORLD_PX):
            wx = -WORLD_HALF + (i + 0.5) * step
            try:
                t = float(biomes.temperature(wx, wy, world.seed))
                h = float(biomes.humidity(wx, wy, world.seed))
                dark = biomes.mix(t, h)[0]
                surf.set_at((i, j), (int(dark[0]), int(dark[1]), int(dark[2])))
            except Exception:
                surf.set_at((i, j), (52, 62, 44))
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


def draw(screen, world, player, home, hub_list, half: float = WORLD_HALF) -> None:
    """The world as far as the view reaches, with the two places that matter."""
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
    thumb = _thumb(world)

    # the source rectangle of the thumbnail this view covers, in thumbnail px
    sx = (cx - view_half + WORLD_HALF) / (2.0 * WORLD_HALF) * WORLD_PX
    sy = (cy - view_half + WORLD_HALF) / (2.0 * WORLD_HALF) * WORLD_PX
    sw = (2.0 * view_half) / (2.0 * WORLD_HALF) * WORLD_PX
    sw = max(1.0, min(float(WORLD_PX), sw))
    src = pygame.Rect(int(sx), int(sy),
                      max(1, int(sw)), max(1, int(sw)))
    src = src.clip(pygame.Rect(0, 0, WORLD_PX, WORLD_PX))
    if src.w > 0 and src.h > 0:
        big = pygame.transform.scale(thumb.subsurface(src), (size, size))
        screen.blit(big, (x0, y0))
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

    def pin(wx, wy, colour, label, size_px=18):
        px, py = at(wx, wy)
        # AN EDGE MARK RATHER THAN NOTHING. A settlement the view has left is
        # still the settlement; it is pinned to the frame with a small mark so
        # the map never simply loses it.
        inside = (x0 <= px <= x0 + size and y0 <= py <= y0 + size)
        if not inside:
            px = max(x0 + 10, min(x0 + size - 10, px))
            py = max(y0 + 10, min(y0 + size - 10, py))
            pygame.draw.rect(screen, EDGE, (px - 5, py - 5, 11, 11),
                             border_radius=3)
            pygame.draw.rect(screen, colour, (px - 3, py - 3, 7, 7),
                             border_radius=2)
            return
        pygame.draw.rect(screen, EDGE, (px - size_px // 2 - 3,
                                        py - size_px // 2 - 3,
                                        size_px + 6, size_px + 6), border_radius=4)
        pygame.draw.rect(screen, colour, (px - size_px // 2, py - size_px // 2,
                                          size_px, size_px), border_radius=3)
        pygame.draw.rect(screen, (250, 248, 240), (px - size_px // 2,
                                                   py - size_px // 2,
                                                   size_px, size_px), 2,
                         border_radius=3)
        txt = label_font.render(label, True, (250, 248, 240))
        shadow = label_font.render(label, True, (10, 9, 8))
        tx = px + size_px // 2 + 6
        ty = py - txt.get_height() // 2
        if tx + txt.get_width() > x0 + size - 6:
            tx = px - size_px // 2 - 6 - txt.get_width()
        screen.blit(shadow, (tx + 1, ty + 1))
        screen.blit(txt, (tx, ty))

    # THE CLOSEST SETTLEMENT AND THE CLOSEST HUT, both to the man, not the view.
    if home is not None:
        pin(home.x, home.y, WAYPOINT, home.name.upper())
    if hub_list:
        near = min(hub_list, key=lambda h: (h.x - player.x) ** 2
                   + (h.y - player.y) ** 2)
        pin(near.x, near.y, HUB_COLOUR, "OUTLAW TRADE")
        hpx, hpy = at(player.x, player.y)
        px, py = at(near.x, near.y)
        if (x0 <= hpx <= x0 + size and y0 <= hpy <= y0 + size):
            pygame.draw.line(screen, (210, 120, 100), (hpx, hpy), (px, py), 1)
    # HIM, last and on top
    px, py = at(player.x, player.y)
    if x0 <= px <= x0 + size and y0 <= py <= y0 + size:
        pygame.draw.rect(screen, EDGE, (px - 6, py - 6, 13, 13))
        pygame.draw.rect(screen, YOU, (px - 4, py - 4, 9, 9))
        pygame.draw.rect(screen, (30, 30, 36), (px - 1, py - 1, 3, 3))

    font = pygame.font.SysFont("dejavusansmono", max(11, vh // 46), bold=True)
    small = pygame.font.SysFont("dejavusansmono", max(9, vh // 60))
    title = font.render("THE COUNTRY", True, WAYPOINT)
    screen.blit(title, (x0, y0 - title.get_height() - 12))
    # HOW CLOSE YOU ARE, in kilometres, and the keys
    km = int(round(view_half / 100.0))
    hint = small.render("%d km across   -   WASD pan,  Q/E zoom,  C centre,  M close"
                        % km, True, (196, 190, 176))
    screen.blit(hint, (x0 + size - hint.get_width(), y0 + size + 14))
