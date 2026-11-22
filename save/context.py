"""context.py -- the maps a restore uses to turn ids back into objects.

Restoring is two passes: create/ensure the objects first, then resolve every
reference between them.  List indices and id() are never used; a saved
reference is a stable ``_save_uid`` string looked up in one of these maps.
"""

from __future__ import annotations


class Context:
    def __init__(self) -> None:
        self.camps: dict[str, object] = {}
        self.people: dict[str, object] = {}
        self.animals: dict[str, object] = {}
        self.houses: dict[str, object] = {}
        self.workplaces: dict[str, object] = {}
        self.chests: dict[str, object] = {}
        self.signs: dict[str, object] = {}
        self.foodboxes: dict[str, object] = {}
        self.planted_trees: dict[str, object] = {}
        self.deferred: list = []

    def later(self, fn) -> None:
        self.deferred.append(fn)

    def resolve(self) -> None:
        while self.deferred:
            fn = self.deferred.pop(0)
            try:
                fn()
            except Exception:
                pass
