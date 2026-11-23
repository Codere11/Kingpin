"""mood.py -- pure mood state for the NPC lab and, later, the mind system.

Phase 0 stores thoughts and a target; it does not yet apply them to behaviour.
Keeping the arithmetic here means the thresholds can be tested without a frame.
"""

from __future__ import annotations

DEFAULT_MOOD = 50.0
DEFAULT_TARGET = 50.0
MOOD_MIN = 0.0
MOOD_MAX = 100.0

# The lab's F8 cycle: calm -> strained -> breaking.
MOOD_STEPS = (70.0, 50.0, 35.0, 25.0, 15.0, 5.0)

BREAK_STATES = ("normal", "sad", "annoyed", "berserk", "breaking_spree")


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

    npc.mood_target = target_from_thoughts(npc)
    cur = float(getattr(npc, "mood", 50.0))
    nxt = cur + (npc.mood_target - cur) * 0.25
    if abs(nxt - npc.mood_target) < 0.5:
        nxt = npc.mood_target
    npc.mood = clamp(nxt)


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
