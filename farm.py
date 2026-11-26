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
import sound
from world import TILE


def dig(world, ground, tx: int, ty: int, toast) -> bool:
    plot = world.plot_at(tx, ty)
    if plot is not None and plot.kind != "grass":
        toast("Already worked this tile")
        return False
    world.set_plot(tx, ty, "dirt")
    ground.invalidate_tile(tx, ty)
    sound.play("till")
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
    if plot.kind in crop.LEAF_KINDS or plot.kind in crop.FOOD_KINDS \
            or plot.kind in crop.FIBRE_KINDS:
        toast("Something is planted here")
        return False
    plot.kind = "fertile"
    ground.invalidate_tile(tx, ty)
    toast("Soil looks fertile now")
    return True


def plant(world, ground, inventory, tx: int, ty: int, now: float, toast,
          seed: str, skill: float = 0.0) -> bool:
    """Plant the seed you are holding -- it grows exactly that crop."""
    kind = crop.SEED_CROP.get(seed)
    if kind is None:
        return False
    plot = world.plot_at(tx, ty)
    if plot is None:
        toast("Dig and water the ground first")
        return False
    if plot.kind in crop.LEAF_KINDS or plot.kind in crop.FOOD_KINDS \
            or plot.kind in crop.FIBRE_KINDS:
        toast("Already planted")
        return False
    if plot.kind != "fertile":
        toast("Water the soil first")
        return False
    x = tx * TILE + TILE / 2.0
    y = ty * TILE + TILE / 2.0
    if not biomes.can_plant(float(world.temperature(x, y)),
                            float(world.humidity(x, y)), kind, x, y):
        toast("That won't grow in this ground")
        return False
    if not inventory.consume(seed, 1):
        toast("No seeds left")
        return False
    plot.kind = kind
    plot.planted_at = now
    plot.grow = crop.grow_seconds(skill)      # HIS hand sets the clock too
    ground.invalidate_tile(tx, ty)
    sound.play("plant")
    toast("Planted some %s" % items.get(kind_name(kind)).name.lower())
    return True


def kind_name(kind: str) -> str:
    """The item a crop grows into (used for messages)."""
    return (crop.LEAF_ITEM.get(kind) or crop.FOOD_ITEM.get(kind)
            or ("cotton" if kind in crop.FIBRE_KINDS else "crop"))


def harvest(world, inventory, plot, now: float, toast, quality: int = 0,
            tx: int | None = None, ty: int | None = None,
            share=None, skill: float = 0.0, camp=None) -> bool:
    """Collect a ripe crop and its own seed.

    ``share``, when given, is called with (item, amount) for every crop taken
    off the field, BEFORE the seed. It exists for the paying player: a villager
    is taxed by economy.take_fifth out of the yield of his plot, and a player
    who farms must pay the same fifth of the same crop. See main.pay_share.
    """
    _grow = getattr(plot, "grow", None) or crop.GROW_SECONDS
    _elapsed = now - (plot.planted_at if plot.planted_at is not None else now)
    if _elapsed < _grow:
        toast("Not ready yet")
        return False
    if getattr(plot, "blight", False):
        plot.kind = "grass"
        plot.planted_at = None
        plot.blight = False
        if tx is not None and ty is not None:
            ground = getattr(world, "ground", None)
            if ground is not None:
                ground.invalidate_tile(tx, ty)
        toast("Blighted crop — nothing worth harvesting")
        return False
    kind = plot.kind
    seed = crop.CROP_SEED.get(kind)
    _scale = crop.yield_scale(skill)
    # BARREN ROCKS: the same field gives about half.  The ground is hard and
    # the crops are stubborn, which is why a local bushel is worth carrying.
    _barren_mult = 1.0
    if tx is not None and ty is not None:
        try:
            import biomes as _bio
            if _bio.is_barren(tx * TILE, ty * TILE):
                _barren_mult = 0.5
        except Exception:
            pass
    # LOCAL STRAIN: every harvest advances every target of this settlement's
    # crop, and the bonus belongs to this lot, not to the whole world.
    _gen = None
    _strain = None
    _ymult = 1.0
    _smult = 1.0
    try:
        import cropgenetics
        _strain = cropgenetics.advance(camp, kind) if camp is not None else None
        if _strain is not None:
            _gen = cropgenetics.genetics(camp, kind)
            _ymult = cropgenetics.yield_mult(_strain)
            _smult = cropgenetics.seed_mult(_strain)
    except Exception:
        pass
    if quality is not None and quality > 5:
        quality = 5                          # base quality is capped at A
    if _strain is not None:
        try:
            import cropgenetics
            quality = cropgenetics.cap_quality(_strain, quality)
        except Exception:
            pass
    if kind in crop.LEAF_KINDS:
        item = crop.LEAF_ITEM[kind]
        amount = max(1, int(round(random.randint(3, 6) * _scale * _ymult
                                  * _barren_mult)))
        seeds = max(1, int(round(random.randint(2, 5) * _smult)))
        inventory.add(item, amount, quality, plant_kind=kind, genetics=_gen)
        if share is not None:
            share(item, amount)
    elif kind in crop.FIBRE_KINDS:
        # COTTON: 5-10 cotton, 1-3 cotton seeds. No quality system.
        item = "cotton"
        amount = max(1, int(round(random.randint(5, 10) * _ymult
                                  * _barren_mult)))
        seeds = max(1, int(round(random.randint(1, 3) * _smult)))
        inventory.add(item, amount, plant_kind=kind, genetics=_gen)
        if share is not None:
            share(item, amount)
    else:
        item = crop.FOOD_ITEM[kind]
        amount = max(1, int(round({"wheat": random.randint(1, 3),
                                   "berries": random.randint(2, 5),
                                   "cactus": random.randint(1, 2),
                                   "hardberry": random.randint(2, 4)}
                                  .get(kind, 1)
                                  * _scale * _ymult * _barren_mult)))
        seeds = max(1, int(round(random.randint(1, 3) * _smult)))
        inventory.add(item, amount, plant_kind=kind, genetics=_gen)
        if share is not None:
            share(item, amount)
        if kind == "wheat":
            # ...AND THE GRAIN. Bread is the crop's food, but the grain is what
            # the mash is made of -- without it a farmer could bake a loaf and
            # never brew a beer, which made no sense at all.
            inventory.add("wheat", amount, plant_kind=kind, genetics=_gen)
            if share is not None:
                share("wheat", amount)
    if seed is not None:
        inventory.add(seed, seeds, plant_kind=kind, genetics=_gen)
    # The crop took everything out of the soil: it is spent, and grass returns.
    plot.kind = "grass"
    plot.planted_at = None
    if tx is not None and ty is not None:
        ground = getattr(world, "ground", None)
        if ground is not None:
            ground.invalidate_tile(tx, ty)
    sound.play("harvest")
    toast("Harvested %d %s and %d %s"
          % (amount, items.get(item).name.lower(), seeds,
             items.get(seed).name.lower() if seed else "seeds"))
    return True
