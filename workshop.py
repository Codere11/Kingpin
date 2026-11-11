"""Workshop crafting menu.

Open it by pressing E next to a workbench. Spend wood and iron to craft tools.
"""

from __future__ import annotations

import pygame

import industry
import items

CRAFTS = [
    {"id": "shovel", "name": "Shovel", "cost": {"wood": 50}},
    {"id": "watering_can", "name": "Watering Can", "cost": {"wood": 30}},
    {"id": "pickaxe", "name": "Pickaxe", "cost": {"wood": 100}},
    {"id": "compass", "name": "Compass", "cost": {"iron": 100}},
    # A BED, out of the cotton you grow.
    {"id": "bed", "name": "Bed", "cost": {"cotton": 30}},
    # A BOW AND ITS ARROWS: ten arrows out of one piece of wood.
    {"id": "bow", "name": "Bow", "cost": {"wood": 30}},
    {"id": "arrow", "name": "Arrows", "cost": {"wood": 1}, "yield": 10},
    # HIDE ARMOR: only once it is researched.
    {"id": "hide_armor", "name": "Hide Armor", "cost": {"hide": 30},
     "requires": "hide_armor"},
]

_COST = {c["id"]: c["cost"] for c in CRAFTS}
_YIELD = {c["id"]: c.get("yield", 1) for c in CRAFTS}


def available_crafts(g=None) -> list:
    """The craft list, hiding anything whose research is not done yet."""
    out = []
    for c in CRAFTS:
        req = c.get("requires")
        if req:
            try:
                import research
                if g is None or research.state(g, req) != "done":
                    continue
            except Exception:
                continue
        out.append(c)
    return out


def craft_cost(item_id: str) -> dict:
    return _COST.get(item_id, {})


def craft_yield(item_id: str) -> int:
    return _YIELD.get(item_id, 1)


class WorkshopMenu:
    COLS = 2                       # a compact grid, so it always fits the view

    def __init__(self, inventory, g=None) -> None:
        self.inv = inventory
        self.g = g
        self.hover = -1
        self.free = False
        self.font_title = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 14, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 11, bold=True)

    def _layout(self, sw: int, sh: int):
        crafts = available_crafts(self.g)
        n = len(crafts)
        cols = self.COLS
        rows = max(1, (n + cols - 1) // cols)
        pad = 10
        cell_w = min(200, max(110, (sw - 60) // cols))
        cell_h = 46
        width = cols * cell_w + (cols + 1) * pad
        height = 32 + rows * cell_h + 16
        width = min(width, sw - 16)
        height = min(height, sh - 16)
        x0 = (sw - width) // 2
        y0 = (sh - height) // 2
        cells = []
        for i in range(n):
            r, c = divmod(i, cols)
            cells.append(pygame.Rect(x0 + pad + c * (cell_w + pad),
                                     y0 + 30 + r * cell_h,
                                     cell_w, cell_h - 6))
        return pygame.Rect(x0, y0, width, height), cells

    def affordable(self, index: int) -> bool:
        if self.free:
            return True
        return all(self.inv.count_of(k) >= v for k, v in available_crafts(self.g)[index]["cost"].items())

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _, cells = self._layout(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i, rect in enumerate(cells):
                if rect.collidepoint(event.pos):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            crafts = available_crafts(self.g)
            for i, rect in enumerate(cells):
                if rect.collidepoint(event.pos) and self.affordable(i):
                    return crafts[i]
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, cells = self._layout(sw, sh)

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))

        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 240), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, (72, 72, 80), board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        title = self.font_title.render("WORKBENCH", True, (222, 214, 196))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 6))

        for i, (craft, rect) in enumerate(zip(available_crafts(self.g), cells)):
            ok = self.affordable(i)
            hovered = (i == self.hover) and ok
            pygame.draw.rect(screen, (48, 46, 40) if hovered else (34, 34, 40),
                             rect, border_radius=8)
            border = (222, 176, 88) if hovered else ((104, 132, 92) if ok else (110, 66, 66))
            pygame.draw.rect(screen, border, rect, width=2, border_radius=8)

            icon = items.icon(craft["id"], rect.height - 12)
            screen.blit(icon, (rect.left + 6, rect.centery - icon.get_height() // 2))

            name = self.font.render(craft["name"], True,
                                    (232, 232, 238) if ok else (142, 142, 150))
            screen.blit(name, (rect.left + icon.get_width() + 12, rect.top + 5))
            parts = []
            for k, v in craft["cost"].items():
                parts.append(f"{v} {k} ({self.inv.count_of(k)})")
            cost = self.font_small.render("  ".join(parts), True,
                                          (206, 184, 122) if ok else (176, 112, 112))
            screen.blit(cost, (rect.left + icon.get_width() + 12, rect.top + 24))
