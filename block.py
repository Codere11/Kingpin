"""block.py -- Minecraft-style 1x1 blocks.

A buildable in the hand shows a 1x1 grid mesh, and a left click places a block
in the hovered square. Blocks are 1 tile (TILE x TILE) and snap to the grid.
"""
import pygame
from world import TILE
import math


# what counts as a block you can place in the hand
BUILDABLE = ("wood", "hide", "bed")


# colours: fill, light bevel, dark shadow, grain/edge
_COLORS = {
    "wood": {"fill": (118, 78, 44), "light": (156, 110, 62),
             "dark": (60, 38, 22), "edge": (78, 50, 28)},
    "hide": {"fill": (124, 86, 54), "light": (166, 122, 74),
             "dark": (66, 42, 26), "edge": (82, 54, 34)},
}


def _fill_block(screen, x, y, kind):
    """The block's face only -- no border, so a row stays one solid wall."""
    c = _COLORS[kind]
    pygame.draw.rect(screen, c["fill"], (x, y, TILE, TILE))
    if kind == "wood":
        for i in range(2):
            yy = y + 9 + i * 12
            pygame.draw.line(screen, c["edge"], (x + 3, yy), (x + TILE - 3, yy), 1)
        pygame.draw.line(screen, c["edge"], (x + TILE // 2, y + 2),
                         (x + TILE // 2, y + 8), 1)
    elif kind == "hide":
        hem = y + TILE - 7
        pygame.draw.rect(screen, c["edge"], (x + 1, hem, TILE - 2, 6))
        for i in range(2, TILE - 3, 4):
            pygame.draw.line(screen, c["light"], (x + i, hem + 2),
                             (x + i, hem + 4), 1)
        for i in range(2, TILE - 2, 4):
            pygame.draw.line(screen, c["edge"], (x + i, y + TILE - 2),
                             (x + i, y + TILE - 1), 1)


def _edges(screen, x, y, kind, up, down, left, right):
    """Only the EXPOSED sides get the bevel/shadow; a neighbour on a side
    means no line there, so a row is one continuous wall."""
    c = _COLORS[kind]
    if not up:
        pygame.draw.line(screen, c["light"], (x + 1, y + 1),
                         (x + TILE - 2, y + 1), 2)
    if not left:
        pygame.draw.line(screen, c["light"], (x + 1, y + 1),
                         (x + 1, y + TILE - 2), 2)
    if not down:
        pygame.draw.line(screen, c["dark"], (x + 2, y + TILE - 2),
                         (x + TILE - 2, y + TILE - 2), 2)
    if not right:
        pygame.draw.line(screen, c["dark"], (x + TILE - 2, y + 2),
                         (x + TILE - 2, y + TILE - 2), 2)


def _bed_block(screen, x, y):
    """A 1x1 white bedroll, top-down -- no dark frame, no shadow."""
    wood = (118, 78, 44)
    sheet = (250, 250, 248)
    pillow = (255, 255, 255)
    blanket = (232, 232, 230)
    blanket_d = (188, 188, 186)
    pygame.draw.rect(screen, wood, (x + 3, y + 5, TILE - 6, TILE - 10), border_radius=2)
    pygame.draw.rect(screen, sheet, (x + 5, y + 7, TILE - 10, TILE - 14), border_radius=2)
    pygame.draw.rect(screen, pillow, (x + 5, y + 7, 6, TILE - 14), border_radius=2)
    pygame.draw.rect(screen, (210, 210, 208), (x + 5, y + 7, 6, TILE - 14), 1, border_radius=2)
    pygame.draw.rect(screen, blanket, (x + 13, y + 12, TILE - 20, TILE - 22), border_radius=2)
    pygame.draw.rect(screen, blanket_d, (x + 13, y + 12, TILE - 20, TILE - 22), 1, border_radius=2)
    pygame.draw.rect(screen, blanket_d, (x + 14, y + 7, TILE - 21, TILE - 16), border_radius=2)
    pygame.draw.rect(screen, blanket, (x + 15, y + 9, TILE - 23, TILE - 20), border_radius=2)


def draw_blocks(screen, blocks, cam_x, cam_y, view):
    """Every placed block, snapped to its square; a row merges into one wall
    with the shadow only around its outside."""
    keys = set(blocks)
    # all the faces first, so no edge ever covers a neighbour's face
    for (tx, ty), kind in blocks.items():
        wx = tx * TILE
        wy = ty * TILE
        if not view.collidepoint(wx + TILE / 2.0, wy + TILE / 2.0):
            continue
        if kind == "bed":
            _bed_block(screen, int(wx - cam_x), int(wy - cam_y))
            continue
        if kind not in _COLORS:
            kind = "wood"
        _fill_block(screen, int(wx - cam_x), int(wy - cam_y), kind)
    # then only the exposed edges
    for (tx, ty), kind in blocks.items():
        wx = tx * TILE
        wy = ty * TILE
        if not view.collidepoint(wx + TILE / 2.0, wy + TILE / 2.0):
            continue
        if kind == "bed":
            continue            # a bedroll gets no wall bevel behind it
        if kind not in _COLORS:
            kind = "wood"
        _edges(screen, int(wx - cam_x), int(wy - cam_y), kind,
               (tx, ty - 1) in keys, (tx, ty + 1) in keys,
               (tx - 1, ty) in keys, (tx + 1, ty) in keys)


def draw_grid(screen, cam_x, cam_y, vw, vh, wmouse_x, wmouse_y):
    """The 1x1 grid mesh, and the hovered square highlighted."""
    overlay = pygame.Surface((vw, vh), pygame.SRCALPHA)
    tx0 = int(cam_x // TILE) - 1
    tx1 = int((cam_x + vw) // TILE) + 1
    ty0 = int(cam_y // TILE) - 1
    ty1 = int((cam_y + vh) // TILE) + 1
    for tx in range(tx0, tx1 + 1):
        x = int(tx * TILE - cam_x)
        pygame.draw.line(overlay, (255, 255, 255, 90), (x, 0), (x, vh), 1)
    for ty in range(ty0, ty1 + 1):
        y = int(ty * TILE - cam_y)
        pygame.draw.line(overlay, (255, 255, 255, 90), (0, y), (vw, y), 1)
    # the square under the mouse: a BRIGHT white outline
    wx = cam_x + wmouse_x
    wy = cam_y + wmouse_y
    tx = int(wx // TILE)
    ty = int(wy // TILE)
    x = int(tx * TILE - cam_x)
    y = int(ty * TILE - cam_y)
    pygame.draw.rect(overlay, (255, 255, 255, 255), (x, y, TILE, TILE), 2)
    pygame.draw.rect(overlay, (0, 0, 0, 160), (x - 1, y - 1, TILE + 2, TILE + 2), 1)
    screen.blit(overlay, (0, 0))


def place_block(g, tx, ty, kind):
    """Put a block down in square (tx, ty) if it is empty. Returns True."""
    if (tx, ty) in g.built_blocks:
        return False
    if g.inventory.count_of(kind) <= 0:
        return False
    g.inventory.consume(kind, 1)
    g.built_blocks[(tx, ty)] = kind
    _clear_cell(g, tx, ty)
    return True


def _clear_cell(g, tx, ty):
    """A block kills what was growing in its square: the stump goes (out of
    the forest itself, so it is never drawn again), and the wild plant never
    regrows."""
    wx = tx * TILE + TILE / 2.0
    wy = ty * TILE + TILE / 2.0
    trees = getattr(g, "trees", None)
    if trees is not None:
        try:
            import trees as _trees
            _cell = getattr(_trees, "CELL", 180)
            for t in list(trees.near(wx, wy, TILE * 1.2)):
                if not getattr(t, "felled", False):
                    continue
                if abs(t.x - wx) < TILE and abs(t.y - wy) < TILE:
                    cx = int(math.floor(t.x / _cell))
                    cy = int(math.floor(t.y / _cell))
                    try:
                        trees._cache[(cx, cy)] = None
                        trees._presence[(cx, cy)] = None
                    except Exception:
                        pass
                    try:
                        if t in getattr(trees, "_stumps", ()):
                            trees._stumps.remove(t)
                    except Exception:
                        pass
        except Exception:
            pass
    try:
        g.world.wild_eaten[(tx, ty)] = float("inf")
    except Exception:
        pass
