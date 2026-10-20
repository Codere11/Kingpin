#!/usr/bin/env python3
"""Kingpin -- top-down open-world game prototype.

WASD / arrows move, SHIFT sprints (limited stamina), the mouse aims, Esc quits.

Left click uses the selected item:
    Rifle                      fire a bullet
    Shovel                     dig a nearby tile into dirt
    Watering Can               turn nearby dirt into fertile soil
    Seed Bag                   plant a tobacco seedling in fertile soil
    First-Aid Kit              heal yourself
    anything but the Rifle     harvest a fully-grown tobacco plant

There is one enemy gunman, who does not come back. Villages of friendly
villagers dot the world; their houses are solid, block line of sight, and many
have a tobacco plot out back. Death brings up a pixelated Game Over screen.
"""

from __future__ import annotations

import math
import lanes
import mine
import os
import random
import sys
import time

import pygame

import crop
import biomes
import board
import compass
import economy
import items
import quality
import farm
import fence
import guns
import map as mapmod
import hubs
import ore
import persist
import steering
import nemesis
import observer
# A TOP-LEVEL IMPORT, not a local one inside a function. PyInstaller follows
# static imports when it decides what to bundle; a `import deaths` buried in a
# try/except inside a hot function is invisible to it, so the exe would raise
# ImportError at the moment of a death -- and the except that guards the call
# would swallow it, and every death would go unrecorded with no sign why.
import deaths
import tournament
import village as village_mod
import war
import wildcrop
import world
import worldmap
from blood import Blood
from build import BuildMenu, build_cost
from combat import Combat, segment_circle_hit
from creatures import (Patrol, Rabbit, Soldier, Wolf, is_trader,
                       choose_target as
                       creatures_choose_target, make_squad,
                       set_time as creatures_set_time)
from effects import DamageVignette, draw_alert
from enemy import Enemy
from gameover import GameOver

_NPC_ERRORS = set()      # distinct per-man tick errors already reported
from interior import (Interior, fill_loot, BARREL_H, BARREL_W, BREW_H, BREW_W,
                      LAB_H, LAB_W, WORKSHOP_H, WORKSHOP_W)
from inventory import Inventory, ItemStack
from physics import (StaticGrid, TeamGrid, avoid_direction, resolve_circle_out_of,
                     resolve_circle_pairs, resolve_circle_rects, segment_rect_hit)
from player import Player
from skills import Skills
from trade import TradeMenu
from workshop import WorkshopMenu
from trees import Trees
from ui import ChestPanel, ConfirmMenu, Hotbar, InventoryPanel, PauseMenu
from village import (NPC_SPACING, ROOFS, SPACING, VILLAGE_SCALE,
                     House, Villages, nation_color, set_forest,
                     nation_name, village_center)
from vision import Vision
from world import TILE, GroundRenderer, Scatter, StaticLayer, World

WIDTH, HEIGHT = 1280, 720
FPS = 60
ZOOM = 2.25                # the world is drawn at 4/9 size, then blown up
WORLD_STEP = 1.0 / 20.0   # villagers/crops/villages tick 20x a second, not 60
REACH = 104.0            # how far the player can work a tile

# THE TRADES A NOTICE BOARD CAN HIRE FOR. Kept here, beside the board that
# offers them, so the wage block and the board can never disagree about what
# counts as "employed".
_BOARD_TRADES = ("farm", "logger", "trader", "smith", "mine", "lab", "brewery")
AXE_REACH = 64.0         # axe swing reach
AXE_ARC = math.radians(78.0)
AXE_STRIKES = 3          # hits to fell a tree
# THE PLAYER HITS AS HARD AS A SOLDIER. He used to hit for 33 -- twice a
# soldier's 16, and more than triple a villager's 10 -- so every fight in the
# world was his to lose and nothing could ever threaten him. 16 is
# creatures.Soldier.melee_damage exactly: the man in the ranks is his equal.
# Unarmed he does 16 / skills.UNARMED_WEAKNESS = 4, which is what every
# candidate in the capital's tournament does.
MELEE_DAMAGE = 16         # == a soldier's melee, and a third of a villager's
BUILD_COST = 100         # wood cost of a house
BUILD_W = 120
BUILD_H = 110
DAY_LENGTH = 600.0       # one full day + night
SLEEP_TIME = 3.0         # seconds of black screen when you sleep in a bed


class _NoKeys:
    """A stand-in key state that reports nothing pressed."""

    def __getitem__(self, key):
        return False


_NO_KEYS = _NoKeys()

TOAST_COLOR = (240, 226, 172)


def draw_crosshair(screen: pygame.Surface, mx: int, my: int) -> None:
    color = (238, 238, 238)
    pygame.draw.circle(screen, color, (mx, my), 7, 1)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(screen, color,
                         (mx + dx * 11, my + dy * 11),
                         (mx + dx * 4, my + dy * 4), 1)


WORLD_HALF = 100000         # the world runs from -100k to +100k


def world_cells():
    """Every village cell whose centre lies inside the world."""
    out = []
    n = int(WORLD_HALF / SPACING) + 1
    # ONE RING FURTHER OUT THAN THE WORLD. A village near the edge has
    # neighbours just past it, and the trade route planner peeks at all eight
    # surrounding cells with villages.get() -- which BUILDS the ones that are
    # missing. So every trader's first run laid out villages beyond the world,
    # 600 ms at a time, inside a frame. That is what the world cache's
    # neighbour ring now prevents: everything the planner can look at is laid
    # out at load, and it never has to build one.
    for gx in range(-n - 2, n + 2):
        for gy in range(-n - 2, n + 2):
            cx, cy = (gx + 0.5) * SPACING, (gy + 0.5) * SPACING
            if (-WORLD_HALF - SPACING * 1.5 <= cx <= WORLD_HALF + SPACING * 1.5
                    and -WORLD_HALF - SPACING * 1.5 <= cy
                    <= WORLD_HALF + SPACING * 1.5):
                out.append((gx, gy))
    return out


_STATE_SKIP = {"id", "name", "village", "home_house", "home_door",
               "bond_partner", "workplace", "refuge", "social_target",
               "guards", "patrol", "npcs", "houses", "workplaces", "mayor",
               "king", "registry", "rng", "_rng", "image", "_atlas", "rect",
               "sight_rect", "slots", "board", "gate_t"}


# What actually changes between saves. Everything else on a person -- his
# trade, his pack, his grades, his skills, every flag -- is the bulk, and it
# is the same from one save to the next. Rebuilding it for two thousand people
# every time cost 194 ms on its own.
_VOLATILE = ("x", "y", "coins", "hunger", "health")
_BULK: dict = {}


def _bulk(n) -> dict:
    out = {}
    for key, value in vars(n).items():
        if key in _STATE_SKIP or key in _VOLATILE or not _simple(value):
            continue
        out[key] = list(value) if isinstance(value, tuple) else value
    return out


def _simple(value) -> bool:
    return (value is None or isinstance(value, (bool, int, float, str))
            or (isinstance(value, (list, tuple))
                and all(v is None or isinstance(v, (bool, int, float, str))
                        for v in value))
            or (isinstance(value, dict)
                and all(isinstance(k, str) and (v is None or
                         isinstance(v, (bool, int, float, str)))
                        for k, v in value.items())))


def _plain(obj) -> dict:
    """EVERY simple field an object has.

    Not a hand-picked dozen: every number, flag, string and little dictionary
    on him -- his hunger, his wear, his loans, his tool orders, his barrel of
    wort, whether he is asleep or indoors. Anything pointing at another object
    is stored separately, by id or by index, because an object is not a
    number. Written this way a new field is saved the day it is added.
    """
    out = {}
    for key, value in vars(obj).items():
        if key in _STATE_SKIP or not _simple(value):
            continue
        out[key] = list(value) if isinstance(value, tuple) else value
    return out


def _restore(obj, blob) -> None:
    for key, value in (blob or {}).items():
        if key in _STATE_SKIP:
            continue
        try:
            setattr(obj, key, value)
        except Exception:
            pass


def world_to_data(villages) -> list:
    """The whole world's state, people and all, in a shape a load can use."""
    out = []
    for (gx, gy), v in villages._cache.items():
        people = []
        for n in v.npcs:
            house = None
            if getattr(n, "home_house", None) is not None:
                try:
                    house = v.houses.index(n.home_house)
                except ValueError:
                    house = None
            work = None
            if getattr(n, "workplace", None) is not None:
                try:
                    work = v.workplaces.index(n.workplace)
                except ValueError:
                    work = None
            ref = getattr(n, "refuge", None)
            sig = (n.job, n.alive, getattr(n, "ranged", False),
                   len(n.stock), len(n.grade), sum(n.stock.values()),
                   len(getattr(n, "tool_orders", ()) or ()),
                   getattr(n, "levied", False), getattr(n, "defender", False),
                   getattr(n, "is_mayor", False))
            got = _BULK.get(id(n))
            if got is None or got[0] != sig:
                got = (sig, _bulk(n))
                _BULK[id(n)] = got
            state = dict(got[1])
            state["x"] = n.x
            state["y"] = n.y
            state["coins"] = n.coins
            state["hunger"] = n.hunger
            state["health"] = n.health
            people.append({
                "id": n.id, "state": state, "house": house, "work": work,
                # skills are an object, not a number: a life's practice has
                # to be carried across by hand.
                "skills": [n.skills.farming, n.skills.movement,
                           n.skills.axe, n.skills.shooting],
                "village": ("%d,%d" % (n.village.gx, n.village.gy)
                            if getattr(n, "village", None) is not None else None),
                "bond": getattr(getattr(n, "bond_partner", None), "id", None),
                "refuge": ("%d,%d" % (ref.gx, ref.gy) if ref is not None else None),
            })
        houses = [{"warmth": float(getattr(h, "warmth", 1.0)),
                   "door_broken": bool(getattr(h, "door_broken", False)),
                   "occupants": [getattr(o, "id", None) for o in
                                 getattr(h, "occupants", ())]}
                  for h in v.houses]
        out.append({
            "gx": gx, "gy": gy,
            "state": _plain(v),
            "houses": houses,
            "workers": [getattr(w.worker, "id", None) for w in v.workplaces],
            "mayor": getattr(getattr(v, "mayor", None), "id", None),
            "king": getattr(getattr(v, "king", None), "id", None),
            "people": people,
        })
    return out


_WORLD_CACHE_VERSION = 5        # bump when the shape of a VILLAGE changes...
# ...or the shape of the WORLD. The cache is keyed by seed alone, so a change
# to the spacing would otherwise load a world laid out to the OLD distances
# while every rule in the game used the new ones.


# THE WORLD'S SHAPE HAS A VERSION, AND IT BELONGS IN THE FILENAME.
#
# The cache is the BUILT world -- every plot, every garden tile already planted,
# every bench already standing. Changing the rules of what a village may contain
# does not change a world that was built before the rules, and the game happily
# loaded the old one: gardens still half tobacco, benches still there, all of it
# looking exactly like the change had never been made. Bump this and the old
# cache is simply not found, so the world is laid out again to the new law.
WORLD_VERSION = 2


def _world_cache_path(seed: int) -> str:
    return os.path.join(persist.DIR,
                        "world_%d_v%d.pkl" % (int(seed), WORLD_VERSION))


def load_cached_world(seed: int):
    """The whole built world, read back instead of laid out again.

    Laying out 36 villages costs about 1.8 s, and every house, plot, fence,
    road and villager in them. The seed decides all of it, so the first launch
    writes the built object graph to disk and every launch after that reads it
    back. Houses keep their sprites out of the file (a Surface cannot be
    pickled) and draw them again the first time they are wanted.
    """
    import pickle
    target = _world_cache_path(seed)
    if not os.path.exists(target):
        return None
    try:
        with open(target, "rb") as fh:
            blob = pickle.load(fh)
    except Exception as exc:
        print("world cache unreadable (%r) -- laying the world out again" % (exc,))
        return None
    if not isinstance(blob, dict) or blob.get("version") != _WORLD_CACHE_VERSION:
        return None
    villages = blob.get("villages")
    if villages is None or getattr(villages, "seed", None) != seed:
        return None
    if not getattr(villages, "_cache", None):
        # AN EMPTY WORLD IS NOT A CACHE. A partial write left a 150-byte file
        # with no towns in it, and this loaded it gladly -- so the game ran on
        # an empty world and every man in it was a stranger to the register.
        print("world cache holds no villages -- laying the world out again")
        return None
    return villages


def save_cached_world(villages, seed: int) -> None:
    """Write the freshly laid out world, so it is never laid out twice."""
    import pickle
    target = _world_cache_path(seed)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        blob = {"version": _WORLD_CACHE_VERSION, "villages": villages}
        tmp = target + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(blob, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, target)
    except Exception as exc:
        print("could not cache the world (%r)" % (exc,))


def world_from_data(villages, blob) -> None:
    """Put every bit of it back."""
    if not blob:
        return
    by_id = {}
    for v in villages._cache.values():
        for n in v.npcs:
            by_id[n.id] = n
    for rec in blob:
        # A LOOKUP, NEVER A BUILD. The world is laid out from its seed; a save
        # only overlays the state of towns that exist. This called get(), which
        # CONSTRUCTS a town that is not there -- so a save from the era of the
        # town-building bug restored three hundred and sixty towns that had
        # never been part of the world, and eighteen thousand people with them.
        v = villages._cache.get((rec["gx"], rec["gy"]))
        if v is None:
            continue
        _restore(v, rec.get("state"))
        for i, hb in enumerate(rec.get("houses", [])):
            if i >= len(v.houses):
                break
            house = v.houses[i]
            house.warmth = float(hb["warmth"])
            house.door_broken = bool(hb["door_broken"])
        keep = set()
        for p in rec["people"]:
            n = by_id.get(p["id"])
            if n is None:
                # A SAVE CANNOT INVENT A CITIZEN. The people come from the
                # world cache, which is laid out from the seed; a save is an
                # overlay of their state and knows nothing the world does not
                # already hold. This branch used to CREATE a villager for any
                # record it could not match -- so a save written while the
                # town-building bug was live came back with 36,595 people who
                # had never existed, invented at load, and the world walked
                # every one of them for ever.
                continue
            _restore(n, p.get("state"))
            if p.get("skills"):
                (n.skills.farming, n.skills.movement,
                 n.skills.axe, n.skills.shooting) = p["skills"]
            # ...and the things that are not numbers: his house, his post,
            # his plot, his partner, the village he belongs to.
            if p.get("house") is not None and p["house"] < len(v.houses):
                n.home_house = v.houses[p["house"]]
            if p.get("work") is not None and p["work"] < len(v.workplaces):
                n.workplace = v.workplaces[p["work"]]
            if p.get("village"):
                vgx, vgy = (int(t) for t in p["village"].split(","))
                n.village = villages.get(vgx, vgy)
            else:
                n.village = v
            if p.get("refuge"):
                rgx, rgy = (int(t) for t in p["refuge"].split(","))
                n.refuge = villages.get(rgx, rgy)
            if n not in v.npcs:
                v.npcs.append(n)
            keep.add(p["id"])
        for n in list(v.npcs):                # gone: dead, or marched away
            if n.id not in keep:
                v.npcs.remove(n)
        for i, wid in enumerate(rec.get("workers", [])):
            if i < len(v.workplaces):
                v.workplaces[i].worker = by_id.get(wid) if wid else None
        for i, hb in enumerate(rec.get("houses", [])):
            if i < len(v.houses):
                v.houses[i].occupants = [by_id[o] for o in hb["occupants"]
                                         if o in by_id]
        # A RESTORE MUST NOT UNSEAT A MAYOR IT NEVER KNEW ABOUT. The village
        # chose its own mayor at creation; the record only carries one if a
        # save was written after an election. Assigning None when the key is
        # missing threw the government of EVERY town in the world away on
        # load, and left only the one town whose id happened to be in the file
        # still holding a chain -- 1 mayor in 33, which is what the survey
        # found. Same for the King: a capital does not lose its crown because
        # an older save did not mention it.
        _m = by_id.get(rec["mayor"]) if rec.get("mayor") else None
        if _m is not None and getattr(_m, "alive", False):
            v.mayor = _m
        _k = by_id.get(rec["king"]) if rec.get("king") else None
        if _k is not None and getattr(_k, "alive", False):
            v.king = _k
        if v.mayor is not None:
            v.mayor.plaza = (v.x, v.y)
        for n in v.npcs:                      # partners, once everyone is in
            pid = next((p["bond"] for p in rec["people"]
                        if p["id"] == n.id), None)
            if pid:
                n.bond_partner = by_id.get(pid)


def load_world(screen, clock, villages, world=None) -> None:
    """Build every village in the world before the player takes a step.

    Villages used to be built lazily as they came into view, which cost about a
    second inside a single frame -- that was the freeze you felt walking up to
    one, and the largest single cost in the whole frame profile. The villages
    are identical; they are simply all made now, once, with a bar to watch.
    """
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
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 74))
        bar = pygame.Rect(WIDTH // 2 - 230, HEIGHT // 2 - 20, 460, 24)
        pygame.draw.rect(screen, (36, 38, 42), bar, border_radius=7)
        frac = (i + 1) / float(len(cells))
        pygame.draw.rect(screen, (198, 152, 72),
                         (bar.x, bar.y, max(2, int(bar.w * frac)), bar.h),
                         border_radius=7)
        pygame.draw.rect(screen, (92, 92, 100), bar, 2, border_radius=7)
        label = small.render("%d of %d villages   -   %s"
                             % (i + 1, len(cells), villages.get(gx, gy).name),
                             True, (190, 186, 176))
        screen.blit(label, (WIDTH // 2 - label.get_width() // 2, bar.bottom + 12))
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
            screen.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 2 - 74))
            b = pygame.Rect(WIDTH // 2 - 230, HEIGHT // 2 - 20, 460, 24)
            pygame.draw.rect(screen, (36, 38, 42), b, border_radius=7)
            frac = (i + 1) / float(max(1, len(villages.villages)))
            pygame.draw.rect(screen, (198, 152, 72),
                             (b.x, b.y, max(2, int(b.w * frac)), b.h),
                             border_radius=7)
            pygame.draw.rect(screen, (92, 92, 100), b, 2, border_radius=7)
            lab = small.render("%d of %d" % (i + 1, len(villages.villages)),
                               True, (190, 186, 176))
            screen.blit(lab, (WIDTH // 2 - lab.get_width() // 2, b.bottom + 12))
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
    screen.blit(done, (WIDTH // 2 - done.get_width() // 2, HEIGHT // 2))
    pygame.display.flip()


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
                v.npcs[:] = v.npcs[:want]
            kept += len(v.npcs)
        village_mod.rebuild_people(villages)
    # THE CAP IS SET WHETHER OR NOT ANYTHING WAS TRIMMED. Leaving it out when
    # the count already equalled the target is how a world of exactly 1,000
    # people grew to 1,032 inside one day: the towns still held a capacity from
    # the build, and a town grows back to its capacity.
    for v in towns:
        v.capacity = len(v.npcs)
    return sum(len(v.npcs) for v in villages.villages)


def _total_houses(towns) -> int:
    return max(1, sum(len(getattr(v, "houses", ())) for v in towns))


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Kingpin")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()

    import menu
    pygame.mouse.set_visible(True)
    chosen = menu.run(screen, clock)
    if chosen is None:
        pygame.quit()
        return
    slot, test_mode = chosen
    # NO BACKSTORY. No trade, no town, no debt, nothing owed to anybody. He
    # starts in the middle of the country with an axe and that is all -- the
    # picker and the letter are still in menu.py, unused, if that changes.
    origin = "idle"
    try:
        deaths.banner("game slot %s%s" % (slot, "  TEST MODE" if test_mode else ""))
    except Exception:
        pass
    persist.set_test(test_mode)
    persist.set_slot(slot)
    pygame.mouse.set_visible(False)

    _save = persist.read()
    world = World(seed=int(_save.get("seed", 20240501)))
    ground = GroundRenderer(world)
    world.ground = ground          # so soil edits from anywhere can redraw
    scatter = Scatter(world.seed, world)
    ground.scatter = scatter
    static_layer = StaticLayer(ground, scatter)
    vision = Vision(cone_deg=175.0, max_dist=560.0)
    interior_vision = Vision(cone_deg=175.0, max_dist=560.0, downscale=3)
    villages = Villages(world.seed)
    ground.villages_v = villages
    trees = Trees(world.seed)
    world.trees = trees            # so loggers can find the woods to cut
    set_forest(trees)              # villages stake out a woodlot as they build
    # Built here, once, with the bar. (A cache of this was tried and thrown
    # away: the save format holds what CHANGED, not the streets and walls that
    # the seed generates, so reading it back still built every village from
    # scratch -- and made a second copy of every villager on the way.)
    # THE WORLD IS LAID OUT ONCE IN ITS LIFE. Every launch after the first
    # reads the built villages back from disk instead of making them again --
    # the loading bar is for a genuinely new world, not for every time you
    # sit down to play.
    _cached = load_cached_world(world.seed)
    if _cached is not None:
        villages = _cached
        ground.villages_v = villages
        # THE REGISTER OF PEOPLE IS REBUILT AFTER A LOAD. Unpickling does not
        # call __init__, so a restored villager never put himself in it, and
        # the world would have walked nobody at all.
        print("registered from the cache: %d people, %d houses"
              % (village_mod.rebuild_people(villages),
                 village_mod.rebuild_houses(villages)))
    else:
        load_world(screen, clock, villages, world)  # every village, before the first step
        # THE POPULATION IS SET BEFORE THE CACHE IS WRITTEN. Writing it after
        # meant the cache held 2,084 people and every later launch restored all
        # of them and then threw half away again.
        set_world_population(villages)
        save_cached_world(villages, world.seed)
        village_mod.rebuild_people(villages)
        village_mod.rebuild_houses(villages)

    # ---- THE HUBS IN THE WILD -- not villages; no war can be declared
    # on one, because no one admits it exists.
    hub_world = hubs.Hubs(world, villages)
    # AND NO WOODS IN THE YARD. The trees are staked per VILLAGE, so a hub out
    # in the wild had a forest growing through its crop and its house. They are
    # marked felled directly rather than cut, because cutting leaves a stump
    # that regrows in three minutes.
    for _h in hub_world.hubs:
        _fr = getattr(_h, "fence_rect", None)
        if _fr is None:
            continue
        for _t in trees.visible(_fr.x - 200, _fr.y - 200,
                                _fr.w + 400, _fr.h + 400):
            if _fr.collidepoint(_t.x, _t.y):
                _t.felled = True
            pass

    # ---- A THOUSAND PEOPLE, AND A THOUSAND CAP, ALWAYS ------------------
    #
    # The last word on the size of the world, and it runs on BOTH paths -- a
    # fresh build and a restored save -- because an older save carries its own
    # `capacity` and `rebuild_people` trims every town down to it. That is
    # where two thirds of the world has been disappearing: the world is built
    # with 58 people a town, an older save says 17, and the register is cut to
    # the smaller number before anyone takes a step. Whatever a file says, the
    # world begins at the size it was designed for.
    _pop = set_world_population(villages)
    if _pop <= 0:
        print("WARNING: the world has no people at all")
    else:
        print("population set to %d over %d towns"
              % (_pop, len(list(villages.villages))))

    # ---- BUILD THE GROUND UNDER THE PLAYER **INSIDE THE LOADING SCREEN** ----
    #
    # The ground is generated a chunk at a time, on demand, as the camera needs
    # it. On a FRESH world nothing had warmed the cache, so the first frames
    # paid for terrain -- 256x256 chunks of fbm, temperature, humidity and
    # numpy clip -- one after another, INSIDE the frame: the first twenty
    # seconds of play ran at two frames a second and one frame took EIGHT.
    # Loading a save already warmed it (refresh_around, below in the restore
    # path); a new world never did.
    #
    # The player spawns at the origin, so that is the ground that is needed.
    # It is built here -- behind the loading screen, where a second of work is
    # a progress bar and not a stutter.
    try:
        ground.refresh_around(0.0, 0.0, WIDTH, HEIGHT)
    except Exception:
        pass

    ore_field = ore.OreField(world.seed)
    # THE TOWN THAT HAS WORK FOR HIM, nearest to the origin first. A man does
    # not arrive in a village that has no forge and call himself a smith.
    def origin_village(kind):
        wants = {"smith": "smith", "artisan": "lab", "brewer": "brewery"}.get(kind)
        if kind == "soldier":
            # THE ARMY IS AT THE CAPITAL. A soldier is the one trade that is
            # not in the town it works in: it is in the biggest town its nation
            # has, drawn up in the square.
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

    _home = None
    # HIS TOWN, UNDER A NAME NOTHING ELSE USES. `_home` is re-bound inside the
    # loop -- to a candidate, to a tuple of coordinates, to None -- and any
    # code that read it later was reading whatever the loop last left there.
    # That is what crashed on the first wolf spawn: `.x` off a tuple.
    _origin_town = _home
    _hx = 0.0                       # the middle of the world
    _hy = 0.0
    if _home is not None:
        # AND NOT IN THE ROAD: he starts a few paces off the door of the place
        # he is going to work, so the first thing he sees is his own trade.
        _wants = {"smith": "smith", "artisan": "lab", "brewer": "brewery"}.get(origin)
        _spot = None
        if _wants is not None:
            _spot = next((wp for wp in _home.workplaces if wp.kind == _wants), None)
        elif origin == "farmer" and _home.farm_plots:
            _tx, _ty, _k = _home.farm_plots[0]
            _spot = type("P", (), {"x": _tx * 32 + 16, "y": _ty * 32 + 16})()
        if _spot is not None:
            _hx, _hy = _spot.x, _spot.y + 64.0
    player = Player(_hx, _hy)
    # A NAME, AND A LETTER WAITING FOR HIM. The name is drawn the same way the
    # towns draw theirs, so he is a man out of this world and not a visitor to
    # it; the letter is the only thing in the game that will ever explain
    # anything, and it says who he is, what he owes, and how his trade pays.
    _rng = random.Random((int(_save.get("seed", 20240501)) ^ 0x5EED) & 0xFFFFFFFF)
    player.name = "%s %s" % (_rng.choice(village_mod.FIRST_NAMES),
                             _rng.choice(village_mod.LAST_NAMES))
    # HE IS ALREADY IN THE BOOK, AND ALREADY IN WORK. The letter says he has
    # just started as a smith; the board has to agree with the letter, so the
    # trade is his from the first frame and the debt is what the letter is
    # about. Idle owes the least and has no post, which is the trade-off.
    _JOB = {"smith": "smith", "artisan": "lab", "brewer": "brewery",
            "farmer": "farm", "logger": "logger", "trader": "trader",
            "soldier": "defender"}
    _DEBT = {"trader": 500, "smith": 450, "soldier": 430, "artisan": 400,
             "brewer": 370, "farmer": 340, "logger": 310, "idle": 300}
    player.origin = origin
    player.debt = 0                 # he owes nobody anything
    player.debt_paid = 0
    player.god = test_mode
    # THE TOWNS CAN NOW SEE HIM. One assignment, so a village can put the
    # player in an election or in a ring without every caller passing him down.
    village_mod.PLAYER = player

    cam_x = player.x - WIDTH / (2.0 * ZOOM)
    cam_y = player.y - HEIGHT / 2

    inventory = Inventory(capacity=32)
    # WHAT THE TRADE COMES WITH. A trader arrives with stock to sell, a smith
    # with iron at the anvil, and the logger with an axe and nothing else in
    # the world -- which is the hardest start and is meant to be.
    KITS = {"idle": (("axe", 1),),
        "trader":  (("tobacco", 10), ("beer", 3), ("cigar", 2)),
        "smith":   (("iron", 24),),
        "soldier": (("rifle", 1), ("ammo", 40), ("first_aid", 1)),
        "artisan": (("tobacco", 24),),
        "brewer":  (("wheat", 12), ("wheat_seed", 6)),
        "farmer":  (("wheat_seed", 12), ("seed_bag", 4), ("shovel", 1),
                    ("watering_can", 1)),
        "logger":  (("axe", 1),),
        "idle":    (),
    }
    for _item, _qty in KITS.get(origin, ()):
        inventory.add(_item, _qty)
    hotbar = Hotbar(inventory, visible=8)
    panel = InventoryPanel(inventory)
    board_panel = board.BoardPanel()
    # TEST MODE'S INSPECTOR AND LOCK-ON. See observer.py -- 'I' lists every
    # living person, filterable by trade, town and nation, and Enter locks the
    # camera onto one of them and starts a log of HIS doings alone.
    observer_ = observer.Observer()
    combat = Combat()
    blood = Blood()
    vignette = DamageVignette()
    overlay = GameOver()
    build_menu = BuildMenu(inventory)
    workshop_menu = WorkshopMenu(inventory)
    confirm = ConfirmMenu()
    compass_state = compass.Compass()
    compass_menu = compass.CompassMenu()
    build_menu.free = test_mode
    workshop_menu.free = test_mode
    pause_menu = PauseMenu()
    skills = Skills(is_player=True)   # the player's own road, see skills.py

    enemies: list[Enemy] = []          # nation soldiers and wolves
    armies: list = []                  # columns on the march, this campaign
    world.enemies = enemies            # so villagers can spot a predator
    rabbits: list[Rabbit] = []
    patrols: list[Patrol] = []
    player.nation = None
    player.squad = []
    spawn_timer = 0.0
    _lane_seen = None
    grid = None
    grid_timer = 0.0
    nav = None
    nav_timer = 0.0

    def make_village_patrol(village):
        """TWO GUARDS, ONE AT EACH GATE, WHO DO NOT WALK AWAY.

        They used to walk the village's whole political border -- a ring a
        kilometre out -- which meant the one thing a wall is for, WHO COMES
        THROUGH THE GATE, was watched by nobody. The wall cannot be cut now and
        the gate is the only way in, so the gate is where the state stands.

        One gate is the way IN and the other the way OUT, and the guard on the
        way in SEARCHES. That is the whole border.
        """
        squad = []
        try:
            gates = fence.gate_list(village)
        except Exception:
            gates = []
        for gi, (_side, gx, gy) in enumerate(gates[:2]):
            s = Soldier(gx, gy + 26.0, village.nation, melee=False,
                        seed=random.randint(0, 2 ** 31),
                        color=nation_color(village.nation))
            s.gate_village = village
            s.gate_index = gi            # 0 is the way in, 1 the way out
            s.gate_post = (gx, gy + 26.0)
            s.patrol_center = (village.x, village.y)
            s.patrol_r = 0.0             # he does not walk
            s.patrol_phase = 0.0
            s.patrol_village = village
            s.hostile = getattr(village, "provoked", False)
            s.fire_cd = random.uniform(0.05, 0.30)
            s.home = s.gate_post
            squad.append(s)
        return squad

    def spawn_patrol() -> None:
        cand = villages.visible(player.x - 4000.0, player.y - 4000.0, 8000, 8000)
        if not cand:
            return
        v = random.choice(cand)
        angle = random.uniform(0.0, 2.0 * math.pi)
        dist = v.radius + random.uniform(140.0, 700.0)
        patrol = Patrol(v.x + math.cos(angle) * dist,
                        v.y + math.sin(angle) * dist, v.nation,
                        size=random.randint(2, 4),
                        color=nation_color(v.nation))
        patrols.append(patrol)
        enemies.extend(patrol.members)

    def _loot(killer, victim) -> None:
        """Everything the dead man carried goes to whoever dropped him."""
        bag = economy.loot_body(getattr(killer, "home_npc", None) or killer,
                                victim)
        if killer is player and bag:          # the player's own pockets
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

    def spawn_wolf() -> None:
        for _ in range(24):
            angle = random.uniform(0.0, 2.0 * math.pi)
            # FURTHER OUT THAN THEY USED TO BE. The ring was 800 to 1,900
            # pixels and it was measured from the PLAYER -- which was fine when
            # he spawned in an empty field and is not fine now, because he
            # spawns inside a TOWN and a town is bigger than that ring. Wolves
            # arrived in the gardens on the first frame.
            dist = random.uniform(2600.0, 5200.0)
            x = player.x + math.cos(angle) * dist
            y = player.y + math.sin(angle) * dist
            # Never inside a village's cleared SQUARE. The old circle test let
            # wolves spawn in the fence corners, which is why they turned up
            # standing in people's gardens.
            if village_mod.village_clearance(x, y, world.seed) < 0.0:
                continue
            # AND NOT IN HIS OWN TOWN, whatever the clearance says.
            _ot = _origin_town
            if _ot is not None and (math.hypot(x - getattr(_ot, "x", x),
                                               y - getattr(_ot, "y", y))
                                    < village_mod.SPACING * 0.12):
                continue
            enemies.append(Wolf(x, y, biomes.predator_kind(
                float(world.temperature(x, y)), float(world.humidity(x, y)))))
            return

    def spawn_rabbit() -> None:
        angle = random.uniform(0.0, 2.0 * math.pi)
        dist = random.uniform(180.0, 700.0)
        rx = player.x + math.cos(angle) * dist
        ry = player.y + math.sin(angle) * dist
        rabbits.append(Rabbit(rx, ry, biomes.rabbit_fur(
            float(world.temperature(rx, ry)), float(world.humidity(rx, ry)))))

    # NO PATROLS. The gangs out on the map were removed in favour of the two
    # standing guards at each gate -- but this line kept spawning three of them
    # at the start of every game, and they and their shotguns were still out
    # there looking for somebody.
    for _ in range(3):
        spawn_wolf()
    for _ in range(5):
        spawn_rabbit()
    # ...and the death screen's own typeface, which was being built for the
    # first time in the frame the player died -- three SysFonts, a visible
    # stop at the worst possible moment. The size comes from the screen, not
    # from vw/vh: those are set inside the loop below, and naming them here
    # crashed the game the moment a world was made.
    _sw, _sh = screen.get_size()
    overlay.layout(_sw, _sh)
    seeded_villages: set[tuple[int, int]] = set()
    village_plots: set[tuple[int, int]] = set()

    game_over = False
    inventory_open = False
    chest_open = False
    chest_panel = None
    trade_open = False
    trade_menu = None
    build_menu_open = False
    workshop_open = False
    confirm_open = False
    compass_open = False
    pause_open = False
    map_open = False
    board_open = False
    smith_open = False
    smith_shop = None
    work_cd = 0.0
    work_msg = ""
    inside_mine = None
    mine_out = (0.0, 0.0)
    view_surf = None
    mine_cd = 0.0
    board_village = None
    ENV_CELL = 220.0            # static ground is cached per patch this size
    ENV_CACHE: dict = {}
    _BUILD_VER = [0]            # bumped when the player builds something
    SPEEDS = (1.0, 5.0, 25.0)     # test-mode time scale
    speed_i = 0
    time_scale = SPEEDS[0]
    # Chart the map at world creation, on a worker thread, so pressing M
    # simply shows it instead of stalling the game for a second.
    world_map = (worldmap.WorldMap(world.seed, background=True)
                 if test_mode else None)
    placing = None
    built_houses: list[House] = []
    built_fences: list = []
    built_gates: list = []
    fence_horizontal = True
    inside_house = None
    door_cooldown = 0.0
    backdrop = None
    kills = 0
    now = 0.0
    toast_text = ""
    toast_time = 0.0
    player_drip = 0.0
    hud_status = ""
    shade_cache: dict = {}
    active_chaos: list = []

    def award_levels() -> None:
        """A REAL level-up wears the shine.

        skills.py raises the flag as the level is crossed -- see
        Skills._note_levels -- and this is where it becomes something you can
        see. Called once a frame from each of the three places the player is
        stepped: the world above ground, the mine, and a house interior each
        have their own, and a man levels up in all three.
        """
        if skills.just_leveled:
            skills.just_leveled = False
            player.level_flash = player.LEVEL_FLASH

    def toast(message: str) -> None:
        nonlocal toast_text, toast_time
        toast_text = message
        toast_time = 1.6

    def clamp_world() -> None:
        """The world is finite, and the loading screen builds all of it.

        Villages used to be made lazily, the moment one came into view: 50-81 ms
        inside a single frame, the worst hitch in the game. load_world() now
        builds every cell up front, but that guarantee only holds if the man
        cannot walk out past the lattice it built. So the edge of the world is
        the edge of the world.
        """
        player.x = min(max(player.x, -WORLD_HALF), WORLD_HALF)
        player.y = min(max(player.y, -WORLD_HALF), WORLD_HALF)

    def respawn() -> None:
        nonlocal game_over
        game_over = False
        pygame.mouse.set_visible(False)
        player.respawn()
        combat.bullets.clear()
        combat.flashes.clear()

    WITNESS_PX = 900.0        # close enough to have watched it happen

    def _see_murder(victim) -> None:
        """Everyone who SAW it keeps it for ever.

        The story goes cold after fifty days, and the men who merely heard it
        forget. The men who watched do not -- so a world that has forgotten
        your name is still dangerous in one street, years later, because one
        old man is standing there who was in the square that afternoon.
        """
        village = getattr(victim, "village", None)
        if village is None:
            return
        for who in village.npcs:
            if not who.alive:
                continue
            if math.hypot(who.x - victim.x, who.y - victim.y) <= WITNESS_PX:
                who.witness((village_mod.PLAYER_ID,))

    def _meet_army(trader, army, now) -> None:
        """A caravan halts at a column. It sells what an army on the march
        cannot buy anywhere else -- powder to the riflemen, a gun to a man with
        coin and nothing to shoot -- and it LISTENS, because that is the only
        way word of a campaign ever gets off the road.
        """
        cap = getattr(army, "capital", None)
        for s in army.soldiers:
            if not getattr(s, "alive", False):
                continue
            man = getattr(s, "home_npc", None)
            if man is None or not man.alive:
                continue
            if getattr(s, "melee", True):
                item, want = "rifle", 1
            else:
                item, want = "ammo", economy.AMMO_WANT * 2 - getattr(s, "ammo", 0)
            if want <= 0:
                continue
            have = int(trader.stock.get(item, 0))
            if have <= 0:
                continue
            base = (cap.prices.get(item, economy.ITEM_VALUE.get(item, 8))
                    if cap is not None else economy.ITEM_VALUE.get(item, 8))
            price = max(1, int(base))
            take = max(0, min(have, want, int(man.coins // price)))
            if take <= 0:
                continue
            trader.stock[item] = have - take
            man.coins -= take * price
            trader.coins += take * price
            if item == "ammo":
                s.ammo = getattr(s, "ammo", 0) + take
            else:
                s.melee = False
                s.gun_kind = guns.RIFLE
                s.mag = guns.MAG[guns.RIFLE]
                s.ammo = getattr(s, "ammo", 0) + economy.AMMO_PER_RIFLE
        for s in army.soldiers[:8]:             # and the news goes with the trade
            war.tell(trader, s, now)

    def make_tradeable(npc):
        """GIVE A MAN A PURSE IF HE HAS NEVER NEEDED ONE.

        A villager is built for trade -- he has coins, a stock, a patience for
        how much leaf he wants and a face that reacts to a good deal. A SOLDIER
        is not: he has a rifle, a nation and a wage that is not modelled. But a
        soldier is a man with pay in his pocket and he buys what the town
        cannot sell him, so he gets the same purse the first time he is asked.
        """
        if getattr(npc, "coins", None) is None:
            npc.coins = 30 + (abs(hash((getattr(npc, "x", 0.0),
                                        getattr(npc, "y", 0.0)))) % 45)
            npc.trade_demand = 4
            npc.restock_timer = 0.0
            npc.stock = {}
        if not getattr(npc, "sly_flash", None):
            npc.sly_flash = 0.0
        # AND EVERYTHING `wants()` READS. A villager is built with a larder, a
        # habit, a thirst and a house; a soldier is built with a rifle. Asking
        # a soldier what he wants without these threw AttributeError from
        # inside the economy, which is a long way from the click that caused
        # it -- and it took the whole game down while the trade menu was being
        # drawn.
        if getattr(npc, "stock", None) is None:
            npc.stock = {}
        if getattr(npc, "job", None) is None:
            npc.job = "soldier"
        if getattr(npc, "home_house", "missing") == "missing":
            npc.home_house = None
        if not hasattr(npc, "wants_product"):
            npc.wants_product = "cigar"      # what he spends his pay on
        if not hasattr(npc, "wants_drink"):
            npc.wants_drink = "beer"
        if not hasattr(npc, "yearning"):
            npc.yearning = 0.85              # a man with pay, off duty
        if not hasattr(npc, "quality_pref"):
            npc.quality_pref = 0
        if not hasattr(npc, "rng"):
            # `wants()` rolls a die on the man's own generator. A soldier never
            # had one because he was never asked anything before.
            npc.rng = random.Random(int(abs(hash((npc.x, npc.y)))) & 0xFFFFFFFF)
        if getattr(npc, "trade_demand", 0) <= 0:
            npc.trade_demand = 4
        if not getattr(npc, "name", None):
            npc.name = "a soldier"
        if not hasattr(npc, "occupation"):
            npc.occupation = lambda: "soldier"
        return npc

    def guard_search(npc) -> None:
        """THE SEARCH AT THE GATE.

        A guard does not look in your pack, he decides whether to. The state's
        chance of finding contraband is the amount of it against the man
        carrying it:

            found = min(1, units / 100) * (1 - 0.09 * smuggling)

        A hundred items at nothing is a certainty; a hundred at ten is one in
        ten. Whatever gets through teaches the trade a little, and selling it
        teaches more -- the skill is bought with the risk and paid in coin.
        """
        contraband = ("tobacco", "cigar", "beer", "liqueur", "mezcal",
                      "dried_mushroom", "red_mushroom", "agave", "wheat_wort",
                      "berry_wort", "agave_wort")
        units = sum(inventory.count_of(i) for i in contraband)
        if units <= 0:
            toast("%s looks you over and waves you through" % npc.name)
            return
        skill = max(0.0, min(10.0, float(getattr(player, "smuggling", 0.0))))
        found = min(1.0, units / 100.0) * (1.0 - 0.09 * skill)
        if random.random() < found:
            toast("%s finds it. %d against the wall." % (npc.name, units))
            commit_crime()
            return
        player.smuggling = min(10.0, skill + 0.06 + units * 0.001)
        toast("Searched clean   (smuggling %.1f)" % player.smuggling)

    def open_trade(npc) -> None:
        nonlocal trade_open, trade_menu
        try:
            npc = make_tradeable(npc)
        except Exception:
            toast("He wants nothing to do with you")
            return
        if getattr(npc, "is_witness", lambda _n: False)(village_mod.PLAYER_ID):
            # UNDER NO CIRCUMSTANCES. He knows exactly what you are, and no
            # amount of time or coin changes it.
            toast("%s wants nothing to do with you" % npc.name)
            return
        trade_menu = TradeMenu(inventory, npc, player)
        trade_open = True
        pygame.mouse.set_visible(True)

    def nearest_hostile(npc):
        """WHAT THIS MAN CAN SEE TO FIGHT, and his own business.

        The town used to decide this for every citizen at once and hand the
        same answer to all of them -- which is how a village could pick a
        threat it could not see, and why an off-screen town needed a special
        case to stop it hunting the player from two hundred kilometres away.
        A man with eyes uses them.
        """
        reach = 900.0
        best, bd = None, reach * reach
        if not player.dead:
            d = (player.x - npc.x) ** 2 + (player.y - npc.y) ** 2
            if d < bd:
                bd, best = d, player
        # NO SOLDIER MUSTERED ANYWHERE is the common case, and it costs one
        # truth test rather than a neighbourhood assembled to answer "nobody".
        if not soldier_grid.buckets:
            return best
        nat = getattr(npc, "nation", None)
        for e in soldier_grid.near(npc.x, npc.y, reach):
            if not e.alive or getattr(e, "nation", None) == nat:
                continue
            d = (e.x - npc.x) ** 2 + (e.y - npc.y) ** 2
            if d < bd:
                bd, best = d, e
        return best

    def commit_crime() -> None:
        """If any villager can see the player, the village turns hostile."""
        occluders = [house.sight_rect for village in visible_villages
                     for house in village.houses]
        occluders += [tree.trunk_rect
                      for tree in trees.near(player.x, player.y, 560.0)
                      if not tree.felled]
        for village in visible_villages:
            for npc in village.npcs:
                if not npc.alive:
                    continue
                if math.hypot(npc.x - player.x, npc.y - player.y) > 540.0:
                    continue
                if any(segment_rect_hit(npc.x, npc.y, player.x, player.y, rect)
                       for rect in occluders):
                    continue
                village.provoke()
                if player.nation == village.nation:      # crime against your own
                    banish(village.nation)
                break

    def player_hunted() -> bool:
        """A guard is actively hunting the player right now."""
        for village in visible_villages:
            for g in getattr(village, "guards", ()) or ():
                if (getattr(g, "hostile", False) and getattr(g, "aware", False)
                        and g.alive):
                    return True
        return False

    def tile_is_mine(tx: int, ty: int) -> bool:
        """True for land inside the player's own fenced homestead: a closed
        rectangle of his fences with one of his houses inside. Farming there
        is not trespass -- unless he is already being hunted.

        AND HIS OWN FIELD FIRST, before any of that: the one the town gave him
        with his backstory. Without it a farmer's very first harvest was a
        crime and the whole town turned on him.
        """
        _p = getattr(player, "farm_plot", None)
        _town = getattr(player, "settled_at", None)
        if _p is not None and _town is not None:
            try:
                _ctx, _cty, _k = _town.farm_plots[_p]
                if (_ctx, _cty) == (tx, ty):
                    return True
            except Exception:
                pass
        if not built_houses or not built_fences:
            return False
        if player_hunted():
            return False
        x = tx * TILE + TILE / 2.0
        y = ty * TILE + TILE / 2.0
        for rect in fence.homesteads(built_fences, built_houses):
            if rect.collidepoint(x, y):
                return True
        return False

    def settle_reload() -> None:
        """A finished reload pulls rounds from the ammo you are carrying."""
        if not player.reload_done:
            return
        player.reload_done = False
        kind = player.reload_kind
        if not kind:
            return
        need = guns.MAG[kind] - player.mags.get(kind, 0)
        take = min(need, inventory.count_of("ammo"))
        if take > 0:
            inventory.consume("ammo", take)
            player.mags[kind] = player.mags.get(kind, 0) + take
            toast(f"Loaded {player.mags[kind]}/{guns.MAG[kind]}")

    def banish(nation) -> None:
        if player.nation != nation:
            return
        player.nation = None
        for old in list(player.squad):
            if old in enemies:
                enemies.remove(old)
        player.squad = []
        toast(f"Banished from {nation_name(nation)}!   They will shoot on sight")

    # -- item actions -------------------------------------------------------
    def fire() -> None:
        stack = inventory.selected_stack()
        if stack is None or stack.defn.id not in (guns.RIFLE, guns.SHOTGUN):
            return
        kind = stack.defn.id
        if player.reloading > 0.0 or player.gun_cd > 0.0:
            return
        if player.mags.get(kind, 0) <= 0:
            toast("Empty \u2014 press R to reload")
            return
        player.mags[kind] -= 1
        player.gun_cd = guns.FIRE_CD[kind]
        fx, fy = player.facing
        px, py = -fy, fx
        muzzle_x = player.x + fx * 30.0 + px * 7.0
        muzzle_y = player.y + fy * 30.0 + py * 7.0
        mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
        wmouse_x, wmouse_y = mouse_x / ZOOM, mouse_y / ZOOM  # world space
        distance = math.hypot((cam_x + wmouse_x) - muzzle_x,
                              (cam_y + wmouse_y) - muzzle_y)
        spread = skills.shot_spread()
        for _ in range(guns.PELLETS[kind]):
            extra = 0.0 if kind == guns.RIFLE else 0.11   # shotgun scatters
            combat.fire(muzzle_x, muzzle_y, player.facing_angle, distance, shooter=player,
                        owner="player", damage=guns.DAMAGE[kind], team="player",
                        spread=spread + extra)
        skills.gain_shooting()

    def use_first_aid() -> None:
        if player.health >= player.max_health:
            toast("Already at full health")
            return
        if not inventory.consume("first_aid", 1):
            toast("No first-aid kits left")
            return
        player.health = min(player.max_health, player.health + 50)
        toast("Patched yourself up")

    def use_axe() -> None:
        nonlocal kills
        if player.dead or not player.can_swing():
            return
        player.start_swing()
        skills.gain_axe()
        # BARE HANDS. The same swing and the same skill whether or not the axe
        # is in the pack -- a fist simply is not an axe. See
        # skills.UNARMED_WEAKNESS: he hits for a quarter, and can still fight.
        # ...AND IN THE RING EVERYBODY IS UNARMED, THE PLAYER INCLUDED. The
        # Test of Strengths is fought with bare hands by the King's own rule,
        # and a man who brought an axe to it would be breaking that rule and
        # killing his rivals into the bargain.
        _ring = getattr(player, "duel_tournament", None) is not None
        _armed = inventory.count_of("axe") > 0 and not _ring
        melee = ((MELEE_DAMAGE if _armed
                  else MELEE_DAMAGE / skills.UNARMED_WEAKNESS)
                 * skills.axe_damage_scale())
        angle = player.facing_angle
        combat.spawn_swing(player.x, player.y, angle)

        def in_arc(tx, ty, extra=0.0):
            dx, dy = tx - player.x, ty - player.y
            if math.hypot(dx, dy) > AXE_REACH + extra:
                return False
            delta = abs(((math.atan2(dy, dx) - angle + math.pi) % (2.0 * math.pi)) - math.pi)
            return delta <= AXE_ARC

        for enemy in enemies:
            if enemy.alive and in_arc(enemy.x, enemy.y, enemy.radius):
                enemy.take_damage(melee)
                blood.spawn(enemy.x, enemy.y, 8, 14.0)
                if (player.nation is not None
                        and getattr(enemy, "nation", None) == player.nation):
                    banish(player.nation)
        for rabbit in rabbits:
            if rabbit.alive and in_arc(rabbit.x, rabbit.y, rabbit.radius):
                died = rabbit.take_damage(melee)
                blood.spawn(rabbit.x, rabbit.y, 8, 12.0)
                if died:
                    amount = random.randint(1, 2)
                    inventory.add("raw_meat", amount)
                    toast(f"Caught a rabbit   +{amount} raw meat")
        for village in visible_villages:
            for npc in village.npcs:
                if npc.alive and in_arc(npc.x, npc.y, npc.radius):
                    died = npc.take_damage(melee)
                    blood.spawn(npc.x, npc.y, 18 if died else 8, 22.0 if died else 14.0)
                    # A CONTEST IS NOT A CRIME. Two men in the ring at the
                    # capital are fighting by the realm's OWN law, in front of
                    # the whole town, for the crown -- and before this the crowd
                    # would turn hostile and the player would be banished from
                    # his own nation for trading a blow with the man he was
                    # DRAWN AGAINST. Nobody in that square sees an assault;
                    # they see the Test of Strengths, which is the point of it.
                    if (getattr(player, "duel_tournament", None) is not None
                            and getattr(npc, "duel_tournament", None)
                            is player.duel_tournament):
                        continue
                    # SELF-DEFENCE IS NOT A MURDER. A man who came at you with
                    # an axe and lost is not a crime, and his neighbours know
                    # it -- so nothing here counts against you.
                    if (npc.village is not None
                            and not village_mod.self_defence(npc)):
                        npc.village.provoke()
                        if died:
                            # HE SHOUTED BEFORE HE DIED. The village is told,
                            # and the refugees and traders carry it on -- but
                            # only the men who SAW it will never forget.
                            npc.village.learn_killers(
                                (village_mod.PLAYER_ID,), now)
                            _see_murder(npc)
                    if player.nation is not None and npc.nation == player.nation:
                        banish(player.nation)
                    if died:
                        kills += 1

        struck = None
        nearest = 1e9
        for tree in trees.near(player.x, player.y, AXE_REACH + 30.0):
            if tree.felled:
                continue
            rect = tree.trunk_rect
            cx = min(max(player.x, rect.left), rect.right)
            cy = min(max(player.y, rect.top), rect.bottom)
            distance = math.hypot(player.x - cx, player.y - cy)
            if distance > AXE_REACH or not in_arc(tree.x, tree.y, 26.0):
                continue
            if distance < nearest:
                nearest = distance
                struck = tree
        if struck is not None:
            struck.strikes += 1
            combat.spawn_impact(struck.x, struck.y, (120, 90, 50))
            if struck.strikes >= AXE_STRIKES:
                trees.fell(struck, now)
                amount = random.randint(10, 30)
                inventory.add("wood", amount)
                pay_share("wood", amount)
                combat.spawn_impact(struck.x, struck.y - 20, (86, 140, 64))
                toast(f"Felled a tree   +{amount} wood")
            else:
                toast(f"Chopping…  {struck.strikes}/{AXE_STRIKES}")

        # Chop down a fence or gate you built yourself.
        for lst in (built_fences, built_gates):
            hit = None
            best = 1e9
            for rect in lst:
                cx = min(max(player.x, rect.left), rect.right)
                cy = min(max(player.y, rect.top), rect.bottom)
                d = math.hypot(player.x - cx, player.y - cy)
                if d <= AXE_REACH and d < best:
                    best, hit = d, rect
            if hit is not None:
                lst.remove(hit)
                combat.spawn_impact(hit.centerx, hit.centery, (140, 100, 56))
                toast("Chopped down your fence")
                mark_dirty()
                return

        # A SETTLEMENT'S FENCE IS NOT WOOD, IT IS LAW. It cannot be cut, by an
        # axe or anything else: the wall is not what keeps people out, the
        # SEARCH at the gate is, and a wall you can hack a hole in would make
        # the gate decorative. The player's own fences are still his to cut.

        # Break a villager's door open with the axe.
        for village in visible_villages:
            for vhouse in village.houses:
                if getattr(vhouse, "door_broken", False):
                    continue
                fx, fy = vhouse.facing
                door_x = vhouse.x + fx * (vhouse.h / 2.0 + 4.0)
                door_y = vhouse.y + fy * (vhouse.h / 2.0 + 4.0)
                if not in_arc(door_x, door_y, 22.0):
                    continue
                vhouse.enterable = True
                vhouse.interior = Interior(random.randint(0, 2 ** 31),
                                           tuple(vhouse.facing))
                fill_loot(vhouse.interior.chest)
                vhouse.break_door()
                commit_crime()
                combat.spawn_impact(door_x, door_y, (120, 78, 44))
                toast("Broke the door open")
                return

    def use_pickaxe() -> None:
        if player.dead or not player.can_swing():
            return
        player.start_swing()
        angle = player.facing_angle
        combat.spawn_swing(player.x, player.y, angle)

        def in_arc(tx, ty, extra=0.0):
            dx, dy = tx - player.x, ty - player.y
            if math.hypot(dx, dy) > AXE_REACH + extra:
                return False
            delta = abs(((math.atan2(dy, dx) - angle + math.pi) % (2.0 * math.pi)) - math.pi)
            return delta <= AXE_ARC

        struck = None
        nearest = 1e9
        for chunk in ore_field.near(player.x, player.y, AXE_REACH + 30.0):
            cx = min(max(player.x, chunk.rect.left), chunk.rect.right)
            cy = min(max(player.y, chunk.rect.top), chunk.rect.bottom)
            distance = math.hypot(player.x - cx, player.y - cy)
            if distance > AXE_REACH or not in_arc(chunk.x, chunk.y, 20.0):
                continue
            if distance < nearest:
                nearest = distance
                struck = chunk
        if struck is None:
            toast("Nothing to mine here")
            return
        struck.strikes += 1
        combat.spawn_impact(struck.x, struck.y, (150, 150, 160))
        if struck.strikes >= ore.STRIKES:
            struck.mined = True
            ore_field.mined.add(struck.cell)
            amount = random.randint(ore.YIELD_LO, ore.YIELD_HI)
            inventory.add("iron", amount)
            pay_share("iron", amount)
            mark_dirty()
            toast(f"Mined iron   +{amount}")
        else:
            toast(f"Mining\u2026  {struck.strikes}/{ore.STRIKES}")

    EAT_RESTORE = 35.0      # any food fills the same belly, as it does for
                            # every villager: one item, one meal.

    def on_click() -> None:
        nonlocal confirm_open
        if player.dead:
            return
        stack = inventory.selected_stack()
        item_id = stack.defn.id if stack else None
        # ANYTHING THE VILLAGERS CALL FOOD, THE PLAYER CAN EAT. This was a
        # list of three hand-written cases -- and berries and cactus fruit were
        # not among them, so a man could starve with a pocket full of them
        # while every villager in the valley ate the same things for supper.
        if item_id in economy.FOOD:
            if inventory.consume(item_id, 1):
                player.eat(EAT_RESTORE)
                toast("Ate some %s" % items.get(item_id).name.lower())
            else:
                toast("None of that left")
            return
        if item_id == "cooked_meat":
            if inventory.consume("cooked_meat", 1):
                player.eat(player.max_hunger)
                toast("Ate cooked meat   -   full up")
            else:
                toast("No cooked meat")
            return
        if item_id == "raw_meat":
            if inside_house is not None and near_fireplace():
                if inventory.consume("raw_meat", 1):
                    inventory.add("cooked_meat", 1)
                    toast("Cooked the meat over the fire")
                else:
                    toast("No raw meat")
            else:
                toast("Cook raw meat at a fireplace")
            return
        if item_id == "compass":
            if compass_state.mode == "village":
                toast(compass.village_report(player.x, player.y, world.seed))
            elif compass_state.mode == "home" and compass_state.home is not None:
                toast(compass.home_report(player.x, player.y, compass_state.home))
            else:
                toast("Press F to choose what to find")
            return
        if inside_house is not None:
            _mx, _my = pygame.mouse.get_pos()
            # the room is drawn at the world's zoom, so the click is brought
            # into that same frame before it is compared with anything in it
            _bx, _by = cam_x + _mx / ZOOM, cam_y + _my / ZOOM
            for _kind, _rect in inside_house.interior.furniture:
                if _kind == "bed" and _rect.inflate(18, 18).collidepoint(_bx, _by):
                    try_sleep()
                    return
            return
        if item_id in ("rifle", "shotgun"):
            fire()
            return
        if item_id == "axe":
            use_axe()
            return
        if item_id == "pickaxe":
            use_pickaxe()
            return

        mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
        wmouse_x, wmouse_y = mouse_x / ZOOM, mouse_y / ZOOM  # world space
        wx, wy = cam_x + wmouse_x, cam_y + wmouse_y   # the world mouse

        # Clicking a villager while not wielding a weapon opens trade.
        if math.hypot(wx - player.x, wy - player.y) <= REACH + 24.0:
            _folk = [n for v in visible_villages for n in v.npcs]
            # AND THE SOLDIERS. They are not in a village's list -- they are
            # the nation's, and they march -- so they were the one kind of man
            # in the world you could not do business with.
            # THE SOLDIERS, NOT THE WOLVES. An enemy list holds both, and a
            # wolf was being offered a trade menu: clicking one went into the
            # economy asking what a wolf WANTS and threw AttributeError, taking
            # the game down. Only a man with a purse is a customer.
            _folk += [e for e in enemies
                      if getattr(e, "kind", "") == "soldier"
                      and getattr(e, "alive", True)
                      and not getattr(e, "attacked", False)]
            for npc in _folk:
                    if getattr(npc, "alive", True) and math.hypot(npc.x - wx, npc.y - wy) < 22.0:
                        if (getattr(npc, "is_commander", False)
                                and not getattr(npc, "attacked", False)):
                            confirm.pending = npc
                            if player.nation == npc.nation:
                                confirm.mode = "leave"
                                confirm.open(f"Leave the {npc.village.name} army?")
                            else:
                                confirm.mode = "join"
                                confirm.open(f"Join the {npc.village.name} army?")
                            confirm_open = True
                            pygame.mouse.set_visible(True)
                            return
                        if getattr(npc, "attacked", False):
                            toast(f"{npc.name} won't trade with you")
                            return
                        # A GUARD AT A GATE SEARCHES; HE DOES NOT TRADE.
                        if getattr(npc, "gate_index", None) is not None:
                            guard_search(npc)
                            return
                        open_trade(npc)
                        return

        if item_id == "first_aid":
            use_first_aid()
            return

        if math.hypot(wx - player.x, wy - player.y) > REACH:
            toast("Too far away")
            return
        tx = int(math.floor(wx / TILE))
        ty = int(math.floor(wy / TILE))

        plot = world.plot_at(tx, ty)
        if plot is not None and plot.kind in crop.LEAF_KINDS:
            grade = skills.tobacco_grade()
            if farm.harvest(world, inventory, plot, now, toast, grade,
                            tx=tx, ty=ty, share=pay_share):
                # The same rate the farmers get. At the old default (0.12) the
                # player reached skill 8 in ~67 harvests -- SSS tobacco by day
                # two, against three weeks for the men who do it for a living.
                skills.gain_farming(0.02)
                if (tx, ty) in village_plots and not tile_is_mine(tx, ty):
                    commit_crime()
            return
        if plot is not None and plot.kind in crop.FOOD_KINDS:
            if farm.harvest(world, inventory, plot, now, toast, tx=tx, ty=ty,
                            share=pay_share):
                if (tx, ty) in village_plots and not tile_is_mine(tx, ty):
                    commit_crime()
            return

        wild = wildcrop.at(world, tx, ty, visible_villages)
        if wild is not None:
            wildcrop.harvest(world, tx, ty, wild[0], wild[1], inventory, toast,
                             share=pay_share)
            skills.gain_farming(0.02)      # wild or sown, the hand learns alike
            return

        if item_id == "shovel":
            farm.dig(world, ground, tx, ty, toast)
        elif item_id == "watering_can":
            farm.water(world, ground, tx, ty, toast)
        elif item_id in crop.SEED_CROP:
            farm.plant(world, ground, inventory, tx, ty, now, toast, item_id)

    # -- building placement -------------------------------------------------
    def placement_pos():
        # THE INTERIOR IS DRAWN AT THE SAME ZOOM AS THE OUTDOORS, so this is
        # the world mouse everywhere. Un-zooming it indoors put every ghost a
        # third of a screen from the cursor, so can_place() tested the wrong
        # square of floor and there was never room for anything.
        mx, my = wmouse_x, wmouse_y
        return (round((cam_x + mx) / 8.0) * 8.0,
                round((cam_y + my) / 8.0) * 8.0)

    def placement_box(x, y):
        if placing in ("fence", "gate"):
            w, h = (60, 16) if placing == "gate" else (140, 16)
            if not fence_horizontal:
                w, h = h, w
            rect = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
            return (0.0, -1.0), rect, rect.inflate(10, 10)
        if placing == "workshop":
            rect = pygame.Rect(int(x - WORKSHOP_W / 2), int(y - WORKSHOP_H / 2),
                               WORKSHOP_W, WORKSHOP_H)
            return (0.0, -1.0), rect, rect.inflate(16, 16)
        # (The brew table and the barrel are measured further down, with the
        # other furniture. A block of try_place's code once sat here by
        # mistake -- it assigned `placing`, which made `placing` a LOCAL of
        # this function, so the first read of it raised UnboundLocalError and
        # the game died the instant the player chose anything to build.)
        if placing == "lab_table":
            rect = pygame.Rect(int(x - LAB_W / 2), int(y - LAB_H / 2), LAB_W, LAB_H)
            return (0.0, -1.0), rect, rect.inflate(16, 16)
        if placing == "brew_table":
            rect = pygame.Rect(int(x - BREW_W / 2), int(y - BREW_H / 2), BREW_W, BREW_H)
            return (0.0, -1.0), rect, rect.inflate(16, 16)
        if placing == "barrel":
            rect = pygame.Rect(int(x - BARREL_W / 2), int(y - BARREL_H / 2),
                               BARREL_W, BARREL_H)
            return (0.0, -1.0), rect, rect.inflate(12, 12)
        dx, dy = player.x - x, player.y - y
        if abs(dx) >= abs(dy):
            facing = (1.0 if dx > 0 else -1.0, 0.0)
        else:
            facing = (0.0, 1.0 if dy > 0 else -1.0)
        if facing[0] != 0.0:
            half_x, half_y = BUILD_H / 2.0, BUILD_W / 2.0
        else:
            half_x, half_y = BUILD_W / 2.0, BUILD_H / 2.0
        rect = pygame.Rect(x - half_x, y - half_y, half_x * 2, half_y * 2)
        return facing, rect, rect.inflate(28, 28)

    def can_place(rect, sight) -> bool:
        if inside_house is not None:
            return inside_house.interior.can_place_workshop(rect)
        if sight.collidepoint(player.x, player.y):
            return False
        for house in built_houses:
            if sight.colliderect(house.sight_rect):
                return False
        for village in visible_villages:
            for house in village.houses:
                if sight.colliderect(house.sight_rect):
                    return False
        for tree in trees.near(rect.centerx, rect.centery, 170.0):
            if not tree.felled and rect.inflate(16, 16).colliderect(tree.trunk_rect):
                return False
        return True

    def try_place() -> None:
        nonlocal placing
        x, y = placement_pos()
        facing, rect, sight = placement_box(x, y)
        if placing in ("fence", "gate"):
            if not can_place(rect, sight):
                toast("Can't build there")
                return
            cost = 30 if placing == "gate" else 10
            name = "Gate" if placing == "gate" else "Fence"
            if not test_mode:
                if inventory.count_of("wood") < cost:
                    toast(f"Need {cost} wood")
                    placing = None
                    pygame.mouse.set_visible(False)
                    return
                inventory.consume("wood", cost)
            (built_gates if placing == "gate" else built_fences).append(rect)
            mark_dirty()
            toast(f"{name} built" if test_mode else f"{name} built   -{cost} wood")
            placing = None
            pygame.mouse.set_visible(False)
            return
        if placing in ("brew_table", "barrel"):
            name = "Brewing table" if placing == "brew_table" else "Barrel"
            if inside_house is None:
                toast("%s can only be built inside a house" % name)
            elif not (inside_house.interior.can_place_brew(rect)
                      if placing == "brew_table"
                      else inside_house.interior.can_place_barrel(rect)):
                toast("No clear floor space here")
                return
            elif not test_mode and inventory.count_of("wood") < build_cost(placing):
                toast("Need %d wood" % build_cost(placing))
            else:
                if not test_mode:
                    inventory.consume("wood", build_cost(placing))
                if placing == "brew_table":
                    inside_house.interior.place_brew(x, y)
                else:
                    inside_house.interior.place_barrel(x, y)
                mark_dirty()
                toast("%s built" % name if test_mode
                      else "%s built   -%d wood" % (name, build_cost(placing)))
            placing = None
            pygame.mouse.set_visible(False)
            return
        if placing == "lab_table":
            if inside_house is None:
                toast("A lab table can only be built inside a house")
            elif not inside_house.interior.can_place_lab(rect):
                toast("No clear floor space here")
                return
            elif not test_mode and inventory.count_of("wood") < build_cost("lab_table"):
                toast("Need %d wood" % build_cost("lab_table"))
            else:
                if not test_mode:
                    inventory.consume("wood", build_cost("lab_table"))
                inside_house.interior.place_lab(x, y)
                mark_dirty()
                toast("Lab table built" if test_mode
                      else "Lab table built   -%d wood" % build_cost("lab_table"))
            placing = None
            pygame.mouse.set_visible(False)
            return
        if placing == "workshop":
            if inside_house is None:
                toast("Workshops can only be built inside a house")
            elif not inside_house.interior.can_place_workshop(rect):
                toast("No clear floor space here")
                return
            elif not test_mode and inventory.count_of("wood") < build_cost("workshop"):
                toast(f"Need {build_cost('workshop')} wood")
            else:
                if not test_mode:
                    inventory.consume("wood", build_cost("workshop"))
                inside_house.interior.place_workshop(x, y)
                mark_dirty()
                toast("Workshop built" if test_mode
                      else f"Workshop built   -{build_cost('workshop')} wood")
            placing = None
            pygame.mouse.set_visible(False)
            return
        if not can_place(rect, sight):
            toast("Can't build there")
            return
        if not test_mode:
            if inventory.count_of("wood") < BUILD_COST:
                toast(f"Need {BUILD_COST} wood")
                placing = None
                pygame.mouse.set_visible(False)
                return
            inventory.consume("wood", BUILD_COST)
        seed = random.randint(0, 2 ** 31)
        house = House(x, y, BUILD_W, BUILD_H, random.choice(ROOFS), facing, seed)
        house.build_seed = seed
        house.interior_seed = random.randint(0, 2 ** 31)
        house.interior = Interior(house.interior_seed, tuple(house.facing))
        house.enterable = True
        built_houses.append(house)
        mark_dirty()
        toast(f"House built   -{BUILD_COST} wood")
        placing = None
        pygame.mouse.set_visible(False)

    def draw_placing() -> None:
        if placing is None:
            return
        _amx, _amy = wmouse_x, wmouse_y      # the world mouse, indoors too
        aim_dx = (cam_x + _amx) - player.x
        aim_dy = (cam_y + _amy) - player.y
        length = math.hypot(aim_dx, aim_dy) or 1.0
        player.facing = (aim_dx / length, aim_dy / length)
        px_, py_ = placement_pos()
        _facing, box, sight = placement_box(px_, py_)
        ok = can_place(box, sight)
        colour = (126, 224, 148) if ok else (226, 96, 84)
        rr = pygame.Rect(box.x - cam_x, box.y - cam_y, box.w, box.h)
        sr = pygame.Rect(sight.x - cam_x, sight.y - cam_y, sight.w, sight.h)
        fill = pygame.Surface(rr.size, pygame.SRCALPHA)
        fill.fill((colour[0], colour[1], colour[2], 48))
        screen.blit(fill, rr.topleft)
        pygame.draw.rect(screen, colour, sr, 2)
        pygame.draw.rect(screen, colour, rr, 2)
        hint_text = "Click to place   ·   right-click to cancel"
        if placing in ("fence", "gate"):
            hint_text = "Click to place   ·   R to rotate   ·   right-click to cancel"
        hint = font.render(hint_text, True, (236, 236, 240))
        screen.blit(hint, (vw // 2 - hint.get_width() // 2, int(vh * 0.82)))

    # -- house interiors ----------------------------------------------------
    def render_backdrop(house):
        """The outdoors around the house, frozen into a surface for windows."""
        surface = pygame.Surface((vw, vh))
        ex = house.x - vw / 2.0
        ey = house.y - vh / 2.0
        ground.update(3, ex, ey, vw, vh)
        static_layer.draw(surface, ex, ey, vw, vh)
        for tree in trees.visible(ex, ey, vw, vh):
            tree.draw(surface, ex, ey, trees.stump())
        for village in villages.visible(ex, ey, vw, vh):
            for village_house in village.houses:
                village_house.draw(surface, ex, ey)
            for npc in village.npcs:
                npc.draw(surface, ex, ey, False)
        for other in built_houses:
            if other is not house:
                other.draw(surface, ex, ey)
        return surface

    def enter_house(house) -> None:
        nonlocal inside_house, backdrop, door_cooldown, cam_x, cam_y
        interior = getattr(house, "interior", None)
        if interior is None:
            return
        inside_house = house
        player.x, player.y = interior.spawn
        player.bleed = 0.0
        door_cooldown = 0.7
        combat.bullets.clear()
        if interior.W <= vw:
            cam_x = interior.W / 2.0 - vw / 2.0
        else:
            cam_x = min(max(player.x - vw / 2.0, 0.0), interior.W - vw)
        if interior.H <= vh:
            cam_y = interior.H / 2.0 - vh / 2.0
        else:
            cam_y = min(max(player.y - vh / 2.0, 0.0), interior.H - vh)
        night = night_factor() > 0.38
        floor = pygame.Rect(interior.T, interior.T,
                            interior.W - 2 * interior.T, interior.H - 2 * interior.T)
        for npc in getattr(house, "occupants", ()):   # residents, home at night
            if not npc.alive or not night:
                continue                    # by day they are out in the village
            npc.in_interior = True
            npc.asleep = False
            npc._saved = (npc.x, npc.y)
            npc.x = interior.W * 0.5 + random.uniform(-130.0, 130.0)
            npc.y = interior.H * 0.5 + random.uniform(-80.0, 80.0)
            npc.facing = (0.0, -1.0)
            npc._interior_rect = floor
            npc._interior_colliders = interior.colliders
            npc.target = (npc.x, npc.y)
            npc.pause = 0.0
        toast("Inside the house")

    def exit_house() -> None:
        nonlocal inside_house, door_cooldown
        house = inside_house
        if house is None:
            return
        night = night_factor() > 0.38
        for npc in getattr(house, "occupants", ()):
            if not npc.in_interior:
                continue
            npc.in_interior = False
            if npc._saved is not None:
                npc.x, npc.y = npc._saved
                npc._saved = None
            npc.asleep = night          # back to bed at night, out by day
            npc._dir = None
        fx, fy = house.facing
        player.x = house.x + fx * (house.h / 2.0 + 30.0)
        player.y = house.y + fy * (house.h / 2.0 + 30.0)
        inside_house = None
        door_cooldown = 0.7

    def draw_exterior(cx, cy, show_names: bool = False, target=None) -> None:
        target = target if target is not None else screen
        static_layer.draw(target, cx, cy, vw, vh)
        blood.draw(target, cx, cy, vw, vh)
        world_villages = villages.visible(cx, cy, vw, vh,
                                          extra=hub_world.hubs)
        world_trees = trees.visible(cx, cy, vw, vh)
        view = pygame.Rect(cx - 150, cy - 150, vw + 300, vh + 300)
        for village in world_villages:
            fence.draw(target, cx, cy, village, view)
        for rect in built_fences:
            if view.colliderect(rect):
                fence.draw_segment(target, cx, cy, rect)
        for rect in built_gates:
            if view.colliderect(rect):
                fence.draw_gate(target, cx, cy, rect)
        items = []
        for (x, y, planted_at, kind, biome) in crop.visible_plants(world, cx, cy,
                                                                   vw, vh):
            if not view.collidepoint(x, y):
                continue
            items.append((y, lambda x=x, y=y, p=planted_at, k=kind, b=biome:
                          crop.draw_crop(target, x, y, k, now - p, cx, cy, b)))
        _stump = trees.stump()
        for (x, y, kind, stage) in wildcrop.visible(world, world_villages,
                                                    cx, cy, vw, vh):
            if not view.collidepoint(x, y):
                continue
            age = (stage + 0.4) * crop.GROW_SECONDS / 4.0
            items.append((y, lambda x=x, y=y, e=age, k=kind:
                          crop.draw_crop(target, x, y, k, e, cx, cy, None)))
        for tree in world_trees:
            items.append((tree.y, lambda t=tree, s=_stump:
                          t.draw(target, cx, cy, s)))
        for chunk in ore_field.visible(cx, cy, vw, vh):
            if view.collidepoint(chunk.x, chunk.y):
                items.append((chunk.y,
                              lambda c=chunk: ore_field.draw(target, cx, cy, c)))
        for enemy in enemies:
            if view.collidepoint(enemy.x, enemy.y):
                items.append((enemy.y, lambda e=enemy: e.draw(target, cx, cy)))
        for rabbit in rabbits:
            if view.collidepoint(rabbit.x, rabbit.y):
                items.append((rabbit.y, lambda r=rabbit: r.draw(target, cx, cy)))
        # ...AND THE PLAYER'S OWN, drawn whether or not any village is in
        # sight. This block used to sit INSIDE the village loop, so a house
        # built out in the open was never drawn at all: solid, enterable, and
        # invisible.
        for house in built_houses:
            if not view.colliderect(house.sight_rect):
                continue
            items.append((house.base_y, lambda h=house: h.draw(target, cx, cy)))
        for village in world_villages:
            items.append((village.board.bottom,
                          lambda v=village: v.draw_board(target, cx, cy)))
            for wp in village.workplaces:
                if not view.colliderect(wp.sight_rect):
                    continue
                items.append((wp.base_y, lambda w=wp: w.draw(target, cx, cy)))
            for house in village.houses:
                if not view.colliderect(house.sight_rect):
                    continue
                items.append((house.base_y, lambda h=house: h.draw(target, cx, cy)))
            for npc in village.npcs:
                if npc.asleep or npc.in_interior:
                    continue
                if not view.collidepoint(npc.x, npc.y):
                    continue
                near = show_names and ((npc.x - player.x) ** 2
                                       + (npc.y - player.y) ** 2) < 260.0 ** 2
                items.append((npc.y, lambda n=npc, s=near:
                              n.draw(target, cx, cy, s)))
        items.sort(key=lambda item: item[0])
        for _y, draw in items:
            draw()


    # -- THE NEWS, AS A MAN HEARS IT ----------------------------------------
    _chat: list = []          # [text, seconds of life left] -- one shown at a time
    _news_lab = [None, None]  # the last bubble text and its rendered surface
    _hear_at = [0.0]          # hear_news runs FOUR TIMES A SECOND, not sixty
    _heard: set = set()       # (village, army, nation): what he already knows

    def hear_news() -> None:
        """THE PLAYER LEARNS THE WAR THE WAY EVERYBODY ELSE DOES: BY BEING TOLD.

        war.tell makes knowledge move man to man and never by magic, so a
        player hears a thing when he is standing near somebody who knows it.
        And NOT from a town already at his throat -- a village that has called
        him a killer does not stop in the street to pass the time of day.
        """
        # ONE AT A TIME, AND NO BACKLOG. Without this the player could walk
        # through a village and stack up four men's worth of war news, then be
        # told it one after another for half a minute -- a queue of speeches,
        # not a conversation. While somebody is talking, nobody else is.
        if player.dead or _chat:
            return
        # NOT EVERY FRAME. This walks every villager of every village on screen
        # and takes a hypot to each -- at 60 fps that is a scan of the square
        # sixty times a second to answer a question whose answer cannot change
        # that fast. Four times a second hears the same conversation.
        _t = time.perf_counter()
        if _t < _hear_at[0]:
            return
        _hear_at[0] = _t + 0.25
        for v in visible_villages:
            if getattr(v, "hostile", False):
                continue
            for n in v.npcs:
                if not n.alive or n.asleep or n.in_interior:
                    continue
                # NOT THE COLUMN. Every man in an army is handed the SAME
                # capture in the same words (see war.note_capture, which gives
                # it to every soldier AND every townsman of the place that
                # fell), so a column marching past the player would announce
                # the fall of one village in a dozen voices at once, one after
                # another, for as long as it took to walk by.
                #
                # A marching army is not a man telling you the news. The news
                # is CARRIED -- by traders, on the road, a village at a time --
                # and that is where a player should hear it. The ranks keep it
                # among themselves; they are busy, and they are not talking to
                # him.
                if (getattr(n, "is_soldier", False)
                        or getattr(n, "levied", False)
                        or getattr(n, "on_duty", False)
                        or getattr(n, "is_commander", False)
                        or getattr(n, "weapon", None) is not None):
                    continue
                if math.hypot(n.x - player.x, n.y - player.y) > 250.0:
                    continue
                # ONLY WHAT HE HIMSELF KNOWS, AND ONLY WHAT HE STILL KNOWS.
                # His own list -- never the town's, never a crown's -- and not
                # the parts of it he has stopped caring about: war.prune_news
                # runs inside war.tell and not on every tick, so a man can be
                # carrying a fifteen-day-old notice long after it has died
                # (WAR_NEWS_LIFETIME). He does not repeat what he has himself
                # forgotten.
                for e in list(getattr(n, "news", ()) or ()):
                    if len(e) < 5:
                        continue
                    if now - e[0] >= war.WAR_NEWS_LIFETIME:
                        continue
                    key = (e[1], int(e[2]), e[4])
                    if key in _heard:
                        continue
                    _heard.add(key)
                    _chat.append(["The nation of %s seized %s"
                                  % (nation_name(e[4]), e[1]), 7.0, n])
                    return            # ONE AT A TIME; the rest wait their turn

    def tick_news(dt: float) -> None:
        if _chat:
            _chat[0][1] -= dt
            if _chat[0][1] <= 0.0:
                _chat.pop(0)

    def draw_news(surf, cam_x: float, cam_y: float, w: int, h: int) -> None:
        """A SPEECH BUBBLE, OUT OF THE SPEAKER'S OWN MOUTH.

        Not a chat log in the corner: one man is telling you one thing, and it
        comes out of HIM. The bubble hangs over the head of the man saying it
        and fades away on its own, so the news always has a face and a place --
        you can see who told you.

        There is no "Name:" in it. In a village you can see the man.
        """
        if not _chat:
            return
        text, life, who = _chat[0]
        if who is None or not getattr(who, "alive", False):
            _chat.pop(0)
            return
        # HE HAS TO BE ABLE TO HEAR HIM. Walk out of earshot and the bubble
        # goes with you -- a man does not keep talking to a back. The words are
        # not lost, they simply are not shown until you are near again.
        if math.hypot(who.x - player.x, who.y - player.y) > 250.0:
            return
        fade = min(1.0, life / 1.6)
        # THE TEXT IS RENDERED ONCE, NOT ONCE A FRAME. It does not change while
        # the bubble is up, and laying out a string is the expensive half of
        # drawing one -- re-doing it sixty times a second for seven seconds to
        # produce the identical pixels is work for nothing. Only the alpha
        # moves, and that is cheap.
        lab = _news_lab[1]
        if lab is None or _news_lab[0] != text:
            lab = speech_font.render(text, True, (30, 26, 22))
            _news_lab[0], _news_lab[1] = text, lab
        pad = 5
        bw, bh = lab.get_width() + pad * 2, lab.get_height() + pad * 2
        # Above his head, in the small frame the world is drawn in.
        hx = int(who.x - cam_x)
        hy = int(who.y - cam_y) - 22
        bx = max(3, min(w - bw - 3, hx - bw // 2))
        by = max(3, hy - bh - 5)
        # THE BUBBLE: cream paper, dark ink, a tail onto the man's crown --
        # the same wood-and-parchment the boards and the toasts are made of.
        box = pygame.Surface((bw, bh + 6), pygame.SRCALPHA)
        pygame.draw.rect(box, (238, 231, 209, int(242 * fade)),
                         pygame.Rect(0, 0, bw, bh), border_radius=5)
        pygame.draw.rect(box, (150, 110, 62, int(238 * fade)),
                         pygame.Rect(0, 0, bw, bh), width=1, border_radius=5)
        tail = max(4, min(bw - 4, hx - bx))
        pygame.draw.polygon(box, (238, 231, 209, int(242 * fade)),
                            [(tail - 5, bh - 1), (tail + 5, bh - 1),
                             (tail, bh + 6)])
        pygame.draw.polygon(box, (150, 110, 62, int(238 * fade)),
                            [(tail - 5, bh - 1), (tail + 5, bh - 1),
                             (tail, bh + 6)], 1)
        surf.blit(box, (bx, by))
        lab.set_alpha(int(255 * fade))
        surf.blit(lab, (bx + pad, by + pad))

    def buy_vote(voter: Any) -> None:
        """THE PLAYER BUYS A VOTE: same price, same one-sale rule.

        The going rate is ELECTION_BRIBE and it is the same for him as for a
        mayor or a rich man -- there is one market and one price in it. A vote
        already sold is already sold, to whoever got there first, and it is
        whoever else wants it that loses.
        """
        if not getattr(voter, "alive", False):
            return
        if getattr(voter, "is_mayor", False) or getattr(voter, "is_king", False):
            toast("%s is standing himself" % voter.name)
            return
        if not economy.vote_buyable(voter, _wd):
            toast("%s has already sold his vote" % voter.name)
            return
        if inventory.count_of("coin") < economy.ELECTION_BRIBE:
            toast("Not enough coin   (%d needed)" % economy.ELECTION_BRIBE)
            return
        inventory.consume("coin", economy.ELECTION_BRIBE)
        voter.coins += economy.ELECTION_BRIBE
        voter.vote_sold = int(_wd)
        voter.vote_for = "player"
        toast("%s takes your coin and your side   (%d)"
              % (voter.name, economy.ELECTION_BRIBE))

    def nearest_voter():
        """A man in his own square, close enough to talk to, whose vote is
        still going. You cannot buy a vote across a field."""
        best = None
        bestd = REACH + 40.0
        for v in villages.visible(player.x - 320.0, player.y - 320.0, 640, 640):
            for n in v.npcs:
                if not n.alive or n.asleep or n.in_interior:
                    continue
                if getattr(n, "is_king", False):
                    continue
                d = math.hypot(n.x - player.x, n.y - player.y)
                if d < bestd:
                    bestd, best = d, n
        return best

    def pay_share(item: str, gained: int) -> int:
        """THE PLAYER PAYS WHAT EVERYBODY ELSE PAYS: A FIFTH, IN KIND.

        Taken out of the pack he has just filled, at the moment he fills it, to
        the village that gave him his post -- which is exactly what
        economy.take_fifth does to a villager's iron and what cut_wood does to
        a logger's timber. He never has to remember it and he can never be
        banished for forgetting, because there is nothing left to forget.

        No post and no village means nothing is owed: an unemployed man works
        for himself.
        """
        town = getattr(player, "settled_at", None)
        if town is None or gained <= 0 or not getattr(player, "job", None):
            return 0
        if not (item in economy.TAXED_OUTPUT or item == "wood"
                or item in economy.FOOD):
            return 0
        frac = getattr(player, "_tax_frac", 0.0) + gained * economy.HARVEST_TAX
        tax = int(frac)
        player._tax_frac = frac - tax
        if tax <= 0:
            return 0
        take = min(tax, int(inventory.count_of(item)))
        if take <= 0:
            return 0
        inventory.consume(item, take)
        economy.store_add(town, item, take)
        toast("The village's share   -%d %s" % (take, item))
        return take

    def near_board():
        for v in visible_villages:
            if math.hypot(player.x - v.board.centerx,
                          player.y - v.board.centery) < REACH + 26.0:
                return v
        return None

    def near_chest() -> bool:
        if inside_house is None:
            return False
        chest = inside_house.interior.chest_rect
        return math.hypot(player.x - chest.centerx,
                          player.y - chest.centery) < 56.0

    def near_brew() -> bool:
        if inside_house is None:
            return False
        return inside_house.interior.brew_near(player.x, player.y)

    def mash_at_table() -> None:
        """Mash what you carry into wort -- up to fifty of a kind."""
        for src, wort in economy.WORT.items():
            idx = next((i for i, st in enumerate(inventory.slots)
                        if st is not None and st.defn.id == src and st.count > 0), None)
            if idx is None:
                continue
            stack = inventory.slots[idx]
            batch = min(stack.count, economy.WORT_BATCH)
            q = stack.quality if stack.quality is not None else 0
            stack.count -= batch
            if stack.count <= 0:
                inventory.slots[idx] = None
            inventory.add(wort, batch, q)
            skills.gain_farming(0.02 * min(batch, 10))
            toast("Mashed %d into %s" % (batch, items.get(wort).name))
            return
        toast("Nothing to mash -- bring wheat, berries or agave")

    def use_barrel() -> None:
        """Fill the barrel with wort, or take what it has made."""
        barrel = inside_house.interior.barrel_near(player.x, player.y)
        if barrel is None:
            return
        if barrel["kind"]:
            if now < barrel["ready_at"]:
                toast("Still fermenting -- %.0f seconds to go"
                      % max(0.0, barrel["ready_at"] - now))
                return
            out = economy.BREW.get(barrel["kind"])
            count, given = barrel["count"], barrel["grade"]
            barrel["kind"], barrel["count"], barrel["ready_at"] = None, 0, 0.0
            barrel["grade"] = 0
            if out:
                hands = skills.leaf_grade(8)
                g = quality.clamp(int(round((hands + given) / 2.0)))
                inventory.add(out, count, g)
                skills.gain_farming(0.02 * min(count, 10))
                toast("%d %s  (%s)" % (count, items.get(out).name, quality.letter(g)))
            return
        for wort in economy.BREW:
            idx = next((i for i, st in enumerate(inventory.slots)
                        if st is not None and st.defn.id == wort and st.count > 0), None)
            if idx is None:
                continue
            stack = inventory.slots[idx]
            batch = min(stack.count, economy.WORT_BATCH)
            barrel["kind"] = wort
            barrel["count"] = batch
            barrel["grade"] = stack.quality if stack.quality is not None else 0
            barrel["ready_at"] = now + economy.BREW_SECONDS
            stack.count -= batch
            if stack.count <= 0:
                inventory.slots[idx] = None
            toast("Filled with %d %s -- five minutes"
                  % (batch, items.get(wort).name))
            return
        toast("Fill it with wort")

    def near_lab() -> bool:
        if inside_house is None:
            return False
        return inside_house.interior.lab_near(player.x, player.y)

    def craft_at_table() -> None:
        """Work the leaf you carry into cigars or dried mushrooms. The grade is
        the MIDPOINT of your hands and the leaf you were given -- good leaf in
        clumsy hands and poor leaf in a master's both make a middling article,
        so this trade has to be learnt just as farming does."""
        for leaf, out in economy.PROCESS.items():
            idx = next((i for i, st in enumerate(inventory.slots)
                        if st is not None and st.defn.id == leaf and st.count > 0), None)
            if idx is None:
                continue
            stack = inventory.slots[idx]
            given = stack.quality if stack.quality is not None else 0
            hands = skills.leaf_grade(8)
            g = quality.clamp(int(round((hands + given) / 2.0)))
            stack.count -= 1
            if stack.count <= 0:
                inventory.slots[idx] = None
            inventory.add(out, 1, g)
            skills.gain_farming(0.02)          # you learn at the bench too
            toast("Made a %s  (%s)" % (items.get(out).name, quality.letter(g)))
            return
        toast("No leaf to work")

    def near_workshop() -> bool:
        if inside_house is None:
            return False
        return inside_house.interior.workshop_near(player.x, player.y)

    def near_workplace():
        """Whichever village workplace the player is at, if any.

        The test is against the BUILDING, not its centre: a mine is 136 by 112,
        so a radius measured from the middle left a man standing at the doorway
        outside it -- pressing E at the pit head did nothing at all.
        """
        for _v in visible_villages:
            for _wp in _v.workplaces:
                if _wp.rect.inflate(170, 170).collidepoint(player.x, player.y):
                    return _wp
        return None

    def work_action(key: str) -> str:
        """Do a stroke of the trade the player is standing at.

        The inputs and the outputs are the village's own constants -- the same
        50-unit mash, the same leaf-to-cigar ratio, the same iron per tool --
        so the player works the bench exactly as the man beside him does. The
        only difference is the clock: a hand at the bench is not a daily
        production quota, so each stroke takes a few seconds.
        """
        nonlocal work_cd
        wp = smith_shop
        if wp is None or work_cd > 0.0:
            return ""
        kind = wp.kind
        if kind == "brewery":
            brew = getattr(player, "brew", None)
            if brew is not None and now >= brew[2]:
                wort, count, _r = brew
                player.brew = None
                out = economy.BREW.get(wort)
                if out:
                    inventory.add(out, count)
                    work_cd = 2.0
                    return "Drew %d %s" % (count, out)
            if brew is None:
                food = getattr(wp.worker.village, "local_food", "wheat") \
                    if wp.worker else "wheat"
                if inventory.count_of(food) >= economy.WORT_BATCH:
                    inventory.consume(food, economy.WORT_BATCH)
                    player.brew = (economy.WORT.get(food, "wheat_wort"),
                                   economy.WORT_BATCH, now + economy.BREW_SECONDS)
                    work_cd = 2.0
                    return "Mashed %d %s   -   ready in %d min" % (
                        economy.WORT_BATCH, food, int(economy.BREW_SECONDS / 60))
            return "Nothing to draw"
        if kind == "lab":
            leaf = next((k for k in economy.PROCESS
                         if inventory.count_of(k) >= economy.CRAFT_CONSUME), None)
            if leaf is None:
                return "No leaf"
            out = economy.PROCESS[leaf]
            inventory.consume(leaf, economy.CRAFT_CONSUME)
            g = skills.leaf_grade(8)
            inventory.add(out, 1, g)
            work_cd = 2.0
            return "Made one %s   (%s)" % (out, quality.letter(g))
        if kind == "mine":
            _dug = random.randint(3, 7)
            inventory.add("iron", _dug)
            pay_share("iron", _dug)
            work_cd = 2.0
            return "Broke out some iron"
        if kind == "smith":
            if inventory.count_of("iron") < economy.IRON_PER_TOOL:
                return "Need %d iron" % economy.IRON_PER_TOOL
            inventory.consume("iron", economy.IRON_PER_TOOL)
            kindw = "shovel"
            for want in ("axe", "pickaxe", "shovel"):
                if any(k == want for _w, k in
                       (getattr(wp.worker, "tool_orders", ()) or ())):
                    kindw = want
                    break
            inventory.add(kindw, 1, skills.leaf_grade(8))
            work_cd = 2.0
            return "Forged a %s" % kindw
        return ""

    def near_fireplace() -> bool:
        if inside_house is None:
            return False
        return inside_house.interior.fireplace_near(player.x, player.y)

    def join_army(npc) -> None:
        """Enlist. You are a soldier of that nation from here on -- no squad of
        your own, no escort, no special treatment.

        An enlisted man is paid the soldier's wage every day, eats what the
        column eats, takes a soldier's share of what it plunders, and is shot
        at by everyone his nation is at war with. The column's war is your war:
        it is somewhere on the map doing what the crown told it to, and if you
        want to be in it you had better keep up. Harm one of your own and the
        banishment stands.
        """
        if player.nation is not None and player.nation == npc.nation:
            toast("You already serve %s" % nation_name(npc.nation))
            return
        player.nation = npc.nation
        # The wage is the wage: a rifleman's if he is carrying a rifle, else
        # an axeman's. It is paid out of the crown, every day, like everyone
        # else in the ranks.
        player.wage = (economy.PAY_RIFLE
                       if inventory.count_of("rifle") > 0 else economy.PAY_MELEE)
        player.army = None
        for a_ in armies:
            if a_.nation == npc.nation and not a_.done:
                player.army = a_          # march with the column in the field
                a_.player = player
                break
        player.village = npc.village
        inventory.add("bread", 3)
        inventory.add("first_aid", 1)
        toast("Enlisted in the %s army   -   pay %d a day%s"
              % (nation_name(npc.nation), player.wage,
                 "   (the column is in the field)" if player.army else ""))

    def leave_army() -> None:
        if getattr(player, "army", None) is not None:
            player.army.player = None
        player.nation = None
        player.army = None
        player.wage = 0
        toast("You left the army")

    def player_hidden_in_village() -> bool:
        for village in visible_villages:
            if math.hypot(player.x - village.x, player.y - village.y) < village.radius:
                return True
        return False

    # One index of the fight, rebuilt once a frame. A fighter only ever
    # considers what is within reach of it, so the cost is linear in the
    # number of men instead of men-squared.
    ENGAGE_REACH = 1200.0
    LOOK_REACH = 1000.0
    enemy_grid = TeamGrid(200.0)
    folk_grid = TeamGrid(260.0)
    # A SECOND GRID, FOR THE ONE QUESTION A VILLAGER ASKS. He wants to know
    # only about SOLDIERS -- the all-creatures grid is mostly wolves, and he
    # threw every one of them away. Worse, its 200-px cells meant a 900-px
    # look assembled a hundred cells per man per tick, and no two men shared
    # an answer. Cell = reach, so the look is nine cells, and the men of one
    # village nearly always want the same nine -- they share it.
    soldier_grid = TeamGrid(900.0)

    class _Watcher:
        """In test mode the armies do not see the player.

        He is there to watch a war, not to be shot by it. Everything else
        about the world stays real -- the soldiers still fight each other, the
        villagers still live and die -- but the man at the keyboard is a ghost
        who happens to be standing in the field.
        """

        __slots__ = ("_p", "dead", "nation", "squad")

        def __init__(self, p) -> None:
            self._p = p
            self.dead = True            # nothing targets a dead man
            self.nation = None
            self.squad: list = []

        @property
        def x(self) -> float:
            return self._p.x

        @property
        def y(self) -> float:
            return self._p.y

    watcher = _Watcher(player)

    def choose_target(creature, villages):
        who = watcher if test_mode else player
        near = enemy_grid.near(creature.x, creature.y, ENGAGE_REACH)
        folk = folk_grid.near(creature.x, creature.y, LOOK_REACH)
        return creatures_choose_target(creature, who, near, rabbits, villages,
                                       player.squad, persons=folk)

    def day_phase() -> str:
        """Where the villagers are in their day.

        Work, then the whole village gathers in the square at mid-day -- and
        that hour is the only time anyone buys or sells -- then work again.
        Nobody spends the day chasing a seller across the fields.
        """
        if night_factor() > 0.38:
            return "sleep"
        t = (0.30 + now / DAY_LENGTH) % 1.0
        if t < 0.30 or t >= 0.72:
            return "home"
        if 0.40 <= t < 0.60:
            return "market"          # mid-day: business is done in the square
        return "work"

    def _nearest_town():
        """THE NEAREST SETTLEMENT, WHICHEVER ONE IT IS.

        It used to hand the map `player.settled_at` -- his own town -- and he
        has none: with no backstory he arrives owning nothing and belonging
        nowhere, so the gold pin had nothing to draw and the map showed one
        outlaw hut in an empty country. A man with no town still needs to know
        where the nearest one is.
        """
        towns = list(getattr(villages, "villages", ()) or ())
        if not towns:
            return None
        return min(towns, key=lambda v: (v.x - player.x) ** 2
                   + (v.y - player.y) ** 2)

    def speed_button() -> pygame.Rect:
        return pygame.Rect(vw // 2 - 74, vh - 142, 148, 32)

    def draw_speed_button() -> None:
        if not test_mode:
            return
        r = speed_button()
        pygame.draw.rect(screen, (30, 30, 36), r, border_radius=8)
        pygame.draw.rect(screen,
                         (222, 176, 88) if time_scale > 1.0 else (110, 110, 122),
                         r, width=2, border_radius=8)
        text = font.render("SPEED  x%d" % int(time_scale), True,
                           (244, 236, 214) if time_scale > 1.0 else (172, 172, 182))
        screen.blit(text, (r.centerx - text.get_width() // 2,
                           r.centery - text.get_height() // 2))

    def night_factor(t=None) -> float:
        if t is None:
            t = now
        tt = (0.30 + t / DAY_LENGTH) % 1.0
        brightness = 0.5 + 0.5 * math.sin(2.0 * math.pi * (tt - 0.25))
        return 1.0 - brightness

    def next_morning(t: float) -> float:
        for _ in range(int(DAY_LENGTH / 5.0) + 2):
            t += 5.0
            if night_factor(t) <= 0.38:
                break
        return t

    def try_sleep() -> None:
        nonlocal sleep_timer
        if inside_house is None:
            return
        bed = None
        for kind, rect in inside_house.interior.furniture:
            if kind == "bed":
                bed = rect
        if bed is None:
            return
        if math.hypot(player.x - bed.centerx, player.y - bed.centery) > REACH + 46.0:
            toast("Get closer to the bed")
            return
        if night_factor() <= 0.38:
            toast("You can only sleep at night")
            return
        sleep_timer = SLEEP_TIME
        pygame.mouse.set_visible(False)

    def draw_night() -> None:
        night = night_factor()
        vision.cone_deg = 175.0 - 55.0 * night
        interior_vision.cone_deg = 175.0 - 55.0 * night
        if night > 0.03:
            shade = shade_cache.get((vw, vh))
            if shade is None:
                shade = pygame.Surface((vw, vh))
                shade.fill((10, 14, 32))
                shade_cache[(vw, vh)] = shade
            shade.set_alpha(int(195 * night))
            screen.blit(shade, (0, 0))
        draw_status()

    def draw_status() -> None:
        """Battle / plunder banner, top-centre."""
        if not hud_status:
            return
        label = font.render(hud_status, True, (244, 236, 214))
        plate = pygame.Surface((label.get_width() + 26, 30), pygame.SRCALPHA)
        pygame.draw.rect(plate, (16, 16, 20, 205), plate.get_rect(), border_radius=8)
        pygame.draw.rect(plate, (150, 120, 60), plate.get_rect(), width=2, border_radius=8)
        screen.blit(plate, (vw // 2 - plate.get_width() // 2, 8))
        screen.blit(label, (vw // 2 - label.get_width() // 2, 8 + (30 - label.get_height()) // 2))

    def tick_conquest(dt) -> None:
        """Plunder timers run everywhere, indoors included."""
        for village in list(active_chaos):
            village.chaos -= dt
            if village.chaos <= 0.0:
                village.chaos = 0.0
                village.conquered = True
                village.nation = player.nation
                for npc in village.npcs:
                    npc.nation = player.nation
                    npc.team = ("nation", player.nation)
                active_chaos.remove(village)
                toast(f"{village.name} has joined your nation")

    def update_hud() -> None:
        nonlocal hud_status
        if active_chaos:
            v = min(active_chaos, key=lambda q: q.chaos)
            hud_status = ("Battle won  -  %d seconds of plundering left"
                          % int(math.ceil(v.chaos)))
        else:
            hud_status = ("Battle" if any(v.battle for v in visible_villages)
                          else "")

    def draw_hunger_gray() -> None:
        """Starving drains the colour out of the world."""
        if player.hunger >= 40.0:
            return
        k = 1.0 - player.hunger / 40.0
        gray = pygame.transform.grayscale(screen)
        gray.set_alpha(int(205 * k))
        screen.blit(gray, (0, 0))

    def mark_dirty() -> None:
        """The world changed: save it SOON, not this instant.

        Mining an iron seam wrote the entire four-and-a-half megabyte world to
        disk on the frame the ore came loose -- which is why the last strike
        always hitched. The write is the same; it just happens a second or two
        later, with the swing already over.
        """
        nonlocal save_dirty, save_timer
        save_dirty = True
        save_timer = min(save_timer, 2.0)

    def save_now() -> None:
        houses = []
        for house in built_houses:
            interior = getattr(house, "interior", None)
            chest = getattr(interior, "chest", None) if interior is not None else None
            houses.append({
                "x": house.x, "y": house.y, "w": house.w, "h": house.h,
                "roof": list(house.roof), "facing": list(house.facing),
                "seed": getattr(house, "build_seed", 0),
                "interior_seed": getattr(house, "interior_seed", 0),
                "chest": ([persist.stack_to_data(s) for s in chest.slots]
                          if chest is not None else []),
                "workshops": ([[r.centerx, r.centery] for r in interior.workshops]
                              if interior is not None else []),
            })
        village_state = {}
        for (gx, gy), v in villages._cache.items():
            broken = [i for i, h in enumerate(v.houses)
                      if getattr(h, "door_broken", False)]
            if v.conquered or v.plundered or v.chaos > 0.0 or broken:
                village_state["%d,%d" % (gx, gy)] = {
                    "conquered": bool(v.conquered),
                    "plundered": bool(v.plundered),
                    "chaos": float(v.chaos),
                    "nation": int(v.nation),
                    "broken": broken,
                    "gaps": [[int(s), float(c), float(hw)]
                             for s, c, hw in v.fence_gaps],
                }
        squad = []
        for s in player.squad:
            if getattr(s, "alive", False):
                squad.append({"x": s.x, "y": s.y,
                              "march": list(s.march_target) if s.march_target else None})
        _payload = {
            "seed": world.seed,
            "houses": houses,
            "player": {
                "x": player.x, "y": player.y,
                "health": player.health, "hunger": player.hunger,
                "stamina": player.stamina, "bleed": player.bleed,
                "nation": (int(player.nation) if player.nation is not None
                           else None),
                "selected": inventory.selected,
            },
            "inventory": [persist.stack_to_data(s) for s in inventory.slots],
            "held": persist.stack_to_data(panel.held),
            "skills": {"farming": skills.farming, "movement": skills.movement,
                       "axe": skills.axe, "shooting": skills.shooting},
            "now": now,
            "kills": kills,
            "plots": [[tx, ty, plot.kind, plot.planted_at]
                      for (tx, ty), plot in world.plots.items()],
            "wild": [[tx, ty] for (tx, ty) in world.wild_removed],
            "compass_home": (list(compass_state.home)
                             if compass_state.home is not None else None),
            "ore": [[cx, cy] for (cx, cy) in ore_field.mined],
            "tiles": [[tx, ty, kind] for (tx, ty), kind in world._overrides.items()],
            "villages": village_state,
            "squad": squad,
            "fences": [[r.x, r.y, r.w, r.h] for r in built_fences],
            "gates": [[r.x, r.y, r.w, r.h] for r in built_gates],
            "world": world_to_data(villages),
        }
        if not persist.write_binary(_payload):
            persist.write(_payload)          # the old JSON writer, as a fallback

    def load_now() -> None:
        nonlocal now, kills, cam_x, cam_y
        data = persist.read_binary()
        if data is None:
            data = persist.read()            # an older save, in JSON
        # THE WORLD FIRST, so everything below can rely on it, and so a load
        # is a load: the people, their skills, their coin, their towns.
        world_from_data(villages, data.get("world"))
        # ONE MAN, ONE PLACE. A save stores his town and his road separately,
        # so a restored traveller could come back on the roll of the town he
        # left as well as on the road. This is where that is made true.
        village_mod.rebuild_people(villages)
        village_mod.rebuild_houses(villages)
        for _v in villages._cache.values():
            for _n in _v.npcs:
                if not (_n.alive and _n.job == "soldier" and not _n.levied):
                    continue
                _sol = Soldier(_n.x, _n.y, _v.nation,
                               melee=not getattr(_n, "ranged", False),
                               seed=random.randint(0, 2 ** 31))
                _sol.name = _n.name
                _sol.skills = _n.skills
                _sol.home_npc = _n
                _sol.home_village = _v
                _sol.patrol_center = (_v.x, _v.y)
                _sol.patrol_r = _v.radius * 0.6
                _sol.garrison_of = _v
                _sol.in_army = True
                war.STANDING.append(_sol)
                enemies.append(_sol)
        for entry in data.get("houses", []):
            try:
                house = House(entry["x"], entry["y"], entry["w"], entry["h"],
                              tuple(entry["roof"]), tuple(entry["facing"]),
                              entry["seed"])
                house.build_seed = entry["seed"]
                house.interior_seed = entry.get("interior_seed", 0)
                interior = Interior(house.interior_seed, tuple(house.facing))
                chest = interior.chest
                for i, datum in enumerate(entry.get("chest", [])):
                    if i < len(chest.slots):
                        chest.slots[i] = persist.data_to_stack(datum)
                for wx, wy in entry.get("workshops", []):
                    interior.place_workshop(wx, wy)
                house.enterable = True       # your own houses stay open
                house.door_broken = True
                house.interior = interior
                built_houses.append(house)
            except Exception:
                continue

        p = data.get("player")
        if p:
            player.x = float(p.get("x", player.x))
            player.y = float(p.get("y", player.y))
            player.health = max(1.0, float(p.get("health", player.health)))
            player.hunger = float(p.get("hunger", player.hunger))
            player.stamina = float(p.get("stamina", player.stamina))
            player.bleed = float(p.get("bleed", 0.0))
            player.dead = False
            nation = p.get("nation")
            player.nation = int(nation) if nation is not None else None
            inventory.selected = int(p.get("selected", 0))
            cam_x = player.x - WIDTH / (2.0 * ZOOM)
            cam_y = player.y - HEIGHT / 2.0
        if data.get("inventory"):
            for i, datum in enumerate(data["inventory"]):
                if i < len(inventory.slots):
                    inventory.slots[i] = persist.data_to_stack(datum)
        panel.held = persist.data_to_stack(data.get("held"))
        for fx0, fy0, fw, fh in data.get("fences", []):
            built_fences.append(pygame.Rect(int(fx0), int(fy0), int(fw), int(fh)))
        for gx0, gy0, gw, gh in data.get("gates", []):
            built_gates.append(pygame.Rect(int(gx0), int(gy0), int(gw), int(gh)))
        if data.get("skills"):
            sk = data["skills"]
            skills.farming = float(sk.get("farming", 0.0))
            skills.movement = float(sk.get("movement", 0.0))
            skills.axe = float(sk.get("axe", 0.0))
            skills.shooting = float(sk.get("shooting", 0.0))
        now = float(data.get("now", now))
        kills = int(data.get("kills", kills))
        for tx, ty, kind, planted in data.get("plots", []):
            world.set_plot(int(tx), int(ty), kind,
                           None if planted is None else float(planted))
        for tx, ty in data.get("wild", []):
            world.wild_removed.add((int(tx), int(ty)))
        ch = data.get("compass_home")
        if ch:
            compass_state.home = (float(ch[0]), float(ch[1]))
        for cx, cy in data.get("ore", []):
            ore_field.mined.add((int(cx), int(cy)))
        for tx, ty, kind in data.get("tiles", []):
            world.set_tile(int(tx), int(ty), kind)
        # The ground was already built from the seed before any of this was
        # restored, so every worked tile and every built floor in the world was
        # missing from it. Rebuild what the player can see, once, now -- rather
        # than letting a queued job trickle in behind a blur.
        # THE GROUND IS BUILT UNDER THE MAN BEING WATCHED TOO.
        #
        # refresh_around() was called with player.x/player.y, and the camera now
        # goes to the watched man -- so at his position the ground had never
        # been generated at all and the view was BLACK. Same mistake as the
        # vision eye below, in a different cache.
        _wt = observer_.target
        if _wt is not None and getattr(_wt, "alive", False):
            ground.refresh_around(_wt.x, _wt.y, WIDTH, HEIGHT)
        else:
            ground.refresh_around(player.x, player.y, WIDTH, HEIGHT)
        for key, st in data.get("villages", {}).items():
            try:
                gx, gy = (int(v) for v in key.split(","))
                v = villages.get(gx, gy)
                v.conquered = bool(st.get("conquered", False))
                v.plundered = bool(st.get("plundered", False))
                v.chaos = float(st.get("chaos", 0.0))
                nation = st.get("nation")
                if nation:
                    v.nation = int(nation)
                for i in st.get("broken", []):
                    if 0 <= i < len(v.houses) and not v.houses[i].door_broken:
                        h = v.houses[i]
                        h.enterable = True
                        h.interior = Interior(random.randint(0, 2 ** 31),
                                              tuple(h.facing))
                        fill_loot(h.interior.chest)
                        h.break_door()
                if st.get("gaps"):
                    v.fence_gaps = [(int(s), float(c), float(hw))
                                    for s, c, hw in st["gaps"]]
                    fence.rebuild(v)
                if v.conquered:
                    for npc in v.npcs:
                        npc.nation = v.nation
                        npc.team = ("nation", v.nation)
                if v.chaos > 0.0:
                    active_chaos.append(v)
            except Exception:
                continue
        squad_data = data.get("squad", [])
        if squad_data and player.nation is not None:
            squad = make_squad(player.nation, player.x, player.y, len(squad_data),
                               color=nation_color(player.nation))
            for soldier, entry in zip(squad, squad_data):
                soldier.x = float(entry.get("x", soldier.x))
                soldier.y = float(entry.get("y", soldier.y))
                march = entry.get("march")
                if march:
                    soldier.march_target = (float(march[0]), float(march[1]))
            enemies.extend(squad)
            player.squad = squad

    # -- first frame --------------------------------------------------------
    font = pygame.font.SysFont("dejavusans", 18)
    # The news box: small, quiet, and out of the way of the world it is
    # describing.
    # Drawn INSIDE the zoomed world frame, so it is deliberately small here:
    # the frame is scaled by ZOOM on the way to the screen.
    speech_font = pygame.font.SysFont("dejavusans", 10)
    screen.fill((18, 24, 18))
    screen.blit(font.render("Growing the world...", True, (120, 150, 110)), (24, 22))
    pygame.display.flip()
    ground.ensure_visible(cam_x, cam_y, *screen.get_size())
    # Warm the neighbourhood while the loading screen is up, so the first real
    # frame does not freeze generating villages and their house sprites.
    villages.visible(cam_x - 500.0, cam_y - 500.0,
                     screen.get_width() + 1000, screen.get_height() + 1000)
    trees.visible(cam_x, cam_y, *screen.get_size())

    visible_villages: list = []
    world_accum = 0.0
    # [the running Test of Strengths, has one been started this game]
    # [the running Test of Strengths, THE DAY THE LAST ONE BEGAN]
    # -1, not False: `False != 0` is False in Python, so a flag initialised to
    # False can never differ from day zero and the first tournament of the
    # world was silently never held.
    _tourney = [None, -1]
    _nem = [None]          # the Nemesis -- see Nemesis.md

    def tick_nemesis(now: float) -> None:
        """THE NEMESIS TICKS A DAY AT A TIME, WHEREVER THE PLAYER IS.

        This lived in the EXTERIOR branch of the frame -- and `now += dt`
        happens in the interior branch too. So the moment the player was inside
        a house the world's clock kept running and the nemesis simply stopped:
        one report, then silence, for as long as the player stayed indoors.
        A world that only exists while you are looking at it is not a world.
        """
        kd = int(now / economy.DAY_LENGTH)
        if _nem[0] is None:
            _nem[0] = nemesis.NemesisWorld(villages, villages, player)
            _nem[0].seed(kd)
            return
        if _nem[0].active is None and kd - _nem[0].dead_day >= 40:
            _nem[0].seed(kd)
        for _ln in _nem[0].tick(kd, now):
            if _ln:
                toast(_ln)
                break
    sleep_timer = 0.0
    save_timer = 20.0
    save_dirty = False
    settle_timer = 8.0        # how often a nation looks to its own vacancies
    house_timer = 1.0         # how often a household shares its larder
    demand_timer = 20.0       # how often the crown asks after its own war
    DESERT_PX = 2400.0          # how far a soldier may stray from the column
    DESERT_SECONDS = 180.0      # ...and for how long, before it is desertion
    player._away = 0.0
    player.settled_at = None
    player.job = None
    load_now()

    if os.environ.get("KP_AUTO_RAID"):        # headless raid self-test hook
        _cand = villages.visible(player.x - 4000.0, player.y - 4000.0, 8000, 8000)
        if len(_cand) >= 2:
            _home = _cand[0]
            join_army(_home.commander)
            _foe = next((w for w in _cand if w.nation != _home.nation), None)
            if _foe is not None:
                player.x = _foe.x + _foe.radius - 120.0
                player.y = _foe.y
                cam_x = player.x - WIDTH / (2.0 * ZOOM)
                cam_y = player.y - HEIGHT / 2.0
                for _i, _s in enumerate(player.squad):
                    _s.x = player.x + 40.0 * (_i - 1)
                    _s.y = player.y + 60.0
                print("AUTO-RAID: joined %s, attacking %s" % (_home.name, _foe.name))
    # ---- PHASE TIMERS: where does the frame actually GO? ------------------
    # py-spy cannot see inside the compiled Cython, so the split of a frame has
    # to be measured rather than sampled. Three windows: the TOWNS (the village
    # loop), the MEN (the NPC loop), and everything between and after them --
    # houses, settling, the draw. This is a measurement, not a feature.
    _PH = {"v": 0.0, "m": 0.0, "n": 0.0, "f": 0, "t": time.time()}
    _watched_last = None      # the man being watched, so a change can rebuild

    # ---- THE LANES: the world cut so more than one core can hold it -------
    #
    # The cut is real and it is AUDITED every time it is remade: every town and
    # every man in exactly one lane. What is not here yet is the processes --
    # every lane is still stepped in this process -- so the behaviour today is
    # exactly what it was, and the split lands on top of a cut that is already
    # proved. If the audit ever fails the frame falls back to stepping the
    # whole world, because a lane that has lost a man is worse than no lanes.
    _LANES = lanes.Partition(1)
    _LANE_TOWNS = list(villages.villages)
    _LANE_PEOPLE = list(village_mod.PEOPLE)
    _lane_timer = 0.0
    _lane_warned = False
    running = True
    # THE WINDOW IS NEVER A FROZEN PICTURE WITH NOTHING ON IT. The first
    # second of the world does its one-time work INSIDE the loop -- indexing
    # every wall and trunk in view, standing the town up, cutting the lanes --
    # and that is by far the heaviest thing the game ever does. The bar is
    # drawn at the TOP of the frame, so it is what is on screen while that
    # work happens rather than a still image and no explanation.
    def draw_boot(surface, title: str, prog: float) -> None:
        w, h = surface.get_size()
        surface.fill((14, 12, 16))
        f_big = pygame.font.SysFont("dejavusansmono", max(14, h // 22), bold=True)
        f_small = pygame.font.SysFont("dejavusansmono", max(10, h // 44))
        head = f_big.render(title, True, (226, 188, 98))
        surface.blit(head, (w // 2 - head.get_width() // 2, int(h * 0.38)))
        bar = pygame.Rect(int(w * 0.22), int(h * 0.52), int(w * 0.56), max(6, h // 40))
        pygame.draw.rect(surface, (34, 30, 26), bar)
        fill = bar.copy()
        fill.w = max(2, int(bar.w * max(0.02, min(1.0, prog))))
        pygame.draw.rect(surface, (226, 188, 98), fill)
        pygame.draw.rect(surface, (110, 90, 54), bar, 1)
        note = f_small.render("settling in", True, (122, 110, 98))
        surface.blit(note, (w // 2 - note.get_width() // 2, bar.bottom + 10))
        pygame.display.flip()

    _boot_title = "WELCOME TO %s" % (_origin_town.name.upper() if _origin_town is not None else "THE WORLD")
    _boot_left = [10]
    _boot_slow = [True]
    _boot_prev = [None]
    # PUT HIM DOWN LAST. The spawn is decided when he is created, but a dozen
    # things between there and the first frame -- the village register, the
    # patrols, the world bounds -- can move him, and one of them was putting
    # every backstory back at the origin. Set here, nothing after it can.
    player.x, player.y = _hx, _hy
    # AND HIS TRADE LAST OF ALL. There is a reset a few hundred lines above
    # that clears `player.job` and `player.settled_at` before the save is
    # read -- correct for a fresh start and fatal for a backstory, because it
    # ran AFTER the backstory had already posted him to a trade. The board
    # then said "no trade, no post, no wage" and refused to let him sell, and
    # both of those looked like two separate bugs.
    # HE LIVES SOMEWHERE WHATEVER HIS TRADE. The town used to be set only for
    # the seven trades, so IDLE -- the man who owns nothing -- had no village
    # at all: he spawned in open country, and the notice board had nobody to
    # sell to and no ledger to owe. He has no POST; he still has a town.
    if _origin_town is not None:
        player.settled_at = _origin_town
        player.village = _origin_town
        if getattr(_origin_town, "nation", None) is not None:
            player.nation = _origin_town.nation
        if origin in _JOB:
            player.job = _JOB[origin]
    while running:
        _boot_t0 = pygame.time.get_ticks()
        # THE FLAG COMES DOWN WHEN A FRAME WAS QUICK. Measure the PREVIOUS one:
        # at the top of a frame you cannot know how long this one will take.
        if _boot_prev[0] is not None and _boot_t0 - _boot_prev[0] < 45:
            _boot_slow[0] = False
        _boot_prev[0] = _boot_t0
        if _boot_left[0] > 0 or _boot_slow[0]:
            # AND IT STAYS UP UNTIL THE FRAMES STOP BEING SLOW. Ten frames was
            # a guess, and the heaviest work does not happen in the first ten:
            # the screen came down and then the window froze behind it. The
            # bar now comes down when the loop can keep up, not on a count.
            draw_boot(pygame.display.get_surface(), _boot_title,
                      min(0.97, (10 - min(10, _boot_left[0])) / 10.0 + 0.05))
            if _boot_left[0] > 0:
                _boot_left[0] -= 1
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        _PH["f"] += 1
        dt = min(dt * time_scale, 0.5)          # test-mode speed-up
        vw, vh = screen.get_size()
        mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
        wmouse_x, wmouse_y = mouse_x / ZOOM, mouse_y / ZOOM  # world space

        for event in pygame.event.get():
            # ---- THE KEY LOG. A one-line record of every key this build's
            # event loop actually receives, appended to
            # ~/.kingpin_saves/keys.log. It exists because I kept claiming the
            # inspector worked on the strength of my own synthetic events while
            # the real game did nothing, and guessing at the difference cost
            # hours. Now the game says what it heard.
            if event.type == pygame.KEYDOWN:
                try:
                    _kf = os.path.expanduser("~/.kingpin_saves/keys.log")
                    with open(_kf, "a") as _fh:
                        _fh.write("%s key=%s name=%s observer=%s test=%s\n"
                                  % (time.strftime("%H:%M:%S"),
                                     event.key,
                                     pygame.key.name(event.key),
                                     getattr(observer_, "open", "?"),
                                     time_scale > 1.0))
                except Exception:
                    pass
            if event.type == pygame.QUIT:
                save_now()
                running = False
            elif observer_.handle(event, player):
                # THE INSPECTOR ANSWERS FIRST, ABOVE EVERY MENU.
                #
                # Every branch below is an `elif`, so whichever one matches
                # EATS the key. With the pack open (`elif inventory_open:`) or
                # any other panel, I never reached the observer at all -- which
                # is why pressing TAB and then I did nothing: the pack had the
                # keyboard. The inspector is how the world is looked at, and
                # the world does not stop for a menu.
                pass
            elif (test_mode and event.type == pygame.KEYDOWN
                  and event.key == pygame.K_l):
                # TEST MODE ONLY. L puts ONE LEVEL on a random skill, so the
                # level-up shine can be looked at without earning it -- which
                # at MOVE_NEED = 7,500,000 px would otherwise be about three
                # hundred days of walking.
                #
                # A LEVEL IS A BAND, and each skill says how wide: 0.125 for
                # the three that run 0..1, and 1.0 for farming, which runs 0..8.
                # Both are eight levels, so this is ONE rule for all four.
                #
                # ALL FOUR, ON EVERY PRESS. A random one of four meant three
                # presses in four left the skill you were watching exactly
                # where it was, and a level-up you cannot see is not a test.
                _done = []
                for _name, _band, _cap in (("movement", 0.125, 1.0),
                                           ("axe", 0.125, 1.0),
                                           ("shooting", 0.125, 1.0),
                                           ("farming", 1.0, 8.0)):
                    _new = min(_cap,
                               (int(getattr(skills, _name) / _band) + 1) * _band)
                    setattr(skills, _name, _new)
                    _done.append("%s %d" % (_name[:4].title(), int(_new / _band)))
                player.level_flash = player.LEVEL_FLASH
                toast("LEVEL UP    " + "   ".join(_done))
            elif (test_mode and event.type == pygame.MOUSEBUTTONDOWN
                  and event.button == 1 and speed_button().collidepoint(event.pos)):
                speed_i = (speed_i + 1) % len(SPEEDS)
                time_scale = SPEEDS[speed_i]
                toast("Speed x%d" % int(time_scale))
            elif inside_mine is not None:
                # UNDERGROUND, THE WORLD IS NOT THERE. The mine uses its own
                # little coordinates, so a swing at the face was being read as
                # a swing at the world at those same numbers -- felling a tree
                # that stands hundreds of yards away above your head. Nothing
                # out there answers to the mouse while you are down here.
                #
                # BUT A MAN'S PACK IS STILL HIS. Everything was swallowed with
                # a bare `pass`, so the number keys did nothing and the mine
                # was a room you could not take your pickaxe out in -- the one
                # tool it is worked with. The hotbar and the pack answer to him
                # down here; nothing of the world does.
                if event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
                    hotbar.select_visible(event.key - pygame.K_1)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_0:
                    _empty = hotbar.first_empty()
                    if _empty is not None:
                        hotbar.select_visible(_empty)
                        toast("Empty hands")
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
                    hotbar.handle_event(event)
                elif (event.type == pygame.KEYDOWN
                      and event.key in (pygame.K_i, pygame.K_TAB)):
                    inventory_open = not inventory_open
                    pygame.mouse.set_visible(inventory_open)
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                vw, vh = event.w, event.h
            elif game_over:
                action = overlay.handle_event(event, vw, vh)
                if action == "respawn":
                    respawn()
                elif action == "quit":
                    save_now()
                    running = False
            elif smith_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    smith_open = False
                    pygame.mouse.set_visible(False)
                elif (event.type == pygame.KEYDOWN
                      and event.key in (pygame.K_SPACE, pygame.K_RETURN)):
                    work_msg = work_action("")
            elif board_open:
                if board_panel.handle_event(event):
                    board_open = False
                    pygame.mouse.set_visible(False)
            elif inventory_open:
                if event.type == pygame.KEYDOWN and event.key in (
                        pygame.K_e, pygame.K_ESCAPE, pygame.K_TAB):
                    inventory_open = False
                    panel.close()
                    pygame.mouse.set_visible(False)
                else:
                    panel.handle_event(event)
            elif chest_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    chest_panel.close()
                    save_now()
                    chest_open = False
                    pygame.mouse.set_visible(False)
                else:
                    chest_panel.handle_event(event)
            elif workshop_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    workshop_open = False
                    pygame.mouse.set_visible(False)
                else:
                    made = workshop_menu.handle_event(event)
                    if made is not None:
                        cost = made["cost"]
                        if not test_mode:
                            for item, qty in cost.items():
                                inventory.consume(item, qty)
                        inventory.add(made["id"], made.get("yield", 1))
                        save_now()
                        cost_txt = " + ".join(f"{q} {k}" for k, q in cost.items())
                        toast(f"Crafted {made['name']}"
                              + ("" if test_mode else f"   -{cost_txt}"))
            elif compass_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_f,
                                                                  pygame.K_ESCAPE):
                    compass_open = False
                    pygame.mouse.set_visible(False)
                else:
                    choice = compass_menu.handle_event(event)
                    if choice == "sethome":
                        compass_state.home = (player.x, player.y)
                        compass_open = False
                        pygame.mouse.set_visible(False)
                        save_now()
                        toast("Home set")
                    elif choice in ("village", "home"):
                        compass_state.mode = choice
                        compass_open = False
                        pygame.mouse.set_visible(False)
                        toast("Click to read the compass")
            elif confirm_open:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    confirm_open = False
                    pygame.mouse.set_visible(False)
                else:
                    answer = confirm.handle_event(event)
                    if answer is True:
                        if getattr(confirm, "mode", "join") == "leave":
                            leave_army()
                        else:
                            join_army(confirm.pending)
                        confirm_open = False
                        pygame.mouse.set_visible(False)
                    elif answer is False:
                        confirm_open = False
                        pygame.mouse.set_visible(False)
            elif pause_open:
                action = pause_menu.handle_event(event)
                if action == "close":
                    pause_open = False
                    pygame.mouse.set_visible(False)
                elif action == "respawn":
                    pause_open = False
                    respawn()
                    player.x, player.y = 0.0, 0.0
                    cam_x = player.x - WIDTH / (2.0 * ZOOM)
                    cam_y = player.y - HEIGHT / 2.0
                    pygame.mouse.set_visible(False)
                elif action == "exit":
                    save_now()
                    running = False
            elif map_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_m,
                                                                  pygame.K_ESCAPE):
                    map_open = False
                elif world_map is not None:
                    world_map.zoom_event(event)
            elif trade_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    trade_open = False
                    pygame.mouse.set_visible(False)
                else:
                    trade_menu.handle_event(event)
            elif build_menu_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_b,
                                                                  pygame.K_ESCAPE):
                    build_menu_open = False
                    pygame.mouse.set_visible(False)
                else:
                    choice = build_menu.handle_event(event)
                    if choice is not None:
                        build_menu_open = False
                        placing = choice
                        fence_horizontal = True
            elif placing is not None:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE,
                                                                  pygame.K_b):
                    placing = None
                    pygame.mouse.set_visible(False)
                elif (event.type == pygame.KEYDOWN and event.key == pygame.K_r
                        and placing in ("fence", "gate")):
                    fence_horizontal = not fence_horizontal
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    placing = None
                    pygame.mouse.set_visible(False)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    try_place()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_v:
                _vt = nearest_voter()
                if _vt is None:
                    toast("No one here is selling a vote")
                else:
                    buy_vote(_vt)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_e:
                _bv = near_board()
                if _bv is not None:
                    board_village = _bv
                    board_open = True
                    board_panel.scroll = 0
                    pygame.mouse.set_visible(True)
                elif near_chest():
                    chest_open = True
                    chest_panel = ChestPanel(inventory, inside_house.interior.chest)
                    pygame.mouse.set_visible(True)
                elif near_brew():
                    mash_at_table()           # mash what you carry into wort
                elif (inside_house is not None
                        and inside_house.interior.barrel_near(player.x, player.y)
                        is not None):
                    use_barrel()              # fill it, or draw what it made
                elif near_lab():
                    craft_at_table()          # one article a press, and you learn
                elif (near_workplace() is not None
                      and near_workplace().kind == "mine"):
                    _wp = near_workplace()
                    if getattr(_wp, "room", None) is None:
                        _wp.room = mine.MineRoom(world.seed ^ id(_wp))
                    mine_out = (player.x, player.y)
                    inside_mine = _wp
                    player._mine_latch = True      # let go of E first
                    player.x, player.y = inside_mine.room.W / 2.0, \
                        inside_mine.room.H - 70.0
                    cam_x = player.x - vw / 2.0
                    cam_y = player.y - vh / 2.0
                    pygame.mouse.set_visible(False)
                elif near_workplace() is not None:
                    smith_shop = near_workplace()
                    smith_open = True
                    work_msg = ""
                    pygame.mouse.set_visible(True)
                elif near_workshop():
                    workshop_open = True
                    pygame.mouse.set_visible(True)
                else:
                    inventory_open = True
                    pygame.mouse.set_visible(True)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                build_menu.open("inside" if inside_house is not None else "outside")
                build_menu_open = True
                pygame.mouse.set_visible(True)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                stack = inventory.selected_stack()
                if stack is not None and stack.defn.id == "compass":
                    compass_menu.open(compass_state.home is not None)
                    compass_open = True
                    pygame.mouse.set_visible(True)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                stack = inventory.selected_stack()
                kind = stack.defn.id if stack else None
                if (kind in (guns.RIFLE, guns.SHOTGUN) and player.reloading <= 0.0
                        and player.mags.get(kind, 0) < guns.MAG[kind]):
                    if inventory.count_of("ammo") > 0:
                        player.reloading = guns.reload_time(kind, skills.shooting)
                        player.reload_total = player.reloading   # for the bar
                        player.reload_kind = kind
                        toast("Reloading\u2026")
                    else:
                        toast("No ammo to reload with")
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_m
                  and not inventory_open and not trade_open and not board_open):
                # FOR EVERYBODY. The chart was test-mode only, which meant the
                # one thing a man on a road needs -- where am I and where is the
                # nearest town -- was a debug tool.
                map_open = not map_open
                pygame.mouse.set_visible(map_open)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pause_open = True
                pygame.mouse.set_visible(True)
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_TAB):
                # THE PACK NEEDED A KEY ABOVE GROUND AND NEVER HAD ONE.
                # inventory_open was only ever toggled inside the mine's key
                # block, so above ground the pack could not be opened at all --
                # and I never noticed, because I was pressing I for the
                # inspector and the inspector DOES answer it (main.py, the
                # observer branch). TAB is free here, so TAB opens the pack.
                inventory_open = not inventory_open
                pygame.mouse.set_visible(inventory_open)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_0:
                empty = hotbar.first_empty()
                if empty is not None:
                    hotbar.select_visible(empty)
                    toast("Empty hands")
            elif event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
                hotbar.select_visible(event.key - pygame.K_1)
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
                consumed = hotbar.handle_event(event)
                if (not consumed and event.type == pygame.MOUSEBUTTONDOWN
                        and event.button == 1):
                    on_click()

        if sleep_timer > 0.0:                  # sleeping through the night
            sleep_timer -= dt
            if sleep_timer <= 0.0:
                now = next_morning(now)
                save_now()
                toast("You slept until morning")
            screen.fill((0, 0, 0))
            pygame.display.flip()
            continue
        # Autosave: whatever else happens, progress is never more than this far
        # behind (covers a crash on exit losing the session).
        save_timer -= dt
        if save_timer <= 0.0 and not game_over and not player.dead:
            save_timer = 20.0
            if save_dirty:
                save_dirty = False
                save_now()
        door_cooldown = max(0.0, door_cooldown - dt)
        work_cd = max(0.0, work_cd - dt)
        if (inside_house is not None and not game_over and not inventory_open
                and not build_menu_open and not chest_open and not trade_open
                and not workshop_open and not confirm_open and not pause_open
                and not map_open and placing is None):
            keys = pygame.key.get_pressed()
            if board_open or smith_open:                       # reading the board: stand still
                keys = _NO_KEYS
            # THE ROOM IS ZOOMED, SO THE AIM MUST BE. Reading the window
            # mouse against a zoomed camera skews every look by the zoom --
            # pointing left of centre actually aimed right, and the whole room
            # could only be half looked at.
            aim = (wmouse_x - (player.x - cam_x),
                   wmouse_y - (player.y - cam_y))
            player.skill_speed = skills.move_scale()
            award_levels()
            player.skill_stamina = skills.stamina_scale()
            player.skill_axe_cd = skills.axe_cooldown()
            _px0, _py0 = player.x, player.y
            player.update(dt, keys, aim, 1.0)
            skills.gain_movement(math.hypot(player.x - _px0, player.y - _py0))
            clamp_world()          # the world ends where the loading screen did
            settle_reload()
            house = inside_house
            interior = house.interior
            player.x, player.y = resolve_circle_rects(
                player.x, player.y, player.radius, interior.colliders)
            cam_x = min(max(player.x - vw / 2.0, 0.0), max(0.0, interior.W - vw))
            cam_y = min(max(player.y - vh / 2.0, 0.0), max(0.0, interior.H - vh))
            if interior.W <= vw:
                cam_x = interior.W / 2.0 - vw / 2.0
            if interior.H <= vh:
                cam_y = interior.H / 2.0 - vh / 2.0
            if door_cooldown <= 0.0 and interior.door_rect.colliderect(
                    pygame.Rect(player.x - 8, player.y - 8, 16, 16)):
                exit_house()
            else:
                # Keep the outside world alive, so the window view is live.
                now += dt
                tick_nemesis(now)
                # LOCKED ON: the player IS the camera, and he stands where the
                # watched man stands. Every existing line that reads player.x
                # then follows the target -- the camera, the visible villages,
                # the ground -- with nothing else changed. The ground around
                # the PLAYER is never built, because the camera left him.
                if observer_.target is not None and observer_.target.alive:
                    # THE PLAYER IS NOT MOVED. He stays exactly where he was --
                    # pinning him onto the target and letting the camera follow
                    # the player was the whole confusion. Only the CAMERA goes
                    # to the watched man; see the cam_x/cam_y above.
                    player.god = True
                    observer_.tick(now)
                creatures_set_time(now)
                wildcrop.set_time(now)
                wildcrop.set_world(world)
                night = night_factor() > 0.38
                wx = house.x - vw / 2.0
                wy = house.y - vh / 2.0
                sim_villages = villages.visible(wx, wy, vw, vh)
                sim_colliders = [vhouse.rect for village in sim_villages
                                 for vhouse in village.houses]
                sim_colliders += [tree.trunk_rect
                                  for tree in trees.visible(wx, wy, vw, vh)
                                  if not tree.felled]
                world_accum += dt
                world_tick = world_accum >= WORLD_STEP
                if world_tick:
                    world_dt = world_accum
                    world_accum = 0.0
                for village in sim_villages:
                    if not world_tick:
                        break
                    village.update(world_dt, world, now, day_phase())
                for enemy in enemies:
                    if enemy.alive:
                        enemy.update(dt, house, combat, [], 1.0, 1.0, False)
                        enemy.x, enemy.y = resolve_circle_rects(
                            enemy.x, enemy.y, enemy.radius, sim_colliders)
                combat.update(dt)
                blood.update(dt)
                ground.update(4, wx, wy, vw, vh)      # worker builds them
        elif (not game_over and not inventory_open and not build_menu_open
              and not chest_open and not trade_open and not workshop_open
              and not confirm_open and not pause_open and not map_open
              and placing is None):
            now += dt
            tick_nemesis(now)
            creatures_set_time(now)
            wildcrop.set_time(now)
            wildcrop.set_world(world)
            night = night_factor() > 0.38

            keys = pygame.key.get_pressed()
            if board_open:                       # reading the board: stand still
                keys = _NO_KEYS
            aim = (wmouse_x - (player.x - cam_x),
                   wmouse_y - (player.y - cam_y))   # the world mouse, not the window's
            foliage = trees.foliage(player.x, player.y)
            player.skill_speed = skills.move_scale()
            award_levels()
            player.skill_stamina = skills.stamina_scale()
            player.skill_axe_cd = skills.axe_cooldown()
            _px0, _py0 = player.x, player.y
            player.update(dt, keys, aim, 1.0 - 0.25 * foliage)
            skills.gain_movement(math.hypot(player.x - _px0, player.y - _py0))
            clamp_world()          # the world ends where the loading screen did
            settle_reload()

            visible_villages = villages.visible(cam_x, cam_y, vw, vh,
                                             extra=hub_world.hubs)

            # ---- RE-CUT THE WORLD, ONCE A SECOND ---------------------
            # The towns in front of the player must be stepped where he is, so
            # the cut follows him. Remaking it is cheap (it is a walk over the
            # towns and the register) but not free, so it is not per-frame.
            # RE-CUT ONLY WHEN THE VIEW ACTUALLY CHANGED. This was once a
            # second, every second, for the whole life of the game -- and
            # re-cutting walks every town and every soul. Measured on a
            # startup, the first re-cut inside the loop took NINETY SECONDS
            # of a frozen window. Nothing about the partition depends on the
            # clock: it depends on WHICH towns are in front of him, so it is
            # cut when that set changes and at no other time.
            _lane_ids = tuple(sorted(id(v) for v in visible_villages))
            _lane_timer -= dt
            if _lane_timer <= 0.0 and _lane_ids != _lane_seen:
                _lane_seen = _lane_ids
                _lane_timer = 4.0
                _all_t = list(villages.villages)
                _LANES.recut(_all_t, main_towns=visible_villages)
                if _LANES.ok(_all_t, village_mod.TRAVELLERS,
                             village_mod.PEOPLE):
                    _LANE_TOWNS = _LANES.towns_for(0)
                    _LANE_PEOPLE = _LANES.people_for(0)
                else:
                    # A LANE LOST A MAN, and this used to answer by stepping
                    # THE WHOLE WORLD instead: every town and every soul, from
                    # scratch, once a second. MEASURED, it is what froze the
                    # game for eighty-five seconds after the first frame and
                    # never stopped freezing.
                    #
                    # The cut is a partition of ownership and it is nearly
                    # right -- a handful of men fall outside it and the old
                    # answer was to throw the whole partition away for their
                    # sake. The repair is to HAND THE MISSING MEN BACK to the
                    # lane rather than to abandon it: same set in, a set
                    # difference out, and nobody is dropped.
                    _LANE_TOWNS = _LANES.towns_for(0)
                    _LANE_PEOPLE = _LANES.people_for(0)
                    _seen = set(map(id, _LANE_PEOPLE))
                    _missing = [m for m in village_mod.PEOPLE if id(m) not in _seen]
                    if _missing:
                        _LANE_PEOPLE = list(_LANE_PEOPLE) + _missing
                    if not _lane_warned:
                        _lane_warned = True
                        print("LANES: cut lost %d men -- handed back, not "
                              "re-cutting the world" % len(_missing))
            view_trees = trees.visible(cam_x, cam_y, vw, vh)
            view_ore = ore_field.visible(cam_x, cam_y, vw, vh)
            for village in visible_villages:        # 5 border guards per village
                if (getattr(village, "guards", None) is None
                        and math.hypot(village.x - player.x,
                                       village.y - player.y) < 6000.0):
                    loop = village.fence_rect.inflate(-218, -218)
                    guards = []
                    # Guards are posted along the wall, so a capital twice the
                    # size keeps twice as many -- same rule, read off the
                    # village's own scale.
                    many = 5 * int(round(village.scale / VILLAGE_SCALE))
                    for gi in range(many):
                        phase = gi / float(many)
                        gx0, gy0, gnx, gny = fence.perimeter_point(loop, phase)
                        guard = Soldier(gx0, gy0,
                                        village.nation, melee=False,
                                        seed=random.randint(0, 2 ** 31),
                                        color=nation_color(village.nation))
                        guard.guard_loop = loop
                        guard.guard_phase = phase
                        guard.guard_village = village
                        guard.hostile = getattr(village, "provoked", False)
                        guard.home = (guard.x, guard.y)
                        guards.append(guard)
                    village.guards = guards
                    enemies.extend(guards)
                # ... plus a 3-soldier patrol of the whole territory border.
                squad = getattr(village, "patrol", None)
                if squad is None:
                    if math.hypot(village.x - player.x,
                                  village.y - player.y) < 13000.0:
                        village.patrol = make_village_patrol(village)
                        village.patrol_timer = 30.0
                        enemies.extend(village.patrol)
                elif not any(s.alive for s in squad):
                    village.patrol_timer -= dt
                    if village.patrol_timer <= 0.0:      # squad wiped: respawn
                        village.patrol = make_village_patrol(village)
                        village.patrol_timer = 30.0
                        enemies.extend(village.patrol)
                village._assign_duty_bodies()
            house_colliders = [house.rect for village in visible_villages
                               for house in village.houses]
            house_colliders += [house.rect for house in built_houses]
            house_colliders += [w for village in visible_villages
                                for w in village.fence_walls]
            house_colliders += built_fences
            house_colliders += [v.board for v in visible_villages]
            house_colliders += [wp.rect for v in visible_villages
                                for wp in v.workplaces]
            house_colliders += [c.rect for c in view_ore]
            colliders = house_colliders + [tree.trunk_rect for tree in view_trees
                                           if not tree.felled]
            # THE HUBS, EVERY FRAME. This was inside the visible-village loop,
            # so a hub stepped only when a TOWN happened to be on screen -- out
            # in the wild it never ran at all, and its people starved between
            # visits. A settlement's day does not depend on being watched.
            try:
                hub_world.update(world_dt, now)
            except Exception:
                pass
            grid_timer -= dt
            if grid is None or grid_timer <= 0.0:
                grid_timer = 0.12
                grid = StaticGrid(96.0)      # index obstacles; query per NPC/tree
                for village in visible_villages:
                    for house in village.houses:
                        grid.add(house.rect)
                    for wall in village.fence_walls:
                        grid.add(wall)
                    grid.add(village.board)
                    for wp in village.workplaces:
                        grid.add(wp.rect)
                for house in built_houses:
                    grid.add(house.rect)
                for rect in built_fences:
                    grid.add(rect)
                for tree in view_trees:
                    if not tree.felled:
                        grid.add(tree.trunk_rect)
                for c in view_ore:
                    grid.add(c.rect)
            solids = [(house.rect, (150, 140, 120)) for village in visible_villages
                      for house in village.houses]
            solids += [(house.rect, (150, 140, 120)) for house in built_houses]
            solids += [(w, (140, 104, 60)) for village in visible_villages
                       for w in village.fence_walls]
            solids += [(rect, (140, 104, 60)) for rect in built_fences]
            # Fence walls a bullet may pass over when fired from right beside them.
            fence_ids = {id(w) for village in visible_villages
                         for w in village.fence_walls}
            fence_ids |= {id(r) for r in built_fences}
            solids += [(tree.trunk_rect, (118, 88, 48)) for tree in view_trees
                       if not tree.felled]
            solids += [(c.rect, (104, 104, 116)) for c in view_ore]
            # AND THE HUBS' WALLS. A hub is not in `villages`, so nothing that
            # walks the village list -- drawing, collision, crops -- knew it
            # was there, and the player walked straight through its fence.
            try:
                for _hub in hub_world.hubs:
                    if not view.colliderect(_hub.fence_rect):
                        continue
                    solids += [(w, (150, 108, 64)) for w in _hub.fence_walls]
                    solids += [(h.rect, (150, 140, 120)) for h in _hub.houses]
                    solids += [(wp.rect, (96, 92, 88)) for wp in _hub.workplaces]
            except Exception:
                pass
            solids += [(v.board, (120, 86, 52)) for v in visible_villages]
            solids += [(wp.rect, (96, 92, 88)) for v in visible_villages
                       for wp in v.workplaces]
            if not player.dead:
                player.x, player.y = resolve_circle_rects(
                    player.x, player.y, player.radius,
                    grid.near(player.x, player.y, player.radius + 6.0))

            for patrol in patrols:
                best = None
                bd = 3200.0
                for other in patrols:
                    if other is patrol or other.nation == patrol.nation:
                        continue
                    d = math.hypot(other.x - patrol.x, other.y - patrol.y)
                    if d < bd:
                        bd = d
                        best = (other.x, other.y)
                patrol.war_target = best
                patrol.update(dt)
            for rabbit in rabbits:
                rabbit.update(dt, None if player.dead else player, grid)
            enemy_grid.build([e for e in enemies if e.alive])
            soldier_grid.build([e for e in enemies
                                if e.alive
                                and getattr(e, "kind", "") == "soldier"])
            # THE BEASTS, PICKED OUT ONCE A FRAME. _predator_near() used to walk
            # the whole enemy list -- every wolf AND every soldier -- per man,
            # per tick, to find one wolf inside 420 px. A plain list, not a
            # grid: the grid measured SLOWER than the scan while the list was
            # short, and this is never slower and cannot grow with the wars.
            world.wolves = [e for e in enemies
                            if e.alive and getattr(e, "kind", "") == "wolf"]
            # The people of a besieged village must be TARGETABLE, not just
            # shootable: soldiers pick who to shoot from this grid, so leaving
            # the siege out of it meant a garrison could be shot at but never
            # chosen -- and a village could therefore never be emptied.
            # WHICH VILLAGES ARE UNDER SIEGE, taken straight from the armies
            # that are besieging them -- not from a variable computed
            # somewhere else a frame earlier. The people of a village being
            # stormed must be TARGETABLE, or an invading column stands in the
            # square unable to see anyone.
            sieges = [a.target for a in armies
                      if not a.done and a.target is not None]
            folk_grid.build([n for v in visible_villages
                             + [x for x in sieges if x not in visible_villages]
                             for n in v.npcs
                             if n.alive and not n.in_interior])
            # THE WORLD KNOWS YOUR FACE. Once word of a murderer has reached a
            # man -- by refugee, by trader, by the army at his gate -- he does
            # one of two things when he lays eyes on him, and nothing else:
            # with a gun or an axe he comes for you, and without one he runs.
            # This is deliberately unsubtle. A world that has been told does not
            # need to be provoked again by every fresh crime.
            for _n in list(folk_grid.near(player.x, player.y, 760.0)) + list(
                    village_mod.TRAVELLERS):
                if not getattr(_n, "alive", False):
                    continue
                if village_mod.PLAYER_ID not in getattr(_n, "knows", ()):
                    continue
                if (village_mod.story_cold(village_mod.PLAYER_ID, now)
                        and not getattr(_n, "witness_to", None)):
                    continue          # a dead rumour -- unless he saw it himself
                if math.hypot(_n.x - player.x, _n.y - player.y) > 760.0:
                    continue
                if _n.weapon is None:
                    _n.weapon = _n.arm()
                if _n.weapon:
                    _n.aggro = True
                    _n.panic = 0.0
                else:
                    _n.panic = max(_n.panic, 6.0)
                    _n.aggro = False

            # THE LIST THE WORLD WALKS, assembled HERE, at the loop, out of
            # the armies themselves. An army that is merely *meant* to be in
            # some shared roster is an army that does not shoot and is not
            # noticed by the village it is standing in -- which is exactly
            # what happened. Built here, from the armies, it cannot be absent.
            enemies[:] = [e for e in enemies if not getattr(e, "in_army", False)]
            for _a in armies:
                if _a.done:
                    continue
                for _s in _a.soldiers:
                    if _s.alive and not getattr(_s, "settled", False):
                        enemies.append(_s)
            # ...and the standing army: bodies on the capital's streets
            for _s in war.STANDING:
                if _s.alive:
                    enemies.append(_s)
            for enemy in enemies:
                if enemy.alive:
                    # A marching column out in the open is walked by war.march
                    # and needs nothing else this frame. Only a column in
                    # contact -- at a wall, or meeting another -- costs the
                    # frame rate. Same war, a fraction of the work.
                    if (getattr(enemy, "in_army", False)
                            and not getattr(enemy, "in_contact", False)):
                        continue
                    if (getattr(enemy, "guard_village", None) is not None
                            and math.hypot(enemy.x - player.x,
                                           enemy.y - player.y) > 4200.0):
                        continue                # made once; only walks while you're near
                    if (getattr(enemy, "patrol_center", None) is not None
                            and math.hypot(enemy.x - player.x,
                                           enemy.y - player.y) > 13000.0):
                        continue                # patrols only walk while near
                    # The ground does not move. Rebuilding one soldier's view
                    # of the trees, the village lattice, the occluders and the
                    # colliders every frame cost 106 ms with four hundred men
                    # on the field. It is the same answer for everybody in the
                    # same stretch of ground, so it is worked out once and
                    # handed round.
                    _ekey = (int(enemy.x // ENV_CELL), int(enemy.y // ENV_CELL),
                             _BUILD_VER[0], len(built_houses), len(built_fences),
                             len(built_gates))
                    _cached = ENV_CACHE.get(_ekey)
                    if _cached is None:
                        enemy_foliage = trees.foliage(enemy.x, enemy.y)
                        e_trees = trees.near(enemy.x, enemy.y, 480.0)
                        e_villages = villages.visible(enemy.x - 700.0,
                                                      enemy.y - 700.0, 1400, 1400)
                        e_occluders = [house.sight_rect for v in e_villages
                                       for house in v.houses]
                        e_occluders += [tree.trunk_rect for tree in e_trees
                                        if not tree.felled]
                        e_occluders += [house.sight_rect for house in built_houses]
                        # COLLISION IS LOCAL. A man is 14 px across: the only
                        # walls that can touch him are the ones beside him.
                        # Handing every soldier the whole village -- ninety
                        # houses, every wall run, fifty trunks -- made steering
                        # crawl and stall, and cost 400 x 100 rect tests twice
                        # a frame. He gets the ones within a few paces.
                        cbox = pygame.Rect(int(enemy.x) - 210, int(enemy.y) - 210,
                                           420, 420)
                        e_colliders = [house.rect for v in e_villages
                                       for house in v.houses
                                       if house.rect.colliderect(cbox)]
                        e_colliders += [house.rect for house in built_houses
                                        if house.rect.colliderect(cbox)]
                        e_colliders += [w for v in e_villages
                                        for w in v.fence_walls
                                        if w.colliderect(cbox)]
                        e_colliders += [r for r in built_fences
                                        if r.colliderect(cbox)]
                        # trunks close enough to be walked into, not the grove
                        e_colliders += [tree.trunk_rect
                                        for tree in trees.near(enemy.x, enemy.y,
                                                               190.0)
                                        if not tree.felled]
                        _cached = (enemy_foliage, e_trees, e_villages,
                                   e_occluders, e_colliders)
                        if len(ENV_CACHE) > 4000:
                            ENV_CACHE.clear()
                        ENV_CACHE[_ekey] = _cached
                    enemy_foliage, e_trees, e_villages, e_occluders, e_colliders = _cached
                    if enemy.kind == "wolf":       # gates keep wolves out, not people
                        e_colliders = e_colliders + built_gates
                    enemy._rects = e_colliders
                    enemy._fences = e_villages
                    enemy.friendly = (player.nation is not None
                                      and getattr(enemy, "nation", None)
                                      == player.nation)
                    # Only the men near enough to be in the way of a shot.
                    # Handing every soldier the whole army list meant each
                    # shot scanned four hundred men -- 160,000 segment tests
                    # a frame, and the frame rate on the floor.
                    enemy._soldiers = enemy_grid.near(enemy.x, enemy.y, 560.0)
                    enemy._player = player
                    enemy._blood = blood
                    mt = getattr(enemy, "march_target", None)
                    if mt is not None and not getattr(enemy, "in_army", False):
                        hv = getattr(enemy, "home_village", None)
                        goal = mt
                        # AN ARMY GOES IN BY THE GATE. Marching at the middle
                        # of a walled village just walks men into the palisade:
                        # they pile up outside, the people are 2600 px away at
                        # the square, and neither side can see the other -- so
                        # the siege never starts at all. The column heads for
                        # the nearest gate, gets inside, and then goes for the
                        # square.
                        tv = getattr(enemy, "march_village", None)
                        if tv is not None and not tv.fence_rect.collidepoint(
                                enemy.x, enemy.y):
                            gside, gxw, gyw = fence.nearest_gate(tv, enemy.x, enemy.y)
                            gox, goy = fence.OUTWARD[gside]
                            goal = (gxw - gox * 120.0, gyw - goy * 120.0)
                        if hv is not None and hv.fence_rect.collidepoint(enemy.x,
                                                                        enemy.y):
                            gwx, gwy = fence.gate_world(hv)
                            gox, goy = fence.gate_outward(hv)
                            goal = (gwx + gox * 110.0, gwy + goy * 110.0)
                        ux, uy = steering.steer(enemy, goal[0], goal[1],
                                                e_colliders, e_villages)
                        enemy.x += ux * 240.0 * dt
                        enemy.y += uy * 240.0 * dt
                        enemy.facing = (ux, uy)
                        if math.hypot(mt[0] - enemy.x, mt[1] - enemy.y) < 130.0:
                            enemy.march_target = None
                            enemy.march_village = None
                    # Re-picking a target is the most expensive thing a
                    # soldier does, and a man does not need to re-decide who
                    # he is shooting twenty times a second. Four times is
                    # plenty; a corpse or an empty field forces an immediate
                    # rethink.
                    enemy._retarget = getattr(enemy, "_retarget", 0.0) - dt
                    tgt = getattr(enemy, "_target", None)
                    if (enemy._retarget <= 0.0 or tgt is None
                            or not getattr(tgt, "alive", True)
                            or getattr(tgt, "dead", False)):
                        tgt = choose_target(enemy, e_villages)
                        enemy._target = tgt
                        enemy._retarget = 0.2
                    enemy.update(dt, tgt, combat, e_occluders,
                                 1.0 - 0.25 * enemy_foliage,
                                 1.0 - 0.2 * enemy_foliage,
                                 colliders=e_colliders)
                    enemy.x, enemy.y = resolve_circle_rects(
                        enemy.x, enemy.y, enemy.radius, e_colliders)

            for village in visible_villages:
                for npc in village.npcs:
                    npc._soldiers = enemies
                    npc._player = player
            # The world tick -- villagers, crops and village state -- runs a
            # few times a second, not every frame. Only combat needs the full
            # frame rate. The accumulated dt keeps time honest.
            world_accum += dt
            world_tick = world_accum >= WORLD_STEP
            if world_tick:
                world_dt = world_accum
                world_accum = 0.0
                # The crown's wars. A capital whose purse is deep enough calls
                # up its nation's idle men once a day; the column then marches,
                # fights, and either takes the village or comes home.
                _wd = int(now / DAY_LENGTH)
                for _army in war.declare(villages, _wd, now):
                    armies.append(_army)
                    toast("%s calls up %d men and marches on %s"
                          % (_army.capital.name, _army.start,
                             _army.target.name))
                # RECONCILE. Every living soldier of every army must be in the
                # list the world walks, every tick, no matter which path put him
                # there. Trusting a single extend() at muster time meant the
                # whole war could sit in a field and never be simulated at all.
                _arr, _die = village_mod.refugees_on_the_road(now, enemies)

                # THE TEST OF STRENGTHS. The King and the mayors fight for the
                # crown in the capital, unarmed, in front of the town. One at a
                # time, on the day, and the winner wears it.
                # MAYOR ELECTIONS ARE TOMORROW. A notice, the day before, in
                # the place a man already looks for "too far away" -- a village
                # keeps its own calendar and there is no other way to know.
                if int(now / economy.DAY_LENGTH) != getattr(player, "_elec_warn", -2):
                    player._elec_warn = int(now / economy.DAY_LENGTH)
                    for _v in villages.visible(player.x - 640.0, player.y - 640.0,
                                               1280, 1280):
                        if economy.election_tomorrow(_v, int(now / economy.DAY_LENGTH)):
                            toast("%s votes for a mayor TOMORROW" % _v.name)
                            break
                hear_news()                     # the news arrives where you are
                tick_news(dt)
                _kday = int(now / economy.DAY_LENGTH)
                _cap = next((v for v in villages.villages
                             if getattr(v, "is_capital", False)
                             and (player.nation is None
                                  or getattr(v, "nation", None) == player.nation)),
                            None)
                if _tourney[0] is not None:
                    _tourney[0].tick(world_dt, combat)
                    if _tourney[0].done:
                        player.duel_tournament = None
                        _tourney[0] = None
                if _cap is not None and _tourney[1] != _kday:
                    # THE CROWN'S CALENDAR -- every KING_ELECTION_DAYS, and a
                    # test game holds one at once so it can be watched.
                    _due = (_kday - _cap.code) % economy.KING_ELECTION_DAYS == 0
                    # `_tourney[1] < 0`, not `not _tourney[1]`: the day
                    # counter is -1 before the first one, and `not -1` is
                    # False -- so the test hook was dead the moment I stopped
                    # using a boolean for a day number.
                    if _due or (test_mode and _tourney[1] < 0):
                        _cands = _cap.candidates_for_crown()
                        # A MAYOR FIGHTS FOR THE CROWN. He is not an NPC, so he
                        # is put in the field by hand and marked as the man the
                        # tournament must not drive -- his own hands do that.
                        _me_in = getattr(player, "job", None) == "mayor"
                        if _me_in:
                            _cands.append(player)
                        if len(_cands) >= 2:
                            _tourney[1] = _kday
                            _tourney[0] = tournament.Tournament(_cap, _cands)
                            _tourney[0].player = player if _me_in else None
                # THE DAY BEFORE. A mayor is told, because a mayor has a stake:
                # the crown is fought for tomorrow and he may be in the ring.
                if (getattr(player, "job", None) == "mayor" and _cap is not None
                        and getattr(player, "_k_warn", -2) != _kday):
                    player._k_warn = _kday
                    if (_kday + 1 - _cap.code) % economy.KING_ELECTION_DAYS == 0:
                        toast("The tournament for the next king will commence "
                              "tomorrow, in the capital")


                # TAXES -- AND ONLY THE PLAYER PAYS THEM THIS WAY. The
                # villagers have their own books (economy.tax_day) and are
                # untouched by any of this. A PLAYER who has taken a post owes
                # the village a hundred coin every three days, unless he is
                # under arms or the mayor. Fail and he is not a trader, or a
                # logger, or a smith: he is nobody -- and if he is standing in
                # the village when they work it out, they will shoot.
                # NO COIN LEVY AND NO BANISHMENT FOR THE PLAYER. He pays the
                # same tax as every villager -- a fifth of what he produces,
                # in kind, taken out of his pack as he works (see pay_share).
                # A flat 100 coin every three days was a WEALTH tax charged to
                # a man who had just been hired: at WAGE = 10 a day a board
                # post earned 30 and owed 100, so taking a job was a net loss
                # and then an exile for being poor. There is nothing to check
                # any more, because the share is taken before he can forget it.

                # DESERTION. A soldier who wanders off from his column -- or
                # from the village he was given -- has left the service, and
                # the nation says so. A TRADER is exempt from the distance
                # rule: a trader's whole trade is being somewhere else, and he
                # settles up with the ledger instead.
                _desert = False
                if _pl_serving := (player.nation is not None):
                    _home = None
                    if player.settled_at is not None:
                        _home = (player.settled_at.x, player.settled_at.y,
                                 player.settled_at.radius + DESERT_PX)
                    elif getattr(player, "army", None) is not None:
                        _live = [s for s in player.army.soldiers
                                 if s.alive and not getattr(s, "settled", False)]
                        if player.army.done or not _live:
                            player.army = None
                        else:
                            _home = (sum(s.x for s in _live) / len(_live),
                                     sum(s.y for s in _live) / len(_live),
                                     DESERT_PX)
                    if _home is not None and _home[2] > 0.0:
                        _far = math.hypot(player.x - _home[0],
                                          player.y - _home[1]) > _home[2]
                        player._away = player._away + world_dt if _far else 0.0
                        if (player._away > DESERT_SECONDS
                                and (player.job or "") != "trader"):
                            _desert = True
                if _desert:
                    toast("You have deserted.   %s wants nothing to do with you"
                          % nation_name(player.nation))
                    banish(player.nation)
                    player.nation = None
                    player.army = None
                    player.wage = 0
                    player.settled_at = None
                    player.job = None
                    player._away = 0.0
                # A CIVILIAN'S WAGE. A man who took a post off a village
                # notice board is paid by the village that hired him -- every
                # day, out of its OWN ledger, with no crown war chest standing
                # between them. A soldier is still paid by his capital below;
                # this is for the farmer, the logger, the smith and the rest.
                _employer = getattr(player, "settled_at", None)
                _trade = getattr(player, "job", None)
                if (_employer is not None and _trade in _BOARD_TRADES
                        and getattr(player, "army", None) is None
                        and getattr(player, "_pay_day", -1) != _wd):
                    player._pay_day = _wd
                    _wage = int(getattr(player, "wage", 0))
                    if _wage > 0 and _employer.ledger_coins >= _wage:
                        _employer.ledger_coins -= _wage
                        inventory.add("coin", _wage)
                        toast("Pay   +%d coin   %s" % (_wage, _employer.name))
                # A SOLDIER'S PAY, for a soldier who is a player.
                if (player.nation is not None and getattr(player, "wage", 0) > 0
                        and getattr(player, "_pay_day", -1) != _wd):
                    player._pay_day = _wd
                    for _v in villages.villages:
                        if not (_v.is_capital and _v.nation == player.nation):
                            continue
                        if _v.ledger_coins - economy.CROWN_BUFFER >= player.wage:
                            _v.ledger_coins -= player.wage
                            inventory.add("coin", player.wage)
                            toast("Pay   +%d coin" % player.wage)
                        break
                # ...and whatever share of the plunder is waiting for him.
                _pend = getattr(player, "loot_pending", 0)
                if _pend > 0:
                    player.loot_pending = 0
                    inventory.add("coin", _pend)
                    toast("Your share of the plunder   +%d coin" % _pend)
                for _it in list(getattr(player, "loot_items", ())):
                    inventory.add(_it, 1)
                    toast("Looted   +1 %s" % _it)
                player.loot_items = []
                # THE TOOLS OF THE TRADE, handed over when a post is taken.
                for _it, _qty in list(getattr(player, "kit_pending", ())):
                    inventory.add(_it, _qty)
                if getattr(player, "kit_pending", None):
                    toast("Tools for the %s   -   %s"
                          % (player.job or "post",
                             ", ".join("%d %s" % (q, i)
                                       for i, q in player.kit_pending)))
                    player.kit_pending = []
                for _army, _res, _info in war.update(armies, world_dt, now):
                    if _res == "taken":
                        toast("%s has fallen to %s   +%d coins of spoils"
                              % (_army.last_name, _army.capital.name, _info))
                    elif _res == "march":
                        toast("%s's army marches on %s"
                              % (_army.capital.name, _info.name))
                    elif _res == "reinforced":
                        enemies.extend(_info)
                        toast("%d men march out to join %s's army"
                              % (len(_info), _army.capital.name))
                    elif _res == "broken":
                        toast("%s's army is broken and straggles home"
                              % _army.capital.name)
                # a soldier who has settled in a taken village, or gone home,
                # is no longer a body on the map
                for _army in armies:
                    for _s in list(_army.soldiers):
                        if _s in enemies and (getattr(_s, "settled", False)
                                              or getattr(_s, "disbanded", False)):
                            enemies.remove(_s)
                armies = [a for a in armies if not a.done]
            # Villages with an army at the gate are live ground: their guards
            # shoot, their people run for the gates, the fight happens in the
            # world where the player can ride over and watch it. Without this
            # a siege could never resolve, because a village that nobody is
            # looking at does not tick.
            # EVERY TOWN, EVERY TICK -- NOT ONLY THE ONES ON SCREEN.
            #
            # This read `visible_villages + sieges`, and the comment above it
            # admitted the consequence out loud: "a village that nobody is
            # looking at does not tick." So wages, tax, the granary, the
            # elections, the daily census and the births ran only in the three
            # or four towns inside the camera -- while EVERY MAN in the world
            # ticked (see the PEOPLE loop below). The people were alive and
            # their towns were frozen: prices never moved, nobody was paid,
            # nothing was harvested into a store that was not on screen.
            #
            # The world is laid out before the first step (load_world), so this
            # is a lookup and not a build, and a town's update is day-guarded
            # almost everywhere it matters.
            # ON TRIAL: every town steps now, to prove the loan loop is dead.
            # one game day -- the same man borrowing 32 coin over and over
            # inside hundredths of a day, the ledger drained, and the world
            # went 1043 -> 128. `place_orders` and `tool_loan` were only ever
            # run for towns that ticked; making every town tick runs them for
            # every man in the world, and the "one loan at a time" guard does
            # not hold. THE GOAL IS STILL EVERY TOWN, EVERY TICK -- but the
            # loan path has to be fixed first or the world starves of it.
            _pt0 = time.perf_counter()
            for village in _LANE_TOWNS:
                if not world_tick:
                    break
                if village in sieges:
                    world.enemies = enemies
                # THE TOWN DECIDES FOR ITSELF WHETHER A WAR IS AT ITS GATE.
                # It no longer picks a threat for its people -- a man finds
                # what he can see for himself (see nearest_hostile below).
                hostile_near = False
                for e in enemies:
                    if (e.alive and e.kind == "soldier"
                            and e.nation != village.nation):
                        if math.hypot(e.x - village.x, e.y - village.y) < village.radius:
                            hostile_near = True
                            break
                if (not player.dead and player.nation is not None
                        and player.nation != village.nation
                        and math.hypot(player.x - village.x,
                                       player.y - village.y) < village.radius):
                    hostile_near = True
                # AN ARMY AT THE GATE IS A PROVOCATION. This was computed and
                # then thrown away -- there was no provoke() call at all -- so
                # a village being stormed never turned hostile: its guards
                # never raised a weapon and its people never fought back. It is
                # why an invading column could stand in the square indefinitely
                # with four defenders 280 px away doing nothing.
                if hostile_near and not village.provoked:
                    village.provoke()
                # THE ARMY AT THE GATE IS TOLD WITH EVERYBODY ELSE. A column
                # standing in a town hears what the townsfolk hear, and a
                # murderer it has been told about becomes its business.
                if village.killers:
                    for _e in enemies:
                        if _e.alive and getattr(_e, "kind", "") == "soldier":
                            _e.forget(now)
                        if (_e.alive and getattr(_e, "kind", "") == "soldier"
                                and math.hypot(_e.x - village.x,
                                               _e.y - village.y) < village.radius):
                            if _e.learn(village.killers, now):
                                _e.hostile = True
                                _e.aware = True
                                _e.aware_timer = 60.0
                # ALL THE SOLDIERS ARE DEAD: the town empties. This is the
                # mouth of the whole system -- the people who watched you do it
                # run to the next town, and tell them on the way in.
                if (village.provoked and not getattr(village, "_exodus", False)
                        and not any(b.alive for b in village.defenders())):
                    village._exodus = True
                    _dests = war.friendly_neighbours(villages, village)
                    if _dests:
                        war.rout(village, _dests, now)
                village.update(world_dt, world, now, day_phase())
                key = (village.gx, village.gy)
                if key not in seeded_villages:       # plant their back gardens
                    seeded_villages.add(key)
                    _vt = float(biomes.temperature(village.x, village.y, world.seed))
                    _vh = float(biomes.humidity(village.x, village.y, world.seed))
                    food, leaf = biomes.crop_kinds(_vt, _vh)
                    for house in village.houses:
                        for tx, ty in house.garden:
                            # FOOD AND NOTHING ELSE. A backyard used to be an
                            # even mix of the local crops -- half of every
                            # garden in the world was tobacco, and every
                            # household was quietly a supplier. Inside a
                            # settlement the state permits what feeds people.
                            # Leaf is grown where the state is not.
                            kind = food
                            world.set_plot(tx, ty, kind, -1000.0)
                            ground.invalidate_tile(tx, ty)
                            village_plots.add((tx, ty))
                    # The communal 5x5 crop plots on the inner border ring.
                    for ctx, cty, kind in getattr(village, "farm_plots", ()):
                        # dual culture: every cell carries its own crop kind
                        for tx, ty, tkind in village.farm_tiles[(ctx, cty)]:
                            world.set_plot(tx, ty, tkind, now - 6.0)
                            ground.invalidate_tile(tx, ty)
                            village_plots.add((tx, ty))

            _pt1 = time.perf_counter()
            _PH["v"] += _pt1 - _pt0
            _pt2 = _pt1                         # in case world_tick is off
            # A village with a trader on the road to it keeps ticking even when
            # it is far away -- otherwise it has nothing to sell him.
            if world_tick:
                visible_keys = {(v.gx, v.gy) for v in visible_villages}
                # Rebuild the list of villages that need ticking: only the ones
                # a trader is actually walking to. This was add-only, so the set
                # grew without end and every world tick simulated more and more
                # distant villages -- the lag crept in as the caravans ran.
                live = set()
                pool = list(visible_villages)
                # NO trade_active SET. It existed only to decide which extra
                # towns needed stepping so a trader's target kept walking
                # off-screen. Every town is stepped now, and every man walks
                # himself, so there is nothing to guess at.
            # Characters are solid: villagers spread apart, and the player
            # cannot walk through anyone.
            npcs = [npc for village in visible_villages
                    for npc in village.npcs
                    if npc.alive and not npc.asleep and not npc.in_interior]
            sim_view = pygame.Rect(cam_x - 220, cam_y - 220, vw + 440, vh + 440)
            active = []
            for npc in npcs:
                on_screen = sim_view.collidepoint(npc.x, npc.y)
                npc._rects = grid if on_screen else ()
                npc._fences = visible_villages if on_screen else ()
                npc.friendly = (player.nation is not None
                                and npc.nation == player.nation)
                if on_screen:
                    active.append(npc)
            resolve_circle_pairs(active, NPC_SPACING)
            for npc in active:
                npc.x, npc.y = resolve_circle_rects(
                    npc.x, npc.y, npc.radius,
                    grid.near(npc.x, npc.y, npc.radius + 6.0))
            for enemy in enemies:
                if enemy.alive:
                    resolve_circle_out_of(enemy, active)
            if not player.dead:
                resolve_circle_out_of(player, active)
                for enemy in enemies:
                    if enemy.alive:
                        resolve_circle_out_of(player, [enemy])
                player.x, player.y = resolve_circle_rects(
                    player.x, player.y, player.radius,
                    grid.near(player.x, player.y, player.radius + 6.0))

            combat.update(dt)

            # -- hit resolution ---------------------------------------------
            combatants = [] if player.dead else [(player, "player")]
            for enemy in enemies:
                if enemy.alive:
                    combatants.append((enemy, enemy.team))
            for rabbit in rabbits:
                if rabbit.alive:
                    combatants.append((rabbit, rabbit.team))
            for village in visible_villages + [v for v in sieges
                                               if v not in visible_villages]:
                for npc in village.npcs:
                    if npc.alive and not npc.asleep and not npc.in_interior:
                        combatants.append((npc, ("nation", npc.nation)))
            body_grid = TeamGrid(300.0)
            body_grid.build([o for o, _t in combatants])
            dict_team = {id(o): t for o, t in combatants}
            for bullet in combat.bullets:
                if bullet.remove:
                    continue
                # A shot travels a few pixels in a frame; only bodies within
                # reach of that little segment can possibly be hit. Sweeping
                # every bullet against every man on the field was 67 ms.
                _mx = (bullet.prev_x + bullet.x) * 0.5
                _my = (bullet.prev_y + bullet.y) * 0.5
                _reach = (math.hypot(bullet.x - bullet.prev_x,
                                     bullet.y - bullet.prev_y) * 0.5 + 48.0)
                for obj in body_grid.near(_mx, _my, _reach):
                    team = dict_team.get(id(obj))
                    if team is None:
                        continue
                    if team == bullet.team:
                        continue
                    if not segment_circle_hit(bullet.prev_x, bullet.prev_y,
                                              bullet.x, bullet.y,
                                              obj.x, obj.y, obj.radius):
                        continue
                    # A CARAVAN IS NOT A TARGET, and a stray round does not
                    # change that. The player's own shots are his business.
                    if bullet.shooter is not player and is_trader(obj):
                        continue
                    if obj is player:
                        player.take_damage(bullet.damage)
                        blood.spawn(player.x, player.y, 7, 14.0)
                        bullet.remove = True
                        break
                    died = obj.take_damage(bullet.damage)
                    if died:
                        _loot(bullet.shooter, obj)
                    blood.spawn(obj.x, obj.y,
                                20 if died else 7, 24.0 if died else 14.0)
                    if (bullet.team == "player" and player.nation is not None
                            and getattr(obj, "nation", None) == player.nation):
                        banish(player.nation)
                    if obj.kind == "rabbit":
                        if died:
                            amount = random.randint(1, 2)
                            inventory.add("raw_meat", amount)
                            toast(f"Shot a rabbit   +{amount} raw meat")
                    elif obj.kind == "villager":
                        if (obj.village is not None
                                and not village_mod.self_defence(obj)):
                            if died and bullet.shooter is player:
                                obj.village.learn_killers(
                                    (village_mod.PLAYER_ID,), now)
                                _see_murder(obj)
                            obj.village.provoke()
                        if died:
                            kills += 1
                    bullet.remove = True
                    break

                if bullet.remove:
                    continue
                # Bullets stop on solid world geometry: tree trunks and walls.
                bx0 = min(bullet.prev_x, bullet.x) - 1.0
                bx1 = max(bullet.prev_x, bullet.x) + 1.0
                by0 = min(bullet.prev_y, bullet.y) - 1.0
                by1 = max(bullet.prev_y, bullet.y) + 1.0
                for rect, colour in solids:
                    if (rect.right < bx0 or rect.left > bx1
                            or rect.bottom < by0 or rect.top > by1):
                        continue
                    if segment_rect_hit(bullet.prev_x, bullet.prev_y,
                                        bullet.x, bullet.y, rect):
                        if id(rect) in fence_ids:
                            # Shooter was standing at the fence: the shot clears it.
                            fx = max(rect.left - bullet.origin_x, 0.0,
                                     bullet.origin_x - rect.right)
                            fy = max(rect.top - bullet.origin_y, 0.0,
                                     bullet.origin_y - rect.bottom)
                            if math.hypot(fx, fy) <= 150.0:
                                continue
                        combat.spawn_impact(bullet.x, bullet.y, colour)
                        bullet.remove = True
                        break

            # -- the dead do not come back; the world stays populated -------
            for enemy in enemies[:]:
                if not enemy.alive:
                    blood.spawn(enemy.x, enemy.y, 22, 26.0)
                    enemies.remove(enemy)
                    kills += 1
            for rabbit in rabbits[:]:
                if not rabbit.alive:
                    rabbits.remove(rabbit)
            for village in visible_villages:
                if any(not npc.alive for npc in village.npcs):
                    village.last_death = now          # births wait for peace
                    village.npcs = [npc for npc in village.npcs if npc.alive]

            patrols[:] = [p for p in patrols if any(m.alive for m in p.members)]
            spawn_timer -= dt
            if spawn_timer <= 0.0:
                spawn_timer = 5.0
                live_soldiers = sum(1 for e in enemies
                                    if e.kind == "soldier" and e.alive)
                live_wolves = sum(1 for e in enemies
                                  if e.kind == "wolf" and e.alive)
                if live_wolves < 4:
                    spawn_wolf()
                if sum(1 for r in rabbits if r.alive) < 6:
                    spawn_rabbit()
            # A NATION FILLS ITS OWN HOLES. Every few seconds each nation looks
            # down its list of towns, and sends men with no trade to the ones
            # short of hands. A village that has been emptied therefore fills
            # back up -- slowly, with strangers, while the player is elsewhere.
            # ---------------- THE PEOPLE, ONCE EACH ----------------------
            # Not the visible ones, not the off-screen ones, not the ones some
            # town thinks a trader might be walking toward -- the people. One
            # flat register, walked once per tick, each man stepping himself.
            # The town is what he calls when he wants the granary or the bank.
            if world_tick:
                _dead_here = False
                # A SNAPSHOT, because a birth appends to that very list. Walking
                # it live meant a child born mid-walk extended the walk, and a
                # village pair bearing children could keep it going for ever --
                # which is the hang. A child born now takes his first step next
                # tick, like everybody else who was not here at the start of it.
                # DAY_PHASE IS ONE ANSWER FOR EVERYBODY. It was evaluated
                # inside this loop, once per man, and day_phase() itself calls
                # night_factor() -- so the phase of the day and the height of
                # the sun were recomputed 590 times a frame, for a value that
                # cannot differ between one man and the next. One call, one
                # tick, handed to every man. Measured 1.9 ms a frame.
                _pt2 = time.perf_counter()
                _PH["m"] += _pt2 - _pt1
                _phase = day_phase()
                for _n in _LANE_PEOPLE:
                    if not _n.alive:
                        _dead_here = True
                        continue
                    try:
                        if not _n.tick(world_dt, world, now, _phase,
                                       combat, night, colliders, nearest_hostile):
                            _dead_here = True
                    except Exception:
                        # ONE MAN'S BUG IS NOT A DEATH SENTENCE. This set
                        # alive = False, which silently EXECUTED a man for a
                        # programming error -- it killed 73 miners over a
                        # missing attribute, and then more than half the world.
                        # He is skipped for this tick instead, and each distinct
                        # error is printed once so it can actually be found.
                        import traceback as _tb
                        _e = _tb.format_exc()
                        if _e not in _NPC_ERRORS:
                            _NPC_ERRORS.add(_e)
                            sys.stderr.write("\n--- NPC TICK ERROR (man skipped, not killed) ---\n" + _e)
                            sys.stderr.flush()
                if _dead_here:
                    village_mod.PEOPLE[:] = [n for n in village_mod.PEOPLE
                                             if n.alive]

            _pt3 = time.perf_counter()
            _PH["n"] += _pt3 - _pt2
            if time.time() - _PH["t"] >= 30.0:
                _fr = max(1, _PH["f"])
                _tot = max(1e-9, _PH["v"] + _PH["m"] + _PH["n"])
                sys.stderr.write(
                    "PHASE  towns %6.2f ms/f (%4.1f%%)   men %6.2f ms/f (%4.1f%%)"
                    "   between %6.2f ms/f   [%.0f fps]\n"
                    % (_PH["v"] / _fr * 1000.0, 100.0 * _PH["v"] / _tot,
                       _PH["n"] / _fr * 1000.0, 100.0 * _PH["n"] / _tot,
                       _PH["m"] / _fr * 1000.0,
                       _fr / max(1e-9, time.time() - _PH["t"])))
                sys.stderr.flush()
                _PH.update(v=0.0, m=0.0, n=0.0, f=0, t=time.time())

            # ---------------- THE HOUSES, ONCE A SECOND ------------------
            # A household's larder is the household's. Same once-a-second it
            # was always done at, driven now from the register of houses rather
            # than from inside whichever town happens to contain them.
            house_timer -= dt
            if house_timer <= 0.0:
                house_timer = 1.0
                for _h in list(village_mod.HOUSES):
                    _h.tick(1.0)

            settle_timer -= dt
            if settle_timer <= 0.0:
                settle_timer = 12.0
                villages.send_idle(now)
            # A CARAVAN AND A COLUMN. Traders work the same roads the armies
            # march on, and the free-trade policy is the only thing that lets
            # them cross a war unshot -- so this is where word of a campaign
            # gets off the road and into the hands that want it.
            for _tr in list(village_mod.TRAVELLERS):
                if (not getattr(_tr, "alive", False)
                        or getattr(_tr, "job", None) != "trader"
                        or getattr(_tr, "trade_state", "none") == "none"):
                    continue
                for _a in armies:
                    if _a.done or getattr(_a, "engage", False):
                        continue          # never during a battle: they scatter
                    _lead = _a.soldiers[0] if _a.soldiers else None
                    if _lead is None or not _lead.alive:
                        continue
                    if math.hypot(_tr.x - _lead.x, _tr.y - _lead.y) > 300.0:
                        continue
                    _meet_army(_tr, _a, now)
            # THE CROWN ASKS, once a day: its strongest column's last five
            # days, and three days for a rider to bring the answer.
            demand_timer -= dt
            if demand_timer <= 0.0:
                demand_timer = DAY_LENGTH
                for _v in villages.villages:
                    # ONLY WHEN THERE IS NO OFFER OUT. Re-posting every day
                    # made the crown's offer perpetual, and a deadline that
                    # never arrives is not a deadline.
                    _d = getattr(_v, "demand", None)
                    if (getattr(_v, "is_capital", False)
                            and (_d is None or now > _d["expires"])):
                        war.post_demand(_v, armies, now)   # a lapsed offer is
                        # replaced: the crown asks again, and again, until it
                        # is told. Without this it asked once and went quiet.
            enemies[:] = [e for e in enemies
                          if getattr(e, "follow", False)
                          or getattr(e, "guard_village", None) is not None
                          or getattr(e, "patrol_center", None) is not None
                          or math.hypot(e.x - player.x, e.y - player.y) < 6500.0]
            rabbits[:] = [r for r in rabbits
                          if math.hypot(r.x - player.x, r.y - player.y) < 3200.0]

            # -- battle, plunder, conquest ----------------------------------
            if player.nation is not None:
                for village in visible_villages:
                    if village.conquered or village.nation == player.nation:
                        continue
                    if village.chaos > 0.0:                 # already plundering
                        continue
                    near = math.hypot(player.x - village.x,
                                      player.y - village.y) < village.radius
                    if not near:
                        near = any(s.alive and math.hypot(s.x - village.x,
                                                          s.y - village.y)
                                   < village.radius for s in player.squad)
                    if near or village.battle:
                        if any(n.alive and n.defender for n in village.npcs):
                            village.battle = True
                            village.provoke()
                        else:                           # won: 3 minutes to loot
                            village.battle = False
                            village.plundered = True
                            village.chaos = 180.0
                            active_chaos.append(village)
                            for h in village.houses:
                                if not getattr(h, "door_broken", False):
                                    h.enterable = True
                                    h.interior = Interior(random.randint(0, 2 ** 31),
                                                          tuple(h.facing))
                                    fill_loot(h.interior.chest)
                                    h.break_door()
                            loot = random.randint(5, 20)
                            inventory.add("coin", loot)
                            inventory.add("tobacco", random.randint(6, 16), 6)
                            toast(f"Battle won!   Plunder for 180s   +{loot} coins")

            # -- wounded characters leave a blood trail ---------------------
            if player.bleed > 0.0 and not player.dead:
                player_drip -= dt
                if player_drip <= 0.0:
                    blood.drip(player.x, player.y, 2)
                    player_drip = 0.28
            else:
                player_drip = 0.0
            for enemy in enemies:
                if enemy.bleed > 0.0:
                    enemy.drip_timer -= dt
                    if enemy.drip_timer <= 0.0:
                        blood.drip(enemy.x, enemy.y, 2)
                        enemy.drip_timer = 0.30
            for village in visible_villages:
                for npc in village.npcs:
                    if npc.bleed > 0.0:
                        npc.drip_timer -= dt
                        if npc.drip_timer <= 0.0:
                            blood.drip(npc.x, npc.y, 2)
                            npc.drip_timer = 0.30

            blood.update(dt)

            # THE CAMERA FOLLOWS WHAT IS BEING WATCHED -- INCLUDING THE EASE.
            #
            # This eased toward player.x/player.y, which UNDID the watching
            # override set below it: the camera was put on the watched man and
            # then dragged back toward the parked player sixty thousand pixels
            # away, a little every frame. The ground streamed after a point that
            # was crawling off the man, so the view drifted and the scenery
            # arrived in the wrong place. The smoothing belongs to whoever the
            # view belongs to.
            _wt = observer_.target
            _watch = _wt is not None and getattr(_wt, "alive", False)
            _fx = _wt.x if _watch else player.x
            _fy = _wt.y if _watch else player.y
            # WHEN THE WATCH CHANGES, BUILD THE GROUND UNDER HIM **NOW**.
            #
            # The worker streams chunks behind the camera and it keeps up with a
            # man walking. It does NOT keep up with a camera that has just
            # jumped a hundred thousand pixels to another village, so the view
            # showed whatever happened to be built -- which is why watching
            # somebody looked wrong at the edges and nothing like the quality
            # around the player. This is exactly what refresh_around() is for
            # ("build the ground under the player NOW, for loading a save"), and
            # it bumps the ground's version so StaticLayer recomposes from the
            # fresh chunks instead of the stale ones.
            _wt = observer_.target
            if _wt is not _watched_last:
                _watched_last = _wt
                if _wt is not None and getattr(_wt, "alive", False):
                    ground.refresh_around(_wt.x, _wt.y, WIDTH, HEIGHT)

            cam_x += (_fx - vw / 2 - cam_x) * min(1.0, dt * 9.0)
            cam_y += (_fy - vh / 2 - cam_y) * min(1.0, dt * 9.0)

            ground.update(6, cam_x, cam_y, vw, vh)   # worker builds ahead of us
            trees.update(now)                        # stumps grow back

            if door_cooldown <= 0.0:
                candidates = list(built_houses)
                for village in visible_villages:
                    candidates.extend(village.houses)
                for house in candidates:
                    if not getattr(house, "enterable", False):
                        continue
                    interior = getattr(house, "interior", None)
                    if interior is None:
                        continue
                    fx, fy = house.facing
                    door_x = house.x + fx * (house.h / 2.0 + 6.0)
                    door_y = house.y + fy * (house.h / 2.0 + 6.0)
                    if ((player.x - door_x) ** 2 + (player.y - door_y) ** 2
                            < 24.0 ** 2):
                        enter_house(house)
                        break

            if player.dead:
                game_over = True
                pygame.mouse.set_visible(True)

        # -- underground ------------------------------------------------------
        # A mine is its own little world: solid rock all round, no window, no
        # view out, and a seam in the middle that never runs out. Handled here
        # and returned from, so nothing in the open air can be disturbed by it.
        if inside_mine is not None:
            _room = inside_mine.room
            _room.update(dt)
            mine_cd = max(0.0, mine_cd - dt)
            _keys = pygame.key.get_pressed()
            # THE KEY THAT OPENED IT MUST BE RELEASED FIRST. This block reads
            # key STATE, not key events, so the E that took you down was still
            # held on the next frame and slammed the door behind you -- a dark
            # flash and a wiggle, then back in the daylight. Every other menu
            # in the game uses KEYDOWN, which fires once; this one waits for
            # the finger to come off E before it will listen to it again.
            if getattr(player, "_mine_latch", False):
                if not _keys[pygame.K_e]:
                    player._mine_latch = False
            elif _keys[pygame.K_e] or _keys[pygame.K_ESCAPE]:
                inside_mine = None                 # back up the shaft
                player.x, player.y = mine_out
                continue
            _aim = (mouse_x - (player.x - cam_x), mouse_y - (player.y - cam_y))
            player.skill_speed = skills.move_scale()
            award_levels()
            player.skill_stamina = skills.stamina_scale()
            player.update(dt, _keys, _aim, 1.0)
            player.x, player.y = _room.clamp(player.x, player.y)
            # THE CAMERA BELONGS TO THE VIEW, NOT THE WINDOW. The world is
            # drawn in a frame two thirds the window's size, so a camera set
            # from the window width sat 355 px to the left of what was on
            # screen -- and every click, every reach, every "too far away" was
            # measured against a world that was not the one being looked at.
            # THE ROOM IS CENTRED ON THE SCREEN, not the man. A camera put on
            # the player at the world's zoom left the chamber hanging off to
            # one side with the aim off by a third of a screen; the working
            # face is a fixed room, and it is the room that is centred.
            cam_x = _room.W / 2.0 - vw / 2.0
            cam_y = _room.H / 2.0 - vh / 2.0
            # SWING AT THE FACE. Fifteen of these to the open seam's three,
            # and it is still there afterwards -- the seam never runs out.
            if pygame.mouse.get_pressed()[0] and mine_cd <= 0.0:
                mine_cd = 0.35
                _hold = inventory.selected_stack()
                if _hold is None or _hold.defn.id != "pickaxe":
                    # IRON IS NOT AXED OUT OF ROCK. The open seams have always
                    # demanded a pickaxe, because only the pickaxe's own swing
                    # goes looking for ore -- but the mine took any click at
                    # all, so a man could break iron out of the face with an
                    # axe, or with his bare hands.
                    toast("You need a pickaxe for the seam")
                elif not _room.hits_chunk(player.x, player.y):
                    toast("Get closer to the seam")
                elif not player.can_swing():
                    pass                      # still getting his wind back
                else:
                    player.start_swing()      # the same wind-up as anywhere
                    combat.spawn_swing(player.x, player.y, player.facing_angle)
                    _got = _room.swing((ore.YIELD_LO, ore.YIELD_HI))
                    if _got:
                        inventory.add("iron", _got)
                        pay_share("iron", _got)
                        toast("Broke out %d iron" % _got)
            _room.draw(screen, cam_x, cam_y, vw, vh)
            _sel = inventory.selected_stack()
            player.draw(screen, cam_x, cam_y, _sel.defn.id if _sel else None)
            observer_.draw(screen)
            hotbar.draw(screen)
            hotbar.draw_stamina(screen, player.stamina / player.max_stamina,
                                player.exhausted)
            hotbar.draw_hunger(screen, player.hunger / player.max_hunger)
            if toast_time > 0.0:
                toast_time = max(0.0, toast_time - dt)
                _lab = font.render(toast_text, True, TOAST_COLOR)
                _lab.set_alpha(int(255 * min(1.0, toast_time / 0.5)))
                screen.blit(_lab, (vw // 2 - _lab.get_width() // 2, int(vh * 0.68)))
            pygame.display.flip()
            continue

        # -- draw world ------------------------------------------------------
        tick_conquest(dt)
        update_hud()
        if map_open and world_map is not None:
            world_map.update(dt)
            # The map is live: while it is open the armies alone continue the
            # march, so their markers walk across it. Nothing else in the world
            # is simulated -- no villages, no economy, no vision -- because
            # running all of that with the map up is what froze the game solid.
            if test_mode and armies:
                for _army in armies:
                    if _army.done:
                        continue
                    for _s in _army.soldiers:
                        mt = getattr(_s, "march_target", None)
                        if mt is None or not _s.alive:
                            continue
                        ux, uy = steering.steer(_s, mt[0], mt[1], [], [])
                        _s.x += ux * 240.0 * dt
                        _s.y += uy * 240.0 * dt
                war.update(armies, dt, now)
        if inside_house is not None:
            interior = inside_house.interior
            # THE INTERIOR IS DRAWN AT THE SAME ZOOM AS THE WORLD. It was still
            # composed in a full-window frame while its camera came from the
            # narrowed one, so the room hung off-centre with the man not in the
            # middle of it. Borrow the view for the room -- the walls, the
            # window, the people, the man -- and hand the window back for the
            # HUD, exactly as the outdoors does.
            scr_w, scr_h = vw, vh
            vw, vh = max(2, int(scr_w / ZOOM)), max(2, int(scr_h / ZOOM))
            if view_surf is None or view_surf.get_size() != (vw, vh):
                view_surf = pygame.Surface((vw, vh))
            real_screen = screen
            screen = view_surf
            cam_x = player.x - vw / 2.0
            cam_y = player.y - vh / 2.0
            world_surface = pygame.Surface((vw, vh))
            draw_exterior(inside_house.x - vw / 2.0, inside_house.y - vh / 2.0,
                          False, world_surface)
            screen.blit(world_surface, (0, 0))
            interior.draw(screen, cam_x, cam_y)
            # (The live outdoors is already behind the room, so the windows open
            # onto the real world and it continues past the walls.)
            eye_x = player.x - cam_x + player.facing[0] * 5.0
            eye_y = player.y - cam_y + player.facing[1] * 5.0
            inside_occluders = [pygame.Rect(r.x - cam_x, r.y - cam_y, r.w, r.h)
                                for r in interior.occluders]
            mask = interior_vision.build(vw, vh, eye_x, eye_y, player.facing_angle,
                                         inside_occluders, None, 1.3)
            screen.blit(mask, (0, 0))
            # Show the live outdoors clearly through every window and the door.
            for opening in interior.window_rects + [interior.door_rect]:
                sr = pygame.Rect(int(round(opening.x - cam_x)),
                                 int(round(opening.y - cam_y)),
                                 opening.w, opening.h)
                inner = sr.inflate(-4, -4)
                if inner.w > 0 and inner.h > 0:
                    screen.blit(world_surface, inner, inner)
            draw_night()
            selected = inventory.selected_stack()
            for npc in getattr(inside_house, "occupants", ()):
                if npc.alive and npc.in_interior:      # residents move about
                    npc.draw(screen, cam_x, cam_y, True)
            player.draw(screen, cam_x, cam_y, selected.defn.id if selected else None)
            # THE GHOST BELONGS TO THE ROOM. draw_placing() works in the room's
            # own coordinates (box.x - cam_x), so it has to be drawn before the
            # frame is blown up -- drawn afterwards it landed at a quarter of
            # its size and a third of a screen from the cursor.
            draw_placing()
            # ...and back to the window for everything that is not the room.
            screen = real_screen
            pygame.transform.scale(view_surf, (scr_w, scr_h), screen)
            vw, vh = scr_w, scr_h
            draw_hunger_gray()
            if not inventory_open:
                draw_crosshair(screen, mouse_x, mouse_y)
            hotbar.draw(screen)
            hotbar.draw_stamina(screen, player.stamina / player.max_stamina,
                                player.exhausted)
            hotbar.draw_hunger(screen, player.hunger / player.max_hunger)
            if toast_time > 0.0:
                toast_time = max(0.0, toast_time - dt)
                fade = min(1.0, toast_time / 0.5)
                label = font.render(toast_text, True, TOAST_COLOR)
                label.set_alpha(int(255 * fade))
                plate = pygame.Surface((label.get_width() + 22, 26), pygame.SRCALPHA)
                pygame.draw.rect(plate, (18, 18, 22, 200), plate.get_rect(), border_radius=6)
                plate.set_alpha(int(255 * fade))
                tt = vw // 2 - label.get_width() // 2
                screen.blit(plate, (tt - 11, int(vh * 0.68) - 3))
                screen.blit(label, (tt, int(vh * 0.68)))
            if smith_open and smith_shop is not None:
                _w = smith_shop.worker
                _orders = list(getattr(_w, "tool_orders", ()) or ())
                _r = pygame.Rect(vw // 2 - 220, vh // 2 - 150, 440, 300)
                _shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
                _shade.fill((0, 0, 0, 170))
                screen.blit(_shade, (0, 0))
                pygame.draw.rect(screen, (26, 26, 30), _r, border_radius=10)
                pygame.draw.rect(screen, (150, 118, 78), _r, 2, border_radius=10)
                _titles = {"smith": "THE FORGE", "mine": "THE PIT HEAD",
                           "lab": "THE LABORATORY", "brewery": "THE BREWHOUSE"}
                screen.blit(font.render(
                    "%s   -   %s's" % (_titles.get(_w.kind if _w else "", "THE BENCH"),
                                       smith_shop.worker.village.name
                                       if smith_shop.worker else "the village"),
                    True, (238, 224, 190)), (_r.x + 14, _r.y + 12))
                screen.blit(font.render("iron in stock: %d"
                                        % int(getattr(_w, "stock", {}).get("iron", 0)),
                                        True, (232, 200, 118)), (_r.x + 14, _r.y + 38))
                _y = _r.y + 66
                if not _orders:
                    screen.blit(font.render("nothing booked", True, (150, 146, 138)),
                                (_r.x + 14, _y))
                for _who, _want in _orders[:9]:
                    _t = "%s wants a %s" % (getattr(_who, "name", "someone"), _want)
                    screen.blit(font.render(_t, True, (216, 212, 200)), (_r.x + 14, _y))
                    _y += 22
                if _w is not None:
                    _held = {k: int(v) for k, v in getattr(_w, "stock", {}).items()
                             if k in ("axe", "shovel", "pickaxe") and v}
                    if _held:
                        screen.blit(font.render("on the shelf: " + ", ".join(
                            "%d %s" % (q, i) for i, q in _held.items()), True,
                            (200, 200, 190)), (_r.x + 14, _r.bottom - 44))
                _kind = smith_shop.kind
                _hint = {"smith": "[Space] forge a tool",
                         "mine": "[Space] break out iron",
                         "lab": "[Space] work the leaf",
                         "brewery": ("[Space] draw the brew"
                                     if getattr(player, "brew", None) is not None
                                     else "[Space] start a mash")}.get(_kind, "")
                screen.blit(font.render("%s      [E] close   " % _hint,
                                        True, (196, 226, 168)),
                            (_r.x + 14, _r.bottom - 24))
                if work_msg:
                    screen.blit(font.render(work_msg, True, (240, 206, 130)),
                                (_r.x + 14, _r.bottom - 46))
            if board_open and board_village is not None:
                board_panel.player = player
                board_panel.inv = inventory
                board_panel.chest = (inside_house.interior.chest
                                     if inside_house is not None
                                     else (built_houses[0].interior.chest
                                           if built_houses
                                           and built_houses[0].interior else None))
                board_panel.tax_day = int(now / DAY_LENGTH)
                board_panel.notice_t = max(0.0, board_panel.notice_t - dt)
                board_panel.draw(screen, board_village)
            draw_speed_button()
            if build_menu_open:
                build_menu.draw(screen)
            if compass_open:
                compass_menu.draw(screen)
            if inventory_open:
                panel.draw(screen)
            if chest_open:
                chest_panel.draw(screen)
            if workshop_open:
                workshop_menu.draw(screen)
            if trade_open:
                trade_menu.draw(screen)
            elif near_chest():
                hint = font.render("[E]  Open chest", True, (240, 232, 200))
                screen.blit(hint, (vw // 2 - hint.get_width() // 2, int(vh * 0.80)))
            elif near_workshop():
                hint = font.render("[E]  Use workshop", True, (240, 232, 200))
                screen.blit(hint, (vw // 2 - hint.get_width() // 2, int(vh * 0.80)))
            elif near_workplace() is not None:
                _k = near_workplace().kind
                _what = {"mine": "Go down the mine",
                         "smith": "The forge",
                         "lab": "The laboratory",
                         "brewery": "The brewhouse"}.get(_k, "Work here")
                hint = font.render("[E]  %s" % _what, True, (240, 232, 200))
                screen.blit(hint, (vw // 2 - hint.get_width() // 2, int(vh * 0.80)))
            if pause_open:
                pause_menu.draw(screen)
            if map_open:
                try:
                    mapmod.draw(screen, world, player, _nearest_town(),
                                hub_world.hubs)
                except Exception:
                    import traceback as _tb; _tb.print_exc()
            pygame.display.flip()
            continue

        # ---- THE ZOOM ------------------------------------------------------
        # The world is built in a surface two thirds the window's size and
        # blown up onto it: fewer pixels to compose every frame, and everything
        # on screen half again as large. `screen` and `vw/vh` are borrowed for
        # the duration, so every line of the world -- ground, trees, people,
        # the vision mask, blood -- lands in the smaller frame without one of
        # them being rewritten. They are handed back before the HUD, which
        # belongs at the window's own size.
        scr_w, scr_h = vw, vh
        vw, vh = max(2, int(scr_w / ZOOM)), max(2, int(scr_h / ZOOM))
        if view_surf is None or view_surf.get_size() != (vw, vh):
            view_surf = pygame.Surface((vw, vh))
        real_screen = screen
        screen = view_surf
        # THE CAMERA FOLLOWS THE MAN BEING WATCHED, NOT THE PLAYER.
        #
        # It followed player.x/player.y, and watching had been implemented by
        # MOVING THE PLAYER onto the watched man every frame -- so the player
        # was dragged about the world with the camera tied to him, and the man
        # being watched was only ever in shot because the player had been
        # teleported onto his head. The player is PARKED where he stands; the
        # camera is the thing that moves.
        _look = observer_.target
        if _look is not None and getattr(_look, "alive", False):
            cam_x = _look.x - vw / 2.0
            cam_y = _look.y - vh / 2.0
        else:
            cam_x = player.x - vw / 2.0
            cam_y = player.y - vh / 2.0
        draw_exterior(cam_x, cam_y, True)
        # AND NOBODY WALKS INTO A TOWN WITHOUT BEING SEARCHED, HIM INCLUDED.
        # Through the gate and past the guard, or the whole street turns.
        # (The "walked past the guard" crime is REMOVED until the gate search
        # is actually built for the player. It fired the moment he stepped
        # inside any fence -- because nothing ever marked him searched -- and
        # the whole town, shotguns included, turned on him for approaching.)
        try:
            hub_world.draw(screen, cam_x, cam_y, vw, vh)
        except Exception:
            pass
        draw_news(screen, cam_x, cam_y, vw, vh)   # the bubble, over his head
        draw_villages = villages.visible(cam_x, cam_y, vw, vh,
                                         extra=hub_world.hubs)
        draw_trees = trees.visible(cam_x, cam_y, vw, vh)

        # Houses and tree trunks block line of sight; canopies soften it.
        reach = vision.max_dist
        occluders = [house.sight_rect for village in draw_villages
                     for house in village.houses
                     if (house.x - player.x) ** 2 + (house.y - player.y) ** 2
                     < (reach + max(house.w, house.h)) ** 2]
        occluders += [house.sight_rect for house in built_houses
                      if (house.x - player.x) ** 2 + (house.y - player.y) ** 2
                      < (reach + max(house.w, house.h)) ** 2]
        nearby = sorted(draw_trees,
                        key=lambda t: (t.x - player.x) ** 2 + (t.y - player.y) ** 2)
        soft: list[pygame.Rect] = []
        for i, tree in enumerate(nearby[:80]):
            if tree.felled:
                continue
            if ((tree.x - player.x) ** 2 + (tree.y - player.y) ** 2
                    > (reach + tree.canopy_r) ** 2):
                continue
            if i < 45:
                occluders.append(tree.trunk_rect)
            r = tree.canopy_r
            soft.append(pygame.Rect(tree.x - r, tree.y - r, r * 2, r * 2))

        screen_occluders = [pygame.Rect(r.x - cam_x, r.y - cam_y, r.w, r.h)
                            for r in occluders]
        screen_soft = [pygame.Rect(r.x - cam_x, r.y - cam_y, r.w, r.h)
                       for r in soft]

        # THE EYES BELONG TO THE MAN BEING WATCHED.
        #
        # This cast the mask from player.x/player.y, so with the camera sixty
        # thousand pixels away on somebody else the cone lit a place that was
        # not on screen and everything else was black -- which is what the
        # black screen was. A watcher also sees the WHOLE scene rather than one
        # man's 175 degrees: that is what watching is for.
        _wt = observer_.target
        _watch = _wt is not None and getattr(_wt, "alive", False)
        _src = _wt if _watch else player
        if _watch:
            _ang = math.atan2(_src.facing[1], _src.facing[0])  # NPC has no
        else:                                                  # facing_angle
            _ang = player.facing_angle
        eye_x = _src.x - cam_x + _src.facing[0] * 5.0
        eye_y = _src.y - cam_y + _src.facing[1] * 5.0
        foliage = trees.foliage(_src.x, _src.y)
        _cone0 = vision.cone_deg
        if _watch:
            vision.cone_deg = 360.0
        mask = vision.build(vw, vh, eye_x, eye_y, _ang,
                            screen_occluders, screen_soft, 1.0 - 0.25 * foliage)
        screen.blit(mask, (0, 0))
        if _watch:
            vision.cone_deg = _cone0
        draw_night()

        selected = inventory.selected_stack()
        player.draw(screen, cam_x, cam_y, selected.defn.id if selected else None)
        combat.draw(screen, cam_x, cam_y)
        draw_hunger_gray()

        if game_over:
            # THE WINDOW IS THE WINDOW. While the world is drawn, the name
            # `screen` points at the small offscreen view surface, and the two
            # lines that put it back -- and upscale the world into it -- live in
            # the else-branch below. Dying skipped them, so the game-over panel
            # was painted onto a surface nothing ever showed while the window
            # kept the last frame it had. That is what "it freezes instead of
            # showing a game over screen" was: a correct panel, drawn offscreen.
            screen = real_screen
            pygame.transform.scale(view_surf, (scr_w, scr_h), screen)
            overlay.draw(screen, [
                f"Kills: {kills}",
                f"Tobacco: {inventory.count_of('tobacco')}",
                f"Seeds: {inventory.count_of('seed_bag')}",
            ])
        else:
            if not player.dead:
                damage = 1.0 - player.health / player.max_health
                vignette.draw(screen, damage, now, player.hit_flash / 0.15)

            eye_world_x = player.x + player.facing[0] * 5.0
            eye_world_y = player.y + player.facing[1] * 5.0
            for enemy in enemies:
                ex, ey = enemy.x - cam_x, enemy.y - cam_y
                if ex < -24 or ey < -24 or ex > vw + 24 or ey > vh + 24:
                    continue
                if not vision.is_visible(eye_world_x, eye_world_y, player.facing_angle,
                                         enemy.x, enemy.y, occluders=occluders):
                    draw_alert(screen, ex, ey, now, enemy.phase)

            draw_placing()

            if not inventory_open:
                draw_crosshair(screen, wmouse_x, wmouse_y)

            # ---- ...and back to the window ---------------------------------
            screen = real_screen
            pygame.transform.scale(view_surf, (scr_w, scr_h), screen)
            vw, vh = scr_w, scr_h
            hotbar.draw(screen)
            # THE INSPECTOR IS DRAWN ABOVE GROUND TOO.
            #
            # observer_.draw() lived ONLY inside the MINE's render block, so
            # above ground the panel opened -- your key log shows observer=True
            # six times -- and not one pixel was painted. It is drawn here, on
            # the real screen, after the world has been scaled up, because
            # Observer.draw works in window coordinates.
            #
            # And it is checked by PIXELS now. For hours I verified this by
            # reading observer.open, which was True the whole time, and told
            # you it worked three times on that basis. State is not a picture.
            observer_.draw(screen)
            hotbar.draw_stamina(screen, player.stamina / player.max_stamina,
                                player.exhausted)
            hotbar.draw_hunger(screen, player.hunger / player.max_hunger)

            if toast_time > 0.0:
                toast_time = max(0.0, toast_time - dt)
                fade = min(1.0, toast_time / 0.5)
                label = font.render(toast_text, True, TOAST_COLOR)
                label.set_alpha(int(255 * fade))
                plate = pygame.Surface((label.get_width() + 22, 26), pygame.SRCALPHA)
                pygame.draw.rect(plate, (18, 18, 22, 200), plate.get_rect(), border_radius=6)
                plate.set_alpha(int(255 * fade))
                px = vw // 2 - label.get_width() // 2
                py = int(vh * 0.68)
                screen.blit(plate, (px - 11, py - 3))
                screen.blit(label, (px, py))
            if smith_open and smith_shop is not None:
                _w = smith_shop.worker
                _orders = list(getattr(_w, "tool_orders", ()) or ())
                _r = pygame.Rect(vw // 2 - 220, vh // 2 - 150, 440, 300)
                _shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
                _shade.fill((0, 0, 0, 170))
                screen.blit(_shade, (0, 0))
                pygame.draw.rect(screen, (26, 26, 30), _r, border_radius=10)
                pygame.draw.rect(screen, (150, 118, 78), _r, 2, border_radius=10)
                _titles = {"smith": "THE FORGE", "mine": "THE PIT HEAD",
                           "lab": "THE LABORATORY", "brewery": "THE BREWHOUSE"}
                screen.blit(font.render(
                    "%s   -   %s's" % (_titles.get(_w.kind if _w else "", "THE BENCH"),
                                       smith_shop.worker.village.name
                                       if smith_shop.worker else "the village"),
                    True, (238, 224, 190)), (_r.x + 14, _r.y + 12))
                screen.blit(font.render("iron in stock: %d"
                                        % int(getattr(_w, "stock", {}).get("iron", 0)),
                                        True, (232, 200, 118)), (_r.x + 14, _r.y + 38))
                _y = _r.y + 66
                if not _orders:
                    screen.blit(font.render("nothing booked", True, (150, 146, 138)),
                                (_r.x + 14, _y))
                for _who, _want in _orders[:9]:
                    _t = "%s wants a %s" % (getattr(_who, "name", "someone"), _want)
                    screen.blit(font.render(_t, True, (216, 212, 200)), (_r.x + 14, _y))
                    _y += 22
                if _w is not None:
                    _held = {k: int(v) for k, v in getattr(_w, "stock", {}).items()
                             if k in ("axe", "shovel", "pickaxe") and v}
                    if _held:
                        screen.blit(font.render("on the shelf: " + ", ".join(
                            "%d %s" % (q, i) for i, q in _held.items()), True,
                            (200, 200, 190)), (_r.x + 14, _r.bottom - 44))
                _kind = smith_shop.kind
                _hint = {"smith": "[Space] forge a tool",
                         "mine": "[Space] break out iron",
                         "lab": "[Space] work the leaf",
                         "brewery": ("[Space] draw the brew"
                                     if getattr(player, "brew", None) is not None
                                     else "[Space] start a mash")}.get(_kind, "")
                screen.blit(font.render("%s      [E] close   " % _hint,
                                        True, (196, 226, 168)),
                            (_r.x + 14, _r.bottom - 24))
                if work_msg:
                    screen.blit(font.render(work_msg, True, (240, 206, 130)),
                                (_r.x + 14, _r.bottom - 46))
            if board_open and board_village is not None:
                board_panel.player = player
                board_panel.inv = inventory
                board_panel.chest = (inside_house.interior.chest
                                     if inside_house is not None
                                     else (built_houses[0].interior.chest
                                           if built_houses
                                           and built_houses[0].interior else None))
                board_panel.tax_day = int(now / DAY_LENGTH)
                board_panel.notice_t = max(0.0, board_panel.notice_t - dt)
                board_panel.draw(screen, board_village)
            draw_speed_button()

        if trade_open:
            trade_menu.draw(screen)
        if build_menu_open:
            build_menu.draw(screen)
        if inventory_open:
            panel.draw(screen)
        if confirm_open:
            confirm.draw(screen)
        if compass_open:
            compass_menu.draw(screen)
        if pause_open:
            pause_menu.draw(screen)
        if map_open:
            try:
                mapmod.draw(screen, world, player, _nearest_town(),
                            hub_world.hubs)
            except Exception:
                pass

        pygame.display.flip()

    pygame.mouse.set_visible(True)
    save_now()
    pygame.quit()


if __name__ == "__main__":
    # A crash leaves the truth behind instead of closing over it.
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        persist.crash(traceback.format_exc())
        traceback.print_exc()
        raise
