"""research.py -- the research tree, bought with market coin and worked by
researchers behind the desk.

A card costs coin to START, and then needs RESEARCH POINTS to finish: each
second of a researcher's work gives one point per skill level. The first
card, Animals, needs 100 points.
"""

CARDS = [
    {"id": "animals", "name": "Animals", "cost": 10, "icon": "hide",
     "desc": "Unlocks the Fur market, and the ability to ride horses.",
     "points": 100},
]


def init(g) -> None:
    g.research_cards = {c["id"]: None for c in CARDS}   # None | "researching" | "done"
    g.research_active = None      # the card id currently earning points
    g.research_points = 0.0       # points earned toward the active card


def card(g, card_id: str):
    for c in CARDS:
        if c["id"] == card_id:
            return c
    return None


def state(g, card_id: str) -> str:
    """'locked', 'researching' or 'done' for a card."""
    v = g.research_cards.get(card_id)
    if v is None:
        return "locked"
    if v == "done":
        return "done"
    return "researching"


def start(g, card) -> bool:
    """Pay for the card and begin researching it. False if he cannot afford it."""
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
    c = card(g, g.research_active)
    if c is None:
        return
    g.research_points += n
    if g.research_points >= c["points"]:
        g.research_cards[g.research_active] = "done"
        g.research_active = None
