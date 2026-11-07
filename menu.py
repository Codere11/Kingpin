"""Main menu and save-slot menu.

Rendered at low resolution and upscaled with nearest-neighbour, matching the
Game Over screen's chunky look. All text is clipped to its own button so it can
never spill outside its boundary.
"""

from __future__ import annotations

import random

import pygame

import persist

BG = (14, 12, 16)
TITLE = (226, 188, 98)
TITLE_DARK = (58, 38, 8)
BTN_BG = (34, 30, 26)
BTN_BG_HOVER = (74, 58, 34)
BTN_BORDER = (110, 90, 54)
BTN_BORDER_HOVER = (236, 196, 110)
BTN_TEXT = (238, 230, 214)
DIM = (168, 156, 138)
HINT = (122, 110, 98)
SLOT = (28, 32, 28)
SLOT_HOVER = (54, 70, 48)
DEL_BG = (66, 26, 24)
DEL_HOVER = (128, 44, 40)
DEL_BORDER = (128, 52, 46)
TEST_BG = (26, 34, 40)
TEST_HOVER = (44, 72, 84)
TEST_BORDER = (66, 118, 138)
TEST_BORDER_HOVER = (140, 222, 240)


def _fit(font, text, max_w, color):
    """Render ``text`` shrinking/truncating so it never exceeds ``max_w``."""
    if max_w <= 4:
        return font.render("", False, color)
    if font.size(text)[0] <= max_w:
        return font.render(text, False, color)
    trimmed = text
    while trimmed and font.size(trimmed + "...")[0] > max_w:
        trimmed = trimmed[:-1]
    return font.render(trimmed + "...", False, color)


class Menu:
    def __init__(self) -> None:
        self.page = "main"
        self.test = False
        self.toast = ""
        self.toast_t = 0.0
        self.hover = -1
        self._rects: list[pygame.Rect] = []
        self._actions: list = []
        self._font_key = None

    def _fonts(self, lw: int) -> None:
        if self._font_key != lw:
            self.title_font = pygame.font.SysFont("dejavusansmono", max(14, int(lw * 0.12)), bold=True)
            self.btn_font = pygame.font.SysFont("dejavusansmono", max(8, int(lw * 0.036)), bold=True)
            self.small_font = pygame.font.SysFont("dejavusansmono", max(6, int(lw * 0.024)), bold=True)
            self._font_key = lw

    def _layout(self, w: int, h: int):
        scale = max(1, w // 320)
        lw, lh = max(1, w // scale), max(1, h // scale)
        self._fonts(lw)
        if self.page == "main":
            bw, bh = max(54, int(lw * 0.24)), max(18, int(lh * 0.15))
            gap = max(8, int(lw * 0.03))
            total = bw * 3 + gap * 2
            x0 = (lw - total) // 2
            y = int(lh * 0.60)
            self._rects = [pygame.Rect(x0 + i * (bw + gap), y, bw, bh)
                           for i in range(3)]
            self._actions = ["singleplayer", "testmode", "quit"]
        else:
            bh = max(14, int(lh * 0.095))
            gap = max(6, int(lh * 0.026))
            dw = max(30, int(lw * 0.11))
            sw = max(112, int(lw * 0.56))
            g2 = max(6, int(lw * 0.018))
            total = sw + g2 + dw
            x0 = (lw - total) // 2
            y = int(lh * 0.28)
            self._rects = []
            self._actions = []
            for i in range(persist.SLOTS):
                yy = y + i * (bh + gap)
                self._rects.append(pygame.Rect(x0, yy, sw, bh))
                self._actions.append(i)
                self._rects.append(pygame.Rect(x0 + sw + g2, yy, dw, bh))
                self._actions.append(("delete", i))
            back = pygame.Rect(lw // 2 - max(52, int(lw * 0.17)),
                               y + persist.SLOTS * (bh + gap) + gap,
                               max(104, int(lw * 0.34)), bh)
            self._rects.append(back)
            self._actions.append("back")
        return scale, lw, lh

    def handle(self, event, w: int, h: int):
        scale, _lw, _lh = self._layout(w, h)
        if event.type == pygame.MOUSEMOTION:
            lx, ly = event.pos[0] // scale, event.pos[1] // scale
            self.hover = -1
            for i, rect in enumerate(self._rects):
                if rect.collidepoint((lx, ly)):
                    self.hover = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx, ly = event.pos[0] // scale, event.pos[1] // scale
            for i, rect in enumerate(self._rects):
                if rect.collidepoint((lx, ly)):
                    return self._actions[i]
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "back" if self.page == "saves" else "quit"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._actions:
                return self._actions[0]
        return None

    def draw(self, screen: pygame.Surface) -> None:
        w, h = screen.get_size()
        scale, lw, lh = self._layout(w, h)
        low = pygame.Surface((lw, lh))
        low.fill(BG)
        for y in range(0, lh, 4):
            pygame.draw.line(low, (18, 16, 20), (0, y), (lw, y))
        persist.set_test(self.test)

        title = "GETWORLD" if self.page == "main" else (
            "TEST SAVES" if self.test else "SAVES")
        t = self.title_font.render(title, False, TITLE)
        o = self.title_font.render(title, False, TITLE_DARK)
        tx = lw // 2 - t.get_width() // 2
        ty = int(lh * 0.15)
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            low.blit(o, (tx + ox, ty + oy))
        low.blit(t, (tx, ty))
        sub = _fit(self.small_font, "tobacco  ·  lead  ·  greed", lw - 16, DIM)
        low.blit(sub, (lw // 2 - sub.get_width() // 2, ty + t.get_height() + 4))

        for i, (rect, act) in enumerate(zip(self._rects, self._actions)):
            hovered = (i == self.hover)
            if isinstance(act, tuple) and act[0] == "delete":
                pygame.draw.rect(low, DEL_HOVER if hovered else DEL_BG, rect)
                pygame.draw.rect(low, DEL_BORDER, rect, 1)
                x = _fit(self.btn_font, "X", rect.w - 6, BTN_TEXT)
                low.blit(x, (rect.centerx - x.get_width() // 2,
                             rect.centery - x.get_height() // 2))
                continue
            if act in ("singleplayer", "quit", "back", "testmode"):
                test = (act == "testmode")
                pygame.draw.rect(low, (TEST_HOVER if hovered else TEST_BG) if test
                                 else (BTN_BG_HOVER if hovered else BTN_BG), rect)
                pygame.draw.rect(low, (TEST_BORDER_HOVER if hovered else TEST_BORDER) if test
                                 else (BTN_BORDER_HOVER if hovered else BTN_BORDER), rect, 1)
                label = {"singleplayer": "SINGLEPLAYER", "quit": "QUIT GAME",
                         "back": "BACK", "testmode": "TEST MODE"}[act]
            else:
                made, houses, coins = persist.summary(act)
                pygame.draw.rect(low, SLOT_HOVER if hovered else SLOT, rect)
                pygame.draw.rect(low, BTN_BORDER_HOVER if hovered else BTN_BORDER, rect, 1)
                if made:
                    label = "SAVE %d   -   %d COINS" % (act + 1, coins)
                else:
                    label = "SAVE %d   -   EMPTY (NEW GAME)" % (act + 1)
            text = _fit(self.btn_font, label, rect.w - 10, BTN_TEXT)
            low.blit(text, (rect.centerx - text.get_width() // 2,
                            rect.centery - text.get_height() // 2))

        hint = self.small_font.render(
            "CLICK TO SELECT" if self.page == "main" else "ESC = BACK", False, HINT)
        low.blit(hint, (lw // 2 - hint.get_width() // 2, lh - 12))
        screen.blit(pygame.transform.scale(low, (w, h)), (0, 0))


def run(screen, clock):
    """Show the menu. Returns the chosen save slot, or None to quit."""
    menu = Menu()
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            act = menu.handle(event, *screen.get_size())
            if act is None:
                continue
            if act == "quit":
                return None
            if act == "singleplayer":
                menu.test = False
                menu.page = "saves"
                menu.hover = -1
            elif act == "testmode":
                menu.test = True
                menu.page = "saves"
                menu.hover = -1
            elif act == "back":
                menu.page = "main"
                menu.hover = -1
            elif isinstance(act, tuple) and act[0] == "delete":
                persist.set_test(menu.test)
                went = persist.delete(act[1])
                menu.hover = -1
                menu.toast = ("Save deleted" if went
                              else "Nothing there to delete")
                menu.toast_t = 2.0
            elif isinstance(act, int):
                persist.set_test(menu.test)
                persist.set_slot(act)
                if not persist.exists(act):
                    persist.write({"seed": random.randint(1, 2 ** 31 - 1)}, act)
                return (act, menu.test)
        menu.draw(screen)
        pygame.display.flip()


# -- the backstory -----------------------------------------------------------
#
# WHO HE WAS BEFORE THE FIRST FRAME. Not a class and not a stat block: an
# occupation, a place in a town that has work for it, and the kit that goes
# with the trade. Seven of them, hardest last, because the whole point of an
# open world is that the man who starts with nothing is not playing a worse
# game -- he is playing a longer one.
ORIGINS = (
    ("trader", "TRADER", "Ten leaf, and five finished goods to sell. Easiest start: you arrive with stock."),
    ("smith", "SMITH", "An armful of iron and the run of the forge. 'E' at the anvil shows the orders."),
    ("soldier", "SOLDIER", "A rifle, forty rounds and a kit. You start in a capital, where the army is."),
    ("artisan", "ARTISAN", "A bale of leaf and a bench to roll it on."),
    ("brewer", "BREWER", "One batch's worth of grain, ready to start."),
    ("farmer", "FARMER", "A plot of your own, seed, a shovel and a can."),
    ("logger", "LOGGER", "An axe. The woods are the woods."),
    ("idle", "IDLE", "Nothing at all. Some men arrive with nothing; some of them end up kings."),
)


def choose_origin(screen, clock):
    """Pick a backstory. Returns the origin key, or None to go back.

    DRAWN AT THE SCREEN'S OWN RESOLUTION. The rest of the menus compose at a
    third of the window and blow the result up, which is right for a screen of
    two buttons -- but this one carries eight trades and a line about each, and
    at three hundred and twenty pixels wide that line was four pixels tall and
    unreadable. Legibility first: the type is sized from the window.
    """
    w, h = screen.get_size()
    title_font = pygame.font.SysFont("dejavusansmono", max(16, h // 15), bold=True)
    sub_font = pygame.font.SysFont("dejavusansmono", max(10, h // 46))
    num_font = pygame.font.SysFont("dejavusansmono", max(11, h // 34), bold=True)
    name_font = pygame.font.SysFont("dejavusansmono", max(12, h // 30), bold=True)
    blurb_font = pygame.font.SysFont("dejavusansmono", max(10, h // 44))
    row_h = max(26, int(h * 0.082))
    list_top = int(h * 0.20)
    list_w = int(w * 0.86)
    list_x = (w - list_w) // 2
    pick = 0
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in (pygame.K_DOWN, pygame.K_s):
                pick = (pick + 1) % len(ORIGINS)
            elif event.key in (pygame.K_UP, pygame.K_w):
                pick = (pick - 1) % len(ORIGINS)
            elif pygame.K_1 <= event.key <= pygame.K_9:
                idx = event.key - pygame.K_1
                if idx < len(ORIGINS):
                    return ORIGINS[idx][0]
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return ORIGINS[pick][0]
            elif event.key == pygame.K_ESCAPE:
                return None
        screen.fill(BG)
        head = title_font.render("WHERE ARE YOU FROM?", True, TITLE)
        screen.blit(head, (w // 2 - head.get_width() // 2, int(h * 0.075)))
        sub = sub_font.render("every trade starts in a town that has work for it",
                              True, HINT)
        screen.blit(sub, (w // 2 - sub.get_width() // 2, int(h * 0.075) + head.get_height() + 4))
        for i, (key, name, blurb) in enumerate(ORIGINS):
            y = list_top + i * row_h
            on = (i == pick)
            rect = pygame.Rect(list_x, y, list_w, row_h - 4)
            pygame.draw.rect(screen, BTN_BG_HOVER if on else SLOT, rect)
            pygame.draw.rect(screen, BTN_BORDER_HOVER if on else BTN_BORDER, rect, 1)
            # the number, in its own small column
            num = num_font.render(str(i + 1), True, TITLE if on else HINT)
            screen.blit(num, (rect.x + 10, rect.centery - num.get_height() // 2))
            # the trade, in a fixed column so all eight line up
            nm = name_font.render(name, True, BTN_TEXT if on else DIM)
            screen.blit(nm, (rect.x + 34, rect.centery - nm.get_height() // 2))
            # and what it means, from a column of its own
            bl = blurb_font.render(blurb, True, BTN_TEXT if on else DIM)
            screen.blit(bl, (rect.x + 34 + int(list_w * 0.20),
                             rect.centery - bl.get_height() // 2))
        hint = blurb_font.render("up / down   or   1-8        enter to begin        esc to go back",
                                 True, HINT)
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h - hint.get_height() - 12))
        pygame.display.flip()


# -- the letter --------------------------------------------------------------
#
# THE FIRST THING ANY MAN READS. Not a tutorial and not a wall of controls: a
# letter from the ledger saying who he is, what he owes, why, and what happens
# if it is not paid -- and then, in three short lines, how his trade earns the
# money for it. Everything else in the game he is meant to find out by walking
# into it.
LETTERS = {
    "trader": (
        "borrowed four hundred coin against a wagon of leaf you had already sold "
        "once, and the man who lent it has gone to the ledger about it",
        ("You arrive with stock: ten leaf, three beers and two cigars.",
         "Sell them to whoever needs them -- E to talk, then trade.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "smith": (
        "took on the forge of a man who died owing the town, and found the bench "
        "came with his debts attached to it",
        ("Stand at the forge and press E to see the orders; choose what to make.",
         "Sell the rifles, tools and iron to the town.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "soldier": (
        "signed for a regiment that was disbanded before it ever marched, and the "
        "pay never came -- but the quartermaster's account did",
        ("You still have your rifle, forty rounds and a first-aid kit.",
         "Take paid work: a posted bounty, a guard's wage, or a wolf worth skinning.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "artisan": (
        "bought a bale of leaf on credit in a season that failed, and the merchant "
        "wrote your name in the book the day the rains did not come",
        ("Your bench is here. Press E at it to roll leaf into cigars.",
         "Sell them -- good leaf and a steady hand fetch real money.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "brewer": (
        "sold barrels that had not been brewed yet, and then the batch soured "
        "before the buyer came to collect them",
        ("Take your grain to the brewhouse and press E to start a batch.",
         "Sell the beer when it is ready -- it is worth more than the grain by far.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "farmer": (
        "took seed on credit and the flood took the field, and the seed was the "
        "town's and not the flood's",
        ("You have a plot, seed, a shovel and a can. Plant it and keep it watered.",
         "Sell what you grow to the townsfolk.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "logger": (
        "bought a fine axe on account the same week the mill closed, and an axe "
        "is not worth much to a man with no work",
        ("You have an axe and nothing else.",
         "Cut wood in the woodlot and sell it to the town.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
    "idle": (
        "arrived with nothing, and were given a bed and a hot meal against your "
        "name, because that is what this town does for a stranger",
        ("You have nothing but your hands.",
         "Take whatever work the town will pay for -- and there is always some.",
         "Carry the coin to the notice board in the square, press E, and pay.")),
}


def _wrap(font, text: str, width: int) -> list:
    words = text.split()
    lines, line = [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if font.size(trial)[0] <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def show_letter(screen, clock, name: str, origin: str, town: str) -> None:
    """The letter he finds waiting. Enter or Esc dismisses it."""
    w, h = screen.get_size()
    head_font = pygame.font.SysFont("dejavusansmono", max(13, h // 26), bold=True)
    body_font = pygame.font.SysFont("dejavusansmono", max(11, h // 38))
    step_font = pygame.font.SysFont("dejavusansmono", max(11, h // 40), bold=True)
    small = pygame.font.SysFont("dejavusansmono", max(10, h // 48))
    why, steps = LETTERS.get(origin, LETTERS["idle"])
    trade = dict((k, n) for k, n, _b in ORIGINS).get(origin, "IDLE").title()

    text_w = int(w * 0.62)
    x = (w - text_w) // 2
    para1 = ("You are %s, and you have just started as a %s in %s."
             % (name, trade.lower(), town))
    para1b = ("You owe the ledger because you %s. Pay it, or you will be declared "
              "a criminal and hunted down." % why)
    para1c = ("The world is harsh, but the limits to your rise depend solely on you.")
    para1d = ("Be careful. You may not be the only ambitious man in this world.")

    lines = []
    for chunk in (para1, "", para1b, "", para1c, "", para1d):
        if chunk == "":
            lines.append(None)
        else:
            for ln in _wrap(body_font, chunk, text_w):
                lines.append((ln, body_font, BTN_TEXT))
    lines.append(None)
    step_head = ("How a %s pays his debt:" % trade.lower())
    for ln in _wrap(step_font, step_head, text_w):
        lines.append((ln, step_font, TITLE))
    for i, s_line in enumerate(steps, 1):
        for k, ln in enumerate(_wrap(step_font, "%d.  %s" % (i, s_line), text_w)):
            lines.append((ln, step_font, BTN_TEXT if k == 0 else DIM))

    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                return
        screen.fill(BG)
        # a sheet of paper, a shade lighter than the night behind it
        pad = int(h * 0.06)
        top = int(h * 0.07)
        sheet = pygame.Rect(x - pad, top - pad // 2, text_w + pad * 2, h - top * 2 + pad)
        pygame.draw.rect(screen, (30, 26, 22), sheet)
        pygame.draw.rect(screen, BTN_BORDER, sheet, 1)
        head = head_font.render("A LETTER FROM THE LEDGER", True, TITLE)
        screen.blit(head, (w // 2 - head.get_width() // 2, top))
        y = top + head.get_height() + int(h * 0.03)
        for item in lines:
            if item is None:
                y += int(h * 0.018)
                continue
            ln, font, colour = item
            screen.blit(font.render(ln, True, colour), (x, y))
            y += font.get_height() + 2
        hint = small.render("press any key to begin", True, HINT)
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h - hint.get_height() - 10))
        pygame.display.flip()
