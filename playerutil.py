"""playerutil.py -- THE PLAYER'S OWN SMALL ACTIONS.

Being hunted, reloading from the pack, banishment, and the first-aid kit.
Extracted from main.py.
"""

from __future__ import annotations

import guns


def player_hunted(visible_villages) -> bool:
    """A guard is actively hunting the player right now."""
    for village in visible_villages:
        for g in getattr(village, "guards", ()) or ():
            if (getattr(g, "hostile", False) and getattr(g, "aware", False)
                    and g.alive):
                return True
    return False


def settle_reload(player, inventory, toast) -> None:
    """A finished reload pulls rounds from the ammo you are carrying."""
    if not player.reload_done:
        return
    player.reload_done = False
    kind = player.reload_kind
    if not kind:
        return
    need = guns.MAG[kind] - player.mags.get(kind, 0)
    take = min(need, inventory.count_of("ammo"))
    if take > 0:
        inventory.consume("ammo", take)
        player.mags[kind] = player.mags.get(kind, 0) + take
        toast(f"Loaded {player.mags[kind]}/{guns.MAG[kind]}")


def banish(player, enemies, nation, toast, nation_name) -> None:
    if player.nation != nation:
        return
    player.nation = None
    for old in list(player.squad):
        if old in enemies:
            enemies.remove(old)
    player.squad = []
    toast(f"Banished from {nation_name(nation)}!   They will shoot on sight")


def use_first_aid(player, inventory, toast) -> None:
    if player.health >= player.max_health:
        toast("Already at full health")
        return
    if not inventory.consume("first_aid", 1):
        toast("No first-aid kits left")
        return
    player.health = min(player.max_health, player.health + 50)
    toast("Patched yourself up")


class Watcher:
    """In test mode the armies do not see the player."""
    __slots__ = ("_p", "dead", "nation", "squad")

    def __init__(self, p) -> None:
        self._p = p
        self.dead = True
        self.nation = None
        self.squad = []

    @property
    def x(self) -> float:
        return self._p.x

    @property
    def y(self) -> float:
        return self._p.y


def on_offences(events, by_id, nemesis) -> None:
    for _ev in events:
        try:
            _aid, _verb, _item, _x, _y, _wids = _ev
            _actor = by_id.get(str(_aid))
            _ws = [by_id.get(str(_i)) for _i in _wids]
            nemesis.note_offence(_actor, _verb, _item, _x, _y,
                                 [w for w in _ws if w is not None])
        except Exception:
            pass


def on_caught(events, by_id, settle_towns, nemesis) -> None:
    for _ev in events:
        try:
            _aid, _ti, _units = _ev
            _actor = by_id.get(str(_aid))
            _ti = int(_ti)
            _town = settle_towns[_ti] if 0 <= _ti < len(settle_towns) else None
            nemesis.note_caught(_actor, _town, int(_units))
        except Exception:
            pass


def inside_h(inside_house):
    try:
        return inside_house is not None
    except Exception:
        return "?"


def dump_trace(why, trace, plog):
    try:
        plog.log("==== TRACE:", why, "====")
        for row in trace:
            plog.log("  T:", " ".join(str(c) for c in row))
    except Exception:
        pass


def watchdog(heart, persist, os, time, faulthandler):
    while True:
        time.sleep(2.0)
        if time.time() - heart[0] < 6.0:
            continue
        try:
            path_ = os.path.join(persist.DIR, "hang.log")
            os.makedirs(persist.DIR, exist_ok=True)
            with open(path_, "a") as fh:
                fh.write("\n==== HANG  %.0f  (no frame for %.1fs) ====\n"
                         % (time.time(), time.time() - heart[0]))
                faulthandler.dump_traceback(file=fh)
        except Exception:
            pass
        heart[0] = time.time()

import nemesis