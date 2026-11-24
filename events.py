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

import pygame

import creatures
import village


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

    def _separate(self, w):
        """Keep the wolf bodily out of a man instead of standing inside him."""
        actors = list(self.targets)
        actors += list(getattr(self.g, "_native_people", ()) or ())
        player = getattr(self.g, "player", None)
        if player is not None:
            actors.append(player)
        actors += self.wolves
        for other in actors:
            if other is w or not getattr(other, "alive", True):
                continue
            dx = w.x - other.x
            dy = w.y - other.y
            d = math.hypot(dx, dy)
            if d < 0.01:
                dx, dy, d = 1.0, 0.0, 1.0
            gap = float(getattr(w, "radius", 11)) + float(getattr(other, "radius", 12)) + 5.0
            if d < gap:
                push = (gap - d)
                w.x += dx / d * push
                w.y += dy / d * push

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
                # Event wolves run at a deliberate lope, not the wild-wolf
                # sprint; the camp should read as a scene, not a fast-forward.
                w.update(dt, target, getattr(self.g, "combat", None),
                         occluders=None, speed_scale=0.62, view_scale=1.0,
                         visible=True, colliders=w._rects)
                self._separate(w)
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


class RogueRaider:
    """ONE armed stranger, not from any settlement, coming for the camp."""

    def __init__(self, g, camp, rng=None):
        self.g = g
        self.camp = camp
        self.age = 0.0
        self.done = False
        rng = rng or random.Random(int(getattr(g, "now", 0.0) * 991) ^ id(camp))
        ang = rng.uniform(0.0, 2.0 * math.pi)
        x = float(camp.x) + math.cos(ang) * 850.0
        y = float(camp.y) + math.sin(ang) * 850.0
        # A NATIVE WARRIOR, not a Soldier: same body, axe, reach and melee
        # dance as the men who defend a settlement.  No rifle, no pennant.
        w = village.NPC(x, y, rng.randint(1, 2 ** 31 - 1),
                        name="rogue warrior", npc_id="rogue_event",
                        role="Warrior")
        w.native = True
        w.native_role = "warrior"
        w.job = "warrior"
        w.weapon = "axe"
        w.team = ("rogue", None)
        w.native_camp = camp
        w.home = (x, y)
        w.speed = 72.0
        w.base_speed = 72.0
        w.event_ai = True
        w.hostile = True
        w.aware = True
        w.aware_timer = 600.0
        w.view_range = 900.0
        w.facing = (-math.cos(ang), -math.sin(ang))
        g.enemies.append(w)
        self.raider = w
        self.targets = _people(camp)
        self.target = None
        _record(g, "rogue_arrive", camp=getattr(camp, "name", "camp"),
                x=round(x, 1), y=round(y, 1))
        _toast(g, "A rogue warrior is coming toward %s" % getattr(camp, "name", "the camp"))

    def tick(self, dt):
        if self.done:
            return
        self.age += dt
        w = self.raider
        if not getattr(w, "alive", True):
            self.done = True
            _record(self.g, "rogue_end", camp=getattr(self.camp, "name", "camp"),
                    outcome="killed")
            _toast(self.g, "The rogue warrior is dead")
            return
        target = getattr(self, "target", None)
        if target is None or not getattr(target, "alive", True):
            live = [p for p in self.targets if getattr(p, "alive", True)]
            player = getattr(self.g, "player", None)
            if player is not None and getattr(player, "alive", True):
                live = live + [player]
            target = (min(live, key=lambda p: (p.x - w.x) ** 2
                          + (p.y - w.y) ** 2) if live else None)
            self.target = target
        if target is None:
            self.done = True
            return
        # MELEE LIKE A MAN, NOT THE SOLDIER'S FULL TARGETING LOOP.  The old
        # update re-decided the nearest target every tick, so he flipped
        # between two people and looked like he was vibrating.
        w._rects = getattr(self.g, "colliders", ()) or ()
        w._fight(dt, target, getattr(self.g, "combat", None), 0.72, True)
        if self.age > 90.0:
            self.done = True
            _record(self.g, "rogue_end", camp=getattr(self.camp, "name", "camp"),
                    outcome="withdrawn")


class BuffaloHerd:
    """A herd crossing the settlement's fields."""

    def __init__(self, g, camp, rng=None):
        self.g = g
        self.camp = camp
        self.age = 0.0
        self.done = False
        self.animals = []
        rng = rng or random.Random(int(getattr(g, "now", 0.0) * 977) ^ id(camp))
        ang = rng.uniform(0.0, 2.0 * math.pi)
        for i in range(4):
            x = float(camp.x) + math.cos(ang) * (700.0 + i * 40.0)
            y = float(camp.y) + math.sin(ang) * (700.0 + i * 40.0)
            b = creatures.Bison(x, y)
            b.name = "buffalo"
            b.event_ai = True
            b.home = (float(camp.x) + rng.uniform(-260.0, 260.0),
                      float(camp.y) + rng.uniform(-260.0, 260.0))
            g.enemies.append(b)
            self.animals.append(b)
        _record(g, "buffalo_arrive", camp=getattr(camp, "name", "camp"),
                count=len(self.animals))
        _toast(g, "A buffalo herd is grazing toward %s" % getattr(camp, "name", "the camp"))

    def tick(self, dt):
        if self.done:
            return
        self.age += dt
        alive = 0
        for b in self.animals:
            if not getattr(b, "alive", True):
                continue
            alive += 1
            b.update(dt, None, getattr(self.g, "combat", None),
                     colliders=getattr(self.g, "colliders", ()) or ())
        if alive == 0 or self.age > 90.0:
            self.done = True
            _record(self.g, "buffalo_end", camp=getattr(self.camp, "name", "camp"),
                    outcome=("killed" if alive == 0 else "moved_on"))


class HorseVisit:
    """A few horses choose the settlement and stay."""

    def __init__(self, g, camp, rng=None):
        self.g = g
        self.camp = camp
        self.done = True
        rng = rng or random.Random(int(getattr(g, "now", 0.0) * 953) ^ id(camp))
        player = getattr(g, "player", None)
        dx = float(camp.x) - float(getattr(player, "x", camp.x))
        dy = float(camp.y) - float(getattr(player, "y", camp.y))
        base = math.atan2(dy, dx) if (abs(dx) + abs(dy) > 1.0) else rng.uniform(0.0, 2.0 * math.pi)
        for i in range(2):
            # Start well away from the player and walk in toward the camp.
            ang = base + (i - 0.5) * 0.22
            x = float(camp.x) + math.cos(ang) * 900.0
            y = float(camp.y) + math.sin(ang) * 900.0
            h = creatures.Horse(x, y, rng.choice(("brown", "black", "white", "palomino")))
            h.tamed = True
            h.conquered = True
            h.g = g
            h.home = (float(camp.x) + (i - 0.5) * 45.0,
                      float(camp.y) + 35.0)
            h.target = h.home
            g.horses.append(h)
        _record(g, "horses_join", camp=getattr(camp, "name", "camp"), count=2)
        _toast(g, "Horses have joined %s" % getattr(camp, "name", "the camp"))

    def tick(self, dt):
        pass


class RainEvent:
    """A short rain; the crops get the water and people get wet."""

    def __init__(self, g, camp, seconds=90.0):
        self.g = g
        self.camp = camp
        self.seconds = float(seconds)
        self.age = 0.0
        self.done = False
        g._rain_t = max(float(getattr(g, "_rain_t", 0.0)), self.seconds)
        _record(g, "rain_start", camp=getattr(camp, "name", "camp"), seconds=int(seconds))
        _toast(g, "Rain is falling over %s" % getattr(camp, "name", "the camp"))

    def tick(self, dt):
        if self.done:
            return
        self.age += dt
        if self.age >= self.seconds:
            self.done = True
            _record(self.g, "rain_end", camp=getattr(self.camp, "name", "camp"))


class BlightEvent:
    """Blight lives on the plants themselves and spreads to nearby crops."""

    def __init__(self, g, camp):
        self.g = g
        self.camp = camp
        self.age = 0.0
        self.spread_t = 0.0
        self.done = False
        self.tiles = []
        groups = list((getattr(camp, "farm_tiles", {}) or {}).values())
        tiles = [t for group in groups for t in (group or ())]
        if not tiles:
            self.done = True
            return
        tx, ty, _kind = random.choice(tiles)
        self._infect(int(tx), int(ty))
        _record(g, "blight", camp=getattr(camp, "name", "camp"),
                tx=int(tx), ty=int(ty))
        _toast(g, "Blight has started in %s" % getattr(camp, "name", "the camp"))

    def _infect(self, tx, ty):
        try:
            plot = self.g.world.plot_at(tx, ty)
            if plot is None or getattr(plot, "planted_at", None) is None:
                return False
            if getattr(plot, "blight", False):
                return False
            plot.blight = True
            self.tiles.append((tx, ty))
            try:
                self.g.ground.invalidate_tile(tx, ty, immediate=True)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def tick(self, dt):
        if self.done:
            return
        self.age += dt
        self.spread_t -= dt
        if self.spread_t > 0.0:
            return
        self.spread_t = 12.0
        # Find an uninfected crop within two tiles of an infected tile.
        groups = list((getattr(self.camp, "farm_tiles", {}) or {}).values())
        candidates = []
        for group in groups:
            for t in (group or ()):
                try:
                    tx, ty = int(t[0]), int(t[1])
                except Exception:
                    continue
                if any(abs(tx - x) <= 2 and abs(ty - y) <= 2
                       for x, y in self.tiles):
                    plot = self.g.world.plot_at(tx, ty)
                    if (plot is not None and getattr(plot, "planted_at", None) is not None
                            and not getattr(plot, "blight", False)):
                        candidates.append((tx, ty))
        if candidates:
            tx, ty = random.choice(candidates)
            if self._infect(tx, ty):
                _record(self.g, "blight_spread", camp=getattr(self.camp, "name", "camp"),
                        tx=tx, ty=ty)
        if self.age >= 150.0:
            self.done = True


class Director:
    """Condition-driven outside events.

    There is no fixed spawn clock. Every few seconds the director looks at
    what a camp actually has -- people, crops, animals, open ground, weather
    and recent history -- and only starts an event when its conditions are
    present. The cooldown is a guard against spam, not a schedule.
    """

    def __init__(self, g):
        self.g = g
        self.events = []
        self.eval_t = 4.0
        self.last = {}
        self.rng = random.Random(int(getattr(g, "now", 0.0) * 41) ^ id(g))

    def _available(self, kind, cooldown=90.0):
        return self.g.now - float(self.last.get(kind, -1e9)) >= cooldown

    def _active(self, camp):
        return any(getattr(e, "camp", None) is camp for e in self.events)

    def _spawn_best(self, camp):
        people = _people(camp)
        if not people:
            return
        farmers = len(getattr(camp, "farmers", ()) or ())
        animals = len([a for a in (getattr(camp, "animals", ()) or ())
                       if getattr(a, "alive", True)])
        plots = len(getattr(camp, "farm_plots", ()) or ())
        score = {}
        if self._available("wolves"):
            # More likely when the camp has people and some wilderness left.
            score["wolves"] = 2.0 + min(3.0, len(people) / 4.0)
        if self._available("rogue"):
            score["rogue"] = 1.5 + min(2.0, len(people) / 6.0)
        if plots and self._available("blight"):
            score["blight"] = 2.0 + min(2.0, plots / 4.0)
        if plots and self._available("buffalo"):
            score["buffalo"] = 1.5 + min(2.0, plots / 4.0)
        if self._available("horses", 150.0):
            score["horses"] = 1.0 + (0.8 if animals else 0.0)
        if self._available("rain", 180.0):
            score["rain"] = 1.5 + (1.0 if plots else 0.0)
        if not score:
            return
        # A little chance, so a rich camp does not get the same event every
        # time; conditions still set the weights.
        total = sum(score.values())
        roll = self.rng.uniform(0.0, total)
        choice = None
        for kind, weight in score.items():
            roll -= weight
            if roll <= 0.0:
                choice = kind
                break
        choice = choice or max(score, key=score.get)
        if choice == "wolves":
            self.events.append(WolfPack(self.g, camp, self.rng))
        elif choice == "rogue":
            self.events.append(RogueRaider(self.g, camp, self.rng))
        elif choice == "buffalo":
            self.events.append(BuffaloHerd(self.g, camp, self.rng))
        elif choice == "blight":
            self.events.append(BlightEvent(self.g, camp))
        elif choice == "horses":
            self.events.append(HorseVisit(self.g, camp, self.rng))
        elif choice == "rain":
            self.events.append(RainEvent(self.g, camp, self.rng.uniform(60.0, 120.0)))
        self.last[choice] = float(self.g.now)

    def tick(self, dt):
        for event in list(self.events):
            try:
                event.tick(dt)
            except Exception:
                event.done = True
            if getattr(event, "done", False):
                self.events.remove(event)
        self.g._rain_t = max(0.0, float(getattr(self.g, "_rain_t", 0.0)) - dt)
        if getattr(self.g, "test_mode", False):
            return
        self.eval_t -= dt
        if self.eval_t > 0.0:
            return
        self.eval_t = 8.0
        for camp in list(getattr(self.g, "player_camps", ()) or ()):
            if not self._active(camp):
                self._spawn_best(camp)

    def spawn_test(self):
        camp = getattr(self.g, "_npc_lab", None)
        if camp is None:
            camps = list(getattr(self.g, "native_settlements", {}).values())
            camp = min(camps, key=lambda c: (c.x - self.g.player.x) ** 2
                       + (c.y - self.g.player.y) ** 2) if camps else None
        if camp is None:
            _toast(self.g, "No settlement for the wolf test")
            return None
        pack = WolfPack(self.g, camp, self.rng)
        self.events.append(pack)
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


_TEST_KINDS = ("wolves", "rogue", "buffalo", "blight", "horses", "rain")


def spawn_test_kind(g, kind):
    """F3 test hook: start one named event in the lab, without waiting."""
    d = ensure(g)
    camp = getattr(g, "_npc_lab", None)
    if camp is None:
        camps = list(getattr(g, "native_settlements", {}).values())
        camp = min(camps, key=lambda c: (c.x - g.player.x) ** 2
                   + (c.y - g.player.y) ** 2) if camps else None
    if camp is None:
        _toast(g, "No settlement for event test")
        return None
    if kind == "wolves":
        event = WolfPack(g, camp, d.rng)
    elif kind == "rogue":
        event = RogueRaider(g, camp, d.rng)
    elif kind == "buffalo":
        event = BuffaloHerd(g, camp, d.rng)
    elif kind == "blight":
        event = BlightEvent(g, camp)
    elif kind == "horses":
        event = HorseVisit(g, camp, d.rng)
    elif kind == "rain":
        event = RainEvent(g, camp, 75.0)
    else:
        return None
    d.events.append(event)
    return event


def cycle_test(g):
    d = ensure(g)
    idx = int(getattr(g, "_event_test_idx", -1)) + 1
    g._event_test_idx = idx
    kind = _TEST_KINDS[idx % len(_TEST_KINDS)]
    _toast(g, "Event test: %s" % kind)
    return spawn_test_kind(g, kind)


def draw(g, screen):
    """Light rain streaks while a RainEvent is active."""
    if float(getattr(g, "_rain_t", 0.0)) <= 0.0:
        return
    w, h = screen.get_size()
    ticks = pygame.time.get_ticks() * 0.35
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(160):
        x = int((i * 97 + ticks * (0.8 + (i % 5) * 0.12)) % (w + 80)) - 40
        y = int((i * 61 + ticks * 2.2) % (h + 80)) - 40
        pygame.draw.line(layer, (105, 165, 235, 155), (x, y), (x, y + 24), 2)
    screen.blit(layer, (0, 0))
