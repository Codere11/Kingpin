"""A compass: bearings to your home and to the nearest village.

The world is a plain grid: +x is east, +y is south, so -y is north -- the same
convention the world map draws with (north up). Bearings are therefore honest.
"""

from __future__ import annotations

import math

import pygame

from village import SPACING, village_center

PX_PER_M = 32.0          # one tile (32 px) reads as one metre

_DIRS = ["east", "northeast", "north", "northwest",
         "west", "southwest", "south", "southeast"]


def bearing(dx: float, dy: float) -> str:
    """One of the eight compass points from an offset (dx, dy) in world px."""
    ang = math.degrees(math.atan2(-dy, dx))      # 0 = east, 90 = north
    return _DIRS[int(round(ang / 45.0)) % 8]


def nearest_village(x: float, y: float, seed: int):
    """Centre and distance of the closest village. Villages sit on a lattice,
    so only the nine surrounding cells can hold it."""
    gx = int(math.floor(x / SPACING))
    gy = int(math.floor(y / SPACING))
    best = None
    best_d = 1e18
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            vx, vy = village_center(gx + ox, gy + oy, seed)
            d = math.hypot(vx - x, vy - y)
            if d < best_d:
                best_d = d
                best = (vx, vy)
    return best, best_d


def village_report(x: float, y: float, seed: int) -> str:
    (vx, vy), d = nearest_village(x, y, seed)
    return "Nearest village: %d m %s" % (int(round(d / PX_PER_M)),
                                         bearing(vx - x, vy - y))


def home_report(x: float, y: float, home) -> str:
    dx, dy = home[0] - x, home[1] - y
    d = math.hypot(dx, dy)
    return "Home: %d m %s" % (int(round(d / PX_PER_M)), bearing(dx, dy))


class Compass:
    """What the compass remembers: your home, and what a click should report."""

    def __init__(self) -> None:
        self.home = None          # (x, y) or None
        self.mode = None          # "village" | "home" | None


class CompassMenu:
    """The little 'press F' chooser."""

    def __init__(self) -> None:
        self.options: list[tuple[str, str]] = []
        self.hover = -1
        self.font = pygame.font.SysFont("dejavusans", 17, bold=True)
        self.title_font = pygame.font.SysFont("dejavusans", 15, bold=True)

    def open(self, has_home: bool) -> None:
        opts = [("village", "Find nearest village")]
        if has_home:
            opts.append(("home", "Find home"))
            opts.append(("sethome", "Set new home here"))
        else:
            opts.append(("sethome", "Set home here"))
        self.options = opts
        self.hover = -1

    def _rects(self, sw: int, sh: int):
        w = 300
        row_h = 46
        h = 44 + row_h * len(self.options) + 14
        x0 = (sw - w) // 2
        y0 = (sh - h) // 2
        rows = [pygame.Rect(x0 + 14, y0 + 40 + i * row_h, w - 28, row_h - 8)
                for i in range(len(self.options))]
        return pygame.Rect(x0, y0, w, h), rows

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _panel, rows = self._rects(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i, r in enumerate(rows):
                if r.collidepoint(event.pos):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(rows):
                if r.collidepoint(event.pos):
                    return self.options[i][0]
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, rows = self._rects(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 242), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, (72, 72, 80), board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)
        title = self.title_font.render("COMPASS", True, (222, 214, 196))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 10))
        for i, (_oid, label) in enumerate(self.options):
            r = rows[i]
            hovered = (i == self.hover)
            pygame.draw.rect(screen, (48, 46, 40) if hovered else (34, 34, 40),
                             r, border_radius=8)
            pygame.draw.rect(screen, (222, 176, 88) if hovered else (104, 132, 92),
                             r, width=2, border_radius=8)
            t = self.font.render(label, True, (232, 232, 238))
            screen.blit(t, (r.centerx - t.get_width() // 2,
                            r.centery - t.get_height() // 2))
