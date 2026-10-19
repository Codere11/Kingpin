"""map.py -- the chunky little map.

COARSE ON PURPOSE. This is drawn on a ninety-six square grid and blown up with
nearest-neighbour, so every block of the world is a fat coloured pixel with hard
edges. It is not a chart and it is not a satellite picture; it is the kind of map
you could have nailed to a wall in this world, and it is far cheaper to make than
the real thing.

AND IT ONLY KNOWS TWO PLACES. A man on the road knows where he came from and
where the nearest trade that is not on the books is; the rest is the dark. So the
map shows his own settlement and the nearest hub, and nothing else -- no other
towns, no other huts, no armies. Everything else he has to walk to.

    M    open and close
"""

from __future__ import annotations

import math

import pygame

import biomes
import hubs

GRID = 96               # samples a side -- 96 x 96 of the whole world
PAD = 26

WAYPOINT = (238, 202, 96)
HUB_COLOUR = (198, 72, 60)
YOU = (246, 246, 240)
FRAME = (150, 116, 70)
PAPER = (26, 23, 20)
EDGE = (12, 10, 9)

_CACHE: dict = {}


def _terrain(world, half: float) -> pygame.Surface:
    """A GRID x GRID thumbnail of the world's colours, made once."""
    key = (world.seed, int(half))
    got = _CACHE.get(key)
    if got is not None:
        return got
    surf = pygame.Surface((GRID, GRID))
    step = (2.0 * half) / GRID
    span = 1.0 / (GRID - 1)
    for j in range(GRID):
        wy = -half + (j + 0.5) * step
        for i in range(GRID):
            wx = -half + (i + 0.5) * step
            try:
                t = float(biomes.temperature(wx, wy, world.seed))
                h = float(biomes.humidity(wx, wy, world.seed))
                dark = biomes.mix(t, h)[0]
                surf.set_at((i, j), (int(dark[0]), int(dark[1]), int(dark[2])))
            except Exception:
                surf.set_at((i, j), (52, 62, 44))
    _CACHE[key] = surf
    return surf


def draw(screen, world, player, home, hub_list, half: float = 100000.0) -> None:
    """The whole map, as a square of fat pixels, with two marks on it."""
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

    # the ground, blown up without smoothing so every block stays a block
    thumb = _terrain(world, half)
    big = pygame.transform.scale(thumb, (size, size))
    screen.blit(big, (x0, y0))

    def at(wx: float, wy: float):
        return (x0 + int((wx + half) / (2.0 * half) * size),
                y0 + int((wy + half) / (2.0 * half) * size))

    # THE TWO PLACES THAT MATTER, BIG ENOUGH TO SEE. Ten pixels on a
    # nine-hundred pixel map is a speck, and the whole point of this map is
    # these two marks.
    label_font = pygame.font.SysFont("dejavusansmono", max(11, vh // 44), bold=True)

    def pin(px, py, colour, label, size=18):
        # a dark halo first, so it reads over light ground and dark
        pygame.draw.rect(screen, EDGE, (px - size // 2 - 3, py - size // 2 - 3,
                                        size + 6, size + 6), border_radius=4)
        pygame.draw.rect(screen, colour, (px - size // 2, py - size // 2,
                                          size, size), border_radius=3)
        pygame.draw.rect(screen, (250, 248, 240), (px - size // 2, py - size // 2,
                                                   size, size), 2, border_radius=3)
        txt = label_font.render(label, True, (250, 248, 240))
        shadow = label_font.render(label, True, (10, 9, 8))
        tx = px + size // 2 + 6
        ty = py - txt.get_height() // 2
        if tx + txt.get_width() > x0 + size - 6:          # keep it inside
            tx = px - size // 2 - 6 - txt.get_width()
        screen.blit(shadow, (tx + 1, ty + 1))
        screen.blit(txt, (tx, ty))

    if home is not None:
        px, py = at(home.x, home.y)
        pin(px, py, WAYPOINT, home.name.upper())
    near = None
    if hub_list:
        near = min(hub_list, key=lambda h: (h.x - player.x) ** 2
                   + (h.y - player.y) ** 2)
        px, py = at(near.x, near.y)
        # a line from him to it, so the map answers the question it is for
        hpx, hpy = at(player.x, player.y)
        pygame.draw.line(screen, (210, 120, 100), (hpx, hpy), (px, py), 1)
        pin(px, py, HUB_COLOUR, "OUTLAW TRADE")
    # HIM, last and on top
    px, py = at(player.x, player.y)
    pygame.draw.rect(screen, EDGE, (px - 6, py - 6, 13, 13))
    pygame.draw.rect(screen, YOU, (px - 4, py - 4, 9, 9))
    pygame.draw.rect(screen, (30, 30, 36), (px - 1, py - 1, 3, 3)))

    font = pygame.font.SysFont("dejavusansmono", max(11, vh // 46), bold=True)
    small = pygame.font.SysFont("dejavusansmono", max(9, vh // 60))
    title = font.render("THE COUNTRY", True, WAYPOINT)
    screen.blit(title, (vw // 2 - title.get_width() // 2, y0 - 34))
    bits = []
    if home is not None:
        bits.append("your town: %s" % home.name)
    if near is not None:
        bits.append("nearest trade: %.0f miles off"
                    % (math.hypot(near.x - player.x, near.y - player.y) / 1000.0))
    line = small.render("     ".join(bits), True, (222, 214, 196))
    screen.blit(line, (vw // 2 - line.get_width() // 2, y0 + size + 10))
    hint = small.render("M  to put it away", True, (150, 140, 126))
    screen.blit(hint, (vw // 2 - hint.get_width() // 2, y0 + size + 26))
