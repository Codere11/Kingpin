#!/usr/bin/env python3
"""Fast, headless checks for persona/mood foundations (NPC.md Phase 0/1).

    python tools/persona_selftest.py

No pygame, no world, no save files.  If this fails, do not build the game.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import mood
import persona


class P:
    def __init__(self, typ="", **kw):
        self.id = kw.pop("id", "")
        self.name = kw.pop("name", "")
        self.x = kw.pop("x", 0.0)
        self.y = kw.pop("y", 0.0)
        self.mbti = typ
        self.traits = kw.pop("traits", [])
        self.mood_thoughts = kw.pop("mood_thoughts", {})
        self.mood = kw.pop("mood", 50.0)
        self.mood_target = kw.pop("mood_target", 50.0)
        self.break_state = kw.pop("break_state", "normal")
        self.trauma_points = 0.0
        self.medicines_received = 0
        self.mental_known = False
        self.break_until = 0.0
        self.break_cooldown = 0.0
        self.frustration = 0.0
        for key, value in kw.items():
            setattr(self, key, value)


def check_distribution():
    n = 100_000
    counts = {t: 0 for t in persona.TYPES}
    for i in range(n):
        counts[persona.assign_from_key("person:%d" % i)] += 1
    for typ, expected in persona.TYPE_WEIGHTS.items():
        got = 100.0 * counts[typ] / n
        assert abs(got - expected) < 0.8, (typ, got, expected)
    return counts


def check_assignment():
    a = P(id="man_7")
    b = P(id="man_7")
    t1 = persona.assign(a)
    t2 = persona.assign(b)
    assert t1 == t2 and t1 in persona.TYPE_WEIGHTS
    assert persona.assign(a) == t1
    assert persona.assign(a, force=True) == t1
    no_id = P(name="Nameless", x=12.0, y=-4.0)
    t3 = persona.assign(no_id)
    assert t3 == persona.assign(P(name="Nameless", x=12.0, y=-4.0))
    return t1, t3


def check_jobs():
    s = P("ISTJ")
    n = P("INTJ")
    f = P("INFJ")
    assert persona.work_mult(s, "farmer") == persona.MATCH_WORK
    assert persona.work_mult(n, "farmer") == persona.MISS_WORK
    assert persona.work_mult(f, "artisan") > persona.MATCH_WORK
    assert persona.work_mult(s, "artisan") == persona.MISS_WORK
    assert persona.work_mult(s, "unemployed") == 1.0
    assert persona.gain_mult_for_job(s, "farmer", "farming") == persona.MATCH_GAIN
    assert persona.gain_mult_for_job(n, "farmer", "farming") == persona.MISS_GAIN
    return True


def check_green_thumb():
    assert persona.can_green_thumb(P("ISFJ")) is True
    assert persona.can_green_thumb(P("INTJ")) is False
    assert persona.can_green_thumb(P("ISFJ", traits=["green_thumb"])) is False
    assert persona.can_green_thumb(P("INTJ", traits=["green_thumb"])) is False
    return True


def check_traits():
    smart = P("ISTJ", traits=["smart"])
    stupid = P("ISTJ", traits=["stupid"])
    strong = P("ISTJ", traits=["strong"])
    assert persona.skill_gain_mult(smart, "farming") == 1.25
    assert persona.skill_gain_mult(stupid, "farming") == 0.75
    assert persona.skill_gain_mult(strong, "axe") == 1.30
    assert persona.skill_gain_mult(strong, "farming") == 1.0
    assert persona.melee_mult(strong) == 1.30

    # Born traits are deterministic and Smart/Stupid never coexist.
    a = P("ISTJ", id="born_7")
    b = P("ISTJ", id="born_7")
    persona.ensure(a)
    persona.ensure(b)
    assert a.traits == b.traits
    assert not ("smart" in a.traits and "stupid" in a.traits)

    # Trauma accumulates harder for F, softer for T, and becomes a trait.
    f = P("INFJ")
    t = P("INTJ")
    persona.add_trauma(f, 10)
    persona.add_trauma(t, 10)
    assert f.trauma_points == 15.0
    assert t.trauma_points == 7.5
    f.trauma_points = 99.0
    assert persona.add_trauma(f, 1)
    assert persona.has_trait(f, "traumatized")
    return True


def check_green_thumb_learning():
    class R:
        def random(self):
            return 0.0
    class Skills:
        farming = 8.0
    s = P("ISFJ")
    s.skills = Skills()
    assert persona.maybe_green_thumb(s, R())
    assert persona.has_trait(s, "green_thumb")
    n = P("INTJ")
    n.skills = Skills()
    assert not persona.maybe_green_thumb(n, R())
    return True


def check_minor_breaks():
    p = P("INTJ")
    mood.set_break(p, "sad", 100.0, forced=True)
    assert mood.move_mult(p) == 0.65
    assert mood.work_mult(p) == 0.50
    assert mood.force_minor(p, 110.0) == "annoyed"
    assert mood.move_mult(p) == 1.0
    assert mood.work_mult(p) == 0.75
    assert mood.force_minor(p, 120.0) == "normal"
    assert mood.move_mult(p) == 1.0 and mood.work_mult(p) == 1.0
    f = P("INFJ")
    t = P("INTJ")
    assert mood.minor_threshold(f) > mood.minor_threshold(t)
    return True


def check_mood():
    p = P()
    mood.ensure(p)
    assert p.mood == 50.0
    assert mood.cycle(p) == 35.0
    assert p.mood == p.mood_target == 35.0
    assert mood.clamp(-5) == 0.0 and mood.clamp(500) == 100.0
    p.mood_thoughts = {"hungry": {"delta": -8.0, "stacks": 2}}
    assert mood.target_from_thoughts(p, base=50.0) == 34.0
    assert "hungry" in mood.thought_summary(p)
    p.mood = 65.0
    assert mood.observed_mood(p) == 60.0
    p.mood = 73.0
    assert mood.observed_mood(p) == 80.0

    q = P()
    q.hunger = 90.0
    q.health = 40.0
    q.max_health = 100.0
    q.stamina = 10.0
    q.max_stamina = 100.0
    mood.tick(q, 10.0, 2.0)
    assert "starving" in q.mood_thoughts
    assert "hurt" in q.mood_thoughts
    assert "exhausted" in q.mood_thoughts
    assert q.mood_target == 28.0
    assert q.mood == 44.5
    mood.add_thought(q, "insult", -10.0, 10.0, seconds=1.0)
    mood.tick(q, 20.0, 2.0)
    assert "insult" not in q.mood_thoughts
    return True


def main():
    check_distribution()
    check_assignment()
    check_jobs()
    check_green_thumb()
    check_traits()
    check_green_thumb_learning()
    check_minor_breaks()
    check_mood()
    print("PERSONA SELFTEST: PASS")


if __name__ == "__main__":
    main()
