"""A LONG WATCH ON THE NEMESIS.

Runs the REAL game -- the same main.main(), the same world tick, the same
1x speed you play at -- with nobody at the keyboard, and writes one line per
IN-GAME DAY about the world and about him.

    python nemsim.py            # runs until you kill it
    tail -f nemesis_sim.log     # watch

THE WORLD MOVES EXACTLY AS IT DOES WHEN YOU PLAY. No accelerated clock, no
skipped simulation, no stubbed ticks: only the drawing is trimmed, because the
window is tiny and there is nobody to look at it. The player stands where he
spawned and does nothing at all.

WHAT IS RECORDED EACH DAY
    P<n>            how many people are alive in the world
    the nemesis     coin, job, whether he holds office, and his four skills
    TRADES          who he has dealt with (economy.opinion grows +1 a trade)
    GRUDGES         the men he has schemed out of a post
    and any BORN / RISES / DEAD line the game itself wrote about him
"""

import os
import sys
import time
import threading
import collections

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pygame

_sm = pygame.display.set_mode
pygame.display.set_mode = lambda *a, **k: _sm((128, 96), 0)

# NO CLOCK STUB. The game keeps time with the real one, so a game day is ten
# real minutes and the world runs at the speed the player sees.
class _K:
    def __init__(self, d):
        self.d = d

    def __getitem__(self, k):
        return k in self.d


pygame.key.get_pressed = lambda: _K(set())
pygame.mouse.get_pos = lambda: (64, 48)
pygame.mouse.get_pressed = lambda: (0, 0, 0)

import nemesis
import village
import economy
import main
import menu

LOG = os.path.join(HERE, "nemesis_sim.log")
STATE = {"day": -1, "last": None, "started": time.time()}


_LOG = os.path.join(os.path.expanduser("~"), ".kingpin_saves", "village.log")
# THE END OF THE LOG, AT STARTUP. Everything before this file position belongs
# to an earlier run and must never be read, counted or shown: the log is
# appended to across every run of the evening, so a cumulative count says
# nothing about the world being watched. 9,536 "STARVED" lines was two months
# of testing, not one day.
_LOGPOS = [0]
CAUSES = collections.Counter()


def _actions():
    """EVERY ACTION HE TOOK, in the game's own words, since the last report.

    The sim does not guess what he did: it reads the lines the game itself
    wrote -- BORN, RISES, OMEN, STRIKE, DEAD -- so what you see each day is
    what actually happened, not what the reporter inferred.
    """
    out = []
    try:
        with open(_LOG, "r") as fh:
            fh.seek(_LOGPOS[0])
            for line in fh:
                if "NEMESIS" in line:
                    out.append("  > " + line.strip())
                for c in ("SLAIN", "STARVED", "CUT DOWN", "KILLED IN ACTION"):
                    if line.startswith(c):
                        CAUSES[c] += 1
                        break
            _LOGPOS[0] = fh.tell()
    except Exception:
        pass
    return out


def _pop():
    return sum(1 for n in village.PEOPLE if getattr(n, "alive", True))


def _line(world, day):
    nm = world.active if world else None
    n = nm.npc if nm is not None else None
    acts = _actions()
    out = ["=" * 4 + " day %-4d " % day + "=" * 4,
           "world: %d alive" % _pop()]
    if CAUSES:
        out.append("DEATHS THIS RUN: " + ", ".join(
            "%s %d" % (k, v) for k, v in CAUSES.most_common()))
    if acts:
        out.append("WHAT HE DID:")
        out += acts
    else:
        out.append("WHAT HE DID: nothing -- no change of post, no move.")
    if n is None:
        out.append("nemesis: none  (dead %s, next due day %d)"
                   % (world.dead_day if world else "?", 
                      (world.dead_day + 40) if world else "?"))
        return out
    sk = getattr(n, "skills", None)
    alive = getattr(n, "alive", False)
    office = ("KING" if getattr(n, "is_king", False)
              else "mayor" if getattr(n, "is_mayor", False)
              else "soldier" if getattr(n, "is_soldier", False)
              or getattr(n, "levied", False) else "-")
    out.append("nemesis: %s  %s%s  coin %d  job %s  office %s  town %s"
               % (n.name, "ALIVE" if alive else "DEAD",
                  "" if alive else " (cause unknown)", n.coins,
                  getattr(n, "job", None) or ("farm" if n.farm_plot is not None
                                              else "none"),
                  office, getattr(nm.town, "name", "?")))
    if sk is not None:
        out.append("  skills: farming %.2f/8  axe %.2f/1  movement %.2f/1  "
                   "shooting %.2f/1   rank %d"
                   % (sk.farming, sk.axe, sk.movement, sk.shooting,
                      nemesis.rank_of(n)))
    op = getattr(n, "opinion", None) or {}
    if op:
        by_id = {getattr(m, "id", None): m.name for m in village.PEOPLE}
        top = sorted(op.items(), key=lambda kv: -kv[1])[:6]
        out.append("  TRADES (%d partners): %s" % (
            len(op), ", ".join("%s x%d" % (by_id.get(k, "?"), int(v))
                               for k, v in top)))
    if nm.grudges:
        out.append("  GRUDGES: " + "; ".join(
            "%s (%s)" % (k, v) for k, v in list(nm.grudges.items())[-6:]))
    out.append("  where he is: %s, %s%s   (rank %d of 10, %d days in this post)"
               % (nm.town.name,
                  getattr(nm.town, "nation", "?"),
                  "  AT COURT" if getattr(n, "at_court", False) else "",
                  nemesis.rank_of(n), nm.days_in_trade))
    out.append("  knows player: %s   strikes landed: %d   last omen day %s"
               % (nm.knows_player, nm.strikes, nm.omen_day))
    return out


def keeper():
    """THE WORLD MUST NOT STOP BECAUSE NOBODY IS PLAYING.

    main()'s frame loop advances the world clock inside the interior branch and
    the exterior branch -- and BOTH are guarded by `not game_over`. An idle
    player starves in about a day, dies, the game-over panel comes up, and from
    that moment `now` never advances again: the whole world freezes with one
    day in the log. That is what we have been staring at.

    So the keeper keeps the body alive -- fed, and invulnerable -- and revives
    it if it dies anyway. The PLAYER is not being simulated here; he is a
    bystander. Everything else in the world runs untouched.
    """
    while True:
        time.sleep(1.0)
        try:
            p = getattr(village, "PLAYER", None)
            if p is None:
                continue
            if getattr(p, "dead", False):
                p.respawn()
            p.god = True                      # the same flag test mode uses
            p.hunger = getattr(p, "max_hunger", 100.0)
            p.health = getattr(p, "max_health", 100)
        except Exception:
            pass


threading.Thread(target=keeper, daemon=True).start()


def heartbeat():
    """IS THE WORLD'S CLOCK ACTUALLY MOVING?

    A heartbeat every 20 seconds showing the game's own clock and the day the
    nemesis last ticked. If these two numbers do not move, the world is not
    advancing and no amount of waiting will produce a day.
    """
    import creatures
    while True:
        time.sleep(20)
        try:
            with open("/tmp/nemsim_beat.txt", "a") as fh:
                fh.write("t=%s  creatures._NOW=%.1f  nemesis_days=%s  day=%s\n"
                         % (time.strftime("%H:%M:%S"),
                            float(getattr(creatures, "_NOW", -1)),
                            getattr(nemesis.WORLD, "_last_day", "?")
                            if nemesis.WORLD else "-",
                            int(float(getattr(creatures, "_NOW", 0))
                                / 600.0)))
        except Exception as e:
            with open("/tmp/nemsim_beat.txt", "a") as fh:
                fh.write("HEARTBEAT ERR %r\n" % (e,))


threading.Thread(target=heartbeat, daemon=True).start()


def _seek_to_end():
    """START READING FROM NOW. Nothing written before this line belongs to
    this run, and counting it would be counting every run of the evening."""
    try:
        with open(_LOG, "r") as fh:
            fh.seek(0, 2)
            _LOGPOS[0] = fh.tell()
    except Exception:
        _LOGPOS[0] = 0


def watch():
    last_day = -1
    while True:
        time.sleep(3)
        world = nemesis.WORLD
        if world is None:
            continue
        day = world._last_day
        if day == last_day:
            continue
        last_day = day
        try:
            with open(LOG, "a") as fh:
                fh.write("\n".join(_line(world, day)) + "\n")
                fh.flush()
        except Exception as e:
            try:
                with open(LOG, "a") as fh:
                    fh.write("REPORTER ERROR %r\n" % (e,))
            except Exception:
                pass


threading.Thread(target=watch, daemon=True).start()
_seek_to_end()
open(LOG, "a").write("\n\n########## nemsim started %s ##########\n"
                     % time.strftime("%Y-%m-%d %H:%M:%S"))
# A NORMAL GAME, NOT TEST MODE: the world must move exactly as it does for the
# player, and test mode holds a tournament on day one.
menu.run = lambda screen, clock: (0, False)
try:
    main.main()
except BaseException:
    import traceback
    with open(LOG, "a") as fh:
        fh.write("\nSIM DIED\n" + traceback.format_exc()[-2000:] + "\n")
