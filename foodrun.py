"""WHERE THE FOOD IS, AND WHERE IT GOES.

Two game days, sampled every fifth of a day. It does not instrument anything --
it READS the world's actual state, so it cannot change what it measures.

    granary   food sitting in the villages' common stores
    packs     food in living people's hands
    TOTAL     the whole world's food, at that instant

If TOTAL falls, food is being destroyed -- eaten. If TOTAL holds but granaries
are empty and packs are full, food exists and cannot move. If TOTAL is low from
the start, it was never produced. Those are three different bugs.
"""

import os
import sys
import time
import threading

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pygame
_sm = pygame.display.set_mode
pygame.display.set_mode = lambda *a, **k: _sm((128, 96), 0)

class _K:
    def __init__(self, d): self.d = d
    def __getitem__(self, k): return k in self.d

pygame.key.get_pressed = lambda: _K(set())
pygame.mouse.get_pos = lambda: (64, 48)
pygame.mouse.get_pressed = lambda: (0, 0, 0)

import village
import economy
import creatures
import main
import menu

OUT = os.path.join(HERE, "foodrun.log")


def snap():
    """Everything alive, and every food item anywhere in the world."""
    people = village.PEOPLE
    alive = [n for n in people if getattr(n, "alive", True)]
    packs = 0
    for n in alive:
        st = getattr(n, "stock", None)
        if not st:
            continue
        packs += sum(int(st.get(f, 0)) for f in economy.FOOD)
    gran = 0
    empty = 0
    seen = set()
    for n in alive:
        v = getattr(n, "village", None)
        if v is None or id(v) in seen:
            continue
        seen.add(id(v))
        g = sum(int(v.ledger_goods.get(f, 0)) for f in economy.FOOD)
        gran += g
        if g <= 0:
            empty += 1
    return len(alive), gran, packs, len(seen), empty


def keeper():
    while True:
        time.sleep(1.0)
        try:
            p = getattr(village, "PLAYER", None)
            if p is None:
                continue
            if getattr(p, "dead", False):
                p.respawn()
            p.god = True
            p.hunger = getattr(p, "max_hunger", 100.0)
            p.health = getattr(p, "max_health", 100)
        except Exception:
            pass


def reporter():
    log_start = None
    last_q = -1
    while True:
        time.sleep(6)
        try:
            now = float(getattr(creatures, "_NOW", 0.0))
        except Exception:
            now = 0.0
        if now <= 0.0:
            # the creatures clock never advances (set_time forgets `global`),
            # so fall back to the wall clock
            now = time.time() - T0[0]
        q = int(now / (600.0 * 0.2))          # a fifth of a game day
        if q == last_q:
            continue
        last_q = q
        tag = "day %.1f" % (now / 600.0)
        try:
            n, g, p, towns, empty = snap()
            with open(OUT, "a") as fh:
                fh.write("%-10s  alive %4d  granary %7d  packs %7d  TOTAL %7d"
                         "   (%4.1f a head)  towns %d, %d with an empty store\n"
                         % (tag, n, g, p, g + p,
                            (g + p) / max(1, n), towns, empty))
                fh.flush()
        except Exception as e:
            with open(OUT, "a") as fh:
                fh.write("SNAP ERROR %r\n" % (e,))


T0 = [time.time()]
threading.Thread(target=keeper, daemon=True).start()
open(OUT, "a").write("\n########## foodrun %s ##########\n"
                     % time.strftime("%Y-%m-%d %H:%M:%S"))
threading.Thread(target=reporter, daemon=True).start()
menu.run = lambda screen, clock: (0, False)
try:
    main.main()
except BaseException:
    import traceback
    with open(OUT, "a") as fh:
        fh.write("\nDIED\n" + traceback.format_exc()[-1500:] + "\n")
