"""Player actions on soil and crops.

Kept separate from the UI so the whole grow/harvest loop can be tested without
a running game. Every crop has its own seed: plant that seed and it grows that
plant, wherever you are. See ``crop.SEED_CROP``.
"""

from __future__ import annotations

import random

import biomes
import crop
import items
from world import TILE


def dig(world, ground, tx: int, ty: int, toast) -> bool:
    plot = world.plot_at(tx, ty)
    if plot is not None and plot.kind != "grass":
        toast("Already worked this tile")
        return False
    world.set_plot(tx, ty, "dirt")
    ground.invalidate_tile(tx, ty)
    toast("Dug up the soil")
    return True


def water(world, ground, tx: int, ty: int, toast) -> bool:
    plot = world.plot_at(tx, ty)
    if plot is None:
        toast("Dig the ground first")
        return False
    if plot.kind == "fertile":
        toast("Already watered")
        return False
    if plot.kind in crop.LEAF_KINDS or plot.kind in crop.FOOD_KINDS:
        toast("Something is planted here")
        return False
    plot.kind = "fertile"
    ground.invalidate_tile(tx, ty)
    toast("Soil looks fertile now")
    return True


def plant(world, ground, inventory, tx: int, ty: int, now: float, toast,
          seed: str) -> bool:
    """Plant the seed you are holding -- it grows exactly that crop."""
    kind = crop.SEED_CROP.get(seed)
    if kind is None:
        return False
    plot = world.plot_at(tx, ty)
    if plot is None:
        toast("Dig and water the ground first")
        return False
    if plot.kind in crop.LEAF_KINDS or plot.kind in crop.FOOD_KINDS:
        toast("Already planted")
        return False
    if plot.kind != "fertile":
        toast("Water the soil first")
        return False
    x = tx * TILE + TILE / 2.0
    y = ty * TILE + TILE / 2.0
    if not biomes.can_plant(float(world.temperature(x, y)),
                            float(world.humidity(x, y)), kind):
        toast("That won't grow in this ground")
        return False
    if not inventory.consume(seed, 1):
        toast("No seeds left")
        return False
    plot.kind = kind
    plot.planted_at = now
    ground.invalidate_tile(tx, ty)
    toast("Planted some %s" % items.get(kind_name(kind)).name.lower())
    return True


def kind_name(kind: str) -> str:
    """The item a crop grows into (used for messages)."""
    return crop.LEAF_ITEM.get(kind) or crop.FOOD_ITEM.get(kind) or "crop"


def harvest(world, inventory, plot, now: float, toast, quality: int = 0,
            tx: int | None = None, ty: int | None = None,
            share=None) -> bool:
    """Collect a ripe crop and its own seed.

    ``share``, when given, is called with (item, amount) for every crop taken
    off the field, BEFORE the seed. It exists for the paying player: a villager
    is taxed by economy.take_fifth out of the yield of his plot, and a player
    who farms must pay the same fifth of the same crop. See main.pay_share.
    """
    if crop.stage(now - (plot.planted_at if plot.planted_at is not None else now)) < 3:
        toast("Not ready yet")
        return False
    kind = plot.kind
    seed = crop.CROP_SEED.get(kind)
    if kind in crop.LEAF_KINDS:
        item = crop.LEAF_ITEM[kind]
        amount = random.randint(3, 6)
        seeds = random.randint(2, 5)
        inventory.add(item, amount, quality)
        if share is not None:
            share(item, amount)
    else:
        item = crop.FOOD_ITEM[kind]
        amount = {"wheat": random.randint(1, 3),
                  "berries": random.randint(2, 5),
                  "cactus": random.randint(1, 2)}.get(kind, 1)
        seeds = random.randint(1, 3)
        inventory.add(item, amount)
        if share is not None:
            share(item, amount)
        if kind == "wheat":
            # ...AND THE GRAIN. Bread is the crop's food, but the grain is what
            # the mash is made of -- without it a farmer could bake a loaf and
            # never brew a beer, which made no sense at all.
            inventory.add("wheat", amount)
            if share is not None:
                share("wheat", amount)
    if seed is not None:
        inventory.add(seed, seeds)
    # The crop took everything out of the soil: it is spent, and grass returns.
    plot.kind = "grass"
    plot.planted_at = None
    if tx is not None and ty is not None:
        ground = getattr(world, "ground", None)
        if ground is not None:
            ground.invalidate_tile(tx, ty)
    toast("Harvested %d %s and %d %s"
          % (amount, items.get(item).name.lower(), seeds,
             items.get(seed).name.lower() if seed else "seeds"))
    return True
