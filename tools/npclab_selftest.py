#!/usr/bin/env python3
"""Headless round-trip for the NPC lab (NPC.md Phase 0 T0).

    python tools/npclab_selftest.py make
    python tools/npclab_selftest.py verify

`make` builds the lab in a test save, writes mind data on one subject, and
saves.  `verify` boots that save and checks the lab, the six types and the
mind fields came back.  It never touches a normal save.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["KINGPIN_OBSERVE"] = "1"

EXPECTED = "/tmp/sw_npclab_expected.json"


def _snapshot(g):
    import npclab
    camp = npclab.ensure(g)
    if camp is None:
        raise AssertionError("no lab camp")
    subjects = list(getattr(g, "_npc_subjects", ()) or ())
    if len(subjects) != len(npclab.SUBJECTS):
        raise AssertionError("want %d subjects, got %d"
                             % (len(npclab.SUBJECTS), len(subjects)))
    out = []
    for n in subjects:
        out.append({
            "name": getattr(n, "name", ""),
            "mbti": getattr(n, "mbti", ""),
            "traits": sorted(getattr(n, "traits", ()) or ()),
            "mood": round(float(getattr(n, "mood", 0.0)), 3),
            "mood_target": round(float(getattr(n, "mood_target", 0.0)), 3),
            "mood_thoughts": dict(getattr(n, "mood_thoughts", {}) or {}),
            "break_state": getattr(n, "break_state", "normal"),
            "trauma_points": round(float(getattr(n, "trauma_points", 0.0)), 3),
            "medicines_received": int(getattr(n, "medicines_received", 0)),
            "mental_known": bool(getattr(n, "mental_known", False)),
        })
    return {"camp": [round(float(camp.x), 1), round(float(camp.y), 1)],
            "subjects": out}


def _make(g):
    import npclab
    import save as savemod
    camp = npclab.reset(g)
    assert camp is not None
    subjects = list(g._npc_subjects)
    # One subject gets a full Phase 0 mind record, so the save test is real.
    n = next(x for x in subjects if getattr(x, "name", "") == "T-ENFP")
    n.traits = ["smart"]
    n.mood = 35.0
    n.mood_target = 25.0
    n.mood_thoughts = {"hungry": {"delta": -6.0, "stacks": 2}}
    n.break_state = "annoyed"
    n.trauma_points = 9.5
    n.medicines_received = 3
    n.mental_known = True
    expected = _snapshot(g)
    with open(EXPECTED, "w") as fh:
        json.dump(expected, fh, indent=1, sort_keys=True)
    savemod.save_now(g, "npclab")
    print("NPCLAB MAKE: %d subjects, saved" % len(subjects))


def _verify(g):
    expected = json.load(open(EXPECTED))
    actual = _snapshot(g)
    problems = []

    def cmp(path, want, got):
        if want != got:
            problems.append("%s: want %r got %r" % (path, want, got))

    cmp("camp", expected["camp"], actual["camp"])
    cmp("subject_count", len(expected["subjects"]), len(actual["subjects"]))
    for want, got in zip(expected["subjects"], actual["subjects"]):
        for key in want:
            cmp("%s.%s" % (want.get("name", "?"), key), want[key],
                got.get(key))
    if problems:
        print("NPCLAB VERIFY: %d PROBLEM(S)" % len(problems))
        for line in problems[:30]:
            print("  " + line)
        raise SystemExit(1)
    print("NPCLAB VERIFY: OK -- %d subjects and their mind fields match"
          % len(actual["subjects"]))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "make"
    import persist
    import save as savemod
    persist.set_test(True)
    persist.set_slot(0)
    if mode == "make":
        savemod.delete(0)
    import engine
    import main as gamemain

    def fake_run(g):
        if mode == "make":
            _make(g)
        else:
            _verify(g)

    engine.run = fake_run
    gamemain.main()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()
        raise
