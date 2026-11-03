"""resettle.py -- THE RESETTLEMENT CAMPAIGN.

A second line leaves the south-westernmost settlement and runs straight OUT
over the world's border: that is where the trains come from, and it is where
the state sends people when the population falls.

If the country loses more than `DEFICIT_AT` people, a train's worth of settlers
is created as data and dropped in the settlements that need them, with trades
of their own -- the camp will burn through people, and this is the top-up.
"""

from __future__ import annotations

import math
import random

import pygame
import plog

DEFICIT_AT = 100              # this many gone, and the state resettles
WAVE = 60                     # how many arrive at once
OUT_PAST = 24000.0            # how far past the border the line runs

_BASE = [None]                # the population at the start
_WAVES = [0]
_END = [None]                 # the far end of the resettlement line
_WAIT = [0.0]


def _world_half() -> float:
    try:
        import main as _m
        return float(getattr(_m, "WORLD_HALF", 500000))
    except Exception:
        return 500000.0


def build(villages) -> list:
    """The resettlement line: from the south-westernmost town, out over the edge."""
    towns = [v for v in (villages or ()) if not getattr(v, "is_hub", False)
             and getattr(v, "fence_rect", None) is not None]
    if not towns:
        return []
    sw = min(towns, key=lambda v: v.x + v.y)          # the most south-western
    try:
        import fence
        side, gx, gy = fence.nearest_gate(sw, -1e9, 1e9)
        ox, oy = fence.OUTWARD[side]
    except Exception:
        gx, gy, ox, oy = sw.x, sw.y, -1.0, 1.0
    half = _world_half()
    far = half + OUT_PAST
    # out along the gate's own direction until it leaves the map
    ex = -far
    ey = far
    pts = [(gx + ox * 120.0, gy + oy * 120.0), (ex, ey)]
    try:
        import rail
        for k in range(len(pts) - 1):
            ax, ay = pts[k]
            bx, by = pts[k + 1]
            rail._SEGS.append((ax, ay, bx, by,
                               pygame.Rect(int(min(ax, bx)) - 40,
                                           int(min(ay, by)) - 40,
                                           int(abs(ax - bx)) + 80,
                                           int(abs(ay - by)) + 80)))
    except Exception as _re:
        try:
            plog.log("RESETTLE-ERROR", repr(_re)[:120])
        except Exception:
            pass
    _END[0] = (ex, ey)
    try:
        plog.log("RESETTLE", "line laid from", getattr(sw, "name", "?"),
                 "to the border at", int(ex), int(ey))
    except Exception:
        pass
    return pts


def note_population(n: int) -> None:
    if _BASE[0] is None:
        _BASE[0] = int(n)


def tick(villages, now: float, dt: float = 1.0) -> int:
    """WHEN THE COUNTRY RUNS LOW, PEOPLE ARRIVE."""
    _WAIT[0] += dt
    if _WAIT[0] < 5.0:
        return 0
    _WAIT[0] = 0.0
    try:
        import village as _v
    except Exception:
        return 0
    alive = sum(1 for n in _v.PEOPLE if getattr(n, "alive", True))
    note_population(alive)
    missing = int(_BASE[0]) - alive
    if missing < DEFICIT_AT:
        return 0
    towns = [v for v in (villages or ()) if not getattr(v, "is_hub", False)
             and getattr(v, "houses", None)]
    if not towns:
        return 0
    towns.sort(key=lambda v: len(getattr(v, "npcs", ()) or ()))
    made = 0
    rng = random.Random(int(now) ^ 0x5EED)
    for i in range(min(WAVE, missing)):
        v = towns[i % len(towns)]
        try:
            x, y = v.random_point(rng)
        except Exception:
            x, y = v.x, v.y
        _v.npc_serial = int(getattr(_v, "npc_serial", 0)) + 1
        name = "%s %s" % (rng.choice(_v.FIRST_NAMES), rng.choice(_v.LAST_NAMES))
        try:
            n = _v.NPC(x, y, random.randrange(1 << 30), name=name,
                       npc_id="settler_%d" % _v.npc_serial,
                       role="Settler", village=v)
        except Exception:
            continue
        n.job = rng.choice(("farm", "logger", "mine", "hand"))
        n.settler = True
        v.npcs.append(n)
        v.people = getattr(v, "people", []) or []
        made += 1
    if made:
        _WAVES[0] += 1
        _BASE[0] = alive + made                # the new people are the new base
        try:
            plog.log("RESETTLE", "wave", _WAVES[0], "|", made, "settlers arrived",
                     "| population was", alive, "of", missing, "missing")
        except Exception:
            pass
    return made


def waves() -> int:
    return _WAVES[0]


def line_end():
    return _END[0]
