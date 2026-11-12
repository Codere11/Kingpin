"""Villager trade menu.

Sell tobacco (3 = 1 coin), but only if it is good enough for them -- and you
pick which stack/quality to sell. Buy seeds, ammo, a rifle and other tools.
Villagers want a limited amount before they need a 10-minute restock.
"""

from __future__ import annotations

import pygame

import economy
import face
import items
import nemesis
from quality import GRADES, SELL_VALUE, letter, sell_coins

BORDER = (72, 72, 80)
TEXT = (222, 222, 228)
DIM = (140, 140, 150)
ACCENT = (222, 176, 88)

SELL_RATE = 3          # leaf per coin
LEAF_ITEMS = ("tobacco", "red_mushroom", "agave", "chili")
RESTOCK_SECONDS = 600.0

BUY = [
    ("seed_bag", 5, "Tobacco Seeds"),
    ("wheat_seed", 5, "Wheat Seeds"),
    ("ammo", 1, "Ammo"),
    ("rifle", 20, "Rifle"),
    ("axe", 10, "Axe"),
    ("shovel", 10, "Shovel"),
    ("watering_can", 10, "Watering Can"),
    ("first_aid", 10, "First-Aid Kit"),
]


# WHAT A MAN WILL BUY OFF THE PLAYER IN ONE DAY.
#
# Town trade already stops at what a man WANTS, but that answer comes from his
# stock -- and for a man the frame is not walking, his stock is whatever it was
# when he was last near the player. So the player could sell the same eight
# logs over and over to a man whose real woodpile was a hundred logs deep, and
# leave a village destitute with nothing but firewood. The budget below does
# not depend on his larder being fresh: it is what the player has sold HIM
# today.
DAILY_DAYS_WORTH = 3.0      # three days of a good, no matter the purse
DAILY_TOOLS = 1             # one tool, or one gun
DAILY_SEEDS = 30            # thirty seeds in all, not of a kind

# A DAY'S WORTH OF EACH THING, from what was measured in a running game
# (NEEDS.md): a person eats 1.69 meals a day and a house burns 5 logs; an
# addict smokes or drinks 1.01; a bench works through eight leaf a day; a
# smith's forge and a soldier's range have their own appetites.
PER_DAY = {"bread": 2.0, "berries": 2.0, "cactus_fruit": 2.0,
           "raw_meat": 2.0, "cooked_meat": 2.0, "wood": 5.0,
           "cigar": 1.0, "beer": 1.0, "liqueur": 1.0, "mezcal": 1.0,
           "tobacco": 8.0, "agave": 8.0, "red_mushroom": 8.0,
           "dried_mushroom": 8.0, "iron": 8.0, "ammo": 10.0,
           "wheat_wort": 20.0, "berry_wort": 20.0, "agave_wort": 20.0}
DEFAULT_PER_DAY = 1.0

_NOW = [0.0]
_SOLD = {}                  # (buyer id, day) -> {"goods": {}, "tools": n, "seeds": n}


def set_now(now: float) -> None:
    _NOW[0] = float(now)


def _day() -> int:
    import economy
    return int(_NOW[0] // economy.DAY_LENGTH)


def _book(npc) -> dict:
    key = (id(npc), _day())
    got = _SOLD.get(key)
    if got is None:
        got = {"goods": {}, "tools": 0, "seeds": 0}
        _SOLD[key] = got
        if len(_SOLD) > 4000:                 # never grow without bound
            for old in list(_SOLD)[:1000]:
                _SOLD.pop(old, None)
    return got


def daily_left(npc, item: str) -> int:
    """HOW MANY MORE OF THIS THE PLAYER MAY SELL HIM TODAY."""
    import economy
    book = _book(npc)
    if item in economy.SEEDS:
        return max(0, DAILY_SEEDS - int(book["seeds"]))
    if item in economy.TOOLS or item in economy.ARMS:
        return max(0, DAILY_TOOLS - int(book["tools"]))
    per_day = PER_DAY.get(item, DEFAULT_PER_DAY)
    cap = int(round(DAILY_DAYS_WORTH * per_day))
    return max(0, cap - int(book["goods"].get(item, 0)))


def record_sale(npc, item: str, count: int) -> None:
    import economy
    if count <= 0:
        return
    book = _book(npc)
    if item in economy.SEEDS:
        book["seeds"] = int(book["seeds"]) + int(count)
    elif item in economy.TOOLS or item in economy.ARMS:
        book["tools"] = int(book["tools"]) + int(count)
    else:
        book["goods"][item] = int(book["goods"].get(item, 0)) + int(count)


class TradeMenu:
    def __init__(self, player_inv, npc, player=None) -> None:
        self.inv = player_inv
        self.player = player
        self.npc = npc
        self.hover = -1
        self.scroll = 0
        self._wants: dict[str, int] = {}
        self.font_title = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 15, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12, bold=True)

    @staticmethod
    def _fit(font, text, max_w, color):
        if font.size(text)[0] <= max_w:
            return font.render(text, True, color)
        trimmed = text
        while trimmed and font.size(trimmed + "...")[0] > max_w:
            trimmed = trimmed[:-1]
        return font.render(trimmed + "...", True, color)

    # -- selling ------------------------------------------------------------
    def _quality_of(self, index: int) -> int:
        stack = self.inv.slots[index]
        if stack is None or stack.quality is None:
            return 0
        return stack.quality

    def _want(self, item: str) -> int:
        """HOW MANY OF THESE THIS MAN WANTS -- the villagers' own rule.

        economy.wants() is what a villager answers when another villager asks
        to sell him something: a larder to fill, a taste he has not got, a tool
        about to break, the leaf his bench runs on, a mash tun to fill, iron
        for the forge, wood for a cold hearth. The trade menu asked the
        village's price list instead and called it desire, which is why a
        farmer would buy a pickaxe and a man with a full woodpile would buy
        more wood.

        It is asked ONCE and kept, because one of its answers is a coin flip:
        asking again while drawing the row could list a thing and then refuse
        to sell it.
        """
        if item not in self._wants:
            # THE MENU MUST NEVER BE THE THING THAT KILLS THE GAME. `wants()`
            # reads a villager's larder, habit, thirst, house and a coin flip
            # from his own generator; a SOLDIER has a rifle and a wage and none
            # of the rest, and asking him threw AttributeError from inside the
            # economy while the trade menu was being DRAWN. A man the economy
            # cannot describe simply wants nothing.
            try:
                self._wants[item] = int(economy.wants(self.npc, item))
            except Exception:
                self._wants[item] = 0
        return self._wants[item]

    def _leaf_count(self) -> int:
        return sum(self.inv.count_of(i) for i in LEAF_ITEMS)

    def _unit_price(self, item: str, grade: int) -> int:
        """What THIS villager will pay for one unit of our goods. His own
        reference price, our quality, and his own craving for it.

        WHOLE COIN, always. The village's own ledger keeps fractions, but a
        price a man is paid cannot be 16.234314 coins, and that is what the
        purse was filling up with.
        """
        village = getattr(self.npc, "village", None)
        fallback = max(1, int(SELL_VALUE[grade] * 4))
        if village is None:
            return fallback
        base = max(1, round(economy.value(village, item) * SELL_VALUE[grade]))
        return max(1, int(economy.bid_price(village, self.npc, item, base)))

    def _sell_amount(self, index: int):
        stack = self.inv.slots[index]
        if stack is None:
            return 0, 0
        item = stack.defn.id
        unit = self._unit_price(item, self._quality_of(index))
        if unit <= 0:
            return 0, 0                 # he is not in the market for this
        # EXACTLY WHAT HE WANTS, no more: one spare shovel while the old one is
        # nearly dead, a house's stack of firewood, a larder's worth of bread.
        demand = self._want(item)
        affordable = int(self.npc.coins / unit) if unit > 0 else 0
        today = daily_left(self.npc, item)
        sold = max(0, min(stack.count, demand, affordable, today))
        return sold, sold * unit

    def _sell_price(self, index: int):
        """(enabled, label) for a sell row -- explaining any refusal."""
        sold, coins = self._sell_amount(index)
        if sold > 0:
            return True, "+%d coin%s" % (coins, "" if coins == 1 else "s")
        stack = self.inv.slots[index]
        have = stack.count if stack is not None else 0
        if self.npc.trade_demand <= 0:
            return False, "not buying right now"
        if have <= 0:
            return False, "nothing to sell"
        if daily_left(self.npc, stack.defn.id) <= 0:
            return False, "he's had his fill today"
        return False, "he can't afford it"

    def _entries(self):
        """Sell rows (one per acceptable tobacco stack) then buy rows."""
        pref = getattr(self.npc, "quality_pref", 0)
        sell = []
        for i, stack in enumerate(self.inv.slots):
            if stack is None:
                continue
            item = stack.defn.id
            if item in LEAF_ITEMS:
                if (self._quality_of(i) >= pref and self._want(item) > 0
                        and self._sell_amount(i)[0] > 0):
                    sell.append(("sell", i))
            elif self._want(item) > 0 and self._sell_amount(i)[0] > 0:
                # ...AND ONLY WHAT HE WANTS, AND ONLY AS MUCH AS HE WANTS --
                # and only if he can actually pay for it. A row he cannot fill
                # is a row that says "he can't afford it" and nothing else.
                sell.append(("sell", i))
        sell.sort(key=lambda entry: self._quality_of(entry[1]))
        if not sell and self._leaf_count() > 0:
            sell.append(("sell_none", None))
        return sell + self._buy_entries()

    def _buy_entries(self):
        """What THIS villager actually has on him, at his own asking price --
        not a fixed catalogue. An empty-handed man has nothing to sell you."""
        village = getattr(self.npc, "village", None)
        out = []
        for item, qty in sorted(getattr(self.npc, "stock", {}).items()):
            if qty <= 0:
                continue
            try:
                name = items.get(item).name
            except Exception:
                continue
            price = (int(economy.ask_price(village, self.npc, item))
                     if village is not None else 1)
            out.append(("buy", (item, max(1, price), name)))
        return out

    def _layout(self, sw: int, sh: int):
        entries = self._entries()
        row_h = 42
        width = 500
        # Never taller than the window: what does not fit is scrolled to.
        shown = max(1, min(len(entries), (sh - 150) // row_h))
        height = 86 + shown * row_h + 14
        x0 = (sw - width) // 2
        y0 = (sh - height) // 2
        self.scroll = max(0, min(self.scroll, max(0, len(entries) - shown)))
        view = entries[self.scroll:self.scroll + shown]
        rects = [pygame.Rect(x0 + 14, y0 + 78 + i * row_h, width - 28, row_h - 8)
                 for i in range(len(view))]
        return pygame.Rect(x0, y0, width, height), view, rects

    def _scroll_by(self, rows: int) -> None:
        surface = pygame.display.get_surface()
        if surface is None:
            return
        self.scroll += rows
        self.scroll = max(0, self.scroll)
        self._layout(*surface.get_size())       # clamps against the last row

    def handle_event(self, event) -> bool:
        surface = pygame.display.get_surface()
        if surface is None:
            return False
        _, entries, rects = self._layout(*surface.get_size())
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_by(-event.y)
            return True
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i, rect in enumerate(rects):
                if rect.collidepoint(event.pos):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(rects):
                if rect.collidepoint(event.pos):
                    return self._activate(entries[i])
        return False

    def _activate(self, entry) -> bool:
        kind, data = entry
        if kind == "sell":
            index = data
            sold, coins = self._sell_amount(index)
            stack = self.inv.slots[index]
            if sold <= 0 or stack is None:
                return False
            stack.count -= sold
            if stack.count <= 0:
                self.inv.slots[index] = None
            self._wants.pop(stack.defn.id, None)      # his want has changed
            self.inv.add("coin", coins)
            record_sale(self.npc, stack.defn.id, sold)   # the day's budget
            # A LUXURY KEEPS WHO SOLD IT. If the militia catches him drinking
            # it and he talks, the name he gives is the player's.
            try:
                import economy as _e
                if stack.defn.id in _e.LUXURY:
                    d = getattr(self.npc, "_seller_of", None)
                    if d is None:
                        d = {}
                        self.npc._seller_of = d
                    d[stack.defn.id] = "player"
            except Exception:
                pass
            # EVERY DEAL TEACHES BOTH OF THEM SOMETHING ABOUT THE OTHER.
            _cap = getattr(self.npc, "social_cap", 3.0)
            self.npc.social = min(_cap, getattr(self.npc, "social", 0.0) + 0.05)
            _pl = getattr(self, "player", None)
            if _pl is not None:
                _pl.social = min(10.0, getattr(_pl, "social", 0.0) + 0.08)
            self.npc.coins = max(0, self.npc.coins - coins)
            self.npc.trade_demand = max(0, self.npc.trade_demand - sold)
            if self.npc.trade_demand <= 0:
                self.npc.restock_timer = RESTOCK_SECONDS
            # SELLING LEAF OR A MADE DRUG IS AN OFFENCE, and any agent close
            # enough to have watched the deal now knows it.
            _pl = getattr(self, "player", None)
            if _pl is not None and stack.defn.id in (nemesis.ILLEGAL_LEAF
                                                     + nemesis.ILLEGAL_DRUGS):
                try:
                    nemesis.note_offence_seen(_pl, "sold", stack.defn.id)
                except Exception:
                    pass
            self._smirk()          # he bought off you, and he knows it
            return True
        if kind == "sell_none":
            return False
        item_id, cost, _name = data
        if self.inv.count_of("coin") < cost:
            return False
        self.inv.consume("coin", cost)
        self.inv.add(item_id, 1)
        self.npc.stock[item_id] = self.npc.stock.get(item_id, 0) - 1   # his stock
        self._wants.clear()
        self.npc.coins += cost
        self._smirk()              # he sold you something, and he knows it
        return True

    def _smirk(self) -> None:
        """A trader who has just done a deal wears the sleazy face.

        The menu moves the coin ITSELF rather than going through
        economy._settle, so it has to raise this on its own -- otherwise the
        one trader the player deals with by hand would be the only trader in
        the world who never smiled at him.
        """
        if getattr(self.npc, "job", None) == "trader":
            self.npc.sly_flash = face.SLY_SECONDS

    # -- drawing ------------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        sw, sh = screen.get_size()
        panel, entries, rects = self._layout(sw, sh)

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (20, 20, 24, 242), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, BORDER, board.get_rect(), width=2, border_radius=12)
        screen.blit(board, panel.topleft)

        title = self.font_title.render(
            f"{self.npc.name}  \u00b7  {self.npc.occupation()}", True, TEXT)
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 8))
        pref = getattr(self.npc, "quality_pref", 0)
        restock = ""
        if self.npc.restock_timer > 0.0:
            restock = "  (restocking %d:%02d)" % (int(self.npc.restock_timer // 60),
                                                  int(self.npc.restock_timer % 60))
        if self.npc.trade_demand > 0:
            want = "will buy up to %d" % self.npc.trade_demand
        else:
            want = "not buying right now"
        sub_text = (
            f"buys {letter(pref)}+ · {want} · "
            f"he has {int(self.npc.coins)} coins · you have {int(self.inv.count_of('coin'))}"
            f"{restock}")
        sub = self._fit(self.font_small, sub_text, panel.width - 24, DIM)
        screen.blit(sub, (panel.centerx - sub.get_width() // 2, panel.top + 34))

        for i, (entry, rect) in enumerate(zip(entries, rects)):
            kind, data = entry
            hovered = (i == self.hover)
            pygame.draw.rect(screen, (46, 46, 52) if hovered else (34, 34, 40),
                             rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT if hovered else BORDER, rect,
                             width=2, border_radius=8)

            if kind == "sell":
                sold, _coins = self._sell_amount(data)
                enabled = sold > 0
                grade = self._quality_of(data)
                stack = self.inv.slots[data]
                leaf_name = stack.defn.name.lower() if stack is not None else "leaf"
                icon = items.icon(stack.defn.id if stack is not None else "tobacco",
                                  rect.height - 12)
                # A GRADE ONLY WHERE A GRADE MEANS SOMETHING. Wood is wood and
                # iron is iron; showing "A wood" was noise, and worse, a lie --
                # the grade of an ungraded stack is meaningless.
                tag = (GRADES[grade] + " ") if (stack is not None
                                               and stack.defn.quality) else ""
                label = (f"Sell {sold} {tag}{leaf_name}" if enabled
                         else f"Sell {tag}{leaf_name}")
                enabled, price = self._sell_price(data)
            elif kind == "sell_none":
                enabled = False
                icon = items.icon("tobacco", rect.height - 12)
                label = "Won't buy your leaf"
                price = f"needs {letter(pref)}+"
            else:
                item_id, cost, name = data
                enabled = self.inv.count_of("coin") >= cost
                icon = items.icon(item_id, rect.height - 12)
                label = name
                price = "%d coin%s" % (cost, "" if cost == 1 else "s")

            screen.blit(icon, (rect.left + 6, rect.centery - icon.get_height() // 2))
            text = self.font.render(label, True, TEXT if enabled else DIM)
            screen.blit(text, (rect.left + icon.get_width() + 14,
                               rect.centery - text.get_height() // 2))
            pr = self.font.render(price, True,
                                  (226, 194, 112) if enabled else (150, 112, 112))
            screen.blit(pr, (rect.right - pr.get_width() - 10,
                             rect.centery - pr.get_height() // 2))

        hint = self.font_small.render("click to trade   ·   E / Esc to close", True, DIM)
        screen.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 20))
