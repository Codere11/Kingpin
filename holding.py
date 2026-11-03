"""holding.py -- A CELL BY THE END OF THE LINE.

One small grey concrete box standing on the empty ground beside each
settlement's railway, with a dark doorway, the word дыра above it, and inside
one dark room: bare concrete, a hole in the floor, nothing else.

It is built like the barn: a workplace-shaped solid with a room you enter by
walking through the door, drawn as one cached picture.
"""

from __future__ import annotations

import math

import pygame
import plog

C1 = (96, 96, 100)
C2 = (120, 120, 124)
C3 = (78, 78, 82)
C4 = (58, 58, 62)
C5 = (40, 40, 44)
DARK = (16, 16, 18)
SIGN_BG = (30, 30, 32)

W, H = 92, 68                    # the building, in world pixels
CLEAR = 120.0                    # no track or building this close to it

_CELLS: list = []
_IMG: dict = {}


class CellRoom:
    """THE INSIDE: dark concrete, and a hole in the floor."""

    W, H = 620, 440
    is_prison = True             # no seam to mine, no seam to swing at
    is_cell = True

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.flash = 0.0
        self.image = self._render(seed)

    def _render(self, seed: int) -> pygame.Surface:
        import random as _r
        W, H = self.W, self.H
        rng = _r.Random((seed or 3) & 0x7FFFFFFF)
        s = pygame.Surface((W, H))
        s.fill(C5)                                   # the walls
        floor = pygame.Rect(36, 36, W - 72, H - 72)
        pygame.draw.rect(s, C3, floor)
        for _ in range(1600):                        # bare, stained concrete
            x = rng.randrange(floor.left, floor.right)
            y = rng.randrange(floor.top, floor.bottom)
            v = rng.randrange(64, 88)
            pygame.draw.rect(s, (v, v, v + 2), (x, y, rng.randrange(2, 8),
                                                rng.randrange(1, 4)))
        for _ in range(30):
            x = rng.randrange(floor.left + 10, floor.right - 10)
            y = rng.randrange(floor.top + 10, floor.bottom - 10)
            for _k in range(rng.randrange(2, 5)):
                pygame.draw.circle(s, (34, 34, 36),
                                   (x + rng.randrange(-12, 12),
                                    y + rng.randrange(-8, 8)), rng.randrange(2, 6))
        # the hole
        hx, hy = floor.centerx, floor.centery
        pygame.draw.ellipse(s, (10, 10, 12), (hx - 32, hy - 22, 64, 44))
        pygame.draw.ellipse(s, (28, 28, 30), (hx - 32, hy - 22, 64, 44), 3)
        # the doorway, from inside
        pygame.draw.rect(s, (10, 10, 12), (W // 2 - 34, H - 36, 68, 36))
        return s

    def update(self, dt: float) -> None:
        self.flash = max(0.0, self.flash - dt)

    def clamp(self, x: float, y: float) -> tuple:
        return (min(max(x, 44.0), self.W - 44.0),
                min(max(y, 44.0), self.H - 44.0))

    def hits_chunk(self, x: float, y: float) -> bool:
        return False

    def swing(self, yields=(0, 0)):
        return 0

    def draw(self, screen, cam_x: float, cam_y: float, vw: int = 0,
             vh: int = 0) -> None:
        w = vw or screen.get_width()
        h = vh or screen.get_height()
        screen.fill((8, 8, 10), (0, 0, w, h))
        screen.blit(self.image, (int(-cam_x), int(-cam_y)))


class Cell:
    """The building itself: grey concrete, dark door, дыра over it."""

    kind = "cell"

    def __init__(self, x: float, y: float, seed: int = 0) -> None:
        self.x, self.y = float(x), float(y)
        self.w, self.h = W, H
        self.rect = pygame.Rect(int(x - W / 2), int(y - H / 2), W, H)
        self.base_y = y + H / 2.0
        self.sight_rect = self.rect.inflate(24, 24)
        self.door = (x, y + H / 2.0 + 8.0)
        self.worker = None
        self.owner = None
        self.camp = True                 # built with the world, never saved
        self.name = "the holding cell"
        self.seed = seed
        self.room = CellRoom(seed)
        self.image = _picture()

    def draw(self, screen, cam_x: float, cam_y: float) -> None:
        screen.blit(self.image, (self.x - cam_x - self.image.get_width() / 2,
                                 self.y - cam_y - self.image.get_height() / 2))


def _picture() -> pygame.Surface:
    """THE CELL AS YOU SEE IT: a concrete front, and дыра written on it.

    A direct elevation -- wall, doorway, two barred windows -- and the word
    painted ON the concrete above the door, not on a plate in front of it.
    """
    got = _IMG.get("cell")
    if got is not None:
        return got
    pad = 8
    s = pygame.Surface((W + pad * 2, H + pad * 3), pygame.SRCALPHA)
    ox, oy = pad, pad * 2
    # the shadow at its feet
    pygame.draw.ellipse(s, (16, 16, 18, 120), (ox + 6, oy + H - 6, W - 12, 14))
    # roof lip, then the concrete face
    pygame.draw.rect(s, C3, (ox - 6, oy - 8, W + 12, 12))
    pygame.draw.rect(s, C4, (ox - 6, oy - 8, W + 12, 12), 2)
    face = pygame.Rect(ox, oy + 2, W, H - 2)
    pygame.draw.rect(s, C2, face)
    import random as _r
    rng = _r.Random(5)
    for _ in range(90):                        # stains and runs down the wall
        x = rng.randrange(face.left + 2, face.right - 2)
        y = rng.randrange(face.top + 2, face.bottom - 2)
        v = rng.randrange(98, 128)
        pygame.draw.rect(s, (v, v, v + 1), (x, y, rng.randrange(1, 5),
                                            rng.randrange(2, 8)))
    pygame.draw.rect(s, C4, face, 3)
    # the doorway: black, split by a bar
    door = pygame.Rect(face.centerx - 20, face.bottom - 34, 40, 34)
    pygame.draw.rect(s, DARK, door)
    pygame.draw.rect(s, C4, door, 2)
    pygame.draw.line(s, C5, (door.centerx, door.top + 3), (door.centerx,
                                                           door.bottom - 2), 2)
    # barred window each side of it
    for wx in (face.left + 10, face.right - 30):
        win = pygame.Rect(wx, door.top + 4, 20, 16)
        pygame.draw.rect(s, (26, 26, 28), win)
        for bx in range(win.left + 4, win.right, 6):
            pygame.draw.line(s, (150, 150, 154), (bx, win.top), (bx, win.bottom), 1)
        pygame.draw.rect(s, C4, win, 1)
    # дыра, ON THE WALL above the door: light paint, worn edges
    font = pygame.font.SysFont("dejavusans", 16, bold=True)
    t = font.render("дыра", True, (226, 226, 230))
    tx = face.centerx - t.get_width() // 2
    ty = door.top - t.get_height() - 8
    s.blit(t, (tx, ty))                        # painted directly on the concrete
    pygame.draw.line(s, (150, 150, 154), (tx - 2, ty + t.get_height() - 1),
                     (tx + t.get_width() + 1, ty + t.get_height() - 1), 1)
    _IMG["cell"] = s
    return s


def cells() -> list:
    return list(_CELLS)


def build(towns) -> int:
    """One cell beside each settlement's railway, on the empty ground."""
    _CELLS.clear()
    try:
        import rail
        rail.ensure(towns)
    except Exception:
        pass
    made = 0
    for v in towns:
        if getattr(v, "is_hub", False):
            continue
        fr = getattr(v, "fence_rect", None)
        if fr is None:
            continue
        best = None
        for side, gx, gy in _gates(v):
            ox, oy = _outward(side)
            # step out past the rail ring, on the empty side of the track
            for dist in (240.0, 340.0, 460.0, 620.0):
                x, y = gx + ox * dist, gy + oy * dist
                if fr.inflate(120, 120).collidepoint(x, y):
                    continue
                if _too_close_to_track(x, y):
                    continue
                if best is None:
                    best = (x, y)
                break
            if best is not None:
                break
        if best is None:
            continue
        _CELLS.append(Cell(best[0], best[1], int(abs(v.code)) & 0x7FFFFFFF))
        made += 1
    try:
        plog.log("CELLS", "holding cells built:", made)
    except Exception:
        pass
    return made


def _gates(v):
    try:
        import fence
        return fence.gate_list(v)
    except Exception:
        return []


def _outward(side):
    return {0: (0.0, -1.0), 1: (1.0, 0.0), 2: (0.0, 1.0), 3: (-1.0, 0.0)}.get(side,
                                                                               (0.0, 1.0))


def _too_close_to_track(x, y) -> bool:
    """THE WHOLE BUILDING, not just its middle: corners and edges too."""
    try:
        import rail
        half_w, half_h = W / 2.0 + 30.0, H / 2.0 + 30.0
        for dx in (-half_w, 0.0, half_w):
            for dy in (-half_h, 0.0, half_h):
                if rail.blocked(x + dx, y + dy, 40.0):
                    return True
        return False
    except Exception:
        return False
