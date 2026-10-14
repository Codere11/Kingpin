"""HUD -- the bottom inventory bar.

Slots are all visible. The mouse wheel moves the *selection* through the items
(wrapping around); it does not scroll the bar.
"""

from __future__ import annotations

import math

import pygame

import items
from inventory import Inventory, ItemStack
from quality import GRADES, merge as _qmerge

PANEL = (18, 18, 22, 205)
SLOT = (46, 46, 52)
SLOT_SEL = (68, 64, 52)
BORDER = (72, 72, 80)
ACCENT = (222, 176, 88)
TEXT = (216, 216, 222)
DIM = (138, 138, 148)


def stack_label(stack) -> str:
    if stack is None:
        return ""
    if stack.defn.quality and stack.quality is not None:
        return f"{stack.defn.name} ({GRADES[stack.quality]})"
    return stack.defn.name


def _draw_quality(screen, rect, stack, font) -> None:
    if stack is None or not stack.defn.quality or stack.quality is None:
        return
    text = font.render(GRADES[stack.quality], True, (255, 232, 140))
    screen.blit(text, (rect.right - text.get_width() - 3, rect.top + 2))


class Hotbar:
    def __init__(self, inventory: Inventory, slot: int = 58, pad: int = 8,
                 margin: int = 16, visible: int = 8) -> None:
        self.inv = inventory
        self.slot = slot
        self.pad = pad
        self.margin = margin
        self.visible = visible
        self.font_name = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)
        self.font_tiny = pygame.font.SysFont("dejavusans", 11)

    # -- selection ----------------------------------------------------------
    def cycle(self, delta: int) -> None:
        """Move the selection one slot, wrapping around (empty hands included)."""
        limit = min(self.visible, self.inv.capacity)
        if limit <= 0:
            return
        self.inv.select((self.inv.selected + delta) % limit)

    def first_empty(self) -> int | None:
        """Index of the first empty visible slot (an empty hand), if any."""
        limit = min(self.visible, self.inv.capacity)
        for i in range(limit):
            if self.inv.slots[i] is None:
                return i
        return None

    def select_visible(self, index: int) -> None:
        self.inv.select(index)

    # -- geometry -----------------------------------------------------------
    def _layout(self, sw: int, sh: int):
        n = min(self.visible, self.inv.capacity)
        slot, pad = self.slot, self.pad
        panel_w = n * slot + (n + 1) * pad
        panel_h = slot + 2 * pad
        x0 = (sw - panel_w) // 2
        y0 = sh - panel_h - self.margin
        rects = [pygame.Rect(x0 + pad + i * (slot + pad), y0 + pad, slot, slot)
                 for i in range(n)]
        return pygame.Rect(x0, y0, panel_w, panel_h), rects

    def slot_at(self, pos) -> int | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _, rects = self._layout(*surface.get_size())
        for i, rect in enumerate(rects):
            if rect.collidepoint(pos):
                return i
        return None

    # -- events -------------------------------------------------------------
    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            # One notch = one step. (pygame also emits legacy button 4/5
            # events for the same notch, so those are deliberately ignored.)
            self.cycle(-event.y)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                index = self.slot_at(event.pos)
                if index is not None:
                    self.inv.select(index)
                    return True
        return False

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, rects = self._layout(sw, sh)

        defn = self.inv.selected_stack()
        if defn is not None:
            label = self.font_name.render(stack_label(defn), True, TEXT)
            lx = panel.centerx - label.get_width() // 2
            ly = panel.top - 26
            plate = pygame.Surface((label.get_width() + 20, 24), pygame.SRCALPHA)
            pygame.draw.rect(plate, (18, 18, 22, 185), plate.get_rect(), border_radius=6)
            screen.blit(plate, (lx - 10, ly))
            screen.blit(label, (lx, ly + 1))

        tab = self.font_tiny.render("INVENTORY", True, DIM)
        tab_rect = pygame.Rect(panel.left, panel.top - 20, tab.get_width() + 20, 20)
        pygame.draw.rect(screen, (18, 18, 22), tab_rect,
                         border_top_left_radius=7, border_top_right_radius=7)
        screen.blit(tab, (tab_rect.left + 10, tab_rect.top + 4))

        panel_surf = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, PANEL, panel_surf.get_rect(), border_radius=12)
        pygame.draw.rect(panel_surf, BORDER, panel_surf.get_rect(), width=1, border_radius=12)
        screen.blit(panel_surf, panel.topleft)

        for i, rect in enumerate(rects):
            stack = self.inv.slots[i]
            selected = (i == self.inv.selected)
            pygame.draw.rect(screen, SLOT_SEL if selected else SLOT, rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT if selected else BORDER, rect,
                             width=2, border_radius=8)
            if stack is not None:
                ic = items.icon(stack.defn.id, self.slot - 14)
                screen.blit(ic, (rect.centerx - ic.get_width() // 2,
                                 rect.centery - ic.get_height() // 2))
                if stack.defn.stackable and stack.count > 1:
                    count = self.font_small.render(str(stack.count), True, TEXT)
                    screen.blit(count, (rect.right - count.get_width() - 5,
                                        rect.bottom - count.get_height() - 2))
                _draw_quality(screen, rect, stack, self.font_tiny)
            number = self.font_tiny.render(str(i + 1), True, DIM)
            screen.blit(number, (rect.left + 5, rect.top + 3))

    def draw_stamina(self, screen: pygame.Surface, ratio: float,
                     exhausted: bool) -> None:
        sw, sh = screen.get_size()
        panel, _ = self._layout(sw, sh)
        bar_w, bar_h = 210, 8
        x = panel.centerx - bar_w // 2
        y = panel.top - 64
        pygame.draw.rect(screen, (22, 22, 26),
                         (x - 1, y - 1, bar_w + 2, bar_h + 2), border_radius=3)
        fill = int(bar_w * max(0.0, min(1.0, ratio)))
        color = (196, 64, 52) if exhausted else (86, 156, 214)
        if fill > 0:
            pygame.draw.rect(screen, color, (x, y, fill, bar_h), border_radius=3)
        pygame.draw.rect(screen, (70, 70, 78), (x, y, bar_w, bar_h), 1, border_radius=3)

    def draw_hunger(self, screen: pygame.Surface, ratio: float) -> None:
        sw, sh = screen.get_size()
        panel, _ = self._layout(sw, sh)
        bar_w, bar_h = 210, 8
        x = panel.centerx - bar_w // 2
        y = panel.top - 52
        pygame.draw.rect(screen, (22, 22, 26),
                         (x - 1, y - 1, bar_w + 2, bar_h + 2), border_radius=3)
        fill = int(bar_w * max(0.0, min(1.0, ratio)))
        color = (214, 138, 60) if ratio > 0.25 else (196, 64, 52)
        if fill > 0:
            pygame.draw.rect(screen, color, (x, y, fill, bar_h), border_radius=3)
        pygame.draw.rect(screen, (70, 70, 78), (x, y, bar_w, bar_h), 1, border_radius=3)


ROWS = 4
COLS = 8


class InventoryPanel:
    """Full inventory screen: 8 columns x 4 rows, opened with E.

    Click an item to pick it up, click a slot to drop or swap it. Right-click
    splits a stack in half. State lives in the Inventory, so it persists.
    """

    def __init__(self, inventory: Inventory, slot: int = 54, pad: int = 8) -> None:
        self.inv = inventory
        self.slot = slot
        self.pad = pad
        self.held: ItemStack | None = None
        self.held_from = None
        self._press = None
        self.hover = -1
        self.font_title = pygame.font.SysFont("dejavusans", 20, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 13, bold=True)
        self.font_tiny = pygame.font.SysFont("dejavusans", 11)

    def count(self) -> int:
        return min(ROWS * COLS, self.inv.capacity)

    def _layout(self, sw: int, sh: int):
        slot, pad = self.slot, self.pad
        rows = ROWS
        grid_w = COLS * slot + (COLS + 1) * pad
        grid_h = rows * slot + (rows + 1) * pad
        panel_w = grid_w
        panel_h = grid_h + 34 + 30
        x0 = (sw - panel_w) // 2
        y0 = (sh - panel_h) // 2
        rects = []
        for r in range(rows):
            for c in range(COLS):
                i = r * COLS + c
                if i >= self.count():
                    break
                rects.append(pygame.Rect(x0 + pad + c * (slot + pad),
                                         y0 + 34 + pad + r * (slot + pad),
                                         slot, slot))
        return pygame.Rect(x0, y0, panel_w, panel_h), rects

    def slot_at(self, pos) -> int | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _, rects = self._layout(*surface.get_size())
        for i, rect in enumerate(rects):
            if rect.collidepoint(pos):
                return i
        return None

    # -- interaction --------------------------------------------------------
    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEMOTION:
            index = self.slot_at(event.pos)
            self.hover = index if index is not None else -1
        elif event.type == pygame.MOUSEBUTTONDOWN:
            index = self.slot_at(event.pos)
            if index is None:
                return
            self._press = event.pos
            if event.button == 1:
                was_empty = self.held is None
                self._left(index)
                if was_empty and self.held is not None:
                    self.held_from = index      # remember where it came from
            elif event.button == 3:
                self._right(index)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            press, self._press = self._press, None
            if self.held is None or press is None:
                return
            moved = math.hypot(event.pos[0] - press[0], event.pos[1] - press[1])
            if moved < 6.0:
                return                          # a plain click: keep carrying it
            index = self.slot_at(event.pos)
            if index is not None:
                self._left(index)               # dropped on a slot
            else:
                self.held = None                # dragged out of the panel: discarded
                self.held_from = None

    def return_held(self) -> None:
        """Put the carried stack somewhere safe -- never silently discard it."""
        if self.held is None:
            return
        src = self.held_from
        if src is not None and 0 <= src < self.inv.capacity and self.inv.slots[src] is None:
            self.inv.slots[src] = self.held
        else:
            slot = self.inv._first_empty()
            if slot is not None:
                self.inv.slots[slot] = self.held
            elif self.inv.add(self.held.defn.id, self.held.count,
                              self.held.quality) is None:
                return                          # inventory full: keep holding it
        self.held = None
        self.held_from = None

    def _left(self, index: int) -> None:
        self.held, self.inv.slots[index] = _place_left(self.held, self.inv.slots[index])

    def _right(self, index: int) -> None:
        self.held, self.inv.slots[index] = _place_right(self.held, self.inv.slots[index])

    def close(self) -> None:
        """Put anything still held back into the inventory."""
        self.return_held()
        self.hover = -1

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, rects = self._layout(sw, sh)

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))

        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 240), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        title = self.font_title.render("INVENTORY", True, TEXT)
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 7))

        for i, rect in enumerate(rects):
            stack = self.inv.slots[i]
            hovered = (i == self.hover)
            pygame.draw.rect(screen, SLOT, rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect,
                             width=2, border_radius=8)
            if stack is not None:
                ic = items.icon(stack.defn.id, self.slot - 14)
                screen.blit(ic, (rect.centerx - ic.get_width() // 2,
                                 rect.centery - ic.get_height() // 2))
                if stack.defn.stackable and stack.count > 1:
                    c = self.font_small.render(str(stack.count), True, TEXT)
                    screen.blit(c, (rect.right - c.get_width() - 5,
                                    rect.bottom - c.get_height() - 2))
                _draw_quality(screen, rect, stack, self.font_tiny)

        if 0 <= self.hover < len(rects) and self.inv.slots[self.hover] is not None:
            text = stack_label(self.inv.slots[self.hover])
        else:
            text = "click to move   ·   right-click to split   ·   E to close"
        label = self.font_tiny.render(text, True, DIM if self.hover < 0 else TEXT)
        screen.blit(label, (panel.centerx - label.get_width() // 2, panel.bottom - 22))

        if self.held is not None:
            mx, my = pygame.mouse.get_pos()
            ic = items.icon(self.held.defn.id, self.slot - 14)
            screen.blit(ic, (mx - ic.get_width() // 2, my - ic.get_height() // 2))
            if self.held.defn.stackable and self.held.count > 1:
                c = self.font_small.render(str(self.held.count), True, TEXT)
                screen.blit(c, (mx + 8, my + 6))


def _merge_quality(other, held, take) -> None:
    if other.defn.quality and held.quality is not None and take > 0:
        base = other.quality if other.quality is not None else held.quality
        other.quality = _qmerge(base, other.count, held.quality, take)


def _place_left(held, other):
    """Left-click drop: pick up, merge or swap. Returns (held, slot)."""
    if held is None:
        return other, None
    if other is not None and other.defn.id == held.defn.id and other.defn.stackable:
        room = other.defn.max_stack - other.count
        if room > 0:
            take = min(room, held.count)
            _merge_quality(other, held, take)
            other.count += take
            held.count -= take
            if held.count <= 0:
                held = None
        return held, other
    return other, held


def _place_right(held, other):
    """Right-click: split in half, or drop one. Returns (held, slot)."""
    if held is None:
        if other is not None and other.count > 1:
            take = other.count // 2
            other.count -= take
            return ItemStack(other.defn, take, other.quality), other
        return None, other
    if other is None:
        held.count -= 1
        return (held if held.count > 0 else None), ItemStack(held.defn, 1, held.quality)
    if other.defn.id == held.defn.id and other.count < other.defn.max_stack:
        _merge_quality(other, held, 1)
        other.count += 1
        held.count -= 1
        return (held if held.count > 0 else None), other
    return held, other


class ChestPanel:
    """Chest storage (8x8 = 64, double the player's 32) above the player bag."""

    COLS = 8
    CHEST_ROWS = 8
    PLAYER_ROWS = 4

    def __init__(self, player_inv: Inventory, chest_inv: Inventory,
                 slot: int = 40, pad: int = 5) -> None:
        self.player = player_inv
        self.chest = chest_inv
        self.slot = slot
        self.pad = pad
        self.held: ItemStack | None = None
        self.held_from = None
        self._press = None
        self.hover = None
        self.font_title = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)
        self.font_tiny = pygame.font.SysFont("dejavusans", 11)

    def _layout(self, sw: int, sh: int):
        slot, pad, cols = self.slot, self.pad, self.COLS
        board_w = cols * slot + (cols + 1) * pad
        chest_h = self.CHEST_ROWS * slot + (self.CHEST_ROWS + 1) * pad
        player_h = self.PLAYER_ROWS * slot + (self.PLAYER_ROWS + 1) * pad
        title, gap = 22, 12
        panel_h = title + chest_h + gap + title + player_h + 14
        x0 = (sw - board_w) // 2
        y0 = (sh - panel_h) // 2

        chest_rects = []
        for r in range(self.CHEST_ROWS):
            for c in range(cols):
                chest_rects.append(pygame.Rect(x0 + pad + c * (slot + pad),
                                               y0 + title + pad + r * (slot + pad),
                                               slot, slot))
        py = y0 + title + chest_h + gap + title
        player_rects = []
        for r in range(self.PLAYER_ROWS):
            for c in range(cols):
                player_rects.append(pygame.Rect(x0 + pad + c * (slot + pad),
                                                py + pad + r * (slot + pad),
                                                slot, slot))
        return pygame.Rect(x0, y0, board_w, panel_h), chest_rects, player_rects

    def _slot_at(self, pos):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _, chest_rects, player_rects = self._layout(*surface.get_size())
        for i, rect in enumerate(chest_rects):
            if rect.collidepoint(pos):
                return ("chest", i)
        for i, rect in enumerate(player_rects):
            if rect.collidepoint(pos):
                return ("player", i)
        return None

    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.hover = self._slot_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            hit = self._slot_at(event.pos)
            if hit is None:
                return
            which, index = hit
            self._press = event.pos
            inv = self.chest if which == "chest" else self.player
            if event.button == 1:
                was_empty = self.held is None
                self.held, inv.slots[index] = _place_left(self.held, inv.slots[index])
                if was_empty and self.held is not None:
                    self.held_from = hit
            elif event.button == 3:
                self.held, inv.slots[index] = _place_right(self.held, inv.slots[index])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            press, self._press = self._press, None
            if self.held is None or press is None:
                return
            moved = math.hypot(event.pos[0] - press[0], event.pos[1] - press[1])
            if moved < 6.0:
                return
            hit = self._slot_at(event.pos)
            if hit is not None:
                which, index = hit
                inv = self.chest if which == "chest" else self.player
                self.held, inv.slots[index] = _place_left(self.held, inv.slots[index])
            else:
                self.held = None                # dragged out: discarded
                self.held_from = None

    def return_held(self) -> None:
        """Put the carried stack somewhere safe -- never silently discard it."""
        if self.held is None:
            return
        if self.held_from is not None:
            which, index = self.held_from
            inv = self.chest if which == "chest" else self.player
            if 0 <= index < inv.capacity and inv.slots[index] is None:
                inv.slots[index] = self.held
                self.held = None
                self.held_from = None
                return
        for inv in (self.player, self.chest):
            slot = inv._first_empty()
            if slot is not None:
                inv.slots[slot] = self.held
                self.held = None
                self.held_from = None
                return
        if self.player.add(self.held.defn.id, self.held.count,
                           self.held.quality) is not None:
            self.held = None
            self.held_from = None

    def close(self) -> None:
        self.return_held()
        self.hover = None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, chest_rects, player_rects = self._layout(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (22, 20, 18, 242), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        ct = self.font_title.render("CHEST", True, (226, 200, 150))
        screen.blit(ct, (panel.centerx - ct.get_width() // 2, panel.top + 5))
        # player title sits just above the player grid
        pt = self.font_title.render("INVENTORY", True, TEXT)
        player_top = player_rects[0].top - self.pad - 22 if player_rects else panel.centery
        screen.blit(pt, (panel.centerx - pt.get_width() // 2, player_top))

        for which, rects, inv in (("chest", chest_rects, self.chest),
                                  ("player", player_rects, self.player)):
            for i, rect in enumerate(rects):
                stack = inv.slots[i] if i < inv.capacity else None
                hovered = self.hover == (which, i)
                pygame.draw.rect(screen, SLOT, rect, border_radius=6)
                pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect,
                                 width=2, border_radius=6)
                if stack is not None:
                    ic = items.icon(stack.defn.id, self.slot - 12)
                    screen.blit(ic, (rect.centerx - ic.get_width() // 2,
                                     rect.centery - ic.get_height() // 2))
                    if stack.defn.stackable and stack.count > 1:
                        c = self.font_small.render(str(stack.count), True, TEXT)
                        screen.blit(c, (rect.right - c.get_width() - 3,
                                        rect.bottom - c.get_height() - 1))
                    _draw_quality(screen, rect, stack, self.font_tiny)

        if self.hover is not None:
            inv = self.chest if self.hover[0] == "chest" else self.player
            stack = inv.slots[self.hover[1]]
            text = stack_label(stack) if stack is not None else ""
        else:
            text = "click to move   ·   right-click to split   ·   E to close"
        label = self.font_tiny.render(text, True, DIM)
        screen.blit(label, (panel.centerx - label.get_width() // 2, panel.bottom - 18))

        if self.held is not None:
            mx, my = pygame.mouse.get_pos()
            ic = items.icon(self.held.defn.id, self.slot - 12)
            screen.blit(ic, (mx - ic.get_width() // 2, my - ic.get_height() // 2))
            if self.held.defn.stackable and self.held.count > 1:
                c = self.font_small.render(str(self.held.count), True, TEXT)
                screen.blit(c, (mx + 8, my + 6))


class ConfirmMenu:
    """A small modal with a question and Yes / No buttons."""

    def __init__(self) -> None:
        self.text = ""
        self.hover = None
        self.font = pygame.font.SysFont("dejavusans", 19, bold=True)
        self.font_btn = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)

    def open(self, text: str) -> None:
        self.text = text
        self.hover = None

    def _rects(self, sw: int, sh: int):
        w, h = 380, 146
        x0, y0 = (sw - w) // 2, (sh - h) // 2
        panel = pygame.Rect(x0, y0, w, h)
        by = y0 + h - 66
        yes = pygame.Rect(x0 + 42, by, 138, 44)
        no = pygame.Rect(x0 + w - 180, by, 138, 44)
        return panel, yes, no

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _panel, yes, no = self._rects(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = "yes" if yes.collidepoint(event.pos) else (
                "no" if no.collidepoint(event.pos) else None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if yes.collidepoint(event.pos):
                return True
            if no.collidepoint(event.pos):
                return False
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_y):
                return True
            if event.key in (pygame.K_ESCAPE, pygame.K_n):
                return False
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, yes, no = self._rects(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 155))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 244), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        label = self.font.render(self.text, True, TEXT)
        screen.blit(label, (panel.centerx - label.get_width() // 2, panel.top + 34))

        for rect, name, key, col in ((yes, "Yes", "yes", (58, 104, 62)),
                                     (no, "No", "no", (124, 58, 58))):
            hovered = (self.hover == key)
            pygame.draw.rect(screen, tuple(min(255, c + 26) for c in col) if hovered
                             else col, rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect,
                             width=2, border_radius=8)
            t = self.font_btn.render(name, True, TEXT)
            screen.blit(t, (rect.centerx - t.get_width() // 2,
                            rect.centery - t.get_height() // 2))


class PauseMenu:
    """Escape menu: Respawn or Exit game (Esc resumes)."""

    def __init__(self) -> None:
        self.hover = None
        self.font_title = pygame.font.SysFont("dejavusans", 26, bold=True)
        self.font_btn = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)

    def _rects(self, sw: int, sh: int):
        w, h = 320, 196
        x0, y0 = (sw - w) // 2, (sh - h) // 2
        panel = pygame.Rect(x0, y0, w, h)
        respawn = pygame.Rect(x0 + 40, y0 + 70, w - 80, 44)
        exit_r = pygame.Rect(x0 + 40, y0 + 124, w - 80, 44)
        return panel, respawn, exit_r

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _panel, respawn, exit_r = self._rects(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = ("respawn" if respawn.collidepoint(event.pos)
                          else "exit" if exit_r.collidepoint(event.pos) else None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if respawn.collidepoint(event.pos):
                return "respawn"
            if exit_r.collidepoint(event.pos):
                return "exit"
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "close"
            if event.key == pygame.K_r:
                return "respawn"
            if event.key == pygame.K_q:
                return "exit"
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, respawn, exit_r = self._rects(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 246), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)
        title = self.font_title.render("PAUSED", True, TEXT)
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 16))
        for rect, name, key, col in ((respawn, "Respawn", "respawn", (58, 104, 62)),
                                     (exit_r, "Exit game", "exit", (124, 58, 58))):
            hovered = (self.hover == key)
            pygame.draw.rect(screen, tuple(min(255, c + 26) for c in col) if hovered
                             else col, rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect,
                             width=2, border_radius=8)
            t = self.font_btn.render(name, True, TEXT)
            screen.blit(t, (rect.centerx - t.get_width() // 2,
                            rect.centery - t.get_height() // 2))
        hint = self.font_small.render("Esc to resume", True, DIM)
        screen.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 22))
