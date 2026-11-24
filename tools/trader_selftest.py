#!/usr/bin/env python3
"""Headless check of the conquered trader's chest -> ship -> coin loop."""

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
    import inventory
    import placement
    import village

    chest = placement.Chest(100.0, 100.0)
    chest.inventory.add("cigar", 50, quality=4)
    player_inv = inventory.Inventory(32)
    g = SimpleNamespace(built_chests=[chest], inventory=player_inv,
                        now=0.0, test_mode=True,
                        toast=lambda _m: None,
                        war_alarms=0, placed_work=[], enemies=[])
    camp = SimpleNamespace(x=100.0, y=100.0, g=g, people=[],
                           farmers=[], warriors=[], handlers=[], workers=[],
                           loggers=[], artisans=[], researchers=[], doctors=[],
                           traders=[], miners=[], smiths=[], weavers=[],
                           spicemen=[], gunsmiths=[], unemployed=[])
    n = village.NPC(100.0, 100.0, 42, name="Tala", npc_id="trader_test",
                    role="Trader")
    n.native = True
    n.native_role = "trader"
    n.job = "trader"
    n.native_camp = camp
    camp.people = [n]
    camp.traders = [n]
    player = SimpleNamespace(x=100.0, y=100.0, alive=True, id="player")
    g.player = player

    for _ in range(2000):
        n._work_trader(0.1)
        g.now += 0.1
    assert chest.inventory.count_of("cigar") == 0, "trader did not take the goods"
    coins = player_inv.count_of("coin")
    assert coins > 0, "trader did not hand over coin"
    assert n.trader_state == "idle", n.trader_state
    print("TRADER SELFTEST: PASS -- gathered 50, sold at ship, handed over %d coin" % coins)


if __name__ == "__main__":
    main()
