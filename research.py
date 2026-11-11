"""research.py -- the research tree, bought with market coin and worked by
researchers behind the desk.

A card costs coin to START, and then needs RESEARCH POINTS to finish: each
second of a researcher's work gives one point per skill level. The first
card, Animals, needs 100 points.
"""

CARDS = [
    {"id": "animals", "name": "Animals", "cost": 100, "icon": "hide",
     "desc": "Unlocks the Fur market, and the ability to ride horses.",
     "points": 100},
    {"id": "hide_armor", "name": "Hide Armor", "cost": 300, "icon": "hide_armor",
     "desc": "Stitched hide you can wear. Doubles your health.",
     "points": 100, "requires": "animals"},
    {"id": "ironworking", "name": "Ironworking", "cost": 500, "icon": "iron_bar",
     "desc": "Smelt iron ore into iron bars at the forge.",
     "points": 300, "requires": "hide_armor"},
    {"id": "gunsmithing", "name": "Gunsmithing", "cost": 500, "icon": "musket",
     "desc": "Unlocks ammo and Musket.",
     "points": 0, "requires": "ironworking"},
    {"id": "industry", "name": "Industry", "cost": 500, "icon": "gear",
     "desc": "Unlocks gears, with which you can later build machines.",
     "points": 0, "requires": "ironworking"},
    {"id": "two_shot", "name": "Two-Shot", "cost": 500, "icon": "musket",
     "desc": "A better musket, shoots two bullets without reloading.",
     "points": 300, "requires": "gunsmithing"},
    {"id": "textiles", "name": "Textiles", "cost": 500, "icon": "textile",
     "desc": "Allows to produce and sell textiles, made from cotton.",
     "points": 300, "requires": "industry"},
    {"id": "spice_sauce", "name": "Spice sauces", "cost": 300, "icon": "sauce",
     "desc": "Allows production and sale of New World spice sauces.",
     "points": 300, "requires": "industry"},
    {"id": "reinforced_armor", "name": "Reinforced armor", "cost": 800, "icon": "reinforced_armor",
     "desc": "Reinforced armor made with iron plates and textiles.",
     "points": 500, "requires": "textiles"},
    {"id": "rifle", "name": "Rifle", "cost": 500, "icon": "rifle",
     "desc": "A proper modern rifle, much shorter reload time.",
     "points": 300, "requires": "two_shot"},
]


def init(g) -> None:
    g.research_cards = {c["id"]: None for c in CARDS}   # None | "researching" | "done"
    g.research_active = None      # the card id currently earning points
    g.research_points = 0.0       # points earned toward the active card


def get_card(g, card_id: str):
    for c in CARDS:
        if c["id"] == card_id:
            return c
    return None


def state(g, card_id: str) -> str:
    """'shadow' (prerequisite not done), 'locked', 'researching' or 'done'."""
    v = g.research_cards.get(card_id)
    c = get_card(g, card_id)
    if c is not None and c.get("requires") and state(g, c["requires"]) != "done":
        return "shadow"
    if v is None:
        return "locked"
    if v == "done":
        return "done"
    return "researching"


def start(g, card) -> bool:
    """Pay for the card and begin researching it. False if he cannot afford it
    or its prerequisite is not done."""
    c = get_card(g, card["id"])
    if c is not None and c.get("requires") and state(g, c["requires"]) != "done":
        return False
    if g.inventory.count_of("coin") < card["cost"]:
        return False
    g.inventory.consume("coin", card["cost"])
    g.research_cards[card["id"]] = "researching"
    g.research_active = card["id"]
    g.research_points = 0.0
    return True


def add_points(g, n: float) -> None:
    """A researcher's work lands here. When the active card is full, it finishes."""
    if g.research_active is None:
        return
    c = get_card(g, g.research_active)
    if c is None:
        return
    g.research_points += n
    if g.research_points >= c["points"]:
        g.research_cards[g.research_active] = "done"
        g.research_active = None
