"""codec.py -- plain data in, plain data out.

The save layer never pickles a live object.  It reads the *simple* fields off
an object (numbers, flags, strings, and small lists/dicts of those), and gives
whole objects to the small number of providers that know how to write them.
Anything that is not plain data is either handled by an explicit provider or
reported by the audit -- it is never silently dropped.
"""

from __future__ import annotations

import math
import os
import uuid

import persist

# A world-space region.  Terrain and built state are written per region, so a
# save only rewrites the ground the player has actually changed.
REGION = 8192.0


def region_key(x: float, y: float) -> str:
    return "%d_%d" % (int(math.floor(float(x) / REGION)),
                      int(math.floor(float(y) / REGION)))


def game_root() -> str:
    return (os.path.dirname(os.path.abspath(os.sys.executable))
            if getattr(os.sys, "frozen", False)
            else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_simple(value, depth: int = 0) -> bool:
    """Can this value be written as JSON without losing what it means?"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if depth > 4:
        return False
    if isinstance(value, (list, tuple)):
        return all(is_simple(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_simple(v, depth + 1)
                   for k, v in value.items())
    return False


def tidy(value):
    """JSON-safe copy: numpy scalars, tuples and simple containers."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        # numpy scalar
        item = value.item()
        if isinstance(item, (bool, int, float, str)):
            return item
    except Exception:
        pass
    if isinstance(value, (list, tuple)):
        return [tidy(v) for v in value]
    if isinstance(value, set):
        return [tidy(v) for v in sorted(value, key=repr)]
    if isinstance(value, dict):
        return {str(k): tidy(v) for k, v in value.items()}
    return None


def json_default(value):
    """Last-ditch converter for json.dumps.  Never lose the write over it."""
    got = tidy(value)
    return got if got is not None else str(value)


# -- fields ----------------------------------------------------------------
def fields_of(obj) -> list[str]:
    """Every data field on an object, Cython cdef fields included.

    A cdef public field is a ``getset_descriptor`` on the type; ordinary
    Python instance fields live in ``vars()``.  Both are the object's state.
    """
    names = set(vars(obj).keys())
    try:
        for name, desc in type(obj).__dict__.items():
            if type(desc).__name__ == "getset_descriptor":
                names.add(name)
    except Exception:
        pass
    return sorted(n for n in names if not n.startswith("__"))


_SEEN_UNKNOWN: set = set()


def _unknown(label: str, name: str, value) -> None:
    key = (label, name)
    if key in _SEEN_UNKNOWN:
        return
    _SEEN_UNKNOWN.add(key)
    try:
        base = persist.DIR_TEST if persist.is_test() else persist.DIR
        path = os.path.join(base, "save_audit.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write("%s.%s is not plain data (%s) -- not saved\n"
                     % (label, name, type(value).__name__))
    except Exception:
        pass


def dump_fields(obj, skip=(), label: str | None = None) -> dict:
    """Read every simple field, skipping the named ones explicitly."""
    skip = set(skip)
    out: dict = {}
    name_of = label or type(obj).__name__
    for name in fields_of(obj):
        if name in skip or name in ("_save_uid",):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if is_simple(value):
            out[name] = tidy(value)
        else:
            _unknown(name_of, name, value)
    return out


def load_fields(obj, data, skip=()) -> None:
    """Put simple fields back, ignoring anything this object cannot hold."""
    skip = set(skip)
    for name, value in (data or {}).items():
        if name in skip:
            continue
        try:
            setattr(obj, name, value)
        except Exception:
            pass


# -- stable identity --------------------------------------------------------
def uid(obj, prefix: str) -> str:
    """A stable id for a saved object.  Never an id() or a list index."""
    if obj is None:
        return ""
    got = getattr(obj, "_save_uid", None)
    if got:
        return str(got)
    got = "%s:%s" % (prefix, uuid.uuid4().hex[:16])
    try:
        obj._save_uid = got
    except Exception:
        pass
    return got


def ref(obj) -> str | None:
    if obj is None:
        return None
    got = getattr(obj, "_save_uid", None)
    return str(got) if got else None


def idref(obj, prefix: str) -> str | None:
    """A reference that assigns the id if the object has not been given one.

    Snapshot steps run in a fixed order, but references cross that order (a
    player inside a house is written before the houses, a worker before the
    camp that owns him).  Assigning here makes the id stable for the rest of
    the snapshot instead of writing None and losing the reference.
    """
    if obj is None:
        return None
    return uid(obj, prefix)


def set_uid(obj, value) -> None:
    if obj is not None and value:
        try:
            obj._save_uid = str(value)
        except Exception:
            pass


# -- items and inventories --------------------------------------------------
def stack_to_data(stack):
    if stack is None:
        return None
    payload = getattr(stack, "payload", None)
    if not is_simple(payload):
        payload = None
    return [stack.defn.id, int(stack.count),
            getattr(stack, "quality", None), payload,
            getattr(stack, "provenance", None),
            getattr(stack, "plant_kind", None),
            getattr(stack, "genetics", None)]


def data_to_stack(data):
    if not data:
        return None
    import items
    from inventory import ItemStack
    try:
        quality = data[2] if len(data) > 2 else None
        stack = ItemStack(items.get(data[0]), int(data[1]), quality)
        if len(data) > 3 and data[3] is not None:
            stack.payload = data[3]
        if len(data) > 4 and data[4] is not None:
            stack.provenance = data[4]
        if len(data) > 5 and data[5] is not None:
            stack.plant_kind = data[5]
        if len(data) > 6 and data[6] is not None:
            stack.genetics = data[6]
        return stack
    except Exception:
        return None


def inventory_to_data(inv):
    if inv is None:
        return None
    return {
        "capacity": int(getattr(inv, "capacity", len(getattr(inv, "slots", ())))),
        "selected": int(getattr(inv, "selected", 0)),
        "slots": [stack_to_data(s) for s in getattr(inv, "slots", ())],
    }


def inventory_restore(inv, data):
    """Fill an existing inventory in place, preserving references to it."""
    if inv is None or data is None:
        return inv
    from inventory import Inventory
    slots = list(data.get("slots") or [])
    capacity = int(data.get("capacity") or len(slots) or 8)
    want = [data_to_stack(s) for s in slots]
    current = getattr(inv, "slots", None)
    if not isinstance(current, list) or len(current) != capacity:
        inv.slots = [None] * capacity
    else:
        inv.slots[:] = [None] * capacity
    for i, stack in enumerate(want[:capacity]):
        inv.slots[i] = stack
    try:
        inv.capacity = capacity
        inv.selected = int(data.get("selected", 0))
    except Exception:
        pass
    return inv


def new_inventory(data=None, capacity: int = 32):
    from inventory import Inventory
    inv = Inventory(capacity=capacity)
    if data is not None:
        inventory_restore(inv, data)
    return inv


# -- skills -----------------------------------------------------------------
def skills_to_data(sk):
    if sk is None:
        return None
    return dump_fields(sk, label="Skills")


def skills_restore(sk, data):
    if sk is None or not data:
        return sk
    load_fields(sk, data)
    return sk


# -- rectangles -------------------------------------------------------------
def rect_to_data(rect):
    return [int(rect.x), int(rect.y), int(rect.w), int(rect.h)]


def rect_from_data(rec):
    import pygame
    return pygame.Rect(int(rec[0]), int(rec[1]), int(rec[2]), int(rec[3]))
