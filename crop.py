"""Crops: drawing and growth.

Two crop *slots* exist everywhere -- a food crop and a leaf crop -- but what
grows in them depends on the biome: wheat/tobacco in the temperate and savanna
lands, red berries and red mushrooms in the snow, cactus fruit and agave in the
desert. Growth is the same for all of them.
"""

from __future__ import annotations

import math

import pygame
from palette import rich

from world import TILE, World

GROW_SECONDS = 180.0                 # a full crop cycle at skill 0
FASTEST_GROW = 60.0                  # ...and at the top of the trade, one minute


def grow_seconds(skill: float) -> float:
    """HOW LONG HIS CROP TAKES: three minutes green, one minute a master.

    The hand that plants it decides it. A farmer at 0 of 8 brings a crop in at
    the old GROW_SECONDS; at 8 he does it in a minute, and everything between
    is the straight line between the two.
    """
    k = max(0.0, min(8.0, float(skill))) / 8.0
    return GROW_SECONDS + (FASTEST_GROW - GROW_SECONDS) * k


def yield_scale(skill: float) -> float:
    """How much ONE crop gives him: 1x green, 3x a master."""
    k = max(0.0, min(8.0, float(skill))) / 8.0
    return 1.0 + 2.0 * k
PHASE_SECONDS = GROW_SECONDS / 4.0        # 3 growth phases, then ripe

LEAF_KINDS = ("plant", "mushroom", "agave")
FOOD_KINDS = ("wheat", "berries", "cactus")
FIBRE_KINDS = ("cotton",)      # neither food nor leaf: cotton, spun into cloth

# EVERY CROP A FIELD CAN GROW, in the order a field's type cycles. Bread is
# the base: a fresh field is wheat, and each click moves on to the next crop.
FIELD_KINDS = ("wheat", "berries", "cactus", "plant", "mushroom", "agave", "cotton")

# the item whose icon sits on a field of each crop (bread for wheat, the
# boll for cotton, and so on)
FIELD_SYMBOL = {
    "wheat": "bread", "berries": "berries", "cactus": "cactus_fruit",
    "plant": "tobacco", "mushroom": "red_mushroom", "agave": "agave",
    "cotton": "cotton",
}

# what each crop yields
LEAF_ITEM = {"plant": "tobacco", "mushroom": "red_mushroom", "agave": "agave"}
FOOD_ITEM = {"wheat": "bread", "berries": "berries", "cactus": "cactus_fruit"}

# every crop has its own seed, and every seed grows exactly one crop
SEED_CROP = {
    "wheat_seed": "wheat", "seed_bag": "plant",
    "berry_seed": "berries", "mushroom_spore": "mushroom",
    "cactus_seed": "cactus", "agave_seed": "agave",
    "cotton_seed": "cotton",
}
CROP_SEED = {crop: seed for seed, crop in SEED_CROP.items()}

# the leaf plant takes its colour from where it grows
LEAF_TINT = {
    "savanna": ((120, 132, 58), (150, 152, 66), (96, 104, 46)),
    "prairie": ((120, 140, 62), (156, 162, 72), (100, 112, 48)),
    "steppe":  ((104, 120, 66), (138, 146, 78), (86, 98, 52)),
    "marsh":   ((72, 122, 66), (98, 146, 78), (58, 96, 54)),
    "jungle":  ((60, 132, 62), (86, 158, 74), (46, 104, 50)),
}
LEAF_DEFAULT = (rich((64, 102, 44)), rich((94, 148, 62)), rich((50, 88, 36)))


def stage(elapsed: float) -> int:
    """0 = seedling, 1-2 = growing, 3 = ripe."""
    return min(3, int(elapsed / PHASE_SECONDS))


def visible_plants(world: World, cam_x: float, cam_y: float,
                   vw: int, vh: int, pad: int = 90):
    """(world_x, world_y, planted_at, kind, biome) for on-screen crops.

    WALK THE TILES ON SCREEN, NOT EVERY PLOT IN THE WORLD. This used to loop
    over world.plots -- every crop plot ever planted, across two hundred
    kilometres -- and discard the ones outside a 90-pixel margin of the
    camera. It was the single most expensive thing in the frame: measured at
    49.5 ms, half of everything, once per frame, to return the ten crops the
    player could actually see.

    The camera covers a rectangle of tiles, so visit that rectangle. Same
    plots, same order of cost irrelevant because the caller sorts by y; the
    filter below is kept so the answer is identical to the old one.
    """
    plants = []
    get = world.plots.get
    tx0 = int((cam_x - pad - TILE * 0.5) // TILE) - 1
    tx1 = int((cam_x + vw + pad - TILE * 0.5) // TILE) + 1
    ty0 = int((cam_y - pad - TILE * 0.5) // TILE) - 1
    ty1 = int((cam_y + vh + pad - TILE * 0.5) // TILE) + 1
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            plot = get((tx, ty))
            if plot is None or plot.planted_at is None:
                continue
            if plot.kind not in LEAF_KINDS and plot.kind not in FOOD_KINDS \
                    and plot.kind not in FIBRE_KINDS:
                continue
            x = tx * TILE + TILE / 2.0
            y = ty * TILE + TILE / 2.0
            if not (cam_x - pad <= x <= cam_x + vw + pad
                    and cam_y - pad <= y <= cam_y + vh + pad):
                continue
            biome = None
            if plot.kind == "plant":             # only tobacco is biome-tinted
                import biomes
                biome = biomes.biome_name(
                    float(world.temperature(x, y)), float(world.humidity(x, y)))
            plants.append((x, y, plot.planted_at, plot.kind, biome))
    return plants


def draw_crop(screen: pygame.Surface, x: float, y: float, kind: str,
              elapsed: float, cam_x: float, cam_y: float, biome=None) -> None:
    fn = _DRAWERS.get(kind)
    if fn is not None:
        fn(screen, x, y, elapsed, cam_x, cam_y, biome)


# ---------------------------------------------------------------- drawing
def _leaf(screen, bx, by, length, angle, width, color, outline):
    c, s = math.cos(angle), math.sin(angle)
    px, py = -s, c
    points = [(bx, by)]
    for t in (0.25, 0.5, 0.75):
        w = width * math.sin(math.pi * t)
        points.append((bx + c * length * t + px * w, by + s * length * t + py * w))
    points.append((bx + c * length, by + s * length))
    for t in (0.75, 0.5, 0.25):
        w = width * math.sin(math.pi * t)
        points.append((bx + c * length * t - px * w, by + s * length * t - py * w))
    pygame.draw.polygon(screen, color, points)
    pygame.draw.polygon(screen, outline, points, 1)


def draw_plant(screen, x, y, elapsed, cam_x, cam_y, biome=None):
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    color, color2, dark = LEAF_TINT.get(biome, LEAF_DEFAULT)

    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 9, sy - 3, 18, 7))

    height = 9.0 + 36.0 * p
    pygame.draw.line(screen, dark, (sx, sy), (sx, sy - height), 2)

    pairs = 1 + st
    for i in range(pairs):
        t = (i + 1) / (pairs + 0.5)
        ly = sy - height * t
        size = (6.0 + 13.0 * p) * (1.15 - 0.4 * t)
        col = color if i % 2 == 0 else color2
        _leaf(screen, sx, ly, size, math.radians(205), size * 0.42, col, dark)
        _leaf(screen, sx, ly, size, math.radians(-25), size * 0.42, col, dark)

    if st >= 3:                            # ripe: flowers
        top_y = sy - height
        for dx, dy in ((-5, 0), (5, 0), (0, -6)):
            fx, fy = int(sx + dx), int(top_y + dy)
            pygame.draw.circle(screen, (224, 126, 166), (fx, fy), 4)
            pygame.draw.circle(screen, (250, 220, 235), (fx, fy), 2)


def draw_mushroom(screen, x, y, elapsed, cam_x, cam_y, biome=None):
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 9, sy - 3, 18, 7))
    stem_h = 6.0 + 16.0 * p
    stem_w = max(4.0, 3.0 + 4.0 * p)
    pygame.draw.rect(screen, (232, 226, 210),
                     (sx - stem_w / 2, sy - stem_h, stem_w, stem_h), border_radius=2)
    pygame.draw.rect(screen, (186, 178, 160),
                     (sx - stem_w / 2, sy - stem_h, stem_w, stem_h), 1, border_radius=2)
    cap_w = 8.0 + 20.0 * p
    cap_h = cap_w * 0.66
    cap = pygame.Rect(sx - cap_w / 2, sy - stem_h - cap_h * 0.75, cap_w, cap_h)
    pygame.draw.ellipse(screen, (206, 58, 52), cap)
    pygame.draw.ellipse(screen, (146, 34, 32), cap, 2)
    if st >= 2:
        for dx, dy in ((-0.28, 0.34), (0.24, 0.28), (0.0, 0.5)):
            pygame.draw.circle(screen, (244, 240, 228),
                               (int(cap.centerx + dx * cap_w),
                                int(cap.centery + dy * cap_h)), 2)


def draw_agave(screen, x, y, elapsed, cam_x, cam_y, biome=None):
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 10, sy - 3, 20, 7))
    size = 10.0 + 26.0 * p
    leaf, dark = (108, 156, 140), (66, 110, 100)
    for ang in (-2.92, -2.25, -1.57, -0.9, -0.22):
        c, s = math.cos(ang), math.sin(ang)
        tx, ty = sx + c * size, sy + s * size * 0.95
        perp = size * 0.20
        pts = [(sx, sy), (sx + c * size * 0.45 - s * perp, sy + s * size * 0.45 + c * perp),
               (tx, ty),
               (sx + c * size * 0.45 + s * perp, sy + s * size * 0.45 - c * perp)]
        pygame.draw.polygon(screen, leaf, pts)
        pygame.draw.line(screen, dark, (sx, sy), (tx, ty), 1)
    if st >= 3:
        pygame.draw.line(screen, dark, (sx, sy - 2), (sx, sy - size * 1.35), 3)
        pygame.draw.ellipse(screen, (216, 196, 120),
                            (sx - 4, sy - size * 1.35 - 8, 8, 10))


def draw_wheat(screen: pygame.Surface, x: float, y: float, elapsed: float,
               cam_x: float, cam_y: float, biome=None) -> None:
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 9, sy - 3, 18, 7))
    height = 8.0 + 30.0 * p
    for i in range(3):
        off = (i - 1) * 5
        pygame.draw.line(screen, (152, 130, 62), (sx + off, sy),
                         (sx + off, sy - height), 2)
        if st >= 3:
            head = 10.0 * p + 5.0
            pygame.draw.ellipse(screen, (216, 184, 94),
                                (sx + off - 3, sy - height - head * 0.5, 6, head))
            pygame.draw.line(screen, (170, 138, 60),
                             (sx + off, sy - height + 2),
                             (sx + off, sy - height + head - 2), 1)
        else:
            pygame.draw.line(screen, (120, 150, 80), (sx + off, sy - height),
                             (sx + off, sy - height + 4), 2)


def draw_berries(screen, x, y, elapsed, cam_x, cam_y, biome=None):
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 10, sy - 3, 20, 7))
    bush = 0.55 + 0.45 * p
    for dx, dy, r, col in ((-6, -1, 8, (74, 126, 62)), (6, 0, 8, (60, 110, 54)),
                           (0, -6, 9, (78, 132, 66)), (0, 3, 7, (56, 102, 50))):
        pygame.draw.circle(screen, col, (int(sx + dx), int(sy + dy)),
                           max(2, int(r * bush)))
    if st >= 3:
        for dx, dy in ((-6, -3), (5, -1), (0, 4), (-2, -9), (7, -8)):
            pygame.draw.circle(screen, (198, 54, 58), (int(sx + dx), int(sy + dy)), 3)
            pygame.draw.circle(screen, (140, 32, 36), (int(sx + dx), int(sy + dy)), 3, 1)


def draw_cactus(screen, x, y, elapsed, cam_x, cam_y, biome=None):
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 9, sy - 3, 18, 7))
    h = 12.0 + 28.0 * p
    w = 8.0 + 8.0 * p
    pad = pygame.Rect(sx - w / 2, sy - h, w, h)
    pygame.draw.ellipse(screen, (86, 142, 76), pad)
    pygame.draw.ellipse(screen, (52, 100, 52), pad, 2)
    for dx in (-0.28, 0.0, 0.28):
        pygame.draw.line(screen, (52, 100, 52),
                         (sx + dx * w, sy - h * 0.75), (sx + dx * w, sy - 3), 1)
    if st >= 3:
        fx, fy = int(sx), int(sy - h - 3)
        pygame.draw.circle(screen, (212, 74, 84), (fx, fy), 4)
        pygame.draw.circle(screen, (150, 44, 54), (fx, fy), 4, 1)
        pygame.draw.circle(screen, (248, 176, 180), (fx - 1, fy - 1), 1)


def draw_cotton(screen, x, y, elapsed, cam_x, cam_y, biome=None):
    """The berry bush, but with white cotton bolls instead of red berries."""
    sx = x - cam_x
    sy = y - cam_y
    p = min(1.0, max(0.0, elapsed / GROW_SECONDS))
    st = stage(elapsed)
    pygame.draw.ellipse(screen, (38, 58, 30), (sx - 10, sy - 3, 20, 7))
    bush = 0.55 + 0.45 * p
    for dx, dy, r, col in ((-6, -1, 8, (74, 126, 62)), (6, 0, 8, (60, 110, 54)),
                           (0, -6, 9, (78, 132, 66)), (0, 3, 7, (56, 102, 50))):
        pygame.draw.circle(screen, col, (int(sx + dx), int(sy + dy)),
                           max(2, int(r * bush)))
    if st >= 3:
        for dx, dy in ((-6, -3), (5, -1), (0, 4), (-2, -9), (7, -8)):
            pygame.draw.circle(screen, (248, 250, 252), (int(sx + dx), int(sy + dy)), 4)
            pygame.draw.circle(screen, (200, 208, 218), (int(sx + dx), int(sy + dy)), 4, 1)


_DRAWERS = {
    "plant": draw_plant,
    "mushroom": draw_mushroom,
    "agave": draw_agave,
    "wheat": draw_wheat,
    "berries": draw_berries,
    "cactus": draw_cactus,
    "cotton": draw_cotton,
}
