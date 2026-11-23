"""player_mind.py -- the player's inferred personality.

The player does not pick a type.  A rolled prior is only the starting bias;
what he actually does moves four decaying counters.  This module is pure data
and arithmetic: hooks in the game call observe(), the card calls summary().
"""

from __future__ import annotations

import persona

HALF_LIFE = 600.0          # one in-game day
PRIOR = 5.0
DECAY_INTERVAL = 2.0       # never per frame
CONTACT_COOLDOWN = 60.0    # one F/T contact per NPC per minute
MERCY_WINDOW = 20.0

FIELDS = ("initiated", "responded", "sensing", "intuitive",
          "f_contacts", "t_contacts", "conquered_provoked",
          "conquered_retaliated", "conquered_merciful")


def _seed(g) -> int:
    return int(getattr(getattr(g, "world", None), "seed", 0) or 0)


def ensure(g) -> dict:
    st = getattr(g, "player_mind", None)
    if not isinstance(st, dict) or "start_type" not in st:
        start = persona.assign_from_key("player:%s" % _seed(g))
        st = {"start_type": start, "_decay_t": 0.0,
              "_provoked_at": 0.0, "_retaliated": False}
        for key in FIELDS:
            st[key] = 0.0
        # The rolled type is a prior, not a permanent label.
        st["initiated" if start[0] == "E" else "responded"] = PRIOR
        st["sensing" if start[1] == "S" else "intuitive"] = PRIOR
        st["f_contacts" if start[2] == "F" else "t_contacts"] = PRIOR
        st["conquered_retaliated" if start[3] == "J" else "conquered_merciful"] = PRIOR
        g.player_mind = st
        return st
    for key in FIELDS:
        st.setdefault(key, 0.0)
    st.setdefault("start_type", persona.assign_from_key("player:%s" % _seed(g)))
    st.setdefault("_decay_t", 0.0)
    st.setdefault("_provoked_at", 0.0)
    st.setdefault("_retaliated", False)
    return st


def _contact(g, subject) -> bool:
    """One F/T contact per NPC per minute, not per click."""
    now = float(getattr(g, "now", 0.0))
    key = str(getattr(subject, "id", "") or id(subject))
    seen = getattr(g, "_mind_contacts", None)
    if seen is None:
        seen = g._mind_contacts = {}
    if now - float(seen.get(key, -1e9)) < CONTACT_COOLDOWN:
        return False
    seen[key] = now
    return True


def observe(g, kind: str, subject=None, amount: float = 1.0) -> None:
    st = ensure(g)
    if kind == "initiated":
        st["initiated"] += amount
    elif kind == "responded":
        st["responded"] += amount
    elif kind == "sensing":
        st["sensing"] += amount
    elif kind == "intuitive":
        st["intuitive"] += amount
    elif kind == "contact" and subject is not None:
        if not _contact(g, subject):
            return
        if persona.is_feeling(subject):
            st["f_contacts"] += amount
        elif persona.is_thinking(subject):
            st["t_contacts"] += amount
    elif kind == "provoked":
        st["_provoked_at"] = float(getattr(g, "now", 0.0))
        st["_retaliated"] = False
    elif kind == "retaliated":
        now = float(getattr(g, "now", 0.0))
        if (st.get("_provoked_at")
                and now - float(st["_provoked_at"]) <= MERCY_WINDOW
                and not st.get("_retaliated")):
            st["conquered_retaliated"] += amount
            st["_retaliated"] = True
            st["_provoked_at"] = 0.0
    elif kind == "merciful":
        st["conquered_merciful"] += amount
        st["_provoked_at"] = 0.0
        st["_retaliated"] = False


def tick(g, dt: float) -> None:
    st = ensure(g)
    st["_decay_t"] = float(st.get("_decay_t", 0.0)) + max(0.0, dt)
    if st["_decay_t"] < DECAY_INTERVAL:
        return
    elapsed = float(st["_decay_t"])
    st["_decay_t"] = 0.0
    factor = 0.5 ** (elapsed / HALF_LIFE)
    for key in FIELDS:
        st[key] = float(st.get(key, 0.0)) * factor
    now = float(getattr(g, "now", 0.0))
    if (st.get("_provoked_at")
            and not st.get("_retaliated")
            and now - float(st["_provoked_at"]) >= MERCY_WINDOW):
        st["conquered_merciful"] += 1.0
        st["_provoked_at"] = 0.0


def _pair(a: float, b: float, positive: str, negative: str):
    total = max(0.0, float(a)) + max(0.0, float(b))
    if total <= 0.0:
        return "?", 50.0, 0.0
    pct = 100.0 * max(0.0, float(a)) / total
    if total < 5.0:
        letter = "?"
    else:
        letter = positive if a > b else negative
    return letter, pct, total


def summary(g) -> dict:
    st = ensure(g)
    ie = _pair(st["initiated"], st["responded"], "E", "I")
    sn = _pair(st["sensing"], st["intuitive"], "S", "N")
    ft = _pair(st["f_contacts"], st["t_contacts"], "F", "T")
    jp_events = float(st["conquered_retaliated"]) + float(st["conquered_merciful"])
    jp = _pair(st["conquered_retaliated"], st["conquered_merciful"], "J", "P")
    if jp_events < 3.0:
        jp = ("?", jp[1], jp_events)
    axes = (("E", "I", ie), ("S", "N", sn), ("F", "T", ft), ("J", "P", jp))
    letters = "".join(pair[2][0] for pair in axes)
    line = ""
    if ie[2] >= 5.0:
        line = ("You start conversations more than you answer them."
                if st["initiated"] > st["responded"]
                else "You usually let other people speak first.")
    elif sn[2] >= 5.0:
        line = ("You prefer work you can do with your hands."
                if st["sensing"] > st["intuitive"]
                else "You prefer plans, people and systems.")
    elif ft[2] >= 5.0:
        line = ("You deal with people through feeling."
                if st["f_contacts"] > st["t_contacts"]
                else "You deal with people through thinking.")
    elif jp[2] >= 3.0:
        line = ("You settle scores." if st["conquered_retaliated"]
                >= st["conquered_merciful"]
                else "You tend to let things go.")
    return {"start_type": st["start_type"], "letters": letters,
            "axes": axes, "line": line}


def snapshot(g) -> dict:
    st = ensure(g)
    out = {"start_type": st.get("start_type", "")}
    for key in FIELDS:
        out[key] = float(st.get(key, 0.0))
    return out


def restore(g, data) -> None:
    st = ensure(g)
    data = data or {}
    if data.get("start_type"):
        st["start_type"] = str(data["start_type"])
    for key in FIELDS:
        try:
            st[key] = float(data.get(key, st.get(key, 0.0)))
        except Exception:
            pass
