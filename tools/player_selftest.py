#!/usr/bin/env python3
"""Headless checks for the player's inferred personality."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import player_mind


class G:
    def __init__(self):
        self.world = type("W", (), {"seed": 12345})()
        self.now = 0.0


class P:
    id = "npc_1"
    mbti = "INFJ"


def main():
    g = G()
    st = player_mind.ensure(g)
    assert st["start_type"] in player_mind.persona.TYPE_WEIGHTS if hasattr(player_mind, "persona") else True
    s0 = player_mind.summary(g)
    assert len(s0["axes"]) == 4
    assert len(s0["letters"]) == 4

    player_mind.observe(g, "initiated", amount=20)
    player_mind.observe(g, "sensing", amount=10)
    player_mind.observe(g, "contact", P(), amount=10.0)
    s1 = player_mind.summary(g)
    assert s1["axes"][0][2][0] == "E"
    assert s1["axes"][1][2][0] == "S"
    assert s1["axes"][2][2][0] == "F"

    # Contact throttle: same NPC inside 60 s does not count twice.
    before = g.player_mind["f_contacts"]
    player_mind.observe(g, "contact", P())
    assert g.player_mind["f_contacts"] == before

    # Decay pulls counters down.
    before = g.player_mind["initiated"]
    player_mind.tick(g, 10.0)
    assert g.player_mind["initiated"] < before

    # Retaliation within the window and mercy after it.
    g.now = 100.0
    player_mind.observe(g, "provoked")
    g.now = 105.0
    player_mind.observe(g, "retaliated")
    assert g.player_mind["conquered_retaliated"] > 0
    g.now = 200.0
    player_mind.observe(g, "provoked")
    g.now = 225.0
    player_mind.tick(g, 2.0)
    assert g.player_mind["conquered_merciful"] > 0

    snap = player_mind.snapshot(g)
    g2 = G()
    player_mind.restore(g2, snap)
    assert player_mind.summary(g2)["start_type"] == snap["start_type"]
    print("PLAYER MIND SELFTEST: PASS -- prior, actions, decay, contacts, J/P")


if __name__ == "__main__":
    main()
