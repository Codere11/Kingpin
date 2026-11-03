"""A ranged enemy gunman.

He is not omniscient: he only notices the player when the player is inside his
own field of view -- within range, inside his cone, and not behind a wall or a
tree trunk. Until then he patrols around his home, scanning as he goes. Losing
sight of the player, he keeps looking for a few seconds, then goes back to it.
"""

from __future__ import annotations

import stats

import math
import random

import pygame

import face

from physics import avoid_direction, segment_rect_hit
import steering
import guns

BODY = (150, 52, 52)
BODY_DARK = (74, 24, 24)
HIT = (244, 226, 226)

AWARE_MEMORY = 5.0                   # seconds he keeps searching after losing sight
VIEW_ANGLE = math.radians(110.0)     # his own cone
VIEW_RANGE = 470.0                   # his own sight range


class Band:
    """A roaming bandit band: a moving camp that its members wander around."""

    def __init__(self, x: float, y: float, size: int = 3) -> None:
        self.x = x
        self.y = y
        self.target = (x, y)
        self.timer = 0.0
        self.members: list[Enemy] = []
        for _ in range(max(1, size)):
            member = Enemy(x + random.uniform(-60, 60), y + random.uniform(-60, 60))
            member.home = (x, y)
            self.members.append(member)

    def update(self, dt: float) -> None:
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
            speed = 62.0
            self.x += dx / distance * speed * dt
            self.y += dy / distance * speed * dt
        for member in self.members:
            member.home = (self.x, self.y)
        if any(member.aware for member in self.members):
            for member in self.members:
                member.aware = True
                member.aware_timer = max(member.aware_timer, 3.0)


CROWD = None        # f() -> everybody whose body must not be shot through
CIVILIANS = None    # f() -> the unarmed townsfolk, who always count


class Enemy:
    kind = "enemy"

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.home = (x, y)
        self.team = ("bandits", None)
        self.facing = (1.0, 0.0)
        # THE SAME BODY AS EVERYBODY ELSE (stats.py).
        self.max_health = stats.PLAYER_MAX_HEALTH
        self.health = self.max_health
        self.radius = 12
        self.speed = 118.0
        self.preferred = 300.0
        self.fire_cd = random.uniform(0.7, 1.5)
        self.hit_flash = 0.0
        self.bleed = 0.0
        self.drip_timer = 0.0
        self.phase = random.uniform(0.0, 5.0)
        # A soldier can be told about a murderer like anyone else -- an army
        # standing in a town hears the news with the townsfolk.
        self.knows: set = set()
        self.known_since: dict = {}
        # WHAT HE HAS SEEN OF THE WAR: the villages that fell while he was
        # there, who took them and how big the column was. Fifteen days and it
        # is stale news, like everybody else's.
        self.news: list = []
        self.strafe = random.choice((-1.0, 1.0))
        self.strafe_timer = random.uniform(1.0, 2.5)
        self.view_angle = VIEW_ANGLE
        self.view_range = VIEW_RANGE
        self.gun_kind = guns.RIFLE
        self.mag = guns.MAG[guns.RIFLE]
        self.reload_timer = 0.0
        self.shoot_skill = random.uniform(0.1, 0.85)

        self.aware = False
        self.aware_timer = 0.0
        self.target = (x, y)
        self.idle_timer = random.uniform(1.0, 3.0)
        self.patrol_speed = 52.0
        self.scan_dir = random.choice((-1.0, 1.0))
        self._colliders = []
        self.last_seen = None

    @property
    def alive(self) -> bool:
        return self.health > 0

    def learn(self, ids, now: float) -> bool:
        """Told something, and when. Returns True if it was news to him."""
        ids = set(ids)
        if not ids:
            return False
        news = bool(ids - self.knows)
        for i in ids:
            if i not in self.knows:
                self.known_since[i] = now
        self.knows |= ids
        return news

    def forget(self, now: float) -> bool:
        """A soldier forgets on the same thirty-day clock as everyone else."""
        if not self.known_since:
            return False
        import village as _village        # imported here, not at the top:
        limit = _village.FORGET_AFTER     # one definition, no import cycle
        gone = [i for i, told_at in self.known_since.items()
                if now - told_at >= limit or _village.story_cold(i, now)]
        for i in gone:
            self.known_since.pop(i, None)
            self.knows.discard(i)
        return bool(gone)

    # The war face and the hurt face, as class defaults: a soldier who has
    # neither struck nor been struck must not be missing what the draw reads.
    hurt_flash: float = 0.0
    attack_flash: float = 0.0

    sleep_t: float = 0.0      # a dart put him down
    held_fire: int = 0        # shots he did not take, for the log

    def take_damage(self, amount: int, tranq: bool = False) -> bool:
        self.health -= amount
        self.hit_flash = 0.15
        self.hurt_flash = face.HURT_SECONDS
        self.bleed = 6.0
        self.aware = True                # being shot gets his attention
        self.aware_timer = AWARE_MEMORY
        if tranq and self.health <= 0:
            # A DART: same damage, but at zero he sleeps -- he does not die.
            self.health = 1
            self.sleep_t = 22.0
            self.bleed = 0.0
            try:
                import plog
                plog.log("TRANQ", getattr(self, "name", "?"), "asleep")
            except Exception:
                pass
            return False
        return self.health <= 0

    # -- perception ---------------------------------------------------------
    def _tick_gun(self, dt: float) -> None:
        if self.reload_timer > 0.0:
            self.reload_timer = max(0.0, self.reload_timer - dt)
            if self.reload_timer == 0.0:
                self.mag = guns.MAG[self.gun_kind]

    def _round_ready(self) -> bool:
        """True if a round is ready (and it is spent); otherwise begins a
        reload so the gunman pauses with an empty magazine."""
        if self.reload_timer > 0.0:
            return False
        if self.mag <= 0:
            self.reload_timer = guns.reload_time(self.gun_kind, self.shoot_skill)
            return False
        self.mag -= 1
        return True

    def lane_clear(self, x, y, angle, distance, tx=None, ty=None) -> bool:
        """NO SHOT THROUGH A CROWD.

        The player running into a knot of townspeople used to draw fire at
        whatever stood behind him: a round took the baker, the baker's friend
        turned on the guard, and the square ate itself. A gunman now waits
        for a clear line: nothing of his own -- man, woman or child -- inside
        the corridor between the muzzle and the target.
        """
        if CROWD is None:
            return True
        try:
            crowd = CROWD() or ()
        except Exception:
            return True
        if tx is None:
            tx = x + math.cos(angle) * distance
            ty = y + math.sin(angle) * distance
        civil = set()
        try:
            civil = set(CIVILIANS() or ()) if CIVILIANS is not None else set()
        except Exception:
            civil = set()
        for o in crowd:
            if o is self or o is None or not getattr(o, "alive", True):
                continue
            if o is tx or o is ty:
                continue
            if isinstance(o, (tuple, list)):
                ox, oy = float(o[0]), float(o[1])
                friend = True                    # a bare point is a body to spare
            else:
                ox, oy = getattr(o, "x", 0.0), getattr(o, "y", 0.0)
                friend = (o in civil
                          or getattr(o, "nation", None) == getattr(self, "nation", object())
                          or getattr(o, "is_militia", False)
                          or getattr(o, "gulag", False))
            if not friend:
                continue
            # cheap reject: far outside the muzzle-to-target box
            if (ox < min(x, tx) - 40.0 or ox > max(x, tx) + 40.0
                    or oy < min(y, ty) - 40.0 or oy > max(y, ty) + 40.0):
                continue
            # inside the corridor? (point-to-segment distance, and nearer than
            # the target)
            dx, dy = tx - x, ty - y
            L = dx * dx + dy * dy
            if L < 1e-9:
                continue
            t = ((ox - x) * dx + (oy - y) * dy) / L
            if t <= 0.0 or t >= 1.0:
                continue
            off = math.hypot(ox - (x + dx * t), oy - (y + dy * t))
            if off <= 26.0:
                return False
        return True

    def _shoot(self, combat, x, y, angle, distance, dmg_lo, dmg_hi,
               tx=None, ty=None) -> None:
        """A shot: one round for a rifle, a spread of pellets for a shotgun.

        THE SAME ROUND AS THE PLAYER'S: `guns.DAMAGE` and nothing else. The
        old per-caller numbers (8 to 14) made an armed man a nuisance instead
        of a threat -- a rifle now takes eighty health off whoever it hits.
        """
        kind = getattr(self, "gun_kind", guns.RIFLE)
        _dmg = guns.DAMAGE[kind]
        if not self.lane_clear(x, y, angle, distance, tx, ty):
            self.held_fire += 1
            if self.held_fire in (1, 10, 50):
                try:
                    import plog
                    plog.log("HELD-FIRE", getattr(self, "name", "?"),
                             "did not shoot:", self.held_fire, "refusals",
                             "| a body of ours is in the line")
                except Exception:
                    pass
            return
        for _ in range(guns.PELLETS[kind]):
            a = angle + random.uniform(-0.07, 0.07)
            combat.fire(x, y, a, distance, owner="enemy", shooter=self,
                        damage=_dmg, team=self.team)

    def _can_see(self, player, occluders, view_scale: float) -> bool:
        dx, dy = player.x - self.x, player.y - self.y
        distance = math.hypot(dx, dy)
        if distance > self.view_range * view_scale:
            return False
        facing = math.atan2(self.facing[1], self.facing[0])
        delta = abs(((math.atan2(dy, dx) - facing + math.pi) % (2.0 * math.pi)) - math.pi)
        if delta > self.view_angle / 2.0:
            return False
        if occluders:
            # Cheap rejection first. A wall nowhere near the sight line cannot
            # block it, and testing all ninety of a village's houses with full
            # segment maths, four hundred times a frame, was tens of
            # milliseconds on its own.
            sx, sy, px, py = self.x, self.y, player.x, player.y
            lox, hix = (sx, px) if sx < px else (px, sx)
            loy, hiy = (sy, py) if sy < py else (py, sy)
            for rect in occluders:
                if (rect.right < lox or rect.left > hix
                        or rect.bottom < loy or rect.top > hiy):
                    continue
                if segment_rect_hit(sx, sy, px, py, rect):
                    return False
        return True

    # -- update -------------------------------------------------------------
    def update(self, dt: float, target, combat, occluders=None,
               speed_scale: float = 1.0, view_scale: float = 1.0,
               visible: bool = True, colliders=None) -> None:
        self._colliders = colliders or []
        self._tick_gun(dt)
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if self.bleed > 0.0:
            self.bleed = max(0.0, self.bleed - dt)
        if not self.alive:
            return

        if self.aware:
            self.aware_timer -= dt
            if self.aware_timer <= 0.0:
                self.aware = False
        if target is None:
            self.aware = False
            self._patrol(dt)
            return
        sees = (visible and not getattr(target, "dead", False)
                and self._can_see(target, occluders, view_scale))
        if sees:
            self.aware = True
            self.aware_timer = AWARE_MEMORY
            self.last_seen = (target.x, target.y)

        if sees:
            self._fight(dt, target, combat, speed_scale, visible)
        elif self.aware:
            self._search(dt)          # lost them: hunt the trail
        else:
            self._patrol(dt)

    def _search(self, dt: float) -> None:
        """Lost sight: go to the last seen spot, following fresh blood if any."""
        goal = None
        blood = getattr(self, "_blood", None)
        if blood is not None:
            goal = blood.freshest_near(self.x, self.y, 400.0)
        if goal is None:
            goal = self.last_seen
        if goal is None:
            self._patrol(dt)
            return
        dx, dy = goal[0] - self.x, goal[1] - self.y
        dist = math.hypot(dx, dy)
        if dist < 12.0:
            if goal is self.last_seen:
                self.last_seen = None
            return
        ux, uy = dx / dist, dy / dist
        ux, uy = self._steer(ux, uy)
        speed = self.patrol_speed * 1.8
        self.x += ux * speed * dt
        self.y += uy * speed * dt
        self.facing = (ux, uy)

    def wind_scale(self) -> float:
        """Winded entities move at six tenths; wolves are never winded."""
        return 0.6 if getattr(self, "exhausted", False) else 1.0

    def _fight(self, dt: float, target, combat, speed_scale: float,
               visible: bool = True) -> None:
        dx, dy = target.x - self.x, target.y - self.y
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = dx / distance, dy / distance
        self.facing = (ux, uy)
        _sk = getattr(self, "skills", None)      # wolves have none
        speed = (self.speed * speed_scale * (_sk.move_scale() if _sk else 1.0)
                 * self.wind_scale())

        if distance < self.preferred - 70.0:
            self.x -= ux * speed * dt
            self.y -= uy * speed * dt
        elif distance > self.preferred + 70.0:
            self.x += ux * speed * 1.6 * dt      # sprint to close the gap
            self.y += uy * speed * 1.6 * dt
        else:
            self.strafe_timer -= dt
            if self.strafe_timer <= 0.0:
                self.strafe *= -1.0
                self.strafe_timer = random.uniform(1.0, 2.5)
            self.x += -uy * self.strafe * speed * 0.6 * dt
            self.y += ux * self.strafe * speed * 0.6 * dt

        self.fire_cd -= dt
        # A GUARD CARRIES THIRTY ROUNDS. None means unlimited, which is what
        # every other soldier in the game still has.
        _ammo = getattr(self, "ammo", None)
        if _ammo is not None and _ammo <= 0:
            return
        _n = guns.rounds_now(self, dt, self.fire_cd <= 0.0 and distance <= 520.0
                             and visible
                             and not getattr(target, "dead", False))
        for _ in range(_n):
            if _ammo is not None and _ammo <= 0:
                break
            if not self._round_ready():
                break
            if _ammo is not None:
                _ammo -= 1
                self.ammo = _ammo
            if self.fire_cd <= 0.0:
                self.fire_cd = random.uniform(0.5, 0.9)
            angle = math.atan2(dy, dx) + random.uniform(-0.03, 0.03)
            muzzle_x = self.x + ux * 20.0
            muzzle_y = self.y + uy * 20.0
            self._shoot(combat, muzzle_x, muzzle_y, angle, distance + 160.0,
                        80, 80, tx=getattr(target, 'x', None),
                        ty=getattr(target, 'y', None))

    def _patrol(self, dt: float) -> None:
        if self.idle_timer > 0.0:
            self.idle_timer -= dt
            angle = math.atan2(self.facing[1], self.facing[0]) + self.scan_dir * 0.9 * dt
            self.facing = (math.cos(angle), math.sin(angle))
            if self.idle_timer <= 0.0:
                angle = random.uniform(0.0, 2.0 * math.pi)
                radius = random.uniform(60.0, 320.0)
                self.target = (self.home[0] + math.cos(angle) * radius,
                               self.home[1] + math.sin(angle) * radius)
            return

        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        if distance < 6.0:
            self.idle_timer = random.uniform(1.5, 4.0)
            return
        ux, uy = steering.steer(self, tx, ty, getattr(self, "_rects", ()),
                                getattr(self, "_fences", ()))
        self.x += ux * self.patrol_speed * dt
        self.y += uy * self.patrol_speed * dt
        self.facing = (ux, uy)

    def _steer(self, ux: float, uy: float):
        return avoid_direction(self.x, self.y, ux, uy, self.radius, self._colliders)

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        sx = self.x - cam_x
        sy = self.y - cam_y
        fx, fy = self.facing

        pygame.draw.ellipse(screen, (22, 12, 12), (sx - 13, sy - 4, 26, 10))
        pygame.draw.line(screen, (32, 32, 38), (sx, sy), (sx + fx * 24, sy + fy * 24), 4)

        body = HIT if self.hit_flash > 0.0 else BODY
        pygame.draw.circle(screen, body, (int(sx), int(sy)), 11)
        pygame.draw.circle(screen, BODY_DARK, (int(sx), int(sy)), 11, 2)
        pygame.draw.circle(screen, (214, 168, 128),
                           (int(sx + fx * 2), int(sy + fy * 2 - 2)), 6)
        pygame.draw.circle(screen, (140, 100, 72),
                           (int(sx + fx * 2), int(sy + fy * 2 - 2)), 6, 1)
