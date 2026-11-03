"""work.py -- MEN FOR HIRE, and what the player may hire them as.

The rule is the station. A man is recruited to a TRADE, and the player can only
offer a trade he can put a man to:

    farmer    needs a plot the player has sown (a field is a field, not a bench)
    logger    needs nothing: the woods are nobody's
    miner     one per mine he has placed
    smith     one per forge he has placed
    artisan   one per bench he has placed
    brewer    one per brewhouse he has placed

WHO IS WORTH ASKING: a man with no trade, no plot and no post -- and less than
fifty coin in his pocket. A man with money is not looking for work; a man with
a living already has one.

WHAT HE IS PAID: what the government would pay his trade, plus 30 per cent --
the player is buying the man, not undercutting the state.
"""

from __future__ import annotations

import economy

MAX_POCKET = 50            # coin; over this and he is not looking for work
PAY_MARGIN = 1.30          # the state's wage, plus this

TRADES = (("farm", "farmer"), ("logger", "logger"), ("mine", "miner"),
          ("smith", "smith"), ("lab", "artisan"), ("brewery", "brewer"),
          ("soldier", "soldier"))
STATION_OF = {"mine": "mine", "smith": "smith", "lab": "lab",
              "brewery": "brewery"}
# A SOLDIER IS PAID DOUBLE A FARMER, and the player has to ARM him.
SOLDIER_PAY_MULT = 2.0
SOLDIER_AMMO_ISSUE = 60          # what he is armed with when hired
TRAIN_MELEE_DAYS = 3.0           # 0 -> master of the axe, at a dummy
TRAIN_RANGED_DAYS = 5.0          # 0 -> master of the gun, at a target
TARGET_AMMO_PER_DAY = 10.0       # the range eats ten rounds a day
SHOT_SECONDS = 60.0              # ...one shot a minute, which is the same thing
DUMMY_STRIKE_SECONDS = 1.2       # how often the post takes a blow
TRAIN_KINDS = ("dummy", "target")
DAY = 600.0                      # the game's day, in seconds of world time


def is_idle(npc) -> bool:
    """No trade, no plot, no post -- and nobody's office."""
    return (not getattr(npc, "job", None)
            and getattr(npc, "farm_plot", None) is None
            and getattr(npc, "workplace", None) is None
            and not getattr(npc, "defender", False)
            and not getattr(npc, "is_commander", False)
            and not getattr(npc, "is_mayor", False)
            and not getattr(npc, "is_king", False))


HATE_AT = 40.0             # the band where a man says "Fuck off."


def regard_of(npc, player) -> float:
    """How he feels about the player, 0..100 -- the truth-teller's own number.

    Read through dialogue's rule (base, plus what the two of them have made of
    each other), imported at the call and not at the top: dialogue imports this
    module, and a cycle at import time is how a module disappears.
    """
    try:
        import dialogue
        return dialogue.player_regard(npc, player)
    except Exception:
        return 50.0


def hates(npc, player) -> bool:
    return regard_of(npc, player) <= HATE_AT


def qualifies(npc, player=None) -> bool:
    """IDLE, POOR -- AND NOT A MAN WHO HATES YOU.

    A man who would tell you to fuck off will not take your coin either: he is
    not offered the work and he cannot be taken on if he is.
    """
    if not getattr(npc, "alive", True) or not is_idle(npc):
        return False
    if int(getattr(npc, "coins", 0) or 0) >= MAX_POCKET:
        return False
    if player is not None and hates(npc, player):
        return False
    return True


def refusal(npc, player=None) -> str:
    """WHY HE WILL NOT TAKE THE WORK, in his own words.

    The row used to be HIDDEN when a man was not worth asking, so the player
    saw no option at all and concluded the game had none -- in a town of
    twenty-two men, eighteen have a trade and two have money, and only two are
    for hire. The rule was right; hiding it was not. He says no, and says why.
    """
    if player is not None and is_employed(player, npc):
        return "I already work for you."
    job = getattr(npc, "job", None)
    if job:
        # HIS OWN TRADE, IN WORDS -- not the key out of the recipe table.
        return {"farm": "I work a field here.",
                "logger": "I cut wood here.",
                "mine": "I work the pit here.",
                "smith": "I am the smith here.",
                "lab": "I work the bench here.",
                "brewery": "I brew here.",
                "trader": "I am a trader here.",
                "defender": "I am on the watch here.",
                "hand": "I take what work there is here."}.get(
                    job, "I have my own trade here.")
    for flag, line in (("is_king", "I am the King."),
                       ("is_mayor", "I am the mayor of this town."),
                       ("is_commander", "I command the garrison."),
                       ("defender", "I am on the town's watch.")):
        if getattr(npc, flag, False):
            return line
    if getattr(npc, "workplace", None) is not None:
        return "I already have a post."
    if getattr(npc, "farm_plot", None) is not None:
        return "I have a field of my own."
    if int(getattr(npc, "coins", 0) or 0) >= MAX_POCKET:
        return ("I have %d coin in my pocket. Why would I work for you?"
                % int(npc.coins))
    if player is not None and hates(npc, player):
        return "Fuck off."
    return "Not today."


def _stations(player) -> dict:
    out: dict = {}
    for wp in getattr(player, "workplaces", ()) or ():
        k = getattr(wp, "kind", None)
        out[k] = out.get(k, 0) + 1
    return out


def _workers(player) -> dict:
    out: dict = {}
    for n in getattr(player, "workers", ()) or ():
        if getattr(n, "alive", True):
            out[n.job] = out.get(n.job, 0) + 1
    return out


def slots(player, trade: str) -> int:
    """How many more men he can put to this trade right now."""
    have = _workers(player).get(trade, 0)
    if trade == "farm":
        return 9999 if len(getattr(player, "plots", ()) or ()) > 0 else 0
    if trade == "logger":
        return 9999                          # the woods belong to nobody
    if trade == "prisoner":
        return 0                      # a prisoner is not paid, ever
    if trade == "soldier":
        # ONE MAN TO A DUMMY, ONE TO A TARGET: the post is the trade.
        posts = sum(1 for wp in (getattr(player, "workplaces", ()) or ())
                    if getattr(wp, "kind", None) in TRAIN_KINDS)
        return max(0, posts - have)
    return max(0, _stations(player).get(STATION_OF[trade], 0) - have)


def pay(trade: str) -> int:
    """WHAT THE MAN IS PAID: the state's wage for the trade, plus 30%.

    The state's own numbers, from economy: 15 for the field, the woods and the
    pit, 50 for the forge. A BENCH HAND OR A BREWER IS PAID NOTHING BY THE
    STATE -- there is no wage for those trades in its books -- so the fallback
    is the labourer's 10, and 13 a day. If that is wrong, it is a number, not
    a structure: say the word.
    """
    if trade == "prisoner":
        return 0                      # a prisoner is not paid, ever
    if trade == "soldier":
        return int(round(pay("farm") * SOLDIER_PAY_MULT))
    base = {"farm": economy.LOGGER_WAGE,
            "logger": economy.LOGGER_WAGE,
            "mine": economy.LOGGER_WAGE,
            "smith": economy.SMITH_WAGE}.get(trade, economy.WAGE)
    return max(1, int(round(base * PAY_MARGIN)))


LIKE_FOR_HIRING = 10.0     # he is pleased to be taken on
LIKE_FOR_FIRING = -15.0    # ...and he remembers being put out
# A MISSED WAGE IS NOT A SACKING ANY MORE. It is a grudge: a man who is not
# paid thinks twenty points less of the player and STAYS, and only walks when
# what is left of his regard is under ten.
UNPAID_BITTER = 20.0
QUIT_BELOW = 10.0


def like(npc, amount: float) -> float:
    """NUDGE HOW HE FEELS ABOUT THE PLAYER, in the same 0..100 he is asked for.

    `player_opinion` is the base the truth-teller reads (50 by default, plus
    five for every deal they have done). This moves that base, not the deal
    count -- ten points of liking, not ten trades.
    """
    base = getattr(npc, "player_opinion", None)
    if base is None:
        base = 50.0
    npc.player_opinion = max(0.0, min(100.0, float(base) + float(amount)))
    return npc.player_opinion


def to_market(player, npc) -> bool:
    """IS HIS PRODUCT GOING TO THE STALL? The player's instruction, per man."""
    return bool(getattr(npc, "to_market", False))


def set_market(player, npc, on: bool) -> bool:
    """TELL HIM WHERE HIS OUTPUT GOES. Refused with no stall to put it on."""
    if on and market_stall(player) is None:
        return False
    npc.to_market = bool(on)
    try:
        import orders
        orders.order(player, npc, "market" if on else "chest")
    except Exception:
        pass
    return True


def market_stall(player):
    """THE STALL IN HIS HUB -- where a man's product goes if he is told to."""
    try:
        import stall
        return stall.in_hub(player, getattr(player, "hub", None)) or (
            stall.stalls_of(player)[0] if stall.stalls_of(player) else None)
    except Exception:
        return None


def is_employed(player, npc) -> bool:
    return bool(getattr(npc, "player_worker", False)
                and npc in (getattr(player, "workers", ()) or ()))


def fire(player, npc) -> bool:
    """PUT HIM OUT. He is idle again -- and he does not like it."""
    if not is_employed(player, npc):
        return False
    player.workers.remove(npc)
    npc.player_worker = False
    npc.wage = 0
    npc.job = None
    npc.work_post = None              # his own town's day again
    like(npc, LIKE_FOR_FIRING)
    try:
        import orders
        orders.order(player, npc, "fire")
    except Exception:
        pass
    try:
        import economy as _e
        _e._note("FIRED     %-16s by the player; he likes him %d now"
                 % (getattr(npc, "name", "?"),
                    int(getattr(npc, "player_opinion", 50.0))))
    except Exception:
        pass
    return True


def offers(player) -> list:
    """What he can offer, and how many places are open."""
    out = []
    for trade, label in TRADES:
        n = slots(player, trade)
        if n > 0:
            out.append((trade, label, n, pay(trade)))
    return out


SOLDIER_KIT_ORDER = ("shotgun", "rifle", "axe")


def soldier_kit(npc) -> str | None:
    """WHAT HE FIGHTS WITH, out of what he is actually carrying.

    Shotgun first, then rifle, then axe -- and a gun with no rounds is not a
    gun, so an empty rifle falls back to the axe in his hands.
    """
    inv = bag(npc)
    rounds = int(inv.count_of("ammo"))
    for gun in ("shotgun", "rifle"):
        if rounds > 0 and int(inv.count_of(gun)) > 0:
            return gun
    if int(inv.count_of("axe")) > 0:
        return "axe"
    return None


def arm(player, npc) -> str | None:
    """HAND HIM A WEAPON -- the player's axe, or a gun and its rounds.

    Returns what he was given, or None when the player has nothing to give:
    a soldier without a weapon is a man standing in a field.
    """
    inv = getattr(player, "pack", None)
    if inv is None:
        return None
    mine = bag(npc)
    for gun in ("shotgun", "rifle"):
        if int(inv.count_of(gun)) > 0 and int(inv.count_of("ammo")) > 0:
            inv.consume(gun, 1)
            mine.add(gun, 1)
            rounds = min(int(inv.count_of("ammo")), SOLDIER_AMMO_ISSUE)
            inv.consume("ammo", rounds)
            mine.add("ammo", rounds)
            return gun
    if int(inv.count_of("axe")) > 0:
        inv.consume("axe", 1)
        mine.add("axe", 1)
        return "axe"
    return None


def hire(player, npc, trade: str) -> dict:
    """PUT THE MAN TO IT. Returns the record, or None if the place is gone."""
    if not qualifies(npc, player) or slots(player, trade) <= 0:
        return None
    # A SOLDIER IS HIRED FOR HIS WAGE LIKE ANY OTHER MAN. Arming him is the
    # player's business, and he can do it any time he likes -- his own pack is
    # a container the player can open, so the axe or the gun goes in when the
    # player feels like it, not as a condition of the hire.
    wage = pay(trade)
    npc.job = trade
    npc.player_worker = True
    npc.wage = wage
    npc.work_post = getattr(player, "work_post", None)
    npc.on_duty = False               # he is not on the town's watch any more
    npc.duty = "labour"
    # A TRADER HIRED MID-RUN STOPS TRADING: his cart is not the player's work.
    npc.trade_state = "none"
    npc.trade_stops = 0
    npc.trade_stop = None
    npc.trade_dest = None
    npc.asleep = False
    npc.in_interior = False
    npc.settled_at = None
    npc.workplace = None
    npc.farm_plot = None
    if not isinstance(getattr(player, "workers", None), list):
        player.workers = []
    if npc not in player.workers:
        player.workers.append(npc)
    if trade == "prisoner":
        return 0                      # a prisoner is not paid, ever
    if trade == "soldier":
        npc.soldier = True
        npc.weapon = soldier_kit(npc) or "axe"   # whatever he came with
        npc.training = None
        npc.shot_timer = 0.0
        npc.strike_timer = 0.0
    like(npc, LIKE_FOR_HIRING)          # being taken on is worth something
    try:
        import orders
        orders.order(player, npc, "hire", item=trade)
    except Exception:
        pass
    try:
        import plog
        plog.log("PHASE-HIRED", getattr(npc, "name", "?"), "as", trade,
                 "wage", wage, "post", getattr(player, "work_post", None),
                 "at", "%d,%d" % (int(npc.x), int(npc.y)))
    except Exception:
        pass
    try:
        import economy as _e
        _e._note("HIRED     %-16s as %-8s at %d a day (the state pays %d)"
                 % (getattr(npc, "name", "?"), trade, wage,
                    int(round(wage / PAY_MARGIN))))
    except Exception:
        pass
    return {"npc": npc, "trade": trade, "wage": wage}


TURN_PX = 160.0             # an agent close enough to have a word with him


def turn_the_bitter(player, agents, radius: float = TURN_PX) -> list:
    """A WORKER WHO HATES YOU KEEPS WORKING -- AND IS TURNED.

    He is not sent away: he stays in the yard, on the payroll, doing the work
    he was hired for. But the first time one of the service's men comes close
    enough to speak to him, he becomes one of them -- and everything he sees
    from then on belongs to the chief.
    """
    turned = []
    held = getattr(player, "workers", None)
    if not held or not agents:
        return turned
    try:
        import nemesis
    except Exception:
        return turned
    live = [n for n in held if getattr(n, "alive", True)]
    r2 = radius * radius
    for n in live:
        if not hates(n, player) or nemesis.is_service(n):
            continue
        for a in agents:
            if a is n or not getattr(a, "alive", True):
                continue
            if ((a.x - n.x) ** 2 + (a.y - n.y) ** 2) > r2:
                continue
            if nemesis.turn(n):
                turned.append(n)
                try:
                    import orders
                    orders.leak(n)      # everything he knew about the yard
                except Exception:
                    pass
            break
    return turned


SEEDS = ("wheat_seed", "seed_bag")


def payroll(player, day: int, chest=None, stall=None) -> dict:
    """THE SALARY COMES OUT OF THE HOUSE CHEST IN THE HUB, once a day.

    Not out of his pack: the men are paid out of the chest the player keeps in
    his own hub, so he has to put the money there. A day he has not is a day
    they are not paid -- and a man who is not paid QUITS, and thinks less of
    him for it, exactly as if he had been put out.

    ...and if the chest cannot cover it, THE STALL'S PURSE is tried next: money
    taken at the counter is money he has.

    A MISSED DAY IS NOT A SACKING. It costs the man twenty points of regard and
    he stays; he walks only when his regard for the player is under ten
    (QUIT_BELOW). This is the rule the player asked for, and it is new.

    Returns {"paid": coin, "quit": [men], "unpaid": [men], "seeds": {...}}.
    """
    out = {"paid": 0, "quit": [], "unpaid": [], "seeds": {}}
    if getattr(player, "_payroll_day", -1) == day:
        return out
    player._payroll_day = day
    held = getattr(player, "workers", ()) or ()
    for n in list(held):
        if not getattr(n, "alive", True):
            player.workers.remove(n)
            continue
        wage = int(getattr(n, "wage", 0) or 0)
        if wage <= 0:
            continue
        purse = int(chest.count_of("coin")) if chest is not None else 0
        purse += int(getattr(stall, "coins", 0) or 0) if stall is not None else 0
        if purse < wage:
            # NOT PAID. HE STAYS, AND HE REMEMBERS -- and only a man whose
            # regard has fallen under ten walks out over it.
            like(n, -UNPAID_BITTER)
            regard = regard_of(n, player)
            _note_unpaid(n, purse, wage, regard)
            if regard < QUIT_BELOW:
                player.workers.remove(n)
                n.player_worker = False
                n.wage = 0
                n.job = None
                n.work_post = None
                n.to_market = False
                out["quit"].append(n)
                _note("WALKED    %s -- %d days of it, regard %d"
                      % (getattr(n, "name", "?"), 1, int(regard)))
            else:
                out["unpaid"].append(n)
            continue
        # THE CHEST FIRST, THE COUNTER SECOND.
        from_chest = min(wage, int(chest.count_of("coin")) if chest is not None else 0)
        if from_chest > 0:
            chest.consume("coin", from_chest)
        rest = wage - from_chest
        if rest > 0 and stall is not None:
            stall.spend(rest)
        n.coins = int(getattr(n, "coins", 0) or 0) + wage
        out["paid"] += wage
        if getattr(n, "job", None) == "farm":
            # A FARMER NEEDS SEED TO SOW, and it is the chest's business to
            # have some. Nothing is taken here -- the sowing will -- but the
            # player is told, once a day, that his field has no seed.
            out["seeds"][getattr(n, "name", "?")] = (
                chest is not None
                and any(int(chest.count_of(s)) > 0 for s in SEEDS))
    return out


# =====================================================================
# WHAT A MAN DOES AT HIS POST, AND WHAT THE PLAYER GETS OUT OF IT.
#
# A hired man is not a figure on a wage: he works the station he was hired
# for, out of material in his OWN hands -- and if his hands are empty he walks
# to the chest and takes what he needs from it. What he makes, he carries, and
# once a batch is done he puts it in the player's chest.
# =====================================================================

BATCH_SECONDS = 90.0       # one batch of work: a day is ten minutes
SMITH_PAIR = 2             # units of iron for one gun and its cartridges
SMITH_AMMO = 30            # cartridges that come with a gun
AMMO_ITEM = "ammo"

# trade -> (tools he must hold, material he spends, product he makes)
# The tool is not consumed: nothing a man can hold wears out doing its job.
# "use" is what a batch SPENDS and "out" is what it MAKES: a seed is a crop,
# five of mash are five drinks, and a pair of iron is one gun with its rounds.
RECIPES = {
    "logger":  {"need": ("axe",), "use": 0, "out": 4, "from": (), "make": "wood"},
    "mine":    {"need": ("pickaxe",), "use": 0, "out": 2, "from": (), "make": "iron"},
    "smith":   {"need": (), "use": SMITH_PAIR, "out": 1,
                "from": ("iron",), "make": None},   # a gun, and it alternates
    "lab":     {"need": (), "use": 1, "out": 1,
                "from": ("tobacco", "red_mushroom"),
                "make": None},            # the leaf decides the product
    "brewery": {"need": (), "use": 5, "out": 5,
                "from": ("wheat", "berries", "agave"),
                "make": None},            # the mash decides the drink
}

# The material families, read from economy so there is one table of them.
def _leaf_map() -> dict:
    try:
        return dict(economy.PROCESS)
    except Exception:
        return {"tobacco": "cigar", "red_mushroom": "dried_mushroom"}


def _mash_map() -> dict:
    """MASH -> DRINK, and it takes two of the economy's tables to say it.

    economy.BREW is keyed by WORT (wheat_wort -> beer), not by what a man puts
    in the table (wheat -> wort -> beer), so reading it directly made every
    mash brew "beer" -- berries and agave included -- and a brewer told to stop
    making beer had nothing to fall back on.
    """
    try:
        return {mash: economy.BREW[wort]
                for mash, wort in economy.WORT.items()
                if wort in economy.BREW}
    except Exception:
        return {"wheat": "beer", "berries": "liqueur", "agave": "mezcal"}


def uses(trade) -> tuple:
    """What the trade spends, as a list of item ids -- for the give page."""
    if trade == "prisoner":
        return 0                      # a prisoner is not paid, ever
    if trade == "soldier":
        return ("ammo",)                # ten rounds a day on the range
    r = RECIPES.get(trade)
    if not r:
        return ()
    return tuple(r["from"])


def products(trade) -> tuple:
    """What the trade makes -- for the take page and for the chest."""
    if trade == "prisoner":
        return 0                      # a prisoner is not paid, ever
    if trade == "soldier":
        return ()                       # he makes a killer, not a product
    if trade == "farm":
        return FARM_CROPS
    if trade == "smith":
        return ("rifle", "shotgun", AMMO_ITEM)
    if trade == "lab":
        return tuple(_leaf_map().values())
    if trade == "brewery":
        return tuple(_mash_map().values())
    r = RECIPES.get(trade)
    return (r["make"],) if r and r["make"] else ()


def relevant(trade) -> tuple:
    """EVERYTHING THIS TRADE TOUCHES: what it spends and what it makes."""
    seen, out = set(), []
    for item in uses(trade) + products(trade) + tuple(
            t for t in (RECIPES.get(trade, {}).get("need") or ())):
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def can_hold(inv, item: str, count: int) -> int:
    """HOW MANY OF THESE THE CONTAINER WOULD TAKE, and not one more.

    Inventory.add returns the index of the stack it used, not what it left
    over, so fullness cannot be read off it -- and a chest that is full must
    say so instead of quietly swallowing a man's work.
    """
    if inv is None or count <= 0:
        return 0
    try:
        import items
        defn = items.get(item)
        room = 0
        for s in inv.slots:
            if s is not None and s.defn.id == item:
                room += max(0, defn.max_stack - s.count)
        room += sum(1 for s in inv.slots if s is None) * defn.max_stack
        return int(min(count, room))
    except Exception:
        return int(count)


PLAYER_SLOTS = 32          # his hands hold exactly what the player's do


def bag(npc):
    """THE MAN'S HANDS: an inventory, 32 slots, the same as the player's.

    Work used to live in the town economy's `stock` dict, which has no size --
    a man could hold a thousand cigars in it. A hired man carries a real pack
    now, so the chest screen opens on him and takes things out and puts things
    in by the same rules as a chest.
    """
    inv = getattr(npc, "pack", None)
    if inv is None:
        import inventory as _inv
        inv = npc.pack = _inv.Inventory(PLAYER_SLOTS)
        # WHAT HE ALREADY HAD COMES WITH HIM -- once, when his pack appears.
        old = getattr(npc, "stock", None)
        if isinstance(old, dict):
            for k, v in list(old.items()):
                try:
                    if int(v) > 0:
                        inv.add(k, int(v))
                except Exception:
                    pass
            npc.stock = {}
    return inv


def _held(npc, item: str) -> int:
    return int(bag(npc).count_of(item))


def _spend(npc, chest, item: str, count: int) -> bool:
    """OUT OF HIS OWN HANDS FIRST, THEN OUT OF THE CHEST."""
    inv = bag(npc)
    have = int(inv.count_of(item))
    here = min(have, count)
    left = count - here
    if left > 0 and (chest is None or int(chest.count_of(item)) < left):
        return False                        # no half-draws: all or nothing
    if here > 0:
        inv.consume(item, here)
    if left > 0:
        chest.consume(item, left)
    return True


def _can_supply(npc, chest, item: str, count: int) -> bool:
    room = int(bag(npc).count_of(item))
    if chest is not None:
        room += int(chest.count_of(item))
    return room >= count


def _spend_any(npc, chest, kinds, count):
    """The first of a family he can put up whole -- and what he spent."""
    for k in kinds:
        if _can_supply(npc, chest, k, count) and _spend(npc, chest, k, count):
            return k
    return None


SECOND_GUN = {"rifle": "shotgun", "shotgun": "rifle"}
NEUTRAL_GRADE = 3          # C -- the economy's own default for unknown goods


def _grade_in(container, item: str) -> int:
    """THE GRADE OF THE MATERIAL HE IS ABOUT TO USE: the first stack of it.

    Inventory.consume takes from the front, and so does this, so the grade read
    here is the grade spent. A container with no graded stocks (a chest of
    them all the same) answers with the neutral C.
    """
    try:
        for s in getattr(container, "slots", ()) or ():
            if s is not None and s.defn.id == item:
                return int(s.quality if s.quality is not None else NEUTRAL_GRADE)
    except Exception:
        pass
    return NEUTRAL_GRADE


def _made_grade(npc, given: int) -> int:
    """THE HANDS AND THE LEAF, THE SAME RULE THE TOWN'S OWN BENCH USES.

    industry.produce gives a made thing the average of the maker's hands and the
    grade of what he worked. A player's bench is not a different world, so it
    applies the same rule -- otherwise everything a hired man makes is born
    grade F, worth a third, and any pricing that looked at quality would price
    the player's own produce as floor sweepings.
    """
    try:
        import quality as _q
        hands = int(npc.skills.leaf_grade(8))
    except Exception:
        hands = NEUTRAL_GRADE
    try:
        import quality as _q
        return int(_q.clamp(int(round((hands + given) / 2.0))))
    except Exception:
        return NEUTRAL_GRADE


def hands_grade(npc) -> int:
    """The grade his own hands would give a batch, before the leaf is counted."""
    try:
        import quality as _q
        return int(_q.clamp(int(npc.skills.leaf_grade(8))))
    except Exception:
        return 3


def price_grade(npc) -> int:
    """THE GRADE TO PRICE HIS WORK AT: what he last made, or his hands."""
    got = getattr(npc, "last_grade", None)
    return int(got) if got is not None else hands_grade(npc)


def quality_answer(npc) -> str:
    """WHAT QUALITY HE MAKES -- HIS OWN WORD FOR IT, TRUTHFULLY.

    A man with hands and no grade in the item (iron, a log, a gun) says so,
    because a lie here costs the player money: the price he is about to agree
    is the price OF A GRADE.
    """
    trade = getattr(npc, "job", None)
    import quality as _q
    goods = [i for i in products(trade)]
    try:
        import items as _items
        graded = [i for i in goods if getattr(_items.get(i), "quality", False)]
    except Exception:
        graded = []
    if not graded:
        return ("Nothing to grade. Iron is iron, a log is a log, and a gun "
                "either fires or it does not.")
    last = getattr(npc, "last_grade", None)
    hands = hands_grade(npc)
    if last is None:
        return ("I have not run a batch yet, but my hands are good for %s."
                % _q.letter(hands))
    if int(last) >= hands:
        return "My last batch was %s, and that is about my best." % _q.letter(int(last))
    return ("My last batch came out %s -- the leaf was poor. My hands are "
            "worth %s." % (_q.letter(int(last)), _q.letter(hands)))


def sellable(npc) -> list:
    """WHAT HE COULD MAKE, one by one -- so the player can stop him making it.

    Cartridges are not on it: they come with a gun, and a forge told to stop
    making cartridges could still make the gun that needs them. A rifle and a
    shotgun ARE on it, which is the whole point of the smith's pair.
    """
    trade = getattr(npc, "job", None)
    return [i for i in products(trade) if i != AMMO_ITEM]


def banned(npc) -> set:
    got = getattr(npc, "no_make", None)
    if not isinstance(got, (set, frozenset, list, tuple)):
        got = npc.no_make = set()
    elif not isinstance(got, set):
        got = npc.no_make = set(got)
    return got


def is_banned(npc, item) -> bool:
    """Stopped from MAKING it."""
    return item in banned(npc)


def not_sold(npc) -> set:
    """Stopped from SELLING it -- he still makes it, it just goes to the chest.

    These are two instructions, not one. "Don't make any more cigars" is a
    bench standing idle; "don't sell the cigars" is a bench that keeps working
    and a shelf that stays empty. A player may want either, and may want the
    first for one thing and the second for another.
    """
    got = getattr(npc, "no_sell", None)
    if not isinstance(got, (set, frozenset, list, tuple)):
        got = npc.no_sell = set()
    elif not isinstance(got, set):
        got = npc.no_sell = set(got)
    return got


def is_not_sold(npc, item) -> bool:
    return item in not_sold(npc)


def set_not_sold(npc, item, stop: bool, player=None) -> bool:
    """Stop him OFFERING it (he goes on making it). Returns whether stopped."""
    if item not in sellable(npc):
        return False
    if stop:
        not_sold(npc).add(item)
    else:
        not_sold(npc).discard(item)
    try:
        import orders
        orders.order(player, npc, "stop_selling" if stop else "sell_again",
                     item=item)
    except Exception:
        pass
    return stop


def set_banned(npc, item, stop: bool, player=None) -> bool:
    """PUT ONE PRODUCT OFF, OR BACK ON. Returns whether it is now stopped."""
    if item not in sellable(npc):
        return False
    if stop:
        banned(npc).add(item)
    else:
        banned(npc).discard(item)
    try:
        import orders
        orders.order(player, npc, "stop_making" if stop else "make_again",
                     item=item)
    except Exception:
        pass
    return stop


def _allowed(npc) -> list:
    """The products he may still make -- empty means the player has stopped
    him making anything at all, which is a decision he is allowed to make."""
    return [i for i in sellable(npc) if not is_banned(npc, i)]


def can_work(npc, chest) -> bool:
    """Whether he could do a batch RIGHT NOW (his tools, and his material)."""
    r = RECIPES.get(getattr(npc, "job", None))
    if not r:
        return False
    if not _allowed(npc):
        return False                       # "stop selling it" means stop
    for tool in r["need"]:
        if _held(npc, tool) <= 0 and not (
                chest is not None and int(chest.count_of(tool)) > 0):
            return False
    if r["use"] <= 0:
        return True
    if getattr(npc, "job", None) in ("lab", "brewery"):
        # THE PRODUCT DECIDES WHICH MATERIAL IS USEFUL. Tobacco is no use to
        # a bench told to stop making cigars, and saying "he can work" while
        # `craft` quietly refuses is how a man stood in a yard for a minute
        # doing nothing and said nothing about it.
        table = _leaf_map() if npc.job == "lab" else _mash_map()
        ok = _allowed(npc)
        return any(table.get(k) in ok and _can_supply(npc, chest, k, r["use"])
                   for k in r["from"])
    return any(_can_supply(npc, chest, k, r["use"]) for k in r["from"])


def stopped_by_order(npc, chest):
    """WHEN THE PLAYER'S OWN INSTRUCTION IS WHAT STOPS HIM, say which one.

    Returns the products to name, or None if the stop is not the reason. This
    is the difference between "I have nothing to work with" and "you told me to
    leave the cigars alone, and there is no other leaf here".
    """
    if not _allowed(npc):
        return list(banned(npc))
    r = RECIPES.get(getattr(npc, "job", None))
    if not r or r["use"] <= 0 or not banned(npc):
        return None
    trade = getattr(npc, "job", None)
    if trade not in ("lab", "brewery"):
        return None
    table = _leaf_map() if trade == "lab" else _mash_map()
    ok = _allowed(npc)
    usable = any(table.get(k) in ok and _can_supply(npc, chest, k, r["use"])
                 for k in r["from"])
    if usable:
        return None
    # he has the material, but only for products the player has stopped
    if any(_can_supply(npc, chest, k, r["use"]) for k in r["from"]):
        return list(banned(npc))
    return None


def craft(npc, chest) -> dict | None:
    """ONE BATCH. Returns {"spent": item, "made": {item: n}} or None."""
    trade = getattr(npc, "job", None)
    r = RECIPES.get(trade)
    if not r or not can_work(npc, chest):
        return None
    _grade = NEUTRAL_GRADE                  # what he is working is not graded
    for tool in r["need"]:                  # held, never spent
        if _held(npc, tool) <= 0:
            _spend(npc, chest, tool, 1)
    if trade == "smith":
        # A FORGE TOLD TO LEAVE OFF ONE GUN MAKES THE OTHER: the pair still
        # costs a pair, and the alternation carries on untouched.
        ok = _allowed(npc)
        if not ok:
            return None
        if not _spend(npc, chest, "iron", SMITH_PAIR):
            return None
        n = int(getattr(npc, "made_guns", 0) or 0)
        want = "rifle" if n % 2 == 0 else "shotgun"
        gun = want if want in ok else (ok[0] if len(ok) == 1 else want)
        if gun not in ok:
            # the wanted one is stopped and the other is not
            gun = SECOND_GUN.get(want, want)
            if gun not in ok:
                return None
        npc.made_guns = n + 1
        bag(npc).add(gun, 1)
        bag(npc).add(AMMO_ITEM, SMITH_AMMO)
        return {"spent": "iron", "made": {gun: 1, AMMO_ITEM: SMITH_AMMO}}
    spent = None
    if trade in ("lab", "brewery"):
        # THE LEAF OR THE MASH DECIDES THE DRINK -- so a stopped product means
        # the OTHER leaf, if he has one, rather than standing idle with a
        # bench full of tobacco.
        table = _leaf_map() if trade == "lab" else _mash_map()
        ok = _allowed(npc)
        order = [k for k in r["from"]
                 if table.get(k) in ok and _can_supply(npc, chest, k, r["use"])]
        if not order:
            return None
        # THE GRADE OF THE LOT HE IS ABOUT TO SPEND, read before it is spent.
        _src = bag(npc) if int(bag(npc).count_of(order[0])) >= r["use"] else chest
        _given = _grade_in(_src if _src is not None else bag(npc), order[0])
        spent = _spend_any(npc, chest, order, r["use"])
        if spent is None:
            return None
        item = table.get(spent)
        _grade = _made_grade(npc, _given)
    else:
        item = r["make"]
        if item and is_banned(npc, item):
            return None
    if not item:
        return None
    n = int(r.get("out", 1) or 1)
    bag(npc).add(item, n, _grade)
    # WHAT HE LAST MADE IS THE HONEST ANSWER TO "what quality do you make?".
    npc.last_grade = int(_grade)
    npc.last_item = item
    return {"spent": spent, "made": {item: n}}


def _deposit_stacks(npc, dst, only, into_stall: bool, player=None) -> dict:
    """MOVE HIS PRODUCTS TO `dst`, STACK BY STACK, GRADES INTACT.

    Adding a count without its grade is how a batch of A-grade leaf became
    F-grade cigars the moment it left his hands: the counter and the chest
    both hold an Inventory, and an Inventory told nothing about quality
    writes grade zero.
    """
    out = {"moved": {}, "left": {}}
    if dst is None:
        return out
    inv = bag(npc)
    allowed = set(only) if only is not None else set(
        products(getattr(npc, "job", None)))
    for i, s in enumerate(list(inv.slots)):
        if s is None or s.defn.id not in allowed or int(s.count) <= 0:
            continue
        item, q, have = s.defn.id, s.quality, int(s.count)
        if into_stall:
            room = int(dst.put(item, have, q))
        else:
            room = min(have, int(can_hold(dst, item, have)))
            if room > 0:
                dst.add(item, room, q)
        if room > 0:
            s.count = have - room
            if s.count <= 0:
                inv.slots[i] = None
            out["moved"][item] = out["moved"].get(item, 0) + room
            try:
                import orders
                orders.handoff(player, npc, item, room,
                               "stall" if into_stall else "chest")
            except Exception:
                pass
    for s in inv.slots:
        if s is not None and s.defn.id in allowed and int(s.count) > 0:
            out["left"][s.defn.id] = out["left"].get(s.defn.id, 0) + int(s.count)
    return out


def deposit(npc, chest, only=None, player=None) -> dict:
    """WHAT HE MADE GOES IN THE PLAYER'S CHEST. What will not fit stays with
    him, and he will tell the player so. `only` limits it to some products, so
    a stopped one can go to the chest while the rest goes on the stall."""
    return _deposit_stacks(npc, chest, only, False, player)


def deposit_into(npc, stall, only=None, player=None) -> dict:
    """A WORKER'S PRODUCT, ON THE STALL. Same rule as the chest: what will not
    fit stays in his hands and he says so."""
    return _deposit_stacks(npc, stall, only, True, player)


# ---- THE FARMER'S REAL WORK -------------------------------------------
# A hired farmer does not turn a seed into four wheat in his pack. He works the
# player's land: he digs it, waters it, sows the seeds HE IS CARRYING and reaps
# what ripens. What he sows is the player's decision -- the player puts seeds in
# his pack -- and HOW he sows it is the rule: ONE OF EACH KIND IN TURN, until a
# kind runs out, then the rest of the other. Thirty tobacco seeds and ten wheat
# are five rounds of tobacco+wheat, then twenty tobacco.
FARM_STEP_SECONDS = 1.1     # one spadeful, one sowing, one reaping
FARM_TOOL = "shovel"

FARM_CROPS = ("bread", "wheat", "tobacco", "red_mushroom", "agave",
              "berries", "cactus_fruit")


def _quiet(*_a, **_k) -> None:
    """The farm helpers insist on a toast; a hired man does not shout."""


def _plot_tiles(plots) -> list:
    """Every tile inside the player's own plots, in a stable order."""
    try:
        from world import TILE as _T
    except Exception:
        _T = 32
    tiles = []
    for rec in plots or ():
        try:
            px, py, pw, ph = rec[0], rec[1], rec[2], rec[3]
        except Exception:
            continue
        tx0, ty0 = int(px // _T), int(py // _T)
        tx1, ty1 = int((px + max(1, pw) - 1) // _T), int((py + max(1, ph) - 1) // _T)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                tiles.append((tx, ty))
    return tiles


def _seed_kinds(npc) -> list:
    """The kinds of seed in his hands, in a fixed order. His sowing rotation."""
    try:
        import crop as _crop
        table = _crop.SEED_CROP
    except Exception:
        return []
    return sorted(k for k in table if _held(npc, k) > 0)


def _next_seed(npc) -> str | None:
    """ONE OF EACH KIND IN TURN -- his `sow_turn` is where the rotation is."""
    kinds = _seed_kinds(npc)
    if not kinds:
        return None
    turn = int(getattr(npc, "sow_turn", 0) or 0) % len(kinds)
    for i in range(len(kinds)):
        k = kinds[(turn + i) % len(kinds)]
        if _held(npc, k) > 0:
            npc.sow_turn = (turn + i + 1) % len(kinds)
            return k
    return None


def _farm_step(npc, world, ground, plots, now: float) -> str:
    """ONE TURN OF THE DAY: reap if anything is ripe, else one soil action.

    Order matters: a ripe field is food on the ground, and sowing over it would
    be the one thing a farmer would never do.
    """
    import farm as _farm
    try:
        import crop as _crop
    except Exception:
        return "idle"
    tiles = _plot_tiles(plots)
    # 1. REAP
    for tx, ty in tiles:
        plot = world.plot_at(tx, ty)
        if plot is None or plot.kind not in (_crop.LEAF_KINDS + _crop.FOOD_KINDS):
            continue
        _elapsed = now - (plot.planted_at if plot.planted_at is not None else now)
        if _elapsed < (getattr(plot, "grow", None) or _crop.GROW_SECONDS):
            continue
        if _farm.harvest(world, bag(npc), plot, now, _quiet, tx=tx, ty=ty,
                         skill=float(getattr(npc.skills, "farming", 0.0))):
            return "harvested"
    # 2. DIG, WATER, SOW -- one action
    seed = _next_seed(npc)
    for tx, ty in tiles:
        plot = world.plot_at(tx, ty)
        kind = getattr(plot, "kind", None)
        if kind in (_crop.LEAF_KINDS + _crop.FOOD_KINDS):
            continue                       # something is already growing
        if seed is None:
            return "no seeds"
        if kind in (None, "grass"):
            if _farm.dig(world, ground, tx, ty, _quiet):
                return "dug"
            continue
        if kind == "dirt":
            if _farm.water(world, ground, tx, ty, _quiet):
                return "watered"
            continue
        if kind == "fertile":
            if _farm.plant(world, ground, bag(npc), tx, ty, now, _quiet,
                           seed=seed,
                           skill=float(getattr(npc.skills, "farming", 0.0))):
                return "sowed " + seed
            continue
    return "no ground"


def farm_produce(npc, player, chest, dt, world, ground, plots, now) -> list:
    """THE FARMER'S DAY. Returns what happened, for the log."""
    out = []
    if world is None:
        return out
    if _held(npc, FARM_TOOL) <= 0 and not _spend(npc, chest, FARM_TOOL, 1):
        npc.say = "I have no shovel."
        return out
    npc.work_timer = float(getattr(npc, "work_timer", 0.0) or 0.0) + float(dt)
    if npc.work_timer < FARM_STEP_SECONDS:
        return out
    npc.work_timer = 0.0
    what = _farm_step(npc, world, ground, plots, now)
    if what in ("dug", "watered") or what.startswith("sowed"):
        npc.say = None
        out.append(("farm", npc, what))
    elif what == "harvested":
        # the crop goes to the player, where his other product goes
        target = market_stall(player) if to_market(player, npc) else chest
        d = _deposit_stacks(npc, target, only=FARM_CROPS,
                            into_stall=target is not None and target is not chest,
                            player=player)
        if d["moved"]:
            out.append(("made", npc, d["moved"]))
        if d["left"]:
            out.append(("full", npc, d["left"]))
    elif what == "no seeds":
        npc.say = "I have no seed to sow."
    elif what == "no ground":
        npc.say = "There is no land staked for me to work."
    return out


AT_POST_PX = 90.0          # close enough to the post to be working at it
AT_POST_TRAIN_PX = 70.0    # ...and close enough to train at the post


def training_post(player, npc):
    """THE POST THAT MATCHES WHAT HE IS CARRYING.

    An axe man belongs at the dummy and a gun man at the target -- and the
    moment the player hands him the other weapon, he moves post himself. A
    post he has left is released so another man can be put to it.
    """
    kit = soldier_kit(npc)
    want = "target" if kit in ("rifle", "shotgun") else "dummy"
    posts = list(getattr(player, "workplaces", ()) or ())
    # let go of the post he is standing at if it is the wrong trade now
    held = getattr(npc, "training", None)
    if held is not None and getattr(held, "kind", None) != want:
        if getattr(held, "worker", None) is npc:
            held.worker = None
        npc.training = None
    for wp in posts:
        if getattr(wp, "kind", None) == want and getattr(wp, "worker", None) in (None, npc):
            wp.worker = npc
            return wp
    return None


def train(npc, player, chest, dt) -> list:
    """A SOLDIER'S DAY: blows at the post, or rounds into the straw.

    Melee: from nothing to master of the axe in three days of swinging.
    Ranged: master of the gun in five days, at one shot a minute -- ten
    rounds a day, which the range takes out of his pouch and then the chest.
    """
    out = []
    sk = getattr(npc, "skills", None)
    if sk is None:
        return out
    # HE FIGHTS WITH WHAT HE HAS. A gun with rounds beats a rifle, a rifle
    # beats an axe, and an empty gun is a club -- so the axe comes out.
    _kit_now = soldier_kit(npc)
    if _kit_now is not None:
        npc.weapon = _kit_now
    if _kit_now is None:
        # AN UNARMED SOLDIER CANNOT TRAIN -- and the player can arm him at any
        # time by putting an axe or a gun and rounds in his pack.
        npc.say = "I have no weapon to train with."
        return out
    post = training_post(player, npc)
    npc.training = post
    if post is None:
        npc.say = ("There is no %s for me to work at."
                   % ("target" if _kit_now in ("rifle", "shotgun") else "dummy"))
        return out
    npc.work_post = (post.x, post.y + 18.0)
    reach = AT_POST_TRAIN_PX * AT_POST_TRAIN_PX
    _d2 = (npc.x - post.x) ** 2 + (npc.y - post.y) ** 2
    if _d2 > reach:
        # STILL WALKING TO IT. Say so once every five seconds, so a man who
        # never arrives is visible in the log rather than invisible in a field.
        _t = float(getattr(npc, "train_said", 0.0) or 0.0)
        import time as _time
        if _time.time() - _t > 5.0:
            npc.train_said = _time.time()
            try:
                import plog
                plog.log("TRAIN-WAIT", getattr(npc, "name", "?"),
                         "%.0f px from the" % (_d2 ** 0.5),
                         getattr(post, "kind", "?"),
                         "at", "%d,%d" % (int(post.x), int(post.y)),
                         "| he is at", "%d,%d" % (int(npc.x), int(npc.y)))
            except Exception:
                pass
        return out
    post.train_flash = max(0.0, float(getattr(post, "train_flash", 0.0)) - dt)
    post.shot_flash = max(0.0, float(getattr(post, "shot_flash", 0.0)) - dt)
    if getattr(post, "kind", None) == "dummy":
        npc.weapon = "axe"
        rate = float(dt) / (TRAIN_MELEE_DAYS * DAY)
        before = float(getattr(sk, "axe", 0.0))
        sk.axe = min(1.0, before + rate)
        npc.strike_timer = float(getattr(npc, "strike_timer", 0.0)) + float(dt)
        if npc.strike_timer >= DUMMY_STRIKE_SECONDS:
            npc.strike_timer = 0.0
            post.train_flash = 0.18
            npc.swing_anim = 0.25        # the frame draws him mid-blow
        try:
            import stats as _stats
            _stats.apply_body(npc)       # the arm and the body together
        except Exception:
            pass
        if int(sk.axe / 0.125) > int(before / 0.125):
            _note("TRAINED   %-16s axe %d/8 at the dummy"
                  % (getattr(npc, "name", "?"), int(sk.axe / 0.125)))
            out.append(("trained", npc, "axe"))
        return out
    # ...the range
    kit = soldier_kit(npc)
    if kit not in ("rifle", "shotgun"):
        npc.say = "I have nothing to shoot with."
        return out
    npc.weapon = kit
    npc.shot_timer = float(getattr(npc, "shot_timer", 0.0)) + float(dt)
    if npc.shot_timer < SHOT_SECONDS:
        return out
    npc.shot_timer -= SHOT_SECONDS
    if _held(npc, "ammo") <= 0 and int(getattr(chest, "count_of", lambda i: 0)("ammo")) <= 0:
        npc.say = "I am out of rounds for the range."
        return out
    _spend(npc, chest, "ammo", 1)          # one round, once
    post.shot_flash = 0.25
    npc.shoot_flash = 0.12
    before = float(getattr(sk, "shooting", 0.0))
    sk.shooting = min(1.0, before + 1.0 / (TRAIN_RANGED_DAYS * TARGET_AMMO_PER_DAY))
    try:
        import stats as _stats
        _stats.apply_body(npc)
    except Exception:
        pass
    if int(sk.shooting / 0.125) > int(before / 0.125):
        _note("TRAINED   %-16s shot %d/8 at the target"
              % (getattr(npc, "name", "?"), int(sk.shooting / 0.125)))
        out.append(("trained", npc, "shooting"))
    return out


def produce(player, chest, dt, world=None, ground=None, plots=(), now=0.0) -> list:
    """THE MEN WORK THE POST THEY WALKED TO, a batch at a time.

    Called from the frame: the lane owns the men's feet, the frame owns the
    yard and its chest, so the work is done where the chest is. A man away
    from his post -- still on the road, or driven off it -- does not work.
    """
    out = []
    post = getattr(player, "work_post", None)
    r2 = AT_POST_PX * AT_POST_PX
    for n in list(getattr(player, "workers", ()) or ()):
        if not getattr(n, "alive", True):
            continue
        # A FARMER'S WORK IS THE FIELD, not the post: he digs, sows and reaps
        # the tiles the player has staked, wherever they are.
        if getattr(n, "job", None) == "farm":
            out.extend(farm_produce(n, player, chest, dt, world, ground,
                                    plots, now))
            continue
        if getattr(n, "job", None) == "soldier":
            # A SOLDIER'S WORK IS THE POST, NOT A BATCH.
            out.extend(train(n, player, chest, dt))
            continue
        if post is None:
            continue
        if ((n.x - post[0]) ** 2 + (n.y - post[1]) ** 2) > r2:
            continue
        if not can_work(n, chest):
            n.work_timer = 0.0
            # HE KEEPS THE LAST THING HE SAID IF IT WAS ABOUT A FULL CHEST:
            # he may be out of iron and still be holding a rifle he cannot
            # put anywhere, and the rifle is the more important news.
            _waiting = any(_held(n, i) > 0
                           for i in products(getattr(n, "job", None)))
            _stopped = stopped_by_order(n, chest)
            if _stopped:
                # THE PLAYER SAID STOP. That is not a shortage and must not
                # read like one.
                if not getattr(n, "said_none", False):
                    n.said_none = True
                    n.say = ("You told me to leave the %s alone, and there is "
                             "nothing else here for me to work."
                             % ", ".join(i.replace("_", " ") for i in _stopped))
                    out.append(("stopped", n, list(_stopped)))
            elif not getattr(n, "said_none", False) and not _waiting:
                n.said_none = True          # say it once, not every frame
                n.say = "I have nothing to work with."
                out.append(("idle", n, None))
            continue
        n.said_none = False
        n.work_timer = float(getattr(n, "work_timer", 0.0) or 0.0) + float(dt)
        if n.work_timer < BATCH_SECONDS:
            continue
        n.work_timer = 0.0
        got = craft(n, chest)
        if got:
            out.append(("made", n, got.get("made")))
        target = None
        if to_market(player, n):
            target = market_stall(player)
        if target is not None:
            _items = products(getattr(n, "job", None))
            _stopped = [i for i in _items if is_not_sold(n, i)]
            _for_sale = [i for i in _items if i not in _stopped]
            d = deposit_into(n, target, only=_for_sale or None, player=player)
            if _stopped and chest is None:
                # NO CHEST TO PUT IT IN, AND TOLD NOT TO SELL IT: he keeps it,
                # and the player is told why the counter is empty.
                n.say = ("You told me not to sell the %s, and there is no "
                         "chest here for it."
                         % ", ".join(i.replace("_", " ") for i in _stopped))
                out.append(("nochess", n, _stopped))
            if _stopped and chest is not None:
                # TOLD NOT TO SELL IT, HE STILL MAKES IT -- and it goes to the
                # chest, where the player can take it or leave it.
                _d2 = deposit(n, chest, only=_stopped, player=player)
                for _k, _v in _d2["moved"].items():
                    d["moved"][_k] = d["moved"].get(_k, 0) + _v
                for _k, _v in _d2["left"].items():
                    d["left"][_k] = d["left"].get(_k, 0) + _v
        elif chest is None:
            n.say = "I have nowhere to put what I make -- there is no chest in your hub."
            out.append(("nochess", n, got.get("made") if got else None))
            continue
        else:
            d = deposit(n, chest)
        if d["left"]:
            _where = "the stall" if target is not None else "your chest"
            n.say = ("I've made %s and there is no room on %s for it."
                     % (", ".join("%d %s" % (q, i.replace("_", " "))
                                  for i, q in d["left"].items()), _where))
            out.append(("full", n, d["left"]))
        elif d["moved"]:
            if target is not None and any(is_not_sold(n, i) for i in d["moved"]):
                n.say = ("The batch is in your chest -- you said not to sell "
                         "the %s." % ", ".join(
                             sorted(i.replace("_", " ") for i in d["moved"]
                                    if is_not_sold(n, i))))
            elif target is not None:
                n.say = "The batch is on your stall."
            else:
                n.say = "The batch is in your chest."
    return out


def _note(text: str) -> None:
    try:
        import economy as _e
        _e._note(text)
    except Exception:
        pass


def _note_unpaid(npc, purse: int, wage: int, regard: float) -> None:
    """One line in the economy's own log: a man who was not paid."""
    try:
        import economy as _e
        _e._note("UNPAID    %-16s chest+stall had %d, wage %d; he likes the "
                 "player %d now" % (getattr(npc, "name", "?"), purse, wage,
                                    int(regard)))
    except Exception:
        pass
