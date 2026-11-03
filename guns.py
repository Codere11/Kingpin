"""Gun magazines and reload timings, shared by the player and the NPCs."""

from __future__ import annotations

RIFLE = "rifle"
SHOTGUN = "shotgun"

MAG = {RIFLE: 10, SHOTGUN: 3}                 # rounds per magazine
# A RIFLE HAS NO COOL-DOWN. One click, one round: the lever is worked by the
# player's own hand, so the limit is how fast he clicks, not a timer. The
# shotgun still has to be pumped.
FIRE_CD = {RIFLE: 0.0, SHOTGUN: 0.62}         # seconds between shots
PELLETS = {RIFLE: 1, SHOTGUN: 12}             # a fistful, not three
DAMAGE = {RIFLE: 80, SHOTGUN: 80}             # ONE ROUND TAKES 80 HEALTH

# Reload seconds, at zero skill -> at maximum skill.
RELOAD_LO = {RIFLE: 3.0, SHOTGUN: 2.0}
RELOAD_HI = {RIFLE: 1.0, SHOTGUN: 2.0}   # the pump takes two seconds, always


# A RIFLEMAN FIRES IN THREES. Three rounds as fast as the lever can be worked,
# then the aim-and-breathe pause he already had. The shotgun stays one pull.
BURST = {RIFLE: 3, SHOTGUN: 1}
BURST_GAP = {RIFLE: 0.08, SHOTGUN: 0.0}


def rounds_now(who, dt: float, can_start: bool) -> int:
    """How many rounds this man pulls the trigger for THIS frame.

    Mid-burst, one round per gap. Finished, nothing until he may start again.
    Starting, the first round now and the rest queued behind `BURST_GAP`.
    """
    kind = getattr(who, "gun_kind", RIFLE)
    left = int(getattr(who, "_burst_left", 0) or 0)
    t = float(getattr(who, "_burst_t", 0.0) or 0.0) - float(dt)
    if t > 0.0:
        who._burst_t = t
        return 0
    if left > 0:
        who._burst_left = left - 1
        who._burst_t = BURST_GAP.get(kind, 0.0)
        return 1
    if not can_start:
        return 0
    who._burst_left = max(0, BURST.get(kind, 1) - 1)
    who._burst_t = BURST_GAP.get(kind, 0.0) if who._burst_left else 0.0
    return 1


def reload_time(kind: str, skill: float) -> float:
    lo = RELOAD_LO.get(kind, 3.0)
    hi = RELOAD_HI.get(kind, 1.0)
    return lo + (hi - lo) * max(0.0, min(1.0, skill))
