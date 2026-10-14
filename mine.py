"""The inside of a village mine.

A room of solid rock with no window and no way to see out: whatever is
happening in the village, the man at the face does not know about it. In the
middle is a seam that never runs out -- the outside seams are worth three
swings and are gone, this one is worth fifteen and is still there tomorrow.

The fifteen is the point. A village's iron is gathered by men who walk to a
seam, break it, and walk on; the man who works the face all day pays for that
with his time, three swings in the open against fifteen in the dark. Same
iron out of it, five times the work.
"""

from __future__ import annotations

import random

import pygame

W = 560                  # room size, in world pixels
H = 420
T = 22                   # thickness of the rock all around
SWINGS = 15              # five times the open seam


class MineRoom:
    """One mine's working face. Made once, kept for the life of the world."""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.rng = random.Random(seed & 0x7FFFFFFF)
        self.W, self.H = W, H
        self.door = pygame.Rect(W // 2 - 26, H - T - 6, 52, T + 6)
        self.chunk = pygame.Rect(W // 2 - 34, H // 2 - 26, 68, 52)
        self.swings = 0
        self.flash = 0.0
        self.rock = self._render_rock()

    def _render_rock(self) -> pygame.Surface:
        """The walls: broken stone, no opening, nothing to look through."""
        surf = pygame.Surface((self.W, self.H))
        surf.fill((34, 32, 34))
        r = self.rng
        for _ in range(420):
            x = r.randrange(0, self.W)
            y = r.randrange(0, self.H)
            w = r.randrange(8, 30)
            h = r.randrange(6, 20)
            shade = r.randrange(38, 62)
            pygame.draw.rect(surf, (shade, shade - 3, shade - 1), (x, y, w, h))
        # the chamber itself, darker and grainy
        floor = pygame.Rect(T, T, self.W - 2 * T, self.H - 2 * T)
        pygame.draw.rect(surf, (46, 42, 40), floor)
        for _ in range(600):
            x = r.randrange(floor.left, floor.right)
            y = r.randrange(floor.top, floor.bottom)
            g = r.randrange(28, 62)
            pygame.draw.rect(surf, (g, g - 2, g - 3), (x, y, 3, 2))
        pygame.draw.rect(surf, (22, 20, 22), floor, 3)
        pygame.draw.rect(surf, (16, 15, 16), (0, 0, self.W, self.H), T)
        return surf

    def inside(self, x: float, y: float) -> bool:
        return (T <= x <= self.W - T and T <= y <= self.H - T)

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        return (min(max(x, T + 12), self.W - T - 12),
                min(max(y, T + 12), self.H - T - 12))

    def hits_chunk(self, x: float, y: float, reach: float = 64.0) -> bool:
        cx = min(max(x, self.chunk.left), self.chunk.right)
        cy = min(max(y, self.chunk.top), self.chunk.bottom)
        return (x - cx) ** 2 + (y - cy) ** 2 <= reach * reach

    def update(self, dt: float) -> None:
        if self.flash > 0.0:
            self.flash = max(0.0, self.flash - dt)

    def swing(self, mine_yield) -> int:
        """Take a swing at the face. Returns iron when it comes loose."""
        self.swings += 1
        self.flash = 0.18
        if self.swings < SWINGS:
            return 0
        self.swings = 0                    # the seam does not run out
        return self.rng.randint(*mine_yield)

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             vw: int = 0, vh: int = 0) -> None:
        # THE ROCK GOES ALL THE WAY TO THE EDGES. The chamber is smaller than
        # the screen, and anything not covered would still be showing the last
        # frame drawn up there -- the world, sliding about as the camera moved.
        # Down here there is no view out: it is stone in every direction.
        w = vw or screen.get_width()
        h = vh or screen.get_height()
        screen.fill((16, 15, 16), (0, 0, w, h))
        ox, oy = int(-cam_x), int(-cam_y)
        screen.blit(self.rock, (ox, oy))
        # ...and rough stone beyond the chamber walls. It is drawn from a
        # per-CELL seed, not from a running random: the first version advanced
        # the generator every frame, so the rock around the chamber boiled and
        # flickered like static.
        cell = 52
        x0 = int((cam_x - 80) // cell)
        y0 = int((cam_y - 80) // cell)
        x1 = int((cam_x + w + 80) // cell)
        y1 = int((cam_y + h + 80) // cell)
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                seed = (cx * 73856093) ^ (cy * 19349663) ^ (self.seed * 2654435761)
                rr = random.Random(seed & 0x7FFFFFFF)
                for _ in range(2):
                    bx = cx * cell + rr.randrange(0, cell) - int(cam_x)
                    by = cy * cell + rr.randrange(0, cell) - int(cam_y)
                    # ROOM SPACE ON BOTH SIDES. bx is a screen coordinate and
                    # ox is -cam_x, so the old test compared room space against
                    # screen space: the rough rock meant to be OUTSIDE the
                    # chamber was painted straight across the floor, sliding
                    # about as the camera moved. That was the "random patterns".
                    if (T < bx + int(cam_x) < self.W - T
                            and T < by + int(cam_y) < self.H - T):
                        continue
                    if not (-40 <= bx <= w + 40 and -40 <= by <= h + 40):
                        continue
                    g = rr.randrange(26, 48)
                    pygame.draw.rect(screen, (g, g - 2, g - 3),
                                     (bx, by, rr.randrange(10, 34),
                                      rr.randrange(8, 24)))
        c = self.chunk
        face = (162, 158, 166) if self.flash > 0.0 else (118, 116, 124)
        pygame.draw.rect(screen, (58, 56, 60),
                         (c.x + ox - 4, c.y + oy - 4, c.w + 8, c.h + 8),
                         border_radius=6)
        pygame.draw.rect(screen, face, (c.x + ox, c.y + oy, c.w, c.h),
                         border_radius=5)
        for i in range(4):                 # a face of broken ore, not a block
            rx = c.x + ox + 6 + i * (c.w - 16) // 4
            pygame.draw.rect(screen, (198, 176, 118),
                             (rx, c.y + oy + 8 + (i % 2) * 14, 9, 8),
                             border_radius=2)
        # the day's work, so a man can see how far into the seam he is
        done = self.swings / float(SWINGS)
        bar = pygame.Rect(c.x + ox, c.y + oy + c.h + 8, c.w, 5)
        pygame.draw.rect(screen, (30, 28, 30), bar)
        pygame.draw.rect(screen, (188, 156, 92),
                         (bar.x, bar.y, int(bar.w * done), bar.h))
        # the way out, at the bottom of the chamber
        d = self.door
        pygame.draw.rect(screen, (12, 11, 12),
                         (d.x + ox, d.y + oy, d.w, d.h))
        pygame.draw.rect(screen, (96, 74, 48),
                         (d.x + ox, d.y + oy, d.w, d.h), 3)
