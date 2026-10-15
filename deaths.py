"""deaths.py -- every death in the world, in one clean file.

WHY A FILE OF ITS OWN. The game already notes every death, but it notes them
into ~/.kingpin_saves/village.log, which is seventeen megabytes of every run
this machine has ever played: harvests, elections, trades, tax and deaths all
interleaved, no way to tell one game from the next, and no way to read it.

So a death gets a line of its own in ~/.kingpin_saves/deaths.log, written the
moment it happens and flushed, so an exit -- or a crash -- cannot lose it:

    day   12.43  STARVED           Bessie Whitfield   of Ash Bend     coin    3  hunger 100.0  food  0

WHERE THE CAUSES COME FROM. There are exactly four places a man is killed,
and each one calls this:

    economy.needs()            hunger reached STARVE_AT          STARVED
    NPC.take_damage()          a blow or a bullet took his health SHOT / BLUDGEONED
    war.rout()                 a refugee run down on the road     CUT DOWN ON THE ROAD
    war.Army.retire()          a soldier killed in the line       KILLED IN ACTION

A fifth path exists -- a man who dies inside update() is settled by
NPC.die() -- but that is the RESULT of one of those four, not a cause of its
own, and logging it would double every entry.
"""

from __future__ import annotations

import os
import time

_PATH: str | None = None


def path() -> str:
    global _PATH
    if _PATH is None:
        d = os.path.expanduser("~/.kingpin_saves")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        _PATH = os.path.join(d, "deaths.log")
    return _PATH


def record(npc, cause: str, detail: str = "", by=None) -> None:
    """One line: the day, how he died, who he was, what he had, and who did it.

    Never raises. A death that cannot be written must not become a second
    death -- an exception here would be caught by the caller's blanket except
    and the man would be skipped, which is exactly the class of bug that
    killed 73 miners over a missing attribute.
    """
    try:
        v = getattr(npc, "village", None)
        day = float(getattr(v, "_day", 0.0)) if v is not None else 0.0
        food = 0
        try:
            for f in ("bread", "berries", "cactus_fruit"):
                food += int(npc.stock.get(f, 0))
        except Exception:
            pass
        who = ""
        if by is not None:
            who = "  by %s of %s" % (
                getattr(by, "name", "?"),
                getattr(getattr(by, "village", None), "name", "?") or "nowhere")
        line = ("day %7.2f  %-22s %-16s of %-14s  coin %5d  hunger %5.1f"
                "  food %3d  job %-8s%s %s\n"
                % (day, cause, getattr(npc, "name", "?"),
                   getattr(v, "name", "nowhere"),
                   int(getattr(npc, "coins", 0)),
                   float(getattr(npc, "hunger", 0.0)), food,
                   getattr(npc, "job", None) or "idle", who, detail))
        with open(path(), "a") as fh:
            fh.write(line)
    except Exception:
        pass


def banner(text: str) -> None:
    """A line to mark where a game began, so one run can be told from the next."""
    try:
        with open(path(), "a") as fh:
            fh.write("\n===== %s  %s =====\n"
                     % (text, time.strftime("%Y-%m-%d %H:%M:%S")))
    except Exception:
        pass


def tail(n: int = 40) -> list:
    """The last n deaths, oldest first -- for the inspector to show."""
    try:
        with open(path(), "r") as fh:
            return fh.readlines()[-n:]
    except Exception:
        return []
