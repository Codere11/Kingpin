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
GOODS = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal",
         "tobacco", "red_mushroom", "agave", "plant", "mushroom")


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

    # -- what he is carrying -------------------------------------------------
    def cargo(self) -> int:
        st = getattr(self.npc, "stock", {})
        return sum(int(st.get(i, 0)) for i in GOODS)

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
            plog.log("CART", getattr(n, "name", "?"), "stage", self.stage,
                     "cargo", self.cargo(), "target", getattr(self, "target", 0),
                     "goal", getattr(_g, "name", None),
                     "dist", int(_d), "at", "%d,%d" % (int(n.x), int(n.y)),
                     "skill", round(float(getattr(n, "smuggling", 0.0)), 2))

        if self.stage == "to_hub":
            if self.goal is None or getattr(self.goal, "is_hub", False) is not True:
                self.goal = self._pick_hub(hubs)
                if self.goal is None:
                    return
            if not self._walk(dt, self.goal.x, self.goal.y + 40.0, 60.0):
                return
            # WHAT HE WILL RISK ON THIS TRIP, by his own hand: a fifth of what
            # would certainly catch him. Beginner 6, master 60.
            self.target = gate.caravan_load(float(getattr(n, "smuggling", 0.0)))
            self._buy(self.goal)
            # HE LEAVES WITH WHAT HE HAS. The target is a CAP on how much risk
            # he will take, not a condition he waits for: a hut with one cigar
            # on its shelf had him standing there buying it again and again --
            # 2090 "loaded" lines in four minutes -- and never setting off.
            if self.cargo() <= 0:
                # A HUT WITH NOTHING ON ITS SHELF IS NOT A TRIP. He used to set
                # off empty, walk to a town, sell nothing and walk back -- 119
                # of 132 "trips" in a measured day carried no cargo at all.
                # Instead he rolls on to the NEXT hut: constant trips, and every
                # one of them actually a trade.
                self._skip = self.goal
                self.goal = None
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
    def _pick_hub(self, hubs):
        """A hut WITH SOMETHING ON THE SHELF, nearest first.

        He used to walk to the nearest hut whatever was in it, find an empty
        shelf, turn round, and walk to the next nearest -- which was the one he
        had just left. Measured: 173 of 175 minutes spent in `to_hub`, goals
        fourteen kilometres away, two sales in the whole run. A trader's first
        question is not "where is the nearest hut" but "where is the goods".
        """
        best, bd = None, 1e18
        fallback, fb_d = None, 1e18
        for h in hubs:
            d = (h.x - self.npc.x) ** 2 + (h.y - self.npc.y) ** 2
            if d < fb_d:
                fallback, fb_d = h, d
            stock = getattr(h, "ledger_goods", None) or {}
            if not any(int(stock.get(i, 0)) > 0 for i in GOODS):
                continue
            if d < bd:
                best, bd = h, d
        return best if best is not None else fallback

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
        _before = self.cargo()
        """WHAT THE HUT MAKES, BOUGHT AND PAID FOR. The coins go into the hut's
        purse -- that is the hut's living, and it is why the chain exists."""
        n = self.npc
        need = max(0, int(getattr(self, "target", LOAD)) - self.cargo())
        if need <= 0:
            return
        purse = int(getattr(n, "coins", 0))
        for item in GOODS:
            qty = int(getattr(hub, "ledger_goods", {}).get(item, 0))
            if qty <= 0:
                continue
            price = max(1, int(round(economy.value(hub, item) * 0.8)))
            take = min(qty, need, purse // price if price else 0)
            if take <= 0:
                continue
            n.stock[item] = int(n.stock.get(item, 0)) + take
            hub.ledger_goods[item] = qty - take
            hub.ledger_coins = int(getattr(hub, "ledger_coins", 0)) + take * price
            n.coins = purse - take * price
            purse = int(n.coins)
            need -= take
            if need <= 0:
                break
        if self.cargo() > _before:
            plog.log("CARAVAN", getattr(n, "name", "?"), "loaded",
                     self.cargo(), "of", getattr(self, "target", LOAD),
                     "at", getattr(hub, "name", "?"))

    def _sell(self, town) -> None:
        """TO THE MEN WHO STILL WANT IT, at the town's own price and a margin."""
        n = self.npc
        sold = 0
        _wanting = _able = 0
        for item in GOODS:
            qty = int(n.stock.get(item, 0))
            if qty <= 0:
                continue
            # THE TOWN'S OWN PRICE, NO MARGIN ON TOP. At +35% a cigar cost 30
            # and only TWO of the five men who wanted one could pay; the cart
            # went home with the rest of its load. A smuggler's margin is the
            # fact that he is there at all.
            price = max(1, int(round(economy.value(town, item))))
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
                p.stock[item] = int(p.stock.get(item, 0)) + 1
                p.coins = coins - price
                p.yearning = max(0.0, float(p.yearning) - 0.5)
                n.coins = int(getattr(n, "coins", 0)) + price
                qty -= 1
                sold += 1
            n.stock[item] = qty
        # WHAT NOBODY COULD AFFORD, THE TOWN BUYS. Its people wanted the goods
        # and had no coin -- six wanting, none affording in a measured sale --
        # so the cart went home full and the craving went unsold. The town's
        # own purse takes the remainder at its own price, and its shop sells it
        # on to whoever earns the money later. That is what a market is.
        if sold >= 0:
            for item in GOODS:
                qty = int(n.stock.get(item, 0))
                if qty <= 0:
                    continue
                price = max(1, int(round(economy.value(town, item))))
                purse = int(getattr(town, "ledger_coins", 0))
                take = min(qty, purse // price if price else 0)
                if take <= 0:
                    continue
                town.ledger_goods[item] = int(town.ledger_goods.get(item, 0)) + take
                town.ledger_coins = purse - take * price
                n.coins = int(getattr(n, "coins", 0)) + take * price
                n.stock[item] = qty - take
                sold += take
        plog.log("CARAVAN", getattr(n, "name", "?"), "sold", sold, "at", town.name,
                 "| carried", self.cargo(), "wanting", _wanting, "afforded", _able,
                 "price", price if 'price' in dir() else "?")
