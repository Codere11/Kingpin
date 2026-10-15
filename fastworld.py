"""fastworld.py -- run the real world for DAYS in MINUTES.

WHY THIS EXISTS. The sim draws frames. A frame is capped at 0.05 s of game
time (main's own `min(clock.tick(FPS) / 1000.0, 0.05)`), so at fifty frames a
second the sim cannot beat 2.5x real time -- a game day every four minutes,
thirty days in two hours. Nothing about the ECONOMY needs a frame drawn.

So this does what the sim does, minus the drawing:

    while days < wanted:
        now += DT
        phase = day_phase(now)              # the same rule main uses
        for town in towns:   town.update(DT, world, now, phase)
        for man in PEOPLE:   man.tick(DT, world, now, phase, ...)
        if now - last_house >= 1.0: for h in HOUSES: h.tick(1.0)

DT is a whole second and the economy is minute-grained, so a second is a fine
step. Thirty days is 18,000 turns. It reports each dawn and stops.

It does NOT replace the sim: the sim is how the game is watched, and this is
how the economy is measured. Anything found here gets confirmed in the sim.
"""

import math
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pygame

_sm = pygame.display.set_mode
pygame.display.set_mode = lambda *a, **k: _sm((64, 48), 0)
pygame.mouse.get_pos = lambda: (32, 24)
pygame.mouse.get_pressed = lambda: (0, 0, 0)


class _K:
    def __init__(self, d):
        self.d = d

    def __getitem__(self, k):
        return k in self.d


pygame.key.get_pressed = lambda: _K(set())

import menu
import persist
import main
import village as V
import economy as E
import industry
import wildcrop

main.WIDTH = 64
main.HEIGHT = 48
menu.run = lambda screen, clock: (0, False)

pygame.init()
screen = pygame.display.set_mode((64, 48))
clock = pygame.time.Clock()

WANT_DAYS = float(os.environ.get("DAYS", "30"))
DT = float(os.environ.get("DT", "1.0"))

t0 = time.time()
_save = persist.read()
world = main.World(seed=int(_save.get("seed", 20240501)))
ground = main.GroundRenderer(world)
world.ground = ground
try:
    ground.scatter = main.Scatter(world.seed, world)
except Exception:
    pass
villages = main.Villages(world.seed)
trees = main.Trees(world.seed)
world.trees = trees
main.set_forest(trees)
_cached = main.load_cached_world(world.seed)
if _cached is not None:
    villages = _cached
    ground.villages_v = villages
else:
    main.load_world(screen, clock, villages, world)
    main.set_world_population(villages)
V.rebuild_people(villages)
V.rebuild_houses(villages)
wildcrop.set_world(world)
print("world up in %.1f s: %d towns, %d people   DT=%.1f  DAYS=%.1f"
      % (time.time() - t0, len(villages.villages), len(V.PEOPLE), DT, WANT_DAYS),
      flush=True)


def day_phase(t: float) -> str:
    """The same rule main.day_phase() uses -- and the same night_factor.

    My first version guessed the night as a cosine and got the PHASE WRONG:
    it never returned "work" at the right hours, nobody farmed, and the whole
    world starved to death in six days -- 1031 down to 125. main's own
    formula has a 0.30 offset in it that a guess does not reproduce.
    """
    tt = (0.30 + t / E.DAY_LENGTH) % 1.0
    brightness = 0.5 + 0.5 * math.sin(2.0 * math.pi * (tt - 0.25))
    night = 1.0 - brightness
    if night > 0.38:
        return "sleep"
    x = (0.30 + t / E.DAY_LENGTH) % 1.0
    if x < 0.30 or x >= 0.72:
        return "home"
    if 0.40 <= x < 0.60:
        return "market"
    return "work"


def census(day):
    alive = [n for n in V.PEOPLE if getattr(n, "alive", False)]
    def armed(who, t):
        return sum(1 for n in who if n.stock.get(t, 0) > 0)
    fn = [n for n in alive if getattr(n, "farm_plot", None) is not None]
    lg = [n for n in alive if getattr(n, "job", None) == "logger"]
    mi = [n for n in alive if (getattr(n, "job", None) == "mine"
          or getattr(getattr(n, "workplace", None), "kind", None) == "mine")]
    sm = [n for n in alive if getattr(n, "job", None) == "smith"]
    worn = sum(1 for n in alive if getattr(n, "tool_uses", 0)
               and getattr(n, "tool_uses", 0) <= E.TOOL_WORN)
    shelf = {}
    led = 0.0
    for v in villages.villages:
        led += float(v.ledger_coins)
        for t in ("shovel", "axe", "pickaxe", "rifle", "ammo"):
            q = v.ledger_goods.get(t, 0)
            if q:
                shelf[t] = shelf.get(t, 0) + q
    purses = sum(float(getattr(n, "coins", 0.0)) for n in alive)
    food = sum(E.food_of(n) for n in alive)
    store_food = 0.0
    for v in villages.villages:
        for k in E.FOOD:
            store_food += v.ledger_goods.get(k, 0)
    hungry = sum(1 for n in alive if getattr(n, "hunger", 0.0) >= E.DOLE_AT)
    starving = sum(1 for n in alive if getattr(n, "hunger", 0.0) >= E.STARVE_AT)
    print("day %-4d pop %4d  ledgers %8.0f  purses %8.0f\n"
          "        farmers %3d armed %3d   loggers %3d armed %3d"
          "   miners %3d armed %3d   smiths %3d\n"
          "        tools worn %3d   town shelves %s"
          % (day, len(alive), led, purses,
             len(fn), armed(fn, "shovel"), len(lg), armed(lg, "axe"),
             len(mi), armed(mi, "pickaxe"), len(sm), worn, shelf or "NONE"),
          flush=True)
    print("        FOOD larders %7.0f  granary/goods %7.0f  = %6.0f total (%.1f a head)"
          "   hunger>=85: %5d   hunger>=100: %5d"
          % (food, store_food, food + store_food,
             (food + store_food) / max(1, len(alive)), hungry, starving), flush=True)


now = float(getattr(villages.villages[0], "_day", 0.0)) * E.DAY_LENGTH
last_house = now
day_seen = int(now / E.DAY_LENGTH)
print("starting at day %.2f" % (now / E.DAY_LENGTH), flush=True)

t1 = time.time()
steps = 0
while now / E.DAY_LENGTH < WANT_DAYS:
    now += DT
    steps += 1
    phase = day_phase(now)
    night = phase == "sleep"

    for v in villages.villages:
        try:
            v.update(DT, world, now, phase)
        except Exception:
            pass
    for n in list(V.PEOPLE):
        if not getattr(n, "alive", False):
            continue
        try:
            n.tick(DT, world, now, phase, None, night, (), None)
        except Exception:
            pass
    if now - last_house >= 1.0:
        last_house = now
        for h in list(V.HOUSES):
            try:
                h.tick(1.0)
            except Exception:
                pass

    d = int(now / E.DAY_LENGTH)
    if d != day_seen:
        day_seen = d
        census(d)
        el = time.time() - t1
        print("        (%.1f game days in %.0f s = %.0f game-s a second, %d steps)"
              % (d, el, now / max(el, 1e-9), steps), flush=True)

print("\n=== DONE: %.1f game days in %.0f real seconds (%.0f steps) ==="
      % (now / E.DAY_LENGTH, time.time() - t1, steps), flush=True)
print("=== deaths ===", flush=True)
