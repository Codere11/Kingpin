"""House interiors.

A room that is bigger than the house looks from outside, but scaled to the
player (a person is 24 px across). Walls and windows are solid -- you cannot
walk through any of them -- but windows are transparent, so the outside world
drawn behind the room is visible through them. The door is the only way out.
"""

from __future__ import annotations

import math
import random

import pygame

from inventory import Inventory

W = 640                  # room size, in world pixels (player is 24 px wide)
H = 420
T = 18                   # wall thickness
WIN = 56                 # window opening size
DOOR_W = 52
WORKSHOP_W = 68          # a workshop's footprint on the floor
WORKSHOP_H = 46
LAB_W = 76               # a laboratory bench
LAB_H = 50
BREW_W = 80              # a brewing table
BREW_H = 52
BARREL_W = 36            # a fermenting barrel
BARREL_H = 44

FLOOR = (150, 112, 74)
FLOOR_LINE = (130, 96, 62)
WALL = (126, 90, 62)
WALL_TOP = (156, 116, 82)
WALL_DARK = (74, 50, 34)


def fill_loot(chest, rng=None) -> None:
    """Populate a villager's chest: usually tobacco and ammo, rarely a rifle,
    and sometimes (but not often) nothing at all."""
    rng = rng if rng is not None else random
    if rng.random() < 0.10:                        # genuinely empty
        return
    got = False
    if rng.random() < 0.72:
        chest.add("tobacco", rng.randint(3, 15), rng.randint(0, 3))
        got = True
    if rng.random() < 0.65:
        chest.add("ammo", rng.randint(5, 20))
        got = True
    if rng.random() < 0.55:
        chest.add("coin", rng.randint(1, 8))
        got = True
    if rng.random() < 0.40:
        chest.add("seed_bag", rng.randint(2, 6))
        got = True
    if rng.random() < 0.35:
        chest.add("bread", rng.randint(1, 3))
        got = True
    if rng.random() < 0.45:
        chest.add("wheat_seed", rng.randint(2, 5))
        got = True
    if rng.random() < 0.06:                        # rare rifle
        chest.add("rifle", 1)
        got = True
    if not got:                                    # never totally bare otherwise
        chest.add("tobacco", rng.randint(2, 8))


def _segments(a, b, gaps):
    segments = []
    current = a
    for g0, g1 in sorted(gaps):
        if g0 > current:
            segments.append((current, g0))
        current = max(current, g1)
    if current < b:
        segments.append((current, b))
    return segments


def _rot_pt(x, y, w, h, k):
    if k == 0:
        return (x, y)
    if k == 1:
        return (y, w - x)
    if k == 2:
        return (w - x, h - y)
    return (h - y, x)


def _rot_rect(rect, w, h, k):
    if k == 0:
        return pygame.Rect(rect)
    pts = [_rot_pt(rect.left, rect.top, w, h, k),
           _rot_pt(rect.right, rect.top, w, h, k),
           _rot_pt(rect.left, rect.bottom, w, h, k),
           _rot_pt(rect.right, rect.bottom, w, h, k)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _door_rotation(facing):
    """Which way to turn the room so the door matches the house's door."""
    fx, fy = facing
    if fx > 0:
        return 1          # door faces east  -> door on the right wall
    if fx < 0:
        return 3          # faces west       -> door on the left wall
    if fy < 0:
        return 2          # faces north      -> door on the top wall
    return 0              # faces south      -> door on the bottom wall


class Interior:
    def __init__(self, seed: int, facing=(0.0, 1.0), width=None, height=None,
                 windows: bool = True, grand: bool = False) -> None:
        self.rng = random.Random(seed & 0xFFFFFFFF)
        k = _door_rotation(facing)
        w, h = width or W, height or H
        self.grand = grand

        # A government building has no windows: nobody looks in on the state.
        top_gaps = ([(w * 0.34 - WIN / 2, w * 0.34 + WIN / 2),
                     (w * 0.66 - WIN / 2, w * 0.66 + WIN / 2)] if windows else [])
        side_gaps = ([(h * 0.5 - WIN / 2, h * 0.5 + WIN / 2)] if windows else [])
        door_gap = (w / 2 - DOOR_W / 2, w / 2 + DOOR_W / 2)

        wall_rects: list[pygame.Rect] = []
        for x0, x1 in _segments(0, w, top_gaps):
            wall_rects.append(pygame.Rect(x0, 0, x1 - x0, T))
        for x0, x1 in _segments(0, w, [door_gap]):
            wall_rects.append(pygame.Rect(x0, h - T, x1 - x0, T))
        for y0, y1 in _segments(T, h - T, side_gaps):
            wall_rects.append(pygame.Rect(0, y0, T, y1 - y0))
            wall_rects.append(pygame.Rect(w - T, y0, T, y1 - y0))

        window_rects: list[pygame.Rect] = []
        for g0, g1 in top_gaps:
            window_rects.append(pygame.Rect(g0, 0, g1 - g0, T))
        for g0, g1 in side_gaps:
            window_rects.append(pygame.Rect(0, g0, T, g1 - g0))
            window_rects.append(pygame.Rect(w - T, g0, T, g1 - g0))
        window_barriers = [pygame.Rect(r) for r in window_rects]

        door_rect = pygame.Rect(door_gap[0], h - T, DOOR_W, T + 14)
        spawn = (w / 2.0, h - T - 30.0)
        if grand:                        # a hall, not a home
            furniture = [
                ("throne", pygame.Rect(w / 2 - 34, 54, 68, 54)),
                ("table", pygame.Rect(w / 2 - 150, h * 0.52, 300, 64)),
                ("desk", pygame.Rect(70, 90, 120, 46)),
                ("desk", pygame.Rect(w - 190, 90, 120, 46)),
                ("shelf", pygame.Rect(60, h - 150, 150, 34)),
                ("shelf", pygame.Rect(w - 210, h - 150, 150, 34)),
                ("rug", pygame.Rect(w / 2 - 190, h * 0.30, 380, h * 0.42)),
                ("brazier", pygame.Rect(40, h / 2 - 20, 30, 30)),
                ("brazier", pygame.Rect(w - 70, h / 2 - 20, 30, 30)),
                ("banner", pygame.Rect(w / 2 - 90, 20, 180, 26)),
            ]
        else:
            furniture = [
                ("bed", pygame.Rect(30, 30, 46, 74)),
                ("table", pygame.Rect(w / 2 - 26, 168, 52, 32)),
                ("crate", pygame.Rect(30, h - 84, 26, 26)),
            ("shelf", pygame.Rect(w - 100, 36, 70, 22)),
            ("fireplace", pygame.Rect(w / 2 - 40, T, 80, 26)),
        ]
        rug = pygame.Rect(w / 2 - 70, 150, 140, 100)
        plant = (w - 36, h - 36)
        chest_rect = pygame.Rect(w - 86, h - 132, 44, 28)

        if k:                                   # turn the whole room
            wall_rects = [_rot_rect(r, w, h, k) for r in wall_rects]
            window_rects = [_rot_rect(r, w, h, k) for r in window_rects]
            window_barriers = [_rot_rect(r, w, h, k) for r in window_barriers]
            door_rect = _rot_rect(door_rect, w, h, k)
            spawn = _rot_pt(spawn[0], spawn[1], w, h, k)
            furniture = [(kind, _rot_rect(r, w, h, k)) for kind, r in furniture]
            rug = _rot_rect(rug, w, h, k)
            plant = _rot_pt(plant[0], plant[1], w, h, k)
            chest_rect = _rot_rect(chest_rect, w, h, k)

        self.W, self.H = (h, w) if k in (1, 3) else (w, h)
        self.T = T
        self.wall_rects = wall_rects
        self.window_rects = window_rects
        self.window_barriers = window_barriers
        self.door_rect = door_rect
        self.spawn = spawn
        self.furniture = furniture
        self.rug = rug
        self.plant = plant
        self.chest_rect = chest_rect
        self.chest = Inventory(64)          # double the player's 32 slots
        self.workshops: list[pygame.Rect] = []
        self.lab_tables: list[pygame.Rect] = []
        self.brew_tables: list[pygame.Rect] = []
        self.barrels: list[dict] = []

        self.colliders: list[pygame.Rect] = (list(self.wall_rects)
                                             + list(self.window_barriers)
                                             + [rect for _k, rect in self.furniture]
                                             + [self.chest_rect])
        self.occluders: list[pygame.Rect] = list(self.wall_rects) + [
            rect for kind, rect in self.furniture
            if kind in ("bed", "table", "fireplace", "shelf")]

    # -- workshops ----------------------------------------------------------
    def can_place_workshop(self, rect: pygame.Rect) -> bool:
        """A workshop needs clear floor inside the room, clear of furniture."""
        inner = pygame.Rect(T + 6, T + 6, self.W - 2 * T - 12, self.H - 2 * T - 12)
        if not inner.contains(rect):
            return False
        return not any(rect.colliderect(c) for c in self.colliders)

    def place_workshop(self, x: float, y: float) -> pygame.Rect:
        rect = pygame.Rect(int(x - WORKSHOP_W / 2), int(y - WORKSHOP_H / 2),
                           WORKSHOP_W, WORKSHOP_H)
        self.workshops.append(rect)
        self.colliders.append(rect)
        self.occluders.append(rect)
        return rect

    def can_place_lab(self, rect: pygame.Rect) -> bool:
        return self.can_place_workshop(rect)

    def place_lab(self, x: float, y: float) -> pygame.Rect:
        rect = pygame.Rect(int(x - LAB_W / 2), int(y - LAB_H / 2), LAB_W, LAB_H)
        self.lab_tables.append(rect)
        self.colliders.append(rect)
        self.occluders.append(rect)
        return rect

    def can_place_brew(self, rect: pygame.Rect) -> bool:
        return self.can_place_workshop(rect)

    def place_brew(self, x: float, y: float) -> pygame.Rect:
        rect = pygame.Rect(int(x - BREW_W / 2), int(y - BREW_H / 2), BREW_W, BREW_H)
        self.brew_tables.append(rect)
        self.colliders.append(rect)
        self.occluders.append(rect)
        return rect

    def brew_near(self, x: float, y: float, pad: float = 46.0) -> bool:
        for rect in self.brew_tables:
            if (math.hypot(x - rect.centerx, y - rect.centery)
                    < max(rect.w, rect.h) / 2.0 + pad):
                return True
        return False

    def can_place_barrel(self, rect: pygame.Rect) -> bool:
        return self.can_place_workshop(rect)

    def place_barrel(self, x: float, y: float) -> dict:
        rect = pygame.Rect(int(x - BARREL_W / 2), int(y - BARREL_H / 2),
                           BARREL_W, BARREL_H)
        barrel = {"rect": rect, "kind": None, "count": 0, "ready_at": 0.0,
                  "grade": 0}
        self.barrels.append(barrel)
        self.colliders.append(rect)
        self.occluders.append(rect)
        return barrel

    def barrel_near(self, x: float, y: float, pad: float = 40.0):
        """The nearest barrel within arm's reach, or None."""
        best = None
        for b in self.barrels:
            r = b["rect"]
            d = math.hypot(x - r.centerx, y - r.centery)
            if d < max(r.w, r.h) / 2.0 + pad and (best is None or d < best[0]):
                best = (d, b)
        return best[1] if best else None

    def lab_near(self, x: float, y: float, pad: float = 46.0) -> bool:
        for rect in self.lab_tables:
            if (math.hypot(x - rect.centerx, y - rect.centery)
                    < max(rect.w, rect.h) / 2.0 + pad):
                return True
        return False

    def workshop_near(self, x: float, y: float, pad: float = 46.0) -> bool:
        for rect in self.workshops:
            if (math.hypot(x - rect.centerx, y - rect.centery)
                    < max(rect.w, rect.h) / 2.0 + pad):
                return True
        return False

    def fireplace_near(self, x: float, y: float, pad: float = 40.0) -> bool:
        for kind, rect in self.furniture:
            if kind == "fireplace" and (math.hypot(x - rect.centerx, y - rect.centery)
                                        < max(rect.w, rect.h) / 2.0 + pad):
                return True
        return False

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        ox, oy = -cam_x, -cam_y

        floor = pygame.Rect(T + ox, T + oy, self.W - 2 * T, self.H - 2 * T)
        pygame.draw.rect(screen, FLOOR, floor)
        for y in range(T + 24, self.H - T, 24):
            pygame.draw.line(screen, FLOOR_LINE, (T + ox, y + oy), (self.W - T + ox, y + oy), 1)

        pygame.draw.ellipse(screen, (128, 62, 60),
                            (self.rug.x + ox, self.rug.y + oy, self.rug.w, self.rug.h))
        pygame.draw.ellipse(screen, (158, 92, 84),
                            (self.rug.x + ox, self.rug.y + oy, self.rug.w, self.rug.h), 2)

        for kind, rect in self.furniture:
            r = pygame.Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)
            if kind == "bed":
                pygame.draw.rect(screen, (108, 84, 58), r, border_radius=5)
                pygame.draw.rect(screen, (70, 52, 36), r, 2, border_radius=5)
                pygame.draw.rect(screen, (206, 202, 210),
                                 (r.x + 4, r.y + 4, r.w - 8, 18), border_radius=3)
                pygame.draw.rect(screen, (96, 116, 168),
                                 (r.x + 4, r.y + 24, r.w - 8, r.h - 28), border_radius=3)
            elif kind == "table":
                pygame.draw.rect(screen, (140, 98, 58), r, border_radius=5)
                pygame.draw.rect(screen, (86, 60, 36), r, 2, border_radius=5)
                for cx, cy in ((r.left + 9, r.top + 8), (r.right - 9, r.top + 8),
                               (r.left + 9, r.bottom - 8), (r.right - 9, r.bottom - 8)):
                    pygame.draw.circle(screen, (110, 78, 48), (cx, cy), 6)
                    pygame.draw.circle(screen, (70, 50, 32), (cx, cy), 6, 1)
            elif kind == "crate":
                pygame.draw.rect(screen, (150, 108, 64), r)
                pygame.draw.rect(screen, (84, 60, 36), r, 2)
                pygame.draw.line(screen, (84, 60, 36), r.topleft, r.bottomright, 1)
                pygame.draw.line(screen, (84, 60, 36), r.topright, r.bottomleft, 1)
            elif kind == "shelf":
                pygame.draw.rect(screen, (120, 84, 52), r)
                pygame.draw.rect(screen, (70, 48, 30), r, 2)
                for i in range(1, 4):
                    x = r.x + i * r.w // 4
                    pygame.draw.line(screen, (70, 48, 30), (x, r.top), (x, r.bottom), 1)
            elif kind == "fireplace":
                pygame.draw.rect(screen, (128, 120, 116), r, border_radius=4)
                pygame.draw.rect(screen, (80, 74, 72), r, 2, border_radius=4)
                fire = pygame.Rect(r.centerx - 16, r.centery - 6, 32, 13)
                pygame.draw.ellipse(screen, (216, 120, 40), fire)
                pygame.draw.ellipse(screen, (244, 196, 96),
                                    (fire.x + 6, fire.y + 4, 20, 8))

        px, py = self.plant

        cr = pygame.Rect(self.chest_rect.x + ox, self.chest_rect.y + oy,
                         self.chest_rect.w, self.chest_rect.h)
        pygame.draw.rect(screen, (140, 96, 52), cr, border_radius=3)
        pygame.draw.rect(screen, (84, 56, 30), cr, 2, border_radius=3)
        pygame.draw.rect(screen, (84, 56, 30), (cr.x, cr.y + 7, cr.w, 3))
        pygame.draw.rect(screen, (168, 168, 174), (cr.x + 5, cr.y, 3, cr.h))
        pygame.draw.rect(screen, (168, 168, 174), (cr.right - 8, cr.y, 3, cr.h))
        pygame.draw.rect(screen, (226, 194, 92), (cr.centerx - 3, cr.y + 12, 6, 6))

        for rect in self.brew_tables:                # a brewing table
            r = pygame.Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)
            pygame.draw.ellipse(screen, (44, 34, 24), (r.x - 4, r.bottom - 7, r.w + 8, 14))
            pygame.draw.rect(screen, (138, 96, 58), r, border_radius=4)
            pygame.draw.rect(screen, (72, 50, 32), r, 2, border_radius=4)
            pygame.draw.rect(screen, (160, 170, 150), (r.x + 8, r.y + 4, 12, 15))
            pygame.draw.rect(screen, (188, 150, 74), (r.x + 26, r.y + 6, 14, 13))

        for b in self.barrels:                       # barrels, filled or not
            r = pygame.Rect(b["rect"].x + ox, b["rect"].y + oy,
                            b["rect"].w, b["rect"].h)
            pygame.draw.ellipse(screen, (44, 34, 24), (r.x - 4, r.bottom - 6, r.w + 8, 12))
            pygame.draw.ellipse(screen, (130, 86, 50), r)
            pygame.draw.ellipse(screen, (78, 52, 30), r, 2)
            pygame.draw.line(screen, (196, 196, 200), (r.x + 3, r.centery),
                             (r.right - 3, r.centery), 2)
            pygame.draw.line(screen, (196, 196, 200), (r.x + 3, r.y + 6),
                             (r.right - 3, r.bottom - 6), 1)
            if b["kind"]:                            # full: show the fill
                pygame.draw.rect(screen, (176, 128, 56),
                                 (r.x + 4, r.centery, r.w - 8, r.h // 2 - 6),
                                 border_radius=3)

        for rect in self.lab_tables:                 # a bench, with glassware
            r = pygame.Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)
            pygame.draw.ellipse(screen, (44, 34, 24), (r.x - 4, r.bottom - 7, r.w + 8, 14))
            pygame.draw.rect(screen, (150, 104, 62), r, border_radius=4)
            pygame.draw.rect(screen, (78, 54, 34), r, 2, border_radius=4)
            pygame.draw.rect(screen, (152, 204, 182), (r.x + 8, r.y + 6, 9, r.h - 22))
            pygame.draw.rect(screen, (176, 224, 204), (r.x + 24, r.y + 2, 9, r.h - 18))
            pygame.draw.circle(screen, (206, 158, 74), (r.right - 14, r.y + 12), 8)
            pygame.draw.circle(screen, (140, 104, 48), (r.right - 14, r.y + 12), 8, 2)

        for rect in self.workshops:
            r = pygame.Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)
            pygame.draw.ellipse(screen, (44, 34, 24),
                                (r.x - 4, r.bottom - 7, r.w + 8, 14))
            pygame.draw.rect(screen, (150, 104, 62), r, border_radius=4)
            pygame.draw.rect(screen, (78, 54, 34), r, 2, border_radius=4)
            pygame.draw.rect(screen, (110, 110, 118),
                             (r.x + 6, r.centery - 3, r.w - 12, 9), border_radius=2)
            pygame.draw.rect(screen, (86, 86, 96),
                             (r.x + 9, r.y + 6, 20, 13), border_radius=2)
            pygame.draw.line(screen, (150, 110, 60),
                             (r.right - 16, r.y + 8), (r.right - 9, r.y + 18), 2)
            pygame.draw.rect(screen, (178, 178, 186),
                             (r.right - 19, r.y + 5, 10, 7))

        px, py = self.plant
        pygame.draw.circle(screen, (96, 62, 40), (int(px + ox), int(py + oy + 7)), 9)
        pygame.draw.circle(screen, (74, 126, 60), (int(px + ox), int(py + oy)), 12)
        pygame.draw.circle(screen, (96, 152, 76), (int(px + ox - 4), int(py + oy - 4)), 6)

        for rect in self.wall_rects:
            r = pygame.Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)
            pygame.draw.rect(screen, WALL, r)
            pygame.draw.rect(screen, WALL_DARK, r, 1)
            if rect.w >= rect.h:
                pygame.draw.line(screen, WALL_TOP, (r.left + 1, r.top + 2),
                                 (r.right - 1, r.top + 2), 1)
            else:
                pygame.draw.line(screen, WALL_TOP, (r.left + 2, r.top + 1),
                                 (r.left + 2, r.bottom - 1), 1)

        for rect in self.window_rects:
            r = pygame.Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)
            pygame.draw.rect(screen, (92, 66, 44), r, 2)
            if r.w >= r.h:
                pygame.draw.line(screen, (92, 66, 44), (r.centerx, r.top),
                                 (r.centerx, r.bottom), 1)
            else:
                pygame.draw.line(screen, (92, 66, 44), (r.left, r.centery),
                                 (r.right, r.centery), 1)
        pygame.draw.rect(screen, (92, 66, 44),
                         (self.door_rect.x + ox, self.door_rect.y + oy,
                          self.door_rect.w, self.door_rect.h), 2)
