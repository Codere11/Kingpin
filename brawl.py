"""brawl.py -- THE MAJOR BREAK: below 20 mood a man goes and punches the one
he hates most. The punched man retaliates, bystanders pile in, the militia
darts the lot, and whoever walks away keeps the catharsis (+40)."""
import math
import economy
import plog

BREAK_MIN_MOOD = 20.0
ROLL_SECONDS = 30.0
BREAK_CHANCE = 0.70
REACH = 46.0
JOIN_RADIUS = 50.0
CATHARSIS = 40.0
SENTENCE_DAYS = 3
BUST_SECONDS = 20.0      # a brawl this old brings the militia


def most_hated(npc, others):
    """The nearby man he holds the lowest opinion of."""
    best, bd = None, None
    for o in others:
        if o is npc or not getattr(o, "alive", True):
            continue
        if getattr(o, "in_cell", False) or getattr(o, "in_interior", False) \
                or getattr(o, "asleep", False) or getattr(o, "sleep_t", 0.0) > 0.0:
            continue
        if math.hypot(o.x - npc.x, o.y - npc.y) > 220.0:
            continue
        op = float(economy.opinion_of(npc, getattr(o, "id", None))
                   .get(getattr(o, "id", None), 0.0))
        if best is None or op < bd:
            best, bd = o, op
    return best


def punch(npc, target, now, combat=None):
    """One punch: the SAME swing arc the player's fist makes, the damage, the
    memory, and the return swing."""
    if target is None or not getattr(target, "alive", True):
        return False
    if math.hypot(target.x - npc.x, target.y - npc.y) > REACH:
        return False
    npc._did_attack()
    # THE SAME SWING THE PLAYER SEES, without the recharge bar underneath.
    if combat is not None:
        try:
            combat.spawn_swing(npc.x, npc.y, math.atan2(target.y - npc.y,
                                                        target.x - npc.x))
        except Exception:
            pass
    target.take_damage(max(1, round((35.0 / 3.0) * npc.skills.axe_damage_scale())))
    try:
        economy.wronged(target, npc, 20.0, now)
    except Exception:
        pass
    target._brawl_target = npc          # he hits back
    return True


def step(npc, now, dt, others, combat=None):
    """One man's brawl step: start a break, chase the target, or swing."""
    _tgt = getattr(npc, "_brawl_target", None)
    # the brawl ends when the other man is down or gone: catharsis
    if _tgt is not None and (not getattr(_tgt, "alive", True)
                             or getattr(_tgt, "sleep_t", 0.0) > 0.0):
        npc._brawl_target = None
        npc.mood = min(100.0, float(getattr(npc, "mood", 50.0)) + CATHARSIS)
        economy._note("BRAWL-END %s catharsis +%d"
                      % (getattr(npc, "name", "?"), CATHARSIS))
        _tgt = None
    if _tgt is None:
        # start one?
        if float(getattr(npc, "mood", 50.0)) < BREAK_MIN_MOOD \
                and not getattr(npc, "asleep", False) \
                and not getattr(npc, "in_interior", False) \
                and not getattr(npc, "in_cell", False):
            npc._break_timer = getattr(npc, "_break_timer", ROLL_SECONDS) - dt
            if npc._break_timer <= 0.0:
                npc._break_timer = ROLL_SECONDS
                if npc.rng.random() < BREAK_CHANCE:
                    _tgt = most_hated(npc, others)
                    if _tgt is not None:
                        npc._brawl_target = _tgt
                        economy._note("BRAWL-BEGIN %s -> %s (mood %.0f)"
                                      % (getattr(npc, "name", "?"),
                                         getattr(_tgt, "name", "?"),
                                         npc.mood))
        return
    d = math.hypot(_tgt.x - npc.x, _tgt.y - npc.y)
    if d > REACH:
        ux = (_tgt.x - npc.x) / d
        uy = (_tgt.y - npc.y) / d
        npc.x += ux * getattr(npc, "speed", 50.0) * 1.4 * dt
        npc.y += uy * getattr(npc, "speed", 50.0) * 1.4 * dt
        npc.facing = (ux, uy)
    else:
        if punch(npc, _tgt, now, combat):
            economy._note("PUNCH %s -> %s"
                          % (getattr(npc, "name", "?"),
                             getattr(_tgt, "name", "?")))
            # bystanders: a man right there may pile in
            for o in others:
                if o is npc or o is _tgt or not getattr(o, "alive", True):
                    continue
                if getattr(o, "in_cell", False) or getattr(o, "sleep_t", 0.0) > 0.0:
                    continue
                if math.hypot(o.x - _tgt.x, o.y - _tgt.y) <= JOIN_RADIUS \
                        and getattr(o, "_brawl_target", None) is None \
                        and o.rng.random() < 0.5:
                    o._brawl_target = npc
                    economy._note("BRAWL-JOIN %s" % getattr(o, "name", "?"))


def town_step(town, now, dt):
    """The militia breaks up a brawl: dart every man throwing punches."""
    fighters = [n for n in getattr(town, "npcs", ())
                if getattr(n, "_brawl_target", None) is not None
                and getattr(n, "alive", True)]
    if len(fighters) < 4:
        return
    # find the brawl's age on one of them, else start the clock
    oldest = max((getattr(f, "_brawl_age", 0.0) for f in fighters), default=0.0)
    for f in fighters:
        f._brawl_age = oldest + dt
    if oldest + dt < BUST_SECONDS:
        return
    for f in fighters:
        if getattr(f, "sleep_t", 0.0) > 0.0:
            continue
        f.tranq()
        f._crime = "brawl"
        f._sentence_days = SENTENCE_DAYS
        economy._note("BRAWL-ARREST %s" % getattr(f, "name", "?"))
