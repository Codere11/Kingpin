"""Workshop crafting menu.

Open it by pressing E next to a workshop you placed inside a house. Spend wood
and iron to craft tools and guns.
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
    # THE SAME MATERIAL THE GUNWORKS USES. The player was turning out rifles
    # for a hundred iron and five cartridges per iron -- a twentieth of what a
    # village smith needs for the same work.
    {"id": "rifle", "name": "Rifle",
     "cost": {"iron": industry.GUN_IRON, "wood": industry.GUN_WOOD}},
    {"id": "shotgun", "name": "Shotgun",
     "cost": {"iron": industry.GUN_IRON, "wood": industry.GUN_WOOD}},
    {"id": "ammo", "name": "Ammo",
     "cost": {"iron": industry.AMMO_IRON, "wood": industry.AMMO_WOOD},
     "yield": 1},
]

_COST = {c["id"]: c["cost"] for c in CRAFTS}
_YIELD = {c["id"]: c.get("yield", 1) for c in CRAFTS}


def craft_cost(item_id: str) -> dict:
    return _COST.get(item_id, {})


def craft_yield(item_id: str) -> int:
    return _YIELD.get(item_id, 1)


class WorkshopMenu:
    def __init__(self, inventory) -> None:
        self.inv = inventory
        self.hover = -1
        self.free = False
        self.font_title = pygame.font.SysFont("dejavusans", 20, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)

    def _layout(self, sw: int, sh: int):
        width = 430
        row_h = 58
        pad = 14
        height = 52 + len(CRAFTS) * row_h + 34
        x0 = (sw - width) // 2
        y0 = (sh - height) // 2
        rows = [pygame.Rect(x0 + pad, y0 + 46 + i * row_h, width - 2 * pad, row_h - 8)
                for i in range(len(CRAFTS))]
        return pygame.Rect(x0, y0, width, height), rows

    def affordable(self, index: int) -> bool:
        if self.free:
            return True
        return all(self.inv.count_of(k) >= v for k, v in CRAFTS[index]["cost"].items())

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _, rows = self._layout(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i, rect in enumerate(rows):
                if rect.collidepoint(event.pos):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(rows):
                if rect.collidepoint(event.pos) and self.affordable(i):
                    return CRAFTS[i]
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, rows = self._layout(sw, sh)

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))

        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 240), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, (72, 72, 80), board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        title = self.font_title.render("WORKSHOP", True, (222, 214, 196))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 8))

        for i, (craft, rect) in enumerate(zip(CRAFTS, rows)):
            ok = self.affordable(i)
            hovered = (i == self.hover) and ok
            pygame.draw.rect(screen, (48, 46, 40) if hovered else (34, 34, 40),
                             rect, border_radius=8)
            border = (222, 176, 88) if hovered else ((104, 132, 92) if ok else (110, 66, 66))
            pygame.draw.rect(screen, border, rect, width=2, border_radius=8)

            icon = items.icon(craft["id"], rect.height - 10)
            screen.blit(icon, (rect.left + 10, rect.centery - icon.get_height() // 2))

            name = self.font.render(craft["name"], True,
                                    (232, 232, 238) if ok else (142, 142, 150))
            screen.blit(name, (rect.left + icon.get_width() + 20, rect.top + 7))
            parts = []
            for k, v in craft["cost"].items():
                parts.append(f"{v} {k} (have {self.inv.count_of(k)})")
            cost = self.font_small.render("   ".join(parts), True,
                                          (206, 184, 122) if ok else (176, 112, 112))
            screen.blit(cost, (rect.left + icon.get_width() + 20, rect.top + 30))

        hint = self.font_small.render("E / Esc to close", True, (138, 138, 148))
        screen.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 24))
