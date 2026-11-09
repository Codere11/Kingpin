"""Item definitions and procedurally drawn icons.

No art assets yet, so each icon is drawn with primitives at high resolution and
downscaled for anti-aliasing. Icons are cached per (item, size).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class ItemDef:
    id: str
    name: str
    description: str
    stackable: bool = False
    max_stack: int = 1
    quality: bool = False            # carries a quality grade (tobacco)


REGISTRY: dict[str, ItemDef] = {
    "rifle": ItemDef("rifle", "Rifle", "A lever-action rifle. Good for hunting, better for settling arguments."),
    "shotgun": ItemDef("shotgun", "Shotgun", "Scatters a fistful of lead. Slow to work the pump."),
    "ammo": ItemDef("ammo", "Ammo", "Cartridges. Fits any gun you own.", stackable=True, max_stack=100),
    # WHAT A SPY CARRIES. Taken off an agent's body: every message he was
    # holding, addressed, dated, and readable by anybody who loots him.
    "secret_folder": ItemDef("secret_folder", "Secret Folder",
                             "A dead agent's messages. Equip it and click."),
    "pickaxe": ItemDef("pickaxe", "Pickaxe", "Breaks iron out of the rock."),
    "compass": ItemDef("compass", "Compass", "Points home, or to the nearest village. Press F."),
    "iron": ItemDef("iron", "Iron", "Raw iron, straight from the ground. Crafting stock.",
                    stackable=True, max_stack=100),
    "shovel": ItemDef("shovel", "Shovel", "For digging. Gardens, graves, whatever needs doing."),
    "watering_can": ItemDef("watering_can", "Watering Can", "Keeps the crop alive. Or puts out a fire."),
    "seed_bag": ItemDef("seed_bag", "Tobacco Seeds",
                         "Plant in fertile soil; grows tobacco.",
                         stackable=True, max_stack=100),
    "berry_seed": ItemDef("berry_seed", "Berry Seeds",
                          "Plant in fertile soil; grows red berries.",
                          stackable=True, max_stack=100),
    "mushroom_spore": ItemDef("mushroom_spore", "Mushroom Spores",
                              "Plant in fertile soil; grows red mushrooms.",
                              stackable=True, max_stack=100),
    "cactus_seed": ItemDef("cactus_seed", "Cactus Seeds",
                           "Plant in fertile soil; grows cactus fruit.",
                           stackable=True, max_stack=100),
    "agave_seed": ItemDef("agave_seed", "Agave Seeds",
                          "Plant in fertile soil; grows agave.",
                          stackable=True, max_stack=100),
    "tobacco": ItemDef("tobacco", "Tobacco", "Cured leaf. The whole point of all this.",
                       stackable=True, max_stack=100, quality=True),
    "wheat": ItemDef("wheat", "Wheat",
                     "Threshed grain. Bread needs it, and so does beer.",
                     stackable=True, max_stack=100),
    "wheat_wort": ItemDef("wheat_wort", "Wheat Wort",
                          "Sweet mash, ready for the barrel.",
                          stackable=True, max_stack=100, quality=True),
    "berry_wort": ItemDef("berry_wort", "Berry Wort",
                          "Crushed berries and water, waiting to ferment.",
                          stackable=True, max_stack=100, quality=True),
    "agave_wort": ItemDef("agave_wort", "Agave Wort",
                          "Roasted agave, mashed. The desert's whole future.",
                          stackable=True, max_stack=100, quality=True),
    "beer": ItemDef("beer", "Beer",
                    "Dark, honest and strong. Worth far more than the grain it came from.",
                    stackable=True, max_stack=100, quality=True),
    "govbeer": ItemDef("govbeer", "Govermentskoye",
                       "State beer, E-grade, and none of the state's business. "
                       "Cheap, brown, and on every table in the republic.",
                       stackable=True, max_stack=100),
    "liqueur": ItemDef("liqueur", "Liqueur",
                       "Sweet, potent, and the finest thing a berry can become.",
                       stackable=True, max_stack=100, quality=True),
    "mezcal": ItemDef("mezcal", "Mezcal",
                      "Smoke and fire. The desert finally has something to sell.",
                      stackable=True, max_stack=100, quality=True),
    "cigar": ItemDef("cigar", "Cigar",
                     "Rolled and cured tobacco. This is what they are actually addicted to.",
                     stackable=True, max_stack=100, quality=True),
    "dried_mushroom": ItemDef("dried_mushroom", "Dried Mushrooms",
                              "Sun-dried caps. Keeps for months, and it is what they crave.",
                              stackable=True, max_stack=100, quality=True),
    "first_aid": ItemDef("first_aid", "First-Aid Kit", "Patches you back up.",
                         stackable=True, max_stack=10),
    "axe": ItemDef("axe", "Axe", "Chops trees for wood. Also works on people."),
    "wood": ItemDef("wood", "Wood", "Timber, for building and burning.",
                    stackable=True, max_stack=100),
    "coin": ItemDef("coin", "Coin", "Money. Buys things off people.",
                    stackable=True, max_stack=9999),
    "wheat_seed": ItemDef("wheat_seed", "Wheat Seeds",
                          "Plant in fertile soil; grows wheat.",
                          stackable=True, max_stack=100),
    "bread": ItemDef("bread", "Bread", "Eat it before you starve.",
                     stackable=True, max_stack=20),
    "berries": ItemDef("berries", "Red Berries", "Sweet and filling.",
                       stackable=True, max_stack=20),
    "cactus_fruit": ItemDef("cactus_fruit", "Cactus Fruit",
                            "Juicy, if you mind the spines. Filling.",
                            stackable=True, max_stack=20),
    "red_mushroom": ItemDef("red_mushroom", "Red Mushroom",
                            "A fine red cap. Traders pay for these.",
                            stackable=True, max_stack=100, quality=True),
    "agave": ItemDef("agave", "Agave", "Thick desert leaves. Traders pay for these.",
                     stackable=True, max_stack=100, quality=True),
    "raw_meat": ItemDef("raw_meat", "Raw Meat", "Fresh off a rabbit. Better cooked.",
                        stackable=True, max_stack=20),
    "cooked_meat": ItemDef("cooked_meat", "Cooked Meat",
                           "Hot and filling. Restores you completely.",
                           stackable=True, max_stack=20),
    "hide": ItemDef("hide", "Hide", "A thick bison hide. Traders pay well for these.",
                    stackable=True, max_stack=50),
    "cotton": ItemDef("cotton", "Cotton", "Fluffy white fibre. Spins into cloth.",
                      stackable=True, max_stack=100),
    "cotton_seed": ItemDef("cotton_seed", "Cotton Seeds",
                           "Plant in fertile soil; grows cotton.",
                           stackable=True, max_stack=100),
    "bed": ItemDef("bed", "Bed", "A cotton bed. Place it and sleep.",
                   stackable=True, max_stack=10),
}


def get(item_id: str) -> ItemDef:
    return REGISTRY[item_id]


# ---------------------------------------------------------------- icon drawing
def _pt(p, s):
    return (p[0] * s, p[1] * s)


def _poly(surf, color, points, s, width=0):
    pygame.draw.polygon(surf, color, [_pt(p, s) for p in points], width)


def _rect(surf, color, r, s, width=0, radius=0):
    x, y, w, h = (v * s for v in r)
    pygame.draw.rect(surf, color, (x, y, w, h), width, border_radius=int(radius * s))


def _outline(surf, color, points, s, width=2):
    _poly(surf, color, points, s, width)


def _canvas(s=128):
    return pygame.Surface((s, s), pygame.SRCALPHA)


def _draw_rifle(s: int) -> pygame.Surface:
    surf = _canvas(s)
    wood, wood_d = (124, 82, 44), (82, 52, 28)
    metal, metal_d = (78, 80, 88), (44, 46, 52)

    stock = [(0.05, 0.58), (0.31, 0.50), (0.31, 0.68), (0.05, 0.76)]
    _poly(surf, wood, stock, s)
    _outline(surf, wood_d, stock, s)
    _rect(surf, metal, (0.28, 0.545, 0.27, 0.13), s)
    _rect(surf, metal_d, (0.28, 0.545, 0.27, 0.13), s, width=2)
    _rect(surf, metal, (0.53, 0.585, 0.42, 0.055), s)
    _rect(surf, metal_d, (0.53, 0.585, 0.42, 0.055), s, width=2)
    _rect(surf, metal_d, (0.93, 0.56, 0.05, 0.10), s, radius=0.01)
    _rect(surf, metal_d, (0.35, 0.66, 0.10, 0.17), s, radius=0.02)
    _outline(surf, metal_d, [(0.35, 0.66), (0.45, 0.66), (0.45, 0.83), (0.35, 0.83)], s)
    _rect(surf, metal_d, (0.72, 0.53, 0.035, 0.055), s)
    return surf


def _draw_ammo(s: int) -> pygame.Surface:
    surf = _canvas(s)
    box, box_d = (94, 98, 58), (56, 60, 34)
    brass, brass_d = (198, 162, 74), (146, 112, 42)

    _rect(surf, box, (0.20, 0.48, 0.58, 0.38), s, radius=0.03)
    _rect(surf, box_d, (0.20, 0.48, 0.58, 0.38), s, width=3, radius=0.03)
    _rect(surf, box_d, (0.20, 0.44, 0.58, 0.08), s, radius=0.02)
    for x in (0.29, 0.44, 0.59):
        _rect(surf, brass, (x, 0.24, 0.10, 0.24), s, radius=0.02)
        _rect(surf, brass_d, (x, 0.24, 0.10, 0.24), s, width=2, radius=0.02)
        _poly(surf, brass_d, [(x, 0.25), (x + 0.05, 0.13), (x + 0.10, 0.25)], s)
    return surf


def _draw_shotgun(s: int) -> pygame.Surface:
    surf = _canvas(s)
    wood, wood_d = (112, 74, 40), (74, 48, 26)
    metal, metal_d = (84, 86, 94), (48, 50, 56)
    stock = [(0.04, 0.58), (0.30, 0.50), (0.30, 0.70), (0.04, 0.78)]
    _poly(surf, wood, stock, s)
    _outline(surf, wood_d, stock, s)
    _rect(surf, metal, (0.28, 0.53, 0.34, 0.14), s)
    _rect(surf, metal_d, (0.28, 0.53, 0.34, 0.14), s, width=2)
    _rect(surf, metal, (0.60, 0.545, 0.36, 0.05), s)
    _rect(surf, metal_d, (0.60, 0.545, 0.36, 0.05), s, width=2)
    _rect(surf, metal, (0.60, 0.625, 0.36, 0.05), s)
    _rect(surf, metal_d, (0.60, 0.625, 0.36, 0.05), s, width=2)
    _rect(surf, metal_d, (0.83, 0.53, 0.05, 0.16), s, radius=0.01)
    return surf


def _draw_pickaxe(s: int) -> pygame.Surface:
    surf = _canvas(s)
    wood, wood_d = (122, 84, 46), (82, 56, 30)
    metal, metal_d = (150, 154, 162), (92, 96, 104)
    pygame.draw.line(surf, wood_d, _pt((0.30, 0.92), s), _pt((0.58, 0.24), s), int(0.09 * s))
    pygame.draw.line(surf, wood, _pt((0.31, 0.91), s), _pt((0.59, 0.23), s), int(0.055 * s))
    head = [(0.14, 0.32), (0.30, 0.16), (0.56, 0.20), (0.88, 0.32),
            (0.86, 0.45), (0.54, 0.34), (0.30, 0.31), (0.19, 0.45)]
    _poly(surf, metal, head, s)
    _outline(surf, metal_d, head, s)
    return surf


def _draw_iron(s: int) -> pygame.Surface:
    surf = _canvas(s)
    rock, rock_d = (122, 122, 130), (74, 74, 84)
    body = [(0.16, 0.66), (0.30, 0.32), (0.58, 0.22), (0.84, 0.44),
            (0.78, 0.74), (0.44, 0.84)]
    _poly(surf, rock, body, s)
    _outline(surf, rock_d, body, s)
    for dx, dy in ((0.36, 0.46), (0.54, 0.40), (0.62, 0.60), (0.42, 0.68)):
        pygame.draw.circle(surf, (168, 96, 52), (int(dx * s), int(dy * s)), int(0.055 * s))
        pygame.draw.circle(surf, (212, 146, 84), (int(dx * s), int(dy * s)), int(0.028 * s))
    return surf


def _draw_compass(s: int) -> pygame.Surface:
    surf = _canvas(s)
    brass, brass_d = (196, 162, 84), (132, 102, 48)
    face, face_d = (232, 228, 214), (168, 162, 148)
    pygame.draw.circle(surf, brass, (int(0.5 * s), int(0.5 * s)), int(0.44 * s))
    pygame.draw.circle(surf, brass_d, (int(0.5 * s), int(0.5 * s)), int(0.44 * s), 3)
    pygame.draw.circle(surf, face, (int(0.5 * s), int(0.5 * s)), int(0.34 * s))
    pygame.draw.circle(surf, face_d, (int(0.5 * s), int(0.5 * s)), int(0.34 * s), 2)
    pygame.draw.polygon(surf, (188, 62, 52),
                        [_pt((0.5, 0.16), s), _pt((0.60, 0.52), s), _pt((0.40, 0.52), s)])
    pygame.draw.polygon(surf, (72, 78, 92),
                        [_pt((0.5, 0.84), s), _pt((0.60, 0.48), s), _pt((0.40, 0.48), s)])
    pygame.draw.circle(surf, brass_d, (int(0.5 * s), int(0.5 * s)), int(0.04 * s))
    return surf


def _draw_berries(s: int) -> pygame.Surface:
    surf = _canvas(s)
    leaf, leaf_d = (76, 128, 62), (48, 90, 40)
    berry, berry_d = (198, 54, 58), (140, 32, 36)
    pygame.draw.line(surf, leaf_d, _pt((0.5, 0.9), s), _pt((0.5, 0.42), s), int(0.07 * s))
    for ang in (-2.4, -0.75):
        pygame.draw.line(surf, leaf, _pt((0.5, 0.62), s),
                         _pt((0.5 + math.cos(ang) * 0.26, 0.62 + math.sin(ang) * 0.26), s),
                         int(0.05 * s))
    for dx, dy in ((0.34, 0.52), (0.60, 0.44), (0.48, 0.68), (0.68, 0.66), (0.38, 0.76)):
        pygame.draw.circle(surf, berry, (int(dx * s), int(dy * s)), int(0.10 * s))
        pygame.draw.circle(surf, berry_d, (int(dx * s), int(dy * s)), int(0.10 * s), 2)
        pygame.draw.circle(surf, (240, 150, 150),
                           (int(dx * s - 0.03 * s), int(dy * s - 0.03 * s)), int(0.035 * s))
    return surf


def _draw_cactus_fruit(s: int) -> pygame.Surface:
    surf = _canvas(s)
    pad, pad_d = (86, 142, 76), (52, 100, 52)
    fruit, fruit_d = (212, 74, 84), (150, 44, 54)
    pygame.draw.ellipse(surf, pad, (0.22 * s, 0.20 * s, 0.56 * s, 0.72 * s))
    pygame.draw.ellipse(surf, pad_d, (0.22 * s, 0.20 * s, 0.56 * s, 0.72 * s), 3)
    for dx in (0.40, 0.50, 0.60):
        pygame.draw.line(surf, pad_d, (int(dx * s), int(0.26 * s)),
                         (int(dx * s), int(0.86 * s)), 1)
    pygame.draw.circle(surf, fruit, (int(0.5 * s), int(0.34 * s)), int(0.14 * s))
    pygame.draw.circle(surf, fruit_d, (int(0.5 * s), int(0.34 * s)), int(0.14 * s), 2)
    pygame.draw.circle(surf, (248, 176, 180), (int(0.44 * s), int(0.28 * s)), int(0.05 * s))
    return surf


def _draw_red_mushroom(s: int) -> pygame.Surface:
    surf = _canvas(s)
    cap, cap_d = (206, 58, 52), (146, 34, 32)
    stem = (232, 226, 210)
    _rect(surf, stem, (0.38, 0.50, 0.24, 0.38), s, radius=0.05)
    _rect(surf, (186, 178, 160), (0.38, 0.50, 0.24, 0.38), s, width=2, radius=0.05)
    pygame.draw.ellipse(surf, cap, (0.14 * s, 0.24 * s, 0.72 * s, 0.40 * s))
    pygame.draw.ellipse(surf, cap_d, (0.14 * s, 0.24 * s, 0.72 * s, 0.40 * s), 3)
    for dx, dy, r in ((0.32, 0.38, 0.055), (0.56, 0.34, 0.045), (0.68, 0.44, 0.04)):
        pygame.draw.circle(surf, (244, 240, 228), (int(dx * s), int(dy * s)), int(r * s))
    return surf


def _draw_agave(s: int) -> pygame.Surface:
    surf = _canvas(s)
    leaf, leaf_d = (108, 156, 140), (66, 110, 100)
    for ang in (-2.9, -2.2, -1.55, -0.9, -0.25):
        tipx = 0.5 + math.cos(ang) * 0.42
        tipy = 0.86 + math.sin(ang) * 0.42
        _poly(surf, leaf, [(0.5, 0.86), (0.44, 0.62),
                           (tipx, tipy), (0.56, 0.62)], s)
        pygame.draw.line(surf, leaf_d, _pt((0.5, 0.86), s), _pt((tipx, tipy), s), 2)
    pygame.draw.circle(surf, leaf_d, (int(0.5 * s), int(0.84 * s)), int(0.07 * s))
    return surf


def _draw_seeds(s: int, color, dark) -> pygame.Surface:
    surf = _canvas(s)
    pygame.draw.ellipse(surf, (96, 74, 48), (0.16 * s, 0.72 * s, 0.68 * s, 0.18 * s))
    for dx, dy, r in ((0.33, 0.62, 0.10), (0.52, 0.58, 0.11),
                      (0.68, 0.66, 0.09), (0.45, 0.74, 0.10)):
        _rect(surf, dark, (dx - r, dy - r * 1.35, 2 * r, 2 * r * 1.35), s, radius=r)
        _rect(surf, color, (dx - r + 0.02, dy - r * 1.35 + 0.02,
                            2 * r - 0.04, 2 * r * 1.35 - 0.04), s, radius=r * 0.8)
    pygame.draw.line(surf, (98, 152, 74), (0.5 * s, 0.72 * s), (0.5 * s, 0.34 * s),
                     max(2, int(0.05 * s)))
    pygame.draw.line(surf, (98, 152, 74), (0.5 * s, 0.52 * s), (0.33 * s, 0.40 * s),
                     max(2, int(0.04 * s)))
    pygame.draw.line(surf, (98, 152, 74), (0.5 * s, 0.46 * s), (0.67 * s, 0.34 * s),
                     max(2, int(0.04 * s)))
    return surf


def _draw_berry_seed(s):
    return _draw_seeds(s, (136, 54, 50), (88, 30, 30))


def _draw_mushroom_spore(s):
    return _draw_seeds(s, (208, 202, 196), (150, 144, 138))


def _draw_cactus_seed(s):
    return _draw_seeds(s, (62, 58, 54), (28, 26, 24))


def _draw_agave_seed(s):
    return _draw_seeds(s, (166, 142, 96), (112, 94, 60))


def _draw_shovel(s: int) -> pygame.Surface:
    surf = _canvas(s)
    wood, wood_d = (122, 84, 46), (82, 56, 30)
    metal, metal_d = (156, 158, 166), (96, 98, 106)

    pygame.draw.line(surf, wood_d, _pt((0.81, 0.11), s), _pt((0.41, 0.63), s), int(0.09 * s))
    pygame.draw.line(surf, wood, _pt((0.80, 0.10), s), _pt((0.40, 0.62), s), int(0.06 * s))
    _rect(surf, wood, (0.72, 0.05, 0.18, 0.07), s, radius=0.03)
    _rect(surf, wood_d, (0.72, 0.05, 0.18, 0.07), s, width=2, radius=0.03)

    blade = [(0.23, 0.61), (0.53, 0.61), (0.49, 0.87), (0.38, 0.96), (0.27, 0.87)]
    _poly(surf, metal, blade, s)
    _outline(surf, metal_d, blade, s)
    pygame.draw.line(surf, metal_d, _pt((0.30, 0.68), s), _pt((0.46, 0.68), s), 2)
    return surf


def _draw_watering_can(s: int) -> pygame.Surface:
    surf = _canvas(s)
    metal, metal_d = (152, 160, 168), (94, 102, 112)
    water = (92, 146, 188)

    body = (0.32, 0.46, 0.42, 0.40)
    _rect(surf, metal, body, s, radius=0.10)
    _rect(surf, metal_d, body, s, width=3, radius=0.10)
    _rect(surf, water, (0.36, 0.60, 0.34, 0.22), s, radius=0.06)
    pygame.draw.ellipse(surf, metal_d, (0.38 * s, 0.41 * s, 0.30 * s, 0.10 * s))
    pygame.draw.ellipse(surf, metal, (0.39 * s, 0.42 * s, 0.28 * s, 0.08 * s))

    # handle
    pygame.draw.arc(surf, metal_d, (0.36 * s, 0.18 * s, 0.34 * s, 0.36 * s),
                    3.14159, 6.28318, 6)

    # spout
    spout = [(0.33, 0.58), (0.11, 0.40), (0.06, 0.47), (0.31, 0.72)]
    _poly(surf, metal, spout, s)
    _outline(surf, metal_d, spout, s)
    pygame.draw.ellipse(surf, metal_d, (0.00 * s, 0.34 * s, 0.14 * s, 0.12 * s))
    return surf


def _draw_seed_bag(s: int) -> pygame.Surface:
    surf = _canvas(s)
    burlap, burlap_d = (180, 152, 106), (120, 96, 58)
    light = (204, 178, 136)
    tie, seed = (104, 78, 44), (74, 56, 34)
    sprout = (98, 152, 74)

    body = [(0.30, 0.40), (0.70, 0.40), (0.80, 0.80), (0.20, 0.80)]
    _poly(surf, burlap, body, s)
    pygame.draw.ellipse(surf, burlap, (0.20 * s, 0.66 * s, 0.60 * s, 0.24 * s))
    _outline(surf, burlap_d, body, s)
    pygame.draw.arc(surf, burlap_d, (0.20 * s, 0.66 * s, 0.60 * s, 0.24 * s), 3.14159, 6.28318, 2)

    _rect(surf, burlap, (0.40, 0.24, 0.20, 0.18), s, radius=0.05)
    _rect(surf, burlap_d, (0.40, 0.24, 0.20, 0.18), s, width=2, radius=0.05)
    _rect(surf, tie, (0.36, 0.35, 0.28, 0.07), s, radius=0.02)
    _poly(surf, light, [(0.34, 0.46), (0.44, 0.46), (0.40, 0.72), (0.29, 0.72)], s)

    for x, y in ((0.40, 0.86), (0.50, 0.88), (0.60, 0.85), (0.45, 0.92), (0.56, 0.91)):
        pygame.draw.ellipse(surf, seed, (x * s, y * s, 0.07 * s, 0.05 * s))

    pygame.draw.line(surf, sprout, (0.50 * s, 0.24 * s), (0.50 * s, 0.14 * s), max(2, int(0.03 * s)))
    pygame.draw.ellipse(surf, sprout, (0.50 * s, 0.10 * s, 0.11 * s, 0.08 * s))
    return surf


def _leaf_shape(bx, by, tx, ty, w):
    """Points for a pointed leaf from (bx,by) to (tx,ty), all normalised."""
    dx, dy = tx - bx, ty - by
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    points = [(bx, by)]
    for t in (0.3, 0.6):
        ww = w * math.sin(math.pi * t)
        points.append((bx + ux * length * t + px * ww, by + uy * length * t + py * ww))
    points.append((tx, ty))
    for t in (0.6, 0.3):
        ww = w * math.sin(math.pi * t)
        points.append((bx + ux * length * t - px * ww, by + uy * length * t - py * ww))
    return points


def _draw_wheat(s: int) -> pygame.Surface:
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    pygame.draw.line(surf, (168, 138, 62), (s // 2, s * 0.16), (s // 2, s * 0.84), 4)
    for i in range(6):
        y = int(s * (0.22 + i * 0.11))
        pygame.draw.ellipse(surf, (214, 178, 84), (s * 0.30, y, s * 0.20, s * 0.10))
        pygame.draw.ellipse(surf, (214, 178, 84), (s * 0.50, y, s * 0.20, s * 0.10))
    return surf


def _draw_drink(s: int, body) -> pygame.Surface:
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    pygame.draw.rect(surf, (206, 214, 220), (s * 0.30, s * 0.24, s * 0.40, s * 0.56),
                     border_radius=6)
    pygame.draw.rect(surf, body, (s * 0.33, s * 0.40, s * 0.34, s * 0.37),
                     border_radius=4)
    pygame.draw.rect(surf, (120, 128, 134), (s * 0.30, s * 0.24, s * 0.40, s * 0.56),
                     3, border_radius=6)
    pygame.draw.rect(surf, (150, 158, 164), (s * 0.44, s * 0.14, s * 0.12, s * 0.12))
    return surf


def _draw_wort(s: int) -> pygame.Surface:
    return _draw_drink(s, (196, 168, 104))


def _draw_beer(s: int) -> pygame.Surface:
    return _draw_drink(s, (168, 112, 40))


def _draw_liqueur(s: int) -> pygame.Surface:
    return _draw_drink(s, (150, 60, 96))


def _draw_mezcal(s: int) -> pygame.Surface:
    return _draw_drink(s, (198, 190, 150))


def _draw_cigar(s: int) -> pygame.Surface:
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    w, h = int(s * 0.70), int(s * 0.20)
    x, y = int(s * 0.15), int(s * 0.40)
    pygame.draw.rect(surf, (108, 66, 38), (x, y, w, h), border_radius=4)
    pygame.draw.rect(surf, (150, 96, 54), (x, y, w, max(2, h // 3)), border_radius=4)
    pygame.draw.rect(surf, (74, 46, 26), (x + w - int(w * 0.22), y, int(w * 0.22), h),
                     border_radius=3)
    pygame.draw.circle(surf, (240, 150, 60), (x + w, y + h // 2), max(2, h // 3))
    return surf


def _draw_dried_mushroom(s: int) -> pygame.Surface:
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    for cx, cy, r in ((0.38, 0.44, 0.22), (0.64, 0.58, 0.17)):
        pygame.draw.ellipse(surf, (120, 74, 58),
                            (int(s * (cx - r)), int(s * (cy - r * 0.7)),
                             int(s * r * 2), int(s * r * 1.4)))
        pygame.draw.ellipse(surf, (86, 52, 40),
                            (int(s * (cx - r)), int(s * (cy - r * 0.7)),
                             int(s * r * 2), int(s * r * 1.4)), 2)
        pygame.draw.rect(surf, (196, 176, 140),
                         (int(s * (cx - r * 0.22)), int(s * (cy + r * 0.5)),
                          int(s * r * 0.45), int(s * r * 1.1)), border_radius=2)
    return surf


def _draw_tobacco(s: int) -> pygame.Surface:
    surf = _canvas(s)
    leaves = [
        ((0.50, 0.88), (0.26, 0.16), 0.13, (180, 146, 76)),
        ((0.50, 0.90), (0.50, 0.07), 0.14, (152, 118, 56)),
        ((0.50, 0.88), (0.74, 0.18), 0.13, (200, 168, 100)),
    ]
    for base, tip, width, color in leaves:
        points = _leaf_shape(base[0], base[1], tip[0], tip[1], width)
        _poly(surf, color, points, s)
        _outline(surf, (96, 72, 32), points, s)
        pygame.draw.line(surf, (122, 94, 42), _pt(base, s), _pt(tip, s), 1)
    _rect(surf, (96, 70, 34), (0.40, 0.82, 0.20, 0.08), s, radius=0.02)
    _rect(surf, (68, 50, 24), (0.40, 0.82, 0.20, 0.08), s, width=1, radius=0.02)
    return surf


def _draw_first_aid(s: int) -> pygame.Surface:
    surf = _canvas(s)
    box, box_d = (236, 232, 224), (150, 146, 140)
    red, red_d = (198, 46, 46), (140, 26, 26)

    _rect(surf, box_d, (0.40, 0.20, 0.20, 0.12), s, radius=0.03)      # handle
    _rect(surf, box, (0.20, 0.28, 0.60, 0.54), s, radius=0.06)
    _rect(surf, box_d, (0.20, 0.28, 0.60, 0.54), s, width=3, radius=0.06)
    pygame.draw.line(surf, box_d, _pt((0.20, 0.44), s), _pt((0.80, 0.44), s), 2)
    _rect(surf, red, (0.44, 0.52, 0.12, 0.26), s, radius=0.02)
    _rect(surf, red, (0.37, 0.59, 0.26, 0.12), s, radius=0.02)
    pygame.draw.line(surf, red_d, _pt((0.44, 0.52), s), _pt((0.44, 0.78), s), 1)
    return surf


def _draw_axe(s: int) -> pygame.Surface:
    surf = _canvas(s)
    wood, wood_d = (122, 84, 46), (74, 50, 26)
    steel, steel_d = (178, 184, 192), (98, 104, 114)

    pygame.draw.line(surf, wood_d, _pt((0.22, 0.86), s), _pt((0.70, 0.24), s), int(0.12 * s))
    pygame.draw.line(surf, wood, _pt((0.22, 0.86), s), _pt((0.70, 0.24), s), int(0.08 * s))
    head = [(0.60, 0.08), (0.88, 0.16), (0.94, 0.42), (0.70, 0.50), (0.56, 0.30)]
    _poly(surf, steel, head, s)
    _outline(surf, steel_d, head, s)
    pygame.draw.line(surf, (234, 240, 246), _pt((0.86, 0.17), s), _pt((0.91, 0.41), s), int(0.035 * s))
    _rect(surf, wood_d, (0.62, 0.30, 0.14, 0.10), s, radius=0.02)
    return surf


def _draw_wood(s: int) -> pygame.Surface:
    surf = _canvas(s)
    bark, bark_d = (112, 76, 44), (70, 46, 26)
    ring, ring_d = (188, 152, 106), (140, 110, 72)
    for x, y, w in ((0.10, 0.60, 0.78), (0.16, 0.42, 0.72), (0.22, 0.24, 0.64)):
        rect = pygame.Rect(x * s, y * s, w * s, 0.17 * s)
        pygame.draw.rect(surf, bark, rect, border_radius=int(0.085 * s))
        pygame.draw.rect(surf, bark_d, rect, 2, border_radius=int(0.085 * s))
        ex, ey = int((x + 0.085) * s), int((y + 0.085) * s)
        pygame.draw.circle(surf, ring, (ex, ey), int(0.085 * s))
        pygame.draw.circle(surf, ring_d, (ex, ey), int(0.085 * s), 1)
        pygame.draw.circle(surf, ring_d, (ex, ey), int(0.035 * s), 1)
    return surf


def _draw_coin(s: int) -> pygame.Surface:
    surf = _canvas(s)
    gold, gold_d, light = (216, 178, 74), (146, 112, 40), (244, 220, 138)
    c = s // 2
    r = int(0.32 * s)
    pygame.draw.circle(surf, gold, (c, c), r)
    pygame.draw.circle(surf, gold_d, (c, c), r, max(2, int(0.05 * s)))
    pygame.draw.circle(surf, light, (int(c - r * 0.3), int(c - r * 0.3)), max(2, int(r * 0.35)))
    pygame.draw.line(surf, gold_d, (int(c - r * 0.28), int(c - r * 0.4)),
                     (int(c - r * 0.28), int(c + r * 0.4)), max(2, int(0.05 * s)))
    pygame.draw.line(surf, gold_d, (int(c + r * 0.28), int(c - r * 0.4)),
                     (int(c + r * 0.28), int(c + r * 0.4)), max(2, int(0.05 * s)))
    pygame.draw.line(surf, gold_d, (int(c - r * 0.28), c), (int(c + r * 0.28), c),
                     max(2, int(0.05 * s)))
    return surf


def _draw_wheat_seed(s: int) -> pygame.Surface:
    surf = _canvas(s)
    sack, sack_d = (198, 168, 96), (140, 112, 56)
    wheat, wheat_d = (230, 198, 96), (170, 138, 60)
    body = [(0.30, 0.42), (0.70, 0.42), (0.78, 0.82), (0.22, 0.82)]
    _poly(surf, sack, body, s)
    pygame.draw.ellipse(surf, sack, (0.22 * s, 0.68 * s, 0.56 * s, 0.22 * s))
    _outline(surf, sack_d, body, s)
    _rect(surf, sack, (0.40, 0.26, 0.20, 0.18), s, radius=0.05)
    _rect(surf, sack_d, (0.40, 0.26, 0.20, 0.18), s, width=2, radius=0.05)
    _rect(surf, wheat_d, (0.37, 0.36, 0.26, 0.07), s, radius=0.02)
    for x, y in ((0.40, 0.86), (0.52, 0.88), (0.62, 0.85)):
        pygame.draw.ellipse(surf, wheat, (x * s, y * s, 0.10 * s, 0.07 * s))
    pygame.draw.line(surf, wheat_d, (0.52 * s, 0.26 * s), (0.52 * s, 0.12 * s), 3)
    pygame.draw.ellipse(surf, wheat, (0.46 * s, 0.10 * s, 0.12 * s, 0.09 * s))
    return surf


def _draw_raw_meat(s: int) -> pygame.Surface:
    surf = _canvas(s)
    meat, meat_d = (196, 92, 92), (140, 54, 54)
    bone, fat = (238, 234, 222), (226, 176, 176)
    pygame.draw.line(surf, bone, _pt((0.16, 0.82), s), _pt((0.80, 0.24), s), int(0.12 * s))
    body = [(0.30, 0.46), (0.60, 0.30), (0.82, 0.50), (0.68, 0.76), (0.40, 0.80)]
    _poly(surf, meat, body, s)
    _outline(surf, meat_d, body, s)
    pygame.draw.ellipse(surf, fat, (0.42 * s, 0.44 * s, 0.24 * s, 0.14 * s))
    return surf


def _draw_hide(s: int) -> pygame.Surface:
    surf = _canvas(s)
    hide, hide_d = (108, 70, 44), (70, 44, 28)
    hide_l = (136, 92, 56)
    body = [(0.50, 0.08), (0.74, 0.16), (0.86, 0.36), (0.78, 0.56),
            (0.88, 0.72), (0.72, 0.86), (0.50, 0.92), (0.28, 0.86),
            (0.12, 0.72), (0.22, 0.56), (0.14, 0.36), (0.26, 0.16)]
    _poly(surf, hide_d, body, s)
    inner = [(x * 0.92 + 0.04, y * 0.92 + 0.04) for x, y in body]
    _poly(surf, hide, inner, s)
    pygame.draw.ellipse(surf, hide_l, (0.30 * s, 0.32 * s, 0.40 * s, 0.36 * s))
    for yy in (0.38, 0.48, 0.58, 0.68):
        pygame.draw.line(surf, hide_d, _pt((0.34, yy), s), _pt((0.66, yy), s), 1)
    return surf


def _draw_cotton(s: int) -> pygame.Surface:
    """A fluffy white cotton boll."""
    surf = _canvas(s)
    white, white_s, husk = (248, 250, 252), (224, 230, 238), (104, 70, 40)
    c = 0.5 * s
    pygame.draw.circle(surf, husk, (int(c), int(0.62 * s)), int(0.16 * s))
    for dx, dy, r in ((0.0, -0.04, 0.30), (-0.14, -0.12, 0.22),
                      (0.14, -0.12, 0.22), (-0.08, 0.06, 0.20),
                      (0.08, 0.06, 0.20), (0.0, -0.22, 0.18)):
        pygame.draw.circle(surf, white, (int(c + dx * s), int(c + dy * s)), int(r * s))
    pygame.draw.circle(surf, white_s, (int(c + 0.08 * s), int(c + 0.10 * s)), int(0.12 * s))
    pygame.draw.circle(surf, (255, 255, 255), (int(c - 0.08 * s), int(c - 0.16 * s)), int(0.08 * s))
    return surf


def _draw_cotton_seed(s: int) -> pygame.Surface:
    return _draw_seeds(s, (176, 136, 78), (124, 90, 50))


def _draw_bed(s: int) -> pygame.Surface:
    """A small bed, top-down: mattress, blanket and a pillow."""
    surf = _canvas(s)
    wood = (118, 78, 44)
    wood_d = (78, 50, 28)
    blanket = (196, 120, 88)
    blanket_d = (150, 84, 60)
    sheet = (240, 238, 232)
    pillow = (252, 250, 246)
    # frame
    pygame.draw.rect(surf, wood_d, (0.16 * s, 0.30 * s, 0.68 * s, 0.46 * s), border_radius=int(0.04 * s))
    pygame.draw.rect(surf, wood, (0.19 * s, 0.33 * s, 0.62 * s, 0.40 * s), border_radius=int(0.03 * s))
    # mattress/sheet
    pygame.draw.rect(surf, sheet, (0.22 * s, 0.36 * s, 0.56 * s, 0.34 * s), border_radius=int(0.03 * s))
    # pillow at the head
    pygame.draw.rect(surf, pillow, (0.22 * s, 0.36 * s, 0.14 * s, 0.34 * s), border_radius=int(0.04 * s))
    pygame.draw.rect(surf, (200, 198, 192), (0.22 * s, 0.36 * s, 0.14 * s, 0.34 * s), 1, border_radius=int(0.04 * s))
    # blanket folded over the foot half
    pygame.draw.rect(surf, blanket_d, (0.46 * s, 0.36 * s, 0.32 * s, 0.34 * s), border_radius=int(0.03 * s))
    pygame.draw.rect(surf, blanket, (0.48 * s, 0.38 * s, 0.28 * s, 0.30 * s), border_radius=int(0.02 * s))
    for yy in (0.42, 0.50, 0.58):
        pygame.draw.line(surf, blanket_d, (0.48 * s, yy * s), (0.76 * s, yy * s), 1)
    return surf


def _draw_cooked_meat(s: int) -> pygame.Surface:
    surf = _canvas(s)
    meat, meat_d = (156, 92, 48), (104, 56, 26)
    bone, sear = (232, 222, 200), (196, 150, 92)
    pygame.draw.line(surf, bone, _pt((0.20, 0.80), s), _pt((0.82, 0.28), s), int(0.12 * s))
    body = [(0.28, 0.48), (0.58, 0.28), (0.82, 0.48), (0.66, 0.76), (0.38, 0.78)]
    _poly(surf, meat, body, s)
    _outline(surf, meat_d, body, s)
    pygame.draw.ellipse(surf, sear, (0.40 * s, 0.42 * s, 0.26 * s, 0.16 * s))
    return surf


def _draw_bread(s: int) -> pygame.Surface:
    surf = _canvas(s)
    crust, crust_d, top = (168, 114, 58), (112, 72, 34), (214, 168, 104)
    pygame.draw.ellipse(surf, crust, (0.12 * s, 0.34 * s, 0.76 * s, 0.44 * s))
    pygame.draw.ellipse(surf, crust_d, (0.12 * s, 0.34 * s, 0.76 * s, 0.44 * s), 3)
    pygame.draw.ellipse(surf, top, (0.20 * s, 0.38 * s, 0.60 * s, 0.22 * s))
    for dx in (0.32, 0.46, 0.60):
        pygame.draw.line(surf, crust, (int(dx * s), int(0.42 * s)),
                         (int((dx + 0.06) * s), int(0.56 * s)), 3)
    return surf


_DRAWERS = {
    "wheat": _draw_wheat,
    "wheat_wort": _draw_wort,
    "berry_wort": _draw_wort,
    "agave_wort": _draw_wort,
    "beer": _draw_beer,
    "liqueur": _draw_liqueur,
    "mezcal": _draw_mezcal,
    "cigar": _draw_cigar,
    "dried_mushroom": _draw_dried_mushroom,
    "rifle": _draw_rifle,
    "shotgun": _draw_shotgun,
    "pickaxe": _draw_pickaxe,
    "compass": _draw_compass,
    "iron": _draw_iron,
    "berries": _draw_berries,
    "cactus_fruit": _draw_cactus_fruit,
    "red_mushroom": _draw_red_mushroom,
    "agave": _draw_agave,
    "ammo": _draw_ammo,
    "shovel": _draw_shovel,
    "watering_can": _draw_watering_can,
    "seed_bag": _draw_seed_bag,
    "berry_seed": _draw_berry_seed,
    "mushroom_spore": _draw_mushroom_spore,
    "cactus_seed": _draw_cactus_seed,
    "agave_seed": _draw_agave_seed,
    "tobacco": _draw_tobacco,
    "first_aid": _draw_first_aid,
    "axe": _draw_axe,
    "wood": _draw_wood,
    "coin": _draw_coin,
    "wheat_seed": _draw_wheat_seed,
    "bread": _draw_bread,
    "raw_meat": _draw_raw_meat,
    "cooked_meat": _draw_cooked_meat,
    "hide": _draw_hide,
    "cotton": _draw_cotton,
    "cotton_seed": _draw_cotton_seed,
    "bed": _draw_bed,
}

_cache: dict[tuple[str, int], pygame.Surface] = {}


def icon(item_id: str, size: int = 48) -> pygame.Surface:
    key = (item_id, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    drawer = _DRAWERS.get(item_id)
    if drawer is None:                     # never crash the UI over a new item
        s0 = pygame.Surface((128, 128), pygame.SRCALPHA)
        pygame.draw.rect(s0, (96, 88, 72), (24, 30, 80, 68), border_radius=10)
        pygame.draw.rect(s0, (58, 52, 42), (24, 30, 80, 68), 4, border_radius=10)
        big = s0
    else:
        big = drawer(128)
    surf = pygame.transform.smoothscale(big, (size, size))
    _cache[key] = surf
    return surf
