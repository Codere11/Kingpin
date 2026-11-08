"""block.py -- Minecraft-style 1x1 blocks.

A buildable in the hand shows a 1x1 grid mesh, and a left click places a block
in the hovered square. Blocks are 1 tile (TILE x TILE) and snap to the grid.
"""
import pygame
from world import TILE


# what counts as a block you can place in the hand
BUILDABLE = ("wood",)


def _wood_block(screen, x, y):
    """A 1x1 plank block, like a Minecraft plank."""
    pygame.draw.rect(screen, (118, 78, 44), (x, y, TILE, TILE))
    pygame.draw.rect(screen, (78, 50, 28), (x, y, TILE, TILE), 2)
    # a little depth: light top-left edge, dark bottom-right edge
    pygame.draw.line(screen, (156, 110, 62), (x + 1, y + 1), (x + TILE - 2, y + 1), 2)
    pygame.draw.line(screen, (156, 110, 62), (x + 1, y + 1), (x + 1, y + TILE - 2), 2)
    pygame.draw.line(screen, (60, 38, 22), (x + 2, y + TILE - 2), (x + TILE - 2, y + TILE - 2), 2)
    pygame.draw.line(screen, (60, 38, 22), (x + TILE - 2, y + 2), (x + TILE - 2, y + TILE - 2), 2)
    for i in range(2):
        yy = y + 9 + i * 12
        pygame.draw.line(screen, (78, 50, 28), (x + 3, yy), (x + TILE - 3, yy), 1)
    pygame.draw.line(screen, (78, 50, 28), (x + TILE // 2, y + 2), (x + TILE // 2, y + 8), 1)


def draw_blocks(screen, blocks, cam_x, cam_y, view):
    """Every placed block, snapped to its square."""
    for (tx, ty), kind in blocks.items():
        wx = tx * TILE
        wy = ty * TILE
        if not view.collidepoint(wx + TILE / 2.0, wy + TILE / 2.0):
            continue
        x = wx - cam_x
        y = wy - cam_y
        if kind == "wood":
            _wood_block(screen, int(x), int(y))


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
    """A block kills what was growing in its square: the stump goes, and the
    wild plant never regrows."""
    wx = tx * TILE + TILE / 2.0
    wy = ty * TILE + TILE / 2.0
    try:
        for t in list(getattr(g.trees, "_stumps", ())):
            if abs(t.x - wx) < TILE and abs(t.y - wy) < TILE:
                g.trees._stumps.remove(t)
    except Exception:
        pass
    try:
        g.world.wild_eaten[(tx, ty)] = float("inf")
    except Exception:
        pass
