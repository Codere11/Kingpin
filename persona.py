"""persona.py -- the deterministic MBTI-like type of a person.

This module is deliberately pure: it imports no game modules and touches no
world state.  A type is derived from a stable key (the NPC's id, or its save
uid), never from the live RNG and never from id().  The same person therefore
has the same type after every load.

Phase 0 only stores and displays the type.  The work/skill multipliers are
here so Phase 1 can call them from one place instead of scattering rules.
"""

from __future__ import annotations

import hashlib

# The 16 types and the commonly cited US adult distribution, rounded to 100.
TYPE_WEIGHTS = {
    "ISFJ": 13.8, "ESFJ": 12.3,
    "ISTJ": 11.6, "ESTJ": 8.7,
    "ISFP": 8.8,  "ESFP": 8.2,
    "ENFP": 8.1,  "ISTP": 5.4,
    "INFP": 4.4,  "ESTP": 4.3,
    "INTP": 3.3,  "ENTP": 3.2,
    "ENFJ": 2.5,  "INTJ": 2.1,
    "ENTJ": 1.8,  "INFJ": 1.5,
}
TYPES = tuple(TYPE_WEIGHTS)

# One table for job affinity.  Remove a job here and it becomes neutral.
JOB_AXIS = {
    "farmer": "S", "logger": "S", "soldier": "S", "miner": "S",
    "weaver": "S", "spiceman": "S", "animal_handler": "S",
    "smith": "S", "gunsmith": "S",
    "artisan": "N", "researcher": "N", "doctor": "N",
}

MATCH_WORK = 1.15
MISS_WORK = 0.85
MATCH_GAIN = 1.25
MISS_GAIN = 0.75

TRAITS = ("smart", "stupid", "strong", "green_thumb", "traumatized")


def _key(npc) -> str:
    """A stable string for a person.  Never id(obj)."""
    ident = getattr(npc, "id", "") or ""
    if ident:
        return "id:" + str(ident)
    uid = getattr(npc, "_save_uid", "") or ""
    if uid:
        return "uid:" + str(uid)
    name = getattr(npc, "name", "") or ""
    x = round(float(getattr(npc, "x", 0.0)), 1)
    y = round(float(getattr(npc, "y", 0.0)), 1)
    return "where:%s|%s|%s" % (name, x, y)


def assign_from_key(key: str) -> str:
    """Weighted draw from the table, deterministic in `key`."""
    digest = hashlib.blake2b(str(key).encode("utf-8"), digest_size=8).digest()
    roll = (int.from_bytes(digest, "big") % 10000) / 100.0
    acc = 0.0
    for name, weight in TYPE_WEIGHTS.items():
        acc += weight
        if roll < acc:
            return name
    return "ISFJ"


def assign(npc, force: bool = False) -> str:
    """Assign and store a type, unless the person already has one."""
    current = getattr(npc, "mbti", "") or ""
    if current and not force:
        return current
    got = assign_from_key(_key(npc))
    try:
        npc.mbti = got
    except Exception:
        pass
    return got


def ensure(npc, force: bool = False) -> str:
    """Normalise Phase 0 fields, then make sure a type exists."""
    if getattr(npc, "traits", None) is None:
        try:
            npc.traits = []
        except Exception:
            pass
    if getattr(npc, "mood_thoughts", None) is None:
        try:
            npc.mood_thoughts = {}
        except Exception:
            pass
    for name, default in (("trauma_points", 0.0),
                          ("medicines_received", 0),
                          ("mental_known", False),
                          ("mood_target", 50.0),
                          ("break_until", 0.0),
                          ("break_cooldown", 0.0),
                          ("frustration", 0.0)):
        if getattr(npc, name, None) is None:
            try:
                setattr(npc, name, default)
            except Exception:
                pass
    if not getattr(npc, "break_state", ""):
        try:
            npc.break_state = "normal"
        except Exception:
            pass
    return assign(npc, force=force)


def axis(npc, pair: str) -> str:
    """Return the person's letter on one of the four axis pairs."""
    t = getattr(npc, "mbti", "") or ""
    if pair == "IE":
        return t[:1] or "I"
    if pair == "SN":
        return t[1:2] or "S"
    if pair == "FT":
        return t[2:3] or "F"
    if pair == "JP":
        return t[3:4] or "J"
    return ""


def is_sensing(npc) -> bool:
    return axis(npc, "SN") == "S"


def is_intuitive(npc) -> bool:
    return axis(npc, "SN") == "N"


def is_feeling(npc) -> bool:
    return axis(npc, "FT") == "F"


def is_thinking(npc) -> bool:
    return axis(npc, "FT") == "T"


def job_axis(job) -> str:
    return JOB_AXIS.get(str(job or ""), "")


def work_mult(npc, job) -> float:
    """Job speed multiplier from S/N affinity, and the F artisan bonus."""
    side = job_axis(job)
    out = 1.0
    if side == "S":
        out = MATCH_WORK if is_sensing(npc) else MISS_WORK
    elif side == "N":
        out = MATCH_WORK if is_intuitive(npc) else MISS_WORK
    if str(job or "") == "artisan" and is_feeling(npc):
        out *= 1.15
    return out


def has_trait(npc, trait: str) -> bool:
    return trait in (getattr(npc, "traits", None) or ())


def can_green_thumb(npc) -> bool:
    """Green Thumb is the one hard MBTI gate: S only, never N."""
    return is_sensing(npc) and not has_trait(npc, "green_thumb")


def skill_gain_mult(npc, skill: str) -> float:
    """Born-trait skill gain.  Use gain_mult_for_job() to add affinity."""
    out = 1.0
    if has_trait(npc, "smart"):
        out *= 1.25
    if has_trait(npc, "stupid"):
        out *= 0.75
    if has_trait(npc, "strong") and str(skill) == "axe":
        out *= 1.30
    # Job affinity is applied by the caller when it knows the job; this
    # function deliberately does not guess.
    return out


def gain_mult_for_job(npc, job, skill: str) -> float:
    """Born traits combined with the S/N job-affinity gain."""
    out = skill_gain_mult(npc, skill)
    side = job_axis(job)
    if side == "S":
        out *= MATCH_GAIN if is_sensing(npc) else MISS_GAIN
    elif side == "N":
        out *= MATCH_GAIN if is_intuitive(npc) else MISS_GAIN
    return out
