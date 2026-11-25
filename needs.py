"""needs.py -- world-state thoughts for a person.

The body's own hunger/injury/exhaustion are handled in mood.py.  This module
adds the place: temperature, warmth, shelter, crowding, safety and recreation.
It is sampled every couple of seconds, never per frame.
"""

from __future__ import annotations

import math

import climate
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


def _temperature(npc, now: float) -> None:
    g = _g(npc)
    if g is None:
        return
    camp = getattr(npc, "native_camp", None)
    inside = bool(getattr(npc, "in_interior", False))
    conquered = bool(getattr(camp, "conquered", False))
    # A FIRE IS NOT INSULATION.  On conquered ground the fire only keeps the
    # weather out when it is enclosed by walls and a door; before conquest the
    # old open-fire behaviour remains.
    if conquered:
        warmth = inside or climate.inside(g, camp, npc.x, npc.y)
    else:
        warmth = inside or _near_fire(npc, g, camp)
    try:
        temp = float(g.world.temperature(npc.x, npc.y))
    except Exception:
        temp = 0.5
    if conquered and not warmth and not inside:
        npc._climate_hunger = 1.35 if (temp < 0.24 or temp > 0.82) else 1.0
    elif conquered:
        npc._climate_hunger = 1.0
    if warmth or inside:
        _set(npc, "cold", None, now)
        _set(npc, "freezing", None, now)
        _set(npc, "hot", None, now)
        _set(npc, "warm", 3.0, now, 120.0)
    elif temp < 0.10:
        _set(npc, "freezing", -9.0, now)
        _set(npc, "cold", None, now)
        _set(npc, "hot", None, now)
        _set(npc, "warm", None, now)
    elif temp < 0.24:
        _set(npc, "cold", -5.0, now)
        _set(npc, "freezing", None, now)
        _set(npc, "hot", None, now)
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


def _environment(npc, now: float) -> None:
    g = _g(npc)
    if g is None:
        return
    camp = getattr(npc, "native_camp", None)
    inside = bool(getattr(npc, "in_interior", False))

    # SHELTER / SLEEP.
    conquered = bool(getattr(camp, "conquered", False))
    asleep = bool(getattr(npc, "asleep", False))
    bed = getattr(npc, "bed", None)
    insulated_bed = bool(conquered and asleep and climate.bed_inside(g, camp, bed))
    sheltered = inside or (asleep and bed is not None and
                           (not conquered or insulated_bed))
    if sheltered:
        _set(npc, "sheltered", 2.0, now, 300.0)
    else:
        _set(npc, "sheltered", None, now)
    if asleep:
        if inside:
            # A house is already shelter; do not call a man outdoors because
            # the bed he is using is not the camp's walled fireplace.
            _set(npc, "slept_outside", None, now)
            _set(npc, "slept_bed", 4.0, now, 600.0)
            npc._climate_hunger = 1.0
        elif conquered and not insulated_bed:
            # A BEDROLL OUTSIDE IS STILL OUTSIDE.  This is the real cost of not
            # building a walled fireplace room: bad sleep, bad mood and a belly
            # that empties faster in the cold/heat.
            _set(npc, "slept_outside", -10.0, now, 600.0)
            _set(npc, "slept_bed", None, now)
            npc._climate_hunger = 1.5
        elif bed is None:
            _set(npc, "slept_outside", -8.0, now, 600.0)
            _set(npc, "slept_bed", None, now)
        else:
            _set(npc, "slept_bed", 4.0, now, 600.0)
            _set(npc, "slept_outside", None, now)
            npc._climate_hunger = 1.0
    elif conquered:
        # Awake again: the night-long hunger penalty ends.  Daytime cold/heat
        # is set separately by _temperature().
        npc._climate_hunger = 1.0

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

    # SAFETY.  A war alarm somewhere else is not a personal threat.  Only a
    # live camp conflict or an enemy physically near this camp matters.
    conflict = bool(getattr(camp, "conflict", False))
    if not conflict:
        for enemy in (getattr(g, "enemies", ()) or ()):
            try:
                if (getattr(enemy, "alive", True)
                        and (enemy.x - npc.x) ** 2 + (enemy.y - npc.y) ** 2
                        <= 320.0 ** 2):
                    conflict = True
                    break
            except Exception:
                pass
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


def tick(npc, now: float, dt: float) -> None:
    """Per-NPC timers: temperature ~60s, the rest ~30s."""
    if getattr(npc, "_needs_temp_t", None) is None:
        try:
            npc._needs_temp_t = float(npc.rng.uniform(0.0, 60.0))
        except Exception:
            npc._needs_temp_t = 0.0
    if getattr(npc, "_needs_env_t", None) is None:
        try:
            npc._needs_env_t = float(npc.rng.uniform(0.0, 30.0))
        except Exception:
            npc._needs_env_t = 0.0
    npc._needs_temp_t -= dt
    if npc._needs_temp_t <= 0.0:
        npc._needs_temp_t = 60.0
        _temperature(npc, now)
    npc._needs_env_t -= dt
    if npc._needs_env_t <= 0.0:
        npc._needs_env_t = 30.0
        _environment(npc, now)
