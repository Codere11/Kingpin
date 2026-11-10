"""crown.py -- THE CROWN'S DEMAND, delivered to the ship.

Every three in-game days the Crown asks for more: leaf product, raw leaf, and
wood, tripling each time and demanding one grade higher. The player carries the
goods to the ship and drops them into the Crown's chest; once the ask is met he
passes that round.
"""
import random

import economy
import quality

# what counts as "leaf product": the finished goods made from leaf
LEAF_PRODUCTS = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")

# THE THREE CROP BIOMES, and the raw leaf + leaf product the Crown asks for
# in each. Snow grows mushroom -> dried mushroom; desert grows agave -> mezcal;
# temperate grows tobacco -> cigars.
BIOMES = ("snow", "desert", "temperate")
BIOME_LABEL = {"snow": "the snows", "desert": "the desert", "temperate": "the plains"}
BIOME_LEAF = {"snow": "red_mushroom", "desert": "agave", "temperate": "tobacco"}
BIOME_PRODUCT = {"snow": "dried_mushroom", "desert": "mezcal", "temperate": "cigar"}

# the opening ask, before any escalation
BASE = {"leaf_product": 30, "leaf": 100, "wood": 300}
GRADE_START = 2            # D
DAYS_PER_ROUND = 3


def spawn_biome(g) -> str:
    """Which crop biome the player stands in at spawn: the first ask follows it."""
    try:
        import biomes
        world = getattr(g, "world", None)
        px = float(getattr(g.player, "x", 0.0))
        py = float(getattr(g.player, "y", 0.0))
        t = float(world.temperature(px, py))
        h = float(world.humidity(px, py))
        if biomes.surface(t, h) == "snow":
            return "snow"
        if biomes.biome_name(t, h) == "desert":
            return "desert"
        return "temperate"
    except Exception:
        return "temperate"


def demand(g):
    """The Crown's current ask: biome, its specific goods, amounts, grade."""
    r = int(getattr(g, "crown_round", 0))
    mult = 3 ** max(0, r)
    grade = min(len(quality.GRADES) - 1, GRADE_START + r)
    biome = getattr(g, "crown_biome", "temperate")
    if biome not in BIOMES:
        biome = "temperate"
    return {
        "biome": biome,
        "leaf_product_item": BIOME_PRODUCT[biome],
        "leaf_item": BIOME_LEAF[biome],
        "leaf_product": BASE["leaf_product"] * mult,
        "leaf": BASE["leaf"] * mult,
        "wood": BASE["wood"] * mult,
        "grade": grade,
    }


def round_of(g) -> int:
    """Which three-day round the clock is in."""
    return int(g.now / economy.DAY_LENGTH / DAYS_PER_ROUND)


def escalate(g) -> bool:
    """Advance the demand when a new three-day round begins: triple the
    amounts, raise the grade, and pick a new biome at random. Returns True if
    it just grew."""
    r = round_of(g)
    if r <= int(getattr(g, "crown_round", 0)):
        return False
    g.crown_round = r
    g.crown_paid = False
    g.crown_biome = random.choice(BIOMES)
    return True


def _grade_of(stack) -> int:
    return int(stack.quality if getattr(stack.defn, "quality", False) else 3)


def satisfied(g) -> bool:
    """Whether the Crown's chest holds enough of its specific goods, at grade."""
    d = demand(g)
    grade = d["grade"]
    lp_item = d["leaf_product_item"]
    leaf_item = d["leaf_item"]
    chest = getattr(g, "crown_chest", None)
    if chest is None:
        return False
    lp = leaf = wood = 0
    for stack in chest.slots:
        if stack is None:
            continue
        iid = stack.defn.id
        if iid == lp_item:
            if _grade_of(stack) >= grade:
                lp += stack.count
        elif iid == leaf_item:
            if _grade_of(stack) >= grade:
                leaf += stack.count
        elif iid == "wood":
            wood += stack.count          # wood carries no grade
    return lp >= d["leaf_product"] and leaf >= d["leaf"] and wood >= d["wood"]


def pay(g, recipient=None) -> None:
    """Take exactly what the ask demands out of the Crown's chest, then pay:
    10 coin on the first delivery, doubled each time after (10, 20, 40...).
    The coin goes to `recipient` -- the player's own purse by hand, or the
    horse's saddle bags so it carries the Crown's coin home."""
    d = demand(g)
    grade = d["grade"]
    need = {"lp": d["leaf_product"], "leaf": d["leaf"], "wood": d["wood"]}
    lp_item = d["leaf_product_item"]
    leaf_item = d["leaf_item"]
    chest = g.crown_chest
    for i in range(len(chest.slots)):
        stack = chest.slots[i]
        if stack is None:
            continue
        iid = stack.defn.id
        if iid == lp_item:
            key = "lp"
            if _grade_of(stack) < grade:
                continue
        elif iid == leaf_item:
            key = "leaf"
            if _grade_of(stack) < grade:
                continue
        elif iid == "wood":
            key = "wood"
        else:
            continue
        if need[key] <= 0:
            continue
        take = min(stack.count, need[key])
        stack.count -= take
        need[key] -= take
        if stack.count <= 0:
            chest.slots[i] = None
    # THE CROWN PAYS FOR WHAT IT TAKES. The first delivery earns 10 coin and
    # every success after that doubles it.
    payout = 10 * (2 ** int(getattr(g, "crown_deliveries", 0)))
    inv = recipient if recipient is not None else getattr(g, "inventory", None)
    if inv is not None:
        try:
            inv.add("coin", payout)
        except Exception:
            pass
    g.crown_deliveries = int(getattr(g, "crown_deliveries", 0)) + 1
    g.crown_payout = 10 * (2 ** int(g.crown_deliveries))
    g.crown_paid = True
    return payout

