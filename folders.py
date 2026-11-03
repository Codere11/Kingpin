"""folders.py -- A DEAD AGENT'S MESSAGES, IN HIS OWN HAND.

An agent's body carries a **Secret Folder**: every piece of service news he was
holding when he died, addressed to him, with who it came from and how old it
is. Equip the folder, click, and read it like mail -- one message after another,
scrolled, with a page count.

RULES
-----
* The folder belongs to ONE agent. Which one is `ItemStack.payload` (a folder
  id), so two folders in a rucksack are two different men's mail.
* A message is what the agent actually held (nemesis.FACTS): the offence he
  witnessed, the man caught at a gate, where the service operates, the roster
  the chief gave him. Nothing is invented for the folder.
* Every message DIES AFTER THREE DAYS -- a folder looted from a cold case is an
  empty folder with a name on it, as it should be.
"""

from __future__ import annotations

FOLDER_DAYS = 3
DAY = 600.0                     # the game's day, in seconds of world time
FOLDERS: dict = {}              # folder id -> {"to": name, "msgs": [ {..} ]}


def _sender(fact: dict) -> str:
    """Who a message is FROM, as far as the marks allow.

    The service does not sign its work, but its facts do say where they were
    gathered: an offence carries a place, a catch carries a gate. The roster
    and the chief's own file come from the chief.
    """
    kind = fact.get("kind")
    place = fact.get("place")
    if kind in ("place", "roster", "chief"):
        return "the chief"
    if kind == "caught":
        return "an agent at the gate of %s" % (place or "somewhere")
    if kind == "offence":
        return "an agent at %s" % (place or "somewhere")
    if kind == "playerorder":
        return "a turned man of yours"
    return "the service"


def _text(fact: dict) -> str:
    got = fact.get("text")
    if got:
        return str(got)
    return " ".join("%s %s" % (k, v) for k, v in sorted(fact.items())
                    if k not in ("id", "kind", "t"))


def new_folder(name: str, facts: list, now: float, limit: int = 60) -> str:
    """Build a folder from the messages a dead agent held. Returns its id.

    Each message may already carry its `from` -- a person's name, from
    nemesis.folder_messages -- and if it does, that is used: a folder looted
    off a body has to say WHO, not "an agent at Ash Valley".
    """
    msgs = []
    for fact in facts[:limit]:
        t = float(fact.get("t", now) or now)
        age_days = max(0.0, (now - t) / DAY)
        if age_days > FOLDER_DAYS:
            continue                     # stale news dies
        msgs.append({"from": fact.get("from") or _sender(fact),
                     "text": _text(fact), "age": age_days, "t": t})
    msgs.sort(key=lambda m: m["t"], reverse=True)   # newest first
    fid = "folder:%s:%d" % (name, int(now))
    FOLDERS[fid] = {"to": name, "msgs": msgs}
    return fid


def read(fid: str) -> dict | None:
    """One folder, with its messages pruned to the last three days."""
    got = FOLDERS.get(fid)
    if got is None:
        return None
    return got


def prune(now: float) -> int:
    """Forget messages older than three days. Returns how many went."""
    gone = 0
    for folder in FOLDERS.values():
        keep = []
        for m in folder.get("msgs", ()):
            if (now - float(m.get("t", now) or now)) / DAY > FOLDER_DAYS:
                gone += 1
            else:
                keep.append(m)
        folder["msgs"] = keep
    return gone


def summary() -> str:
    total = sum(len(f.get("msgs", ())) for f in FOLDERS.values())
    return "%d folder(s), %d message(s)" % (len(FOLDERS), total)


def to_data() -> dict:
    return {k: {"to": v.get("to", "?"), "msgs": list(v.get("msgs", ()))}
            for k, v in FOLDERS.items()}


def from_data(data) -> None:
    FOLDERS.clear()
    for fid, rec in (data or {}).items():
        try:
            FOLDERS[fid] = {"to": rec.get("to", "?"),
                            "msgs": list(rec.get("msgs", ()))}
        except Exception:
            continue
