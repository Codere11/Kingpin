"""WHERE FOOD AND LOGS GO. Three game days, at 1x, sampled every 1/5 day.

Reads the world's real state -- it instruments nothing, so it cannot change
what it measures. Food and wood, in the granary and in packs, plus the
population, counted three ways so a discrepancy can be seen rather than
guessed at.
"""

import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)

import pygame
_sm = pygame.display.set_mode
pygame.display.set_mode = lambda *a, **k: _sm((128, 96), 0)
class _K:
    def __init__(self, d): self.d = d
    def __getitem__(self, k): return k in self.d
pygame.key.get_pressed = lambda: _K(set())
pygame.mouse.get_pos = lambda: (64, 48)
pygame.mouse.get_pressed = lambda: (0, 0, 0)

import village, economy, main, menu

OUT = os.path.join(HERE, "flow.log")
START = [time.time()]
DAY = 600.0


def keeper():
    while True:
        time.sleep(1)
        try:
            p = getattr(village, "PLAYER", None)
            if p is None: continue
            if getattr(p, "dead", False): p.respawn()
            p.god = True
            p.hunger = getattr(p, "max_hunger", 100.0)
            p.health = getattr(p, "max_health", 100)
        except Exception:
            pass


def sample():
    people = village.PEOPLE
    alive = [n for n in people if getattr(n, "alive", True)]
    f_pack = sum(int(n.stock.get(f, 0)) for n in alive for f in economy.FOOD)
    w_pack = sum(int(n.stock.get("wood", 0)) for n in alive)
    f_gran = w_gran = 0
    towns = 0
    onroll = 0
    empty = 0
    seen = set()
    for v in (getattr(n, "village", None) for n in alive):
        if v is None or id(v) in seen: continue
        seen.add(id(v)); towns += 1
        onroll += len(v.npcs)
        f = sum(int(v.ledger_goods.get(x, 0)) for x in economy.FOOD)
        w = int(v.ledger_goods.get("wood", 0))
        f_gran += f; w_gran += w
        if f <= 0: empty += 1
    road = len(getattr(village, "TRAVELLERS", ()) or ())
    return dict(alive=len(alive), roll=onroll, towns=towns, road=road, empty=empty,
                f_pack=f_pack, f_gran=f_gran, w_pack=w_pack, w_gran=w_gran)


def reporter():
    last = -1
    while True:
        time.sleep(6)
        elapsed = time.time() - START[0]
        day = elapsed / DAY
        q = int(day / 0.2)
        if q == last: continue
        last = q
        try:
            s = sample()
            with open(OUT, "a") as fh:
                fh.write(
                    "day %.1f  alive %4d (on roll %4d, %d towns, %d on the road)\n"
                    "          FOOD  granary %6d  packs %6d  TOTAL %6d  (%4.1f a head)  %d empty stores\n"
                    "          WOOD  granary %6d  packs %6d  TOTAL %6d\n"
                    % (day, s["alive"], s["roll"], s["towns"], s["road"],
                       s["f_gran"], s["f_pack"], s["f_gran"] + s["f_pack"],
                       (s["f_gran"] + s["f_pack"]) / max(1, s["alive"]), s["empty"],
                       s["w_gran"], s["w_pack"], s["w_gran"] + s["w_pack"]))
                fh.flush()
        except Exception as e:
            with open(OUT, "a") as fh:
                fh.write("SNAP ERROR %r\n" % (e,))


open(OUT, "a").write("\n########## flow %s ##########\n" % time.strftime("%H:%M:%S"))
threading.Thread(target=keeper, daemon=True).start()
threading.Thread(target=reporter, daemon=True).start()
menu.run = lambda screen, clock: (0, False)
try:
    main.main()
except BaseException:
    import traceback
    with open(OUT, "a") as fh:
        fh.write("\nDIED\n" + traceback.format_exc()[-1200:] + "\n")
