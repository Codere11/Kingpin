"""A village notice board: a live read-out of every villager's purse and of the
village ledger.

It deliberately does **not** pause the world -- the numbers move as you watch,
so speeding time up shows the economy working.
"""

from __future__ import annotations

import pygame

import crop
import economy
import items

ROW = 15

TRADE_NAMES = {
    "farm": "Farmer", "logger": "Logger", "trader": "Trader",
    "smith": "Smith", "mine": "Miner", "lab": "Artisan",
    "brewery": "Brewer", "defender": "Guard", "commander": "Commander",
}


class BoardPanel:
    def __init__(self) -> None:
        self.scroll = 0
        # Set by main: the player's pockets and his house chest, which is what
        # a man's tax is worked out from.
        self.inv = None
        self.chest = None
        self.player = None
        self.tax_day = -1
        self.paid_day = -1
        self.tax_button = None
        self.debt_button = None
        self.sell_button = None
        self.notice = ""
        self.notice_t = 0.0
        self.job_rows: list = []       # (rect, village, trade) for the mouse
        self.font_title = pygame.font.SysFont("dejavusans", 19, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 15, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 12)

    def _holdings_value(self) -> int:
        """EVERYTHING A MAN IS WORTH: his pack and his house chest.

        Coin counts, and so do the goods -- a hundred cigars in a chest are
        wealth whether or not they have been sold yet.
        """
        total = 0
        for holder in (self.inv, self.chest):
            if holder is None:
                continue
            for stack in getattr(holder, "slots", ()):
                if stack is None:
                    continue
                item = stack.defn.id
                unit = (1 if item == "coin"
                        else economy.ITEM_VALUE.get(item, 4))
                total += int(unit) * int(stack.count)
        return total

    def tax_due(self) -> int:
        """AN UNEMPLOYED MAN OWES NOTHING.

        The tax is a working man's share of what the village has enabled him to
        earn. With no post there is no earning, and a charge for standing in the
        square is a fine for being poor. The three-day window in main already
        checks player.job before it banishes anybody -- this is the other half,
        so the board does not ask him for money he does not owe.
        """
        if self.player is not None and getattr(self.player, "job", None) is None:
            return 0
        return int(economy.tax_due(self._holdings_value()))

    # THE LEDGER BUYS FROM ITS OWN PEOPLE, AT A FRACTION. It has to buy below
    # the market price -- it is the thing that resells, and it pays the wages
    # out of the difference -- so a working man gets a third of what the goods
    # are worth over the counter. That is the deal: the town takes a cut and
    # in exchange it buys ALL of it, today, without walking the street looking
    # for a man who happens to want a cigar.
    LEDGER_BUYS = 0.34        # a third of the market price
    LEDGER_MIN = 1            # and never less than a coin apiece

    def _sellable(self) -> list:
        """The stacks in his pack the ledger will take, and their price."""
        if self.inv is None:
            return []
        out = []
        for i, stack in enumerate(self.inv.slots):
            if stack is None:
                continue
            item = stack.defn.id
            if item == "coin" or item not in economy.LUXURY:
                continue                     # the town buys FINISHED goods
            village = getattr(self.player, "settled_at", None)
            base = (economy.value(village, item) if village is not None
                    else economy.ITEM_VALUE.get(item, 4))
            unit = max(self.LEDGER_MIN, int(round(base * self.LEDGER_BUYS)))
            out.append((i, item, int(stack.count), unit))
        return out

    def handle_event(self, event) -> bool:
        """Returns True if the panel should close."""
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_e, pygame.K_ESCAPE):
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 2)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, v, kind in self.job_rows:
                if not rect.collidepoint(event.pos):
                    continue
                if self.player is None:
                    break
                if v.hire(self.player, kind):
                    self.notice, self.notice_t = (
                        "Taken   -   %s in %s" % (TRADE_NAMES.get(kind, kind),
                                                  v.name)), 3.0
                else:
                    self.notice, self.notice_t = "That post is gone", 2.5
                return False
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.sell_button is not None
                and self.sell_button.collidepoint(event.pos)
                and self.inv is not None and self.player is not None):
            village = getattr(self.player, "settled_at", None)
            if village is None:
                self.notice, self.notice_t = "You have no village to sell to", 2.5
            else:
                units = 0
                coin = 0
                for i, item, qty, unit in self._sellable():
                    space = max(0, int(village.ledger_coins))
                    if space <= 0:
                        break
                    can = min(qty, space // max(1, unit))
                    if can <= 0:
                        continue
                    grade = 3
                    try:
                        grade = int(self.inv.slots[i].grade)
                    except Exception:
                        pass
                    self.inv.consume(item, can)
                    economy.store_add(village, item, can, grade)
                    village.ledger_coins -= can * unit
                    coin += can * unit
                    units += can
                if units:
                    self.inv.add("coin", coin)
                    self.notice, self.notice_t = (
                        "Sold %d to the ledger   +%d coin" % (units, coin)), 3.0
                else:
                    self.notice, self.notice_t = ("The ledger is empty -- "
                                                  "nothing to buy with"), 3.0
            return False
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.debt_button is not None
                and self.debt_button.collidepoint(event.pos)
                and self.inv is not None and self.player is not None):
            # THE DEBT IS PAID DOWN AS FAR AS THE COIN GOES, not all at once --
            # a man who is three hundred short should be able to hand over what
            # he has instead of being told to come back richer.
            owed = max(0, int(getattr(self.player, "debt", 0)))
            purse = self.inv.count_of("coin")
            if owed <= 0:
                self.notice, self.notice_t = "The ledger is clear", 2.5
            elif purse <= 0:
                self.notice, self.notice_t = "You have no coin at all", 2.5
            else:
                give = min(purse, owed)
                self.inv.consume("coin", give)
                self.player.debt = owed - give
                self.player.debt_paid = getattr(self.player, "debt_paid", 0) + give
                self.notice, self.notice_t = ("Paid %d toward the debt -- %d left"
                                              % (give, self.player.debt)), 3.0
            return False
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.tax_button is not None
                and self.tax_button.collidepoint(event.pos)
                and self.inv is not None):
            due = self.tax_due()
            if due <= 0:
                self.notice, self.notice_t = "Nothing owed", 2.5
            elif self.inv.count_of("coin") < due:
                self.notice, self.notice_t = "Not enough coin (%d owed)" % due, 2.5
            else:
                self.inv.consume("coin", due)
                self.paid_day = self.tax_day
                if self.player is not None:
                    self.player.tax_paid += due
                self.notice, self.notice_t = "Taxes paid   -%d coin" % due, 2.5
        return False

    @staticmethod
    def _panel(vw: int, vh: int) -> pygame.Rect:
        w, h = min(920, vw - 60), min(660, vh - 60)
        return pygame.Rect((vw - w) // 2, (vh - h) // 2, w, h)

    def _nearest(self, village, count: int = 3) -> list:
        """This board's village and the two nearest others.

        A man who finds nothing going where he stands should be able to see who
        IS hiring without walking the country to find out -- that is what a
        notice board is FOR.
        """
        out = [village]
        reg = getattr(village, "registry", None)
        towns = list(getattr(reg, "villages", ()) or ()) if reg is not None else []
        if not towns:
            return out
        others = [v for v in towns
                  if v is not village and getattr(v, "name", None)]
        others.sort(key=lambda v: ((v.x - village.x) ** 2
                                   + (v.y - village.y) ** 2))
        return out + others[:max(0, count - 1)]

    def draw(self, screen: pygame.Surface, village) -> None:
        vw, vh = screen.get_size()
        panel = self._panel(vw, vh)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 158))
        screen.blit(shade, (0, 0))
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (26, 23, 20, 246), board.get_rect(), border_radius=12)
        pygame.draw.rect(board, (154, 110, 62), board.get_rect(), width=2,
                         border_radius=12)
        screen.blit(board, panel.topleft)

        title = self.font_title.render("%s   NOTICE BOARD" % village.name, True,
                                       (240, 230, 206))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 12))

        lx = panel.left + 30
        rx = panel.right - 30
        y = panel.top + 54

        # ---- YOUR ACCOUNT -------------------------------------------------
        # WHO THE BOARD THINKS HE IS. The letter told him what he does and what
        # he owes, and this is the same two sentences in the same place every
        # day, next to the button that does something about it.
        self.debt_button = None
        if self.player is not None:
            box = pygame.Rect(lx, y, panel.width - 60, 66)
            pygame.draw.rect(screen, (40, 34, 26), box, border_radius=6)
            pygame.draw.rect(screen, (154, 110, 62), box, 1, border_radius=6)
            nm = getattr(self.player, "name", None) or "A stranger"
            trade = getattr(self.player, "job", None)
            town = getattr(self.player, "settled_at", None)
            if trade:
                where = (" in %s" % town.name) if town is not None else ""
                line = "%s   --   %s%s" % (nm, TRADE_NAMES.get(trade, trade).lower(), where)
                col = (216, 210, 190)
            else:
                line = "%s   --   no trade, no post, no wage" % nm
                col = (196, 172, 140)
            screen.blit(self.font.render(line[:68], True, col), (lx + 12, y + 10))
            owed = max(0, int(getattr(self.player, "debt", 0)))
            if owed > 0:
                screen.blit(self.font_small.render(
                    "The ledger holds your name for %d coin" % owed, True,
                    (214, 150, 130)), (lx + 12, y + 34))
                self.debt_button = pygame.Rect(box.right - 138, y + 30, 126, 24)
                hot = self.debt_button.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(screen, (128, 74, 40) if hot else (86, 52, 30),
                                 self.debt_button, border_radius=5)
                pygame.draw.rect(screen, (200, 150, 96), self.debt_button, 1,
                                 border_radius=5)
                lbl = self.font_small.render("PAY WHAT YOU CAN", True, (246, 236, 214))
                screen.blit(lbl, (self.debt_button.centerx - lbl.get_width() // 2,
                                  self.debt_button.centery - lbl.get_height() // 2))
            else:
                screen.blit(self.font_small.render(
                    "The ledger is clear. Nothing is owed.", True,
                    (150, 190, 140)), (lx + 12, y + 34))
            # ---- AND THE LEDGER BUYS --------------------------------
            y += 44
            rows = self._sellable()
            trade = getattr(self.player, "job", None)
            if trade:
                if rows:
                    share = sum(q * u for _i, _it, q, u in rows)
                    txt = ("%d goods in your pack -- the ledger pays %d coin for them"
                           % (sum(q for _i, _it, q, _u in rows), share))
                    col = (206, 200, 180)
                else:
                    txt = "Nothing the ledger buys. Bring it finished goods."
                    col = (176, 164, 146)
                screen.blit(self.font_small.render(txt, True, col), (lx + 12, y))
                self.sell_button = pygame.Rect(box.right - 138, y - 4, 126, 22)
                hot = self.sell_button.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(screen, (58, 84, 52) if hot else (38, 56, 36),
                                 self.sell_button, border_radius=5)
                pygame.draw.rect(screen, (140, 190, 120), self.sell_button, 1,
                                 border_radius=5)
                lbl = self.font_small.render("SELL TO THE LEDGER", True,
                                             (234, 244, 226))
                screen.blit(lbl, (self.sell_button.centerx - lbl.get_width() // 2,
                                  self.sell_button.centery - lbl.get_height() // 2))
            y += 26

        screen.blit(self.font.render("WORK GOING", True, (238, 224, 190)), (lx, y))
        y += 28

        me = getattr(self.player, "job", None)
        my_town = getattr(self.player, "settled_at", None)
        self.job_rows = []
        any_post = False
        for v in self._nearest(village, 3):
            posts = v.open_posts()
            if not posts:
                continue
            any_post = True
            mine = (my_town is v)
            hdr = v.name + ("     YOUR VILLAGE" if mine else "")
            screen.blit(self.font.render(hdr, True,
                                         (226, 198, 120) if mine else (200, 196, 186)),
                        (lx, y))
            y += 21
            counts: dict = {}
            for k in posts:
                counts[k] = counts.get(k, 0) + 1
            for kind in sorted(counts):
                n = counts[kind]
                label = TRADE_NAMES.get(kind, kind)
                if n > 1:
                    label += "   x%d" % n
                row = pygame.Rect(lx + 14, y - 3, panel.width - 76, 18)
                if row.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, (54, 48, 38), row, border_radius=4)
                screen.blit(self.font_small.render(label, True, (234, 230, 220)),
                            (lx + 22, y))
                pay = self.font_small.render(
                    "takes %s   -   pays %d a day"
                    % ("the post" if me is None else "it",
                       economy.WAGE), True, (150, 176, 132))
                screen.blit(pay, (rx - pay.get_width(), y))
                self.job_rows.append((row, v, kind))
                y += 18
            y += 8
        if not any_post:
            screen.blit(self.font.render("No work going anywhere near here.",
                                         True, (150, 146, 138)), (lx, y))
            y += 28

        foot = panel.bottom - 92
        pygame.draw.line(screen, (96, 78, 54), (lx, foot - 12), (rx, foot - 12), 1)
        if me:
            line = "You are employed as a %s%s." % (
                TRADE_NAMES.get(me, me),
                " in %s" % my_town.name if my_town is not None else "")
        else:
            line = "You are unemployed   -   and you owe no tax."
        screen.blit(self.font.render(line, True, (238, 238, 228)), (lx, foot))

        # THERE IS NO TAX BUTTON, AND THAT IS THE POINT. A working man pays a
        # fifth of what he produces, in kind, out of his own pack, as he works
        # -- see main.pay_share, which is economy.take_fifth with a player in
        # the villager's place. He is never asked for coin, so there is nothing
        # here to press.
        self.tax_button = None
        if me:
            note = ("a fifth of what you produce goes to %s, taken as you work"
                    % (my_town.name if my_town is not None else "the village"))
        else:
            note = "with no post there is nothing to pay"
        screen.blit(self.font_small.render(note, True, (186, 180, 166)),
                    (lx, foot + 26))
        if self.notice_t > 0.0:
            screen.blit(self.font_small.render(self.notice, True, (240, 206, 130)),
                        (rx - self.font_small.size(self.notice)[0], foot + 32))
        close = self.font_small.render("E / Esc to close", True, (150, 146, 138))
        screen.blit(close, (panel.centerx - close.get_width() // 2, panel.bottom - 26))
