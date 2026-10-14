"""whopays.py -- which PROFESSIONS actually take money in.

The question: the loggers got rich; do any of the other trades earn at all,
or is there exactly one living in this economy? Answered by snapshotting
every man's purse by his trade and looking at the DELTA.

A man's coins can rise by selling, by wages, by a mayor's salary, or by luck
in the market. This does not care which: it asks only whether the trade he
does puts coin in his pocket, and prints the top of the list every 60s so
there is no ten-minute wait for an answer.

Run: /tmp/kingpin-venv/bin/python whopays.py
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

main.WIDTH = 160
main.HEIGHT = 120
menu.run = lambda screen, clock: (0, False)

pygame.init()
screen = pygame.display.set_mode((160, 120))
clock = pygame.time.Clock()
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

# ---- hook the sale, so we can separate EARNING from RECEIVING ------------
EARN = {}
_orig_settle = E._settle


def _settle(village, item, price, qty, seller, buyer):
    if seller is not None:
        d = EARN.setdefault(getattr(seller, "job", None) or "idle",
                            [0, 0, 0])
        d[0] += 1                       # sales
        d[1] += int(price) * int(qty)   # coin taken
        d[2] += int(qty)                # units moved
    return _orig_settle(village, item, price, qty, seller, buyer)


E._settle = _settle


def purses():
    out = {}
    for n in V.PEOPLE:
        if not getattr(n, "alive", False):
            continue
        j = getattr(n, "job", None) or "idle"
        c, s = out.get(j, (0, 0.0))
        out[j] = (c + 1, s + float(getattr(n, "coins", 0.0)))
    return out


def report():
    t0 = time.time()
    p0 = purses()
    e0 = {}
    while True:
        time.sleep(60)
        el = time.time() - t0
        p1 = purses()
        print("\n+%4.0fs  ================ COIN BY TRADE ================" % el,
              flush=True)
        rows = []
        for j, (c1, s1) in p1.items():
            c0, s0 = p0.get(j, (c1, s1))
            rows.append((s1 - s0, j, c1, s1 / max(c1, 1)))
        rows.sort()
        for gain, j, c, avg in rows:
            print("   %-9s %4d men  purse %8.0f  (%6.1f each)   change %+8.0f"
                  % (j, c, p1[j][1], avg, gain), flush=True)
        print("   ---- where the SALES went (since start) ----", flush=True)
        for j, (n, coin, units) in sorted(EARN.items(),
                                          key=lambda kv: -kv[1][1]):
            print("   %-9s %5d sales  %8d coin  %7d units"
                  % (j, n, coin, units), flush=True)
        tot = sum(s for _, s in p1.values())
        print("   TOTAL in purses %8.0f" % tot, flush=True)
        # top five men alive
        top = sorted((n for n in V.PEOPLE if getattr(n, "alive", False)),
                     key=lambda n: -float(getattr(n, "coins", 0.0)))[:5]
        print("   RICHEST  " + "  ".join(
            "%s(%s)%d" % (getattr(n, "name", "?").split()[0],
                          getattr(n, "job", None) or "idle",
                          int(getattr(n, "coins", 0.0))) for n in top),
            flush=True)
        if el > 180:
            os._exit(0)


import threading

threading.Thread(target=report, daemon=True).start()

try:
    main.main()
except BaseException:
    import traceback
    traceback.print_exc()
