"""worldbuild.py -- LAY OUT THE WORLD AND ITS PEOPLE.

The loading screen that builds every village up front, and the population
rule that makes the country exactly a thousand souls. Extracted from main.py.
"""

from __future__ import annotations

import random

import pygame
import plog
import village as village_mod


def world_cells():
    """Every village cell whose centre lies inside the world."""
    import main
    out = []
    n = int(main.CORE_HALF / main.SPACING) + 1
    # ONE RING FURTHER OUT THAN THE WORLD. A village near the edge has
    # neighbours just past it, and the trade route planner peeks at all eight
    # surrounding cells with villages.get() -- which BUILDS the ones that are
    # missing. So every trader's first run laid out villages beyond the world,
    # 600 ms at a time, inside a frame. That is what the world cache's
    # neighbour ring now prevents: everything the planner can look at is laid
    # out at load, and it never has to build one.
    for gx in range(-n - 2, n + 2):
        for gy in range(-n - 2, n + 2):
            cx, cy = (gx + 0.5) * main.SPACING, (gy + 0.5) * main.SPACING
            if (-main.CORE_HALF - main.SPACING * 1.5 <= cx <= main.CORE_HALF + main.SPACING * 1.5
                    and -main.CORE_HALF - main.SPACING * 1.5 <= cy
                    <= main.CORE_HALF + main.SPACING * 1.5):
                out.append((gx, gy))
    return out


def load_world(screen, clock, villages, world=None) -> None:
    """Build every village in the world before the player takes a step.

    Villages used to be built lazily as they came into view, which cost about a
    second inside a single frame -- that was the freeze you felt walking up to
    one, and the largest single cost in the whole frame profile. The villages
    are identical; they are simply all made now, once, with a bar to watch.
    """
    import main
    cells = world_cells()
    font = pygame.font.SysFont("dejavusans", 24, bold=True)
    small = pygame.font.SysFont("dejavusans", 15, bold=True)
    clock = pygame.time.Clock()
    for i, (gx, gy) in enumerate(cells):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
        villages.get(gx, gy)                     # build it here, not mid-swing
        screen.fill((14, 16, 18))
        title = font.render("Charting the world", True, (234, 230, 218))
        screen.blit(title, (main.WIDTH // 2 - title.get_width() // 2, main.HEIGHT // 2 - 74))
        bar = pygame.Rect(main.WIDTH // 2 - 230, main.HEIGHT // 2 - 20, 460, 24)
        pygame.draw.rect(screen, (36, 38, 42), bar, border_radius=7)
        frac = (i + 1) / float(len(cells))
        pygame.draw.rect(screen, (198, 152, 72),
                         (bar.x, bar.y, max(2, int(bar.w * frac)), bar.h),
                         border_radius=7)
        pygame.draw.rect(screen, (92, 92, 100), bar, 2, border_radius=7)
        label = small.render("%d of %d villages   -   %s"
                             % (i + 1, len(cells), villages.get(gx, gy).name),
                             True, (190, 186, 176))
        screen.blit(label, (main.WIDTH // 2 - label.get_width() // 2, bar.bottom + 12))
        pygame.display.flip()
        clock.tick(120)
    # THE ONE-TIME WORK, HERE, WHERE YOU CAN SEE IT. A village's first step
    # costs 54 ms and every step after it costs 0.2 -- and the 54 is the trade
    # route planner: "building all eight at once cost four seconds and 240 MB
    # inside a single frame". Sixty-four of those is three and a half seconds,
    # which is the loading screen's business and nobody else's. Paid here, the
    # whole world can then be stepped every step for 4.3 ms a frame.
    if world is not None:
        for i, v in enumerate(villages.villages):
            v.update(0.05, world, 1.0, "home")
            # AND THE ROUTE PLAN EXHAUSTED. trade_routes() fills ONE route per
            # call -- nine candidates, nine calls -- and a single warm-up left
            # eight of nine to be built during play, which is where the stall
            # was coming from even after the first step was paid for.
            for _ in range(10):
                try:
                    v.trade_routes()
                except Exception:
                    break
            screen.fill((14, 16, 18))
            t = font.render("Waking the villages", True, (234, 230, 218))
            screen.blit(t, (main.WIDTH // 2 - t.get_width() // 2, main.HEIGHT // 2 - 74))
            b = pygame.Rect(main.WIDTH // 2 - 230, main.HEIGHT // 2 - 20, 460, 24)
            pygame.draw.rect(screen, (36, 38, 42), b, border_radius=7)
            frac = (i + 1) / float(max(1, len(villages.villages)))
            pygame.draw.rect(screen, (198, 152, 72),
                             (b.x, b.y, max(2, int(b.w * frac)), b.h),
                             border_radius=7)
            pygame.draw.rect(screen, (92, 92, 100), b, 2, border_radius=7)
            lab = small.render("%d of %d" % (i + 1, len(villages.villages)),
                               True, (190, 186, 176))
            screen.blit(lab, (main.WIDTH // 2 - lab.get_width() // 2, b.bottom + 12))
            pygame.display.flip()
        # AND EVERY MAN, ONCE. His one-time work -- a trader's first route, an
        # order booked, a plot taken -- is paid for here with the towns', so
        # the first tick of the real game has nothing cold left in it.
        village_mod.rebuild_people(villages)
        for i, n in enumerate(list(village_mod.PEOPLE)):
            if n.alive:
                n.tick(0.05, world, 1.0, "home", None, False, (),
                       lambda who: None)

    screen.fill((14, 16, 18))
    done = small.render("The world is ready.", True, (190, 186, 176))
    screen.blit(done, (main.WIDTH // 2 - done.get_width() // 2, main.HEIGHT // 2))
    pygame.display.flip()


def _grow_town(v, n: int) -> int:
    """PUT n MORE PEOPLE IN A TOWN, the way the town was first peopled.

    A save can be thinner than the world it describes: the rosters are
    restored from a file, and a file written when the world was smaller (or
    when `rebuild_people` was capping towns at an old capacity) leaves the
    country half empty for ever. Nothing ever grew a town back, so 1,000
    people were 883 at the build and 535 after a load.
    """
    made = 0
    rng = getattr(v, "_rng", None) or random.Random(v.code & 0xFFFFFFFF)
    pool = getattr(v, "_name_pool", None) or list(village_mod.FIRST_NAMES)
    name_rng = getattr(v, "_name_rng", None) or random.Random(v.code ^ 0x9E3779B9)
    houses = list(getattr(v, "houses", ()) or ())
    for _ in range(max(0, int(n))):
        house = houses[rng.randrange(len(houses))] if houses else None
        if house is not None:
            fx, fy = getattr(house, "facing", (0.0, 1.0))
            door = (house.x + fx * (house.h / 2.0 + 10.0),
                    house.y + fy * (house.h / 2.0 + 10.0))
        else:
            door = (v.x, v.y)
        v._name_i = int(getattr(v, "_name_i", 0)) + 1
        name = "%s %s" % (pool[v._name_i % len(pool)],
                          name_rng.choice(village_mod.LAST_NAMES))
        try:
            sx, sy = v.random_point(rng)
        except Exception:
            sx, sy = v.x, v.y
        p = village_mod.NPC(sx, sy, v.code ^ (v._name_i * 83492791), name=name,
                            npc_id="npc_%d_%d_g%d" % (v.gx, v.gy, v._name_i),
                            village=v)
        p.home_house = house
        p.home_door = door
        p.wear = getattr(v, "_wear", 1.0)
        p.nation = v.nation
        p.team = ("nation", v.nation)
        if house is not None:
            house.occupants.append(p)
        v.npcs.append(p)
        made += 1
    return made


def set_world_population(villages, target: int = 1000) -> int:
    """The world is a thousand people. Make it exactly so, on either path.

    A town's share is its HOUSES -- a house is what a man sleeps in -- and the
    cap is set to match so `can_grow` holds it there instead of letting the
    town expand back to some number no file can account for.

    This runs BEFORE the world cache is written, which is the other half of the
    bug: the cache carried all 2,084 of them, so a launch that restored from
    the cache rebuilt two thousand men and then cut half away, every time.
    """
    towns = list(villages.villages)
    if not towns:
        return 0
    total = sum(len(v.npcs) for v in towns)
    _born = _cut = 0
    if total != target:
        kept = 0
        for i, v in enumerate(towns):
            if i == len(towns) - 1:
                want = max(1, target - kept)          # the last takes the rest
            else:
                # by HOUSES, so a big town keeps a big population
                houses = max(1, len(getattr(v, "houses", ())))
                want = max(1, int(round(float(target) * houses
                                        / float(_total_houses(towns)))))
            if len(v.npcs) > want:
                _cut += len(v.npcs) - want
                v.npcs[:] = v.npcs[:want]
            elif len(v.npcs) < want:
                # A TOWN BELOW ITS SHARE IS FILLED, not left short. Trimming
                # only ever took people away, so a world built at 883 stayed
                # at 883 and a save of 535 stayed at 535.
                _born += _grow_town(v, want - len(v.npcs))
            # THE CAP MUST COVER THE TOWN BEFORE THE REGISTER IS REBUILT.
            # `rebuild_people` keeps a town's men only up to its CAPACITY, and
            # this ran BEFORE the capacity was raised -- so every man just
            # grown was cut away again in the same call. 883 -> 1000 -> 883.
            v.capacity = max(int(getattr(v, "capacity", 0)), len(v.npcs))
            kept += len(v.npcs)
        village_mod.rebuild_people(villages)
    # THE CAP IS SET WHETHER OR NOT ANYTHING WAS TRIMMED. Leaving it out when
    # the count already equalled the target is how a world of exactly 1,000
    # people grew to 1,032 inside one day: the towns still held a capacity from
    # the build, and a town grows back to its capacity.
    # THE CAP IS THE TOWN'S SHARE, NOT ITS LUCK. A town whose capacity is
    # exactly what it holds can never take a birth back after a hard winter;
    # its SHARE is what it is allowed to grow to.
    houses_all = float(_total_houses(towns))
    for v in towns:
        share = int(round(float(target) * max(1, len(getattr(v, "houses", ())))
                          / houses_all))
        # THE CAP IS THE SHARE -- not the old capacity, which came from a
        # smaller world and let the sum of ceilings reach 1,119.
        v.capacity = max(share, len(v.npcs))
    _fin = sum(len(v.npcs) for v in villages.villages)
    try:
        plog.log("POP", "entry", total, "target", target, "grown", _born,
                 "cut", _cut, "final", _fin,
                 "capacities", sum(int(getattr(v, "capacity", 0)) for v in towns))
    except Exception:
        pass
    return _fin


def _total_houses(towns) -> int:
    return max(1, sum(len(getattr(v, "houses", ())) for v in towns))




import economy
import fence
from creatures import Soldier, Wolf, Rabbit, choose_target as creatures_choose_target
from village import nation_color
import biomes


def make_village_patrol(village, count, fence, random, nation_color, Soldier):
    """THE MEN AT THE GATE."""
    squad = []
    for gi, (_side, gx, gy) in enumerate(fence.gate_list(village)[:count]):
        _ox, _oy = fence.OUTWARD.get(_side, (0.0, 1.0))
        _ax, _ay = -_oy, _ox
        _bx = gx + _ox * 26.0
        _by = gy + _oy * 26.0
        _px, _py = _bx, _by
        _best = -1.0
        try:
            import rail as _r
            for _out, _off in ((0.0, 110.0), (0.0, -110.0), (0.0, 150.0),
                               (0.0, -150.0), (76.0, 0.0), (-76.0, 0.0),
                               (150.0, 0.0), (-150.0, 0.0),
                               (76.0, 110.0), (76.0, -110.0)):
                _cx = _bx + _ax * _off + _ox * _out
                _cy = _by + _ay * _off + _oy * _out
                _d = _r.dist(_cx, _cy)
                if _d > _best:
                    _best, _px, _py = _d, _cx, _cy
                if _d >= 95.0:
                    break
        except Exception:
            _px = _bx + _ax * (130.0 if gi % 2 == 0 else -130.0)
            _py = _by + _ay * (130.0 if gi % 2 == 0 else -130.0)
        s = Soldier(_px, _py, village.nation, melee=False,
                    seed=random.randint(0, 2 ** 31),
                    color=nation_color(village.nation))
        s.is_militia = True
        try:
            import guns as _guns
            s.weapon = "rifle"
            s.gun_kind = _guns.RIFLE
            s.mag = _guns.MAG[_guns.RIFLE]
        except Exception:
            pass
        s.gate_village = village
        s.guard_village = village
        s.name = "the guard of %s" % getattr(village, "name", "the gate")
        s.gate_index = gi
        s.gate_post = (_px, _py)
        s.home = s.gate_post
        s.target = s.gate_post
        s.patrol_center = None
        s.patrol_r = 0.0
        s.idle_timer = 1.0e9
        s.hostile = getattr(village, "provoked", False)
        s.fire_cd = random.uniform(0.05, 0.30)
        s.ammo = 30
        squad.append(s)
    return squad


def loot(killer, victim, player, economy, inventory, toast) -> None:
    """Everything the dead man carried goes to whoever dropped him."""
    bag = economy.loot_body(getattr(killer, "home_npc", None) or killer, victim)
    if killer is player and bag:
        shown = []
        for item, qty in bag.items():
            if qty <= 0:
                continue
            left = inventory.add(item, int(qty))
            if int(qty) - left > 0:
                shown.append("%s x%d" % (item, int(qty) - left))
            if left:
                toast("Dropped %s x%d -- no room" % (item, left))
        victim.stock.clear()
        if shown:
            toast("Looted " + ", ".join(shown))


def spawn_wolf(player, world, village_mod, enemies, biomes, math, random,
               Wolf, origin_town) -> None:
    for _ in range(24):
        angle = random.uniform(0.0, 2.0 * math.pi)
        dist = random.uniform(2600.0, 5200.0)
        x = player.x + math.cos(angle) * dist
        y = player.y + math.sin(angle) * dist
        if village_mod.village_clearance(x, y, world.seed) < 0.0:
            continue
        _ot = origin_town
        if _ot is not None and (math.hypot(x - getattr(_ot, "x", x),
                                           y - getattr(_ot, "y", y))
                                < village_mod.SPACING * 0.12):
            continue
        enemies.append(Wolf(x, y, biomes.predator_kind(
            float(world.temperature(x, y)), float(world.humidity(x, y)))))
        return


def spawn_rabbit(player, world, rabbits, biomes, math, random, Rabbit) -> None:
    angle = random.uniform(0.0, 2.0 * math.pi)
    dist = random.uniform(180.0, 700.0)
    rx = player.x + math.cos(angle) * dist
    ry = player.y + math.sin(angle) * dist
    rabbits.append(Rabbit(rx, ry, biomes.rabbit_fur(
        float(world.temperature(rx, ry)), float(world.humidity(rx, ry)))))


def main_capital(villages):
    """The seat: the town whose king is the Dictator."""
    best = None
    for _v in villages.villages:
        if getattr(_v, "king", None) is not None:
            return (_v,)
        if best is None and getattr(_v, "is_capital", False):
            best = _v
    return (best,)


def choose_target(creature, villages, who, enemy_grid, engage_reach, folk_grid,
                  look_reach, rabbits, squad):
    near = enemy_grid.near(creature.x, creature.y, engage_reach)
    folk = folk_grid.near(creature.x, creature.y, look_reach)
    return creatures_choose_target(creature, who, near, rabbits, villages,
                                   squad, persons=folk)


def origin_village(kind, villages):
    """The town that has work for him, nearest to the origin first."""
    wants = {"smith": "smith", "artisan": "lab", "brewer": "brewery"}.get(kind)
    if kind == "soldier":
        for v in sorted(villages.villages, key=lambda v: v.x * v.x + v.y * v.y):
            if getattr(v, "is_capital", False):
                return v
        return None
    for v in sorted(villages.villages, key=lambda v: v.x * v.x + v.y * v.y):
        if kind == "farmer":
            if v.farm_plots:
                return v
        elif wants is None:
            return v
        elif any(wp.kind == wants for wp in v.workplaces):
            return v
    return None
