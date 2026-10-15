"""THE SIMPLE ONE.

Runs the real game at 1x with nobody at the keyboard and writes ONE line per
in-game day:

    day 12   population 1041   nemesis  coin 180  job smith  farming 4.65  axe 0.31  movement 1.00  shooting 0.00

Nothing else. No clues, no deaths, no grudges, no theory.

Five rules it keeps, because breaking each of them cost an evening:

  1.  THE DAY COMES FROM THE GAME, AND FROM THE MOST ADVANCED CLOCK IN IT.
      Village._day is filled by Village.update, but not every village is ticked
      every frame -- some hold a clock stopped at 0.002 while the world runs
      on. Taking the first one found reported the world crawling at 0.06x when
      it was running at 0.96x. The MAX is the world's real time.

  2.  ONE LINE PER DAY, ONCE. The day number is remembered and compared; a
      frame that arrives twice in the same day writes nothing.

  3.  NOTHING IS WRITTEN UNTIL THE WORLD IS UP. Recording begins only once the
      player exists and the clock has started moving, so the build never lands
      in the log -- and a day is only reported once the world is fully built.

  4.  IT ONLY EVER TOUCHES THE PLAYER. main advances the world clock inside two
      branches and BOTH are guarded by `not game_over`, so an idle player who
      starves freezes the world with one day in the log. The keeper feeds him
      and makes him invulnerable. Nobody else is written to, ever.

  5.  SIXTY FRAMES A SECOND OR MORE, so the dt ceiling (50 ms) never bites and
      the world clock tracks real time. The window is small and the canvas is
      small: the game composes WIDTH x HEIGHT every frame regardless of the
      display, so it is the CANVAS that has to come down.

    python sim.py            # runs until you kill it
    tail -f sim.log          # one line per day
    tail -f sim.fps          # the frame rate, every 30 seconds
"""

import os
import sys
import time
import threading

# THE GPU, NOT THE CPU. `SDL_VIDEODRIVER=dummy` renders every pixel in
# software on the CPU -- 921,600 of them a frame at 1280x720, which is about
# two frames a second. Every timing I took tonight was taken through that, and
# it is why "the world is too big" looked true. This machine has a working
# Intel GPU on DISPLAY=:0; the real driver is used and a small window appears
# (which is also the only way to see that it is running).
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")   # audio is not needed
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pygame

_sm = pygame.display.set_mode
pygame.display.set_mode = lambda *a, **k: _sm((160, 120), 0)


class _K:
    def __init__(self, d):
        self.d = d

    def __getitem__(self, k):
        return k in self.d


pygame.key.get_pressed = lambda: _K(set())
pygame.mouse.get_pos = lambda: (120, 90)
pygame.mouse.get_pressed = lambda: (0, 0, 0)

FRAMES = [0]
_flip = pygame.display.flip


def _count():
    FRAMES[0] += 1
    _flip()


pygame.display.flip = _count

import village
import economy
E2_TOOL_WORN = 30
import nemesis
import main
import menu

# ---- THE FAST CLOCK, IF ASKED FOR ----------------------------------------
# main() computes `dt = min(clock.tick(FPS) / 1000.0, 0.05)` and then caps it
# again after the time scale. So the world's own speed limit is 0.05 s of game
# per FRAME, whatever the clock says. Lie to it and the world runs at that cap:
# at fifty frames a second it is eighteen times real time, one game day every
# thirty seconds, and thirty days in a quarter of an hour instead of five
# hours. The loop still runs frame by frame, so nothing is integrated any
# coarser than 0.05 s -- the same step the game itself allows.
if os.environ.get("KINGPIN_FAST"):
    # pygame.time.Clock is a C type and its `tick` cannot be assigned, so the
    # clock is PROXIED instead: main() builds pygame.time.Clock() and gets this,
    # every other attribute is passed straight through, and `tick` paces the
    # loop exactly as before while reporting 50 ms -- which is main's own cap.
    _RealClock = pygame.time.Clock

    class _FastClock:
        def __init__(self, *a, **k):
            self._c = _RealClock(*a, **k)

        def __getattr__(self, name):
            return getattr(self._c, name)

        def tick(self, *a, **k):
            self._c.tick(*a, **k)          # still pace the loop
            return 50                      # ...and report main's own dt cap

    pygame.time.Clock = _FastClock

# THE CANVAS, NOT THE WINDOW, IS WHAT COSTS. The game composes WIDTH x HEIGHT
# every frame and blits it onto the display; a small display over a big canvas
# still paints every one of those pixels, in software, on the CPU.
main.WIDTH = 160
main.HEIGHT = 120

LOG = os.path.join(HERE, "sim.log")
FPSLOG = os.path.join(HERE, "sim.fps")
START = time.time()


def day_now():
    """THE MOST ADVANCED CLOCK IN THE WORLD -- see rule 1."""
    best = -1.0
    for n in village.PEOPLE:
        v = getattr(n, "village", None)
        if v is not None:
            d = float(getattr(v, "_day", -1.0))
            if d > best:
                best = d
    return best


def population():
    return sum(1 for n in village.PEOPLE if getattr(n, "alive", True))


PIN = [None]


def keeper():
    """Rule 4: the player only -- and he is PINNED WHERE HE STANDS.

    A wolf takes the idle player and drags him across the field. The camera
    follows him, every ground chunk it crosses has to be regenerated -- 256x256
    of terrain noise each -- and the frame rate halves: it went 45 -> 19-28 the
    moment a wolf got hold of him. God mode stops him being bitten; it does not
    stop him being CARRIED.

    He is not part of this simulation. He is a camera that happens to have a
    body, so the body is put back where it started every second and the view
    never moves.
    """
    while True:
        time.sleep(0.5)
        try:
            p = getattr(village, "PLAYER", None)
            if p is None:
                continue
            if PIN[0] is None:
                PIN[0] = (p.x, p.y)
            p.x, p.y = PIN[0]
            if getattr(p, "dead", False):
                p.respawn()
            p.god = True
            p.hunger = getattr(p, "max_hunger", 100.0)
            p.health = getattr(p, "max_health", 100)
        except Exception:
            pass


def fps_watch():
    """Rule 5: prove the frame rate, so a slow clock is never a mystery."""
    last = 0
    while True:
        time.sleep(30)
        f = FRAMES[0]
        try:
            with open(FPSLOG, "a") as fh:
                fh.write("real %s  +%5.0fs   fp 30s %6.1f   game day %7.3f\n"
                         % (time.strftime("%H:%M:%S"), time.time() - START,
                            (f - last) / 30.0, day_now()))
                fh.flush()
        except Exception:
            pass
        last = f


def reporter():
    """Rule 2 and rule 3: one line a day, and not a word until the world is up."""
    last = -1
    started = False
    while True:
        time.sleep(1.0)
        day = day_now()
        if day < 0.0:
            continue
        if not started:
            # the world is up once the clock is actually moving
            if day > 0.02 and getattr(village, "PLAYER", None) is not None:
                started = True
                open(LOG, "a").write(
                    "########## sim started %s -- world up at day %.2f ##########\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), day))
            else:
                continue
        whole = int(day)
        if whole == last:
            continue
        last = whole
        w = nemesis.WORLD
        nm = w.active if w else None
        if nm is None:
            line = ("day %-4d  population %4d   nemesis  none\n"
                    % (whole, population()))
        else:
            n = nm.npc
            sk = getattr(n, "skills", None)
            job = getattr(n, "job", None) or ("farm" if n.farm_plot is not None
                                              else "none")
            if sk is None:
                skills = "no skills"
            else:
                skills = ("farming %.2f  axe %.2f  movement %.2f  shooting %.2f"
                          % (sk.farming, sk.axe, sk.movement, sk.shooting))
            line = ("day %-4d  population %4d   %-16s coin %4d  job %-8s  %s\n"
                    % (whole, population(), n.name, n.coins, job, skills))
        # WHERE IS THE COIN? A village ledger that lends 440 a day and takes
        # in 50 is not an economy, it is a bank -- and the tax base is only the
        # men who earned CASH, which the tax log says is 6 hands in a town of
        # 29. So count the purses against the ledgers: if the coin is sitting
        # in men's pockets, nothing else in this file will ever balance.
        try:
            import village as _vm
            import wildcrop
            people = list(_vm.PEOPLE)
            purses = sum(float(getattr(n, "coins", 0.0)) for n in people)
            earners = sum(1 for n in people
                          if float(getattr(n, "book_in", 0.0)) > 0.0)
            ledgers = 0.0
            w = wildcrop._WORLD
            reg = getattr(getattr(w, "ground", None), "villages_v", None)
            if reg is not None:
                ledgers = sum(float(getattr(v, "ledger_coins", 0.0))
                              for v in reg.villages)
            line += ("       COIN   ledgers %9.0f   purses %9.0f"
                     "   earned-today %4d of %4d\n"
                     % (ledgers, purses, earners, len(people)))
            # WHO HAS IT. If the coin is not in the ledgers and it is not in
            # the shops, it is in somebody's pocket -- and the trade of the men
            # holding the most of it says exactly who the economy is feeding.
            top = sorted((n for n in people if getattr(n, "alive", False)),
                         key=lambda n: -float(getattr(n, "coins", 0.0)))[:6]
            line += ("       RICH   " + "   ".join(
                "%s(%s)%d" % (getattr(n, "name", "?").split()[0],
                              getattr(n, "job", None) or "idle",
                              int(getattr(n, "coins", 0.0)))
                for n in top) + "\n")
            # AND WHO OWED: a man is taxed on book_in - book_out, so count the
            # men whose NET cleared the 20-coin tax-free floor.
            over = sum(1 for n in people
                       if float(getattr(n, "book_in", 0.0))
                       - float(getattr(n, "book_out", 0.0)) > 20.0)
            rich = sum(1 for n in people if float(getattr(n, "coins", 0.0)) > 100.0)
            line += ("       TAXABLE over-20-net %4d of %4d   purses-over-100 %4d\n"
                     % (over, len(people), rich))
            # ---- THE CLASS STRUCTURE ---------------------------------------
            # By EARNINGS (book_in, which the town books to zero once a day, so
            # it is one day's income) and by WEALTH (the purse). Both, because
            # they are not the same ladder: a king earns a salary and owns
            # nothing, a logger's purse is bounded by his wage now.
            cl = {}
            for n in people:
                if not getattr(n, "alive", False):
                    continue
                j = getattr(n, "job", None) or (
                    "farm" if getattr(n, "farm_plot", None) is not None
                    else "idle")
                if getattr(n, "is_king", False):
                    j = "king"
                elif getattr(n, "is_mayor", False):
                    j = "mayor"
                d = cl.setdefault(j, [0, 0.0, 0.0, []])
                d[0] += 1
                d[1] += float(getattr(n, "book_in", 0.0))
                d[2] += float(getattr(n, "coins", 0.0))
                d[3].append(float(getattr(n, "coins", 0.0)))
            rows = sorted(cl.items(), key=lambda kv: -kv[1][1])
            line += ("       CLASS BY DAILY EARNING (book_in)\n")
            for j, (c, earned, purse, arr) in rows[:14]:
                arr.sort()
                med = arr[len(arr) // 2] if arr else 0.0
                line += ("         %-9s %4d men   earned %7.0f  (%6.1f each)"
                         "   purse %8.0f  median %5.0f\n"
                         % (j, c, earned, earned / max(1, c), purse, med))
            line += ("       everyone else: %d trades below\n"
                     % max(0, len(rows) - 14))
            # ---- TOOLS: DOES THE FORGE DRESS THE PEOPLE WHO WORK? -----------
            # The question the whole night came down to. A farmer with no
            # shovel cannot till; a tool is worth TOOL_USES = 90 swings; the
            # smith replaces anything under TOOL_WORN = 30 -- IF he forges it,
            # and IF it reaches the man. Count every link separately.
            try:
                import industry as _ind
                fn = [n for n in people
                      if getattr(n, "alive", False)
                      and getattr(n, "farm_plot", None) is not None]
                lg = [n for n in people if getattr(n, "alive", False)
                      and getattr(n, "job", None) == "logger"]
                mi = [n for n in people if getattr(n, "alive", False)
                      and (getattr(n, "job", None) == "mine"
                           or getattr(getattr(n, "workplace", None), "kind",
                                      None) == "mine")]
                def _n(held, who, t):
                    return sum(1 for n in who if n.stock.get(t, 0) > 0)
                shelf = {}
                reg = getattr(getattr(wildcrop._WORLD, "ground", None),
                              "villages_v", None)
                if reg is not None:
                    for v in reg.villages:
                        for t in ("shovel", "axe", "pickaxe"):
                            q = v.ledger_goods.get(t, 0)
                            if q:
                                shelf[t] = shelf.get(t, 0) + q
                worn = sum(1 for n in people if getattr(n, "alive", False)
                           and getattr(n, "tool_uses", 0)
                           and getattr(n, "tool_uses", 0) <= E2_TOOL_WORN)
                line += ("       TOOLS  farmers %3d with a shovel %3d"
                         "   loggers %3d with an axe %3d"
                         "   miners %3d with a pickaxe %3d\n"
                         % (len(fn), _n("shovel", fn, "shovel"),
                            len(lg), _n("axe", lg, "axe"),
                            len(mi), _n("pickaxe", mi, "pickaxe")))
                line += ("       WEAR   tools with 30 or fewer workings left %3d"
                         "   on the town shelves: %s\n"
                         % (worn, shelf if shelf else "NONE"))
            except Exception as _e:
                line += "       TOOLS  (unavailable: %r)\n" % (_e,)
        except Exception as _e:
            line += "       COIN   (unavailable: %r)\n" % (_e,)
        try:
            with open(LOG, "a") as fh:
                fh.write(line)
                fh.flush()
        except Exception as e:
            with open(LOG, "a") as fh:
                fh.write("REPORTER ERROR %r\n" % (e,))


# A GENUINELY NEW GAME, NOT THE LAST ONE RESUMED. The save carries `now` --
# mine said day 63 -- and a run that loads it starts at the previous run's day,
# with the previous run's population, and looks exactly like a world that has
# collapsed. BOTH files go: the world cache and the save.
_sd = os.path.join(HERE, "saves")
if os.path.isdir(_sd):
    for _f in os.listdir(_sd):
        if _f.startswith(("world_", "save_")):
            try:
                os.remove(os.path.join(_sd, _f))
            except Exception:
                pass

open(FPSLOG, "a").write("########## sim started %s ##########\n"
                        % time.strftime("%Y-%m-%d %H:%M:%S"))
threading.Thread(target=keeper, daemon=True).start()
threading.Thread(target=fps_watch, daemon=True).start()
threading.Thread(target=reporter, daemon=True).start()

# A NORMAL GAME. Test mode holds a tournament on day one, and that is not how
# a world begins for a player.
menu.run = lambda screen, clock: (0, False)
try:
    main.main()
except BaseException:
    import traceback
    with open(LOG, "a") as fh:
        fh.write("\nSIM DIED\n" + traceback.format_exc()[-1500:] + "\n")
