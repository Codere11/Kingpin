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
