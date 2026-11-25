"""itemstory.py -- a thing remembers where it came from.

This is Phase 1 of the provenance spine: unique objects carry a small,
plain-data history (maker, origin, owner and events).  It is deliberately
generic; cooking, blacksmithing, theft and fire all write the same records.
"""

from __future__ import annotations

import math
import uuid

import pygame


def is_unique(item_id: str) -> bool:
    try:
        import items
        return not bool(items.get(item_id).stackable)
    except Exception:
        return False


def new_uid() -> str:
    return uuid.uuid4().hex[:12]


def make(item_id: str, maker=None, origin=None, owner=None, now=0.0) -> dict:
    return {
        "uid": new_uid(),
        "item": str(item_id),
        "maker": _name(maker),
        "origin": _name(origin),
        "owner": _name(owner),
        "made_at": round(float(now), 1),
        "history": [],
    }


def _name(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(getattr(value, "name", "") or getattr(value, "id", "") or value)


def ensure(stack, maker=None, origin=None, owner=None, now=0.0) -> dict:
    prov = getattr(stack, "provenance", None)
    if isinstance(prov, dict):
        return prov
    if not is_unique(getattr(stack.defn, "id", "")):
        return {}
    prov = make(stack.defn.id, maker, origin, owner, now)
    try:
        stack.provenance = prov
    except Exception:
        pass
    return prov


def record(stack, action: str, actor=None, place=None, now=0.0,
           detail: str = "") -> None:
    prov = ensure(stack)
    if not prov:
        return
    hist = prov.get("history")
    if not isinstance(hist, list):
        hist = prov["history"] = []
    event = {
        "t": round(float(now), 1),
        "action": str(action),
        "actor": _name(actor),
        "place": _name(place),
        "detail": str(detail or ""),
    }
    hist.append(event)
    if len(hist) > 24:
        del hist[:-24]
    remember(actor, stack)


def remember(who, stack) -> None:
    """A person who made, owns or handled a unique thing knows its ID."""
    prov = getattr(stack, "provenance", None)
    if who is None or not isinstance(prov, dict):
        return
    try:
        known = getattr(who, "known_items", None)
        if not isinstance(known, dict):
            known = who.known_items = {}
        uid = prov.get("uid")
        if uid:
            known[uid] = {
                "item": prov.get("item", ""),
                "maker": prov.get("maker", ""),
                "owner": prov.get("owner", ""),
                "events": len(prov.get("history") or ()),
            }
    except Exception:
        pass


def set_owner(stack, owner) -> None:
    prov = ensure(stack)
    if prov:
        prov["owner"] = _name(owner)
        remember(owner, stack)


def transfer(stack, new_owner, action="taken", actor=None, place=None,
             now=0.0) -> None:
    """Record an ownership change and who made it.  This is the hook theft,
    trade, gifting and inheritance call; the item story then writes itself."""
    prov = ensure(stack)
    if not prov:
        return
    old = prov.get("owner", "")
    new = _name(new_owner)
    prov["owner"] = new
    detail = ("%s -> %s" % (old or "nobody", new or "nobody"))
    record(stack, action, actor=actor or new_owner, place=place, now=now,
           detail=detail)
    remember(new_owner, stack)


def quality_text(stack) -> str:
    try:
        if getattr(stack.defn, "quality", False) and stack.quality is not None:
            import quality
            return quality.letter(int(stack.quality))
    except Exception:
        pass
    return ""


def describe(stack) -> list[str]:
    """The readable biography shown on the inventory tooltip."""
    if stack is None:
        return []
    prov = getattr(stack, "provenance", None)
    lines = [stack.defn.name]
    q = quality_text(stack)
    if q:
        lines[0] += "  (%s)" % q
    try:
        if getattr(stack, "plant_kind", None):
            lines.append("Plant: %s" % stack.plant_kind)
        if getattr(stack, "genetics", None):
            lines.append("Genetics: %s" % stack.genetics)
    except Exception:
        pass
    if not isinstance(prov, dict):
        lines.append("No provenance recorded.")
        return lines
    if prov.get("maker"):
        lines.append("Made by %s" % prov["maker"])
    if prov.get("origin"):
        lines.append("at %s" % prov["origin"])
    if prov.get("owner"):
        lines.append("Owner: %s" % prov["owner"])
    for event in (prov.get("history") or [])[-5:]:
        what = event.get("action", "event")
        who = event.get("actor", "")
        where = event.get("place", "")
        detail = event.get("detail", "")
        text = what
        if who:
            text += " — %s" % who
        if where:
            text += " at %s" % where
        if detail:
            text += " (%s)" % detail
        lines.append(text)
    return lines


def _wrap(font, text, width):
    words = str(text).split()
    out, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if cur and font.size(test)[0] > width:
            out.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        out.append(cur)
    return out or [""]


def draw_tooltip(screen, stack, mouse, font) -> None:
    if stack is None:
        return
    lines = describe(stack)
    wrapped = []
    for line in lines:
        wrapped.extend(_wrap(font, line, 300))
    if not wrapped:
        return
    w = min(360, max(180, max(font.size(s)[0] for s in wrapped) + 18))
    h = len(wrapped) * (font.get_height() + 2) + 12
    sw, sh = screen.get_size()
    x = min(max(8, mouse[0] + 16), sw - w - 8)
    y = min(max(8, mouse[1] + 14), sh - h - 8)
    box = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(box, (20, 19, 17, 235), box.get_rect(), border_radius=7)
    pygame.draw.rect(box, (160, 136, 92, 255), box.get_rect(), 1, border_radius=7)
    for i, line in enumerate(wrapped):
        img = font.render(line, True, (232, 222, 196) if i == 0 else (194, 188, 174))
        box.blit(img, (9, 6 + i * (font.get_height() + 2)))
    screen.blit(box, (x, y))
