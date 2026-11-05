"""combat_actions.py -- THE PLAYER'S OWN WEAPONS.

Firing a gun, swinging the axe, working the pick, and the click that opens a
man. Extracted from main.py, one action at a time.
"""

from __future__ import annotations

import math

import pygame
import guns


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
