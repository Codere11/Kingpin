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
    pygame.draw.rect(screen, (78, 50, 28), (x, y, TILE, TILE), 1)
    for i in range(3):
        yy = y + 5 + i * 9
        pygame.draw.line(screen, (78, 50, 28), (x + 2, yy), (x + TILE - 2, yy), 1)
    # side seams so the planks read as separate boards
    pygame.draw.line(screen, (78, 50, 28), (x + TILE // 2, y), (x + TILE // 2, y + 5), 1)


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
    return True
