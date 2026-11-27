"""relationships.py -- what one person remembers about another.

Each NPC keeps a small social memory: the player and the handful of people
who mattered most.  Actions update it immediately; decay/trimming is on each
NPC's own 30-second timer.  No per-frame scan, no unbounded history.
"""

from __future__ import annotations

import math
import random

PLAYER_KEY = "player"
KEEP = 10
DECAY_INTERVAL = 30.0


def _is_player(who) -> bool:
    return (getattr(who, "is_player", False)
            or type(who).__name__ == "Player")


def _key(who) -> str:
    if _is_player(who):
        return PLAYER_KEY
    ident = getattr(who, "id", None) or getattr(who, "_save_uid", None)
    return str(ident or id(who))


def ensure(npc) -> dict:
    mem = getattr(npc, "social_memory", None)
    if not isinstance(mem, dict):
        mem = {}
        try:
            npc.social_memory = mem
        except Exception:
            pass
    return mem


def _record(mem, key, name):
    rec = mem.get(key)
    if not isinstance(rec, dict):
        rec = {"name": name, "affinity": 0.0, "fear": 0.0,
               "respect": 0.0, "contacts": 0, "last_seen": 0.0,
               "last_event": "", "tags": []}
        mem[key] = rec
    if name:
        rec["name"] = name
    return rec


def _add_tag(rec, tag):
    tags = rec.get("tags")
    if not isinstance(tags, list):
        tags = []
        rec["tags"] = tags
    if tag not in tags:
        tags.append(tag)
    if len(tags) > 8:
        del tags[:-8]


def _remove_tag(rec, tag):
    tags = rec.get("tags")
    if isinstance(tags, list) and tag in tags:
        tags.remove(tag)


def observe(target, actor, kind: str, now: float, g=None, detail: str = "") -> None:
    """`target` remembers something `actor` just did."""
    if target is None or actor is None or target is actor:
        return
    if _is_player(target):
        return
    mem = ensure(target)
    key = _key(actor)
    name = "You" if key == PLAYER_KEY else getattr(actor, "name", "someone")
    rec = _record(mem, key, name)
    rec["contacts"] = int(rec.get("contacts", 0)) + 1
    rec["last_seen"] = float(now)
    rec["last_event"] = detail or kind
    aff, fear, resp = {
        "praise": (8.0, 0.0, 2.0),
        "insult": (-8.0, 0.0, -2.0),
        "insulted": (-8.0, 0.0, -2.0),
        "threaten": (-10.0, 8.0, -1.0),
        "threatened": (-10.0, 8.0, -1.0),
        "wronged": (-15.0, 12.0, -4.0),
        "attacked": (-15.0, 12.0, -4.0),
        "heal": (10.0, 0.0, 8.0),
        "medicine": (10.0, 0.0, 8.0),
        "gift": (8.0, 0.0, 1.0),
        "shared_food": (4.0, 0.0, 0.0),
        "shared_drink": (5.0, 0.0, 0.0),
        "grateful": (6.0, 0.0, 1.0),
        "ingrate": (-4.0, 0.0, -1.0),
        "complaint": (-3.0, 0.0, 0.0),
        "refused": (-5.0, 0.0, 0.0),
        "worked": (2.0, 0.0, 1.0),
        "forgave": (8.0, 0.0, 3.0),
        "witnessed_death": (-3.0, 4.0, 0.0),
    }.get(kind, (0.0, 0.0, 0.0))
    rec["affinity"] = max(-100.0, min(100.0, float(rec.get("affinity", 0.0)) + aff))
    rec["fear"] = max(0.0, min(100.0, float(rec.get("fear", 0.0)) + fear))
    rec["respect"] = max(-100.0, min(100.0, float(rec.get("respect", 0.0)) + resp))
    if kind in ("insult", "insulted", "threaten", "threatened", "wronged", "attacked"):
        _add_tag(rec, "grudge")
    if kind in ("threaten", "threatened", "wronged", "attacked"):
        _add_tag(rec, "fears")
    if kind in ("heal", "medicine"):
        _add_tag(rec, "grateful")
    if kind == "praise":
        _remove_tag(rec, "grudge")
    _trim(mem)


def _influence(rec) -> float:
    return (abs(float(rec.get("affinity", 0.0)))
            + float(rec.get("fear", 0.0))
            + abs(float(rec.get("respect", 0.0)))
            + 0.5 * int(rec.get("contacts", 0)))


def _trim(mem) -> None:
    if len(mem) <= KEEP:
        return
    player = mem.get(PLAYER_KEY)
    rest = [(k, v) for k, v in mem.items() if k != PLAYER_KEY]
    rest.sort(key=lambda kv: _influence(kv[1]), reverse=True)
    keep = dict(rest[:KEEP - (1 if player else 0)])
    if player:
        keep[PLAYER_KEY] = player
    mem.clear()
    mem.update(keep)


def reaction_chance(who, other) -> float:
    """Chance `who` reacts positively to something `other` did.

    At zero affinity this is exactly 50/50. A pre-existing positive relation
    moves it up; a negative one moves it down. Each side uses its OWN memory
    of the other, so the two rolls are independent.
    """
    if who is None or other is None:
        return 0.5
    rec = ensure(who).get(_key(other))
    aff = float(rec.get("affinity", 0.0)) if isinstance(rec, dict) else 0.0
    return max(0.05, min(0.95, 0.5 + aff / 200.0))


def reaction(who, other) -> bool:
    """True = positive reaction, False = negative reaction."""
    rng = getattr(who, "rng", None)
    try:
        roll = float(rng.random()) if rng is not None else random.random()
    except Exception:
        roll = random.random()
    return roll < reaction_chance(who, other)


def seed_camp(camp) -> None:
    """Give a new camp a small, pre-existing social history.

    Each person starts knowing two to four others -- not the whole camp --
    with a seeded opinion based on MBTI compatibility and a little chance.
    Existing memories are never overwritten, so loading a save preserves the
    relations the player has already seen.
    """
    people = []
    seen = set()
    for attr in ("farmers", "warriors", "handlers", "workers", "loggers",
                 "artisans", "researchers", "doctors", "traders", "miners",
                 "smiths", "weavers", "spicemen", "gunsmiths",
                 "unemployed"):
        for p in (getattr(camp, attr, ()) or ()):
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            people.append(p)
    if len(people) < 2:
        return
    try:
        import persona
    except Exception:
        persona = None
    for a in people:
        mem = ensure(a)
        if mem:
            continue
        rng = getattr(a, "rng", None)
        if rng is None:
            continue
        others = [b for b in people if b is not a]
        rng.shuffle(others)
        count = rng.randint(2, min(4, len(others)))
        for b in others[:count]:
            aff = rng.uniform(-12.0, 15.0)
            if persona is not None:
                try:
                    if persona.axis(a, "SN") == persona.axis(b, "SN"):
                        aff += 6.0
                    if persona.axis(a, "FT") == persona.axis(b, "FT"):
                        aff += 3.0
                    if persona.has_trait(a, "traumatized"):
                        aff -= 5.0
                except Exception:
                    pass
            rec = _record(mem, _key(b), getattr(b, "name", "someone"))
            rec["affinity"] = max(-100.0, min(100.0, aff))
            rec["contacts"] = rng.randint(1, 3)
            rec["last_event"] = "old history"
            if aff <= -20.0:
                _add_tag(rec, "grudge")
            elif aff >= 25.0:
                _add_tag(rec, "trusted")
        _trim(mem)


def share_reaction(receiver, giver, kind: str, now: float, g=None,
                   item: str = "") -> bool:
    """Roll how BOTH people feel about a share, using their old opinion.

    At neutral opinion each side is exactly 50/50.  A positive existing
    relation makes a positive reaction more likely; a negative one makes a
    complaint, insult or refusal more likely.  The receiver still accepts food
    when starving, but may resent it.

    Returns True if the receiver accepts the item.
    """
    if receiver is None or giver is None:
        return False
    receiver_positive = reaction(receiver, giver)
    giver_positive = reaction(giver, receiver)
    try:
        starving = float(getattr(receiver, "hunger", 0.0)) >= 85.0
    except Exception:
        starving = False
    accepted = bool(receiver_positive or starving)
    try:
        if accepted:
            observe(receiver, giver,
                    kind if receiver_positive else "complaint",
                    now, g, detail="%s %s" % (kind, item))
            if giver_positive:
                observe(giver, receiver, "grateful", now, g,
                        detail="grateful for sharing")
            else:
                observe(giver, receiver, "ingrate", now, g,
                        detail="ungrateful for food")
        else:
            # The giver offered; the receiver refused and spoke harshly.
            observe(giver, receiver, "insult", now, g,
                    detail="refused %s" % item)
            observe(receiver, giver, "refused", now, g,
                    detail="refused %s" % item)
        import mood as _mood
        if receiver_positive:
            _mood.add_thought(receiver, "grateful", 3.0, now, 300.0)
        else:
            _mood.add_thought(receiver, "insulted", -5.0, now, 300.0)
        if not giver_positive:
            _mood.add_thought(giver, "ungrateful", -3.0, now, 300.0)
        import comm as _comm
        _comm.spawn_cloud(receiver.x, receiver.y,
                          "praise" if receiver_positive else "insult",
                          text=("thank you" if receiver_positive else
                                ("not enough" if accepted else "no")),
                          speaker=receiver)
    except Exception:
        pass
    return accepted


def tick(npc, now: float, dt: float) -> None:
    """Slow decay and top-ten trimming on the NPC's own clock."""
    if getattr(npc, "_rel_t", None) is None:
        try:
            npc._rel_t = float(npc.rng.uniform(0.0, DECAY_INTERVAL))
        except Exception:
            npc._rel_t = 0.0
    npc._rel_t -= dt
    if npc._rel_t > 0.0:
        return
    npc._rel_t = DECAY_INTERVAL
    mem = ensure(npc)
    for rec in mem.values():
        rec["affinity"] = float(rec.get("affinity", 0.0)) * 0.97
        rec["fear"] = float(rec.get("fear", 0.0)) * 0.97
        rec["respect"] = float(rec.get("respect", 0.0)) * 0.97
        if abs(rec["affinity"]) < 1.0:
            rec["affinity"] = 0.0
        if rec["fear"] < 1.0:
            rec["fear"] = 0.0
        if abs(rec["respect"]) < 1.0:
            rec["respect"] = 0.0
    _trim(mem)


def label(rec) -> str:
    aff = float(rec.get("affinity", 0.0))
    fear = float(rec.get("fear", 0.0))
    if fear >= 30.0:
        return "Feared"
    if aff <= -30.0:
        return "Hated"
    if aff <= -10.0:
        return "Disliked"
    if aff >= 30.0:
        return "Trusted"
    if aff >= 10.0:
        return "Liked"
    return "Neutral"


def summary(npc, limit=8) -> list:
    mem = ensure(npc)
    rows = []
    for key, rec in mem.items():
        rows.append((_influence(rec), key, rec))
    rows.sort(key=lambda r: (r[1] != PLAYER_KEY, -r[0]))
    out = []
    for _score, key, rec in rows[:limit]:
        out.append({
            "key": key,
            "name": "You" if key == PLAYER_KEY else rec.get("name", "someone"),
            "label": label(rec),
            "affinity": float(rec.get("affinity", 0.0)),
            "fear": float(rec.get("fear", 0.0)),
            "respect": float(rec.get("respect", 0.0)),
            "contacts": int(rec.get("contacts", 0)),
            "last_event": rec.get("last_event", ""),
            "tags": list(rec.get("tags", ()) or ()),
        })
    return out
