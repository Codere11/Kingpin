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

import economy
import pygame
import world as world_mod

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

        # ---- EXACTLY FOUR, WITH THE FOUR POSTS --------------------------
        # Built from scratch rather than hoped for. The town no longer makes a
        # bench, so the hub MAKES one; and the four posts are assigned by
        # index, so a hub is always a soldier, a farmer, a bench hand and a
        # trader, whatever the town happened to give us.
        import industry
        # THE BENCH, AND ONLY THE BENCH. A town's workplaces belong to the
        # town -- three mines and a smithy it built for itself -- and they are
        # nowhere near this yard. A hub has exactly one bench, standing in it.
        wp = industry.Workplace("lab", self.x + 96.0, self.y - 40.0, seed + 5)
        self.workplaces = [wp]
        bench = wp
        while len(self.npcs) < 4:
            k = len(self.npcs)
            who = "%s %s" % (self._rng.choice(village_mod.FIRST_NAMES),
                             self._rng.choice(village_mod.LAST_NAMES))
            n = village_mod.NPC(self.x + (k - 1.5) * 26.0, self.y + 30.0,
                                self._rng.randrange(1 << 30), who,
                                "%08x%02x" % (seed & 0xFFFFFFFF, k),
                                "Criminal", self)
            self.npcs.append(n)
        self.npcs = self.npcs[:4]
        for k, (n, job) in enumerate(zip(self.npcs,
                                         ("soldier", "farm", "lab", "trader"))):
            n.job = job
            n.role = "Criminal"
            n.village = self
            n.hub = self
            n.nation = NATION
            n.team = ("nation", NATION)
            n.searched_village = self
            n.farm_plot = 0 if job == "farm" else None
            n.workplace = bench if job == "lab" else None
            if job == "farm":
                n.leaf_farmer = True
                n.stock["shovel"] = 1
                n.tool_uses = economy.TOOL_USES
            n.stock.clear()
            n.stock[self._food_kind()] = 10
        bench.worker = self.npcs[2]

        # ---- FIVE FIELDS, IN THE YARD, IN THE WORLD'S OWN PLOT MAP -----
        # The town's plots are ITS plots, at its own coordinates -- the farmer
        # walked to them and the world had never heard of them, which threw a
        # KeyError out of _work_field every single tick. A hub's fields are
        # planted where the hub is, in `world.plots`, so the crop machinery
        # knows them.
        self.farm_plots = []
        for k in range(5):
            tx = int(math.floor((self.x - 80 + (k % 3) * 34) / 32.0))
            ty = int(math.floor((self.y + 74 + (k // 3) * 34) / 32.0))
            self.farm_plots.append((tx, ty, "wheat"))
            if world is not None:
                try:
                    world.plots[(tx, ty)] = world_mod.Plot("wheat", 0.0)
                except Exception:
                    pass
        for n in self.npcs:
            n.farm_plot = 0 if getattr(n, "job", None) == "farm" else None

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
        # AND RE-FENCED AT ITS OWN SIZE. The fence inherited from the town is
        # five thousand pixels square -- the whole town's wall. A hub is two
        # hundred and ten pixels of yard with one gate, built by the same
        # `fence.install` a town uses.
        import fence
        self.radius = HUB_RADIUS
        fence.install(self, self._rng)
        # AND ONLY NOW IS THERE A HOUSE, because only now is the fence the
        # hub's own. It was built against the TOWN's five-thousand-pixel wall
        # -- five kilometres from where the hub stands -- so the yard had a
        # bench, two gates and not one building inside it.
        self.houses = []
        try:
            _fr = self.fence_rect
            _house = village_mod.House(self.x - _fr.w * 0.26,
                                       self.y - _fr.h * 0.26, 96, 68,
                                       (118, 62, 50), (0.0, 1.0), seed + 13)
            _house.village = self
            _house.occupants = []
            self.houses = [_house]
        except Exception:
            pass
        self.ledger_coins = max(60, int(self.ledger_coins))
        self.ledger_goods = {}

    def _food_kind(self) -> str:
        try:
            import biomes
            return biomes.crop_kinds(float(biomes.temperature(self.x, self.y, 20240501)),
                                     float(biomes.humidity(self.x, self.y, 20240501)))[0]
        except Exception:
            return "wheat"

    def update(self, dt: float, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        """THE DAY, AND THE WORK.

        `Village.update` is the TOWN's business -- its books, its board, its
        roster -- and it has never ticked a single man. In a town the main loop
        walks `PEOPLE` and calls `NPC.tick` on every one of them. Hub folk were
        taken off `PEOPLE` (so they would not be stepped twice) and then
        nothing stepped them at all: four people, four posts, and not one of
        them ever moving or working.

        So the hub ticks its own, with the same call the world uses.
        """
        night = (float(now) % 600.0) >= 300.0
        for n in self.npcs:
            if not n.alive:
                continue
            try:
                n.tick(dt, world, now, "home" if night else "work",
                       night=night)
            except Exception:
                pass
        try:
            super().update(dt, world, now, "home" if night else "work")
        except Exception:
            pass
        # AND THE SOLDIER NEVER LEAVES THE GATE -- held last, after his own
        # step, so nothing can walk him off it.
        for n in self.npcs:
            if n.alive and getattr(n, "job", None) == "soldier":
                try:
                    g = self.gate_list()[0]
                    n.x, n.y = g[1], g[2] + 26.0
                    n.asleep = False
                except Exception:
                    pass

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
