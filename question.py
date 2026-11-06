"""question.py -- A militiaman who SEES a man consume approaches and questions.

The militia does not sweep for drinkers; it reacts to what it actually sees. A
man holding a bottle or a smoke within sight of a militiaman is approached and
questioned -- a '?' bubble -- and the encounter ends one of three ways:

    30%  both men lose 20 mood (the fright of being caught, the guard's own
         trouble over it),
    40%  nothing comes of it,
    30%  the man gives up his supplier, who is branded wanted.

Only what the militiaman SEES, never a telepathic sweep.
"""
import math
import random

import economy
import comm
from physics import segment_rect_hit

SIGHT = 280.0          # how far a militiaman sees a man consuming
REACH = 44.0           # close enough to put the question
CD = 10.0              # seconds before he questions again
LOSE_MOOD = 20.0


def tick(soldier, people, now, dt, occluders=(), combat=None, player=None):
    """One militiaman's watch: find a man physically consuming in sight, then
    walk over and question him. Called from the frame while he is near."""
    if not getattr(soldier, "alive", True):
        return
    _q = getattr(soldier, "_q_target", None)
    if _q is None:
        if now < float(getattr(soldier, "_q_cd", 0.0)):
            return
        for man in people:
            if man is soldier or not getattr(man, "alive", True):
                continue
            if getattr(man, "militia", False) or getattr(man, "is_militia", False):
                continue
            _fx = getattr(man, "use_fx", None)
            if _fx is None:
                continue
            if not _sees(soldier, man, occluders):
                continue
            soldier._q_target = man
            soldier._q_item = _fx[0]
            soldier._questioning = True
            economy._note("QUESTION %-14s -> %-16s (consuming %s)"
                          % (getattr(soldier, "name", "militia"),
                             getattr(man, "name", "?"), _fx[0]))
            break
        return
    # -- he has a man to question: walk over, then put the '?' -------------
    man = _q
    if (not getattr(man, "alive", True)
            or getattr(man, "use_fx", None) is None):
        _clear(soldier, now)
        return
    dx = man.x - soldier.x
    dy = man.y - soldier.y
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    soldier.facing = (ux, uy)
    if d > REACH:
        soldier.x += ux * getattr(soldier, "speed", 122.0) * 1.3 * dt
        soldier.y += uy * getattr(soldier, "speed", 122.0) * 1.3 * dt
        try:
            from physics import resolve_circle_rects
            soldier.x, soldier.y = resolve_circle_rects(
                soldier.x, soldier.y, getattr(soldier, "radius", 12),
                getattr(soldier, "_colliders", ()))
        except Exception:
            pass
        return
    _resolve(soldier, man, now, player)


def _clear(soldier, now):
    soldier._q_target = None
    soldier._q_item = None
    soldier._questioning = False
    soldier._q_cd = now + CD


def _resolve(soldier, man, now, player):
    """The '?' and the answer."""
    try:
        comm.spawn_cloud(soldier.x, soldier.y, "insult", "?")
    except Exception:
        pass
    _item = getattr(soldier, "_q_item", None)
    _clear(soldier, now)
    r = random.random()
    if r < 0.30:
        _lose(soldier, man)
    elif r < 0.70:
        economy._note("QUESTION-DROP %-14s %s"
                      % (getattr(soldier, "name", "militia"),
                         getattr(man, "name", "?")))
    else:
        _snitch(soldier, man, player, _item)


def _lose(soldier, man):
    try:
        import mind as _mind
        _mind.apply_mood(man, -LOSE_MOOD, reason="questioned")
        _mind.apply_mood(soldier, -LOSE_MOOD, reason="questioned a man")
    except Exception:
        pass
    economy._note("QUESTION-LOSE %-14s %s"
                  % (getattr(soldier, "name", "militia"),
                     getattr(man, "name", "?")))


def _snitch(soldier, man, player, item):
    seller = _seller_of(man, item)
    if seller is None:
        economy._note("QUESTION-SNITCH %s has no seller to name"
                      % getattr(man, "name", "?"))
        return
    if seller == "player":
        if player is not None:
            player.wanted = True
        economy._note("QUESTION-SNITCH %s names THE PLAYER"
                      % getattr(man, "name", "?"))
    else:
        seller.wanted = True
        economy._note("QUESTION-SNITCH %s names %s"
                      % (getattr(man, "name", "?"),
                         getattr(seller, "name", "?")))


def _seller_of(man, item):
    d = getattr(man, "_seller_of", None)
    if d and item:
        return d.get(item)
    return None


def _sees(soldier, man, occluders):
    dx = man.x - soldier.x
    dy = man.y - soldier.y
    d = math.hypot(dx, dy)
    if d > SIGHT:
        return False
    if occluders:
        lox, hix = (soldier.x, man.x) if soldier.x < man.x else (man.x, soldier.x)
        loy, hiy = (soldier.y, man.y) if soldier.y < man.y else (man.y, soldier.y)
        for rect in occluders:
            if (rect.right < lox or rect.left > hix
                    or rect.bottom < loy or rect.top > hiy):
                continue
            if segment_rect_hit(soldier.x, soldier.y, man.x, man.y, rect):
                return False
    return True
