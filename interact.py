"""interact.py -- THE STREET-LEVEL MOMENTS.

Murder witnesses, the man a villager can see to fight, a caravan meeting an
army on the road, and the single call that turns a town against the player.
Extracted from main.py.
"""

from __future__ import annotations

import math
import pygame

import economy
import guns
import plog
import war
import village as village_mod

WITNESS_PX = 900.0


def see_murder(victim) -> None:
    """Everyone who SAW it keeps it for ever."""
    village = getattr(victim, "village", None)
    if village is None:
        return
    for who in village.npcs:
        if not who.alive:
            continue
        if math.hypot(who.x - victim.x, who.y - victim.y) <= WITNESS_PX:
            who.witness((village_mod.PLAYER_ID,))


def nearest_hostile(npc, player):
    """WHAT THIS MAN CAN SEE TO FIGHT, and his own business."""
    reach = 900.0
    _reason = (getattr(npc, "hostile", False)
               or getattr(player, "wanted", False)
               or getattr(getattr(npc, "village", None), "provoked", False)
               or getattr(npc, "defender", False))
    if player.dead or not _reason:
        return None
    d = (player.x - npc.x) ** 2 + (player.y - npc.y) ** 2
    return player if d < reach * reach else None


def meet_army(trader, army, now) -> None:
    """A caravan halts at a column: it sells and it listens."""
    cap = getattr(army, "capital", None)
    for s in army.soldiers:
        if not getattr(s, "alive", False):
            continue
        man = getattr(s, "home_npc", None)
        if man is None or not man.alive:
            continue
        if getattr(s, "melee", True):
            item, want = "rifle", 1
        else:
            item, want = "ammo", economy.AMMO_WANT * 2 - getattr(s, "ammo", 0)
        if want <= 0:
            continue
        have = int(trader.stock.get(item, 0))
        if have <= 0:
            continue
        base = (cap.prices.get(item, economy.ITEM_VALUE.get(item, 8))
                if cap is not None else economy.ITEM_VALUE.get(item, 8))
        price = max(1, int(base))
        take = max(0, min(have, want, int(man.coins // price)))
        if take <= 0:
            continue
        trader.stock[item] = have - take
        man.coins -= take * price
        trader.coins += take * price
        if item == "ammo":
            s.ammo = getattr(s, "ammo", 0) + take
        else:
            s.melee = False
            s.gun_kind = guns.RIFLE
            s.mag = guns.MAG[guns.RIFLE]
            s.ammo = getattr(s, "ammo", 0) + economy.AMMO_PER_RIFLE
    for s in army.soldiers[:8]:             # and the news goes with the trade
        war.tell(trader, s, now)


def commit_crime(where, villages, player, now, work_lanes) -> None:
    """THE TOWN TURNS ON HIM. One call, one town, nothing else."""
    town = where
    if town is None:
        for v in villages.villages:
            fr = getattr(v, "fence_rect", None)
            if fr is not None and fr.collidepoint(player.x, player.y):
                town = v
                break
    if town is not None:
        town.provoke()
        town.learn_killers((village_mod.PLAYER_ID,), now)
        work_lanes.crime(town, (village_mod.PLAYER_ID,))
        for _w in town.npcs:
            if _w.alive and math.hypot(_w.x - player.x,
                                       _w.y - player.y) <= WITNESS_PX:
                _w.witness((village_mod.PLAYER_ID,))
        plog.log("AGGRO", getattr(town, "name", "?"),
                 "known_to", len(getattr(town, "killers", ()) or ()))
        return
    for v in villages.villages:
        if math.hypot(v.x - player.x, v.y - player.y) < v.radius + 400.0:
            v.provoke()
            plog.log("AGGRO", getattr(v, "name", "?"))
            break


def make_tradeable(npc, random):
    """GIVE A MAN A PURSE IF HE HAS NEVER NEEDED ONE."""
    if getattr(npc, "coins", None) is None:
        npc.coins = 30 + (abs(hash((getattr(npc, "x", 0.0),
                                    getattr(npc, "y", 0.0)))) % 45)
        npc.trade_demand = 4
        npc.restock_timer = 0.0
        npc.stock = {}
    if not getattr(npc, "sly_flash", None):
        npc.sly_flash = 0.0
    if getattr(npc, "stock", None) is None:
        npc.stock = {}
    if getattr(npc, "job", None) is None:
        npc.job = "soldier"
    if getattr(npc, "home_house", "missing") == "missing":
        npc.home_house = None
    if not hasattr(npc, "wants_product"):
        npc.wants_product = "cigar"
    if not hasattr(npc, "wants_drink"):
        npc.wants_drink = "beer"
    if not hasattr(npc, "yearning"):
        npc.yearning = 0.85
    if not hasattr(npc, "quality_pref"):
        npc.quality_pref = 0
    if not hasattr(npc, "rng"):
        npc.rng = random.Random(int(abs(hash((npc.x, npc.y)))) & 0xFFFFFFFF)
    if getattr(npc, "trade_demand", 0) <= 0:
        npc.trade_demand = 4
    if not getattr(npc, "name", None):
        npc.name = "a soldier"
    if not hasattr(npc, "occupation"):
        npc.occupation = lambda: "soldier"
    return npc


def leave_army(player, toast) -> None:
    if getattr(player, "army", None) is not None:
        player.army.player = None
    player.nation = None
    player.army = None
    player.wage = 0
    toast("You left the army")


def player_hidden_in_village(player, visible_villages, math) -> bool:
    for village in visible_villages:
        if math.hypot(player.x - village.x, player.y - village.y) < village.radius:
            return True
    return False


def nearest_town(player, villages, world_half):
    towns = [v for v in (getattr(villages, "villages", ()) or ())
             if abs(v.x) <= world_half and abs(v.y) <= world_half]
    if not towns:
        return None
    return min(towns, key=lambda v: (v.x - player.x) ** 2 + (v.y - player.y) ** 2)


def guard_search(npc, inventory, player, toast, commit_crime, random) -> None:
    """THE SEARCH AT THE GATE."""
    contraband = ("tobacco", "cigar", "beer", "liqueur", "mezcal",
                  "dried_mushroom", "red_mushroom", "agave", "wheat_wort",
                  "berry_wort", "agave_wort")
    units = sum(inventory.count_of(i) for i in contraband)
    if units <= 0:
        toast("%s looks you over and waves you through"
              % getattr(npc, "name", "The guard"))
        return
    skill = max(0.0, min(10.0, float(getattr(player, "smuggling", 0.0))))
    found = min(1.0, units / 100.0) * (1.0 - 0.09 * skill)
    if random.random() < found:
        toast("%s finds it. %d against the wall."
              % (getattr(npc, "name", "The guard"), units))
        commit_crime()
        return
    player.smuggling = min(10.0, skill + 0.06 + units * 0.001)
    toast("Searched clean   (smuggling %.1f)" % player.smuggling)


def open_trade(npc, make_tradeable, player, main_capital, dialogue_panel,
               pygame, plog) -> None:
    """CLICK A MAN AND TALK TO HIM."""
    try:
        npc = make_tradeable(npc)
    except Exception:
        pass
    dialogue_panel.open(npc, player, main_capital()[0])
    pygame.mouse.set_visible(True)
    plog.log("TALK", "opened with", getattr(npc, "name", "?"),
             "job", getattr(npc, "job", None),
             "truth", getattr(npc, "is_truth_teller", False))


def open_trade_menu(npc, make_tradeable, player, inventory, toast, village_mod,
                    trade_menu_cls, pygame, plog):
    """THE COUNTER, when he asks for it."""
    try:
        npc = make_tradeable(npc)
    except Exception:
        toast("He wants nothing to do with you")
        return False, None
    if getattr(npc, "is_witness", lambda _n: False)(village_mod.PLAYER_ID):
        toast("%s wants nothing to do with you" % npc.name)
        return False, None
    _m = trade_menu_cls(inventory, npc, player)
    pygame.mouse.set_visible(True)
    plog.log("TRADE", "opened with", getattr(npc, "name", "?"))
    return True, _m
