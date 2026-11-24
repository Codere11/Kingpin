#!/usr/bin/env python3
"""Headless checks for NPC social memory."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import relationships


class P:
    def __init__(self, name, ident):
        self.name = name
        self.id = ident
        self.social_memory = None


def main():
    target = P("Target", "t")
    a = P("A", "a")
    b = P("B", "b")
    p = type("Player", (), {"is_player": True})()
    relationships.observe(target, a, "praise", 10.0)
    relationships.observe(target, b, "insult", 11.0)
    relationships.observe(target, p, "threaten", 12.0)
    rows = relationships.summary(target)
    assert rows and rows[0]["name"] == "You", rows
    assert rows[0]["label"] in ("Feared", "Disliked"), rows[0]
    assert rows[0]["fear"] > 0
    assert any(r["name"] == "A" and r["affinity"] > 0 for r in rows)
    assert any(r["name"] == "B" and r["affinity"] < 0 for r in rows)

    for i in range(20):
        relationships.observe(target, P("N%d" % i, "n%d" % i), "praise", 20.0 + i)
    assert len(target.social_memory) <= relationships.KEEP
    assert "player" in target.social_memory

    before = target.social_memory["a"]["affinity"]
    for _ in range(5):
        relationships.tick(target, 100.0, 30.0)
    assert target.social_memory["a"]["affinity"] < before
    print("RELATIONSHIPS SELFTEST: PASS -- player-first, tags, trim, decay")


if __name__ == "__main__":
    main()
