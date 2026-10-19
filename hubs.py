"""hubs.py -- the illegal production hubs.

THE STATE FORBIDS WHAT PLEASES. Leaf, mash and the things made from them may not
be grown, dried, brewed or rolled inside a settlement, so they are grown outside
one. A hub is four people in the wild doing exactly that, and it is small on
purpose: a 5 by 5 plot, a house, a bench, a fence with a gate, and one soldier
standing at the gate because that gate is the only thing between them and
everyone.

THEY ARE NOT A VILLAGE, AND THAT IS THE POINT. They are not in `villages`, so
nothing that walks a village list can find them -- no taxes, no census, no war,
no conquest, no refugees. A hub cannot be declared on, because no one admits it
exists. That is the whole of their protection, and it is the same protection the
real thing has always had: not walls, but not being on the list.

WHAT THEY SHARE IS EVERYTHING. One purse, one larder, one stack of leaf. Nobody
in a hut owns a coin; the hut does. The trader carries the goods out to a village
and brings the money back, and that money buys the next crop.

THE FOUR:
    the FARMER    works the 5x5 -- twenty tiles of leaf and five of food
    the ARTISAN   works the bench, turning leaf into what it becomes
    the TRADER    carries it to the nearest village and sells it there
    the SOLDIER   stands at the gate and never leaves it
"""

from __future__ import annotations

import math
import os
import random

import pygame

import biomes
import economy
import items
import village as village_mod

# THE FACTION. Index 1 in the state's own registry of who-is-who, though the
# state does not acknowledge that the index exists.
NATION = 1


def _note(message: str) -> None:
    try:
        with open(os.path.expanduser("~/.kingpin_saves/village.log"), "a") as fh:
            fh.write(message + "\n")
    except Exception:
        pass

HUB_COUNT = 25              # 25 hubs x 4 people = 100, about a tenth of the world
MIN_FROM_VILLAGE = 6200.0   # out of sight of any fence
SPACING = 160.0             # a 5x5 of 32-pixel tiles
PLOT = 5

LEAF_PER_MIN = 2.0          # what twenty tiles of leaf yield
FOOD_PER_MIN = 0.6
CONVERT_MIN = 3.0           # leaf into product
CARRY_MIN = 55.0            # a trader walks out this often
CARRY_MAX = 12              # and carries up to this much

FENCE = (120, 96, 62)
FENCE_DARK = (84, 66, 42)
DIRT = (74, 62, 44)
LEAF_SOIL = (58, 74, 42)
FOOD_SOIL = (78, 74, 40)
HOUSE_WALL = (86, 74, 58)
HOUSE_ROOF = (58, 44, 36)
BENCH = (110, 92, 66)
GATE = (150, 120, 74)


class Hub:
    """Four people, one purse, one illegal crop."""

    def __init__(self, world, x: float, y: float, seed: int) -> None:
        self.x = float(x)
        self.y = float(y)
        self.seed = seed & 0xFFFFFFFF
        self.rng = random.Random(self.seed)
        self.coins = self.rng.randint(40, 120)      # the shared purse
        self.stock = {}                             # the shared shelf
        self.leaf_kind = "plant"
        self.brew_kind = "lab"
        self.timer = self.rng.uniform(0.0, 30.0)
        self.carry_t = self.rng.uniform(10.0, CARRY_MIN)
        self.npcs: list = []

        # THE GROUND. A 5x5 of tiles: one row of food, the rest leaf.
        cx = int(math.floor(self.x / 32.0))
        cy = int(math.floor(self.y / 32.0))
        self.plots = []
        for j in range(PLOT):
            for i in range(PLOT):
                kind = "food" if j == 0 else "leaf"
                self.plots.append((cx + i - PLOT // 2, cy + j - PLOT // 2, kind))
        half = SPACING * 0.5
        self.fence = pygame.Rect(int(self.x - half - 26), int(self.y - half - 26),
                                 int(SPACING + 52), int(SPACING + 52))
        self.gate = pygame.Rect(int(self.x - 18), self.fence.bottom - 5, 36, 10)
        self.house = pygame.Rect(int(self.x - 44), int(self.y - half - 96), 88, 62)
        self.bench = pygame.Rect(int(self.x + half - 40), int(self.y + 6), 44, 26)

        self._people()

    # -- the four ---------------------------------------------------------
    def _food(self) -> str:
        """The food of the country this hub stands in."""
        try:
            t = float(biomes.temperature(self.x, self.y, 20240501))
            h = float(biomes.humidity(self.x, self.y, 20240501))
            return biomes.crop_kinds(t, h)[0]
        except Exception:
            return "wheat"

    def _people(self) -> None:
        names = village_mod.FIRST_NAMES
        lasts = village_mod.LAST_NAMES
        roles = (("soldier", "soldier"), ("farm", "farmer"),
                 (self.brew_kind, "artisan"), ("trader", "trader"))
        for k, (job, _label) in enumerate(roles):
            r = random.Random(self.seed + k * 7919)
            who = "%s %s" % (r.choice(names), r.choice(lasts))
            npc = village_mod.NPC(self.x + (k - 1.5) * 22.0,
                                  self.y + 24.0 + (k % 2) * 12.0,
                                  self.seed + k * 131, who,
                                  "%08x%02x" % (self.seed, k), "Criminal", None)
            npc.job = job
            # AND NOBODY IS BORN GOOD AT IT. Four people start at nothing, the
            # same as the player and the same as every villager -- whatever
            # they become they become by doing it.
            # TEN OF THE LOCAL FOOD EACH, IN HIS OWN PACK. They live off it,
            # and whatever they do not eat they put on the shared shelf.
            npc.stock[self._food()] = 10
            npc.nation = NATION
            npc.team = ("nation", NATION)
            npc.hub = self
            if job == "soldier":
                npc.x, npc.y = self.gate.centerx, self.gate.centery + 14.0
                npc.home = (npc.x, npc.y)
                npc.weapon = "rifle"
            self.npcs.append(npc)
            # THEY ARE NOT ON ANYBODY'S REGISTER. The village machinery walks
            # `PEOPLE` every tick and would step them again, with no village to
            # step them in -- so they are taken off it and stepped here.
            if npc in village_mod.PEOPLE:
                village_mod.PEOPLE.remove(npc)

    # -- the work ---------------------------------------------------------
    def update(self, dt: float, now: float, villages) -> None:
        # NOBODY HERE KEEPS A TOWN'S HOURS. No church, no market, no shift, no
        # day off: they work while it is light and they sleep while it is dark,
        # and the SOLDIER DOES NOT SLEEP AT ALL -- he stands at the gate because
        # a gate nobody watches is a door.
        night = self._is_night(now)
        for npc in self.npcs:
            if npc.job == "soldier":
                npc.asleep = False
                npc.x, npc.y = self.gate.centerx, self.gate.centery + 14.0
                continue
            npc.asleep = night
            if night:
                npc.x, npc.y = self.house.centerx + (npc.rng.random() - 0.5) * 30.0, \
                    self.house.centery + 20.0
        # EVERYTHING IS SHARED, SO EVERYTHING IS SHARED OUT. The purse is not
        # the hut's and the food is not the shelf's: what the hub has, its four
        # people have, equally, and then they go and earn some more. Every few
        # minutes the till is split and the shelf is emptied into their packs.
        self.split_t = getattr(self, "split_t", 180.0) - dt
        if self.split_t <= 0.0:
            self.split_t = 180.0
            live = [n for n in self.npcs if n.alive]
            if live:
                share = int(self.coins) // len(live)
                for n in live:
                    n.coins += share
                self.coins -= share * len(live)
                for item, qty in list(self.stock.items()):
                    if item in ("bread", "berries", "cactus_fruit", "wheat") and qty > 0:
                        per = int(qty) // len(live)
                        if per:
                            for n in live:
                                n.stock[item] = n.stock.get(item, 0) + per
                            self.stock[item] = int(qty) - per * len(live)
        self._carry_step(dt)
        self.timer += dt
        while self.timer >= 60.0:                   # a minute of growing
            self.timer -= 60.0
            self.stock["tobacco"] = (self.stock.get("tobacco", 0)
                                     + int(LEAF_PER_MIN))
            self.stock["bread"] = self.stock.get("bread", 0) + 1
        # the bench
        leaf = int(self.stock.get("tobacco", 0))
        if leaf >= 3 and now - getattr(self, "_last_convert", 0.0) > CONVERT_MIN:
            self._last_convert = now
            self.stock["tobacco"] = leaf - 3
            out = "cigar" if self.brew_kind == "lab" else "beer"
            self.stock[out] = self.stock.get(out, 0) + 2
        # the trader carries it out
        self.carry_t -= dt
        if self.carry_t <= 0.0:
            self.carry_t = self.rng.uniform(CARRY_MIN, CARRY_MIN * 2.0)
            self._sell_out(villages)

    def _sell_out(self, villages) -> None:
        """SEND THE TRADER, DO NOT TELEPORT THE GOODS.

        This used to put the cigars into the nearest town's store and take the
        coin out of its ledger from where it stood -- no gate, no guard, no
        search, no risk. Twenty-five hubs minted money by not existing as far
        as the border was concerned, which made the whole apparatus of the
        state decorative.

        Now he LOADS UP and WALKS. He crosses the town's fence at the gate,
        stands in the queue with everybody else, and the guard decides whether
        he is a trader or a criminal. If he is caught the cargo is gone and the
        town is provoked. Whatever gets through teaches him the trade.
        """
        towns = getattr(villages, "villages", villages)
        if not towns or getattr(self, "_carrier", None) is not None:
            return
        goods = [k for k in ("cigar", "beer", "liqueur", "mezcal",
                             "dried_mushroom") if self.stock.get(k, 0) > 0]
        if not goods:
            return
        trader = next((n for n in self.npcs
                       if n.alive and n.job == "trader"), None)
        if trader is None:
            return
        cargo = {}
        for item in goods:
            take = min(int(self.stock[item]), CARRY_MAX)
            if take > 0:
                self.stock[item] -= take
                cargo[item] = take
        if not cargo:
            return
        near = min(towns, key=lambda v: (v.x - self.x) ** 2 + (v.y - self.y) ** 2)
        self._carrier = trader
        self._cargo = cargo
        self._goal = near
        self._stage = "out"

    def _carry_step(self, dt: float) -> None:
        """He walks there, is searched at the gate, and walks back."""
        trader = getattr(self, "_carrier", None)
        if trader is None or not trader.alive:
            self._carrier = None
            self._cargo = {}
            return
        town = self._goal
        if (town.x - trader.x) ** 2 + (town.y - trader.y) ** 2 > 120.0 ** 2:
            dx, dy = town.x - trader.x, town.y - trader.y
            d = math.hypot(dx, dy) or 1.0
            step = min(d, 70.0 * dt)
            trader.x += dx / d * step
            trader.y += dy / d * step
            return
        if self._stage == "out":
            # AT THE GATE. The guard's roll, the same one the player faces.
            units = sum(self._cargo.values())
            skill = max(0.0, min(10.0, float(getattr(trader, "smuggling", 0.0))))
            found = min(1.0, units / 100.0) * 0.55 * (1.0 - 0.09 * skill)
            if trader.rng.random() < found:
                town.provoked = True
                trader.wanted = True
                self._cargo = {}
                _note("HUB SEARCH  %s caught at %s with %d"
                      % (trader.name, town.name, units))
            else:
                for item, take in self._cargo.items():
                    economy.store_add(town, item, take, 2)
                    unit = max(1, int(round(economy.value(town, item) * 0.5)))
                    self.coins += take * unit
                    town.ledger_coins = max(0, int(town.ledger_coins) - take * unit)
                trader.smuggling = min(10.0, skill + 0.06 + units * 0.001)
                self._cargo = {}
            self._stage = "home"
            return
        self._carrier = None
        self._cargo = {}

    @staticmethod
    def _is_night(now: float) -> bool:
        """Half the ten-minute day is dark."""
        return (float(now) % 600.0) >= 300.0

    # -- the picture ------------------------------------------------------
    def draw(self, screen, cam_x: float, cam_y: float) -> None:
        ox, oy = -cam_x, -cam_y
        for cx, cy, kind in self.plots:
            px = int(cx * 32 + ox)
            py = int(cy * 32 + oy)
            pygame.draw.rect(screen, FOOD_SOIL if kind == "food" else LEAF_SOIL,
                             (px, py, 32, 32))
        pygame.draw.rect(screen, FENCE_DARK, self.fence.move(ox, oy), 3)
        pygame.draw.rect(screen, GATE, self.gate.move(ox, oy))
        pygame.draw.rect(screen, HOUSE_WALL, self.house.move(ox, oy))
        pygame.draw.rect(screen, HOUSE_ROOF,
                         self.house.move(ox, oy).inflate(-10, -28).move(0, -6))
        pygame.draw.rect(screen, BENCH, self.bench.move(ox, oy))
        for npc in self.npcs:
            if npc.alive:
                npc.draw(screen, cam_x, cam_y, False)


class Hubs:
    def __init__(self, world, villages) -> None:
        self.hubs: list[Hub] = []
        self._world = world
        self._villages = villages
        self.build(world, villages)

    def build(self, world, villages) -> None:
        """Twenty-five of them, out of sight of every fence and every other."""
        rng = random.Random(int(world.seed) ^ 0x0C0FFEE)
        towns = list(getattr(villages, "villages", ()))
        tries = 0
        while len(self.hubs) < HUB_COUNT and tries < 4000:
            tries += 1
            x = rng.uniform(-84000.0, 84000.0)
            y = rng.uniform(-84000.0, 84000.0)
            if any((v.x - x) ** 2 + (v.y - y) ** 2
                   < MIN_FROM_VILLAGE ** 2 for v in towns):
                continue
            if any((h.x - x) ** 2 + (h.y - y) ** 2 < 9000.0 ** 2
                   for h in self.hubs):
                continue
            self.hubs.append(Hub(world, x, y, rng.randrange(1 << 30)))

    def update(self, dt: float, now: float) -> None:
        for hub in self.hubs:
            hub.update(dt, now, self._villages)
        self._refill(dt, now)

    def _refill(self, dt: float, now: float) -> None:
        """A HUB THAT LOSES A MAN TAKES ANOTHER ONE FROM THE TOWNS.

        The trade does not shrink because a carrier was shot; it recruits. Some
        idle man in a city -- no post, no plot, nothing to inherit -- walks out
        of the gate, and by the time he reaches the fence he is a Criminal. He
        does it himself: no one sends for him.
        """
        towns = list(getattr(self._villages, "villages", ()) or ())
        for hub in self.hubs:
            need = [r for r in ("soldier", "farm", hub.brew_kind, "trader")
                    if not any(n.alive and getattr(n, "job", None) == r
                               for n in hub.npcs)]
            if not need or not towns:
                continue
            walker = getattr(hub, "_walker", None)
            if walker is not None and walker.alive:
                dx = hub.x - walker.x
                dy = hub.y - walker.y
                d = math.hypot(dx, dy)
                if d < 90.0:
                    walker.x, walker.y = hub.x + 18.0, hub.y + 26.0
                    walker.home = (walker.x, walker.y)
                    walker.hub = hub
                    hub.npcs.append(walker)
                    hub._walker = None
                else:
                    step = min(d, 60.0 * dt)
                    walker.x += dx / d * step
                    walker.y += dy / d * step
                continue
            # find a man with nothing to lose
            pick = None
            for town in towns:
                for n in town.npcs:
                    if (n.alive and not getattr(n, "job", None)
                            and getattr(n, "farm_plot", None) is None
                            and not getattr(n, "defender", False)
                            and not getattr(n, "is_commander", False)
                            and not getattr(n, "is_king", False)
                            and not getattr(n, "is_mayor", False)
                            and not getattr(n, "is_soldier", False)):
                        pick = (town, n)
                        break
                if pick:
                    break
            if pick is None:
                continue
            town, man = pick
            if man in town.npcs:
                town.npcs.remove(man)
            man.nation = NATION
            man.team = ("nation", NATION)
            man.job = need[0]
            man.role = "Criminal"
            man.village = None
            if man in village_mod.PEOPLE:
                village_mod.PEOPLE.remove(man)
            hub._walker = man

    def draw(self, screen, cam_x: float, cam_y: float, vw: int, vh: int) -> None:
        view = pygame.Rect(int(cam_x) - 200, int(cam_y) - 200, vw + 400, vh + 400)
        for hub in self.hubs:
            if view.colliderect(hub.fence):
                hub.draw(screen, cam_x, cam_y)

    def all_npcs(self) -> list:
        out = []
        for hub in self.hubs:
            out.extend(n for n in hub.npcs if n.alive)
        return out
