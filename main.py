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
from types import SimpleNamespace

import stats

import math
import lanes
import mine
import os
import random
import sys
import threading
import time

import pygame
import plog
import worldio
import worldbuild
import houseuse
import hudtime
import newsbubble
import nearby
import playerutil
import interact
import savegame
import combat_actions

import crop
import biomes
import board
import compass
import economy
import items
import industry
import quality
import farm
import fence
import gate
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
import dialogue
import village as village_mod
import war
import work
import wildcrop
import world
import worldmap
import lanes_mp as workers
from blood import Blood
from build import BuildMenu, build_cost, build_materials
import stall as stall_mod
import corpse as corpse_mod
import folders as folders_mod
import manhunt
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
from ui import (ChestPanel, ConfirmMenu, FolderPanel, Hotbar,
                InventoryPanel, MarketPanel, PauseMenu)
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
# Unarmed he does 16 / skills.UNARMED_WEAKNESS = 4, like any man in the
# street who swings a fist.
MELEE_DAMAGE = 35         # the axe
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


CORE_HALF = 100000          # THE SETTLED COUNTRY: unchanged, all of it
# FIVE TIMES THE LENGTH AND FIVE TIMES THE WIDTH: each side is 1,000,000 px
# across, the settled country stays where it always was, in the middle of it,
# and the ring around it is the Siberian waste.
WORLD_HALF = CORE_HALF * 5


def _present(dest, src, w, h):
    """PUT THE SCALED VIEW ON THE WINDOW, WITHOUT ASSUMING ITS SIZE.

    `pygame.transform.scale(src, (w, h), dest)` raises ValueError -- "Destination
    surface not the given width or height" -- when the window surface is not
    exactly (w, h). That is a hard crash in the last line of drawing, and it is
    what closed the game at the gate.
    """
    try:
        size = dest.get_size()
    except Exception:
        return
    if size == (w, h):
        try:
            pygame.transform.scale(src, (w, h), dest)
            return
        except (TypeError, ValueError):
            pass
    try:
        pygame.transform.scale(src, size, dest)
    except (TypeError, ValueError):
        try:
            dest.blit(pygame.transform.smoothscale(src, size), (0, 0))
        except Exception:
            pass


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Kingpin")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()

    import menu
    pygame.mouse.set_visible(True)
    # AN UNATTENDED INSTANCE STILL HAS TO GET PAST THE MENU. In observe mode
    # there is nobody to click "new game", so it is chosen for him.
    if os.environ.get("KINGPIN_OBSERVE"):
        chosen = (0, True)      # 0 = new game, True = start
    else:
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
    # THE CACHE IS NOT READ. A fresh build agrees with `village_center()` to the
    # pixel; the cached world on disk did not -- every town in it stood 22 km
    # from the position the lattice reports, so its fence, its gates, its
    # guards and its culling were all computed for a place the town was not.
    # That is why a man at a gate saw no wall and no guard, and why a settlement
    # looked like a patch of berries with nothing around it. 1.8 seconds at the
    # loading screen is cheaper than a world that lies about where it is.
    _cached = None
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
        worldbuild.load_world(screen, clock, villages, world)  # every village, before the first step
        # THE POPULATION IS SET BEFORE THE CACHE IS WRITTEN. Writing it after
        # meant the cache held 2,084 people and every later launch restored all
        # of them and then threw half away again.
        worldbuild.set_world_population(villages)
        worldio.save_cached_world(villages, world.seed)
        village_mod.rebuild_people(villages)
        village_mod.rebuild_houses(villages)

    # ---- THE HUBS IN THE WILD -- not villages; no war can be declared
    # on one, because no one admits it exists.
    hub_world = hubs.Hubs(world, villages)
    # A HANDLE FOR TOOLS AND TESTS, like village.PLAYER: the hub registry is a
    # local, so nothing outside main() could ever see the player's own yard.
    try:
        village_mod.HUBS = hub_world
    except Exception:
        pass
    dialogue_panel = dialogue.Dialogue()

    def _main_capital():
        """The seat: the town whose king is the Dictator."""
        best = None
        for _v in villages.villages:
            if getattr(_v, "king", None) is not None:
                return (_v,)
            if best is None and getattr(_v, "is_capital", False):
                best = _v
        return (best,)
    hub_world.build_caravans(world)
    # NO TREE THROUGH A ROOF -- BUT THE WOODS STILL GROW IN THE YARD.
    #
    # This used to mark EVERY tree inside a hub's fence as felled, directly
    # and for ever: not cut (cutting leaves a stump that regrows), just marked.
    # The result was a hub environment where trees never grew back and every
    # stump that was there before simply stayed a stump -- or, after a reload,
    # vanished. What the yard needs is only this: no tree standing in a HOUSE
    # or a WORKPLACE. Everything else is woods, and woods grow.
    for _h in hub_world.hubs:
        _built = []
        for _b in list(getattr(_h, "houses", ()) or ()):
            _br = getattr(_b, "rect", None)
            if _br is not None:
                _built.append(_br.inflate(40, 40))
        for _b in list(getattr(_h, "workplaces", ()) or ()):
            _br = getattr(_b, "rect", None)
            if _br is not None:
                _built.append(_br.inflate(40, 40))
        if not _built:
            continue
        for _t in trees.visible(min(r.x for r in _built) - 200,
                                min(r.y for r in _built) - 200,
                                max(r.right for r in _built) + 200
                                - min(r.x for r in _built),
                                max(r.bottom for r in _built) + 200
                                - min(r.y for r in _built)):
            if any(r.collidepoint(_t.x, _t.y) for r in _built):
                _t.felled = True

    # ---- A THOUSAND PEOPLE, AND A THOUSAND CAP, ALWAYS ------------------
    #
    # The last word on the size of the world, and it runs on BOTH paths -- a
    # fresh build and a restored save -- because an older save carries its own
    # `capacity` and `rebuild_people` trims every town down to it. That is
    # where two thirds of the world has been disappearing: the world is built
    # with 58 people a town, an older save says 17, and the register is cut to
    # the smaller number before anyone takes a step. Whatever a file says, the
    # world begins at the size it was designed for.
    _pop = worldbuild.set_world_population(villages)
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
    # HE WAKES IN THE WILDERNESS, SOMEWHERE NEW EVERY WORLD.
    #
    # A man with an axe and nothing else, in open country, with the nearest
    # town a walk away -- not standing in a square he did not choose. The spot
    # is drawn from the world's own seed, so the same save always wakes in the
    # same place, and no town's fence, no hut's yard is within sight of him.
    try:
        _towns_all = [v for v in villages.villages
                      if not getattr(v, "is_hub", False)]
    except Exception:
        _towns_all = []
    _spawn_rng = random.Random((int(_save.get("seed", 20240501)) ^ 0xA11CE5EED)
                               & 0xFFFFFFFF)
    _start = None
    _hx, _hy = 0.0, 0.0
    for _try in range(600):
        _sx = _spawn_rng.uniform(-65000.0, 65000.0)
        _sy = _spawn_rng.uniform(-65000.0, 65000.0)
        if any((v.x - _sx) ** 2 + (v.y - _sy) ** 2 < 1500.0 ** 2
               for v in _towns_all):
            continue
        if any(getattr(_h, "fence_rect", None) is not None
               and _h.fence_rect.inflate(900, 900).collidepoint(_sx, _sy)
               for _h in getattr(hub_world, "hubs", ()) or ()):
            continue
        _hx, _hy = _sx, _sy
        break
    # HE STARTS IN THE OPEN, IN THE MIDDLE OF THE MAP: out in the country
    # between the towns, no fence over him and nobody looking at him.
    print("OPEN-FIELD SPAWN  %.0f,%.0f" % (_hx, _hy))
    # ---- OBSERVE MODE ------------------------------------------------------
    # KINGPIN_OBSERVE=1 runs a real instance -- real window, real frame, real
    # world -- with the player standing invincible in open ground while
    # everything else lives around him. He is not moved by anything and nothing
    # can hurt him; the world carries on. Used to watch the gates work.
    _observe_spot = None
    if os.environ.get("KINGPIN_OBSERVE"):
        try:
            _towns = [v for v in villages.villages
                      if getattr(v, "fence_rect", None) is not None
                      and not getattr(v, "is_hub", False)]
            if _towns:
                _t0 = min(_towns, key=lambda v: v.x * v.x + v.y * v.y)
                # AT THE GATE. The point of watching is to see the guard walk
                # over and search him, ten seconds, bar under his feet.
                _g0 = fence.gate_list(_t0)[0]
                _ox0, _oy0 = fence.OUTWARD[_g0[0]]
                _observe_spot = (_g0[1] + _ox0 * 130.0, _g0[2] + _oy0 * 130.0)
                _hx, _hy = _observe_spot
                _origin_town = _t0
                print("OBSERVE: pinned at %.0f,%.0f -- 1.7 km from %s"
                      % (_observe_spot[0], _observe_spot[1], _t0.name))
        except Exception:
            _observe_spot = None
    # ---- THE CHAIN TEST ----------------------------------------------------
    # KINGPIN_CHAIN=1 watches ONE hub, link by link, in the running game. Each
    # link has a deadline; when one does not happen in time the instance STOPS
    # and says which link broke. Nothing is simulated outside the game.
    def _csay(msg: str) -> None:
        """A line the test can be read from: written and flushed at once,
        because a windowed build buffers stdout and shows nothing."""
        try:
            print(msg, flush=True)
        except Exception:
            pass
        try:
            with open(os.path.expanduser("~/.kingpin_saves/chain.log"), "a") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass

    _chain = None
    if os.environ.get("KINGPIN_CHAIN"):
        _chain = {"hub": None, "t0": 0.0, "link": 1, "seen": {}, "t": 0.0,
                  "f": 0, "wall0": time.perf_counter(), "last_say": -1.0}

    _TRUTH = [None]      # the man who is always beside the player, if any
    player = Player(_hx, _hy)
    # HE WAKES UP INSIDE THE TOWN, not climbing into it (see the wall-crossing
    # check further down): the first frame must not read as an unsearched
    # entry, or the whole square is at his throat before he takes a step.
    if _start is not None:
        player.was_inside_v = _start
        player.waved_by = None
        player.aggro_village = None
    # ---- THE TRUTH-TELLER -----------------------------------------------
    # One man who stands beside the player from the first frame and never
    # leaves. He is a REAL NPC -- a real name, a real settlement, a real trade,
    # the same class every other man in the world is made of -- he simply
    # cannot be killed and does not walk away. He exists to be talked to.
    _truth = None
    _truth_home = [0.0, 0.0]      # the spot on the ground he never leaves
    try:
        _towns_t = [v for v in villages.villages
                    if getattr(v, "fence_rect", None) is not None
                    and not getattr(v, "is_hub", False)]
        # THE SAME TOWN YOU WAKE IN, so the man beside you is one of its own.
        _tt_town = (_origin_town
                    if getattr(_origin_town, "fence_rect", None) is not None
                    else (random.choice(_towns_t) if _towns_t else None))
        if _tt_town is not None:
            _truth = village_mod.NPC(
                player.x + 44.0, player.y, random.randrange(1 << 30),
                "%s %s" % (random.choice(village_mod.FIRST_NAMES),
                           random.choice(village_mod.LAST_NAMES)),
                "truth_teller", "Truth-teller", _tt_town)
            _truth.job = random.choice(
                ["farm", "logger", "mine", "smith", "trader",
                 "lab", "brewery", "hand"])
            _truth.nation = _tt_town.nation
            _truth.team = ("nation", _tt_town.nation)
            _truth.max_health = stats.PLAYER_MAX_HEALTH
            _truth.health = stats.PLAYER_MAX_HEALTH
            _truth.is_truth_teller = True
            _tt_town.npcs.append(_truth)
            _TRUTH[0] = _truth      # from the moment he exists, he is clickable
            _truth_home[0], _truth_home[1] = _truth.x, _truth.y
            plog.log("TRUTH", "created", _truth.name, "of", _tt_town.name,
                     "trade", _truth.job, "at", "%d,%d"
                     % (int(_truth.x), int(_truth.y)))
    except Exception as _te:
        # A WINDOWED BUILD SWALLOWS stdout. If he cannot be made, the reason
        # must reach a file or nobody will ever know.
        plog.log("TRUTH-ERROR", repr(_te)[:200])
    if _observe_spot is not None:
        player.god = True
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
    # player in a town's own books without every caller passing him down.
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
    }
    for _item, _qty in KITS.get(origin, ()):
        inventory.add(_item, _qty)
    # EVERY MAN IN THE WOODS HAS AN AXE. "idle" was written twice in that
    # table -- the second entry, empty, won -- so the one start with nothing
    # was also the one start that could not cut a tree for its first coin.
    if inventory.count_of("axe") <= 0:
        inventory.add("axe", 1)
    # THE PACK ON THE MAN. Dialogue and the yard's work need to move things
    # into and out of it, and neither is handed the local `inventory`; the
    # player is the one object they both already have.
    player.pack = inventory
    player.hub_chest = None
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

    # ---- THE TEST ENGINE, running the whole network once ----------------
    _TEST_TRAIN = [None]
    _panic_t = [0.0]           # gunfire -> the crowd breaks and runs
    _EXPRESS = [False]         # the engine is running for the camp, not touring
    try:
        import train as _train_mod
        import rail as _rail_t
        _rail_t.ensure(villages.villages)
        _rt = _rail_t.tour()
        if _rt:
            _TEST_TRAIN[0] = _train_mod.Train(_rt)
            plog.log("TRAIN-START", len(_rt), "route points,",
                     int(_rail_t.count()[1]), "px of track")
    except Exception as _te:
        plog.log("TRAIN-ERROR", repr(_te)[:160])
    try:
        import resettle as _resettle
        _resettle.build(villages.villages)
    except Exception as _rse:
        plog.log("RESETTLE-ERROR", repr(_rse)[:140])
    try:
        import rail as _rail0
        _rail0.ensure(villages.villages)
    except Exception as _re0:
        plog.log("RAIL-ERROR", repr(_re0)[:120])
    armies: list = []                  # columns on the march, this campaign
    world.enemies = enemies            # so villagers can spot a predator
    # WHO CAN SEE A THING HAPPEN: the whole living population, for witnesses.
    try:
        import economy as _eco_hook
        _eco_hook.POPULATION = lambda: list(village_mod.PEOPLE)
    except Exception:
        pass
    # A GUNMAN DOES NOT SHOOT THROUGH HIS OWN PEOPLE.
    try:
        import enemy as _enemy_hooks
        _enemy_hooks.CROWD = lambda: list(village_mod.PEOPLE) + list(enemies)
        _enemy_hooks.CIVILIANS = lambda: list(village_mod.PEOPLE)
    except Exception as _eh:
        plog.log("CROWD-HOOK-ERR", repr(_eh)[:120])
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

    def make_village_patrol(village, count=4):
        """THE MEN AT THE GATE. Standing still, armed, thirty rounds each.

        Pivot.md S2: two guards, one at each gate, who DO NOT WALK AWAY. One gate
        is the way in and its guard SEARCHES; the other is the way out and nobody
        is searched leaving. That asymmetry is the whole border.

        A hub gets ONE (S1: "a soldier -- always standing at the gate"), a
        settlement gets two.
        """
        squad = []
        for gi, (_side, gx, gy) in enumerate(fence.gate_list(village)[:count]):
            # HE STANDS BESIDE THE TRACK, NOT ON IT. The rail runs in through
            # the middle of the opening; a guard on the permanent way would be
            # shot for standing where the sleepers are.
            _ox, _oy = fence.OUTWARD.get(_side, (0.0, 1.0))
            _ax, _ay = -_oy, _ox                    # along the wall
            # WELL CLEAR OF THE PERMANENT WAY: a guard standing at 52 px was
            # inside the engine's sweep as it came through the gate.
            _bx = gx + _ox * 26.0
            _by = gy + _oy * 26.0
            # HE STANDS WHERE THE RAIL IS FURTHEST AWAY, along the wall from
            # the opening -- always within sight of his gate, never on the
            # sleepers. The old rule stepped him OUTWARD until he was clear,
            # which walked him away from the gate he is posted to guard.
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
            s.is_militia = True       # the Narodna militsiya hold the gates
            # A MILITIAMAN CARRIES A RIFLE, one dart a squeeze. A shotgun's
            # twelve pellets would put a man down before the magazine was dry.
            try:
                import guns as _guns
                s.weapon = "rifle"
                s.gun_kind = _guns.RIFLE
                s.mag = _guns.MAG[_guns.RIFLE]
            except Exception:
                pass
            s.gate_village = village
            # AND `guard_village`, which is the name the TARGETING reads. He had
            # only `gate_village`, so choose_target fell through every branch it
            # knows -- guard, patrol, march -- and landed in the fallback, which
            # shoots any man of another nation. A nationless player is
            # `None != 1`, so every gate guard in the world shot at him on
            # sight, with `wanted False` and `aggro None` in the log.
            s.guard_village = village
            s.name = "the guard of %s" % getattr(village, "name", "the gate")
            s.gate_index = gi            # 0 is the way in, 1 the way out
            s.gate_post = (_px, _py)
            s.home = s.gate_post
            s.target = s.gate_post
            s.patrol_center = None       # not a territory patrol: he STANDS
            s.patrol_r = 0.0
            s.idle_timer = 1.0e9         # stands at his gate until he is sent
            s.hostile = getattr(village, "provoked", False)
            s.fire_cd = random.uniform(0.05, 0.30)
            s.ammo = 30                  # thirty rounds, and then he is a man
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
    # A HIRED MAN'S PACK, OPENED THE WAY A CHEST IS.
    worker_panel_open = False
    worker_panel = None
    # THE MARKET STALL: the player's counter, its prices, and its purse.
    stall_open = False
    stall_panel = None
    # A BODY ON THE GROUND, OPENED LIKE A CHEST.
    body_open = False
    body_panel = None
    # A DEAD AGENT'S MAIL, OPENED BY EQUIPPING HIS FOLDER AND CLICKING.
    folder_open = False
    folder_panel = None
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
    placed_work: list = []          # the four trades, out of doors, on his land
    built_plots: list = []          # plots he has drawn on his own ground
    plot_start = [None]             # where the plot drag began
    built_fences: list = []
    # THE CAMP'S WALL IS NOT THE PLAYER'S FENCE. Kept out of `built_fences`
    # (which the axe may chop and the save file remembers) and drawn and
    # collided with separately: a wall you can hack a hole in is not a prison.
    camp_walls: list = []

    # THE GULAG IS BUILT WITH THE WORLD, and its guards are raised with it.
    # (Laid out here, before anything asks what may grow where, so the railway
    # corridor is clear ground from the first frame.)
    try:
        import gulag as _gulag
        _gulag.build()

        def _camp_guard(px, py, nation):
            return Soldier(px, py, nation, melee=False,
                           seed=random.randint(0, 2 ** 31))
        _camp_men = _gulag.make_guards(_camp_guard, nation=1)
        # THE CAMP GUARDS ARE NOT IN THE GENERAL ENEMY LIST AT ALL.
        #
        # Twenty men put into `enemies` means twenty men running the full
        # soldier brain every frame -- target acquisition, steering over every
        # collider in the world, line-of-sight against thirty mine buildings and
        # two houses -- to stand still on a post. That was the stutter at the
        # gate, and it was also why they wanted the player but never fired:
        # they were "in combat" without a clean shot. They are driven by the
        # camp itself now (gulag.tick), which makes them cheap AND certain.
        # REAL BUILDINGS AND A REAL FENCE: the game's own lists, so they
        # collide, block sight, are drawn by the fence and house code, and the
        # two buildings can be walked into like any other house.
        built_houses.extend(_gulag.houses())
        # THE BARN IS A WORKPLACE, ENTERED LIKE A MINE (E at the door).
        _barn = _gulag.prison()
        if _barn is not None and _barn not in placed_work:
            placed_work.append(_barn)
        # A HOLDING CELL BY EACH SETTLEMENT'S RAILWAY.
        try:
            import holding as _holding
            _holding.build(villages.villages)
            for _c in _holding.cells():
                if _c not in placed_work:
                    placed_work.append(_c)
        except Exception as _hce:
            plog.log("CELLS-ERROR", repr(_hce)[:140])

        def _attach_camp() -> None:
            """PUT THE CAMP BACK AFTER A SAVE HAS CLEARED THE YARD.

            # THE SPAWN GOES DOWN FIRST; A SAVE OVERRIDES IT. Applying the spawn after
    # the load is what threw a restored player back at the open-field spot.
    player.x, player.y = _hx, _hy
    load_now() empties placed_work and refills it from the save -- so a
            barn (and thirty mines) attached at world build were thrown away a
            moment later, which is why pressing E at the barn door did nothing.
            Called from both places; it will not double up.
            """
            try:
                import gulag as _g
                for _objs, _lst in ((_g.works(), placed_work),
                                    (_g.houses(), built_houses),
                                    (_g.walls(), camp_walls)):
                    for _o in _objs:
                        if _o not in _lst:
                            _lst.append(_o)
                _p = _g.prison()
                if _p is not None and _p not in placed_work:
                    placed_work.append(_p)
            except Exception:
                pass
        _gulag.plant_trees(trees)          # fifty REAL trees, in rows
        # WARM THE CAMP BEFORE ANYBODY WALKS IN. Ground, scatter, tree cells and
        # wild-plant cells round the gate are composed and cached at load, so
        # the first approach costs nothing: the hitch at the entrance was every
        # one of these being made on demand, one region at a time.
        try:
            import world as _world_mod
            _cx, _cy = _gulag.SITE
            for _dx in (-2600, 0, 2600):
                for _dy in (-1600, 0, 1600):
                    static_layer.warm(_cx + _dx, _cy + _dy, 1600, 900)
            trees.visible(_cx - 4000.0, _cy - 4000.0, 8000.0, 8000.0)
            try:
                import wildcrop as _wc
                _wc.visible(world, villages.villages, _cx - 4000.0,
                            _cy - 4000.0, 8000.0, 8000.0)
            except Exception:
                pass
            plog.log("WARM", "camp ground, trees and wild cells prepared")
        except Exception as _we:
            plog.log("WARM-ERROR", repr(_we)[:140])
        placed_work.extend(_gulag.works())
        camp_walls.extend(_gulag.walls())
        plog.log("GULAG", "built at %d,%d | guards %d | houses %d | mines %d "
                 "| walls %d | pines %d"
                 % (int(_gulag.SITE[0]), int(_gulag.SITE[1]), len(_camp_men),
                    len(_gulag.houses()), len(_gulag.works()),
                    len(_gulag.walls()), len(_gulag.tree_spots())))
    except Exception as _ge:
        plog.log("GULAG-ERROR", repr(_ge)[:160])
    built_gates: list = []
    fence_horizontal = True
    inside_house = None
    door_cooldown = 0.0
    backdrop = None            # the frozen outdoors behind a house's windows
    backdrop_for = None        # which house it belongs to
    backdrop_age = [0]         # how many frames it has been up
    kills = 0
    now = 0.0
    toast_text = ""
    toast_time = 0.0
    player_drip = 0.0
    hud_status = ""
    shade_cache: dict = {}
    active_chaos: list = []

    def award_levels() -> None:
        hudtime.award_levels(skills, player)

    def toast(message: str) -> None:
        nonlocal toast_text, toast_time
        toast_text = message
        toast_time = 1.6
        # WHAT HE WAS JUST TOLD, IN THE LOG. A refusal on screen that leaves no
        # trace is a refusal nobody can ever diagnose -- "it would not build"
        # cost an evening more than once.
        try:
            plog.log("TOAST", message)
        except Exception:
            pass

    def clamp_world() -> None:
        hudtime.clamp_world(player, WORLD_HALF)

    def try_talk() -> bool:
        """DID THE PLAYER CLICK THE MAN WHO ANSWERS QUESTIONS?

        His own test, in the EVENT LOOP, before anything else can consume the
        click -- items, the hotbar, trade. A cutout is drawn above its anchor,
        so the box is his whole silhouette: 34 px each way, from 80 px above his
        feet to 30 below.
        """
        tt = _TRUTH[0]
        if tt is None:
            for _n in list(village_mod.PEOPLE) + list(village_mod.TRAVELLERS):
                if getattr(_n, "is_truth_teller", False):
                    tt = _n
                    _TRUTH[0] = tt
                    break
        if tt is None:
            return False
        mx, my = pygame.mouse.get_pos()
        wx = cam_x + mx / ZOOM
        wy = cam_y + my / ZOOM
        if abs(wx - tt.x) < 34.0 and -80.0 < (wy - tt.y) < 30.0:
            dialogue_panel.open(tt, player, _main_capital()[0])
            pygame.mouse.set_visible(True)
            plog.log("TALK", "opened with", getattr(tt, "name", "?"))
            return True
        return False

    def respawn() -> None:
        nonlocal game_over
        game_over = False
        pygame.mouse.set_visible(False)
        player.respawn()
        # HE COMES BACK WITH YOU. A respawn moved the player to the middle of
        # the world and left the truth-teller standing where the body fell, out
        # of sight for ever.
        if _truth is not None:
            _truth_home[0], _truth_home[1] = player.x + 44.0, player.y
            _truth.x, _truth.y = _truth_home[0], _truth_home[1]
            _truth.alive = True
            _truth.asleep = False
            _truth.health = _truth.max_health
            _TRUTH[0] = _truth
        combat.bullets.clear()
        combat.flashes.clear()

    WITNESS_PX = 900.0        # close enough to have watched it happen

    def _see_murder(victim) -> None:
        interact.see_murder(victim)

    def _meet_army(trader, army, now) -> None:
        interact.meet_army(trader, army, now)

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
            toast("%s looks you over and waves you through"
              % getattr(npc, "name", "The guard"))
            return
        skill = max(0.0, min(10.0, float(getattr(player, "smuggling", 0.0))))
        found = min(1.0, units / 100.0) * (1.0 - 0.09 * skill)
        if random.random() < found:
            toast("%s finds it. %d against the wall."
                  % (getattr(npc, "name", "The guard"), units))
            commit_crime()
            return
        player.smuggling = min(10.0, skill + 0.06 + units * 0.001)
        toast("Searched clean   (smuggling %.1f)" % player.smuggling)

    def open_trade(npc) -> None:
        """CLICK A MAN AND TALK TO HIM. EVERY MAN, not only the truth-teller.

        The four questions are the same for everybody -- what he thinks of the
        Dictator, what he thinks of you, what he is craving, and whether he
        wants to trade -- because every man has the fields they read. "Wanna
        trade?" is what opens the counter (see open_trade_menu), so the trade
        menu is now a thing you ask for, not the first thing a click does.
        """
        try:
            npc = make_tradeable(npc)
        except Exception:
            pass
        dialogue_panel.open(npc, player, _main_capital()[0])
        pygame.mouse.set_visible(True)
        plog.log("TALK", "opened with", getattr(npc, "name", "?"),
                 "job", getattr(npc, "job", None),
                 "truth", getattr(npc, "is_truth_teller", False))

    def open_trade_menu(npc) -> None:
        """THE COUNTER, when he asks for it."""
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
        plog.log("TRADE", "opened with", getattr(npc, "name", "?"))

    def nearest_hostile(npc):
        return interact.nearest_hostile(npc, player)

    def commit_crime(where=None) -> None:
        interact.commit_crime(where, villages, player, now, _WORK)

    def player_hunted() -> bool:
        return playerutil.player_hunted(visible_villages)

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
        playerutil.settle_reload(player, inventory, toast)

    def banish(nation) -> None:
        playerutil.banish(player, enemies, nation, toast, nation_name)

    # -- item actions -------------------------------------------------------
    def fire() -> None:
        combat_actions.fire(player, inventory, skills, combat, cam_x, cam_y,
                            ZOOM, toast)

    def use_first_aid() -> None:
        playerutil.use_first_aid(player, inventory, toast)

    def use_axe() -> None:
        nonlocal kills
        _g = SimpleNamespace(
            player=player, skills=skills, inventory=inventory, combat=combat,
            enemies=enemies, blood=blood, rabbits=rabbits, hub_world=hub_world,
            truth=_TRUTH, trees=trees, built_fences=built_fences,
            built_gates=built_gates, visible_villages=visible_villages,
            work_lanes=_WORK, now=now,
            toast=toast, mark_dirty=mark_dirty, pay_share=pay_share,
            commit_crime=commit_crime, see_murder=_see_murder, banish=banish)
        kills = combat_actions.use_axe(_g, kills)

    def use_pickaxe() -> None:
        combat_actions.use_pickaxe(player, combat, ore_field, inventory,
                                   pay_share, mark_dirty, toast)

    EAT_RESTORE = 35.0      # any food fills the same belly, as it does for
                            # every villager: one item, one meal.

    def click_a_man(at=None) -> bool:
        """CLICK A MAN, OPEN THAT MAN. Nothing else.

        The nearest living man to the point you clicked, within 48 px. If he is
        the truth-teller his questions open; if he is anybody else his trade
        opens. It does not care what you are holding, where you are standing,
        whether a house is open, or which men happen to be on screen -- every
        man in the world is a candidate, because a man you can see is a man in
        a village's list.
        """
        # THE CLICK'S OWN POSITION. The event carries it; the cursor is only a
        # fallback, because a click is where it happened, not where the pointer
        # happens to be when the frame reads it.
        if at is not None:
            mx, my = at
        else:
            mx, my = pygame.mouse.get_pos()
        wx = cam_x + mx / ZOOM
        wy = cam_y + my / ZOOM
        # A BODY FIRST: it is not a man you can talk to, and `open_trade` on a
        # corpse would be nonsense -- but a body is what you loot.
        _body = corpse_mod.nearest(wx, wy)
        if _body is not None:
            nonlocal body_open, body_panel
            body_panel = ChestPanel(inventory, _body.pack,
                                    top_label=getattr(_body, "name", "a body"))
            body_open = True
            pygame.mouse.set_visible(True)
            plog.log("BODY-OPEN", getattr(_body, "name", "?"), "at",
                     int(math.hypot(_body.x - player.x, _body.y - player.y)), "px")
            return True
        best, bd = None, 1e18
        # HIM FIRST AND ALWAYS. He is a village's man, but a village's list can
        # be rebuilt at load -- so he is a candidate in his own right.
        if _TRUTH[0] is not None:
            best = _TRUTH[0]
            bd = math.hypot(best.x - wx, best.y - wy)
        for _v in villages.villages:
            for _n in _v.npcs:
                if not getattr(_n, "alive", True) or getattr(_n, "in_interior", False):
                    continue
                d = math.hypot(_n.x - wx, _n.y - wy)
                if d < bd:
                    best, bd = _n, d
        for _n in list(getattr(village_mod, "TRAVELLERS", ())):
            if not getattr(_n, "alive", True):
                continue
            d = math.hypot(_n.x - wx, _n.y - wy)
            if d < bd:
                best, bd = _n, d
        # NOTHING WITHIN 48 PX? THEN ANY CLICK NEAR HIM OPENS HIM. There is
        # exactly one truth-teller in the world; if you are standing beside him
        # and you click, that click is for him -- no distance arithmetic, no
        # camera/zoom to get wrong, nothing left to fail.
        if best is None or bd > 48.0:
            # NOTHING WAS CLICKED. This used to open the truth-teller whenever
            # he happened to be within 140 px OF THE PLAYER -- a third of the
            # screen -- so a click on empty ground across the square opened a
            # conversation. A man is opened by clicking HIM.
            plog.log("PICK-NONE", "nearest",
                     int(bd) if best is not None else -1)
            return False
        if getattr(best, "is_truth_teller", False):
            dialogue_panel.open(best, player, _main_capital()[0])
            toast("%s looks at you." % getattr(best, "name", "He"))
        else:
            open_trade(best)
        pygame.mouse.set_visible(True)
        plog.log("PICK", getattr(best, "name", "?"), "at", int(bd),
                 "truth", getattr(best, "is_truth_teller", False))
        return True

    def on_click() -> None:
        nonlocal confirm_open
        _st0 = inventory.selected_stack()
        plog.log("CLICK", "on_click", "item",
                 (_st0.defn.id if _st0 else None), "dead", player.dead,
                 "house", inside_house is not None,
                 "at", "%d,%d" % (int(player.x), int(player.y)))
        if player.dead:
            return
        # ---- HIM, BEFORE ANYTHING ELSE -------------------------------------
        # Every other path in this handler can return first: a held item, a
        # house, an axe, the reach gate, the list of men in view. This does not
        # depend on any of them. Click his body and the questions open.
        # ALWAYS FIND HIM. The handle can be stale after a reload; his own
        # town's list and the wanderers' list are both searched, so there is no
        # state in which he exists and this cannot find him.
        _tt0 = _TRUTH[0]
        if _tt0 is None:
            for _tv in villages.villages:
                for _tn in _tv.npcs:
                    if getattr(_tn, "is_truth_teller", False):
                        _tt0 = _tn
                        _TRUTH[0] = _tt0
                        break
                if _tt0 is not None:
                    break
        if _tt0 is not None:
            _tmx, _tmy = pygame.mouse.get_pos()
            _twx = cam_x + _tmx / ZOOM
            _twy = cam_y + _tmy / ZOOM
            _tdx, _tdy = _twx - _tt0.x, _twy - _tt0.y
            # LOGGED ON EVERY CLICK, HIT OR MISS, WITH THE NUMBERS. If this ever
            # fails again, the log says by how much rather than needing a guess.
            plog.log("CLICK-HIM", "click", "%d,%d" % (int(_twx), int(_twy)),
                     "him", "%d,%d" % (int(_tt0.x), int(_tt0.y)),
                     "d", "%d,%d" % (int(_tdx), int(_tdy)))
            # HIS BODY, AND NOT A SQUARE AROUND HIS FEET. The cutout is drawn
            # above the anchor, so the box is the same one every other man is
            # hit with: about his width across, and up to his head.
            if abs(_tdx) <= 26.0 and -64.0 < _tdy < 22.0:
                dialogue_panel.open(_tt0, player, _main_capital()[0])
                pygame.mouse.set_visible(True)
                plog.log("TALK", "opened with", getattr(_tt0, "name", "?"),
                         "click", "%d,%d" % (int(_twx), int(_twy)),
                         "him", "%d,%d" % (int(_tt0.x), int(_tt0.y)))
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
        # TALKING COMES BEFORE THE AXE. `on_click` returned at the axe branch
        # below, so with a weapon in hand -- and the starter kit IS an axe --
        # no man could ever be spoken to. The man who answers questions is
        # clicked first, and the axe still works on everybody else.
        if _TRUTH[0] is not None:
            _mx, _my = pygame.mouse.get_pos()
            _wx = cam_x + _mx / ZOOM
            _wy = cam_y + _my / ZOOM
            if (math.hypot(_wx - _TRUTH[0].x, _wy - _TRUTH[0].y) < 26.0
                    and math.hypot(_wx - player.x, _wy - player.y) <= REACH + 40.0):
                dialogue_panel.open(_TRUTH[0], player, _main_capital()[0])
                pygame.mouse.set_visible(True)
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

        # THE MAN WHO ANSWERS QUESTIONS IS CLICKED ON HIS BODY, NOT HIS FEET.
        # A cutout figure is drawn ABOVE its anchor point, so a click on the
        # chest is 20-40 px from (x, y) and a 22 px circle around the feet
        # missed him entirely. He is found first, by his silhouette.
        _tt = _TRUTH[0]
        if _tt is None:
            for _n in list(village_mod.PEOPLE) + list(village_mod.TRAVELLERS):
                if getattr(_n, "is_truth_teller", False):
                    _tt = _n
                    break
        if _tt is not None and abs(wx - _tt.x) < 30.0 and -70.0 < (wy - _tt.y) < 26.0:
            dialogue_panel.open(_tt, player, _main_capital()[0])
            pygame.mouse.set_visible(True)
            return

        # Clicking a villager while not wielding a weapon opens trade.
        if math.hypot(wx - player.x, wy - player.y) <= REACH + 24.0:
            _folk = [n for v in visible_villages for n in v.npcs]
            if _TRUTH[0] is not None and _TRUTH[0] not in _folk:
                _folk.append(_TRUTH[0])         # he is a man like any other
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
            plog.log("CLICK", "folk", len(_folk), "reach_test", True,
                     "mouse", "%d,%d" % (int(wx), int(wy)),
                     "player", "%d,%d" % (int(player.x), int(player.y)))
            for npc in _folk:
                    _dd = math.hypot(npc.x - wx, npc.y - wy)
                    if _dd < 60.0:
                        plog.log("CLICK-NEAR", getattr(npc, "name", "?"),
                                 "d", int(_dd), "dx", int(npc.x - wx),
                                 "dy", int(npc.y - wy),
                                 "truth", getattr(npc, "is_truth_teller", False),
                                 "alive", getattr(npc, "alive", None))
                    # A cutout is drawn ABOVE its anchor, so the hit area is his
                    # body, not a circle at his feet -- the same test for every
                    # man in the world, villagers included.
                    if (getattr(npc, "alive", True)
                            and abs(npc.x - wx) < 26.0
                            and -64.0 < (wy - npc.y) < 22.0):
                        if getattr(npc, "is_truth_teller", False):
                            dialogue_panel.open(npc, player, _main_capital()[0])
                            pygame.mouse.set_visible(True)
                            return
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
                            skill=skills.farming,
                            tx=tx, ty=ty, share=pay_share):
                # LEAF IS ILLEGAL. Any agent close enough to have watched it
                # now knows it, and says so to the next one he meets.
                nemesis.note_offence_seen(player, "grew",
                                          crop.LEAF_ITEM.get(plot.kind,
                                                             plot.kind))
                # The same rate the farmers get. At the old default (0.12) the
                # player reached skill 8 in ~67 harvests -- SSS tobacco by day
                # two, against three weeks for the men who do it for a living.
                skills.gain_farming(0.02)
                if (tx, ty) in village_plots and not tile_is_mine(tx, ty):
                    commit_crime()
            return
        if plot is not None and plot.kind in crop.FOOD_KINDS:
            if farm.harvest(world, inventory, plot, now, toast, tx=tx, ty=ty,
                            skill=skills.farming,
                            share=pay_share):
                if (tx, ty) in village_plots and not tile_is_mine(tx, ty):
                    commit_crime()
            return

        wild = wildcrop.at(world, tx, ty, visible_villages)
        if wild is not None:
            wildcrop.harvest(world, tx, ty, wild[0], wild[1], inventory, toast,
                             share=pay_share)
            if wild[0] in crop.LEAF_KINDS:
                nemesis.note_offence_seen(player, "grew",
                                          crop.LEAF_ITEM.get(wild[0], wild[0]))
            skills.gain_farming(0.02)      # wild or sown, the hand learns alike
            return

        if item_id == "shovel":
            farm.dig(world, ground, tx, ty, toast)
        elif item_id == "watering_can":
            farm.water(world, ground, tx, ty, toast)
        elif item_id in crop.SEED_CROP:
            _sown = farm.plant(world, ground, inventory, tx, ty, now, toast,
                               item_id, skills.farming)
            if _sown and tile_is_mine(tx, ty):
                # A PLOT OF HIS OWN, and what a hired farmer can be put to.
                if not isinstance(getattr(player, "plots", None), set):
                    player.plots = set()
                player.plots.add((tx, ty))

    # -- building placement -------------------------------------------------
    def placement_pos():
        # THE ROOM IS 1:1, SO THE ROOM'S MOUSE IS THE WINDOW'S MOUSE. The
        # `wmouse_x` value is the OUTDOOR mouse (window / ZOOM), and it is only
        # re-mapped inside the room branch AFTER the event loop has already
        # run -- so a click read the outdoor mouse against the indoor camera,
        # landed a third of a screen away, and the floor always read as full.
        if inside_house is not None or (inside_mine is not None
                                        and getattr(inside_mine, "kind", "") == "house"):
            mx, my = pygame.mouse.get_pos()
        else:
            mx, my = wmouse_x, wmouse_y
        return (round((cam_x + mx) / 8.0) * 8.0,
                round((cam_y + my) / 8.0) * 8.0)

    def placement_box(x, y):
        # THE FOUR TRADES OUT OF DOORS, at the size of the thing itself (the
        # same rects industry.Workplace builds, without building one every
        # frame to ask).
        _sizes = {"lab": (96, 66), "brewery": (116, 78),
                  "smith": (122, 110), "mine": (136, 112),
                  "stall": (96, 64)}
        if placing in _sizes:
            _w, _h = _sizes[placing]
            rect = pygame.Rect(int(x - _w / 2), int(y - _h / 2), _w, _h)
            return (0.0, -1.0), rect, rect.inflate(70, 70)
        if placing == "plot":
            rect = pygame.Rect(int(x - 40), int(y - 40), 80, 80)
            return (0.0, -1.0), rect, rect.inflate(8, 8)
        if placing == "demolish":
            rect = pygame.Rect(int(x - 12), int(y - 12), 24, 24)
            return (0.0, -1.0), rect, rect
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

    def _own_things():
        """Everything of HIS a click could take down, smallest first."""
        out = []
        for _r in built_plots:
            out.append((_r, "plot", _r))
        for _wp in placed_work:
            out.append((_wp.rect, "station", _wp))
        for _r in built_gates:
            out.append((_r, "gate", _r))
        for _r in built_fences:
            out.append((_r, "fence", _r))
        for _h in built_houses:
            out.append((_h.rect, "house", _h))
        return out

    def demolish_at(wx: float, wy: float) -> str:
        """ONE CLICK TAKES ONE THING OF HIS DOWN -- the smallest under it."""
        hits = [(r.w * r.h, kind, r, obj) for (r, kind, obj) in _own_things()
                if r.collidepoint(wx, wy)]
        if not hits:
            return ""
        hits.sort(key=lambda h: h[0])
        _area, kind, rect, obj = hits[0]
        if kind == "plot":
            if rect in built_plots:
                built_plots.remove(rect)
            if isinstance(getattr(player, "plots", None), set):
                player.plots.discard(tuple(rect.topleft))
            mark_dirty()
            return "Plot cleared"
        if kind == "station":
            if obj in placed_work:
                placed_work.remove(obj)
            if obj in (getattr(player, "workplaces", ()) or ()):
                player.workplaces.remove(obj)
            if getattr(obj, "is_stall", False):
                # A STALL TAKEN DOWN IS GONE: its goods and its purse come
                # back to the player rather than vanishing with the timber.
                _back = int(getattr(obj, "coins", 0) or 0)
                for _s in list(getattr(obj, "stock", None).slots
                               if getattr(obj, "stock", None) else ()):
                    if _s is not None:
                        inventory.add(_s.defn.id, _s.count, _s.quality)
                if _back:
                    inventory.add("coin", _back)
                if obj in stall_mod.stalls_of(player):
                    stall_mod.stalls_of(player).remove(obj)
                for _n in (getattr(player, "workers", ()) or ()):
                    if getattr(_n, "to_market", False):
                        _n.to_market = False
                mark_dirty()
                return "Stall taken down -- goods and %d coin returned" % _back
            mark_dirty()
            return "Stations taken down"
        if kind == "gate" and rect in built_gates:
            built_gates.remove(rect)
            mark_dirty()
            return "Gate taken down"
        if kind == "fence" and rect in built_fences:
            built_fences.remove(rect)
            mark_dirty()
            return "Fence taken down"
        if kind == "house" and obj in built_houses:
            built_houses.remove(obj)
            mark_dirty()
            return "House taken down"
        return ""

    def salary_chest():
        """WHERE THE MEN ARE PAID FROM: a chest in a house of his, in his hub.

        The salary is not carried in his pack -- he has to PUT IT IN THE CHEST,
        the way a man with a yard and hands would. No chest in the hub, or an
        empty one, and the day is missed.
        """
        for _h in built_houses:
            _in = getattr(_h, "interior", None)
            if _in is None or getattr(_in, "chest", None) is None:
                continue
            if hubs.in_player_hub(_h.rect, hub_world.hubs):
                return _in.chest
        return None

    def hub_stall():
        """THE PLAYER'S STALL: the one in his own hub, or his only one."""
        try:
            _mine = stall_mod.in_hub(player, getattr(player, "hub", None))
            if _mine is not None:
                return _mine
            _all = stall_mod.stalls_of(player)
            return _all[0] if _all else None
        except Exception:
            return None

    def near_stall():
        return nearby.near_stall(player)

    def _town_price_for(item, grade):
        return nearby.town_price_for(player, visible_villages, item, grade)

    def _on_stall_sales(sales) -> None:
        """WHAT A CART BOUGHT, applied here, where the goods and the coin are."""
        _st = hub_stall()
        for rec in sales or ():
            try:
                item, grade, qty, coins = rec
            except Exception:
                continue
            if _st is None:
                break
            if _st.sold(item, qty, coins, "free trader", grade=int(grade)):
                try:
                    import quality as _q
                    _g = _q.letter(int(grade))
                except Exception:
                    _g = "?"
                toast("Sold %d %s (%s) -- %d coin in the stall"
                      % (int(qty), str(item).replace("_", " "), _g, int(coins)))

    def _commit_plot() -> None:
        """A PLOT IS A RECTANGLE HE DRAWS: no cost, no bench, just ground."""
        nonlocal placing
        start = plot_start[0]
        plot_start[0] = None
        if start is None:
            return
        x2, y2 = placement_pos()
        x1, y1 = start
        rect = pygame.Rect(int(min(x1, x2)), int(min(y1, y2)),
                           int(abs(x2 - x1)), int(abs(y2 - y1)))
        if rect.w < 32 or rect.h < 32:
            toast("Too small for a plot")
            return
        if not hubs.land_ok(rect, villages.villages, hub_world.hubs,
                           player.x, player.y):
            toast("Not your land -- the wild, or your own hub")
            return
        built_plots.append(rect)
        if not isinstance(getattr(player, "plots", None), set):
            player.plots = set()
        player.plots.add(tuple(rect.topleft))
        player.yard_plots = [tuple(_r) for _r in built_plots]
        mark_dirty()
        if hubs.in_player_hub(rect, hub_world.hubs):
            toast("Plot staked on your own ground")
        else:
            _h = hub_world.add_player_hub(player, rect.inflate(120, 120).copy(),
                                          [], [])
            if _h is not None:
                nemesis.PLACES.append(_h)
                player.work_post = (_h.x, _h.y + 40)
                player.hub = _h
                plog.log("PHASE-HUB", _h.name, "at",
                         "%d,%d" % (int(_h.x), int(_h.y)),
                         "post", player.work_post)
                toast("Plot staked -- this is your hub now:   %s" % _h.name)
            else:
                toast("Plot staked")
        placing = None
        pygame.mouse.set_visible(False)

    def try_place() -> None:
        nonlocal placing
        x, y = placement_pos()
        if placing == "demolish":
            _wm = cam_x + (pygame.mouse.get_pos()[0] / ZOOM)
            _wm2 = cam_y + (pygame.mouse.get_pos()[1] / ZOOM)
            _said = demolish_at(_wm, _wm2)
            toast(_said or "Nothing of yours there")
            placing = None
            pygame.mouse.set_visible(False)
            return
        if placing == "plot":
            return                      # a plot is drawn, not clicked (see below)
        facing, rect, sight = placement_box(x, y)
        if placing in ("fence", "gate"):
            if not can_place(rect, sight):
                toast("Can't build there")
                return
            if not hubs.land_ok(rect, villages.villages, hub_world.hubs,
                               player.x, player.y):
                toast("Not your land -- the wild, or your own hub")
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
            # A YARD HE HAS CLOSED IN THE WILD IS HIS HUB. Checked each time he
            # sets a piece down -- the flood fill is a few thousand cells and it
            # only ever runs while he is building.
            try:
                _yard, _ring = fence.enclosure(built_fences + built_gates,
                                               player.x, player.y)
                if _yard is not None:
                    _wild = True
                    for _v in (list(villages.villages)
                               + list(getattr(hub_world, "hubs", ()))):
                        _fr = getattr(_v, "fence_rect", None)
                        if _fr is not None and _fr.colliderect(
                                _yard.inflate(600, 600)):
                            _wild = False
                            break
                    if _wild:
                        _h = hub_world.add_player_hub(player, _yard, _ring,
                                                      built_gates)
                        if _h is not None:
                            nemesis.PLACES.append(_h)
                            toast("This is your hub now:   %s" % _h.name)
                            plog.log("HUB", "fenced", _h.name, "at",
                                     "%d,%d" % (int(_h.x), int(_h.y)),
                                     "%dx%d" % (_yard.w, _yard.h))
            except Exception as _he:
                plog.log("HUB-ERROR", repr(_he)[:200])
            mark_dirty()
            toast(f"{name} built" if test_mode else f"{name} built   -{cost} wood")
            placing = None
            pygame.mouse.set_visible(False)
            return
        if placing == "stall":
            # A STALL STANDS IN HIS HUB AND NOWHERE ELSE. The land question is
            # asked first, so a man who tries to put one in the open is told
            # why and does not lose the timber.
            if not hubs.in_player_hub(rect, hub_world.hubs):
                toast("A stall must stand inside your own hub")
                placing = None
                pygame.mouse.set_visible(False)
                return
            if not can_place(rect, sight):
                toast("No clear ground here")
                return
            _hub = next((h for h in hub_world.hubs
                         if getattr(h, "is_player_hub", False)
                         and h.fence_rect.colliderect(rect)), None)
            if _hub is None:
                toast("A stall must stand inside your own hub")
                placing = None
                pygame.mouse.set_visible(False)
                return
            if stall_mod.in_hub(player, _hub) is not None:
                toast("You already have a stall in this hub")
                placing = None
                pygame.mouse.set_visible(False)
                return
            _cost = build_materials("stall")
            if not test_mode:
                for _it, _q in _cost.items():
                    if inventory.count_of(_it) < _q:
                        toast("Need %d %s" % (_q, _it))
                        placing = None
                        pygame.mouse.set_visible(False)
                        return
                for _it, _q in _cost.items():
                    inventory.consume(_it, _q)
            _st = stall_mod.add(player, _hub, x, y)
            if _st is None:
                toast("A stall must stand inside your own hub")
                placing = None
                pygame.mouse.set_visible(False)
                return
            placed_work.append(_st)
            mark_dirty()
            toast("Market stall built   -%d wood" % int(_cost.get("wood", 0)))
            placing = None
            pygame.mouse.set_visible(False)
            return
        if placing in ("lab", "brewery", "smith", "mine", "dummy", "target"):
            _wp = industry.Workplace(placing, x, y, random.randrange(1 << 30))
            if not hubs.land_ok(_wp.rect, villages.villages, hub_world.hubs,
                               player.x, player.y):
                toast("Not your land -- the wild, or your own hub")
                return
            if not can_place(_wp.rect, _wp.rect.inflate(70, 70)):
                toast("No clear ground here")
                return
            _cost = build_materials(placing)
            if not test_mode:
                for _it, _q in _cost.items():
                    if inventory.count_of(_it) < _q:
                        toast("Need %d %s" % (_q, _it))
                        placing = None
                        pygame.mouse.set_visible(False)
                        return
                for _it, _q in _cost.items():
                    inventory.consume(_it, _q)
            _wp.worker = None
            _wp.owner = player
            placed_work.append(_wp)
            if not isinstance(getattr(player, "workplaces", None), list):
                player.workplaces = []
            player.workplaces.append(_wp)          # he can put a man to it
            mark_dirty()
            _land = hubs.in_player_hub(_wp.rect, hub_world.hubs)
            if not _land:
                # THE WILD IS HIS NOW. A bench, a forge or a shaft on open
                # ground is a claim: the yard around it is his hub.
                _yard = _wp.rect.inflate(320, 320).copy()
                _h = hub_world.add_player_hub(player, _yard, [], [])
                if _h is not None:
                    nemesis.PLACES.append(_h)
                    player.work_post = (_h.x, _h.y + 40)
                    player.hub = _h
                    plog.log("PHASE-HUB", _h.name, "at",
                             "%d,%d" % (int(_h.x), int(_h.y)),
                             "post", player.work_post)
                    toast("Built -- this is your hub now:   %s" % _h.name)
                else:
                    toast("Built")
            else:
                toast("Built on your own ground")
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
        elif placing == "plot":
            hint_text = "Drag a rectangle   ·   right-click to cancel"
        elif placing == "demolish":
            hint_text = "Click a thing of yours to take it down   ·   right-click to cancel"
        if placing == "plot" and plot_start[0] is not None:
            # THE RECTANGLE HE IS DRAWING, live under the mouse.
            _sx, _sy = plot_start[0]
            _ex, _ey = px_, py_
            _drag = pygame.Rect(int(min(_sx, _ex)), int(min(_sy, _ey)),
                                int(abs(_ex - _sx)), int(abs(_ey - _sy)))
            _ok = hubs.land_ok(_drag, villages.villages, hub_world.hubs,
                               player.x, player.y)
            _col = (126, 224, 148) if _ok else (226, 96, 84)
            _dr = pygame.Rect(_drag.x - cam_x, _drag.y - cam_y,
                              _drag.w, _drag.h)
            _df = pygame.Surface((max(1, _dr.w), max(1, _dr.h)), pygame.SRCALPHA)
            _df.fill((_col[0], _col[1], _col[2], 48))
            screen.blit(_df, _dr.topleft)
            pygame.draw.rect(screen, _col, _dr, 2)
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

    class _HouseBar:
        def __init__(self, house, room, door) -> None:
            self.house = house
            self.room = room
            self.door = door
            self.kind = "house"

    def enter_house(house) -> None:
        nonlocal inside_house, backdrop, door_cooldown, cam_x, cam_y
        interior = getattr(house, "interior", None)
        if interior is None:
            return
        # BAKE THE ROOM ON THE WAY IN, not on the first frame indoors: a
        # room's art never changes, so it is painted once and then it is one
        # blit a frame. This is why a mine is instant; now a house is too.
        try:
            interior.bake()
        except AttributeError:
            pass
        try:
            player.world_xy = (float(player.x), float(player.y))
        except Exception:
            pass
        plog.log("ENTER-HOUSE", getattr(house, "name", "?"),
                 "from", int(player.x), int(player.y),
                 "-> spawn", int(interior.spawn[0]), int(interior.spawn[1]),
                 "room", interior.W, interior.H)
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
        plog.log("EXIT-HOUSE", "out to", int(player.x), int(player.y))
        inside_house = None
        door_cooldown = 0.7

    _draws: dict = {}

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
        for rect in camp_walls:
            if view.colliderect(rect):
                fence.draw_segment(target, cx, cy, rect)
        for rect in built_gates:
            if view.colliderect(rect):
                fence.draw_gate(target, cx, cy, rect)
        # THE CAMP, drawn on the ground.
        try:
            import gulag as _gulag_d
            _gulag_d.draw(target, cx, cy, view)
        except Exception as _ge2:
            if not getattr(main, "_ge2_seen", False):
                main._ge2_seen = True
                import traceback as _tb2
                plog.log("GULAG-DRAW-ERROR", repr(_ge2)[:120])
                plog.log("GULAG-TRACE", _tb2.format_exc()[:900])
        # THE RAILWAY, on the ground under everything that stands on it.
        try:
            import rail as _rail
            _rail.ensure(villages.villages)
            _rail.draw(target, cx, cy, vw, vh)
        except Exception as _re:
            plog.log("RAIL-ERROR", repr(_re)[:120])
        # ...AND THEN THE ENGINE, ON TOP OF ITS OWN TRACK. Riding, though, the
        # ground is painted first and the track goes over it: from the train
        # the rail is the thing that matters, not the grass under it.
        if not getattr(player, "aboard", False):
            try:
                _TEST_TRAIN[0].draw(target, cx, cy)
                _TEST_TRAIN[0].draw_knocked(target, cx, cy)
            except Exception:
                pass
        items = []
        # THE DEAD ARE ON THE GROUND. Bodies are sorted into the same painter's
        # list as the living, so a man walking in front of a corpse stands in
        # front of it and one behind it does not. Nothing ever called
        # corpse.draw: a body could be clicked and looted and was never ONCE
        # put on the screen.
        for _c in corpse_mod.CORPSES:
            if not view.collidepoint(_c.x, _c.y):
                continue
            items.append((_c.y, lambda c=_c: c.draw(target, cx, cy, now)))
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
                if npc is _TRUTH[0]:
                    continue        # drawn once, with the world, below
                if not view.collidepoint(npc.x, npc.y):
                    continue
                near = show_names and ((npc.x - player.x) ** 2
                                       + (npc.y - player.y) ** 2) < 260.0 ** 2
                items.append((npc.y, lambda n=npc, s=near:
                              n.draw(target, cx, cy, s)))
        if _TRUTH[0] is not None:
            _tn = _TRUTH[0]
            try:
                _draws["n"] = _draws.get("n", 0) + 1
                if _draws["n"] % 120 == 1:
                    plog.log("TRUTH-DRAW", "at", "%d,%d" % (int(_tn.x), int(_tn.y)),
                             "view", view.collidepoint(_tn.x, _tn.y),
                             "player", "%d,%d" % (int(player.x), int(player.y)))
            except Exception:
                pass
            if view.collidepoint(_tn.x, _tn.y):
                _tnear = show_names and ((_tn.x - player.x) ** 2
                                         + (_tn.y - player.y) ** 2) < 260.0 ** 2
                items.append((_tn.y, lambda n=_tn, s=_tnear:
                              n.draw(target, cx, cy, s)))
        items.sort(key=lambda item: item[0])
        for _y, draw in items:
            draw()
        if getattr(player, "aboard", False):
            # RIDING: the permanent way is drawn OVER the ground, and the
            # engine over the rail.
            try:
                import rail as _rail_r
                _rail_r.ensure(villages.villages)
                _rail_r.draw(target, cx, cy, vw, vh)
            except Exception:
                pass
            try:
                _TEST_TRAIN[0].draw(target, cx, cy)
                _TEST_TRAIN[0].draw_knocked(target, cx, cy)
            except Exception:
                pass


    # -- THE NEWS, AS A MAN HEARS IT ----------------------------------------
    _chat: list = []          # [text, seconds of life left] -- one shown at a time
    _news_lab = [None, None]  # the last bubble text and its rendered surface
    _hear_at = [0.0]          # hear_news runs FOUR TIMES A SECOND, not sixty
    _heard: set = set()       # (village, army, nation): what he already knows

    def hear_news() -> None:
        newsbubble.hear_news(player, _chat, _hear_at, _heard, visible_villages,
                             now, nation_name)

    def tick_news(dt: float) -> None:
        newsbubble.tick_news(_chat, dt)

    def draw_news(surf, cam_x: float, cam_y: float, w: int, h: int) -> None:
        newsbubble.draw_news(surf, cam_x, cam_y, w, h, _chat, player,
                             _news_lab, speech_font)

    def pay_share(item: str, gained: int) -> int:
        return nearby.pay_share(item, gained, player, inventory, toast)

    def near_board():
        return nearby.near_board(player, visible_villages, REACH)

    def near_chest() -> bool:
        return houseuse.near_chest(player, inside_house)

    def near_brew() -> bool:
        return houseuse.near_brew(player, inside_house)

    def mash_at_table() -> None:
        houseuse.mash_at_table(inventory, skills, toast)

    def use_barrel() -> None:
        houseuse.use_barrel(player, inside_house, inventory, skills, now, toast)

    def near_lab() -> bool:
        return houseuse.near_lab(player, inside_house)

    def craft_at_table() -> None:
        houseuse.craft_at_table(player, inventory, skills, toast)

    def near_workshop() -> bool:
        return houseuse.near_workshop(player, inside_house)

    def near_workplace():
        return nearby.near_workplace(player, placed_work, visible_villages)

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
        return hudtime.near_fireplace(player, inside_house)

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
    # (A SECOND GRID STOOD HERE, FOR A QUESTION NOBODY ASKS ANY MORE. It held
    # only soldiers, because a villager looking for "a soldier of another
    # nation" threw the wolves away -- and with one nation in the world the
    # answer was always nobody. See nearest_hostile.)

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
        return hudtime.day_phase(now, DAY_LENGTH)

    def _nearest_town():
        """THE NEAREST SETTLEMENT, WHICHEVER ONE IT IS.

        It used to hand the map `player.settled_at` -- his own town -- and he
        has none: with no backstory he arrives owning nothing and belonging
        nowhere, so the gold pin had nothing to draw and the map showed one
        outlaw hut in an empty country. A man with no town still needs to know
        where the nearest one is.
        """
        # ONLY A TOWN YOU COULD ACTUALLY WALK TO. The world is laid out one ring
        # beyond the edge it plays in, so men on the road have neighbours to
        # trade with -- but those cells stand out past WORLD_HALF, where the
        # player is clamped and the map ends. Pinning one sent a man walking at
        # a settlement he could never reach.
        towns = [v for v in (getattr(villages, "villages", ()) or ())
                 if abs(v.x) <= WORLD_HALF and abs(v.y) <= WORLD_HALF]
        if not towns:
            return None
        return min(towns, key=lambda v: (v.x - player.x) ** 2
                   + (v.y - player.y) ** 2)

    def speed_button() -> pygame.Rect:
        return hudtime.speed_button(vw, vh)

    def draw_speed_button() -> None:
        hudtime.draw_speed_button(screen, font, test_mode, time_scale, vw, vh)

    def night_factor(t=None) -> float:
        return hudtime.night_factor(now, DAY_LENGTH, t)

    def next_morning(t: float) -> float:
        return hudtime.next_morning(t, now, DAY_LENGTH)

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
        hudtime.draw_status(screen, font, hud_status, vw)

    def tick_conquest(dt) -> None:
        hudtime.tick_conquest(active_chaos, player, toast, dt)

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
        hudtime.draw_hunger_gray(screen, player)

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
        _g = SimpleNamespace(
            built_houses=built_houses, villages=villages, player=player,
            inventory=inventory, panel=panel, skills=skills, now=now, kills=kills,
            world=world, compass_state=compass_state, ore_field=ore_field,
            trees=trees, built_fences=built_fences, built_gates=built_gates,
            built_plots=built_plots, placed_work=placed_work, hub_world=hub_world,
            train=_TEST_TRAIN, inside_house=inside_house)
        savegame.write(_g)

    def load_now() -> None:
        nonlocal now, kills, cam_x, cam_y
        _g = SimpleNamespace(
            villages=villages, player=player, inventory=inventory, panel=panel,
            enemies=enemies, built_houses=built_houses, built_fences=built_fences,
            built_gates=built_gates, built_plots=built_plots, placed_work=placed_work,
            hub_world=hub_world, train=_TEST_TRAIN, camp_walls=camp_walls,
            width=WIDTH, height=HEIGHT, zoom=ZOOM, now=now, kills=kills,
            world=world, observer_=observer_, active_chaos=active_chaos,
            ground=ground, cam_x=cam_x, cam_y=cam_y, skills=skills, trees=trees)
        savegame.restore(_g)
        now, kills = _g.now, _g.kills
        cam_x, cam_y = _g.cam_x, _g.cam_y

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
    # AN AXE IN HIS HAND, ONCE THE SAVE HAS HAD ITS SAY. The starting kit is
    # added before the save is read -- so a restored pack overwrote it and a
    # man who loaded a game had no axe at all. Anyone with nothing to cut with
    # gets one; a man who already has a tool keeps his own.
    if (inventory.count_of("axe") <= 0
            and inventory.count_of("pickaxe") <= 0):
        inventory.add("axe", 1)
        mark_dirty()

    # ...AND THE WORLD IS A THOUSAND PEOPLE AFTER THE LOAD, TOO. The save is
    # laid over the rosters and can only make them smaller; this is the one
    # place that says how big the country is, whatever a file remembers.
    try:
        _pop2 = worldbuild.set_world_population(villages)
        plog.log("WORLD", "population after the load:", _pop2)
    except Exception as _pe:
        plog.log("WORLD-ERROR", repr(_pe)[:200])

    # THE MAN WHO ANSWERS QUESTIONS IS NOT A CASUALTY OF A SAVE LOAD.
    # `load_now` rebuilds every town's roll up to its capacity, and he is the
    # LAST man appended to his town -- so the cap dropped him, and he survived
    # only as a handle: clickable, but off the roster and therefore not drawn.
    # He is put back, with the room to hold him.
    if _truth is not None:
        _home_town = getattr(_truth, "village", None)
        if _home_town is not None:
            if _truth not in _home_town.npcs:
                _home_town.npcs.append(_truth)
            _home_town.capacity = max(int(getattr(_home_town, "capacity", 0)),
                                      len(_home_town.npcs))
        if _truth not in village_mod.PEOPLE:
            village_mod.PEOPLE.append(_truth)
        _TRUTH[0] = _truth

    # ---- THE SERVICE: ITS CHIEF, AND HIS MEN ------------------------------
    # Planted AFTER the save has been laid over the world and BEFORE the lanes
    # fork, so that every process holds the same marked men. The chief is
    # chosen here for the same reason: he must exist, with his mark, in the
    # process that draws him and in the one that walks him.
    #
    # MARKS ONLY, for now: nothing reads them and nothing changes because of
    # them. Three agents in every settlement, one in three hubs in ten, and one
    # chief in a labourer's clothes somewhere far off.
    # ---- NO LABS AND NO BREWHOUSES IN A SETTLEMENT -----------------------
    # The law has said so since the pivot: the trade moved to the huts in the
    # wild. But a SAVE remembers a man's trade, and men traded as `lab` and
    # `brewery` before the law (the register carried 14 labs and 12 brewers in
    # towns that no longer have a bench). A post whose station does not exist
    # is not a post: they are made idle, and the board will offer them honest
    # work. The huts keep their bench -- that is the whole point of a hut.
    _retraded = 0
    try:
        for _v in villages.villages:
            if getattr(_v, "is_hub", False):
                continue
            _v.workplaces = [wp for wp in getattr(_v, "workplaces", ())
                             if getattr(wp, "kind", None) not in ("lab", "brewery")]
            _v.lab = None
            _v.brewery = None
            for _n in getattr(_v, "npcs", ()):
                if getattr(_n, "job", None) in ("lab", "brewery"):
                    _n.job = None
                    _n.workplace = None
                    _retraded += 1
        if _retraded:
            plog.log("TRADES", "made idle in settlements:", _retraded,
                     "(no lab or brewhouse by law)")
    except Exception as _te:
        plog.log("TRADES-ERROR", repr(_te)[:200])

    try:
        _ta, _ha = nemesis.plant(villages, hub_world, world.seed)
        nemesis.seed_chief(villages, player, world.seed)
        nemesis.issue()          # secret news: who is told what, and nobody else
        nemesis.set_places(villages, hub_world)   # for naming where a crime was
        plog.log("SERVICE", nemesis.summary(villages, hub_world),
                 "| planted", _ta, "town /", _ha, "hub")
        plog.log("SERVICE", nemesis.secret_summary())
    except Exception as _se:
        plog.log("SERVICE-ERROR", repr(_se)[:200])

    # ---- WHAT THE LANES SAW ----------------------------------------------
    # A lane notices an offence and sends the offender's id, the verb, the
    # goods, where he stood and which of its agents were close enough to watch.
    # The facts live HERE, in one process, so there is one answer to "who
    # knows what" -- and no lane can invent a fact or forget one.
    _BY_ID: dict = {}
    try:
        for _v in villages.villages:
            for _n in _v.npcs:
                _BY_ID[str(getattr(_n, "id", ""))] = _n
        for _h in hub_world.hubs:
            for _n in _h.npcs:
                _BY_ID[str(getattr(_n, "id", ""))] = _n
        for _c in getattr(hub_world, "_caravans", ()):
            _BY_ID[str(getattr(_c.npc, "id", ""))] = _c.npc
    except Exception:
        pass

    def _on_offences(events) -> None:
        for _ev in events:
            try:
                _aid, _verb, _item, _x, _y, _wids = _ev
                _actor = _BY_ID.get(str(_aid))
                _ws = [_BY_ID.get(str(_i)) for _i in _wids]
                nemesis.note_offence(_actor, _verb, _item, _x, _y,
                                     [w for w in _ws if w is not None])
            except Exception:
                pass

    # (the sink is attached once the lanes exist -- see below)

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
    _IVIS = [None, None]        # the room's light mask, and what it was made for
    _HF = [0, time.perf_counter()]      # indoor frame counter, for the log
    prison_cd = 0.0                     # the barn's doorway, just after leaving
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
    _town_acc = {}            # accumulated time per town, for its books
    _LANE_TOWNS = list(villages.villages)
    _LANE_PEOPLE = list(village_mod.PEOPLE)
    _lane_timer = 0.0
    _lane_warned = False
    # THE GATE SEARCH, bound before the loop: the frame reads these.
    gate_search_t = 0.0
    gate_search_v = None
    _hb = 0.0
    _blk = 0.0
    _stuck = 0.0
    # ---- THE PLAYER TRACE -------------------------------------------------
    # The last ninety frames, every number that could stop him moving. It is
    # held in memory and written ONLY when something is wrong, so it costs
    # nothing and cannot itself be the reason for a hitch.
    from collections import deque as _deque
    _trace = _deque(maxlen=90)
    _still = 0
    _lastpt = [None]
    _branch = "?"

    def _inside_h():
        try:
            return inside_house is not None
        except Exception:
            return "?"

    def _dump_trace(why):
        try:
            plog.log("==== TRACE:", why, "====")
            for row in _trace:
                plog.log("  T:", " ".join(str(c) for c in row))
        except Exception:
            pass

    def close_modals(why="") -> None:
        """SHUT EVERY PANEL. THE WORLD IS NEVER HELD HOSTAGE BY A MENU.

        Each of these flags skips the whole world update while it is set, so a
        menu that fails to close -- or a click that opens one the player never
        notices -- freezes him solid while the HUD keeps drawing. There must
        always be a way out, and this is it.
        """
        nonlocal inventory_open, trade_open, board_open, chest_open
        nonlocal worker_panel_open, stall_open, body_open, folder_open
        nonlocal smith_open, workshop_open, confirm_open, map_open
        nonlocal pause_open, build_menu_open, placing
        inventory_open = trade_open = board_open = chest_open = False
        worker_panel_open = False
        stall_open = False
        body_open = False
        folder_open = False
        smith_open = workshop_open = confirm_open = map_open = False
        pause_open = build_menu_open = False
        placing = None
        try:
            pygame.mouse.set_visible(False)
        except Exception:
            pass
        if why:
            toast(why)

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
    # EVERY GATE IS GUARDED FROM THE FIRST DAY, not only the ones the player
    # happens to walk past. The guards used to be raised for towns in the
    # player's lane -- so a caravan arriving anywhere else in the world found an
    # EMPTY gate, was waved through by `search_visitor`, and sold its load
    # without ever being looked at. Measured in a live day: 132 purchases, 13
    # loads, 2 sales, and ZERO searches. A wall with nobody on the gate is not a
    # border.
    try:
        for _v in villages.villages:
            if getattr(_v, "is_hub", False) or getattr(_v, "patrol", None):
                continue
            _v.patrol = make_village_patrol(_v, 4)
            enemies.extend(_v.patrol)
            _v.patrol_timer = 30.0
        print("gate guards raised for %d settlements" % len(villages.villages))
    except Exception as _ge:
        print("gate guard pass failed: %r" % (_ge,))

    # ---- THE LANES: THE FRAME, THE HUBS, THE SETTLEMENTS -----------------
    # Two forked processes (see workers.py): process 1 owns the hubs, their
    # people and the free traders; process 2 owns the settlements, their books
    # and their people. THIS process keeps the player, the soldiers, the
    # bullets, the terrain and every pixel. Falls back to stepping everything
    # here if the fork cannot be made.
    _WORK = workers.start(world, villages, hub_world, player)
    _W_ON = _WORK.ok()
    # WHAT THE LANES SAW, and how often agents pass it on.
    _posted: dict = {}
    _walk_log: dict = {}
    _WORK.offence_sink = _on_offences
    _WORK.stall_sink = _on_stall_sales

    # A SEARCH THAT FOUND SOMETHING: the agents of THAT settlement know.
    _SETTLE_TOWNS = [v for v in villages.villages
                     if not getattr(v, "is_hub", False)]

    def _on_caught(events) -> None:
        for _ev in events:
            try:
                _aid, _ti, _units = _ev
                _actor = _BY_ID.get(str(_aid))
                _ti = int(_ti)
                _town = _SETTLE_TOWNS[_ti] if 0 <= _ti < len(_SETTLE_TOWNS) else None
                nemesis.note_caught(_actor, _town, int(_units))
            except Exception:
                pass

    _WORK.caught_sink = _on_caught
    _tell_timer = 0.0

    class _BoardAPI:
        """THE NOTICE BOARD, ACROSS THE FENCE.

        The board is drawn in the frame; the town that answers it is simulated
        in another process. So a hire and a sale are REQUESTS: the town does
        them, the frame is told what happened and moves the player's own pack
        and purse. Nothing is faked and nothing goes stale -- the posts it
        offers and the prices it pays arrive with the tick (see _WORK.watch).
        """

        def hire(self, town, kind, cb) -> None:
            def done(res):
                if res and res.get("hired"):
                    player.job = res.get("job") or player.job
                    player.wage = int(res.get("wage") or 0)
                    player.farm_plot = res.get("farm_plot")
                    if res.get("nation") is not None:
                        player.nation = res["nation"]
                    player.settled_at = town
                    player.village = town
                    player._pay_day = -1
                cb(res)

            _WORK.hire(town, kind, done)

        def sell(self, town, offers, cb) -> None:
            def done(res):
                if res and res.get("sold"):
                    for item, n in (res.get("taken") or {}).items():
                        inventory.consume(item, int(n))
                        nemesis.note_offence_seen(player, "sold", item)
                    if res.get("coin"):
                        inventory.add("coin", int(res["coin"]))
                cb(res)

            _WORK.sell(town, offers, done)

    _BOARD_API = _BoardAPI()

    # ---- THE HANG WATCHDOG ------------------------------------------------
    # A freeze leaves no traceback: the process is alive and nothing is
    # written. This thread watches a heartbeat the frame sets, and when the
    # frame has not moved for six seconds it dumps EVERY thread's stack into
    # saves/hang.log -- so a freeze names its own line instead of costing an
    # evening of guessing.
    _HEART = [time.time()]

    def _watchdog() -> None:
        import faulthandler
        while True:
            time.sleep(2.0)
            if time.time() - _HEART[0] < 6.0:
                continue
            try:
                path_ = os.path.join(persist.DIR, "hang.log")
                os.makedirs(persist.DIR, exist_ok=True)
                with open(path_, "a") as fh:
                    fh.write("\n==== HANG  %.0f  (no frame for %.1fs) ====\n"
                             % (time.time(), time.time() - _HEART[0]))
                    faulthandler.dump_traceback(file=fh)
            except Exception:
                pass
            _HEART[0] = time.time()

    try:
        threading.Thread(target=_watchdog, daemon=True).start()
    except Exception:
        pass

    while running:
        _HEART[0] = time.time()
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
        _framet0 = time.perf_counter()
        _pt1 = _pt2 = _pt3 = _framet0      # phase marks, if no phase runs
        # THE HIDDEN DART BAR DOES NOT REFILL. A dart is a dose; the bar is
        # how much of the dose is still in him. Refilling it between shots was
        # why ten darts never put the player down -- each 80-dart had its bite
        # healed back almost as fast as it landed.
        # THE MAN IS AT A PAIR OF NUMBERS, always. A tuple that reached
        # player.x/y used to take the whole frame down at the first `- vh/2`.
        try:
            if not isinstance(player.x, (int, float)):
                _bad = (player.x, player.y)
                player.x = float(_bad[0][0] if isinstance(_bad[0], (tuple, list))
                                 else _bad[0])
                player.y = float(_bad[1][0] if isinstance(_bad[1], (tuple, list))
                                 else _bad[1]) if isinstance(_bad[1], (int, float))                     else float(_bad[1][1] if isinstance(_bad[1], (tuple, list)) else 0.0)
                plog.log("POS-FIX", "player position was", repr(_bad),
                         "->", int(player.x), int(player.y))
            elif not isinstance(player.y, (int, float)):
                player.y = float(player.y[0] if isinstance(player.y, (tuple, list))
                                 else 0.0)
                plog.log("POS-FIX", "player y was a container ->", int(player.y))
        except Exception as _px:
            plog.log("POS-FIX-FAIL", repr(_px)[:120])
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        _PH["f"] += 1
        dt = min(dt * time_scale, 0.5)          # test-mode speed-up
        vw, vh = screen.get_size()
        mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
        wmouse_x, wmouse_y = mouse_x / ZOOM, mouse_y / ZOOM  # world space

        # THE LANES HAVE FINISHED A TICK: take their state before anything
        # reads a man or draws one. Never blocks -- a lane that is late is one
        # tick of latency, not a stall.
        dialogue.set_now(now)
        try:
            import trade as _trade_mod
            _trade_mod.set_now(now)
        except Exception:
            pass
        _WORK.apply(world, combat)
        if (_PH["f"] & 15) == 0:
            _W_ON = _WORK.ok()
            if _WORK.enabled and not _W_ON:
                _WORK.stop()          # one lane died: step both here again
                _WORK.enabled = False

        _had_event = False
        for event in pygame.event.get():
            _had_event = True
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
            elif inside_mine is not None and getattr(inside_mine, "kind", "") != "house":
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
            elif stall_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    stall_open = False
                    mark_dirty()
                    save_now()
                    pygame.mouse.set_visible(False)
                else:
                    stall_panel.handle_event(event)
            elif folder_open:
                if folder_panel.handle_event(event):
                    folder_open = False
                    pygame.mouse.set_visible(False)
            elif body_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    body_panel.close()
                    body_open = False
                    mark_dirty()
                    pygame.mouse.set_visible(False)
                else:
                    body_panel.handle_event(event)
            elif worker_panel_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    worker_panel.close()
                    worker_panel_open = False
                    pygame.mouse.set_visible(False)
                else:
                    worker_panel.handle_event(event)
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
                    plot_start[0] = None
                    pygame.mouse.set_visible(False)
                elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                      and placing == "plot"):
                    plot_start[0] = placement_pos()      # one corner
                elif (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                      and placing == "plot"):
                    _commit_plot()                        # ...and the other
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    try_place()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_e:
                plog.log("E-KEY", "board", near_board() is not None,
                         "stall", near_stall() is not None,
                         "chest", near_chest() is not None,
                         "work", getattr(near_workplace(), "kind", None),
                         "house", inside_house is not None,
                         "at", int(player.x), int(player.y))
                if (near_workplace() is not None
                      and getattr(near_workplace(), "kind", None) in ("mine", "prison")):
                    plog.log("ENTER-TRY", getattr(near_workplace(), "kind", "?"),
                             "door", getattr(near_workplace(), "door", None),
                             "player", int(player.x), int(player.y))
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
                _bv = near_board()
                if _bv is not None:
                    board_village = _bv
                    board_open = True
                    board_panel.scroll = 0
                    pygame.mouse.set_visible(True)
                elif near_stall() is not None:
                    # THE COUNTER IS A CHEST, AND WHATEVER IS IN IT IS FOR SALE.
                    stall_open = True
                    stall_panel = MarketPanel(inventory, near_stall())
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
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE
                  and not (inventory_open or trade_open or board_open
                           or chest_open or stall_open or worker_panel_open
                           or workshop_open or smith_open or confirm_open
                           or map_open or pause_open or build_menu_open
                           or dialogue_panel.open_ or placing is not None)):
                # SPACE: LUNGE. A quarter of the wind, in the way he is holding
                # -- a step he cannot take twice in a breath.
                if player.lunge(pygame.key.get_pressed()):
                    try:
                        _lx, _ly = player.lunge_dir
                        combat.spawn_impact(player.x - _lx * 18.0,
                                            player.y - _ly * 18.0,
                                            (206, 196, 168))
                    except Exception:
                        pass
                else:
                    toast("No wind for a lunge" if player.lunge_cd <= 0.0
                          else "Not yet")
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_m
                  and not inventory_open and not trade_open and not board_open):
                # FOR EVERYBODY. The chart was test-mode only, which meant the
                # one thing a man on a road needs -- where am I and where is the
                # nearest town -- was a debug tool.
                map_open = not map_open
                pygame.mouse.set_visible(map_open)
            elif (dialogue_panel.open_
                  and ((event.type == pygame.KEYDOWN
                        and event.key in (pygame.K_1, pygame.K_2, pygame.K_3,
                                          pygame.K_4, pygame.K_5, pygame.K_6,
                                          pygame.K_7, pygame.K_8, pygame.K_9,
                                          pygame.K_KP1, pygame.K_KP2,
                                          pygame.K_KP3, pygame.K_KP4,
                                          pygame.K_KP5, pygame.K_KP6,
                                          pygame.K_KP7, pygame.K_KP8,
                                          pygame.K_KP9,
                                          pygame.K_ESCAPE, pygame.K_q))
                       or (event.type == pygame.MOUSEBUTTONDOWN
                           and event.button == 1
                           and dialogue_panel.hit(event.pos)))):
                # ONLY ITS OWN FOUR KEYS. This branch used to take EVERY event
                # while the panel was open -- so one click opened it and from
                # then on the mouse, the wheel and the pack were dead: no NPC
                # could be clicked and the inventory could not be scrolled.
                # A conversation must never own the input system.
                _d = dialogue_panel.handle_event(event)
                if _d == "close":
                    pygame.mouse.set_visible(False)
                elif _d == "pack":
                    _wn = dialogue_panel.npc
                    if _wn is not None and getattr(_wn, "pack", None) is not None:
                        worker_panel = ChestPanel(
                            inventory, work.bag(_wn),
                            top_rows=4, top_label=getattr(_wn, "name", "PACK"))
                        worker_panel_open = True
                        pygame.mouse.set_visible(True)
                elif _d == "trade":
                    _dn = dialogue_panel.npc
                    dialogue_panel.close()
                    pygame.mouse.set_visible(False)
                    if _dn is not None:
                        open_trade_menu(_dn)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                # ESC USED TO PAUSE UNCONDITIONALLY, even with a menu already
                # open -- so a panel that would not close left a man with no
                # way out at all. ESC now closes what is open, and only opens
                # the pause menu when nothing is.
                if (inventory_open or trade_open or board_open or chest_open
                        or worker_panel_open or stall_open or body_open
                        or folder_open
                        or smith_open or workshop_open or confirm_open
                        or map_open or build_menu_open or placing is not None):
                    close_modals()
                elif pause_open:
                    pause_open = False
                    pygame.mouse.set_visible(False)
                else:
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
                if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                        and dialogue_panel.open_
                        and not dialogue_panel.hit(event.pos)):
                    dialogue_panel.close()          # click AWAY: put it away
                    pygame.mouse.set_visible(False)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    _held = inventory.selected_stack()
                    _held_id = _held.defn.id if _held else None
                    if _held_id == "secret_folder":
                        # A DEAD AGENT'S MAIL, OPENED BY A CLICK IN THE HAND.
                        _pay = getattr(_held, "payload", None)
                        if _pay:
                            folder_panel = FolderPanel(_pay)
                            folder_open = True
                            pygame.mouse.set_visible(True)
                            plog.log("FOLDER-OPEN", _pay)
                            break
                    # A BODY IS LOOTED, NOT SWUNG AT. Whatever is in his hand
                    # -- axe included -- a click on a corpse opens the corpse.
                    _bw = (cam_x + event.pos[0] / ZOOM,
                           cam_y + event.pos[1] / ZOOM)
                    _body = corpse_mod.nearest(_bw[0], _bw[1])
                    if _body is not None:
                        body_panel = ChestPanel(
                            inventory, _body.pack,
                            top_label=getattr(_body, "name", "a body"))
                        body_open = True
                        pygame.mouse.set_visible(True)
                        plog.log("BODY-OPEN", getattr(_body, "name", "?"))
                        break
                    # A WEAPON IS AN ATTACK, NOT A CONVERSATION.
                    if _held_id not in ("axe", "pickaxe", "rifle", "shotgun"):
                        if click_a_man(event.pos):
                            break
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
        # WHY IS HE NOT MOVING? Every frame that any of these is set skips the
        # world update entirely -- and `board_open` zeroes the keys outright --
        # so a man can be frozen solid with the HUD happily drawing on top. If
        # the log has a BLOCKED line, the line names what did it.
        if (inventory_open or trade_open or build_menu_open or chest_open
                or workshop_open or confirm_open or pause_open or map_open
                or placing is not None or inside_house is not None
                or inside_mine is not None or board_open or smith_open):
            _blk += dt
            # A MENU LEFT ALONE FOR TWENTY SECONDS RELEASES THE WORLD. Not a
            # fix for any particular panel -- a guarantee that no panel, known
            # or not yet written, can hold the game still for good.
            _stuck = 0.0 if _had_event else _stuck + dt
            if _stuck >= 20.0:
                _stuck = 0.0
                close_modals("Closed: that menu had stopped responding")
            if _blk >= 1.0:
                _blk = 0.0
                plog.log("BLOCKED", "inv", inventory_open, "trade", trade_open,
                         "board", board_open, "chest", chest_open,
                         "smith", smith_open, "work", workshop_open,
                         "confirm", confirm_open, "pause", pause_open,
                         "map", map_open, "placing", placing is not None,
                         "house", inside_house is not None,
                         "mine", inside_mine is not None,
                         "dead", player.dead, "hp", int(player.health),
                         "at", "%d,%d" % (int(player.x), int(player.y)))
        else:
            _blk = 0.0

        if (inside_house is not None and inside_mine is None
                and not game_over and not pause_open
                and not map_open and not confirm_open
                and not build_menu_open and placing is None):
            _branch = 'house'
            _HF[0] += 1
            _now_hf = time.perf_counter()
            if _now_hf - _HF[1] >= 2.0:
                plog.log("HOUSE-FPS", "%.1f fps indoors"
                         % (_HF[0] / max(1e-6, _now_hf - _HF[1])))
                _HF[0], _HF[1] = 0, _now_hf
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
                # A ROOM IS NOT THE WORLD. Standing in a house used to re-cut
                # the visible villages, re-collect every collider and step the
                # whole neighbourhood every frame -- exactly what a mine does
                # not do, which is why a mine never stutters and a doorway did.
                # The world is stepped in its own lanes; from indoors it is
                # only the clock that has to keep running.
                night = night_factor() > 0.38
                sim_villages = []
                sim_colliders = []
                world_accum += dt
                world_tick = world_accum >= WORLD_STEP
                if world_tick:
                    world_dt = world_accum
                    world_accum = 0.0
                    if _W_ON:
                        _WORK.tick(now, world_dt, day_phase(), night, player,
                                   enemies)
                for village in sim_villages:
                    if not world_tick or _W_ON:
                        break
                    # THE BUBBLE, NOT THE VIEW. `visible()` is a DRAWING cull --
                # a fence is big, so it returns every town whose wall is
                # anywhere near the frame. Stepping each of those costs a dozen
                # economy passes, and several towns at once is what made the
                # frame die at a gate. A town's books run when the man is near
                # the town.
                if (abs(village.x - player.x) < village.radius + 3000.0
                        and abs(village.y - player.y) < village.radius + 3000.0):
                    # THE SEARCH, EVERY FRAME: one guard, the men near him,
                    # and nothing else in the world.
                    try:
                        import gate as gate_mod
                        _r2 = gate_mod.tick_town(world_dt, village)
                        if _r2 is not None and _r2[0] == "caught":
                            village.provoke()
                        elif _r2 is not None:
                            pass
                    except Exception:
                        pass
                    # THE TOWN'S BOOKS, TEN TIMES A SECOND. They are all
                    # day-guarded anyway; asking sixty times a second whether
                    # the day has changed was most of the town phase's cost.
                    _bk = _town_acc.get(id(village), 0.0) + world_dt
                    if _bk >= 0.1:
                        _town_acc[id(village)] = 0.0
                        village.update(_bk, world, now, day_phase())
                    else:
                        _town_acc[id(village)] = _bk
                for enemy in enemies:
                    if enemy.alive:
                        enemy.update(dt, house, combat, [], 1.0, 1.0, False)
                        enemy.x, enemy.y = resolve_circle_rects(
                            enemy.x, enemy.y, enemy.radius, sim_colliders)
                combat.update(dt)
                blood.update(dt)
                # the ground worker still keeps the house's own chunks ready
                ground.update(4, house.x - vw / 2.0, house.y - vh / 2.0, vw, vh)
        elif (inside_house is None and inside_mine is None
              and not game_over and not inventory_open and not build_menu_open
              and not chest_open and not trade_open and not workshop_open
              and not confirm_open and not pause_open and not map_open
              and placing is None):
            _branch = 'world'
            if abs(player.x) < 3000.0 and abs(player.y) < 3000.0:
                # He is standing on room coordinates in the open world.
                _wx, _wy = getattr(player, "world_xy", (0.0, 0.0))
                if _wx or _wy:
                    player.x, player.y = _wx, _wy
                    plog.log("WORLD-POS-FIX", "room coordinates in the world;"
                             " put back at", int(_wx), int(_wy))
            now += dt
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
            # THE HEARTBEAT. Written from INSIDE the overworld update, every two
            # seconds of game time, so that "the world froze" has evidence: if
            # these lines stop while the game is still drawing the HUD, the
            # overworld branch is not being reached -- and the last line before
            # they stop says where the loop was.
            _hb += dt
            if _hb >= 2.0:
                _hb = 0.0
                plog.log("HEARTBEAT", "x", int(player.x), "y", int(player.y),
                         "dt", round(dt, 3), "board", board_open,
                         "dead", player.dead,
                         "hp", int(player.health))
            if getattr(player, "aboard", False):
                _tr = _TEST_TRAIN[0]
                if _tr is not None:
                    if not _EXPRESS[0]:
                        # AN EXPRESS, NOT A TOUR: somebody is aboard and the
                        # camp is where he is going.
                        try:
                            import gulag as _gl_x
                            import train as _tmx
                            import rail as _railx
                            _glx, _gly = _gl_x.gate_point()
                            _len = _tr.to_camp((_glx, _gly))
                            _EXPRESS[0] = True
                            plog.log("EXPRESS", "the engine runs for the camp |",
                                     int(_len), "px of track |",
                                     round(_len / _tmx.TRAIN_SPEED / 60.0, 1),
                                     "minutes")
                        except Exception as _xe:
                            plog.log("EXPRESS-ERR", repr(_xe)[:140])
                    player.x, player.y = _tr.x, _tr.y
                    cam_x = player.x - vw / 2.0
                    cam_y = player.y - vh / 2.0
                    try:
                        import gulag as _gl_end
                        if ((_tr.x - _gl_end.gate_point()[0]) ** 2
                                + (_tr.y - _gl_end.gate_point()[1]) ** 2) < 600.0 ** 2:
                            # THE END OF THE LINE IS THE CAMP
                            _detain_release = True
                            try:
                                import detain as _dr
                                _dr.release_kit(player, None)
                                # the tour resumes; the express is over
                                try:
                                    import rail as _railr
                                    _tr.set_route(_railr.tour())
                                    _EXPRESS[0] = False
                                except Exception:
                                    pass
                                plog.log("DROP-OFF", "the player is put down at the camp",
                                         "with the other", len(getattr(_tr, "aboard", []) or []),
                                         "prisoners")
                            except Exception:
                                pass
                    except Exception:
                        pass
            if getattr(player, "sleep_t", 0.0) > 0.0:
                player.sleep_t = max(0.0, player.sleep_t - dt)
                keys = _NO_KEYS
            player.update(dt, keys, aim, 1.0 - 0.25 * foliage)
            if getattr(player, "aboard", False):
                _tr = _TEST_TRAIN[0]
                if _tr is not None:
                    if not _EXPRESS[0]:
                        # AN EXPRESS, NOT A TOUR: somebody is aboard and the
                        # camp is where he is going.
                        try:
                            import gulag as _gl_x
                            import train as _tmx
                            import rail as _railx
                            _glx, _gly = _gl_x.gate_point()
                            _len = _tr.to_camp((_glx, _gly))
                            _EXPRESS[0] = True
                            plog.log("EXPRESS", "the engine runs for the camp |",
                                     int(_len), "px of track |",
                                     round(_len / _tmx.TRAIN_SPEED / 60.0, 1),
                                     "minutes")
                        except Exception as _xe:
                            plog.log("EXPRESS-ERR", repr(_xe)[:140])
                    player.x, player.y = _tr.x, _tr.y
                    cam_x = player.x - vw / 2.0
                    cam_y = player.y - vh / 2.0
                    try:
                        import gulag as _gl_end
                        if ((_tr.x - _gl_end.gate_point()[0]) ** 2
                                + (_tr.y - _gl_end.gate_point()[1]) ** 2) < 600.0 ** 2:
                            # THE END OF THE LINE IS THE CAMP
                            _detain_release = True
                            try:
                                import detain as _dr
                                _dr.release_kit(player, None)
                                # the tour resumes; the express is over
                                try:
                                    import rail as _railr
                                    _tr.set_route(_railr.tour())
                                    _EXPRESS[0] = False
                                except Exception:
                                    pass
                                plog.log("DROP-OFF", "the player is put down at the camp",
                                         "with the other", len(getattr(_tr, "aboard", []) or []),
                                         "prisoners")
                            except Exception:
                                pass
                    except Exception:
                        pass
            if getattr(player, "sleep_t", 0.0) > 0.0:
                try:
                    _z = font.render("Zzz", True, (232, 232, 240))
                    screen.blit(_z, (vw // 2 + 14, vh // 2 - 44))
                except Exception:
                    pass
            if _chain is not None:
                try:
                    if _chain["hub"] is None:
                        _chain["hub"] = hub_world.hubs[0]
                        _chain["t0"] = now
                        _csay("CHAIN watching hub %s" % _chain["hub"].name)
                    _hubx = _chain["hub"]      # NOT `_hb`: that is the
                    # heartbeat timer, and overwriting it with a Hub object
                    # raised a TypeError on the very next frame -- which is why
                    # this report printed its first line and then nothing.
                    _live = [n for n in _hubx.npcs if n.alive]
                    _farm = next((n for n in _live if n.job == "farm"), None)
                    _art = next((n for n in _live if n.job in ("lab", "brewery")), None)
                    _trd = next((n for n in _live if n.job == "trader"), None)
                    _LEAF = ("tobacco", "red_mushroom", "agave", "plant", "mushroom")
                    _MADE = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")
                    _food = sum(int((_farm.stock if _farm else {}).get(x, 0))
                                for x in economy.FOOD) if _farm else 0
                    _shelf = sum(int(_hubx.ledger_goods.get(x, 0)) for x in economy.FOOD)
                    _leaf = (sum(int((_art.stock if _art else {}).get(k, 0)) for k in _LEAF)
                             if _art else 0)
                    _made = (sum(int((_art.stock if _art else {}).get(k, 0)) for k in _MADE)
                             if _art else 0)
                    _carry = (sum(int((_trd.stock if _trd else {}).get(k, 0)) for k in _MADE)
                              if _trd else 0)
                    _st = _chain["seen"]
                    _st["food"] = max(_st.get("food", 0), _food + _shelf)
                    _st["leaf"] = max(_st.get("leaf", 0), _leaf)
                    _st["made"] = max(_st.get("made", 0), _made)
                    _st["carry"] = max(_st.get("carry", 0), _carry)
                    _st["trip"] = _st.get("trip", 0) or bool(_hubx._carrier)
                    _st["stage"] = _hubx._stage
                    _st["ledger"] = int(_hubx.ledger_coins)
                    _chain["f"] += 1
                    _chain["t"] = time.perf_counter() - _chain["wall0"]
                    # A STATUS LINE EVERY MINUTE: the actual contents, item by
                    # item. Without this the test could only say "the leaf did
                    # not arrive" -- never where it went.
                    if _chain["t"] - _chain.get("last_say", -1.0) >= 15.0:
                        _chain["last_say"] = _chain["t"]
                        _csay("CHAIN %4.0fs  farmer.food=%d shelf.food=%d  "
                              "farmer.leaf=%s  shelf=%s  artisan=%s  trader=%d"
                              % (_chain["t"], _food, _shelf,
                                 {k: int(_farm.stock.get(k, 0)) for k in _LEAF
                                  if int(_farm.stock.get(k, 0)) > 0} if _farm else {},
                                 {k: int(v) for k, v in _hubx.ledger_goods.items() if v},
                                 {k: int(_art.stock.get(k, 0)) for k in
                                  (_LEAF + _MADE) if int(_art.stock.get(k, 0)) > 0}
                                 if _art else {},
                                 _carry))
                    _deadline = {1: 300.0, 2: 600.0, 3: 900.0, 4: 1200.0,
                                 5: 1500.0, 6: 2400.0, 7: 2700.0, 8: 3300.0,
                                 9: 3900.0}
                    _need = {1: ("food", 1), 2: ("leaf", 1), 3: ("made", 1),
                             4: ("carry", 20), 5: ("trip", True)}
                    _say = {1: "the farmer harvests any food at all",
                            2: "the farmer hands leaf to the artisan",
                            3: "the artisan makes a finished product",
                            4: "the artisan gives 20 finished goods to the trader",
                            5: "the trader leaves on a trip with 20",
                            6: "the trader reaches a town gate",
                            7: "the guard searches him at the gate",
                            8: "he sells to the town",
                            9: "he comes home and the hut's purse grows"}
                    while _chain["link"] <= 9:
                        _k = _chain["link"]
                        _ok = False
                        if _k in _need:
                            _key, _val = _need[_k]
                            _ok = (_st.get(_key, 0) >= _val) if _val is not True else bool(_st.get(_key))
                        elif _k == 6:
                            _ok = _st.get("stage") in ("home",) and bool(_st.get("trip"))
                        elif _k == 7:
                            _ok = _st.get("ledger", 0) > 0 or _st.get("stage") == "home"
                        elif _k in (8, 9):
                            _ok = _st.get("stage") == "idle" and _st.get("trip")
                        if _ok:
                            plog.log("CHAIN OK", _k, _say[_k])
                            _csay("CHAIN OK  %d: %s" % (_k, _say[_k]))
                            _chain["link"] = _k + 1
                            continue
                        if _chain["t"] > _deadline[_k]:
                            _csay("CHAIN FAILED AT LINK %d: %s" % (_k, _say[_k]))
                            _csay("   state: food=%s leaf=%s made=%s carry=%s "
                                  "trip=%s stage=%s ledger=%s"
                                  % (_st.get("food"), _st.get("leaf"),
                                     _st.get("made"), _st.get("carry"),
                                     _st.get("trip"), _st.get("stage"),
                                     _st.get("ledger")))
                            plog.log("CHAIN FAILED", _k, _say[_k], _st)
                            pygame.quit()
                            raise SystemExit(9)
                        break
                    if _chain["link"] > 9:
                        _csay("CHAIN COMPLETE: every link fired")
                        plog.log("CHAIN COMPLETE")
                        pygame.quit()
                        raise SystemExit(0)
                except SystemExit:
                    raise
                except Exception as _ce:
                    _csay("CHAIN MONITOR ERROR:", repr(_ce)[:160])
            if _observe_spot is not None:
                player.god = True
                player.hunger = 100.0
                player.x, player.y = _observe_spot      # fixed: nothing moves him
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
                # A HUB IS NOT A TOWN AND GETS NO GARRISON. `visible()` now
                # hands back the off-lattice hubs too, so this loop was putting
                # five wall guards AND a two-man gate patrol on every hut --
                # more soldiers in a criminal camp than in a market town. A hub
                # has exactly one armed man: the soldier's post at his gate.
                if (not getattr(village, "is_hub", False)
                        and getattr(village, "guards", None) is None
                        and math.hypot(village.x - player.x,
                                       village.y - player.y) < 6000.0):
                    loop = village.fence_rect.inflate(-218, -218)
                    guards = []
                    # Guards are posted along the wall, so a capital twice the
                    # size keeps twice as many -- same rule, read off the
                    # village's own scale.
                    # NOBODY WALKS THE PERIMETER. Two men, at the two gates,
                    # standing still -- one searching the way in, one watching
                    # the way out. The ring of five was a patrol nobody asked
                    # for; the gate is the only way through a wall.
                    many = 0
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
                # HIS YARD IS NOT A GARRISON. No patrol, no roster, no duty:
                # the whole block below is the town's standing watch, and a
                # hub he built has no watch. (This is what crashed the game on
                # the first plot: `patrol_timer` on a PlayerHub.)
                squad = getattr(village, "patrol", None)
                if getattr(village, "is_player_hub", False):
                    continue
                if squad is None:
                    if math.hypot(village.x - player.x,
                                  village.y - player.y) < 30000.0:
                        village.patrol = make_village_patrol(
                            village, 2 if getattr(village, "is_hub", False) else 4)
                        village.patrol_timer = 30.0
                        enemies.extend(village.patrol)
                elif not any(s.alive for s in squad):
                    village.patrol_timer -= dt
                    if village.patrol_timer <= 0.0:      # squad wiped: respawn
                        village.patrol = make_village_patrol(
                            village, 2 if getattr(village, "is_hub", False) else 4)
                        village.patrol_timer = 30.0
                        enemies.extend(village.patrol)
                village._assign_duty_bodies()
            house_colliders = [house.rect for village in visible_villages
                               for house in village.houses]
            house_colliders += [house.rect for house in built_houses]
            house_colliders += [w for village in visible_villages
                                for w in village.fence_walls]
            house_colliders += built_fences
            house_colliders += camp_walls
            house_colliders += [v.board for v in visible_villages]
            house_colliders += [wp.rect for v in visible_villages
                                for wp in v.workplaces]
            house_colliders += [wp.rect for wp in placed_work]
            house_colliders += [c.rect for c in view_ore]
            colliders = house_colliders + [tree.trunk_rect for tree in view_trees
                                           if not tree.felled]
            # THE CARTS, EVERY FRAME AND AT THE FRAME'S OWN PACE. A cart is a
            # vehicle: at 240 px/s it moves four pixels a frame, which is
            # smooth; on the 20 Hz world tick it would move twelve at a time --
            # the "jumping" the throttled build was reverted for. What made it
            # expensive was never the clock, it was the empty-shelf scan (see
            # caravans.Caravan), and that is gated by a retry clock now.
            #
            # AND `dt`, NOT `world_dt`. `world_dt` is only ever assigned on the
            # world tick, so every frame was handed the same 0.05 s step: the
            # carts walked at 720 px/s instead of SPEED = 240. See Hubs.update
            # for the hubs themselves, which now keep the world's clock.
            if not _W_ON:
                try:
                    hub_world.drive_carts(dt, now)
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
                for wp in placed_work:
                    grid.add(wp.rect)
                for house in built_houses:
                    grid.add(house.rect)
                for rect in built_fences:
                    grid.add(rect)
                # THE CAMP WALL, IN THE GRID THE PLAYER IS PUSHED OUT OF.
                # It was in the collider *list* and not in this grid, and the
                # player's movement is resolved against the grid -- so the wall
                # was drawn, stood in the list, and could be walked straight
                # through like paint on the floor.
                for rect in camp_walls:
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
            solids += [(rect, (140, 104, 60)) for rect in camp_walls]
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
            solids += [(wp.rect, (96, 92, 88)) for wp in placed_work]
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
            _folk_list = [n for v in visible_villages
                          + [x for x in sieges if x not in visible_villages]
                          for n in v.npcs
                          if n.alive and not n.in_interior]
            if _TRUTH[0] is not None and _TRUTH[0] not in _folk_list:
                _folk_list.append(_TRUTH[0])    # shootable, healable, seen
            folk_grid.build(_folk_list)
            # THE WORLD KNOWS YOUR FACE -- AND LEARNS IT ONCE.
            #
            # This pass used to walk every man within 760 px, EVERY FRAME, set
            # `aggro = True` on each of them again, and write a log line for
            # each: 88,283 lines in one session (89,394 in the whole file), 350
            # file writes a second, and a man who could never calm down while
            # the player was in sight. The learning lives in the lane now
            # (`threat_of`): a man who knows the face adds him to his own list
            # of feuds ONCE, and the list is what he fights.
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
                # THE HUBS, ON THE WORLD TICK -- the same clock, and the same
                # step, as every man in every town (see the _LANE_PEOPLE loop
                # below). `hub_world.update` used to be called EVERY FRAME
                # with `world_dt`, a value only this branch ever assigns: so
                # twenty-five hubs, three men each and a whole ledger ran on
                # every rendered frame with a 0.05 s step -- 2 to 3 times their
                # own speed, and the largest single block left in the frame
                # (12.3 ms/f profiled). A settlement's day does not depend on
                # being watched; it depends on the world's clock.
                if _W_ON:
                    # THE TWO LANES TAKE THE TICK: the hubs to process 1, the
                    # settlements to process 2 (workers.tick hands it over).
                    _WORK.tick(now, world_dt, day_phase(), night, player,
                               enemies)
                else:
                    try:
                        hub_world.update(world_dt, now, day_phase(), combat,
                                         nearest_hostile)
                    except Exception:
                        pass
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
                _arr, _die = ((0, 0) if _W_ON else
                              village_mod.refugees_on_the_road(now, enemies))

                # THE TEST OF STRENGTHS. The King and the mayors fight for the
                # crown in the capital, unarmed, in front of the town. One at a
                # time, on the day, and the winner wears it.
                hear_news()                     # the news arrives where you are
                tick_news(dt)

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
            # the daily census and the births ran only in the three
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
                if not world_tick or _W_ON:
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
                # THE BUBBLE, NOT THE VIEW. `visible()` is a DRAWING cull --
                # a fence is big, so it returns every town whose wall is
                # anywhere near the frame. Stepping each of those costs a dozen
                # economy passes, and several towns at once is what made the
                # frame die at a gate. A town's books run when the man is near
                # the town.
                if (abs(village.x - player.x) < village.radius + 3000.0
                        and abs(village.y - player.y) < village.radius + 3000.0):
                    # THE SEARCH, EVERY FRAME: one guard, the men near him,
                    # and nothing else in the world.
                    try:
                        import gate as gate_mod
                        _r2 = gate_mod.tick_town(world_dt, village)
                        if _r2 is not None and _r2[0] == "caught":
                            village.provoke()
                        elif _r2 is not None:
                            pass
                    except Exception:
                        pass
                    # THE TOWN'S BOOKS, TEN TIMES A SECOND. They are all
                    # day-guarded anyway; asking sixty times a second whether
                    # the day has changed was most of the town phase's cost.
                    _bk = _town_acc.get(id(village), 0.0) + world_dt
                    if _bk >= 0.1:
                        _town_acc[id(village)] = 0.0
                        village.update(_bk, world, now, day_phase())
                    else:
                        _town_acc[id(village)] = _bk
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
                            # A PLOT IS DRAWN BY THE CROP RENDERER, NOT BY THE
                            # GROUND CHUNK. Invalidating the chunk here threw it
                            # away and re-composed the layer for every planted
                            # tile -- three hundred and ninety of them on the
                            # frame the town arrived. The ground under a field
                            # does not change when something is planted in it.
                            world.set_plot(tx, ty, kind, -1000.0)
                            # NOT IMMEDIATE. `invalidate_tile` THROWS THE CHUNK
                            # AWAY and generates a fresh 256x256 one -- noise,
                            # temperature, humidity, numpy clip -- and a town
                            # seeds a garden tile for every house and every
                            # tile of every field: about three hundred and
                            # ninety chunk rebuilds in ONE frame. Measured: 46
                            # to 49 seconds, on the frame a town first came into
                            # the simulation. The worker thread does these.

                            village_plots.add((tx, ty))
                    # The communal 5x5 crop plots on the inner border ring.
                    for ctx, cty, kind in getattr(village, "farm_plots", ()):
                        # dual culture: every cell carries its own crop kind
                        for tx, ty, tkind in village.farm_tiles[(ctx, cty)]:
                            world.set_plot(tx, ty, tkind, now - 6.0)

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
            if _W_ON:
                # A LANE OWNS THE MEN'S POSITIONS. Resolving their collisions
                # here as well would be two writers to one fact.
                active = []
            else:
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
                        _sh = bullet.shooter
                        if _sh is not None and _sh is not player:
                            plog.log("SHOT", getattr(_sh, "name", "?"),
                                     getattr(_sh, "kind", getattr(_sh, "job", "?")),
                                     "nation", getattr(_sh, "nation", None),
                                     "dmg", bullet.damage,
                                     "hp_before", int(player.health),
                                     "dart", getattr(bullet, "dart", False),
                                     "wanted", getattr(player, "wanted", False),
                                     "aggro", getattr(_sh, "aggro", None),
                                     "dist", int(math.hypot(_sh.x - player.x,
                                                            _sh.y - player.y)))
                        if getattr(bullet, "dart", False):
                            # A DART DRAINS A SEPARATE, HIDDEN BAR. His real
                            # health is never touched by the militia. When the
                            # bar empties, he goes down -- asleep, alive.
                            player.tranq_health = getattr(player, "tranq_health",
                                                          player.TRANQ_HEALTH) - bullet.damage
                            if player.tranq_health <= 0:
                                player.tranq_health = player.TRANQ_HEALTH
                                player.tranq()
                        else:
                            player.take_damage(bullet.damage)
                        blood.spawn(player.x, player.y, 7, 14.0)
                        bullet.remove = True
                        break
                    if (bullet.shooter is player
                            and (getattr(obj, "is_militia", False)
                                 or getattr(obj, "militia", False))):
                        try:
                            import detain as _db
                            _db.militia_attacked(player, obj, list(enemies),
                                                 list(village_mod.PEOPLE))
                        except Exception:
                            pass
                    _dart = (getattr(bullet, "dart", False)
                             and getattr(obj, "kind", "") not in ("wolf", "rabbit"))
                    died = obj.take_damage(bullet.damage, tranq=_dart)
                    if getattr(obj, "kind", "") == "villager":
                        _WORK.damage(obj, bullet.damage)
                    try:
                        _sh2 = bullet.shooter
                        if _sh2 is not None and _sh2 is not obj:
                            import economy as _ec
                            _ec.wronged(obj, _sh2, 20.0, now)
                    except Exception:
                        pass
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
                for _n in (_LANE_PEOPLE if not _W_ON else ()):
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

            # AGENTS TELL EACH OTHER. Twice a second is enough for a meeting
            # in a square; the test is a distance, not a line of sight.
            _tell_timer -= dt
            if _tell_timer <= 0.0:
                _tell_timer = 0.5
                nemesis.spread_on_contact()

            # WHERE THE MEN WALK TO. The frame owns the yard; the lane owns
            # the men, so the post is relayed -- and cleared when one is let go.
            _wp = getattr(player, "work_post", None)
            _now_held = {id(n): n for n in (getattr(player, "workers", ()) or ())}
            for _k, _n in list(_posted.items()):
                if _k not in _now_held:
                    _WORK.post(_n, None)
                    _posted.pop(_k, None)
            for _k, _n in _now_held.items():
                if _posted.get(_k, "unset") != _wp:
                    _WORK.post(_n, _wp)
                    _posted[_k] = _wp
            # ---- THE WALK, PHASE BY PHASE -------------------------------
            # A hired man is a man in a town who then has to WALK to the yard.
            # This is the whole journey in the log: he starts, he is a
            # measured distance from the post every twenty seconds, and he
            # arrives -- so "did he actually come?" is never a guess.
            if _wp is not None:
                for _k, _n in _now_held.items():
                    if not getattr(_n, "alive", True):
                        _walk_log.pop(_k, None)
                        continue
                    _d = math.hypot(_n.x - _wp[0], _n.y - _wp[1])
                    _seen = _walk_log.get(_k)
                    if _d <= 40.0:
                        if _seen is not None:
                            # _seen is [first_seen, last_logged] -- a list, and
                            # subtracting it crashed the frame on the very
                            # arrival it was written to celebrate.
                            plog.log("PHASE-ARRIVED", getattr(_n, "name", "?"),
                                     "after", int(now - _seen[0]), "s", "at",
                                     "%d,%d" % (int(_n.x), int(_n.y)))
                            _walk_log.pop(_k, None)
                    elif _seen is None:
                        _walk_log[_k] = [now, now]
                        plog.log("PHASE-WALK", getattr(_n, "name", "?"),
                                 "starts", int(_d), "px from the post")
                    elif now - _seen[1] >= 20.0:
                        _seen[1] = now
                        plog.log("PHASE-WALK", getattr(_n, "name", "?"),
                                 "distance", int(_d), "px after",
                                 int(now - _seen[0]), "s")

            try:
                nemesis.set_now(now)
            except Exception:
                pass
            # ---- ANYBODY OVER THE CAMP FENCE IS SHOT --------------------
            try:
                import gulag as _gulag_t
                _n_in = _gulag_t.tick(player, enemies, village_mod.PEOPLE,
                                      combat=combat, dt=dt)
                if _n_in and int(now) - int(getattr(_gulag_t, "_said", -99)) >= 3:
                    _gulag_t._said = now
                    plog.log("GULAG-INTRUDER", _n_in, "inside the fence")
            except Exception:
                pass
            # ---- THE STATE'S BEER COMES OFF THE TRAIN -------------------
            try:
                import govbeer as _govbeer
                if _TEST_TRAIN[0] is not None:
                    _govbeer.tick(_TEST_TRAIN[0], villages.villages, dt, now)
            except Exception as _gbe:
                plog.log("GOVBEER-ERR", repr(_gbe)[:140])
            # ---- GUNFIRE SCATTERS A CROWD ------------------------------
            try:
                _panic_t[0] += dt
                if _panic_t[0] >= 0.25:
                    _panic_t[0] = 0.0
                    _fresh = [b for b in combat.bullets if b.travelled < 40.0]
                    for _b in _fresh[:3]:
                        _WORK.panic_at(_b.origin_x, _b.origin_y, 620.0)
            except Exception as _pn:
                plog.log("PANIC-ERR", repr(_pn)[:120])
            # ---- THE CAMP'S PEOPLE --------------------------------------
            try:
                import prison as _prison
                _prison.tick(player, enemies, list(village_mod.PEOPLE), dt, now, combat)
            except Exception as _pe:
                plog.log("PRISON-ERROR", repr(_pe)[:140])
            # ---- THE RESETTLEMENT CAMPAIGN ------------------------------
            try:
                import resettle as _reset
                _reset.tick(villages.villages, now, dt)
            except Exception as _re3:
                plog.log("RESETTLE-ERROR", repr(_re3)[:140])
            # ---- ARREST AND DETENTION -----------------------------------
            try:
                import detain as _detain
                # a tranquilised player is carried in by the nearest militia
                if getattr(player, "sleep_t", 0.0) > 0.0 and not getattr(player, "aboard", False):
                    _pc = _detain.player_cell()
                    if _pc is None:
                        _near = _detain._militia_near(player, enemies,
                                                      village_mod.PEOPLE,
                                                      player.x, player.y, 900.0)
                        _cell = _detain._nearest_cell(player.x, player.y)
                        if _near and _cell is not None:
                            _detain.arrest_player(player, _cell)
                            # HE IS CARRIED INSIDE, NOT LEFT ON THE ROOF.
                            _croom = getattr(_cell, "room", None)
                            if _croom is not None:
                                inside_mine = _cell
                                player._mine_latch = True
                                player.x = _croom.W / 2.0
                                player.y = _croom.H - 40.0
                                cam_x = player.x - vw / 2.0
                                cam_y = player.y - vh / 2.0
                                pygame.mouse.set_visible(True)
                                plog.log("ENTER-CELL", "the player is inside the cell at",
                                         int(_cell.x), int(_cell.y))
                _detain.player_tick(player, _TEST_TRAIN[0], dt)
                # the train plans its calls where people are actually waiting
                if int(now * 2) != int(getattr(_detain, "_plan_at", -1)):
                    _detain._plan_at = now * 2
                    _detain.pickup_order(_TEST_TRAIN[0])
                _detain.tick(player, enemies, village_mod.PEOPLE, dt, now)
                _tr0 = _TEST_TRAIN[0]
                if _tr0 is not None and not _tr0.done:
                    _detain.board_train(_tr0, player, now)
            except Exception as _de:
                plog.log("DETAIN-ERROR", repr(_de)[:140])
            # ---- THE TEST TRAIN -----------------------------------------
            try:
                _tr = _TEST_TRAIN[0]
                if _tr is not None and not _tr.done:
                    _tr.update(world_dt if world_tick else dt)
                    try:
                        import train as _tm2
                        _tm2.KNOCK[:] = [k for k in _tm2.KNOCK
                                         if not k.settled or k.life < 8.0]
                        for _k in _tm2.KNOCK:
                            _k.update(dt, blood, corpse_mod)
                        _tr.hit_people(list(village_mod.PEOPLE), list(enemies),
                                       player, blood)
                    except Exception as _ke:
                        plog.log("TRAIN-KILL-ERR", repr(_ke)[:120])
                    if int(now * 4) != int(getattr(_tr, "_ck", -1)):
                        _tr._ck = now * 4
                        _towns_near = [v for v in villages.villages
                                       if abs(v.x - _tr.x) < 9000.0
                                       and abs(v.y - _tr.y) < 9000.0]
                        _tr.check(world, _towns_near, built_houses,
                                  placed_work, camp_walls)
            except Exception as _te2:
                plog.log("TRAIN-ERROR", repr(_te2)[:160])
            # ---- THE CROWN ANSWERS THE NAME -----------------------------
            try:
                _lead = nemesis.FACTS.get(nemesis.LEADER_ID)
                if _lead is not None:
                    if not manhunt.SENT:
                        manhunt.dispatch(player, _lead.get("at"), now=now,
                                         enemies=enemies,
                                         villages=villages.villages)
                    manhunt.tick(player, enemies, now)
                    if int(now) - int(getattr(manhunt, "_said", -999)) >= 5:
                        manhunt._said = now
                        plog.log("MANHUNT-STATE",
                                 "standing", manhunt.any_standing(enemies),
                                 "of", len(enemies), "soldiers",
                                 "| at", int(player.x), int(player.y))
            except Exception as _exc:
                plog.log("MANHUNT-ERR", repr(_exc))
            if int(now) % 60 == 0:
                try:
                    folders_mod.prune(now)
                except Exception:
                    pass

            # ---- THE DEAD STAY WHERE THEY FALL --------------------------
            _last_death = getattr(_WORK, "_last_death", None)
            for _rec in _WORK.take_deaths():
                _rec = tuple(_rec) + (False, [], False, [])
                (_dx, _dy, _who, _pack, _grade, _cloth, _agent, _facts,
                 _worker, _bag) = _rec[:10]
                _fid = None
                if _agent:
                    # THE FOLDER IN HIS POCKET: everything the service told him.
                    _fid = folders_mod.new_folder(_who, _facts, now)
                    plog.log("FOLDER", _who, "carried",
                             len(folders_mod.FOLDERS[_fid]["msgs"]), "message(s)")
                corpse_mod.spawn(_dx, _dy, _who, now, _cloth,
                                 _bag or _pack, _grade, folder=_fid)
                plog.log("CORPSE", _who, "fell at",
                         "%d,%d" % (int(_dx), int(_dy)),
                         "carrying", len(_bag) or len(_pack))
                if _worker:
                    # A BODY IS EVIDENCE. An agent who comes upon one of the
                    # player's dead learns that the yard has a leader.
                    try:
                        for _a in nemesis.agents():
                            if not getattr(_a, "alive", True):
                                continue
                            if ((_a.x - _dx) ** 2 + (_a.y - _dy) ** 2
                                    > nemesis.SEEN_PX ** 2):
                                continue
                            if nemesis.note_leader(_a, at=(_dx, _dy)):
                                plog.log("LEADER", getattr(_a, "name", "?"),
                                         "saw the body of", _who,
                                         "and learned who leads the yard")
                            break
                    except Exception:
                        pass
            for _gone in corpse_mod.update(now):
                plog.log("CORPSE", _gone.name, "is bones and gone")

            # THE STALL GOES ACROSS THE FENCE, once a second: the carts that
            # might walk to it are in the hub lane, and a counter they cannot
            # see is a counter nobody comes to.
            _stall_now = hub_stall()
            player.hub_stall = _stall_now
            player.town_price_for = _town_price_for
            _WORK.stall = (_stall_now.relay()
                           if _stall_now is not None else None)

            # THE MEN WORK THE POST THEY WALKED TO. The frame owns the yard
            # and its chest, so the work -- and what is made, and what will
            # not fit -- happens here, where the chest is.
            _chest = salary_chest()
            player.hub_chest = _chest
            # `dt`, NOT `world_dt`: the men work once per FRAME, and
            # `world_dt` is the step of the world tick that is about to run --
            # the last one, five times a frame's length. Every trade was
            # therefore working about three times faster than a day says.
            for _kind, _man, _what in work.produce(
                    player, _chest, dt, world=world, ground=ground,
                    plots=(getattr(player, "yard_plots", None)
                           or [tuple(r) for r in built_plots]), now=now):
                if _kind == "made":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             getattr(_man, "job", "?"), "made", _what)
                elif _kind == "full":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "chest FULL, kept", _what)
                    toast("%s: nowhere to put the %s"
                          % (getattr(_man, "name", "he"),
                             ", ".join(i.replace("_", " ") for i in _what)))
                elif _kind == "idle":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "has nothing to work with")
                elif _kind == "stopped":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "told to leave off", _what)
                elif _kind == "farm":
                    plog.log("FARM", getattr(_man, "name", "?"), _what,
                             "at", "%d,%d" % (int(_man.x), int(_man.y)))
                elif _kind == "nochess":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "made", _what, "-- NO CHEST in the hub")

            # HIS OWN MEN ARE PAID OUT OF THE CHEST IN HIS HUB, once a day.
            _pay = work.payroll(player, int(now / DAY_LENGTH), salary_chest(),
                                hub_stall())
            for _q in _pay.get("unpaid", ()):
                toast("%s was not paid.   He remembers it." % getattr(_q, "name", "he"))
            for _q in _pay.get("quit", ()):
                toast("%s was not paid.   He walks."
                      % getattr(_q, "name", "He"))
            for _who, _has in (_pay.get("seeds") or {}).items():
                if not _has:
                    toast("%s has no seed to sow -- put some in the chest" % _who)
            # AND A BITTER ONE IS NOT SACKED: he stays on the payroll, and the
            # first service man to come near him turns him. Nothing is said to
            # the player -- that is the point of it.
            work.turn_the_bitter(player, nemesis.agents())

            settle_timer -= dt
            if settle_timer <= 0.0:
                settle_timer = 12.0
                if not _W_ON:
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
            # A HUNTING PARTY IS NEVER CULLED BY DISTANCE. It is sent to a
            # place, not to the player: it stands there until it is met or
            # killed. Without this line the ten men were created, logged, and
            # deleted in the same frame whenever the player was not already
            # within 6.5 km of the spot the crown picked.
            enemies[:] = [e for e in enemies
                          if getattr(e, "follow", False)
                          or getattr(e, "manhunt", False)
                          or getattr(e, "gulag", False)
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

            # THE BARN IS ENTERED BY WALKING THROUGH ITS DOOR, the way a house
            # is -- and lands in the mine's own room branch, so the drawing and
            # the way out are the mine's.
            prison_cd = max(0.0, prison_cd - dt)
            if inside_house is None and inside_mine is None and prison_cd <= 0.0:
                try:
                    import gulag as _gbar
                    _bar = _gbar.prison()
                except Exception:
                    _bar = None
                _doors = []
                if _bar is not None:
                    _doors.append(_bar)
                try:
                    import holding as _hwalk
                    _doors.extend(_hwalk.cells())
                except Exception:
                    pass
                _hit = None
                for _d in _doors:
                    _dx2 = player.x - _d.door[0]
                    _dy2 = player.y - _d.door[1]
                    if _dx2 * _dx2 + _dy2 * _dy2 < 26.0 * 26.0:
                        _hit = _d
                        break
                if _hit is not None:
                    mine_out = (player.x, player.y)
                    inside_mine = _hit
                    player._mine_latch = True
                    player.x = _hit.room.W / 2.0
                    player.y = _hit.room.H - 70.0
                    cam_x = player.x - vw / 2.0
                    cam_y = player.y - vh / 2.0
                    pygame.mouse.set_visible(True)
                    plog.log("ENTER-CELL", getattr(_hit, "kind", "?"), "at",
                             int(_hit.x), int(_hit.y))
                    continue
                if _bar is not None:
                    _ddx = player.x - _bar.door[0]
                    _ddy = player.y - _bar.door[1]
                    if _ddx * _ddx + _ddy * _ddy < 26.0 * 26.0:
                        mine_out = (player.x, player.y)
                        inside_mine = _bar
                        player._mine_latch = True
                        player.x = _bar.room.W / 2.0
                        player.y = _bar.room.H - 90.0
                        cam_x = player.x - vw / 2.0
                        cam_y = player.y - vh / 2.0
                        pygame.mouse.set_visible(True)   # the cursor stays
                        plog.log("ENTER-BARN", "through the door at",
                                 int(_bar.door[0]), int(_bar.door[1]))
                        continue

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
                        try:
                            import houseroom as _hr
                            _room_h = _hr.HouseRoom(house, interior)
                        except Exception as _hre:
                            plog.log("HOUSEROOM-ERR", repr(_hre)[:140])
                            break
                        mine_out = (door_x + fx * 60.0, door_y + fy * 60.0)
                        inside_mine = _HouseBar(house, _room_h, mine_out)
                        inside_house = house
                        player._mine_latch = True
                        player.world_xy = (float(door_x), float(door_y))
                        # LIKE THE GULAG: HE LANDS BESIDE THE DOOR. The exit is a
                        # 24-pixel collision now, not a wide radius, so standing
                        # 30 px up from the door cannot fire it -- but he is one
                        # step from the way out, not a walk across the room.
                        _sp = getattr(interior, "spawn",
                                      (interior.W / 2.0, interior.H - 48.0))
                        player.x, player.y = float(_sp[0]), float(_sp[1])
                        player.bleed = 0.0
                        combat.bullets.clear()
                        prison_cd = 0.7
                        door_cooldown = 0.7      # grace: not thrown straight out
                        pygame.mouse.set_visible(True)
                        plog.log("ENTER-HOUSE", getattr(house, "name", "?"),
                                 "through the door at", int(door_x), int(door_y),
                                 "room", interior.W, interior.H)
                        break

            if player.dead:
                game_over = True
                pygame.mouse.set_visible(True)

        # -- underground ------------------------------------------------------
        # A mine is its own little world: solid rock all round, no window, no
        # view out, and a seam in the middle that never runs out. Handled here
        # and returned from, so nothing in the open air can be disturbed by it.
        if inside_mine is not None:
            _branch = 'mine'
            _room = inside_mine.room
            _room.update(dt)
            mine_cd = max(0.0, mine_cd - dt)
            door_cooldown = max(0.0, door_cooldown - dt)
            _keys = pygame.key.get_pressed()
            if getattr(_room, "is_house", False):
                _door = getattr(_room, "door_rect", None)
                if _door is not None:
                    _dd = math.hypot(player.x - _door.centerx,
                                     player.y - _door.centery)
                    if _dd < 140.0:
                        _HCH = getattr(main, "_house_check", 0.0)
                        main._house_check = _HCH + dt
                        if main._house_check >= 0.5:
                            main._house_check = 0.0
                            plog.log("HOUSE-DOOR", "player", int(player.x),
                                     int(player.y), "door", int(_door.centerx),
                                     int(_door.centery), "dist", int(_dd),
                                     "in", inside_house is not None,
                                     "mine", inside_mine is not None)
            # THE KEY THAT OPENED IT MUST BE RELEASED FIRST. This block reads
            # key STATE, not key events, so the E that took you down was still
            # held on the next frame and slammed the door behind you -- a dark
            # flash and a wiggle, then back in the daylight. Every other menu
            # in the game uses KEYDOWN, which fires once; this one waits for
            # the finger to come off E before it will listen to it again.
            # THE WAY OUT IS THE WAY IN: walk back into the doorway.
            if getattr(_room, "is_prison", False) or getattr(_room, "is_house", False):
                _dr = getattr(_room, "door_rect", None)
                # THE DOORWAY IS A DOORWAY, NOT A HAIRLINE. The old test asked
                # a 16-pixel box to overlap the frame exactly; a man walking at
                # a run stepped clear past it between two frames and never left.
                # Distance to the middle of the doorway: get anywhere near it
                # and you are out.
                if (_dr is not None
                        and math.hypot(player.x - _dr.centerx,
                                       player.y - _dr.centery) < 40.0):
                    inside_mine = None
                    inside_house = None
                    player.x, player.y = mine_out
                    player.world_xy = (float(mine_out[0]), float(mine_out[1]))
                    prison_cd = 1.0
                    door_cooldown = 0.7
                    pygame.mouse.set_visible(False)
                    plog.log("EXIT-HOUSE", "door", int(_dr.centerx),
                             int(_dr.centery), "-> outside", int(mine_out[0]),
                             int(mine_out[1]))
                    continue
            if getattr(_room, "is_house", False) or getattr(_room, "is_cell", False):
                pass        # a cell's door is the state's, not E's
            elif getattr(player, "_mine_latch", False):
                if not _keys[pygame.K_e]:
                    player._mine_latch = False
            elif _keys[pygame.K_e] or _keys[pygame.K_ESCAPE]:
                inside_mine = None                 # back up the shaft
                inside_house = None
                player.x, player.y = mine_out
                prison_cd = 1.0                    # step off the threshold first
                pygame.mouse.set_visible(False)
                continue
            # A HOUSE IS DRAWN EXACTLY LIKE THE GULAG: 1:1, centred, the whole
            # floor on screen including the door. No buffer, no second scale --
            # that buffer was cutting the bottom hundred pixels of the room off,
            # so the doorway was below the visible floor and he could never
            # walk into it.
            cam_x = _room.W / 2.0 - vw / 2.0
            cam_y = _room.H / 2.0 - vh / 2.0
            _draw_w, _draw_h = vw, vh
            wmouse_x = mouse_x
            wmouse_y = mouse_y
            _aim = (wmouse_x - (player.x - cam_x), wmouse_y - (player.y - cam_y))
            player.skill_speed = skills.move_scale()
            award_levels()
            player.skill_stamina = skills.stamina_scale()
            player.update(dt, _keys, _aim, 1.0)
            if getattr(_room, "is_house", False):
                try:
                    player.x, player.y = resolve_circle_rects(
                        player.x, player.y, player.radius,
                        getattr(inside_house, "interior").colliders)
                except Exception:
                    player.x, player.y = _room.clamp(player.x, player.y)
            else:
                player.x, player.y = _room.clamp(player.x, player.y)
            if getattr(_room, "is_cell", False):
                try:
                    import detain as _det_c
                    _det_c.player_tick(player, _TEST_TRAIN[0], dt)
                except Exception:
                    pass
                if getattr(player, "aboard", False):
                    inside_mine = None
                    inside_house = None
                    pygame.mouse.set_visible(False)
                    continue
            # SWING AT THE FACE. Fifteen of these to the open seam's three,
            # and it is still there afterwards -- the seam never runs out.
            if (pygame.mouse.get_pressed()[0] and mine_cd <= 0.0
                    and not getattr(_room, "is_prison", False)
                    and not getattr(_room, "is_house", False)):
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
            _room.draw(screen, cam_x, cam_y, _draw_w, _draw_h)
            if getattr(_room, "is_house", False):
                draw_placing()
            if getattr(_room, "is_prison", False):
                # SIMPLY DARK: one flat veil over the room, nothing else. No
                # hole to follow the man, no rectangles to leave edges.
                try:
                    import gulag as _gdark
                    _gdark.darken(screen)
                except Exception:
                    pass
            _sel = inventory.selected_stack()
            if not getattr(player, "aboard", False):
                player.draw(screen, cam_x, cam_y, _sel.defn.id if _sel else None)
            observer_.draw(screen)
            try:
                if chest_open:
                    chest_panel.draw(screen)
                if workshop_open:
                    workshop_menu.draw(screen)
                if inventory_open:
                    panel.draw(screen)
                if build_menu_open:
                    build_menu.draw(screen)
                if trade_open:
                    trade_menu.draw(screen)
                if pause_open:
                    pause_menu.draw(screen)
            except Exception as _pe2:
                plog.log("ROOM-PANEL-ERR", repr(_pe2)[:120])
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
        if inside_house is not None and inside_mine is None:
            interior = inside_house.interior
            # THE INTERIOR IS DRAWN AT THE SAME ZOOM AS THE WORLD. It was still
            # composed in a full-window frame while its camera came from the
            # narrowed one, so the room hung off-centre with the man not in the
            # middle of it. Borrow the view for the room -- the walls, the
            # window, the people, the man -- and hand the window back for the
            # HUD, exactly as the outdoors does.
            # THE ROOM IS DRAWN AT 1:1, STRAIGHT TO THE SCREEN, LIKE A MINE.
            # It used to be rendered into a 4/9 surface and smooth-scaled back
            # up every frame: a full-window resample per frame for a picture
            # that never changes.
            real_screen = screen
            cam_x = min(max(player.x - vw / 2.0, 0.0),
                        max(0.0, interior.W - vw))
            cam_y = min(max(player.y - vh / 2.0, 0.0),
                        max(0.0, interior.H - vh))
            # INSIDE A HOUSE THERE IS NO OUTSIDE. Black beyond the walls --
            # not a painted world. The room, the furniture, the chest, the
            # workshop, the residents and the vision mask are all exactly as
            # they were; only the view out of the windows is gone, and with it
            # the only reason this branch ever touched the world outside.
            screen.fill((0, 0, 0))
            # ONE BLIT OF A ROOM PAINTED ONCE -- exactly how a mine does it.
            try:
                interior.draw_baked(screen, cam_x, cam_y)
            except AttributeError:
                interior.draw(screen, cam_x, cam_y)
            # THE SAME GREEN OUTLINE AS OUTDOORS, while he is placing furniture.
            draw_placing()
            eye_x = player.x - cam_x + player.facing[0] * 5.0
            eye_y = player.y - cam_y + player.facing[1] * 5.0
            if not getattr(interior, "windows", True):
                # A WINDOWLESS HALL: nothing to look through, so no cone to
                # rasterise and no dark to lay over it.
                draw_below = False
            inside_occluders = [pygame.Rect(r.x - cam_x, r.y - cam_y, r.w, r.h)
                                for r in interior.occluders]
            # THE ROOM'S LIGHT CONE IS NOT REBUILT EVERY FRAME. `build` walks
            # the occluders and rasterises a mask -- and it was being done sixty
            # times a second while the eye moved by a pixel, which is the hitch
            # going into any building. Same mask while the eye is in the same
            # eighth-of-a-metre cell and the head has not turned.
            # A HOUSE IS LIT. The old vision cone laid a darkness over the
            # room except a sliver around the man's head -- which is why a
            # house looked like an empty dark box. The room is drawn bright,
            # furniture and all; no mask, no night veil over it.
            selected = inventory.selected_stack()
            for npc in getattr(inside_house, "occupants", ()):
                if npc.alive and npc.in_interior:      # residents move about
                    npc.draw(screen, cam_x, cam_y, True)
        _sel0 = inventory.selected_stack()      # never rely on a name that a
        # branch may not have assigned: `selected` was unbound on the frames the
        # player was not inside a house, and this is the line that draws him.
        if not getattr(player, "aboard", False):
            player.draw(screen, cam_x, cam_y, _sel0.defn.id if _sel0 else None)
        if getattr(player, "search_progress", 0.0) > 0.0:
            # THE BAR HANGS UNDER THE MAN DOING THE SEARCHING, not in the middle
            # of the screen. Pivot.md S3: he is ten seconds at it, and the
            # patience of the queue is the whole point of the gate.
            _sv = getattr(player, "search_village", None)
            _bx = _by = None
            for _s in (getattr(_sv, "patrol", ()) or ()):
                if getattr(_s, "gate_index", None) == 0 or len(
                        getattr(_sv, "patrol", ()) or ()) == 1:
                    _bx, _by = _s.x - cam_x, _s.y - cam_y
                    break
            if _bx is None:
                _bx, _by = screen.get_width() * 0.5, screen.get_height() * 0.5
            Player._draw_action_bar(screen, _bx, _by,
                                    min(1.0, player.search_progress / 10.0))
            # own coordinates (box.x - cam_x), so it has to be drawn before the
            # frame is blown up -- drawn afterwards it landed at a quarter of
            # its size and a third of a screen from the cursor.
            draw_placing()
            # ...and back to the window for everything that is not the room.
            screen = real_screen
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
                board_panel.town_api = _BOARD_API if _W_ON else None
                if _W_ON:
                    _WORK.watch(board_panel._nearest(board_village, 3))
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
            if dialogue_panel.open_:
                try:
                    dialogue_panel.draw(screen)
                except Exception:
                    import traceback as _tb
                    _tb.print_exc()
            if inventory_open:
                panel.draw(screen)
            if folder_open:
                folder_panel.draw(screen)
                plog.log("FOLDER-DRAW", "panel", int(folder_panel.page),
                         "at", int(screen.get_width()))
            if body_open:
                body_panel.draw(screen)
            if stall_open:
                stall_panel.draw(screen)
            if worker_panel_open:
                worker_panel.draw(screen)
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
                    _wh = 0
                    for _e in pygame.event.get(pygame.MOUSEWHEEL):
                        _wh += _e.y
                    mapmod.handle_input(dt, player, wheel=_wh)
                    mapmod.draw(screen, world, player, _nearest_town(),
                                hub_world.hubs,
                                settlements=list(villages.villages))
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
        # INDOORS THE ROOM IS THE FRAME. The world's zoom borrow exists to
        # compose the outdoors in a smaller surface -- and its `_present` call
        # at the end of the frame scaled that (stale, black) surface back over
        # the window, wiping the room that had just been drawn. That is the
        # empty void: a correct room, painted over.
        _inside_now = inside_house is not None or inside_mine is not None
        # A HOUSE IS COMPOSED SMALL AND BLOWN UP, like the world, so its floor
        # fills the window and the mouse maps at the same scale. A MINE draws
        # straight to the window at 1:1, as it always has.
        scr_w, scr_h = vw, vh
        real_screen = screen
        if inside_mine is not None:
            vw, vh = scr_w, scr_h
        else:
            vw, vh = (max(2, int(scr_w / ZOOM)), max(2, int(scr_h / ZOOM)))
            if view_surf is None or view_surf.get_size() != (vw, vh):
                view_surf = pygame.Surface((vw, vh))
            screen = view_surf
        # THE CAMERA FOLLOWS THE MAN BEING WATCHED, NOT THE PLAYER.
        # (Only outdoors: a room sets its own camera from its own size.)
        #
        # It followed player.x/player.y, and watching had been implemented by
        # MOVING THE PLAYER onto the watched man every frame -- so the player
        # was dragged about the world with the camera tied to him, and the man
        # being watched was only ever in shot because the player had been
        # teleported onto his head. The player is PARKED where he stands; the
        # camera is the thing that moves.
        _look = observer_.target
        if _inside_now:
            pass                      # the room's own branch sets the camera
        elif _look is not None and getattr(_look, "alive", False):
            cam_x = _look.x - vw / 2.0
            cam_y = _look.y - vh / 2.0
        else:
            cam_x = player.x - vw / 2.0
            cam_y = player.y - vh / 2.0
        # HE STANDS AT THE PLAYER'S SHOULDER, EVERY FRAME, AWAKE, ALIVE. The pin
        # and the `_TRUTH` hand-off belong HERE, outside the camera branch --
        # and `asleep` must be cleared, because an NPC is born asleep at night
        # and the draw pass used to skip a sleeping man.
        if _truth is not None:
            # HE DOES NOT FOLLOW. He was pinned to the player's shoulder every
            # frame, so he slid along the road beside him -- "fixed to where I
            # move" instead of a man standing in one place. He is placed ONCE,
            # at the spot he was born on, and held there like a post.
            _truth.x = _truth_home[0]
            _truth.y = _truth_home[1]
            _truth.asleep = False
            _truth.in_interior = False
            _truth.alive = True
            _truth.health = _truth.max_health
            _truth.pause = 1.0
            _TRUTH[0] = _truth
        # THE WORLD IS NOT DRAWN WHILE HE IS INDOORS OR UNDERGROUND. This call
        # painted the wilderness over the room's frame -- which is why entering
        # the barn showed the middle of the map instead of the hall.
        if not _inside_now:
            draw_exterior(cam_x, cam_y, True)
        try:
            # HIS OWN BENCHES, FORGES AND SHAFTS. A village's workplaces are
            # part of its ground; his are his, and have to be drawn.
            for _wp in (() if _inside_now else placed_work):
                _wp.draw(screen, cam_x, cam_y)
            # HIS PLOTS ARE ALWAYS MARKED, and while the build menu is open or
            # he is placing something they are LIT -- so he can see the ground
            # he has already staked before he stakes more.
            _lit = build_menu_open or placing is not None
            for _r in (() if _inside_now else built_plots):
                _sr = pygame.Rect(int(_r.x - cam_x), int(_r.y - cam_y),
                                  _r.w, _r.h)
                if _lit:
                    _glow = pygame.Surface((max(1, _sr.w), max(1, _sr.h)),
                                           pygame.SRCALPHA)
                    _glow.fill((248, 206, 96, 54))
                    screen.blit(_glow, _sr.topleft)
                    pygame.draw.rect(screen, (250, 214, 110), _sr, 3)
                else:
                    pygame.draw.rect(screen, (92, 72, 42), _sr, 2)
        except Exception:
            pass
        try:
            if not _inside_now:
                hub_world.draw(screen, cam_x, cam_y, vw, vh)
        except Exception:
            pass
        if not _inside_now:
            draw_news(screen, cam_x, cam_y, vw, vh)   # the bubble, over his head
        draw_villages = villages.visible(cam_x, cam_y, vw, vh,
                                         extra=hub_world.hubs)
        # THE BAR UNDER THE GUARD, for the man HE is searching -- ten seconds
        # on the same bar the axe swing uses.
        for _v2 in (() if _inside_now else draw_villages):
            _sq = getattr(_v2, "search_now", None)
            if _sq is None:
                continue
            for _g3 in (getattr(_v2, "patrol", ()) or ()):
                Player._draw_action_bar(
                    screen, _g3.x - cam_x, _g3.y - cam_y,
                    min(1.0, float(getattr(_v2, "search_t", 0.0)) / 10.0))
                break

        draw_trees = trees.visible(cam_x, cam_y, vw, vh)
        # ---- THE GATE ------------------------------------------------------
        # Everything about it lives in gate.py now: close -> he comes to you ->
        # ten seconds, bar under him -> one roll -> aggro or through. This block
        # only reports what the module decided.
        try:
            import gate as gate_mod
            # A MAN RIDING THE TRAIN IS NOT AT A GATE. No guard steps up to
            # him, nobody searches him, nobody shouts.
            _res = (None if (_inside_now or getattr(player, "aboard", False))
                    else gate_mod.tick(dt, player, villages.villages, inventory))
            if _res is not None:
                _kind, _town, _units = _res
                plog.log("SEARCHED", _kind, "units", _units,
                         "town", getattr(_town, "name", "?"))
                if _kind == "caught":
                    # HE MAKES SPACE, THEN SHOOTS: the toast is the player
                    # being told, and the town only erupts when the round goes.
                    toast("Searched. %d found. Run." % _units)
                    nemesis.note_caught(player, _town, _units)
                    gate_mod.begin_caught(player, _town, _units)
                elif _kind == "fled":
                    toast("You broke away from the guard. He shouts.")
                    commit_crime(_town)
                elif _units > 0:
                    toast("Searched clean   (smuggling %.1f)" % player.smuggling)
                else:
                    toast("Searched and waved through")
            if gate_mod.tick_caught(dt, player) == "shot":
                gate_mod.fire_shot(player, combat)
                commit_crime(_town)
                gate_mod.caught_over()
            _pg = gate_mod.progress()
            if _pg > 0.0 and gate_mod.guard_of() is not None:
                _gg = gate_mod.guard_of()
                Player._draw_action_bar(screen, _gg.x - cam_x, _gg.y - cam_y, _pg)
        except Exception:
            import traceback as _tb
            _tb.print_exc()

        # CROSSING A WALL WITHOUT BEING WAVED THROUGH IS AGGRO -- and the crime
        # is the CROSSING, not standing inside. This read "he is inside the
        # fence and not waved by", so a game that now BEGINS in a square
        # convicted the player on his first frame: every armed man in the town
        # was aggro before he had taken a step. A man who wakes up inside is
        # inside; a man who steps over the line without a pass is a criminal.
        try:
            _here = None
            for _v in villages.villages:
                _fr = getattr(_v, "fence_rect", None)
                if _fr is None or getattr(_v, "is_hub", False):
                    continue
                if _fr.collidepoint(player.x, player.y):
                    _here = _v
                    break
            _was = getattr(player, "was_inside_v", None)
            player.was_inside_v = _here
            if _here is None:
                # A PASS LASTS WHILE HE IS AT THE GATE. Clearing it the moment
                # he stepped outside the wall searched him again on the way
                # back in, and again -- three times a minute at one gate. The
                # guard remembers him until he has actually GONE AWAY: out of
                # the town's reach, when he is a stranger again.
                _pass = _was or getattr(player, "waved_by", None)
                if _pass is not None and gate.pass_expired(player, _pass):
                    player.waved_by = None
                    player.aggro_village = None
            elif _here is not _was:
                if getattr(player, "waved_by", None) is not _here:
                    if getattr(player, "aggro_village", None) is not _here:
                        player.aggro_village = _here
                        toast("You crossed the wall unsearched. The street turns.")
                        commit_crime(_here)
        except Exception:
            pass

        # Houses and tree trunks block line of sight; canopies soften it.
        reach = vision.max_dist
        occluders = [house.sight_rect for village in draw_villages
                     for house in village.houses
                     if (house.x - player.x) ** 2 + (house.y - player.y) ** 2
                     < (reach + max(house.w, house.h)) ** 2]
        occluders += [house.sight_rect for house in built_houses
                      if (house.x - player.x) ** 2 + (house.y - player.y) ** 2
                      < (reach + max(house.w, house.h)) ** 2]
        near_trees = sorted(draw_trees,
                            key=lambda t: (t.x - player.x) ** 2 + (t.y - player.y) ** 2)
        soft: list[pygame.Rect] = []
        for i, tree in enumerate(near_trees[:80]):
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
        _sel0 = inventory.selected_stack()      # never rely on a name that a
        # branch may not have assigned: `selected` was unbound on the frames the
        # player was not inside a house, and this is the line that draws him.
        if not getattr(player, "aboard", False):
            player.draw(screen, cam_x, cam_y, _sel0.defn.id if _sel0 else None)
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
            if inside_mine is None:
                _present(screen, view_surf, scr_w, scr_h)
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
            if inside_mine is None:
                _present(screen, view_surf, scr_w, scr_h)
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
                board_panel.town_api = _BOARD_API if _W_ON else None
                if _W_ON:
                    _WORK.watch(board_panel._nearest(board_village, 3))
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
        # THE CONVERSATION. It was drawn ONLY inside the house branch, so
        # outdoors it opened and was never painted -- a click that changed the
        # state and showed nothing. Every other panel is drawn here, in the
        # frame the player is actually looking at.
        if dialogue_panel.open_:
            dialogue_panel.draw(screen)
        if inventory_open:
            panel.draw(screen)
        if confirm_open:
            confirm.draw(screen)
        # THE CONTAINERS AND THE DEAD MAN'S MAIL, OUTDOORS. Every one of these
        # was drawn only inside the house branch, so above ground a chest, a
        # hired man's pack, a stall, a body or a folder opened to a state
        # change and NOTHING ON SCREEN.
        if chest_open:
            chest_panel.draw(screen)
        if worker_panel_open:
            worker_panel.draw(screen)
        if stall_open:
            stall_panel.draw(screen)
        if body_open:
            body_panel.draw(screen)
        if folder_open:
            folder_panel.draw(screen)
        if compass_open:
            compass_menu.draw(screen)
        if pause_open:
            pause_menu.draw(screen)
        if map_open:
            try:
                _wh2 = 0
                for _e in pygame.event.get(pygame.MOUSEWHEEL):
                    _wh2 += _e.y
                mapmod.handle_input(dt, player, wheel=_wh2)
                mapmod.draw(screen, world, player, _nearest_town(),
                            hub_world.hubs,
                            settlements=list(villages.villages))
            except Exception:
                pass

        # ---- THE PLAYER TRACE, EVERY FRAME ------------------------------
        try:
            _ks = pygame.key.get_pressed()
            _b = (1 if _ks[pygame.K_w] or _ks[pygame.K_UP] else 0) | \
                 (2 if _ks[pygame.K_s] or _ks[pygame.K_DOWN] else 0) | \
                 (4 if _ks[pygame.K_a] or _ks[pygame.K_LEFT] else 0) | \
                 (8 if _ks[pygame.K_d] or _ks[pygame.K_RIGHT] else 0)
            _lp = _lastpt[0]
            _mv = -1.0 if _lp is None else ((player.x - _lp[0]) ** 2
                                            + (player.y - _lp[1]) ** 2) ** 0.5
            try:
                _visn = len(visible_villages)
            except Exception:
                _visn = -1
            _trace.append((
                "%dms" % int((time.perf_counter() - _framet0) * 1000.0),
                "br=%s" % _branch, "dt=%.3f" % dt, "key=%d" % _b,
                "mv=%.1f" % _mv,
                "at=%d,%d" % (int(player.x), int(player.y)),
                "hp=%d" % int(player.health), "dead=%s" % player.dead,
                "want=%s" % getattr(player, "wanted", False),
                "srch=%.1f" % float(getattr(player, "search_progress", 0.0)),
                "sv=%s" % getattr(getattr(player, "searched_village", None), "name", "-"),
                "house=%s" % (_inside_h()),
                "vis=%d" % _visn, "wanted=%s" % getattr(player, "wanted", False),
            ))
            _lastpt[0] = (player.x, player.y)
            if _b and _mv >= 0.0 and _mv < 0.6:
                _still += 1
            else:
                _still = 0
            if _still == 40:
                _dump_trace("STUCK: %d frames with a movement key held and no movement"
                            % _still)
        except Exception:
            pass

        # ---- THE SLOW-FRAME RECORD -------------------------------------
        # If this frame took more than a quarter of a second, say so, with the
        # breakdown and the one number that matters -- how many towns were being
        # simulated at the time. A freeze is a frame that never ends, and now it
        # leaves a receipt.
        try:
            _fend = time.perf_counter()
            _fms = (_fend - _framet0) * 1000.0
            if _fms > 250.0:
                _vis_n = 0
                try:
                    _vis_n = len(visible_villages)
                except Exception:
                    _vis_n = -1
                _ng = -1
                try:
                    _ng = int(min(abs(v.x - player.x) + abs(v.y - player.y)
                                  for v in villages.villages))
                except Exception:
                    pass
                plog.log("SLOWFRAME", "%dms" % int(_fms),
                         "towns %dms" % int((_pt1 - _framet0) * 1000.0),
                         "men %dms" % int((_pt2 - _pt1) * 1000.0),
                         "rest %dms" % int((_pt3 - _pt2) * 1000.0),
                         "draw %dms" % int((_fend - _pt3) * 1000.0),
                         "visible_towns", _vis_n,
                         "nearest_town_px", _ng,
                         "at", "%d,%d" % (int(player.x), int(player.y)),
                         "dead", player.dead)
                _dump_trace("SLOW FRAME %dms" % int(_fms))
        except Exception:
            pass
        pygame.display.flip()

    _WORK.stop()
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
