"""persist.py -- where runtime files live, and the crash log.

The save data itself lives in the :mod:`save` package.  This module keeps the
two things the rest of the game still needs: the runtime directory (so logs
and saves sit beside the game, source or executable) and a crash log the
player can actually find.
"""

from __future__ import annotations

import os
import sys
import time

_HERE = (os.path.dirname(os.path.abspath(sys.executable))
         if getattr(sys, "frozen", False)
         else os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_HERE, "saves")
DIR_TEST = os.path.join(_HERE, "saves_test")
SLOTS = 4

_slot = 0
_test = False


def set_test(flag: bool) -> None:
    global _test
    _test = bool(flag)


def is_test() -> bool:
    return _test


def set_slot(slot: int) -> None:
    global _slot
    _slot = int(slot)


def get_slot() -> int:
    return _slot


def crash(text: str) -> None:
    """A traceback from a crash, written where the player can find it."""
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(os.path.join(DIR, "crash.log"), "a") as fh:
            fh.write("\n==== %s ====\n%s\n"
                     % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass
