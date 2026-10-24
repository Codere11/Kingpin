"""Village economy: a free market of villagers who each own what they make,
a village ledger that is both the government and the bank, and -- the thing
that makes it more than subsistence -- a taste for variety.

Rules
-----
* A worker keeps what he produces, minus a 20% harvest tax paid in goods.
* Villagers hold personal prices: they sell at the lowest they'll accept, buy at
  the highest they'll pay, and a trade happens where those cross. Crossing
  happens when two villagers meet, and at the evening market.
* Villagers want a *taste of every kind* of food, not just calories. A village
  that only grows bread therefore bids high for berries -- which is what makes
  carrying goods between villages worth anybody's while.
* The ledger pays the watch, and lends coin to entrepreneurs at interest. Its
  interest income is what funds the watch.
"""

from __future__ import annotations

import math
import os
import random

import quality
import wildcrop
import face


_NOTE_PATH = None


def _note(text: str) -> None:
    """Append one line to ~/.kingpin_saves/village.log. Diagnostics only --
    it never changes behaviour, and it is how we find out what really happens
    in a running game rather than in a test harness.

    THE PATH IS WORKED OUT ONCE. This used to run os.makedirs(...) on EVERY
    call -- a mkdir syscall, then an open and a close, for every single line
    written to an eleven-megabyte file. A village election ends with one of
    these, and so does every harvest, death and trade note in the world; the
    syscall was pure overhead on a path that only ever appends.
    """
    global _NOTE_PATH
    try:
        path = _NOTE_PATH
        if path is None:
            path = os.path.join(os.path.expanduser("~"), ".kingpin_saves",
                                "village.log")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _NOTE_PATH = path
        with open(path, "a") as fh:
            fh.write(text + "\n")
    except Exception:
        pass

FOOD = ("bread", "berries", "cactus_fruit")
LEAF = ("tobacco", "red_mushroom", "agave")
# The artisan's trade: what a laboratory turns leaf INTO. Nobody craves the raw
# leaf any more -- the craving is for the finished article.
PROCESS = {"tobacco": "cigar", "red_mushroom": "dried_mushroom"}
FINISHED = tuple(PROCESS.values())
LEAF_STOCK = 24            # leaf an artisan keeps on the bench to work with
CRAFT_CONSUME = 1          # leaf per finished good

# The brewery: mash first, then ferment. Two steps, two waits, two grades.
MASH = ("wheat", "berries", "agave")             # what goes into the brewing table
WORT = {"wheat": "wheat_wort", "berries": "berry_wort", "agave": "agave_wort"}
BREW = {"wheat_wort": "beer", "berry_wort": "liqueur", "agave_wort": "mezcal"}
LUXURY = FINISHED + tuple(BREW.values())         # everything made, not grown
WORT_BATCH = 50            # fifty at a time through the table, and the barrel
WORT_STOCK = 40            # mash a brewer keeps on hand
BREW_SECONDS = 300.0       # five minutes in the barrel
SEEDS = ("wheat_seed", "seed_bag")
TOOLS = ("shovel", "pickaxe", "axe")
# ARMS ARE GOODS. A rifle is 1,050 coin: a HUNDRED AND FIVE DAYS of a
# labourer's wage at WAGE = 10, or thirty-five days of a rifleman's PAY_RIFLE
# -- a third of a game year for the man who makes the bread. They therefore
# move in small numbers, but they move: the crown buys them off its own people
# (see _buy_off_people) and a caravan carries them from where they are cheap to
# where they are dear. See wants() and surplus() for the two guards that keep
# this from arming the whole countryside by accident.
ARMS = ("rifle", "shotgun", "ammo")
GOODS = (FOOD + LEAF + FINISHED + SEEDS + TOOLS + ARMS
         + ("iron", "wood", "wheat") + tuple(WORT.values())
         + tuple(BREW.values()))
WAGE_GOODS = FOOD + LEAF + SEEDS

ITEM_VALUE = {
    # Base prices, by how hard a thing is to produce: tools > iron > food.
    # Each village skews these by what it actually grows -- see Village.prices.
    "bread": 4, "berries": 3, "cactus_fruit": 4,
    "tobacco": 7, "red_mushroom": 8, "agave": 7,
    "cigar": 20, "dried_mushroom": 22,          # leaf is the input; this is the good
    "wheat": 3, "wheat_wort": 4, "berry_wort": 4, "agave_wort": 4,
    "beer": 22, "liqueur": 26, "mezcal": 24,    # luxuries: worth many times the mash
    "wheat_seed": 3, "seed_bag": 3,
    "iron": 6, "shovel": 45, "pickaxe": 50, "axe": 40,
    # A log is worth a loaf. At base 1 its floor was 0.55 against bread's 2.20,
    # so a woodcutter sold FOUR logs for one meal -- his whole trade sat
    # underwater and no amount of foraging could fix that arithmetic.
    "wood": 4,
    # GUNS. A gun eats a hundredweight of iron and five hundredweight of
    # timber, so it is priced above what those cost at the floor -- the
    # village makes money on the material and the smith makes money on the
    # work, and the woods finally have a customer that buys in bulk.
    # THE PRICE OF A GUN, AND IT IS THE SAME PRICE EVERYWHERE -- what the
    # crown pays, what a trader pays, and what the player pays. These were
    # 1600 / 1900 / 8, with a CROWN_ARMS_MULT of 1.35 applied in one place
    # only, so the crown paid 2160 for a rifle the player could buy for
    # 1600 -- two prices for one gun, and the crown the only one paying the
    # real one. The premium is now simply the price.
    # THE MARGIN IS THE POINT. A gun eats 100 iron + 50 wood = 800 coin of
    # material at list prices, and a man will not build one for nothing --
    # but 2.7x the material was too much the other way. 250 over the
    # materials on a gun, 270 on a kit with its rounds: a living, not a
    # killing. 2160 was the old base PLUS the crown's 1.35 premium, which
    # is no longer applied separately.
    "rifle": 1050, "shotgun": 1100, "ammo": 11,
}
# THE CROWN'S STANDING OFFER. A nation at war pays well over the odds for
# arms, and it pays it openly: the capital's price IS the order, and a trader
# who can read a margin will carry rifles to it all day. That is how the crown
# gets serviced without anyone scripting a caravan.
PAY_MELEE = 20             # a soldier's day, axe and all
PAY_RIFLE = 30             # a rifleman's: more, but he has to buy his rounds
AMMO_WANT = 20             # below this a rifleman goes looking for cartridges
CROWN_BUFFER = 1500        # coin the crown never spends. The floor exists so
                           # the crown can always afford the dearest thing it
                           # ever buys -- a kit is 2160 + 30x11 = 2490, the
                           # priciest single item is a shotgun at 2565 -- with
                           # a little left over. 1000 was an arbitrary round
                           # number that happened to sit below the price of the
                           # thing it was supposed to guarantee.
CROWN_ARMS_MULT = 1.35     # what the crown bids over the going rate
RIFLEMEN_IN_THREE = 1      # one rifleman for every two melee
AMMO_PER_RIFLE = 30        # a rifleman is not fielded without his rounds

HARVEST_TAX = 0.20         # share of every harvest taken as goods
# What the state takes a fifth of. It used to be only crops and wood -- which
# taxed the two poorest trades in the village and let the mine, the forge, the
# laboratory and the brewery keep every coin they made.
TAXED_OUTPUT = ("iron", "cigar", "dried_mushroom", "beer", "liqueur", "mezcal")
SALES_TAX = 0.06           # share of every trade taken as coin
DAY_LENGTH = 600.0         # must match main's day/night cycle
WAGE = 10                  # a day's pay for a day's work
LOGGER_WAGE = 15           # AND A WOODSMAN IS AN EMPLOYEE, NOT A MERCHANT.
                           # He was a free trader selling logs at whatever the
                           # market bore, and measured over five days he took
                           # the whole town's money: ledgers 34,509 -> 10,226
                           # while the richest man alive went from a king with
                           # 201 to a logger with 1,526. He is paid a wage for
                           # a day's work now, and the wood he cuts is the
                           # TOWN's -- see cut_wood.
LOGGER_KEEP = 10           # logs a woodsman keeps for his own hearth; the
                           # rest is the town's, because he is its employee
KING_WAGE = 120            # the crown's salary: twelve days' work for one
MAYOR_SHARE = (2.0, 3.0)   # of the second-richest man's day, to the mayor
MAYOR_FLOOR = 20.0         # ...but never less than a decent day's pay
CROWN_SHARE = 0.50         # of every village's daily profit, to the capital
CROWN_FOOD_SHARE = 0.35    # and this much of its daily gain in FOOD

HUNGER_RATE = 100.0 / DAY_LENGTH   # a belly empties in a single day
EAT_AT = 50.0              # satiety 50 out of 100: time to eat
EAT_BY = 50.0              # one loaf restores half of a full belly
STARVE_AT = 100.0          # satiety 0

KEEP_FOOD = 3              # food a villager won't sell
STOCK_FOOD = 5             # a larder of five loaves
FUEL_KEEP = 1              # firewood a villager won't sell
STOCK_WOOD = 20.0          # ...and what a HOUSE aims to keep stacked
WOOD_PER_HOUSE = 5.0       # logs a hearth burns in a day -- it is a HOUSE that
                           # was 10, which at ITEM_VALUE 4 coin a log is 40 coin
                           # a day against a WAGE of 10: heating cost four days'
                           # wages. Five is a house kept warm for half a wage.
WARMTH_RATE = WOOD_PER_HOUSE / DAY_LENGTH   # burns wood, not a person
COLD_HUNGER = 2.0          # a cold house means you need twice the food
MINT_ITEM = "wood"         # the treasury coins its firewood, one coin the log
MINT_RESERVE = 1000        # ...but never the stack the hearths are lit from
GRADE_MEMORY = 0.30        # how far each new delivery moves the store's grade
PROVISIONS = 4             # a small bite for the road; the rest he forages
FORAGE_MEAL = 55.0         # what a roadside meal takes off his hunger
CARAVAN_DEBT_CAP = 600     # a trader may work off a debt, up to this much
FORGE_IRON = 24            # iron the ledger keeps the forge supplied with
ORDER_AT = 0.40            # durability at which a man orders his next tool
# The state intervenes. Whoever cleared a profit today is taxed on it, steeply
# the more he cleared, and four fifths of the take is handed to the trades that
# ran at a loss -- deepest hole first. The rest stays in the common purse.
TAX_BRACKETS = ((20.0, 0.00), (100.0, 0.15), (300.0, 0.30),
                (1000.0, 0.45), (float("inf"), 0.60))
# THE TAX STAYS IN THE VILLAGE. IT IS NOT REDISTRIBUTED AS COIN.
#
# This was 0.80: four fifths of every village's tax was handed straight back
# out to the poorest men as CASH, the same day it was collected. It was doing
# nothing the granary does not already do -- economy.dole() feeds a starving
# man out of the common store for nothing, "nobody dies while there is bread in
# the store" -- so it was not a safety net, it was the village giving away its
# own income and then borrowing to pay its wages.
#
# With it gone the tax stays where it lands: the village keeps it and pays the
# people it employs out of it, and the crown takes its half of the profit --
# which can now actually exist, because a village is no longer forbidden to end
# the day richer than it started.
SUBSIDY_SHARE = 0.0
MAX_STOPS = 5              # villages on one caravan route before heading home
HOUSE_PURSE = 80           # a house keeps its workers in tools and seed
HOUSE_KEEP = 100           # ...without a breadwinner giving away his last coin
HEAL_WELL_FED = 20.0       # hunger below this and the body mends itself
DOLE_AT = 85.0             # starving this badly, and the granary feeds you
DOLE_LAST = 92            # ...and he is fed regardless at this hunger. He
                           # has tried to buy and failed; the granary is the
                           # floor under EVERYBODY, not only the poor. Gating
                           # the dole on coin alone removed the last net from
                           # a man whose purchase failed, and 253 people died
                           # in a fifth of a day.
DOLE_POOR = 5              # ...but ONLY if he cannot buy a loaf himself. The
                           # cheapest food is 3-4 coin, and a seller asks a
                           # little over his cost. A man with five coin in his
                           # pocket is not a charity case -- he goes to the
                           # farmer. Without this the granary, which exists to
                           # catch the destitute, was drained dry by men who
                           # could have paid, and then fed nobody at all.
HEAL_RATE = 1.5            # hit points a second while well fed
VARIETY_MIN = 1            # ...and a taste of every kind of food there is
LEAF_KEEP = 1
LEAF_FARMER_KEEP = 5
TOOL_USES = 90             # workings a plain tool survives
TOOL_WORN = 30             # ...and a tool with fewer workings left than this
                           # is REPLACED. The old threshold was TOOL_USES // 4
                           # = 22, which is close to dead: a farmer went to the
                           # field with a tool on its last legs and then had
                           # nothing. Thirty is the smith's cue.
SMITH_WAGE = 50            # a day's pay for the forge. He is the town's
                           # employee: the iron is the town's, the bench is
                           # the town's, and so is everything he makes.
FARMER_KEEP_FOOD = 10      # what a farmer keeps of his own crop for his own
FARMER_KEEP_LEAF = 5       # hearth, a day, before the rest is the town's


def tool_dur_mult(grade: int) -> float:
    """How much longer a finer tool lasts. Deliberately SLOWER than its price:
    an SSS axe lasts 3.8x as long and costs 5.8x as much, so quality is a
    convenience and never a saving -- the smith always earns more from it, which
    is the whole reason to forge the good stuff."""
    return 1.0 + 0.35 * quality.clamp(grade)


def tool_price_mult(grade: int) -> float:
    """The price side of the same bargain. Always ahead of durability."""
    return 1.0 + 0.60 * quality.clamp(grade)
TOOL_KEEP = 1
IRON_STOCK = 48            # iron a smith likes to keep in the shop
IRON_CASH_FLOAT = 24
IRON_PER_TOOL = 4

# -- the bank and the caravans -----------------------------------------------
LOAN = 900                 # most the ledger will advance for one run
INTEREST = 0.0             # no interest on a caravan loan
BROKE_AT = 40              # below this, a trader starts looking for a run
CARAVAN_LOAD = 40          # units a trader aims to carry, each way
MIN_LOAN = 16              # below this the walk is not worth the interest
MAX_CARAVANS = 2           # caravans a village will have out at once

# -- the local leaf ----------------------------------------------------------
ADDICTED_SHARE = 0.5
YEARING_RATE = 1.0 / DAY_LENGTH
# HOW MANY PEOPLE WANT A DRINK OR A CIGAR. This was six in ten; the state
# forbids both, which is exactly what makes them worth wanting, and a large part
# of the world is now willing to get its hands on anything there is. Lower is
# more buyers -- this is a THRESHOLD on a man's craving, not a probability.
YEARING_BUY = 0.28
YEARING_ACT = 1.00
USE_FX_SECONDS = 3.0     # how long a villager savours a luxury


def crop_yield(kind: str, rng) -> tuple[str, int]:
    """(item, count) a villager gets from one ripe crop."""
    if kind == "wheat":
        return "bread", rng.randint(3, 6)
    if kind == "berries":
        return "berries", rng.randint(4, 8)
    if kind == "cactus":
        return "cactus_fruit", rng.randint(2, 4)
    if kind == "plant":
        return "tobacco", rng.randint(4, 8)
    if kind == "mushroom":
        return "red_mushroom", rng.randint(4, 8)
    if kind == "agave":
        return "agave", rng.randint(4, 8)
    return "", 0


def value(village, item: str) -> float:
    """A village's price for a thing. Kept FRACTIONAL: truncating to whole
    coins pinned every good worth under two coins at one forever -- wood could
    never show a glut or a shortage because 0.55 and 2.0 both truncate to 1."""
    return village.prices.get(item, ITEM_VALUE.get(item, 4))


def grade_of(npc, item: str) -> int:
    """The grade of the goods in this person's hands. C is the neutral middle,
    which is what all our existing prices assume."""
    return getattr(npc, "grade", {}).get(item, 3)


def graded_value(village, npc, item: str) -> float:
    """What the goods in HIS hands are worth: the village price scaled by the
    quality of his stock. F is worth a third, SSS six times over."""
    base = value(village, item)
    if item in TOOLS:
        return max(0.05, base * tool_price_mult(grade_of(npc, item)))
    return max(0.05, base * quality.SELL_VALUE[quality.clamp(grade_of(npc, item))])


def prospect(dest, item: str, grade: int) -> float:
    """What a cargo of this grade would fetch over there. Quality is part of
    the price, so it has to be part of the margin -- otherwise a village of
    SSS leaf looks exactly like a village of floor sweepings to a caravan."""
    base = value(dest, item)
    return max(0.05, base * quality.SELL_VALUE[quality.clamp(grade)])


def ledger_value(village, item: str) -> float:
    """The granary's price: its stock is a blend of everyone's grades."""
    grade = getattr(village, "ledger_grade", {}).get(item, 3)
    base = value(village, item)
    return max(0.05, base * quality.SELL_VALUE[quality.clamp(grade)])


# -- a villager's books ------------------------------------------------------
def setup(npc) -> None:
    npc.stock = {}
    npc.hunger = npc.rng.uniform(0.0, 30.0)
    npc.leaf_item = "tobacco"
    npc.grade = {}                     # the quality of what is in his hands
    npc.paid = {}                      # average price paid per unit of cargo
    npc.wants_product = PROCESS.get(npc.leaf_item)   # his smoke
    npc.wants_drink = npc.rng.choice(list(BREW.values()))   # and his drink
    npc.brew = None                    # what is sitting in his barrels
    npc.use_fx = None                  # what he is smoking, drinking or chewing
    npc.tool_order = None              # what he has booked with the smith
    npc.tool_reserved = None           # forged, sitting on the smith's shelf
    npc.tool_keep = {}                 # tools forged and held for their order
    npc.tool_orders = []               # the smith's book
    npc.book_in = 0.0                  # today's takings, for the taxman
    npc.book_out = 0.0                 # ...and today's spending
    npc.trade_stops = 0                # villages visited on this run
    npc.trade_stop = None              # the village he is heading for
    npc.quality_cap = npc.rng.randint(2, 8)   # his talent: never above this
    npc.addiction = 0.0
    if npc.rng.random() < ADDICTED_SHARE:
        npc.addiction = npc.rng.uniform(0.15, 1.0)
    npc.yearning = npc.addiction * npc.rng.uniform(0.0, 0.30)
    npc.leaf_farmer = False
    npc.tool_uses = 0
    npc.warmth = 1.0               # burns a log a day when the cold comes
    npc.duty = "labour"
    npc.duty_group = npc.rng.randint(0, 1)
    npc.on_duty = False
    npc.loan = 0                       # what he owes the ledger
    npc.trade_state = "none"           # "none"|"out"|"buy"|"home"|"sell"
    npc.trade_item = None            # what he carries out
    npc.trade_back = None            # ...and what he brings home
    npc.trade_home = None
    npc.trade_dest = None
    npc.trade_goal = 0
    npc._shop_target = None            # who he's walking to, to buy something
    npc._shop_timer = npc.rng.uniform(0.0, 1.5)   # staggered, so searches spread


def food_of(npc) -> int:
    return sum(npc.stock.get(i, 0) for i in FOOD)


def fuel_of(npc) -> int:
    return npc.stock.get("wood", 0)


def house_wood(house) -> int:
    """How many logs the whole household has stacked."""
    return sum(n.stock.get("wood", 0) for n in house.occupants if n.alive)


def household_share(house, dt: float = 1.0, village=None) -> None:
    """A house is a family, not a market: whoever has food, firewood or coin
    gives to whoever hasn't, for nothing. This is how the people with jobs carry
    the people without -- and the hearth burns for all of them at once.

    The purse must be shared for the same reason the larder is. A house that
    feeds an idle son but leaves him without a coin for a shovel has kept him
    alive and let his living rot: no shovel, no crop, no coin, forever."""
    members = [n for n in house.occupants if n.alive]
    if not members:
        return
    # The fire: a household burns a good stack of logs a day, taken from
    # whoever in the house has any. Run it cold and everybody in it suffers.
    house.warmth = max(0.0, getattr(house, "warmth", 1.0) - WARMTH_RATE * dt)
    if house.warmth <= 0.12:
        for npc in members:
            if npc.stock.get("wood", 0) > 0:
                npc.stock["wood"] -= 1
                house.warmth = 1.0
                break
        else:
            # Nobody in the house has a log. The village keeps the hearths lit
            # out of the common stack rather than let a family freeze -- this is
            # what the loggers' tax is for.
            if village is not None and village.ledger_goods.get("wood", 0) > 0:
                store_take(village, "wood", 1)
                house.warmth = 1.0
    if len(members) < 2:
        return
    for npc in members:
        if npc.in_interior:
            continue
        if npc.hunger >= EAT_AT or food_of(npc) <= 0:
            for other in members:
                if other is npc or other.in_interior:
                    continue
                given = False
                for item in FOOD:
                    if other.stock.get(item, 0) > KEEP_FOOD:
                        other.stock[item] -= 1
                        npc.stock[item] = npc.stock.get(item, 0) + 1
                        given = True
                        break
                if given:
                    break
    # THE PURSE IS NOT THE FAMILY'S. BREAD AND FIREWOOD ARE.
    #
    # This topped every member's purse up to HOUSE_PURSE out of whoever had
    # spare coin above HOUSE_KEEP -- "the purse is the family's too" -- so a
    # man with no trade was handed his brother's wages. Measured at day 10 of a
    # live world, 164 men with no job were earning 13 coin a day each, 2,128 a
    # day out of the ledgers, for nothing at all. A household that lets its own
    # go cold or hungry is not a household; a man who wants a purse takes a
    # post. He eats from the family larder and the common granary -- see
    # household_share's food and fuel loops above, and economy.dole.
    for npc in members:
        if npc.in_interior:
            continue
        if fuel_of(npc) <= 0:
            for other in members:
                if other is npc or other.in_interior:
                    continue
                if other.stock.get("wood", 0) > FUEL_KEEP:
                    other.stock["wood"] -= 1
                    npc.stock["wood"] = npc.stock.get("wood", 0) + 1
                    break


def leaf_of(npc) -> int:
    return sum(npc.stock.get(i, 0) for i in LEAF)


def local_leaf_of(npc) -> int:
    item = npc.leaf_item
    return npc.stock.get(item, 0) if item else 0


def is_worker(npc) -> bool:
    return (npc.farm_plot is not None
            or npc.job in ("mine", "smith", "logger")
            or npc.defender
            or npc.duty == "armed")


def wears_tool(npc, item: str) -> bool:
    """Who uses what. Farmers wear shovels; woodsmen wear axes.

    AND MINERS WEAR PICKAXES -- which this never said, so no man in the world
    was ever a pickaxe's owner: `wears_tool` answered False for one, so
    `needs_tool` answered False, so nobody was ever short of one, so the forge
    had no reason to make one and `forge_kind` had no way to choose it. A
    pickaxe has never been produced in this game.
    """
    if item == "shovel":
        return npc.farm_plot is not None
    if item == "axe":
        return npc.job == "logger"
    if item == "pickaxe":
        wp = getattr(npc, "workplace", None)
        return (getattr(npc, "job", None) == "mine"
                or getattr(wp, "kind", None) == "mine")
    return False


def needs_tool(npc, item: str) -> bool:
    """Is he down to the last of it, with nothing on the shelf?"""
    if not wears_tool(npc, item):
        return False
    if npc.stock.get(item, 0) > 0:
        return False
    return npc.tool_uses <= TOOL_WORN


def place_orders(village, npc) -> None:
    """A working man orders his next tool before the last one dies.

    At 40% wear he books one with the smith, who works from the order book --
    so the forge turns out what the village is actually short of, and a man
    never finds himself standing idle because nobody guessed he would need an
    axe three weeks from now.
    """
    # One order at a time. `tool_reserved` was a second lock -- the mark left
    # when a finished tool was parked on the smith's lap -- and it deadlocked
    # the whole chain, so fill_orders no longer sets it and nothing sets it.
    if npc.tool_order is not None:
        return
    # AND A PICKAXE IS A TOOL A MAN ORDERS TOO. This list was ("shovel",
    # "axe"), so no miner in the world ever booked one -- the only reason he
    # could buy a pickaxe at all was the shelf, and the shelf only ever held
    # one because forge_next was going behind the book's back.
    want = next((t for t in ("shovel", "axe", "pickaxe")
                 if wears_tool(npc, t)), None)
    if want is None or npc.stock.get(want, 0) > 0:
        return
    # THE USES MUST BELONG TO THE TRADE HE IS IN NOW.
    #
    # `tool_uses` is the life left in the tool in his hand, and it does not
    # travel: a farmer who takes a post at the pit keeps a banked 90 that
    # described a shovel he has since put down, and 90 reads as "plenty left"
    # for a pickaxe he has never owned. So he never books one, stands at the
    # face with an empty hand, and the forge never hears from him. Measured:
    # 96 miners, 22 pickaxes.
    #
    # A tool of a DIFFERENT kind is not a tool of this kind, so the count
    # starts again from nothing and the book gets its order.
    if getattr(npc, "tool_kind", None) != want:
        npc.tool_kind = want
        npc.tool_uses = 0
    # THIRTY WORKINGS, as asked. It was 40% of the tool's life, which is a
    # different number for a fine tool than a plain one and is not the cue
    # anybody chose.
    if npc.tool_uses > TOOL_WORN:
        return
    # AND HE DOES NOT ORDER WHAT THE TOWN ALREADY HAS ON THE SHELF.
    #
    # Without this the brake is only `tool_order`, and that is cleared the
    # moment the order is filled -- which is BEFORE he has bought the thing.
    # He still has no tool, so the next tick he books another one, and the
    # forge hammers him a second, and a third. The shelf read 51, then 728,
    # then 1016 pickaxes for ninety miners.
    #
    # This is a brake that cannot deadlock, because the store is sellable: the
    # tool is there, on the common shelf, and he buys it like anything else.
    if int(village.ledger_goods.get(want, 0)) > 0:
        return
    smith = next((o for o in village.npcs
                  if o.job == "smith" and o.alive), None)
    if smith is None:
        return
    npc.tool_order = want
    smith.tool_orders.append((npc, want))


def fill_orders(village, smith, kind: str) -> int:
    """A hammered tool ANSWERS an order, and then goes on the town shelf.

    It used to be parked on the SMITH's own shelf as `tool_keep` and marked on
    the man as `tool_reserved` -- a second delivery system, and it deadlocked:
    economy.count_available counts `tool_keep` as KEPT, so the reserved tool was
    hidden from the market, so the very man who ordered it could not find a
    seller, and `tool_reserved` stopped him ordering another. He waited for
    ever and the smith held the tool. Measured: 96 miners, 22 pickaxes.

    The store is the one place a tool is sold. Send it there -- smith_shift has
    already put it on the shelf -- and clear the order so the man can book
    another when this one wears.
    """
    done = 0
    for order in list(getattr(smith, "tool_orders", ())):
        who, want = order
        if want != kind:
            continue
        smith.tool_orders.remove(order)
        if not getattr(who, "alive", False):
            continue
        who.tool_order = None               # answered; he may book again
        who.tool_reserved = None
        done += 1
    return done


# -- production ---------------------------------------------------------------
def store_add(village, item: str, n: int, grade: int = 3) -> None:
    """Count every unit into the store by the grade it came in at."""
    if n <= 0:
        return
    village.ledger_goods[item] = village.ledger_goods.get(item, 0) + n
    lots = village.ledger_lots.setdefault(item, {})
    lots[grade] = lots.get(grade, 0) + n
    store_grade(village, item)


def store_take(village, item: str, n: int) -> int:
    """Take n out, worst grade first: the poor leaf leaves before the good, so
    what is left in the store is as good as it looks."""
    if n <= 0:
        return 0
    have = int(village.ledger_goods.get(item, 0))
    take = min(have, n)
    if take <= 0:
        return 0
    village.ledger_goods[item] = have - take
    lots = village.ledger_lots.get(item)
    if lots is not None:
        left = take
        for g in sorted(lots):
            got = min(lots[g], left)
            lots[g] -= got
            left -= got
            if left <= 0:
                break
    store_grade(village, item)
    return take


def store_grade(village, item: str) -> None:
    """The store's grade is the plain weighted mean of what it actually holds:
    100 of F and 100 of A is 200 of the middle. Nothing cleverer."""
    lots = village.ledger_lots.get(item)
    total = sum(lots.values()) if lots else 0
    if total <= 0:
        village.ledger_grade[item] = 3
        return
    mean = sum(g * c for g, c in lots.items()) / float(total)
    village.ledger_grade[item] = quality.clamp(int(round(mean)))


def harvest(village, npc, kind: str, rng) -> None:
    """A farmer brings in a crop. HE IS AN EMPLOYEE AND THE CROP IS THE TOWN'S.

    He keeps FARMER_KEEP_FOOD of food and FARMER_KEEP_LEAF of leaf a day for
    his own hearth, draws a wage like the woodsman, and everything else he
    reaps goes onto the common shelf for the town to sell.

    It was "the village takes its 20%" -- a tax on a private crop, which left
    him a smallholder with a stall. Measured at day 0 of a live world: farm,
    191 men, earned 0.0 a day each, while a shovel costs 45. When his lasted
    its ninety swings there was no way on earth for him to buy another, and
    that is what killed the fields.
    """
    item, count = crop_yield(kind, rng)
    if not item or count <= 0:
        return
    # A MASTER'S HAND GATHERS THREE TIMES AS MUCH from the same plant.
    try:
        import crop as _crop
        count = max(1, int(round(count * _crop.yield_scale(npc.skills.farming))))
    except Exception:
        pass
    if kind == "wheat":                    # thresh it too: bread, and grain
        grain = rng.randint(2, 4)
        npc.stock["wheat"] = npc.stock.get("wheat", 0) + grain
    grade = 3
    if item in LEAF:                       # leaf has a grade; grain does not (yet)
        grade = npc.skills.leaf_grade(npc.quality_cap)
        npc.grade[item] = grade
    keep = farmer_keep(npc, item, int(count))
    if keep > 0:
        npc.stock[item] = npc.stock.get(item, 0) + keep
    rest = int(count) - keep
    if rest > 0:
        store_add(village, item, rest, grade)


def farmer_keep(npc, item: str, count: int) -> int:
    """How much of this pick he keeps: ten of food a day, five of leaf.

    Counted per DAY, because a harvest arrives a tile at a time and a man may
    reap a hundred of them before supper. Without the daily tally he would
    keep ten of every tile and the town would get nothing at all.
    """
    v = getattr(npc, "village", None)
    day = int(getattr(v, "_day", 0.0)) if v is not None else 0
    if getattr(npc, "keep_day", -1) != day:
        npc.keep_day = day                 # a fresh day, a fresh ration
        npc.keep_food = 0
        npc.keep_leaf = 0
    if item in FOOD:
        room = FARMER_KEEP_FOOD - int(getattr(npc, "keep_food", 0))
        keep = max(0, min(int(count), room))
        npc.keep_food = int(getattr(npc, "keep_food", 0)) + keep
        return keep
    if item in LEAF:
        room = FARMER_KEEP_LEAF - int(getattr(npc, "keep_leaf", 0))
        keep = max(0, min(int(count), room))
        npc.keep_leaf = int(getattr(npc, "keep_leaf", 0)) + keep
        return keep
    return int(count)          # grain and anything else is his own


def take_fifth(village, npc, item: str, made: int) -> int:
    """A fifth of it, in kind, to the common store -- the same as a crop.

    Iron out of the pit, cigars off the bench, beer out of the barrel: the
    state takes its share of what is produced, not merely of what is grown.
    Returns what the maker keeps.
    """
    if item not in TAXED_OUTPUT or made <= 0:
        return made
    # A fifth of ONE cigar rounds to nothing, and the artisan works one at a
    # time -- so carry the fraction until it makes a whole. (The harvest tax
    # had exactly this bug once already.)
    frac = npc.tax_frac + made * HARVEST_TAX
    tax = int(frac)
    npc.tax_frac = frac - tax
    if tax > 0:
        store_add(village, item, tax, grade_of(npc, item))
    return made - tax


def cut_wood(village, npc, amount: int) -> None:
    """A logger's take. HE IS PAID A WAGE AND THE WOOD IS THE TOWN'S.

    He used to be a free trader: every log he cut was his, he sold it at
    whatever the market bore, and he kept the lot. Measured over five days of
    a live world, that one arrangement moved the whole economy into his
    pocket -- the towns' ledgers fell 34,509 to 10,226, seventy per cent of
    every coin they had, while the richest man alive went from a king with 201
    to a logger with 1,526, and 337 men sat on a hundred coins each.

    So he keeps ten logs for his own hearth, the rest goes into the common
    store, and the town SELLS it to the people who need it. The coin for the
    wood lands in the ledger that pays his wage, which is the whole point.
    """
    amount = int(amount)
    keep = min(amount, LOGGER_KEEP)
    rest = amount - keep
    if keep > 0:
        npc.stock["wood"] = npc.stock.get("wood", 0) + keep
    if rest > 0:
        store_add(village, "wood", rest)


# -- what a villager wants, and what he'll pay --------------------------------
def urgency(npc, item: str) -> float:
    if item in FOOD:
        empty = 1.0 if food_of(npc) <= 0 else 0.0
        # A taste of a kind he hasn't got. This is the whole reason a village
        # will pay over the odds for something it cannot grow itself.
        missing = 0.85 if npc.stock.get(item, 0) < VARIETY_MIN else 0.0
        return max(empty, missing, min(1.0, npc.hunger / 100.0))
    if item in LEAF:
        # A tradesman buying STOCK is not a man buying a smoke. His living
        # depends on the leaf, so his bid must beat the farmers' ask -- pricing
        # his bench off his own craving left the artisan unable to buy anything.
        if npc.job == "lab" and item in PROCESS:
            return 1.0
        return min(1.0, npc.yearning)
    if item in MASH:
        # Same for the mash tun: the brewer buys to brew, not to taste.
        return 1.0 if npc.job == "brewery" else 0.0
    if item == "wood":
        # A cold house is urgent. This is what makes firewood worth buying
        # rather than merely piling up in the woodsman's yard.
        house = npc.home_house
        if house is not None and getattr(house, "warmth", 1.0) <= 0.35:
            return 1.0
        return 0.2
    if item in TOOLS:
        return 1.0 if needs_tool(npc, item) else 0.0
    if item == "iron":
        if npc.job == "smith":
            return 1.0 if npc.stock.get("iron", 0) < IRON_STOCK else 0.0
        return 0.0
    return 0.15


def ask_price(village, npc, item: str, base: float | None = None) -> float:
    """A seller haggles only a little: the worth of the goods -- which carries
    both local scarcity and their quality -- is what decides a trade."""
    if base is None:
        base = graded_value(village, npc, item)
    patience = min(1.0, npc.coins / 80.0)
    return max(0.05, base * (0.90 + 0.10 * patience))


def bid_price(village, npc, item: str, base: float | None = None) -> float:
    if base is None:
        base = graded_value(village, npc, item)
    return max(0.05, base * (0.90 + 0.25 * urgency(npc, item)))


def surplus(npc, item: str) -> int:
    if npc.trade_state != "none":
        return npc.stock.get(item, 0)      # a trader's cargo is all for sale
    keep = 0
    if item in ARMS:
        # A MAN KEEPS THE MUSKET HE CARRIES. One is his own kit; a second is
        # stock, and stock is for sale. Without this the first evening market
        # after a garrison stood down would flog every veteran's rifle, and he
        # would be unarmed by supper -- a choice the market made FOR him. The
        # crown is not bound by this: _buy_off_people reads stock directly, so
        # a deliberate buyer can still purchase the musket off a man's back.
        keep = 1
    elif item in FOOD:
        keep = KEEP_FOOD
    elif (item == npc.leaf_item
          and npc.addiction > 0.0):
        keep = LEAF_FARMER_KEEP if npc.leaf_farmer else LEAF_KEEP
    elif item == "iron":
        keep = IRON_STOCK if npc.job == "smith" else 0
    elif item == "wood":
        # The hearth comes first: a man does not sell wood his own house still
        # needs. Sell only what is above the household's stack.
        house = npc.home_house
        own = npc.stock.get("wood", 0)
        if house is None:
            keep = FUEL_KEEP
        else:
            keep = max(FUEL_KEEP, STOCK_WOOD - (house_wood(house) - own))
        return max(0, own - keep) if item == "wood" else 0
    elif item in TOOLS:
        # WHO WEARS THIS TOOL, BY NAME. This was `npc.farm_plot is not None or
        # npc.job == "logger"` -- which is the same answer for every tool, so a
        # woodsman kept a spare SHOVEL and a farmer kept a spare AXE, and
        # neither would sell what the other needed.
        worn = ((item == "shovel" and npc.farm_plot is not None)
                or (item == "axe" and getattr(npc, "job", None) == "logger")
                or (item == "pickaxe"
                    and (getattr(npc, "job", None) == "mine"
                         or getattr(getattr(npc, "workplace", None),
                                    "kind", None) == "mine")))
        keep = TOOL_KEEP if npc.stock.get(item, 0) or worn else 0
        keep += int(getattr(npc, "tool_keep", {}).get(item, 0))   # promised work
    return max(0, npc.stock.get(item, 0) - keep)


def wants(npc, item: str) -> int:
    if item in FOOD:
        have = npc.stock.get(item, 0)
        if have < VARIETY_MIN:
            return VARIETY_MIN - have       # always room for a new taste
        if food_of(npc) < STOCK_FOOD:
            return STOCK_FOOD - food_of(npc)   # in bulk: a larder, not a loaf
        return 0
    if item in FINISHED:
        # The habit is for the FINISHED good now. Raw leaf does nothing for it.
        if (item == npc.wants_product
                and npc.yearning >= YEARING_BUY):
            return 1
        return 0
    if item in BREW.values():
        # A drink is a want of its own, and everybody wants one.
        if (item == npc.wants_drink
                and npc.yearning >= YEARING_BUY):
            return 1
        return 0
    if item in MASH:
        # Only a brewer buys mash -- and never the food out of a man's larder.
        if npc.job != "brewery":
            return 0
        short = WORT_STOCK - npc.stock.get(item, 0)
        return short if short > 0 else 0        # a mash tun wants a cartload
    if item in LEAF:
        # Raw leaf is an INPUT now, not a habit. Only the artisan wants it, and
        # only the kinds his laboratory can work.
        if npc.job == "lab" and item in PROCESS:
            short = LEAF_STOCK - npc.stock.get(item, 0)
            if short > 0:
                return short                     # buy the bench full, in bulk
        return 0
    if item == "iron":
        if npc.job == "smith":
            shortfall = IRON_STOCK - npc.stock.get("iron", 0)
            price = max(1, ITEM_VALUE.get("iron", 4))
            affordable = int(max(0, (npc.coins - IRON_CASH_FLOAT) // max(0.05, price)))
            return max(0, min(shortfall, affordable))
        return 0
    if item == "wood":
        # Keep the woodpile up, exactly as a larder is kept up: a house wants
        # a stack, not a single log, and it buys a few at a time.
        house = npc.home_house
        if house is None:
            return 0
        short = int(STOCK_WOOD - house_wood(house))
        return min(8, short) if short > 0 else 0
    if item in ARMS:
        # THE ARMS TRADE, AND WHO IS IN IT. A musketeer is the crown, which
        # arms its soldiers off its own people, and the caravan, which carries
        # what is cheap here to where it is dear. A VILLAGER DOES NOT SHOP FOR
        # A GUN: left to the 3% fallback below he would, and every man who
        # bought one would drop out of the levy as "already a fighting man"
        # (see war._takeable) -- a war lost to a rounding error.
        if npc.trade_state != "none":
            return 1                 # a caravan will carry one, for the margin
        return 0
    if item in TOOLS:
        return 2 if needs_tool(npc, item) else 0     # a spare, while he is there
    # A soldier traded with at a gate has no `rng` of his own, and this
    # raised AttributeError inside the menu's layout -- which froze the game
    # the moment you clicked one. Anyone without dice rolls the world's.
    _rng = getattr(npc, "rng", None)
    if _rng is None:
        import random as _random
        _rng = _random.Random()
    return 1 if _rng.random() < 0.03 else 0


# -- settlement ---------------------------------------------------------------
def monetize(village, amount: int) -> int:
    """Coin the granary's firewood, one coin the log.

    The ledger's wealth is held in goods, so when it wants coin it must coin
    its own stock -- not tax the village's coin out of circulation. Every coin
    taken in sales tax was a coin the farmers never got to spend on shovels.

    Wood is the right stock to coin because a log is worth exactly one coin:
    the exchange destroys nothing. A leaf is worth seven, so coining leaf burnt
    seven coins of value to make one."""
    if amount <= 0:
        return 0
    have = int(village.ledger_goods.get(MINT_ITEM, 0))
    # Coin only what is above the reserve. Burning the village's winter fuel
    # for coin froze its houses, doubled every hunger rate and starved 161
    # people in a month -- the mint must not touch the wood that warms them.
    take = min(max(0, have - MINT_RESERVE), amount)
    if take <= 0:
        return amount
    store_take(village, MINT_ITEM, take)
    flow(village, 'monetize', (take))
    village.ledger_coins += take
    return amount - take


def _settle(village, item, price, qty, seller, buyer) -> int:
    """Move qty of item for qty*price, plus sales tax between villagers."""
    if seller is None:
        price = max(1, price)
        qty = int(min(qty, village.ledger_goods.get(item, 0),
                      buyer.coins // max(0.05, price)))
        if qty <= 0:
            return 0
        cost = int(round(price * qty))
        store_take(village, item, qty)
        flow(village, '_settle', (cost))
        village.ledger_coins += cost
        buyer.coins -= cost
    else:
        qty = int(min(qty, seller.stock.get(item, 0), surplus(seller, item),
                      buyer.coins // max(0.05, price)))
        if qty <= 0:
            return 0
        gross = int(round(price * qty))
        if item in TOOLS and buyer.tool_reserved == item:
            buyer.tool_reserved = None      # collected: he can order again
        if item in TOOLS and item in getattr(seller, "tool_keep", {}):
            # A promised tool leaves the reserved shelf when it is collected.
            seller.tool_keep[item] = max(0, seller.tool_keep[item] - qty)
        if item in TOOLS or item in LEAF:
            # A tool carries its workmanship, and leaf carries its quality: buy
            # floor sweepings and the cigars you roll from them are floor
            # sweepings too, however good your hands are.
            held = buyer.stock.get(item, 0)
            buyer.grade[item] = quality.merge(grade_of(buyer, item), held,
                                              grade_of(seller, item), qty)
        seller.stock[item] -= qty
        # ------------------------------------------------------------------
        # THE TOWN'S CUT COMES OUT OF THE SALE, NOT OUT OF THIN AIR.
        #
        # This said `seller.coins += gross` -- THE SELLER KEEPS THE LOT -- and
        # then MINTED the town's 6% by coining the town's own firewood. So a
        # trade moved coin from a buyer's purse to a seller's purse and the
        # town, which had paid the wage that bought the loaf, took home nothing
        # it did not have to burn a log for. Measured over five days:
        #
        #   ledgers  34,509 -> 10,226      the towns losing 24,283, 70% of all
        #   purses   79,038 -> 115,197     their money
        #   richest  Josiah(king)201  ->  Bubba(logger)1,526
        #
        # The town's money is not a gift from the forest. It is a share of the
        # trade it makes possible, and it is taken at the moment of the trade.
        frac = getattr(village, "_tax_frac", 0.0) + gross * SALES_TAX
        cut = int(frac)
        village._tax_frac = frac - cut
        seller.coins += gross - cut
        seller.book_in = getattr(seller, "book_in", 0.0) + (gross - cut)
        buyer.book_out = buyer.book_out + gross
        buyer.coins -= gross
        flow(village, '_settle', (cut))
        village.ledger_coins += cut
    buyer.stock[item] = buyer.stock.get(item, 0) + qty
    if seller is not None:
        # A TRADE IS A RELATIONSHIP. Both men come away knowing the other a
        # little better -- +1 each way, capped. Buying off the village's own
        # ledger is not a trade with a person, so it warms nobody.
        grow_opinion(seller, buyer)
    # AND THE DEAL SHOWS ON HIS FACE. Raised HERE, at the settlement, so it is
    # the TRADE that does it and not the fact that he is a trader standing in
    # a market. Both sides are checked, because a trader buying looks exactly
    # as pleased with himself as a trader selling -- and a deal that fell
    # through returns long before this line, so nothing shows on his face.
    for _who in (seller, buyer):
        if _who is not None and getattr(_who, "job", None) == "trader":
            _who.sly_flash = face.SLY_SECONDS
    return qty


def pair_trade(village, a, b) -> bool:
    """A villager buys what he wants from the other, if their prices meet."""
    for seller, buyer in ((a, b), (b, a)):
        for item in GOODS:
            want = wants(buyer, item)
            if want <= 0:
                continue
            qty = surplus(seller, item)
            if qty <= 0:
                # A NEIGHBOUR AT THE POINT OF DEATH OUTRANKS A KEEPER'S RESERVE.
                # KEEP_FOOD is three loaves, and a village that shares its
                # harvest evenly sits at about three a head -- so surplus() was
                # zero for EVERY soul, there was no seller in the whole town,
                # the granary stayed empty because nobody sold, and men with
                # coin starved beside a neighbour's bread. His hunger beats the
                # seller's keep: he buys ONE loaf, at the asking price.
                if (item in FOOD and getattr(buyer, "hunger", 0.0) >= DOLE_LAST
                        and seller.stock.get(item, 0) > 0):
                    qty = 1
                else:
                    continue
            ask = ask_price(village, seller, item)
            bid = bid_price(village, buyer, item)
            if ask > bid:
                continue
            if _settle(village, item, (ask + bid) // 2,
                       min(want, qty), seller, buyer):
                return True
    return False


def market(village) -> None:
    """The evening market: a call auction per item, cleared by price."""
    for item in GOODS:
        sellers = []
        for npc in village.npcs:
            if npc.alive and not npc.in_interior and not npc.asleep \
                    and npc.trade_state == "none" \
                    and surplus(npc, item) > 0:
                sellers.append((ask_price(village, npc, item),
                                surplus(npc, item), npc))
        buyers = []
        for npc in village.npcs:
            if npc.alive and not npc.in_interior and not npc.asleep \
                    and npc.trade_state == "none" \
                    and wants(npc, item) > 0:
                buyers.append((bid_price(village, npc, item),
                               wants(npc, item), npc))
        if not sellers or not buyers:
            continue
        village._rng.shuffle(sellers)
        sellers.sort(key=lambda s: s[0])
        buyers.sort(key=lambda b: -b[0])
        last = None
        for _b, bqty, buyer in buyers:
            for i, (ask, sqty, seller) in enumerate(sellers):
                if sqty <= 0 or bqty <= 0:
                    continue
                # Price the bid off the goods actually on the table, not off the
                # buyer's own idea of what the thing is worth. Asking 235 for a
                # master's axe against a C-grade bid of 145 cleared nothing, so
                # no fine tool could ever change hands.
                bid = bid_price(village, buyer, item,
                                graded_value(village, seller, item))
                if ask > bid:
                    continue
                sold = _settle(village, item, (ask + bid) // 2, bqty,
                               seller, buyer)
                if sold:
                    last = (ask + bid) // 2
                    sellers[i] = (ask + 1, sqty - sold, seller)
                    bqty -= sold
        if last is not None:
            base = ITEM_VALUE.get(item, 4)
            new = value(village, item) * 0.8 + last * 0.2
            # Keep the fraction: a glut of wood must be able to read below one
            # coin, and a shortage above it.
            village.prices[item] = round(max(base * 0.55, min(base * 2.0, new)), 3)


# -- the bank -----------------------------------------------------------------
def borrow(village, npc, amount: int) -> int:
    """The ledger lends at interest. Returns the principal actually advanced."""
    amount = min(amount, village.ledger_coins)
    if amount <= 0:
        return 0
    flow(village, 'borrow', -(amount))
    village.ledger_coins -= amount
    npc.coins += amount          # THE PRINCIPAL ACTUALLY CHANGES HANDS.
    # Without this the ledger quietly deleted the money, recorded a debt, and
    # the borrower never saw a coin: traders borrowed 224 a trip and shopped
    # with 30, and farmers "borrowed" for a shovel and could not buy one --
    # 669 sales failed with "buyer broke (has 0, wants 46)" while the bank
    # reported lending him the price. One missing line starved the fields.
    npc.loan += int(round(amount * (1.0 + INTEREST)))
    return amount


def repay(village, npc) -> None:
    """Pay back what you can of the loan, interest included."""
    if npc.loan <= 0:
        return
    paid = min(npc.loan, npc.coins)
    npc.coins -= paid
    npc.loan -= paid
    flow(village, 'repay', (paid))
    village.ledger_coins += paid


# ---- CASH FLOW INSTRUMENT (temporary: tells us where a village's money GOES) --
# The big outgoings have never logged anything: pay_crown, pay_wages,
# pay_garrison, buy_material and the gunworks all move coin in silence, so a
# village ledger could bleed 700 a day with nothing in the log to say why.
FLOW: dict = {}
_FLOW_DAY = -1
def flow(village, tag: str, amount) -> None:
    try:
        d = FLOW.setdefault(getattr(village, "name", "?"), {})
        d[tag] = d.get(tag, 0.0) + float(amount)
    except Exception:
        pass


def flow_report(day) -> None:
    """One line a day: every village's money in and out, biggest first."""
    global _FLOW_DAY
    if _FLOW_DAY == day:
        return                      # once a day, not once a village
    _FLOW_DAY = day
    _note("day %4d  ---------- WHERE THE MONEY GOES ----------" % day)
    # EVERY town with real movement, not the top eight: the capitals were
    # draining 1,087 in the day and only 366 of it was in the printed window,
    # and a report that hides a third of the money is worse than none.
    for name, d in sorted(FLOW.items(),
                          key=lambda kv: -abs(sum(kv[1].values()))):
        inn = sum(v for k, v in d.items() if v > 0)
        out = sum(v for k, v in d.items() if v < 0)
        if abs(inn) < 1 and abs(out) < 1:
            continue
        parts = " ".join("%s:%+d" % (k, int(v))
                         for k, v in sorted(d.items(), key=lambda kv: -abs(kv[1]))
                         if abs(v) >= 1)[:220]
        _note("day %4d  FLOW %-14s in %6d  out %7d  net %+7d   %s"
              % (day, name, int(inn), int(out), int(inn + out), parts))
    FLOW.clear()


SHOVEL_LOAN_MARGIN = 1.2    # lend enough to cover the ask and then some
LOAN_RESERVE = 60           # a working man keeps something in his pocket


def tool_loan(village, npc) -> int:
    """A working man must not lose his living for want of the price of a shovel.
    The ledger is a bank, so it advances the tool's price against the harvest.
    One loan at a time -- debts do NOT roll (that was never authorised, and when
    I tried it a farmer borrowed cash, spent it on bread, borrowed again, and
    ran up 4,008 coins of debt while draining the ledger to zero)."""
    want = next((t for t in ("shovel", "axe") if needs_tool(npc, t)), None)
    if want is None or npc.loan > 0:
        return 0
    # Size the advance from what the smith is ACTUALLY asking -- his own
    # workmanship is priced in, and a master's axe costs five times a plain one.
    # Lending against the base price left poor men unable to afford the very
    # tool the loan was meant to buy them.
    smith = next((o for o in village.npcs
                  if o.job == "smith" and o.alive
                  and o.stock.get(want, 0) > 0), None)
    ask = (ask_price(village, smith, want) if smith is not None
           else value(village, want) * SHOVEL_LOAN_MARGIN)
    price = int(ask * SHOVEL_LOAN_MARGIN) + 2
    if npc.coins >= price:
        return 0                        # he can afford it; leave the bank alone
    got = borrow(village, npc, price - npc.coins)
    if got:
        _note("day %.2f  %-16s borrowed %d for a %s (purse had %d, owes %d)"
              % (getattr(village, "_day", 0.0), npc.name, got, want, npc.coins, npc.loan))
    return got


def buy_provisions(village, npc) -> int:
    """No trader leaves the gate without food for the road.

    He takes what the household can spare first and BUYS the rest -- off the
    granary, then off any neighbour with a surplus. A trader who sets out
    hungry dies on the road, and the ledger loses the man and the loan."""
    bought = 0
    for _ in range(PROVISIONS * 2):
        if PROVISIONS - sum(npc.stock.get(i, 0) for i in FOOD) <= 0:
            break
        for item in FOOD:
            price = value(village, item)
            if npc.coins < price:
                continue
            if village.ledger_goods.get(item, 0) > 0:
                store_take(village, item, 1)
                flow(village, 'buy_provisions', (price))
                village.ledger_coins += price
            else:
                seller = next((o for o in village.npcs
                               if o is not npc and o.alive
                               and o.stock.get(item, 0) > KEEP_FOOD), None)
                if seller is None:
                    continue
                seller.stock[item] -= 1
                seller.coins += price
            npc.coins -= price
            npc.stock[item] = npc.stock.get(item, 0) + 1
            bought += 1
            break
        else:
            break                    # nobody anywhere has food to sell
    return bought


def forge_loan(village, npc) -> int:
    """The ledger keeps the forge in iron.

    A smith who cannot buy stock cannot sell a tool, and a village with no tools
    cannot work: his poverty is everybody's. The bank advances the ore straight
    out of the miners' hands and takes it back out of the tools -- the same
    bargain as a farmer's shovel, extended to the man who makes them."""
    if npc.job != "smith" or not npc.alive:
        return 0
    short = FORGE_IRON - int(npc.stock.get("iron", 0))
    if short <= 0:
        return 0
    price = max(1.0, value(village, "iron"))
    for miner in village.npcs:
        if getattr(miner, "job", None) != "mine" or not miner.alive:
            continue
        have = int(miner.stock.get("iron", 0))
        if have <= 0:
            continue
        take = int(min(have, short, village.ledger_coins // price))
        if take <= 0:
            return 0
        paid = int(round(price * take))
        miner.stock["iron"] -= take
        miner.coins += paid
        flow(village, 'forge_loan', -(paid))
        village.ledger_coins -= paid
        npc.stock["iron"] = npc.stock.get("iron", 0) + take
        npc.loan += paid                       # the forge owes the bank
        return take
    return 0


def service_loan(village, npc) -> None:
    """Pay the ledger back out of what is left once a man has lived."""
    if npc.loan <= 0:
        return
    # A LOAN FOR AN UNBOUGHT TOOL IS NOT REPAID.
    #
    # This sat three lines under tool_loan in NPC.tick, so a man who needed a
    # shovel borrowed the price of one and had it taken straight back by the
    # very next call: purse 119 -> borrow 32 -> 151 -> spare 151-60 -> repay
    # 32 -> 119. He still had no shovel, so one second later he did it again,
    # and again, for ever -- draining the ledger and burning the frame. It was
    # invisible while only a few towns ticked.
    #
    # The loan exists so the man can BUY the tool. While he still needs it, the
    # debt stands and tool_loan's own `npc.loan > 0` guard keeps him from
    # borrowing twice. Once it is bought, needs_tool goes false and this
    # repays out of his spare like any other debt.
    if any(needs_tool(npc, t) for t in ("shovel", "axe")):
        return
    spare = npc.coins - LOAN_RESERVE
    if spare <= 0:
        return
    paid = min(npc.loan, spare)
    npc.coins -= paid
    npc.loan -= paid
    flow(village, 'service_loan', (paid))
    village.ledger_coins += paid


def is_watch(npc) -> bool:
    """Only the watch is on the payroll -- everyone else sells what they make."""
    return (npc.defender
            or npc.is_commander
            or npc.duty == "armed")


def tax_due(profit: float) -> float:
    """What a man owes on a day's profit. Progressive, by the bracket."""
    if profit <= 0.0:
        return 0.0
    total = 0.0
    floor = 0.0
    for cap, rate in TAX_BRACKETS:
        if profit <= floor:
            break
        total += (min(profit, cap) - floor) * rate
        floor = cap
    return total


def crown_dues(village, day: int) -> int:
    """Half of a village's net profit for the day, straight to the capital.

    Profit, not turnover: the crown takes its half of what the village actually
    cleared after wages, iron and everything else. A village that lost money
    owes nothing -- the capital does not feed on a deficit.
    """
    if getattr(village, "is_capital", False):
        return 0
    if getattr(village, "_crown_day", -1) == day:
        return 0
    village._crown_day = day
    now = village.ledger_coins
    prev = getattr(village, "_crown_base", None)
    village._crown_base = now
    if prev is None:
        return 0
    profit = now - prev
    if profit <= 0:
        return 0
    due = int(profit * CROWN_SHARE)
    if due <= 0:
        return 0
    cap = village.capital()
    if cap is None or cap is village:
        return 0
    flow(village, 'crown_dues', -(due))
    village.ledger_coins -= due
    flow(cap, 'crown_dues', (due))
    cap.ledger_coins += due
    _note("day %4d  %-16s CROWN %5d of %5d profit sent to %s"
          % (day, village.name, due, profit, cap.name))
    return due


def village_food(village) -> int:
    """Everything edible the village is holding: granary and larders."""
    return (sum(food_of(n) for n in village.npcs if n.alive)
            + sum(village.ledger_goods.get(k, 0) for k in FOOD))


def take_food(village, amount: int) -> dict:
    """Take food out of a village: the granary first, then the people's
    larders. Returns {item: units} actually taken -- never more than is there."""
    left = int(amount)
    moved: dict = {}
    if left <= 0:
        return moved
    for item in FOOD:                            # the government's stores first
        have = village.ledger_goods.get(item, 0)
        if have <= 0:
            continue
        take = min(have, left)
        village.ledger_goods[item] = have - take
        moved[item] = moved.get(item, 0) + take
        left -= take
        if left <= 0:
            return moved
    for n in village.npcs:                       # then off the people's shelves
        if left <= 0:
            break
        if not n.alive:
            continue
        for item in FOOD:
            if left <= 0:
                break
            have = n.stock.get(item, 0)
            if have <= 0:
                continue
            take = min(have, left)
            n.stock[item] = have - take
            moved[item] = moved.get(item, 0) + take
            left -= take
    return moved


def tithe_food(village, day: int) -> dict:
    """A share of the village's net gain in food for the day, to the crown.

    Coin was never the only thing worth taxing: a harvest is the thing a
    capital actually lives on, and it is what feeds the armies it raises.
    """
    if getattr(village, "is_capital", False):
        return {}
    if getattr(village, "_crown_food_day", -1) == day:
        return {}
    village._crown_food_day = day
    now = village_food(village)
    prev = getattr(village, "_crown_food_base", None)
    village._crown_food_base = now
    if prev is None or now <= prev:
        return {}
    due = int((now - prev) * CROWN_FOOD_SHARE)
    if due <= 0:
        return {}
    cap = village.capital()
    if cap is None or cap is village:
        return {}
    moved = take_food(village, due)
    for item, qty in moved.items():
        cap.ledger_goods[item] = cap.ledger_goods.get(item, 0) + qty
    if moved:
        _note("day %4d  %-16s CROWN-FOOD %d to %s"
              % (day, village.name, sum(moved.values()), cap.name))
    return moved


def pay_crown(village, day: int) -> int:
    """The King's salary, out of the capital's own purse -- which is the
    village's takings plus every village's half of its profit."""
    king = getattr(village, "king", None)
    if king is None or not king.alive:
        return 0
    if getattr(village, "_crown_pay_day", -1) == day:
        return 0
    village._crown_pay_day = day
    paid = int(min(KING_WAGE, max(0, village.ledger_coins - CROWN_BUFFER)))
    if paid <= 0:
        return 0
    king.coins += paid
    king.book_in = getattr(king, "book_in", 0.0) + paid
    flow(village, 'pay_crown', -(paid))
    village.ledger_coins -= paid
    return paid


def loot_body(killer, victim) -> dict:
    """Everything the dead man was carrying changes hands.

    A man who kills another takes what he had -- his coin stays with him as
    coin, his goods, and above all his GUN and his ROUNDS. A conscript who
    drops a rifleman picks the rifle up and becomes one, with the cartridges
    that are still in it.
    """
    if killer is None or victim is None or killer is victim:
        return {}
    # A soldier's kit is carried by the man, not the body on the field.
    # A SOLDIER HAS A home_npc -- the villager he stands for. A PLAIN VILLAGER
    # DOES NOT, and this reached straight for the attribute: any shot villager
    # with loot to drop brought the whole game down with AttributeError, from
    # the bullet path in main._loot. getattr, with the victim as the fallback,
    # is what the caller already does for the killer two lines up.
    vsrc = getattr(victim, "home_npc", None) or victim
    bag = dict(getattr(vsrc, "stock", {}) or {})
    grades = dict(getattr(vsrc, "grade", {}) or {})
    if not bag:
        return {}
    # who is doing the taking? A soldier keeps his things with the man himself
    # AND THE SAME ON THE KILLER'S SIDE. A soldier keeps his things with the
    # man he stands for; a plain villager IS the man. Reaching for the
    # attribute took the game down with AttributeError from the bullet path,
    # whichever end of it was a civilian.
    holder = getattr(killer, "home_npc", None) or killer
    if not hasattr(holder, "stock"):
        return bag                          # the player: the caller decides
    for item, qty in bag.items():
        if qty <= 0:
            continue
        holder.stock[item] = int(holder.stock.get(item, 0)) + int(qty)
        if item in grades:
            holder.grade[item] = quality.merge(
                holder.grade.get(item, grades[item]), 0, grades[item],
                int(qty))
    vsrc.stock.clear()
    vsrc.grade.clear()
    # AND IF HE WAS A RIFLEMAN, THE KILLER IS ONE NOW.
    if (killer.kind == "soldier"
            and getattr(killer, "melee", False)
            and victim.kind == "soldier"
            and not getattr(victim, "melee", True)):
        rounds = int(victim.ammo)
        if rounds > 0 or bag.get("rifle", 0) > 0 or bag.get("shotgun", 0) > 0:
            killer.melee = False
            killer.weapon = "rifle"
            killer.preferred = 300.0
            killer.speed = 122.0
            killer.base_speed = 122.0
            killer.ammo = int(killer.ammo) + rounds
            victim.ammo = 0
    return {}


def _buy_off_people(village, item: str, want: int) -> int:
    """Buy up to ``want`` of an item off the village's own people.

    AT THE CROWN'S OWN PRICE. CROWN_ARMS_MULT has been declared since the
    beginning -- "what the crown bids over the going rate" -- and was never
    used by anything. The crown bid exactly the market price, so no smith and
    no trader ever had a reason to see it as the buyer worth carrying guns to.
    A premium nobody pays is not a premium.
    """
    got = 0
    # No multiplier here: the premium IS the base price now (see
    # ITEM_VALUE), so applying it again would charge the crown twice.
    price = village.prices.get(item, ITEM_VALUE.get(item, 4))
    for n in village.npcs:
        if got >= want:
            break
        have = int(n.stock.get(item, 0))
        if have <= 0:
            continue
        afford = int(max(0.0, village.ledger_coins - CROWN_BUFFER)
                     // max(0.01, price))
        take = min(have, want - got, afford)
        if take <= 0:
            break
        cost = int(round(price * take))
        n.stock[item] = have - take
        n.coins += cost
        n.book_in = n.book_in + cost
        flow(village, '_buy_off_people', -(cost))
        village.ledger_coins -= cost
        village.ledger_goods[item] = village.ledger_goods.get(item, 0) + take
        got += take
    return got


def pay_garrison(village, day: int) -> int:
    """The standing army is paid every day, out of the crown.

    A soldier never goes back to being an idler: he settles in a town he took,
    or he comes home to the capital and stays a soldier on the payroll. His
    wage does not stop because the war did.
    """
    if not getattr(village, "is_capital", False):
        return 0
    if getattr(village, "_standing_day", -1) == day:
        return 0
    village._standing_day = day
    paid = 0
    for n in village.npcs:
        if not n.alive or n.job != "soldier":
            continue
        wage = PAY_RIFLE if n.ranged else PAY_MELEE
        if village.ledger_coins - CROWN_BUFFER < wage:
            break
        n.coins += wage
        n.book_in = n.book_in + wage
        flow(village, 'pay_garrison', -(wage))
        village.ledger_coins -= wage
        paid += wage
    return paid


def crown_arms_order(village, day: int) -> int:
    """The crown arms itself, off its own people, at its own high price.

    It buys WHOLE KITS -- a rifle and the thirty rounds that make it a rifle
    -- because an unloaded gun is a club, and a nation that spends its whole
    purse on five guns and no ammunition has armed nobody. Rounds for the guns
    it already holds come first; then one complete man at a time, for as long
    as there is money for the war.
    """
    if not getattr(village, "is_capital", False):
        return 0
    if getattr(village, "_arms_day", -1) == day:
        return 0
    village._arms_day = day
    # PUT THE PREMIUM IN THE PRICE LIST, not just at the counter. A crown that
    # only pays over the odds to men who happen to be standing in its square
    # is invisible to every trader planning a route -- and guns have to be
    # CARRIED to a capital, nobody forges them there by accident. Raising the
    # capital's own price for arms is what makes the trade run profitable to
    # walk, and the route planner reads exactly this price list.
    village.prices["rifle"] = ITEM_VALUE["rifle"]
    village.prices["ammo"] = ITEM_VALUE["ammo"]
    pr = village.prices.get("rifle", ITEM_VALUE["rifle"])
    pa = village.prices.get("ammo", ITEM_VALUE["ammo"])
    kit = pr + AMMO_PER_RIFLE * pa
    target = max(0, (getattr(village, "capacity", 0) + len(village.npcs)) // 3)
    got = _buy_off_people(village, "ammo", max(
        0, int(village.ledger_goods.get("rifle", 0)) * AMMO_PER_RIFLE
        - int(village.ledger_goods.get("ammo", 0))))
    while int(village.ledger_goods.get("rifle", 0)) < target:
        if village.ledger_coins - CROWN_BUFFER < kit:
            break
        if _buy_off_people(village, "rifle", 1) != 1:
            break
        if _buy_off_people(village, "ammo", AMMO_PER_RIFLE) != AMMO_PER_RIFLE:
            break                     # cannot load it: leave it, unfieldable
        got += 1 + AMMO_PER_RIFLE
    return got


# -- ELECTIONS --------------------------------------------------------------
# SOCIAL MOBILITY, MADE MECHANICAL. A mayor was handed the chair at world
# creation and held it for ever; there was no way up and no way out. Now the
# village CHOOSES, every ELECTION_DAYS, and the choice is made of the two
# things that decide such things everywhere: who a man knows, and who is
# willing to pay him.
ELECTION_DAYS = 15          # the village chooses its mayor this often
ELECTION_BRIBE = 50         # coin a candidate pays a voter for his vote
ELECTION_KEEP = 50          # ...and he stops buying before he is left with less
KING_ELECTION_DAYS = 50     # the throne changes hands this rarely

# THE MAYOR'S ROUND. Ten days of business at court, ten days of business at
# home, and the road between them -- which is why it is "roughly" ten: the
# journey is real, he WALKS it, and the days it costs are days he is neither
# here nor there. That is what travelling is.


OPINION_MAX = 100.0          # a man can only think so well of another
MAYOR_DAYS_AT_COURT = 10     # and the same again at home; see Village.court_day
TOURNAMENT_FLOOR = 50        # a bout at court STOPS here: nobody is butchered
                             # at a coronation. Was 35; 50 makes a bout a
                             # contest of a few honest blows rather than a
                             # grind, and it is the threshold the winner is
                             # declared on.


def opinion_of(npc, other_id) -> dict:
    """THE OPINIONS A MAN HOLDS, made on first use.

    ``other_id`` is deliberately UNTYPED. A man's id is a STRING in this world
    -- the save records key on it -- and annotating it ``int`` made Cython
    enforce that type at the boundary, so the first trade raised
    "Argument 'other_id' has incorrect type (expected int, got str)". A wrong
    annotation in a compiled module is not a comment; it is a contract.

    A dict per man rather than a matrix for the world. Only men who have
    actually dealt with each other ever appear in it, so a village that trades
    among itself costs a few dozen numbers and a stranger costs nothing at all
    until he does business.
    """
    op = getattr(npc, "opinion", None)
    if op is None:
        op = {}
        npc.opinion = op
    return op


def grow_opinion(a, b, amount: float = 1.0) -> None:
    """TWO MEN WHO HAVE DEALT WITH EACH OTHER THINK BETTER OF EACH OTHER.

    +1 a trade, EACH WAY -- the buyer's opinion of the seller and the seller's
    of the buyer -- and never past OPINION_MAX, because a man can be known
    perfectly and no further. This is the only part of a relationship that is
    REMEMBERED rather than read off a man's circumstances; see regard().
    """
    if a is None or b is None or a is b:
        return
    for me, other in ((a, b), (b, a)):
        oid = getattr(other, "id", None)
        if oid is None:
            continue
        op = opinion_of(me, oid)
        cur = float(op.get(oid, 0.0))
        if cur < OPINION_MAX:
            op[oid] = min(OPINION_MAX, cur + amount)


def regard(a, b) -> float:
    """HOW MUCH ONE MAN THINKS OF ANOTHER.

    NOT STORED, AND THAT MATTERS. A village of thirty would need nine hundred
    numbers and a nation of a thousand a million, most of them zero. It is read
    off the things that actually make men know one another -- the same roof,
    the same bench, the same trade, the same plot, and the evening walk -- so
    it costs nothing to keep and can never go stale when a man moves house or
    changes his work.
    """
    if a is b:
        return 999.0                       # a man is always his own first choice
    score = 0.0
    ah, bh = getattr(a, "home_house", None), getattr(b, "home_house", None)
    if ah is not None and ah is bh:
        score += 3.0                       # under the same roof
    aw, bw = getattr(a, "workplace", None), getattr(b, "workplace", None)
    if aw is not None and aw is bw:
        score += 2.0                       # at the same bench
    if getattr(a, "job", None) and a.job == getattr(b, "job", None):
        score += 1.0                       # the same trade
    if getattr(a, "farm_plot", None) is not None             and a.farm_plot == getattr(b, "farm_plot", None):
        score += 1.0                       # side by side in the field
    if getattr(a, "bond_partner", None) is b:
        score += 10.0                      # the evening walk
    if getattr(a, "is_king", False) or getattr(b, "is_king", False):
        score += 0.5                       # a king is known by everybody, a little
    op = getattr(a, "opinion", None)
    if op:
        # ...AND WHAT THEY HAVE MADE OF EACH OTHER OVER THE YEARS. +1 a trade,
        # remembered. It is what makes standing movable: a man who deals
        # honestly with the whole town for a season is known for it, and the
        # chair can change hands without a coin being spent.
        score += float(op.get(getattr(b, "id", None), 0.0))
    return min(OPINION_MAX, score)


def election_tomorrow(village, day: int) -> bool:
    """Does this town vote tomorrow? The calendar is Village.update's."""
    return (day + 1 > 0 and (day + 1 - village.code) % ELECTION_DAYS == 0)


def vote_buyable(voter, day: int) -> bool:
    """A VOTE MAY BE SOLD ONCE. Once a man has taken coin for it the matter is
    settled -- he cannot sell the same vote to two purses, which is the only
    thing that makes buying an election cost anything at all."""
    return int(getattr(voter, "vote_sold", -1)) != int(day)


def sell_vote(voter, buyer, day: int) -> bool:
    """ONE VOTE, ONE SALE, ONE PRICE.

    Every bribe in the world goes through here -- a mayor's, a rich man's and
    the player's alike -- so the going rate is the going rate and nobody can be
    bought twice. Returns False if the vote is gone, the buyer is the voter, or
    the buyer cannot afford it without being left short.
    """
    if voter is buyer or not getattr(voter, "alive", False):
        return False
    # A CANDIDATE IS NOT FOR SALE. He is standing, not voting -- and the rule
    # belongs HERE, in the one function every purse in the world pays through,
    # not in the loop that happens to call it. It was in hold_election only, so
    # the player's own path could buy a mayor's vote while the town's could not.
    if getattr(voter, "is_mayor", False) or getattr(voter, "is_king", False):
        return False
    if not vote_buyable(voter, day):
        return False
    if buyer.coins - ELECTION_BRIBE < ELECTION_KEEP:
        return False
    buyer.coins -= ELECTION_BRIBE
    voter.coins += ELECTION_BRIBE
    voter.vote_sold = int(day)
    voter.vote_for = getattr(buyer, "id", None)
    return True


def election_candidates(village, player=None) -> list:
    """WHO MAY STAND: the player, and the three richest men in the town.

    NOT the sitting mayor. He holds the chair, he does not own it -- if he
    wants another term he must be one of the three richest men and take his
    chances with everybody else. Standing is what you get for being rich, and
    keeping it is what you get for being better at it than the other three.

    THE PLAYER STANDS BY BEING THERE. He does not apply, register or declare:
    he is a man in the square with a purse, which is the whole qualification,
    and he is in the field for as long as he is inside the fence.
    """
    out: list = []
    seen: set = set()
    if player is not None:
        near = ((player.x - village.x) ** 2
                + (player.y - village.y) ** 2) ** 0.5
        if near <= village.radius + 140.0:
            out.append(player)
            seen.add(id(player))
    rich = sorted((n for n in village.npcs
                   if getattr(n, "alive", False) and id(n) not in seen
                   and not getattr(n, "is_king", False)
                   and not getattr(n, "is_commander", False)),
                  key=lambda n: n.coins, reverse=True)
    return out + rich[:3]


def hold_election(village, day: int, player=None) -> Any:
    """THE VILLAGE CHOOSES, AND THE CROWN MERELY PAYS HIM.

    Every voter picks whoever he knows best -- see regard. A candidate may then
    BRIBES him for that vote at ELECTION_BRIBE, and a bribe overrides the vote,
    because that is what a bribe is. The richest candidate bids first, so the
    deepest purse wins the votes it wants; but no man beggars himself for a
    chair, and a candidate stops buying before he is left with less than
    ELECTION_KEEP.
    """
    if village.is_capital or getattr(village, "_vote_day", -1) == day:
        return None
    village._vote_day = day
    voters = [n for n in village.npcs
              if getattr(n, "alive", False)
              and not getattr(n, "is_king", False)
              and not getattr(n, "is_commander", False)]
    if len(voters) < 3:
        return None
    cands = election_candidates(village, player)
    if not cands:
        return None
    # The purse decides the ORDER of bidding, not the outcome: richest first.
    # A MAN WITHOUT A PURSE CANNOT BID, AND A PLAYER'S COIN IS IN HIS PACK.
    # He buys his votes in the square with his own hands (see main.buy_vote),
    # not through this loop -- so he takes no part in the bidding, but his
    # bought votes count like any others.
    buyers = sorted((n for n in cands if getattr(n, "coins", None) is not None),
                    key=lambda n: n.coins, reverse=True)
    tally: dict = {id(c): 0 for c in cands}
    spent: dict = {id(c): 0 for c in cands}
    by_id = {id(c): c for c in cands}
    # WHAT IT TAKES TO WIN. A majority of the votes cast; no man buys more
    # than that, because a vote he does not need is coin thrown away.
    need = len(voters) // 2 + 1
    for voter in voters:
        # 1. HIS OWN CHOICE: whoever he knows best.
        pick = max(cands, key=lambda c: regard(voter, c))
        # 2. THE PURSE. A CANDIDATE IS NOT A CUSTOMER -- nobody buys a rival's
        # vote, and nobody sells his own (a man in the field does not vote for
        # sale). The vote goes to the first candidate who can afford it AND
        # still wants it: the fastest purse wins the race, and the vote is then
        # GONE (see sell_vote), so no other purse can take it.
        if voter in cands:
            # A CANDIDATE VOTES FOR HIMSELF. Always -- regard(a, a) is the top
            # of the scale, so it is what he would choose anyway, and it means
            # no purse can talk him out of his own name.
            tally[id(voter)] = tally.get(id(voter), 0) + 1
            continue
        for buyer in buyers:
            if buyer is voter:
                break
            if tally[id(buyer)] >= need:
                continue                   # he has what it takes to win
            if sell_vote(voter, buyer, day):
                spent[id(buyer)] += ELECTION_BRIBE
                pick = buyer
                break
        tally[id(pick)] = tally.get(id(pick), 0) + 1
    win = max(cands, key=lambda c: (tally[id(c)],
                                    getattr(c, "coins", 0)))
    if not hasattr(win, "coins"):
        # THE PLAYER HAS WON THE CHAIR. He is not an NPC: pay_mayor reads a
        # villager's purse and books, so the town is left with no NPC mayor at
        # all (and the crown pays him nothing) -- the office is his, and its
        # income is whatever the town's trade brings him.
        old = getattr(village, "mayor", None)
        if old is not None and old is not win and getattr(old, "alive", True):
            old.is_mayor = False
            old.role = None
            old.plaza = None
            if getattr(old, "job", None) == "mayor":
                old.job = None
                village.free_post(old)
        village.mayor = None
        win.is_mayor = True
        win.job = "mayor"
        win.settled_at = village
        win.village = village
        if getattr(village, "nation", None) is not None:
            win.nation = village.nation
        village.mayor_is_player = True
        _note("day %.2f  ELECTION  THE PLAYER takes %s (%d votes)"
              % (day, village.name, tally.get(id(win), 0)))
        return win
    village.mayor_is_player = False
    install_mayor(village, win)
    _note("day %.2f  ELECTION  %-16s mayor (votes %d of %d, spent %d)"
          % (day, win.name, tally[id(win)], len(voters), spent[id(win)]))
    return win


def install_mayor(village, npc) -> None:
    """Put the chain on him, and take it off the man who had it.

    The old mayor is not exiled -- he is a villager again, and the town will
    hand him a trade like anybody else (his post was never his; the chair was).
    """
    old = getattr(village, "mayor", None)
    if old is not None and old is not npc and getattr(old, "alive", True):
        old.is_mayor = False
        old.role = None
        old.plaza = None
        if getattr(old, "job", None) == "mayor":
            old.job = None
            village.free_post(old)
    npc.is_mayor = True
    npc.role = "Mayor"
    npc.job = "mayor"
    npc.plaza = (village.x, village.y)
    village.mayor = npc


def pay_mayor(village, day: int) -> int:
    """The mayor's wage, out of the nation's treasury.

    He is paid against the second-richest man in the village -- two to three
    times what the best-off commoner earned today -- so the mayor is always
    visibly the richest man in town, and never *only just*: the gap is the
    point. The crown keeps him in check, though: his wage is capped below
    half the King's, so the King is always two to three times the mayor and
    the ladder has a top.
    """
    mayor = getattr(village, "mayor", None)
    if mayor is None or not mayor.alive or village.is_capital:
        return 0
    if getattr(village, "_mayor_day", -1) == day:
        return 0
    village._mayor_day = day
    cap = village.capital()
    if cap is None or cap is village:
        return 0
    others = [n for n in village.npcs
              if n.alive and n is not mayor and not n.is_king]
    if not others:
        return 0
    others.sort(key=lambda n: n.coins, reverse=True)   # the local elite
    second = others[0]
    bench = max(float(getattr(second, "book_in", 0.0)), MAYOR_FLOOR,
                float(second.coins) / 20.0)            # a day's worth of his wealth
    want = int(bench * random.uniform(*MAYOR_SHARE))
    want = min(want, KING_WAGE // 2)                   # the King stays 2-3x above
    # ------------------------------------------------------------------
    # THE TOWN PAYS ITS OWN MAYOR, OUT OF THE TOWN'S OWN MONEY.
    #
    # This paid him out of the CAPITAL's ledger (and skipped the buffer check
    # by exactly the amount it felt like), so one crown owed its whole nation's
    # mayors at once: measured, the crown took in 127 coin in a day and paid
    # out 1,600 in mayoral wages, and because CROWN_BUFFER holds 1,500 back,
    # the two together were a LID. The crown filled to 1,500, was emptied to
    # 1,500 by mayors, and never once reached the 4,000 coin that WAR_CHEST
    # demands -- which is why no army ever marched in any run tonight.
    #
    # The wage itself was also the wrong shape: 2-3x the SECOND-RICHEST MAN'S
    # DAILY TURNOVER, so one trader having a good day raised the mayor's pay
    # whether or not the town had earned anything. A town pays what it can: a
    # rich town keeps an expensive mayor, a poor town an inexpensive one, and
    # the crown is left to the King, the army and the war it wants to fight.
    paid = int(min(want, max(0, village.ledger_coins - MAYOR_FLOOR)))
    if paid <= 0:
        return 0
    mayor.coins += paid
    mayor.book_in = getattr(mayor, "book_in", 0.0) + paid
    flow(village, 'pay_mayor', -(paid))
    village.ledger_coins -= paid
    return paid


def tax_day(village, day: int) -> None:
    flow_report(day)
    """Settle the day's books: tax the winners, carry the losers. Once a day,
    not once a tick -- pay_wages guards itself and this must too."""
    if getattr(village, "_tax_day", -1) == day:
        return
    village._tax_day = day
    liv = [n for n in village.npcs if n.alive]
    net = {}
    for n in liv:
        net[n] = n.book_in - n.book_out
    pool = 0
    taxed = 0
    for n in liv:
        if net[n] <= 0.0:
            continue
        if n.is_king:
            continue                  # the crown does not tax itself
        due = int(tax_due(net[n]))
        paid = int(min(due, n.coins))
        if paid <= 0:
            continue
        n.coins -= paid
        flow(village, 'tax_day', (paid))
        village.ledger_coins += paid
        pool += paid
        taxed += 1
    give = int(pool * SUBSIDY_SHARE)
    helped = 0
    for n in sorted((x for x in liv if net[x] < 0.0), key=lambda x: net[x]):
        if give <= 0:
            break
        need = int(min(-net[n], give))
        if need <= 0:
            continue
        n.coins += need
        flow(village, 'tax_day', -(need))
        village.ledger_coins -= need
        give -= need
        helped += 1
    if pool or helped:
        given = int(pool * SUBSIDY_SHARE) - max(0, give)
        _note("day %4d  %-16s TAX %6d from %2d hands, %6d to %2d of the worst off "
              "(ledger keeps %d)"
              % (day, village.name, pool, taxed, given, helped, pool - given))
    for n in liv:                          # a fresh book for tomorrow
        n.book_in = 0.0
        n.book_out = 0.0


def pay_wages(village, day: int) -> None:
    """A day's wage for the watch -- and for the woodsmen the town employs."""
    if day == village.wage_day:
        return
    village.wage_day = day
    for npc in village.npcs:
        if not npc.alive:
            continue
        if is_watch(npc):
            wage = WAGE
        elif getattr(npc, "job", None) == "logger":
            wage = LOGGER_WAGE          # the woods are the town's payroll now
        elif getattr(npc, "job", None) == "smith":
            wage = SMITH_WAGE           # and so is the forge
        elif getattr(npc, "farm_plot", None) is not None:
            wage = LOGGER_WAGE          # A FARMER IS AN EMPLOYEE TOO. He reaps
                                        # for the town and keeps a ration of
                                        # it; without the wage he could never
                                        # buy the shovel he wears out.
        elif getattr(getattr(npc, "workplace", None), "kind", None) == "mine":
            wage = LOGGER_WAGE          # and the pit is the town's work as well
        else:
            continue
        paid = min(wage, village.ledger_coins)
        npc.coins += paid
        npc.book_in = npc.book_in + paid   # wages are income
        flow(village, 'pay_wages', -(paid))
        village.ledger_coins -= paid


def dole(village, npc) -> bool:
    """Starving, with an empty larder and no coin to buy with: the village
    granary feeds you for nothing. Nobody dies while there is bread in the
    store -- that is the floor under the whole economy."""
    if npc.hunger < DOLE_AT:
        return False
    for item in FOOD:
        if village.ledger_goods.get(item, 0) > 0:
            store_take(village, item, 1)      # the dole, out of the common store
            npc.hunger = max(0.0, npc.hunger - EAT_BY)
            _note("day %.2f  %-16s %-8s fed by the granary (hunger %.0f, coin %d)"
                  % (getattr(village, "_day", 0.0), npc.name, npc.job or "villager",
                     npc.hunger, npc.coins))
            return True
    return False


def needs(npc, dt: float) -> bool:
    """HIS BODY, AND NOTHING ELSE. Returns False if he died of it.

    Hunger, craving, healing, eating out of his OWN pack, a smoke, a drink,
    and starvation. No town is needed anywhere in here -- a man on the road
    has exactly the same hunger as a man at home -- which is why it is his and
    not the village's. The granary and the bank are SERVICES he calls from his
    own tick, not things done to him in a loop over the population.

    READ THE MAN ONCE. Every npc.hunger below is a dictionary lookup, and this
    runs twenty times a second for every soul in the world -- so his body is
    read into locals, worked on, and written back at the end. Same decisions,
    same numbers, fewer visits to the same three fields.
    """
    hunger = npc.hunger
    house = npc.home_house
    if house is not None and house.warmth <= 0.0:
        hunger = hunger + HUNGER_RATE * COLD_HUNGER * dt
    else:
        hunger = hunger + HUNGER_RATE * dt
    if hunger > 130.0:
        hunger = 130.0
    yearning = npc.yearning + YEARING_RATE * npc.addiction * dt
    if yearning > 1.0:
        yearning = 1.0
    stock = npc.stock
    if (npc.asleep or npc.in_interior) and hunger < HEAL_WELL_FED:
        health = npc.health
        top = npc.max_health
        if health < top:
            health = health + HEAL_RATE * dt
            npc.health = top if health > top else health
    if hunger >= EAT_AT:
        for item in FOOD:
            if stock.get(item, 0) > 0:
                stock[item] -= 1
                hunger = hunger - EAT_BY
                if hunger < 0.0:
                    hunger = 0.0
                break
        else:
            if npc.trade_state != "none":
                if wildcrop.forage(wildcrop._WORLD, npc.x, npc.y):
                    hunger = hunger - FORAGE_MEAL
                    if hunger < 0.0:
                        hunger = 0.0
    if yearning >= YEARING_ACT:
        want = npc.wants_product
        if want and stock.get(want, 0) > 0:
            stock[want] -= 1
            yearning = 0.0
            npc.use_fx = (want, USE_FX_SECONDS)
        else:
            drink = npc.wants_drink
            if stock.get(drink, 0) > 0:
                stock[drink] -= 1
                yearning = 0.0
                npc.use_fx = (drink, USE_FX_SECONDS)
    fx = npc.use_fx
    if fx is not None:
        item, left = fx
        left -= dt
        npc.use_fx = None if left <= 0.0 else (item, left)
    npc.hunger = hunger
    npc.yearning = yearning
    if hunger >= STARVE_AT:
        npc.alive = False
        npc.health = 0
        _note("STARVED  %-16s hunger %.0f  coin %d  food %d"
              % (npc.name, hunger, npc.coins, food_of(npc)))
        try:
            import deaths
            deaths.record(npc, "STARVED")
        except Exception:
            pass
        return False
    return True


def tick(village, npc, dt: float) -> bool:
    """Advance needs, eat, smoke, burn a log. Returns False if they died.

    Kept as the old entry point: his needs, then the services the town owes
    him. A man's own tick calls needs() and the services directly; this remains
    for any caller that still holds a village.
    """
    if not needs(npc, dt):
        return False
    if village is None:
        return True
    if npc.hunger >= DOLE_AT:                   # the granary, for nothing
        dole(village, npc)
    npc.loan_clock = npc.loan_clock + dt
    if npc.loan_clock >= 1.0:
        npc.loan_clock = 0.0
        place_orders(village, npc)
        tool_loan(village, npc)
        forge_loan(village, npc)
        service_loan(village, npc)
    return True


