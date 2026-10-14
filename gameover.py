"""Pixelated game-over screen with Respawn / Quit Game buttons.

The whole frame is rendered at low resolution (about 320 px wide) with
non-antialiased text and then upscaled with nearest-neighbour, so it reads as
chunky pixel art rather than a smooth web-style overlay.
"""

from __future__ import annotations

import pygame

TITLE = (198, 42, 36)
TITLE_DARK = (40, 4, 4)
BLOOD = (150, 18, 16)
BTN_BG = (38, 14, 14)
BTN_BG_HOVER = (84, 24, 22)
BTN_BORDER = (128, 44, 40)
BTN_BORDER_HOVER = (236, 92, 82)
BTN_TEXT = (240, 222, 216)
DIM = (182, 144, 138)
HINT = (122, 88, 86)


class GameOver:
    def __init__(self) -> None:
        self.buttons = [("RESPAWN", "respawn"), ("QUIT GAME", "quit")]
        self.hover = -1
        self._low_rects: list[pygame.Rect] = []
        self._font_size: int | None = None
        self.title_font = self.btn_font = self.small_font = None

    def _scale(self, w: int) -> int:
        return max(1, w // 320)

    def layout(self, w: int, h: int):
        scale = self._scale(w)
        lw, lh = max(1, w // scale), max(1, h // scale)
        if self._font_size != lw:
            self.title_font = pygame.font.SysFont("dejavusansmono", max(12, int(lw * 0.085)), bold=True)
            self.btn_font = pygame.font.SysFont("dejavusansmono", max(8, int(lw * 0.034)), bold=True)
            self.small_font = pygame.font.SysFont("dejavusansmono", max(6, int(lw * 0.022)), bold=True)
            self._font_size = lw
        bw = max(44, int(lw * 0.24))
        bh = max(14, int(lh * 0.13))
        gap = max(8, int(lw * 0.035))
        x0 = (lw - (bw * 2 + gap)) // 2
        y = int(lh * 0.60)
        self._low_rects = [pygame.Rect(x0, y, bw, bh),
                           pygame.Rect(x0 + bw + gap, y, bw, bh)]
        return scale, lw, lh

    def handle_event(self, event, w: int, h: int) -> str | None:
        scale, _, _ = self.layout(w, h)
        if event.type == pygame.MOUSEMOTION:
            lx, ly = event.pos[0] // scale, event.pos[1] // scale
            self.hover = -1
            for i, rect in enumerate(self._low_rects):
                if rect.collidepoint((lx, ly)):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx, ly = event.pos[0] // scale, event.pos[1] // scale
            for i, rect in enumerate(self._low_rects):
                if rect.collidepoint((lx, ly)):
                    return self.buttons[i][1]
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return "respawn"
            if event.key == pygame.K_ESCAPE:
                return "quit"
        return None

    def draw(self, screen: pygame.Surface, stats: list[str]) -> None:
        w, h = screen.get_size()
        scale, lw, lh = self.layout(w, h)

        # Pixelate the frozen scene behind the menu.
        low = pygame.transform.scale(screen, (lw, lh))
        shade = pygame.Surface((lw, lh), pygame.SRCALPHA)
        shade.fill((26, 2, 2, 205))
        low.blit(shade, (0, 0))

        title = self.title_font.render("GAME OVER", False, TITLE)
        outline = self.title_font.render("GAME OVER", False, TITLE_DARK)
        tx = lw // 2 - title.get_width() // 2
        ty = int(lh * 0.20)
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            low.blit(outline, (tx + ox, ty + oy))
        low.blit(title, (tx, ty))

        # blood drips
        base_y = ty + title.get_height() - 1
        for i in range(6):
            dx = tx + int(title.get_width() * (0.14 + 0.13 * i))
            length = 2 + (i * 5) % 7
            pygame.draw.line(low, BLOOD, (dx, base_y), (dx, base_y + length))
            pygame.draw.rect(low, BLOOD, (dx - 1, base_y + length, 2, 2))

        for i, line in enumerate(stats):
            text = self.small_font.render(line, False, DIM)
            low.blit(text, (lw // 2 - text.get_width() // 2,
                            ty + title.get_height() + 7 + i * 10))

        for i, ((label, _action), rect) in enumerate(zip(self.buttons, self._low_rects)):
            hovered = i == self.hover
            pygame.draw.rect(low, BTN_BG_HOVER if hovered else BTN_BG, rect)
            pygame.draw.rect(low, BTN_BORDER_HOVER if hovered else BTN_BORDER, rect, 1)
            text = self.btn_font.render(label, False, BTN_TEXT)
            low.blit(text, (rect.centerx - text.get_width() // 2,
                            rect.centery - text.get_height() // 2))

        hint = self.small_font.render("ENTER=RESPAWN   ESC=QUIT", False, HINT)
        low.blit(hint, (lw // 2 - hint.get_width() // 2, self._low_rects[0].bottom + 6))

        screen.blit(pygame.transform.scale(low, (w, h)), (0, 0))
