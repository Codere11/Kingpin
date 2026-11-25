"""scent.py -- a coarse smell field for people and horses.

Wolves do not see a name through the trees.  They smell a body, follow the
strongest scent they can find, and only then see who it belongs to.

The field is deliberately coarse and updated every couple of seconds.  It is
not a per-frame scan of every man and horse in the world.
"""

from __future__ import annotations

import math


CELL = 96.0
RANGE = 1800.0
UPDATE = 2.0
DECAY = 0.82


class ScentField:
    def __init__(self, g) -> None:
        self.g = g
        self.cells = {}        # (cx, cy) -> [strength, source]
        self.t = 0.0
        self._sources_t = 0.0

    def _sources(self):
        g = self.g
        out = []
        player = getattr(g, "player", None)
        if player is not None and getattr(player, "alive", True):
            out.append(player)
        for n in (getattr(g, "_native_people", ()) or ()):
            if getattr(n, "alive", True) and not getattr(n, "in_interior", False):
                out.append(n)
        for h in (getattr(g, "horses", ()) or ()):
            if getattr(h, "alive", True):
                out.append(h)
        return out

    def _add(self, src, x, y, strength):
        cx = int(x // CELL)
        cy = int(y // CELL)
        # The source cell carries most of the scent; neighbours carry the
        # edge of the trail.  A wolf can follow that edge when the body is
        # behind a rise, a wall or a stand of trees.
        for ox, oy, mult in ((0, 0, 1.0), (1, 0, 0.24), (-1, 0, 0.24),
                              (0, 1, 0.24), (0, -1, 0.24),
                              (1, 1, 0.10), (-1, 1, 0.10),
                              (1, -1, 0.10), (-1, -1, 0.10)):
            key = (cx + ox, cy + oy)
            got = self.cells.get(key)
            value = strength * mult
            if got is None or value > got[0]:
                self.cells[key] = [value, src]

    def tick(self, g, dt):
        self.t += max(0.0, dt)
        if self.t < UPDATE:
            return
        self.t = 0.0
        # Old scent fades.  Trails linger long enough to be followed, but not
        # long enough to make the whole map smell like one permanent camp.
        for key, value in list(self.cells.items()):
            value[0] *= DECAY
            if value[0] < 0.015:
                self.cells.pop(key, None)
        for src in self._sources():
            try:
                strength = 1.0
                if src is getattr(g, "player", None):
                    strength = 2.4
                elif getattr(src, "kind", "") == "horse":
                    strength = 2.0
                else:
                    max_hp = max(1.0, float(getattr(src, "max_health", 1.0)))
                    hurt = 1.0 - min(1.0, float(getattr(src, "health", max_hp)) / max_hp)
                    strength += hurt * 0.8
                self._add(src, float(src.x), float(src.y), strength)
            except Exception:
                continue

    def target_for(self, g, wolf, reach: float = RANGE):
        """The living body whose smell is strongest within reach, or None."""
        wx = float(getattr(wolf, "x", 0.0))
        wy = float(getattr(wolf, "y", 0.0))
        best = None
        best_score = 0.0
        for key, value in self.cells.items():
            src = value[1]
            if src is wolf or src is None or not getattr(src, "alive", True):
                continue
            try:
                dx = float(src.x) - wx
                dy = float(src.y) - wy
            except Exception:
                continue
            d = math.hypot(dx, dy)
            if d > reach:
                continue
            # Smell strength, with a gentle preference for the nearer body.
            score = float(value[0]) / (1.0 + d / 360.0)
            if score > best_score:
                best_score = score
                best = src
        return best


def ensure(g):
    field = getattr(g, "scent", None)
    if not isinstance(field, ScentField):
        field = ScentField(g)
        g.scent = field
    return field


def tick(g, dt):
    ensure(g).tick(g, dt)


def target_for(g, wolf, reach: float = RANGE):
    return ensure(g).target_for(g, wolf, reach)
