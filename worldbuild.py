"""worldbuild.py -- WILD SPAWNS AND THE LOOT CALL.

The old town builder, its population pass, its patrols and its capital lookup
are gone. The native world lays out its own camps. What remains here is the
handful of helpers the frame still calls for wild animals, corpse loot and
creature targeting.
"""

from __future__ import annotations

from creatures import choose_target as creatures_choose_target


# -- legacy town hooks, now empty -------------------------------------------
def world_cells() -> list:
    return []


def load_world(screen, clock, villages, world=None) -> None:
    return None


def set_world_population(villages, target: int = 1000) -> int:
    return 0


def freeze_far_villages(villages, px: float, py: float, radius: float) -> int:
    return 0


def make_village_patrol(village, count, fence, random, nation_color, Soldier):
    return []


def main_capital(villages):
    return (None,)


def origin_village(kind, villages):
    return None


# -- live wild spawns -------------------------------------------------------
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
        import world as _world
        if x > _world.coast_x(y, world.seed):
            continue
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
    import world as _world
    if rx > _world.coast_x(ry, world.seed):
        return
    rabbits.append(Rabbit(rx, ry, biomes.rabbit_fur(
        float(world.temperature(rx, ry)), float(world.humidity(rx, ry)))))


def spawn_horse(player, world, horses, biomes, math, random, Horse) -> None:
    for _ in range(12):
        angle = random.uniform(0.0, 2.0 * math.pi)
        dist = random.uniform(300.0, 1200.0)
        hx = player.x + math.cos(angle) * dist
        hy = player.y + math.sin(angle) * dist
        import world as _world
        if hx > _world.coast_x(hy, world.seed):
            continue
        t = float(world.temperature(hx, hy))
        h = float(world.humidity(hx, hy))
        if biomes.biome_name(t, h) == "desert":
            continue
        coat = random.choice(("brown", "brown", "black", "white", "palomino"))
        n = random.randint(2, 4)
        for _ in range(n):
            ox = random.uniform(-70.0, 70.0)
            oy = random.uniform(-70.0, 70.0)
            horses.append(Horse(hx + ox, hy + oy, coat))
        return


def spawn_bison(player, world, enemies, biomes, math, random, Bison) -> None:
    for _ in range(24):
        angle = random.uniform(0.0, 2.0 * math.pi)
        dist = random.uniform(1800.0, 4200.0)
        hx = player.x + math.cos(angle) * dist
        hy = player.y + math.sin(angle) * dist
        import world as _world
        if hx > _world.coast_x(hy, world.seed):
            continue
        t = float(world.temperature(hx, hy))
        h = float(world.humidity(hx, hy))
        if biomes.biome_name(t, h) == "desert":
            continue
        for _ in range(random.randint(3, 5)):
            ox = random.uniform(-80.0, 80.0)
            oy = random.uniform(-80.0, 80.0)
            enemies.append(Bison(hx + ox, hy + oy))
        return


def choose_target(creature, villages, who, enemy_grid, engage_reach, folk_grid,
                  look_reach, rabbits, squad):
    near = enemy_grid.near(creature.x, creature.y, engage_reach)
    folk = folk_grid.near(creature.x, creature.y, look_reach)
    return creatures_choose_target(creature, who, near, rabbits, villages,
                                   squad, persons=folk)
