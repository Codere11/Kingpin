"""conversation.py -- one meaningful conversation at a time.

NPCs no longer shout praise/insults at whoever is nearby.  A speaker walks to
a spot directly in front of the other person, waits until they are face to
face, says one line tied to a real need or relationship, and only then applies
the social effect.
"""

from __future__ import annotations

import math

import economy
import relationships


def _state(g):
    s = getattr(g, "_conversation_state", None)
    if s is None:
        s = {"active": None, "next": 0.0}
        g._conversation_state = s
    return s


def _player(who):
    return (getattr(who, "is_player", False)
            or type(who).__name__ == "Player")


def _busy(who):
    return (not getattr(who, "alive", True)
            or getattr(who, "asleep", False)
            or getattr(who, "in_interior", False)
            or getattr(who, "break_state", "normal") in
            ("berserk", "breaking_spree", "crop_spree", "depression"))


def _front(target):
    fx, fy = getattr(target, "facing", (0.0, 1.0)) or (0.0, 1.0)
    d = math.hypot(fx, fy) or 1.0
    return (float(target.x) + fx / d * 36.0,
            float(target.y) + fy / d * 36.0)


def _need_line(npc, target, g):
    """One readable line, grounded in a need or a relationship."""
    name = getattr(npc, "name", "?")
    other = getattr(target, "name", "you")
    try:
        if float(getattr(npc, "hunger", 0.0)) >= 80.0:
            return "need", "I'm starving. We have no food."
        if float(getattr(npc, "health", 1.0)) < float(getattr(npc, "max_health", 1.0)) * 0.55:
            return "need", "I'm hurt. Do we have medicine?"
        if getattr(npc, "slept_outside", False):
            return "need", "I need a bed before another night outside."
        if float(getattr(npc, "mood", 50.0)) <= 30.0:
            return "need", "I can't keep working like this."
        if _player(target):
            line = getattr(npc, "wants_product", None) or getattr(npc, "wants_drink", None)
            if line:
                return "need", "I need a %s." % str(line).replace("_", " ")
            return "talk", "%s, we should talk when you have a moment." % name
        rec = relationships.ensure(npc).get(getattr(target, "id", ""))
        aff = float(rec.get("affinity", 0.0)) if isinstance(rec, dict) else 0.0
        if aff <= -10.0:
            return "complaint", "We need to settle what happened between us."
        if aff >= 20.0:
            return "praise", "You have been good to me, %s." % other
        return "talk", "How are things going here?"
    except Exception:
        return "talk", "We should talk."


def _start(g, speaker, target, now):
    st = _state(g)
    if st["active"] is not None or now < float(st.get("next", 0.0)):
        return False
    if speaker is target or _busy(speaker) or _busy(target):
        return False
    if _player(target):
        try:
            if (g.pause_open or g.build_menu_open or g.inventory_open
                    or g.dialogue_panel.open_ or g.npc_card_open):
                return False
        except Exception:
            pass
    kind, text = _need_line(speaker, target, g)
    st["active"] = {"speaker": speaker, "target": target, "kind": kind,
                    "text": text, "phase": "walk", "until": 0.0}
    try:
        speaker._convo_busy_until = now + 12.0
        target._convo_busy_until = now + 12.0
    except Exception:
        pass
    return True


def request_npc(g, speaker, target, now=None):
    """Social life asks for an NPC-to-NPC conversation."""
    if now is None:
        now = float(getattr(g, "now", 0.0))
    return _start(g, speaker, target, now)


def tick(g, dt):
    st = _state(g)
    now = float(getattr(g, "now", 0.0))
    act = st.get("active")
    if act is not None:
        speaker = act.get("speaker")
        target = act.get("target")
        if (speaker is None or target is None
                or not getattr(speaker, "alive", True)
                or not getattr(target, "alive", True)
                or _busy(speaker) or _busy(target)):
            st["active"] = None
            st["next"] = now + 8.0
            return
        if act["phase"] == "walk":
            tx, ty = _front(target)
            d = math.hypot(tx - speaker.x, ty - speaker.y)
            if d > 34.0:
                try:
                    speaker._step_toward(tx, ty, dt, 0.9)
                except Exception:
                    return
                return
            # face the listener and begin
            ux, uy = target.x - speaker.x, target.y - speaker.y
            den = math.hypot(ux, uy) or 1.0
            speaker.facing = (ux / den, uy / den)
            if not _player(target):
                target.facing = (-ux / den, -uy / den)
            act["phase"] = "talk"
            act["until"] = now + 6.0
            try:
                import comm
                comm.spawn_cloud(speaker.x, speaker.y, act["kind"],
                                 text=act["text"])
            except Exception:
                pass
            try:
                g.toast("%s: %s" % (getattr(speaker, "name", "Someone"),
                                    act["text"]))
            except Exception:
                pass
            try:
                import playlog
                playlog.record(g, "social", action="talk",
                               actor=getattr(speaker, "name", "?"),
                               target=getattr(target, "name", "you"),
                               text=act["text"])
            except Exception:
                pass
            return
        if act["phase"] == "talk":
            if now < float(act.get("until", 0.0)):
                return
            try:
                if act["kind"] in ("need", "complaint"):
                    relationships.observe(target, speaker, "talk", now, g)
                elif act["kind"] == "praise":
                    relationships.observe(target, speaker, "praise", now, g)
            except Exception:
                pass
            try:
                speaker._convo_busy_until = 0.0
                target._convo_busy_until = 0.0
            except Exception:
                pass
            st["active"] = None
            st["next"] = now + 18.0
            return
    if now < float(st.get("next", 0.0)):
        return
    scan = float(st.get("scan_t", 0.0)) - dt
    if scan > 0.0:
        st["scan_t"] = scan
        return
    st["scan_t"] = 2.0
    # One NPC may come to the player, but only if the player is nearby and
    # nobody else is already talking.
    player = getattr(g, "player", None)
    if player is None or _busy(player):
        return
    best = None
    bd = 520.0
    for n in (getattr(g, "_native_people", ()) or ()):
        if not getattr(n, "conquered", False) or n is player or _busy(n):
            continue
        if now < float(getattr(n, "_convo_busy_until", 0.0)):
            continue
        d = math.hypot(n.x - player.x, n.y - player.y)
        if d < bd:
            bd, best = d, n
    if best is not None:
        _start(g, best, player, now)
        return
    # If nobody has a need, NPC-to-NPC talk is started by social_life.py.
    st["next"] = now + 8.0
