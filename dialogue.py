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
    """-100 = he wants nothing to do with you, +100 = he likes you."""
    try:
        import economy
        import village as _vm
        op = economy.opinion_of(npc, _vm.PLAYER_ID)
        stored = float(op.get(_vm.PLAYER_ID, 0.0))       # +1 per honest deal
    except Exception:
        stored = 0.0
    bias = 0.0
    try:
        bias = random.Random(str(getattr(npc, "npc_id", "x")) + "me").randint(-35, 20)
    except Exception:
        pass
    return max(-100.0, min(100.0, stored * 8.0 + bias))


def dictator_answer(love: float) -> str:
    if love >= 70.0:
        return "He is a strong leader. The country is quiet."
    if love >= 40.0:
        return "I don't know. I keep my head down."
    return "He is a piece of shit, and every man here knows it."


def regard_answer(score: float) -> str:
    if score >= 20.0:
        return "I like you. You have been straight with me."
    if score <= -20.0:
        return "Fuck off. I know what you are."
    return "I don't know you well enough to say."


class Dialogue:
    """The little panel: three questions, one answer at a time."""

    def __init__(self) -> None:
        self.npc = None
        self.capital = None
        self.player = None
        self.answer = ""
        self.who = ""
        self.font = pygame.font.SysFont("dejavusans", 16, bold=True)
        self.font_small = pygame.font.SysFont("dejavusans", 13)
        self.font_title = pygame.font.SysFont("dejavusans", 18, bold=True)
        self.rows: list = []          # (rect, key)

    # -- opening ---------------------------------------------------------
    def open(self, npc, player, capital=None) -> None:
        self.npc = npc
        self.player = player
        self.capital = capital
        self.who = getattr(npc, "name", "him")
        self.answer = ""

    def close(self) -> None:
        self.npc = None
        self.answer = ""

    @property
    def open_(self) -> bool:
        return self.npc is not None

    # -- the questions ---------------------------------------------------
    def ask(self, which: int) -> str:
        npc = self.npc
        if npc is None:
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
        return ""

    # -- input -----------------------------------------------------------
    def handle_event(self, event) -> str:
        """Returns "trade", "close", or "" -- nothing to do."""
        if not self.open_:
            return ""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                self.close()
                return "close"
            if event.key in (pygame.K_1, pygame.K_KP1):
                return self.ask(1) or ""
            if event.key in (pygame.K_2, pygame.K_KP2):
                self.ask(2)
                return "answer"
            if event.key in (pygame.K_3, pygame.K_KP3):
                self.ask(3)
                return "answer"
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for rect, key in self.rows:
                if rect.collidepoint(mx, my):
                    if key == 1:
                        return self.ask(1) or ""
                    self.ask(key)
                    return "answer"
        return ""

    # -- drawing ---------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        if not self.open_:
            return
        vw, vh = screen.get_size()
        w, h = 470, 250
        panel = pygame.Rect(vw // 2 - w // 2, vh // 2 - h // 2, w, h)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (24, 22, 20), panel, border_radius=10)
        pygame.draw.rect(screen, (154, 118, 78), panel, 2, border_radius=10)

        title = self.font_title.render(self.who.upper(), True, (238, 224, 190))
        screen.blit(title, (panel.x + 16, panel.y + 12))
        job = "  -  %s" % (getattr(self.npc, "job", None) or "no trade")
        screen.blit(self.font_small.render(job, True, (176, 168, 152)),
                    (panel.x + 16 + title.get_width(), panel.y + 16))

        _cap = self.capital
        dname = dictator_name(_cap)
        options = [
            (1, "1.  Wanna trade?"),
            (2, "2.  What do you think about %s?" % dname),
            (3, "3.  What do you think about me?"),
        ]
        self.rows = []
        y = panel.y + 52
        for key, text in options:
            r = pygame.Rect(panel.x + 16, y, w - 32, 30)
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(screen, (44, 40, 34) if hover else (32, 30, 26),
                             r, border_radius=5)
            screen.blit(self.font.render(text, True, (226, 216, 196)),
                        (r.x + 10, r.y + 6))
            self.rows.append((r, key))
            y += 34

        if self.answer:
            lines, cur = [], ""
            for word in self.answer.split():
                trial = (cur + " " + word).strip()
                if self.font_small.size(trial)[0] > w - 44:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            if cur:
                lines.append(cur)
            ay = panel.y + 158
            for line in lines[:3]:
                screen.blit(self.font_small.render(line, True, (206, 232, 200)),
                            (panel.x + 16, ay))
                ay += 18
        screen.blit(self.font_small.render("ESC to walk away", True, (140, 134, 122)),
                    (panel.x + 16, panel.bottom - 24))
