"""Bullets and muzzle flashes, for both the player and enemies."""

from __future__ import annotations

import math
import random

import pygame

BULLET_SPEED = 1500.0
BULLET_SPREAD = math.radians(1.5)
FLASH_TIME = 0.07
SWING_TIME = 0.30                   # axe swing animation length


def segment_circle_hit(x0, y0, x1, y1, cx, cy, r) -> bool:
    """True if the segment (x0,y0)-(x1,y1) comes within r of (cx,cy).

    Used instead of a point test so fast bullets cannot tunnel through a body.
    """
    dx, dy = x1 - x0, y1 - y0
    if dx == 0.0 and dy == 0.0:
        return math.hypot(cx - x0, cy - y0) <= r
    t = ((cx - x0) * dx + (cy - y0) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(cx - (x0 + t * dx), cy - (y0 + t * dy)) <= r


class Bullet:
    __slots__ = ("x", "y", "dx", "dy", "travelled", "prev_x", "prev_y",
                 "max_dist", "remove", "owner", "damage", "team",
                 "origin_x", "origin_y", "shooter", "dart")

    def __init__(self, x, y, dx, dy, max_dist, owner, damage, team=None,
                 shooter=None, dart=False):
        self.dart = bool(dart)
        self.shooter = shooter            # who fired it: the killer, for loot
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.prev_x = x
        self.prev_y = y
        self.origin_x = x                 # where the shot was fired from
        self.origin_y = y
        self.travelled = 0.0
        self.max_dist = max_dist
        self.remove = False
        self.owner = owner
        self.damage = damage
        self.team = team


class Combat:
    def __init__(self) -> None:
        self.bullets: list[Bullet] = []
        self.flashes: list[list] = []          # [x, y, angle, time, owner]
        self.impacts: list[list] = []          # [x, y, vx, vy, life, colour]
        self.swings: list[list] = []           # [x, y, angle, life]

    def spawn_swing(self, x: float, y: float, angle: float) -> None:
        self.swings.append([x, y, angle, SWING_TIME])

    def spawn_impact(self, x: float, y: float, colour) -> None:
        for _ in range(6):
            angle = random.uniform(0.0, 2.0 * math.pi)
            speed = random.uniform(30.0, 150.0)
            self.impacts.append([x, y, math.cos(angle) * speed,
                                 math.sin(angle) * speed,
                                 random.uniform(0.14, 0.34), colour])

    def fire(self, x, y, angle, distance, owner="player", damage=25, team=None,
             spread=None, shooter=None, dart=False) -> None:
        dev = BULLET_SPREAD if spread is None else spread
        a = angle + random.uniform(-dev, dev)
        self.bullets.append(Bullet(x, y, math.cos(a), math.sin(a),
                                   max(1.0, distance), owner, damage, team,
                                   shooter, dart=dart))
        self.flashes.append([x, y, a, FLASH_TIME, owner])

    def update(self, dt: float) -> None:
        if any(b.remove for b in self.bullets):
            self.bullets = [b for b in self.bullets if not b.remove]
        for b in self.bullets:
            if b.travelled >= b.max_dist:
                b.remove = True
                continue
            b.prev_x, b.prev_y = b.x, b.y
            step = min(BULLET_SPEED * dt, b.max_dist - b.travelled)
            b.x += b.dx * step
            b.y += b.dy * step
            b.travelled += step
        if any(b.remove for b in self.bullets):
            self.bullets = [b for b in self.bullets if not b.remove]
        for f in self.flashes:
            f[3] -= dt
        if self.flashes:
            self.flashes = [f for f in self.flashes if f[3] > 0.0]
        if self.impacts:
            for p in self.impacts:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[4] -= dt
            self.impacts = [p for p in self.impacts if p[4] > 0.0]
        if self.swings:
            for s in self.swings:
                s[3] -= dt
            self.swings = [s for s in self.swings if s[3] > 0.0]

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        for b in self.bullets:
            x1, y1 = b.x - cam_x, b.y - cam_y
            x0, y0 = b.prev_x - cam_x, b.prev_y - cam_y
            if getattr(b, "dart", False):
                # A MILITIA DART: blue, so a tranquiliser is never mistaken
                # for a bullet. Same flight, same speed, different colour.
                glow, core, head = (36, 96, 150), (80, 176, 210), (190, 232, 246)
            elif b.owner == "player":
                glow, core, head = (220, 150, 40), (255, 232, 150), (255, 255, 220)
            else:
                glow, core, head = (150, 30, 20), (255, 120, 60), (255, 205, 160)
            pygame.draw.line(screen, glow, (x0, y0), (x1, y1), 4)
            pygame.draw.line(screen, core, (x0, y0), (x1, y1), 2)
            pygame.draw.circle(screen, head, (int(x1), int(y1)), 2)

        for x, y, _vx, _vy, life, colour in self.impacts:
            pygame.draw.circle(screen, colour,
                               (int(x - cam_x), int(y - cam_y)),
                               max(1, int(1 + 4 * life)))

        for x, y, angle, life in self.swings:
            k = life / SWING_TIME                 # 1 at the start, 0 at the end
            progress = 1.0 - k
            sx, sy = x - cam_x, y - cam_y
            radius = 46
            rect = pygame.Rect(sx - radius, sy - radius, radius * 2, radius * 2)
            at = angle - 1.15 + 2.3 * progress
            fade = int(230 * k) + 25
            pygame.draw.arc(screen, (fade, fade, fade), rect, at - 0.55, at + 0.55, 4)
            pygame.draw.arc(screen, (150, 158, 168), rect, at - 0.95, at + 0.95, 2)

        for x, y, angle, time_left, owner in self.flashes:
            k = max(0.0, time_left / FLASH_TIME)
            sx, sy = x - cam_x, y - cam_y
            length = 8 + 22 * k
            color = (255, 214, 96) if owner == "player" else (255, 150, 90)
            for spread in (-0.45, 0.0, 0.45):
                ex = sx + math.cos(angle + spread) * length
                ey = sy + math.sin(angle + spread) * length
                pygame.draw.line(screen, color, (sx, sy), (ex, ey), 2)
            pygame.draw.circle(screen, (255, 248, 210), (int(sx), int(sy)), 2 + int(4 * k))


def friendly_in_line(mx, my, ex, ey, shooter, friend_team, soldiers, player, nation):
    """True if a *friendly soldier* (or the enlisted player) is in the shot.

    Civilians are deliberately ignored so village firefights stay chaotic.
    """
    for other in soldiers:
        if other is shooter or not getattr(other, "alive", False):
            continue
        if getattr(other, "team", None) != friend_team:
            continue
        if segment_circle_hit(mx, my, ex, ey, other.x, other.y, other.radius + 6):
            return True
    if (player is not None and not getattr(player, "dead", False)
            and getattr(player, "nation", None) == nation):
        if segment_circle_hit(mx, my, ex, ey, player.x, player.y, player.radius + 6):
            return True
    return False
