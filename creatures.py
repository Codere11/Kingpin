"""Nation soldiers, wolves and rabbits.

Soldiers and wolves reuse Enemy's perception/patrol plumbing but pick their own
targets (handled by main). Wolves smell you twice as far as a person and bite
for half a person's melee. Rabbits are harmless, fast, and skittish.
"""

from __future__ import annotations

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
    # The war face's timer. A CLASS default, because a soldier who has never
    # swung a blow must not be missing the attribute the draw reads.
    attack_flash: float = 0.0

    kind = "soldier"

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
        self.max_health = 115
        self.health = 115
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
        self._colliders = colliders or []
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
            if self.fire_cd <= 0.0 and distance <= 520.0 and self._round_ready():
                self.fire_cd = random.uniform(0.5, 0.9)
                angle = math.atan2(dy, dx) + random.uniform(-0.03, 0.03)
                self._shoot(combat, self.x + ux * 20.0, self.y + uy * 20.0,
                            angle, distance + 160.0, 8, 14)
        else:
            self.view_angle = math.radians(90.0)    # eyes on the fence
            self._walk_loop(dt)

    def _patrol_update(self, dt, target, combat, occluders, view_scale, visible):
        """A territory patrol: walk the village's political border; engage
        anything hostile that comes into sight, then carry on."""
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
            if self.fire_cd <= 0.0 and distance <= 560.0 and self._round_ready():
                self.fire_cd = random.uniform(0.45, 0.8)
                angle = math.atan2(dy, dx) + random.uniform(-0.035, 0.035)
                self._shoot(combat, self.x + ux * 20.0, self.y + uy * 20.0,
                            angle, distance + 160.0, 8, 14)
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
        self.fire_cd -= dt
        dx, dy = target.x - self.x, target.y - self.y
        dist = math.hypot(dx, dy) or 1.0
        if self.fire_cd <= 0.0 and dist <= 560.0:
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
                    self.fire_cd = random.uniform(0.55, 0.95) * (
                    1.8 if self.exhausted else 1.0)
                    self.attack_flash = face.WAR_SECONDS
                    self._shoot(combat, mx, my, angle, dist + 160.0, 7, 12)

    def _fight(self, dt, target, combat, speed_scale, visible=True):
        dx, dy = target.x - self.x, target.y - self.y
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = steering.steer(self, target.x, target.y,
                                getattr(self, "_rects", ()),
                                getattr(self, "_fences", ()))
        self.facing = (ux, uy)
        speed = self.speed * speed_scale * self.skills.move_scale()

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
                combat.fire(mx, my, angle, distance + 160.0, owner="enemy",
                            # THE SAME BULLET THE PLAYER FIRES. It was
                            # randint(7, 12): a soldier's musket hit for a
                            # third of the player's rifle, so the ranks were
                            # firing popguns and the player was a corps of
                            # one. It is guns.DAMAGE[RIFLE] now, one number
                            # for one weapon in the whole world.
                            damage=guns.DAMAGE[guns.RIFLE], team=self.team,
                            spread=self.skills.shot_spread(), shooter=self)

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
        pygame.draw.circle(screen, (214, 172, 132), (int(_hx), int(_hy)), 8)
        pygame.draw.circle(screen, (140, 104, 76), (int(_hx), int(_hy)), 8, 1)
        face.draw(screen, _hx, _hy, 8, fx, fy,
                  face.mood_of(self.hurt_flash, self.attack_flash,
                               starved=getattr(self, "hunger", 0.0)
                               >= face.STARVED_HUNGER),
                  vet=face.vet_tier(self.skills.axe, self.skills.shooting))
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


def make_squad(nation, x: float, y: float, count: int = 3, color=None):
    """Soldiers that follow the player -- the army you get when you enlist."""
    squad = []
    for _ in range(count):
        ang = random.uniform(0.0, 2.0 * math.pi)
        soldier = Soldier(x + math.cos(ang) * 46.0, y + math.sin(ang) * 46.0,
                          nation, melee=False, seed=random.randint(0, 2 ** 31),
                          color=color)
        soldier.follow = True
        soldier.max_health = 160          # your squad is veteran, not militia
        soldier.health = 160
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


def choose_target(creature, player, enemies, rabbits, villages, squad=(),
                  persons=None):
    """The nearest thing ``creature`` should be attacking, or None."""
    hidden = any(math.hypot(player.x - v.x, player.y - v.y) < v.radius
                 for v in villages)
    cands = []
    if creature.kind == "soldier":
        guard = getattr(creature, "guard_village", None)
        if guard is not None:
            # A border guard is watching the fence line: only people OUTSIDE
            # the palisade are his business.  Someone inside the village is
            # NOT shot -- not even a neutral standing right in front of him.
            # Provocation (a crime, or being an enemy) makes him hunt anywhere.
            outside = not guard.fence_rect.collidepoint(player.x, player.y)
            in_sight = math.hypot(player.x - creature.x,
                                  player.y - creature.y) < creature.view_range + 90.0
            if (not player.dead
                    and (getattr(creature, "hostile", False)
                         or (player.nation != creature.nation
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
            if not player.dead and player.nation != creature.nation:
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
            if not player.dead and player.nation != creature.nation and not hidden:
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
