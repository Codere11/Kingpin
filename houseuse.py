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
            hands = skills.leaf_grade(8)
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
        hands = skills.leaf_grade(8)
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
