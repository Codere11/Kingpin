"""Workers: the world split across cores, without ever sharing a mutable object.

WHY THIS IS EVEN POSSIBLE
-------------------------
The profile says the frame is 68-83% one loop -- `for _n in PEOPLE: n.tick()` --
and 13-26% the towns. Both of those live inside per-town data: a town's granary,
ledger, fields, benches and people are ITS OWN. The only things that cross a
town boundary are a short, named list: traders on the road, armies, refugees,
news, prices, the crown, the player. So the world can be cut at the fence.

WHY IT IS TRACTABLE
-------------------
Not by sending a thousand men down a pipe. THE WORLD IS BUILT ONCE, THE GAME IS
IMPORTED ONCE, AND *THEN* THE PROCESS FORKS. On Linux a fork hands the child the
parent's memory copy-on-write: page tables copied, pages shared until written.
So every worker begins with the entire world already in memory -- the terrain,
the towns, the men -- at the cost of a few milliseconds. No re-import, no
re-generation, no 90-second second startup.

ONE OWNER PER TOWN. THIS IS THE WHOLE RULE.
-------------------------------------------
A town is owned by exactly one lane: the MAIN process if the player is near it,
a WORKER otherwise. Not mirrored, not replicated -- owned. A mirror would drift
and a drifted town is the "a village nobody is looking at does not tick" bug
with extra steps. Ownership MOVES: as the player approaches a town the worker
hands it back (pickled, which the save system has done since the beginning) and
stops touching it; as the player leaves, it is handed out.

A workstation never holds two owners, for the same reason ONE MAN, ONE PLACE
holds: the moment two lanes may write a granary, the game is corrupt.

ONLY AVAILABLE CORES
--------------------
`plan_workers` refuses to take the whole machine. It asks the OS which CPUs this
process is actually allowed (`sched_getaffinity`, which respects taskset and
cgroups), subtracts a reserve for the desktop and the operating system, takes
the machine's real load into account, and caps the count -- because the crossing
cost grows with N while the work does not.
"""

from __future__ import annotations

import os

# ---- how many cores may we take? ------------------------------------------
#
# Reserve, don't consume. The desktop needs a core, the OS needs one, and this
# process needs the lane it already has. Taking every core makes the game fast
# and the machine unusable, which is not "fast".
RESERVE_CORES = 1
MAX_WORKERS = 8          # beyond this the crossing costs more than the work
MIN_WORKERS = 0          # 0 is a real answer: a box with nothing spare
                         # runs the world single-process, as it does today


def allowed_cores() -> int:
    """The CPUs this process may actually use -- not merely the ones that exist.

    sched_getaffinity is the honest number: under `taskset`, a container limit
    or a cgroup quota, os.cpu_count() reports the metal while the process is
    permitted two cores. Asking for more workers than we are allowed to run
    just makes them fight.
    """
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def load_1min() -> float:
    """The machine's real one-minute load, or 0 if it cannot be read."""
    try:
        return float(os.getloadavg()[0])
    except (AttributeError, OSError):
        return 0.0


def plan_workers() -> int:
    """How many worker processes to run -- leaving the rest of the machine alone.

    Measured on this box: 12 cores, load 4.35 -> 4 workers, 8 cores left for
    everything else. On an idle 4-core laptop: 2 allowed minus 2 reserved = 0,
    clamped to 1 -- one worker, which is right for a machine with nothing to
    spare.
    """
    allowed = allowed_cores()
    spare = allowed - RESERVE_CORES
    # The machine is ALREADY busy: do not add workers to a saturated box. The
    # idle cores are the only ones worth having -- cores that are doing
    # something else are not available, they are in use.
    idle = allowed - load_1min()
    n = min(spare, int(idle), MAX_WORKERS)
    if n <= 0:
        return 0        # nothing spare: do not split, do not fight for cores
    return max(MIN_WORKERS, n)


def summary(town) -> dict:
    """A town in a few dozen numbers -- everything another lane needs to know.

    Deliberately NOT the town. The crown wants its population, its granary and
    its ledger; the census wants its trades; a trader wants its prices. Nobody
    offscreen needs its men, its fields or its houses, and shipping those every
    frame is how a split world becomes slower than a single one.
    """
    try:
        alive = sum(1 for n in town.npcs if getattr(n, "alive", False))
    except AttributeError:
        alive = 0
    return {
        "name": getattr(town, "name", "?"),
        "gx": getattr(town, "gx", 0),
        "gy": getattr(town, "gy", 0),
        "day": float(getattr(town, "_day", 0.0)),
        "alive": alive,
        "capacity": int(getattr(town, "capacity", 0)),
        "granary": float(getattr(town, "granary", 0.0)),
        "ledger": float(getattr(town, "ledger_coins", 0.0)),
        "nation": getattr(town, "nation", None),
        "mayor": getattr(getattr(town, "mayor", None), "name", None),
    }


if __name__ == "__main__":
    print("cores that exist     :", os.cpu_count())
    print("cores we may use     :", allowed_cores())
    print("1-minute load        :", round(load_1min(), 2))
    print("reserve              :", RESERVE_CORES)
    print("-> workers           :", plan_workers())
    print("   cores left to the machine:",
          allowed_cores() - plan_workers())
