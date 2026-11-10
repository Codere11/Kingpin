"""smoke.py -- a smoke signal rising from a conquered settlement's fire."""
import math
import random

import pygame


class Smoke:
    """Grey puffs that rise and drift; a signal stays lit for a while."""

    def __init__(self) -> None:
        self.parts: list[list] = []     # [x, y, r, age, max_age, drift]
        self.sources: list[list] = []   # [x, y, time_left, emit_timer]

    def signal(self, x: float, y: float, seconds: float = 14.0) -> None:
        """Light a smoke signal: a column that keeps pouring for `seconds`."""
        self.sources.append([x, y, seconds, 0.0])

    def update(self, dt: float) -> None:
        # keep each source pouring while it is lit
        for s in self.sources:
            s[2] -= dt
            s[3] -= dt
            if s[3] <= 0.0 and s[2] > 0.0:
                s[3] = 0.10
                for _ in range(2):
                    a = random.uniform(0.0, 2.0 * math.pi)
                    r = random.uniform(0.0, 6.0)
                    self.parts.append([
                        s[0] + math.cos(a) * r,
                        s[1] + math.sin(a) * r,
                        random.uniform(3.0, 8.0),
                        0.0,
                        random.uniform(5.0, 9.0),
                        random.uniform(-10.0, 10.0),
                    ])
        self.sources[:] = [s for s in self.sources if s[2] > 0.0]
        # age every puff: it rises, drifts, swells and thins out
        keep = []
        for p in self.parts:
            p[3] += dt
            p[1] -= 46.0 * dt
            p[0] += p[5] * dt
            p[2] += 5.0 * dt
            if p[3] < p[4]:
                keep.append(p)
        self.parts = keep
        if len(self.parts) > 600:
            del self.parts[:len(self.parts) - 600]

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             vw: int, vh: int) -> None:
        for x, y, r, age, max_age, _d in self.parts:
            sx = x - cam_x
            sy = y - cam_y
            if sx < -40 or sy < -80 or sx > vw + 40 or sy > vh + 20:
                continue
            t = age / max_age
            alpha = int(110 * (1.0 - t))
            rr = max(2, int(r))
            d = rr * 2 + 4
            patch = pygame.Surface((d, d), pygame.SRCALPHA)
            g = 90 + int(70 * t)
            pygame.draw.circle(patch, (g, g, g + 8, alpha), (d // 2, d // 2), rr)
            screen.blit(patch, (int(sx) - d // 2, int(sy) - d // 2))
