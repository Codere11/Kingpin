#!/usr/bin/env python3
"""StratWest -- top-down open-world game prototype.

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
import houseroom
import hudtime
import newsbubble
import nearby
import playerutil
import interact
import savegame
import combat_actions
import life
import render
import engine
import placement

import crop
import smoke
import biomes
import board
import boardapi
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
import lanes_mp as workers
from blood import Blood
from build import BuildMenu, build_cost, build_materials
import stall as stall_mod
import corpse as corpse_mod
import folders as folders_mod
import manhunt
from combat import Combat, segment_circle_hit
from creatures import (Bison, Horse, Patrol, Rabbit, Soldier, Wolf, is_trader,
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
from ui import (BarracksPanel, ChestPanel, ConfirmMenu, FolderPanel, GunsmithPanel,
                HorsePanel, Hotbar, InventoryPanel, MarketPanel, PauseMenu,
                ResearchPanel, RoutePanel, ShipMarketPanel, SignPanel, SmithPanel)
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
# Unarmed he does 16 / skills.UNARMED_WEAKNESS = 5, like any man in the
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
# THE SIMULATED DISTANCE. Settlements within this radius of the player's spawn
# are generated and lived at load; everything beyond is generated, chunk by
# chunk, as he reaches it.
SIM_RADIUS = 2.0 * SPACING
# THE FREEZE RADIUS. A settlement further than this from the player is frozen:
# serialized and dropped from the live world, to wake exactly as it was when he
# returns. Larger than SIM_RADIUS, so a town is not frozen the moment it is
# built.
FREEZE_RADIUS = 3.0 * SPACING
# THE MINECRAFT-STYLE WORLD BORDER. The world is procedurally infinite in the
# west; the only wall is this huge figure, far beyond anything a man will walk.
WORLD_BORDER = 30_000_000


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
    g = SimpleNamespace()
    pygame.init()
    g.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("StratWest")
    pygame.mouse.set_visible(False)
    g.clock = pygame.time.Clock()

    import menu
    pygame.mouse.set_visible(True)
    # AN UNATTENDED INSTANCE STILL HAS TO GET PAST THE MENU. In observe mode
    # there is nobody to click "new game", so it is chosen for him.
    if os.environ.get("KINGPIN_OBSERVE"):
        g.chosen = (0, True)      # 0 = new game, True = start
    else:
        g.chosen = menu.run(g.screen, g.clock)
    if g.chosen is None:
        pygame.quit()
        return
    g.slot, g.test_mode = g.chosen
    # NO BACKSTORY. No trade, no town, no debt, nothing owed to anybody. He
    # starts in the middle of the country with an axe and that is all -- the
    # picker and the letter are still in menu.py, unused, if that changes.
    g.origin = "idle"
    try:
        deaths.banner("game slot %s%s" % (g.slot, "  TEST MODE" if g.test_mode else ""))
    except Exception:
        pass
    persist.set_test(g.test_mode)
    persist.set_slot(g.slot)
    pygame.mouse.set_visible(False)

    g._save = persist.read()
    g.world = World(seed=int(g._save.get("seed", 20240501)))
    g.ground = GroundRenderer(g.world)
    g.world.ground = g.ground          # so soil edits from anywhere can redraw
    g.scatter = Scatter(g.world.seed, g.world)
    g.ground.scatter = g.scatter
    g.static_layer = StaticLayer(g.ground, g.scatter)
    g.vision = Vision(cone_deg=175.0, max_dist=560.0)
    g.interior_vision = Vision(cone_deg=175.0, max_dist=560.0, downscale=3)
    g.villages = Villages(g.world.seed)
    g.ground.villages_v = g.villages
    g.SPACING = SPACING
    g.FREEZE_RADIUS = FREEZE_RADIUS
    g.SIM_RADIUS = SIM_RADIUS
    g.zoom = ZOOM
    g.aiming = False           # holding a musket/double-shot/rifle: shadowless, zoomable view
    g._aiming_prev = False
    g.trees = Trees(g.world.seed)
    g.world.trees = g.trees            # so loggers can find the woods to cut
    set_forest(g.trees)              # villages stake out a woodlot as they build
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
    g._cached = None
    if g._cached is not None:
        g.villages = g._cached
        g.ground.villages_v = g.villages
        # THE REGISTER OF PEOPLE IS REBUILT AFTER A LOAD. Unpickling does not
        # call __init__, so a restored villager never put himself in it, and
        # the world would have walked nobody at all.
        print("registered from the cache: %d people, %d houses"
              % (village_mod.rebuild_people(g.villages),
                 village_mod.rebuild_houses(g.villages)))
    else:
        worldbuild.load_world(g.screen, g.clock, g.villages, g.world)  # every village, before the first step
        # THE POPULATION IS SET BEFORE THE CACHE IS WRITTEN. Writing it after
        # meant the cache held 2,084 people and every later launch restored all
        # of them and then threw half away again.
        worldbuild.set_world_population(g.villages)
        worldio.save_cached_world(g.villages, g.world.seed)
        village_mod.rebuild_people(g.villages)
        village_mod.rebuild_houses(g.villages)

    # ---- THE HUBS IN THE WILD -- not villages; no war can be declared
    # on one, because no one admits it exists.
    g.hub_world = hubs.Hubs(g.world, g.villages)
    # A HANDLE FOR TOOLS AND TESTS, like village.PLAYER: the hub registry is a
    # local, so nothing outside main() could ever see the player's own yard.
    try:
        village_mod.HUBS = g.hub_world
    except Exception:
        pass
    g.dialogue_panel = dialogue.Dialogue()

    def _main_capital():
        return worldbuild.main_capital(g.villages)

    g.hub_world.build_caravans(g.world)
    # NO TREE THROUGH A ROOF -- BUT THE WOODS STILL GROW IN THE YARD.
    #
    # This used to mark EVERY tree inside a hub's fence as felled, directly
    # and for ever: not cut (cutting leaves a stump that regrows), just marked.
    # The result was a hub environment where trees never grew back and every
    # stump that was there before simply stayed a stump -- or, after a reload,
    # vanished. What the yard needs is only this: no tree standing in a HOUSE
    # or a WORKPLACE. Everything else is woods, and woods grow.
    for _h in g.hub_world.hubs:
        g._built = []
        for _b in list(getattr(_h, "houses", ()) or ()):
            g._br = getattr(_b, "rect", None)
            if g._br is not None:
                g._built.append(g._br.inflate(40, 40))
        for _b in list(getattr(_h, "workplaces", ()) or ()):
            g._br = getattr(_b, "rect", None)
            if g._br is not None:
                g._built.append(g._br.inflate(40, 40))
        if not g._built:
            continue
        for _t in g.trees.visible(min(r.x for r in g._built) - 200,
                                min(r.y for r in g._built) - 200,
                                max(r.right for r in g._built) + 200
                                - min(r.x for r in g._built),
                                max(r.bottom for r in g._built) + 200
                                - min(r.y for r in g._built)):
            if any(r.collidepoint(_t.x, _t.y) for r in g._built):
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
    g._pop = worldbuild.set_world_population(g.villages)
    if g._pop <= 0:
        print("WARNING: the world has no people at all")
    else:
        print("population set to %d over %d towns"
              % (g._pop, len(list(g.villages.villages))))


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
        g.ground.refresh_around(0.0, 0.0, WIDTH, HEIGHT)
    except Exception:
        pass

    # ---- THE WORLD MAP IS DRAWN ONCE, HERE, BEHIND THE LOADING SCREEN ----
    #
    # The map is one fixed image of the whole country (terrain, camps, all of
    # it). Building it samples the noise for a million points -- a second or so
    # of work. Do it here, under the progress bar, so the first press of M just
    # shows it: the player never stands there waiting for the map to appear.
    try:
        mapmod.prewarm(g.world)
    except Exception:
        pass

    g.ore_field = ore.OreField(g.world.seed)
    # THE TOWN THAT HAS WORK FOR HIM, nearest to the origin first. A man does
    # not arrive in a village that has no forge and call himself a smith.
    def origin_village(kind):
        return worldbuild.origin_village(kind, g.villages)

    g._home = origin_village(g.origin)
    # HIS TOWN, UNDER A NAME NOTHING ELSE USES.
    g._origin_town = g._home
    g._hx = 0.0
    g._hy = 0.0
    if g._home is not None:
        # NOT IN THE ROAD: a few paces off the door of the place he works, so
        # the first thing he sees is his own trade.
        g._wants = {"smith": "smith", "artisan": "lab", "brewer": "brewery"}.get(g.origin)
        g._spot = None
        if g._wants is not None:
            g._spot = next((wp for wp in g._home.workplaces if wp.kind == g._wants), None)
        elif g.origin == "farmer" and g._home.farm_plots:
            g._tx, g._ty, _k = g._home.farm_plots[0]
            g._spot = type("P", (), {"x": g._tx * 32 + 16, "y": g._ty * 32 + 16})()
        if g._spot is not None:
            g._hx, g._hy = g._spot.x, g._spot.y + 64.0
        if g._hx == 0.0 and g._hy == 0.0:
            # no bench beside him: the square itself, inside the wall
            g._hx, g._hy = g._home.x, g._home.y
    # HE WAKES INSIDE HIS TOWN, not climbing the wall. Mark the town he woke
    # in, so the wall-crossing check does not convict him on the first frame.
    g._start = g._home
    if g._home is None:
        # NO TOWN AT ALL: open country, somewhere new every world.
        try:
            g._towns_all = [v for v in g.villages.villages
                          if not getattr(v, "is_hub", False)]
        except Exception:
            g._towns_all = []
        g._spawn_rng = random.Random((int(g._save.get("seed", 20240501)) ^ 0xA11CE5EED)
                                   & 0xFFFFFFFF)
        g._hx, g._hy = 0.0, 0.0
        for _try in range(600):
            g._sx = g._spawn_rng.uniform(-65000.0, 65000.0)
            g._sy = g._spawn_rng.uniform(-65000.0, 65000.0)
            if any((v.x - g._sx) ** 2 + (v.y - g._sy) ** 2 < 1500.0 ** 2
                   for v in g._towns_all):
                continue
            if any(getattr(_h, "fence_rect", None) is not None
                   and _h.fence_rect.inflate(900, 900).collidepoint(g._sx, g._sy)
                   for _h in getattr(g.hub_world, "hubs", ()) or ()):
                continue
            g._hx, g._hy = g._sx, g._sy
            break
        print("OPEN-FIELD SPAWN  %.0f,%.0f" % (g._hx, g._hy))
    else:
        print("SETTLEMENT SPAWN  %.0f,%.0f  in %s"
              % (g._hx, g._hy, getattr(g._home, "name", "?")))
    # ---- THE COLONIAL COAST ----------------------------------------------
    # He wakes on the beach: the ocean to his right, the ship just offshore,
    # and the land stretching away west. The first biome is never snow, so
    # the coast is walked until the ground is warm enough.
    import world as _world
    import biomes as _bio
    _sx = _world.coast_x(0.0, g.world.seed) - 44.0
    _sy = 0.0
    for _i in range(1, 400):
        _found = False
        for _sgn in (-1, 1):
            _y = _sgn * _i * 3000.0
            _x = _world.coast_x(_y, g.world.seed) - 44.0
            if _bio.temperature(_x, _y, g.world.seed) >= 0.40:
                _sx, _sy = _x, _y
                _found = True
                break
        if _found:
            break
    g._spawn = (_sx, _sy)
    g._hx, g._hy = _sx, _sy
    g._home = None
    g._start = None
    # ---- NO TEST SPRITES. The only people are the native settlements. -----
    g._observe_npcs = []
    g._observe_soldiers = []
    # ---- OBSERVE MODE ------------------------------------------------------
    # KINGPIN_OBSERVE=1 runs a real instance -- real window, real frame, real
    # world -- with the player standing invincible in open ground while
    # everything else lives around him. He is not moved by anything and nothing
    # can hurt him; the world carries on. Used to watch the gates work.
    g._observe_spot = None
    if os.environ.get("KINGPIN_OBSERVE"):
        try:
            g._towns = [v for v in g.villages.villages
                      if getattr(v, "fence_rect", None) is not None
                      and not getattr(v, "is_hub", False)]
            if g._towns:
                g._t0 = min(g._towns, key=lambda v: v.x * v.x + v.y * v.y)
                # AT THE GATE. The point of watching is to see the guard walk
                # over and search him, ten seconds, bar under his feet.
                g._g0 = fence.gate_list(g._t0)[0]
                g._ox0, g._oy0 = fence.OUTWARD[g._g0[0]]
                g._observe_spot = (g._g0[1] + g._ox0 * 130.0, g._g0[2] + g._oy0 * 130.0)
                g._hx, g._hy = g._observe_spot
                g._origin_town = g._t0
                print("OBSERVE: pinned at %.0f,%.0f -- 1.7 km from %s"
                      % (g._observe_spot[0], g._observe_spot[1], g._t0.name))
        except Exception:
            g._observe_spot = None
    # ---- THE CHAIN TEST ----------------------------------------------------
    # KINGPIN_CHAIN=1 watches ONE hub, link by link, in the running game. Each
    # link has a deadline; when one does not happen in time the instance STOPS
    # and says which link broke. Nothing is simulated outside the game.
    def _csay(msg: str) -> None:
        playerutil.csay(msg, os)

    g._chain = None
    if os.environ.get("KINGPIN_CHAIN"):
        g._chain = {"hub": None, "t0": 0.0, "link": 1, "seen": {}, "t": 0.0,
                  "f": 0, "wall0": time.perf_counter(), "last_say": -1.0}

    g._TRUTH = [None]      # the man who is always beside the player, if any
    g.player = Player(g._hx, g._hy)
    # HE WAKES UP INSIDE THE TOWN, not climbing into it (see the wall-crossing
    # check further down): the first frame must not read as an unsearched
    # entry, or the whole square is at his throat before he takes a step.
    if g._start is not None:
        g.player.was_inside_v = g._start
        g.player.waved_by = None
        g.player.aggro_village = None
    # ---- THE TRUTH-TELLER -----------------------------------------------
    # One man who stands beside the player from the first frame and never
    # leaves. He is a REAL NPC -- a real name, a real settlement, a real trade,
    # the same class every other man in the world is made of -- he simply
    # cannot be killed and does not walk away. He exists to be talked to.
    g._truth = None
    g._truth_home = [0.0, 0.0]      # the spot on the ground he never leaves
    try:
        g._towns_t = [v for v in g.villages.villages
                    if getattr(v, "fence_rect", None) is not None
                    and not getattr(v, "is_hub", False)]
        # THE SAME TOWN YOU WAKE IN, so the man beside you is one of its own.
        g._tt_town = (g._origin_town
                    if getattr(g._origin_town, "fence_rect", None) is not None
                    else (random.choice(g._towns_t) if g._towns_t else None))
        if g._tt_town is not None:
            g._truth = village_mod.NPC(
                g.player.x + 44.0, g.player.y, random.randrange(1 << 30),
                "%s %s" % (random.choice(village_mod.FIRST_NAMES),
                           random.choice(village_mod.LAST_NAMES)),
                "truth_teller", "Truth-teller", g._tt_town)
            g._truth.job = random.choice(
                ["farm", "logger", "mine", "smith", "trader",
                 "lab", "brewery", "hand"])
            g._truth.nation = g._tt_town.nation
            g._truth.team = ("nation", g._tt_town.nation)
            g._truth.max_health = stats.PLAYER_MAX_HEALTH
            g._truth.health = stats.PLAYER_MAX_HEALTH
            g._truth.is_truth_teller = True
            g._tt_town.npcs.append(g._truth)
            g._TRUTH[0] = g._truth      # from the moment he exists, he is clickable
            g._truth_home[0], g._truth_home[1] = g._truth.x, g._truth.y
            plog.log("TRUTH", "created", g._truth.name, "of", g._tt_town.name,
                     "trade", g._truth.job, "at", "%d,%d"
                     % (int(g._truth.x), int(g._truth.y)))
    except Exception as _te:
        # A WINDOWED BUILD SWALLOWS stdout. If he cannot be made, the reason
        # must reach a file or nobody will ever know.
        plog.log("TRUTH-ERROR", repr(_te)[:200])
    if g._observe_spot is not None:
        g.player.god = True
    # A NAME, AND A LETTER WAITING FOR HIM. The name is drawn the same way the
    # towns draw theirs, so he is a man out of this world and not a visitor to
    # it; the letter is the only thing in the game that will ever explain
    # anything, and it says who he is, what he owes, and how his trade pays.
    g._rng = random.Random((int(g._save.get("seed", 20240501)) ^ 0x5EED) & 0xFFFFFFFF)
    g.player.name = "%s %s" % (g._rng.choice(village_mod.FIRST_NAMES),
                             g._rng.choice(village_mod.LAST_NAMES))
    # HE IS ALREADY IN THE BOOK, AND ALREADY IN WORK. The letter says he has
    # just started as a smith; the board has to agree with the letter, so the
    # trade is his from the first frame and the debt is what the letter is
    # about. Idle owes the least and has no post, which is the trade-off.
    g._JOB = {"smith": "smith", "artisan": "lab", "brewer": "brewery",
            "farmer": "farm", "logger": "logger", "trader": "trader",
            "soldier": "defender"}
    g._DEBT = {"trader": 500, "smith": 450, "soldier": 430, "artisan": 400,
             "brewer": 370, "farmer": 340, "logger": 310, "idle": 300}
    g.player.origin = g.origin
    g.player.debt = 0                 # he owes nobody anything
    g.player.debt_paid = 0
    g.player.god = g.test_mode
    # THE TOWNS CAN NOW SEE HIM. One assignment, so a village can put the
    # player in a town's own books without every caller passing him down.
    village_mod.PLAYER = g.player

    g.cam_x = g.player.x - WIDTH / (2.0 * ZOOM)
    g.cam_y = g.player.y - HEIGHT / 2

    g.inventory = Inventory(capacity=32)
    # WHAT THE TRADE COMES WITH. A trader arrives with stock to sell, a smith
    # with iron at the anvil, and the logger with an axe and nothing else in
    # the world -- which is the hardest start and is meant to be.
    g.KITS = {"idle": (("axe", 1),),
        "trader":  (("tobacco", 10), ("beer", 3), ("cigar", 2)),
        "smith":   (("iron", 24),),
        "soldier": (("rifle", 1), ("ammo", 40), ("first_aid", 1)),
        "artisan": (("tobacco", 24),),
        "brewer":  (("wheat", 12), ("wheat_seed", 6)),
        "farmer":  (("wheat_seed", 12), ("seed_bag", 4), ("shovel", 1),
                    ("watering_can", 1)),
        "logger":  (("axe", 1),),
    }
    for _item, _qty in g.KITS.get(g.origin, ()):
        g.inventory.add(_item, _qty)
    # EVERY MAN IN THE WOODS HAS AN AXE. "idle" was written twice in that
    # table -- the second entry, empty, won -- so the one start with nothing
    # was also the one start that could not cut a tree for its first coin.
    if g.inventory.count_of("axe") <= 0:
        g.inventory.add("axe", 1)
    # THE PACK ON THE MAN. Dialogue and the yard's work need to move things
    # into and out of it, and neither is handed the local `inventory`; the
    # player is the one object they both already have.
    g.player.pack = g.inventory
    g.player.hub_chest = None
    g.hotbar = Hotbar(g.inventory, visible=8)
    g.panel = InventoryPanel(g.inventory)
    g.panel.player = g.player
    g.board_panel = board.BoardPanel()
    # TEST MODE'S INSPECTOR AND LOCK-ON. See observer.py -- 'I' lists every
    # living person, filterable by trade, town and nation, and Enter locks the
    # camera onto one of them and starts a log of HIS doings alone.
    g.observer_ = observer.Observer()
    g.combat = Combat()
    g.blood = Blood()
    g.vignette = DamageVignette()
    g.overlay = GameOver()
    g.build_menu = BuildMenu(g.inventory, g)
    g.workshop_menu = WorkshopMenu(g.inventory, g)
    g.confirm = ConfirmMenu()
    g.compass_state = compass.Compass()
    g.compass_menu = compass.CompassMenu()
    g.comm = None            # equipped way to speak: insult / praise / threaten
    g.comm_mode = False      # G toggles the hotbar between items and words
    g.build_menu.free = g.test_mode
    g.workshop_menu.free = g.test_mode
    g.pause_menu = PauseMenu()
    g.skills = Skills(is_player=True)   # the player's own road, see skills.py

    g.enemies: list[Enemy] = []          # nation soldiers and wolves

    # ---- THE TEST ENGINE, running the whole network once ----------------
    g._TEST_TRAIN = [None]
    g._panic_t = [0.0]           # gunfire -> the crowd breaks and runs
    g._EXPRESS = [False]         # the engine is running for the camp, not touring
    try:
        import train as _train_mod
        import rail as _rail_t
        _rail_t.ensure(g.villages.villages)
        g._rt = _rail_t.tour()
        if g._rt:
            g._TEST_TRAIN[0] = _train_mod.Train(g._rt)
            plog.log("TRAIN-START", len(g._rt), "route points,",
                     int(_rail_t.count()[1]), "px of track")
    except Exception as _te:
        plog.log("TRAIN-ERROR", repr(_te)[:160])
    try:
        import rail as _rail0
        _rail0.ensure(g.villages.villages)
    except Exception as _re0:
        plog.log("RAIL-ERROR", repr(_re0)[:120])
    g.armies: list = []                  # columns on the march, this campaign
    g.world.enemies = g.enemies            # so villagers can spot a predator
    # WHO CAN SEE A THING HAPPEN: the whole living population, for witnesses.
    try:
        import economy as _eco_hook
        _eco_hook.POPULATION = lambda: list(village_mod.PEOPLE)
    except Exception:
        pass
    # A GUNMAN DOES NOT SHOOT THROUGH HIS OWN PEOPLE.
    try:
        import enemy as _enemy_hooks
        _enemy_hooks.CROWD = lambda: list(village_mod.PEOPLE) + list(g.enemies)
        _enemy_hooks.CIVILIANS = lambda: list(village_mod.PEOPLE)
    except Exception as _eh:
        plog.log("CROWD-HOOK-ERR", repr(_eh)[:120])
    g.rabbits: list[Rabbit] = []
    g.horses: list[Horse] = []
    g.patrols: list[Patrol] = []
    g.player.nation = None
    g.player.squad = []
    g.spawn_timer = 0.0
    g._lane_seen = None
    g.grid = None
    g.grid_timer = 0.0
    g.nav = None
    g.nav_timer = 0.0

    def make_village_patrol(village, count=4):
        return worldbuild.make_village_patrol(village, count, fence, random,
                                              nation_color, Soldier)

    def spawn_patrol() -> None:
        cand = g.villages.visible(g.player.x - 4000.0, g.player.y - 4000.0, 8000, 8000)
        if not cand:
            return
        v = random.choice(cand)
        angle = random.uniform(0.0, 2.0 * math.pi)
        dist = v.radius + random.uniform(140.0, 700.0)
        patrol = Patrol(v.x + math.cos(angle) * dist,
                        v.y + math.sin(angle) * dist, v.nation,
                        size=random.randint(2, 4),
                        color=nation_color(v.nation))
        g.patrols.append(patrol)
        g.enemies.extend(patrol.members)

    def _loot(killer, victim) -> None:
        worldbuild.loot(killer, victim, g.player, economy, g.inventory, toast)

    def spawn_wolf() -> None:
        worldbuild.spawn_wolf(g.player, g.world, village_mod, g.enemies, biomes, math,
                              random, Wolf, g._origin_town)

    def spawn_rabbit() -> None:
        worldbuild.spawn_rabbit(g.player, g.world, g.rabbits, biomes, math, random,
                                Rabbit)

    def spawn_horse() -> None:
        worldbuild.spawn_horse(g.player, g.world, g.horses, biomes, math, random,
                               Horse)

    def spawn_bison() -> None:
        worldbuild.spawn_bison(g.player, g.world, g.enemies, biomes, math, random,
                               Bison)

    # NO PATROLS. The gangs out on the map were removed in favour of the two
    # standing guards at each gate -- but this line kept spawning three of them
    # at the start of every game, and they and their shotguns were still out
    # there looking for somebody.
    for _ in range(3):
        spawn_wolf()
    for _ in range(5):
        spawn_rabbit()
    for _ in range(2):
        spawn_horse()
    for _ in range(2):
        spawn_bison()
    # ...and the death screen's own typeface, which was being built for the
    # first time in the frame the player died -- three SysFonts, a visible
    # stop at the worst possible moment. The size comes from the screen, not
    # from vw/vh: those are set inside the loop below, and naming them here
    # crashed the game the moment a world was made.
    g._sw, g._sh = g.screen.get_size()
    g.overlay.layout(g._sw, g._sh)
    g.seeded_villages: set[tuple[int, int]] = set()
    g.village_plots: set[tuple[int, int]] = set()

    g.game_over = False
    g.inventory_open = False
    g.chest_open = False
    g.chest_panel = None
    # THE SIGN-POST: how many conquered people work each job.
    g.sign_open = False
    g.sign_panel = None
    g.sign_post = None
    # A GUNSMITH'S CHOICE OF PRODUCT, opened by clicking him.
    g.gunsmith_open = False
    g.gunsmith_panel = None
    g.gunsmith_npc = None
    # A SMITH'S CHOICE OF PRODUCT, opened by clicking him.
    g.smith_panel_open = False
    g.smith_panel = None
    g.smith_npc = None
    # THE BARRACKS: buy a soldier with armor, rifle and ammo.
    g.barracks_open = False
    g.barracks_panel = None
    g.barracks_wp = None
    # THE FREE MARKET: sell manufactured goods out of the ship's hold.
    g.ship_hold = Inventory(capacity=32)
    g.market_open = False
    g.market_panel = None
    import market as _market
    _market.init(g)
    g.smoke = smoke.Smoke()            # a smoke signal over a conquered fire
    g.war_alarms = 0                  # smoke alarms raised: 1 arms a bowman, 2 arms two bowmen
    # A CONQUERED HORSE'S SADDLE BAGS, with the Send-to-ship button.
    g.horse_panel_open = False
    g.horse_panel = None
    g.horse_sel = None
    g.riding = None               # the horse he is on, or None
    # A HIRED MAN'S PACK, OPENED THE WAY A CHEST IS.
    g.worker_panel_open = False
    g.worker_panel = None
    # THE MARKET STALL: the player's counter, its prices, and its purse.
    g.stall_open = False
    g.stall_panel = None
    # A BODY ON THE GROUND, OPENED LIKE A CHEST.
    g.body_open = False
    g.body_panel = None
    # A DEAD AGENT'S MAIL, OPENED BY EQUIPPING HIS FOLDER AND CLICKING.
    g.folder_open = False
    g.folder_panel = None
    g.trade_open = False
    g.trade_menu = None
    g.build_menu_open = False
    g.workshop_open = False
    g.confirm_open = False
    g.compass_open = False
    g.pause_open = False
    g.map_open = False
    g.board_open = False
    g.smith_open = False
    g.smith_shop = None
    g.artisan_open = False
    g.artisan_bench = None
    g.naming_open = False
    g.naming_camp = None
    g.naming_text = ""
    g.naming_placeholder = ""
    g.conquered_count = 0
    g.route_open = False
    g.route_panel = None
    g.route_horse = None
    g.research_open = False
    g.research_panel = None
    import research as _research
    _research.init(g)
    g.work_cd = 0.0
    g.work_msg = ""
    g.inside_mine = None
    g.mine_out = (0.0, 0.0)
    g.view_surf = None
    g.mine_cd = 0.0
    g.board_village = None
    g.ENV_CELL = 220.0            # static ground is cached per patch this size
    g.ENV_CACHE: dict = {}
    g._BUILD_VER = [0]            # bumped when the player builds something
    g.SPEEDS = (1.0, 5.0, 25.0)     # test-mode time scale
    g.speed_i = 0
    g.time_scale = g.SPEEDS[0]
    # Chart the map at world creation, on a worker thread, so pressing M
    # simply shows it instead of stalling the game for a second. The map is
    # the simulation's view: a region the size of the old world, around him.
    g.world_map = None   # the old town map is gone; map.py draws the world now
    g.placing = None
    # SETTLEMENT DESIGNATION: pick 'Field' and the player freezes while the
    # camera pans like a city-management view; drag a rectangle to designate.
    g.field_design = False
    g.field_mode = "field"          # what the current designation lays: field|orchard
    g.field_start = [None]            # one corner of the field being drawn
    g.field_raw = [None]              # the un-snapped click, to tell click from drag
    g.field_del = [False]             # right-drag: deleting, not adding
    g.field_designations: list = []   # [{"rect","type","kind"}], one per designation
    g.player_camp = None              # the conquered settlement (colony.py)
    g.sync_player_camp = None
    g.next_field_kind = None
    g.first_field_kind = None
    g.built_houses: list[House] = []
    g.placed_work: list = []          # the four trades, out of doors, on his land
    g.built_chests: list = []          # the 1x2 chests he has built
    g.built_signs: list = []           # the sign-posts that set job counts
    g.built_foodboxes: list = []       # feed boxes the livestock eat from
    g.built_plots: list = []          # plots he has drawn on his own ground
    g.plot_start = [None]             # where the plot drag began
    g.built_fences: list = []
    g.built_blocks: dict = {}         # (tx, ty) -> kind: Minecraft-style 1x1 blocks
    # THE CAMP'S WALL IS NOT THE PLAYER'S FENCE. Kept out of `built_fences`
    # (which the axe may chop and the save file remembers) and drawn and
    # collided with separately: a wall you can hack a hole in is not a prison.
    g.camp_walls: list = []

    # THE GULAG IS GONE: no camp, no guards, no barn, no holding cells.
    g._camp_men = []
    g._barn = None
    g._holding = []

    g.built_gates: list = []
    g.fence_horizontal = True
    g.inside_house = None
    g.door_cooldown = 0.0
    g.backdrop = None            # the frozen outdoors behind a house's windows
    g.backdrop_for = None        # which house it belongs to
    g.backdrop_age = [0]         # how many frames it has been up
    g.kills = 0
    g.now = 0.0
    g.toast_text = ""
    g.toast_time = 0.0
    g.player_drip = 0.0
    g.hud_status = ""
    g.shade_cache: dict = {}
    g.active_chaos: list = []

    def award_levels() -> None:
        hudtime.award_levels(g.skills, g.player)

    def toast(message: str) -> None:
        
        g.toast_text = message
        g.toast_time = 1.6
        # WHAT HE WAS JUST TOLD, IN THE LOG. A refusal on screen that leaves no
        # trace is a refusal nobody can ever diagnose -- "it would not build"
        # cost an evening more than once.
        try:
            plog.log("TOAST", message)
        except Exception:
            pass

    def clamp_world() -> None:
        hudtime.clamp_world(g.player, WORLD_BORDER)

    def try_talk() -> bool:
        return life.try_talk(g._TRUTH, village_mod, pygame, g.cam_x, g.cam_y, ZOOM,
                             g.dialogue_panel, g.player, _main_capital, plog)

    def respawn() -> None:
        
        g.game_over = life.respawn(g.player, g._truth, g._truth_home, g._TRUTH, g.combat,
                                 pygame)

    g.WITNESS_PX = 900.0        # close enough to have watched it happen

    def _see_murder(victim) -> None:
        interact.see_murder(victim)

    def _meet_army(trader, army, now) -> None:
        interact.meet_army(trader, army, now)

    def make_tradeable(npc):
        return interact.make_tradeable(npc, random)

    def guard_search(npc) -> None:
        interact.guard_search(npc, g.inventory, g.player, toast, commit_crime, random)

    def open_trade(npc) -> None:
        interact.open_trade(npc, make_tradeable, g.player, _main_capital,
                            g.dialogue_panel, pygame, plog)

    def open_trade_menu(npc) -> None:
        
        g.trade_open, g.trade_menu = interact.open_trade_menu(
            npc, make_tradeable, g.player, g.inventory, toast, village_mod,
            TradeMenu, pygame, plog)

    def nearest_hostile(npc):
        return interact.nearest_hostile(npc, g.player)

    def commit_crime(where=None) -> None:
        interact.commit_crime(where, g.villages, g.player, g.now, g._WORK)

    def player_hunted() -> bool:
        return playerutil.player_hunted(g.visible_villages)

    def tile_is_mine(tx: int, ty: int) -> bool:
        return placement.tile_is_mine(tx, ty, g.player, g.built_houses,
                                      g.built_fences, player_hunted, TILE, fence)

    def settle_reload() -> None:
        playerutil.settle_reload(g.player, g.inventory, toast)

    def banish(nation) -> None:
        playerutil.banish(g.player, g.enemies, nation, toast, nation_name)

    # -- item actions -------------------------------------------------------
    def fire() -> None:
        combat_actions.fire(g.player, g.inventory, g.skills, g.combat, g.cam_x, g.cam_y,
                            ZOOM, toast)

    def use_first_aid() -> None:
        playerutil.use_first_aid(g.player, g.inventory, toast)

    def use_axe() -> None:
        
        _g = SimpleNamespace(
            player=g.player, skills=g.skills, inventory=g.inventory, combat=g.combat,
            enemies=g.enemies, blood=g.blood, rabbits=g.rabbits, horses=g.horses,
            hub_world=g.hub_world,
            truth=g._TRUTH, trees=g.trees, built_fences=g.built_fences,
            built_gates=g.built_gates, built_blocks=g.built_blocks,
            built_chests=g.built_chests, built_signs=g.built_signs,
            built_foodboxes=g.built_foodboxes, placed_work=g.placed_work,
            visible_villages=g.visible_villages,
            work_lanes=g._WORK, now=g.now,
            toast=toast, mark_dirty=mark_dirty, pay_share=pay_share,
            commit_crime=commit_crime, see_murder=_see_murder, banish=banish)
        g.kills = combat_actions.use_axe(_g, g.kills)

    def use_pickaxe() -> None:
        combat_actions.use_pickaxe(g.player, g.combat, g.ore_field, g.inventory,
                                   pay_share, mark_dirty, toast)

    g.EAT_RESTORE = 35.0      # any food fills the same belly, as it does for
                            # every villager: one item, one meal.

    def click_a_man(at=None) -> bool:
        
        _g = SimpleNamespace(
            player=g.player, inventory=g.inventory, cam_x=g.cam_x, cam_y=g.cam_y,
            zoom=ZOOM, truth=g._TRUTH, villages=g.villages,
            dialogue_panel=g.dialogue_panel, main_capital=_main_capital,
            toast=toast, open_trade=open_trade,
            body_open=g.body_open, body_panel=g.body_panel)
        _ok, g.body_open, g.body_panel = combat_actions.click_a_man(_g, at)
        return _ok

    def on_click() -> None:
        
        _g = SimpleNamespace(
            player=g.player, inventory=g.inventory, skills=g.skills,
            enemies=g.enemies, villages=g.villages, visible_villages=g.visible_villages,
            world=g.world, ground=g.ground, now=g.now, cam_x=g.cam_x, cam_y=g.cam_y,
            zoom=ZOOM, reach=REACH, tile=TILE, eat_restore=g.EAT_RESTORE,
            inside_house=g.inside_house, compass_state=g.compass_state,
            dialogue_panel=g.dialogue_panel, confirm=g.confirm,
            truth=g._TRUTH, main_capital=_main_capital, village_plots=g.village_plots,
            fire=fire, use_axe=use_axe, use_pickaxe=use_pickaxe,
            use_first_aid=use_first_aid, try_sleep=try_sleep,
            guard_search=guard_search, open_trade=open_trade,
            commit_crime=commit_crime, pay_share=pay_share,
            tile_is_mine=tile_is_mine, near_fireplace=near_fireplace, toast=toast,
            comm=g.comm,
            confirm_open=g.confirm_open)
        g.confirm_open = combat_actions.on_click(_g)

    # -- building placement -------------------------------------------------
    def placement_pos():
        return placement.placement_pos(g.player, g.inside_house, g.inside_mine,
                                       g.cam_x, g.cam_y, g.wmouse_x, g.wmouse_y)

    def placement_box(x, y):
        return placement.placement_box(x, y, g.placing, g.fence_horizontal,
                                       g.player, BUILD_W, BUILD_H)

    def can_place(rect, sight) -> bool:
        return placement.can_place(rect, sight, g.player, g.inside_house,
                                   g.built_houses, g.visible_villages, g.trees)

    def _own_things():
        return placement.own_things(g.built_plots, g.placed_work, g.built_gates,
                                    g.built_fences, g.built_houses, g.built_blocks,
                                    g.built_chests, g.built_signs, g.built_foodboxes)

    def demolish_at(wx: float, wy: float) -> str:
        return placement.demolish_at(wx, wy, g.player, g.built_plots, g.built_gates,
                                     g.built_fences, g.built_houses, g.placed_work,
                                     mark_dirty, g.inventory, stall_mod, g.built_blocks,
                                     g.built_chests, g.built_signs, g.built_foodboxes)

    def salary_chest():
        return placement.salary_chest(g.built_houses, hubs, g.hub_world)

    def hub_stall():
        return placement.hub_stall(g.player, stall_mod)

    def near_stall():
        return nearby.near_stall(g.player)

    def _town_price_for(item, grade):
        return nearby.town_price_for(g.player, g.visible_villages, item, grade)

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
        
        g.placing = placement.commit_plot(g.placing, g.plot_start, placement_pos,
                                        toast, hubs, g.villages, g.hub_world,
                                        g.player, g.built_plots, mark_dirty,
                                        nemesis, plog)

    def try_place() -> None:
        
        _g = SimpleNamespace(
            placing=g.placing, player=g.player, inventory=g.inventory,
            built_houses=g.built_houses, built_fences=g.built_fences,
            built_gates=g.built_gates, placed_work=g.placed_work,
            built_chests=g.built_chests, built_signs=g.built_signs,
            built_foodboxes=g.built_foodboxes, built_blocks=g.built_blocks,
            hub_world=g.hub_world, villages=g.villages, inside_house=g.inside_house,
            cam_x=g.cam_x, cam_y=g.cam_y, zoom=ZOOM, test_mode=g.test_mode,
            build_cost=build_cost, build_materials=build_materials,
            build_w=BUILD_W, build_h=BUILD_H, build_house_cost=BUILD_COST,
            can_place=can_place, demolish_at=demolish_at,
            placement_pos=placement_pos, placement_box=placement_box,
            mark_dirty=mark_dirty, toast=toast)
        g.placing = placement.try_place(_g)

    def draw_placing() -> None:
        _g = SimpleNamespace(
            placing=g.placing, player=g.player, cam_x=g.cam_x, cam_y=g.cam_y,
            vw=g.vw, vh=g.vh, wmouse_x=g.wmouse_x, wmouse_y=g.wmouse_y, screen=g.screen,
            font=g.font, villages=g.villages, hub_world=g.hub_world, plot_start=g.plot_start,
            can_place=can_place, placement_pos=placement_pos,
            placement_box=placement_box)
        placement.draw_placing(_g)

    def draw_field_design() -> None:
        """While designating: the rectangle being dragged, every field with
        its crop symbol and every orchard with a tree symbol, over the world."""
        if not g.field_design:
            return
        for fd in g.field_designations:
            _r = fd["rect"]
            _is_orchard = fd.get("type") == "orchard"
            _sr = pygame.Rect(int(_r.x - g.cam_x), int(_r.y - g.cam_y), _r.w, _r.h)
            _glow = pygame.Surface((max(1, _sr.w), max(1, _sr.h)), pygame.SRCALPHA)
            _glow.fill((96, 150, 70, 70) if _is_orchard else (120, 160, 80, 70))
            g.screen.blit(_glow, _sr.topleft)
            pygame.draw.rect(g.screen, (120, 180, 88) if _is_orchard else (140, 190, 90), _sr, 2)
            try:
                _cx = int(_r.centerx - g.cam_x)
                _cy = int(_r.centery - g.cam_y)
                if _is_orchard:
                    # A TREE marks an orchard -- no crop choice to cycle.
                    _sz = min(30, max(16, _r.w, _r.h))
                    pygame.draw.circle(g.screen, (245, 244, 232), (_cx, _cy), int(_sz * 0.62))
                    pygame.draw.circle(g.screen, (120, 118, 108), (_cx, _cy), int(_sz * 0.62), 2)
                    pygame.draw.line(g.screen, (120, 84, 50),
                                     (_cx, _cy + int(_sz * 0.18)), (_cx, _cy + int(_sz * 0.55)), 3)
                    pygame.draw.circle(g.screen, (40, 84, 44), (_cx, _cy), int(_sz * 0.42))
                    pygame.draw.circle(g.screen, (56, 108, 54), (_cx, _cy), int(_sz * 0.42), 2)
                else:
                    _sym = crop.FIELD_SYMBOL.get(fd["kind"])
                    if _sym is not None:
                        _sz = min(32, max(16, _r.w, _r.h))
                        _ic = items.icon(_sym, _sz)
                        pygame.draw.circle(g.screen, (245, 244, 232),
                                           (_cx, _cy), int(_sz * 0.62))
                        pygame.draw.circle(g.screen, (120, 118, 108),
                                           (_cx, _cy), int(_sz * 0.62), 2)
                        g.screen.blit(_ic, _ic.get_rect(center=(_cx, _cy)))
            except Exception:
                pass
        if g.field_start[0] is not None:
            _sx, _sy = g.field_start[0]
            _ex = g.cam_x + g.wmouse_x
            _ey = g.cam_y + g.wmouse_y
            _r = pygame.Rect(int(min(_sx, _ex)), int(min(_sy, _ey)),
                             int(abs(_ex - _sx)), int(abs(_ey - _sy)))
            _sr = pygame.Rect(int(_r.x - g.cam_x), int(_r.y - g.cam_y), _r.w, _r.h)
            _glow = pygame.Surface((max(1, _sr.w), max(1, _sr.h)), pygame.SRCALPHA)
            if g.field_del[0]:
                _glow.fill((220, 90, 70, 80))
                pygame.draw.rect(g.screen, (240, 120, 90), _sr, 2)
            else:
                _glow.fill((200, 220, 120, 80))
                pygame.draw.rect(g.screen, (230, 240, 160), _sr, 2)
            g.screen.blit(_glow, _sr.topleft)

    def render_backdrop(house):
        return houseroom.render_backdrop(house, pygame, g.vw, g.vh, g.ground,
                                         g.static_layer, g.trees, g.villages,
                                         g.built_houses)

    g._HouseBar = houseroom._HouseBar

    def enter_house(house) -> None:
        
        _r = houseroom.enter_house(house, g.player, plog, g.combat, g.vw, g.vh,
                                   night_factor, pygame, random, toast)
        if _r[0] is not None:
            g.inside_house, g.door_cooldown, g.cam_x, g.cam_y = _r

    def exit_house() -> None:
        
        g.inside_house, g.door_cooldown = houseroom.exit_house(
            g.inside_house, g.player, night_factor, plog)

    g._draws: dict = {}

    def draw_exterior(cx, cy, show_names: bool = False, target=None) -> None:
        _g = SimpleNamespace(
            screen=g.screen, static_layer=g.static_layer, blood=g.blood,
            villages=g.villages, hub_world=g.hub_world, trees=g.trees, vw=g.vw, vh=g.vh,
            pygame=pygame, fence=fence, built_fences=g.built_fences,
            camp_walls=g.camp_walls, built_gates=g.built_gates, player=g.player,
            _TEST_TRAIN=g._TEST_TRAIN, corpse_mod=corpse_mod, now=g.now, crop=crop,
            world=g.world, wildcrop=wildcrop, ore_field=g.ore_field,
            enemies=g.enemies, rabbits=g.rabbits, horses=g.horses, built_houses=g.built_houses,
            _TRUTH=g._TRUTH, _draws=g._draws, plog=plog,
            inventory=g.inventory, built_blocks=g.built_blocks,
            wmouse_x=g.wmouse_x, wmouse_y=g.wmouse_y,
            _observe_npcs=g._observe_npcs, _observe_soldiers=g._observe_soldiers,
            field_design=g.field_design, placing=g.placing)
        render.draw_exterior(_g, cx, cy, show_names, target)


    # -- THE NEWS, AS A MAN HEARS IT ----------------------------------------
    g._chat: list = []          # [text, seconds of life left] -- one shown at a time
    g._news_lab = [None, None]  # the last bubble text and its rendered surface
    g._hear_at = [0.0]          # hear_news runs FOUR TIMES A SECOND, not sixty
    g._heard: set = set()       # (village, army, nation): what he already knows

    def hear_news() -> None:
        newsbubble.hear_news(g.player, g._chat, g._hear_at, g._heard, g.visible_villages,
                             g.now, nation_name)

    def tick_news(dt: float) -> None:
        newsbubble.tick_news(g._chat, dt)

    def draw_news(surf, cam_x: float, cam_y: float, w: int, h: int) -> None:
        newsbubble.draw_news(surf, cam_x, cam_y, w, h, g._chat, g.player,
                             g._news_lab, g.speech_font)

    def pay_share(item: str, gained: int) -> int:
        return nearby.pay_share(item, gained, g.player, g.inventory, toast)

    def near_board():
        return nearby.near_board(g.player, g.visible_villages, REACH)

    def near_chest() -> bool:
        return houseuse.near_chest(g.player, g.inside_house)

    def near_chest_building():
        """The nearest 1x1 chest he has built, or None."""
        for _ch in getattr(g, "built_chests", ()):
            if math.hypot(g.player.x - _ch.x, g.player.y - _ch.y) < 64.0:
                return _ch
        return None

    def animals_researched() -> bool:
        import research as _research
        return _research.state(g, "animals") == "done"

    def near_horse():
        """The nearest conquered horse he can mount, or None."""
        for _h in getattr(g, "horses", ()):
            if getattr(_h, "conquered", False) and getattr(_h, "alive", True):
                if math.hypot(g.player.x - _h.x, g.player.y - _h.y) < 48.0:
                    return _h
        return None

    def mount(horse) -> None:
        g.riding = horse
        horse.route = None              # a ridden horse forgets its route
        horse.delivering = False
        horse.returning = False
        toast("Mounted")

    def dismount() -> None:
        _h = getattr(g, "riding", None)
        if _h is not None:
            _h.x, _h.y = g.player.x, g.player.y
            _h.facing = g.player.facing
        g.riding = None
        toast("Dismounted")

    def near_sign():
        """The nearest sign-post he has built, or None."""
        for _sg in getattr(g, "built_signs", ()):
            if math.hypot(g.player.x - _sg.x, g.player.y - _sg.y) < 56.0:
                return _sg
        return None

    def near_foodbox():
        """The nearest feed box he has built, or None."""
        for _fb in getattr(g, "built_foodboxes", ()):
            if math.hypot(g.player.x - _fb.x, g.player.y - _fb.y) < 56.0:
                return _fb
        return None

    def food_box():
        """The feed box the livestock and the handler use: the nearest built."""
        boxes = getattr(g, "built_foodboxes", ()) or ()
        if not boxes:
            return None
        return min(boxes, key=lambda b: (b.x - g.player.x) ** 2 + (b.y - g.player.y) ** 2)

    def ship_pos():
        """The ship, anchored off the coast at the player's spawn."""
        import world as _world
        _sy = getattr(g, "_spawn", (0.0, 0.0))[1]
        return (_world.coast_x(_sy, g.world.seed) + 56.0, _sy)

    def open_horse(horse) -> None:
        g.horse_sel = horse
        g.horse_panel = HorsePanel(g.inventory, horse, g)
        g.horse_panel_open = True
        pygame.mouse.set_visible(True)

    def toggle_horse_escort(horse) -> None:
        """Flip the horse's Soldier escort. A soldier rides with it and fights
        anything that comes for the cargo."""
        horse.escort = not bool(getattr(horse, "escort", False))
        if horse.escort:
            # put the nearest free soldier on its back
            best = None
            bd = 1e18
            for _n in getattr(g, "_native_people", ()) or ():
                if (not getattr(_n, "alive", True)
                        or getattr(_n, "native_role", "") != "soldier"
                        or getattr(_n, "escort_horse", None) is not None):
                    continue
                _d = (_n.x - horse.x) ** 2 + (_n.y - horse.y) ** 2
                if _d < bd:
                    bd, best = _d, _n
            if best is not None:
                best.escort_horse = horse
                horse.escort_soldier = best
                toast("%s rides escort." % getattr(best, "name", "A soldier"))
            else:
                toast("No free soldier to send.")
        else:
            _s = getattr(horse, "escort_soldier", None)
            if _s is not None:
                _s.escort_horse = None
            horse.escort_soldier = None
            toast("Escort called off.")

    def open_gunsmith(npc) -> None:
        g.gunsmith_npc = npc
        g.gunsmith_panel = GunsmithPanel(npc, g)
        g.gunsmith_open = True
        pygame.mouse.set_visible(True)

    def open_smith(npc) -> None:
        g.smith_npc = npc
        g.smith_panel = SmithPanel(npc, g)
        g.smith_panel_open = True
        pygame.mouse.set_visible(True)

    def open_barracks(wp) -> None:
        g.barracks_wp = wp
        g.barracks_panel = BarracksPanel(g, wp)
        g.barracks_open = True
        pygame.mouse.set_visible(True)

    def buy_soldier() -> None:
        """Spend the armor, rifle and ammo; a soldier steps out of the barracks."""
        _wp = g.barracks_wp
        if _wp is None:
            return
        for _it, _q in BarracksPanel.COST:
            if g.inventory.count_of(_it) < _q:
                toast("Not enough materials")
                return
        for _it, _q in BarracksPanel.COST:
            g.inventory.consume(_it, _q)
        try:
            import colony as _colony
            _n = _colony.spawn_soldier(g, float(_wp.x), float(_wp.y + 50.0))
            toast("%s reports for duty." % getattr(_n, "name", "A soldier"))
        except Exception as _e:
            plog.log("BARRACKS-BUY-ERR", repr(_e)[:160])
        g.barracks_open = False
        g.barracks_panel = None
        g.barracks_wp = None
        pygame.mouse.set_visible(False)

    def open_market() -> None:
        """The ship's market: sell manufactured goods out of the hold."""
        g.market_panel = ShipMarketPanel(g, g.inventory, g.ship_hold)
        g.market_open = True
        pygame.mouse.set_visible(True)

    def send_horse() -> None:
        h = g.horse_sel
        if h is not None and getattr(h, "alive", True):
            h.delivering = True
            h.returning = False
            g.toast("%s runs to the ship." % (getattr(h, "name", "Horse") or "Horse"))
        g.horse_panel_open = False
        g.horse_panel = None
        g.horse_sel = None
        pygame.mouse.set_visible(False)

    def near_brew() -> bool:
        return houseuse.near_brew(g.player, g.inside_house)

    def mash_at_table() -> None:
        houseuse.mash_at_table(g.inventory, g.skills, toast)

    def use_barrel() -> None:
        houseuse.use_barrel(g.player, g.inside_house, g.inventory, g.skills, g.now, toast)

    def near_lab() -> bool:
        return houseuse.near_lab(g.player, g.inside_house)

    def craft_at_table() -> None:
        houseuse.craft_at_table(g.player, g.inventory, g.skills, toast)

    def near_workshop() -> bool:
        return houseuse.near_workshop(g.player, g.inside_house)

    def near_workplace():
        return nearby.near_workplace(g.player, g.placed_work, g.visible_villages)

    def work_action(key: str) -> str:
        import research as _research
        _iw = _research.state(g, "ironworking") == "done"
        g.work_cd, _msg = houseuse.work_action(key, g.smith_shop, g.player, g.now,
                                             economy, g.inventory, g.skills, random,
                                             pay_share, quality, ironworking=_iw)
        return _msg

    def near_fireplace() -> bool:
        return hudtime.near_fireplace(g.player, g.inside_house)

    def join_army(npc) -> None:
        interact.join_army(npc, g.player, toast, nation_name, economy, g.inventory,
                           g.armies)

    def leave_army() -> None:
        interact.leave_army(g.player, toast)

    def player_hidden_in_village() -> bool:
        return interact.player_hidden_in_village(g.player, g.visible_villages, math)

    # One index of the fight, rebuilt once a frame. A fighter only ever
    # considers what is within reach of it, so the cost is linear in the
    # number of men instead of men-squared.
    g.ENGAGE_REACH = 1200.0
    g.LOOK_REACH = 1000.0
    g.enemy_grid = TeamGrid(200.0)
    g.folk_grid = TeamGrid(260.0)
    # (A SECOND GRID STOOD HERE, FOR A QUESTION NOBODY ASKS ANY MORE. It held
    # only soldiers, because a villager looking for "a soldier of another
    # nation" threw the wolves away -- and with one nation in the world the
    # answer was always nobody. See nearest_hostile.)

    g._Watcher = playerutil.Watcher

    g.watcher = g._Watcher(g.player)

    def choose_target(creature, villages):
        who = g.watcher if g.test_mode else g.player
        return worldbuild.choose_target(creature, villages, who, g.enemy_grid,
                                        g.ENGAGE_REACH, g.folk_grid, g.LOOK_REACH,
                                        g.rabbits, g.player.squad)

    def day_phase() -> str:
        return hudtime.day_phase(g.now, DAY_LENGTH)

    def _nearest_town():
        return interact.nearest_town(g.player, g.villages, WORLD_BORDER)

    def speed_button() -> pygame.Rect:
        return hudtime.speed_button(g.vw, g.vh)

    def draw_speed_button() -> None:
        hudtime.draw_speed_button(g.screen, g.font, g.test_mode, g.time_scale, g.vw, g.vh)

    def night_factor(t=None) -> float:
        return hudtime.night_factor(g.now, DAY_LENGTH, t)

    def next_morning(t: float) -> float:
        return hudtime.next_morning(t, g.now, DAY_LENGTH)

    def try_sleep() -> None:
        
        g.sleep_timer = life.try_sleep(g.inside_house, g.player, math, REACH, toast,
                                     night_factor, SLEEP_TIME, pygame)

    def draw_night() -> None:
        # EVERY FIREPLACE IS A LIGHT: pass its on-screen position so the night
        # shade is cut open around it.
        _lights = [(wp.x - g.cam_x, wp.y - g.cam_y)
                   for wp in getattr(g, "placed_work", ())
                   if getattr(wp, "kind", "") == "fireplace"]
        life.draw_night(night_factor, g.vision, g.interior_vision, g.shade_cache,
                        g.vw, g.vh, g.screen, draw_status, _lights)

    def draw_status() -> None:
        hudtime.draw_status(g.screen, g.font, g.hud_status, g.vw)

    def tick_conquest(dt) -> None:
        hudtime.tick_conquest(g.active_chaos, g.player, toast, dt)

    def update_hud() -> None:
        
        g.hud_status = life.update_hud(g.active_chaos, g.visible_villages, math)

    def draw_hunger_gray() -> None:
        hudtime.draw_hunger_gray(g.screen, g.player)

    def mark_dirty() -> None:
        """The world changed: save it SOON, not this instant.

        Mining an iron seam wrote the entire four-and-a-half megabyte world to
        disk on the frame the ore came loose -- which is why the last strike
        always hitched. The write is the same; it just happens a second or two
        later, with the swing already over.
        """
        
        g.save_dirty = True
        g.save_timer = min(g.save_timer, 2.0)

    def save_now() -> None:
        _g = SimpleNamespace(
            built_houses=g.built_houses, villages=g.villages, player=g.player,
            inventory=g.inventory, panel=g.panel, skills=g.skills, now=g.now, kills=g.kills,
            world=g.world, compass_state=g.compass_state, ore_field=g.ore_field,
            trees=g.trees, built_fences=g.built_fences, built_gates=g.built_gates,
            built_plots=g.built_plots, placed_work=g.placed_work, hub_world=g.hub_world,
            train=g._TEST_TRAIN, inside_house=g.inside_house)
        savegame.write(_g)

    def load_now() -> None:
        
        _g = SimpleNamespace(
            villages=g.villages, player=g.player, inventory=g.inventory, panel=g.panel,
            enemies=g.enemies, built_houses=g.built_houses, built_fences=g.built_fences,
            built_gates=g.built_gates, built_plots=g.built_plots, placed_work=g.placed_work,
            hub_world=g.hub_world, train=g._TEST_TRAIN, camp_walls=g.camp_walls,
            width=WIDTH, height=HEIGHT, zoom=ZOOM, now=g.now, kills=g.kills,
            world=g.world, observer_=g.observer_, active_chaos=g.active_chaos,
            compass_state=g.compass_state, ore_field=g.ore_field,
            ground=g.ground, cam_x=g.cam_x, cam_y=g.cam_y, skills=g.skills, trees=g.trees)
        savegame.restore(_g)
        g.now, g.kills = _g.now, _g.kills
        g.cam_x, g.cam_y = _g.cam_x, _g.cam_y

    # -- first frame --------------------------------------------------------
    g.font = pygame.font.SysFont("dejavusans", 18)
    # The news box: small, quiet, and out of the way of the world it is
    # describing.
    # Drawn INSIDE the zoomed world frame, so it is deliberately small here:
    # the frame is scaled by ZOOM on the way to the screen.
    g.speech_font = pygame.font.SysFont("dejavusans", 10)
    g.screen.fill((18, 24, 18))
    g.screen.blit(g.font.render("Growing the world...", True, (120, 150, 110)), (24, 22))
    pygame.display.flip()
    g.ground.ensure_visible(g.cam_x, g.cam_y, *g.screen.get_size())
    # Warm the neighbourhood while the loading screen is up, so the first real
    # frame does not freeze generating villages and their house sprites.
    g.villages.visible(g.cam_x - 500.0, g.cam_y - 500.0,
                     g.screen.get_width() + 1000, g.screen.get_height() + 1000)
    g.trees.visible(g.cam_x, g.cam_y, *g.screen.get_size())

    g.visible_villages: list = []
    g.world_accum = 0.0
    g.sleep_timer = 0.0
    g.save_timer = 20.0
    g.save_dirty = False
    g.settle_timer = 8.0        # how often a nation looks to its own vacancies
    g.house_timer = 1.0         # how often a household shares its larder
    g.demand_timer = 20.0       # how often the crown asks after its own war
    g.DESERT_PX = 2400.0          # how far a soldier may stray from the column
    g.DESERT_SECONDS = 180.0      # ...and for how long, before it is desertion
    g.player._away = 0.0
    g.player.settled_at = None
    g.player.job = None
    load_now()
    # THE COAST IS WHERE HE WAKES, whatever the save says. Re-applied AFTER
    # the load, because the save's old position is the last word otherwise and
    # drags him back inland, away from the ship and the ocean.
    import world as _world
    g.player.x = g._spawn[0]
    g.player.y = g._spawn[1]
    # FACE THE SEA: the ship is offshore to the east, and the vision cone must
    # look at it or the whole ocean -- ship included -- sits in the dark.
    g.player.facing = (1.0, 0.0)
    g.cam_x = g.player.x - WIDTH / (2.0 * ZOOM)
    g.cam_y = g.player.y - HEIGHT / (2.0 * ZOOM)
    # Rebuild the ground under him NOW and force the static layer to recompose,
    # so the ocean, sand and ship are actually on screen from the first frame.
    try:
        g.ground.refresh_around(g.player.x, g.player.y, WIDTH, HEIGHT)
    except Exception:
        pass
    # AN AXE IN HIS HAND, ONCE THE SAVE HAS HAD ITS SAY. The starting kit is
    # added before the save is read -- so a restored pack overwrote it and a
    # man who loaded a game had no axe at all. Anyone with nothing to cut with
    # gets one; a man who already has a tool keeps his own.
    if (g.inventory.count_of("axe") <= 0
            and g.inventory.count_of("pickaxe") <= 0):
        g.inventory.add("axe", 1)
        mark_dirty()

    # ...AND THE WORLD IS A THOUSAND PEOPLE AFTER THE LOAD, TOO. The save is
    # laid over the rosters and can only make them smaller; this is the one
    # place that says how big the country is, whatever a file remembers.
    try:
        g._pop2 = worldbuild.set_world_population(g.villages)
        plog.log("WORLD", "population after the load:", g._pop2)
    except Exception as _pe:
        plog.log("WORLD-ERROR", repr(_pe)[:200])

    # THE NATIVE SETTLEMENTS: the home camp three hundred blocks inland, plus
    # every lattice cell within the simulated distance, each a ring of teepees
    # and fields around a fire. Built AFTER the population pass.
    g.native_settlements = {}
    g.native_settlement = None
    try:
        import native as _native
        import world as _w
        _nseed = (int(g.world.seed) ^ 0x7E7E) & 0xFFFFFFFF
        _ns_x = _w.coast_x(g.player.y, g.world.seed) - 300 * 32.0
        _home = _native.build(g, _ns_x, g.player.y, _nseed)
        _home.cell = None
        g.native_settlements["home"] = _home
        g.native_settlement = _home
        _made = _native.ensure_near(g, g.player.x, g.player.y, _native.NATIVE_RADIUS)
        _native.spawn_starter_camps(g)
        plog.log("NATIVE", "home at %.0f,%.0f + %d native settlements"
                 % (_home.x, _home.y, len(_made)))
    except Exception as _ne:
        plog.log("NATIVE-ERROR", repr(_ne)[:200])

    # THE PLAYER'S OWN SETTLEMENT: a camp and three conquered farmers beside
    # him, ready to work whatever fields he designates.
    try:
        import colony as _colony
        g.player_camp = _colony.make_camp(g)
        g.sync_player_camp = _colony.sync_camp
        g.next_field_kind = _colony.next_kind
        g.first_field_kind = _colony.first_kind
        g.conquer_camp = _colony.conquer_camp
        g.sync_jobs = _colony.sync_jobs
        # NO PEOPLE ARE HANDED TO THE PLAYER AT SPAWN. A conquered workforce
        # is WON: clear a native settlement's warriors and its farmers are his.
        plog.log("COLONY", "camp ready, empty")
    except Exception as _ce:
        plog.log("COLONY-ERROR", repr(_ce)[:200])

    # ONE COTTON PLANT, RIGHT BESIDE THE SPAWN, full grown so it can be seen
    # and picked the moment he opens his eyes. A WILD plant, like wild tobacco.
    try:
        _ctx = int((g.player.x - 4 * 32.0) // TILE)
        _cty = int(g.player.y // TILE)
        g.world.wild_forced[(_ctx, _cty)] = ("cotton", 3)
    except Exception as _e:
        plog.log("COTTON-SPAWN", repr(_e)[:120])

    # THE MAN WHO ANSWERS QUESTIONS IS NOT A CASUALTY OF A SAVE LOAD.
    # `load_now` rebuilds every town's roll up to its capacity, and he is the
    # LAST man appended to his town -- so the cap dropped him, and he survived
    # only as a handle: clickable, but off the roster and therefore not drawn.
    # He is put back, with the room to hold him.
    if g._truth is not None:
        g._home_town = getattr(g._truth, "village", None)
        if g._home_town is not None:
            if g._truth not in g._home_town.npcs:
                g._home_town.npcs.append(g._truth)
            g._home_town.capacity = max(int(getattr(g._home_town, "capacity", 0)),
                                      len(g._home_town.npcs))
        if g._truth not in village_mod.PEOPLE:
            village_mod.PEOPLE.append(g._truth)
        g._TRUTH[0] = g._truth

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
    g._retraded = 0
    try:
        for _v in g.villages.villages:
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
                    g._retraded += 1
        if g._retraded:
            plog.log("TRADES", "made idle in settlements:", g._retraded,
                     "(no lab or brewhouse by law)")
    except Exception as _te:
        plog.log("TRADES-ERROR", repr(_te)[:200])

    try:
        g._ta, g._ha = nemesis.plant(g.villages, g.hub_world, g.world.seed)
        nemesis.seed_chief(g.villages, g.player, g.world.seed)
        nemesis.issue()          # secret news: who is told what, and nobody else
        nemesis.set_places(g.villages, g.hub_world)   # for naming where a crime was
        plog.log("SERVICE", nemesis.summary(g.villages, g.hub_world),
                 "| planted", g._ta, "town /", g._ha, "hub")
        plog.log("SERVICE", nemesis.secret_summary())
    except Exception as _se:
        plog.log("SERVICE-ERROR", repr(_se)[:200])

    # ---- WHAT THE LANES SAW ----------------------------------------------
    # A lane notices an offence and sends the offender's id, the verb, the
    # goods, where he stood and which of its agents were close enough to watch.
    # The facts live HERE, in one process, so there is one answer to "who
    # knows what" -- and no lane can invent a fact or forget one.
    g._BY_ID: dict = {}
    try:
        for _v in g.villages.villages:
            for _n in _v.npcs:
                g._BY_ID[str(getattr(_n, "id", ""))] = _n
        for _h in g.hub_world.hubs:
            for _n in _h.npcs:
                g._BY_ID[str(getattr(_n, "id", ""))] = _n
        for _c in getattr(g.hub_world, "_caravans", ()):
            g._BY_ID[str(getattr(_c.npc, "id", ""))] = _c.npc
    except Exception:
        pass

    def _on_offences(events) -> None:
        playerutil.on_offences(events, g._BY_ID, nemesis)

    # (the sink is attached once the lanes exist -- see below)

    if os.environ.get("KP_AUTO_RAID"):        # headless raid self-test hook
        g._cand = g.villages.visible(g.player.x - 4000.0, g.player.y - 4000.0, 8000, 8000)
        if len(g._cand) >= 2:
            g._home = g._cand[0]
            join_army(g._home.commander)
            g._foe = next((w for w in g._cand if w.nation != g._home.nation), None)
            if g._foe is not None:
                g.player.x = g._foe.x + g._foe.radius - 120.0
                g.player.y = g._foe.y
                g.cam_x = g.player.x - WIDTH / (2.0 * ZOOM)
                g.cam_y = g.player.y - HEIGHT / 2.0
                for _i, _s in enumerate(g.player.squad):
                    _s.x = g.player.x + 40.0 * (_i - 1)
                    _s.y = g.player.y + 60.0
                print("AUTO-RAID: joined %s, attacking %s" % (g._home.name, g._foe.name))
    # ---- PHASE TIMERS: where does the frame actually GO? ------------------
    # py-spy cannot see inside the compiled Cython, so the split of a frame has
    # to be measured rather than sampled. Three windows: the TOWNS (the village
    # loop), the MEN (the NPC loop), and everything between and after them --
    # houses, settling, the draw. This is a measurement, not a feature.
    g._PH = {"v": 0.0, "m": 0.0, "n": 0.0, "f": 0, "t": time.time()}
    g._IVIS = [None, None]        # the room's light mask, and what it was made for
    g._HF = [0, time.perf_counter()]      # indoor frame counter, for the log
    g.prison_cd = 0.0                     # the barn's doorway, just after leaving
    g._watched_last = None      # the man being watched, so a change can rebuild

    # ---- THE LANES: the world cut so more than one core can hold it -------
    #
    # The cut is real and it is AUDITED every time it is remade: every town and
    # every man in exactly one lane. What is not here yet is the processes --
    # every lane is still stepped in this process -- so the behaviour today is
    # exactly what it was, and the split lands on top of a cut that is already
    # proved. If the audit ever fails the frame falls back to stepping the
    # whole world, because a lane that has lost a man is worse than no lanes.
    g._LANES = lanes.Partition(1)
    g._town_acc = {}            # accumulated time per town, for its books
    g._LANE_TOWNS = list(g.villages.villages)
    g._LANE_PEOPLE = list(village_mod.PEOPLE)
    g._lane_timer = 0.0
    g._lane_warned = False
    # THE GATE SEARCH, bound before the loop: the frame reads these.
    g.gate_search_t = 0.0
    g.gate_search_v = None
    g._hb = 0.0
    g._blk = 0.0
    g._stuck = 0.0
    # ---- THE PLAYER TRACE -------------------------------------------------
    # The last ninety frames, every number that could stop him moving. It is
    # held in memory and written ONLY when something is wrong, so it costs
    # nothing and cannot itself be the reason for a hitch.
    from collections import deque as _deque
    g._trace = _deque(maxlen=90)
    g._still = 0
    g._lastpt = [None]
    g._branch = "?"

    def _inside_h():
        return playerutil.inside_h(g.inside_house)

    def _dump_trace(why):
        playerutil.dump_trace(why, g._trace, plog)

    def close_modals(why="") -> None:
        """SHUT EVERY PANEL. THE WORLD IS NEVER HELD HOSTAGE BY A MENU.

        Each of these flags skips the whole world update while it is set, so a
        menu that fails to close -- or a click that opens one the player never
        notices -- freezes him solid while the HUD keeps drawing. There must
        always be a way out, and this is it.
        """
        
        
        
        
        g.inventory_open = g.trade_open = g.board_open = g.chest_open = False
        g.sign_open = False
        g.gunsmith_open = False
        g.smith_panel_open = False
        g.barracks_open = False
        g.horse_panel_open = False
        g.worker_panel_open = False
        g.stall_open = False
        g.body_open = False
        g.folder_open = False
        g.smith_open = g.workshop_open = g.confirm_open = g.map_open = False
        g.pause_open = g.build_menu_open = False
        g.placing = None
        try:
            pygame.mouse.set_visible(False)
        except Exception:
            pass
        if why:
            toast(why)

    g.running = True
    # THE WINDOW IS NEVER A FROZEN PICTURE WITH NOTHING ON IT. The first
    # second of the world does its one-time work INSIDE the loop -- indexing
    # every wall and trunk in view, standing the town up, cutting the lanes --
    # and that is by far the heaviest thing the game ever does. The bar is
    # drawn at the TOP of the frame, so it is what is on screen while that
    # work happens rather than a still image and no explanation.
    def draw_boot(surface, title: str, prog: float) -> None:
        render.draw_boot(surface, title, prog, pygame)

    g._boot_title = "WELCOME TO %s" % (g._origin_town.name.upper() if g._origin_town is not None else "THE WORLD")
    g._boot_left = [10]
    g._boot_slow = [True]
    g._boot_prev = [None]
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
    if g._origin_town is not None:
        g.player.settled_at = g._origin_town
        g.player.village = g._origin_town
        if getattr(g._origin_town, "nation", None) is not None:
            g.player.nation = g._origin_town.nation
        if g.origin in g._JOB:
            g.player.job = g._JOB[g.origin]
    # EVERY GATE IS GUARDED FROM THE FIRST DAY, not only the ones the player
    # happens to walk past. The guards used to be raised for towns in the
    # player's lane -- so a caravan arriving anywhere else in the world found an
    # EMPTY gate, was waved through by `search_visitor`, and sold its load
    # without ever being looked at. Measured in a live day: 132 purchases, 13
    # loads, 2 sales, and ZERO searches. A wall with nobody on the gate is not a
    # border.
    try:
        for _v in g.villages.villages:
            if getattr(_v, "is_hub", False) or getattr(_v, "patrol", None):
                continue
            _v.patrol = make_village_patrol(_v, 4)
            g.enemies.extend(_v.patrol)
            _v.patrol_timer = 30.0
        print("gate guards raised for %d settlements" % len(g.villages.villages))
    except Exception as _ge:
        print("gate guard pass failed: %r" % (_ge,))

    # ---- THE LANES: THE FRAME, THE HUBS, THE SETTLEMENTS -----------------
    # Two forked processes (see workers.py): process 1 owns the hubs, their
    # people and the free traders; process 2 owns the settlements, their books
    # and their people. THIS process keeps the player, the soldiers, the
    # bullets, the terrain and every pixel. Falls back to stepping everything
    # here if the fork cannot be made.
    g._WORK = workers.start(g.world, g.villages, g.hub_world, g.player)
    g._W_ON = g._WORK.ok()
    # WHAT THE LANES SAW, and how often agents pass it on.
    g._posted: dict = {}
    g._walk_log: dict = {}
    g._WORK.offence_sink = _on_offences
    g._WORK.stall_sink = _on_stall_sales

    # A SEARCH THAT FOUND SOMETHING: the agents of THAT settlement know.
    g._SETTLE_TOWNS = [v for v in g.villages.villages
                     if not getattr(v, "is_hub", False)]

    def _on_caught(events) -> None:
        playerutil.on_caught(events, g._BY_ID, g._SETTLE_TOWNS, nemesis)

    g._WORK.caught_sink = _on_caught
    g._tell_timer = 0.0

    class _BoardAPI:
        def __init__(self):
            self._api = boardapi.BoardAPI(g.player, g.inventory, g._WORK)
        def hire(self, town, kind, cb) -> None:
            self._api.hire(town, kind, cb)
        def sell(self, town, offers, cb) -> None:
            self._api.sell(town, offers, cb)

    g._BOARD_API = _BoardAPI()

    # ---- THE HANG WATCHDOG ------------------------------------------------
    # A freeze leaves no traceback: the process is alive and nothing is
    # written. This thread watches a heartbeat the frame sets, and when the
    # frame has not moved for six seconds it dumps EVERY thread's stack into
    # saves/hang.log -- so a freeze names its own line instead of costing an
    # evening of guessing.
    g._HEART = [time.time()]

    def _watchdog() -> None:
        import faulthandler
        playerutil.watchdog(g._HEART, persist, os, time, faulthandler)

    try:
        threading.Thread(target=_watchdog, daemon=True).start()
    except Exception:
        pass

    # bind the wrappers onto g so the loop can call them
    g._BoardAPI = _BoardAPI
    g._commit_plot = _commit_plot
    g._csay = _csay
    g._dump_trace = _dump_trace
    g._inside_h = _inside_h
    g._loot = _loot
    g._main_capital = _main_capital
    g._meet_army = _meet_army
    g._nearest_town = _nearest_town
    g._on_caught = _on_caught
    g._on_offences = _on_offences
    g._on_stall_sales = _on_stall_sales
    g._own_things = _own_things
    g._see_murder = _see_murder
    g._town_price_for = _town_price_for
    g._watchdog = _watchdog
    g.award_levels = award_levels
    g.banish = banish
    g.can_place = can_place
    g.choose_target = choose_target
    g.clamp_world = clamp_world
    g.click_a_man = click_a_man
    g.close_modals = close_modals
    g.commit_crime = commit_crime
    g.craft_at_table = craft_at_table
    g.day_phase = day_phase
    g.demolish_at = demolish_at
    g.draw_boot = draw_boot
    g.draw_exterior = draw_exterior
    g.draw_hunger_gray = draw_hunger_gray
    g.draw_news = draw_news
    g.draw_night = draw_night
    g.draw_placing = draw_placing
    g.draw_field_design = draw_field_design
    g.draw_speed_button = draw_speed_button
    g.draw_status = draw_status
    g.enter_house = enter_house
    g.exit_house = exit_house
    g.fire = fire
    g.guard_search = guard_search
    g.hear_news = hear_news
    g.hub_stall = hub_stall
    g.join_army = join_army
    g.leave_army = leave_army
    g.load_now = load_now
    g.make_tradeable = make_tradeable
    g.make_village_patrol = make_village_patrol
    g.mark_dirty = mark_dirty
    g.mash_at_table = mash_at_table
    g.near_board = near_board
    g.near_brew = near_brew
    g.near_chest = near_chest
    g.near_chest_building = near_chest_building
    g.animals_researched = animals_researched
    g.near_horse = near_horse
    g.mount = mount
    g.dismount = dismount
    g.near_sign = near_sign
    g.near_foodbox = near_foodbox
    g.food_box = food_box
    g.ship_pos = ship_pos
    g.open_horse = open_horse
    g.toggle_horse_escort = toggle_horse_escort
    g.open_gunsmith = open_gunsmith
    g.open_smith = open_smith
    g.open_barracks = open_barracks
    g.buy_soldier = buy_soldier
    g.open_market = open_market
    g.send_horse = send_horse
    g.near_fireplace = near_fireplace
    g.near_lab = near_lab
    g.near_stall = near_stall
    g.near_workplace = near_workplace
    g.near_workshop = near_workshop
    g.nearest_hostile = nearest_hostile
    g.next_morning = next_morning
    g.night_factor = night_factor
    g.on_click = on_click
    g.open_trade = open_trade
    g.open_trade_menu = open_trade_menu
    g.origin_village = origin_village
    g.pay_share = pay_share
    g.placement_box = placement_box
    g.placement_pos = placement_pos
    g.player_hidden_in_village = player_hidden_in_village
    g.player_hunted = player_hunted
    g.render_backdrop = render_backdrop
    g.respawn = respawn
    g.salary_chest = salary_chest
    g.save_now = save_now
    g.settle_reload = settle_reload
    g.spawn_patrol = spawn_patrol
    g.spawn_rabbit = spawn_rabbit
    g.spawn_horse = spawn_horse
    g.spawn_wolf = spawn_wolf
    g.spawn_bison = spawn_bison
    g.speed_button = speed_button
    g.tick_conquest = tick_conquest
    g.tick_news = tick_news
    g.tile_is_mine = tile_is_mine
    g.toast = toast
    g.try_place = try_place
    g.try_sleep = try_sleep
    g.try_talk = try_talk
    g.update_hud = update_hud
    g.use_axe = use_axe
    g.use_barrel = use_barrel
    g.use_first_aid = use_first_aid
    g.use_pickaxe = use_pickaxe
    g.work_action = work_action
    engine.run(g)

    g._WORK.stop()
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
