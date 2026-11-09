"""dialogue.py -- TALKING TO A MAN.

Three questions, and he answers every one of them TRUTHFULLY. That is the
whole point of him: no flattery, no guessing, no "he seems to like you". The
numbers behind the answers are his real ones.

    1) Wanna trade?                     -> opens the trade menu
    2) What do you think about <Dictator>?  -> 0 (hates him) .. 100 (loves him)
    3) What do you think about me?      -> -100 (fuck off) .. +100 (I like you)

Answers are BANDS, not numbers: a man whose love of the Dictator sits at 71
says "he is a strong leader" exactly as one at 100 does. You learn where he
stands, not the digit.
"""

from __future__ import annotations

import random

import pygame

import plog

import war
import work

# THE GAME'S CLOCK, set by main once a frame. Dialogue is opened by a click and
# asked by a key, so a value refreshed with the frame is never stale enough to
# matter; it is what dates what a man has heard.
NOW = [0.0]


def set_now(now: float) -> None:
    NOW[0] = float(now)


DICTATOR_BASE_TOWNSMAN = 60.0     # an ordinary citizen starts well disposed
DICTATOR_BASE_HUB = 30.0          # a criminal in a hut, much less so


def dictator_name(capital) -> str:
    """The man on the seat, by name -- the King of the main capital."""
    try:
        king = getattr(capital, "king", None)
        if king is not None and getattr(king, "name", ""):
            return king.name
        if capital is not None and getattr(capital, "name", ""):
            return "the Dictator of %s" % capital.name
    except Exception:
        pass
    return "the Dictator"


def dictator_love(npc) -> float:
    """0 = he hates him, 100 = he loves him. Base by where the man lives."""
    got = getattr(npc, "dictator_love", None)
    if got is not None:
        return float(got)
    try:
        hub = bool(getattr(npc, "hub", None)) or bool(getattr(npc, "is_hub", False))
        base = DICTATOR_BASE_HUB if hub else DICTATOR_BASE_TOWNSMAN
        bias = random.Random(getattr(npc, "npc_id", "x")).randint(-18, 18)
        npc.dictator_love = max(0.0, min(100.0, base + bias))
    except Exception:
        npc.dictator_love = DICTATOR_BASE_TOWNSMAN
    return float(npc.dictator_love)


def player_regard(npc, player) -> float:
    """0..100, and EVERY MAN STARTS AT 50 -- the middle.

    He neither likes nor dislikes you until something has happened between you:
    every honest bargain moves it up, every man you get killed moves it down.
    """
    base = getattr(npc, "player_opinion", None)
    if base is None:
        base = 50.0
        npc.player_opinion = base
    try:
        import economy
        import village as _vm
        op = economy.opinion_of(npc, _vm.PLAYER_ID)
        deals = float(op.get(_vm.PLAYER_ID, 0.0))        # +1 per honest deal
    except Exception:
        deals = 0.0
    return max(0.0, min(100.0, float(base) + deals * 5.0))


def dictator_answer(love: float) -> str:
    if love >= 70.0:
        return "He is a strong leader. The country is quiet."
    if love >= 40.0:
        return "I don't know. I keep my head down."
    return "He is a piece of shit, and every man here knows it."


def _grade_word(grade) -> str:
    """A grade as a man would say it: "an S grade", "C work"."""
    try:
        import quality
        letter = quality.letter(int(grade))
    except Exception:
        return "ungraded work"
    # "an S grade" -- S, F, A and E are said with a vowel sound.
    return ("an %s grade" % letter if letter and letter[0] in "AEFS"
            else "a %s grade" % letter)


def _item_name(item) -> str:
    """The thing by the name a man would say out loud."""
    try:
        import items
        return items.get(item).name.lower()
    except Exception:
        return str(item).replace("_", " ")


def _crave(item, yearning: float) -> str:
    """One thing he is after, in his own words, at the strength he feels it."""
    name = _item_name(item)
    plural = name.endswith("s")            # "dried mushrooms"
    art = "some" if plural else "a"
    if yearning >= 0.70:
        return "I need %s %s. Today." % (art, name)
    if yearning >= 0.35:
        return "I could do with %s %s." % (art, name)
    if plural:
        return "I'd take some %s if there was any going." % name
    return "I'd take a %s if there was one going." % name


def craving_answer(npc) -> str:
    """WHAT HE WANTS, TRUTHFULLY -- his own drug, and his own drink.

    The habit is `addiction` (half the world has one) and the appetite is
    `yearning`, which climbs with it and is spent when he smokes or drinks
    (economy.needs). What he smokes is what his country's leaf makes -- a
    cigar, dried mushrooms -- and what he drinks is his own brew. A man whose
    leaf has no finished article (agave) craves only the drink, and he must
    SOUND like it: the honest answer is his habit, not the shape of a table in
    economy.PROCESS.

    BANDS, not numbers, exactly like his other answers: you learn what he is
    after and how badly, never the digit.
    """
    want = getattr(npc, "wants_product", None)
    drink = getattr(npc, "wants_drink", None)
    yearning = float(getattr(npc, "yearning", 0.0))
    addiction = float(getattr(npc, "addiction", 0.0))
    if addiction < 0.03 and yearning < 0.15:
        return "Nothing. I don't touch any of it."
    if want:
        line = _crave(want, yearning)
        if drink and drink != want and addiction >= 0.25:
            dname = _item_name(drink)
            line += " And %s %s, if you have it." % (
                "some" if dname.endswith("s") else "a", dname)
        return line
    if drink:
        return _crave(drink, yearning)
    return "Nothing. I don't touch any of it."


def _nation(n) -> str:
    try:
        import village as _vm
        return _vm.nation_name(n)
    except Exception:
        return "the state"


def news_answer(npc) -> str:
    """WHAT HE HAS BEEN TOLD -- his own list, dated, and nothing else.

    News is CARRIED in this world, man to man (war.tell, note_capture), so what
    he repeats is what actually reached him, and war.prune_news gives it a
    fifteen-day life. Nothing here is the town's knowledge or the crown's: it
    is his. If he was also told that YOU did for a man, that is news too.
    """
    now = NOW[0]
    fresh = [e for e in list(getattr(npc, "news", ()) or ())
             if len(e) >= 5 and now - e[0] < war.WAR_NEWS_LIFETIME]
    parts = []
    if fresh:
        fresh.sort(key=lambda e: e[0], reverse=True)
        e = fresh[0]
        days = max(0, int((now - e[0]) / 600.0))
        when = ("today" if days == 0 else
                "yesterday" if days == 1 else "%d days ago" % days)
        parts.append("%s has taken %s. I heard it %s."
                     % (_nation(e[4]), e[1], when))
    try:
        import village as _vm
        if _vm.PLAYER_ID in getattr(npc, "knows", ()):
            parts.append("And they say you did for a man.")
    except Exception:
        pass
    if not parts:
        return "Nothing. Nobody tells me anything."
    return " ".join(parts)


def regard_answer(score: float) -> str:
    """50 is the middle. Above 60 he likes you; below 40 he does not."""
    if score >= 60.0:
        return "I like you."
    if score <= 40.0:
        return "Fuck off."
    return "I don't know."


class Dialogue:
    """The little panel: three questions, one answer at a time."""

    def __init__(self) -> None:
        self.npc = None
        self.capital = None
        self.player = None
        self.answer = ""
        self.who = ""
        self.font = pygame.font.SysFont("dejavusans", 16)
        self.font_small = pygame.font.SysFont("dejavusans", 13)
        self.font_title = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.font_body = pygame.font.SysFont("dejavusans", 15)
        self.font_hint = pygame.font.SysFont("dejavusans", 13)
        # THE LIVE PANEL, for observation only: there is exactly one on
        # screen, and this is it (the observer and my own play-tests read it).
        Dialogue._LIVE = self
        self.rows: list = []          # (rect, key)
        self.page = "ask"             # ask | hire | about
        self.offers: list = []        # [("farm", "farmer", places, pay)]
        self.items: list = []         # the products on the price/stop pages
        self.price_item = None
        self.price_grade = 3
        self.answer = ""
        self._rect = None

    # -- opening ---------------------------------------------------------
    def open(self, npc, player, capital=None) -> None:
        self.npc = npc
        self.player = player
        self.capital = capital
        self.who = getattr(npc, "name", "him")
        self.answer = ""
        self.page = "ask"
        self.offers = []

    def hit(self, pos) -> bool:
        return self._rect is not None and self._rect.collidepoint(pos)

    def close(self) -> None:
        self.npc = None
        self.answer = ""

    @property
    def open_(self) -> bool:
        return self.npc is not None

    # -- the questions ---------------------------------------------------
    def ask(self, which: int) -> str:
        got = self._ask(which)
        try:
            plog.log("TALK", self.who, "Q%d" % which, "->", self.answer[:110])
        except Exception:
            pass
        return got

    def _ask(self, which: int) -> str:
        npc = self.npc
        if npc is None:
            return ""
        if getattr(npc, "conquered", False):
            # HIS OWN CONQUERED WORKER: pockets first, then trade.
            if which == 1:
                self.answer = "%s: \"Help yourself.\"" % self.who
                return "pack"
            if which == 2:
                return "trade"
            return ""
        if which == 1:
            return "trade"
        if which == 2:
            love = dictator_love(npc)
            self.answer = "%s: \"%s\"" % (self.who, dictator_answer(love))
            return "answer"
        if which == 3:
            score = player_regard(npc, self.player)
            self.answer = "%s: \"%s\"" % (self.who, regard_answer(score))
            return "answer"
        if which == 4:
            self.answer = "%s: \"%s\"" % (self.who, craving_answer(npc))
            return "answer"
        if which == 5:
            self.answer = "%s: \"%s\"" % (self.who, news_answer(npc))
            return "answer"
        if which == 6:
            # LOOKING FOR WORK. Only an idle man with less than fifty coin is
            # worth asking, and only he is shown the question.
            if not work.qualifies(npc, self.player):
                # NOT A HIDDEN ROW. He refuses, in his own words.
                self.answer = "%s: \"%s\"" % (self.who,
                                               work.refusal(npc, self.player))
                return "answer"
            self.page = "hire"
            self.offers = work.offers(self.player) if self.player is not None else []
            if not self.offers:
                self.answer = "%s: \"Aye -- but you have nothing to put me to.\"" % self.who
                self.page = "ask"
            else:
                self.answer = "%s: \"Aye. What have you got?\"" % self.who
            return "work"
        if which == 7:
            # ABOUT WORK. Every question a hired man has is behind this one
            # row: what he is making, what he needs, and the door.
            return self._about()
        return ""

    # -- ABOUT WORK: what a hired man is asked --------------------------
    def _chest(self):
        """THE PLAYER'S CHEST -- the one in a house of his, in his hub."""
        return getattr(self.player, "hub_chest", None)

    def _about(self) -> str:
        if self.player is None or not work.is_employed(self.player, self.npc):
            return ""
        self.page = "about"
        self.answer = self._status()
        return "answer"

    def _status(self) -> str:
        """WHAT HE HAS, WHAT HE IS MAKING, AND WHAT IS IN THE WAY."""
        npc = self.npc
        trade = getattr(npc, "job", None)
        stock = getattr(npc, "stock", None) or {}
        bits = []
        for item in work.relevant(trade):
            q = int(stock.get(item, 0) or 0)
            if q:
                bits.append("%d %s" % (q, _item_name(item)))
        said = getattr(npc, "say", None)
        line = ""
        if said:
            line = "%s " % said
        if bits:
            line += "I have %s." % ", ".join(bits)
        if not work.can_work(npc, self._chest()):
            line += " I have nothing to work with."
        if not line:
            line = "Nothing to show for the day yet."
        if work.market_stall(self.player) is not None and work.to_market(
                self.player, npc):
            line += " What I make goes on your stall."
        return "%s: \"%s\"" % (self.who, line.strip())

    def _stall(self):
        try:
            return work.market_stall(self.player)
        except Exception:
            return None

    def _about_actions(self) -> list:
        """THE ROWS OF THE WORK PAGE, IN ORDER -- and the keys are 1..n.

        One list, used by both the drawing and the input, because the two used
        to number themselves separately: a row appeared when a stall was built
        and every key after it meant something else.
        """
        # THE MAN FIRST, THE SHOP SECOND. What he makes and what he is
        # charging are the two things this conversation exists for; where it
        # goes and what he should leave alone come after.
        out = [("Open his pack.", "pack")]
        if work.sellable(self.npc):
            out.append(("What quality do you make?", "quality"))
            if self._stall() is not None:
                out.append(("What do you want for it?", "price"))
        if work.market_stall(self.player) is not None:
            out.append(("Put his product back in the chest."
                        if work.to_market(self.player, self.npc) else
                        "Put his product on the stall.", "market"))
        if work.sellable(self.npc):
            out.append(("Stop selling something...", "stop"))
        out.append(("How is the work?", "status"))
        out.append(("Fire him.", "fire"))
        return out

    def _about_key(self, key: int) -> str:
        acts = self._about_actions()
        if not (1 <= key <= len(acts)):
            return ""
        label, what = acts[key - 1]
        if what == "pack":
            # HIS PACK, OPENED THE WAY A CHEST IS: what is his on top, what
            # is yours underneath, and a click moves a stack either way.
            self.answer = "%s: \"Help yourself.\"" % self.who
            return "pack"
        if what == "market":
            want = not work.to_market(self.player, self.npc)
            if work.set_market(self.player, self.npc, want):
                self.answer = ("%s: \"I'll put my work on the counter.\"" % self.who
                               if want else
                               "%s: \"It goes in your chest, then.\"" % self.who)
                plog.log("WORK", self.who, "to_market", bool(want))
            else:
                self.answer = "%s: \"You have no stall.\"" % self.who
            return "answer"
        if what == "quality":
            self.answer = "%s: \"%s\"" % (self.who, work.quality_answer(self.npc))
            plog.log("WORK", self.who, "quality", work.hands_grade(self.npc))
            return "answer"
        if what == "price":
            return self._open_price()
        if what == "stop":
            return self._open_stop()
        if what == "status":
            self.answer = self._status()
            return "answer"
        if what == "fire":
            who = self.who
            if work.fire(self.player, self.npc):
                self.page = "ask"
                self.answer = "%s: \"Then I'm off.\"" % who
                return "answer"
        return ""

    def _open_price(self) -> str:
        """WHAT HE IS CHARGING, AND WHAT HE MAY CHARGE.

        The price belongs to the man, because he makes the thing and it is his
        grade that is being sold: the counter holds goods, the agreement is
        between the two of you. Each of his products is listed with the price
        the market is asking for it -- and the town's ceiling beside it, which
        is the number he is undercutting.
        """
        stall = self._stall()
        items_ = work.sellable(self.npc)
        if stall is None or not items_:
            self.answer = "%s: \"There is nothing of mine to price.\"" % self.who
            return "answer"
        self.items = items_
        self.page = "price"
        g = work.price_grade(self.npc)
        self.answer = ("%s: \"%s, and I'd want a fair price for it.\""
                       % (self.who, _grade_word(g)))
        return "answer"

    def _open_price_one(self, index: int) -> str:
        stall = self._stall()
        if stall is None or not (0 <= index < len(self.items)):
            return ""
        self.price_item = self.items[index]
        self.price_grade = work.price_grade(self.npc)
        self.page = "price_one"
        self.answer = self._price_line()
        return "answer"

    def _price_line(self) -> str:
        stall = self._stall()
        item = getattr(self, "price_item", None)
        grade = int(getattr(self, "price_grade", 3))
        if stall is None or item is None:
            return ""
        price = stall.price_of(item, grade)
        line = "%s: \"%s at %s -- %d coin each.\"" % (
            self.who, _item_name(item), _grade_word(grade), price)
        try:
            ref = getattr(self.player, "town_price_for", None)
            if ref is not None:
                pays = int(round(float(ref(item, grade))))
                if pays:
                    rel = ("that is under the town" if price < pays
                           else "that is over the town" if price > pays
                           else "that is the town's own price")
                    line += " (the town pays %d -- %s)" % (pays, rel)
        except Exception:
            pass
        return line

    def _price_step(self, delta: int) -> str:
        stall = self._stall()
        item = getattr(self, "price_item", None)
        if stall is None or item is None:
            return ""
        grade = int(getattr(self, "price_grade", 3))
        new = stall.set_price(item, grade, stall.price_of(item, grade) + delta)
        try:
            import orders
            orders.order(self.player, self.npc, "price", item=item, value=new)
        except Exception:
            pass
        plog.log("WORK", self.who, "price", item, "grade", grade, "->", new)
        self.answer = self._price_line()
        return "answer"

    def _price_key(self, key: int) -> str:
        if self.page == "price":
            if not (1 <= key <= len(self.items)):
                return ""
            return self._open_price_one(key - 1)
        # price_one: 1 -10, 2 -1, 3 +1, 4 +10, 5 done
        if key == 1:
            return self._price_step(-10)
        if key == 2:
            return self._price_step(-1)
        if key == 3:
            return self._price_step(+1)
        if key == 4:
            return self._price_step(+10)
        if key == 5:
            return self._open_price()
        return ""

    def _open_stop(self) -> str:
        """WHAT HE MAKES AND WHAT HE OFFERS -- TWO ORDERS, ONE PER PRODUCT.

        "Don't make any more cigars" leaves a bench standing idle. "Don't SELL
        the cigars" leaves the bench working and the counter empty, with the
        product going to the player's chest instead. They are different
        instructions about the same thing, so each product appears twice: once
        to be taken off the market, once to be taken out of his hands.
        """
        self.items = [(i, "sell") for i in work.sellable(self.npc)]
        self.items += [(i, "make") for i in work.sellable(self.npc)]
        if not self.items:
            self.answer = "%s: \"I make nothing to stop.\"" % self.who
            return "answer"
        self.page = "stop"
        self.answer = ("%s: \"Which of them? Make it, or sell it?\"" % self.who)
        return "answer"

    def _stop_key(self, key: int) -> str:
        if not (1 <= key <= len(self.items)):
            return ""
        item, mode = self.items[key - 1]
        name = _item_name(item)
        if mode == "sell":
            stop = not work.is_not_sold(self.npc, item)
            work.set_not_sold(self.npc, item, stop, self.player)
            self.answer = ("%s: \"Then I keep the %s off your counter.\""
                           % (self.who, name) if stop else
                           "%s: \"The %s goes back on your counter.\""
                           % (self.who, name))
            plog.log("WORK", self.who,
                     "stop_selling" if stop else "sell_again", item)
        else:
            stop = not work.is_banned(self.npc, item)
            work.set_banned(self.npc, item, stop, self.player)
            self.answer = ("%s: \"Then I'll make no more %s.\"" % (self.who, name)
                           if stop else
                           "%s: \"I'll make the %s again.\"" % (self.who, name))
            plog.log("WORK", self.who,
                     "stop_making" if stop else "make_again", item)
        return "answer"

    def _activate(self, key: int) -> str:
        """One place where a number key or a click becomes an action."""
        if self.page == "hire":
            return self._hire(key - 1)
        if self.page == "about":
            return self._about_key(key)
        if self.page == "stop":
            return self._stop_key(key)
        if self.page in ("price", "price_one"):
            return self._price_key(key)
        return self.ask(key) or ""

    # -- input -----------------------------------------------------------
    def _hire(self, index: int) -> str:
        if not (0 <= index < len(self.offers)) or self.npc is None:
            return ""
        trade, label, _places, wage = self.offers[index]
        got = work.hire(self.player, self.npc, trade)
        if got is None:
            if trade == "soldier":
                self.answer = ("%s: \"Put a dummy or a target in your yard "
                               "and I will take the post.\"" % self.who)
            else:
                self.answer = "%s: \"That place is gone.\"" % self.who
            return "answer"
        self.answer = "%s takes the work: %s, %d a day." % (self.who, label, wage)
        self.offers = work.offers(self.player) if self.player is not None else []
        self.page = "ask"
        return "answer"

    def handle_event(self, event) -> str:
        """Returns "trade", "close", or "" -- nothing to do."""
        if not self.open_:
            return ""
        if event.type == pygame.KEYDOWN:
            # A NUMBER IS A ROW ON WHATEVER PAGE IS UP. Each page used to own
            # its own copy of the digits, so a new page meant a new table and
            # a click that did nothing; there is one table now.
            digit = None
            if pygame.K_1 <= event.key <= pygame.K_9:
                digit = event.key - pygame.K_0
            elif pygame.K_KP1 <= event.key <= pygame.K_KP9:
                digit = event.key - pygame.K_KP1 + 1
            if digit is not None:
                return self._activate(digit)
            if self.page == "ask":
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.close()
                    return "close"
                return ""
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                # BACK ONE STEP, NOT OUT OF THE CONVERSATION.
                if self.page == "price_one":
                    return self._open_price()
                if self.page == "price":
                    return self._about()
                if self.page == "stop":
                    return self._about()
                if self.page == "about":
                    self.page = "ask"
                    self.answer = ""
                elif self.page == "hire":
                    self.page = "ask"
                    self.answer = ""
                return "answer"
            return ""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for rect, key in self.rows:
                if rect.collidepoint(mx, my):
                    return self._activate(key)
        return ""

    # -- drawing ---------------------------------------------------------
    @staticmethod
    def spaced(screen, font, text, pos, colour, extra=0):
        """PLAIN TEXT, set the way every other panel in the game is set.

        The per-character version put a pixel between every glyph and destroyed
        the font's kerning -- it looked worse, not better.
        """
        img = font.render(text, True, colour)
        screen.blit(img, pos)
        return pos[0] + img.get_width()

    def _wrap(self, text, font, width) -> list:
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if font.size(trial)[0] > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines

    def draw(self, screen: pygame.Surface) -> None:
        if not self.open_:
            return
        vw, vh = screen.get_size()
        w = min(560, vw - 80)
        h = 470
        panel = pygame.Rect(vw // 2 - w // 2, vh // 2 - h // 2, w, h)
        self._rect = panel
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (24, 22, 20), panel, border_radius=10)
        pygame.draw.rect(screen, (154, 118, 78), panel, 2, border_radius=10)

        # ---- the man -------------------------------------------------
        self.spaced(screen, self.font_title, self.who.upper(),
                    (panel.x + 18, panel.y + 14), (238, 224, 190), 1)
        job = "-  %s" % (getattr(self.npc, "job", None) or "no trade")
        self.spaced(screen, self.font_small, job,
                    (panel.x + 18, panel.y + 38), (176, 168, 152), 1)

        # ---- the questions -------------------------------------------
        dname = dictator_name(self.capital)
        if getattr(self.npc, "conquered", False):
            options = [
                (1, "1.   Show me your pockets."),
                (2, "2.   Wanna trade?"),
            ]
        else:
            options = [
                (1, "1.   Wanna trade?"),
                (2, "2.   What do you think about %s?" % dname),
                (3, "3.   What do you think about me?"),
                (4, "4.   Like to have fun?"),
                (5, "5.   Any news?"),
            ]
        # ALWAYS THERE. Whether he will take it is his answer, not a missing
        # option: eighteen men in twenty have a trade, and a player who cannot
        # see the question thinks the game has none. A conquered worker has his
        # own two options above and no hire/fire page.
        if not getattr(self.npc, "conquered", False):
            if not (self.player is not None
                    and work.is_employed(self.player, self.npc)):
                options.append((6, "6.   Looking for work?"))
            if self.player is not None and work.is_employed(self.player, self.npc):
                options.append((7, "7.   About work..."))
        self.rows = []
        y = panel.y + 66
        if self.page == "hire":
            options = []
            for _i, (_tr, _lab, _n, _pay) in enumerate(self.offers, 1):
                options.append((_i, "%d.   %s   -   %d a day%s"
                                % (_i, _lab.capitalize(), _pay,
                                   "" if _n >= 9999 else "   (%d places)" % _n)))
        elif self.page in ("about", "stop"):
            options = [(i, "%d.   %s" % (i, _lab))
                       for i, (_lab, _what) in
                       enumerate(self._about_actions(), 1)]
        elif self.page == "price":
            options = []
            stall = self._stall()
            g = work.price_grade(self.npc)
            for _i, _item in enumerate(self.items, 1):
                _p = stall.price_of(_item, g) if stall is not None else 0
                options.append((_i, "%d.   %-14s %s   %d coin each"
                                % (_i, _item_name(_item), _grade_word(g), _p)))
            options.append((len(self.items) + 1, "Back."))
        elif self.page == "price_one":
            _p = (self._stall().price_of(self.price_item, self.price_grade)
                  if self._stall() is not None else 0)
            options = [
                (1, "1.   cheaper by 10      ->  %d" % max(1, _p - 10)),
                (2, "2.   cheaper by 1       ->  %d" % max(1, _p - 1)),
                (3, "3.   dearer by 1        ->  %d" % (_p + 1)),
                (4, "4.   dearer by 10       ->  %d" % (_p + 10)),
                (5, "5.   Done."),
            ]
        elif self.page == "stop":
            options = []
            for _i, (_item, _mode) in enumerate(self.items, 1):
                _n = _item_name(_item)
                if _mode == "sell":
                    if work.is_not_sold(self.npc, _item):
                        _txt = "Start selling the %s again." % _n
                    else:
                        _on = ""
                        try:
                            _st = work.market_stall(self.player)
                            _q = _st.held(_item) if _st is not None else 0
                            if _q:
                                _on = "  (%d on the stall)" % _q
                        except Exception:
                            pass
                        _txt = "Stop selling the %s.%s" % (_n, _on)
                else:
                    _txt = (("Start making the %s again." % _n)
                            if work.is_banned(self.npc, _item)
                            else ("Stop making the %s." % _n))
                options.append((_i, "%d.   %s" % (_i, _txt)))
            options.append((len(self.items) + 1, "Back."))
        for key, text in options:
            r = pygame.Rect(panel.x + 16, y, w - 32, 32)
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(screen, (46, 42, 36) if hover else (31, 29, 25),
                             r, border_radius=5)
            pygame.draw.rect(screen, (66, 60, 50), r, 1, border_radius=5)
            self.spaced(screen, self.font, text, (r.x + 12, r.y + 8),
                        (228, 218, 198), 1)
            self.rows.append((r, key))
            y += 38

        # ---- the answer ----------------------------------------------
        pygame.draw.line(screen, (74, 68, 58),
                         (panel.x + 16, y + 4), (panel.right - 16, y + 4), 1)
        ay = y + 16
        if self.answer:
            for line in self._wrap(self.answer, self.font_body, w - 44)[:5]:
                self.spaced(screen, self.font_body, line,
                            (panel.x + 18, ay), (206, 232, 200), 1)
                ay += 22
        else:
            self.spaced(screen, self.font_small, "Ask him anything. He does not lie.",
                        (panel.x + 18, ay), (150, 146, 134), 1)
        _hint = "[1] [2] [3]    ESC to walk away"
        if self.page == "hire":
            _hint = "a number puts a man to work    ESC is back"
        elif self.page in ("about", "stop"):
            _hint = "a number chooses    ESC is back"
        self.spaced(screen, self.font_hint, _hint,
                    (panel.x + 18, panel.bottom - 26), (140, 134, 122), 1)
