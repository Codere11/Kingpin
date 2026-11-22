"""lanes_mp.py -- a compatibility stub for the old multi-process worker lanes.

The native game walks its own people from `engine.run` (`g._native_people`),
not through town worker lanes. The old lanes, their carts, their crime reports
and their death queue are gone; this object keeps the handful of calls the
frame still makes harmless.
"""

from __future__ import annotations

import os

import persist


LOG = os.path.join(persist.DIR, "workers.log")


class WorkerLanes:
    enabled = False
    offence_sink = None
    stall_sink = None
    caught_sink = None
    _last_death = None
    stall = None

    def ok(self) -> bool:
        return False

    def apply(self, world, combat) -> None:
        return None

    def tick(self, *a, **k) -> None:
        return None

    def stop(self) -> None:
        return None

    def damage(self, *a, **k) -> None:
        return None

    def post(self, *a, **k) -> None:
        return None

    def panic_at(self, *a, **k) -> None:
        return None

    def take_deaths(self) -> list:
        return []

    def watch(self, *a, **k) -> None:
        return None

    def crime(self, *a, **k) -> None:
        return None


def start(world, villages, hubs, player) -> WorkerLanes:
    return WorkerLanes()
