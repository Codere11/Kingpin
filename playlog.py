"""playlog.py -- the director's raw material.

Semantic actions and a coarse snapshot of the conquered camps.  It is not a
keylogger: one line per meaningful act, and one camp snapshot per minute.
"""

from __future__ import annotations

import json
import os
import time

SNAPSHOT_SECONDS = 60.0


def _path() -> str:
    return os.path.expanduser("~/.kingpin_saves/playlog.jsonl")


def _skills(obj):
    s = getattr(obj, "skills", None)
    if s is None:
        return {}
    out = {}
    for key in ("farming", "movement", "axe", "shooting",
                "research", "smithing"):
        try:
            out[key] = round(float(getattr(s, key, 0.0)), 3)
        except Exception:
            pass
    return out


def _people(camp):
    seen = set()
    out = []
    lists = ("farmers", "warriors", "handlers", "workers", "loggers",
             "artisans", "researchers", "doctors", "miners", "smiths",
             "weavers", "spicemen", "gunsmiths", "unemployed")
    for attr in lists:
        for p in (getattr(camp, attr, ()) or ()):
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            out.append(p)
    people = getattr(camp, "people", None)
    if isinstance(people, list):
        for p in people:
            if id(p) in seen or not getattr(p, "alive", True):
                continue
            seen.add(id(p))
            out.append(p)
    return out


def _thoughts(npc, limit=4):
    try:
        import mood
        thoughts = getattr(npc, "mood_thoughts", None) or {}
        rows = []
        for tid, t in thoughts.items():
            try:
                rows.append((tid, float(t.get("delta", 0.0))
                             * int(t.get("stacks", 1))))
            except Exception:
                pass
        rows.sort(key=lambda r: abs(r[1]), reverse=True)
        return [{"id": k, "value": round(v, 1)} for k, v in rows[:limit]]
    except Exception:
        return []


def record(g, kind: str, **fields) -> None:
    """Write one action line.  Failures must never affect the game."""
    if g is None or os.environ.get("KINGPIN_PLAYLOG") == "0":
        return
    try:
        data = {
            "t": round(float(getattr(g, "now", 0.0)), 2),
            "wall": time.strftime("%H:%M:%S"),
            "kind": str(kind),
            "test": bool(getattr(g, "test_mode", False)),
            "player": {
                "x": round(float(getattr(g.player, "x", 0.0)), 1),
                "y": round(float(getattr(g.player, "y", 0.0)), 1),
                "skills": _skills(g.player),
            },
        }
        try:
            import player_mind
            data["player"]["mbti"] = player_mind.summary(g)["letters"]
        except Exception:
            pass
        clean = {}
        for key, value in fields.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                clean[key] = value
            elif hasattr(value, "name"):
                clean[key] = getattr(value, "name", str(value))
            else:
                clean[key] = str(value)
        data.update(clean)
        path = _path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(data, sort_keys=True) + "\n")
    except Exception:
        pass


def _camp_snapshot(camp, g):
    people = _people(camp)
    moods = []
    out_people = []
    for p in people:
        try:
            moods.append(float(getattr(p, "mood", 50.0)))
        except Exception:
            pass
        out_people.append({
            "name": getattr(p, "name", "?"),
            "job": getattr(p, "job", None) or getattr(p, "native_role", None),
            "mbti": getattr(p, "mbti", ""),
            "skills": _skills(p),
            "mood": round(float(getattr(p, "mood", 50.0)), 1),
            "target": round(float(getattr(p, "mood_target", 50.0)), 1),
            "break": getattr(p, "break_state", "normal"),
            "drivers": _thoughts(p),
        })
    avg = sum(moods) / len(moods) if moods else 50.0
    return {
        "name": getattr(camp, "name", "camp"),
        "x": round(float(getattr(camp, "x", 0.0)), 1),
        "y": round(float(getattr(camp, "y", 0.0)), 1),
        "population": len(people),
        "avg_mood": round(avg, 1),
        "low_mood": sum(1 for m in moods if m <= 32.0),
        "people": out_people,
    }


def snapshot(g) -> None:
    if g is None or os.environ.get("KINGPIN_PLAYLOG") == "0":
        return
    try:
        camps = []
        for camp in (getattr(g, "native_settlements", {}) or {}).values():
            if not getattr(camp, "conquered", False):
                continue
            camps.append(_camp_snapshot(camp, g))
        data = {
            "t": round(float(getattr(g, "now", 0.0)), 2),
            "wall": time.strftime("%H:%M:%S"),
            "kind": "snapshot",
            "test": bool(getattr(g, "test_mode", False)),
            "player_skills": _skills(g.player),
            "player_pos": [round(float(g.player.x), 1),
                           round(float(g.player.y), 1)],
            "camps": camps,
        }
        try:
            import player_mind
            data["player_mbti"] = player_mind.summary(g)
        except Exception:
            pass
        path = _path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(data, sort_keys=True) + "\n")
    except Exception:
        pass


def tick(g, dt: float) -> None:
    if not hasattr(g, "_playlog_t"):
        g._playlog_t = 0.0      # first snapshot immediately, then every minute
    wait = float(g._playlog_t) - float(dt)
    if wait > 0.0:
        g._playlog_t = wait
        return
    g._playlog_t = SNAPSHOT_SECONDS
    snapshot(g)
