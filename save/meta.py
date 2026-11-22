"""meta.py -- the world's identity and clock.

The seed, the beach he woke on, the ship's berth, the clock and the counters
that belong to no single settlement.
"""

from __future__ import annotations

import time


def snapshot(g) -> dict:
    ship = getattr(g, "ship_npc", None)
    return {
        "seed": int(g.world.seed),
        "spawn": [float(g._spawn[0]), float(g._spawn[1])],
        "ship": ([float(ship.x), float(ship.y)] if ship is not None else None),
        "now": float(getattr(g, "now", 0.0)),
        "kills": int(getattr(g, "kills", 0)),
        "war_alarms": int(getattr(g, "war_alarms", 0)),
        "conquered_count": int(getattr(g, "conquered_count", 0)),
        "saved_at": time.time(),
    }


def apply(g, data: dict) -> None:
    data = data or {}
    g.now = float(data.get("now", getattr(g, "now", 0.0)))
    g.kills = int(data.get("kills", getattr(g, "kills", 0)))
    g.war_alarms = int(data.get("war_alarms", getattr(g, "war_alarms", 0)))
    g.conquered_count = int(data.get("conquered_count",
                                     getattr(g, "conquered_count", 0)))
    spawn = data.get("spawn")
    if spawn and len(spawn) >= 2:
        g._spawn = (float(spawn[0]), float(spawn[1]))
    ship = data.get("ship")
    if ship and len(ship) >= 2 and getattr(g, "ship_npc", None) is not None:
        g.ship_npc.x = float(ship[0])
        g.ship_npc.y = float(ship[1])
