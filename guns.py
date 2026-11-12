"""Gun magazines and reload timings, shared by the player and the NPCs.

The gunsmith turns out three weapons. A musket holds one round and takes five
seconds to reload; a double-shot holds two and takes the same five; a rifle
holds three and reloads in a single second. All three eat the same `ammo`.
"""

from __future__ import annotations

MUSKET = "musket"
DOUBLE_SHOT = "double_shot"
RIFLE = "rifle"
SHOTGUN = "shotgun"          # legacy; no longer made or issued

MAG = {MUSKET: 1, DOUBLE_SHOT: 2, RIFLE: 3, SHOTGUN: 3}   # rounds per gun
# Seconds between trigger pulls. The rifle works one round a second; the
# musket and double-shot are slow to re-aim.
FIRE_CD = {MUSKET: 0.4, DOUBLE_SHOT: 0.4, RIFLE: 1.0, SHOTGUN: 0.62}
PELLETS = {MUSKET: 1, DOUBLE_SHOT: 1, RIFLE: 1, SHOTGUN: 12}
DAMAGE = {MUSKET: 90, DOUBLE_SHOT: 90, RIFLE: 80, SHOTGUN: 80}

# Reload seconds, at zero skill -> at maximum skill. The three new weapons
# reload in a fixed time: five seconds for the old guns, one for the rifle.
RELOAD_LO = {MUSKET: 5.0, DOUBLE_SHOT: 5.0, RIFLE: 1.0, SHOTGUN: 2.0}
RELOAD_HI = {MUSKET: 5.0, DOUBLE_SHOT: 5.0, RIFLE: 1.0, SHOTGUN: 2.0}


# A RIFLEMAN FIRES IN THREES (legacy soldier pacing). The player pulls the
# trigger one round at a time instead.
BURST = {MUSKET: 1, DOUBLE_SHOT: 1, RIFLE: 3, SHOTGUN: 1}
BURST_GAP = {MUSKET: 0.0, DOUBLE_SHOT: 0.0, RIFLE: 0.08, SHOTGUN: 0.0}


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


def enemy_fire(combat, shooter, x, y, angle, distance, spread=None) -> None:
    """ONE ROUND FROM AN ENEMY, AND THE ONLY PLACE ONE IS FIRED.

    The dart decision lives here and nowhere else: a militiaman's round is a
    dart -- same damage, and at zero health the target sleeps instead of dying.
    Every gunman, soldier and warder fires through this, so a "bullet that
    should have been a dart" cannot be written a second time.
    """
    kind = getattr(shooter, "gun_kind", RIFLE)
    combat.fire(x, y, angle, distance, owner="enemy", shooter=shooter,
                damage=DAMAGE[kind], team=getattr(shooter, "team", None),
                spread=spread,
                dart=bool(getattr(shooter, "is_militia", False)))


def reload_time(kind: str, skill: float) -> float:
    lo = RELOAD_LO.get(kind, 5.0)
    hi = RELOAD_HI.get(kind, 1.0)
    return lo + (hi - lo) * max(0.0, min(1.0, skill))
