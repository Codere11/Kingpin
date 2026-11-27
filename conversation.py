"""conversation.py -- one meaningful conversation at a time.

NPCs no longer shout praise/insults at whoever is nearby.  A speaker walks to
a spot directly in front of the other person, waits until they are face to
face, says one line tied to a real need or relationship, and only then applies
the social effect.
"""

from __future__ import annotations

import math

import climate
import economy
import persona
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
            or getattr(who, "_antic_active", False)
            or getattr(who, "break_state", "normal") in
            ("berserk", "breaking_spree", "crop_spree", "depression"))


def _front(target):
    fx, fy = getattr(target, "facing", (0.0, 1.0)) or (0.0, 1.0)
    d = math.hypot(fx, fy) or 1.0
    return (float(target.x) + fx / d * 36.0,
            float(target.y) + fy / d * 36.0)


def _tried(npc, item):
    try:
        return int((getattr(npc, "consumed_items", None) or {}).get(item, 0)) > 0
    except Exception:
        return False


def _role_name(npc):
    return (getattr(npc, "native_role", "") or getattr(npc, "job", "") or "").lower()


def _reply_for(target, kind):
    """A short, human answer -- not a second monologue."""
    rng = getattr(target, "rng", None)
    if kind == "need":
        lines = ("Then we'll find a way.", "I'll see what I can spare.",
                 "You're not the only one carrying that.", "We'll make it stretch.")
    elif kind == "complaint":
        lines = ("Say it plainly, then.", "I hear you. I don't agree.",
                 "We can settle it without shouting.", "That isn't the whole story.")
    elif kind == "praise":
        lines = ("I noticed. Thank you.", "You did the work; I only watched.",
                 "We remember that sort of thing.", "Good. We needed that.")
    else:
        lines = ("Aye. Walk with me a moment.", "I was thinking the same.",
                 "Tell me the rest of it.", "That's a fair point.",
                 "We should speak more often.", "I hadn't looked at it that way.")
    return rng.choice(lines) if rng is not None else lines[0]


def _cold_hint(npc, target, g):
    """One person per camp per few minutes points out the obvious.

    The player should learn the shelter rule from the people living with it,
    not from a manual.  The cooldown is on the CAMP, so a whole settlement
    does not line up to say the same sentence.
    """
    if not _player(target):
        return None
    camp = getattr(npc, "native_camp", None)
    if camp is None or not getattr(camp, "conquered", False):
        return None
    # ASK DURING THE DAY, NOT WHILE THEY ARE IN BED.  This is a warning about
    # the coming night, so the player has time to build the walls and door.
    if bool(getattr(g, "night", False)):
        return None
    if getattr(npc, "asleep", False) or getattr(npc, "in_interior", False):
        return None
    now = float(getattr(g, "now", 0.0))
    if now < float(getattr(camp, "_cold_hint_t", 0.0)):
        return None
    try:
        temp = float(g.world.temperature(camp.x, camp.y))
    except Exception:
        temp = 0.5
    if temp > 0.58:
        return None                         # a hot climate is not this lesson
    cells = climate.room(g, camp)
    bed = getattr(npc, "bed", None)
    if cells and bed is not None and climate.bed_inside(g, camp, bed):
        return None
    if cells:
        text = ("The fire is walled now, but my bedroll is still outside it. "
                "If I move it inside the door before dark, I will sleep warm.")
    else:
        text = ("It will be cold tonight. If we put four walls around the fire "
                "and leave a door, we would all sleep warmer.")
    camp._cold_hint_t = now + 180.0
    reply = ("Then we will build it before the next night.",
             "Good. A wall and a door will do more than another blanket.",
             "Tell the others. We will make room by the fire.")
    rng = getattr(npc, "rng", None)
    return ("need", text, rng.choice(reply) if rng is not None else reply[0])


def _speech(npc, target, g):
    """A line with a little life in it, plus the listener's reply.

    Needs come first only when they are actually urgent.  Product cravings
    do not exist until the person has tried that product once; the rest is
    role, relationship, mood and type.
    """
    name = getattr(npc, "name", "?")
    other = getattr(target, "name", "you")
    role = _role_name(npc)
    rng = getattr(npc, "rng", None)
    pick = (lambda seq: rng.choice(seq)) if rng is not None else (lambda seq: seq[0])
    try:
        if float(getattr(npc, "hunger", 0.0)) >= 80.0:
            return ("need", pick((
                    "The pot has been thin since morning. I can last until supper, but I would not say no to something solid before then.",
                    "My belly has been arguing with my work all day. I could use a proper meal before I make a mistake.",
                    "I have been stretching what little there is. If there is food to spare, I would rather ask than steal.")),
                    _reply_for(target, "need"))
        if float(getattr(npc, "health", 1.0)) < float(getattr(npc, "max_health", 1.0)) * 0.55:
            return ("need", pick((
                    "That last knock left my side aching. If there is medicine in the camp, I would take it.",
                    "I have been hiding a wound so I would not look weak. It is not healing, and I am done pretending.",
                    "I can still work, but not for long like this. A bandage and a little medicine would change that.")),
                    _reply_for(target, "need"))
        if getattr(npc, "slept_outside", False):
            return ("need", pick((
                    "The ground was cold as stone last night. I need a bedroll, or at least a place by the fire.",
                    "I woke up stiff enough that the morning work hurt. Another night outside will cost us more than a bed.",
                    "I am not asking for a house. I am asking not to sleep in the wet again.")),
                    _reply_for(target, "need"))
        if float(getattr(npc, "mood", 50.0)) <= 27.0:
            return ("need", pick((
                    "I keep doing the same work and wondering why it matters. It is not the work -- it is the quiet.",
                    "I am not broken. I am tired in a way sleep does not fix, and I do not know what to do with that.",
                    "Everyone keeps asking me for things. Nobody has asked how I am, so I am telling you.")),
                    _reply_for(target, "need"))

        cold = _cold_hint(npc, target, g)
        if cold is not None:
            return cold

        if _player(target):
            product = getattr(npc, "wants_product", None)
            drink = getattr(npc, "wants_drink", None)
            if (float(getattr(npc, "yearning", 0.0)) >= economy.YEARING_BUY
                    and ((product and _tried(npc, product))
                         or (drink and _tried(npc, drink)))):
                if product and _tried(npc, product) and (not drink or pick((True, False))):
                    return ("need", pick((
                            "When there is a quiet minute, I would not say no to a smoke. My hands will not settle otherwise.",
                            "I have been thinking about a smoke since noon. It is a small thing, but small things get loud by evening.",
                            "If you have a cigar to spare, I will owe you one. My nerves are frayed and my hands need something to do.")),
                            _reply_for(target, "need"))
                return ("need", pick((
                        "If there is a bottle to spare, I would take it. The evening sits easier with one.",
                        "I would not mind a drink tonight. Not to get drunk -- just to put the day down for an hour.",
                        "The work is done and the quiet is starting. A cup would make the quiet feel less like waiting.")),
                        _reply_for(target, "need"))

            if role in ("farmer", "farm"):
                if persona.is_sensing(npc):
                    return ("talk", pick((
                        "The east rows are dry, and the wind has been wrong all day. If the weather holds we get a harvest; if it turns, we lose half of it.",
                        "The soil under the wheat is still cold. I would give it another day before I trust it with seed.",
                        "Something has been at the edge of the field. Not enough to ruin it yet, but enough that I noticed.")),
                        _reply_for(target, "talk"))
                return ("talk", pick((
                        "The fields are talking to each other. What happens in one row keeps showing up in another, and I do not like the pattern.",
                        "I keep thinking the crop is one thing, and the water another, and the work a third. They are all the same argument.",
                        "Give it a season and this camp will be known for what it grows -- if we do not eat the seed corn first.")),
                        _reply_for(target, "talk"))
            if role in ("warrior", "soldier"):
                return ("talk", pick((
                        "The treeline has been quiet all day. Too quiet for my liking. I would rather be bored than surprised.",
                        "Two of the new tracks are old and one is fresh. I have not decided what that means yet.",
                        "A wall is only as good as the people who walk it when nobody is watching.")),
                        _reply_for(target, "talk"))
            if role == "doctor":
                return ("talk", pick((
                        "I have been mending small things all day. A real conversation would be a welcome change.",
                        "Half my work is knowing when to do nothing. The other half is convincing people of it.",
                        "I could use more clean water and less heroism. The heroes are harder to keep alive.")),
                        _reply_for(target, "talk"))
            if role == "trader":
                return ("talk", pick((
                        "The ship's prices are moving again. If you have goods to spare, now is the time to move them.",
                        "A full cart is a promise. An empty one is a story about the road.",
                        "I can find a buyer for almost anything. The difficult part is finding the thing worth carrying.")),
                        _reply_for(target, "talk"))
            if role == "logger":
                return ("talk", pick((
                        "The woodlot is thinning faster than it grows. We should talk about what we leave standing.",
                        "A tree takes a lifetime and a fire takes an afternoon. I think about that more than I used to.",
                        "The wood is good this season. The work is not the problem; the walk back is.")),
                        _reply_for(target, "talk"))
            if role in ("unemployed", ""):
                return ("talk", pick((
                        "I have been watching the camp. Everyone has a place except me. I would like to earn mine.",
                        "I am not afraid of work. I am afraid of being the man nobody notices is missing.",
                        "Give me a job and I will learn it. I have been idle long enough to know the difference.")),
                        _reply_for(target, "talk"))

            aff = 0.0
            try:
                rec = relationships.ensure(npc).get("player")
                if isinstance(rec, dict):
                    aff = float(rec.get("affinity", 0.0))
            except Exception:
                pass
            if aff <= -10.0:
                return ("complaint", pick((
                        "We should settle what happened. I do not like carrying it around, and I doubt you do either.",
                        "I have been biting my tongue since the last decision. I would rather argue with you than resent you.",
                        "You may think it is forgotten. It is not. I want to hear your side before I decide what to do with mine.")),
                        _reply_for(target, "complaint"))
            if aff >= 20.0:
                return ("praise", pick((
                        "You have been good to me. I do not forget that sort of thing.",
                        "I did not expect anyone to notice, but you did. That matters more than you know.",
                        "The camp talks about what you did. I talk about how you did it.")),
                        _reply_for(target, "praise"))
            return ("talk", pick((
                    "You have been quiet lately. Is it the work, the camp, or something you would rather not put into words?",
                    "The camp feels different tonight. I cannot tell whether that is the weather or the people.",
                    "I have been thinking about what we are building here. I am not sure it is the same thing you are building.",
                    "You do not have to answer this, but I would like to know what keeps you going.")),
                    _reply_for(target, "talk"))

        # NPC to NPC: relationship, work and personality, not a random bark.
        aff = 0.0
        try:
            rec = relationships.ensure(npc).get(getattr(target, "id", ""))
            if isinstance(rec, dict):
                aff = float(rec.get("affinity", 0.0))
        except Exception:
            pass
        if aff <= -10.0:
            return ("complaint", pick((
                    "We need to settle what happened between us. I am tired of stepping around it.",
                    "You have been short with me since the argument. If I did something, say it to my face.",
                    "I do not want to work beside someone I am avoiding. Let us have it out and be done.")),
                    _reply_for(target, "complaint"))
        if aff >= 20.0:
            return ("praise", pick((
                    "You have been carrying more than your share lately. I noticed.",
                    "I trust you with the work. That is not a small thing coming from me.",
                    "You make the hard days easier. I hope somebody tells you that besides me.")),
                    _reply_for(target, "praise"))
        if role and role == _role_name(target):
            return ("talk", pick((
                    "Two pairs of hands at the same job. We should compare notes before the day gets away from us.",
                    "You take the left side today and I will take the right. We will cover more ground and argue less.",
                    "Same work, same weather, same complaints. At least we are not doing it alone.")),
                    _reply_for(target, "talk"))
        if persona.is_sensing(npc) and persona.is_intuitive(target):
            return ("talk", pick((
                    "You see the whole pattern; I see the row in front of me. Between us we might get it right.",
                    "I do not always follow your plans, but I know good ground when I stand on it. Tell me where to put my hands.",
                    "You think three steps ahead. I notice the stone under step one. We should use both.")),
                    _reply_for(target, "talk"))
        if persona.is_intuitive(npc) and persona.is_sensing(target):
            return ("talk", pick((
                    "I keep looking at the larger shape of this place. You keep me honest about what is actually under our feet.",
                    "I can see where this is going. You can see what it will cost to get there. I need both answers.",
                    "You notice what I miss when I am thinking too far ahead. Do not stop doing that.")),
                    _reply_for(target, "talk"))
        return ("talk", pick((
                "How are things on your side of the camp? Mine have been stranger than usual.",
                "I heard something today that I cannot make fit. Have you noticed anything odd?",
                "You look like a man carrying a question. I have time for one if you do.",
                "We should compare notes before the day decides for us.")),
                _reply_for(target, "talk"))
    except Exception:
        return ("talk", pick(("We should talk when there is a moment.",
                              "I have something on my mind, but not the words for it yet.")),
                _reply_for(target, "talk"))


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
    kind, text, reply = _speech(speaker, target, g)
    st["active"] = {"speaker": speaker, "target": target, "kind": kind,
                    "text": text, "reply": reply, "reply_at": 0.0,
                    "reply_said": False, "phase": "walk", "until": 0.0}
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
            act["until"] = now + 7.0
            act["reply_at"] = now + 1.5
            try:
                import comm
                comm.spawn_cloud(speaker.x, speaker.y, act["kind"],
                                 text=act["text"], speaker=speaker)
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
            if (not act.get("reply_said", False)
                    and act.get("reply")
                    and now >= float(act.get("reply_at", 0.0))):
                try:
                    import comm
                    comm.spawn_cloud(target.x, target.y, "talk",
                                     text=act.get("reply"), speaker=target)
                    g.toast("%s: %s" % (getattr(target, "name", "Someone"),
                                        act.get("reply")))
                except Exception:
                    pass
                act["reply_said"] = True
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
