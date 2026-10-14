"""Blood decals.

When someone is hit, droplets spawn at their position and spread outward over
a moment, then stay on the ground. Blood is drawn with the world (before the
vision mask), so it is subject to what the player can actually see.
"""

from __future__ import annotations

import math
import random

import pygame

BLOOD = (120, 10, 16)
BLOOD_DARK = (86, 6, 10)
BLOOD_DRY = (74, 40, 30)         # what a dried splat settles into
MAX_SPLATS = 500
DRY_MIN = 60.0                   # a minute before it starts going
DRY_MAX = 180.0                  # three, and it is gone
DRY_FADE = 25.0                  # the last stretch it fades out


class Blood:
    def __init__(self) -> None:
        # [x, y, radius, age, max_radius, dry_at]
        self.splats: list[list] = []

    def spawn(self, x: float, y: float, drops: int = 7, spread: float = 14.0) -> None:
        for _ in range(drops):
            angle = random.uniform(0.0, 2.0 * math.pi)
            distance = random.uniform(0.0, spread)
            self.splats.append([
                x + math.cos(angle) * distance,
                y + math.sin(angle) * distance,
                random.uniform(1.0, 2.6),
                0.0,
                random.uniform(4.0, 10.0),
                random.uniform(DRY_MIN, DRY_MAX),
            ])
        if len(self.splats) > MAX_SPLATS:
            del self.splats[:len(self.splats) - MAX_SPLATS]

    def drip(self, x: float, y: float, drops: int = 2) -> None:
        """A small spot of blood, for trails left by a wounded character."""
        for _ in range(drops):
            angle = random.uniform(0.0, 2.0 * math.pi)
            distance = random.uniform(0.0, 5.0)
            self.splats.append([
                x + math.cos(angle) * distance,
                y + math.sin(angle) * distance,
                random.uniform(0.8, 1.8),
                0.0,
                random.uniform(2.5, 5.0),
                random.uniform(DRY_MIN, DRY_MAX),
            ])

    def freshest_near(self, x: float, y: float, radius: float = 380.0,
                      max_age: float = 40.0):
        """Position of the newest (least-dried) splat within radius, or None."""
        best = None
        best_age = max_age
        limit = radius * radius
        for sx, sy, _r, age, _mr, _dry in self.splats:
            if age >= best_age:
                continue
            dx, dy = sx - x, sy - y
            if dx * dx + dy * dy <= limit:
                best_age = age
                best = (sx, sy)
        return best

    def update(self, dt: float) -> None:
        keep = []
        for splat in self.splats:
            splat[3] += dt
            if splat[2] < splat[4]:
                splat[2] = min(splat[4], splat[2] + dt * 6.0)
            if splat[3] < splat[5]:        # spilled, then dried, then gone
                keep.append(splat)
        if len(keep) != len(self.splats):
            self.splats = keep

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             vw: int, vh: int) -> None:
        for x, y, radius, age, _maxr, dry_at in self.splats:
            sx, sy = x - cam_x, y - cam_y
            if sx < -20 or sy < -20 or sx > vw + 20 or sy > vh + 20:
                continue
            # It dries darker as it sits, then thins away over the last stretch.
            left = dry_at - age
            if left >= DRY_FADE:
                fresh, alpha = 0.0, 255
            else:
                fresh = 1.0 - max(0.0, left) / DRY_FADE
                alpha = int(255 * max(0.0, left) / DRY_FADE)
            col = tuple(int(a + (b - a) * fresh) for a, b in zip(BLOOD, BLOOD_DRY))
            dark = tuple(int(a + (b - a) * fresh) for a, b in zip(BLOOD_DARK, BLOOD_DRY))
            r = max(1.0, radius * (0.55 + 0.45 * (1.0 - fresh)))
            if alpha >= 250:
                pygame.draw.circle(screen, col, (int(sx), int(sy)), max(1, int(r)))
                pygame.draw.circle(screen, col, (int(sx + r * 0.9), int(sy - r * 0.5)),
                                   max(1, int(r * 0.45)))
                pygame.draw.circle(screen, dark, (int(sx - r * 0.8), int(sy + r * 0.6)),
                                   max(1, int(r * 0.4)))
            else:
                d = int(r * 2.4) + 6
                patch = pygame.Surface((d, d), pygame.SRCALPHA)
                c = (d / 2.0, d / 2.0)
                pygame.draw.circle(patch, col + (alpha,), c, max(1, int(r)))
                pygame.draw.circle(patch, col + (alpha,),
                                   (c[0] + r * 0.9, c[1] - r * 0.5), max(1, int(r * 0.45)))
                pygame.draw.circle(patch, dark + (alpha,),
                                   (c[0] - r * 0.8, c[1] + r * 0.6), max(1, int(r * 0.4)))
                screen.blit(patch, (sx - c[0], sy - c[1]))
