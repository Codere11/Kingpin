#!/usr/bin/env python3
"""Headless check of the breaking spree and repair path."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def main():
    import pygame
    pygame.init()
    pygame.display.set_mode((640, 480))
    import engine
    import placement
    import village

    chest = placement.Chest(100.0, 100.0)
    camp = SimpleNamespace(x=100.0, y=100.0, g=None, people=[],
                           farmers=[], warriors=[], handlers=[], workers=[],
                           loggers=[], artisans=[], researchers=[], doctors=[],
                           miners=[], smiths=[], weavers=[], spicemen=[],
                           gunsmiths=[], unemployed=[])
    g = SimpleNamespace(built_chests=[chest], built_signs=[],
                        built_foodboxes=[], placed_work=[],
                        player=SimpleNamespace(x=500.0, y=500.0, alive=True,
                                               id="player"),
                        inventory=None, test_mode=True, now=0.0,
                        toast=lambda _m: None)
    camp.g = g
    n = village.NPC(80.0, 100.0, 7, name="Anpao", npc_id="break_test",
                    role="Farmer")
    n.native = True
    n.native_role = "farmer"
    n.job = "farmer"
    n.native_camp = camp
    camp.people = [n]
    camp.farmers = [n]

    # Simulate the real F9 cycle with time between presses: berserk picks the
    # player as its target, then the next press switches to spree.  The old
    # code kept that player target and the spree followed the player.  The
    # state change must clear it.
    import mood
    g.player.x, g.player.y = 300.0, 100.0
    g.player.max_health = 100
    g.player.health = 100
    g.player.radius = 10
    g.player.take_damage = lambda *a, **k: None
    n.break_state = "berserk"
    n.break_until = 1000.0
    n._break_target = None
    n._break_action(0.2, None, 0.0)
    assert getattr(n, "_break_target", None) is g.player
    mood.set_break(n, "breaking_spree", 1.0, seconds=1000.0)
    assert getattr(n, "_break_target", None) is None
    n._break_action(0.2, None, 1.2)
    assert hasattr(getattr(n, "_break_target", None), "condition"), \
        "spree kept a person target instead of a breakable"
    n.break_state = "breaking_spree"
    n.break_until = 1000.0
    n._spree_broken = 0
    n._break_target = None
    now = 0.0
    for _ in range(400):
        n._break_action(0.2, None, now)
        now += 0.2
        if chest.broken:
            break
    assert chest.broken, "spree did not break the chest"
    assert chest.condition <= 0.0

    assert engine._repair_broken(g, chest.x, chest.y)
    assert not chest.broken
    assert chest.condition == chest.max_condition
    print("MAJOR BREAK SELFTEST: PASS -- spree broke the chest, repair restored it")


if __name__ == "__main__":
    main()
