"""Gun magazines and reload timings, shared by the player and the NPCs."""

from __future__ import annotations

RIFLE = "rifle"
SHOTGUN = "shotgun"

MAG = {RIFLE: 10, SHOTGUN: 3}                 # rounds per magazine
FIRE_CD = {RIFLE: 0.28, SHOTGUN: 0.62}        # seconds between shots
PELLETS = {RIFLE: 1, SHOTGUN: 6}              # projectiles per shot
DAMAGE = {RIFLE: 25, SHOTGUN: 12}             # damage per projectile

# Reload seconds, at zero skill -> at maximum skill.
RELOAD_LO = {RIFLE: 3.0, SHOTGUN: 5.0}
RELOAD_HI = {RIFLE: 1.0, SHOTGUN: 1.0}


def reload_time(kind: str, skill: float) -> float:
    lo = RELOAD_LO.get(kind, 3.0)
    hi = RELOAD_HI.get(kind, 1.0)
    return lo + (hi - lo) * max(0.0, min(1.0, skill))
