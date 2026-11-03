"""nemesis.py -- THE SERVICE: one chief, and his men.

MARKS, AND NOTHING ELSE, for now. This file does not make anybody climb,
scheme, send omens or come for you in the dark: all of that is gone. What it
does is decide -- once, deterministically -- WHO IS WHO, so that the work that
comes later can find them:

  * ONE CHIEF of the secret police: in a settlement (never in a hub -- a hut is
    not on any map, and the service is part of the state it serves), wearing a
    LABOURER'S trade as his cover (never a trader: a trade that leaves town
    every week is not a cover, it is an absence), and never one of his own
    agents.
  * THREE AGENTS in every settlement -- and never a trader, because the trade
    has its own quota below.
  * THIRTY AGENTS AMONG THE TRADERS, drawn from the WHOLE trade: the men a
    town employs and the free carts alike. A trader walks in and out of every
    gate in the country and belongs to nobody, which is what an agent is for.
  * NOBODY INSIDE THE HUBS. The huts are the trade's, not the service's.

Nothing in the game reads `secret_police` or `secret_police_chief` yet. They
are there to be found, counted, and used later.
"""

from __future__ import annotations

import random

import economy

AGENTS_PER_TOWN = 3
AGENT_TRADERS = 30          # spread over the WHOLE trade, cart and townsman
CHIEF = None                 # the man, once seed_chief() has run
CHIEF_PLACE = None           # the settlement he works from
AGENTS: list = []            # [{"npc", "place", "rank", "hub"}] -- the roster

# -- SECRET NEWS -------------------------------------------------------------
# A SECOND KIND OF NEWS, and the opposite of the first. Regular news is
# CARRIED: anybody can be told, and tells the next man (NPC.knows, NPC.news).
# Secret news is ISSUED: it is planted in named heads and goes no further, and
# most people never hold any of it at all.
#
# THE FIRST KIND IS LOCATION -- who is operating where:
#
#   * every AGENT knows every agent's PLACE (his own included), and who the
#     chief is. He does not know the others' names.
#   * the CHIEF knows the ROSTER: each agent's name, his place, and his rank
#     (his standing in that town -- the trade that is his cover).
#   * NOBODY ELSE KNOWS ANY OF IT.
#
# A fact is held by a man as an ID in `NPC.secret_news` (a list, so it saves),
# and the fact itself lives here. Both directions are therefore answerable:
# what does this man know, and who knows this fact.
NOW = [0.0]                  # the game clock, set by the frame


def set_now(t: float) -> None:
    NOW[0] = float(t)


FACTS: dict = {}             # fact id -> the fact
KNOWERS: dict = {}           # fact id -> [man ids]
# WHO TOLD WHOM. A folder looted off a dead agent has to say a NAME -- "an
# agent at Ash Valley" is not a person you can go and find. `(fact, holder) ->
# the name of the man who told him`, or None if he learned it himself.
TOLD: dict = {}


def _fact(fid: str, kind: str, **data) -> dict:
    # WHEN IT WAS LEARNED. A message dies after three days, so every fact has to
    # know its own age -- without this a folder looted from an old body would
    # read like this morning's post.
    fact = dict(data, kind=kind, id=fid, t=float(NOW[0]))
    FACTS[fid] = fact
    return fact


def _give(npc, fid: str, frm: str | None = None) -> None:
    """One fact, into one head. Nobody else is told -- and WHO told him.
    The first man to hold a fact is its author, and his name is what the fact
    says it came from unless somebody else passed it on."""
    if npc is None:
        return
    held = getattr(npc, "secret_news", None)
    if held is None:
        held = []
        npc.secret_news = held
    if fid not in held:
        held.append(fid)
        KNOWERS.setdefault(fid, []).append(getattr(npc, "id", "?"))
        fact = FACTS.get(fid)
        if fact is not None:
            fact.setdefault("by", getattr(npc, "name", "?"))
        TOLD[(fid, id(npc))] = frm
        # A TURNED AGENT WHO HAS HEARD THE YARD'S ORDERS KNOWS WHOSE YARD IT IS.
        # The moment the service's own news includes the player's orders, the
        # man holding it can put a name to the leader -- and the network is told.
        if fact is not None and fact.get("kind") == "playerorder":
            note_leader(npc, at=(float(getattr(npc, "x", 0.0)),
                                 float(getattr(npc, "y", 0.0))))


# -- THE SECOND KIND OF SECRET: THE OFFENCE ----------------------------------
# An agent who WITNESSES something illegal knows it, and it is a fact like any
# other -- held in a named head, not broadcast. It moves only when one agent
# meets another, and then to that man and to whoever else is standing with
# them. It ends with agents and the chief: no townsman ever holds one.
#
# A MAN HAS ONE COUNT OF A THING. See the same hub farmer turn the same leaf
# three times or thirty, and it is one fact, not thirty. Do two different
# things -- grow it, then sell it -- and he has both, because they are two.
SEEN_PX = 260.0         # close enough to have watched it happen
TELL_PX = 160.0         # close enough to tell a man -- and whoever is with him
ILLEGAL_LEAF = ("tobacco", "red_mushroom", "agave")
ILLEGAL_DRUGS = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")
OFFENCE_VERB = {"grew": "GREW", "made": "MADE", "sold": "SOLD"}
PLACES: list = []       # every settlement and hut, for naming where it happened


def set_places(villages, hub_world) -> None:
    """Every place a crime can happen near: the settlements, and the huts."""
    PLACES[:] = (list(getattr(villages, "villages", ()) or ())
                 + list(getattr(hub_world, "hubs", ()) or ()))


def place_at(x: float, y: float):
    best, bd = None, 1e18
    for v in PLACES:
        d = (v.x - x) ** 2 + (v.y - y) ** 2
        if d < bd:
            best, bd = v, d
    return best


def is_service(npc) -> bool:
    return bool(getattr(npc, "secret_police", False)
                or getattr(npc, "secret_police_chief", False))


def witnesses_at(x: float, y: float, agents, radius: float = SEEN_PX) -> list:
    r2 = radius * radius
    return [a for a in agents
            if getattr(a, "alive", True)
            and ((a.x - x) ** 2 + (a.y - y) ** 2) <= r2]


def _item_name(item: str) -> str:
    return str(item).replace("_", " ")


def note_offence(actor, verb: str, item: str, x: float, y: float,
                 witnesses=()):
    """ONE FACT PER MAN PER KIND. Returns it, or None if it is not news.

    NOT NEWS WHEN THE MAN IS OURS: an agent's own work is operations, and
    operations are not written down anywhere -- not even in the log.
    """
    if actor is None:
        return None
    if is_service(actor):
        return None                    # operations, not news -- and not logged
    seen = [w for w in witnesses
            if w is not actor and is_service(w)
            and getattr(w, "alive", True)]
    if not seen:
        return None                    # NOBODY SAW IT: there is nothing to know
    aid = str(getattr(actor, "id", "") or getattr(actor, "name", "?"))
    fid = "offence:%s:%s" % (verb, aid)
    fact = FACTS.get(fid)
    if fact is None:
        place = place_at(x, y)
        where = getattr(place, "name", "somewhere")
        name = getattr(actor, "name", "somebody")
        fact = _fact(fid, "offence", actor=aid, name=name, verb=verb,
                     item=item,
                     text="%s %s %s IN %s"
                          % (name, OFFENCE_VERB.get(verb, verb.upper()),
                             _item_name(item), where),
                     place=where, x=round(float(x), 1), y=round(float(y), 1))
        try:
            import plog
            plog.log("OFFENCE", fact["text"], "| witnesses", len(seen),
                     "| place", fact["place"])
        except Exception:
            pass
    # ONLY THE MEN WHO SAW IT start with it. The chief is not told from here:
    # he hears it when one of them tells him (spread_on_contact), exactly like
    # everybody else in the service.
    for w in seen:
        _give(w, fid)
    return fact


# WHAT THE MEETINGS ACTUALLY DID -- read by tests, and logged when a fact moves.
STATS = {"calls": 0, "meetings": 0, "told": 0, "lonely": 0}


AT_PLACE_PAD = 220.0    # at the gate counts as at the place (a cart
                        # stops 70-140 px outside the wall)


def place_of(npc):
    """THE PLACE HE IS STANDING IN -- a settlement, or a hut, or nowhere.

    An agent at a gate is AT that town: the fence is inflated by a little more
    than the standoff a cart keeps, so a trader stopped outside the wall and a
    townsman inside it are in the same place.
    """
    x, y = getattr(npc, "x", 0.0), getattr(npc, "y", 0.0)
    for p in PLACES:
        r = getattr(p, "fence_rect", None)
        if r is None:
            continue
        if r.inflate(2 * AT_PLACE_PAD, 2 * AT_PLACE_PAD).collidepoint(x, y):
            return p
    return None


def note_caught(actor, town, units: int):
    """CAUGHT AT THE GATE: THE AGENTS OF THAT SETTLEMENT KNOW IT.

    Not a witness -- the men whose town it is. A search that finds something
    is a fact about the man who was carrying it, and the service keeps it: the
    agents operating out of that settlement, wherever inside it they stand.
    """
    if actor is None or town is None:
        return None
    key = str(getattr(actor, "id", "") or getattr(actor, "name", "?"))
    fid = "caught:" + key
    fact = FACTS.get(fid)
    if fact is None:
        name = getattr(actor, "name", "somebody")
        fact = _fact(fid, "caught", actor=key, name=name,
                     place=getattr(town, "name", "?"),
                     text="%s CAUGHT AT THE GATE OF %s WITH %d"
                          % (name, getattr(town, "name", "?"), int(units)))
        try:
            import plog
            plog.log("CAUGHT", fact["text"])
        except Exception:
            pass
    # THE AGENTS OF THAT SETTLEMENT: those standing in it, and those whose
    # patch it is -- they are the ones who work there.
    ids = {id(a["npc"]) for a in AGENTS
           if getattr(a, "place", None) is town}
    for a in agents():
        if id(a) in ids or place_of(a) is town:
            _give(a, fid)
    return fact


def spread_on_contact(agents=None) -> int:
    """AGENTS AT THE SAME PLACE TELL EACH OTHER -- all of it, both ways.

    Not a speaking distance: a PLACE. Two of the service standing in the same
    settlement, or the same hut, at the same tick, tell each other everything
    they know about offences -- and since the whole group is there, everyone in
    it ends up knowing. Nothing is broadcast: a man 10 px outside the wall is
    not in the town, and a man in the next town is not told.
    """
    live = [a for a in (agents if agents is not None
                        else [x["npc"] for x in AGENTS])
            if getattr(a, "alive", True)]
    STATS["calls"] += 1
    groups: dict = {}
    for a in live:
        p = place_of(a)
        if p is not None:
            groups.setdefault(id(p), []).append(a)
    told = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        STATS["meetings"] += len(group)
        # EVERY OFFENCE ANY OF THEM HOLDS, TO EVERY ONE OF THEM. Location facts
        # and the roster of names are ISSUED and never pass from hand to hand:
        # otherwise an agent would learn every other agent's name by shaking
        # the chief's hand, and the chief's one advantage would be everybody's.
        known = set()
        for a in group:
            known.update(f for f in (getattr(a, "secret_news", None) or ())
                         if f in FACTS and FACTS[f].get("kind") == "offence")
        if not known:
            continue
        # WHO TELLS WHOM: the first man in the group holding the fact is the
        # one who says it out loud. That name goes in the folder of every man
        # who hears it.
        first_holder = {}
        for a in group:
            for fid in (getattr(a, "secret_news", None) or ()):
                first_holder.setdefault(fid, a)
        for a in group:
            held = getattr(a, "secret_news", None) or ()
            for fid in known:
                if fid not in held:
                    _from = first_holder.get(fid, a)
                    _give(a, fid, frm=getattr(_from, "name", None))
                    told += 1
    if told:
        STATS["told"] += told
        try:
            import plog
            plog.log("SECRET", "a place told", told, "facts",
                     "| agents present", sum(len(g) for g in groups.values()))
        except Exception:
            pass
    return told


def agents() -> list:
    """Every agent and the chief, as they stand in THIS process right now."""
    out = [a["npc"] for a in AGENTS if getattr(a["npc"], "alive", True)]
    if CHIEF is not None and getattr(CHIEF, "alive", True):
        out.append(CHIEF)
    return out


def note_offence_seen(actor, verb: str, item: str):
    """A crime committed in THIS process (the player's own hands): the agents
    close enough to have watched it are told, and nobody else."""
    if actor is None:
        return None
    x = float(getattr(actor, "x", 0.0))
    y = float(getattr(actor, "y", 0.0))
    return note_offence(actor, verb, item, x, y, witnesses_at(x, y, agents()))


def turn(npc, place=None):
    """THE SERVICE TURNS HIM, WHERE HE STANDS.

    A man who has come to hate the player is not sent away -- he is recruited.
    He goes on working in the player's yard, and everything he sees from now on
    is the service's. He is told what an agent is told: where the others
    operate, and who the chief is.
    """
    if npc is None or not getattr(npc, "alive", True) or is_service(npc):
        return None
    npc.secret_police = True
    npc.secret_police_chief = False
    if place is None:
        place = place_of(npc) or getattr(npc, "village", None)
    if not any(a["npc"] is npc for a in AGENTS):
        AGENTS.append({"npc": npc, "place": place,
                       "rank": getattr(npc, "job", None) or "idler",
                       "hub": bool(getattr(place, "is_hub", False))})
    cid = ("chief:" + str(getattr(CHIEF, "id", "?"))
           if CHIEF is not None else None)
    for fid, fact in FACTS.items():
        if fact.get("kind") == "place" or (cid and fid == cid):
            _give(npc, fid)
    try:
        import plog
        plog.log("TURNED", getattr(npc, "name", "?"),
                 "in", getattr(place, "name", "?"),
                 "| working for the player:", bool(getattr(npc, "player_worker", False)))
    except Exception:
        pass
    return npc


def offences_of(npc) -> list:
    return [FACTS[f] for f in (getattr(npc, "secret_news", None) or ())
            if f in FACTS and FACTS[f].get("kind") == "offence"]


def knows(npc, fid: str) -> bool:
    return fid in (getattr(npc, "secret_news", None) or ())


def facts_of(npc) -> list:
    return [FACTS[f] for f in (getattr(npc, "secret_news", None) or ())
            if f in FACTS]


def who_knows(fid: str) -> list:
    return list(KNOWERS.get(fid, ()))


def _people(town):
    """Who in a town can be the service's: a living commoner."""
    return [n for n in getattr(town, "npcs", ())
            if getattr(n, "alive", False)
            and not getattr(n, "is_mayor", False)
            and not getattr(n, "is_king", False)
            and not getattr(n, "is_commander", False)
            and not getattr(n, "is_truth_teller", False)]


def _every_man(villages, hub_world):
    for v in list(getattr(villages, "villages", ()) or ()):
        for n in getattr(v, "npcs", ()):
            yield n
    for h in getattr(hub_world, "hubs", ()) or ():
        for n in getattr(h, "npcs", ()):
            yield n
    for c in getattr(hub_world, "_caravans", ()) or ():
        if getattr(c, "npc", None) is not None:
            yield c.npc


def clear(villages, hub_world) -> None:
    """Take every mark off -- and every secret with it.

    `secret_news` is SAVED (it is a list of plain strings), and the facts it
    names are rebuilt from scratch each launch. A man who kept yesterday's ids
    would be holding facts that no longer exist, or that belong to men who are
    no longer in the service: a leak of nothing, but still a leak. Re-issuing
    starts from an empty head.
    """
    for n in _every_man(villages, hub_world):
        n.secret_police = False
        n.secret_police_chief = False
        n.secret_news = None


def plant(villages, hub_world, seed: int = 20240501):
    """THREE IN EVERY SETTLEMENT (never a trader), AND THIRTY OF THE TRADE.

    Deterministic: the same world always has the same agents, because the seed
    is the world's own and the lists are walked in the order they were built.
    Re-running it is therefore harmless, which matters because the marks must
    also exist in a save written before they did.
    """
    global CHIEF, CHIEF_PLACE
    CHIEF, CHIEF_PLACE = None, None
    del AGENTS[:]
    FACTS.clear()
    KNOWERS.clear()
    clear(villages, hub_world)
    rng = random.Random(0x5EC3E7 ^ int(seed))
    towns = [v for v in getattr(villages, "villages", ()) or ()
             if not getattr(v, "is_hub", False)]
    town_agents = 0
    short = []
    for v in towns:
        pool = [n for n in _people(v) if getattr(n, "job", None) != "trader"]
        rng.shuffle(pool)
        take = pool[:AGENTS_PER_TOWN]
        if len(take) < AGENTS_PER_TOWN:
            short.append("%s(%d)" % (v.name, len(take)))
        for n in take:
            n.secret_police = True
            AGENTS.append({"npc": n, "place": v,
                           "rank": getattr(n, "job", None) or "idler",
                           "hub": False})
            town_agents += 1
    # THIRTY OF THE TRADE, FROM THE WHOLE TRADE. Not only the free carts: a
    # town's own trader carries goods between towns on the same roads, sleeps
    # in the same squares, and is asked the same questions at the gate. The
    # draw is over every working trader in the world -- the men a town employs
    # and the carts that belong to nobody -- and it stops at thirty.
    carts = list(getattr(hub_world, "_caravans", ()) or ())
    trade = []
    for t in towns:
        for n in getattr(t, "npcs", ()):
            if (getattr(n, "alive", False)
                    and getattr(n, "job", None) == "trader"
                    and not getattr(n, "secret_police_chief", False)):
                trade.append((n, t, False))          # a town's trader
    for c in carts:
        n = getattr(c, "npc", None)
        if n is not None and getattr(n, "alive", False):
            trade.append((n, getattr(c, "hub", None), True))   # a free cart
    rng.shuffle(trade)
    traders = carts_taken = 0
    for n, place, is_cart in trade[:AGENT_TRADERS]:
        n.secret_police = True
        AGENTS.append({"npc": n, "place": place, "rank": "trader",
                       "hub": bool(is_cart)})
        traders += 1
        carts_taken += 1 if is_cart else 0
    try:
        economy._note("SERVICE   %d agents in %d settlements (up to %d each, "
                      "never a trader); %d of %d traders are agents "
                      "(%d town, %d cart)"
                      % (town_agents, len(towns), AGENTS_PER_TOWN, traders,
                         len(trade), traders - carts_taken, carts_taken))
    except Exception:
        pass
    if short:
        try:
            economy._note("SERVICE   thin in: " + ", ".join(short[:8]))
        except Exception:
            pass
    return town_agents, traders


def seed_chief(villages, player, seed: int = 20240501):
    """THE ONE. A settlement, a labourer's trade, and never one of his own."""
    global CHIEF, CHIEF_PLACE
    rng = random.Random(0x4E3E5155 ^ int(seed))
    px = float(getattr(player, "x", 0.0))
    py = float(getattr(player, "y", 0.0))
    best = None
    best_d = -1.0
    for v in getattr(villages, "villages", ()) or ():
        if getattr(v, "is_hub", False) or getattr(v, "is_capital", False):
            continue
        men = [n for n in _people(v)
               if not getattr(n, "secret_police", False)
               and getattr(n, "job", None) != "trader"
               and getattr(n, "trade_state", "none") == "none"]
        if not men:
            continue
        d = (v.x - px) ** 2 + (v.y - py) ** 2
        if d > best_d:                     # a long way off, never next door
            best, best_d = (v, men), d
    if best is None:
        return None
    town, men = best
    man = rng.choice(men)
    man.secret_police = False
    man.secret_police_chief = True
    CHIEF, CHIEF_PLACE = man, town
    try:
        economy._note("SERVICE   chief: %s, a %s of %s  (never a hut, never a "
                      "trader, never one of his own)"
                      % (man.name, getattr(man, "job", None) or "idler", town.name))
    except Exception:
        pass
    return man


def issue() -> dict:
    """PLANT THE SECRET NEWS. Once, after plant() and seed_chief()."""
    FACTS.clear()
    KNOWERS.clear()
    if CHIEF is None:
        return {"place": 0, "roster": 0, "chief": 0}
    cid = "chief:" + str(getattr(CHIEF, "id", "?"))
    _fact(cid, "chief", agent=CHIEF.id,
          name=getattr(CHIEF, "name", "?"),
          place=getattr(CHIEF_PLACE, "name", "?"),
          rank=getattr(CHIEF, "job", None) or "idler",
          text="THE CHIEF OF THE SERVICE IS %s, in %s."
               % (str(getattr(CHIEF, "name", "?")).upper(),
                  getattr(CHIEF_PLACE, "name", "?")))
    places, rosters = [], []
    for a in AGENTS:
        n = a["npc"]
        where = getattr(a["place"], "name", "?")
        pid = "place:" + str(getattr(n, "id", "?"))
        _fact(pid, "place", agent=n.id, place=where,
              hub=bool(a.get("hub")),
              text="THE SERVICE OPERATES IN %s -- I am posted there."
                   % str(where).upper())
        rid = "roster:" + str(getattr(n, "id", "?"))
        _fact(rid, "roster", agent=n.id, name=getattr(n, "name", "?"),
              place=where, rank=a.get("rank") or "idler",
              hub=bool(a.get("hub")),
              text="%s, %s, %s -- one of ours."
                   % (str(getattr(n, "name", "?")).upper(), where,
                      a.get("rank") or "idler"))
        places.append(pid)
        rosters.append(rid)
    # EVERY AGENT: every place (his own included), and who the chief is.
    _chief_name = getattr(CHIEF, "name", "the chief")
    for pid in places:
        _fact(pid, "place", **{k: v for k, v in FACTS[pid].items()
                               if k not in ("id", "kind", "t")})
        FACTS[pid]["by"] = _chief_name
    for rid in rosters:
        FACTS[rid]["by"] = _chief_name
    FACTS[cid]["by"] = _chief_name
    for a in AGENTS:
        for pid in places:
            _give(a["npc"], pid, frm=_chief_name)
        _give(a["npc"], cid, frm=_chief_name)
    # THE CHIEF: the roster -- names, places and ranks -- and himself.
    for rid in rosters:
        _give(CHIEF, rid)
    _give(CHIEF, cid)
    # NOBODY ELSE. That is the whole of the rule: no other man is given any of
    # these ids, so he can neither repeat them nor be tricked into confirming.
    return {"place": len(places), "roster": len(rosters), "chief": 1}


def secret_summary() -> str:
    """What the service knows, and who holds it -- counted from the marks."""
    n_agents = len(AGENTS)
    agent_holds = [len(getattr(a["npc"], "secret_news", None) or ())
                   for a in AGENTS]
    chief_holds = len(getattr(CHIEF, "secret_news", None) or ()) if CHIEF else 0
    by_kind: dict = {}
    for f in FACTS.values():
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
    dupes = len(AGENTS) - len({str(getattr(a["npc"], "id", "?")) for a in AGENTS})
    return ("secret news: %d facts (%d place, %d roster, %d chief); "
            "each of %d agents holds %s; chief holds %d; nobody else holds any%s"
            % (len(FACTS), by_kind.get("place", 0), by_kind.get("roster", 0),
               by_kind.get("chief", 0), n_agents,
               sorted(set(agent_holds)), chief_holds,
               ("; DUPLICATE NPC IDS AMONG AGENTS: %d" % dupes) if dupes else ""))


LEADER_ID = "leader:identified"
LEADER = "the Kingpin"          # what the service calls the man behind the yard


def note_leader(agent, player=None, at=None) -> str | None:
    """THE SERVICE LEARNS WHO THE LEADER IS -- ONCE, AND ALL AT ONCE.

    Two things can put a name to the organisation: a dead worker of the
    player's seen by an agent (the body is the evidence), and a turned agent
    who has heard the player's own orders. When either happens the fact is
    written down, signed by the man who found it, and **given to every agent in
    the network** -- this is not gossip that has to travel from mouth to mouth,
    it is the service's own conclusion, and it goes everywhere the service is.
    """
    if agent is None:
        return None
    if LEADER_ID in FACTS:
        return None                      # it is already known
    who = getattr(player, "name", None) or LEADER
    text = ("THE LEADER OF THE CRIMINAL ORGANISATION IS %s -- "
            "the man whose yard the workers answer to." % str(who).upper())
    fact = _fact(LEADER_ID, "leader", text=text, place=None,
                 name=getattr(agent, "name", "?"))
    # WHERE THE NEWS CAME FROM: the body, the yard, the spot he was seen. The
    # crown sends its men there, so the fact has to remember the place.
    fact["at"] = at or (float(getattr(agent, "x", 0.0)),
                        float(getattr(agent, "y", 0.0)))
    fact["by"] = getattr(agent, "name", "?")
    if CHIEF is not None:
        _give(CHIEF, LEADER_ID, frm=getattr(agent, "name", None))
    for a in AGENTS:
        _give(a["npc"], LEADER_ID,
              frm=getattr(agent, "name", None) if a["npc"] is not agent else None)
    try:
        import plog
        plog.log("LEADER", "identified by", getattr(agent, "name", "?"),
                 "| spread to", len(AGENTS), "agent(s)")
    except Exception:
        pass
    return LEADER_ID


def folder_messages(npc) -> list:
    """A DEAD AGENT'S MAIL, with a NAME on every line.

    `FROM` is the man who told him -- or, if he learned it himself, the name
    recorded as the fact's author (his own, for something he witnessed with his
    own eyes). Nothing here is a place pretending to be a person.
    """
    out = []
    for fid in (getattr(npc, "secret_news", None) or ()):
        fact = FACTS.get(fid)
        if fact is None:
            continue
        sender = (TOLD.get((fid, id(npc))) or fact.get("by") or "the chief")
        where = None
        for a in AGENTS:             # where the sender can be found now
            if getattr(a["npc"], "name", None) == sender and a.get("place"):
                where = getattr(a["place"], "name", None)
                break
        out.append({
            "from": sender,
            "where": where or (getattr(fact.get("place"), "name", None)
                               if isinstance(fact.get("place"), object)
                               and not isinstance(fact.get("place"), str)
                               else fact.get("place")),
            "text": fact.get("text") or " ".join(
                "%s %s" % (k, v) for k, v in sorted(fact.items())
                if k not in ("id", "kind", "t", "by")),
            "t": float(fact.get("t", 0.0)),
            "kind": fact.get("kind"),
        })
    return out


def summary(villages, hub_world) -> str:
    """WHAT IS ACTUALLY OUT THERE, counted from the marks themselves."""
    towns = [v for v in getattr(villages, "villages", ()) or ()
             if not getattr(v, "is_hub", False)]
    a_town = sum(1 for v in towns for n in getattr(v, "npcs", ())
                 if getattr(n, "secret_police", False)
                 and getattr(n, "job", None) != "trader")
    a_trade_town = sum(1 for v in towns for n in getattr(v, "npcs", ())
                       if getattr(n, "secret_police", False)
                       and getattr(n, "job", None) == "trader")
    carts = list(getattr(hub_world, "_caravans", ()) or ())
    a_trade_free = sum(1 for c in carts
                       if getattr(getattr(c, "npc", None), "secret_police", False))
    trade_all = sum(1 for v in towns for n in getattr(v, "npcs", ())
                    if getattr(n, "job", None) == "trader") + len(carts)
    in_huts = sum(1 for h in getattr(hub_world, "hubs", ()) or ()
                  for n in getattr(h, "npcs", ())
                  if getattr(n, "secret_police", False))
    return ("1 chief=%s  agents: %d settlement, %d of %d traders "
            "(%d town + %d free), %d inside the huts"
            % (getattr(CHIEF, "name", None), a_town,
               a_trade_town + a_trade_free, trade_all,
               a_trade_town, a_trade_free, in_huts))
