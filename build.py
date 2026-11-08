"""Build menu.

Press B to open it; pick a building to start placing it.

Houses go outdoors; a Workshop can only be placed *inside* a house (it needs a
floor and walls). The menu only offers what is valid where you are standing.
"""

from __future__ import annotations

import pygame

BUILDINGS = [
    {"id": "fence", "name": "Fence", "wood": 10, "where": "outside"},
    {"id": "gate", "name": "Gate", "wood": 30, "where": "outside"},
    # THE TRADES, OUT OF DOORS. A bench, a brewhouse, a forge and a shaft
    # are things a man puts on his own ground -- not only inside a house.
    # Only legal in the wilderness or in the player's own hub (see
    # hubs.land_ok), and in the wild the ground becomes his.
    # A PLOT IS MARKED, NOT BUILT: no wood, and it is a rectangle he draws.
    {"id": "plot", "name": "Plot", "wood": 0, "where": "outside"},
    # ...and the opposite: take something of his down with one click.
    {"id": "demolish", "name": "Demolish", "wood": 0, "where": "outside"},
    {"id": "lab", "name": "Artisan's bench", "wood": 150, "where": "outside"},
    {"id": "brewery", "name": "Brewhouse", "wood": 120, "where": "outside"},
    # THE PLAYER'S OWN SHOP. It stands inside his hub (main refuses it
    # anywhere else) and it is the one place his goods may be sold from.
    {"id": "stall", "name": "Market stall", "wood": 100, "where": "outside"},
    # THE YARD'S OWN SCHOOL OF ARMS. A soldier works at one of these, and the
    # post is what makes him better than a man with a gun.
    {"id": "dummy", "name": "Training dummy", "wood": 40, "where": "outside"},
    {"id": "target", "name": "Archery target", "wood": 60, "where": "outside"},
    # A FORGE IS IRON -- not wood alone.
    {"id": "smith", "name": "Forge", "wood": 0,
     "cost": {"iron": 300}, "where": "outside"},
]


def build_materials(building_id: str) -> dict:
    """EVERYTHING IT TAKES, by item. Wood alone was never the whole story."""
    for b in BUILDINGS:
        if b["id"] == building_id:
            return dict(b.get("cost") or {"wood": b.get("wood", 0)})
    return {}


def build_cost(building_id: str) -> int:
    for b in BUILDINGS:
        if b["id"] == building_id:
            return b["wood"]
    return 0

def stall_icon(size: int = 46) -> pygame.Surface:
    """A striped awning over a counter -- what a stall looks like from above."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    w, h = size, size
    for i in range(5):
        x0 = int(i * w / 5)
        x1 = int((i + 1) * w / 5)
        pygame.draw.rect(s, (196, 176, 140) if i % 2 == 0 else (168, 78, 62),
                         (x0, int(h * 0.10), max(1, x1 - x0 - 1),
                          int(h * 0.26)))
    pygame.draw.rect(s, (96, 74, 50), (int(w * 0.08), int(h * 0.58),
                                       int(w * 0.84), int(h * 0.22)),
                     border_radius=3)
    for px in (int(w * 0.10), int(w * 0.86)):
        pygame.draw.rect(s, (92, 70, 46), (px, int(h * 0.32), max(2, int(w * 0.04)),
                                           int(h * 0.26)))
    return s


def dummy_icon(size: int = 46) -> pygame.Surface:
    """A post with a sack head and a crossbar -- a thing to hit."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(s, (110, 78, 48), (int(size * 0.46), int(size * 0.20),
                                        max(2, int(size * 0.08)),
                                        int(size * 0.70)))
    pygame.draw.rect(s, (126, 92, 58), (int(size * 0.22), int(size * 0.34),
                                        int(size * 0.56), max(2, int(size * 0.08))))
    pygame.draw.circle(s, (186, 168, 128), (int(size * 0.50), int(size * 0.20)),
                       int(size * 0.13))
    pygame.draw.circle(s, (60, 48, 34), (int(size * 0.50), int(size * 0.20)),
                       int(size * 0.13), 2)
    # and the axe in it, because that is what it is for
    pygame.draw.line(s, (70, 54, 36), (int(size * 0.26), int(size * 0.30)),
                     (int(size * 0.42), int(size * 0.52)), 2)
    pygame.draw.polygon(s, (176, 180, 186),
                        [(int(size * 0.40), int(size * 0.46)),
                         (int(size * 0.52), int(size * 0.54)),
                         (int(size * 0.46), int(size * 0.62))])
    return s


def target_icon(size: int = 46) -> pygame.Surface:
    """A straw round on legs: rings, and a few arrows in it."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = int(size * 0.50), int(size * 0.42)
    for i, (r, col) in enumerate(((int(size * 0.34), (222, 214, 186)),
                                  (int(size * 0.24), (188, 78, 62)),
                                  (int(size * 0.14), (222, 214, 186)),
                                  (int(size * 0.06), (188, 78, 62)))):
        pygame.draw.circle(s, col, (cx, cy), r)
    pygame.draw.circle(s, (72, 58, 40), (cx, cy), int(size * 0.34), 2)
    pygame.draw.line(s, (110, 78, 48), (int(size * 0.34), int(size * 0.74)),
                     (int(size * 0.30), int(size * 0.94)), 2)
    pygame.draw.line(s, (110, 78, 48), (int(size * 0.66), int(size * 0.74)),
                     (int(size * 0.70), int(size * 0.94)), 2)
    return s


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

    ROWS = 3                      # THREE ROWS OF BUILDINGS, ALWAYS

    def _layout(self, sw: int, sh: int):
        """A GRID, THREE ROWS DEEP. One tall column ran off the bottom of the
        screen as soon as the list grew; three rows read across instead."""
        visible = self._visible()
        n = len(visible)
        cols = max(1, (n + self.ROWS - 1) // self.ROWS)
        pad = 14
        cell_h = 66
        # the cells shrink to fit the window instead of hanging off it
        avail_w = max(320, sw - 80)
        cell_w = max(150, min(300, (avail_w - (cols + 1) * pad) // cols))
        width = cols * cell_w + (cols + 1) * pad
        height = 56 + self.ROWS * cell_h + 30
        width = min(width, sw - 20)
        height = min(height, sh - 20)
        x0 = (sw - width) // 2
        y0 = (sh - height) // 2
        rows = []
        for i in range(n):
            r, c = i // cols, i % cols
            rows.append(pygame.Rect(x0 + pad + c * (cell_w + pad),
                                    y0 + 50 + r * cell_h,
                                    cell_w, cell_h - 12))
        return pygame.Rect(x0, y0, width, height), rows, visible

    def affordable(self, index: int) -> bool:
        """EVERY MATERIAL, not just wood -- a forge is 300 iron and no wood,
        and it used to read as affordable with an empty pocket."""
        if self.free:
            return True
        for item, qty in build_materials(BUILDINGS[index]["id"]).items():
            if self.inv.count_of(item) < qty:
                return False
        return True

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
                       "lab_table": lab_icon, "lab": lab_icon,
                       "brew_table": brew_icon, "barrel": barrel_icon,
                       "brewery": brew_icon, "smith": workshop_icon,
                       "mine": workshop_icon, "plot": fence_icon,
                       "stall": stall_icon,
                       "dummy": dummy_icon, "target": target_icon,
                       "demolish": fence_icon,
                       "fence": fence_icon, "gate": gate_icon}[building["id"]]
            icon = icon_fn(rect.height - 14)
            screen.blit(icon, (rect.left + 10, rect.centery - icon.get_height() // 2))

            name = self.font.render(building["name"], True,
                                    (232, 232, 238) if ok else (142, 142, 150))
            screen.blit(name, (rect.left + icon.get_width() + 20, rect.top + 9))
            _mats = build_materials(building["id"])
            _txt = "  +  ".join("%d %s" % (q, it) for it, q in _mats.items()) or "free"
            cost = self.font_small.render(f"{_txt}  (have {wood})", True,
                                          (206, 184, 122) if ok else (176, 112, 112))
            screen.blit(cost, (rect.left + icon.get_width() + 20, rect.top + 34))

        hint = self.font_small.render("B / Esc to close", True, (138, 138, 148))
        screen.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 26))
