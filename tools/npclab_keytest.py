#!/usr/bin/env python3
"""Headless check that engine really routes F6/F7/F8 to the NPC lab.

The real engine loop is used; only pygame.event.get is replaced for the first
frame with a synthetic key sequence, then QUIT.  This catches a key branch
that exists in the source but is unreachable behind another handler.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["KINGPIN_OBSERVE"] = "1"


def main():
    import pygame
    import persist
    persist.set_test(True)
    persist.set_slot(0)

    import engine
    import main as gamemain

    real_run = engine.run
    state = {"done": False}

    def fake_get(*_args, **_kwargs):
        if state["done"]:
            return []
        state["done"] = True
        return [
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6),
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F7),
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8),
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9),
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F10),
            pygame.event.Event(pygame.QUIT),
        ]

    def wrapped_run(g):
        pygame.event.get = fake_get
        real_run(g)
        camp = getattr(g, "_npc_lab", None)
        subjects = list(getattr(g, "_npc_subjects", ()) or ())
        assert camp is not None, "F6 did not build the lab"
        assert camp.x < g.player.x, ("lab is east of the player (the ocean "
                                     "side): %.1f vs %.1f"
                                     % (camp.x, g.player.x))
        try:
            import world as _world
            _coast = _world.coast_x(camp.y, g.world.seed)
            assert camp.x < _coast - 900.0, ("lab is too close to the coast: "
                                             "%.1f vs %.1f"
                                             % (camp.x, _coast))
        except AssertionError:
            raise
        except Exception:
            pass
        assert len(subjects) == 8, "lab has %d subjects" % len(subjects)
        assert g._npc_sel == 1, "F7 did not advance selection: %r" % g._npc_sel
        n = subjects[1]
        assert n.mood == 35.0, "F8 did not change mood: %r" % n.mood
        assert n.mental_known and n.medicines_received == 1, \
            "F10 did not unlock the medical record"
        assert n.break_state in ("sad", "annoyed"), \
            "F9 did not force a minor break: %r" % n.break_state
        # The card is the only place the mind is shown, and only after that.
        _unknown = g.persona_card._medical_lines(subjects[0])
        _utext = " ".join(line for line, _c in _unknown)
        assert "No medical record" in _utext and "MBTI" not in _utext
        _known = g.persona_card._medical_lines(n)
        _ktext = " ".join(line for line, _c in _known)
        assert "MBTI" in _ktext and "Medicine 1" in _ktext
        g.persona = subjects[0]
        g.npc_card_open = True
        g.draw_persona()
        g.draw_persona_card()
        assert getattr(g, "_persona_subject", None) is subjects[0]
        # A click on a lab native (not a conquered worker) opens the card.
        g.npc_card_open = False
        g.persona = None
        _target = subjects[2]
        g.cam_x = _target.x
        g.cam_y = _target.y
        assert g.click_a_man((0, 0)) is True
        assert g.npc_card_open and g.persona is _target
        import npclab
        npclab.give_medicine(g)
        assert _target.mental_known and _target.medicines_received == 1
        import persona
        for sub in subjects:
            assert getattr(sub, "mbti", ""), ("no MBTI on %s"
                                              % getattr(sub, "name", "?"))
        # A generated native, not one the lab typed by hand: this proves the
        # NPC constructor assigns a type too.
        natives = [x for x in getattr(g, "_native_people", ())
                   if not str(getattr(x, "id", "")).startswith("lab_")]
        assert natives and all(getattr(x, "mbti", "") for x in natives), \
            "generated native NPC without MBTI"
        assert all(getattr(x, "traits_rolled", False) for x in natives), \
            "generated native NPC without rolled traits"
        assert all(not str(getattr(x, "name", "")).startswith("T-")
                   for x in subjects), "type leaked into a subject's name"
        import native as _native_names
        assert all(getattr(x, "name", "") in _native_names._NAMES
                   for x in subjects), "lab subject has a non-native name"
        sf = next(x for x in subjects
                  if x.native_role == "farmer" and persona.is_sensing(x))
        nf = next(x for x in subjects
                  if x.native_role == "farmer" and persona.is_intuitive(x))
        assert sf.farm_plot is not None and nf.farm_plot is not None
        assert persona.is_sensing(sf) and persona.is_intuitive(nf)
        assert persona.work_mult(sf, "farmer") > persona.work_mult(nf, "farmer")
        print("NPCLAB KEYTEST: PASS -- F6 built 8, F7 selected %s, F8 mood %.0f, "
              "S/N farmer affinity %.2f/%.2f"
              % (getattr(n, "name", "?"), n.mood,
                 persona.work_mult(sf, "farmer"),
                 persona.work_mult(nf, "farmer")))

    engine.run = wrapped_run
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
