"""TEST MODE: LOOK AT ANYBODY.

Press I to open the inspector. It lists every living person in the world, and
you can filter by profession, by village and by nation. Pick one and the game
LOCK ON to him: the camera leaves the player and follows that person, the
player is frozen where he stood and made invulnerable, and a log of what the
chosen man actually does is written from that moment until you let him go.

THE POINT IS THE OPTIMISATION, and it is all in what is NOT done:

  * The classic log is quiet. World population, town captures, and the
    nemesis -- nothing else. See note_world().
  * ONCE LOCKED ON, the ground around the PLAYER is never built, because the
    camera is not there. Drawing follows the camera, so the whole cost of the
    player's surroundings disappears the moment you look away from him.
  * The player does not move. He is pinned, so the camera cannot be dragged by
    a wolf and no chunk is rebuilt because of him.
  * ONLY THE OBSERVED MAN'S LOG IS WRITTEN, and only while he is observed. It
    starts when you lock on and stops when you let go. Nothing about anybody
    else is recorded at all.

That is the difference between watching a world and watching a man.
"""

from __future__ import annotations

import math
import time

import pygame

# What the inspector shows and how it sorts.
FILTER_NONE = 0
FILTER_JOB = 1
FILTER_TOWN = 2
FILTER_NATION = 3
FILTER_NAMES = ("all", "profession", "village", "nation")

ROW = 16


def job_of(npc) -> str:
    """What a man actually does -- the same words the day log uses."""
    if getattr(npc, "is_king", False):
        return "king"
    if getattr(npc, "is_mayor", False):
        return "mayor"
    if getattr(npc, "is_commander", False):
        return "commander"
    if getattr(npc, "defender", False):
        return "soldier"
    if getattr(npc, "levied", False):
        return "soldier"
    j = getattr(npc, "job", None)
    if j:
        return j
    if getattr(npc, "farm_plot", None) is not None:
        return "farmer"
    return "idle"


class Observer:
    """The inspector, the lock-on, and the log of the man being watched."""

    def __init__(self) -> None:
        self.open = False
        self.target = None            # the man being watched
        self.scroll = 0
        self.filt = FILTER_NONE
        self.filt_key = None          # the village / nation / job being shown
        self.log: list = []           # HIS log, from the moment of lock-on
        self.t0 = 0.0
        self._last = None             # last snapshot, for diffing
        self._last_log_t = 0.0
        self.font = pygame.font.SysFont("dejavusans", 14, bold=True)
        self.small = pygame.font.SysFont("dejavusans", 12)

    # -- the list ----------------------------------------------------------
    def everyone(self) -> list:
        import village
        return [n for n in village.PEOPLE if getattr(n, "alive", True)]

    def rows(self) -> list:
        out = self.everyone()
        if self.filt == FILTER_JOB and self.filt_key:
            out = [n for n in out if job_of(n) == self.filt_key]
        elif self.filt == FILTER_TOWN and self.filt_key:
            out = [n for n in out
                   if getattr(getattr(n, "village", None), "name", "?")
                   == self.filt_key]
        elif self.filt == FILTER_NATION and self.filt_key is not None:
            out = [n for n in out if getattr(n, "nation", None) == self.filt_key]
        out.sort(key=lambda n: (job_of(n),
                                getattr(getattr(n, "village", None), "name", ""),
                                n.name))
        return out

    def keys(self) -> list:
        """The values available for the current filter."""
        vals = set()
        for n in self.everyone():
            if self.filt == FILTER_JOB:
                vals.add(job_of(n))
            elif self.filt == FILTER_TOWN:
                vals.add(getattr(getattr(n, "village", None), "name", "?"))
            elif self.filt == FILTER_NATION:
                vals.add(getattr(n, "nation", None))
        return sorted(vals, key=lambda v: (v is None, str(v)))

    # -- keys --------------------------------------------------------------
    def handle(self, event, player) -> bool:
        """Returns True if the event was consumed."""
        if event.type != pygame.KEYDOWN:
            return False
        k = event.key
        if k == pygame.K_i:
            self.open = not self.open
            return True
        if not self.open:
            return False
        if k == pygame.K_x and self.target is not None:
            self.release()
            return True
        if k == pygame.K_f:
            self.filt = (self.filt + 1) % len(FILTER_NAMES)
            self.filt_key = None
            self.scroll = 0
            return True
        if k in (pygame.K_LEFT, pygame.K_RIGHT) and self.filt:
            ks = self.keys()
            if ks:
                if self.filt_key in ks:
                    i = ks.index(self.filt_key)
                    self.filt_key = ks[(i + (1 if k == pygame.K_RIGHT else -1))
                                       % len(ks)]
                else:
                    self.filt_key = ks[0]
            self.scroll = 0
            return True
        if k == pygame.K_DOWN:
            self.scroll += 1
            return True
        if k == pygame.K_UP:
            self.scroll = max(0, self.scroll - 1)
            return True
        if k == pygame.K_RETURN:
            rs = self.rows()
            if rs:
                self.observe(rs[min(self.scroll, len(rs) - 1)])
            return True
        return False

    # -- lock on, let go ---------------------------------------------------
    def observe(self, npc) -> None:
        """START WATCHING THIS MAN. His log begins here, and only his."""
        self.target = npc
        self.log = []
        self.t0 = time.time()
        self._last = self.snap(npc)
        self._last_log_t = 0.0
        self.say("-- locked on to %s of %s (%s)"
                 % (npc.name, getattr(getattr(npc, "village", None), "name", "?"),
                    job_of(npc)))

    def release(self) -> None:
        if self.target is not None:
            self.say("-- let go of %s" % self.target.name)
        self.target = None
        self._last = None

    def say(self, line: str) -> None:
        self.log.append(line)
        if len(self.log) > 400:
            del self.log[:100]

    # -- his state, and what changed ---------------------------------------
    @staticmethod
    def snap(n) -> dict:
        op = getattr(n, "opinion", None) or {}
        sk = getattr(n, "skills", None)
        return {
            "x": n.x, "y": n.y, "coins": n.coins,
            "job": job_of(n), "hunger": round(getattr(n, "hunger", 0.0)),
            "food": sum(int(n.stock.get(f, 0)) for f in ("bread", "berries",
                                                         "cactus_fruit")),
            "wood": int(n.stock.get("wood", 0)),
            "iron": int(n.stock.get("iron", 0)),
            "axe": round(sk.axe, 2) if sk else 0,
            "farm": round(sk.farming, 2) if sk else 0,
            "move": round(sk.move_scale(), 2) if sk else 0,
            "asleep": bool(getattr(n, "asleep", False)),
            "trades": len(op),
            "village": getattr(getattr(n, "village", None), "name", "?"),
            "nation": getattr(n, "nation", None),
        }

    def tick(self, now: float) -> None:
        """Sample the man being watched and write down what CHANGED.

        This is his log and nobody else's -- the game writes no per-man
        history, so the observer makes one by watching him.
        """
        n = self.target
        if n is None or not getattr(n, "alive", False):
            if n is not None:
                self.say("day %.2f  HE IS DEAD" % (now / 600.0))
                self.target = None
            return
        if now - self._last_log_t < 1.0:
            return
        self._last_log_t = now
        s = self.snap(n)
        p = self._last or s
        d = now / 600.0
        if s["job"] != p["job"]:
            self.say("day %.2f  took the %s post  (was %s)"
                     % (d, s["job"], p["job"]))
        if s["village"] != p["village"]:
            self.say("day %.2f  left %s for %s" % (d, p["village"], s["village"]))
        if s["asleep"] != p["asleep"]:
            self.say("day %.2f  %s" % (d, "went to sleep" if s["asleep"]
                                       else "woke up"))
        if s["coins"] != p["coins"]:
            self.say("day %.2f  coin %+d  (now %d)"
                     % (d, s["coins"] - p["coins"], s["coins"]))
        for k, label in (("farm", "farming"), ("axe", "axe")):
            if s[k] > p[k]:
                self.say("day %.2f  %s %.2f -> %.2f" % (d, label, p[k], s[k]))
        if s["food"] < p["food"] and s["food"] <= 2:
            self.say("day %.2f  larder down to %d" % (d, s["food"]))
        if s["wood"] != p["wood"] and abs(s["wood"] - p["wood"]) >= 10:
            self.say("day %.2f  wood %s%d" % (d, "+" if s["wood"] > p["wood"] else "",
                                              s["wood"] - p["wood"]))
        if s["trades"] > p["trades"]:
            self.say("day %.2f  dealt with somebody new (%d partners)"
                     % (d, s["trades"]))
        moved = math.hypot(s["x"] - p["x"], s["y"] - p["y"])
        if moved > 400.0:
            self.say("day %.2f  travelled %.0f px" % (d, moved))
        self._last = s

    # -- drawing -----------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        vw, vh = screen.get_size()
        if self.target is not None:
            self._draw_target(screen, vw, vh)
        if not self.open:
            return
        w, h = min(760, vw - 40), min(560, vh - 40)
        panel = pygame.Rect((vw - w) // 2, (vh - h) // 2, w, h)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (22, 20, 18), panel, border_radius=10)
        pygame.draw.rect(screen, (150, 110, 62), panel, 2, border_radius=10)
        title = self.font.render("WHO --  I closes,  f filter(%s),  "
                                 "<> value,  up/down,  Enter watch,  x let go"
                                 % FILTER_NAMES[self.filt], True, (238, 226, 196))
        screen.blit(title, (panel.left + 12, panel.top + 10))
        sub = "  value: %s" % (self.filt_key if self.filt_key is not None else "-")
        screen.blit(self.small.render(sub, True, (198, 176, 128)),
                    (panel.left + 12, panel.top + 30))
        rows = self.rows()
        first = panel.top + 52
        per = max(1, (panel.bottom - first - 26) // ROW)
        self.scroll = max(0, min(self.scroll, max(0, len(rows) - per)))
        for i in range(per):
            j = self.scroll + i
            if j >= len(rows):
                break
            n = rows[j]
            y = first + i * ROW
            hit = (j == self.scroll)
            if hit:
                pygame.draw.rect(screen, (52, 46, 36),
                                 (panel.left + 8, y - 2, panel.width - 16, ROW))
            line = ("%-16s %-9s %-14s nat %-3s  coin %6d  food %3d  hunger %3d%s"
                    % (n.name, job_of(n),
                       getattr(getattr(n, "village", None), "name", "?"),
                       getattr(n, "nation", None), n.coins,
                       sum(int(n.stock.get(f, 0))
                           for f in ("bread", "berries", "cactus_fruit")),
                       int(getattr(n, "hunger", 0)),
                       "   ASLEEP" if getattr(n, "asleep", False) else ""))
            screen.blit(self.small.render(line, True, (232, 228, 218)),
                        (panel.left + 12, y))
        screen.blit(self.small.render("%d shown of %d alive"
                                      % (len(rows), len(self.everyone())),
                                      True, (150, 146, 138)),
                    (panel.left + 12, panel.bottom - 20))

    def _draw_target(self, screen, vw, vh) -> None:
        """The watched man's log, and a mark over his head."""
        n = self.target
        w = min(430, vw - 30)
        h = min(260, vh - 30)
        panel = pygame.Rect(vw - w - 12, vh - h - 12, w, h)
        board = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(board, (18, 16, 14, 232), board.get_rect(),
                         border_radius=8)
        pygame.draw.rect(board, (150, 110, 62, 235), board.get_rect(), 1,
                         border_radius=8)
        screen.blit(board, panel.topleft)
        head = self.font.render("WATCHING  %s" % n.name, True, (240, 226, 172))
        screen.blit(head, (panel.left + 10, panel.top + 8))
        info = self.small.render(
            "%s of %s, nation %s   coin %d" % (job_of(n),
                getattr(getattr(n, "village", None), "name", "?"),
                getattr(n, "nation", None), n.coins),
            True, (198, 176, 128))
        screen.blit(info, (panel.left + 10, panel.top + 26))
        show = self.log[-(h // 14 - 3):]
        for i, line in enumerate(show):
            screen.blit(self.small.render(line, True, (222, 218, 208)),
                        (panel.left + 10, panel.top + 46 + i * 14))
