"""antics.py -- small, visible slices of camp life.

Every camp now and then does something that is not work:
a dance around the fire, or a chase around the settlement.  One activity at a
time, a few people, and only while they are awake.  The module moves those
people; NPC.update returns early while they are busy, and NPC.draw adds the
little visual flourishes.
"""

from __future__ import annotations

import math
import random


DANCE_MIN, DANCE_MAX = 14.0, 24.0
CHASE_MIN, CHASE_MAX = 12.0, 20.0
FIRST_DELAY = (24.0, 55.0)
NEXT_DELAY = (70.0, 135.0)


def _people(camp):
    seen = set()
    out = []
    for attr in ("farmers", "warriors", "handlers", "workers", "loggers",
                 "artisans", "researchers", "doctors", "traders", "miners",
                 "smiths", "weavers", "spicemen", "gunsmiths", "unemployed"):
        for p in (getattr(camp, attr, ()) or ()):
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            out.append(p)
    pool = getattr(camp, "people", None)
    if isinstance(pool, list):
        for p in pool:
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            out.append(p)
    return out


def _camp(g):
    """Prefer the player's own camp, otherwise the nearest conquered one."""
    own = getattr(g, "player_camp", None)
    if own is not None and getattr(own, "conquered", False):
        return own
    camps = [c for c in (getattr(g, "native_settlements", {}) or {}).values()
             if getattr(c, "conquered", False)]
    if not camps:
        return None
    px = float(getattr(getattr(g, "player", None), "x", 0.0))
    py = float(getattr(getattr(g, "player", None), "y", 0.0))
    return min(camps, key=lambda c: (getattr(c, "x", px) - px) ** 2
               + (getattr(c, "y", py) - py) ** 2)


def _fire(camp):
    fire = getattr(camp, "fireplace", None)
    if fire is not None:
        return float(getattr(fire, "x", camp.x)), float(getattr(fire, "y", camp.y))
    return float(getattr(camp, "x", 0.0)), float(getattr(camp, "y", 0.0))


def _free_people(g, camp, now):
    out = []
    for p in _people(camp):
        if (not getattr(p, "alive", True)
                or getattr(p, "asleep", False)
                or getattr(p, "in_interior", False)
                or getattr(p, "break_state", "normal") != "normal"
                or getattr(p, "_antic_active", False)
                or getattr(p, "trader_rider", None) is not None):
            continue
        if float(getattr(p, "_convo_busy_until", 0.0)) > now:
            continue
        out.append(p)
    return out


def _clear_one(p):
    try:
        p._antic_active = False
        p.activity = ""
        p._antic_spot = None
    except Exception:
        pass


def _stop(g):
    state = getattr(g, "_antic", None)
    if state:
        for p in state.get("actors", ()):
            _clear_one(p)
    g._antic = None
    g._antic_next = float(getattr(g, "now", 0.0)) + random.uniform(*NEXT_DELAY)


def _start(g, now):
    camp = _camp(g)
    if camp is None:
        return False
    people = _free_people(g, camp, now)
    if len(people) < 2:
        return False
    if getattr(camp, "conflict", False) or getattr(camp, "battle", False):
        return False
    rng = getattr(g, "_antics_rng", None)
    if rng is None:
        rng = g._antics_rng = random.Random(
            int(getattr(getattr(g, "world", None), "seed", 1)) ^ 0xA17C5)
    fx, fy = _fire(camp)
    night = bool(getattr(g, "night", False))
    dance = night or rng.random() < 0.42
    if dance:
        actors = rng.sample(people, min(len(people), rng.randint(2, 4)))
        base = rng.uniform(0.0, math.tau)
        for i, p in enumerate(actors):
            p._antic_active = True
            p.activity = "dance"
            p._antic_phase = base + i * (math.tau / max(1, len(actors)))
            p._antic_spot = (fx, fy, 38.0 + (i % 2) * 14.0)
            p.pause = 0.0
            p.moving = True
        g._antic = {"kind": "dance", "camp": camp, "actors": actors,
                    "fire": (fx, fy), "until": now + rng.uniform(DANCE_MIN, DANCE_MAX),
                    "next_step": 0.0}
        return True
    pair = rng.sample(people, 2)
    runner, chaser = pair[0], pair[1]
    for p in pair:
        p._antic_active = True
        p.activity = "chase"
        p.pause = 0.0
        p.moving = True
    runner._antic_spot = (fx, fy, 70.0)
    chaser._antic_spot = (runner.x, runner.y, 0.0)
    g._antic = {"kind": "chase", "camp": camp, "actors": pair,
                "runner": runner, "chaser": chaser,
                "until": now + rng.uniform(CHASE_MIN, CHASE_MAX),
                "next_step": 0.0, "home": (fx, fy)}
    return True


def _tick_dance(g, state, dt, now):
    fx, fy = state["fire"]
    for p in state["actors"]:
        if not getattr(p, "alive", True) or getattr(p, "asleep", False):
            _clear_one(p)
            continue
        ang = float(getattr(p, "_antic_phase", 0.0)) + now * 0.75
        radius = 38.0 + (id(p) % 2) * 14.0
        tx = fx + math.cos(ang) * radius
        ty = fy + math.sin(ang) * radius
        try:
            d = math.hypot(tx - p.x, ty - p.y)
            if d > 8.0:
                p._step_toward(tx, ty, dt, 1.05)
            else:
                p.facing = ((fx - p.x) / max(1e-3, math.hypot(fx - p.x, fy - p.y)),
                            (fy - p.y) / max(1e-3, math.hypot(fx - p.x, fy - p.y)))
                p.moving = True
        except Exception:
            pass


def _tick_chase(g, state, dt, now):
    runner = state["runner"]
    chaser = state["chaser"]
    if (not getattr(runner, "alive", True) or not getattr(chaser, "alive", True)
            or getattr(runner, "asleep", False) or getattr(chaser, "asleep", False)):
        _clear_one(runner)
        _clear_one(chaser)
        return
    hx, hy = state["home"]
    state["next_step"] = float(state.get("next_step", 0.0)) - dt
    if state["next_step"] <= 0.0:
        state["next_step"] = random.uniform(1.1, 2.1)
        ang = random.uniform(0.0, math.tau)
        rr = random.uniform(28.0, 115.0)
        runner._antic_spot = (hx + math.cos(ang) * rr, hy + math.sin(ang) * rr, 0.0)
    tx, ty = runner._antic_spot[0], runner._antic_spot[1]
    try:
        if math.hypot(tx - runner.x, ty - runner.y) > 10.0:
            runner._step_toward(tx, ty, dt, 1.25)
        chaser._step_toward(runner.x, runner.y, dt, 1.32)
        chaser.facing = ((runner.x - chaser.x) / max(1e-3, math.hypot(runner.x - chaser.x, runner.y - chaser.y)),
                         (runner.y - chaser.y) / max(1e-3, math.hypot(runner.x - chaser.x, runner.y - chaser.y)))
    except Exception:
        pass


def tick(g, dt):
    now = float(getattr(g, "now", 0.0))
    state = getattr(g, "_antic", None)
    if state is not None:
        if now >= float(state.get("until", 0.0)):
            _stop(g)
            return
        if state["kind"] == "dance":
            _tick_dance(g, state, dt, now)
        else:
            _tick_chase(g, state, dt, now)
        return
    nxt = float(getattr(g, "_antic_next", 0.0))
    if nxt <= 0.0:
        # Stagger the first activity: the camp already has enough going on at
        # the first frame.
        g._antic_next = now + random.uniform(*FIRST_DELAY)
        return
    if now < nxt:
        return
    if not _start(g, now):
        g._antic_next = now + random.uniform(*NEXT_DELAY)
    else:
        g._antic_next = now + random.uniform(*NEXT_DELAY)
