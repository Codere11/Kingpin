"""crown.py -- THE CROWN'S DEMAND, delivered to the ship.

Every three in-game days the Crown asks for more: leaf product, raw leaf, and
wood, tripling each time and demanding one grade higher. The player carries the
goods to the ship and drops them into the Crown's chest; once the ask is met he
passes that round.
"""
import economy
import quality

# what counts as "leaf product": the finished goods made from leaf
LEAF_PRODUCTS = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")

# the opening ask, before any escalation
BASE = {"leaf_product": 30, "leaf": 100, "wood": 300}
GRADE_START = 2            # D
DAYS_PER_ROUND = 3


def demand(g):
    """The Crown's current ask: amounts and the grade index they must meet."""
    r = int(getattr(g, "crown_round", 0))
    mult = 3 ** max(0, r)
    grade = min(len(quality.GRADES) - 1, GRADE_START + r)
    return {
        "leaf_product": BASE["leaf_product"] * mult,
        "leaf": BASE["leaf"] * mult,
        "wood": BASE["wood"] * mult,
        "grade": grade,
    }


def round_of(g) -> int:
    """Which three-day round the clock is in."""
    return int(g.now / economy.DAY_LENGTH / DAYS_PER_ROUND)


def escalate(g) -> bool:
    """Advance the demand when a new three-day round begins. Returns True if
    it just grew."""
    r = round_of(g)
    if r <= int(getattr(g, "crown_round", 0)):
        return False
    g.crown_round = r
    g.crown_paid = False
    return True


def _grade_of(stack) -> int:
    return int(stack.quality if getattr(stack.defn, "quality", False) else 3)


def satisfied(g) -> bool:
    """Whether the Crown's chest holds enough of everything, at grade."""
    d = demand(g)
    grade = d["grade"]
    chest = getattr(g, "crown_chest", None)
    if chest is None:
        return False
    lp = leaf = wood = 0
    for stack in chest.slots:
        if stack is None:
            continue
        iid = stack.defn.id
        if iid in LEAF_PRODUCTS:
            if _grade_of(stack) >= grade:
                lp += stack.count
        elif iid in economy.LEAF:
            if _grade_of(stack) >= grade:
                leaf += stack.count
        elif iid == "wood":
            wood += stack.count          # wood carries no grade
    return lp >= d["leaf_product"] and leaf >= d["leaf"] and wood >= d["wood"]


def pay(g) -> None:
    """Take exactly what the ask demands out of the Crown's chest."""
    d = demand(g)
    grade = d["grade"]
    need = {"leaf_product": d["leaf_product"], "leaf": d["leaf"], "wood": d["wood"]}
    chest = g.crown_chest
    for i in range(len(chest.slots)):
        stack = chest.slots[i]
        if stack is None:
            continue
        iid = stack.defn.id
        if iid in LEAF_PRODUCTS:
            key = "leaf_product"
            if _grade_of(stack) < grade:
                continue
        elif iid in economy.LEAF:
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
    g.crown_paid = True


def line(d) -> str:
    """One line of the ask, for the screen."""
    g = quality.letter(d["grade"])
    return ("%d leaf product, %d leaf, %d wood  (grade %s or higher)"
            % (d["leaf_product"], d["leaf"], d["wood"], g))
