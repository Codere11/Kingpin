"""Main menu and save-slot menu.

Rendered at low resolution and upscaled with nearest-neighbour, matching the
Game Over screen's chunky look. All text is clipped to its own button so it can
never spill outside its boundary.
"""

from __future__ import annotations

import random

import pygame

import persist

BG = (14, 12, 16)
TITLE = (226, 188, 98)
TITLE_DARK = (58, 38, 8)
BTN_BG = (34, 30, 26)
BTN_BG_HOVER = (74, 58, 34)
BTN_BORDER = (110, 90, 54)
BTN_BORDER_HOVER = (236, 196, 110)
BTN_TEXT = (238, 230, 214)
DIM = (168, 156, 138)
HINT = (122, 110, 98)
SLOT = (28, 32, 28)
SLOT_HOVER = (54, 70, 48)
DEL_BG = (66, 26, 24)
DEL_HOVER = (128, 44, 40)
DEL_BORDER = (128, 52, 46)
TEST_BG = (26, 34, 40)
TEST_HOVER = (44, 72, 84)
TEST_BORDER = (66, 118, 138)
TEST_BORDER_HOVER = (140, 222, 240)


def _fit(font, text, max_w, color):
    """Render ``text`` shrinking/truncating so it never exceeds ``max_w``."""
    if max_w <= 4:
        return font.render("", False, color)
    if font.size(text)[0] <= max_w:
        return font.render(text, False, color)
    trimmed = text
    while trimmed and font.size(trimmed + "...")[0] > max_w:
        trimmed = trimmed[:-1]
    return font.render(trimmed + "...", False, color)


class Menu:
    def __init__(self) -> None:
        self.page = "main"
        self.test = False
        self.toast = ""
        self.toast_t = 0.0
        self.hover = -1
        self._rects: list[pygame.Rect] = []
        self._actions: list = []
        self._font_key = None

    def _fonts(self, lw: int) -> None:
        if self._font_key != lw:
            self.title_font = pygame.font.SysFont("dejavusansmono", max(14, int(lw * 0.12)), bold=True)
            self.btn_font = pygame.font.SysFont("dejavusansmono", max(8, int(lw * 0.036)), bold=True)
            self.small_font = pygame.font.SysFont("dejavusansmono", max(6, int(lw * 0.024)), bold=True)
            self._font_key = lw

    def _layout(self, w: int, h: int):
        scale = max(1, w // 320)
        lw, lh = max(1, w // scale), max(1, h // scale)
        self._fonts(lw)
        if self.page == "main":
            bw, bh = max(54, int(lw * 0.24)), max(18, int(lh * 0.15))
            gap = max(8, int(lw * 0.03))
            total = bw * 3 + gap * 2
            x0 = (lw - total) // 2
            y = int(lh * 0.60)
            self._rects = [pygame.Rect(x0 + i * (bw + gap), y, bw, bh)
                           for i in range(3)]
            self._actions = ["singleplayer", "testmode", "quit"]
        else:
            bh = max(14, int(lh * 0.095))
            gap = max(6, int(lh * 0.026))
            dw = max(30, int(lw * 0.11))
            sw = max(112, int(lw * 0.56))
            g2 = max(6, int(lw * 0.018))
            total = sw + g2 + dw
            x0 = (lw - total) // 2
            y = int(lh * 0.28)
            self._rects = []
            self._actions = []
            for i in range(persist.SLOTS):
                yy = y + i * (bh + gap)
                self._rects.append(pygame.Rect(x0, yy, sw, bh))
                self._actions.append(i)
                self._rects.append(pygame.Rect(x0 + sw + g2, yy, dw, bh))
                self._actions.append(("delete", i))
            back = pygame.Rect(lw // 2 - max(52, int(lw * 0.17)),
                               y + persist.SLOTS * (bh + gap) + gap,
                               max(104, int(lw * 0.34)), bh)
            self._rects.append(back)
            self._actions.append("back")
        return scale, lw, lh

    def handle(self, event, w: int, h: int):
        scale, _lw, _lh = self._layout(w, h)
        if event.type == pygame.MOUSEMOTION:
            lx, ly = event.pos[0] // scale, event.pos[1] // scale
            self.hover = -1
            for i, rect in enumerate(self._rects):
                if rect.collidepoint((lx, ly)):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx, ly = event.pos[0] // scale, event.pos[1] // scale
            for i, rect in enumerate(self._rects):
                if rect.collidepoint((lx, ly)):
                    return self._actions[i]
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "back" if self.page == "saves" else "quit"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._actions:
                return self._actions[0]
        return None

    def draw(self, screen: pygame.Surface) -> None:
        w, h = screen.get_size()
        scale, lw, lh = self._layout(w, h)
        low = pygame.Surface((lw, lh))
        low.fill(BG)
        for y in range(0, lh, 4):
            pygame.draw.line(low, (18, 16, 20), (0, y), (lw, y))
        persist.set_test(self.test)

        title = "KINGPIN" if self.page == "main" else (
            "TEST SAVES" if self.test else "SAVES")
        t = self.title_font.render(title, False, TITLE)
        o = self.title_font.render(title, False, TITLE_DARK)
        tx = lw // 2 - t.get_width() // 2
        ty = int(lh * 0.15)
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            low.blit(o, (tx + ox, ty + oy))
        low.blit(t, (tx, ty))
        sub = _fit(self.small_font, "tobacco  ·  lead  ·  greed", lw - 16, DIM)
        low.blit(sub, (lw // 2 - sub.get_width() // 2, ty + t.get_height() + 4))

        for i, (rect, act) in enumerate(zip(self._rects, self._actions)):
            hovered = (i == self.hover)
            if isinstance(act, tuple) and act[0] == "delete":
                pygame.draw.rect(low, DEL_HOVER if hovered else DEL_BG, rect)
                pygame.draw.rect(low, DEL_BORDER, rect, 1)
                x = _fit(self.btn_font, "X", rect.w - 6, BTN_TEXT)
                low.blit(x, (rect.centerx - x.get_width() // 2,
                             rect.centery - x.get_height() // 2))
                continue
            if act in ("singleplayer", "quit", "back", "testmode"):
                test = (act == "testmode")
                pygame.draw.rect(low, (TEST_HOVER if hovered else TEST_BG) if test
                                 else (BTN_BG_HOVER if hovered else BTN_BG), rect)
                pygame.draw.rect(low, (TEST_BORDER_HOVER if hovered else TEST_BORDER) if test
                                 else (BTN_BORDER_HOVER if hovered else BTN_BORDER), rect, 1)
                label = {"singleplayer": "SINGLEPLAYER", "quit": "QUIT GAME",
                         "back": "BACK", "testmode": "TEST MODE"}[act]
            else:
                made, houses, coins = persist.summary(act)
                pygame.draw.rect(low, SLOT_HOVER if hovered else SLOT, rect)
                pygame.draw.rect(low, BTN_BORDER_HOVER if hovered else BTN_BORDER, rect, 1)
                if made:
                    label = "SAVE %d   -   %d COINS" % (act + 1, coins)
                else:
                    label = "SAVE %d   -   EMPTY (NEW GAME)" % (act + 1)
            text = _fit(self.btn_font, label, rect.w - 10, BTN_TEXT)
            low.blit(text, (rect.centerx - text.get_width() // 2,
                            rect.centery - text.get_height() // 2))

        hint = self.small_font.render(
            "CLICK TO SELECT" if self.page == "main" else "ESC = BACK", False, HINT)
        low.blit(hint, (lw // 2 - hint.get_width() // 2, lh - 12))
        screen.blit(pygame.transform.scale(low, (w, h)), (0, 0))


def run(screen, clock):
    """Show the menu. Returns the chosen save slot, or None to quit."""
    menu = Menu()
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            act = menu.handle(event, *screen.get_size())
            if act is None:
                continue
            if act == "quit":
                return None
            if act == "singleplayer":
                menu.test = False
                menu.page = "saves"
                menu.hover = -1
            elif act == "testmode":
                menu.test = True
                menu.page = "saves"
                menu.hover = -1
            elif act == "back":
                menu.page = "main"
                menu.hover = -1
            elif isinstance(act, tuple) and act[0] == "delete":
                persist.set_test(menu.test)
                went = persist.delete(act[1])
                menu.hover = -1
                menu.toast = ("Save deleted" if went
                              else "Nothing there to delete")
                menu.toast_t = 2.0
            elif isinstance(act, int):
                persist.set_test(menu.test)
                persist.set_slot(act)
                if not persist.exists(act):
                    persist.write({"seed": random.randint(1, 2 ** 31 - 1)}, act)
                return (act, menu.test)
        menu.draw(screen)
        pygame.display.flip()
