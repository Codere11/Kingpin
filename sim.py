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
import nemesis
import main
import menu

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
