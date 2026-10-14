"""Build menu.

Press B to open it; pick a building to start placing it.

Houses go outdoors; a Workshop can only be placed *inside* a house (it needs a
floor and walls). The menu only offers what is valid where you are standing.
"""

from __future__ import annotations

import pygame

BUILDINGS = [
    {"id": "house", "name": "House", "wood": 100, "where": "outside"},
    {"id": "workshop", "name": "Workshop", "wood": 300, "where": "inside"},
    {"id": "lab_table", "name": "Lab Table", "wood": 150, "where": "inside"},
    {"id": "brew_table", "name": "Brewing Table", "wood": 120, "where": "inside"},
    {"id": "barrel", "name": "Barrel", "wood": 60, "where": "inside"},
    {"id": "fence", "name": "Fence", "wood": 10, "where": "outside"},
    {"id": "gate", "name": "Gate", "wood": 30, "where": "outside"},
]


def build_cost(building_id: str) -> int:
    for b in BUILDINGS:
        if b["id"] == building_id:
            return b["wood"]
    return 0

_ICON = None
_WS_ICON = None
_LAB_ICON = None


def brew_icon(size: int = 46) -> pygame.Surface:
    global _LAB_ICON
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    top = pygame.Rect(size * 0.08, size * 0.50, size * 0.84, size * 0.28)
    pygame.draw.rect(s, (138, 96, 58), top, border_radius=3)
    pygame.draw.rect(s, (72, 50, 32), top, 2, border_radius=3)
    pygame.draw.rect(s, (160, 170, 150), (size * 0.16, size * 0.30,
                                          size * 0.13, size * 0.20))
    pygame.draw.rect(s, (188, 150, 74), (size * 0.36, size * 0.26,
                                         size * 0.15, size * 0.24))
    pygame.draw.ellipse(s, (130, 86, 50), (size * 0.60, size * 0.20,
                                           size * 0.26, size * 0.32))
    return s


def barrel_icon(size: int = 46) -> pygame.Surface:
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    r = pygame.Rect(size * 0.24, size * 0.12, size * 0.52, size * 0.76)
    pygame.draw.ellipse(s, (130, 86, 50), r)
    pygame.draw.ellipse(s, (78, 52, 30), r, 2)
    pygame.draw.line(s, (196, 196, 200), (r.x + 3, r.centery),
                     (r.right - 3, r.centery), 2)
    return s


def lab_icon(size: int = 46) -> pygame.Surface:
    """The player's own laboratory bench: glassware and a still."""
    global _LAB_ICON
    if _LAB_ICON is None or _LAB_ICON.get_width() != size:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        top = pygame.Rect(size * 0.08, size * 0.50, size * 0.84, size * 0.30)
        pygame.draw.rect(s, (150, 104, 62), top, border_radius=3)
        pygame.draw.rect(s, (78, 54, 34), top, 2, border_radius=3)
        pygame.draw.rect(s, (152, 204, 182), (size * 0.18, size * 0.28,
                                              size * 0.13, size * 0.22))
        pygame.draw.rect(s, (176, 224, 204), (size * 0.38, size * 0.20,
                                              size * 0.13, size * 0.30))
        pygame.draw.circle(s, (206, 158, 74),
                           (int(size * 0.72), int(size * 0.40)), int(size * 0.12))
        pygame.draw.circle(s, (140, 104, 48),
                           (int(size * 0.72), int(size * 0.40)), int(size * 0.12), 2)
        _LAB_ICON = s
    return _LAB_ICON


def house_icon(size: int = 46) -> pygame.Surface:
    global _ICON
    if _ICON is None or _ICON.get_width() != size:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        body = pygame.Rect(size * 0.24, size * 0.46, size * 0.52, size * 0.40)
        pygame.draw.rect(s, (226, 210, 182), body)
        pygame.draw.rect(s, (150, 128, 100), body, 2)
        roof = [(size * 0.10, size * 0.50), (size * 0.5, size * 0.14),
                (size * 0.90, size * 0.50)]
        pygame.draw.polygon(s, (150, 76, 58), roof)
        pygame.draw.polygon(s, (60, 44, 38), roof, 2)
        pygame.draw.rect(s, (116, 76, 46), (size * 0.42, size * 0.64,
                                            size * 0.16, size * 0.22))
        _ICON = s
    return _ICON


def workshop_icon(size: int = 46) -> pygame.Surface:
    global _WS_ICON
    if _WS_ICON is None or _WS_ICON.get_width() != size:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        # workbench
        body = pygame.Rect(size * 0.12, size * 0.48, size * 0.76, size * 0.38)
        pygame.draw.rect(s, (150, 104, 62), body, border_radius=3)
        pygame.draw.rect(s, (78, 54, 34), body, 2, border_radius=3)
        pygame.draw.rect(s, (110, 110, 118),
                         (size * 0.18, size * 0.46, size * 0.64, size * 0.10),
                         border_radius=2)
        # anvil
        pygame.draw.rect(s, (86, 86, 96), (size * 0.22, size * 0.28,
                                           size * 0.22, size * 0.18), border_radius=2)
        # tools on the wall
        pygame.draw.line(s, (150, 110, 60), (size * 0.66, size * 0.16),
                         (size * 0.74, size * 0.40), 2)
        pygame.draw.rect(s, (176, 176, 184), (size * 0.62, size * 0.12,
                                              size * 0.14, size * 0.08))
        _WS_ICON = s
    return _WS_ICON


def fence_icon(size: int = 46) -> pygame.Surface:
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(4):
        x = size * (0.12 + 0.22 * i)
        pygame.draw.rect(s, (150, 108, 64), (x, size * 0.22, size * 0.08, size * 0.58))
        pygame.draw.rect(s, (92, 62, 36), (x, size * 0.22, size * 0.08, size * 0.58), 1)
    pygame.draw.rect(s, (172, 128, 76), (size * 0.08, size * 0.34, size * 0.84, size * 0.09))
    pygame.draw.rect(s, (172, 128, 76), (size * 0.08, size * 0.58, size * 0.84, size * 0.09))
    return s


def gate_icon(size: int = 46) -> pygame.Surface:
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for x in (size * 0.16, size * 0.76):
        pygame.draw.rect(s, (58, 40, 26), (x, size * 0.18, size * 0.09, size * 0.64))
        pygame.draw.rect(s, (206, 160, 96), (x + 1, size * 0.20, size * 0.05, size * 0.60))
    pygame.draw.rect(s, (58, 40, 26), (size * 0.14, size * 0.16, size * 0.72, size * 0.07))
    pygame.draw.rect(s, (206, 160, 96), (size * 0.15, size * 0.18, size * 0.70, size * 0.04))
    pygame.draw.line(s, (172, 128, 76), (size * 0.26, size * 0.36),
                     (size * 0.74, size * 0.36), 3)
    pygame.draw.line(s, (172, 128, 76), (size * 0.26, size * 0.62),
                     (size * 0.74, size * 0.62), 3)
    return s


class BuildMenu:
    def __init__(self, inventory) -> None:
        self.inv = inventory
        self.where = "outside"
        self.hover = -1
        self.free = False
        self.font_title = pygame.font.SysFont("dejavusans", 22, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)

    def open(self, where: str) -> None:
        self.where = where
        self.hover = -1

    def _visible(self) -> list[int]:
        return [i for i, b in enumerate(BUILDINGS) if b["where"] == self.where]

    def _layout(self, sw: int, sh: int):
        visible = self._visible()
        width = 400
        row_h = 68
        pad = 14
        height = 56 + len(visible) * row_h + 36
        x0 = (sw - width) // 2
        y0 = (sh - height) // 2
        rows = [pygame.Rect(x0 + pad, y0 + 50 + i * row_h, width - 2 * pad, row_h - 12)
                for i in range(len(visible))]
        return pygame.Rect(x0, y0, width, height), rows, visible

    def affordable(self, index: int) -> bool:
        return self.free or self.inv.count_of("wood") >= BUILDINGS[index]["wood"]

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _, rows, visible = self._layout(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i, rect in enumerate(rows):
                if rect.collidepoint(event.pos):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(rows):
                if rect.collidepoint(event.pos) and self.affordable(visible[i]):
                    return BUILDINGS[visible[i]]["id"]
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, rows, visible = self._layout(sw, sh)

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))

        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 240), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, (72, 72, 80), board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        where = "indoors" if self.where == "inside" else "outdoors"
        title = self.font_title.render("BUILD  (%s)" % where, True, (216, 216, 222))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 8))

        wood = self.inv.count_of("wood")
        for i, (bi, rect) in enumerate(zip(visible, rows)):
            building = BUILDINGS[bi]
            ok = self.affordable(bi)
            hovered = (i == self.hover) and ok
            pygame.draw.rect(screen, (48, 46, 40) if hovered else (34, 34, 40),
                             rect, border_radius=8)
            border = (222, 176, 88) if hovered else ((104, 132, 92) if ok else (110, 66, 66))
            pygame.draw.rect(screen, border, rect, width=2, border_radius=8)

            icon_fn = {"house": house_icon, "workshop": workshop_icon,
                       "lab_table": lab_icon,
                       "brew_table": brew_icon, "barrel": barrel_icon,
                       "fence": fence_icon, "gate": gate_icon}[building["id"]]
            icon = icon_fn(rect.height - 14)
            screen.blit(icon, (rect.left + 10, rect.centery - icon.get_height() // 2))

            name = self.font.render(building["name"], True,
                                    (232, 232, 238) if ok else (142, 142, 150))
            screen.blit(name, (rect.left + icon.get_width() + 20, rect.top + 9))
            cost = self.font_small.render(f"{building['wood']} wood  (have {wood})", True,
                                          (206, 184, 122) if ok else (176, 112, 112))
            screen.blit(cost, (rect.left + icon.get_width() + 20, rect.top + 34))

        hint = self.font_small.render("B / Esc to close", True, (138, 138, 148))
        screen.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 26))
