"""newsbubble.py -- HEARING AND SHOWING THE WAR NEWS.

One man tells the player one thing, out of his own mouth, in a bubble over
his head. Extracted from main.py.
"""

from __future__ import annotations

import math
import time

import pygame
import war


def hear_news(player, chat, hear_at, heard, visible_villages, now,
              nation_name) -> None:
    """THE PLAYER LEARNS THE WAR THE WAY EVERYBODY ELSE DOES: BY BEING TOLD."""
    if player.dead or chat:
        return
    # NOT EVERY FRAME: four times a second hears the same conversation.
    _t = time.perf_counter()
    if _t < hear_at[0]:
        return
    hear_at[0] = _t + 0.25
    for v in visible_villages:
        if getattr(v, "hostile", False):
            continue
        for n in v.npcs:
            if not n.alive or n.asleep or n.in_interior:
                continue
            # NOT THE COLUMN. A marching army is not a man telling you the news.
            if (getattr(n, "is_soldier", False)
                    or getattr(n, "levied", False)
                    or getattr(n, "on_duty", False)
                    or getattr(n, "is_commander", False)
                    or getattr(n, "weapon", None) is not None):
                continue
            if math.hypot(n.x - player.x, n.y - player.y) > 250.0:
                continue
            for e in list(getattr(n, "news", ()) or ()):
                if len(e) < 5:
                    continue
                if now - e[0] >= war.WAR_NEWS_LIFETIME:
                    continue
                key = (e[1], int(e[2]), e[4])
                if key in heard:
                    continue
                heard.add(key)
                chat.append(["The nation of %s seized %s"
                             % (nation_name(e[4]), e[1]), 7.0, n])
                return


def tick_news(chat, dt: float) -> None:
    if chat:
        chat[0][1] -= dt
        if chat[0][1] <= 0.0:
            chat.pop(0)


def draw_news(surf, cam_x: float, cam_y: float, w: int, h: int, chat,
              player, news_lab, speech_font) -> None:
    """A SPEECH BUBBLE, OUT OF THE SPEAKER'S OWN MOUTH."""
    if not chat:
        return
    text, life, who = chat[0]
    if who is None or not getattr(who, "alive", False):
        chat.pop(0)
        return
    if math.hypot(who.x - player.x, who.y - player.y) > 250.0:
        return
    fade = min(1.0, life / 1.6)
    lab = news_lab[1]
    if lab is None or news_lab[0] != text:
        lab = speech_font.render(text, True, (30, 26, 22))
        news_lab[0], news_lab[1] = text, lab
    pad = 5
    bw, bh = lab.get_width() + pad * 2, lab.get_height() + pad * 2
    hx = int(who.x - cam_x)
    hy = int(who.y - cam_y) - 22
    bx = max(3, min(w - bw - 3, hx - bw // 2))
    by = max(3, hy - bh - 5)
    box = pygame.Surface((bw, bh + 6), pygame.SRCALPHA)
    pygame.draw.rect(box, (238, 231, 209, int(242 * fade)),
                     pygame.Rect(0, 0, bw, bh), border_radius=5)
    pygame.draw.rect(box, (150, 110, 62, int(238 * fade)),
                     pygame.Rect(0, 0, bw, bh), width=1, border_radius=5)
    tail = max(4, min(bw - 4, hx - bx))
    pygame.draw.polygon(box, (238, 231, 209, int(242 * fade)),
                        [(tail - 5, bh - 1), (tail + 5, bh - 1), (tail, bh + 6)])
    pygame.draw.polygon(box, (150, 110, 62, int(238 * fade)),
                        [(tail - 5, bh - 1), (tail + 5, bh - 1), (tail, bh + 6)], 1)
    surf.blit(box, (bx, by))
    lab.set_alpha(int(255 * fade))
    surf.blit(lab, (bx + pad, by + pad))
