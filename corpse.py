"""corpse.py -- THE DEAD STAY WHERE THEY FALL.

A man who dies does not vanish. He becomes a body on the ground: immovable, the
colour draining out of him over the next three days, and the blood where it
spat. A player who clicks him can open him like a chest and take what he was
carrying, or put something in.

    day 0 .. 3    a body, paling towards grey
    day 3 .. 6    bones
    after day 6   gone

Two things this deliberately does NOT do: it does not let the body move, and it
does not remove the blood -- the blood is the world's, not the corpse's, and a
man's last minute should still be readable on the ground after he is bones.
"""

from __future__ import annotations

import pygame

import inventory
import items

PALE_SECONDS = 3 * 600.0       # three days of a 10-minute day
BONES_SECONDS = 6 * 600.0      # three more, and the skeleton goes
CORPSES: list = []             # every body in the world
SPAWNED: list = []             # deaths reported this frame, drained by main
CLICK_PX = 34.0                # how close a click has to be to open him


class Corpse:
    """One body: where he fell, what he was carrying, and how long he has lain."""

    def __init__(self, x: float, y: float, name: str, died_at: float,
                 clothing=None, pack: dict | None = None,
                 grade: dict | None = None, facing=(0.0, 1.0),
                 folder: str | None = None) -> None:
        self.x = float(x)
        self.y = float(y)
        self.name = name or "a body"
        self.died_at = float(died_at)
        self.clothing = tuple(clothing or (150, 110, 70))
        fx, fy = facing or (0.0, 1.0)
        n = (fx * fx + fy * fy) ** 0.5 or 1.0
        self.facing = (fx / n, fy / n)
        self.pack = inventory.Inventory(32)
        if isinstance(pack, (list, tuple)):
            # STACK BY STACK, quality and payload intact: a worker's bag.
            for row in pack:
                try:
                    idx = self.pack.add(row[0], int(row[1]),
                                        row[2] if len(row) > 2 else None)
                    if idx is not None and len(row) > 3 and row[3]:
                        self.pack.slots[idx].payload = row[3]
                except Exception:
                    continue
        else:
            for item, count in (pack or {}).items():
                try:
                    n = int(count)
                except Exception:
                    continue
                if n > 0:
                    self.pack.add(item, n, (grade or {}).get(item))
        self.radius = 12.0
        if folder:
            # THE FOLDER IS HIS, not just any folder: the stack carries which.
            idx = self.pack.add("secret_folder", 1)
            if idx is not None and self.pack.slots[idx] is not None:
                self.pack.slots[idx].payload = folder

    # -- age ---------------------------------------------------------------
    def age(self, now: float) -> float:
        return max(0.0, float(now) - self.died_at)

    def is_bones(self, now: float) -> bool:
        return self.age(now) >= PALE_SECONDS

    def is_gone(self, now: float) -> bool:
        return self.age(now) >= BONES_SECONDS

    def pale(self, now: float) -> float:
        """0 = as he fell, 1 = grey, and bones after that."""
        return min(1.0, self.age(now) / PALE_SECONDS)

    # -- drawing -----------------------------------------------------------
    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             now: float) -> None:
        """A PERSON'S DIMENSIONS, DEAD.

        Exactly the body the living get -- the same 10-pixel body, the same
        8-pixel head, the same coat and outline -- with an X for each eye and
        his tongue out. The colour drains out of all of it over three days;
        after that the head is a skull and the body is ribs, in the same
        footprint, so the shape of the man is never lost.
        """
        if self.is_gone(now):
            return                        # the skeleton is gone: draw nothing
        import face
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        hx, hy = sx + fx * 2, sy + fy * 2 - 2
        p = self.pale(now)
        bones = self.is_bones(now)

        def grey(col):
            return (int(col[0] + (152 - col[0]) * p),
                    int(col[1] + (152 - col[1]) * p),
                    int(col[2] + (152 - col[2]) * p))

        pygame.draw.ellipse(screen, (20, 36, 20), (int(sx) - 12, int(sy) - 4,
                                                   24, 9))
        if bones:
            # the body is a ribcage, in the same 20-pixel footprint
            bone = (226, 220, 202)
            pygame.draw.circle(screen, bone, (int(sx), int(sy)), 10, 2)
            for i in range(3):
                yy = int(sy) - 5 + i * 4
                pygame.draw.line(screen, bone, (int(sx) - 7, yy),
                                 (int(sx) + 7, yy), 2)
            pygame.draw.line(screen, bone, (int(sx), int(sy) - 8),
                             (int(sx), int(sy) + 7), 2)
            # and the head is a skull
            pygame.draw.circle(screen, bone, (int(hx), int(hy)), 8)
            pygame.draw.circle(screen, (70, 64, 56), (int(hx), int(hy)), 8, 1)
            for sgn in (-1, 1):
                pygame.draw.circle(screen, (36, 32, 28),
                                   (int(hx + sgn * 3), int(hy) - 1), 2)
            for i in range(3):
                pygame.draw.line(screen, (70, 64, 56),
                                 (int(hx) - 3 + i * 3, int(hy) + 4),
                                 (int(hx) - 3 + i * 3, int(hy) + 6), 1)
            return

        body = grey(self.clothing)
        pygame.draw.circle(screen, body, (int(sx), int(sy)), 10)
        pygame.draw.circle(screen, (44, 40, 36), (int(sx), int(sy)), 10, 2)
        pygame.draw.circle(screen, grey((216, 172, 132)), (int(hx), int(hy)), 8)
        pygame.draw.circle(screen, (150, 112, 82), (int(hx), int(hy)), 8, 1)
        # THE DEAD FACE: X for each eye, tongue out -- and greying with him
        try:
            face.draw(screen, hx, hy, 8, fx, fy, "dead")
        except Exception:
            pass


# -- the world's list -------------------------------------------------------
def spawn(x: float, y: float, name: str, now: float, clothing=None,
          pack=None, grade=None, facing=(0.0, 1.0),
          folder=None) -> Corpse:
    """A man has died: leave him where he is."""
    body = Corpse(x, y, name, now, clothing, pack, grade, facing, folder)
    CORPSES.append(body)
    return body


def update(now: float) -> list:
    """Age them, and take out the ones that are gone."""
    gone = [c for c in CORPSES if c.is_gone(now)]
    if gone:
        CORPSES[:] = [c for c in CORPSES if not c.is_gone(now)]
    return gone


def draw(screen: pygame.Surface, cam_x: float, cam_y: float, now: float) -> None:
    for c in CORPSES:
        try:
            c.draw(screen, cam_x, cam_y, now)
        except Exception:
            pass


def nearest(x: float, y: float, within: float = CLICK_PX):
    """The body under that click, if there is one."""
    best, bd = None, float(within) * float(within)
    for c in CORPSES:
        d = (c.x - x) ** 2 + (c.y - y) ** 2
        if d <= bd:
            best, bd = c, d
    return best


def to_data() -> list:
    out = []
    for c in CORPSES:
        items_ = []
        for s in c.pack.slots:
            if s is not None:
                items_.append([s.defn.id, int(s.count), s.quality,
                           s.payload if isinstance(s.payload, str) else None])
        out.append([round(c.x, 1), round(c.y, 1), c.name, round(c.died_at, 1),
                    list(c.clothing), items_])
    return out


def from_data(recs) -> None:
    CORPSES.clear()
    for rec in recs or ():
        try:
            x, y, name, died_at, clothing, pack = rec
            body = Corpse(x, y, name, died_at, tuple(clothing))
            for row in pack or ():
                idx = body.pack.add(row[0], int(row[1]),
                                    row[2] if len(row) > 2 else None)
                if idx is not None and len(row) > 3 and row[3]:
                    body.pack.slots[idx].payload = row[3]
            CORPSES.append(body)
        except Exception:
            continue


def clear() -> None:
    CORPSES.clear()
