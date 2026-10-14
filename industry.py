"""Village industry: the iron mine and the smithy.

A mine is an unlimited seam of iron; the smithy turns it into tools. The forge
must out-produce the farm: nine farmers wear out about 1.1 shovels a day, so a
shelf of two and two tools a day left the village permanently short -- the bare
farmers could not till, their fields reverted to grass, and the farm died by
about the twelfth day. The smith now keeps a stock and works fast enough to
cover the wear with room to spare.
"""

from __future__ import annotations

import random

import pygame

import economy
import quality

DAY_LENGTH = 600.0
WORK_FRACTION = 0.25       # share of the day folk spend at work
MINER_PAY = 0.2            # coin the village pays per iron dug. At the
                           # ~88 iron a miner actually gets out of the rock
                           # in a day that is about seventeen coin -- a
                           # living, between the ten a day's work is worth
                           # and the twenty a mayor is floored at. He is a
                           # hired hand, not a man with iron to sell.
IRON_PER_DAY = 100.0       # a miner's output. It was 12.0, and a gun
                           # costs GUN_IRON=100 + GUN_IRON_KEEP=24, so
                           # no village ledger ever climbed past the 24
                           # it was keeping back: ten days of a whole
                           # village's iron for ONE gun. Zero guns were
                           # ever made anywhere, in any run.
TOOLS_PER_DAY = 5.0        # a smith's output, if he has the iron
MINES_MIN = 2
MINES_MAX = 3
CRAFT_PER_DAY = 60.0       # a laboratory output rate, if it has the leaf for it
FORGE_SHELF = 10           # tools the smith keeps on the shelf -- enough to
                           # outlast the once-a-day market, or he can never stock up
# (A dead module-level TOOL_KINDS = economy.TOOLS lived here. Nothing read
# it, and it made industry import economy at load, which closed the circle
# village -> industry -> economy -> village once economy began cimporting
# the man to compile his body. Removed.)

ROCK = (108, 104, 99)
ROCK_D = (70, 67, 63)
ROCK_L = (148, 144, 138)
TIMBER = (98, 70, 42)
TIMBER_D = (58, 40, 24)
MOUTH = (16, 15, 17)
STONE = (132, 128, 122)
STONE_D = (76, 72, 68)
ROOF = (86, 62, 58)
ROOF_L = (120, 88, 80)
FORGE = (232, 138, 48)


def daily_rate(per_day: float) -> float:
    """The per-second rate that yields ``per_day`` over one working day."""
    return per_day / (DAY_LENGTH * WORK_FRACTION)


def forge_kind(village, now: float) -> str:
    """What the forge turns out: whatever the ORDER BOOK is asking for.

    The smith works to order -- a man books his next tool at 40% wear -- so the
    forge makes what the village is short of instead of guessing and hoping the
    right man walks past before the shelf fills up."""
    book = []
    for n in village.npcs:
        if getattr(n, "job", None) == "smith":
            book = getattr(n, "tool_orders", ())
            break
    if book:
        tally = {}
        for _who, want in book:
            tally[want] = tally.get(want, 0) + 1
        return max(tally, key=lambda k: tally[k])
    return forge_by_stock(village, now)


def forge_by_stock(village, now: float) -> str:
    # Forge for DEMAND: if more woodsmen are standing idle without an axe than
    # farmers are without a shovel, the forge turns out axes.
    unarmed_axe = sum(1 for n in village.npcs if n.alive
                      and getattr(n, "job", None) == "logger"
                      and n.stock.get("axe", 0) <= 0 and n.tool_uses <= 0)
    unarmed_shovel = sum(1 for n in village.npcs if n.alive
                         and getattr(n, "farm_plot", None) is not None
                         and n.stock.get("shovel", 0) <= 0 and n.tool_uses <= 0)
    if unarmed_axe or unarmed_shovel:
        return "axe" if unarmed_axe >= unarmed_shovel else "shovel"
    if any(getattr(n, "job", None) == "logger" for n in village.npcs):
        return "axe" if int(now / DAY_LENGTH) % 2 == 0 else "shovel"
    return "shovel"


GUN_IRON = 100             # a gun: a hundredweight of iron...
GUN_WOOD = 50              # ...and fifty of timber. It was 500, which at
                           # 4 coin a log is 2,000 coin of timber for a gun
                           # worth 1,600 -- the gun cost MORE than its own
                           # price, so no village could sell one to the
                           # crown without losing money on it.
GUN_PAY = 10               # the village pays the smith this much a gun
AMMO_IRON = 1
AMMO_WOOD = 1
AMMO_PAY = 1
GUNS_PER_DAY = 20.0        # iron is the true limit, not the clock
AMMO_PER_DAY = 40.0
GUN_IRON_KEEP = 24         # iron the ledger keeps back from the gunworks
GUN_COIN_KEEP = 300        # and coin it will not spend on material


def buy_material(village, item: str, want: int) -> int:
    """The ledger buys material off the village at the going rate.

    This is the whole point of the gunworks: a village drowning in timber
    suddenly has a customer. The ledger pays the woodcutter for his logs, the
    miner for his iron, and the smith for the work -- and sells the gun.
    """
    got = 0
    price = village.prices.get(item, economy.ITEM_VALUE.get(item, 4))
    for n in village.npcs:
        if got >= want:
            break
        if not getattr(n, "alive", False):
            continue
        have = int(n.stock.get(item, 0))
        if have <= 0:
            continue
        afford = int((village.ledger_coins - GUN_COIN_KEEP) // max(0.01, price))
        take = min(have, want - got, max(0, afford))
        if take <= 0:
            break
        cost = int(round(price * take))
        n.stock[item] = have - take
        n.coins += cost
        n.book_in = getattr(n, "book_in", 0.0) + cost
        village.ledger_coins -= cost
        # ...AND INTO THE STORE. Without this the ledger paid for the timber,
        # handed it to nobody, found the shelf still empty and bought it again
        # every tick until it was skint -- one gun, then never another.
        village.ledger_goods[item] = village.ledger_goods.get(item, 0) + take
        got += take
    return got


def gunworks(npc, dt: float) -> bool:
    """THE GUNWORKS. The village finds the material, the smith finds the work.

    A hundred iron and five hundred wood make a gun; one and one make a
    cartridge; the ledger pays ten coin a gun and one a round. A village with
    a mine and a forest can arm itself -- and the woods get a buyer at last.
    """
    v = npc.village
    if v is None:
        return False
    store = v.ledger_goods
    fast = 1.0 + npc.skills.axe            # a better hand works quicker
    if store.get("iron", 0) < GUN_IRON + GUN_IRON_KEEP:
        buy_material(v, "iron", GUN_IRON + GUN_IRON_KEEP - store.get("iron", 0))
    if store.get("wood", 0) < GUN_WOOD:
        buy_material(v, "wood", GUN_WOOD - store.get("wood", 0))
    npc.gun_acc = getattr(npc, "gun_acc", 0.0) + daily_rate(GUNS_PER_DAY * fast) * dt
    # A GUN IS FORGED AS A KIT. "An unloaded gun is a club" -- the crown's own
    # words in crown_arms_order -- and a forge that turns out rifles without
    # their rounds is turning out clubs. So the gun and its thirty cartridges
    # are made in the same breath, out of the same bench, and for the same
    # customer. They stay TWO items: a rifle is a rifle and a round is a
    # round, and a man may own one without the other. What changes is only
    # that they are made together, so there is never a rifle in the world
    # that cannot be loaded.
    kit_iron = GUN_IRON + AMMO_IRON * economy.AMMO_PER_RIFLE
    kit_wood = GUN_WOOD + AMMO_WOOD * economy.AMMO_PER_RIFLE
    if (npc.gun_acc >= 1.0
            and store.get("iron", 0) >= kit_iron + GUN_IRON_KEEP
            and store.get("wood", 0) >= kit_wood
            and v.ledger_coins >= GUN_PAY + GUN_COIN_KEEP):
        npc.gun_acc -= 1.0
        store["iron"] -= kit_iron
        store["wood"] -= kit_wood
        v.ledger_coins -= GUN_PAY
        npc.coins += GUN_PAY
        npc.book_in = getattr(npc, "book_in", 0.0) + GUN_PAY
        kind = "rifle" if npc.rng.random() < 0.72 else "shotgun"
        if getattr(v, "is_capital", False):
            # THE CROWN'S OWN FORGE DELIVERS TO THE CROWN. The ledger bought
            # the iron, the ledger bought the timber, the ledger paid the
            # wage -- so the ledger already owns the gun. It is not sold back
            # to the crown by the man the crown just hired. He is paid his
            # ten coin for the work; the gun goes on the crown's own shelf.
            v.ledger_goods[kind] = int(v.ledger_goods.get(kind, 0)) + 1
            v.ledger_goods["ammo"] = (int(v.ledger_goods.get("ammo", 0))
                                      + economy.AMMO_PER_RIFLE)
        else:
            npc.stock[kind] = npc.stock.get(kind, 0) + 1
            npc.stock["ammo"] = npc.stock.get("ammo", 0) + economy.AMMO_PER_RIFLE
        npc.skills.gain_farming(0.15)
        return True
    # CARTRIDGES, UP TO THIRTY A GUN AND NOT ONE MORE. The bench ran the
    # cartridge clock on its own, so a forge piled up hundreds of rounds for
    # rifles nobody had yet -- and the crown's daily loop bought every one of
    # them, draining the treasury on ammunition for guns that did not exist.
    # Rounds are made to MATCH the guns they belong to: thirty apiece, counting
    # the guns on the smith's own bench AND the ones already on the crown's
    # shelf. A gun with no rounds is a club; rounds with no gun are just coin
    # set on fire.
    guns_here = (int(store.get("rifle", 0)) + int(store.get("shotgun", 0))
                 + int(npc.stock.get("rifle", 0)) + int(npc.stock.get("shotgun", 0)))
    ammo_cap = economy.AMMO_PER_RIFLE * guns_here
    ammo_now = (int(store.get("ammo", 0)) + int(npc.stock.get("ammo", 0)))
    npc.ammo_acc = getattr(npc, "ammo_acc", 0.0) + daily_rate(AMMO_PER_DAY * fast) * dt
    made = 0
    while (npc.ammo_acc >= 1.0
           and ammo_now + made < ammo_cap
           and store.get("iron", 0) >= AMMO_IRON + GUN_IRON_KEEP
           and store.get("wood", 0) >= AMMO_WOOD
           and v.ledger_coins >= AMMO_PAY + GUN_COIN_KEEP):
        npc.ammo_acc -= 1.0
        store["iron"] -= AMMO_IRON
        store["wood"] -= AMMO_WOOD
        v.ledger_coins -= AMMO_PAY
        npc.coins += AMMO_PAY
        npc.book_in = getattr(npc, "book_in", 0.0) + AMMO_PAY
        npc.stock["ammo"] = npc.stock.get("ammo", 0) + 1
        made += 1
        if made >= 20:
            break
    npc.ammo_acc = min(npc.ammo_acc, 2.0)
    return made > 0


def produce(npc, dt: float, now: float) -> None:
    """A day at the pit head or the forge. The worker keeps what he makes."""
    workplace = getattr(npc, "workplace", None)
    if workplace is None:
        return
    scale = getattr(workplace, "rate_scale", 1.0)
    if workplace.kind == "brewery":
        # 1. The barrels first: draw whatever has finished fermenting.
        brew = getattr(npc, "brew", None)
        if brew is not None and now >= brew[2]:
            wort, count, _ready = brew
            npc.brew = None
            out = economy.BREW.get(wort)
            if out:
                hands = npc.skills.leaf_grade(8)
                given = npc.grade.get(wort, 3)
                g = quality.clamp(int(round((hands + given) / 2.0)))
                held = npc.stock.get(out, 0)
                npc.grade[out] = quality.merge(npc.grade.get(out, g), held, g, count)
                npc.stock[out] = held + economy.take_fifth(npc.village, npc, out, count)
                npc.skills.gain_farming(0.02 * min(count, 10))
        # 2. The table: mash what is on hand into wort, fifty at a time.
        if getattr(npc, "brew", None) is None:
            for src in economy.MASH:
                have = int(npc.stock.get(src, 0))
                if have <= 0:
                    continue
                batch = min(have, economy.WORT_BATCH)
                wort = economy.WORT[src]
                npc.stock[src] -= batch
                held = npc.stock.get(wort, 0)
                npc.grade[wort] = quality.merge(npc.grade.get(wort, 3), held,
                                                npc.grade.get(src, 3), batch)
                npc.stock[wort] = held + batch
                npc.skills.gain_farming(0.02 * min(batch, 10))
                break
        # 3. Load the barrel and start the clock -- five minutes of waiting.
        if getattr(npc, "brew", None) is None:
            for wort in economy.BREW:
                have = int(npc.stock.get(wort, 0))
                if have <= 0:
                    continue
                batch = min(have, economy.WORT_BATCH)
                npc.stock[wort] -= batch
                npc.brew = (wort, batch, now + economy.BREW_SECONDS)
                break
        return
    if workplace.kind == "lab":
        # Leaf in, finished goods out -- and the grade of the good is the
        # MIDPOINT of the leaf and the artisan's own hands. SSS leaf in a
        # clumsy man's fingers, or floor sweepings in a master's, both give a
        # middling cigar. It takes both of them to make something fine.
        npc.produce_acc += daily_rate(CRAFT_PER_DAY * scale) * dt
        made = 0
        while npc.produce_acc >= 1.0:
            leaf = next((k for k in economy.PROCESS if npc.stock.get(k, 0) > 0), None)
            if leaf is None:
                break
            out = economy.PROCESS[leaf]
            npc.produce_acc -= 1.0
            npc.stock[leaf] -= economy.CRAFT_CONSUME
            hands = npc.skills.leaf_grade(8)
            given = npc.grade.get(leaf, 3)
            g = quality.clamp(int(round((hands + given) / 2.0)))
            held = npc.stock.get(out, 0)
            npc.grade[out] = quality.merge(npc.grade.get(out, g), held, g, 1)
            npc.stock[out] = held + economy.take_fifth(npc.village, npc, out, 1)
            made += 1
            npc.skills.gain_farming(0.02)      # a slow trade, like the others
        if made:
            npc.produce_acc = min(npc.produce_acc, 2.0)
        return
    if workplace.kind == "mine":
        npc.produce_acc += daily_rate(IRON_PER_DAY * scale) * dt
        if npc.produce_acc >= 1.0:
            made = int(npc.produce_acc)
            npc.produce_acc -= made
            v2 = npc.village
            if v2 is None:
                return
            # THE MINE IS THE VILLAGE'S. A miner is not an entrepreneur. He is
            # not an artisan with goods of his own to sell, nor a smith with a
            # bench and a name on it -- he swings a pick at the village's face
            # and the ore is the village's from the moment it leaves the rock.
            # It goes onto the common shelf WHOLE, untaxed, because you do not
            # tax a man on what was never his.
            #
            # He is paid a wage instead: a piece rate that lands him a living
            # -- near enough the twenty a mayor is floored at, for a day's
            # digging -- and leaves the iron, all of it, with the village that
            # owns the pit. That is the difference between a mine and a trade.
            economy.store_add(v2, "iron", made, economy.grade_of(npc, "iron"))
            npc.wage_acc = getattr(npc, "wage_acc", 0.0) + made * MINER_PAY
            whole = int(npc.wage_acc)
            if whole > 0:
                npc.wage_acc -= whole
                whole = min(whole, int(v2.ledger_coins))
                if whole > 0:
                    v2.ledger_coins -= whole
                    npc.coins += whole
                    npc.book_in = getattr(npc, "book_in", 0.0) + whole
        return
    # The forge works to a small shelf, and every tool costs its lump of iron.
    # Count what is FREE of the kind he is about to make -- and count it per
    # kind. Reserved tools are promised, not stock. Counting every kind
    # together parked the smith with ten shovels on the shelf, six axe orders
    # in the book, and not one hammer blow struck in thirty days.
    gunworks(npc, dt)
    kind_wanted = forge_kind(npc.village, now)
    booked = sum(1 for _w, k in getattr(npc, "tool_orders", ()) if k == kind_wanted)
    free = (int(npc.stock.get(kind_wanted, 0))
            - int(getattr(npc, "tool_keep", {}).get(kind_wanted, 0)))
    if free >= max(FORGE_SHELF, booked):
        return                          # stocked for now, or nothing ordered
    npc.produce_acc += daily_rate(TOOLS_PER_DAY * scale) * dt
    made = 0
    while (npc.produce_acc >= 1.0
           and npc.stock.get("iron", 0) >= economy.IRON_PER_TOOL):
        npc.produce_acc -= 1.0
        npc.stock["iron"] -= economy.IRON_PER_TOOL
        made += 1
    if made:
        kind = kind_wanted
        # His OWN workmanship goes into the steel: a skilled smith turns out
        # tools that last, and charges accordingly.
        g = npc.skills.leaf_grade(8)
        held = npc.stock.get(kind, 0)
        npc.grade[kind] = quality.merge(npc.grade.get(kind, g), held, g, made)
        npc.stock[kind] = held + economy.take_fifth(npc.village, npc, kind, made)
        npc.skills.gain_farming(0.02 * made)     # the forge hones the smith too
        economy.fill_orders(npc.village, npc, kind)   # and the order is met
    npc.produce_acc = min(npc.produce_acc, 2.0)   # no banking a backlog


class Workplace:
    """A mine or a smithy standing inside the village fence."""

    def __init__(self, kind: str, x: float, y: float, seed: int) -> None:
        self.kind = kind
        self.x = float(x)
        self.y = float(y)
        self._rng_seed = seed & 0xFFFFFFFF
        self.rng = random.Random(self._rng_seed)
        self.w, self.h = ((136, 112) if kind == "mine"
                          else (96, 66) if kind == "lab"
                          else (116, 78) if kind == "brewery"
                          else (122, 110))
        self.rect = pygame.Rect(int(x - self.w / 2), int(y - self.h / 2),
                                self.w, self.h)
        self.base_y = y + self.h / 2.0
        self.sight_rect = self.rect.inflate(48, 48)
        self.door = (x, y + self.h / 2.0 + 15.0)
        self.worker = None
        self._image: pygame.Surface | None = None
        self.image = self._render_image()

    # -- art ----------------------------------------------------------------
    # -- the sprite, drawn once and kept ------------------------------------
    def _render_image(self) -> pygame.Surface:
        if self.kind == "mine":
            return self._render_mine()
        if self.kind == "lab":
            return self._render_lab()
        if self.kind == "brewery":
            return self._render_brewery()
        return self._render_smith()

    @property
    def image(self) -> pygame.Surface:
        """The building's sprite, drawn the first time it is asked for.

        A pygame Surface will not pickle, so the world cache leaves it out.
        Unlike a house, these walls are scattered from the building's own rng,
        so drawing it again has to REPLAY those draws from the same seed -- see
        __setstate__ -- or the picture would differ and the shared generator
        would be left somewhere else than it was saved.
        """
        if self._image is None:
            self._image = self._render_image()
        return self._image

    @image.setter
    def image(self, surface: pygame.Surface) -> None:
        self._image = surface

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_image"] = None
        return state

    def __setstate__(self, state):
        saved_rng = state["rng"]                 # where the generator really was
        self.__dict__.update(state)
        self._image = None
        self.rng = random.Random(state.get("_rng_seed", 0))
        self._image = self._render_image()       # the same picture, to the pixel
        self.rng = saved_rng                     # and nothing else disturbed

    def _render_mine(self) -> pygame.Surface:
        w, h, pad = self.w, self.h, 20
        surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        ox, oy = pad, pad
        pygame.draw.ellipse(surf, (0, 0, 0, 82), (ox + 8, oy + h - 12, w - 16, 26))
        pygame.draw.ellipse(surf, ROCK_D, (ox, oy + 28, w, h - 26))
        pygame.draw.ellipse(surf, ROCK, (ox + 8, oy + 16, w - 16, h - 32))
        pygame.draw.ellipse(surf, ROCK_L, (ox + 30, oy + 8, w - 74, h - 60))
        for _ in range(7):                       # boulders on the spoil heap
            bx = ox + self.rng.randint(16, w - 16)
            by = oy + self.rng.randint(34, h - 16)
            r = self.rng.randint(4, 10)
            pygame.draw.circle(surf, ROCK_D, (bx, by), r)
            pygame.draw.circle(surf, ROCK, (bx - 1, by - 1), max(1, r - 1))
        mw, mh = 48, 46
        mx = ox + int(w / 2 - mw / 2)
        my = oy + h - 28 - mh
        pygame.draw.rect(surf, MOUTH, (mx, my, mw, mh + 10))
        pygame.draw.ellipse(surf, MOUTH, (mx, my - 10, mw, 22))
        pygame.draw.rect(surf, TIMBER, (mx - 7, my - 12, 8, mh + 22))
        pygame.draw.rect(surf, TIMBER, (mx + mw - 1, my - 12, 8, mh + 22))
        pygame.draw.rect(surf, TIMBER_D, (mx - 7, my - 14, mw + 14, 8))
        pygame.draw.rect(surf, TIMBER_D, (mx - 7, my + mh - 2, mw + 14, 6))
        for i in range(3):                       # rails running out of the mouth
            ry = oy + h + 2 + i * 5
            pygame.draw.line(surf, TIMBER_D, (mx - 12, ry), (mx + mw + 12, ry), 2)
        return surf

    def _render_brewery(self) -> pygame.Surface:
        """A brewing table with barrels racked beside it."""
        w, h, pad = self.w, self.h, 18
        surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        ox, oy = pad, pad
        pygame.draw.ellipse(surf, (0, 0, 0, 78), (ox + 4, oy + h - 8, w - 8, 18))
        top = pygame.Rect(ox, oy + 14, int(w * 0.62), h - 24)
        pygame.draw.rect(surf, (138, 96, 58), top, border_radius=4)
        pygame.draw.rect(surf, (72, 50, 32), top, 2, border_radius=4)
        pygame.draw.rect(surf, (160, 170, 150), (ox + 10, oy + 2, 12, 16), border_radius=3)
        pygame.draw.rect(surf, (188, 150, 74), (ox + 30, oy + 4, 14, 14), border_radius=3)
        bx = ox + int(w * 0.68)
        for i, by in enumerate((oy + 6, oy + 34)):
            pygame.draw.ellipse(surf, (130, 86, 50), (bx, by, 30, 34))
            pygame.draw.ellipse(surf, (78, 52, 30), (bx, by, 30, 34), 2)
            pygame.draw.line(surf, (196, 196, 200), (bx + 3, by + 16), (bx + 27, by + 16), 2)
            pygame.draw.line(surf, (196, 196, 200), (bx + 3, by + 4), (bx + 27, by + 28), 1)
            pygame.draw.line(surf, (196, 196, 200), (bx + 3, by + 28), (bx + 27, by + 4), 1)
        return surf

    def _render_lab(self) -> pygame.Surface:
        """A laboratory is a TABLE, not a building: a bench, glassware, a still.
        The player builds the same bench in his own house."""
        w, h, pad = self.w, self.h, 18
        surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        ox, oy = pad, pad
        pygame.draw.ellipse(surf, (0, 0, 0, 78), (ox + 4, oy + h - 8, w - 8, 18))
        top = pygame.Rect(ox, oy + 12, w, h - 20)
        pygame.draw.rect(surf, (150, 104, 62), top, border_radius=4)
        pygame.draw.rect(surf, (78, 54, 34), top, 2, border_radius=4)
        pygame.draw.rect(surf, (118, 78, 46), (ox + 5, oy + h - 10, 8, 10))
        pygame.draw.rect(surf, (118, 78, 46), (ox + w - 13, oy + h - 10, 8, 10))
        for fx, gh, col in ((0.16, 20, (152, 204, 182)), (0.36, 28, (176, 224, 204))):
            pygame.draw.rect(surf, col, (ox + int(w * fx), oy + 12 - gh, 10, gh),
                             border_radius=3)
            pygame.draw.rect(surf, (90, 130, 116),
                             (ox + int(w * fx), oy + 12 - gh, 10, gh), 2, border_radius=3)
        cx = ox + int(w * 0.68)
        pygame.draw.circle(surf, (206, 158, 74), (cx, oy + 16), 10)
        pygame.draw.circle(surf, (140, 104, 48), (cx, oy + 16), 10, 2)
        pygame.draw.rect(surf, (100, 74, 40), (cx + 7, oy + 10, 5, 12))
        return surf

    def _render_smith(self) -> pygame.Surface:
        w, h, pad = self.w, self.h, 20
        surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        ox, oy = pad, pad
        pygame.draw.rect(surf, (16, 30, 16, 95), (ox + 6, oy + 10, w, h))
        pygame.draw.rect(surf, STONE, (ox, oy + 20, w, h - 14))
        pygame.draw.rect(surf, STONE_D, (ox, oy + 20, w, h - 14), 2)
        for yy in range(oy + 28, oy + h, 14):    # courses of stone
            pygame.draw.line(surf, STONE_D, (ox + 2, yy), (ox + w - 2, yy), 1)
        roof_h = 42
        pygame.draw.rect(surf, ROOF_L, (ox - 5, oy + 4, w + 10, roof_h // 2))
        pygame.draw.rect(surf, ROOF, (ox - 5, oy + 4 + roof_h // 2, w + 10, roof_h // 2))
        pygame.draw.rect(surf, TIMBER_D, (ox - 5, oy + 4, w + 10, roof_h), 2)
        cx = ox + int(w * 0.74)
        pygame.draw.rect(surf, STONE_D, (cx, oy - 8, 16, 24))    # chimney
        for i, r in enumerate((7, 9, 6)):
            pygame.draw.circle(surf, (152, 152, 154, 88),
                               (cx + 10 + i * 5, oy - 16 - i * 9), r)
        dw, dh = 30, 34                          # the forge mouth, aglow
        dx = ox + int(w / 2 - dw / 2)
        dy = oy + h - 12 - dh
        pygame.draw.rect(surf, (42, 28, 20), (dx, dy, dw, dh))
        pygame.draw.rect(surf, FORGE, (dx + 4, dy + dh - 15, dw - 8, 11))
        pygame.draw.rect(surf, TIMBER_D, (dx, dy, dw, dh), 2)
        ax = ox + w - 30                         # anvil by the door
        pygame.draw.rect(surf, (60, 60, 64), (ax, oy + h - 24, 22, 6))
        pygame.draw.rect(surf, (46, 46, 50), (ax + 8, oy + h - 18, 6, 12))
        return surf

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        image = self.image
        screen.blit(image, (self.x - cam_x - image.get_width() / 2,
                            self.y - cam_y - image.get_height() / 2))
