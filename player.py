"""The player-controlled character, drawn as a simple top-down figure that
holds whatever inventory item is selected.
"""

from __future__ import annotations

import math

import pygame
import face

import items
import guns

KEY_LEFT = (pygame.K_a, pygame.K_LEFT)
KEY_RIGHT = (pygame.K_d, pygame.K_RIGHT)
KEY_UP = (pygame.K_w, pygame.K_UP)
KEY_DOWN = (pygame.K_s, pygame.K_DOWN)

# item_id -> (icon size, rotates with facing, side offset from the body)
HOLD: dict[str, tuple[int, bool, float]] = {
    "rifle": (48, True, 7.0),
    "shotgun": (52, True, 7.0),
    "pickaxe": (46, True, 7.0),
    "compass": (30, False, 10.0),
    "iron": (28, False, 10.0),
    "shovel": (46, True, 7.0),
    "watering_can": (32, False, 10.0),
    "seed_bag": (30, False, 10.0),
    "ammo": (26, False, 10.0),
    "first_aid": (30, False, 10.0),
    "axe": (46, True, 7.0),
    "wood": (30, False, 10.0),
    "raw_meat": (30, False, 10.0),
    "cooked_meat": (30, False, 10.0),
    "bread": (30, False, 10.0),
    "wheat_seed": (30, False, 10.0),
}

SWING_COOLDOWN = 1.5
SWING_ANIM = 0.32


class Player:
    def __init__(self, x: float, y: float, speed: float = 240.0) -> None:
        self.x = x
        self.y = y
        self.speed = speed
        self.facing = (0.0, 1.0)
        self.moving = False
        # THE SAME BODY AS THE MAN IN THE RANKS. creatures.Soldier has 115;
        # the player had 100, so he was both the strongest blow in the world
        # and the frailest body that threw one. One standard, applied.
        self.max_health = 115
        self.health = 100
        self.heal_rate = 1.5           # hp/s while well fed (hunger = satiety)
        self.radius = 12
        self.hit_flash = 0.0
        self.dead = False
        self.death_timer = 0.0
        self.bleed = 0.0
        self.sprint_speed = speed * 1.7
        self.max_stamina = 30.0        # seconds of sprinting (base)
        self.base_stamina = 30.0
        self.stamina = 30.0
        self.exhausted = False
        self.sprinting = False
        self.swing_cd = 0.0
        self.attack_flash = 0.0
        self.hurt_flash = 0.0
        self.swing_anim = 0.0
        self.skill_speed = 1.0         # movement skill multiplier
        self.skill_stamina = 1.0       # stamina-duration multiplier
        self.skill_axe_cd = SWING_COOLDOWN
        self.mags = {k: v for k, v in guns.MAG.items()}   # rounds per weapon
        self.reloading = 0.0
        self.reload_kind = None
        self.reload_done = False
        self.gun_cd = 0.0
        self.max_hunger = 100.0
        self.hunger = 100.0
        self.god = False
        # Enlistment. A soldier of a nation is paid the soldier's wage every
        # day, takes a soldier's share of what the column plunders, and is a
        # lawful target for everyone that nation is at war with.
        self.wage = 0
        self.tax_paid = 0          # coin paid in the current three-day window
        self.tax_window = -1       # the day that window opened
        self.army = None
        self.village = None
        self.squad: list = []
        self._shadow = pygame.Surface((30, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(self._shadow, (15, 25, 15, 90), (0, 0, 30, 12))

    @property
    def hunger_factor(self) -> float:
        """Movement multiplier: starving slows you down."""
        return 0.55 + 0.45 * min(1.0, self.hunger / 40.0)

    def eat(self, amount: float) -> None:
        self.hunger = min(self.max_hunger, self.hunger + amount)

    def respawn(self) -> None:
        self.health = self.max_health
        self.dead = False
        self.death_timer = 0.0
        self.bleed = 0.0
        self.hit_flash = 0.0
        self.hunger = max(self.hunger, 60.0)

    def can_swing(self) -> bool:
        return self.swing_cd <= 0.0

    def start_swing(self) -> None:
        self.swing_cd = self.skill_axe_cd
        self.swing_anim = SWING_ANIM
        self.attack_flash = face.WAR_SECONDS   # and he wears the war face

    @property
    def swing_progress(self) -> float:
        if self.swing_anim <= 0.0:
            return 0.0
        return 1.0 - self.swing_anim / SWING_ANIM

    def take_damage(self, amount: int) -> None:
        if self.dead or self.god:
            return
        self.health = max(0, self.health - amount)
        self.hit_flash = 0.15
        self.hurt_flash = face.HURT_SECONDS
        self.bleed = 6.0
        if self.health <= 0:
            self.dead = True
            self.death_timer = 1.8

    def update(self, dt: float, keys, aim: tuple[float, float] | None = None,
               speed_scale: float = 1.0) -> None:
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if self.bleed > 0.0:
            self.bleed = max(0.0, self.bleed - dt)
        if self.attack_flash > 0.0:
            self.attack_flash = max(0.0, self.attack_flash - dt)
        if self.hurt_flash > 0.0:
            self.hurt_flash = max(0.0, self.hurt_flash - dt)
        if self.swing_cd > 0.0:
            self.swing_cd = max(0.0, self.swing_cd - dt)
        # A full belly mends a body: the player's hunger is satiety, so 80+ is well fed.
        if self.hunger >= 80.0 and self.health < self.max_health:
            self.health = min(self.max_health, self.health + self.heal_rate * dt)
        if self.swing_anim > 0.0:
            self.swing_anim = max(0.0, self.swing_anim - dt)
        if self.gun_cd > 0.0:
            self.gun_cd = max(0.0, self.gun_cd - dt)
        if self.reloading > 0.0:
            self.reloading = max(0.0, self.reloading - dt)
            if self.reloading == 0.0:
                self.reload_done = True

        # Hunger: one full 10-minute day/night cycle starves you to death.
        if not self.dead and not self.god:
            self.hunger = max(0.0, self.hunger - dt * (100.0 / 600.0))
            if self.hunger <= 0.0:
                self.health = 0
                self.dead = True
                self.death_timer = 1.8
        speed_scale *= self.hunger_factor * self.skill_speed
        self.max_stamina = self.base_stamina * self.skill_stamina
        if self.stamina > self.max_stamina:
            self.stamina = self.max_stamina
        if self.dead:
            return

        dx = float(any(keys[k] for k in KEY_RIGHT)) - float(any(keys[k] for k in KEY_LEFT))
        dy = float(any(keys[k] for k in KEY_DOWN)) - float(any(keys[k] for k in KEY_UP))
        self.moving = bool(dx or dy)

        sprinting = (self.moving
                     and (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
                     and (self.god or (not self.exhausted and self.stamina > 0.0)))
        self.sprinting = sprinting

        if self.moving:
            length = math.hypot(dx, dy)
            dx, dy = dx / length, dy / length
            if sprinting and self.god:
                speed = self.speed * 10.0 * speed_scale
            else:
                speed = (self.sprint_speed if sprinting else self.speed) * speed_scale
            self.x += dx * speed * dt
            self.y += dy * speed * dt

        # 30 s of sprinting empties stamina; 20 s of rest refills it. Once
        # emptied, he is winded until it is completely full again.
        if sprinting and not self.god:
            self.stamina = max(0.0, self.stamina - dt)
            if self.stamina <= 0.0:
                self.exhausted = True
        elif not self.god and self.stamina < self.max_stamina:
            self.stamina = min(self.max_stamina, self.stamina + dt * 1.5)
            if self.exhausted and self.stamina >= self.max_stamina:
                self.exhausted = False

        # The mouse fully controls which way he is facing (his POV/orientation),
        # independently of which way he is walking.
        if aim is not None:
            length = math.hypot(aim[0], aim[1])
            if length > 1e-4:
                self.facing = (aim[0] / length, aim[1] / length)

    @property
    def facing_angle(self) -> float:
        return math.atan2(self.facing[1], self.facing[0])

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             held: str | None = None) -> None:
        sx = self.x - cam_x
        sy = self.y - cam_y
        fx, fy = self.facing

        screen.blit(self._shadow, (sx - 15, sy - 4))

        # small direction nub (visible even when holding a non-pointing item)
        tip = (sx + fx * 15, sy + fy * 15)
        left = (sx - fy * 4, sy + fx * 4)
        right = (sx + fy * 4, sy - fx * 4)
        pygame.draw.polygon(screen, (34, 30, 26), (tip, left, right))

        # torso
        body = (238, 228, 228) if self.hit_flash > 0.0 else (54, 74, 122)
        pygame.draw.circle(screen, body, (sx, sy), 11)
        pygame.draw.circle(screen, (30, 44, 74), (sx, sy), 11, 2)

        if held is not None:
            self._draw_held(screen, held, sx, sy, fx, fy, self.swing_progress)

        # head last so it sits on top
        _hx, _hy = sx + fx * 2, sy + fy * 2 - 2
        pygame.draw.circle(screen, (222, 178, 138), (_hx, _hy), 9)
        pygame.draw.circle(screen, (150, 108, 78), (_hx, _hy), 9, 1)
        # the same face as everybody else, on the bigger head
        face.draw(screen, _hx, _hy, 9, fx, fy,
                  face.mood_of(self.hurt_flash, self.attack_flash,
                               starved=self.hunger <= face.STARVED_SATIETY))

    @staticmethod
    def _draw_held(screen: pygame.Surface, item_id: str, sx: float, sy: float,
                   fx: float, fy: float, swing: float = 0.0) -> None:
        size, rotates, side = HOLD.get(item_id, (28, False, 9.0))
        icon = items.icon(item_id, size)

        px, py = -fy, fx                     # the character's right-hand side
        hx = sx + fx * 4.0 + px * side
        hy = sy + fy * 4.0 + py * side

        if rotates:
            degrees = -math.degrees(math.atan2(fy, fx))
            if item_id == "axe" and swing > 0.0:
                degrees += -70.0 + 140.0 * swing
            icon = pygame.transform.rotate(icon, degrees)
            hx += fx * 4.0                   # hold it out, grip near the hand
            hy += fy * 4.0

        screen.blit(icon, icon.get_rect(center=(hx, hy)))
