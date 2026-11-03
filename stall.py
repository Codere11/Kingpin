"""stall.py -- THE MARKET STALL: the player's own shop, and the only seller.

DESIGN, IN FULL, BEFORE THE CODE. What follows is the whole thing: what a stall
is, who may put things on it, who may buy, where the coin goes, and where each
answer comes from in the code as it stands today.

-------------------------------------------------------------------------------
1. WHAT IT IS

    A building of the player's, standing INSIDE HIS OWN HUB. It is not a
    settlement and it does not hire anybody: it is a counter, a shelf and a
    purse. It holds goods (`stock`, a real Inventory of 32 slots, the same as
    the player's pack), a price for each thing on it (`prices`), the money
    taken so far (`coins`), and a switch (`on`).

    It is a `placed_work` building -- the same list as the bench, the forge,
    the brewhouse and the shaft (main.py, `placed_work`). That list is already
    drawn (`wp.draw(screen, cam_x, cam_y)`), already solid (`wp.rect`), already
    saved and restored (`yard_work` in save_now/load_now), and already what
    `near_work()` finds when the player presses E at a building. The stall
    therefore costs almost no new plumbing -- but see 8: it must NOT go through
    the `yard_work` restore, which rebuilds an `industry.Workplace`.

2. WHAT MAKES IT LEGAL

    build.BUILDINGS gets one entry: id "stall", 100 wood, outdoors. main's
    placement branch for it demands what the branch for the four trades
    demands (clear ground, the materials) and one thing more:

        hubs.in_player_hub(rect, hub_world.hubs) must be True

    -- "he can only place it inside his hub", which already exists as a
    question the code can answer (hubs.py:59).

3. WHO PUTS GOODS ON IT

    Nobody automatically. Every good on a stall was either

    (a) dragged there by the player -- the stall's own screen takes from and
        gives to his pack exactly as a chest does (ui.ChestPanel is reused for
        that), or
    (b) put there by a man he employs, after the player TELLS that man to.

    (b) is a per-man flag, `npc.to_market`, set from "About work..." in the
    dialogue (row "Put his product on the market" / "...on the chest"). It is
    the same idea as `npc.work_post`: a worker's output goes to the chest
    unless the player says otherwise. `work.produce()` owns that decision:

        target = stall_in_his_hub if npc.to_market and the stall exists
                 else the chest in his hub

    and it deposits with the same fullness rule as the chest: what will not fit
    stays in his pack and he says so.

    A man who is employed never sells by himself. There is no code path in
    which a hired man acts as a trader: `work.hire` already ends his own trade
    run (`trade_state = "none"`), and this module adds no other.

4. WHO BUYS, AND HOW THEY SEE IT

    The free traders -- caravans.Caravan, the carts the huts spawn -- are the
    buyers. They live in the HUB LANE (lanes_mp.py, `_hub_step`: "the hubs,
    their people, and the free traders"), and they pick a destination in
    `Caravan._pick_hub`: the nearest hub whose `ledger_goods` holds something
    in their GOODS, then walk to it, buy, and carry it to a town.

    The stall is in the FRAME. The carts are in a CHILD PROCESS. They cannot
    see each other, so the stall is RELAYED to the lane (the same mechanism the
    crown's stipend already uses, `_to_hub` / `msg["relay"]`):

        frame -> lane, once a second:  ("stall", x, y, name, on, goods, prices)
        lane  -> frame, every reply:   msg["stall"] = {"sales": [(item, n, coin)]}

    In the lane the stall is a PROXY with exactly the attributes the cart code
    reads from a hut: `x`, `y`, `name`, `is_hub`, `ledger_goods`, `ledger_coins`,
    plus `is_stall` and `price_of(item)`. `Caravan._buy` gets one branch for it:

        at a hut   the price is economy.value(hub, item) * 0.8   (unchanged)
        at a stall the price is WHAT THE PLAYER SET -- no discount, no haggle

    and the cart pays out of its own purse, in the lane, where its purse lives.

    Goods the carts will not carry are not relayed: a cart's goods are
    caravans.GOODS (leaf, drugs, drink). A rifle on the stall is kept and shown
    but no cart offers for it -- caravans do not trade arms anywhere in this
    world (economy.ARMS move between towns and the crown). That is a gap in the
    WORLD, not in the stall, and it is reported rather than invented.

5. THE PRICE

    The player sets it, per thing, on the stall's own screen, next to the
    inventory: select a product, set the price, done (`prices[item]`, whole
    coins, at least 1, up to 9999).

    A LOT IS (thing, grade), and a lot is the unit of price. A stack of SSS
    cigars is not a stack of F cigars and is not sold for the same coin: the
    world already keeps every shelf in lots by grade (economy.store_add /
    ledger_lots), and the stall now prices the same way.

    A lot that lands on the stall is PRICED AS IT LANDS, at the world's value
    OF THAT GRADE (economy.ITEM_VALUE x quality.SELL_VALUE[grade]): a cigar is
    20 at C, 6 at F, 120 at SSS. That is the anchor, not the decision. It is
    the player's price from the moment he changes it, and the switch (`on`) is
    how he takes everything off the market at once. A price of zero is not an
    offer, and set_price will not make one.

    THE PANEL, AND WHY IT IS SHAPED THIS WAY. The screen is a counter, a pack
    and one number to change, and quality must not turn that into a matrix of
    grades the player has to learn. So the rule is:

        YOU PRICE THE THING YOU CLICKED.

    The counter grid draws every stack with its grade on it. Left-clicking a
    stack selects THAT LOT; the column shows, in this order:

        Cigar -- grade S
        6 on the counter
        world value        120        <- what the grade is worth by the book
        the town pays      118        <- what a cart could resell it for
        YOUR PRICE         100        <- yours, with -10 -1 +1 +10

    Two anchors and one decision: you can see the ceiling (the town) and the
    book (the world), and undercut the first by as much as you like. Nothing is
    priced that has not been selected, so a player who never touches the price
    column still has a stall that sells at the world's rate -- and the moment
    he wants to be clever, the number he is being clever about is on screen.

6. THE MONEY

    Every purchase puts its coins INSIDE THE STALL (`stall.coins`). They stay
    there until the player collects them (the stall screen has a Collect row,
    which moves them to his pack) -- or until his men are paid.

    PAYROLL: work.payroll already takes the day's wages out of the chest in his
    hub. The stall's purse is the second place it looks, because money made on
    the stall is money he has, and a man's wage should not be missed because
    the chest was empty while a hundred coin sat in the counter. Chest first,
    then the stall; if neither can cover it, the day is missed (see 7).

7. PAY, AND THE TWO NEW RULES ABOUT QUITTING

    Until now a missed wage was instant desertion. That changes:

        a missed day is -20 regard (not a sacking)
        a man quits ONLY when his regard for the player is under 10

    so a man who is not paid once stays, and has an opinion about it; a man who
    is not paid three or four times running walks. `work.QUIT_BELOW = 10.0` and
    `work.UNPAID_BITTER = 20.0`, and `work.payroll` applies both.

8. SAVING

    The stall is in `placed_work`, so it would be written by `yard_work` -- but
    `yard_work` is restored as an `industry.Workplace`, which a stall is not.
    So: `yard_work` SKIPS stalls, and a separate `stalls` record carries
    everything a Workplace cannot: the rect, whether it is on, the coin, the
    prices, and the stock (`[item, count, quality]`). Restored in load_now
    after the hubs, so `hub` can be found again by containment.

    The workers' `to_market` flags are saved as a list of ids
    (`market_workers`) and applied after the workers themselves are restored.

9. WHAT THIS MODULE DOES NOT DO

    * It does not make a market out of the whole hub: one stall, one counter.
    * It does not sell to townsmen walking past the fence. Only carts buy, and
      only because the cart code already has a buying loop to hook into.
    * It does not price haggling, haggling is not in this world.
    * It does not let a hired man sell: he stocks the stall or the chest.
"""

from __future__ import annotations

import random

import pygame

import economy
import items
import plog

STALL_WOOD = 100               # what the timber costs
STALL_SLOTS = 32               # the same room as the player's pack
STALL_NAME = "Market stall"
DEFAULT_PRICE = 1              # never free: a price of nothing is not an offer


def _note(text: str) -> None:
    try:
        plog.log("STALL", text)
    except Exception:
        pass


def _grade_of(stack) -> int:
    """A stack's grade, and C for anything that has none."""
    import quality as _q
    q = getattr(stack, "quality", None)
    return int(_q.clamp(3 if q is None else q))


def _base_price(item: str, grade=None) -> int:
    """WHAT THE WORLD THINKS A THING OF THAT GRADE IS WORTH.

    The book's price times the grade's own multiplier -- economy.prospect with
    no particular place, which is what a shelf nobody has priced yet is worth.
    A cigar is 20 at C, 7 at F, 120 at SSS.
    """
    try:
        import quality as _q
        g = _q.clamp(3 if grade is None else grade)
        base = float(economy.ITEM_VALUE.get(item, 4) or 4)
        return max(DEFAULT_PRICE, int(round(base * _q.SELL_VALUE[g])))
    except Exception:
        return DEFAULT_PRICE


class Stall:
    """A counter in the player's hub: goods, prices, a purse and a switch.

    It answers every question the rest of the game asks of a `placed_work`
    building (rect, x, y, kind, draw) and, on the other side of the fence, it
    answers what a cart asks of a hut (ledger_goods, ledger_coins, is_hub).
    """

    kind = "stall"
    is_stall = True

    def __init__(self, owner, hub, x: float, y: float, seed: int = 0) -> None:
        import inventory as _inv
        self.owner = owner
        self.hub = hub
        self.x = float(x)
        self.y = float(y)
        self._rng_seed = int(seed) & 0xFFFFFFFF
        self.rng = random.Random(self._rng_seed)
        self.w, self.h = 96, 64
        self.rect = pygame.Rect(int(x - self.w / 2), int(y - self.h / 2),
                               self.w, self.h)
        self.base_y = y + self.h / 2.0
        self.sight_rect = self.rect.inflate(48, 48)
        self.door = (x, y + self.h / 2.0 + 12.0)
        self.worker = None                 # nothing to hire here
        self.name = STALL_NAME
        self.on = True
        self.coins = 0
        self.stock = _inv.Inventory(STALL_SLOTS)
        self.prices: dict = {}
        self.sales = 0                     # how many things have gone
        self._image: pygame.Surface | None = None

    # -- what is on the shelf ---------------------------------------------
    def held(self, item: str, grade=None) -> int:
        """How many of a thing -- of one grade, or of all of them."""
        n = 0
        for s in self.stock.slots:
            if s is None or s.defn.id != item:
                continue
            if grade is not None and _grade_of(s) != int(grade):
                continue
            n += int(s.count)
        return n

    def _default_price(self, item: str, grade) -> int:
        return _base_price(item, grade)

    def price_of(self, item: str, grade=None) -> int:
        """THE PLAYER'S PRICE FOR THAT LOT -- or, unset, the world's value of
        that grade. A price of zero means "not for sale" and never happens."""
        import quality as _q
        g = _q.clamp(3 if grade is None else grade)
        got = self.prices.get((item, int(g)))
        if got is None:
            return self._default_price(item, g)
        return max(0, int(got or 0))

    def price_set(self, item: str, grade) -> bool:
        """Whether the player has named a price, or this is still the book's."""
        import quality as _q
        return (item, int(_q.clamp(3 if grade is None else grade))) in self.prices

    def set_price(self, item: str, grade, price: int) -> int:
        import quality as _q
        g = int(_q.clamp(3 if grade is None else grade))
        price = max(DEFAULT_PRICE, min(9999, int(price)))
        self.prices[(item, g)] = price
        return price

    def lots(self) -> dict:
        """EVERY LOT ON THE COUNTER: {(item, grade): how many}."""
        out = {}
        for s in self.stock.slots:
            if s is None:
                continue
            key = (s.defn.id, _grade_of(s))
            out[key] = out.get(key, 0) + int(s.count)
        return out

    def offered(self, carryable=None) -> list:
        """[(item, grade, count, price)] -- what is there and switched on."""
        if not self.on:
            return []
        out = []
        for (item, grade), n in self.lots().items():
            if carryable is not None and item not in carryable:
                continue
            p = self.price_of(item, grade)
            if n > 0 and p > 0:
                out.append((item, grade, int(n), p))
        return out

    def space_for(self, item: str, count: int) -> int:
        """How many more would fit -- read from work.can_hold, one rule for
        chests, packs and stalls, so a full stall behaves like a full chest."""
        import work
        return int(work.can_hold(self.stock, item, count))

    def put(self, item: str, count: int = 1, quality=None) -> int:
        """A worker's product lands here. Returns how many fitted.

        The GRADE comes with it. A stack of SSS cigars put on a counter used to
        arrive as grade F -- the worst there is -- because the count was added
        without the grade, and the counter does not keep a grade of its own.
        """
        room = self.space_for(item, int(count))
        if room > 0:
            self.stock.add(item, room, quality)
        return int(max(0, room))

    def take(self, item: str, count: int = 1, grade=None) -> int:
        """Take from a lot -- that grade's stacks, and no others."""
        want = int(max(0, int(count)))
        got = 0
        for s in self.stock.slots:
            if got >= want or s is None or s.defn.id != item:
                continue
            if grade is not None and _grade_of(s) != int(grade):
                continue
            take = min(want - got, int(s.count))
            s.count -= take
            got += take
            if s.count <= 0:
                try:
                    self.stock.slots[self.stock.slots.index(s)] = None
                except ValueError:
                    pass
        return got

    # -- the sale, applied on THIS side of the fence ----------------------
    def sold(self, item: str, count: int, coins: int, who: str = "traveller",
             grade=None) -> bool:
        """A cart came and bought. The frame owns the goods and the money, so
        a sale is only a sale when it is applied here."""
        # A SALE IS WHAT ACTUALLY CHANGES HANDS. The lane reports what a cart
        # paid for; if this side holds fewer than it says, the fewer is sold
        # and the unit price is what was paid per unit -- nothing is created.
        unit = (int(coins) // int(count)) if int(count) > 0 else int(coins)
        n = self.take(item, count, grade)
        if n <= 0:
            return False
        paid = n * (unit if unit > 0 else self.price_of(item))
        self.coins = int(self.coins) + int(max(0, paid))
        self.sales += n
        _note("SOLD %3d %-14s at %4d  to %-16s | stall purse %d"
              % (n, item, int(max(0, paid)) // max(1, n), who, self.coins))
        return True

    def collect(self):
        """The counter is emptied into the player's pack. Returns how much."""
        got = int(self.coins)
        self.coins = 0
        return got

    def spend(self, amount: int) -> bool:
        """Wages out of the counter. False if the counter cannot cover it."""
        amount = int(amount)
        if amount <= 0 or int(self.coins) < amount:
            return False
        self.coins = int(self.coins) - amount
        return True

    # -- the other side of the fence: a cart's questions ------------------
    @property
    def is_hub(self) -> bool:
        return True

    def relay(self) -> tuple:
        """WHAT THE LANE IS TOLD, once a second. Only what a cart can carry --
        a cart has no business with a rifle, and carrying one would be cargo it
        could not count (caravans.GOODS)."""
        try:
            import caravans
            carryable = set(caravans.GOODS)
        except Exception:
            carryable = set()
        lots = {}
        for item, grade, n, p in self.offered(carryable):
            lots.setdefault(item, {})[int(grade)] = [int(n), int(p)]
        return (round(self.x, 1), round(self.y, 1), self.name,
                bool(self.on), lots)

    # -- drawing ----------------------------------------------------------
    @property
    def image(self) -> pygame.Surface:
        if self._image is None:
            self._image = self._render()
        return self._image

    def _render(self) -> pygame.Surface:
        """A stall: a counter, four posts, a canvas roof, and goods on it."""
        s = pygame.Surface((self.w, self.h + 26), pygame.SRCALPHA)
        rng = self.rng
        cx = self.w // 2
        # the counter
        pygame.draw.rect(s, (122, 92, 60), (8, self.h - 26, self.w - 16, 22),
                         border_radius=3)
        pygame.draw.rect(s, (86, 64, 42), (8, self.h - 26, self.w - 16, 22), 2,
                         border_radius=3)
        # posts
        for px in (10, self.w - 16):
            pygame.draw.rect(s, (92, 70, 46), (px, 8, 6, self.h - 26))
        # the canvas roof, striped
        for i in range(6):
            x0 = 4 + i * (self.w - 8) // 6
            x1 = 4 + (i + 1) * (self.w - 8) // 6
            col = (196, 176, 140) if i % 2 == 0 else (168, 78, 62)
            pygame.draw.polygon(s, col, [(x0, 20), (x1, 20), (x1, 6), (x0, 6)])
        pygame.draw.rect(s, (110, 90, 66), (4, 4, self.w - 8, 18), 2,
                         border_radius=2)
        # a few things out on the counter
        for i in range(4):
            gx = 18 + i * 18
            gy = self.h - 32 + rng.randint(-3, 1)
            pygame.draw.rect(s, rng.choice([(190, 160, 96), (150, 96, 70),
                                            (120, 140, 96)]),
                             (gx, gy, 9, 8), border_radius=2)
        return s

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        img = self.image
        screen.blit(img, (int(self.x - cam_x - self.w / 2),
                          int(self.y - cam_y - self.h / 2 + 8)))
        # A SIGN WHEN IT IS SHUT: the world can see whether he is trading.
        if not self.on:
            try:
                font = pygame.font.SysFont("dejavusans", 12, bold=True)
                tag = font.render("SHUT", True, (230, 120, 100))
                screen.blit(tag, (int(self.x - cam_x - tag.get_width() / 2),
                                  int(self.y - cam_y - self.h / 2 - 6)))
            except Exception:
                pass


# -- the player's stalls ----------------------------------------------------
def stalls_of(player) -> list:
    held = getattr(player, "stalls", None)
    if not isinstance(held, list):
        held = player.stalls = []
    return held


def add(player, hub, x: float, y: float):
    """BUILD A COUNTER -- AND ONLY INSIDE THE PLAYER'S OWN YARD.

    A stall with no hub is a counter standing in a settlement square that
    nobody built and anybody may empty: my own test probes made two of those
    by passing `None`, and one of them was found in a live game with coin in
    it. There is no legitimate way to have one, so this refuses.
    """
    if hub is None or not getattr(hub, "is_player_hub", False):
        _note("REFUSED a stall at %d,%d: it is not inside a hub of the player's"
              % (int(x), int(y)))
        return None
    if not hub.fence_rect.colliderect(pygame.Rect(int(x) - 48, int(y) - 32,
                                                  96, 64)):
        _note("REFUSED a stall at %d,%d: %s's fence does not cover it"
              % (int(x), int(y), getattr(hub, "name", "the hub")))
        return None
    st = Stall(player, hub, x, y, abs(hash((x, y, len(stalls_of(player)))))
               & 0x7FFFFFFF)
    stalls_of(player).append(st)
    _note("BUILT at %d,%d in %s" % (int(x), int(y),
                                    getattr(hub, "name", "the wild")))
    return st


def in_hub(player, hub) -> Stall | None:
    """The stall standing in this hub, if any."""
    for st in stalls_of(player):
        if hub is not None and getattr(st, "hub", None) is hub:
            return st
    return None


def nearest(player, x: float, y: float, within: float = 90.0) -> Stall | None:
    best, bd = None, within * within
    for st in stalls_of(player):
        d = (st.x - x) ** 2 + (st.y - y) ** 2
        if d <= bd:
            best, bd = st, d
    return best


def to_data(player) -> list:
    """Everything a Workplace record cannot hold."""
    out = []
    for st in stalls_of(player):
        if (getattr(st, "hub", None) is None
                or not getattr(st.hub, "is_player_hub", False)):
            _note("NOT SAVED a stall at %d,%d -- it has no hub of the player's"
                  % (int(st.x), int(st.y)))
            continue
        stock = []
        for s in st.stock.slots:
            if s is not None:
                stock.append([s.defn.id, int(s.count), s.quality])
        hub = getattr(st, "hub", None)
        out.append({
            "rect": [st.rect.x, st.rect.y, st.rect.w, st.rect.h],
            "hub": ([hub.fence_rect.x, hub.fence_rect.y,
                     hub.fence_rect.w, hub.fence_rect.h] if hub is not None else None),
            "on": bool(st.on),
            "coins": int(st.coins),
            "prices": [[k[0], int(k[1]), int(v)] for k, v in st.prices.items()],
            "stock": stock,
            "sales": int(st.sales),
        })
    return out


def from_data(player, recs, hubs) -> list:
    """Rebuilt after the hubs, so a stall can find the yard it stands in."""
    out = []
    for rec in recs or ():
        try:
            hub = None
            if rec.get("hub"):
                want = pygame.Rect(*[int(v) for v in rec["hub"]])
                for h in hubs:
                    if (getattr(h, "is_player_hub", False)
                            and h.fence_rect == want):
                        hub = h
                        break
            r = pygame.Rect(*[int(v) for v in rec["rect"]])
            if hub is None:
                # A STALL WITHOUT ITS YARD IS NOT RESTORED. It used to be given
                # whatever hub happened to overlap it -- or none at all, which
                # is how a counter stood in a settlement square and paid out.
                _note("DROPPED a stall at %d,%d: its hub is not in the save"
                      % (r.centerx, r.centery))
                continue
            st = add(player, hub, r.centerx, r.centery)
            if st is None:
                continue
            st.on = bool(rec.get("on", True))
            st.coins = int(rec.get("coins", 0) or 0)
            st.sales = int(rec.get("sales", 0) or 0)
            st.prices = {}
            for row in rec.get("prices") or ():
                if isinstance(row, (list, tuple)) and len(row) == 3:
                    st.prices[(row[0], int(row[1]))] = int(row[2])
            st.stock = __import__("inventory").Inventory(STALL_SLOTS)
            for row in rec.get("stock") or ():
                item, count = row[0], int(row[1])
                q = row[2] if len(row) > 2 else None
                st.stock.add(item, count, q)
            out.append(st)
        except Exception as exc:
            _note("RESTORE-ERROR %r" % (exc,))
    if out:
        _note("RESTORED %d stall(s): %s"
              % (len(out), ", ".join("%d goods, %d coin"
                                     % (sum(1 for s in st.stock.slots if s),
                                        st.coins) for st in out)))
    return out
