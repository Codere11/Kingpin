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
        assert len(subjects) == 6, "lab has %d subjects" % len(subjects)
        assert g._npc_sel == 1, "F7 did not advance selection: %r" % g._npc_sel
        n = subjects[1]
        assert n.mood == 35.0, "F8 did not change mood: %r" % n.mood
        print("NPCLAB KEYTEST: PASS -- F6 built 6, F7 selected %s, F8 mood %.0f"
              % (getattr(n, "name", "?"), n.mood))

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
