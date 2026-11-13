"""Nation soldiers, wolves and rabbits.

Soldiers and wolves reuse Enemy's perception/patrol plumbing but pick their own
targets (handled by main). Wolves smell you twice as far as a person and bite
for half a person's melee. Rabbits are harmless, fast, and skittish.
"""

from __future__ import annotations

import stats

import math
import random

import pygame
import face

from enemy import AWARE_MEMORY, VIEW_RANGE, Enemy
from combat import friendly_in_line
from fence import perimeter_point
import economy
import guns
import nations
import skills
import steering

SOLDIER_VIEW = 430.0
SOLDIER_ANGLE = math.radians(115.0)
WOLF_VIEW = VIEW_RANGE * 2.0          # smells you twice as far as a human
WOLF_ANGLE = math.radians(210.0)
# THE WORLD'S POWER LEVEL. The player hit for 33 and now hits for a soldier's
# 16, so every beast is scaled by the same factor -- PROPORTIONALLY WEAKER, to
# the letter. It is not a nerf to the beasts and not a buff: the fight between
# a man and a wolf is exactly the difficulty it always was, and it now happens
# at a level where a blow is a blow.
#
# The arithmetic, because it is the whole point. A wolf has WOLF_HP and the
# player does 33: 1.58 blows, and at 5 a bite that is 7.9 damage taken. At 16
# he needs 3.25 blows, so the wolf lands 2.06x as many bites; at 5 a bite that
# would be 10.3. Scaling the bite by 16/33 = 0.485 puts it back to 7.9, exactly.
#
# He was "half a person's melee (10)" -- a villager's, who is unchanged, so he
# is now a fifth of one. The number moved; the relationship did not.
BEAST_SCALE = 16.0 / 33.0
WOLF_BITE = 5 * BEAST_SCALE           # was 5, and was half a villager's 10
WOLF_SPEED = 168.0
WOLF_HP = 52

# A MAXIMUM-SKILLED PLAYER AT FULL SPRINT -- 240 * 1.7 * 1.5. Wild bisons and
# horses run from you at exactly this speed, and ONLY when they are running.
SPRINTER_MAX = 240.0 * 1.7 * 1.5

# GRAZING ANIMALS SHARE A PLANT: every horse and bison within this radius of
# the bite gets an equal amount of it, stored for later.
SHARE_RADIUS = 300.0

# -- the pecking order --------------------------------------------------------
# Six wolves in ten are weaklings, three are a fair fight, and one in ten is a
# nightmare. WHICH wolves those are is reshuffled every period, and it is keyed
# to where the beast was spawned -- so the same animal is a runt at dawn, a
# monster by afternoon, and a runt again tomorrow, while the nightmare moves to
# the other side of the map. Purely deterministic, so it is repeatable.
WOLF_TIER_PERIOD = 240.0
# name, health, bite, speed, lunge -- the lunge is doubled for a fair wolf and
# tripled for a beast: it is the moment a careful dance goes wrong.
WOLF_TIERS = (
    ("weak",  1.00, 1.0, 1.00, 1.0),
    ("equal", 1.35, 1.8, 1.20, 2.0),
    ("beast", 2.20, 3.0, 1.60, 3.0),
)
_NOW = 0.0


def set_time(t: float) -> None:
    global _NOW
    _NOW = t


def wolf_tier(spawn, now: float):
    """60% weakling, 30% equal, 10% beast -- reshuffled each period."""
    epoch = int(now / WOLF_TIER_PERIOD)
    h = (int(spawn[0]) * 73856093) ^ (int(spawn[1]) * 19349663) ^ (epoch * 2654435761)
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    roll = h % 100
    if roll < 10:
        return WOLF_TIERS[2]
    if roll < 40:
        return WOLF_TIERS[1]
    return WOLF_TIERS[0]




class Soldier(Enemy):
    name: str = "a soldier"      # guards are named by the gate they hold
    # The war face's timer. A CLASS default, because a soldier who has never
    # swung a blow must not be missing the attribute the draw reads.
    attack_flash: float = 0.0

    kind = "soldier"
    is_militia = False        # the Narodna militsiya: blue cap, dart rifle
    mood: float = 50.0        # a soldier has a mood too, for mind.apply_mood

    def __init__(self, x: float, y: float, nation, melee: bool = False,
                 seed: int | None = None, color=None) -> None:
        super().__init__(x, y)
        rng = random.Random(seed) if seed is not None else random
        self.nation = nation
        self.team = ("nation", nation)
        # ONE uniform to a nation. A soldier is dressed by whose army he is
        # in and nothing else -- no random colours, so a column on the map, a
        # column in the field and the banner on the map all agree at a glance.
        self.color = color if color is not None else nations.color(nation)
        self.melee = melee
        self.ammo = 0                     # rounds he is carrying
        self.max_health = stats.PLAYER_MAX_HEALTH
        self.health = self.max_health
        self.mood = 50.0        # the same mood a villager has
        self.view_range = SOLDIER_VIEW
        self.view_angle = SOLDIER_ANGLE
        self.speed = 138.0 if melee else 122.0
        self.preferred = 46.0 if melee else 300.0
        self.melee_damage = 16
        self.skills = skills.Skills()
        # STAMINA. A full tank is roughly four seconds of running: enough to
        # close on a position or break off, not enough to do both. Blow it and
        # a man is winded in front of the enemy -- slower, slower to steady a
        # rifle, slower to swing. That is what gives a charge a range.
        self.max_stamina = 100.0 * self.skills.stamina_scale()
        self.stamina = self.max_stamina
        self.exhausted = False
        self._last_xy = None
        self.base_speed = self.speed
        self.patrol_speed = 60.0
        self.weapon = "axe" if melee else "rifle"
        if self.weapon == "rifle" and rng.random() < 0.25:
            self.gun_kind = guns.SHOTGUN
            self.mag = guns.MAG[guns.SHOTGUN]
        self.march_target = None
        self.guard_loop = None          # rectangle they walk around
        self.guard_phase = 0.0
        self.guard_village = None
        self.hostile = False           # set when the village is provoked
        self.patrol_center = None        # territory patrol: (x, y) or None
        self.patrol_r = 0.0
        self.patrol_phase = 0.0
        self.patrol_village = None

    def wind_scale(self) -> float:
        """Winded men do everything at six tenths."""
        return 0.6 if self.exhausted else 1.0

    def _exert(self, step: float, dt: float) -> None:
        """Charge for it. Walking is free; running is not."""
        if dt <= 0.0:
            return
        scale = self.skills.stamina_scale()
        self.max_stamina = 100.0 * scale
        speed = step / dt
        if speed > self.base_speed * 0.95:            # running, not walking
            self.stamina -= 32.0 * (speed / self.base_speed) * dt
        else:
            self.stamina += 15.0 * scale * dt
        self.stamina = max(0.0, min(self.max_stamina, self.stamina))
        self.exhausted = self.stamina <= 0.0

    def update(self, dt, target, combat, occluders=None, speed_scale=1.0,
               view_scale=1.0, visible=True, colliders=None):
        # CARRYING A SLEEPER: straight to the cell, put him down, back to duty.
        if getattr(self, "carry_victim", None) is not None:
            _v = self.carry_victim
            _cell = self.carry_cell
            if _cell is None or not getattr(_v, "alive", True):
                self.carry_victim = None
                self.carry_cell = None
            else:
                _dx = _cell.x - self.x
                _dy = _cell.y - self.y
                _d = math.hypot(_dx, _dy) or 1.0
                self.facing = (_dx / _d, _dy / _d)
                _step = self.speed * 1.4 * dt
                self.x += _dx / _d * _step
                self.y += _dy / _d * _step
                if _d < 30.0:
                    try:
                        import detain
                        detain.deposit(_v, _cell)
                    except Exception:
                        pass
                    self.carry_victim = None
                    self.carry_cell = None
                    # back to his post
                    _gp = getattr(self, "gate_post", None)
                    if _gp is not None:
                        self.target = _gp
                        self.home = _gp
            return
        if getattr(self, "sleep_t", 0.0) > 0.0:
            self.sleep_t = max(0.0, self.sleep_t - dt)
            return
        self._colliders = colliders or []
        if getattr(self, "_questioning", False):
            # question.py is walking him toward the man he caught consuming;
            # the guard's own watch waits until the question has been put.
            return
        stats.apply_body(self)                        # skill makes him bigger
        if self.attack_flash > 0.0:                   # the war face runs down
            self.attack_flash = max(0.0, self.attack_flash - dt)
        if self.hurt_flash > 0.0:                     # ...and so does the hurt
            self.hurt_flash = max(0.0, self.hurt_flash - dt)
        if self._last_xy is not None:                 # what did last frame cost?
            self._exert(math.hypot(self.x - self._last_xy[0],
                                   self.y - self._last_xy[1]), dt)
        self._last_xy = (self.x, self.y)
        if self.guard_loop is not None:
            self._guard_update(dt, target, combat, occluders, view_scale, visible)
            return
        if self.patrol_center is not None:
            self._patrol_update(dt, target, combat, occluders, view_scale, visible)
            return
        if getattr(self, "march_target", None) is not None:
            # Two armies in one field is a battle, not a parade. If the enemy
            # in front of me is a soldier, the march stops here and we have it
            # out; the orders stand, so the column resumes the moment the
            # field is clear. Anything else is return fire on the move.
            if (target is not None and getattr(target, "kind", None) == "soldier"
                    and target.alive and visible
                    and self._can_see(target, occluders, view_scale)):
                self.aware = True
                self.aware_timer = AWARE_MEMORY
                super().update(dt, target, combat, occluders, speed_scale,
                               view_scale, visible, colliders)
                return
            if self.hit_flash > 0.0:
                self.hit_flash = max(0.0, self.hit_flash - dt)
            if self.bleed > 0.0:
                self.bleed = max(0.0, self.bleed - dt)
            self._tick_gun(dt)
            if (target is not None and visible
                    and not getattr(target, "dead", False)
                    and self._can_see(target, occluders, view_scale)):
                self.aware = True
                self.aware_timer = AWARE_MEMORY
            if target is not None and self.aware:
                self._fire_while_marching(dt, target, combat)
            return
        super().update(dt, target, combat, occluders, speed_scale, view_scale,
                       visible, colliders)

    def _guard_update(self, dt, target, combat, occluders, view_scale, visible):
        """A border guard has exactly two states, and never wanders:

        ENGAGE  -- an enemy is in his line of sight: face it and shoot it.
        PATROL  -- nothing in sight (or it died): walk the fence line, eyes
                   square to the fence.  Switching is instant and total.
        """
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if self.bleed > 0.0:
            self.bleed = max(0.0, self.bleed - dt)
        self._tick_gun(dt)
        if not self.alive:
            return
        in_sight = (target is not None and visible
                    and not getattr(target, "dead", False)
                    and self._can_see(target, occluders, view_scale))
        if in_sight:
            self.view_angle = SOLDIER_ANGLE
            dx, dy = target.x - self.x, target.y - self.y
            distance = math.hypot(dx, dy) or 1.0
            ux, uy = dx / distance, dy / distance
            self.facing = (ux, uy)
            self.fire_cd -= dt
            _n = guns.rounds_now(self, dt,
                                 self.fire_cd <= 0.0 and distance <= 520.0)
            if _n and self.fire_cd <= 0.0:
                self.fire_cd = random.uniform(0.5, 0.9)
            for _ in range(_n):
                if not self._round_ready():
                    break
                angle = math.atan2(dy, dx) + random.uniform(-0.03, 0.03)
                self._shoot(combat, self.x + ux * 20.0, self.y + uy * 20.0,
                            angle, distance + 160.0, 80, 80)
        else:
            self.view_angle = math.radians(90.0)    # eyes on the fence
            self._walk_loop(dt)

    def _patrol_update(self, dt, target, combat, occluders, view_scale, visible):
        """A territory patrol: walk the village's political border; engage
        anything hostile that comes into sight, then carry on."""
        # A soldier does not shoot people: a brawl is fists, not bullets.
        if (not getattr(self, "is_militia", False)
                and target is not None
                and getattr(target, "kind", "") not in ("soldier", "wolf", "rabbit")):
            self._fight(dt, target, combat, 1.0, visible)
            return
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if self.bleed > 0.0:
            self.bleed = max(0.0, self.bleed - dt)
        self._tick_gun(dt)
        if not self.alive:
            return
        in_sight = (target is not None and visible
                    and not getattr(target, "dead", False)
                    and self._can_see(target, occluders, view_scale))
        if in_sight:
            self.view_angle = SOLDIER_ANGLE
            dx, dy = target.x - self.x, target.y - self.y
            distance = math.hypot(dx, dy) or 1.0
            ux, uy = dx / distance, dy / distance
            self.facing = (ux, uy)
            self.fire_cd -= dt
            _n = guns.rounds_now(self, dt,
                                 self.fire_cd <= 0.0 and distance <= 560.0)
            if _n and self.fire_cd <= 0.0:
                self.fire_cd = random.uniform(0.45, 0.8)
            for _ in range(_n):
                if not self._round_ready():
                    break
                angle = math.atan2(dy, dx) + random.uniform(-0.035, 0.035)
                self._shoot(combat, self.x + ux * 20.0, self.y + uy * 20.0,
                            angle, distance + 160.0, 80, 80)
        else:
            self.view_angle = math.radians(150.0)
            self._walk_circle(dt)

    def _walk_circle(self, dt):
        """Walk the border of the village's territory, looking outward."""
        cx, cy = self.patrol_center
        r = self.patrol_r or 1.0
        length = 2.0 * math.pi * r
        self.patrol_phase = (self.patrol_phase + self.patrol_speed * dt / length) % 1.0
        a = self.patrol_phase * 2.0 * math.pi
        tx = cx + math.cos(a) * r
        ty = cy + math.sin(a) * r
        ddx, ddy = tx - self.x, ty - self.y
        dist = math.hypot(ddx, ddy)
        step = self.patrol_speed * dt
        if dist > step:
            self.x += ddx / dist * step
            self.y += ddy / dist * step
        else:
            self.x, self.y = tx, ty
        nx, ny = self.x - cx, self.y - cy
        nd = math.hypot(nx, ny) or 1.0
        self.facing = (nx / nd, ny / nd)      # eyes out, at the frontier

    def _walk_loop(self, dt):
        """Walk the inner border of the fence, round and round, always
        looking 90 degrees off the direction of travel (out at the fence)."""
        rect = self.guard_loop
        L = 2.0 * (rect.w + rect.h) or 1.0
        self.guard_phase = (self.guard_phase + self.patrol_speed * dt / L) % 1.0
        tx, ty, nx, ny = perimeter_point(rect, self.guard_phase)
        ddx, ddy = tx - self.x, ty - self.y
        dist = math.hypot(ddx, ddy)
        step = self.patrol_speed * dt
        if dist > step:
            self.x += ddx / dist * step
            self.y += ddy / dist * step
        else:
            self.x, self.y = tx, ty
        if dist > 48.0:                     # walking back onto the line
            self.facing = (ddx / dist, ddy / dist)
        else:
            self.facing = (nx, ny)          # on watch: square to the fence

    def _fire_while_marching(self, dt, target, combat):
        # A soldier does not shoot people: a brawl is fists, not bullets.
        if (not getattr(self, "is_militia", False)
                and target is not None
                and getattr(target, "kind", "") not in ("soldier", "wolf", "rabbit")):
            self._fight(dt, target, combat, 1.0, True)
            return
        self.fire_cd -= dt
        dx, dy = target.x - self.x, target.y - self.y
        dist = math.hypot(dx, dy) or 1.0
        _n = guns.rounds_now(self, dt, self.fire_cd <= 0.0 and dist <= 560.0)
        for _ in range(_n):
            ux, uy = dx / dist, dy / dist
            angle = math.atan2(dy, dx) + random.uniform(-0.035, 0.035)
            mx, my = self.x + ux * 20.0, self.y + uy * 20.0
            ex = mx + math.cos(angle) * (dist + 160.0)
            ey = my + math.sin(angle) * (dist + 160.0)
            if not self.melee:                 # a rifleman needs his rounds
                if getattr(self, "ammo", 0) <= 0:
                    return
                self.ammo -= 1
            if not friendly_in_line(mx, my, ex, ey, self, self.team,
                                    getattr(self, "_soldiers", ()),
                                    getattr(self, "_player", None), self.nation):
                if self._round_ready():
                    if _n and self.fire_cd <= 0.0:
                        self.fire_cd = random.uniform(0.55, 0.95) * (
                            1.8 if self.exhausted else 1.0)
                    self.attack_flash = face.WAR_SECONDS
                    self._shoot(combat, mx, my, angle, dist + 160.0, 80, 80)

    def _fight(self, dt, target, combat, speed_scale, visible=True):
        dx, dy = target.x - self.x, target.y - self.y
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = steering.steer(self, target.x, target.y,
                                getattr(self, "_rects", ()),
                                getattr(self, "_fences", ()))
        self.facing = (ux, uy)
        speed = self.speed * speed_scale * self.skills.move_scale()

        # A SOLDIER DOES NOT SHOOT PEOPLE. His rifle is for enemy soldiers and
        # wolves; against a civilian -- or the player -- he closes and swings
        # his fists. The militia is exempt: it darts, it does not punch.
        if (not getattr(self, "is_militia", False)
                and not self.melee
                and getattr(target, "kind", "") not in ("soldier", "wolf", "rabbit")):
            self.x += ux * speed * 1.3 * dt
            self.y += uy * speed * 1.3 * dt
            self.fire_cd -= dt
            if distance <= 34.0 and self.fire_cd <= 0.0:
                self.fire_cd = max(0.35, self.skills.axe_cooldown()) * (
                    1.6 if self.exhausted else 1.0)
                self.attack_flash = face.WAR_SECONDS
                self.skills.gain_axe()
                if hasattr(target, "take_damage"):
                    _base = self.melee_damage / skills.UNARMED_WEAKNESS
                    target.take_damage(max(1, round(
                        _base * self.skills.axe_damage_scale())))
            return

        if self.melee:
            self.x += ux * speed * 1.3 * dt
            self.y += uy * speed * 1.3 * dt
            self.fire_cd -= dt
            if distance <= 34.0 and self.fire_cd <= 0.0:
                # Swings come faster as the axe is learned (2.0 s down to
                # 0.1 s on paper) -- floored at 0.35 s, because a man swinging
                # sixteen damage ten times a second is not a soldier, he is a
                # blender.
                self.fire_cd = max(0.35, self.skills.axe_cooldown()) * (
                    1.6 if self.exhausted else 1.0)
                self.attack_flash = face.WAR_SECONDS
                self.skills.gain_axe()
                if hasattr(target, "take_damage"):
                    # An axeman swings an axe; anybody else swings a fist.
                    _base = (self.melee_damage if self.weapon == "axe"
                             else self.melee_damage / skills.UNARMED_WEAKNESS)
                    if target.take_damage(max(1, round(
                            _base * self.skills.axe_damage_scale()))):
                        economy.loot_body(self, target)     # his kit is mine
            return

        if distance < self.preferred - 70.0:
            self.x -= ux * speed * dt
            self.y -= uy * speed * dt
        elif distance > self.preferred + 70.0:
            self.x += ux * speed * 1.6 * dt
            self.y += uy * speed * 1.6 * dt
        else:
            self.strafe_timer -= dt
            if self.strafe_timer <= 0.0:
                self.strafe *= -1.0
                self.strafe_timer = random.uniform(1.0, 2.5)
            self.x += -uy * self.strafe * speed * 0.6 * dt
            self.y += ux * self.strafe * speed * 0.6 * dt

        self.fire_cd -= dt
        if self.fire_cd <= 0.0 and distance <= 540.0 and visible:
            angle = math.atan2(dy, dx) + random.uniform(-0.035, 0.035)
            mx, my = self.x + ux * 20.0, self.y + uy * 20.0
            ex = mx + math.cos(angle) * (distance + 160.0)
            ey = my + math.sin(angle) * (distance + 160.0)
            if not self.melee:                 # a rifleman needs his rounds
                if getattr(self, "ammo", 0) <= 0:
                    return
                self.ammo -= 1
            if not friendly_in_line(mx, my, ex, ey, self, self.team,
                                    getattr(self, "_soldiers", ()),
                                    getattr(self, "_player", None), self.nation):
                self.fire_cd = random.uniform(0.55, 0.95) * (
                    1.8 if self.exhausted else 1.0)
                # MARKSWOMANSHIP. Ten degrees of wobble for a green levy,
                # dead-on for a veteran, and every shot makes him better. This
                # is what turns a campaign into hardened troops.
                self.skills.gain_shooting()
                # THE SAME ROUND THE PLAYER FIRES, fired through the one place.
                guns.enemy_fire(combat, self, mx, my, angle,
                                distance + 160.0,
                                spread=self.skills.shot_spread())

    def draw(self, screen, cam_x, cam_y):
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        pygame.draw.ellipse(screen, (20, 16, 14), (sx - 12, sy - 4, 24, 10))
        pygame.draw.line(screen, (40, 40, 46), (sx, sy), (sx + fx * 22, sy + fy * 22), 4)
        body = (244, 226, 226) if self.hit_flash > 0.0 else self.color
        pygame.draw.circle(screen, body, (int(sx), int(sy)), 11)
        pygame.draw.circle(screen, (28, 30, 34), (int(sx), int(sy)), 11, 2)
        # A SOLDIER IS A MAN AND WEARS THE SAME FACE AS EVERYBODY ELSE. The
        # patrols were the one body of people drawn on their own path, so they
        # were the one body of people with no face at all.
        _hx, _hy = sx + fx * 2, sy + fy * 2 - 2
        face.hair(screen, _hx, _hy, 8)          # long hair behind the head
        pygame.draw.circle(screen, (214, 172, 132), (int(_hx), int(_hy)), 8)
        pygame.draw.circle(screen, (140, 104, 76), (int(_hx), int(_hy)), 8, 1)
        face.draw(screen, _hx, _hy, 8, fx, fy,
                  face.mood_of(self.hurt_flash, self.attack_flash,
                               starved=getattr(self, "hunger", 0.0)
                               >= face.STARVED_HUNGER),
                  vet=face.vet_tier(self.skills.axe, self.skills.shooting))
        face.feather(screen, _hx, _hy, 8, fx, fy)
        # WAR PAINT ACROSS THE EYES: every soldier wears it.
        if getattr(self, "kind", "") == "soldier":
            face.war_paint(screen, _hx, _hy, 8, fx, fy)
        if getattr(self, "sleep_t", 0.0) > 0.0:
            try:
                fnt = pygame.font.SysFont("dejavusans", 12, bold=True)
                z = fnt.render("Zzz", True, (226, 226, 236))
                screen.blit(z, (_hx + 6, _hy - 20))
            except Exception:
                pass
        # Nation pennant, so the armies are never mistaken for each other.
        pygame.draw.line(screen, (44, 38, 30), (sx + 7, sy - 6), (sx + 7, sy - 30), 2)
        pygame.draw.polygon(screen, self.color,
                            [(sx + 7, sy - 30), (sx + 21, sy - 26), (sx + 7, sy - 22)])
        pygame.draw.polygon(screen, (26, 22, 18),
                            [(sx + 7, sy - 30), (sx + 21, sy - 26), (sx + 7, sy - 22)], 1)
        if getattr(self, "friendly", False):       # your nation: teal ring
            pygame.draw.circle(screen, (110, 226, 226), (int(sx), int(sy)), 15, 2)
        if getattr(self, "follow", False):        # your squad: gold chevron
            pygame.draw.polygon(screen, (250, 220, 90),
                                [(sx, sy - 18), (sx - 6, sy - 28), (sx + 6, sy - 28)])
            pygame.draw.polygon(screen, (120, 90, 20),
                                [(sx, sy - 18), (sx - 6, sy - 28), (sx + 6, sy - 28)], 1)


class Wolf(Enemy):
    kind = "wolf"

    def __init__(self, x: float, y: float, species: str = "wolf") -> None:
        super().__init__(x, y)
        self.species = species
        self.team = ("wolves", None)
        self.spawn = (round(x), round(y))     # his identity, and his station
        self.tier = "weak"
        self._tier_epoch = None
        self.max_health = WOLF_HP
        self.health = WOLF_HP
        self.radius = 11
        self.view_range = WOLF_VIEW
        self.view_angle = WOLF_ANGLE
        self.speed = WOLF_SPEED
        self.preferred = 32.0
        self.patrol_speed = 72.0
        self.melee_damage = WOLF_BITE
        self.hit_flash = 0.0
        # The lunge: every few seconds the beast throws itself at a man. It is
        # the one moment in a careful dance when teeth can find flesh.
        self.lunge_cd = random.uniform(2.0, 4.0)
        self.lunging = 0.0
        self._apply_tier()          # last, so nothing overwrites the station

    def _apply_tier(self) -> None:
        """Re-check the pecking order; only does work when the period turns."""
        epoch = int(_NOW / WOLF_TIER_PERIOD)
        if epoch == self._tier_epoch:
            return
        self._tier_epoch = epoch
        name, hp, dmg, spd, lunge = wolf_tier(self.spawn, _NOW)
        self.tier = name
        self.max_health = int(round(WOLF_HP * hp))
        self.health = self.max_health             # a different beast entirely
        # NOT rounded to a whole number: WOLF_BITE is fractional now (2.42),
        # and int(round(...)) would throw a fifth of a tier-1 wolf's damage
        # away and make the weakest tier weaker than the scale intends. The
        # blow itself is rounded once, where it lands (see Wolf._fight).
        self.melee_damage = max(1.0, WOLF_BITE * dmg)
        self.speed = WOLF_SPEED * spd
        self.lunge_scale = lunge
        self.radius = 11 + (4 if name == "beast" else 0)

    def _fight(self, dt, target, combat, speed_scale, visible=True):
        self._apply_tier()
        dx, dy = target.x - self.x, target.y - self.y
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = steering.steer(self, target.x, target.y,
                                getattr(self, "_rects", ()),
                                getattr(self, "_fences", ()))
        self.facing = (ux, uy)
        self.fire_cd -= dt
        if self.lunging > 0.0:
            self.lunging = max(0.0, self.lunging - dt)
        else:
            self.lunge_cd -= dt
            if self.lunge_cd <= 0.0 and 34.0 < distance < 150.0:
                self.lunging = 0.45 * self.lunge_scale   # throw himself at the man
                self.lunge_cd = random.uniform(2.5, 5.5)
        lunging = self.lunging > 0.0
        speed = self.speed * speed_scale * (
            (1.9 + 0.25 * (self.lunge_scale - 1.0)) if lunging else 1.0)
        self.x += ux * speed * dt
        self.y += uy * speed * dt
        reach = 30.0 + (6.0 * self.lunge_scale if lunging else 0.0)
        if distance <= reach and self.fire_cd <= 0.0:
            self.fire_cd = 1.0
            if hasattr(target, "take_damage"):
                hit = self.melee_damage * (self.lunge_scale if lunging else 1.0)
                target.take_damage(max(1, int(round(hit))))

    def draw(self, screen, cam_x, cam_y):
        if self.species == "snake":
            self._draw_snake(screen, cam_x, cam_y)
            return
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        if self.species == "white_wolf":
            body, line, ear, eye = (230, 233, 238), (168, 174, 184), (150, 158, 172), (90, 120, 150)
        elif self.species == "hyena":
            body, line, ear, eye = (156, 128, 84), (98, 78, 52), (110, 86, 56), (40, 32, 24)
        else:
            body, line, ear, eye = (96, 96, 104), (58, 58, 66), (58, 58, 66), (222, 196, 120)
        pygame.draw.ellipse(screen, (18, 16, 14), (sx - 12, sy - 4, 24, 10))
        body_c = (238, 236, 232) if self.hit_flash > 0.0 else body
        pygame.draw.line(screen, line, (sx - fx * 12, sy - fy * 12),
                         (sx - fx * 22, sy - fy * 22), 4)
        pygame.draw.circle(screen, body_c, (int(sx), int(sy)), 10)
        if self.species == "hyena":                      # sloped back + spots
            pygame.draw.circle(screen, (104, 84, 56), (int(sx - 3), int(sy - 2)), 2)
            pygame.draw.circle(screen, (104, 84, 56), (int(sx + 2), int(sy + 2)), 2)
            pygame.draw.circle(screen, (104, 84, 56), (int(sx - 1), int(sy + 4)), 2)
        pygame.draw.circle(screen, line, (int(sx), int(sy)), 10, 2)
        hx, hy = sx + fx * 9, sy + fy * 9
        pygame.draw.circle(screen, body_c, (int(hx), int(hy)), 6)
        pygame.draw.polygon(screen, ear, [
            (hx - fy * 5 - fx * 2, hy + fx * 5 - fy * 2),
            (hx - fy * 5 + fx * 3, hy + fx * 5 + fy * 3),
            (hx - fy * 2, hy + fx * 2)])
        pygame.draw.circle(screen, eye, (int(hx + fx * 3), int(hy + fy * 3)), 2)

    def _draw_snake(self, screen, cam_x, cam_y):
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        px, py = -fy, fx                       # perpendicular to facing
        base = (240, 240, 226) if self.hit_flash > 0.0 else (152, 156, 96)
        dark = (74, 92, 50)
        pygame.draw.ellipse(screen, (18, 16, 14), (sx - 14, sy - 4, 28, 8))
        n = 24
        spine = []
        for i in range(n):                     # wiggling spine trailing behind
            t = i / (n - 1.0)
            back = t * 46.0
            wave = math.sin(t * 6.6 + 0.5) * (1.5 + 9.0 * t)
            spine.append((sx - fx * back + px * wave,
                          sy - fy * back + py * wave))
        for i, (bx, by) in enumerate(spine):   # tapered round body
            t = i / (n - 1.0)
            pygame.draw.circle(screen, base, (int(bx), int(by)), max(2, int(10 - 6 * t)))
        for i in range(n - 1):                 # dark dorsal stripe
            pygame.draw.line(screen, dark, spine[i], spine[i + 1], 2)
        hx, hy = sx + fx * 7, sy + fy * 7
        pygame.draw.ellipse(screen, base, (hx - 7, hy - 6, 14, 12))
        pygame.draw.ellipse(screen, dark, (hx - 7, hy - 6, 14, 12), 2)
        pygame.draw.circle(screen, (238, 204, 74),
                           (int(hx + fx * 3), int(hy + fy * 3 - 2)), 2)
        pygame.draw.line(screen, (200, 60, 60), (hx + fx * 7, hy + fy * 7),
                         (hx + fx * 14, hy + fy * 14), 1)


class Rabbit:
    kind = "rabbit"

    def __init__(self, x: float, y: float, fur: str = "grey") -> None:
        self.x = float(x)
        self.y = float(y)
        self.fur = fur
        self.home = (float(x), float(y))
        self.team = ("rabbit", None)
        self.facing = (1.0, 0.0)
        self.radius = 7
        self.max_health = 12
        self.health = 12
        self.speed = 215.0
        self.hit_flash = 0.0
        self.flee_timer = 0.0
        self.hop_timer = random.uniform(0.4, 1.6)
        self.target = (self.x, self.y)

    @property
    def alive(self) -> bool:
        return self.health > 0

    take_damage = Enemy.take_damage

    def update(self, dt: float, threat=None, colliders=None) -> None:
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if not self.alive:
            return
        if threat is not None and not getattr(threat, "dead", False):
            dx, dy = self.x - threat.x, self.y - threat.y
            distance = math.hypot(dx, dy)
            if distance < 230.0:
                self.flee_timer = 1.2
                if distance > 1e-4:
                    self.x += dx / distance * self.speed * dt
                    self.y += dy / distance * self.speed * dt
                    self.facing = (dx / distance, dy / distance)
                return
        self.flee_timer = max(0.0, self.flee_timer - dt)
        self.hop_timer -= dt
        if self.hop_timer <= 0.0:
            self.hop_timer = random.uniform(0.5, 1.8)
            angle = random.uniform(0.0, 2.0 * math.pi)
            radius = random.uniform(20.0, 120.0)
            self.target = (self.home[0] + math.cos(angle) * radius,
                           self.home[1] + math.sin(angle) * radius)
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        if distance > 6.0:
            self.x += dx / distance * self.speed * 0.4 * dt
            self.y += dy / distance * self.speed * 0.4 * dt
            self.facing = (dx / distance, dy / distance)

    def draw(self, screen, cam_x, cam_y):
        sx = self.x - cam_x
        sy = self.y - cam_y
        fx, fy = self.facing
        palette = {"white": ((240, 242, 246), (176, 182, 190)),
                   "yellow": ((222, 198, 112), (156, 134, 66)),
                   "brown": ((154, 118, 78), (100, 74, 46)),
                   "grey": ((206, 196, 186), (120, 112, 106))}
        body, line = palette.get(self.fur, palette["grey"])
        pygame.draw.ellipse(screen, (18, 16, 14), (sx - 7, sy - 2, 14, 6))
        if self.hit_flash > 0.0:
            body = (250, 240, 240)
        pygame.draw.circle(screen, body, (int(sx), int(sy)), 7)
        pygame.draw.circle(screen, line, (int(sx), int(sy)), 7, 1)
        hx, hy = sx + fx * 6, sy + fy * 5 - 2
        pygame.draw.circle(screen, body, (int(hx), int(hy)), 4)
        pygame.draw.line(screen, line, (hx, hy - 2), (hx - 2, hy - 9), 2)
        pygame.draw.line(screen, line, (hx, hy - 2), (hx + 2, hy - 9), 2)


class Horse:
    """A horse: a harmless, skittish beast that wanders the plains and flees
    from people. Killable, but drops nothing for now."""
    kind = "horse"
    SPRITES = None                      # coat -> pre-scaled pygame surface
    HORSES: list = []                   # the whole herd, for separation
    COAT_FILES = {"brown": "horse.png", "black": "horse_black.png",
                  "white": "horse_white.png", "palomino": "horse_palomino.png"}
    DRAW = 80                           # on-screen size of the whole sprite

    def __init__(self, x: float, y: float, coat: str = "brown") -> None:
        self.x = float(x)
        self.y = float(y)
        self.coat = coat
        self.home = (float(x), float(y))
        self.team = ("horse", None)
        self.facing = (0.0, -1.0)
        self.radius = 15
        self.max_health = 70
        self.health = 70
        self.speed = 190.0
        self.hit_flash = 0.0
        self.flee_timer = 0.0
        self.graze_timer = random.uniform(0.5, 2.0)
        self.hunger = random.uniform(0.0, 30.0)   # like a man's belly
        self.food = random.randint(0, 2)          # what it has stored
        self.tamed = False                        # a settlement's livestock
        self.conquered = False                    # the player's own horse
        self.delivering = False                   # running the goods to the ship
        self.returning = False                    # coming back to its sleeping spot
        self.pack = None                          # an Inventory, made on demand
        self.coins = 0.0                          # the ship's payment, carried home
        self.g = None                             # the frame, for the ship and the market
        self.baby = False                         # a newborn, grows up over a day
        self.born_at = 0.0
        self.breeding = False                     # facing a mate, hearts out
        self.breed_partner = None
        self.route = None                         # a planned route: {origin, dest, item_a, item_b, amount}
        self.route_phase = None                   # "to_dest" | "to_home"
        self.route_loaded = False                 # cargo + feed are aboard
        self.route_feed = 0.0
        self.route_eat_t = 0.0
        self.escort = False                       # a soldier rides with it (Army)
        self.escort_soldier = None                # the soldier on its back
        self.target = (self.x, self.y)
        Horse.HORSES = [h for h in Horse.HORSES if h.alive]
        Horse.HORSES.append(self)

    @property
    def alive(self) -> bool:
        return self.health > 0

    def take_damage(self, amount: int, tranq: bool = False) -> bool:
        dead = Enemy.take_damage(self, amount, tranq)
        if dead:
            # A DEAD HORSE DROPS ITS CARGO: the saddle bags are lost with it.
            _p = getattr(self, "pack", None)
            if _p is not None and hasattr(_p, "slots"):
                _p.slots = [None] * len(_p.slots)
            self.route = None
            self.delivering = False
            self.returning = False
            self.escort_soldier = None
        return dead

    def _sprite(self):
        if Horse.SPRITES is None:
            Horse.SPRITES = {}
            for coat, fn in Horse.COAT_FILES.items():
                try:
                    img = pygame.image.load(fn).convert_alpha()
                    Horse.SPRITES[coat] = pygame.transform.smoothscale(
                        img, (Horse.DRAW, Horse.DRAW))
                except Exception:
                    Horse.SPRITES[coat] = None
        return Horse.SPRITES.get(self.coat)

    def _separation(self):
        """A push away from herd mates, so horses never crowd onto one spot."""
        px = py = 0.0
        for h in Horse.HORSES:
            if h is self or not h.alive:
                continue
            dx = self.x - h.x
            dy = self.y - h.y
            d = math.hypot(dx, dy)
            if 0.01 < d < 60.0:
                w = (60.0 - d) / 60.0
                px += dx / d * w
                py += dy / d * w
        return px, py

    def _move(self, ux: float, uy: float, speed: float, dt: float) -> None:
        sx, sy = self._separation()
        self.x += (ux * speed + sx * 140.0) * dt
        self.y += (uy * speed + sy * 140.0) * dt

    def _pack(self):
        """The horse's saddle bags: an Inventory, made the first time it is opened."""
        p = getattr(self, "pack", None)
        if p is None:
            try:
                from inventory import Inventory
                self.pack = Inventory(32)
            except Exception:
                self.pack = None
        return self.pack

    def _do_delivery(self, dt: float, colliders=None) -> None:
        """Run to the ship, offload, and come back to the sleeping spot.
        Steering dodges whatever stands in the way, so it never gets stuck on
        a wall or a tree trunk."""
        g = getattr(self, "g", None)
        if self.delivering:
            if g is None:
                self.delivering = False
                return
            sx, sy = g.ship_pos()
            d = math.hypot(sx - self.x, sy - self.y)
            if d < 52.0:
                self._deliver(g)
                self.delivering = False
                self.returning = True
                return
            ux, uy = steering.steer(self, sx, sy, colliders or (), ())
            self.x += ux * self.speed * 1.4 * dt
            self.y += uy * self.speed * 1.4 * dt
            self.facing = (ux, uy)
            return
        if self.returning:
            hx, hy = self.home
            d = math.hypot(hx - self.x, hy - self.y)
            if d < 24.0:
                self.returning = False
                self.x, self.y = hx, hy
                self.facing = (0.0, -1.0)
                self._drop_coin(g)          # the ship's coin reaches the chest
                return
            ux, uy = steering.steer(self, hx, hy, colliders or (), ())
            self.x += ux * self.speed * 1.2 * dt
            self.y += uy * self.speed * 1.2 * dt
            self.facing = (ux, uy)
            return

    def _deliver(self, g) -> None:
        """SELL the saddle bags to the ship. The coin rides home in the bags;
        goods the ship will not buy stay aboard -- nothing is given away."""
        n = self._sell_pack(g)
        if n > 0:
            try:
                g.toast("The horse sold %d goods for the ship's coin." % n)
            except Exception:
                pass

    def _sell_pack(self, g) -> int:
        """Sell every sellable good in the saddle bags to the ship, crediting
        the horse's own purse. Returns how many were sold."""
        try:
            import market as _market
        except Exception:
            return 0
        pack = self._pack()
        if pack is None:
            return 0
        coin = 0.0
        sold = 0
        sellable = _market.sellable(g)
        for i in range(len(pack.slots)):
            stack = pack.slots[i]
            if stack is None:
                continue
            if stack.defn.id not in sellable:
                continue
            grade = stack.quality if stack.defn.quality is not None else _market.MID_GRADE
            coin += _market.sell_value(g, stack.defn.id, stack.count, grade)
            sold += stack.count
            pack.slots[i] = None
        if coin > 0.0:
            self.coins = float(getattr(self, "coins", 0.0)) + coin
        return sold

    def _home_chest(self, g):
        """The settlement chest nearest the horse's sleeping spot."""
        chests = getattr(g, "built_chests", ()) if g is not None else ()
        if not chests:
            return None
        hx, hy = self.home
        return min(chests, key=lambda c: (c.x - hx) ** 2 + (c.y - hy) ** 2)

    def _drop_coin(self, g) -> None:
        """On arriving home, pay the settlement's chest with the coin the ship
        gave. With no chest the coin stays in the saddle bags for next time."""
        coins = int(round(float(getattr(self, "coins", 0.0))))
        if coins <= 0:
            return
        chest = self._home_chest(g)
        if chest is None or getattr(chest, "inventory", None) is None:
            return
        chest.inventory.add("coin", coins)
        self.coins = 0.0
        try:
            g.toast("The horse brought %d coin home." % coins)
        except Exception:
            pass

    # -- horse routes ----------------------------------------------------
    ROUTE_FEED = 10                # feed the horse takes per leg
    ROUTE_EAT_EVERY = 6.0          # seconds between eating one feed on the road

    def _route_chest(self, camp):
        """The 'Horse' chest nearest a settlement (its route node)."""
        g = getattr(self, "g", None)
        chests = getattr(g, "built_chests", ()) if g is not None else ()
        mine = [c for c in chests if getattr(c, "filter", None) == "horse"]
        if not mine:
            return None
        return min(mine, key=lambda c: (c.x - camp.x) ** 2 + (c.y - camp.y) ** 2)

    def _route_take(self, chest, item, amount):
        """Take up to `amount` of item out of a chest and into the saddle
        bags, grade intact. Returns how many were loaded."""
        inv = getattr(chest, "inventory", None)
        if inv is None:
            return 0
        want = min(int(amount), inv.count_of(item))
        if want <= 0:
            return 0
        remaining = want
        grades = []
        for i, stack in enumerate(inv.slots):
            if stack is None or stack.defn.id != item:
                continue
            take = min(remaining, stack.count)
            q = stack.quality if stack.defn.quality else None
            if q is not None:
                grades.append((q, take))
            stack.count -= take
            remaining -= take
            if stack.count <= 0:
                inv.slots[i] = None
            if remaining <= 0:
                break
        taken = want - remaining
        if taken <= 0:
            return 0
        pack = self._pack()
        if grades:
            tot = sum(c for _, c in grades)
            grade = int(round(sum(q * c for q, c in grades) / max(1, tot)))
            pack.add(item, taken, quality=grade)
        else:
            pack.add(item, taken)
        return taken

    def _route_drop(self, chest, item):
        """Pour every unit of item out of the saddle bags into a chest."""
        inv = getattr(chest, "inventory", None)
        if inv is None:
            return
        pack = self._pack()
        for i, stack in enumerate(list(pack.slots)):
            if stack is None or stack.defn.id != item:
                continue
            inv.add(item, stack.count, stack.quality)
            pack.slots[i] = None

    def _route_feed(self, chest):
        """Load a little food from the chest for the road."""
        inv = getattr(chest, "inventory", None)
        if inv is None:
            return
        want = max(0, self.ROUTE_FEED - int(getattr(self, "food", 0)))
        if want <= 0:
            return
        for item in economy.FOOD:
            have = inv.count_of(item)
            if have <= 0:
                continue
            take = min(want, have)
            remaining = take
            for i, stack in enumerate(inv.slots):
                if stack is None or stack.defn.id != item:
                    continue
                d = min(remaining, stack.count)
                stack.count -= d
                remaining -= d
                if stack.count <= 0:
                    inv.slots[i] = None
                if remaining <= 0:
                    break
            self.food = int(getattr(self, "food", 0)) + take
            return

    def _route_steer(self, tx, ty, dt, colliders):
        ux, uy = steering.steer(self, tx, ty, colliders or (), ())
        self.x += ux * self.speed * 1.4 * dt
        self.y += uy * self.speed * 1.4 * dt
        self.facing = (ux, uy)

    def _do_route(self, dt, colliders=None):
        """Run a planned route forever: load cargo + feed at the home horse
        chest, carry it to the destination, drop it, load the destination's
        cargo + feed, and carry that home. Repeat."""
        r = self.route
        g = getattr(self, "g", None)
        if r is None or g is None:
            self.route = None
            return
        origin = r.get("origin")
        dest = r.get("dest")
        item_a = r.get("item_a")
        item_b = r.get("item_b")
        amount = int(r.get("amount", 300))
        ship = dest == "ship"
        if ship:
            tx, ty = g.ship_pos()
            dest_chest = getattr(g, "ship_hold", None)
        else:
            tx, ty = dest.x, dest.y
            dest_chest = self._route_chest(dest)
        home_chest = self._route_chest(origin)
        # eat (or get hungry) on the road
        self.route_eat_t += dt
        if self.route_eat_t >= self.ROUTE_EAT_EVERY:
            self.route_eat_t = 0.0
            if int(getattr(self, "food", 0)) > 0:
                self.food -= 1
                self.hunger = max(0.0, self.hunger - 20.0)
            else:
                self.hunger = min(130.0, self.hunger + 8.0)
        if self.route_phase != "to_home":
            self.route_phase = "to_dest"
            if not self.route_loaded:
                if home_chest is not None:
                    self._route_take(home_chest, item_a, amount)
                    self._route_feed(home_chest)
                self.route_loaded = True
            if math.hypot(tx - self.x, ty - self.y) > 28.0:
                self._route_steer(tx, ty, dt, colliders)
                return
            if ship:
                self._sell_pack(g)          # the ship buys the cargo, coin to the purse
            elif dest_chest is not None:
                self._route_drop(dest_chest, item_a)
                self._route_take(dest_chest, item_b, amount)
                self._route_feed(dest_chest)
            self.route_phase = "to_home"
            return
        # to_home
        hx, hy = origin.x, origin.y
        if math.hypot(hx - self.x, hy - self.y) > 28.0:
            self._route_steer(hx, hy, dt, colliders)
            return
        self._drop_coin(g)              # the ship's coin reaches the settlement
        if home_chest is not None:
            if item_b and not ship:
                self._route_drop(home_chest, item_b)
            self._route_drop(home_chest, item_a)
        self.route_phase = "to_dest"
        self.route_loaded = False
        return

    def update(self, dt: float, threat=None, colliders=None) -> None:
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if not self.alive:
            return
        self._animal_baby_tick(dt)
        if self._animal_breeding_tick():
            return
        # RUNNING A PLANNED ROUTE: it outranks everything but life itself.
        if getattr(self, "route", None) is not None:
            self._do_route(dt, colliders)
            return
        # RUNNING A DELIVERY: to the ship, then back to the sleeping spot.
        if self.delivering or self.returning:
            self._do_delivery(dt, colliders)
            return
        self._animal_hunger(dt)
        if self.hunger >= economy.STARVE_AT:
            self.health = 0
            return
        # SKITTISH: a person near spooks it into a full run -- a TAMED horse
        # does not run from people.
        if not getattr(self, "tamed", False) and threat is not None and not getattr(threat, "dead", False):
            dx, dy = self.x - threat.x, self.y - threat.y
            d = math.hypot(dx, dy)
            if d < 260.0:
                self.flee_timer = 1.4
                if d > 1e-4:
                    self._move(dx / d, dy / d, SPRINTER_MAX, dt)
                    self.facing = (dx / d, dy / d)
                return
        self.flee_timer = max(0.0, self.flee_timer - dt)
        # HUNGRY: a wild horse forages; a tamed one eats from the feed box.
        if self.hunger >= economy.EAT_AT and self.food <= 0:
            if getattr(self, "tamed", False):
                if self._eat_from_box(dt, colliders):
                    return
            elif self._animal_forage(dt):
                return
        # GRAZE: pick a new spot near home now and then, then amble to it.
        self.graze_timer -= dt
        if self.graze_timer <= 0.0:
            self.graze_timer = random.uniform(1.0, 3.0)
            ang = random.uniform(0.0, 2.0 * math.pi)
            # a tamed horse keeps close to its sleeping spot
            r = (random.uniform(20.0, 70.0) if getattr(self, "tamed", False)
                 else random.uniform(30.0, 200.0))
            self.target = (self.home[0] + math.cos(ang) * r,
                           self.home[1] + math.sin(ang) * r)
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d > 8.0:
            self._move(dx / d, dy / d, self.speed * 0.35, dt)
            self.facing = (dx / d, dy / d)

    def draw(self, screen, cam_x, cam_y):
        img = self._sprite()
        sx, sy = self.x - cam_x, self.y - cam_y
        if img is None:
            # fallback if the PNG is missing: a plain top-down oval
            pygame.draw.ellipse(screen, (120, 90, 56),
                                (sx - 13, sy - 22, 26, 44))
            return
        # A NEWBORN IS SMALL: it grows into a full horse across one day.
        if getattr(self, "baby", False):
            img = pygame.transform.smoothscale(img, (45, 45))
        fx, fy = self.facing
        deg = math.degrees(math.atan2(fy, fx))
        rot = pygame.transform.rotate(img, -(deg + 90.0))
        screen.blit(rot, rot.get_rect(center=(int(sx), int(sy))))
        if getattr(self, "breeding", False):
            self._draw_breeding_hearts(screen, sx, sy)


class Bison(Enemy):
    """A bison: passive, keeps its distance from you, and only charges when
    one of the herd is hit. Drops meat (5x a rabbit) and hides."""
    kind = "bison"
    BISONS: list = []          # the whole herd, for the herd-aggro rule

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.team = ("bison", None)
        self.max_health = stats.PLAYER_MAX_HEALTH     # as much health as a man
        self.health = self.max_health
        self.radius = 13
        self.speed = 100.0                            # twice a man's walk
        self.melee_damage = 2.0 * (35.0 / 3.0)        # double a man's punch
        self.aggro = False
        self.graze_timer = random.uniform(0.5, 2.0)
        self.hunger = random.uniform(0.0, 30.0)   # like a man's belly
        self.food = random.randint(0, 2)          # what it has stored
        self.tamed = False                        # a settlement's livestock
        self.baby = False                         # a newborn, grows up over a day
        self.born_at = 0.0
        self.breeding = False                     # facing a mate, hearts out
        self.breed_partner = None
        self.fire_cd = 0.0
        Bison.BISONS = [b for b in Bison.BISONS if b.alive]   # drop the dead
        Bison.BISONS.append(self)

    def take_damage(self, amount: int, tranq: bool = False) -> bool:
        dead = super().take_damage(amount, tranq)
        if getattr(self, "tamed", False):
            return dead                # livestock never turns on the herd
        if not dead and not getattr(self, "dead", False):
            # THE HERD TURNS ON THE ATTACKER: every bison nearby charges.
            for b in Bison.BISONS:
                if b is not self and b.alive:
                    if math.hypot(b.x - self.x, b.y - self.y) < 520.0:
                        b.aggro = True
            self.aggro = True
        return dead

    def _separation(self):
        """A push away from herd mates, so bisons never pile onto one spot."""
        px = py = 0.0
        for b in Bison.BISONS:
            if b is self or not b.alive:
                continue
            dx = self.x - b.x
            dy = self.y - b.y
            d = math.hypot(dx, dy)
            if 0.01 < d < 46.0:
                w = (46.0 - d) / 46.0
                px += dx / d * w
                py += dy / d * w
        return px, py

    def _move(self, ux: float, uy: float, speed: float, dt: float) -> None:
        sx, sy = self._separation()
        self.x += (ux * speed + sx * 90.0) * dt
        self.y += (uy * speed + sy * 90.0) * dt

    def update(self, dt: float, target, combat, occluders=None,
               speed_scale: float = 1.0, view_scale: float = 1.0,
               visible: bool = True, colliders=None) -> None:
        self._colliders = colliders or []
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if not self.alive:
            return
        self._animal_baby_tick(dt)
        if self._animal_breeding_tick():
            return
        self._animal_hunger(dt)
        if self.hunger >= economy.STARVE_AT:
            self.health = 0
            return
        # A TAMED BISON never charges and never flees: it grazes at home.
        if not getattr(self, "tamed", False) and self.aggro:
            self._charge(dt, target)
            return
        # PASSIVE: keep a respectful distance from the player, else graze.
        if not getattr(self, "tamed", False) and target is not None and not getattr(target, "dead", False):
            dx, dy = self.x - target.x, self.y - target.y
            d = math.hypot(dx, dy)
            if d < 220.0:
                ux, uy = (dx / d, dy / d)
                # RUN: a bison at full flight is as fast as the fastest man.
                self._move(ux, uy, SPRINTER_MAX, dt)
                self.facing = (ux, uy)
                return
        # HUNGRY: a wild bison forages; a tamed one eats from the feed box.
        if self.hunger >= economy.EAT_AT and self.food <= 0:
            if getattr(self, "tamed", False):
                if self._eat_from_box(dt, colliders):
                    return
            elif self._animal_forage(dt):
                return
        self.graze_timer -= dt
        if self.graze_timer <= 0.0:
            self.graze_timer = random.uniform(1.0, 3.0)
            ang = random.uniform(0.0, 2.0 * math.pi)
            # a tamed bison keeps close to its sleeping spot
            r = (random.uniform(20.0, 70.0) if getattr(self, "tamed", False)
                 else random.uniform(20.0, 140.0))
            self.target = (self.home[0] + math.cos(ang) * r,
                           self.home[1] + math.sin(ang) * r)
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d > 6.0:
            self._move(dx / d, dy / d, self.speed * 0.3, dt)
            self.facing = (dx / d, dy / d)

    def _charge(self, dt: float, target) -> None:
        if target is None:
            target = getattr(self, "_player", None)
        if target is None or not getattr(target, "alive", True):
            self.aggro = False
            return
        dx, dy = target.x - self.x, target.y - self.y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        self.facing = (ux, uy)
        self._move(ux, uy, self.speed, dt)
        self.fire_cd -= dt
        if d <= 44.0 and self.fire_cd <= 0.0:
            self.fire_cd = 1.0
            if hasattr(target, "take_damage"):
                target.take_damage(max(1, int(round(self.melee_damage))))

    def draw(self, screen, cam_x, cam_y):
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        coat = (110, 72, 44)
        coat_d = (70, 44, 26)
        hump = (164, 114, 62)
        head = (82, 52, 30)
        horn = (214, 196, 164)
        horn_d = (150, 128, 96)
        eye = (12, 9, 7)
        if self.hit_flash > 0.0:
            coat = hump = head = (240, 236, 230)
        # A NEWBORN CALF IS SMALL: a simple small body, no full horns yet.
        if getattr(self, "baby", False):
            pygame.draw.ellipse(screen, (16, 13, 10), (sx - 10, sy - 2, 20, 8))
            pygame.draw.circle(screen, coat_d, (int(sx), int(sy)), 9)
            pygame.draw.circle(screen, coat, (int(sx), int(sy)), 8)
            pygame.draw.circle(screen, head, (int(sx + fx * 7), int(sy + fy * 7)), 5)
            if getattr(self, "breeding", False):
                self._draw_breeding_hearts(screen, sx, sy)
            return
        pygame.draw.ellipse(screen, (16, 13, 10), (sx - 15, sy - 3, 32, 10))
        pygame.draw.line(screen, coat_d, (sx - fx * 14, sy - fy * 14),
                         (sx - fx * 22, sy - fy * 22), 3)
        pygame.draw.circle(screen, coat_d, (int(sx), int(sy)), 14)
        pygame.draw.circle(screen, coat, (int(sx), int(sy)), 13)
        hx0, hy0 = int(sx - fx * 4), int(sy - fy * 4)
        pygame.draw.ellipse(screen, hump, (hx0 - 8, hy0 - 7, 16, 14))
        hx, hy = sx + fx * 13, sy + fy * 13
        pygame.draw.circle(screen, coat_d, (int(hx), int(hy)), 9)
        pygame.draw.circle(screen, head, (int(hx), int(hy)), 8)
        # two thick curved horns, sweeping forward
        for sgn in (1, -1):
            cx, cy = int(hx), int(hy + sgn * 8)
            rect = pygame.Rect(cx - 6, cy - 5, 16, 10)
            if sgn == 1:
                pygame.draw.arc(screen, horn_d, rect, -1.15, -0.05, 4)
                pygame.draw.arc(screen, horn, rect, -1.15, -0.05, 2)
            else:
                pygame.draw.arc(screen, horn_d, rect, 0.05, 1.15, 4)
                pygame.draw.arc(screen, horn, rect, 0.05, 1.15, 2)
        pygame.draw.circle(screen, eye, (int(hx), int(hy - 4)), 2)
        pygame.draw.circle(screen, eye, (int(hx), int(hy + 4)), 2)
        if getattr(self, "breeding", False):
            self._draw_breeding_hearts(screen, sx, sy)


def _grazing_animals():
    """Every horse and bison alive -- the two herds share their grazing."""
    out = [h for h in Horse.HORSES if h.alive]
    out += [b for b in Bison.BISONS if b.alive]
    return out


def _animal_hunger(self, dt: float) -> None:
    """A grazing beast's belly empties exactly like a man's: hunger rises on
    the day clock, and stored food is eaten first, one bite at a time."""
    self.hunger = getattr(self, "hunger", 0.0) + economy.HUNGER_RATE * dt
    if self.hunger > 130.0:
        self.hunger = 130.0
    if self.hunger >= economy.EAT_AT and getattr(self, "food", 0) > 0:
        self.food -= 1
        self.hunger = max(0.0, self.hunger - economy.EAT_BY)


def _animal_forage(self, dt: float) -> bool:
    """Walk to the nearest wild plant and eat it up; every other grazing
    animal near the bite gets an equal amount, stored for later. Returns True
    while it is walking or eating."""
    try:
        import wildcrop as _wc
    except Exception:
        return False
    world = _wc._WORLD
    if world is None:
        return False
    found = _wc._nearest(world, self.x, self.y, 520.0)
    if found is None:
        return False
    tx, ty, _kind = found
    try:
        from world import TILE
        wx = tx * TILE + TILE / 2.0
        wy = ty * TILE + TILE / 2.0
    except Exception:
        wx = tx * 32 + 16.0
        wy = ty * 32 + 16.0
    dx, dy = wx - self.x, wy - self.y
    d = math.hypot(dx, dy)
    if d > 22.0:
        self._move(dx / d, dy / d, getattr(self, "speed", 100.0) * 0.5, dt)
        self.facing = (dx / d, dy / d)
        return True
    # EAT IT UP: the plant is gone until it regrows.
    try:
        world.wild_eaten[(tx, ty)] = _wc._NOW + _wc.REGEN
    except Exception:
        pass
    self.hunger = max(0.0, getattr(self, "hunger", 0.0) - economy.FORAGE_MEAL)
    # SHARE: nearby animals each get the same bite, stored for later.
    for other in _grazing_animals():
        if other is self or not getattr(other, "alive", True):
            continue
        if math.hypot(other.x - wx, other.y - wy) < SHARE_RADIUS:
            other.food = getattr(other, "food", 0) + 1
    return True


def _animal_food_box(self):
    """The nearest feed box, or None."""
    g = getattr(self, "g", None)
    boxes = getattr(g, "built_foodboxes", None) if g is not None else None
    if not boxes:
        return None
    return min(boxes, key=lambda b: (b.x - self.x) ** 2 + (b.y - self.y) ** 2)


def _eat_from_box(self, dt: float, colliders=None) -> bool:
    """A tamed beast: walk to the feed box and eat one bite out of it. Returns
    True while it is walking or eating."""
    box = _animal_food_box(self)
    if box is None or getattr(box, "inventory", None) is None:
        return False
    d = math.hypot(box.x - self.x, box.y - self.y)
    if d > 22.0:
        ux, uy = steering.steer(self, box.x, box.y, colliders or (), ())
        self.x += ux * getattr(self, "speed", 100.0) * 0.5 * dt
        self.y += uy * getattr(self, "speed", 100.0) * 0.5 * dt
        self.facing = (ux, uy)
        return True
    for item in economy.FOOD:
        if box.inventory.consume(item, 1):
            self.food = getattr(self, "food", 0) + 1
            return True
    return True                    # the box is empty: wait beside it


def _animal_baby_tick(self, dt: float) -> None:
    """A newborn grows into an adult across one full day."""
    if not getattr(self, "baby", False):
        return
    g = getattr(self, "g", None)
    if g is None:
        return
    if float(getattr(g, "now", 0.0)) - float(getattr(self, "born_at", 0.0)) >= economy.DAY_LENGTH:
        self.baby = False


def _animal_breeding_tick(self) -> bool:
    """While breeding, the beast faces its mate and stands still. Returns True
    so the caller's update can stop here."""
    if not getattr(self, "breeding", False):
        return False
    p = getattr(self, "breed_partner", None)
    if p is not None and getattr(p, "alive", True):
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        self.facing = (dx / d, dy / d)
    return True


def _draw_breeding_hearts(self, screen, sx, sy) -> None:
    """Floating hearts over a breeding pair, rising on the game clock."""
    try:
        import wildcrop as _wc
        now = float(getattr(_wc, "_NOW", 0.0))
        fnt = pygame.font.SysFont("dejavusans", 14, bold=True)
        for i in range(2):
            phase = (now * 1.3 + i * 0.5) % 1.0
            hx = int(sx + (i - 0.5) * 12)
            hy = int(sy - 24 - phase * 14)
            h = fnt.render("\u2665", True, (226, 72, 72))
            screen.blit(h, (hx, hy))
    except Exception:
        pass


Horse._animal_hunger = _animal_hunger
Horse._animal_forage = _animal_forage
Horse._animal_food_box = _animal_food_box
Horse._eat_from_box = _eat_from_box
Horse._animal_baby_tick = _animal_baby_tick
Horse._animal_breeding_tick = _animal_breeding_tick
Horse._draw_breeding_hearts = _draw_breeding_hearts
Bison._animal_hunger = _animal_hunger
Bison._animal_forage = _animal_forage
Bison._animal_food_box = _animal_food_box
Bison._eat_from_box = _eat_from_box
Bison._animal_baby_tick = _animal_baby_tick
Bison._animal_breeding_tick = _animal_breeding_tick
Bison._draw_breeding_hearts = _draw_breeding_hearts


def make_squad(nation, x: float, y: float, count: int = 3, color=None):
    """Soldiers that follow the player -- the army you get when you enlist."""
    squad = []
    for _ in range(count):
        ang = random.uniform(0.0, 2.0 * math.pi)
        soldier = Soldier(x + math.cos(ang) * 46.0, y + math.sin(ang) * 46.0,
                          nation, melee=False, seed=random.randint(0, 2 ** 31),
                          color=color)
        soldier.follow = True
        # VETERANS HAVE SKILLS, NOT MORE MEAT: the same body as the player.
        soldier.max_health = stats.PLAYER_MAX_HEALTH
        soldier.health = stats.PLAYER_MAX_HEALTH
        soldier.march_village = None
        squad.append(soldier)
    return squad


def is_trader(obj) -> bool:
    """A caravan, under the free-trade policy between kingdoms.

    Nobody shoots at a trader: not a soldier of a nation at war, not a border
    guard, not a patrol, not a column on the march. They are how the world
    learns anything and how an army buys its powder, and every king knows it.
    The player is never covered by this, whatever he is employed as -- he is
    not a caravan.
    """
    return (getattr(obj, "trade_state", "none") != "none"
            or getattr(obj, "job", None) == "trader")


def _g_inside(npc) -> bool:
    try:
        import gulag as _g
        return _g.inside(getattr(npc, "x", 0.0), getattr(npc, "y", 0.0))
    except Exception:
        return False


def choose_target(creature, player, enemies, rabbits, villages, squad=(),
                  persons=None):
    """The nearest thing ``creature`` should be attacking, or None."""
    hidden = any(math.hypot(player.x - v.x, player.y - v.y) < v.radius
                 for v in villages)
    cands = []
    if creature.kind == "soldier":
        if getattr(creature, "gulag", False):
            # A CAMP GUARD SHOOTS ANYBODY INSIDE THE FENCE WHO IS NOT ONE OF
            # HIS OWN. That is the whole of the law out here.
            try:
                import gulag as _g
                _camp = getattr(creature, "_player", None) or player
                _here = _g.inside(getattr(_camp, "x", 0.0),
                                  getattr(_camp, "y", 0.0), 40.0)
            except Exception:
                _camp, _here = player, False
            if _here and not _camp.dead:
                cands.append(_camp)
            pool = list(persons or ())
            for v in villages:
                pool.extend(getattr(v, "npcs", ()) or ())
            for npc in pool:
                if (getattr(npc, "alive", True) and not npc.in_interior
                        and not getattr(npc, "gulag", False)
                        and _g_inside(npc)):
                    cands.append(npc)
            best, best_d2 = None, 1e30
            for c in cands:
                if getattr(c, "dead", False):
                    continue
                d2 = (c.x - creature.x) ** 2 + (c.y - creature.y) ** 2
                if d2 < best_d2:
                    best_d2, best = d2, c
            return best
        if getattr(creature, "manhunt", False):
            # A HUNTING PARTY HAS STANDING ORDERS. The leader and every known
            # man of his organisation are fair game on sight, whatever nation
            # they claim -- and the men are named, not inferred, so a fresh
            # hire standing in the yard is not "just another villager".
            # THE LEADER HIMSELF, not whatever `player` happens to be: in the
            # game's own test mode that argument is the observer, and a hunting
            # party that hunts the observer never fires a shot at the player.
            _who = getattr(creature, "_player", None) or player
            _ids = getattr(creature, "hunt_ids", None) or ()
            # ON SIGHT, not by telepathy: a party marching to the yard does not
            # open fire on a name three kilometres away. Everything on the
            # list becomes a candidate once it is in front of their rifles.
            _reach = max(getattr(creature, "view_range", 0.0), 480.0)
            _reach2 = _reach * _reach
            if (not _who.dead
                    and (_who.x - creature.x) ** 2
                    + (_who.y - creature.y) ** 2 < _reach2):
                cands.append(_who)
            if _ids:
                pool = list(persons or ())
                for v in villages:
                    pool.extend(getattr(v, "npcs", ()) or ())
                seen = set()
                for npc in pool:
                    if not getattr(npc, "alive", True) or npc.in_interior:
                        continue
                    if id(npc) in seen:
                        continue
                    if str(getattr(npc, "id", "")) in _ids:
                        if ((npc.x - creature.x) ** 2
                                + (npc.y - creature.y) ** 2) < _reach2:
                            seen.add(id(npc))
                            cands.append(npc)
            for other in enemies:
                if other is creature or not other.alive:
                    continue
                if other.kind == "soldier" and other.nation != creature.nation:
                    cands.append(other)
                elif other.kind == "wolf":
                    cands.append(other)
            best = None
            best_d2 = 1e30
            for c in cands:
                if c is _who and _who.dead:
                    continue
                d2 = (c.x - creature.x) ** 2 + (c.y - creature.y) ** 2
                if d2 < best_d2:
                    best_d2, best = d2, c
            return best
        guard = getattr(creature, "guard_village", None)
        if guard is not None:
            # A border guard is watching the fence line: only people OUTSIDE
            # the palisade are his business.  Someone inside the village is
            # NOT shot -- not even a neutral standing right in front of him.
            # Provocation (a crime, or being an enemy) makes him hunt anywhere.
            outside = not guard.fence_rect.collidepoint(player.x, player.y)
            in_sight = math.hypot(player.x - creature.x,
                                  player.y - creature.y) < creature.view_range + 90.0
            # A MAN WITH NO NATION HAS NO NATION'S WAR. This read
            # `player.nation != creature.nation`, and the arrival owns nothing
            # and belongs to nobody -- None != 1 -- so every gate guard in the
            # country treated him as a foreign soldier and opened fire the
            # moment he walked up the road. Nationless is not foreign.
            _town = getattr(creature, "gate_village", None) or getattr(
                creature, "guard_village", None)
            # A BRAWL IS NOT HIS FIGHT. The town turning on a brawl used to
            # make its own guards shoot the PLAYER, just for standing in the
            # middle. A guard hunts a WANTED man; he does not shoot a man for
            # being near a punch-up.
            _angry = getattr(player, "wanted", False)
            if (not player.dead
                    and (_angry
                         or (player.nation is not None
                             and player.nation != creature.nation
                             and outside and in_sight))):
                cands.append(player)
            for other in enemies:
                if other is creature or not other.alive:
                    continue
                if other.kind == "soldier" and other.nation != creature.nation:
                    cands.append(other)
                elif other.kind == "wolf":
                    cands.append(other)
        elif getattr(creature, "patrol_center", None) is not None:
            # A territory patrol: shoots any non-army player on sight (inside
            # a village or not), other nations' soldiers, and wolves. Same
            # nation means no quarrel.
            if (not player.dead and player.nation is not None
                    and player.nation != creature.nation):
                cands.append(player)
            for other in enemies:
                if other is creature or not other.alive:
                    continue
                if other.kind == "soldier" and other.nation != creature.nation:
                    cands.append(other)
                elif other.kind == "wolf":
                    cands.append(other)
        elif getattr(creature, "march_target", None) is not None:
            # On a mission -- but the road belongs to whoever is on it. Another
            # column in sight is not "something to shoot at in passing": it is
            # the battle. Anything else gets return fire at close range only.
            # AND THE PLAYER. A column on the road does not know him from
            # anyone else: a stranger of another nation inside the view is a
            # threat, and standing there watching them go by is not an option.
            if (not player.dead and getattr(player, "nation", None) is not None
                    and player.nation != creature.nation):
                dx, dy = player.x - creature.x, player.y - creature.y
                if dx * dx + dy * dy < creature.view_range ** 2:
                    cands.append(player)
            for other in enemies:
                if other is creature or not other.alive or other.team == creature.team:
                    continue
                reach = (creature.view_range
                         if other.kind == "soldier" else 480.0)
                dx, dy = other.x - creature.x, other.y - creature.y
                if dx * dx + dy * dy < reach * reach:      # no square root
                    cands.append(other)
            if persons is not None:
                near2 = 480.0 * 480.0
                for npc in persons:         # only the people actually nearby
                    dx, dy = npc.x - creature.x, npc.y - creature.y
                    if (npc.alive and not npc.in_interior
                            and npc.nation != creature.nation
                            and dx * dx + dy * dy < near2):
                        cands.append(npc)
            else:
                for v in villages:
                    if v.nation != creature.nation:
                        for npc in v.npcs:  # the people, not just the guards
                            if (npc.alive and not npc.in_interior
                                    and math.hypot(npc.x - creature.x,
                                                   npc.y - creature.y) < 480.0):
                                cands.append(npc)
        else:
            # THE SAME RULE AS EVERYWHERE ELSE: a man with no nation has no
            # nation's war. This line was the last place that read
            # `None != 1` as "an enemy soldier".
            if (not player.dead and getattr(player, "nation", None) is not None
                    and player.nation != creature.nation and not hidden):
                cands.append(player)
            for other in enemies:
                if other is creature or not other.alive:
                    continue
                if other.kind == "soldier" and other.nation != creature.nation:
                    cands.append(other)
                elif other.kind == "wolf":
                    cands.append(other)
            for v in villages:                 # enemy defenders are fair game
                if persons is not None:
                    hunting = getattr(creature, "hostile", False)
                    for npc in persons:
                        if (npc.alive and not npc.in_interior
                                and npc.nation != creature.nation
                                and (npc.defender or hunting)):
                            cands.append(npc)
                else:
                    hunting = getattr(creature, "hostile", False)
                    for npc in v.npcs:
                        if npc.alive and not npc.in_interior and (npc.defender
                                                                  or hunting):
                            cands.append(npc)
    elif creature.kind == "wolf":
        if not player.dead:
            cands.append(player)
        for other in enemies:
            if other.alive and other.kind == "soldier":
                cands.append(other)
        for rabbit in rabbits:
            if rabbit.alive:
                cands.append(rabbit)
        for v in villages:                          # wolves hate every human
            for npc in v.npcs:
                if npc.alive:
                    cands.append(npc)
    best = None
    best_d2 = 1e30
    for c in cands:
        if c is player and player.dead:
            continue
        # THE ROAD IS OPEN TO TRADERS. Checked here, once, for every kind of
        # creature and every branch above -- so no future target rule can
        # forget it.
        if c is not player and is_trader(c):
            continue
        d2 = (c.x - creature.x) ** 2 + (c.y - creature.y) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = c
    return best


class Patrol:
    """A squad of one nation's soldiers that roams the countryside together."""

    def __init__(self, x: float, y: float, nation, size: int = 3,
                 melee_fraction: float = 0.35, color=None) -> None:
        self.nation = nation
        self.team = ("nation", nation)
        self.x = x
        self.y = y
        self.target = (x, y)
        self.timer = 0.0
        self.war_target = None
        self.members: list[Soldier] = []
        for i in range(max(1, size)):
            melee = random.random() < melee_fraction
            member = Soldier(x + random.uniform(-70, 70), y + random.uniform(-70, 70),
                             nation, melee=melee, seed=random.randint(0, 2 ** 31),
                             color=color)
            member.home = (x, y)
            self.members.append(member)

    def update(self, dt: float) -> None:
        speed = 74.0
        if self.war_target is not None:        # march at the enemy
            dx, dy = self.war_target[0] - self.x, self.war_target[1] - self.y
            dist = math.hypot(dx, dy)
            if dist > 70.0:
                self.x += dx / dist * speed * dt
                self.y += dy / dist * speed * dt
            self.timer = max(self.timer, 3.0)
        else:
            self.timer -= dt
            dx, dy = self.target[0] - self.x, self.target[1] - self.y
            distance = math.hypot(dx, dy)
            if distance < 40.0 or self.timer <= 0.0:
                angle = random.uniform(0.0, 2.0 * math.pi)
                radius = random.uniform(400.0, 1200.0)
                self.target = (self.x + math.cos(angle) * radius,
                               self.y + math.sin(angle) * radius)
                self.timer = random.uniform(12.0, 24.0)
            else:
                self.x += dx / distance * speed * dt
                self.y += dy / distance * speed * dt
        for member in self.members:
            if member.alive:
                member.home = (self.x, self.y)
        if any(m.alive and m.aware for m in self.members):
            for member in self.members:
                if member.alive:
                    member.aware = True
                    member.aware_timer = max(member.aware_timer, 3.0)
