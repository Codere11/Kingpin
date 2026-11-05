"""SMALL LIFE/HUD ACTIONS extracted from main's frame (the truth-teller click,
respawn, sleeping, the night shade, and the conquest HUD line)."""
import pygame
import plog


def try_talk(truth_holder, village_mod, pygame, cam_x, cam_y, zoom,
             dialogue_panel, player, main_capital, plog) -> bool:
    """DID THE PLAYER CLICK THE MAN WHO ANSWERS QUESTIONS?"""
    tt = truth_holder[0]
    if tt is None:
        for _n in list(village_mod.PEOPLE) + list(village_mod.TRAVELLERS):
            if getattr(_n, "is_truth_teller", False):
                tt = _n
                truth_holder[0] = tt
                break
    if tt is None:
        return False
    mx, my = pygame.mouse.get_pos()
    wx = cam_x + mx / zoom
    wy = cam_y + my / zoom
    if abs(wx - tt.x) < 34.0 and -80.0 < (wy - tt.y) < 30.0:
        dialogue_panel.open(tt, player, main_capital()[0])
        pygame.mouse.set_visible(True)
        plog.log("TALK", "opened with", getattr(tt, "name", "?"))
        return True
    return False


def respawn(player, truth, truth_home, truth_holder, combat, pygame) -> bool:
    """HE COMES BACK WITH YOU."""
    pygame.mouse.set_visible(False)
    player.respawn()
    if truth is not None:
        truth_home[0], truth_home[1] = player.x + 44.0, player.y
        truth.x, truth.y = truth_home[0], truth_home[1]
        truth.alive = True
        truth.asleep = False
        truth.health = truth.max_health
        truth_holder[0] = truth
    combat.bullets.clear()
    combat.flashes.clear()
    return False


def try_sleep(inside_house, player, math, reach, toast, night_factor,
              sleep_time, pygame) -> float:
    """LIE DOWN WHEN THE NIGHT IS DEEP ENOUGH."""
    if inside_house is None:
        return None
    bed = None
    for kind, rect in inside_house.interior.furniture:
        if kind == "bed":
            bed = rect
    if bed is None:
        return None
    if math.hypot(player.x - bed.centerx, player.y - bed.centery) > reach + 46.0:
        toast("Get closer to the bed")
        return None
    if night_factor() <= 0.38:
        toast("You can only sleep at night")
        return None
    pygame.mouse.set_visible(False)
    return sleep_time


def draw_night(night_factor, vision, interior_vision, shade_cache, vw, vh,
               screen, draw_status) -> None:
    night = night_factor()
    vision.cone_deg = 175.0 - 55.0 * night
    interior_vision.cone_deg = 175.0 - 55.0 * night
    if night > 0.03:
        shade = shade_cache.get((vw, vh))
        if shade is None:
            shade = pygame.Surface((vw, vh))
            shade.fill((10, 14, 32))
            shade_cache[(vw, vh)] = shade
        shade.set_alpha(int(195 * night))
        screen.blit(shade, (0, 0))
    draw_status()


def update_hud(active_chaos, visible_villages, math) -> str:
    if active_chaos:
        v = min(active_chaos, key=lambda q: q.chaos)
        return ("Battle won  -  %d seconds of plundering left"
                % int(math.ceil(v.chaos)))
    return ("Battle" if any(v.battle for v in visible_villages) else "")
