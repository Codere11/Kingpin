"""incidents.py -- small social emergencies.

An insult or threat is a real event: it creates a speech bubble, a thought,
an opinion change, and a reaction chosen from the target's MBTI.  The
reaction can stay verbal, become a short brawl, or push the target into a
minor/major break.
"""

from __future__ import annotations

import economy
import mind
import mood
import persona


def _is_player(who) -> bool:
    return (getattr(who, "is_player", False)
            or type(who).__name__ == "Player")


def _nearby_target(actor, g, reach=200.0):
    """Nearest living NPC; the player only when no NPC is close."""
    best, bd = None, reach
    for n in (getattr(g, "_native_people", ()) or ()):
        if n is actor or not getattr(n, "alive", True):
            continue
        try:
            d = ((n.x - actor.x) ** 2 + (n.y - actor.y) ** 2) ** 0.5
        except Exception:
            continue
        if d < bd:
            best, bd = n, d
    if best is not None:
        return best
    player = getattr(g, "player", None)
    if player is not None and getattr(player, "alive", True):
        try:
            d = ((player.x - actor.x) ** 2 + (player.y - actor.y) ** 2) ** 0.5
            if d < reach:
                return player
        except Exception:
            pass
    return None


def _say(who, kind, text=None):
    try:
        import comm
        comm.spawn_cloud(who.x, who.y, kind, text=text)
    except Exception:
        pass


def _opinion_change(who, other, amount, now):
    try:
        oid = getattr(other, "id", None) or "player"
        opd = economy.opinion_of(who, oid)
        opd[oid] = max(-100.0, float(opd.get(oid, 0.0)) + amount)
    except Exception:
        pass


def _start_brawl(target, actor, now, seconds=20.0):
    try:
        target._brawl_target = actor
        target._brawl_until = float(now) + seconds
    except Exception:
        pass


def react(target, actor, g, now):
    """The target's first response, before the next tick."""
    if target is None or _is_player(target):
        return
    sid = getattr(actor, "id", None) or "player"
    # E/T/J answer back; I/F/P withdraw.  S makes it physical; N makes it
    # social/remembered.
    e = persona.axis(target, "IE") == "E"
    s = persona.is_sensing(target)
    t = persona.is_thinking(target)
    j = persona.axis(target, "JP") == "J"
    f = persona.is_feeling(target)
    p = persona.axis(target, "JP") == "P"
    low = float(getattr(target, "mood", 50.0)) <= mood.minor_threshold(target)
    if (e or t or j) and not low:
        if s and (t or e):
            _say(target, "threaten")
            _opinion_change(target, actor, -12.0, now)
            mood.add_thought(target, "threatened", -12.0, now, 300.0)
            _start_brawl(target, actor, now)
        else:
            _say(target, "insult")
            _opinion_change(target, actor, -8.0, now)
            mood.add_thought(target, "wronged", -8.0, now, 300.0)
    elif f or p or low:
        _say(target, "sad", text="...")
        _opinion_change(target, actor, -6.0, now)
        if low and (f or p):
            mood.set_break(target, "depression", now, seconds=180.0)
        elif low:
            mood.set_break(target, "sad", now, seconds=180.0)
    else:
        _opinion_change(target, actor, -5.0, now)


def insult(actor, target, kind, g, now, react_back=True):
    """One person publicly insults or threatens another."""
    if actor is None or target is None:
        return
    delta = -12.0 if kind == "threaten" else -8.0
    _say(actor, kind)
    _opinion_change(target, actor, -10.0 if kind == "threaten" else -7.0, now)
    if _is_player(target):
        try:
            g.toast("%s %ss you!" % (getattr(actor, "name", "Someone"),
                                     "threaten" if kind == "threaten" else "insult"))
        except Exception:
            pass
        try:
            import player_mind
            player_mind.observe(g, "responded")
        except Exception:
            pass
    else:
        try:
            mind.apply_mood(target, delta, reason=kind)
            mood.add_thought(target, "threatened" if kind == "threaten" else "insulted",
                             delta, now, 300.0)
            import relationships as _rel
            _rel.observe(target, actor, kind, now, g)
        except Exception:
            pass
        if react_back:
            react(target, actor, g, now)


def nearest(g, actor):
    return _nearby_target(actor, g)
