"""events.py -- outside events for a settlement.

The first event is a wolf pack.  Wolves come in from ONE direction as a loose
group, with different spacing and different targets, so they do not look like
three copies walking in parallel or chewing on the same man.

The event director is deliberately simple and cheap: one timer per player camp,
one active wolf pack at a time, and wolves are moved by this module rather than
the generic enemy targeter (which only understands towns, not native camps).
"""

from __future__ import annotations

import math
import random

import creatures


PACK_SIZE = 3
PACK_SPAWN_DIST = 760.0
PACK_LIFETIME = 90.0
PACK_COOLDOWN = (150.0, 240.0)
PACK_FIRST_DELAY = (45.0, 90.0)


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
    # Rosters only.  `camp.people` can contain outsiders loaded around the
    # camp; the wolf pack must hunt the settlement it came for.
    return out


def _toast(g, text):
    try:
        g.toast(text)
    except Exception:
        pass


def _record(g, action, **fields):
    try:
        import playlog
        playlog.record(g, "event", action=action, **fields)
    except Exception:
        pass


class WolfPack:
    def __init__(self, g, camp, rng=None):
        self.g = g
        self.camp = camp
        self.age = 0.0
        self.done = False
        self.outcome = ""
        self.wolves = []
        self._log_t = 0.0
        rng = rng or random.Random(int(getattr(g, "now", 0.0) * 1000) ^ id(camp))
        # One approach direction.  The three start on a shallow diagonal, not
        # on a line, and each gets its own delay and target.
        angle = rng.uniform(0.0, 2.0 * math.pi)
        ux, uy = math.cos(angle), math.sin(angle)
        px, py = -uy, ux
        cx = float(getattr(camp, "x", getattr(g.player, "x", 0.0)))
        cy = float(getattr(camp, "y", getattr(g.player, "y", 0.0)))
        people = _people(camp)
        for i in range(PACK_SIZE):
            forward = PACK_SPAWN_DIST + rng.uniform(-35.0, 55.0) + i * 38.0
            side = (-1.0 if i == 0 else (1.0 if i == 1 else 0.0)) * rng.uniform(65.0, 105.0)
            x = cx + ux * forward + px * side
            y = cy + uy * forward + py * side
            w = creatures.Wolf(x, y)
            try:
                w.name = "wolf-%d" % (i + 1)
            except Exception:
                pass
            w.event_ai = True
            w.event_pack = self
            w.event_target = None
            w.event_delay = i * rng.uniform(0.25, 0.65)
            w.aware = True
            w.aware_timer = 600.0
            w.view_range = 1600.0
            w.view_angle = math.radians(300.0)
            w.facing = (-ux, -uy)
            w._event_rects = ()
            g.enemies.append(w)
            self.wolves.append(w)
        self.targets = list(people)
        self._assign_targets()
        _record(g, "wolves_arrive", camp=getattr(camp, "name", "camp"),
                count=len(self.wolves), x=round(cx, 1), y=round(cy, 1),
                targets=", ".join(getattr(w.event_target, "name", "-")
                                  for w in self.wolves))
        _toast(g, "Wolves are moving toward %s" % getattr(camp, "name", "the camp"))

    def _assign_targets(self):
        """Give each wolf a DIFFERENT living person when one is available."""
        used = set()
        live = [p for p in self.targets if getattr(p, "alive", True)]
        for w in self.wolves:
            t = getattr(w, "event_target", None)
            if t is not None and getattr(t, "alive", True):
                used.add(id(t))
        for w in self.wolves:
            if not getattr(w, "alive", True):
                continue
            t = getattr(w, "event_target", None)
            if t is not None and getattr(t, "alive", True):
                continue
            candidates = [p for p in live if id(p) not in used]
            if not candidates:
                # Only when every person is already taken: the player is the
                # natural second choice, never the same victim as a packmate.
                player = getattr(self.g, "player", None)
                if player is not None and getattr(player, "alive", True):
                    candidates = [player]
            if not candidates:
                w.event_target = None
                continue
            target = min(candidates,
                         key=lambda p: (p.x - w.x) ** 2 + (p.y - w.y) ** 2)
            w.event_target = target
            used.add(id(target))

    def tick(self, dt):
        if self.done:
            return
        self.age += dt
        self._log_t = float(getattr(self, "_log_t", 0.0)) - dt
        if self._log_t <= 0.0:
            self._log_t = 2.0
            for w in self.wolves:
                if not getattr(w, "alive", True):
                    continue
                t = getattr(w, "event_target", None)
                _record(self.g, "wolves_state", camp=getattr(self.camp, "name", "camp"),
                        wolf=getattr(w, "name", "wolf"),
                        target=getattr(t, "name", "-") if t is not None else "-",
                        x=round(float(getattr(w, "x", 0.0)), 1),
                        y=round(float(getattr(w, "y", 0.0)), 1),
                        dist=round(math.hypot(getattr(t, "x", w.x) - w.x,
                                              getattr(t, "y", w.y) - w.y), 1)
                        if t is not None else -1.0)
        alive = 0
        for w in self.wolves:
            if not getattr(w, "alive", True):
                continue
            alive += 1
            w.event_delay = max(0.0, float(getattr(w, "event_delay", 0.0)) - dt)
            if w.event_delay > 0.0:
                continue
            self._assign_targets()
            target = getattr(w, "event_target", None)
            if target is not None and not getattr(target, "alive", True):
                w.event_target = None
                target = None
            if target is not None:
                # Look at the person he chose; otherwise the wolf's view cone
                # can leave him wandering with a target assigned.
                dx, dy = target.x - w.x, target.y - w.y
                d = math.hypot(dx, dy) or 1.0
                w.facing = (dx / d, dy / d)
                w._rects = getattr(self.g, "colliders", ()) or ()
                w._fences = getattr(self.g, "visible_villages", ()) or ()
                w.update(dt, target, getattr(self.g, "combat", None),
                         occluders=None, speed_scale=1.0, view_scale=1.0,
                         visible=True, colliders=w._rects)
            else:
                w.update(dt, None, getattr(self.g, "combat", None),
                         visible=False, colliders=getattr(self.g, "colliders", ()) or ())
        if alive == 0:
            self.done = True
            self.outcome = "killed"
            _record(self.g, "wolves_end", camp=getattr(self.camp, "name", "camp"),
                    outcome="killed", seconds=round(self.age, 1))
            _toast(self.g, "The wolf pack is dead")
        elif self.age >= PACK_LIFETIME:
            self.done = True
            self.outcome = "withdrawn"
            for w in self.wolves:
                if getattr(w, "alive", True) and w in getattr(self.g, "enemies", ()):
                    try:
                        self.g.enemies.remove(w)
                    except ValueError:
                        pass
            _record(self.g, "wolves_end", camp=getattr(self.camp, "name", "camp"),
                    outcome="withdrawn", seconds=round(self.age, 1))
            _toast(self.g, "The wolves have had enough and withdraw")


class Director:
    def __init__(self, g):
        self.g = g
        self.packs = []
        self.timers = {}

    def tick(self, dt):
        for pack in list(self.packs):
            pack.tick(dt)
            if pack.done:
                self.packs.remove(pack)
        if getattr(self.g, "test_mode", False):
            return
        camps = list(getattr(self.g, "player_camps", ()) or ())
        for camp in camps:
            key = id(camp)
            if key not in self.timers:
                self.timers[key] = random.uniform(*PACK_FIRST_DELAY)
            self.timers[key] -= dt
            if self.timers[key] > 0.0:
                continue
            if any(p.camp is camp for p in self.packs):
                self.timers[key] = 15.0
                continue
            self.packs.append(WolfPack(self.g, camp))
            self.timers[key] = random.uniform(*PACK_COOLDOWN)

    def spawn_test(self):
        camp = getattr(self.g, "_npc_lab", None)
        if camp is None:
            camps = list(getattr(self.g, "native_settlements", {}).values())
            camp = min(camps, key=lambda c: (c.x - self.g.player.x) ** 2
                       + (c.y - self.g.player.y) ** 2) if camps else None
        if camp is None:
            _toast(self.g, "No settlement for the wolf test")
            return None
        pack = WolfPack(self.g, camp)
        self.packs.append(pack)
        return pack


def ensure(g):
    d = getattr(g, "_event_director", None)
    if d is None:
        d = Director(g)
        g._event_director = d
    return d


def tick(g, dt):
    ensure(g).tick(dt)


def spawn_test(g):
    return ensure(g).spawn_test()
