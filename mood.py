"""mood.py -- pure mood state for the NPC lab and, later, the mind system.

Phase 0 stores thoughts and a target; it does not yet apply them to behaviour.
Keeping the arithmetic here means the thresholds can be tested without a frame.
"""

from __future__ import annotations

import persona

DEFAULT_MOOD = 50.0
DEFAULT_TARGET = 50.0
MOOD_MIN = 0.0
MOOD_MAX = 100.0

# The lab's F8 cycle: calm -> strained -> breaking.
MOOD_STEPS = (70.0, 50.0, 35.0, 25.0, 15.0, 5.0)

BREAK_STATES = ("normal", "sad", "annoyed", "berserk", "breaking_spree")
MINOR_THRESHOLD = 32.0
MAJOR_THRESHOLD = 16.0
MINOR_SECONDS = 240.0
BREAK_ROLL_SECONDS = 20.0
BREAK_COOLDOWN = 300.0


def clamp(value, lo=MOOD_MIN, hi=MOOD_MAX):
    return max(lo, min(hi, float(value)))


def ensure(npc):
    """Give a person the Phase 0 mood fields without touching their values."""
    if getattr(npc, "mood", None) is None:
        try:
            npc.mood = DEFAULT_MOOD
        except Exception:
            pass
    if getattr(npc, "mood_target", None) is None:
        try:
            npc.mood_target = DEFAULT_TARGET
        except Exception:
            pass
    if getattr(npc, "mood_thoughts", None) is None:
        try:
            npc.mood_thoughts = {}
        except Exception:
            pass
    if getattr(npc, "_break_roll_t", None) is None:
        try:
            npc._break_roll_t = float(npc.rng.uniform(0.0, BREAK_ROLL_SECONDS))
        except Exception:
            npc._break_roll_t = 0.0
    if getattr(npc, "_mood_t", None) is None:
        # STAGGER THE FIRST SCAN.  A batch of people all starting at zero
        # would update on the same frame every two seconds; a small random
        # offset spreads the work and the behaviour across the interval.
        try:
            npc._mood_t = float(npc.rng.uniform(0.0, 2.0))
        except Exception:
            try:
                npc._mood_t = 0.0
            except Exception:
                pass
    if not getattr(npc, "break_state", ""):
        try:
            npc.break_state = "normal"
        except Exception:
            pass
    return npc


def set_mood(npc, value, target=None):
    ensure(npc)
    npc.mood = clamp(value)
    npc.mood_target = clamp(npc.mood if target is None else target)
    return npc.mood


def next_step(current):
    """The next value in the lab cycle.  An unknown value starts at 70."""
    try:
        i = MOOD_STEPS.index(float(current))
    except ValueError:
        return MOOD_STEPS[0]
    return MOOD_STEPS[(i + 1) % len(MOOD_STEPS)]


def cycle(npc):
    ensure(npc)
    got = next_step(getattr(npc, "mood", DEFAULT_MOOD))
    npc.mood = got
    npc.mood_target = got
    npc._mood_hold_t = 10.0
    return got


def target_from_thoughts(npc, base=DEFAULT_TARGET):
    """Sum the active thought deltas.  Expiry is checked by the caller later."""
    ensure(npc)
    total = float(base)
    for thought in (getattr(npc, "mood_thoughts", None) or {}).values():
        try:
            total += float(thought.get("delta", 0.0)) * int(thought.get("stacks", 1))
        except Exception:
            continue
    return clamp(total)


def minor_threshold(npc) -> float:
    value = MINOR_THRESHOLD
    if persona.is_feeling(npc):
        value += 8.0
    if persona.is_thinking(npc):
        value -= 6.0
    if persona.has_trait(npc, "traumatized"):
        value *= 0.75
    return clamp(value)


def major_threshold(npc) -> float:
    value = MAJOR_THRESHOLD
    if persona.is_feeling(npc):
        value += 2.0
    if persona.is_thinking(npc):
        value -= 6.0
    if persona.has_trait(npc, "traumatized"):
        value *= 0.75
    return clamp(value)


def set_break(npc, state: str, now: float, seconds: float = MINOR_SECONDS,
              forced: bool = False) -> None:
    ensure(npc)
    npc.break_state = state
    npc.break_until = float(now) + float(seconds)
    npc.break_cooldown = 0.0
    npc._spree_broken = 0
    npc._break_target = None
    npc._break_scan_t = 0.0
    npc._break_action_t = 0.0
    if forced:
        npc._break_hold_t = 60.0
        # A forced lab break is visible even if the subject was content.
        npc.mood = min(float(getattr(npc, "mood", 50.0)),
                       minor_threshold(npc) - 4.0)


def clear_break(npc, now: float) -> None:
    ensure(npc)
    if getattr(npc, "break_state", "normal") in ("sad", "annoyed",
                                                   "berserk", "breaking_spree"):
        try:
            add_thought(npc, "catharsis", 20.0, now, 300.0)
        except Exception:
            pass
    npc.break_state = "normal"
    npc.break_until = 0.0
    npc.break_cooldown = float(now) + BREAK_COOLDOWN
    npc._break_target = None


def force_minor(npc, now: float, state=None) -> str:
    """Test/lab entry point: force sad or annoyed, cycling if no state given."""
    ensure(npc)
    current = getattr(npc, "break_state", "normal")
    if state is None:
        state = {"normal": "sad", "sad": "annoyed",
                 "annoyed": "normal"}.get(current, "sad")
    if state == "normal":
        clear_break(npc, now)
    else:
        set_break(npc, state, now, seconds=MINOR_SECONDS, forced=True)
    return npc.break_state


def force_break(npc, now: float) -> str:
    """Test/lab entry point: cycle normal → sad → annoyed → berserk → spree."""
    ensure(npc)
    current = getattr(npc, "break_state", "normal")
    state = {"normal": "sad", "sad": "annoyed",
             "annoyed": "berserk", "berserk": "breaking_spree",
             "breaking_spree": "normal"}.get(current, "sad")
    if state == "normal":
        clear_break(npc, now)
    else:
        seconds = 240.0 if state in ("sad", "annoyed") else 60.0
        set_break(npc, state, now, seconds=seconds, forced=True)
    return npc.break_state


def move_mult(npc) -> float:
    return 0.65 if getattr(npc, "break_state", "normal") == "sad" else 1.0


def work_mult(npc) -> float:
    state = getattr(npc, "break_state", "normal")
    if state == "sad":
        return 0.50
    if state == "annoyed":
        return 0.75
    return 1.0


def _annoyed_act(npc, now: float) -> None:
    """Annoyed: every ten seconds, insult the nearest low-opinion neighbour."""
    wait = float(getattr(npc, "_annoy_t", 0.0) or 0.0) - 2.0
    if wait > 0.0:
        npc._annoy_t = wait
        return
    npc._annoy_t = 10.0
    try:
        people = npc._camp_people()
    except Exception:
        return
    best, bd = None, 120.0 ** 2
    for other in people:
        if other is npc or not getattr(other, "alive", True):
            continue
        dx = float(getattr(other, "x", 0.0)) - float(getattr(npc, "x", 0.0))
        dy = float(getattr(other, "y", 0.0)) - float(getattr(npc, "y", 0.0))
        d = dx * dx + dy * dy
        if d > bd:
            continue
        try:
            import economy
            oid = getattr(other, "id", None)
            op = float(economy.opinion_of(npc, oid).get(oid, 0.0)) if oid else 0.0
        except Exception:
            op = 0.0
        if op < 30.0:
            best, bd = other, d
    if best is None:
        return
    try:
        import mind
        mind.apply_mood(best, -8.0, reason="insulted by %s" % getattr(npc, "name", "?"))
        add_thought(best, "insulted", -8.0, now, 300.0)
        import economy
        oid = getattr(npc, "id", None)
        if oid:
            opd = economy.opinion_of(best, oid)
            opd[oid] = max(-100.0, float(opd.get(oid, 0.0)) - 8.0)
    except Exception:
        pass


def break_tick(npc, now: float, dt: float) -> None:
    """Break state transitions and minor-break behaviour."""
    state = getattr(npc, "break_state", "normal")
    if state in ("sad", "annoyed"):
        hold = float(getattr(npc, "_break_hold_t", 0.0) or 0.0)
        if hold > 0.0:
            npc._break_hold_t = max(0.0, hold - dt)
        else:
            threshold = minor_threshold(npc)
            if (now >= float(getattr(npc, "break_until", 0.0))
                    or float(getattr(npc, "mood", 50.0)) > threshold + 10.0):
                clear_break(npc, now)
                return
        if state == "annoyed":
            _annoyed_act(npc, now)
        return
    if state != "normal":
        return
    if now < float(getattr(npc, "break_cooldown", 0.0) or 0.0):
        return
    wait = float(getattr(npc, "_break_roll_t", 0.0) or 0.0) - dt
    if wait > 0.0:
        npc._break_roll_t = wait
        return
    npc._break_roll_t = BREAK_ROLL_SECONDS
    mood_now = float(getattr(npc, "mood", 50.0))
    if mood_now > minor_threshold(npc):
        return
    rng = getattr(npc, "rng", None)
    if rng is None:
        return
    if mood_now <= major_threshold(npc):
        major_chance = (0.15 if persona.is_feeling(npc)
                        else (0.35 if persona.is_thinking(npc) else 0.25))
        if rng.random() < major_chance:
            state = "berserk" if rng.random() < 0.5 else "breaking_spree"
            set_break(npc, state, now, seconds=60.0)
            return
    if persona.is_feeling(npc):
        chance = 0.60
    elif persona.is_thinking(npc):
        chance = 0.25
    else:
        chance = 0.40
    if rng.random() >= chance:
        return
    sad_score = 0.0
    if persona.axis(npc, "IE") == "I":
        sad_score += 1.0
    if persona.is_feeling(npc):
        sad_score += 1.0
    if persona.axis(npc, "JP") == "P":
        sad_score += 0.5
    state = "sad" if rng.random() * 2.5 < sad_score else "annoyed"
    set_break(npc, state, now, seconds=MINOR_SECONDS)


def add_thought(npc, tid: str, delta: float, now: float,
                seconds: float = 180.0, stacks: int = 1) -> None:
    """Add or refresh a reason.  Same id stacks, so two insults hurt more."""
    ensure(npc)
    thoughts = npc.mood_thoughts
    old = thoughts.get(tid)
    old_stacks = int(old.get("stacks", 1)) if isinstance(old, dict) else 0
    thoughts[tid] = {
        "delta": float(delta),
        "expires_at": float(now) + float(seconds),
        "stacks": max(1, min(3, old_stacks + int(stacks))),
    }


def ensure_thought(npc, tid: str, delta: float, now: float,
                   seconds: float = 120.0) -> None:
    """Keep an environmental thought fresh without stacking every scan."""
    ensure(npc)
    thoughts = npc.mood_thoughts
    old = thoughts.get(tid)
    if (isinstance(old, dict)
            and float(old.get("expires_at", 0.0)) > float(now) + 2.0):
        old["delta"] = float(delta)
        return
    thoughts[tid] = {"delta": float(delta),
                     "expires_at": float(now) + float(seconds),
                     "stacks": 1}


def tick(npc, now: float, dt: float, interval: float = 2.0) -> None:
    """Cheap periodic mood step: once every two seconds, never per frame.

    Environmental thoughts (hunger, injury, exhaustion) are refreshed here;
    event thoughts (insult, praise, wronged, treated) are added by the systems
    that caused them and expire on their own.
    """
    ensure(npc)
    hold = float(getattr(npc, "_mood_hold_t", 0.0) or 0.0)
    if hold > 0.0:
        npc._mood_hold_t = max(0.0, hold - dt)
        return
    wait = float(getattr(npc, "_mood_t", 0.0) or 0.0) - dt
    if wait > 0.0:
        npc._mood_t = wait
        return
    npc._mood_t = interval
    thoughts = npc.mood_thoughts
    for tid, thought in list(thoughts.items()):
        try:
            if float(thought.get("expires_at", 0.0)) <= float(now):
                thoughts.pop(tid, None)
        except Exception:
            thoughts.pop(tid, None)

    hunger = float(getattr(npc, "hunger", 0.0) or 0.0)
    if hunger >= 85.0:
        ensure_thought(npc, "starving", -12.0, now)
        thoughts.pop("hungry", None)
    elif hunger >= 50.0:
        ensure_thought(npc, "hungry", -5.0, now)
        thoughts.pop("starving", None)
    else:
        thoughts.pop("hungry", None)
        thoughts.pop("starving", None)

    health = float(getattr(npc, "health", 0.0) or 0.0)
    top = float(getattr(npc, "max_health", 1.0) or 1.0)
    ratio = health / top if top > 0.0 else 1.0
    if ratio < 0.35:
        ensure_thought(npc, "badly_hurt", -12.0, now)
        thoughts.pop("hurt", None)
    elif ratio < 0.75:
        ensure_thought(npc, "hurt", -6.0, now)
        thoughts.pop("badly_hurt", None)
    else:
        thoughts.pop("hurt", None)
        thoughts.pop("badly_hurt", None)

    stamina = float(getattr(npc, "stamina", 100.0) or 0.0)
    stamina_top = float(getattr(npc, "max_stamina", 100.0) or 100.0)
    if stamina_top > 0.0 and stamina / stamina_top < 0.20:
        ensure_thought(npc, "exhausted", -4.0, now)
    else:
        thoughts.pop("exhausted", None)

    try:
        import needs as _needs
        _needs.update(npc, now)
    except Exception:
        pass
    npc.mood_target = target_from_thoughts(npc)
    cur = float(getattr(npc, "mood", 50.0))
    nxt = cur + (npc.mood_target - cur) * 0.25
    if abs(nxt - npc.mood_target) < 0.5:
        nxt = npc.mood_target
    npc.mood = clamp(nxt)
    try:
        break_tick(npc, now, interval)
    except Exception:
        pass


def observed_mood(npc) -> float:
    """The mood the player can read without a medical record.

    It is rounded to the nearest 20: 65 reads as 60, 73 as 80.  The real
    value still drives behaviour; only the card is blurred.
    """
    value = clamp(getattr(npc, "mood", DEFAULT_MOOD))
    return clamp(int(value / 20.0 + 0.5) * 20.0)


def biggest_drivers(npc):
    """The strongest positive and negative reason, for an unread mind."""
    ensure(npc)
    pos = None
    neg = None
    for tid, thought in (getattr(npc, "mood_thoughts", None) or {}).items():
        try:
            total = float(thought.get("delta", 0.0)) * int(thought.get("stacks", 1))
        except Exception:
            continue
        rec = (str(tid).replace("_", " "), total)
        if total > 0.0 and (pos is None or total > pos[1]):
            pos = rec
        elif total < 0.0 and (neg is None or total < neg[1]):
            neg = rec
    return pos, neg


def thought_summary(npc, limit=4):
    ensure(npc)
    thoughts = getattr(npc, "mood_thoughts", None) or {}
    if not thoughts:
        return "none"
    parts = []
    for key, thought in list(thoughts.items())[:limit]:
        try:
            parts.append("%s %+.0f" % (key, float(thought.get("delta", 0.0))))
        except Exception:
            parts.append(str(key))
    if len(thoughts) > limit:
        parts.append("...")
    return ", ".join(parts)
