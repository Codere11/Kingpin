"""hudtime.py -- SMALL LEAF HELPERS: the clock, the day, the HUD buttons.

award_levels, clamp_world, the day/night clock, the speed button, and the
fireplace test. Pulled out of main.py so the engine loop stays thin.
"""

from __future__ import annotations

import math

import pygame


def award_levels(skills, player) -> None:
    """A REAL level-up wears the shine."""
    if skills.just_leveled:
        skills.just_leveled = False
        player.level_flash = player.LEVEL_FLASH


def clamp_world(player, world_half: float) -> None:
    """The world is finite, and the loading screen builds all of it."""
    player.x = min(max(player.x, -world_half), world_half)
    player.y = min(max(player.y, -world_half), world_half)


def night_factor(now, day_length, t=None) -> float:
    if t is None:
        t = now
    tt = (0.30 + t / day_length) % 1.0
    brightness = 0.5 + 0.5 * math.sin(2.0 * math.pi * (tt - 0.25))
    return 1.0 - brightness


def next_morning(t: float, now, day_length: float) -> float:
    for _ in range(int(day_length / 5.0) + 2):
        t += 5.0
        if night_factor(now, day_length, t) <= 0.38:
            break
    return t


def day_phase(now, day_length: float) -> str:
    """Where the villagers are in their day."""
    if night_factor(now, day_length) > 0.38:
        return "sleep"
    t = (0.30 + now / day_length) % 1.0
    if t < 0.30 or t >= 0.72:
        return "home"
    if 0.40 <= t < 0.60:
        return "market"          # mid-day: business is done in the square
    return "work"


def speed_button(vw: int, vh: int) -> pygame.Rect:
    return pygame.Rect(vw // 2 - 74, vh - 142, 148, 32)


def draw_speed_button(screen, font, test_mode, time_scale, vw, vh) -> None:
    if not test_mode:
        return
    r = speed_button(vw, vh)
    pygame.draw.rect(screen, (30, 30, 36), r, border_radius=8)
    pygame.draw.rect(screen,
                     (222, 176, 88) if time_scale > 1.0 else (110, 110, 122),
                     r, width=2, border_radius=8)
    text = font.render("SPEED  x%d" % int(time_scale), True,
                       (244, 236, 214) if time_scale > 1.0 else (172, 172, 182))
    screen.blit(text, (r.centerx - text.get_width() // 2,
                       r.centery - text.get_height() // 2))


def near_fireplace(player, inside_house) -> bool:
    if inside_house is None:
        return False
    return inside_house.interior.fireplace_near(player.x, player.y)


def draw_status(screen, font, hud_status, vw) -> None:
    """Battle / plunder banner, top-centre."""
    if not hud_status:
        return
    label = font.render(hud_status, True, (244, 236, 214))
    plate = pygame.Surface((label.get_width() + 26, 30), pygame.SRCALPHA)
    pygame.draw.rect(plate, (16, 16, 20, 205), plate.get_rect(), border_radius=8)
    pygame.draw.rect(plate, (150, 120, 60), plate.get_rect(), width=2, border_radius=8)
    screen.blit(plate, (vw // 2 - plate.get_width() // 2, 8))
    screen.blit(label, (vw // 2 - label.get_width() // 2, 8 + (30 - label.get_height()) // 2))


def tick_conquest(active_chaos, player, toast, dt) -> None:
    """Plunder timers run everywhere, indoors included."""
    for village in list(active_chaos):
        village.chaos -= dt
        if village.chaos <= 0.0:
            village.chaos = 0.0
            village.conquered = True
            village.nation = player.nation
            for npc in village.npcs:
                npc.nation = player.nation
                npc.team = ("nation", player.nation)
            active_chaos.remove(village)
            toast(f"{village.name} has joined your nation")


def draw_hunger_gray(screen, player) -> None:
    """Starving drains the colour out of the world."""
    if player.hunger >= 40.0:
        return
    k = 1.0 - player.hunger / 40.0
    gray = pygame.transform.grayscale(screen)
    gray.set_alpha(int(205 * k))
    screen.blit(gray, (0, 0))
