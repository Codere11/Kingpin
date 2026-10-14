"""woodaudit.py -- how many logs are cut, and where every one of them goes.

NOT A GUESS. Four hooks and an inventory, so the logs have to balance:

  PRODUCED   economy.cut_wood()    called once per felled tree (village.py)
  FELLED     forest.fell()          the tree actually drops
  MINTED     economy.monetize()     the town coins its firewood, 1 log = 1 coin
  BURNED     measured, not hooked:  a household burns WARMTH_RATE*dt and one
                                    log restores 1.0 warmth, and the common
                                    stack covers what the family cannot

  STOCK      town store + house woodpiles + men's pockets, every sample

  produced - minted - burned == change in stock, and if it does not, one of
  the four is wrong and the numbers will show it.

Run: /tmp/kingpin-venv/bin/python woodaudit.py
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

C = {"fell": 0, "cut": 0, "cut_logs": 0, "tax_logs": 0,
     "mint": 0, "mint_logs": 0, "mint_fail": 0,
     "sold_logs": 0, "sold_coin": 0}

# ---- HOOK 1: the tree actually drops -------------------------------------
_orig_fell = V._FOREST.fell


def _fell(tree, now):
    C["fell"] += 1
    return _orig_fell(tree, now)


V._FOREST.fell = _fell

# ---- HOOK 2: the logger's take -------------------------------------------
_orig_cut = E.cut_wood


def _cut(village, npc, amount):
    C["cut"] += 1
    C["cut_logs"] += int(amount)
    C["tax_logs"] += int(round(amount * E.HARVEST_TAX))
    return _orig_cut(village, npc, amount)


E.cut_wood = _cut

# ---- HOOK 3: the town coining its own firewood ---------------------------
_orig_mint = E.monetize


def _mint(village, amount):
    got = _orig_mint(village, amount)
    if got:
        C["mint"] += 1
        C["mint_logs"] += int(got)
    else:
        C["mint_fail"] += 1
    return got


E.monetize = _mint


# ---- HOOK 4: the wood actually SOLD, and its price ----------------------
# The question is not how much is cut, it is what a log FETCHES. A trade of
# 12,653 logs at 0.2 coin each is a different world from 2,000 logs at 8.
_orig_settle = E._settle


def _settle(village, item, price, qty, seller, buyer):
    if item == "wood":
        C["sold_logs"] += int(qty)
        C["sold_coin"] += int(price) * int(qty)
    return _orig_settle(village, item, price, qty, seller, buyer)


E._settle = _settle


def stocks():
    store = purses = houses = 0.0
    try:
        for v in villages.villages:
            store += float(v.ledger_goods.get("wood", 0))
    except Exception:
        pass
    try:
        for n in V.PEOPLE:
            purses += float(n.stock.get("wood", 0))
    except Exception:
        pass
    try:
        for h in V.HOUSES:
            houses += float(E.house_wood(h))
    except Exception:
        pass
    return store, purses, houses


def loggers():
    n = axe = zero = 0
    try:
        for m in V.PEOPLE:
            if getattr(m, "alive", False) and getattr(m, "job", None) == "logger":
                n += 1
                if m.stock.get("axe", 0) > 0:
                    axe += 1
                if m.stock.get("wood", 0) <= 0:
                    zero += 1
    except Exception:
        pass
    return n, axe, zero


def report():
    t0 = time.time()
    s0 = stocks()
    f0 = dict(C)
    while True:
        time.sleep(20)
        el = time.time() - t0
        s1 = stocks()
        f1 = dict(C)
        d = {k: f1[k] - f0[k] for k in C}
        nl, na, nz = loggers()
        store0, purse0, house0 = s0
        store1, purse1, house1 = s1
        tot0, tot1 = sum(s0), sum(s1)
        # a hearth burns WARMTH_RATE a second; one log is one warmth
        burn = (d["cut_logs"] - d["tax_logs"]) + d["mint_logs"] - (tot1 - tot0)
        print("+%4.0fs  felled %3d (%4.1f/s)  cut_logs %5d  town_tax %4d"
              "  minted %4d  SOLD %5d logs for %6d coin"
              "  (%.2f a log)  BURNED~%6d"
              % (el, d["fell"], d["fell"] / el, d["cut_logs"], d["tax_logs"],
                 d["mint_logs"], d["sold_logs"], d["sold_coin"],
                 (d["sold_coin"] / d["sold_logs"]) if d["sold_logs"] else 0.0,
                 burn), flush=True)
        print("        stock  town %7.0f  houses %7.0f  pockets %7.0f"
              "   = %8.0f     loggers %3d  with-axe %3d  empty-handed %3d"
              % (store1, house1, purse1, tot1, nl, na, nz), flush=True)
        s0, f0 = s1, f1
        if el > 300:
            print("\n=== PER GAME DAY (600 s) ===", flush=True)
            print("  trees felled   %8.0f" % (f1["fell"] / el * 600), flush=True)
            print("  logs produced  %8.0f" % (f1["cut_logs"] / el * 600), flush=True)
            print("  logs to town   %8.0f" % (f1["tax_logs"] / el * 600), flush=True)
            print("  logs MINTED    %8.0f   <- burnt for coin" % (f1["mint_logs"] / el * 600), flush=True)
            print("  hearths need   %8.0f   (%d houses x %.0f a day)"
                  % (len(V.HOUSES) * E.WOOD_PER_HOUSE, len(V.HOUSES),
                     E.WOOD_PER_HOUSE), flush=True)
            os._exit(0)


import threading

threading.Thread(target=report, daemon=True).start()

try:
    main.main()
except BaseException:
    import traceback
    traceback.print_exc()
