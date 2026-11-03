"""orders.py -- THE PLAYER'S OWN SECRET NEWS.

The service keeps its knowledge as FACTS held in named heads (nemesis.py).
This is the same idea for the other side of the table: **the player's
organisation has its own secret news, and it is secret in the same way.**

THE RULE
--------
An order the player gives is known by exactly two parties: **the player** and
**the man he gave it to**. Nobody else in the world holds it -- not the other
workers, not the towns, not the service. A handoff of goods inside the
organisation ("I took four wheat off the shelf", "the batch went on the stall")
is the same kind of thing: a fact held by the men involved, and by nobody else.

The agents' own orders work the same way round: their orders are already secret
(nemesis: `is_service` men are never news), and the public -- including the
player -- knows nothing of them until he *finds out*, by witness, by an
interrogation or by turning a man.

WHY IT IS A SEPARATE LEDGER FROM NEMESIS
----------------------------------------
Because it must be able to LEAK. Today the two ledgers never touch: a worker
knows your orders, the chief knows nothing. The moment a worker who knows them
is turned (work.turn_the_bitter -> nemesis.turn) or talks, the service learns
what he held -- and that is the whole point of keeping them: a secret nobody
can betray is not a secret, it is a spreadsheet.

A fact is an id in a list on the holder (`npc.player_orders`, a list, so it
saves), and the fact itself lives here. Both directions are answerable: what
does this man know, and who knows this.

KINDS
-----
    order:<kind>:<man>     an instruction ("put your work on the stall")
    handoff:<man>:<item>   goods moving (a batch to the stall, a draw from
                           the chest) -- one per man per item, so a busy yard
                           does not become a million lines
    hire / fire            the payroll itself

NONE OF THESE ARE WRITTEN TO THE PUBLIC LOG except a one-line note, because
the log is a debugging tool and the game must not tell the player's secrets to
anybody. `plog.log("ORDER", ...)` is the player's own record of what he told
whom -- it is his ledger, not a rumour in the world.
"""

from __future__ import annotations

FACTS: dict = {}             # fact id -> the fact
KNOWERS: dict = {}           # fact id -> [man ids]

# WHO ELSE SAW IT. A secret is held by the man who did the thing and by anybody
# who happened to be looking -- a neighbour, another of the player's men, a
# trader stopped at the gate. The same rule the service's offences use: a fact
# needs no witness to exist, but every witness gets it.
SEEN_PX = 260.0

# What a man carries, in words the player would use, for reading later.
VERB = {"market": "put his work on the stall",
        "chest": "put his work in the chest",
        "stop_making": "stop making",
        "make_again": "make again",
        "stop_selling": "stop selling",
        "sell_again": "sell again",
        "price": "his price is",
        "hire": "was hired",
        "fire": "was put out"}


def _fact(fid: str, kind: str, **data) -> dict:
    got = FACTS.get(fid)
    if got is not None:
        got.update(data)
        return got
    fact = dict(data, kind=kind, id=fid)
    FACTS[fid] = fact
    return fact


def _give(npc, fid: str) -> bool:
    """One fact into one head. Nobody else is told -- that is the whole rule."""
    if npc is None:
        return False
    held = getattr(npc, "player_orders", None)
    if not isinstance(held, list):
        held = []
        npc.player_orders = held
    if fid in held:
        return False
    held.append(fid)
    KNOWERS.setdefault(fid, []).append(getattr(npc, "id", "?"))
    return True


def _witnesses(x: float, y: float, exclude=()) -> list:
    """EVERYONE WHO CAN SEE THAT SPOT, right now.

    Townsmen in the square, travellers on the road, the men of a hut -- and the
    service's own agents, who are men like any other and have eyes. The cheap
    box test first, the circle second, so a thousand people cost a thousand
    comparisons and not a thousand square roots.
    """
    out = []
    try:
        import village as _vm
        pool = list(getattr(_vm, "PEOPLE", ())) + list(getattr(_vm, "TRAVELLERS", ()))
    except Exception:
        pool = []
    try:
        import nemesis
        pool = pool + list(nemesis.agents())
    except Exception:
        pass
    for n in pool:
        if n is None or not getattr(n, "alive", True):
            continue
        if any(n is e for e in exclude):
            continue
        dx = getattr(n, "x", 1e9) - x
        dy = getattr(n, "y", 1e9) - y
        if abs(dx) > SEEN_PX or abs(dy) > SEEN_PX:
            continue
        if dx * dx + dy * dy <= SEEN_PX * SEEN_PX:
            out.append(n)
    return out


def _service_told(fid: str, text: str) -> None:
    """AN AGENT WHO SAW IT KNOWS IT -- and the service keeps its own copy.

    This is the only bridge between the two ledgers, and it is built of eyes:
    nothing here hears about an order unless one of its men was standing there.
    """
    try:
        import nemesis
        sfid = "playerorders:" + fid
        nemesis._fact(sfid, "playerorder", text="THE YARD: " + text)
        for a in nemesis.agents():
            nemesis._give(a, sfid)
    except Exception:
        pass


def _note(*parts) -> None:
    try:
        import plog
        plog.log("ORDER", *parts)
    except Exception:
        pass


def order(player, npc, kind: str, item: str = "", value=None) -> dict | None:
    """THE PLAYER TELLS ONE MAN ONE THING. He and that man know it; nobody else."""
    if npc is None or kind not in VERB:
        return None
    wid = str(getattr(npc, "id", "") or getattr(npc, "name", "?"))
    fid = "order:%s:%s" % (kind, wid)
    fact = _fact(fid, "order", kind_="order", man=wid,
                 name=getattr(npc, "name", "?"), verb=kind, item=item,
                 value=value,
                 text="%s %s%s" % (getattr(npc, "name", "?"), VERB[kind],
                                   (" " + item) if item else ""))
    _give(npc, fid)
    seen = _witnesses(getattr(npc, "x", 0.0), getattr(npc, "y", 0.0),
                      exclude=(npc,))
    for w in seen:
        _give(w, fid)
    fact["seen"] = len(seen)
    if any(getattr(w, "secret_police", False) for w in seen):
        _service_told(fid, fact["text"])
    _note(fact["text"], ("= " + str(value)) if value is not None else "",
          "| known by the player, him, and %d who saw it" % len(seen))
    return fact


def handoff(player, who, item: str, count: int, where: str) -> dict | None:
    """GOODS MOVING INSIDE THE ORGANISATION: one fact per man per item.

    The man who carried them knows, and the player knows. The shelf they went
    to does not talk, and neither does anybody standing next to it.
    """
    if who is None or int(count) <= 0:
        return None
    wid = str(getattr(who, "id", "") or getattr(who, "name", "?"))
    fid = "handoff:%s:%s:%s" % (where, wid, item)
    fact = FACTS.get(fid)
    total = int(count) + (int(fact.get("count", 0)) if fact else 0)
    fact = _fact(fid, "handoff", man=wid, name=getattr(who, "name", "?"),
                 item=item, where=where, count=total,
                 text="%s: %d %s -> %s" % (getattr(who, "name", "?"), total,
                                           item, where))
    _give(who, fid)
    seen = _witnesses(getattr(who, "x", 0.0), getattr(who, "y", 0.0),
                      exclude=(who,))
    for w in seen:
        _give(w, fid)
    fact["seen"] = int(fact.get("seen", 0)) + len(seen)
    if any(getattr(w, "secret_police", False) for w in seen):
        _service_told(fid, fact["text"])
    _note(fact["text"], "| known by the player, him, and %d who saw it"
          % len(seen))
    return fact


def hire_order(player, npc) -> dict | None:
    return order(player, npc, "hire")


def fire_order(player, npc) -> dict | None:
    return order(player, npc, "fire")


# -- what a man knows, and what happens when he talks ----------------------
def held(npc) -> list:
    got = getattr(npc, "player_orders", None)
    return [FACTS[f] for f in (got or ()) if f in FACTS]


def who_knows(fid: str) -> list:
    return list(KNOWERS.get(fid, ()))


def leak(npc, to=None) -> list:
    """A WORKER WHO TALKS. Everything he held about the yard goes with it.

    Called when one of the player's men is turned by the service: the chief
    did not know the player's orders, and now he does -- through a man, not a
    crystal ball, exactly like every other fact in this world.
    """
    out = held(npc)
    if not out:
        return []
    try:
        import nemesis
        for fact in out:
            fid = "playerorders:" + str(fact.get("id", "?"))
            nem = nemesis._fact(fid, "playerorder",
                                name=fact.get("name", "?"),
                                text="THE YARD: " + fact.get("text", ""))
            for a in nemesis.agents():
                nemesis._give(a, fid)
    except Exception:
        pass
    _note("%s TALKED: %d things about the yard are now the service's"
          % (getattr(npc, "name", "?"), len(out)))
    return out


def summary() -> str:
    orders = sum(1 for f in FACTS.values() if f.get("kind") == "order")
    hand = sum(1 for f in FACTS.values() if f.get("kind") == "handoff")
    holders = len({k for f in FACTS for k in KNOWERS.get(f, ())})
    return ("%d order(s), %d handoff lot(s), held by %d man/men"
            % (orders, hand, holders))


def clear() -> None:
    FACTS.clear()
    KNOWERS.clear()
