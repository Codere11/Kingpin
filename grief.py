"""grief.py -- SEEING A CORPSE: -15 mood, once per body, spread over a minute."""
import math
import corpse as corpse_mod

_pending = []
_index = 0
RADIUS = 120.0


def tick(people, dt):
    global _pending, _index
    if not corpse_mod.CORPSES:
        return
    if not _pending:
        _pending = [p for p in people if getattr(p, "alive", True)]
        _index = 0
    if not _pending:
        return
    count = max(1, int(len(_pending) * dt / 60.0))
    for _ in range(count):
        if _index >= len(_pending):
            _pending = []
            break
        p = _pending[_index]
        _index += 1
        _see(p)


def _see(p):
    seen = getattr(p, "_corpse_seen", None)
    if seen is None:
        seen = set()
        p._corpse_seen = seen
    for c in corpse_mod.CORPSES:
        if id(c) in seen:
            continue
        if math.hypot(c.x - p.x, c.y - p.y) <= RADIUS:
            seen.add(id(c))
            try:
                import mind as _mind
                _mind.apply_mood(p, -15.0, reason="corpse")
            except Exception:
                pass
