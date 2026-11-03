"""Tiny JSON saves, one file per slot. Holds built houses + their contents."""

from __future__ import annotations

import json
import os
import sys
import time

# A saves/ DIRECTORY, beside the game, where you can see it. It works from
# source and from the built executable: next to the folder on one, next to the
# .exe on the other.
import sys as _sys
_HERE = (os.path.dirname(os.path.abspath(_sys.executable))
         if getattr(_sys, "frozen", False)
         else os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_HERE, "saves")
DIR_TEST = os.path.join(_HERE, "saves_test")
LEGACY = os.path.expanduser("~/.kingpin_save.json")
_OLD_DIR = os.path.expanduser("~/.kingpin_saves")
SLOTS = 4

_slot = 0
_test = False


def crash(text: str) -> None:
    """A traceback from a crash, written where the player can find it.

    A crash used to take the window and the evidence with it, leaving nothing
    to go on but the memory of what one was doing at the time -- and a guess
    dressed up as a diagnosis is worse than no diagnosis at all. Now the real
    stack is left behind in saves/crash.log.
    """
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(os.path.join(DIR, "crash.log"), "a") as fh:
            fh.write("\n==== %s ====\n%s\n"
                     % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass


def _log(text: str) -> None:
    """A line about what the save system just did, in the saves folder."""
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(os.path.join(DIR, "persist.log"), "a") as fh:
            fh.write(text + "\n")
    except Exception:
        pass


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


def path(slot: int) -> str:
    base = DIR_TEST if _test else DIR
    return os.path.join(base, "save_%d.json" % int(slot))


def _migrate() -> None:
    """Bring old saves across: one spare file, and the whole old directory."""
    if _test:
        return
    try:
        os.makedirs(DIR, exist_ok=True)
        if os.path.exists(LEGACY) and not os.path.exists(path(0)):
            os.replace(LEGACY, path(0))
        if os.path.isdir(_OLD_DIR):                 # the old hidden folder
            import shutil
            for name in os.listdir(_OLD_DIR):
                if not name.startswith("save_") or not name.endswith(".json"):
                    continue
                src = os.path.join(_OLD_DIR, name)
                dst = os.path.join(DIR, name)
                if os.path.exists(dst):
                    continue
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    continue
                # AND AWAY WITH THE ORIGINAL. Copying left the old file in
                # place, so the next launch migrated the deleted save straight
                # back in: a save you could not get rid of. It was one file in
                # two places and the delete only ever saw one of them.
                try:
                    os.remove(src)
                except Exception:
                    pass
    except Exception:
        pass


_migrated = False


def _ensure_migrated() -> None:
    global _migrated
    if not _migrated:
        _migrated = True
        _migrate()


def exists(slot: int) -> bool:
    _ensure_migrated()
    return os.path.exists(path(slot))


def delete(slot: int) -> bool:
    """Remove a save. Returns whether it actually went, and says why not.

    It used to swallow every error in silence, so a delete that failed looked
    exactly like a button that does nothing.
    """
    _ensure_migrated()
    target = path(slot)
    if not os.path.exists(target):
        _log("delete: slot %d had no file at %s" % (slot, target))
        return False
    legacy = os.path.join(_OLD_DIR, os.path.basename(target))
    gone = False
    for path_ in (target, legacy):
        try:
            if os.path.exists(path_):
                os.remove(path_)
                gone = True
                _log("delete: removed %s" % path_)
        except Exception as exc:
            _log("delete FAILED for %s: %r" % (path_, exc))
    return gone


def write_binary(obj, slot: int | None = None) -> bool:
    """Write a save as pickle rather than JSON.

    The same world is 2.1 MB instead of 4.5, and encoding it is 27 ms instead
    of 162 -- measured, not guessed. That is most of the save hitch gone.
    """
    import pickle
    target = path(slot if slot is not None else _slot)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, target)
        return True
    except Exception as exc:
        _log("pickle save FAILED for %s: %r" % (target, exc))
        return False


def read_binary(slot: int | None = None):
    import pickle
    target = path(slot if slot is not None else _slot)
    for candidate in (target, target.replace(".json", ".pkl")):
        try:
            with open(candidate, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            continue
    return None


def read(slot: int | None = None) -> dict:
    _migrate()
    target = _slot if slot is None else int(slot)
    try:
        with open(path(target), "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _jsonable(obj):
    """Last-ditch converter so one odd value can never lose the whole save."""
    try:
        return obj.item()          # numpy scalars -> python int/float/bool
    except Exception:
        pass
    if isinstance(obj, (set, tuple)):
        return list(obj)
    return str(obj)


def write(data: dict, slot: int | None = None) -> None:
    os.makedirs(os.path.dirname(path(slot if slot is not None else _slot)),
                exist_ok=True)
    target = _slot if slot is None else int(slot)
    path_ = path(target)
    try:
        os.makedirs(os.path.dirname(path_), exist_ok=True)
        tmp = path_ + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, default=_jsonable)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path_)          # atomic: never a half-written save
    except Exception as exc:            # never fail silently again
        sys.stderr.write("KINGPIN SAVE FAILED: %r\n" % (exc,))
        try:
            with open(os.path.join(os.path.dirname(path_), "save_error.txt"),
                      "w", encoding="utf-8") as log:
                log.write("KINGPIN SAVE FAILED: %r\n" % (exc,))
        except Exception:
            pass


def summary(slot: int):
    """(exists, houses, coins) for the save-slot menu."""
    data = read(slot)
    if not data:
        return (exists(slot), 0, 0)
    coins = 0
    for stack in data.get("inventory", []) or []:      # carried coins
        if stack and stack[0] == "coin":
            coins += int(stack[1])
    for house in data.get("houses", []):
        for stack in house.get("chest", []) or []:      # stashed coins
            if stack and stack[0] == "coin":
                coins += int(stack[1])
    return (True, len(data.get("houses", [])), coins)


def stack_to_data(stack):
    if stack is None:
        return None
    pay = stack.payload if isinstance(getattr(stack, "payload", None), str) else None
    return [stack.defn.id, int(stack.count), stack.quality, pay]


def data_to_stack(data):
    if not data:
        return None
    import items
    from inventory import ItemStack

    try:
        quality = data[2] if len(data) > 2 else None
        stack = ItemStack(items.get(data[0]), int(data[1]), quality)
        if len(data) > 3 and data[3]:
            stack.payload = data[3]
        return stack
    except Exception:
        return None
