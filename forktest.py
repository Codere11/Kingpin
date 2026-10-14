"""Does the fork actually work, and is the child's world its own?

THE BET THE WHOLE DESIGN RESTS ON: build the world once in the main process,
then fork -- and each worker wakes up already holding the entire world, for the
price of a few milliseconds, with copy-on-write pages.

THE RISK: this process is THREADED by the time the world exists. pygame.init()
starts SDL's threads and GroundRenderer starts a terrain worker, both BEFORE the
first village is built. fork() gives the child only the calling thread; any lock
those vanished threads held stays locked for ever. So the bet is only good if a
worker never touches SDL or the terrain.

So this measures three things and nothing else:

  1. does the fork survive at all, in a threaded, world-holding process?
  2. is the child's copy PRIVATE -- does the parent see nothing it did?
  3. what does the fork actually cost?

Run: /tmp/kingpin-venv/bin/python forktest.py
"""

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
pygame.display.set_mode = lambda *a, **k: _sm((160, 120), 0)
pygame.mouse.get_pos = lambda: (80, 60)

import menu
import persist
import main

main.WIDTH = 160
main.HEIGHT = 120
menu.run = lambda screen, clock: (0, False)

print("building the world the way main() does ...", flush=True)
t0 = time.time()
pygame.init()
screen = pygame.display.set_mode((160, 120))
clock = pygame.time.Clock()

_save = persist.read()
world = main.World(seed=int(_save.get("seed", 20240501)))
ground = main.GroundRenderer(world)
world.ground = ground
scatter = main.Scatter(world.seed, world)
ground.scatter = scatter
static_layer = main.StaticLayer(ground, scatter)
villages = main.Villages(world.seed)
ground.villages_v = villages
trees = main.Trees(world.seed)
world.trees = trees
main.set_forest(trees)

_cached = main.load_cached_world(world.seed)
if _cached is not None:
    villages = _cached
    ground.villages_v = villages
    main.village_mod.rebuild_people(villages)
    main.village_mod.rebuild_houses(villages)
else:
    main.load_world(screen, clock, villages, world)
    main.save_cached_world(villages, world.seed)
    main.village_mod.rebuild_people(villages)
    main.village_mod.rebuild_houses(villages)

print("world up in %.1f s: %d towns, %d people"
      % (time.time() - t0, len(villages.villages),
         sum(len(v.npcs) for v in villages.villages)), flush=True)

# ---- the town we will hand to the child ----------------------------------
town = None
for v in villages.villages:
    if len(getattr(v, "npcs", ())) >= 8:
        town = v
        break
if town is None:
    print("no town with people; cannot test"); raise SystemExit(1)


def look(v):
    return (round(float(getattr(v, "_day", -1.0)), 4),
            sum(1 for n in v.npcs if getattr(n, "alive", False)),
            round(float(getattr(v, "granary", -1.0)), 2),
            round(float(getattr(v, "ledger_coins", -1.0)), 2))


before = look(town)
print("\ntown under test: %s  day %.3f  alive %d  granary %.1f  ledger %.1f"
      % (town.name, before[0], before[1], before[2], before[3]), flush=True)

# ---- FORK ----------------------------------------------------------------
threads_here = 0
try:
    import threading
    threads_here = threading.active_count()
except Exception:
    pass
print("threads alive at fork time: %d   (SDL + the terrain worker)"
      % threads_here, flush=True)

t_fork = time.time()
pid = os.fork()
fork_ms = (time.time() - t_fork) * 1000.0

if pid == 0:
    # ---------------------------- THE CHILD -------------------------------
    try:
        phase = "home"          # day_phase() is local to main(); "home" is the default
        now = float(getattr(town, "_day", 0.0)) * 600.0
        for i in range(120):
            now += 1.0
            town.update(1.0, world, now, phase)
        after = look(town)
        os.write(1, ("CHILD  ticked 120 s offline -> day %.3f  alive %d"
                     "  granary %.1f  ledger %.1f\n"
                     % (after[0], after[1], after[2], after[3])).encode())
        os.write(1, b"CHILD  survived the fork in a threaded process: YES\n")
    except BaseException as e:
        os.write(1, ("CHILD  FAILED: %r\n" % (e,)).encode()[:400])
    os._exit(0)

# ---------------------------- THE PARENT ----------------------------------
_, status = os.waitpid(pid, 0)
time.sleep(0.2)
after = look(town)
print("PARENT unchanged?  %s" % ("YES" if after == before else "NO -- %r" % (after,)))
print("fork cost: %.1f ms" % fork_ms)
print("child exit status: %d" % status)
