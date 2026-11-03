"""caravans.py -- THE FREE TRADER. Not a hub's man, not a town's.

A caravan trader belongs to nobody. He is NATIONLESS, he has no village, and no
crown can claim him: he buys leaf where the state does not reach and sells it
where the craving still is. He walks a loop --

    a hub  ->  buys what it makes, and pays it  ->  a settlement's GATE
           ->  the town's guard searches him  ->  clean: sells to the men who
               still want it  ->  back to a hub for another load

-- and if he is caught he loses the load and the town turns out, which is the
whole risk of the trade.

He starts with TEN BREAD and no coin to speak of, the same as a man would.

Wiring: `Hubs` spawns them (Hubs.build), steps them every frame (Hubs.update),
and owns their list. They are put into the npcs list of whatever they are
standing in -- a hut or a town -- so they are drawn, fed and seen by every
system that walks a settlement, and they are in `village.TRAVELLERS` while they
are on the road.
"""

from __future__ import annotations

import math

import economy
import gate
import plog

LOAD = 20                    # fallback only: the real load is skill-based
SPEED = 240.0                # px a second: a cart on a made road
GATE_STANDOFF = 70.0         # where he stops to be looked at
# HOW LONG A CART WAITS AT AN EMPTY SHELF BEFORE LOOKING ROUND AGAIN. He used
# to look again on the NEXT FRAME -- sixty times a second, each look a scan of
# every hut in the world -- and found the same empty shelf every time. Five
# seconds of game time is a fifth of a minute in a trip that takes many
# minutes, and one scan instead of three hundred.
HUB_RETRY_SECONDS = 5.0
GOODS = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal",
         "tobacco", "red_mushroom", "agave", "plant", "mushroom")


def _take_lot(npc, item: str, grade: int, count: int) -> None:
    """KEEP THE SHIPMENT'S BOOKS IN STEP WITH THE BALLOT BOXES.

    A cart's hold is LOTS (`Caravan.lots`), because a trader who pours an SSS
    lot into a hold of floor sweepings and calls the mixture one grade has
    thrown his own margin away -- the blend is worth the blend. `npc.stock` is
    still kept as the TOTAL of every lot, because every other system reads it:
    the gate's contraband check, the pack sync, the drawn figure.
    """
    if count <= 0:
        return
    npc.stock[item] = int(npc.stock.get(item, 0)) + int(count)


def _take_from_shelf(shelf, item: str, grade: int, count: int) -> None:
    """TAKE ONE LOT OFF A SHELF, and leave the shelf's books true.

    A hut keeps `ledger_lots` (units by grade) and a mean grade in
    `ledger_grade`; the player's stall keeps piles by grade as well. Both are
    decremented here, and a shelf that has lost its last unit is empty.
    """
    count = int(count)
    if count <= 0:
        return
    try:
        goods = shelf.ledger_goods
        goods[item] = max(0, int(goods.get(item, 0)) - count)
    except Exception:
        pass
    lots = getattr(shelf, "_lots", None)          # the stall proxy
    if isinstance(lots, dict) and item in lots:
        by = lots[item]
        if isinstance(by, dict) and int(grade) in by:
            try:
                by[int(grade)] = max(0, int(by[int(grade)][0]) - count)
            except Exception:
                by[int(grade)] = max(0, int(by[int(grade)]) - count)
        return
    book = getattr(shelf, "ledger_lots", None)
    if isinstance(book, dict) and item in book:
        by = book[item]
        if isinstance(by, dict):
            by[int(grade)] = max(0, int(by.get(int(grade), 0)) - count)
            if by[int(grade)] <= 0:
                by.pop(int(grade), None)
            try:
                import economy as _e
                _e.store_grade(shelf, item)
            except Exception:
                pass


class Caravan:
    """One free trader, with a pack and a route."""

    def __init__(self, npc, home_hub):
        self.npc = npc
        self.hub = home_hub            # where he goes back to; he does not live there
        self.stage = "to_hub"
        self.goal = None               # a hub while loading, a town while selling
        self.verdict = None
        self.trips = 0
        self.caught = 0
        # THE HUT HE HAS JUST FOUND EMPTY, AND WHEN HE MAY LOOK ROUND AGAIN.
        # `_skip` was written here twice and never read, so a cart at an empty
        # hut re-picked the same hut on the next frame for ever.
        self._skip = None
        self._retry_at = 0.0
        # THE HOLD, BY LOT: {(item, grade): count}. Started from whatever he
        # is carrying -- ten loaves that came with the cart.
        self.lots: dict = {}
        for item, qty in (getattr(npc, "stock", None) or {}).items():
            if item in GOODS and int(qty) > 0:
                self.lots[(item, 3)] = int(qty)

    # -- what he is carrying -------------------------------------------------
    def cargo(self) -> int:
        return sum(int(q) for (_i, _g), q in self.lots.items())

    # -- the hold, lot by lot -------------------------------------------
    def _expected_sale(self, item: str, grade: int) -> float:
        """WHAT THIS LOT SHOULD FETCH at the town he would sell in.

        Set by `tick` before he buys. Without it a trader could not tell a
        bargain from a trap, and the order he filled his hold in would be the
        alphabetical order of his own cargo.
        """
        town = getattr(self, "_dest_town", None)
        try:
            if town is not None:
                return float(economy.prospect(town, item, int(grade)))
            import quality
            return (float(economy.ITEM_VALUE.get(item, 4) or 4)
                    * float(quality.SELL_VALUE[quality.clamp(int(grade))]))
        except Exception:
            return 0.0

    def _by_margin(self, lots: dict) -> list:
        """LOTS ORDERED BY WHAT EACH IS WORTH PER UNIT -- best margin first.

        A cart used to fill its hold in the order the lots happened to be
        listed, which meant a purse could be spent on floor sweepings while a
        bargain sat on the same shelf.
        """
        rows = []
        for (item, grade), row in lots.items():
            try:
                qty, price = int(row[0]), int(row[1])
            except Exception:
                qty, price = int(row), 0
            rows.append(((item, int(grade)), qty, price,
                         self._expected_sale(item, int(grade)) - price))
        rows.sort(key=lambda r: (-r[3], r[0]))
        return rows

    def _load(self, item: str, grade: int, count: int) -> None:
        key = (item, int(grade))
        self.lots[key] = int(self.lots.get(key, 0)) + int(count)
        _take_lot(self.npc, item, int(grade), int(count))

    def _unload(self, item: str, grade: int, count: int) -> None:
        key = (item, int(grade))
        have = int(self.lots.get(key, 0))
        take = min(have, int(count))
        if take <= 0:
            return
        if have - take <= 0:
            self.lots.pop(key, None)
        else:
            self.lots[key] = have - take
        self.npc.stock[item] = max(0, int(self.npc.stock.get(item, 0)) - take)

    def _lot_grade(self, item: str) -> int:
        """The best grade of a thing in the hold -- kept for old callers."""
        grades = [g for (i, g) in self.lots if i == item]
        return int(max(grades)) if grades else 3

    # -- the loop ------------------------------------------------------------
    def tick(self, dt, hubs, towns, now) -> None:
        n = self.npc
        if not getattr(n, "alive", False):
            return
        economy.needs(n, dt)                     # hunger is his own business
        if n.hunger >= 100.0:
            return

        # WHERE IS HE, AND WHY IS HE THERE. Every minute, per cart.
        if now - getattr(self, "_say_t", -999.0) >= 60.0:
            self._say_t = now
            _g = self.goal
            _d = (math.hypot(_g.x - n.x, _g.y - n.y) if _g is not None else -1)
            plog.log("CART", getattr(n, "id", "?"), getattr(n, "name", "?"),
                     "stage", self.stage,
                     "cargo", self.cargo(), "target", getattr(self, "target", 0),
                     "goal", getattr(_g, "name", None),
                     "dist", int(_d), "at", "%d,%d" % (int(n.x), int(n.y)),
                     "skill", round(float(getattr(n, "smuggling", 0.0)), 2))

        if self.stage == "to_hub":
            if self.goal is None or getattr(self.goal, "is_hub", False) is not True:
                # A HUT WITH NOTHING ON ITS SHELF IS NOT RE-EXAMINED EVERY
                # FRAME. He used to re-pick instantly, so a cart waiting at an
                # empty hut scanned every hut in the world sixty times a
                # second: 24.6 of every 25 cart-frames were a full 25-hut scan,
                # 13.4 million stock reads in one run. The retry clock makes it
                # one scan every HUB_RETRY_SECONDS while there is nothing to buy.
                if now < getattr(self, "_retry_at", 0.0):
                    return
                self.goal = self._pick_hub(hubs, towns,
                                           skip=getattr(self, "_skip", None))
                if self.goal is None:
                    return
            if not self._walk(dt, self.goal.x, self.goal.y + 40.0, 60.0):
                return
            # WHAT HE WILL RISK ON THIS TRIP, by his own hand: a fifth of what
            # would certainly catch him. Beginner 6, master 60.
            self.target = gate.caravan_load(float(getattr(n, "smuggling", 0.0)))
            # WHERE HE WOULD SELL, so he can tell a bargain from a trap before
            # he opens his purse.
            self._dest_town = self._pick_town(towns, n)
            self._buy(self.goal)
            # HE LEAVES WITH WHAT HE HAS. The target is a CAP on how much risk
            # he will take, not a condition he waits for: a hut with one cigar
            # on its shelf had him standing there buying it again and again --
            # 2090 "loaded" lines in four minutes -- and never setting off.
            if self.cargo() <= 0:
                # A HUT WITH NOTHING ON ITS SHELF IS NOT A TRIP. He used to set
                # off empty, walk to a town, sell nothing and walk back -- 119
                # of 132 "trips" in a measured day carried no cargo at all.
                # Instead he rolls on to the NEXT hut THAT HAS GOODS; and if no
                # hut has any, he stays where he is and looks again when the
                # clock says so, rather than walking to another empty one.
                self._skip = self.goal
                self.goal = None
                self._retry_at = now + HUB_RETRY_SECONDS
                return
            self._skip = None
            self.stage = "to_town"

        elif self.stage == "to_town":
            if self.goal is None or getattr(self.goal, "is_hub", False):
                self.goal = self._pick_town(towns, n)
                if self.goal is None:
                    return
            # TO THE GATE, not the square. He is searched like anybody else.
            gx, gy = self._gate_of(self.goal)
            if not self._walk(dt, gx, gy, GATE_STANDOFF):
                return
            v = gate.search_visitor(dt, self.goal, n)
            if v is None:
                return                            # the guard is still looking
            if v == "caught":
                self.caught += 1
                self.goal.provoke()
                for i in list(n.stock):
                    if i in GOODS:
                        n.stock[i] = 0
                plog.log("CARAVAN", getattr(n, "name", "?"), "CAUGHT at",
                         self.goal.name)
                self.stage = "to_hub"
                self.goal = None
                return
            # THROUGH CLEAN: he learns the trade, and his next load is bigger.
            n.smuggling = min(10.0, float(getattr(n, "smuggling", 0.0))
                              + 0.02 + 0.0005 * self.cargo())
            self._sell(self.goal)
            self.trips += 1
            self.stage = "to_hub"
            self.goal = None

    # -- the pieces ----------------------------------------------------------
    @staticmethod
    def _lots_of(hub) -> dict:
        """{(item, grade): [how many, price]} FOR ANY SHELF IN THE WORLD.

        A hut or a town keeps its stock in `ledger_lots` -- units counted by
        the grade they came in at (economy.store_add) -- and asks a single
        price basis, so a lot's price is economy.prospect: the place's value
        times the grade's own multiplier. The player's stall keeps lots too,
        and names its own price for each. One shape for both, so a cart asks
        one question of either.
        """
        out = {}
        if getattr(hub, "is_stall", False) and hasattr(hub, "lots"):
            for (item, grade), row in hub.lots().items():
                try:
                    qty, price = int(row[0]), int(row[1])
                except Exception:
                    qty, price = int(row), 0
                if qty > 0 and price > 0:
                    out[(item, int(grade))] = [qty, price]
            return out
        lots = getattr(hub, "ledger_lots", None) or {}
        for item, by_grade in lots.items():
            total = int((getattr(hub, "ledger_goods", None) or {}).get(item, 0))
            if total <= 0:
                continue
            for grade, qty in (by_grade or {}).items():
                qty = int(qty or 0)
                if qty <= 0:
                    continue
                price = max(1, int(round(
                    economy.prospect(hub, item, int(grade)) * 0.8)))
                out[(item, int(grade))] = [qty, price]
        # A SHELF WITH GOODS BUT NO LOT BOOK (an old save, a stall without
        # grades) is still worth buying: one lot at the shelf's own grade.
        if not out:
            goods = getattr(hub, "ledger_goods", None) or {}
            for item, qty in goods.items():
                qty = int(qty or 0)
                if qty <= 0 or item not in GOODS:
                    continue
                grade = int((getattr(hub, "ledger_grade", None) or {}).get(item, 3))
                out[(item, grade)] = [qty, max(1, int(round(
                    economy.prospect(hub, item, grade) * 0.8)))]
        return out

    @staticmethod
    def _price_at(hub, item, grade=None) -> int:
        """WHAT A THING COSTS AT THIS PLACE, to a trader standing in the road.

        A hut sells at its own price less a fifth; a stall sells at exactly
        what the player set -- which is the whole of his power over the trade:
        he may undersell the world and take its traffic, or price himself out
        of it and watch the carts go by.
        """
        if getattr(hub, "is_stall", False):
            return (int(hub.price_of(item, grade))
                    if hasattr(hub, "price_of") else 0)
        try:
            g = 3 if grade is None else int(grade)
            return max(1, int(round(economy.prospect(hub, item, g) * 0.8)))
        except Exception:
            return 1

    def _profit_rate(self, hub, towns) -> float:
        """WHAT THE TRIP IS WORTH: coin of margin per second of walking.

        This is the question a trader actually asks, and until now this cart
        did not ask it. He paid a FIXED 0.8 of the hut's own value, sold at the
        town's price with no margin on top, and chose his destinations by
        DISTANCE -- so a place that sold cheap was not more attractive to him,
        it was merely closer or further. A price is the whole of the player's
        power over trade, and none of the code that decides where a cart goes
        had ever read one.

        So: for the best thing on this shelf, (sale price - asking price) times
        the number he could actually take, divided by the seconds it costs to
        walk there and on to the town he would sell in. A counter that
        undercuts the world wins the traffic; one that asks more than the town
        pays is worth nothing at all, however close it stands.
        """
        lots = self._lots_of(hub)
        if not lots:
            return 0.0
        town = self._pick_town(towns, self.npc) if towns else None
        purse = int(getattr(self.npc, "coins", 0) or 0)
        hold = int(getattr(self, "target", 0) or LOAD)
        d_here = math.hypot(hub.x - self.npc.x, hub.y - self.npc.y)
        d_town = (math.hypot(town.x - hub.x, town.y - hub.y)
                  if town is not None else 0.0)
        seconds = max(1.0, (d_here + d_town) / SPEED)
        best = 0.0
        for (item, grade), row in lots.items():
            qty = int(row[0])
            cost = int(row[1])
            if qty <= 0 or cost <= 0:
                continue                      # not for sale
            # QUALITY IS PART OF THE PRICE ON BOTH SIDES: the lot is bought at
            # its grade and sold at its grade. This is what `economy.prospect`
            # was written for and had never been asked.
            sale = (float(economy.prospect(town, item, grade)) if town is not None
                    else float(economy.ITEM_VALUE.get(item, 4) or 4)
                    * float(__import__("quality").SELL_VALUE[
                        __import__("quality").clamp(grade)]))
            margin = sale - cost
            if margin <= 0:
                continue                      # dearer than the town pays
            take = min(qty, hold, purse // cost if cost else 0)
            if take <= 0:
                continue                      # he cannot afford even one
            rate = margin * take / seconds
            if rate > best:
                best = rate
        return best

    def _pick_hub(self, hubs, towns=(), skip=None):
        """A hut WITH SOMETHING ON THE SHELF, nearest first -- and never the
        one he has just found empty, if any other hut has anything at all.

        He used to walk to the nearest hut whatever was in it, find an empty
        shelf, turn round, and walk to the next nearest -- which was the one he
        had just left. Measured: 173 of 175 minutes spent in `to_hub`, goals
        fourteen kilometres away, two sales in the whole run. A trader's first
        question is not "where is the nearest hut" but "where is the goods".

        `skip` is the hut he has just failed at: excluded from the search, so
        "roll on to the next" is what actually happens. If NOTHING anywhere has
        stock there is no journey worth making, and he is told to stay put.
        """
        best, bd = None, 1e18
        fallback, fb_d = None, 1e18
        best_pull = 0.0
        for h in hubs:
            if skip is not None and h is skip:
                continue
            d = (h.x - self.npc.x) ** 2 + (h.y - self.npc.y) ** 2
            if d < fb_d:
                fallback, fb_d = h, d
            stock = getattr(h, "ledger_goods", None) or {}
            if not any(int(stock.get(i, 0)) > 0 for i in GOODS):
                continue
            # MARGIN PER SECOND, not metres. What he would make on the trip,
            # over what the trip costs him in walking -- the price is in this
            # number, and so is the distance, and neither is invented.
            pull = self._profit_rate(h, towns)
            if pull > best_pull:
                best, best_pull, bd = h, pull, d
        if best is not None:
            return best
        # EVERY SHELF IS EMPTY: wait where he is. Walking to another empty hut
        # could not become a trade, and it is the walk that used to ping-pong.
        return skip if skip is not None else fallback

    def _pick_town(self, towns, n):
        best, bd = None, 1e18
        for t in towns:
            if getattr(t, "is_hub", False):
                continue
            d = (t.x - n.x) ** 2 + (t.y - n.y) ** 2
            if d < bd:
                best, bd = t, d
        return best

    def _gate_of(self, town):
        try:
            import fence
            side, gx, gy = fence.gate_list(town)[0]
            ox, oy = fence.OUTWARD[side]
            return gx + ox * GATE_STANDOFF, gy + oy * GATE_STANDOFF
        except Exception:
            return town.x, town.y

    def _walk(self, dt, tx, ty, within) -> bool:
        n = self.npc
        dx, dy = tx - n.x, ty - n.y
        d = math.hypot(dx, dy) or 1.0
        if d <= within:
            return True
        step = min(d, SPEED * dt)
        n.x += dx / d * step
        n.y += dy / d * step
        n.target = (tx, ty)
        return False

    def _buy(self, hub) -> None:
        # THE PLAYER'S STALL. One branch, and the only difference is the price:
        # a hut sells at the world's price less a fifth, a stall at the price
        # the player set. What he does with the load afterwards is unchanged.
        if getattr(hub, "is_stall", False):
            return self._buy_stall(hub)
        _before = self.cargo()
        """WHAT THE HUT MAKES, BOUGHT AND PAID FOR, LOT BY LOT.

        The coins go into the hut's purse -- that is the hut's living, and it
        is why the chain exists. The grade comes aboard with the goods: what a
        cart pays for a lot and what it asks for it later are both the lot's
        grade's business.
        """
        n = self.npc
        need = max(0, int(getattr(self, "target", LOAD)) - self.cargo())
        if need <= 0:
            return
        purse = int(getattr(n, "coins", 0))
        for (item, grade), qty, price, margin in self._by_margin(self._lots_of(hub)):
            if need <= 0:
                break
            if item not in GOODS or qty <= 0 or price <= 0 or margin <= 0:
                continue                      # a trader does not buy at a loss
            take = min(qty, need, purse // price)
            if take <= 0:
                continue
            self._load(item, int(grade), take)
            _take_from_shelf(hub, item, int(grade), take)
            hub.ledger_coins = int(getattr(hub, "ledger_coins", 0)) + take * price
            n.coins = purse - take * price
            purse = int(n.coins)
            need -= take
        if self.cargo() > _before:
            plog.log("CARAVAN", getattr(n, "name", "?"), "loaded",
                     self.cargo(), "of", getattr(self, "target", LOAD),
                     "at", getattr(hub, "name", "?"))

    def _buy_stall(self, hub) -> None:
        """BUYING AT THE PLAYER'S COUNTER: his price, his purse, no haggling."""
        n = self.npc
        need = max(0, int(getattr(self, "target", LOAD)) - self.cargo())
        if need <= 0:
            return
        purse = int(getattr(n, "coins", 0))
        got = 0
        for (item, grade), qty, price, margin in self._by_margin(self._lots_of(hub)):
            if need <= 0:
                break
            if price <= 0 or qty <= 0 or margin <= 0:
                continue                      # a trader does not buy at a loss
            take = min(qty, need, purse // price)
            if take <= 0:
                continue
            self._load(item, int(grade), take)
            # THE LANE'S OWN COPY OF THE SHELF GOES DOWN WITH THE SALE, lot and
            # total both, or a second cart in the same tick buys the cigar that
            # has already been sold.
            _take_from_shelf(hub, item, int(grade), take)
            hub.ledger_coins = int(getattr(hub, "ledger_coins", 0)) + take * price
            n.coins = purse - take * price
            purse = int(n.coins)
            need -= take
            got += take
            try:
                hub.sales_log.append((item, int(grade), take, price * take))
            except Exception:
                pass
        if got:
            plog.log("CARAVAN", getattr(n, "name", "?"), "bought", got,
                     "at the", getattr(hub, "name", "stall"),
                     "for", int(hub.ledger_coins))

    def _sell(self, town) -> None:
        """TO THE MEN WHO STILL WANT IT, LOT BY LOT, AT THE LOT'S OWN PRICE.

        Each grade goes at what that grade fetches here -- SSS leaf at six times
        F, because quality.SELL_VALUE says so and economy.prospect is how the
        town's own price is scaled by it. The hold is sold lot by lot rather
        than poured together, so a good shipment keeps its value all the way to
        the counter instead of being averaged into the rubbish.
        """
        n = self.npc
        sold = 0
        _wanting = _able = 0
        _last_price = "?"
        for (item, grade) in sorted(self.lots, key=lambda k: (k[0], -k[1])):
            if item not in GOODS:
                continue
            qty = int(self.lots.get((item, grade), 0))
            if qty <= 0:
                continue
            price = max(1, int(round(economy.prospect(town, item, int(grade)))))
            _last_price = price
            for p in town.npcs:
                if qty <= 0:
                    break
                if not p.alive or p.in_interior:
                    continue
                if float(getattr(p, "yearning", 0.0)) < economy.YEARING_BUY:
                    continue
                _wanting += 1
                coins = int(getattr(p, "coins", 0))
                if coins < price:
                    continue
                _able += 1
                try:
                    import quality
                    held = int(p.stock.get(item, 0))
                    p.stock[item] = held + 1
                    if not isinstance(getattr(p, "grade", None), dict):
                        p.grade = {}
                    p.grade[item] = quality.merge(int(p.grade.get(item, 3)),
                                                  held, int(grade), 1)
                except Exception:
                    p.stock[item] = int(p.stock.get(item, 0)) + 1
                p.coins = coins - price
                p.yearning = max(0.0, float(p.yearning) - 0.5)
                n.coins = int(getattr(n, "coins", 0)) + price
                qty -= 1
                sold += 1
                self._unload(item, int(grade), 1)
        # WHAT NOBODY COULD AFFORD, THE TOWN BUYS. Its people wanted the goods
        # and had no coin -- six wanting, none affording in a measured sale --
        # so the cart went home full and the craving went unsold. The town's
        # own purse takes the remainder at the lot's own price, and its shop
        # sells it on to whoever earns the money later.
        for (item, grade) in sorted(self.lots, key=lambda k: (k[0], -k[1])):
            if item not in GOODS:
                continue
            qty = int(self.lots.get((item, grade), 0))
            if qty <= 0:
                continue
            price = max(1, int(round(economy.prospect(town, item, int(grade)))))
            purse = int(getattr(town, "ledger_coins", 0))
            take = min(qty, purse // price if price else 0)
            if take <= 0:
                continue
            try:
                economy.store_add(town, item, take, int(grade))
            except Exception:
                town.ledger_goods[item] = int(town.ledger_goods.get(item, 0)) + take
            town.ledger_coins = purse - take * price
            n.coins = int(getattr(n, "coins", 0)) + take * price
            self._unload(item, int(grade), take)
            sold += take
        plog.log("CARAVAN", getattr(n, "name", "?"), "sold", sold, "at", town.name,
                 "| carried", self.cargo(), "wanting", _wanting,
                 "afforded", _able, "price", _last_price)

    # -- the pieces ----------------------------------------------------------
