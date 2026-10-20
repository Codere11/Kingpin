"""EVERY DECISION MADE ABOUT THE PLAYER, WRITTEN DOWN.

Who takes him as a target and why; who arms himself because he KNOWS him; who
sets aggression; who hurts him.  ~/.kingpin_saves/player.log
"""
import os
import time

_PATH = os.path.join(os.path.expanduser("~/.kingpin_saves"), "player.log")
_T0 = time.time()
_ON = True


def reset() -> None:
    global _T0
    _T0 = time.time()
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        open(_PATH, "w").close()
    except Exception:
        pass


def log(*parts) -> None:
    if not _ON:
        return
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, "a") as f:
            f.write("%8.2f  " % (time.time() - _T0)
                    + " ".join(str(x) for x in parts) + "\n")
    except Exception:
        pass
