"""houseuse.py -- USING THE THINGS INSIDE A HOUSE.

The chest, the workshop, the lab, the brew table, the barrel: what is near
the player, and what happens when he presses E at each. Extracted from main.py
so the engine does not carry the furniture logic.
"""

from __future__ import annotations

import math

import economy
import items
import nemesis
import quality


def near_chest(player, inside_house) -> bool:
    if inside_house is None:
        return False
    chest = inside_house.interior.chest_rect
    return math.hypot(player.x - chest.centerx,
                      player.y - chest.centery) < 56.0


def near_brew(player, inside_house) -> bool:
    if inside_house is None:
        return False
    return inside_house.interior.brew_near(player.x, player.y)


def mash_at_table(inventory, skills, toast) -> None:
    """Mash what you carry into wort -- up to fifty of a kind."""
    for src, wort in economy.WORT.items():
        idx = next((i for i, st in enumerate(inventory.slots)
                    if st is not None and st.defn.id == src and st.count > 0), None)
        if idx is None:
            continue
        stack = inventory.slots[idx]
        batch = min(stack.count, economy.WORT_BATCH)
        q = stack.quality if stack.quality is not None else 0
        stack.count -= batch
        if stack.count <= 0:
            inventory.slots[idx] = None
        inventory.add(wort, batch, q)
        skills.gain_farming(0.02 * min(batch, 10))
        toast("Mashed %d into %s" % (batch, items.get(wort).name))
        return
    toast("Nothing to mash -- bring wheat, berries or agave")


def use_barrel(player, inside_house, inventory, skills, now, toast) -> None:
    """Fill the barrel with wort, or take what it has made."""
    barrel = inside_house.interior.barrel_near(player.x, player.y)
    if barrel is None:
        return
    if barrel["kind"]:
        if now < barrel["ready_at"]:
            toast("Still fermenting -- %.0f seconds to go"
                  % max(0.0, barrel["ready_at"] - now))
            return
        out = economy.BREW.get(barrel["kind"])
        count, given = barrel["count"], barrel["grade"]
        barrel["kind"], barrel["count"], barrel["ready_at"] = None, 0, 0.0
        barrel["grade"] = 0
        if out:
            hands = skills.leaf_grade()
            g = quality.clamp(int(round((hands + given) / 2.0)))
            inventory.add(out, count, g)
            nemesis.note_offence_seen(player, "made", out)   # drugs, broached
            skills.gain_farming(0.02 * min(count, 10))
            toast("%d %s  (%s)" % (count, items.get(out).name, quality.letter(g)))
        return
    for wort in economy.BREW:
        idx = next((i for i, st in enumerate(inventory.slots)
                    if st is not None and st.defn.id == wort and st.count > 0), None)
        if idx is None:
            continue
        stack = inventory.slots[idx]
        batch = min(stack.count, economy.WORT_BATCH)
        barrel["kind"] = wort
        barrel["count"] = batch
        barrel["grade"] = stack.quality if stack.quality is not None else 0
        barrel["ready_at"] = now + economy.BREW_SECONDS
        stack.count -= batch
        if stack.count <= 0:
            inventory.slots[idx] = None
        toast("Filled with %d %s -- five minutes"
              % (batch, items.get(wort).name))
        return
    toast("Fill it with wort")


def near_lab(player, inside_house) -> bool:
    if inside_house is None:
        return False
    return inside_house.interior.lab_near(player.x, player.y)


def craft_at_table(player, inventory, skills, toast) -> None:
    """Work the leaf you carry into cigars or dried mushrooms. The grade is
    the MIDPOINT of your hands and the leaf you were given -- good leaf in
    clumsy hands and poor leaf in a master's both make a middling article,
    so this trade has to be learnt just as farming does."""
    for leaf, out in economy.PROCESS.items():
        idx = next((i for i, st in enumerate(inventory.slots)
                    if st is not None and st.defn.id == leaf and st.count > 0), None)
        if idx is None:
            continue
        stack = inventory.slots[idx]
        given = stack.quality if stack.quality is not None else 0
        hands = skills.leaf_grade()
        g = quality.clamp(int(round((hands + given) / 2.0)))
        stack.count -= 1
        if stack.count <= 0:
            inventory.slots[idx] = None
        inventory.add(out, 1, g)
        nemesis.note_offence_seen(player, "made", out)   # drugs, at a bench
        skills.gain_farming(0.02)          # you learn at the bench too
        toast("Made a %s  (%s)" % (items.get(out).name, quality.letter(g)))
        return
    toast("No leaf to work")


def near_workshop(player, inside_house) -> bool:
    if inside_house is None:
        return False
    return inside_house.interior.workshop_near(player.x, player.y)


def work_action(key, smith_shop, player, now, economy, inventory, skills,
                random, pay_share, quality, ironworking=False):
    """Do a stroke of the trade the player is standing at. Returns (cd, msg)."""
    wp = smith_shop
    if wp is None:
        return 0.0, ""
    kind = wp.kind
    if kind == "brewery":
        brew = getattr(player, "brew", None)
        if brew is not None and now >= brew[2]:
            wort, count, _r = brew
            player.brew = None
            out = economy.BREW.get(wort)
            if out:
                inventory.add(out, count)
                return 2.0, "Drew %d %s" % (count, out)
        if brew is None:
            food = getattr(wp.worker.village, "local_food", "wheat") \
                if wp.worker else "wheat"
            if inventory.count_of(food) >= economy.WORT_BATCH:
                inventory.consume(food, economy.WORT_BATCH)
                player.brew = (economy.WORT.get(food, "wheat_wort"),
                               economy.WORT_BATCH, now + economy.BREW_SECONDS)
                return 2.0, "Mashed %d %s   -   ready in %d min" % (
                    economy.WORT_BATCH, food, int(economy.BREW_SECONDS / 60))
        return 0.0, "Nothing to draw"
    if kind == "lab":
        leaf = next((k for k in economy.PROCESS
                     if inventory.count_of(k) >= economy.CRAFT_CONSUME), None)
        if leaf is None:
            return 0.0, "No leaf"
        out = economy.PROCESS[leaf]
        inventory.consume(leaf, economy.CRAFT_CONSUME)
        g = skills.leaf_grade()
        inventory.add(out, 1, g)
        return 2.0, "Made one %s   (%s)" % (out, quality.letter(g))
    if kind == "mine":
        _dug = random.randint(3, 7)
        inventory.add("iron", _dug)
        pay_share("iron", _dug)
        return 2.0, "Broke out some iron"
    if kind == "smith":
        # IRONWORKING: the forge smelts ore into bars, one for one.
        if ironworking:
            if inventory.count_of("iron") < 1:
                return 0.0, "No iron ore"
            inventory.consume("iron", 1)
            inventory.add("iron_bar", 1)
            return 1.0, "Smelted an iron bar"
        if inventory.count_of("iron") < economy.IRON_PER_TOOL:
            return 0.0, "Need %d iron" % economy.IRON_PER_TOOL
        inventory.consume("iron", economy.IRON_PER_TOOL)
        kindw = "shovel"
        for want in ("axe", "pickaxe", "shovel"):
            if any(k == want for _w, k in
                   (getattr(wp.worker, "tool_orders", ()) or ())):
                kindw = want
                break
        inventory.add(kindw, 1, skills.leaf_grade())
        return 2.0, "Forged a %s" % kindw
    return 0.0, ""
