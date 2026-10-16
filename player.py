"""The player-controlled character, drawn as a simple top-down figure that
holds whatever inventory item is selected.
"""

from __future__ import annotations

import math

import pygame
import face
import effects
import terrain

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

# -- THE THIRD AXIS ---------------------------------------------------------
# A jump is a BOUNCE, not a parabola that stops dead at the bottom: he leaves
# the ground hard, and the landing throws him up again a little, twice. That
# is the whole of the "funny", and it is four numbers.
JUMP_V = 12.0             # metres a second he leaves the ground at
GRAVITY = 30.0            # metres a second, squared
BOUNCE_KEEP = 0.42        # how much of the fall the landing gives back
BOUNCE_FROM = 4.0         # ...but only off a fall faster than this
BOUNCE_MAX = 3            # and it dies out after three of them
STEP_GRACE = 0.35         # metres of a ledge he will still catch on the way up

SWING_COOLDOWN = 1.5
SWING_ANIM = 0.32


class Player:
    # A CLASS ATTRIBUTE, NOT A MODULE ONE. main() has a LOCAL called `player`
    # -- the Player instance -- which SHADOWS the `player` module for the whole
    # of main(). So `player.LEVEL_FLASH` reached the instance, and the module's
    # constant was unreachable from the only place that wanted it:

    #   AttributeError: 'Player' object has no attribute 'LEVEL_FLASH'

    # A class attribute answers to both spellings and cannot be shadowed.
    LEVEL_FLASH = 1.6              # how long the level-up shine lasts
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
        self.level_flash = 0.0
        # -- THE THIRD AXIS -------------------------------------------------
        self.z = 0.0                   # how high his feet are, in metres
        self.ground_z = 0              # the height of the ground beneath them
        self.jump_v = 0.0              # upward speed while he is off it
        self.airborne = False
        self.bounces = 0
        self.squash = 0.0              # landing squash, 1 -> 0
        self.elevation = None          # terrain.height_at, handed over by main
        self.swing_anim = 0.0
        self.skill_speed = 1.0         # movement skill multiplier
        self.skill_stamina = 1.0       # stamina-duration multiplier
        self.skill_axe_cd = SWING_COOLDOWN
        self.mags = {k: v for k, v in guns.MAG.items()}   # rounds per weapon
        self.reloading = 0.0
        self.reload_total = 0.0     # what it was set to, for the bar
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

    def jump(self) -> bool:
        """Off the ground, if he is on it."""
        if self.airborne or self.dead:
            return False
        self.jump_v = JUMP_V
        self.airborne = True
        self.bounces = 0
        return True

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
        if self.level_flash > 0.0:
            self.level_flash = max(0.0, self.level_flash - dt)
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
            length = speed * dt
            nx = self.x + dx * length
            ny = self.y + dy * length
            # ONE METRE UP, OR JUMP IT. Everything else is legal: any drop, any
            # distance along the level, one step at a time.
            if self.elevation is None or terrain.step_ok(self.ground_z, nx, ny,
                                                         self.airborne,
                                                         length):
                self.x, self.y = nx, ny
            else:
                # A WALL IS NOT A CORNER. Try each axis on its own, so he
                # slides along the face of it instead of sticking to it.
                if terrain.step_ok(self.ground_z, nx, self.y, self.airborne, length):
                    self.x = nx
                elif terrain.step_ok(self.ground_z, self.x, ny, self.airborne, length):
                    self.y = ny

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

        # -- THE THIRD AXIS -------------------------------------------------
        if self.elevation is not None:
            under = float(self.elevation(self.x, self.y))
            self.ground_z = int(under)
            if not self.airborne:
                self.z = under                    # his feet are on it
            else:
                # HE LANDS ON WHAT IS UNDER HIM WHEN HE GETS THERE, so a jump
                # onto a two-metre ledge works by walking over it in the air.
                self.z += self.jump_v * dt
                self.jump_v -= GRAVITY * dt
                if self.z <= under:
                    self.z = under
                    if self.jump_v < -BOUNCE_FROM and self.bounces < BOUNCE_MAX:
                        self.jump_v = -self.jump_v * BOUNCE_KEEP
                        self.bounces += 1
                    else:
                        self.jump_v = 0.0
                        self.airborne = False
                        self.bounces = 0
                    self.squash = 1.0             # and he squashes on landing
        if self.squash > 0.0:
            self.squash = max(0.0, self.squash - dt * 4.5)

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

        # SQUASH AND STRETCH, which is most of what makes a jump look funny.
        # He is long on the way up and down and flat for a moment on landing,
        # and the flat part is the one that reads: `squash` is 1.0 the instant
        # his feet touch and runs down to 0 over a fifth of a second.
        stretch = 0.0
        if self.airborne:
            stretch = max(-0.32, min(0.32, self.jump_v * 0.030))
        stretch -= self.squash * 0.38
        if stretch:
            rw = int(round(11 * (1.0 - stretch * 0.55)))
            rh = int(round(11 * (1.0 + stretch * 0.55)))
            # torso
            body = (238, 228, 228) if self.hit_flash > 0.0 else (54, 74, 122)
            rect = pygame.Rect(int(sx) - rw, int(sy) - rh, rw * 2, rh * 2)
            pygame.draw.ellipse(screen, body, rect)
            pygame.draw.ellipse(screen, (30, 44, 74), rect, 2)
        else:
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
        # THE WAITING BAR, just below him -- the swing, or the reload.
        #
        # THE SAME BAR FOR BOTH, because they are the same thing to look at: a
        # wait, and how much of it is left. The reload wins when there is one,
        # since a man cannot be mid-swing and mid-reload at once.
        if self.reloading > 0.0 and self.reload_total > 0.0:
            self._draw_action_bar(screen, sx, sy,
                                  1.0 - self.reloading / self.reload_total)
        elif (held == "axe" and self.swing_cd > 0.0
                and self.skill_axe_cd > 0.0):
            # ITS LENGTH IS THE WAIT ITSELF. skill_axe_cd comes from
            # skills.axe_cooldown(), which is 2.0 s at no skill and 0.1 s
            # mastered, so the better the axe the sooner the bar fills.
            self._draw_action_bar(screen, sx, sy,
                                  1.0 - self.swing_cd / self.skill_axe_cd)

        # AND THE SHINE, OVER HIM, while the level-up lasts.
        if self.level_flash > 0.0:
            effects.draw_level_up(screen, sx, sy,
                                  1.0 - self.level_flash / self.LEVEL_FLASH)

    @staticmethod
    def _draw_action_bar(screen: pygame.Surface, sx: float, sy: float,
                         prog: float) -> None:
        """The white bar under him: how far through a wait he is.

        Used for the axe's swing cooldown and for a rifle's reload, because to
        look at they are the same thing. prog runs 0 (just started) to 1 (done).
        """
        prog = max(0.0, min(1.0, prog))
        bw, bh = 26, 4
        bx = int(sx) - bw // 2
        by = int(sy) + 19
        pygame.draw.rect(screen, (16, 14, 12), (bx - 1, by - 1, bw + 2, bh + 2))
        pygame.draw.rect(screen, (56, 54, 50), (bx, by, bw, bh))
        fill = int(round(bw * prog))
        if fill > 0:
            pygame.draw.rect(screen, (246, 246, 242), (bx, by, fill, bh))

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
