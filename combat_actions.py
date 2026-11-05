"""combat_actions.py -- THE PLAYER'S OWN WEAPONS.

Firing a gun, swinging the axe, working the pick, and the click that opens a
man. Extracted from main.py, one action at a time.
"""

from __future__ import annotations

import math

import random

import pygame
import guns
import ore


def fire(player, inventory, skills, combat, cam_x, cam_y, zoom, toast) -> None:
    stack = inventory.selected_stack()
    if stack is None or stack.defn.id not in (guns.RIFLE, guns.SHOTGUN):
        return
    kind = stack.defn.id
    if player.reloading > 0.0 or player.gun_cd > 0.0:
        return
    if player.mags.get(kind, 0) <= 0:
        toast("Empty \u2014 press R to reload")
        return
    player.mags[kind] -= 1
    player.gun_cd = guns.FIRE_CD[kind]
    fx, fy = player.facing
    px, py = -fy, fx
    muzzle_x = player.x + fx * 30.0 + px * 7.0
    muzzle_y = player.y + fy * 30.0 + py * 7.0
    mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
    wmouse_x, wmouse_y = mouse_x / zoom, mouse_y / zoom  # world space
    distance = math.hypot((cam_x + wmouse_x) - muzzle_x,
                          (cam_y + wmouse_y) - muzzle_y)
    spread = skills.shot_spread()
    for _ in range(guns.PELLETS[kind]):
        extra = 0.0 if kind == guns.RIFLE else 0.11   # shotgun scatters
        combat.fire(muzzle_x, muzzle_y, player.facing_angle, distance,
                    shooter=player, owner="player", damage=guns.DAMAGE[kind],
                    team="player", spread=spread + extra)
    skills.gain_shooting()


def use_pickaxe(player, combat, ore_field, inventory, pay_share, mark_dirty,
                toast) -> None:
    import main as _m
    if player.dead or not player.can_swing():
        return
    player.start_swing()
    angle = player.facing_angle
    combat.spawn_swing(player.x, player.y, angle)

    def in_arc(tx, ty, extra=0.0):
        dx, dy = tx - player.x, ty - player.y
        if math.hypot(dx, dy) > _m.AXE_REACH + extra:
            return False
        delta = abs(((math.atan2(dy, dx) - angle + math.pi) % (2.0 * math.pi)) - math.pi)
        return delta <= _m.AXE_ARC

    struck = None
    nearest = 1e9
    for chunk in ore_field.near(player.x, player.y, _m.AXE_REACH + 30.0):
        cx = min(max(player.x, chunk.rect.left), chunk.rect.right)
        cy = min(max(player.y, chunk.rect.top), chunk.rect.bottom)
        distance = math.hypot(player.x - cx, player.y - cy)
        if distance > _m.AXE_REACH or not in_arc(chunk.x, chunk.y, 20.0):
            continue
        if distance < nearest:
            nearest = distance
            struck = chunk
    if struck is None:
        toast("Nothing to mine here")
        return
    struck.strikes += 1
    combat.spawn_impact(struck.x, struck.y, (150, 150, 160))
    if struck.strikes >= ore.STRIKES:
        struck.mined = True
        ore_field.mined.add(struck.cell)
        amount = random.randint(ore.YIELD_LO, ore.YIELD_HI)
        inventory.add("iron", amount)
        pay_share("iron", amount)
        mark_dirty()
        toast(f"Mined iron   +{amount}")
    else:
        toast(f"Mining\u2026  {struck.strikes}/{ore.STRIKES}")
