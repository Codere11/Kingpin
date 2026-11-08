"""The player-controlled character, drawn as a simple top-down figure that
holds whatever inventory item is selected.
"""

from __future__ import annotations

import stats

import math

import pygame
import face
import effects

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


LUNGE_COST = 0.25          # a fourth of full stamina
LUNGE_SECONDS = 0.20       # how long the burst lasts
LUNGE_SPEED_MULT = 3.6     # times his walking speed while it lasts
LUNGE_COOLDOWN = 0.35      # so a lunge cannot be spammed


class Player:
    # THE GATE. `searched_village` is the last township that has had its hands
    # in his pack; `search_progress` is the ten seconds it takes; `search_village`
    # is whose gate he is standing at. Class defaults, because a player restored
    # from a save is never re-__init__'d.
    searched_village: object = None
    search_village: object = None
    search_progress: float = 0.0
    # THE GATE. Every one of these is read before it is ever written, so every
    # one of them must exist on the class -- a player restored from a save is
    # never __init__'d again.
    gate_guard: object = None
    waved_by: object = None        # the town that has already waved him through       # the soldier who has come over to search him
    passed_guard: object = None     # the one who has already waved him through
    aggro_village: object = None    # the town that has turned on him
    was_inside_v: object = None     # which town's fence he was inside last frame
    search_guard: object = None
    wanted: bool = False
    # A CLASS ATTRIBUTE, NOT A MODULE ONE. main() has a LOCAL called `player`
    # -- the Player instance -- which SHADOWS the `player` module for the whole
    # of main(). So `player.LEVEL_FLASH` reached the instance, and the module's
    # constant was unreachable from the only place that wanted it:

    #   AttributeError: 'Player' object has no attribute 'LEVEL_FLASH'

    # A class attribute answers to both spellings and cannot be shadowed.
    LEVEL_FLASH = 1.6              # how long the level-up shine lasts
    # WHO HE IS AND WHAT HE OWES. Class defaults as well as instance fields:
    # an unpickled save written before they existed never runs __init__.
    origin = "idle"
    debt = 0
    debt_paid = 0
    farm_plot = None        # his OWN field, by index into his town's list
    smuggling = 0.0
    social = 0.0
    # WHAT HE HAS BUILT AND WHOM HE PAYS. Class defaults: a player restored
    # from a save never runs __init__, and every one of these is read before
    # it is written (work.slots, work.payroll, the plot and station lists).
    workplaces: Any = None
    workers: Any = None
    plots: Any = None
    _payroll_day: Any = -1
    work_post: Any = None          # where his hired men walk to
    yard_plots: Any = None         # the rects of the land he has staked
    hub_stall: Any = None          # the counter in his hub, for the dialogue
    town_price_for: Any = None     # what a cart could resell a lot for            # his ceiling is 10 -- the only man who can reach it         # 0 to 10. What the state does not find is what
                            # teaches a man how to carry it.
    def __init__(self, x: float, y: float, speed: float = 240.0) -> None:
        self.x = x
        self.y = y
        self.speed = speed
        self.facing = (0.0, 1.0)
        self.moving = False
        # THE SAME BODY AS THE MAN IN THE RANKS. creatures.Soldier has 115;
        # the player had 100, so he was both the strongest blow in the world
        # and the frailest body that threw one. One standard, applied.
        self.max_health = stats.PLAYER_MAX_HEALTH
        self.health = 100
        self.heal_rate = 1.5           # hp/s while well fed (hunger = satiety)
        self.radius = 12
        self.hit_flash = 0.0
        self.dead = False
        self.death_timer = 0.0
        self.bleed = 0.0
        self.sprint_speed = speed * 1.7
        # SPACE: A BURST OF SPEED FOR A QUARTER OF THE WIND.
        self.lunge_t = 0.0             # seconds of burst left
        self.lunge_dir = (1.0, 0.0)
        self.lunge_cd = 0.0
        self.max_stamina = 30.0        # seconds of sprinting (base)
        self.base_stamina = 30.0
        self.stamina = 30.0
        self.exhausted = False
        self.sprinting = False
        self.swing_cd = 0.0
        self.attack_flash = 0.0
        self.hurt_flash = 0.0
        self.level_flash = 0.0
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
        self.tranq_health = 160.0     # drained ONLY by militia darts
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

    sleep_t: float = 0.0          # a dart put him down
    shackled: bool = False        # held in a cell

    TRANQ_HEALTH = 160.0          # the hidden bar a dart drains

    def tranq(self, seconds: float = 25.0) -> None:
        """A DART IN THE PLAYER: he goes down, he does not die. The dart never
        touched his health -- it emptied the hidden tranquiliser bar."""
        self.sleep_t = float(seconds)
        self.moving = False
        self.tranq_health = self.TRANQ_HEALTH
        try:
            import plog
            plog.log("TRANQ", "the player is asleep")
        except Exception:
            pass

    def take_damage(self, amount: int) -> None:
        # A TRANQUILISED MAN IS NOT SHOT AGAIN. Once the dart is in him he is
        # being carried off; a second round does not undo that -- and it must
        # not game-over him out from under the militia's arms.
        if self.dead or self.god or getattr(self, "sleep_t", 0.0) > 0.0:
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
        # HIS BODY GROWS WITH HIS SKILL, the same rule as every other man.
        stats.apply_body(self)
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

        # THE LUNGE ITSELF: a hard shove on top of the walk, for a fifth of a
        # second. It goes through the same collision pass as every step.
        self.lunge_cd = max(0.0, self.lunge_cd - dt)
        if self.lunge_t > 0.0:
            self.lunge_t = max(0.0, self.lunge_t - dt)
            _boost = self.speed * LUNGE_SPEED_MULT * speed_scale
            self.x += self.lunge_dir[0] * _boost * dt
            self.y += self.lunge_dir[1] * _boost * dt

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

    def lunge(self, keys) -> bool:
        """SPACE -- A QUARTER OF THE WIND FOR ONE BURST.

        He throws himself the way he is HOLDING (WASD), or the way he is
        LOOKING if no direction key is down. It costs a fourth of full
        stamina, and a man with less than that in him does not go -- which is
        the whole trade: the lunge is a move you cannot make twice.
        """
        if self.dead or self.lunge_cd > 0.0:
            return False
        cost = self.max_stamina * LUNGE_COST
        if not self.god and self.stamina < cost:
            return False
        dx = (float(any(keys[k] for k in KEY_RIGHT))
              - float(any(keys[k] for k in KEY_LEFT)))
        dy = (float(any(keys[k] for k in KEY_DOWN))
              - float(any(keys[k] for k in KEY_UP)))
        if dx or dy:
            n = math.hypot(dx, dy)
            self.lunge_dir = (dx / n, dy / n)
        else:
            self.lunge_dir = (float(self.facing[0]), float(self.facing[1]))
        if not self.god:
            self.stamina = max(0.0, self.stamina - cost)
            if self.stamina <= 0.0:
                self.exhausted = True
        self.lunge_t = LUNGE_SECONDS
        self.lunge_cd = LUNGE_COOLDOWN
        return True

    @property
    def facing_angle(self) -> float:
        return math.atan2(self.facing[1], self.facing[0])

    _zzz_font = None

    def _draw_zzz(self, screen, sx, sy) -> None:
        if Player._zzz_font is None:
            Player._zzz_font = pygame.font.SysFont("dejavusans", 13, bold=True)
        for i, (dx, dy, size) in enumerate(((-14, -30, 10), (0, -40, 13), (14, -32, 9))):
            lab = Player._zzz_font.render("z", True, (226, 236, 244))
            lab = pygame.transform.scale(lab, (size, size))
            screen.blit(lab, (sx + dx - size // 2, sy + dy - size // 2))

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

        # torso -- a native hide tunic, like every other civilian
        body = (238, 228, 228) if self.hit_flash > 0.0 else (162, 120, 76)
        pygame.draw.circle(screen, body, (sx, sy), 11)
        pygame.draw.circle(screen, (108, 78, 48), (sx, sy), 11, 2)

        if held is not None:
            self._draw_held(screen, held, sx, sy, fx, fy, self.swing_progress)

        # head last so it sits on top
        _hx, _hy = sx + fx * 2, sy + fy * 2 - 2
        face.hair(screen, _hx, _hy, 9)
        pygame.draw.circle(screen, (222, 178, 138), (_hx, _hy), 9)
        pygame.draw.circle(screen, (150, 108, 78), (_hx, _hy), 9, 1)
        # THE DART HAS HIM: he lies there with the sleep rising off him.
        if getattr(self, "sleep_t", 0.0) > 0.0:
            self._draw_zzz(screen, sx, sy)
        # the same face as everybody else, on the bigger head
        _mood = ("sleep" if getattr(self, "sleep_t", 0.0) > 0.0
                 else face.mood_of(self.hurt_flash, self.attack_flash,
                                   starved=self.hunger <= face.STARVED_SATIETY))
        face.draw(screen, _hx, _hy, 9, fx, fy, _mood)
        face.feather(screen, _hx, _hy, 9, fx, fy)
        # THE WAITING BAR, just below him -- the swing, or the reload.
        #
        # THE SAME BAR FOR BOTH, because they are the same thing to look at: a
        # wait, and how much of it is left. The reload wins when there is one,
        # since a man cannot be mid-swing and mid-reload at once.
        if self.reloading > 0.0 and self.reload_total > 0.0:
            self._draw_action_bar(screen, sx, sy,
                                  1.0 - self.reloading / self.reload_total)
        elif (self.swing_cd > 0.0 and self.skill_axe_cd > 0.0):
            # THE SAME WAIT FOR A FIST AS FOR AN AXE. The bar is the swing
            # cooldown, whatever he swung with: skill_axe_cd comes from
            # skills.axe_cooldown(), 2.0 s at no skill and 0.1 s mastered,
            # so the better the axe the sooner the bar fills.
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
