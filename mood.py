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
