"""research.py -- the research tree, bought with market coin.

Cards are researched one at a time: pick one, pay its coin, and it runs for a
while before the unlock lands.
"""

RESEARCH_SECONDS = 30.0        # how long a card takes to finish researching

CARDS = [
    {"id": "animals", "name": "Animals", "cost": 10, "icon": "hide",
     "desc": "Unlocks the Fur market, and the ability to ride horses."},
]


def init(g) -> None:
    g.research_cards = {c["id"]: None for c in CARDS}   # None | started_at


def state(g, card_id: str) -> str:
    """'locked', 'researching' or 'done' for a card."""
    t = g.research_cards.get(card_id)
    if t is None:
        return "locked"
    if g.now - t >= RESEARCH_SECONDS:
        return "done"
    return "researching"


def start(g, card) -> bool:
    """Pay for the card and begin researching it. False if he cannot afford it."""
    if g.inventory.count_of("coin") < card["cost"]:
        return False
    g.inventory.consume("coin", card["cost"])
    g.research_cards[card["id"]] = g.now
    return True
