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
import gate
import caravans
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


def in_player_hub(rect, hubs) -> bool:
    """Is this ground inside a yard of the player's own?"""
    for h in hubs:
        if getattr(h, "is_player_hub", False) and h.fence_rect.colliderect(rect):
            return True
    return False


def land_ok(rect, villages, hubs, px: float, py: float, clearance=140.0) -> bool:
    """HIS OWN GROUND, OR OPEN COUNTRY -- NEVER SOMEBODY ELSE'S.

    The old-world hubs are gone; only real towns (none remain) and his own
    fenced yard matter. A conquered native settlement is HIS ground, so a
    sign-post, a bench or a fence goes up right beside it."""
    if in_player_hub(rect, hubs):
        return True
    for v in list(villages or ()):
        fr = getattr(v, "fence_rect", None)
        if fr is not None and fr.inflate(clearance, clearance).colliderect(rect):
            return False
        if math.hypot(getattr(v, "x", 0.0) - px,
                      getattr(v, "y", 0.0) - py) < float(getattr(v, "radius", 0.0)) + 260.0:
            return False
    return True


def _note(message: str) -> None:
    try:
        with open(os.path.expanduser("~/.kingpin_saves/village.log"), "a") as fh:
            fh.write(message + "\n")
    except Exception:
        pass


_NAME_TAIL = ("Ansel", "Bram", "Cass", "Dorn", "Ewan", "Fen",
              "Galt", "Hale", "Ivo", "Jory", "Kell", "Lund")


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
        # NOT AT (0, 0). A zero-size rect still has a CENTRE, and the origin is
        # where the player spawns -- `near_board()` measures against
        # `v.board.center`, so every hub in the world read as "you are standing
        # at the notice board", `board_open` went true, the frame set
        # `keys = _NO_KEYS`, and movement died while the menus kept working.
        # Put it ten million pixels away: nothing is ever near it, it draws
        # nothing at zero size, and it collides with nothing.
        self.board = pygame.Rect(-10 ** 7, -10 ** 7, 0, 0)
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
        # A HUT HAS A LARDER, and it must cover the FIRST crop. `hunger` is
        # satiety in this game: it climbs to 100 and a man dies there, so ten
        # loaves each is about a hundred seconds of life -- and the first
        # harvest is GROW_SECONDS (180 s) away. Every hut therefore starved to
        # death at day 0.02 with its field still growing. The shelf feeds them
        # until the farmer brings the first crop in.
        try:
            self.ledger_goods[economy.FOOD[0]] = 40
        except Exception:
            pass

        # 10. AND THE FOUR POSTS, LAST OF ALL -- after the move, the re-fence
        # and the seeding, none of which may undo them. Assigned by index, and
        # asserted: if the four are not exactly these four, the hub is not a
        # hub and saying so now is worth more than finding out by watching a
        # farmer stand in an untouched field for ten minutes.
        # THREE MEN, AND NO MORE: a soldier, a farmer, an artisan. The trader
        # is not a hut's man at all -- traders are free, nationless men who COME
        # to the huts, buy what the bench has made and carry it to a settlement.
        self.npcs = [n for n in self.npcs if n.alive][:3]
        while len(self.npcs) < 3:
            k = len(self.npcs)
            who = "%s %s" % (self._rng.choice(village_mod.FIRST_NAMES),
                             self._rng.choice(village_mod.LAST_NAMES))
            self.npcs.append(village_mod.NPC(
                self.x + (k - 1.5) * 30.0, self.y + 34.0,
                self._rng.randrange(1 << 30), who,
                "%08x%02x" % (seed & 0xFFFFFFFF, k), "Criminal", self))
        for k, (n, job) in enumerate(zip(self.npcs,
                                         ("soldier", "farm", "lab"))):
            # A HUT'S MAN NEEDS A NAME OF HIS OWN. These three came out of
            # `Village.__init__`, which numbers its people by LATTICE CELL
            # ("npc_{-2}_{-2}_0"), and two huts can stand in the same cell --
            # so two different men were minted with the same id. The save
            # files key on that id, and so does every register of who is who.
            # The hut's own position is unique; use it.
            n.id = "hub_%d_%d_%d" % (int(self.x), int(self.y), k)
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
        if got != ["soldier", "farm", "lab"]:
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
            # HE GOES TO THE GATE, NOT THE TOWN SQUARE. The old route walked to
            # the middle of the settlement -- through its fence and its guard --
            # and then rolled a private dice of its own. The guard on the gate
            # is the whole point: the town searches him, or it does not.
            try:
                gside, gxw, gyw = fence.gate_list(goal)[0]
                gox, goy = fence.OUTWARD[gside]
                gpx, gpy = gxw + gox * 70.0, gyw + goy * 70.0
            except Exception:
                gpx, gpy = goal.x, goal.y
            if (gpx - trader.x) ** 2 + (gpy - trader.y) ** 2 > 40.0 ** 2:
                d = math.hypot(gpx - trader.x, gpy - trader.y) or 1.0
                step = min(d, 70.0 * dt)
                trader.x += (gpx - trader.x) / d * step
                trader.y += (gpy - trader.y) / d * step
                return
            # AT THE GATE. The town's own guard looks at him, ten seconds.
            verdict = gate.search_visitor(dt, goal, trader)
            if verdict is None:
                return                       # still being looked at
            if verdict == "caught":
                goal.provoke()
                _note("SEARCH   %s caught at the gate of %s with %d"
                      % (trader.name, goal.name, sum(self._cargo.values())))
                self._cargo = {}
                trader.health = getattr(trader, "health", 100.0) - 45.0
                self._stage = "home"
                return
            # THROUGH THE GATE, AND SOLD TO THE MEN WHO STILL WANT IT. Not
            # dumped into the town's own store: a man with the craving and the
            # coin buys it from him, and the money goes home with him.
            units = sum(self._cargo.values())
            sold = 0
            for item in list(self._cargo):
                qty = int(self._cargo.get(item, 0))
                price = max(1, int(round(economy.value(goal, item) * 1.35)))
                for n in goal.npcs:
                    if qty <= 0:
                        break
                    if not n.alive or n.in_interior:
                        continue
                    if float(getattr(n, "yearning", 0.0)) < economy.YEARING_BUY:
                        continue
                    coins = int(getattr(n, "coins", 0))
                    if coins < price:
                        continue
                    n.stock[item] = int(n.stock.get(item, 0)) + 1
                    n.coins = coins - price
                    n.yearning = max(0.0, float(n.yearning) - 0.5)
                    self.ledger_coins += price
                    qty -= 1
                    sold += 1
                if qty > 0:                      # what nobody wanted is left here
                    economy.store_add(goal, item, qty, 2)
                self._cargo[item] = 0
            trader.smuggling = min(10.0, float(getattr(trader, "smuggling", 0.0))
                                   + 0.06 + units * 0.001)
            _note("TRIP     %s sold %d of %d at %s"
                  % (trader.name, sold, units, goal.name))
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
        _note("RETURN   %s is home; the hut's purse is %d coin"
              % (getattr(trader, "name", "trader"), int(self.ledger_coins)))
        self._carrier, self._cargo, self._stage, self._goal = None, {}, "idle", None

    def gate_list(self):
        return fence.gate_list(self)

    # -- the day ------------------------------------------------------------
    def _field_census(self, world, now) -> None:
        """ONCE A MINUTE: WHAT IS STANDING IN THE FIELD, TILE BY TILE."""
        if now - getattr(self, "_census_t", -999.0) < 60.0:
            return
        self._census_t = now
        try:
            ctx, cty, _k = self.farm_plots[0]
            states = {}
            ages = []
            for tx, ty, tile_kind in self.farm_tiles[(ctx, cty)]:
                p = world.plot_at(tx, ty) if world is not None else None
                st = getattr(p, "kind", "none") if p is not None else "none"
                key = "%s/%s" % (st, tile_kind)
                states[key] = states.get(key, 0) + 1
                if p is not None and getattr(p, "planted_at", None) is not None:
                    ages.append(now - float(p.planted_at))
            _note("FIELD   %s tiles %s  now=%.0f  crop age min/max=%s"
                  % (self.name, states, now,
                     ("%.0f/%.0f" % (min(ages), max(ages))) if ages else "none"))
        except Exception as _e:
            _note("FIELD   %s census failed %s" % (self.name, repr(_e)[:80]))

    def update(self, dt: float, world=None, now: float = 0.0,
               phase: str = "home", combat=None, threat_of=None,
               colliders=()) -> None:
        # THE SAME DAY A SETTLEMENT KEEPS. `phase` is handed in from main's own
        # `day_phase()` and the night flag from `night_factor()` -- the hub used
        # to make up its own crude `(now % 600) >= 300`, so its people worked on
        # a different clock from every farmer in the world, which is exactly the
        # kind of difference that leaves one field reaped and another not.
        night = phase == "sleep"
        # THE HUB STEPS ITS OWN PEOPLE. Nothing else does: they are not in
        # `PEOPLE`, and `Village.update` has never ticked a man.
        self._field_census(world, now)
        for n in self.npcs:
            if n.alive:
                # NO IDLING. `NPC.update` opens with `if self.pause > 0:
                # return`, and a pause is a second or two of a day in a TOWN
                # where there are sixty men to work forty plots. Here there are
                # four of them on a hundred and twenty-five tiles, so a pause
                # between every swing meant they never reaped enough to fill
                # the shelf -- and all four starved beside a growing field.
                n.pause = 0.0
                # AND HE IS NEVER ASLEEP. `NPC.tick` wakes a sleeping man only
                # if he has a `home_door` to step out of -- and a hub's house is
                # built with no doors at all, so once a hut's farmer fell asleep
                # he slept FOR EVER: the tick returned at `if self.asleep:
                # return` on every frame after it, and he never worked a tile
                # again. That is why settlement farmers farm and hub ones do
                # not: a settlement has doors.
                n.asleep = False
                n.in_interior = False
                n.on_duty = False
                try:
                    n.tick(dt, world, now, "work" if phase == "sleep" else phase,
                           combat, night, colliders, threat_of)
                except Exception as _e:
                    # NEVER SILENT. This ran inside main's `except: pass`, so a
                    # single error here stopped every man in every hut on every
                    # frame -- no farming, no bench, no trade -- and the game
                    # simply looked idle.
                    import traceback as _tb
                    _note("HUB ERROR %s: %s" % (self.name, repr(_e)[:140]))
                    if getattr(self, "_err_shown", 0) < 3:
                        self._err_shown = getattr(self, "_err_shown", 0) + 1
                        _tb.print_exc()
        # A HUT HAS NO CIVIC LIFE, AND MUST NOT RUN A TOWN'S.
        #
        # This called Village.update -- wages, tax, crown dues, the tithe, the
        # MARKET and the ELECTIONS. A hut held an election, elected its own
        # trader as MAYOR, and from that moment there was no trader in it:
        # `trader = next(n for n in live if n.job == "trader")` was None, the
        # artisan's pack could never be emptied into a carrier, and the whole
        # chain of hands stopped dead. Seen in the live game:
        #     HANDOFF? Poor Farm bench=1 moved=0 trader=None
        #     HANDOFF?   Orville Lassiter job=mayor
        # A hut keeps its own books (the ledger, the wages it draws, the
        # handoffs above) and owes the crown nothing at all -- it does not
        # exist, as far as the crown is concerned.
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
        # A TRIP THAT CANNOT FINISH MUST NOT BLOCK THE HUT FOR EVER. `_carrier`
        # and `_stage` are saved, so a trip interrupted by a save came back
        # as "away" on every frame: the made goods were never handed to the
        # trader, the artisan's pack filled with cigars and nothing was ever
        # sold again. If the carrier is missing, dead, no longer one of ours,
        # or the stage is not a stage, the trip is over.
        if (self._carrier is not None
                and (not getattr(self._carrier, "alive", False)
                     or self._carrier not in self.npcs)):
            _note("TRIP     %s: lost carrier %s, back to idle"
                  % (self.name, getattr(self._carrier, "name", "?")))
            self._carrier, self._cargo, self._stage, self._goal = None, {}, "idle", None
        if self._stage not in ("idle", "out", "home"):
            self._carrier, self._cargo, self._stage, self._goal = None, {}, "idle", None
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
        _moved = hand(farmer, artisan, leaf_kinds)
        if _moved:
            _note("HANDOFF  %s -> %s  %d leaf (by hand)"
                  % (getattr(farmer, "name", "farmer"),
                     getattr(artisan, "name", "artisan"), _moved))
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
                # ONCE A MINUTE, NOT ONCE A TICK. This wrote 175,773 lines into
                # village.log in one session -- every tick the bench took its
                # five leaf, every tick it said so.
                _key = (id(artisan), taken)
                if getattr(self, "_handoff_note", None) != _key or \
                        getattr(self, "_handoff_t", -1e9) + 60.0 <= now:
                    self._handoff_note = _key
                    self._handoff_t = now
                    _note("HANDOFF  shelf -> %s  %d leaf"
                          % (getattr(artisan, "name", "artisan"), taken))
        # THE BENCH KEEPS TWENTY, AND THE REST IS FOR SALE. Every leaf the hut
        # grows was going straight into the artisan's pack, so a passing trader
        # had nothing to buy until the bench had finished with it -- and the
        # bench is one man. What he cannot work today goes on the shelf, and a
        # cart takes it away: the hut earns on the leaf as well as the product.
        if artisan is not None:
            _held = 0
            for _k in leaf_kinds:
                _q = int(artisan.stock.get(_k, 0))
                if _q <= 0:
                    continue
                _room = max(0, 20 - _held)
                if _q > _room:
                    _spare = _q - _room
                    artisan.stock[_k] = _room
                    self.ledger_goods[_k] = int(self.ledger_goods.get(_k, 0)) + _spare
                _held += int(artisan.stock.get(_k, 0))
        # the artisan's work -> the trader, WHO IS NOT LOADED WHILE HE IS AWAY:
        # what is made meanwhile stockpiles in the artisan's pack.
        if artisan is not None:
            _made = sum(int(artisan.stock.get(k, 0)) for k in made_kinds)
            if _made >= 20 and getattr(self, "_made_logged", 0) < _made // 20:
                self._made_logged = _made // 20
                _note("MADE     %s has %d finished goods"
                      % (getattr(artisan, "name", "artisan"), _made))
        if not getattr(self, "_away_logged", 0) or away != getattr(self, "_away_last", None):
            self._away_logged = 1
            self._away_last = away
            _note("TRADE    %s away=%s trader=%s stage=%s carrier=%s"
                  % (self.name, away, getattr(trader, "name", None),
                     self._stage, getattr(self._carrier, "name", None)))
        _bench = (sum(int(artisan.stock.get(k, 0)) for k in made_kinds)
                  if artisan is not None else 0)
        if away and _bench > 0:
            _note("HANDOFF? %s BLOCKED away=True stage=%s carrier=%s bench=%d"
                  % (self.name, self._stage,
                     getattr(self._carrier, "name", None), _bench))
        if not away:
            _moved = 0
            for n in live:
                if n is not trader:
                    _g = hand(n, trader, made_kinds)
                    _moved += _g
                    if _g:
                        _note("HANDOFF  %s -> %s  %d finished"
                              % (getattr(n, "name", "?"),
                                 getattr(trader, "name", "trader"), _g))
            # AND SAY SO WHEN IT DOES NOTHING. A man holding twenty-five and a
            # trader holding none, with the handoff "running", is the exact
            # state this chain died in -- so the values it ran with are logged.
            if _bench > 0 and _moved == 0 and not getattr(self, "_stuck_logged", 0):
                self._stuck_logged = 1
                _note("HANDOFF? %s bench=%d moved=0 trader=%s trader_is_artisan=%s"
                      " trader_alive=%s trader_in_npcs=%s live=%d"
                      % (self.name, _bench, getattr(trader, "name", None),
                         trader is artisan,
                         getattr(trader, "alive", None),
                         trader in self.npcs if trader is not None else None,
                         len(live)))
                for _n2 in live:
                    _note("HANDOFF?   %-16s job=%-8s made=%d alive=%s"
                          % (getattr(_n2, "name", "?"), _n2.job,
                             sum(int(_n2.stock.get(k, 0)) for k in made_kinds),
                             _n2.alive))
            # ...and anything already finished on the shared shelf
            if trader is not None:
                for item in list(self.ledger_goods.keys()):
                    if item not in made_kinds:
                        continue
                    qty = int(self.ledger_goods.get(item, 0))
                    if qty > 0:
                        trader.stock[item] = trader.stock.get(item, 0) + qty
                        self.ledger_goods[item] = 0

        # THE HUT'S STOCK FOR SALE. The bench's finished goods go onto the
        # shelf, and that is what a free trader coming up the road buys.
        if artisan is not None:
            for _k in made_kinds:
                _q = int(artisan.stock.get(_k, 0))
                if _q > 0:
                    self.ledger_goods[_k] = int(self.ledger_goods.get(_k, 0)) + _q
                    artisan.stock[_k] = 0
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


class PlayerHub:
    """THE PLAYER'S OWN HUB: a yard he closed in the wild, and his.

    Not a criminal camp -- no men, no bench, no field. What makes it a hub is
    that HE fenced it: the walls are his own fences, already drawn and already
    solid, and this object is the name the world can point at -- "his hub" for
    the service, for a place in a sentence, for whatever comes next.
    """
    is_hub = True
    is_player_hub = True
    is_capital = False

    def __init__(self, owner, yard, ring, gates) -> None:
        self.owner = owner
        self.fence_rect = pygame.Rect(yard)
        self.fence_walls = list(ring)
        self.gates = list(gates)
        self.x = float(yard.centerx)
        self.y = float(yard.centery)
        self.radius = max(yard.w, yard.h) / 2.0
        first = (getattr(owner, "name", "") or "The player").split()[0]
        self.name = "%s's hold" % first
        self.houses: list = []
        self.workplaces: list = []
        self.npcs: list = []
        self.farm_plots: list = []
        self.farm_tiles: dict = {}
        self.ledger_coins = 0
        self.ledger_goods: dict = {}
        self.ledger_grade: dict = {}
        self.ledger_lots: dict = {}
        self.prices: dict = {}
        self.nation = None
        self.provoked = False
        self.battle = False
        self.chaos = 0.0
        self.conquered = False
        self.search_queue: list = []
        self.search_now = None
        self.search_t = 0.0
        self.board = pygame.Rect(-10 ** 7, -10 ** 7, 0, 0)

    # -- what the rest of the world asks a settlement, answered honestly ----
    # A yard has no watch, no roster, no board, no trade and no crown. These
    # are the questions other systems ask a Village; a hub that pretended to
    # be one crashed the frame on the first plot (patrol_timer).
    patrol: tuple = ()
    guards: list = []
    patrol_timer: float = 0.0
    capacity: int = 0
    last_death: float = -1e9
    killers: set = set()
    news: list = []
    demand: object = None
    mayor: object = None
    king: object = None
    commander: object = None
    _armed: list = []
    farm_plots: list = []
    farm_tiles: dict
    gate_side: int = 0
    gate_side2: int = 2

    def gate_list(self):
        return [(0, g.centerx, g.centery) for g in self.gates]

    def update(self, *a, **k):
        return None

    def draw(self, *a, **k):
        return None

    def _assign_duty_bodies(self):
        return None

    def _rotate_duty(self, day):
        return None

    def _seed_fields(self, world, now):
        return None

    def draw_board(self, *a, **k):
        return None

    def defenders(self):
        return []

    def provoke(self):
        return None

    def learn_killers(self, ids, now, teller=None):
        return False

    def forget_killers(self, now):
        return False

    def free_post(self, npc):
        return None

    def offer_post(self, npc):
        return False

    def open_posts(self):
        return []

    def staffing(self):
        return []

    def vacancies(self):
        return 0

    def woodlot(self):
        return []

    def capital(self):
        return None

    def trade_routes(self):
        return []

    def stone_chunks(self):
        return {}

    def random_point(self, rng):
        return (self.x, self.y)

    def can_grow(self, now):
        return False

    def birth(self, parent):
        return None


class Hubs:
    """The hubs, and nothing else. Not a registry: the crown cannot see them."""

    def __init__(self, world, villages) -> None:
        self._world = world
        self._villages = villages
        self.hubs: list[Hub] = []
        self.build(world, villages)

    def build(self, world, villages) -> None:
        # ATTACHED TO THE REGISTRY, so the player's own yard (add_player_hub)
        # is reachable as a hub. THE OLD-WORLD HUBS ARE GONE: no 25 huts, no
        # 100 men, no free traders -- only the yard the player fences himself.
        villages.offlattice = self.hubs
        villages._hubs = self
        self._caravans = []

    def build_caravans(self, world) -> None:
        """THE FREE TRADERS. Nationless, owned by nobody, and not a hut's man:
        they buy what the huts make and sell it where the craving is. Two for
        every five huts, so a hut sees a buyer reasonably often."""
        if getattr(self, "_caravans", None):
            return
        import village as _vm
        self._caravans = []
        want = len(self.hubs)        # ONE TRADER FOR EVERY HUT
        for i in range(want):
            hub = self.hubs[(i * 7) % len(self.hubs)]
            n = _vm.NPC(hub.x + 30.0 * (i % 3), hub.y + 60.0 + 10.0 * i,
                        900000 + i * 13, "Trader %s" % _NAME_TAIL[i % len(_NAME_TAIL)],
                        "caravan_%d" % i, "Free trader", None)
            n.nation = None                 # NATIONLESS: no crown may claim him
            n.team = None
            n.village = None
            n.hub = None
            n.job = "trader"
            n.role = "Free trader"
            n.stock = {"bread": 10}         # ten loaves and the road
            # A CART NEEDS CAPITAL. At 120 coin a trader could not afford a
            # single cigar -- a luxury is worth more than that -- so every
            # purchase came out as `take = purse // price = 0`, 323 attempts
            # with 3 loads. He carries enough to buy a full load and a margin.
            n.coins = 600
            n.hunger = 0.0
            # ONE PILOT ONLY. `NPC` registers every man it makes in
            # `village.PEOPLE`, and the world's own loop ticks those -- so a
            # cart was being walked to its hut by `caravans` AND walked to its
            # own civilian errand by the world, every frame, and it never
            # arrived anywhere. Measured: 100 samples of 100, all `to_hub`,
            # one of them 87 px from the hut it had been heading to for three
            # minutes. A hut's men are removed from that register for exactly
            # this reason; a cart's must be too.
            if n in _vm.PEOPLE:
                _vm.PEOPLE.remove(n)
            self._caravans.append(caravans.Caravan(n, hub))
            if n not in _vm.TRAVELLERS:
                _vm.TRAVELLERS.append(n)    # stepped with the wanderers
        _note("CARAVANS %d free traders on the road" % len(self._caravans))

    def update(self, dt: float, now: float, phase: str = "home",
               combat=None, threat_of=None, colliders=()) -> None:
        for hub in self.hubs:
            if getattr(hub, "is_player_hub", False):
                continue                        # his yard has no men to step
            hub.update(dt, self._world, now, phase, combat, threat_of, colliders)
        try:
            self._refill(dt, now)
        except Exception as _e:
            import traceback as _tb
            if not getattr(self, "_refill_shown", 0):
                self._refill_shown = 1
                _note("REFILL ERROR %s" % repr(_e)[:160])
                _tb.print_exc()

    def drive_carts(self, dt: float, now: float) -> None:
        """THE FREE TRADERS, EVERY FRAME, ON THE FRAME'S OWN CLOCK.

        A cart is a vehicle and is drawn every frame: 240 px/s is four pixels
        a frame. Stepping it on the 20 Hz world tick would move it twelve at a
        time -- the "jumping" the throttled build was reverted for -- so it
        keeps the frame clock. And it is handed `dt`, the real frame time, so
        its speed is its own SPEED again: it used to be handed `world_dt`,
        which only the world tick assigns, so a cart was given the same 0.05 s
        step on every rendered frame and walked at three times its pace.

        It is cheap enough to drive every frame now, because a cart with
        nothing to buy waits on a clock instead of re-scanning every hut in the
        world sixty times a second (see Caravan._pick_hub).
        """
        for c in getattr(self, "_caravans", ()):
            try:
                c.tick(dt, self.hubs, self._villages.villages, now)
            except Exception as _e:
                if not getattr(self, "_car_shown", 0):
                    self._car_shown = 1
                    _note("CARAVAN ERROR %s" % repr(_e)[:150])

    def _refill(self, dt: float, now: float) -> None:
        """A HUT THAT LOSES A MAN TAKES ANOTHER.

        There was no such thing: a hub whose trader died kept the post empty
        for ever, so the artisan's pack filled with cigars that could never be
        carried anywhere, and the chain of hands simply stopped. The nation has
        idle men in its towns; a hut takes one, and he becomes a criminal
        because that is what living out here makes him.
        """
        need_row = ("soldier", "farm", "lab")
        for hub in self.hubs:
            if getattr(hub, "is_player_hub", False):
                continue              # his yard is staffed by him, or by nobody
            have = {n.job for n in hub.npcs if n.alive}
            missing = [j for j in need_row if j not in have]
            if not missing:
                continue
            want = missing[0]
            for town in (getattr(self._villages, "villages", ()) or ()):
                if getattr(town, "is_hub", False):
                    continue
                cand = next((n for n in town.npcs
                             if n.alive and n.job is None
                             and n.farm_plot is None and n.workplace is None
                             and not n.defender and not n.is_commander
                             and not n.is_mayor), None)
                if cand is None:
                    continue
                town.npcs.remove(cand)
                try:
                    import village as _vm
                    if cand in _vm.PEOPLE:
                        _vm.PEOPLE.remove(cand)
                except Exception:
                    pass
                cand.village = hub
                cand.hub = hub
                cand.nation = NATION
                cand.role = "Criminal"
                cand.job = want
                cand.farm_plot = 0 if want == "farm" else None
                cand.workplace = None
                cand.stock["shovel" if want == "farm" else "axe"] = 1
                cand.tool_uses = economy.TOOL_USES
                cand.x, cand.y = hub.x, hub.y + 40.0
                cand.home = (cand.x, cand.y)
                hub.npcs.append(cand)
                _note("HUB      %s takes %s from %s as %s"
                      % (hub.name, getattr(cand, "name", "?"), town.name, want))
                break

    def add_player_hub(self, owner, yard, ring, gates=()):
        """THE YARD HE CLOSED BECOMES HIS HUB, once, and by name."""
        for h in self.hubs:
            if getattr(h, "is_player_hub", False):
                if h.fence_rect.colliderect(yard.inflate(300, 300)):
                    return None                 # that ground is already his
        hub = PlayerHub(owner, yard, ring, gates)
        self.hubs.append(hub)
        reg = getattr(self, "_villages", None)
        if reg is not None:
            # HIS YARD IS NOT IN THE WORLD'S LIST OF SETTLEMENTS. The criminal
            # huts must be there (nothing else knows where they are); his is
            # not: his fences and his houses are already drawn and already
            # solid, and a yard pretending to be a town crashed the frame.
            reg.offlattice = [h for h in self.hubs
                              if not getattr(h, "is_player_hub", False)]
        _note("PLAYER HUB  %s  at (%.0f,%.0f)  %dx%d" %
              (hub.name, hub.x, hub.y, yard.w, yard.h))
        return hub

    def draw(self, screen, cam_x: float, cam_y: float, vw: int, vh: int) -> None:
        view = pygame.Rect(int(cam_x) - 300, int(cam_y) - 300, vw + 600, vh + 600)
        for hub in self.hubs:
            fr = getattr(hub, "fence_rect", None)
            if fr is not None and view.colliderect(fr):
                hub.draw(screen, cam_x, cam_y, vw, vh)

    def all_npcs(self) -> list:
        return [n for h in self.hubs for n in h.npcs if n.alive]
