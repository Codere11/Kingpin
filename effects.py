"""Screen-space damage feedback.

Instead of a flat red overlay, damage grows a network of blood veins creeping
in from the screen edges. They spread further, thicken, and pump harder and
faster the closer the player is to death. A restrained red tint sits under
them.

Also home to the little off-screen-enemy alert icon.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pygame


class DamageVignette:
    def __init__(self, downscale: int = 8) -> None:
        self.downscale = downscale
        self._size: tuple[int, int] | None = None
        self._alpha = None
        self._small: pygame.Surface | None = None
        self._out: pygame.Surface | None = None
        self._veins: list = []

    # -- one-time geometry --------------------------------------------------
    def _prepare(self, w: int, h: int) -> None:
        if self._size == (w, h):
            return
        s = self.downscale
        mw, mh = max(1, w // s), max(1, h // s)
        ys, xs = np.mgrid[0:mh, 0:mw]
        dx = (xs + 0.5 - mw / 2.0) / (mw / 2.0)
        dy = (ys + 0.5 - mh / 2.0) / (mh / 2.0)
        dist = np.sqrt(dx * dx + dy * dy) / math.sqrt(2.0)
        radial = np.clip((dist - 0.35) / 0.62, 0.0, 1.0) ** 1.4
        falloff = 0.55 + 0.45 * radial
        self._alpha = (falloff * 255.0).astype(np.uint8)
        self._small = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._small.fill((152, 0, 0, 0))
        self._out = pygame.Surface((w, h), pygame.SRCALPHA)
        self._veins = self._make_veins(w, h)
        self._size = (w, h)

    def _make_veins(self, w: int, h: int) -> list:
        rng = random.Random(9173)
        veins = []
        cx, cy = w / 2.0, h / 2.0
        diagonal = math.hypot(w, h)
        for _ in range(13):
            edge = rng.randrange(4)
            if edge == 0:
                x, y = rng.uniform(0.0, w), -12.0
            elif edge == 1:
                x, y = w + 12.0, rng.uniform(0.0, h)
            elif edge == 2:
                x, y = rng.uniform(0.0, w), h + 12.0
            else:
                x, y = -12.0, rng.uniform(0.0, h)
            angle = math.atan2(cy - y, cx - x) + rng.uniform(-0.55, 0.55)
            points = [(x, y)]
            target = rng.uniform(0.34, 0.62) * diagonal
            travelled = 0.0
            while travelled < target:
                angle += rng.uniform(-0.5, 0.5)
                nx = x + math.cos(angle) * 18.0
                ny = y + math.sin(angle) * 18.0
                points.append((nx, ny))
                travelled += math.hypot(nx - x, ny - y)
                x, y = nx, ny
            cumulative = [0.0]
            for i in range(1, len(points)):
                cumulative.append(cumulative[-1] + math.hypot(
                    points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]))
            start = rng.uniform(0.0, 0.74)          # damage level at which it appears
            veins.append((points, cumulative, start))
        return veins

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface, damage: float, now: float,
             hit_flash: float) -> None:
        w, h = screen.get_size()
        self._prepare(w, h)
        damage = max(0.0, min(1.0, damage))

        pulse = 0.5 + 0.5 * math.sin(now * (3.0 + 11.0 * damage))
        strength = 0.50 * damage * (0.45 + 0.55 * pulse) + 0.45 * hit_flash
        strength = max(0.0, min(1.0, strength))
        if strength > 0.002:
            alpha = (self._alpha.astype(np.float32) * strength).astype(np.uint8)
            pixels = pygame.surfarray.pixels_alpha(self._small)
            pixels[:] = alpha.T
            del pixels
            try:
                pygame.transform.smoothscale(self._small, (w, h), self._out)
            except TypeError:
                self._out = pygame.transform.smoothscale(self._small, (w, h))
            screen.blit(self._out, (0, 0))

        self._draw_veins(screen, damage, now, hit_flash)

    def _draw_veins(self, screen: pygame.Surface, damage: float,
                    now: float, hit_flash: float) -> None:
        intensity = min(1.0, damage + 0.5 * hit_flash)
        if intensity <= 0.02:
            return
        phase = now * (4.0 + 13.0 * intensity)     # pumps faster when worse

        for points, cumulative, start in self._veins:
            if intensity <= start:
                continue
            span = 1.0 - start
            reach = (intensity - start) / span
            reach = min(1.0, reach + 0.05 * math.sin(phase * 0.7 + start * 9.0))
            if reach <= 0.0:
                continue
            total = cumulative[-1]
            max_dist = reach * total
            for j in range(len(points) - 1):
                if cumulative[j] >= max_dist:
                    break
                x0, y0 = points[j]
                x1, y1 = points[j + 1]
                if cumulative[j + 1] > max_dist:
                    t = (max_dist - cumulative[j]) / (cumulative[j + 1] - cumulative[j])
                    x1 = x0 + (x1 - x0) * t
                    y1 = y0 + (y1 - y0) * t
                s = cumulative[j] / total
                wave = max(0.0, math.sin(phase - s * 7.0)) ** 2

                thickness = 1.0 + 3.0 * intensity + (1.5 + 4.0 * intensity) * wave
                hot = 0.3 + 0.7 * wave
                glow = (int(20 + 70 * hot), int(4 * hot), int(2 + 8 * hot))
                core = (int(40 * intensity + 150 * hot), int(14 * hot), int(18 * hot))
                pygame.draw.line(screen, glow, (x0, y0), (x1, y1), max(1, int(thickness)))
                pygame.draw.line(screen, core, (x0, y0), (x1, y1),
                                 max(1, int(thickness * 0.5)))


def draw_alert(screen: pygame.Surface, sx: float, sy: float,
               now: float, phase: float) -> None:
    """A small, hand-drawn looking '!' over someone the player cannot see."""
    cycle = (now * 1.35 + phase * 0.37) % 1.0
    if not (cycle < 0.16 or 0.28 <= cycle < 0.44):   # irregular double-blink
        return
    bob = math.sin(now * 6.0 + phase) * 1.6
    jitter = math.sin(now * 9.0 + phase * 2.3) * 1.4
    top_x = sx + jitter
    top_y = sy - 32.0 + bob
    bot_x, bot_y = top_x - 1.6, top_y + 13.0

    points = [(top_x - 2.0, top_y), (top_x + 2.0, top_y),
              (bot_x + 3.3, bot_y), (bot_x - 3.3, bot_y)]
    pygame.draw.polygon(screen, (247, 228, 164), points)
    pygame.draw.polygon(screen, (58, 40, 22), points, 2)
    pygame.draw.circle(screen, (247, 228, 164), (int(top_x), int(top_y + 19)), 2)
    pygame.draw.circle(screen, (58, 40, 22), (int(top_x), int(top_y + 19)), 2, 1)
