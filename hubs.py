"""hubs.py -- the illegal production hubs, as a KIND OF VILLAGE.

A hub is not a special effect and not a diorama. It is a `Village` -- the same
class the thirty-six towns are -- with a smaller radius, five fields instead of
a town's worth, one house, one bench, four people, and `nation = 1`.

That is the whole design, and it is the whole reason this file is short: every
thing a villager does in a town, a villager does in a hub, because it is the
same code reading the same fields. The farmer works `village.farm_plots`, the
artisan works `village.workplaces`, the trader runs the caravan, the board is a
board. There is no hub-specific behaviour anywhere, because a hub is not a
special case -- it is a small town that the state does not admit exists.

WHAT THE STATE CANNOT SEE. Hubs are NOT in `Villages` -- the registry every
crown, tax collector and army walks -- so no war can be declared on one, no
levy can be raised from one, and no census counts its people. Its protection is
not walls. It is not being on the list.
"""

from __future__ import annotations

import math
import os
import random

import pygame

import village as village_mod

NATION = 1              # the criminals' flag; the state does not acknowledge it
HUB_COUNT = 25          # 25 x 4 people = 100, about a tenth of the world
MIN_FROM_TOWN = 6200.0  # out of sight of any fence
HUB_RADIUS = 210.0
HUB_NAME = ("Stillwater", "Cinder Creek", "Hollow Ash", "Bitter Wells",
            "Crow Hollow", "Dry Gulch", "Salt Lick", "Sour Run", "Mud Lick",
            "Wolf Trap", "Grave Hollow", "Rattler's Rest", "Bone Ford",
            "Dead Ox", "Cold Camp", "Thin Pine", "Red Dirt", "Smoke Rise",
            "Long Gulch", "Quiet Fork", "Black Bank", "Last Chance",
            "Hard Scratch", "Poor Farm", "Nine Mile")


def _note(message: str) -> None:
    try:
        with open(os.path.expanduser("~/.kingpin_saves/village.log"), "a") as fh:
            fh.write(message + "\n")
    except Exception:
        pass


class Hub(village_mod.Village):
    """A town the size of a yard, and a criminal one."""

    is_hub = True
    is_capital = False

    def __init__(self, world, x: float, y: float, seed: int) -> None:
        # Built by the same constructor a town is built by -- from the cell it
        # stands in -- and then MADE SMALL and MOVED to where it belongs.
        gx = int(math.floor(x / village_mod.SPACING))
        gy = int(math.floor(y / village_mod.SPACING))
        super().__init__(gx, gy, seed)
        self.is_capital = False
        self.is_hub = True
        self.nation = NATION
        self.radius = HUB_RADIUS
        self.name = HUB_NAME[abs(hash((gx, gy, seed))) % len(HUB_NAME)]
        self.hub_seed = seed

        # ---- FOUR PEOPLE, NOT FORTY ------------------------------------
        wanted = ("soldier", "farm", None, "trader")     # None = the bench
        keep = []
        for job in wanted:
            if job is None:
                pick = next((n for n in self.npcs
                             if getattr(n, "workplace", None) is not None
                             or getattr(n, "job", None) in ("lab", "brewery")),
                            None)
            else:
                pick = next((n for n in self.npcs
                             if getattr(n, "job", None) == job), None)
            if pick is not None and pick not in keep:
                keep.append(pick)
        for job in ("farm", "trader"):
            if not any(getattr(n, "job", None) == job for n in keep):
                spare = next((n for n in self.npcs if n not in keep), None)
                if spare is not None:
                    spare.job = job
                    keep.append(spare)
        if not any(n not in keep and getattr(n, "workplace", None) for n in self.npcs):
            spare = next((n for n in self.npcs if n not in keep), None)
            if spare is not None:
                keep.append(spare)
        dropped = [n for n in self.npcs if n not in keep]
        for n in dropped:
            n.alive = False
            n.village = None
            try:
                if n in village_mod.PEOPLE:
                    village_mod.PEOPLE.remove(n)
            except Exception:
                pass
        self.npcs = keep
        for n in self.npcs:
            n.nation = NATION
            n.team = ("nation", NATION)
            n.village = self
            n.hub = self
            n.searched_village = self        # they live inside their own fence

        # ---- FOUR, WHATEVER THE TOWN GAVE US ---------------------------
        # A town no longer builds a bench (the state forbids the trade), so a
        # hub cannot inherit one -- it MAKES one. And a town's people are not
        # guaranteed to include a soldier. Both are filled in here, so a hub is
        # always the same four posts.
        import industry
        if not self.workplaces:
            try:
                wp = industry.Workplace("lab", self.x + 96.0, self.y - 40.0,
                                        seed + 5)
                self.workplaces.append(wp)
            except Exception:
                pass
        roles = [getattr(n, "job", None) for n in self.npcs]
        for need in ("soldier", "farm", "trader"):
            if need in roles:
                continue
            spare = next((n for n in self.npcs
                          if getattr(n, "job", None) not in ("soldier", "farm",
                                                             "trader")
                          and getattr(n, "workplace", None) is None), None)
            if spare is not None:
                spare.job = need
                roles.append(need)
        if not any(getattr(n, "workplace", None) is not None for n in self.npcs):
            hand = next((n for n in self.npcs
                         if getattr(n, "job", None) in (None, "logger", "hand")),
                        self.npcs[0] if self.npcs else None)
            if hand is not None and self.workplaces:
                hand.job = "lab"
                hand.workplace = self.workplaces[0]
                self.workplaces[0].worker = hand

        # ---- FIVE FIELDS, NOT FIFTY ------------------------------------
        self.farm_plots = list(self.farm_plots)[:5]
        for i, n in enumerate([n for n in self.npcs
                               if getattr(n, "job", None) == "farm"]):
            n.farm_plot = i

        # ---- ONE HOUSE AND ONE BENCH -----------------------------------
        self.houses = list(self.houses)[:1]
        bench = next((w for w in self.workplaces
                      if getattr(w, "kind", None) in ("lab", "brewery")), None)
        self.workplaces = [bench] if bench is not None else []
        if bench is not None:
            bench.kind = "lab"
            bench.worker = next((n for n in self.npcs
                                 if getattr(n, "workplace", None) is not None),
                                None)
            if bench.worker is not None:
                bench.worker.workplace = bench
        self.farm_plots = [(tx, ty, k) for (tx, ty, k) in self.farm_plots]

        # ---- AND MOVED TO WHERE IT STANDS ------------------------------
        dx = float(x) - float(self.x)
        dy = float(y) - float(self.y)
        self.x, self.y = float(x), float(y)
        for n in self.npcs:
            n.x += dx
            n.y += dy
            n.home = (n.x, n.y)
            n.refuge = None
        for h in self.houses:
            h.x += dx
            h.y += dy
        for w in self.workplaces:
            w.x += dx
            w.y += dy
            w.rect = pygame.Rect(int(w.x - w.rect.w / 2),
                                 int(w.y - w.rect.h / 2), w.rect.w, w.rect.h)
        for r in list(getattr(self, "fence_walls", ())):
            r.x = int(r.x + dx)
            r.y = int(r.y + dy)
        if getattr(self, "fence_rect", None) is not None:
            self.fence_rect = self.fence_rect.move(int(dx), int(dy))
        if getattr(self, "board", None) is not None:
            self.board = self.board.move(int(dx), int(dy))
        n_tiles = len(self.farm_plots)
        self.farm_plots = [(int(math.floor((self.x + (i - n_tiles / 2.0) * 34) / 32)),
                            int(math.floor((self.y + 96) / 32)), k)
                           for i, (_t, _u, k) in enumerate(self.farm_plots)]
        self.ledger_coins = max(60, int(self.ledger_coins))
        self.ledger_goods = {}

    def update(self, dt: float, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        # THE ORDINARY DAY. The town's own update, with the hub's own people in
        # it -- work by day, home by night, and the real trades in between.
        night = (float(now) % 600.0) >= 300.0
        super().update(dt, world, now, "home" if night else "work")
        # the soldier holds the gate and is not allowed to wander
        for n in self.npcs:
            if n.alive and getattr(n, "job", None) == "soldier":
                g = (self.gate_list()[0] if hasattr(self, "gate_list") else None)
                if g is not None:
                    n.x, n.y = g[1], g[2] + 26.0
                n.asleep = False

    def gate_list(self):
        import fence
        return fence.gate_list(self)

    # -- drawing: all of it the real renderers ---------------------------
    def draw(self, screen, cam_x: float, cam_y: float, vw: int = 900,
             vh: int = 900) -> None:
        import crop
        import fence
        ox, oy = -cam_x, -cam_y
        view = pygame.Rect(int(cam_x) - 300, int(cam_y) - 300, 1200, 1200)
        for (tx, ty, kind) in self.farm_plots:
            try:
                crop.draw_crop(screen, tx * 32 + 16, ty * 32 + 16,
                               "wheat" if kind in ("wheat", "food") else "plant",
                               70.0, cam_x, cam_y, None)
            except Exception:
                pass
        fence.draw(screen, cam_x, cam_y, self, view)
        for house in self.houses:
            try:
                house.draw(screen, cam_x, cam_y)
            except Exception:
                pass
        for wp in self.workplaces:
            try:
                wp.draw(screen, cam_x, cam_y)
            except Exception:
                pass
        for n in self.npcs:
            if n.alive:
                n.draw(screen, cam_x, cam_y, False)


class Hubs:
    def __init__(self, world, villages) -> None:
        self._world = world
        self._villages = villages
        self.hubs: list[Hub] = []
        self.build(world, villages)

    def build(self, world, villages) -> None:
        rng = random.Random(int(world.seed) ^ 0x0C0FFEE)
        towns = list(getattr(villages, "villages", ()) or ())
        tries = 0
        while len(self.hubs) < HUB_COUNT and tries < 6000:
            tries += 1
            x = rng.uniform(-86000.0, 86000.0)
            y = rng.uniform(-86000.0, 86000.0)
            if any((v.x - x) ** 2 + (v.y - y) ** 2 < MIN_FROM_TOWN ** 2
                   for v in towns):
                continue
            if any((h.x - x) ** 2 + (h.y - y) ** 2 < 9000.0 ** 2
                   for h in self.hubs):
                continue
            try:
                hub = Hub(world, x, y, rng.randrange(1 << 30))
            except Exception:
                continue
            self.hubs.append(hub)

    def update(self, dt: float, now: float) -> None:
        for hub in self.hubs:
            try:
                hub.update(dt, self._world, now)
            except Exception:
                pass

    def draw(self, screen, cam_x: float, cam_y: float, vw: int, vh: int) -> None:
        view = pygame.Rect(int(cam_x) - 300, int(cam_y) - 300, vw + 600, vh + 600)
        for hub in self.hubs:
            fr = getattr(hub, "fence_rect", None)
            if fr is not None and view.colliderect(fr):
                hub.draw(screen, cam_x, cam_y, vw, vh)

    def all_npcs(self) -> list:
        return [n for h in self.hubs for n in h.npcs if n.alive]
