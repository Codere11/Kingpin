"""hubs.py -- the illegal production hubs.

A HUB IS A VILLAGE. Not a diorama, not a special effect: a `Hub(Village)`, the
same class the thirty-six towns are, built by the same constructor, and then
made small. Everything a villager does in a town, a villager does in a hub,
because it is the same code reading the same fields.

WHAT THE TOWNS DO THAT A HUB MUST ALSO DO -- the list I got wrong four times:

  `farm_plots`   [(ctx, cty, kind)] -- one entry per field
  `farm_tiles`   {(ctx, cty): [(tx, ty, kind) ...]} -- THE TILES OF EACH FIELD.
                 `NPC._work_field` reads this and nothing else: without it a
                 farmer throws KeyError the moment he gets to his rows.
  `_seed_fields` plants those tiles into the world's plot map so there is a
                 standing crop on day one instead of a bare field.
  `registry`     the Villages object, so a trader can ask `nearest_other()` for
                 somewhere to go. A hub is NOT in `_cache`, so the crown, the
                 tax, the levy and the war code still cannot see it.
  `workplaces`   a real `industry.Workplace`, with `.worker` set.
  `houses`       a real `village.House`, inside the fence.
  `npcs`         four people, each with the field his trade reads:
                 `workplace` for the bench hand, `farm_plot` for the farmer.

AND WHO STEPS THEM. In a town the main loop walks `PEOPLE` and calls `NPC.tick`
on each man. A hub's people are not in `PEOPLE` (they must not be stepped
twice), so THE HUB STEPS THEM ITSELF, with the same call. `Village.update` is
the town's business -- books, board, roster -- and has never ticked a man.
"""

from __future__ import annotations

import math
import os
import random

import pygame

import economy
import fence
import industry
import village as village_mod
import world as world_mod

NATION = 1              # the criminals' flag; the state does not acknowledge it
HUB_COUNT = 25          # 25 x 4 = 100 people, about a tenth of the world
MIN_FROM_TOWN = 6200.0  # out of sight of any fence
HUB_RADIUS = 210.0

NAMES = ("Stillwater", "Cinder Creek", "Hollow Ash", "Bitter Wells",
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

    def __init__(self, world, x: float, y: float, seed: int,
                 registry=None) -> None:
        gx = int(math.floor(float(x) / village_mod.SPACING))
        gy = int(math.floor(float(y) / village_mod.SPACING))
        # 1. THE TOWN, BUILT AS A TOWN IS BUILT.
        super().__init__(gx, gy, seed)
        self.is_capital = False
        self.is_hub = True
        self.nation = NATION
        self.registry = registry            # so a trader can find a town
        self.name = NAMES[abs(hash((gx, gy, seed))) % len(NAMES)]

        # 2. FOUR PEOPLE, WITH THE FOUR POSTS.
        while len(self.npcs) < 4:
            k = len(self.npcs)
            who = "%s %s" % (self._rng.choice(village_mod.FIRST_NAMES),
                             self._rng.choice(village_mod.LAST_NAMES))
            self.npcs.append(village_mod.NPC(
                self.x + (k - 1.5) * 26.0, self.y + 30.0,
                self._rng.randrange(1 << 30), who,
                "%08x%02x" % (seed & 0xFFFFFFFF, k), "Criminal", self))
        keep = self.npcs[:4]
        for n in self.npcs[4:]:
            n.alive = False
            n.village = None
            if n in village_mod.PEOPLE:
                village_mod.PEOPLE.remove(n)
        self.npcs = keep
        for n in self.npcs:
            if n in village_mod.PEOPLE:     # stepped by the hub, not the world
                village_mod.PEOPLE.remove(n)

        # 3. (the bench is built AFTER the move -- see below)

        # 4. FIVE FIELDS, WITH THEIR TILES -- the thing that was missing.
        self.farm_plots = []
        self.farm_tiles = {}
        # FROM THE HUB'S REAL POSITION, NOT THE LATTICE. `self.x` here is still
        # the lattice cell it was constructed on -- the move comes later -- so
        # the fields were being planted forty thousand pixels from the yard.
        # ONE FIELD, FIVE BY FIVE. It was five fields of twenty-five tiles --
        # a hundred and twenty-five plots marching across the wild, which is
        # not what a hut in the woods looks like and not what was asked for.
        for k in range(1):
            ctx = int(math.floor((float(x) - 110.0) / 32.0))
            cty = int(math.floor((float(y) + 40.0) / 32.0))
            kind = "wheat"
            self.farm_plots.append((ctx, cty, kind))
            # A FIVE BY FIVE PLOT, as specified -- twenty-five tiles, not nine.
            # Nine-tile plots gave the hub five food tiles in total and no
            # surplus at all, so `economy.harvest` passed nothing to the common
            # shelf, the dole had nothing to hand out, and three of the four
            # starved inside the first quarter of an hour every single time.
            cells = [(ctx + dx, cty + dy)
                     for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)]
            # FIVE PLANTS ARE FOOD, THE REST IS THE LEAF OF THIS COUNTRY.
            # Every tile was wheat, so the artisan had nothing to work and the
            # bench stood idle with a man standing at it.
            self.farm_tiles[(ctx, cty)] = [
                # FIVE FOOD IN EVERY PLOT -- "5 plants are food, rest is the
                # local version of leaf". Applied to the first plot only, the
                # whole hub had five food tiles and starved.
                (tx, ty, "wheat" if i < 5 else self._leaf_kind(world))
                for i, (tx, ty) in enumerate(cells)]

        # (posts are assigned at the very end -- see step 10)

        # 6. IT STAYS WHERE ITS LATTICE CELL IS. It used to be moved to an
        # arbitrary spot in the wild, which made it invisible to everything:
        # `villages.visible` finds a town by asking `village_center(gx, gy)`
        # where the town is, not by asking the town. A moved hub failed that
        # test, so the exterior draw never drew it, the player's collision
        # never met its fence, and the crops were never rendered.
        dx = float(x) - float(self.x)
        dy = float(y) - float(self.y)
        self.x, self.y = float(x), float(y)
        for n in self.npcs:
            n.x += dx
            n.y += dy
            n.home = (n.x, n.y)
            n.refuge = None
        for w in self.workplaces:
            w.x += dx
            w.y += dy
            w.rect = pygame.Rect(int(w.x - w.rect.w / 2),
                                 int(w.y - w.rect.h / 2), w.rect.w, w.rect.h)
        # NO NOTICE BOARD IN A HUT. A board is the state talking: taxes,
        # elections, the crown's business. There is no state here. Zero-sized,
        # so it is neither drawn nor solid and every `village.board` reference
        # in the rest of the game stays valid.
        self.board = pygame.Rect(0, 0, 0, 0)
        self.radius = HUB_RADIUS
        # 7. ITS OWN FENCE AND GATES -- the same call a town uses.
        self._rng2 = random.Random(seed & 0xFFFFFFFF)
        fence.install(self, self._rng2)

        # 8. A HOUSE, inside the fence (fence_rect is finally ours).
        fr = self.fence_rect
        house = village_mod.House(self.x - fr.w * 0.26, self.y - fr.h * 0.26,
                                  96, 68, (118, 62, 50), (0.0, 1.0), seed + 13)
        house.village = self
        house.occupants = []
        self.houses = [house]

        # 8b. THE BENCH, BUILT HERE, WHERE IT STANDS. `Workplace` computes its
        # `.door` in __init__, and `_work_place` walks the artisan to that door
        # -- so a bench built before the hub was moved sent him to a doorway
        # forty thousand pixels away and he never arrived.
        bench = industry.Workplace("lab", self.x + 120.0, self.y - 60.0, seed + 5)
        self.workplaces = [bench]
        bench.worker = None

        # 9. AND A CROP STANDING ON DAY ONE.
        try:
            self._seed_fields(world, 0.0)
        except Exception:
            pass

        self._stage = "idle"        # idle -> out -> home -> idle
        self._carrier = None        # the trader, while he is on the road
        self._cargo = {}
        self._goal = None
        self._split_t = 180.0
        self.ledger_coins = max(120, int(self.ledger_coins))
        self.ledger_goods = {}

        # 10. AND THE FOUR POSTS, LAST OF ALL -- after the move, the re-fence
        # and the seeding, none of which may undo them. Assigned by index, and
        # asserted: if the four are not exactly these four, the hub is not a
        # hub and saying so now is worth more than finding out by watching a
        # farmer stand in an untouched field for ten minutes.
        self.npcs = [n for n in self.npcs if n.alive][:4]
        while len(self.npcs) < 4:
            k = len(self.npcs)
            who = "%s %s" % (self._rng.choice(village_mod.FIRST_NAMES),
                             self._rng.choice(village_mod.LAST_NAMES))
            self.npcs.append(village_mod.NPC(
                self.x + (k - 1.5) * 30.0, self.y + 34.0,
                self._rng.randrange(1 << 30), who,
                "%08x%02x" % (seed & 0xFFFFFFFF, k), "Criminal", self))
        for k, (n, job) in enumerate(zip(self.npcs,
                                         ("soldier", "farm", "lab", "trader"))):
            n.job = job
            n.role = "Criminal"
            n.village = self
            n.hub = self
            n.nation = NATION
            n.team = ("nation", NATION)
            n.searched_village = self
            n.farm_plot = None
            n.workplace = None
            n.alive = True
            if n in village_mod.PEOPLE:
                village_mod.PEOPLE.remove(n)
            n.stock.clear()                  # CLEARED FIRST -- it was being
            # TEN OF THE LOCAL **FOOD**, NOT TEN OF THE LOCAL CROP. Wheat is
            # grain; `needs()` eats bread, berries and cactus fruit. They were
            # starting with a bag of seed grain, nothing edible, and were dead
            # of hunger before the first harvest came in.
            n.stock[economy.FOOD[0]] = 10   # cleared AFTER the shovel,
                                                # so the farmer had none
            if job == "lab":
                n.workplace = bench
                n.x, n.y = bench.x, bench.y + 30.0
                bench.worker = n
            elif job == "farm":
                n.farm_plot = 0
                n.leaf_farmer = True
                n.stock["shovel"] = 1
                n.tool_uses = economy.TOOL_USES
            elif job == "soldier":
                try:
                    g = self.gate_list()[0]
                    n.x, n.y = g[1], g[2] + 26.0
                except Exception:
                    pass
            elif job == "trader":
                n.x, n.y = self.x, self.y + 60.0
            if job == "farm":
                # ON HIS OWN FIELD, inside the fence, where the work is.
                ctx0, cty0, _k = self.farm_plots[0]
                n.x = ctx0 * 32 + 16.0
                n.y = cty0 * 32 + 16.0
            elif job != "soldier" and job != "lab":
                n.x, n.y = self.x, self.y + 40.0
            n.home = (n.x, n.y)
        got = [n.job for n in self.npcs]
        if got != ["soldier", "farm", "lab", "trader"]:
            raise RuntimeError("hub %s has the wrong posts: %r"
                               % (self.name, got))
        _note("HUB %-14s at (%.0f,%.0f)  posts %s  plots %d  bench %s"
              % (self.name, self.x, self.y, got, len(self.farm_plots),
                 bench.kind))

    # -- what grows here ----------------------------------------------------
    def _leaf_kind(self, world) -> str:
        """The leaf of this country: tobacco, mushrooms or agave."""
        try:
            import biomes
            t = float(biomes.temperature(self.x, self.y, 20240501))
            h = float(biomes.humidity(self.x, self.y, 20240501))
            return biomes.crop_kinds(t, h)[1]
        except Exception:
            return "plant"

    def _food_kind(self, world) -> str:
        try:
            import biomes
            t = float(biomes.temperature(self.x, self.y, 20240501))
            h = float(biomes.humidity(self.x, self.y, 20240501))
            return biomes.crop_kinds(t, h)[0]
        except Exception:
            return "wheat"

    # -- the trip -----------------------------------------------------------
    def _load_and_go(self, trader) -> None:
        """He takes exactly twenty and leaves. Nothing more goes into his pack
        until he is back -- what is made meanwhile waits with the artisan."""
        made = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")
        cargo = {}
        need = 20
        for item in made:
            have = int(trader.stock.get(item, 0))
            if have <= 0:
                continue
            take = min(have, need)
            trader.stock[item] = have - take
            cargo[item] = cargo.get(item, 0) + take
            need -= take
            if need <= 0:
                break
        if not cargo:
            return
        self._cargo = cargo
        self._carrier = trader
        self._stage = "out"
        _note("TRIP     %s leaves %s with %d"
              % (trader.name, self.name, sum(cargo.values())))

    def _carry_step(self, dt: float, world, now: float) -> None:
        """Out to the nearest town, searched at its gate, and home again."""
        trader = self._carrier
        if self._stage == "idle":
            return
        if trader is None or not trader.alive:
            self._carrier, self._cargo, self._stage = None, {}, "idle"
            return
        towns = list(getattr(self.registry, "villages", ()) or ())
        towns = [t for t in towns if not getattr(t, "is_hub", False)]
        if not towns:
            self._carrier, self._cargo, self._stage = None, {}, "idle"
            return
        if self._goal is None:
            self._goal = min(towns, key=lambda v: (v.x - trader.x) ** 2
                             + (v.y - trader.y) ** 2)
        goal = self._goal
        if self._stage == "out":
            if (goal.x - trader.x) ** 2 + (goal.y - trader.y) ** 2 > 150.0 ** 2:
                d = math.hypot(goal.x - trader.x, goal.y - trader.y) or 1.0
                step = min(d, 70.0 * dt)
                trader.x += (goal.x - trader.x) / d * step
                trader.y += (goal.y - trader.y) / d * step
                return
            units = sum(self._cargo.values())
            skill = max(0.0, min(10.0, float(getattr(trader, "smuggling", 0.0))))
            if trader.rng.random() < min(1.0, units / 100.0) * 0.55 * (1.0 - 0.09 * skill):
                goal.provoked = True
                trader.health = getattr(trader, "health", 100.0) - 45.0
                _note("SEARCH   %s caught at %s with %d" % (trader.name, goal.name, units))
                self._cargo = {}
            else:
                for item, qty in self._cargo.items():
                    economy.store_add(goal, item, qty, 2)
                    unit = max(1, int(round(economy.value(goal, item) * 0.5)))
                    self.ledger_coins += qty * unit
                    goal.ledger_coins = max(0, int(goal.ledger_coins) - qty * unit)
                trader.smuggling = min(10.0, skill + 0.06 + units * 0.001)
                self._cargo = {}
            self._stage = "home"
            return
        # home again
        if (self.x - trader.x) ** 2 + (self.y - trader.y) ** 2 > 120.0 ** 2:
            d = math.hypot(self.x - trader.x, self.y - trader.y) or 1.0
            step = min(d, 70.0 * dt)
            trader.x += (self.x - trader.x) / d * step
            trader.y += (self.y - trader.y) / d * step
            return
        trader.x, trader.y = self.x, self.y + 40.0
        trader.home = (trader.x, trader.y)
        self._carrier, self._cargo, self._stage, self._goal = None, {}, "idle", None

    def gate_list(self):
        return fence.gate_list(self)

    # -- the day ------------------------------------------------------------
    def update(self, dt: float, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        night = (float(now) % 600.0) >= 300.0
        # THE HUB STEPS ITS OWN PEOPLE. Nothing else does: they are not in
        # `PEOPLE`, and `Village.update` has never ticked a man.
        for n in self.npcs:
            if n.alive:
                # NO IDLING. `NPC.update` opens with `if self.pause > 0:
                # return`, and a pause is a second or two of a day in a TOWN
                # where there are sixty men to work forty plots. Here there are
                # four of them on a hundred and twenty-five tiles, so a pause
                # between every swing meant they never reaped enough to fill
                # the shelf -- and all four starved beside a growing field.
                n.pause = 0.0
                n.tick(dt, world, now, "home" if night else "work",
                       night=night)
        # ...and then the town's own business: the board, the books, the crop.
        super().update(dt, world, now, "home" if night else "work")
        # ONE COMMON LEDGER. Nobody in a hut owns a coin: the hut does. A man
        # draws what he needs to buy with straight out of the ledger, and
        # whatever he takes in goes straight back into it. The ledger is the
        # purse, the shop and the payroll, and between shifts the four of them
        # hold nothing at all.
        live = [n for n in self.npcs if n.alive]
        if live:
            keep = 60                       # what a man may carry to buy with
            for n in live:
                purse = int(getattr(n, "coins", 0))
                if purse < keep:
                    take = min(keep - purse, int(self.ledger_coins))
                    if take > 0:
                        n.coins = purse + take
                        self.ledger_coins -= take
                elif purse > keep * 3:
                    gave = purse - keep
                    n.coins = keep
                    self.ledger_coins += gave

        # A PHYSICAL CHAIN OF HANDS, NOT A SHOP.
        #
        # The farmer puts leaf into the ARTISAN's hands, in full, the moment it
        # is picked. The artisan works it and puts what he makes into the
        # TRADER's hands. Nothing is bought and nothing goes through a shop --
        # it is passed along, man to man, the way it would actually happen.
        farmer = next((n for n in live if n.job == "farm"), None)
        artisan = next((n for n in live if n.job in ("lab", "brewery")), None)
        trader = next((n for n in live if n.job == "trader"), None)
        away = bool(self._carrier) or self._stage != "idle"

        leaf_kinds = ("tobacco", "red_mushroom", "agave", "plant", "mushroom")
        made_kinds = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")

        def hand(src, dst, kinds):
            """Everything of these kinds goes from one man's pack to another."""
            if src is None or dst is None:
                return 0
            moved = 0
            for item in list(src.stock.keys()):
                if item not in kinds:
                    continue
                qty = int(src.stock.get(item, 0))
                if qty <= 0:
                    continue
                dst.stock[item] = dst.stock.get(item, 0) + qty
                src.stock[item] = 0
                moved += qty
            return moved

        # the farmer's leaf -> the artisan. AND THE LEDGER'S: `economy.harvest`
        # gives a farmer a ration of five and puts THE REST IN THE SHARED
        # SHELF, so looking only in his pack found nothing at all -- he keeps
        # five a day and the other forty go to the town. The leaf the hub grows
        # is in the ledger, and the ledger's leaf goes straight to the bench.
        hand(farmer, artisan, leaf_kinds)
        if artisan is not None:
            taken = 0
            for item in list(self.ledger_goods.keys()):
                if item not in leaf_kinds:
                    continue
                qty = int(self.ledger_goods.get(item, 0))
                if qty > 0:
                    artisan.stock[item] = artisan.stock.get(item, 0) + qty
                    self.ledger_goods[item] = 0
                    taken += qty
            if taken:
                pass
        # the artisan's work -> the trader, WHO IS NOT LOADED WHILE HE IS AWAY:
        # what is made meanwhile stockpiles in the artisan's pack.
        if not away:
            for n in live:
                if n is not trader:
                    hand(n, trader, made_kinds)
            # ...and anything already finished on the shared shelf
            if trader is not None:
                for item in list(self.ledger_goods.keys()):
                    if item not in made_kinds:
                        continue
                    qty = int(self.ledger_goods.get(item, 0))
                    if qty > 0:
                        trader.stock[item] = trader.stock.get(item, 0) + qty
                        self.ledger_goods[item] = 0

        # THE TRIP. Twenty is the load, and he goes when he has twenty.
        if trader is not None and not away:
            carry = sum(int(trader.stock.get(k, 0)) for k in made_kinds)
            if carry >= 20:
                self._load_and_go(trader)

        self._carry_step(dt, world, now)

        # THEIR TOOLS DO NOT WEAR OUT -- nation 1 only, which is the guard in
        # `_swing_tool`. Give them back the uses every tick so nothing a
        # criminal picks up can ever break while we watch the trade.
        for n in live:
            n.tool_uses = max(int(getattr(n, "tool_uses", 0)),
                              int(economy.TOOL_USES))
            if n.job == "farm":
                n.stock["shovel"] = 1

        # AND THE FOOD GOES ON THE COMMON SHELF, or the three who do not farm
        # have nothing. `economy.harvest` gives a farmer a ration and puts the
        # remainder in the town's store -- but a hub has five fields and the
        # remainder was zero, so the shelf stayed empty and three of the four
        # starved every time. What the farmer grows ABOVE his own ration is the
        # shelf's, and the dole feeds the rest from it.
        if farmer is not None and farmer.alive:
            for item in economy.FOOD:
                have = int(farmer.stock.get(item, 0))
                if have > 6:
                    give = have - 6
                    farmer.stock[item] = 6
                    self.ledger_goods[item] = int(
                        self.ledger_goods.get(item, 0)) + give

        # FEED THEM FROM THE LEDGER, EVERY TICK. `needs()` eats only out of a
        # man's OWN pack, and dies at hunger 100 having found nothing -- so in
        # a hut where the shelf holds the food and the men hold none, all four
        # starve beside a full larder. This is the equal redistribution: any
        # man with nothing to eat is handed a few from the shelf, and the
        # farmer's surplus is what fills it.
        for n in live:
            if not n.alive:
                continue
            if any(int(n.stock.get(x, 0)) > 0 for x in economy.FOOD):
                continue
            for item in economy.FOOD:
                have = int(self.ledger_goods.get(item, 0))
                if have > 0:
                    give = min(have, 3)
                    self.ledger_goods[item] = have - give
                    n.stock[item] = int(n.stock.get(item, 0)) + give
                    break

        # NOBODY HERE FIGHTS A STRANGER. `nearest_hostile` gives a man a
        # target, and `aggro` decides whether he takes it -- so a hub that had
        # been provoked once, or whose people had been set hostile by the
        # nation they belong to, shot at every man who walked in the gate. The
        # four of them mind their own business unless they are attacked.
        for n in self.npcs:
            if n.alive:
                n.aggro = False
                n.hostile = False
                n.provoked = False

        # THE SOLDIER NEVER LEAVES THE GATE.
        for n in self.npcs:
            if n.alive and getattr(n, "job", None) == "soldier":
                try:
                    g = self.gate_list()[0]
                    n.x, n.y = g[1], g[2] + 26.0
                    n.home = (n.x, n.y)
                    n.asleep = False
                except Exception:
                    pass

    # -- the picture, by the real renderers ---------------------------------
    def draw(self, screen, cam_x: float, cam_y: float, vw: int = 900,
             vh: int = 900) -> None:
        import crop
        view = pygame.Rect(int(cam_x) - 300, int(cam_y) - 300, 1200, 1200)
        for ctx, cty, _kind in self.farm_plots:
            for tx, ty, tkind in self.farm_tiles.get((ctx, cty), ()):
                try:
                    crop.draw_crop(screen, tx * 32 + 16, ty * 32 + 16, tkind,
                                   120.0, cam_x, cam_y, None)
                except Exception:
                    pass
        fence.draw(screen, cam_x, cam_y, self, view)
        for house in self.houses:
            house.draw(screen, cam_x, cam_y)
        for w in self.workplaces:
            w.draw(screen, cam_x, cam_y)
        for n in self.npcs:
            if n.alive:
                n.draw(screen, cam_x, cam_y, False)


class Hubs:
    """The hubs, and nothing else. Not a registry: the crown cannot see them."""

    def __init__(self, world, villages) -> None:
        self._world = world
        self._villages = villages
        self.hubs: list[Hub] = []
        self.build(world, villages)

    def build(self, world, villages) -> None:
        # ATTACHED TO THE REGISTRY, so every system that asks the registry
        # which settlements are near a point gets the hubs too.
        villages.offlattice = self.hubs
        rng = random.Random(int(world.seed) ^ 0x0C0FFEE)
        towns = list(getattr(villages, "villages", ()) or ())
        tries = 0
        while len(self.hubs) < HUB_COUNT and tries < 8000:
            tries += 1
            # OFF THE LATTICE, AND INSIDE THE MAP. Every lattice cell within
            # reach is already a town, so a hub cannot be on the lattice -- and
            # `villages.visible` finds a town by asking the LATTICE where it is,
            # so nothing that walks `villages` will ever find a hub. That is
            # why a hub needs its own list, its own draw AND ITS OWN COLLISION.
            x = rng.uniform(-80000.0, 80000.0)
            y = rng.uniform(-80000.0, 80000.0)
            if any((v.x - x) ** 2 + (v.y - y) ** 2 < MIN_FROM_TOWN ** 2
                   for v in towns):
                continue
            if any((h.x - x) ** 2 + (h.y - y) ** 2 < 9000.0 ** 2
                   for h in self.hubs):
                continue
            try:
                hub = Hub(world, x, y, rng.randrange(1 << 30),
                          registry=villages)
            except Exception:
                continue
            # IN THE REGISTRY, LIKE A TOWN. This is the whole of it: the
            # exterior draw loop walks `villages.visible`, the player's
            # collision walks the same villages' `fence_walls`, the crops are
            # drawn from `world.plots`, and the board, the fence and the people
            # all appear because they are a village that the world can see.
            # Hand-drawing them separately gave a picture with no collision,
            # no crops and nobody in it.
            self.hubs.append(hub)

    def update(self, dt: float, now: float) -> None:
        for hub in self.hubs:
            hub.update(dt, self._world, now)

    def draw(self, screen, cam_x: float, cam_y: float, vw: int, vh: int) -> None:
        view = pygame.Rect(int(cam_x) - 300, int(cam_y) - 300, vw + 600, vh + 600)
        for hub in self.hubs:
            fr = getattr(hub, "fence_rect", None)
            if fr is not None and view.colliderect(fr):
                hub.draw(screen, cam_x, cam_y, vw, vh)

    def all_npcs(self) -> list:
        return [n for h in self.hubs for n in h.npcs if n.alive]
