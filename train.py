"""train.py -- THE TEST ENGINE, AND WHAT IT RUNS INTO.

One locomotive that runs the whole network once, at five times a man's sprint,
and WRITES DOWN every solid thing it touches on the way -- a tree, a chunk of
iron, a fence, a house, a mine. People are ignored for now (nobody minds a
train yet).

Nothing here moves the world: it is a test that shows, in the game's own log,
whether the permanent way is actually clear.
"""

from __future__ import annotations

import math

import pygame
import plog

# a man's sprint is about 190 px/s; five times that
TRAIN_SPEED = 950.0
BODY = 34.0              # half-length of the engine, for contact
HALF_W = 16.0

_GREY = [(12, 12, 14), (18, 18, 21), (27, 27, 31), (38, 38, 43),
         (52, 52, 58), (70, 70, 78)]
RED = (186, 34, 28)
RED_D = (132, 22, 20)
_SURF: dict = {}
KNOCK: list = []           # bodies in the air
KILL_AHEAD = 130.0         # how far in front the buffer beam reaches
KILL_HALF = 46.0           # ...and how wide


def sprite() -> pygame.Surface:
    """The locomotive, drawn once: black, one red star on the nose."""
    got = _SURF.get("loco")
    if got is not None:
        return got
    L, W = 300, 64
    s = pygame.Surface((L, W), pygame.SRCALPHA)
    K0, K1, K2, K3, K4, K5 = _GREY

    def R(x, y, w, h, c, r=0):
        pygame.draw.rect(s, c, (x, y, w, h), 0, r)
    h2 = W // 2
    R(4, 6, L - 8, W - 12, K1, 10)
    pygame.draw.rect(s, K0, (4, 6, L - 8, W - 12), 2, 10)
    R(10, 10, 66, W - 20, K2, 4)
    pygame.draw.ellipse(s, K0, (16, 14, 54, W - 28))
    pygame.draw.ellipse(s, K3, (22, 17, 42, W - 34))
    R(76, 8, 4, W - 16, K0)
    R(80, 9, 58, W - 18, K3, 4)
    R(86, 14, 18, 16, K5); R(110, 14, 18, 16, K5)
    pygame.draw.rect(s, K0, (86, 14, 18, 16), 1)
    pygame.draw.rect(s, K0, (110, 14, 18, 16), 1)
    R(80, 9, 58, 4, K4)
    R(138, 12, 110, W - 24, K2, 3)
    for i in range(6):
        pygame.draw.line(s, K0, (146 + i * 17, 12), (146 + i * 17, W - 12), 2)
    pygame.draw.line(s, K4, (140, 15), (246, 15), 1)
    R(248, 13, 30, W - 26, K1, 3)
    for i in range(3):
        pygame.draw.line(s, K0, (252 + i * 9, 13), (252 + i * 9, W - 13), 1)
    R(278, 7, 14, W - 14, K0, 3)
    pygame.draw.rect(s, K3, (278, 7, 14, W - 14), 1, 3)
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = 9.5 if i % 2 == 0 else 9.5 * 0.44
        pts.append((285 + math.cos(a) * r, h2 + math.sin(a) * r))
    pygame.draw.polygon(s, RED, pts)
    pygame.draw.polygon(s, RED_D, pts, 1)
    pygame.draw.circle(s, K0, (196, h2 + 1), 13)
    pygame.draw.circle(s, K4, (194, h2), 12)
    pygame.draw.circle(s, K5, (194, h2), 7)
    pygame.draw.circle(s, K0, (194, h2), 7, 2)
    pygame.draw.circle(s, K3, (164, h2), 9)
    pygame.draw.circle(s, K4, (164, h2), 5)
    for wx in (30, 68, 120, 168, 214, 252):
        for sy in (3, W - 3):
            pygame.draw.circle(s, K0, (wx, sy), 5)
            pygame.draw.circle(s, K2, (wx, sy), 5, 1)
    R(292, h2 - 6, 6, 12, K1)
    pygame.draw.rect(s, K0, (292, h2 - 6, 6, 12), 1)
    _SURF["loco"] = s
    return s


class Knocked:
    """A BODY TAKEN BY THE BUFFER BEAM -- and it is funny, not real.

    Old-school: he pops a little way up off the sleepers, hangs there, and then
    topples away down the side of the track, slowly, and lies down. Nothing
    about it is a physics model; the joke is the point.
    """

    HOP = 0.70               # seconds in the air
    HOP_UP = 18.0            # how high he pops
    DRIFT = 250.0            # px/s sideways: he ends up OFF the sleepers
    TOTAL = 3.4              # the whole performance

    def __init__(self, victim, angle) -> None:
        self.victim = victim
        self.x = float(getattr(victim, "x", 0.0))
        self.y = float(getattr(victim, "y", 0.0))
        self.x0, self.y0 = self.x, self.y
        self.name = getattr(victim, "name", "a body")
        self.cloth = tuple(getattr(victim, "clothing", (150, 110, 70)))
        nx, ny = -math.sin(angle), math.cos(angle)      # across the line
        self.side = 1.0 if (hash(self.name) & 1) else -1.0
        self.nx, self.ny = nx * self.side, ny * self.side
        self.life = 0.0
        self.settled = False
        self.trail = 0.0
        self.angle = angle
        self.spin = 7.0 * self.side
        # mostly SIDEWAYS off the track, with a little of the engine's push
        self.vx = math.cos(angle) * 18.0 + self.nx * self.DRIFT
        self.vy = math.sin(angle) * 18.0 + self.ny * self.DRIFT

    def update(self, dt: float, blood=None, corpse_mod=None) -> None:
        if self.settled:
            return
        self.life += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        damp = 0.985 ** (dt * 60.0)
        self.vx *= damp
        self.vy *= damp
        self.angle += self.spin * dt
        self.spin *= 0.995 ** (dt * 60.0)
        self.trail += dt
        if blood is not None and self.life > self.HOP * 0.75 and self.trail >= 0.09:
            self.trail = 0.0
            try:
                blood.drip(self.x, self.y, 2)
            except Exception:
                pass
        if self.life >= self.TOTAL:
            self.settled = True
            try:
                if corpse_mod is not None:
                    corpse_mod.spawn(self.x, self.y, self.name, 0.0,
                                     self.cloth, {}, {})
            except Exception:
                pass

    def height(self) -> float:
        """How far off the ground he is: a pop up, and a fall."""
        if self.life >= self.HOP:
            return 0.0
        return self.HOP_UP * math.sin(math.pi * self.life / self.HOP)

    def draw(self, screen, cam_x: float, cam_y: float) -> None:
        if self.settled:
            return
        x = int(self.x - cam_x)
        y = int(self.y - cam_y - self.height())
        pygame.draw.circle(screen, self.cloth, (x, y), 10)
        pygame.draw.circle(screen, (44, 40, 36), (x, y), 10, 2)
        hx = x + int(math.cos(self.angle) * 8)
        hy = y + int(math.sin(self.angle) * 8)
        pygame.draw.circle(screen, (216, 172, 132), (hx, hy), 7)
        pygame.draw.circle(screen, (150, 112, 82), (hx, hy), 7, 1)
        try:
            import face
            face.draw(screen, hx, hy, 7, math.cos(self.angle),
                      math.sin(self.angle), "dead")     # the game's own X
        except Exception:
            pass


class Train:
    def __init__(self, route) -> None:
        self.route = route
        self.i = 0                      # the leg being run
        self.t = 0.0                    # progress along that leg
        self.x, self.y = (route[0] if route else (0.0, 0.0))
        self.angle = 0.0
        self.done = not route
        self.hits: set = set()
        self.aboard: list = []          # who is riding
        self.plan: list = []            # cells to call at, nearest first
        self.aboard_player = False
        self.travelled = 0.0
        self.started = False

    # -- movement ----------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.done:
            return
        step = TRAIN_SPEED * dt
        while step > 0.0 and self.i < len(self.route) - 1:
            ax, ay = self.route[self.i]
            bx, by = self.route[self.i + 1]
            seg = math.hypot(bx - ax, by - ay)
            if seg <= 1e-6:
                self.i += 1
                self.t = 0.0
                continue
            left = seg - self.t
            if step < left:
                self.t += step
                step = 0.0
            else:
                step -= left
                self.i += 1
                self.t = 0.0
                self.travelled += left
            ax, ay = self.route[self.i]
            nx, ny = (self.route[self.i + 1] if self.i + 1 < len(self.route)
                      else self.route[self.i])
            if abs(nx - ax) + abs(ny - ay) > 1e-6:
                self.angle = math.atan2(ny - ay, nx - ax)
        if self.i < len(self.route) - 1:
            ax, ay = self.route[self.i]
            bx, by = self.route[self.i + 1]
            seg = math.hypot(bx - ax, by - ay) or 1.0
            f = self.t / seg
            self.x = ax + (bx - ax) * f
            self.y = ay + (by - ay) * f
            self.angle = math.atan2(by - ay, bx - ax)
        else:
            self.done = True
            plog.log("TRAIN-DONE", "ran the whole network:",
                     int(self.travelled), "px |", "contacts:", len(self.hits))

    # -- the buffer beam ---------------------------------------------------
    def hit_people(self, townsmen=(), enemies=(), player=None, blood=None) -> int:
        """ANYTHING IN FRONT OF THE ENGINE IS DEAD.

        No damage roll and no armour: a body on the rails is taken by the
        buffer beam, thrown clear, and left where it stops.
        """
        killed = 0
        ax, ay = math.cos(self.angle), math.sin(self.angle)
        nx, ny = -ay, ax
        for who in list(townsmen) + list(enemies) + ([player] if player else []):
            if who is None or not getattr(who, "alive", True):
                continue
            dx, dy = who.x - self.x, who.y - self.y
            ahead = dx * ax + dy * ay
            across = abs(dx * nx + dy * ny)
            if ahead < -10 or ahead > KILL_AHEAD or across > KILL_HALF:
                continue
            try:
                who.take_damage(99999)
            except Exception:
                pass
            KNOCK.append(Knocked(who, self.angle))
            killed += 1
            try:
                plog.log("TRAIN-KILL", getattr(who, "name", "?") if who is not player
                         else "the player", "in front of the engine at",
                         int(who.x), int(who.y))
            except Exception:
                pass
        return killed

    def draw_knocked(self, screen, cam_x: float, cam_y: float) -> None:
        for k in KNOCK:
            k.draw(screen, cam_x, cam_y)

    # -- what it is touching ----------------------------------------------
    def note(self, kind, what, x, y) -> None:
        key = (kind, str(what))
        if key in self.hits:
            return
        self.hits.add(key)
        plog.log("TRAIN-HIT", kind, what, "at", int(x), int(y))

    def check(self, world, villages=(), houses=(), works=(), fences=()) -> None:
        """Log anything solid it is inside of. People are not checked."""
        if self.done:
            return
        px, py = self.x, self.y
        # AN ENGINE IS A LONG THING ON AN ANGLED LINE. An axis-aligned box
        # around it is half again too wide on a diagonal, and reported trees
        # the track was 45 px clear of as contacts. Distance from the engine's
        # centre is rotation-proof.
        reach = 36.0
        box = pygame.Rect(int(px - reach), int(py - reach),
                          int(reach * 2), int(reach * 2))
        try:
            for tr in world.trees.near(px, py, 70.0):
                if (not tr.felled
                        and math.hypot(tr.x - px, tr.y - py) <= reach):
                    self.note("tree", (int(tr.x), int(tr.y)), tr.x, tr.y)
        except Exception:
            pass
        try:
            field = getattr(world, "ore_field", None)
            if field is not None:
                for ch in field.visible(px - 90, py - 90, 180, 180, margin=0.0):
                    if box.colliderect(ch.rect):
                        self.note("ore", (int(ch.x), int(ch.y)), ch.x, ch.y)
        except Exception:
            pass
        for v in villages:
            fr = getattr(v, "fence_rect", None)
            if fr is None or not fr.inflate(400, 400).colliderect(box):
                continue
            for wall in getattr(v, "fence_walls", ()):
                if wall.colliderect(box):
                    self.note("fence", getattr(v, "name", "?"), px, py)
                    break
            for h in getattr(v, "houses", ()):
                if h.rect.colliderect(box):
                    self.note("house", getattr(v, "name", "?"), h.x, h.y)
        for h in houses:
            if h.rect.colliderect(box):
                self.note("building", (int(h.x), int(h.y)), h.x, h.y)
        for wp in works:
            if wp.rect.colliderect(box):
                self.note("work", getattr(wp, "kind", "?"), wp.x, wp.y)
        for r in fences:
            if r.colliderect(box):
                self.note("fence", (int(r.x), int(r.y)), r.centerx, r.centery)

    # -- drawing -----------------------------------------------------------
    def draw(self, screen, cam_x: float, cam_y: float) -> None:
        if self.done and self.i >= len(self.route) - 1:
            return
        img = sprite()
        rot = pygame.transform.rotozoom(img, -math.degrees(self.angle), 1.0)
        screen.blit(rot, (self.x - cam_x - rot.get_width() / 2,
                          self.y - cam_y - rot.get_height() / 2))
