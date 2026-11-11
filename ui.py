"""HUD -- the bottom inventory bar.

Slots are all visible. The mouse wheel moves the *selection* through the items
(wrapping around); it does not scroll the bar.
"""

from __future__ import annotations

import math

import pygame

import items
import plog
import quality
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
        self.player = None              # set by the frame, for the armor slot
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
        panel_h = grid_h + 34 + 30 + slot + 16     # room for the armor slot
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

    def _armor_rect(self, sw: int, sh: int):
        """The single armor slot, centred below the grid."""
        panel, rects = self._layout(sw, sh)
        if rects:
            ay = rects[-1].bottom + self.pad
        else:
            ay = panel.top + 34 + self.pad
        return pygame.Rect(panel.centerx - self.slot // 2, ay, self.slot, self.slot)

    def _armor_click(self, event) -> bool:
        """Equip hide armor by clicking it into the slot; click again to take
        it off. Returns True if the click was the armor slot."""
        surface = pygame.display.get_surface()
        if surface is None or self.player is None:
            return False
        ar = self._armor_rect(*surface.get_size())
        if not ar.collidepoint(event.pos):
            return False
        if event.button == 1:
            if self.held is not None and self.held.defn.id == "hide_armor":
                self.player.equip_armor("hide_armor")
                self.held = None
                self.held_from = None
                return True
            if self.held is None and getattr(self.player, "armor", None):
                old = self.player.unequip_armor()
                if old:
                    self.held = ItemStack(items.get(old), 1, None)
                    self.held_from = None
                return True
        return False

    # -- interaction --------------------------------------------------------
    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEMOTION:
            index = self.slot_at(event.pos)
            self.hover = index if index is not None else -1
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self._armor_click(event):
                return
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

        # THE ARMOR SLOT, one slot below the grid.
        if self.player is not None:
            ar = self._armor_rect(sw, sh)
            pygame.draw.rect(screen, SLOT, ar, border_radius=8)
            pygame.draw.rect(screen, BORDER, ar, width=2, border_radius=8)
            armor = getattr(self.player, "armor", None)
            if armor:
                ic = items.icon(armor, self.slot - 14)
                screen.blit(ic, (ar.centerx - ic.get_width() // 2,
                                 ar.centery - ic.get_height() // 2))
            lab = self.font_tiny.render("ARMOR", True, DIM)
            screen.blit(lab, (ar.right + 8, ar.centery - lab.get_height() // 2))

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
                 slot: int = 40, pad: int = 5, top_rows: int | None = None,
                 top_label: str = "CHEST", filter_owner=None,
                 filter_items=None) -> None:
        self.player = player_inv
        self.chest = chest_inv
        # THE OTHER CONTAINER IS NOT ALWAYS A CHEST. A hired man's pack holds
        # exactly what the player's does -- 32 slots -- so the same panel
        # opens on it, drawn at his size and under his name.
        self.top_rows = int(top_rows) if top_rows else self.CHEST_ROWS
        self.top_label = top_label
        # A CHEST HE BUILT CARRIES A FILTER: only the item shown on the lid may
        # go in ('Any' means everything). A man's pack and the market have
        # none, so filter_owner stays None for them.
        self.filter_owner = filter_owner
        # WHAT THE LID MAY BE TURNED TO, for a settlement chest: Any, this
        # biome's food, leaf and product, and wood -- never the whole registry.
        self.filter_items = filter_items
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
        chest_h = self.top_rows * slot + (self.top_rows + 1) * pad
        player_h = self.PLAYER_ROWS * slot + (self.PLAYER_ROWS + 1) * pad
        title, gap = 22, 12
        # A CHEST HE BUILT SHOWS ITS LID FILTER ABOVE THE GRID: 'Any' and two
        # arrows. Everything else stacks from the top as before.
        filter_h = 26 if self.filter_owner is not None else 0
        panel_h = title + filter_h + chest_h + gap + title + player_h + 14
        x0 = (sw - board_w) // 2
        y0 = (sh - panel_h) // 2

        chest_rects = []
        for r in range(self.top_rows):
            for c in range(cols):
                chest_rects.append(pygame.Rect(x0 + pad + c * (slot + pad),
                                               y0 + title + filter_h + pad + r * (slot + pad),
                                               slot, slot))
        py = y0 + title + filter_h + chest_h + gap + title
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

    def _filter_list(self):
        if self.filter_items is not None:
            return list(self.filter_items)
        return [None] + list(items.REGISTRY.keys())

    def _filter_index(self) -> int:
        try:
            return self._filter_list().index(getattr(self.filter_owner, "filter", None))
        except ValueError:
            return 0

    def _filter_rects(self, sw: int, sh: int):
        panel, _, _ = self._layout(sw, sh)
        cx = panel.centerx
        cy = panel.top + 22 + 13
        return (pygame.Rect(cx - 60, cy - 9, 22, 22),
                pygame.Rect(cx + 38, cy - 9, 22, 22),
                pygame.Rect(cx - 34, cy - 11, 68, 24))

    def _chest_allows(self, stack) -> bool:
        """Whether a stack may be put INTO the chest under its current filter."""
        if self.filter_owner is None or stack is None:
            return True
        f = getattr(self.filter_owner, "filter", None)
        return f is None or stack.defn.id == f

    def _handle_filter_click(self, event) -> bool:
        """Left/right arrows next to the lid filter. True if consumed."""
        if self.filter_owner is None or event.type != pygame.MOUSEBUTTONDOWN \
                or event.button != 1:
            return False
        surface = pygame.display.get_surface()
        if surface is None:
            return False
        left, right, _ = self._filter_rects(*surface.get_size())
        lst = self._filter_list()
        i = self._filter_index()
        if left.collidepoint(event.pos):
            self.filter_owner.filter = lst[(i - 1) % len(lst)]
            return True
        if right.collidepoint(event.pos):
            self.filter_owner.filter = lst[(i + 1) % len(lst)]
            return True
        return False

    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.hover = self._slot_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self._handle_filter_click(event):
                return
            hit = self._slot_at(event.pos)
            if hit is None:
                return
            which, index = hit
            self._press = event.pos
            inv = self.chest if which == "chest" else self.player
            if event.button == 1:
                if which == "chest" and not self._chest_allows(self.held):
                    return
                was_empty = self.held is None
                self.held, inv.slots[index] = _place_left(self.held, inv.slots[index])
                if was_empty and self.held is not None:
                    self.held_from = hit
            elif event.button == 3:
                if which == "chest" and not self._chest_allows(self.held):
                    return
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
                if which == "chest" and not self._chest_allows(self.held):
                    return
                self.held, inv.slots[index] = _place_left(self.held, inv.slots[index])
            else:
                # DRAGGED OFF THE PANEL: PUT IT BACK, never into the void.
                # A 300-stack picked up and let go over the black lost 218
                # because this line silently threw it away.
                self.return_held()

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

        ct = self.font_title.render(self.top_label.upper(), True, (226, 200, 150))
        screen.blit(ct, (panel.centerx - ct.get_width() // 2, panel.top + 5))
        # THE LID FILTER: what this chest will accept, with two arrows to turn
        # it. 'Any' means everything may go in.
        if self.filter_owner is not None:
            left, right, mid = self._filter_rects(sw, sh)
            f = getattr(self.filter_owner, "filter", None)
            label = "ANY" if f is None else f.upper()
            txt = self.font_small.render(label, True, (238, 224, 190))
            screen.blit(txt, (mid.centerx - txt.get_width() // 2,
                              mid.centery - txt.get_height() // 2))
            for rr in (left, right):
                pygame.draw.rect(screen, (70, 60, 44), rr, border_radius=4)
                pygame.draw.rect(screen, BORDER, rr, width=1, border_radius=4)
            for rr, sym in ((left, "<"), (right, ">")):
                s = self.font_small.render(sym, True, (226, 200, 150))
                screen.blit(s, (rr.centerx - s.get_width() // 2,
                                rr.centery - s.get_height() // 2))
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
            try:
                inv = self.chest if self.hover[0] == "chest" else self.player
                _hi = self.hover[1]
                stack = inv.slots[_hi] if 0 <= _hi < len(inv.slots) else None
            except Exception:
                stack = None
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


class SignPanel:
    """The sign-post: how many conquered people farm, log, or go unemployed.
    A click on [-] / [+] moves one person between the jobs."""

    def __init__(self, sign, camp, sync, show_smiths=None) -> None:
        self.sign = sign
        self.camp = camp
        self.sync = sync
        self.show_smiths = show_smiths   # callable -> bool, for the gated job
        self.hover = None
        self.font = pygame.font.SysFont("dejavusans", 20, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 15, bold=True)

    def _total(self) -> int:
        return len(getattr(self.camp, "people", ()) or ())

    def _jobs(self):
        jobs = [("Farmers", "farmers"), ("Loggers", "loggers"),
                ("Artisans", "artisans"), ("Researchers", "researchers"),
                ("Miners", "miners")]
        if self.show_smiths is not None and self.show_smiths():
            jobs.append(("Smiths", "smiths"))
        return jobs

    def _rects(self, sw: int, sh: int):
        jobs = self._jobs()
        w = 380
        h = 66 + len(jobs) * 52 + 46
        x0, y0 = (sw - w) // 2, (sh - h) // 2
        panel = pygame.Rect(x0, y0, w, h)
        rows = []
        for i, (label, key) in enumerate(jobs):
            ry = y0 + 66 + i * 52
            minus = pygame.Rect(x0 + w - 150, ry, 40, 34)
            plus = pygame.Rect(x0 + w - 52, ry, 40, 34)
            rows.append((label, key, minus, plus, ry))
        return panel, rows

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        _panel, rows = self._rects(*surface.get_size())
        total = self._total()
        if event.type == pygame.MOUSEMOTION:
            self.hover = None
            for _label, key, minus, plus, _ry in rows:
                if minus.collidepoint(event.pos):
                    self.hover = (key, -1)
                elif plus.collidepoint(event.pos):
                    self.hover = (key, +1)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for _label, key, minus, plus, _ry in rows:
                if minus.collidepoint(event.pos):
                    setattr(self.sign, key, max(0, int(getattr(self.sign, key, 0)) - 1))
                    self.sync()
                    return "changed"
                if plus.collidepoint(event.pos):
                    _used = sum(int(getattr(self.sign, k, 0))
                                for _l, k in self._jobs())
                    if _used < total:
                        setattr(self.sign, key, int(getattr(self.sign, key, 0)) + 1)
                        self.sync()
                    return "changed"
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "close"
        return None

    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, rows = self._rects(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 155))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 244), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        title = self.font.render("JOBS", True, TEXT)
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 18))
        total = self._total()
        for label, key, minus, plus, ry in rows:
            val = int(getattr(self.sign, key, 0))
            t = self.font_small.render("%s" % label, True, (206, 184, 122))
            screen.blit(t, (panel.left + 26, ry + 8))
            for rect, sym, hkey in ((minus, "-", (key, -1)), (plus, "+", (key, +1))):
                hovered = (self.hover == hkey)
                pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52),
                                 rect, border_radius=6)
                pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect,
                                 width=2, border_radius=6)
                tt = self.font.render(sym, True, TEXT)
                screen.blit(tt, (rect.centerx - tt.get_width() // 2,
                                 rect.centery - tt.get_height() // 2))
            n = self.font.render(str(val), True, TEXT)
            screen.blit(n, (minus.left - 40 - n.get_width(), ry + 8))
        used = sum(int(getattr(self.sign, k, 0)) for _l, k in self._jobs())
        unemp = max(0, total - used)
        u = self.font_small.render("Unemployed:  %d" % unemp, True, (176, 168, 152))
        screen.blit(u, (panel.left + 26, panel.bottom - 40))


class HorsePanel:
    """A conquered horse: its saddle bags open like a chest, with a Send to
    ship button underneath."""

    def __init__(self, player_inv, horse) -> None:
        self.chest = ChestPanel(player_inv, horse._pack(),
                                top_label=getattr(horse, "name", "HORSE") or "HORSE")
        self.horse = horse
        self.hover = None
        self.font = pygame.font.SysFont("dejavusans", 16, bold=True)

    def _buttons(self, sw: int, sh: int):
        w, h = 200, 42
        y = sh - 54
        send = pygame.Rect((sw - 2 * w - 12) // 2, y, w, h)
        route = pygame.Rect(send.right + 12, y, w, h)
        return send, route

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        send, route = self._buttons(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            if send.collidepoint(event.pos):
                self.hover = "send"
            elif route.collidepoint(event.pos):
                self.hover = "route"
            else:
                self.hover = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if send.collidepoint(event.pos):
                return "send"
            if route.collidepoint(event.pos):
                return "route"
        return self.chest.handle_event(event)

    def draw(self, screen: pygame.Surface) -> None:
        self.chest.draw(screen)
        sw, sh = screen.get_size()
        send, route = self._buttons(sw, sh)
        for rect, label, key in ((send, "Send to ship", "send"),
                                 (route, "Plan route", "route")):
            hovered = self.hover == key
            pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52),
                             rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect, width=2,
                             border_radius=8)
            t = self.font.render(label, True, TEXT)
            screen.blit(t, (rect.centerx - t.get_width() // 2,
                            rect.centery - t.get_height() // 2))


class RoutePanel:
    """Plan a horse's roundtrip: origin (pre-filled), a destination from the
    conquered settlements plus the ship, what to load at each end, and a
    per-leg amount. Start route sends the horse off, forever."""

    def __init__(self, horse, origin, destinations, origin_items, dest_items_fn) -> None:
        self.horse = horse
        self.origin = origin
        self.dests = destinations          # list of camps, or the string "ship"
        self.dest_index = 0
        self.origin_items = list(origin_items)
        self.dest_items_fn = dest_items_fn
        self.origin_item_index = 0
        self.dest_item_index = 0
        self.amount = 300
        self.hover = None
        self.font = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 15, bold=True)
        self.font_btn = pygame.font.SysFont("dejavusans", 16, bold=True)

    def _name(self, item_id):
        if item_id is None:
            return "Any"
        d = items.get(item_id)
        return d.name if d is not None else str(item_id)

    def _dest_label(self, i):
        d = self.dests[i]
        if d == "ship":
            return "The ship"
        return getattr(d, "name", "settlement") or "settlement"

    def _dest_items(self):
        if self.dest_index < len(self.dests):
            return list(self.dest_items_fn(self.dests[self.dest_index]))
        return []

    def _rects(self, sw, sh):
        w, h = 540, 400
        x0, y0 = (sw - w) // 2, (sh - h) // 2
        panel = pygame.Rect(x0, y0, w, h)
        cx = x0 + w // 2
        rows = []
        # each row: (label, left_arrow, right_arrow, plus, minus)
        y = y0 + 52
        for i in range(5):
            left = pygame.Rect(cx + 120, y, 30, 28)
            right = pygame.Rect(cx + 196, y, 30, 28)
            plus = pygame.Rect(cx + 158, y, 30, 28)
            minus = pygame.Rect(cx + 84, y, 30, 28)
            rows.append((left, right, plus, minus))
            y += 46
        start = pygame.Rect(cx - 90, y0 + h - 62, 180, 42)
        return panel, rows, start

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        panel, rows, start = self._rects(*surface.get_size())
        if event.type == pygame.MOUSEMOTION:
            self.hover = None
            for i, (l, r, plus, minus) in enumerate(rows):
                if l.collidepoint(event.pos):
                    self.hover = (i, -1)
                elif r.collidepoint(event.pos):
                    self.hover = (i, +1)
                elif plus.collidepoint(event.pos):
                    self.hover = (i, 2)
                elif minus.collidepoint(event.pos):
                    self.hover = (i, -2)
            if start.collidepoint(event.pos):
                self.hover = ("start",)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, (l, r, plus, minus) in enumerate(rows):
                if l.collidepoint(event.pos):
                    self._step(i, -1)
                    return "changed"
                if r.collidepoint(event.pos):
                    self._step(i, +1)
                    return "changed"
                if plus.collidepoint(event.pos):
                    self.amount = min(9999, self.amount + 50)
                    return "changed"
                if minus.collidepoint(event.pos):
                    self.amount = max(0, self.amount - 50)
                    return "changed"
            if start.collidepoint(event.pos):
                return "start"
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "close"
        return None

    def _step(self, row, direction):
        if row == 1:                       # origin load item
            n = len(self.origin_items)
            self.origin_item_index = (self.origin_item_index + direction) % max(1, n)
        elif row == 2:                     # destination
            n = len(self.dests)
            self.dest_index = (self.dest_index + direction) % max(1, n)
            self.dest_item_index = 0
        elif row == 3:                     # destination load item
            n = len(self._dest_items())
            self.dest_item_index = (self.dest_item_index + direction) % max(1, n)

    def _current(self):
        dest = self.dests[self.dest_index] if self.dests else "ship"
        ship = dest == "ship"
        item_a = self.origin_items[self.origin_item_index] if self.origin_items else None
        items_b = self._dest_items()
        item_b = (items_b[self.dest_item_index] if items_b else None) if not ship else None
        return dest, ship, item_a, item_b

    def draw(self, screen):
        sw, sh = screen.get_size()
        panel, rows, start = self._rects(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (22, 20, 18, 244), panel, border_radius=12)
        pygame.draw.rect(screen, BORDER, panel, 2, border_radius=12)
        t = self.font.render("PLAN ROUTE", True, TEXT)
        screen.blit(t, (panel.centerx - t.get_width() // 2, panel.top + 14))
        dest, ship, item_a, item_b = self._current()
        labels = [
            "From: %s" % (getattr(self.origin, "name", "?") or "?"),
            "Loads: %s" % self._name(item_a),
            "To: %s" % self._dest_label(self.dest_index),
            "Loads: %s" % (self._name(item_b) if not ship else "- (delivers to the ship)"),
            "Amount: %d" % self.amount,
        ]
        for i, (l, r, plus, minus) in enumerate(rows):
            text = self.font_small.render(labels[i], True, (226, 200, 150))
            screen.blit(text, (panel.left + 26, l.centery - text.get_height() // 2))
            for rr, sym in ((l, "<"), (r, ">")):
                hovered = self.hover == (i, -1 if rr is l else +1)
                pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52),
                                 rr, border_radius=6)
                pygame.draw.rect(screen, ACCENT if hovered else BORDER, rr, width=2,
                                 border_radius=6)
                s = self.font_small.render(sym, True, TEXT)
                screen.blit(s, (rr.centerx - s.get_width() // 2, rr.centery - s.get_height() // 2))
            if i == 4:
                for rr, sym in ((minus, "-"), (plus, "+")):
                    hovered = self.hover == (i, -2 if rr is minus else 2)
                    pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52),
                                     rr, border_radius=6)
                    pygame.draw.rect(screen, ACCENT if hovered else BORDER, rr, width=2,
                                     border_radius=6)
                    s = self.font_small.render(sym, True, TEXT)
                    screen.blit(s, (rr.centerx - s.get_width() // 2, rr.centery - s.get_height() // 2))
        hovered = self.hover == ("start",)
        pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52), start, border_radius=8)
        pygame.draw.rect(screen, ACCENT if hovered else BORDER, start, width=2, border_radius=8)
        s = self.font_btn.render("Start route", True, TEXT)
        screen.blit(s, (start.centerx - s.get_width() // 2, start.centery - s.get_height() // 2))


class ShipMarketPanel:
    """THE FREE MARKET: sell manufactured goods out of the ship's hold.

    Left: the player's pack (top) and the ship's hold (bottom), dragged
    between like a chest. Right: the sellable goods with their mid-grade
    prices; click one to open its price history and sell it."""

    COLS = 8
    PLAYER_ROWS = 4
    HOLD_ROWS = 4

    def __init__(self, g, player_inv, hold_inv) -> None:
        self.g = g
        self.player = player_inv
        self.hold = hold_inv
        self.held = None
        self.held_from = None
        self.selected = 0
        self.hover = None
        self.font = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 14, bold=True)
        self.font_tiny = pygame.font.SysFont("dejavusans", 11)

    def _goods(self):
        import market
        return list(market.SELLABLE)

    def _layout(self, sw, sh):
        slot, pad, cols = 36, 4, self.COLS
        grid_w = cols * slot + (cols + 1) * pad
        lx, ly = 16, 40
        player_rects = []
        y = ly + 28
        for r in range(self.PLAYER_ROWS):
            for c in range(cols):
                player_rects.append(pygame.Rect(lx + pad + c * (slot + pad),
                                                y + pad + r * (slot + pad), slot, slot))
        player_h = self.PLAYER_ROWS * slot + (self.PLAYER_ROWS + 1) * pad
        hold_y = y + player_h + 30
        hold_rects = []
        for r in range(self.HOLD_ROWS):
            for c in range(cols):
                hold_rects.append(pygame.Rect(lx + pad + c * (slot + pad),
                                              hold_y + pad + r * (slot + pad), slot, slot))
        hold_h = self.HOLD_ROWS * slot + (self.HOLD_ROWS + 1) * pad
        rx = lx + grid_w + 20
        rw = max(200, sw - rx - 16)
        goods_rects = []
        gy = ly + 28
        for i in range(len(self._goods())):
            goods_rects.append(pygame.Rect(rx, gy + i * 52, rw, 46))
        hist = pygame.Rect(rx, gy + len(self._goods()) * 52 + 8, rw, 140)
        sell = pygame.Rect(rx + rw // 2 - 90, hist.bottom + 10, 180, 40)
        return (lx, ly, player_rects, hold_rects, y, hold_y, rx, rw,
                goods_rects, hist, sell)

    def _slot_at(self, pos):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        (_lx, _ly, pr, hr, _y, _hy, _rx, _rw, gr, _hist, _sell) = self._layout(*surface.get_size())
        for i, r in enumerate(pr):
            if r.collidepoint(pos):
                return ("player", i)
        for i, r in enumerate(hr):
            if r.collidepoint(pos):
                return ("hold", i)
        return None

    def _good_at(self, pos):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        (_lx, _ly, pr, hr, _y, _hy, _rx, _rw, gr, _hist, _sell) = self._layout(*surface.get_size())
        for i, r in enumerate(gr):
            if r.collidepoint(pos):
                return i
        return None

    def _sell_rect(self):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        return self._layout(*surface.get_size())[10]

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = event.pos
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            gi = self._good_at(event.pos)
            if gi is not None:
                self.selected = gi
                return None
            sell = self._sell_rect()
            if sell is not None and sell.collidepoint(event.pos):
                self._sell_selected()
                return None
            hit = self._slot_at(event.pos)
            if hit is None:
                return None
            which, index = hit
            inv = self.player if which == "player" else self.hold
            was_empty = self.held is None
            self.held, inv.slots[index] = _place_left(self.held, inv.slots[index])
            if was_empty and self.held is not None:
                self.held_from = hit
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            hit = self._slot_at(event.pos)
            if hit is None:
                return None
            which, index = hit
            inv = self.player if which == "player" else self.hold
            self.held, inv.slots[index] = _place_right(self.held, inv.slots[index])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.held is None:
                return None
            hit = self._slot_at(event.pos)
            if hit is not None:
                which, index = hit
                inv = self.player if which == "player" else self.hold
                self.held, inv.slots[index] = _place_left(self.held, inv.slots[index])
            else:
                self._return_held()
        return None

    def _return_held(self):
        if self.held is None:
            return
        if self.held_from is not None:
            which, index = self.held_from
            inv = self.player if which == "player" else self.hold
            if 0 <= index < inv.capacity and inv.slots[index] is None:
                inv.slots[index] = self.held
                self.held = None
                self.held_from = None
                return
        for inv in (self.player, self.hold):
            slot = inv._first_empty()
            if slot is not None:
                inv.slots[slot] = self.held
                self.held = None
                self.held_from = None
                return

    def _hold_count(self, good):
        return self.hold.count_of(good)

    def _sell_selected(self):
        import market
        good = self._goods()[self.selected]
        base = self.g.market["base"].get(good, market.spec(good)[0])
        coin = 0.0
        for i, stack in enumerate(list(self.hold.slots)):
            if stack is None or stack.defn.id != good:
                continue
            grade = stack.quality if stack.defn.quality is not None else market.MID_GRADE
            coin += market.sell_value(self.g, good, stack.count, grade)
            self.hold.slots[i] = None
        if coin > 0.0:
            self.player.add("coin", int(round(coin)))
            try:
                self.g.toast("Sold %s for %d coin" % (good, int(round(coin))))
            except Exception:
                pass

    def close(self):
        self._return_held()

    def draw(self, screen):
        sw, sh = screen.get_size()
        import market
        (lx, ly, pr, hr, py, hy, rx, rw, gr, hist_rect, sell) = self._layout(sw, sh)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        board = pygame.Surface((sw - 24, sh - 40), pygame.SRCALPHA)
        pygame.draw.rect(board, (22, 20, 18, 244), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, (12, 20))
        # titles
        for label, yy in (("YOUR PACK", py - 24), ("SHIP HOLD", hy - 24)):
            t = self.font_small.render(label, True, (226, 200, 150))
            screen.blit(t, (lx + 4, yy))
        # left inventories
        for which, rects, inv in (("player", pr, self.player), ("hold", hr, self.hold)):
            for i, rect in enumerate(rects):
                stack = inv.slots[i] if i < inv.capacity else None
                hovered = self.hover is not None and rect.collidepoint(self.hover)
                pygame.draw.rect(screen, SLOT, rect, border_radius=5)
                pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect, width=2, border_radius=5)
                if stack is not None:
                    ic = items.icon(stack.defn.id, rect.width - 10)
                    screen.blit(ic, (rect.centerx - ic.get_width() // 2,
                                     rect.centery - ic.get_height() // 2))
                    if stack.defn.stackable and stack.count > 1:
                        c = self.font_tiny.render(str(stack.count), True, TEXT)
                        screen.blit(c, (rect.right - c.get_width() - 2, rect.bottom - c.get_height() - 1))
                    _draw_quality(screen, rect, stack, self.font_tiny)
        # right goods list
        t = self.font.render("THE MARKET", True, (238, 224, 190))
        screen.blit(t, (rx + 4, ly))
        for i, good in enumerate(self._goods()):
            rect = gr[i]
            base = self.g.market["base"].get(good, market.spec(good)[0])
            hist = self.g.market["history"].get(good, [base])
            trend = ""
            if len(hist) >= 2:
                trend = " \u25b2" if hist[-1] > hist[-2] else (" \u25bc" if hist[-1] < hist[-2] else "")
            hovered = self.hover is not None and rect.collidepoint(self.hover)
            sel = (i == self.selected)
            pygame.draw.rect(screen, (54, 46, 38) if (sel or hovered) else (34, 34, 40),
                             rect, border_radius=7)
            pygame.draw.rect(screen, ACCENT if sel else BORDER, rect, width=2, border_radius=7)
            ic = items.icon(good, 30)
            screen.blit(ic, (rect.left + 8, rect.centery - 15))
            nm = self.font_small.render(items.get(good).name if items.get(good) else good,
                                        True, (226, 214, 190))
            screen.blit(nm, (rect.left + 48, rect.top + 6))
            price = self.font_small.render("B: %.1f c%s" % (base, trend), True, (232, 200, 118))
            screen.blit(price, (rect.right - price.get_width() - 10, rect.top + 6))
            have = self._hold_count(good)
            hv = self.font_tiny.render("in hold: %d" % have, True, (150, 146, 134))
            screen.blit(hv, (rect.left + 48, rect.bottom - 18))
        # price history for the selected good
        good = self._goods()[self.selected]
        base = self.g.market["base"].get(good, market.spec(good)[0])
        hist = self.g.market["history"].get(good, [base])
        pygame.draw.rect(screen, (30, 28, 32), hist_rect, border_radius=7)
        pygame.draw.rect(screen, BORDER, hist_rect, 2, border_radius=7)
        hd = self.font_small.render("%s price history (mid-grade)" % good, True, (206, 184, 122))
        screen.blit(hd, (hist_rect.left + 8, hist_rect.top + 4))
        # sparkline
        if len(hist) >= 2:
            lo, hi = min(hist), max(hist)
            span = (hi - lo) or 1.0
            pts = []
            for k, p in enumerate(hist):
                x = hist_rect.left + 6 + k * (hist_rect.width - 12) / (len(hist) - 1)
                y = hist_rect.bottom - 10 - (p - lo) / span * (hist_rect.height - 34)
                pts.append((int(x), int(y)))
            if len(pts) > 1:
                pygame.draw.lines(screen, (120, 200, 150), False, pts, 2)
            cur = self.font_small.render("now %.1f c" % base, True, (232, 200, 118))
            screen.blit(cur, (hist_rect.left + 8, hist_rect.bottom - 24))
        # sell button
        n = self._hold_count(good)
        hovered = self.hover is not None and sell.collidepoint(self.hover)
        pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52), sell, border_radius=8)
        pygame.draw.rect(screen, ACCENT if hovered else BORDER, sell, width=2, border_radius=8)
        s = self.font_small.render("Sell all (%d)" % n, True, TEXT)
        screen.blit(s, (sell.centerx - s.get_width() // 2, sell.centery - s.get_height() // 2))
        # held stack follows the mouse
        if self.held is not None:
            mx, my = pygame.mouse.get_pos()
            ic = items.icon(self.held.defn.id, 30)
            screen.blit(ic, (mx - 15, my - 15))


class ResearchPanel:
    """THE RESEARCH TREE: a full-screen card grid, bought with coin.
    Click a card to select it (dark blue); a Research button appears at the
    bottom and starts it if the coin is there."""

    def __init__(self, g) -> None:
        self.g = g
        self.selected = None
        self.hover = None
        self.font = pygame.font.SysFont("dejavusans", 24, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 15, bold=True)
        self.font_tiny = pygame.font.SysFont("dejavusans", 12)
        self.font_btn = pygame.font.SysFont("dejavusans", 17, bold=True)

    def _cards(self):
        import research
        return research.CARDS

    def _card_rects(self, sw, sh):
        cards = self._cards()
        n = len(cards)
        cols = max(1, min(4, n))
        rows = (n + cols - 1) // cols
        cw, ch, gap = 200, 150, 16
        grid_w = cols * cw + (cols - 1) * gap
        grid_h = rows * ch + (rows - 1) * gap
        x0 = (sw - grid_w) // 2
        y0 = (sh - grid_h) // 2 + 10
        rects = []
        for i in range(n):
            r, c = divmod(i, cols)
            rects.append(pygame.Rect(x0 + c * (cw + gap), y0 + r * (ch + gap), cw, ch))
        return rects

    def _button(self, sw, sh):
        return pygame.Rect(sw // 2 - 100, sh - 92, 200, 50)

    def _wrap(self, text, font, maxw):
        lines = []
        cur = ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if not cur or font.size(t)[0] <= maxw:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def handle_event(self, event):
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        sw, sh = surface.get_size()
        rects = self._card_rects(sw, sh)
        btn = self._button(sw, sh)
        if event.type == pygame.MOUSEMOTION:
            self.hover = event.pos
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(rects):
                if r.collidepoint(event.pos):
                    self.selected = i
                    return None
            if btn.collidepoint(event.pos):
                self._research()
                return None
        return None

    def _research(self):
        if self.selected is None:
            return
        import research
        card = self._cards()[self.selected]
        st = research.state(self.g, card["id"])
        if st == "locked":
            if research.start(self.g, card):
                try:
                    self.g.toast("Researching %s..." % card["name"])
                except Exception:
                    pass
            else:
                try:
                    self.g.toast("Need %d coin" % card["cost"])
                except Exception:
                    pass

    def draw(self, screen):
        sw, sh = screen.get_size()
        import research
        # FULLY OPAQUE BACKGROUND: the research screen is a room, not an overlay.
        screen.fill((16, 16, 20))
        t = self.font.render("RESEARCH", True, (238, 224, 190))
        screen.blit(t, (sw // 2 - t.get_width() // 2, 28))
        rects = self._card_rects(sw, sh)
        for i, card in enumerate(self._cards()):
            r = rects[i]
            st = research.state(self.g, card["id"])
            sel = (i == self.selected)
            if sel:
                bg = (30, 52, 96)                    # dark blue selection
            elif st == "done":
                bg = (24, 62, 42)
            elif st == "shadow":
                bg = (26, 26, 30)                    # greyed until unlocked
            else:
                bg = (34, 34, 40)
            pygame.draw.rect(screen, bg, r, border_radius=10)
            pygame.draw.rect(screen, ACCENT if sel else BORDER, r, width=2, border_radius=10)
            ic = items.icon(card["icon"], 44)
            screen.blit(ic, (r.left + 12, r.top + 12))
            nm = self.font_small.render(card["name"], True, (226, 214, 190))
            screen.blit(nm, (r.left + 64, r.top + 12))
            cost = self.font_tiny.render("%d c" % card["cost"], True, (232, 200, 118))
            screen.blit(cost, (r.left + 64, r.top + 34))
            if st == "done":
                st_txt = self.font_tiny.render("Researched", True, (150, 224, 150))
                screen.blit(st_txt, (r.right - st_txt.get_width() - 10, r.top + 12))
            elif st == "shadow":
                req = card.get("requires")
                req_name = next((c["name"] for c in self._cards() if c["id"] == req), "?")
                st_txt = self.font_tiny.render("Requires %s" % req_name, True, (120, 120, 128))
                screen.blit(st_txt, (r.right - st_txt.get_width() - 10, r.top + 12))
            elif st == "researching":
                pts = int(getattr(self.g, "research_points", 0.0)) \
                    if getattr(self.g, "research_active", None) == card["id"] else 0
                st_txt = self.font_tiny.render("Researching... %d/%d" % (pts, card.get("points", 0)),
                                               True, (232, 200, 118))
                screen.blit(st_txt, (r.right - st_txt.get_width() - 10, r.top + 12))
            # description wrapped into the lower half of the card
            lines = self._wrap(card["desc"], self.font_tiny, r.width - 24)
            ly = r.bottom - len(lines) * 16 - 10
            for ln in lines:
                dt = self.font_tiny.render(ln, True, (196, 188, 172))
                screen.blit(dt, (r.left + 12, ly))
                ly += 16
        if self.selected is not None:
            card = self._cards()[self.selected]
            st = research.state(self.g, card["id"])
            if st == "locked":
                btn = self._button(sw, sh)
                hovered = self.hover is not None and btn.collidepoint(self.hover)
                pygame.draw.rect(screen, (58, 104, 62) if hovered else (44, 46, 52),
                                 btn, border_radius=8)
                pygame.draw.rect(screen, ACCENT if hovered else BORDER, btn, width=2,
                                 border_radius=8)
                s = self.font_btn.render("Research", True, TEXT)
                screen.blit(s, (btn.centerx - s.get_width() // 2,
                                btn.centery - s.get_height() // 2))


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


class MarketPanel(ChestPanel):
    """THE MARKET STALL, OPENED LIKE A CHEST.

    Whatever is in it is on the market. Clicking moves a stack either way --
    your pack below, the counter above -- and that is the whole screen. There
    are no prices here, because prices are not a property of a shelf: they are
    what you and the man who makes the goods agreed on, and they are set in his
    dialogue (see dialogue.py, "What do you want for it?").

    One key remains: T, the stall's own switch. Shut, the goods stay on the
    counter and nobody buys, which is what a closed shop is.
    """

    def __init__(self, player_inv: Inventory, stall, slot: int = 40,
                 pad: int = 5) -> None:
        super().__init__(player_inv, stall.stock, slot=slot, pad=pad,
                         top_rows=4, top_label="MARKET")
        self.stall = stall
        self.font_note = pygame.font.SysFont("dejavusans", 12)

    def handle_event(self, event) -> None:
        # THERE IS NO pygame.K_T. A capital letter arrives as K_t with SHIFT
        # held, so asking for K_T raised AttributeError the first time a player
        # pressed T -- in the market screen, in the middle of a game.
        if event.type == pygame.KEYDOWN and event.key == pygame.K_t:
            self.stall.on = not bool(self.stall.on)
            try:
                plog.log("STALL", "trading" if self.stall.on else "SHUT")
            except Exception:
                pass
            return
        super().handle_event(event)

    def draw(self, screen: pygame.Surface) -> None:
        super().draw(screen)
        try:
            sw, sh = screen.get_size()
            panel, _top, _bot = self._layout(sw, sh)
            state = ("TRADING" if self.stall.on
                     else "SHUT -- nobody will buy")
            col = (176, 200, 176) if self.stall.on else (220, 130, 110)
            head = pygame.font.SysFont("dejavusans", 15, bold=True).render(
                state, True, col)
            screen.blit(head, (panel.centerx - head.get_width() // 2,
                               panel.top + 4))
            note = self.font_note.render(
                "everything on the counter is for sale   ·   "
                "prices are agreed with the man who makes it   ·   "
                "T to open or shut   ·   E to close",
                True, (150, 146, 134))
            screen.blit(note, (panel.centerx - note.get_width() // 2,
                               panel.bottom - 34))
        except Exception:
            pass


class FolderPanel:
    """A DEAD AGENT'S MAIL: TO, FROM, and what the news is.

    A scrollable page of messages, three to a page, with the page count in the
    corner and the folder's owner in the header -- because two folders in one
    rucksack are two different dead men.
    """

    PER_PAGE = 3

    def __init__(self, folder_id: str) -> None:
        self.fid = folder_id
        self.page = 0
        self.font_title = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 15)
        self.font_small = pygame.font.SysFont("dejavusans", 13)
        self.font_tiny = pygame.font.SysFont("dejavusans", 11)

    # -- data --------------------------------------------------------------
    def _folder(self):
        try:
            import folders
            return folders.read(self.fid)
        except Exception:
            return None

    def _pages(self) -> int:
        got = self._folder()
        n = len(got.get("msgs", ())) if got else 0
        return max(1, (n + self.PER_PAGE - 1) // self.PER_PAGE)

    def _wrap(self, text, font, width) -> list:
        lines, cur = [], ""
        for word in str(text).split():
            trial = (cur + " " + word).strip()
            if font.size(trial)[0] > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines

    # -- input -------------------------------------------------------------
    def handle_event(self, event) -> bool:
        """True when the panel wants to close."""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_q):
                return True
            if event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_PAGEDOWN):
                self.page = min(self._pages() - 1, self.page + 1)
            elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_PAGEUP):
                self.page = max(0, self.page - 1)
        elif event.type == pygame.MOUSEWHEEL:
            if event.y < 0:
                self.page = min(self._pages() - 1, self.page + 1)
            elif event.y > 0:
                self.page = max(0, self.page - 1)
        return False

    # -- drawing -----------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        vw, vh = screen.get_size()
        w = min(760, vw - 80)
        h = min(560, vh - 80)
        panel = pygame.Rect(vw // 2 - w // 2, vh // 2 - h // 2, w, h)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 165))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (22, 20, 18), panel, border_radius=10)
        pygame.draw.rect(screen, (154, 118, 78), panel, 2, border_radius=10)

        got = self._folder()
        to = (got or {}).get("to", "an agent")
        msgs = list((got or {}).get("msgs", ()))
        pages = self._pages()
        self.page = max(0, min(pages - 1, self.page))

        head = self.font_title.render("SECRET FOLDER", True, (226, 200, 150))
        screen.blit(head, (panel.x + 20, panel.y + 12))
        top = self.font.render("TO: %s" % to, True, (228, 218, 198))
        screen.blit(top, (panel.x + 20, panel.y + 38))
        count = self.font_small.render(
            "page %d / %d   --   %d message%s" % (self.page + 1, pages, len(msgs),
                                                  "" if len(msgs) == 1 else "s"),
            True, (170, 164, 150))
        screen.blit(count, (panel.right - 20 - count.get_width(), panel.y + 42))

        y = panel.y + 72
        chunk = msgs[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]
        if not chunk:
            empty = self.font.render("Nothing. Whatever he knew is stale.",
                                     True, (176, 168, 152))
            screen.blit(empty, (panel.x + 20, y))
        for m in chunk:
            rule = pygame.Rect(panel.x + 16, y, w - 32, 1)
            pygame.draw.rect(screen, (70, 64, 54), rule)
            y += 8
            _from = "FROM: %s" % m.get("from", "?")
            if m.get("where"):
                _from += "  ·  at %s" % m.get("where")
            frm = self.font.render(_from, True, (206, 196, 172))
            screen.blit(frm, (panel.x + 20, y))
            _age = float(m.get("age", 0.0))
            _days = max(1, int(round(_age)))
            _when = ("today" if _age < 0.5 else
                     "%d day%s ago" % (_days, "" if _days == 1 else "s"))
            age = self.font_tiny.render(_when, True, (150, 144, 130))
            screen.blit(age, (panel.right - 20 - age.get_width(), y + 2))
            y += 22
            for line in self._wrap(m.get("text", ""), self.font, w - 60)[:6]:
                t = self.font.render(line, True, (232, 226, 210))
                screen.blit(t, (panel.x + 30, y))
                y += 20
            y += 10
            if y > panel.bottom - 60:
                break

        hint = self.font_tiny.render(
            "wheel or A / D to turn the page   ·   E or ESC to close",
            True, (140, 134, 122))
        screen.blit(hint, (panel.x + 20, panel.bottom - 26))
