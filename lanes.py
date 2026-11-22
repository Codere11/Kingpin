"""lanes.py -- compatibility stub for the old town partition lanes.

The native world has no town lanes. The frame still asks the partition whether
it is alive and for its people; the answers are empty.
"""

from __future__ import annotations


class Partition:
    def __init__(self, count: int = 1) -> None:
        self.count = int(count)
        self.towns: list = []
        self.people: list = []

    def ok(self, *a, **k) -> bool:
        return False

    def recut(self, *a, **k) -> None:
        self.towns = []
        self.people = []

    def towns_for(self, *a, **k) -> list:
        return []

    def people_for(self, *a, **k) -> list:
        return []
