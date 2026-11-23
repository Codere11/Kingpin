"""needs.py -- world-state thoughts for a person.

The body's own hunger/injury/exhaustion are handled in mood.py.  This module
adds the place: temperature, warmth, shelter, crowding, safety and recreation.
It is sampled every couple of seconds, never per frame.
"""

from __future__ import annotations

import math

import mood


def _g(npc):
    camp = getattr(npc, "native_camp", None)
    return getattr(camp, "g", None) if camp is not None else None


def _near_fire(npc, g, camp) -> bool:
    fire = getattr(camp, "fireplace", None) if camp is not None else None
    if fire is not None:
        try:
            if math.hypot(fire.x - npc.x, fire.y - npc.y) < 180.0:
                return True
        except Exception:
            pass
    for wp in (getattr(g, "placed_work", ()) or ()):
        if getattr(wp, "kind", "") == "fireplace":
            try:
                if math.hypot(wp.x - npc.x, wp.y - npc.y) < 180.0:
                    return True
            except Exception:
                pass
    return False


def _set(npc, tid, delta, now, seconds=180.0):
    if delta is None:
        try:
            npc.mood_thoughts.pop(tid, None)
        except Exception:
            pass
    else:
        mood.ensure_thought(npc, tid, delta, now, seconds)


def update(npc, now: float) -> None:
    """Add/remove the thoughts caused by the world around this person."""
    g = _g(npc)
    if g is None:
        return
    camp = getattr(npc, "native_camp", None)
    warmth = _near_fire(npc, g, camp)
    inside = bool(getattr(npc, "in_interior", False))

    # TEMPERATURE.  The world temperature is 0 cold .. 1 hot.
    try:
        temp = float(g.world.temperature(npc.x, npc.y))
    except Exception:
        temp = 0.5
    if warmth or inside:
        _set(npc, "cold", None, now)
        _set(npc, "freezing", None, now)
        _set(npc, "warm", 3.0, now, 120.0)
    elif temp < 0.10:
        _set(npc, "freezing", -9.0, now)
        _set(npc, "cold", None, now)
        _set(npc, "warm", None, now)
    elif temp < 0.24:
        _set(npc, "cold", -5.0, now)
        _set(npc, "freezing", None, now)
        _set(npc, "warm", None, now)
    elif temp > 0.82:
        _set(npc, "hot", -4.0, now)
        _set(npc, "cold", None, now)
        _set(npc, "freezing", None, now)
        _set(npc, "warm", None, now)
    else:
        _set(npc, "cold", None, now)
        _set(npc, "freezing", None, now)
        _set(npc, "hot", None, now)
        _set(npc, "warm", None, now)

    # SHELTER / SLEEP.
    if inside or getattr(npc, "asleep", False) and getattr(npc, "bed", None) is not None:
        _set(npc, "sheltered", 2.0, now, 300.0)
    else:
        _set(npc, "sheltered", None, now)
    if getattr(npc, "asleep", False):
        if getattr(npc, "bed", None) is None:
            _set(npc, "slept_outside", -5.0, now, 600.0)
            _set(npc, "slept_bed", None, now)
        else:
            _set(npc, "slept_bed", 4.0, now, 600.0)
            _set(npc, "slept_outside", None, now)

    # CROWDING: only extreme crowding matters.
    try:
        people = npc._camp_people()
    except Exception:
        people = ()
    close = 0
    for p in people:
        if p is npc or not getattr(p, "alive", True):
            continue
        try:
            if math.hypot(p.x - npc.x, p.y - npc.y) < 120.0:
                close += 1
        except Exception:
            pass
    if close >= 12:
        _set(npc, "crowded", -3.0, now)
    else:
        _set(npc, "crowded", None, now)

    # SAFETY.
    conflict = bool(getattr(camp, "conflict", False)) or int(getattr(g, "war_alarms", 0)) > 0
    if conflict:
        _set(npc, "threatened", -6.0, now)
        _set(npc, "safe", None, now)
    else:
        _set(npc, "threatened", None, now)
        _set(npc, "safe", 1.0, now, 120.0)

    # RECREATION: a craving left unsatisfied.
    if float(getattr(npc, "yearning", 0.0)) >= 0.5:
        _set(npc, "recreation_unsatisfied", -5.0, now)
    else:
        _set(npc, "recreation_unsatisfied", None, now)

    # LONELINESS: no bond and nobody close.
    if getattr(npc, "bond_partner", None) is None and close <= 1:
        _set(npc, "lonely", -2.0, now, 300.0)
    else:
        _set(npc, "lonely", None, now)
