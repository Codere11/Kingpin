"""Villages and friendly villagers.

Houses are big, cannot be walked through, block line of sight, and many have a
small tobacco plot in the backyard. Villages sit on a deterministic lattice so
one is always a short walk away.

Each house stores two world rectangles:
    rect        the walls (movement collision)
    sight_rect  walls plus roof overhang (what blocks vision)
"""

from __future__ import annotations

import colorsys
import functools
import math
import random

from typing import Any


import pygame

import fence
import crop
import biomes
import economy
import guns
import industry
import interior
import nations
import skills
import wildcrop
import physics
import steering
from combat import friendly_in_line
from world import TILE

SPACING = 55000.0                    # world distance between village cells.
                                     # 38k gave 64 cells; 55k gives 36, so
                                     # the same ~1,000 people live in villages
                                     # twice the size -- big enough to run the
                                     # industry the constants assume.
# DOUBLED. The villages are the same size as they ever were; the country
# between them is twice as wide, so the same 36 towns are spread over four
# times the ground. Nothing per-frame changes: only the villages inside a
# bubble are ever simulated or drawn, and there are now FEWER of those at once.
VILLAGE_SCALE = 6.0                  # houses / people / footprint per village

# ---- ONE THOUSAND PEOPLE IN THE WORLD, AND NOT TWO THOUSAND ----
#
# The world is a THOUSAND people. The spec in Village.__init__ is texture --
# which house is crowded and which is not -- but the TOTAL is the size of the
# world, and it was building 2,084 of them and throwing half away after the
# loading screen. Two thousand men were named, housed, given wear and a place
# in the register, and the cache carried every one of them.
#
# IT IS SET BY THE HOUSES, because a house is what a man sleeps in. 665 houses
# across the world at 1.51 a house is a thousand people, and a town's share is
# its own houses -- the capital is already the biggest town on the map (57
# houses against 20) and does not need a second thumb on the scale.
PEOPLE_PER_HOUSE = 1.55
GOV_W, GOV_H = 240, 220              # the Government: twice a good house
RADIUS_BASE = 430.0 * VILLAGE_SCALE  # the ground a village owns


def village_radius(gx: int, gy: int, spacing: float = SPACING) -> float:
    """The ground a village owns.

    A capital is NOT a special kind of place -- it is a village with a bigger
    number. Every system that needs to know how far a village reaches calls
    this, so there is one rule rather than a capital-shaped version of it in
    each file. (There was, briefly, and the trees grew through the walls.)
    """
    return RADIUS_BASE * (2.0 if nations.is_capital_cell(gx, gy, spacing) else 1.0)
EAVE = 14                            # roof overhang around a house footprint
ROOFS = [(150, 76, 58), (122, 98, 74), (98, 106, 122), (156, 116, 74),
         (128, 78, 84), (104, 92, 70)]

WALL = (228, 212, 184)
WALL_DARK = (150, 128, 100)
STONE = (176, 168, 152)
STONE_DARK = (118, 112, 98)

PLAYER_ID = "player"             # the name a village knows the player by

# AND THE MAN HIMSELF, once main has made him. A town could always NAME the
# player (PLAYER_ID) but had no way to hand him a purse, a ballot or a ring --
# so he could be a criminal, a customer or a soldier in its books and could
# never be a candidate. Set once, at load, and never again.
PLAYER = None
# HOW LONG A MAN HOLDS IT AGAINST YOU. News with no date on it is a grudge
# that outlives the crime: the world stayed angry for ever and a player who
# survived had nothing to survive TOWARDS. Everyone forgets thirty days after
# they were told, so disappearing until the story dies is a real way out.
FORGET_AFTER = 30.0 * 600.0      # a man forgets what he was told after this
# THE STORY'S OWN AGE, which is a different thing. A man can be told again and
# forget again for ever, so a relay of fresh listeners could keep a rumour
# alive for ever -- and "hide until they forget" would never actually pay off.
# The story itself dies fifty days after the crime, however many times it has
# been retold; a NEW crime re-dates it.
STORY_LIFETIME = 50.0 * 600.0
STORY_BORN: dict = {}            # murderer -> when the crime itself happened


def self_defence(victim) -> bool:
    """True when a death is a fight rather than a murder.

    A man who was already coming for you, and lost, is not a murder -- his
    neighbours know he swung first. BUT ONLY ONCE THE WORLD ALREADY KNOWS WHAT
    YOU ARE. Without that second half the exemption swallows the first killing
    whole: a village provoked for any other reason at all -- a theft from its
    fields, an army at its gate, a man the player wronged an hour ago -- has
    every armed villager aggro the moment he walks in, so no story would ever
    be born and no witness would ever be marked.
    """
    if not victim.aggro:
        return False
    if victim.village is None:
        return False
    return PLAYER_ID in STORY_BORN


def story_cold(name, now: float) -> bool:
    """True once the story is too old for anyone to believe or repeat."""
    born = STORY_BORN.get(name)
    return born is not None and now - born >= STORY_LIFETIME
NPC_SPACING = 22.0                   # personal space villagers keep between them
LOGGERS_PER_VILLAGE = 2    # hands in the woods (see the quota in offer_post)
WORLD_POP_CAP = 1000       # HARD CAP on living people in the whole world
TRADERS_PER_VILLAGE = 3    # caravans a village keeps on the road
_FOREST = None             # set once by main, so villages can find their woods
_TRADE_GRID = None         # allocated once, rebuilt per village per step
LOG_CHOP_SECONDS = 3.0    # how long a logger takes to drop one tree
BIRTH_BOND = 18.0                    # seconds of evening friendship before a child
PEACE_DELAY = 30.0                   # no children until this long after a death

FIRST_NAMES = [
    "Cletus", "Cooter", "Earl", "Earlene", "Merle", "Darlene", "Waylon",
    "Loretta", "Clyde", "Bessie", "Otis", "Verna", "Rufus", "Maybelle",
    "Jethro", "Hank", "Sue Ellen", "Bubba", "Josiah", "Wyatt", "Chester",
    "Orville", "Wilbur", "Tammy", "Junior", "Lurlene", "Hollis", "Pearl",
    "Grover", "Minnie", "Elwood", "Clovis", "Faye", "Boyd", "Nadine",
    "Ray", "Delma", "Homer", "Opal", "Curtis", "Bonnie", "Dewey",
]
LAST_NAMES = [
    "Tucker", "Boone", "Callahan", "Sizemore", "Pruitt", "Lassiter",
    "Barlow", "Crowder", "Mercer", "Hollis", "Dalton", "Vance",
    "Whitaker", "Riggins", "Sparrow", "Beaumont", "Kincaid", "Mosley",
]
ROLES = ["Farmer", "Trader", "Hand", "Gunsmith", "Vendor", "Preacher",
         "Moonshiner", "Sheriff"]

NATION_PREFIX = ["Red", "Black", "Iron", "Golden", "Salt", "Pine", "Crow",
                 "Ash", "Stone", "Raven", "Copper", "Willow", "Ember", "Frost"]
NATION_SUFFIX = ["Reach", "Hollow", "Valley", "Crossing", "Flats", "Ridge",
                 "Bend", "Ford", "Bluffs", "Springs", "Hill", "Creek",
                 "March", "Barrens"]
NATION_COLORS = [(176, 62, 58), (62, 96, 176), (74, 138, 74), (170, 138, 52),
                 (140, 74, 158), (58, 148, 152), (190, 104, 46), (96, 96, 108)]


def village_name(gx: int, gy: int, seed: int = 0) -> str:
    code = ((gx * 73856093) ^ (gy * 19349663)
            ^ (seed * 2654435761)) & 0xFFFFFFFF
    return (NATION_PREFIX[code % len(NATION_PREFIX)] + " "
            + NATION_SUFFIX[(code // len(NATION_PREFIX)) % len(NATION_SUFFIX)])


def nation_name(nation: int) -> str:
    return nations.name(nation)


def nation_color(nation: int):
    return nations.color(nation)


_NAME_FONT = None


def _name_font():
    global _NAME_FONT
    if _NAME_FONT is None:
        _NAME_FONT = pygame.font.SysFont("dejavusans", 12, bold=True)
    return _NAME_FONT


def _lighten(color, amount):
    return tuple(min(255, c + amount) for c in color)


def _darken(color, amount):
    return tuple(max(0, c - amount) for c in color)


def _center_jitter(rng):
    return (rng.uniform(-SPACING * 0.22, SPACING * 0.22),
            rng.uniform(-SPACING * 0.22, SPACING * 0.22))


VILLAGE_SKIRT = 260.0     # clear ground outside the fence: a gate must open
                          # onto open air, and nobody should walk into a trunk


def village_clear_half(gx: int, gy: int) -> float:
    """Half-width of a village's cleared ground.

    A village is fenced with a SQUARE, so its cleared ground is a square too.
    Measuring it as a circle left the four corners open -- 1400 px of them on a
    capital -- which is exactly where trees grew through the wall and wolves
    walked in. Every spawner asks this one question.
    """
    return village_radius(gx, gy) + fence.MARGIN + VILLAGE_SKIRT


def village_clearance(x: float, y: float, seed: int) -> float:
    """How far outside the nearest village's cleared square a point stands.
    Negative means it is inside one."""
    gx0 = int(math.floor(x / SPACING))
    gy0 = int(math.floor(y / SPACING))
    best = 1e18
    for gx in (gx0 - 1, gx0, gx0 + 1):
        for gy in (gy0 - 1, gy0, gy0 + 1):
            vx, vy = village_center(gx, gy, seed)
            half = village_clear_half(gx, gy)
            d = max(abs(x - vx) - half, abs(y - vy) - half)   # a square, not a circle
            if d < best:
                best = d
    return best


@functools.lru_cache(maxsize=8192)
def village_center(gx: int, gy: int, seed: int):
    """Cheap, deterministic village centre (matches Village.__init__)."""
    code = (gx * 73856093) ^ (gy * 19349663) ^ (seed * 2654435761)
    rng = random.Random(code & 0xFFFFFFFF)
    jx, jy = _center_jitter(rng)
    return (gx + 0.5) * SPACING + jx, (gy + 0.5) * SPACING + jy


# THE MAN'S COMPILED FIELDS, NAMED IN ONE PLACE. village.pxd turns these
# into C struct members, which means they are NOT in __dict__ and a
# default pickle would lose them. __getstate__/__setstate__ below use
# this list so a man serialises as ONE PLAIN DICT -- the same shape the
# uncompiled class wrote -- and a cache written before he was compiled
# still loads instead of forcing the whole world to be rebuilt.
_NPC_CDEF_STATE = (
    "x",
    "y",
    "_px",
    "_py",
    "radius",
    "spacing",
    "speed",
    "base_speed",
    "stamina",
    "max_stamina",
    "hunger",
    "yearning",
    "health",
    "max_health",
    "hit_flash",
    "bleed",
    "drip_timer",
    "panic",
    "flee",
    "pause",
    "stuck",
    "_steer_timer",
    "_trade_timer",
    "_shop_timer",
    "chop_timer",
    "produce_acc",
    "attack_cd",
    "reload_timer",
    "tool_uses",
    "shoot_skill",
    "combat_speed",
    "alive",
    "aggro",
    "defender",
    "is_commander",
    "is_soldier",
    "on_duty",
    "king_run",
    "_dead_settled",
)


class NPC:
    # Real class defaults for attributes the code reads with
    # getattr(x, name, D). Every site agrees on D, so the default
    # says the same thing -- and the read can be a direct one.
    is_king: Any = False
    is_mayor: Any = False
    levied: Any = False
    refuge: Any = None
    refuge_eta: Any = 0.0
    # DEFAULTS AS CLASS ATTRIBUTES -- IMMUTABLE ONES ONLY.
    #
    # Every npc.x in a hot path is a question whose answer
    # is already known: every man has these. Declaring the default here means
    # plain attribute access is safe for any instance that has not set one --
    # which is the only thing the fallback was ever for -- and costs nothing.
    # Nothing mutable goes here: a dict or list on the class would be SHARED by
    # every villager in the world.
    home_house: Any = None
    asleep: Any = False
    in_interior: Any = False
    trade_state: Any = "none"
    loan_clock: Any = 0.0
    wants_product: Any = None
    wants_drink: Any = ""
    use_fx: Any = None
    _last_phase: Any = None
    # THE CARRY FOR A ROUNDED-UP TAX. economy.take_fifth() keeps the
    # fraction of a taxed unit it could not take yet, so one cigar still
    # pays its fifth eventually. It was never given a starting value, so
    # the FIRST taxed thing a man ever produced raised AttributeError --
    # which main's blanket `except Exception: alive = False` turned into
    # his death. Every miner died on his first swing: 73 became 34, and
    # 1,002 people became 747, and not one unit of iron was ever made.
    tax_frac: Any = 0.0
    # WHAT HE THINKS OF THE MEN HE HAS DEALT WITH, keyed by their id. None
    # until he trades with anybody -- a dict on every one of a thousand men
    # would be a thousand empty dicts, and this way a stranger costs nothing
    # until he is worth remembering. See economy.grow_opinion.
    opinion: Any = None
    at_court: Any = False        # a mayor: at the capital, or at home
    duel_tournament: Any = None  # the Test of Strengths is driving him
    vote_sold: Any = -1          # the day he last took coin for his vote
    vote_for: Any = None         # ...and who bought it

    # -- WHAT A MAN IS, WRITTEN DOWN --------------------------------------
    # One plain dict: every compiled field and everything in __dict__. The
    # compiled class would rather hand pickle a (dict, slots) tuple, and the
    # uncompiled class a dict -- which is why a cache written before this
    # change refused to load and the world rebuilt itself. Both shapes are
    # accepted on the way in; one shape is written on the way out.
    def __getstate__(self):
        # object.__getattribute__ because a cdef class may not name __dict__
        # directly -- Cython rejects the attribute access at compile time.
        state = dict(object.__getattribute__(self, "__dict__"))
        for _name in _NPC_CDEF_STATE:
            # Not every declared field is set in __init__ -- `flee` is only
            # given a value when he runs. The compiled class defaults it to
            # 0.0; the uncompiled one has no attribute at all, so a hard
            # getattr here is a crash on the first save. Skip what isn't there.
            try:
                state[_name] = getattr(self, _name)
            except AttributeError:
                pass
        return state

    def __setstate__(self, state):
        if isinstance(state, tuple):          # Cython's own (dict, slots)
            _dict = state[0] if state and isinstance(state[0], dict) else {}
            _slots = state[1] if len(state) > 1 and state[1] else {}
            state = dict(_dict)
            state.update(_slots)
        for _name, _value in state.items():
            setattr(self, _name, _value)


    def __init__(self, x: float, y: float, seed: int, name: str = "",
                 npc_id: str = "", role: str = "Villager", village=None) -> None:
        self.rng = random.Random(seed & 0xFFFFFFFF)
        self.name = name
        self.id = npc_id
        PEOPLE.append(self)          # he exists, so he is in the register
        self.role = role
        self.village = village
        self.home = (x, y)
        self.x = x
        self.y = y
        self.radius = 10
        self.spacing = NPC_SPACING
        self.facing = (0.0, 1.0)
        self.speed = self.rng.uniform(42.0, 68.0)
        self.base_speed = self.speed
        self.max_stamina = 100.0
        self.stamina = 100.0
        self._market_spot = None
        self.skills = skills.Skills()      # the same skills the player has
        self.target = (x, y)
        self.pause = self.rng.uniform(0.2, 1.2)
        self.stuck = 0.0
        self._px = x
        self._py = y
        self._dir = None
        self._steer_timer = 0.0
        self._steer_slot = abs(seed) % 8
        self.home_house = None
        self.home_door = None
        self.asleep = False          # gone into the house for the night
        self.in_interior = False     # currently standing inside a house
        self._saved = None
        self.clothing = self.rng.choice([
            (150, 110, 70), (118, 92, 150), (92, 132, 112), (176, 142, 92),
        ])
        self.kind = "villager"
        self.max_health = 40
        self.health = 40
        self.alive = True
        self.hit_flash = 0.0
        self.bleed = 0.0
        self.drip_timer = 0.0
        self.panic = 0.0
        self.attacked = False                              # holds a grudge
        # Quality they will buy. Nearly everyone buys ordinary leaf; demanding
        # a top grade is rare, so picky buyers feel like the exception.
        #            F     E     D     C     B     A     S     SS    SSS
        weights = (0.55, 0.20, 0.12, 0.07, 0.035, 0.015, 0.006, 0.003, 0.001)
        roll = self.rng.random()
        acc = 0.0
        self.quality_pref = 0
        for i, weight in enumerate(weights):
            acc += weight
            if roll <= acc:
                self.quality_pref = i
                break
        self.trade_demand = 0 if self.rng.random() < 0.06 else self.rng.randint(1, 20)
        self.restock_timer = 600.0 if self.trade_demand == 0 else 0.0
        self.coins = self.rng.randint(20, 120)             # his own wallet
        self.defender = False
        self.weapon = None                                 # "rifle" or "axe"
        # WHO THIS MAN KNOWS TO BE A MURDERER. News in this world is CARRIED,
        # never broadcast: a man who saw a killing tells the village he runs
        # to, its people tell the traders at the gate, and the traders tell the
        # next town down the road.
        self.knows: set = set()
        self.known_since: dict = {}      # name -> the moment he was told
        # WHAT HE SAW WITH HIS OWN EYES. A witness never lets it go -- not
        # after thirty days, not after the story itself has gone cold. He is
        # the reason a man who thought he was forgotten can walk into a market
        # three months later and watch somebody drop his basket and run.
        self.witness_to: set = set()
        self.news: list = []             # what he has heard of the war
        self.nation = None
        self.team = None                                   # ("nation", (gx, gy))
        self.is_commander = False
        self.is_soldier = False
        self.gun_kind = guns.RIFLE
        self.mag = guns.MAG[guns.RIFLE]
        self.reload_timer = 0.0
        self.shoot_skill = self.rng.uniform(0.1, 0.8)
        self.farm_plot = None        # fixed plot this villager tends
        self.job = None              # "miner" / "smith" / "logger"
        self.workplace = None
        self.produce_acc = 0.0
        self.chop_timer = 0.0
        self._log_tree = None
        self.schedule = "home"       # time-of-day phase right now
        self.bond_partner = None     # who they walk out with in the evening
        self.bond = 0.0              # growing affection
        self.social_target = None
        self._interior_rect = None
        self._interior_colliders = ()
        self.aggro = False
        self.attack_cd = self.rng.uniform(0.3, 0.8)
        self.combat_speed = self.rng.uniform(120.0, 160.0)
        self.strafe_dir = self.rng.choice((-1.0, 1.0))
        economy.setup(self)          # goods, coin, hunger, craving, duty
        self._trade_timer = self.rng.uniform(0.5, 2.5)

    def _tick_gun(self, dt: float) -> None:
        if self.reload_timer > 0.0:
            self.reload_timer = max(0.0, self.reload_timer - dt)
            if self.reload_timer == 0.0:
                self.mag = guns.MAG[self.gun_kind]

    def _round_ready(self) -> bool:
        """True if a round is ready (and spent); else starts a reload pause."""
        if self.reload_timer > 0.0:
            return False
        if self.mag <= 0:
            self.reload_timer = guns.reload_time(self.gun_kind, self.shoot_skill)
            return False
        self.mag -= 1
        return True

    def _shoot(self, combat, x, y, angle, distance, dmg_lo, dmg_hi) -> None:
        if self.gun_kind == guns.SHOTGUN:
            dmg_lo = max(2, dmg_lo // 2)
            dmg_hi = max(3, dmg_hi // 2)
        for _ in range(guns.PELLETS[self.gun_kind]):
            a = angle + self.rng.uniform(-0.07, 0.07)
            combat.fire(x, y, a, distance, owner="enemy",
                        damage=self.rng.randint(dmg_lo, dmg_hi), team=self.team)

    def take_damage(self, amount: int) -> bool:
        self.health -= amount
        self.hit_flash = 0.15
        self.bleed = 5.0
        self.panic = 6.0
        self.attacked = True          # he will not trade with you now
        if self.health <= 0:
            self.alive = False
            # EVERY VIOLENT DEATH IS WRITTEN DOWN. This was silent, so every
            # killing that was not a levied soldier -- wolves, soldiers, a
            # neighbour with an axe, a bullet -- vanished without a note. The
            # world lost four hundred people in two days and the log showed
            # only the starved and the rank-and-file, which is why a massacre
            # looked like a famine for a whole evening.
            try:
                import economy as _e
                _e._note("SLAIN    %-16s of %-14s by %d damage (health %d)"
                         % (self.name, getattr(getattr(self, "village", None),
                                               "name", "?"), amount,
                            max(0, self.health)))
            except Exception:
                pass
            self.die()                # A MAN SHOT DEAD SETTLES UP AS WELL.
            # The starvation path called this; a bullet did not -- so the dead
            # stayed in the register and in their town's roster for ever, and
            # the world walked corpses. That is what grew the register from
            # three thousand to forty.
        return not self.alive

    def tick(self, dt: float, world, now: float, phase: str = "home",
             combat=None, night: bool = False, colliders=(),
             threat_of=None) -> bool:
        """A MAN'S OWN STEP -- his body, then his business.

        Everything economy.tick() and NPC.update() did between them, called by
        the man himself rather than by a loop inside his town that reached into
        sixty people twenty times a second to ask how they were. The town is a
        service he uses: the granary when he is starving, the bank when his
        tool is worn, the order book when it breaks.
        """
        if not self.alive:
            return False
        # THE EVENING IS HIS. The town says when the market is; who he spends
        # it with, and where they stand, he arranges himself -- along with
        # clearing up after it. These are the three fields the town used to
        # set and wipe on every citizen.
        if phase != self._last_phase:
            self._last_phase = phase
            if phase == "market":
                self._pair_off()
            else:
                self.bond_partner = None
                self.social_target = None
                self._market_spot = None
        if not economy.needs(self, dt):
            self.die()               # starved
            return False
        home = self.village
        if home is not None:
            # THE GRANARY IS THE LAST RESORT, NOT THE FIRST. A man with the
            # price of a loaf in his pocket runs to whoever is selling -- see
            # _seek_goods() in his own update. Only a man who cannot buy at
            # all is fed for nothing. The dole used to fire at hunger 85
            # whether he held eighty coin or none, so the common store -- the
            # floor under the whole economy -- was emptied by men who could
            # have paid for their own bread, and then had nothing left for the
            # ones who truly could not.
            # BUY FIRST, AND THE GRANARY CATCHES YOU IF YOU CANNOT. A man
            # with the price of a loaf goes to the farmer -- _seek_goods() in
            # his own update walks him there. A man with nothing is fed at
            # once. And a man with coin whose purchase FAILED -- no seller,
            # or a price he could not meet -- is fed too, once he is nearly
            # dead. The dole is the floor under everybody; it is only the
            # ORDER that changes: the poor are caught early, the solvent are
            # caught at the last.
            if (self.hunger >= economy.DOLE_AT
                    and (self.coins < economy.DOLE_POOR
                         or self.hunger >= economy.DOLE_LAST)):
                economy.dole(home, self)              # the granary, for nothing
            self.loan_clock += dt
            if self.loan_clock >= 1.0:
                self.loan_clock = 0.0
                if (self.job is None and self.farm_plot is None
                        and self.workplace is None):
                    home.offer_post(self)     # the post is the town's to OFFER
                economy.place_orders(home, self)
                economy.tool_loan(home, self)
                economy.forge_loan(home, self)
                economy.service_loan(home, self)
        # A MAN TRADES WHEN HE PASSES SOMEBODY. This was the town's loop:
        # every villager's timer checked by the village, then a scan of the
        # whole village for each one that fired. His own timer and his own
        # search cost nothing extra, and the town stops reading sixty timers.
        self._trade_timer -= dt
        if self._trade_timer <= 0.0 and home is not None:
            self._trade_timer = self.rng.uniform(1.5, 3.5)
            other = self._passer_by()
            if other is not None:
                economy.pair_trade(home, self, other)
        threat = threat_of(self) if threat_of is not None else None
        self.update(dt, threat, colliders, combat, night, world, now, phase)
        if not self.alive:
            self.die()
            return False
        return True

    def _pair_off(self) -> None:
        """HE FINDS HIS OWN COMPANY, and chooses where they stand.

        The town used to shuffle its people into couples and hand each pair a
        spot in the square. He looks among his neighbours for somebody also
        unpaired, picks one with his own dice, and off they go -- the same
        evening, arranged by the people having it.
        """
        v = self.village
        if v is None or not self.alive or self.asleep or self.in_interior:
            return
        if self.bond_partner is not None and self.bond_partner.alive:
            return
        pool = [n for n in v.npcs
                if n is not self and n.alive and not n.asleep
                and not n.in_interior and n.bond_partner is None]
        if not pool:
            return
        partner = pool[self.rng.randrange(len(pool))]
        ang = self.rng.uniform(0.0, 2.0 * math.pi)
        rr = v.plaza_radius * 0.55 * math.sqrt(self.rng.random())
        spot = (v.x + math.cos(ang) * rr, v.y + math.sin(ang) * rr)
        self.bond_partner = partner
        partner.bond_partner = self
        self.social_target = spot
        partner.social_target = spot

    def _passer_by(self):
        """Somebody close enough to do business with, or nobody.

        The nearest man within 46 px, first-strictly-nearest in list order, so
        the same pair meets whoever asks first.
        """
        v = self.village
        if v is None:
            return None
        best, bd = None, 46.0 * 46.0
        for other in v.npcs:
            if (other is self or not other.alive
                    or other.in_interior or other.asleep):
                continue
            d = (other.x - self.x) ** 2 + (other.y - self.y) ** 2
            if d < bd:
                bd, best = d, other
        return best

    def die(self) -> None:
        """A man settles his own affairs: his post is freed, his caravan comes
        off the road, and the town's roster loses him. This used to be a sweep
        the village ran over everyone every step, looking for the dead."""
        if getattr(self, "_dead_settled", False):
            return
        self._dead_settled = True
        v = self.village
        reg = getattr(v, "registry", None) if v is not None else None
        if self.job == "trader" and reg is not None:
            reg.trader_deaths += 1
            if self.trade_state != "none":
                reg.trader_kills_away += 1
        if self.trade_state != "none":
            home = self.trade_home
            if home is not None:                 # the debt dies with him
                home.caravans = max(0, home.caravans - 1)
        self.refuge = None
        if self in TRAVELLERS:
            TRAVELLERS.remove(self)
        if self in PEOPLE:                       # and off the register of the
            PEOPLE.remove(self)                  # living, which is the list the
        if v is not None:                        # world walks every tick
            v.free_post(self)
            if self in v.npcs:
                v.npcs.remove(self)

    def update(self, dt: float, threat=None, colliders=None, combat=None,
               night: bool = False, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        # THE TEST OF STRENGTHS OUTRANKS EVERYTHING. A man in the ring at the
        # capital is not running a caravan, not moseying round a square and
        # not going home at night: the tournament is fighting him (see
        # tournament.Tournament.tick), so nothing else may.
        if self.duel_tournament is not None:
            return
        if self.known_since:              # ONLY A MAN WHO HAS BEEN TOLD
            self.forget(now)              # anything has anything to forget.
        self.speed = self.base_speed * self.skills.move_scale()   # practice tells
        # GET TO SAFETY. A refugee has exactly one mission and it outranks
        # his trade: a man running for his life does not stop to run a caravan.
        if getattr(self, "refuge", None) is not None and not self.in_interior:
            self.hit_flash = max(0.0, self.hit_flash - dt)
            self._tick_gun(dt)
            if self.alive:
                self._flee_village(dt)
            return
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)
        if self.bleed > 0.0:
            self.bleed = max(0.0, self.bleed - dt)
        if self.reload_timer > 0.0:       # a gun nobody is reloading needs
            self._tick_gun(dt)            # no function call to say so
        if self.restock_timer > 0.0:
            self.restock_timer -= dt
            if self.restock_timer <= 0.0:
                self.trade_demand = (0 if self.rng.random() < 0.06
                                     else self.rng.randint(1, 20))
                self.coins = self.rng.randint(20, 120)
                if self.trade_demand == 0:
                    self.restock_timer = 600.0                # try again later
        if not self.alive:
            return
        if self.on_duty:                           # represented by a soldier
            return
        if self.in_interior:                       # a guest in a house
            self._wander_interior(dt)
            return
        if not night and self.asleep and self.home_door is not None:
            self.x, self.y = self.home_door          # step out at dawn
            self.asleep = False
            self._dir = None
        if self.asleep:
            return

        # A wolf in the trees is a threat whether or not the village has
        # noticed: a man out in the woods -- or out on the road -- looks after
        # himself. This has to come BEFORE the trade run, or a trader walks
        # fifty miles of wolf country without ever raising his axe.
        beast = self._predator_near(world)
        if beast is not None and combat is not None:
            self._fight(dt, beast, combat)
            return
        if self.trade_state != "none":          # out on a trade run
            # A MAN ON THE ROAD TURNS BACK FOR HIS OWN TOWN. The trade run was
            # settled before the defence, so a man sent off on an errand walked
            # his route while his village burned behind him. Called home, he
            # makes for it -- and fights his way in if the murderer is there.
            if (self.aggro and threat is not None
                    and not getattr(threat, "dead", False)):
                home = self.trade_home
                if home is not None:
                    self.trade_stop = home
                    self.trade_dest = home
                self._fight(dt, threat, combat)
                return
            self._trade_step(dt, now)
            return
        # A trader may work off a debt on the road. Requiring loan <= 0 meant
        # that one trip ended in debt -- which it always does, since the
        # proceeds must cover provisions and both legs -- and then benched him
        # for life: three traders, three trips, twenty days. The cap keeps him
        # from running away into a spiral like the farmer's shovel loan did.
        if (self.job == "trader" and self.loan <= economy.CARAVAN_DEBT_CAP
                and self.hunger < 80.0):
            if self._trade_start(now):           # a trader trades, always
                self._trade_step(dt, now)
                return
        if getattr(self, "is_mayor", False):
            self._mosey(dt)
            return
        if self.aggro and threat is not None and not getattr(threat, "dead", False):
            self._fight(dt, threat, combat)
            return

        if self.panic > 0.0 and threat is not None:
            self.panic -= dt
            dx, dy = self.x - threat.x, self.y - threat.y
            distance = math.hypot(dx, dy) or 1.0
            self.x += dx / distance * 118.0 * dt
            self.y += dy / distance * 118.0 * dt
            self.facing = (dx / distance, dy / distance)
            return

        if self.pause > 0.0:
            self.pause -= dt
            return
        self.schedule = phase
        if phase == "market":          # mid-day: everyone to the square, where
            if self.social_target is not None:
                self._socialize(dt, now)   # they court, and children are born
                return
            self._go_to_market(dt)         # business is done there, face to face
            return
        if phase == "work" and world is not None and self.farm_plot is not None:
            if self._work_field(dt, world, now):    # tend the fields by day
                return
        elif phase == "work" and self.job == "logger":
            if self._work_woods(dt, now, world):    # out in the woods
                return
        elif phase == "work" and self.workplace is not None:
            industry.produce(self, dt, now)         # a shift is a shift
            if self._work_place(dt, now):           # and off they walk to it
                return
        elif phase == "social" and self.social_target is not None:
            self._socialize(dt, now)                # meet up in the evening
            return
        # A MAN BUYS WHAT HE HASN'T GOT. _seek_goods() was written for exactly
        # this -- "how goods move around a village", in its own words -- and
        # was called from NOWHERE. So a hungry man with coin in his pocket
        # stood about in a village full of food until he starved: the market
        # is open one fifth of the day, and a chance trade needs two men to
        # come within 46 pixels of each other. If he has a need and the coin
        # for it, he walks to whoever is selling.
        if self.coins > 0 and self._seek_goods(dt):
            return
        if (night or phase == "sleep") and self.home_door is not None:
            tx, ty = self.home_door
            if math.hypot(self.x - tx, self.y - ty) < 24.0:
                self.asleep = True               # walk up to the door and vanish
                self._dir = None
                return
        else:
            tx, ty = self.target
            if math.hypot(tx - self.x, ty - self.y) < 6.0:
                self.target = self._pick_target()
                self.pause = self.rng.uniform(0.6, 2.4)
                self._dir = None
                return
        # Roaming is low-effort: reuse the direction for a few frames.
        self._steer_timer -= dt
        if self._dir is None or self._steer_timer <= 0.0:
            self._steer_timer = 0.30 + self._steer_slot * 0.045
            self._dir = steering.steer(self, tx, ty, getattr(self, "_rects", ()),
                                       getattr(self, "_fences", ()))
        ux, uy = self._dir
        self.x += ux * self.speed * dt
        self.y += uy * self.speed * dt
        self.facing = (ux, uy)
        step = math.hypot(self.x - self._px, self.y - self._py)
        self.skills.gain_movement(step)
        self._px, self._py = self.x, self.y
        if step < self.speed * dt * 0.2:
            self.stuck += dt
            if self.stuck > 0.7 and not night:
                self.stuck = 0.0
                self.target = self._pick_target()
                self.pause = self.rng.uniform(0.2, 0.6)
                self._dir = None
        else:
            self.stuck = 0.0

    def _pick_target(self):
        if self.village is not None:
            return self.village.random_point(self.rng)
        angle = self.rng.uniform(0.0, 2.0 * math.pi)
        radius = self.rng.uniform(0.0, 220.0)
        return (self.home[0] + math.cos(angle) * radius,
                self.home[1] + math.sin(angle) * radius)

    def _step_toward(self, tx: float, ty: float, dt: float,
                     speed_scale: float = 1.0) -> None:
        ux, uy = steering.steer(self, tx, ty, getattr(self, "_rects", ()),
                                getattr(self, "_fences", ()))
        self.x += ux * self.speed * speed_scale * dt
        self.y += uy * self.speed * speed_scale * dt
        self.facing = (ux, uy)
        self.skills.gain_movement(self.speed * speed_scale * dt)

    def _work_field(self, dt: float, world, now: float) -> bool:
        """Tend the assigned field one action at a time: harvest a ripe crop,
        plant fertile soil, water dug soil, or break fresh ground with a
        shovel. Returns True while it is busy with the field."""
        job: Any = self.farm_plot
        if job is None or self.village is None or job >= len(self.village.farm_plots):
            return False
        ctx, cty, kind = self.village.farm_plots[job]
        todo: dict = {}
        for ttx, tty, tkind in self.village.farm_tiles[(ctx, cty)]:
            plot = world.plot_at(ttx, tty)
            state = plot.kind if plot is not None else None
            if state in crop.FOOD_KINDS or state in crop.LEAF_KINDS:
                if (plot.planted_at is not None
                        and now - plot.planted_at >= crop.GROW_SECONDS):
                    todo.setdefault("harvest", (ttx, tty, tkind))
            elif state == "fertile":
                todo.setdefault("plant", (ttx, tty, tkind))   # ready for the seed
            elif state == "dirt":
                todo.setdefault("water", (ttx, tty, tkind))   # dug but dry
            else:
                todo.setdefault("till", (ttx, tty, tkind))    # grass: break it open
        can_till = self.tool_uses > 0 or self.stock.get("shovel", 0) > 0
        task = None
        for action in ("harvest", "plant", "water", "till"):
            if action in todo:
                ttx, tty, tkind = todo[action]   # the KIND travels with the task
                task = (ttx, tty, action)
                break
        if task is not None and task[2] == "till" and not can_till:
            # The ground is dead and we have nothing to break it with. Standing
            # in a field we cannot work is not farming: go and buy a shovel.
            # (Before this, a farmer with a grass field and no shovel idled by
            # it forever -- his field died, he never learnt, and the plateau
            # that froze the whole village at 205 harvests was this one line.)
            self._go_to_market(dt)
            return True
        if task is None:                        # nothing to do: wait by the field
            tx, ty = ctx * TILE + TILE / 2.0, cty * TILE + TILE / 2.0
            if math.hypot(tx - self.x, ty - self.y) > 40.0:
                self._step_toward(tx, ty, dt, 0.7)
            return True
        ttx, tty, action = task
        tx = ttx * TILE + TILE / 2.0
        ty = tty * TILE + TILE / 2.0
        if math.hypot(tx - self.x, ty - self.y) > 12.0:
            self._step_toward(tx, ty, dt)
            return True
        if action == "harvest":
            plot = world.plot_at(ttx, tty)
            if plot is not None:
                economy.harvest(self.village, self, plot.kind, self.rng)
                self.skills.gain_farming(0.02)  # reaping hones the hand, slowly
            world.set_plot(ttx, tty, "grass", None)     # the soil is spent
        elif action == "till":
            if not self._swing_tool():
                return True                     # no shovel: we must buy one
            world.set_plot(ttx, tty, "dirt", None)
        elif action == "water":
            world.set_plot(ttx, tty, "fertile", None)
        else:                                    # plant the seed for that cell
            world.set_plot(ttx, tty, tkind, now)
        ground = getattr(world, "ground", None)
        if ground is not None:
            # DEFERRED. Rebuilding a 256x256 chunk of terrain noise inside the
            # frame that tilled one tile is fine once; with a hundred and sixty
            # farmers doing it hundreds of times a second it was the whole
            # frame. The worker thread does it instead.
            ground.invalidate_tile(ttx, tty, immediate=False)
        self.pause = 0.12          # a quick pair of hands
        return True

    def _swing_tool(self, item: str = "shovel") -> bool:
        """Wear the tool in hand, taking a spare from the crate when it breaks.
        A finer tool lasts longer -- but never long enough to pay for itself,
        because the price climbs faster than the work does. False means there is
        nothing left to work with, and he must go and buy one."""
        if self.tool_uses <= 0:
            if self.stock.get(item, 0) <= 0:
                return False
            self.stock[item] -= 1
            g = economy.grade_of(self, item)
            self.tool_uses = max(1, int(economy.TOOL_USES * economy.tool_dur_mult(g)))
        self.tool_uses -= 1
        return True

    def _find_tree(self, home, forest=None):
        """The nearest standing tree in the village's pre-staked woodlot. No
        searching here -- that was paid for once, when the village was built."""
        if self._log_tree is not None and not self._log_tree.felled:
            return self._log_tree
        # An explicit loop, not min(key=lambda ...): mypyc cannot compile the
        # generator-with-key form. Same search -- first-strictly-nearest in
        # woodlot order, and None if nothing stands.
        best = None
        best_d = 0.0
        for t in home.woodlot():
            if t.felled:
                continue
            d = (t.x - self.x) ** 2 + (t.y - self.y) ** 2
            if best is None or d < best_d:
                best, best_d = t, d
        self._log_tree = best
        return self._log_tree

    def _work_woods(self, dt: float, now: float, world) -> bool:
        """A logger: find a standing tree near the village, cut it down, stack
        the wood. The stump puts a new tree up in three minutes."""
        # THERE IS NO world.trees. The forest is staked out ONCE, per village,
        # into the module-level village._FOREST (see set_forest, called by
        # main), and home.woodlot() hands back the trees nearest THIS village.
        #
        # `getattr(world, "trees", None)` was therefore ALWAYS None, so this
        # returned False on its first line and _find_tree was never reached.
        # NO LOGGER IN THIS WORLD HAS EVER CUT A TREE: no wood, no axe gained,
        # no logger able to master logging, and no veteran woodsman anywhere.
        home = self.village
        if home is None:
            return False
        target = self._find_tree(home)
        if target is None:
            return False                    # no woods left standing near home
        if math.hypot(target.x - self.x, target.y - self.y) > 28.0:
            # Reuse the heading for a few frames, as ordinary roaming does:
            # steering every single frame is what made ten loggers expensive.
            self._steer_timer -= dt
            if self._dir is None or self._steer_timer <= 0.0:
                self._steer_timer = 0.35
                self._dir = steering.steer(self, target.x, target.y,
                                           getattr(self, "_rects", ()),
                                           getattr(self, "_fences", ()))
            ux, uy = self._dir
            self.x += ux * self.speed * 1.15 * dt
            self.y += uy * self.speed * 1.15 * dt
            self.facing = (ux, uy)
            return True
        self.facing = (0.0, 1.0)
        self.chop_timer += dt
        # A woodsman's hands decide how fast a tree falls. A veteran axeman
        # turned logger drops one in two seconds against a boy's four -- same
        # trade, four times the man.
        if self.chop_timer >= LOG_CHOP_SECONDS / (1.0 + self.skills.axe):
            # An axe blunts quicker than it looks -- a working woodsman goes
            # through one in a week or two, so the smith has a trade.
            if not self._swing_tool("axe"):
                return True                 # no axe, no work: go and buy one
            for _ in range(2):
                if not self._swing_tool("axe"):
                    break
            self.chop_timer = 0.0
            # IMPORTED HERE, NOT AT THE TOP. trees.py does `from village
            # import SPACING, ...`, so `import trees` in village's header is a
            # circular import and takes the whole game down with
            # "cannot import name 'SPACING' from partially initialized module".
            # By the time a logger swings, every module is loaded.
            # _FOREST is the forest OBJECT -- the same one main names `trees`
            # and hands to set_forest(). `fell` is a METHOD on it, not a
            # function in the trees module, which is why `trees.fell(...)` in
            # main works and `import trees; trees.fell(...)` here does not.
            if _FOREST is not None:
                _FOREST.fell(target, now)
            economy.cut_wood(self.village, self, self.rng.randint(10, 30))
            # FELLING TEACHES THE AXE. It never did. gain_axe was called on a
            # soldier's swing, the player's swing and a villager's fight -- and
            # nowhere else -- so a man who spent his whole life in the woods
            # never got better at the one tool he used. trade_mastered() reads
            # the axe, so no logger could EVER master logging, and any man
            # whose living was the axe stood on that rung for ever. It also
            # meant the world had no veteran woodsmen in it at all.
            self.skills.gain_axe()
            self._log_tree = None
        # ...and picks whatever grows beside the stump: food for his own
        # larder, leaf for his pocket, at whatever quality his hands are worth.
        self.forage_timer = getattr(self, "forage_timer", 0.0) - dt
        if self.forage_timer <= 0.0:
            self.forage_timer = 2.0 + self.rng.random() * 3.0
            wildcrop.forage_npc(world, self)
        return True

    def _work_place(self, dt: float, now: float) -> bool:
        """Turn up at the pit head or the forge."""
        wp: Any = self.workplace
        tx, ty = wp.door
        if math.hypot(tx - self.x, ty - self.y) > 18.0:
            self._step_toward(tx, ty, dt)
            return True
        self.facing = (0.0, 1.0)
        return True

    def _seek_goods(self, dt: float) -> bool:
        """Hungry, yearning, or craving a taste he hasn't got: walk to the
        nearest neighbour selling it. This is how goods move around a village."""
        vl = self.village
        if vl is None or self.coins <= 0:
            return False
        needs = []
        if not (economy.food_of(self) > 0 and self.hunger < economy.EAT_AT):
            needs.extend(economy.FOOD)
        for item in economy.FOOD:                # variety: a taste of each kind
            if self.stock.get(item, 0) < economy.VARIETY_MIN:
                needs.append(item)
        house = self.home_house
        if (house is not None
                and economy.house_wood(house) < economy.STOCK_WOOD):
            needs.append("wood")                 # the woodpile needs topping up
        leaf = getattr(self, "leaf_item", None)
        if (leaf and self.yearning >= economy.YEARING_BUY
                and self.stock.get(leaf, 0) <= 0):
            needs.append(leaf)
        for tool in economy.TOOLS:
            if economy.needs_tool(self, tool):
                needs.append(tool)
        if (self.job == "smith"
                and self.stock.get("iron", 0) < economy.IRON_STOCK):
            needs.append("iron")
        if not needs:
            self._shop_target = None
            return False
        # A starving man's need outranks a keeper's reserve -- otherwise an
        # evenly-fed village has no seller at all. See economy.pair_trade.
        desperate = self.hunger >= economy.DOLE_LAST
        target: Any = self._shop_target
        if target is not None:
            if (not target.alive or target.asleep or target.in_interior
                    or not (any(economy.surplus(target, it) > 0 for it in needs)
                            or (desperate and economy.food_of(target) > 0))):
                target = None
        if target is None:
            # The search is O(villagers x needs). Only do it every so often, and
            # stagger it: doing it for every soul on every tick was 93% of the
            # whole village tick.
            self._shop_timer -= dt
            if self._shop_timer > 0.0:
                return False
            self._shop_timer = 1.5
            best = None
            best_d = 1e18
            for other in vl.npcs:
                if other is self or not other.alive or other.on_duty:
                    continue
                if other.asleep or other.in_interior:
                    continue
                if not (any(economy.surplus(other, it) > 0 for it in needs)
                        or (desperate and economy.food_of(other) > 0)):
                    continue
                d = (other.x - self.x) ** 2 + (other.y - self.y) ** 2
                if d < best_d:
                    best_d, best = d, other
            target = best
            self._shop_target = target
            if target is None:
                return False
        if (target.x - self.x) ** 2 + (target.y - self.y) ** 2 <= 42.0 * 42.0:
            economy.pair_trade(vl, target, self)
            self._shop_target = None            # done here; look again later
            return True
        self._step_toward(target.x, target.y, dt)
        return True

    def _cart_space(self) -> int:
        return economy.CARAVAN_LOAD - sum(
            q for i, q in self.stock.items() if i in economy.GOODS)

    def _paid_unit(self, item: str, fallback: float) -> float:
        return self.paid.get(item, fallback)

    def _trade_load(self, village) -> int:
        """Buy what is cheap HERE and dear somewhere else, while the cart has
        room and the purse has coin. Best edge first, so the money goes where
        it earns most."""
        bought = 0
        routes = village.trade_routes()
        while self._cart_space() > 0:
            pick = None
            for item in economy.GOODS:
                if int(village.ledger_goods.get(item, 0)) <= 0:
                    continue
                here = max(1, economy.ledger_value(village, item))
                if self.coins < here:
                    continue
                far = max((economy.value(v, item) for v in routes), default=0)
                edge = far - here
                if edge <= 0:
                    continue
                if pick is None or edge > pick[0]:
                    pick = (edge, item, here)
            seller = None
            if pick is None:
                # Nothing in the common store worth carrying: buy it off the
                # PEOPLE. The granary is only half a market.
                for person in village.npcs:
                    if person is self or not person.alive or person.asleep:
                        continue
                    if person.in_interior:
                        continue
                    for item in economy.GOODS:
                        if economy.surplus(person, item) <= 0:
                            continue
                        here = economy.ask_price(village, person, item)
                        if self.coins < here:
                            continue
                        far = max((economy.value(v, item) for v in routes), default=0)
                        edge = far - here
                        if edge <= 0:
                            continue
                        if pick is None or edge > pick[0]:
                            pick = (edge, item, here)
                            seller = person
            if pick is None:
                break
            _, item, here = pick
            held = self.stock.get(item, 0)
            prev = self.paid.get(item, here)
            self.paid[item] = ((prev * held + here) / (held + 1)) if held else here
            if seller is None:                      # the wholesale house
                economy.store_take(village, item, 1)
                village.ledger_coins += here
                self.coins -= here
                self.stock[item] = held + 1
            elif economy._settle(village, item, here, 1, seller, self):
                pass                                # paid the man, got the good
            else:
                break
            bought += 1
        return bought

    def _trade_unload(self, village) -> int:
        """Sell what this village wants -- and never a unit below what I paid."""
        sold = 0
        for item in list(self.stock):
            qty = self.stock.get(item, 0)
            if qty <= 0 or item not in economy.GOODS:
                continue
            here = economy.value(village, item)
            if here <= self.paid.get(item, 0.0):
                continue                      # not worth parting with
            sold += self._trade_sell(village, item, qty)
        return sold

    def _best_next_stop(self, home):
        """Where does what I am HOLDING fetch the most above what I paid?"""
        best = None
        for cand in home.trade_routes():
            if cand is self.trade_stop:
                continue
            gain = 0
            for item, qty in self.stock.items():
                if qty <= 0 or item not in economy.GOODS:
                    continue
                price = economy.value(cand, item)
                paid = self.paid.get(item, price)
                if price > paid:
                    gain += qty * (price - paid)
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, cand)
        return best[1] if best else None

    def _trade_start(self, now: float) -> bool:
        """Load at home on one loan, then work a route: sell where the craving
        is, buy what is cheap there, and keep going while the cargo still has
        an edge -- five villages at most, then beeline home."""
        home = self.village
        registry = getattr(home, "registry", None)
        if registry is None or home.caravans >= economy.MAX_CARAVANS:
            return False
        routes = home.trade_routes()
        if not routes:
            return False
        # One loan, for the first purchase only. After that he trades his own
        # proceeds -- which is how a merchant actually works.
        best_edge = 0
        for item in economy.GOODS:
            if int(home.ledger_goods.get(item, 0)) <= 0:
                continue
            here = max(1, economy.ledger_value(home, item))
            far = max((economy.value(v, item) for v in routes), default=0)
            best_edge = max(best_edge, far - here)
        if best_edge <= 0:
            return False
        need = int(economy.CARAVAN_LOAD * best_edge * 0.6) + 20
        if need < economy.MIN_LOAN:
            return False
        if economy.borrow(home, self, need) <= 0:
            return False
        self._take_provisions(home)
        self.trade_home = home
        self.trade_stops = 0
        self.trade_item = None
        self.trade_back = None
        self.trade_goal = economy.CARAVAN_LOAD
        self._trade_load(home)                     # the first purchase
        nxt = self._best_next_stop(home) or routes[0]
        self.trade_stop = nxt
        self.trade_dest = nxt
        self.trade_state = "out"
        # A MAN ON THE ROAD IS A TRAVELLER, NOT A TOWNSMAN. He keeps his trade
        # -- he is still this town's trader, that is his living -- but he is not
        # standing in it, so the town's list of who is HERE does not hold him.
        # One man, one place.
        if self in home.npcs:
            home.npcs.remove(self)
        if self not in TRAVELLERS:
            TRAVELLERS.append(self)
        home.caravans += 1
        # (the trade_active set is gone: every town is stepped now, so a
        #  trader's target keeps walking without anyone tracking it)
        return True

    # A cart travels faster than a man. At the old 1.25x a single leg took 1.6
    # game days and three traders managed three trips in twenty days.
    CARAVAN_SPEED: Any = 4.0

    def _gate_goal(self, village):
        """The spot just outside a village's gate -- the only way through the
        wall. Exactly the trick the raiders use when they march on a village."""
        gwx, gwy = fence.gate_world(village)
        gox, goy = fence.gate_outward(village)
        return gwx + gox * 110.0, gwy + goy * 110.0

    def _arrive(self, village, dt: float) -> bool:
        """Walk to the village -- and near enough IS enough.

        Trading is done with the people and the ledger, not with the flagstones.
        Steering for the plaza and waiting until he stood on it left caravans
        orbiting the fence for days: they would reach the gate point, turn for
        the square, be refused, turn back for the gate, and circle forever.
        A trader who has come within sight of the wall has arrived.
        """
        if math.hypot(village.x - self.x, village.y - self.y) <= village.radius + 150.0:
            return True
        self._step_toward(village.x, village.y, dt, self.CARAVAN_SPEED)
        return False

    def _trade_step(self, dt: float, now: float) -> None:
        """The route. Arrive, sell what they want, buy what is cheap, decide
        where the rest of the load earns most, and go."""
        home = self.trade_home
        stop = self.trade_stop
        if home is None:
            self._trade_end()
            return
        if stop is None:
            self.trade_stop = home
            return
        if not self._arrive(stop, dt):
            return
        # Business is done in the market hour, when the whole village is
        # gathered in the square. A caravan that arrives at midnight and trades
        # with whoever is awake never meets the people it came to sell to.
        clock = (0.30 + now / economy.DAY_LENGTH) % 1.0
        if not (0.40 <= clock < 0.60):
            return                                 # stand about until it fills
        self._trade_unload(stop)                   # sell what they will buy
        # NEWS AT THE GATE, BOTH WAYS. A trader is how the world learns
        # anything: he tells this town what he heard on the road, and he
        # listens to what the town knows before he moves on. This is the
        # whole mechanism by which word of a murderer crosses the map.
        stop.learn_killers(self.knows, now, teller=self)
        self.learn(stop.killers, now)
        # ...AND THE NEWS OF THE WAR, which is a different trade entirely.
        import war as _war                       # lazily: war imports village
        _war.tell(self, stop, now)
        if getattr(stop, "is_capital", False) and getattr(stop, "demand", None):
            _war.pay_for_news(stop, self, now)   # the crown buys what it lacks
        if stop is home:                           # home again: settle up
            self._trade_end()
            return
        self._trade_load(stop)                     # re-invest in what is cheap
        self.trade_stops += 1
        if self.trade_stops >= economy.MAX_STOPS:
            nxt = home                             # five stops is enough
        else:
            nxt = self._best_next_stop(home) or home
        self.trade_stop = nxt
        self.trade_dest = nxt

    def _trade_end(self) -> None:
        home = self.trade_home
        # HOME AGAIN, SO A TOWNSMAN AGAIN -- off the road and back on the roll.
        if self in TRAVELLERS:
            TRAVELLERS.remove(self)
        if home is not None and self.alive and self not in home.npcs:
            home.npcs.append(self)
        if home is not None:
            self._trade_unload(home)               # dump the rest at home
            economy.repay(home, self)              # settle up
            home.caravans = max(0, home.caravans - 1)
        self.trade_state = "none"
        self.trade_item = None
        self.trade_back = None
        self.trade_stop = None
        self.trade_stops = 0

    def _take_provisions(self, home) -> None:
        """Load a few days' bread and a couple of logs out of the household."""
        family = [n for n in home.npcs if n is not self and n.alive
                  and n.home_house is not None and n.home_house is self.home_house]
        for item in economy.FOOD:
            need = 3 - self.stock.get(item, 0)
            for other in family:
                if need <= 0:
                    break
                if other.stock.get(item, 0) > economy.KEEP_FOOD:
                    take = min(need, other.stock[item] - economy.KEEP_FOOD)
                    other.stock[item] -= take
                    self.stock[item] = self.stock.get(item, 0) + take
                    need -= take
        for other in family:
            if self.stock.get("wood", 0) >= 2:
                break
            if other.stock.get("wood", 0) > economy.FUEL_KEEP:
                other.stock["wood"] -= 1
                self.stock["wood"] = self.stock.get("wood", 0) + 1

    def _trade_buy(self, village, item: str, want: int) -> int:
        """Fill the cart at the village ledger -- the wholesale house, which
        sells to foreign traders only, at its own fixed price -- and top up
        from whatever the villagers themselves will part with."""
        got = 0
        price = max(1, economy.ledger_value(village, item))
        have = village.ledger_goods.get(item, 0)
        qty = int(min(want, have, self.coins // max(0.05, price)))
        if qty > 0:
            economy.store_take(village, item, qty)
            village.ledger_coins += qty * price
            self.coins -= qty * price
            self.stock[item] = self.stock.get(item, 0) + qty
            got += qty
        return got

    def _trade_sell(self, village, item: str, want: int) -> int:
        sold = 0
        for buyer in list(village.npcs):
            if buyer is self or not buyer.alive or sold >= want:
                continue
            while (sold < want and self.stock.get(item, 0) > 0
                   and economy.wants(buyer, item) > 0):
                base = economy.graded_value(village, self, item)
                bid = economy.bid_price(village, buyer, item, base)
                if not economy._settle(village, item, bid, 1, self, buyer):
                    break
                sold += 1
        return sold

    def _go_to_market(self, dt: float) -> None:
        """Get to the square -- the whole village gathers at mid-day, and that
        hour is when everything is bought and sold."""
        home = self.village
        if home is None:
            return
        if math.hypot(home.x - self.x, home.y - self.y) > home.plaza_radius * 0.75:
            self._step_toward(home.x, home.y, dt, 1.2)   # hurry in
            return
        if self._market_spot is None:
            ang = self.rng.uniform(0.0, 2.0 * math.pi)
            rr = home.plaza_radius * 0.55 * math.sqrt(self.rng.random())
            self._market_spot = (home.x + math.cos(ang) * rr,
                                 home.y + math.sin(ang) * rr)
        tx, ty = self._market_spot
        if math.hypot(tx - self.x, ty - self.y) > 14.0:
            self._step_toward(tx, ty, dt, 0.75)

    def _socialize(self, dt: float, now: float) -> None:
        """Evening: meet your partner at the square and grow the friendship."""
        tx, ty = self.social_target
        if math.hypot(tx - self.x, ty - self.y) > 22.0:
            self._step_toward(tx, ty, dt, 0.85)
            return
        partner: Any = self.bond_partner
        if partner is None or not partner.alive:
            return
        dx, dy = partner.x - self.x, partner.y - self.y
        dist = math.hypot(dx, dy) or 1.0
        self.facing = (dx / dist, dy / dist)
        if dist < 36.0:
            self.bond += dt
            if (self.bond >= BIRTH_BOND and self.id < partner.id
                    and self.village is not None
                    and self.village.can_grow(now)):
                self.village.birth(self)

    def _wander_interior(self, dt: float) -> None:
        """Potter about the room while the player is inside the house."""
        rect: Any = self._interior_rect
        if rect is None:
            return
        if self.pause > 0.0:
            self.pause -= dt
            return
        tx, ty = self.target
        if math.hypot(tx - self.x, ty - self.y) < 10.0:
            self.target = (self.rng.uniform(rect.left + 22, rect.right - 22),
                           self.rng.uniform(rect.top + 22, rect.bottom - 22))
            self.pause = self.rng.uniform(0.5, 2.0)
            return
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        self.x += ux * self.speed * 0.55 * dt
        self.y += uy * self.speed * 0.55 * dt
        self.facing = (ux, uy)
        if self._interior_colliders:
            self.x, self.y = _resolve(self.x, self.y, self.radius,
                                      self._interior_colliders)

    def _predator_near(self, world, reach: float = 420.0):
        """Which wolf to go for. Prefer one the lads are already on -- a pack
        of woodsmen should fall on the same beast, not trickle in one by one.

        ASK THE BEASTS' OWN GRID, NOT THE WHOLE ENEMY LIST. This walked every
        wolf and every soldier on the map, per man, per tick, and kept only
        the wolves -- then threw away everything outside 420 px. The list is
        the one thing in the world that only grows.
        """
        grid = getattr(world, "wolves", None)
        if grid is not None:
            if not grid:
                return None
            near = grid
        else:                                    # nothing pre-picked: read all
            near = getattr(world, "enemies", None) or ()
        best = None
        best_score = None
        for e in near:
            if not e.alive or getattr(e, "kind", None) != "wolf":
                continue
            d2 = (e.x - self.x) ** 2 + (e.y - self.y) ** 2
            if d2 > reach * reach:
                continue
            mates = sum(1 for a in getattr(self.village, "npcs", ())
                        if a is not self and a.alive
                        and (a.x - e.x) ** 2 + (a.y - e.y) ** 2 <= 90.0 * 90.0)
            score = (mates, -d2)
            if best_score is None or score > best_score:
                best_score, best = score, e
        return best

    def _wind(self, sprinting: bool, dt: float, burn: float = 1.0) -> None:
        """Sprint while the wind lasts, breathe when it doesn't. The stamina
        skill sets the size of the tank, exactly as it does for the player."""
        top = self.max_stamina * self.skills.stamina_scale()
        if sprinting and self.stamina > 0.0:
            self.stamina = max(0.0, self.stamina - 28.0 * burn * dt)
        else:
            self.stamina = min(top, self.stamina + 12.0 * dt)

    def occupation(self) -> str:
        """What this person actually DOES.

        Every villager is rolled a flavour title at birth -- Preacher, Vendor,
        Gunsmith, Sheriff -- which describes no work he has ever done. When you
        are buying a man's iron or his grain, the only thing worth printing is
        the trade he actually holds, or the plain fact that he holds none.
        """
        if getattr(self, "is_king", False):
            return "King"
        if getattr(self, "is_mayor", False):
            return "Mayor"
        if self.is_commander:
            return "Commander"
        if self.defender:
            return "Soldier"
        job = self.job
        if job == "soldier":
            return "Rifleman" if getattr(self, "ranged", False) else "Soldier"
        if job:
            return {"mine": "Miner", "smith": "Smith", "lab": "Artisan",
                    "brewery": "Brewer", "logger": "Logger",
                    "trader": "Trader"}.get(job, job.title())
        if self.farm_plot is not None:
            return "Farmer"
        return "No trade"          # honestly nothing

    def _mosey(self, dt: float) -> None:
        """The mayor's day: stand about the square, being important.

        And, twice a month, walk to the capital and back. See court_day: the
        plaza he is walking toward is either his own or the King's, and the
        ROAD between them is walked at a travelling pace rather than the
        half-speed shuffle a man uses in a square he is already standing in.
        """
        px, py = getattr(self, "plaza", (self.x, self.y))
        dx, dy = self.x - px, self.y - py
        d = math.hypot(dx, dy)
        if d > 400.0:
            # ON THE ROAD. A man walking to court does not stroll at half
            # pace -- the journey is meant to take days, not weeks, and at
            # 0.45x a capital two days away became a fortnight's absence,
            # which is most of the term he was supposed to be serving.
            ux, uy = (px - self.x) / d, (py - self.y) / d
            self.facing = (ux, uy)
            self.x += ux * self.speed * dt
            self.y += uy * self.speed * dt
            return
        if d > 120.0:                     # wandered off: stroll back
            ux, uy = (px - self.x) / d, (py - self.y) / d
        else:
            self.pause -= dt
            if self.pause > 0.0:
                return
            self.pause = self.rng.uniform(2.0, 6.0)
            a = self.rng.uniform(0.0, math.tau)
            ux, uy = math.cos(a), math.sin(a)
        self.facing = (ux, uy)
        self.x += ux * self.speed * 0.45 * dt
        self.y += uy * self.speed * 0.45 * dt

    def _flee_village(self, dt: float) -> None:
        """Run for the nearest gate, then run for the next village that will
        have us. A refugee arrives with nothing and is given no trade."""
        dest: Any = self.refuge
        home = self.village
        r = home.fence_rect if home is not None else None
        if r is not None and r.collidepoint(self.x, self.y):
            side, gx, gy = fence.nearest_gate(home, self.x, self.y)
            ox, oy = fence.OUTWARD[side]
            tx, ty = gx + ox * 240.0, gy + oy * 240.0     # out through the gap
        else:
            tx, ty = dest.x, dest.y
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < 12.0 and (r is None or not r.collidepoint(self.x, self.y)):
            self._arrive_refuge(dest)
            return
        d = d or 1.0
        self.facing = (dx / d, dy / d)
        speed = self.base_speed * self.skills.move_scale() * 1.5   # terror
        self.x += dx / d * speed * dt
        self.y += dy / d * speed * dt
        if r is not None and not r.collidepoint(self.x, self.y):
            if self not in TRAVELLERS:      # out of the gate: he works here no more
                TRAVELLERS.append(self)
                if home is not None:
                    home.free_post(self)
            if math.hypot(dest.x - self.x, dest.y - self.y) < dest.radius + 260.0:
                self._arrive_refuge(dest)

    def _arrive_refuge(self, dest, now: float = 0.0) -> None:
        """Handed over: the old village loses a mouth, the new one gains an
        idle pair of hands."""
        if self in TRAVELLERS:
            TRAVELLERS.remove(self)
        old = self.village
        if old is not None:
            old.free_post(self)
            if self in getattr(old, "npcs", ()):
                old.npcs.remove(self)
        self.refuge = None
        self.village = dest
        self.job = None                 # a refugee has no trade
        self.workplace = None
        self.farm_plots = []
        self.plot = None
        self.aggro = False
        self.panic = 0.0
        self.flee = 0.0
        ang = random.uniform(0.0, 2.0 * math.pi)
        dist = random.uniform(0.25, 0.85) * dest.radius
        self.x = dest.x + math.cos(ang) * dist
        self.y = dest.y + math.sin(ang) * dist
        if self not in dest.npcs:
            dest.npcs.append(self)
        dest.refugees = getattr(dest, "refugees", 0) + 1
        dest._fill_vacancies()        # a hand that arrives is a hand put to work
        if getattr(self, "king_run", False):
            # HE GOT THERE. He is handed his thirty coins at the gate, and the
            # crown has the news -- which is more than any of the others, who
            # only made it as far as the next town.
            self.king_run = False
            import war as _war2
            if getattr(dest, "is_capital", False):
                self.coins += _war2.MESSENGER_PAY
                self.book_in = getattr(self, "book_in", 0.0) + _war2.MESSENGER_PAY
        # AND HE TELLS THEM WHY HE CAME -- both halves of it. Word of a
        # murderer, and word of the war that drove him out.
        dest.learn_killers(self.knows, now, teller=self)
        import war as _war                 # lazily: war imports village
        _war.tell(self, dest, now)

    def learn(self, ids, now: float) -> bool:
        """Told something, and when. Returns True if it was news to him."""
        ids = {i for i in ids if not story_cold(i, now)}
        if not ids:
            return False
        news = bool(ids - self.knows)
        for i in ids:
            if i not in self.knows:
                self.known_since[i] = now
        self.knows |= ids
        return news

    def witness(self, ids) -> None:
        """He saw it himself, so he keeps it for good."""
        ids = set(ids)
        self.witness_to |= ids
        self.knows |= ids
        for i in ids:
            self.known_since.setdefault(i, 0.0)

    def is_witness(self, name: str) -> bool:
        return name in self.witness_to

    def forget(self, now: float) -> bool:
        """Old news is let go. True if he forgot anything.

        Thirty days after he was told, a man stops caring -- unless he was
        THERE. A witness is never talked out of what he watched happen, and
        the story going cold does not touch him either: it only stops him
        telling anyone else.
        """
        if not self.known_since:
            return False
        gone = [i for i, told_at in self.known_since.items()
                if i not in self.witness_to
                and (now - told_at >= FORGET_AFTER or story_cold(i, now))]
        for i in gone:
            self.known_since.pop(i, None)
            self.knows.discard(i)
        return bool(gone)

    def arm(self) -> str | None:
        """What this man can fight with, if anything.

        A gun he owns, or the axe on his belt. A logger has one in his hands
        by trade even if the pack is empty. Everyone else has nothing, and
        nothing is what he fights with.
        """
        if getattr(self, "ranged", False):
            return "rifle"
        if self.stock.get("rifle", 0) > 0 or self.stock.get("shotgun", 0) > 0:
            return "rifle"
        if self.stock.get("axe", 0) > 0 or self.job == "logger":
            return "axe"
        return None

    def _fight(self, dt: float, target, combat) -> None:
        dx, dy = target.x - self.x, target.y - self.y
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = dx / distance, dy / distance
        self.facing = (ux, uy)
        if self.weapon == "rifle":
            preferred = 220.0
            if distance > preferred + 40.0:
                self.x += ux * self.combat_speed * 1.5 * dt      # sprint in
                self.y += uy * self.combat_speed * 1.5 * dt
            elif distance < preferred - 40.0:
                self.x -= ux * self.combat_speed * dt
                self.y -= uy * self.combat_speed * dt
            else:
                self.x += -uy * self.strafe_dir * self.combat_speed * 0.5 * dt
                self.y += ux * self.strafe_dir * self.combat_speed * 0.5 * dt
            self.attack_cd -= dt
            if self.attack_cd <= 0.0 and combat is not None and distance <= 460.0:
                angle = math.atan2(dy, dx) + random.uniform(-0.03, 0.03)
                mx, my = self.x + ux * 16.0, self.y + uy * 16.0
                ex = mx + math.cos(angle) * (distance + 120.0)
                ey = my + math.sin(angle) * (distance + 120.0)
                if not friendly_in_line(mx, my, ex, ey, self, self.team,
                                        getattr(self, "_soldiers", ()),
                                        getattr(self, "_player", None), self.nation):
                    if self._round_ready():
                        self.attack_cd = random.uniform(0.5, 0.9)
                        self._shoot(combat, mx, my, angle, distance + 120.0, 6, 12)
        else:
            # Axe work. Hold the range where the axe reaches and the teeth do
            # not: a wolf bites at 30, so dance at 33 to 40 and let him wear
            # himself out. Use the legs -- and the wind -- to keep that gap.
            # A lunge is the moment of truth: dig in and get out of the way,
            # and it costs a man his wind to do it. No wind, and he is bitten.
            lunged = getattr(target, "lunging", 0.0) > 0.0
            sprint = self.stamina > 0.0
            step = self.combat_speed * ((1.9 if lunged else 1.6)
                                        if sprint else 1.0) * dt
            burn = 2.0 if lunged else 1.0
            if distance > 46.0:                     # too far: close him down
                self.x += ux * step
                self.y += uy * step
                self._wind(False, dt)
            elif distance < 38.0:
                # He is getting inside the swing. Give ground -- a man who
                # retreats faster than the wolf charges never gets bitten,
                # because the wolf reaches 30 and the axe reaches 46.
                self.x -= ux * step
                self.y -= uy * step
                self._wind(sprint, dt, burn)
            else:
                # Jockeying for the gap costs the legs even when you are not
                # sprinting. There is no free breathing in a fight -- this is
                # what turns the duel into a race against your own wind.
                self.stamina = max(0.0, self.stamina - 10.0 * dt)
            self.attack_cd -= dt
            if distance <= 46.0 and self.attack_cd <= 0.0:
                self.attack_cd = 1.0
                if hasattr(target, "take_damage"):
                    self.skills.gain_axe()
                    # A MAN WITH AN AXE SWINGS AN AXE; A MAN WITHOUT ONE SWINGS
                    # HIS FISTS. Same motion, same skill, a quarter of the
                    # damage -- see skills.UNARMED_WEAKNESS. Before this he
                    # fought bare-handed at full axe weight, so an unarmed
                    # villager hit as hard as an armed one.
                    _armed = (self.stock.get("axe", 0) > 0
                              or self.job == "logger")
                    _base = (10.0 if _armed
                             else 10.0 / skills.UNARMED_WEAKNESS)
                    target.take_damage(max(1, round(
                        _base * self.skills.axe_damage_scale())))

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             show_name: bool = False) -> None:
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        hx, hy = sx + fx * 2, sy + fy * 2 - 2      # head centre
        wear = getattr(self, "wear", "normal")
        flash = self.hit_flash > 0.0
        pygame.draw.ellipse(screen, (20, 36, 20), (sx - 12, sy - 4, 24, 9))

        if flash or wear == "normal":
            body = (242, 232, 232) if flash else self.clothing
            pygame.draw.circle(screen, body, (int(sx), int(sy)), 10)
            pygame.draw.circle(screen, (44, 40, 36), (int(sx), int(sy)), 10, 2)
            pygame.draw.circle(screen, (216, 172, 132), (int(hx), int(hy)), 5)
            pygame.draw.circle(screen, (150, 112, 82), (int(hx), int(hy)), 5, 1)
        elif wear == "fur":                        # fur coat + ushanka
            fur, fur_hi = (176, 156, 122), (214, 196, 162)
            pygame.draw.circle(screen, fur, (int(sx), int(sy)), 11)
            for i in range(10):
                a = i * math.tau / 10.0
                pygame.draw.circle(screen, fur_hi,
                                   (int(sx + math.cos(a) * 10), int(sy + math.sin(a) * 10)), 4)
            pygame.draw.circle(screen, (108, 90, 66), (int(sx), int(sy)), 11, 2)
            pygame.draw.circle(screen, (150, 128, 98), (int(hx), int(hy)), 8)
            pygame.draw.circle(screen, (216, 172, 132), (int(hx), int(hy)), 4)
            pygame.draw.rect(screen, (150, 128, 98), (int(hx - 8), int(hy - 3), 16, 5),
                             border_radius=2)
        elif wear == "tuareg":                     # indigo robe + head wrap
            robe, robe_hi = (56, 74, 122), (34, 48, 88)
            pygame.draw.circle(screen, robe, (int(sx), int(sy)), 10)
            pygame.draw.circle(screen, robe_hi, (int(sx), int(sy)), 10, 2)
            pygame.draw.line(screen, (196, 186, 160), (sx - 7, sy + 4), (sx + 7, sy + 4), 2)
            pygame.draw.circle(screen, (222, 214, 190), (int(hx), int(hy)), 8)
            pygame.draw.circle(screen, (158, 150, 130), (int(hx), int(hy)), 8, 1)
            pygame.draw.rect(screen, (222, 214, 190), (int(hx - 8), int(hy - 2), 16, 5))
            pygame.draw.line(screen, (34, 32, 36), (hx - 3, hy + 1), (hx + 3, hy + 1), 2)
        elif wear == "zebra":                      # striped cloth
            pygame.draw.circle(screen, (234, 230, 222), (int(sx), int(sy)), 10)
            for dy in (-6, -2, 2, 6):
                half = int(math.sqrt(max(0.0, 100 - dy * dy)) * 0.92)
                pygame.draw.line(screen, (32, 30, 34), (sx - half, sy + dy),
                                 (sx + half, sy + dy), 3)
            pygame.draw.circle(screen, (44, 40, 36), (int(sx), int(sy)), 10, 2)
            pygame.draw.circle(screen, (216, 172, 132), (int(hx), int(hy)), 5)
            pygame.draw.circle(screen, (150, 112, 82), (int(hx), int(hy)), 5, 1)

        if self.is_commander:
            hx = sx + fx * 2
            hy = sy + fy * 2 - 2
            pygame.draw.circle(screen, (46, 52, 74), (int(hx), int(hy - 1)), 8)
            pygame.draw.rect(screen, (46, 52, 74), (int(hx - 9), int(hy - 5), 18, 4))
            pygame.draw.line(screen, (214, 184, 96), (hx - 7, hy - 1), (hx + 7, hy - 1), 2)
            pygame.draw.circle(screen, (214, 184, 96), (int(hx), int(hy - 4)), 2)
        if show_name and self.name:
            font = _name_font()
            label = font.render(self.name, True, (242, 238, 224))
            shadow = font.render(self.name, True, (24, 20, 14))
            lx = int(sx - label.get_width() / 2)
            ly = int(sy - 32)
            screen.blit(shadow, (lx + 1, ly + 1))
            screen.blit(label, (lx, ly))
        if getattr(self, "friendly", False):       # your nation's people
            pygame.draw.circle(screen, (110, 226, 226), (int(sx), int(sy)), 14, 2)
        self._draw_use_fx(screen, sx, sy, hx, hy)

    def _draw_use_fx(self, screen, sx, sy, hx, hy) -> None:
        """Three seconds of enjoyment: a cigar and its smoke, a mouthful of
        dried mushroom and its colours, or a bottle held in the hand. All of it
        half-transparent, drawn over the villager so it reads at a glance."""
        fx = self.use_fx
        if fx is None:
            return
        item, left = fx
        prog = 1.0 - max(0.0, min(1.0, left / economy.USE_FX_SECONDS))
        fxdir = self.facing
        hx2 = sx + fxdir[0] * 13.0
        hy2 = sy + fxdir[1] * 13.0 + 2.0
        pad = 46
        surf = pygame.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
        cx, cy = pad, pad
        dx, dy = hx2 - sx, hy2 - sy

        if item == "cigar":
            pygame.draw.rect(surf, (108, 66, 38, 235),
                             (cx + dx - 3, cy + dy - 2, 12, 4), border_radius=2)
            pygame.draw.circle(surf, (240, 150, 60, 235), (cx + dx + 9, cy + dy), 2)
            for i in range(6):                      # smoke curling upward
                p = prog * 1.2 + i * 0.16
                if p > 1.0:
                    continue
                rad = int(2 + p * 7)
                a = int(96 * (1.0 - p))
                wob = math.sin(p * 7.0) * 5.0
                pygame.draw.circle(surf, (222, 222, 228, a),
                                   (int(cx + dx + wob), int(cy + dy - 6 - p * 26)), rad)

        elif item == "dried_mushroom":
            pygame.draw.circle(surf, (196, 176, 140, 235), (int(cx + dx), int(cy + dy)), 4)
            rings = ((232, 96, 200), (96, 214, 232), (238, 220, 96))
            for i, col in enumerate(rings):         # colours pulsing around him
                p = (prog * 1.15 + i * 0.22) % 1.0
                rad = int(10 + p * 30)
                a = int(115 * (1.0 - p))
                pygame.draw.circle(surf, col + (a,), (cx, cy), rad, 3)
            for i in range(4):
                a = 70 + int(50 * math.sin(prog * 12.0 + i))
                ang = prog * 6.0 + i * 1.57
                pygame.draw.circle(surf, (255, 255, 255, max(0, a)),
                                   (int(cx + math.cos(ang) * 24), int(cy + math.sin(ang) * 18)), 2)

        else:                                        # beer, liqueur, mezcal
            bottle = pygame.Surface((14, 22), pygame.SRCALPHA)
            colour = {"beer": (168, 112, 40), "liqueur": (150, 60, 96),
                      "mezcal": (198, 190, 150)}.get(item, (168, 112, 40))
            pygame.draw.rect(bottle, colour + (215,), (1, 7, 12, 14), border_radius=3)
            pygame.draw.rect(bottle, (206, 214, 220, 190), (4, 0, 6, 8))
            pygame.draw.rect(bottle, (210, 210, 216, 150), (1, 7, 12, 14), 1, border_radius=3)
            surf.blit(bottle, (cx + dx - 7, cy + dy - 15))

        screen.blit(surf, (sx - pad, sy - pad))


def _resolve(x, y, r, rects):
    from physics import resolve_circle_rects
    return resolve_circle_rects(x, y, r, rects)


class House:
    def tick(self, dt: float, village=None) -> None:
        """A HOUSEHOLD'S OWN BUSINESS: the family shares a larder, and the fire
        burns a log. Neither the town's nor quite one man's, which is why it
        never fitted in either and sat in the village's loop for so long.

        Driven from the register of houses now, by itself, at the same once a
        second it was always done at. The town it stands in is found from the
        family living in it.
        """
        if village is None and self.occupants:
            village = getattr(self.occupants[0], "village", None)
        if village is None:
            return
        economy.household_share(self, dt, village)

    warmth: Any = 1.0          # a hearth that has not been lit is neither warm nor
                          # cold; the getattr fallback said so, and now the
                          # class says it for nothing.
    def __init__(self, x: float, y: float, w: int, h: int, roof, facing, seed: int,
                 government: bool = False) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.roof = roof
        self.government = government
        self.facing = facing                       # cardinal unit vector
        self.base_y = y + h / 2.0
        self.rng = random.Random(seed & 0xFFFFFFFF)

        if facing[0] == 0.0:                       # faces north/south
            half_x, half_y = w / 2.0, h / 2.0
        else:                                      # faces east/west (rotated 90)
            half_x, half_y = h / 2.0, w / 2.0
        self.rect = pygame.Rect(x - half_x, y - half_y, half_x * 2, half_y * 2)
        self.sight_rect = self.rect.inflate(EAVE * 2, EAVE * 2)
        self.door_broken = False
        self.interior = None
        self.enterable = False
        self.occupants: list = []

        self._image: pygame.Surface | None = None
        self.image = self._render()
        if government:
            self._render_government()
        self.garden = self._make_garden()
        HOUSES.append(self)

    # -- the sprite, drawn once and kept ------------------------------------
    @property
    def image(self) -> pygame.Surface:
        """The house's sprite, drawn the first time it is asked for.

        A pygame Surface cannot be pickled, so the world cache leaves this out
        and it is made again on demand -- which is safe because _render() is
        deterministic from the house's own shape, colour, facing, roof and
        broken door, and uses no random numbers at all. Drawing it again gives
        back exactly the same picture, and it costs nothing until a house is
        actually on screen.
        """
        if self._image is None:
            self._image = self._render()
        return self._image

    @image.setter
    def image(self, surface: pygame.Surface) -> None:
        self._image = surface

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_image"] = None          # redrawn on demand; never written out
        return state

    def _render_government(self) -> None:
        """Twice a house in both directions, and no windows at all: the state
        does not want to be looked into. Columns, a pediment, a banner."""
        img = self.image
        w, h = self.w, self.h
        ex = EAVE
        body = pygame.Rect(ex, ex, w, h)
        pygame.draw.rect(img, (194, 188, 174), body)
        pygame.draw.rect(img, (126, 120, 108), body, 3)
        for i in range(5):
            cx = ex + 16 + i * (w - 32) / 4.0
            pygame.draw.rect(img, (224, 218, 204), (int(cx) - 2, ex + 12, 11, h - 22))
            pygame.draw.rect(img, (150, 144, 132), (int(cx) - 2, ex + 12, 11, h - 22), 1)
        pygame.draw.rect(img, (170, 164, 150), (ex, ex, w, 13))
        pygame.draw.rect(img, (108, 102, 90), (ex, ex, w, 13), 2)
        pygame.draw.rect(img, (92, 40, 36), (ex + int(w / 2) - 16, ex + 5, 32, 20))
        pygame.draw.rect(img, (234, 210, 122), (ex + int(w / 2) - 5, ex + 10, 10, 10))
        pygame.draw.rect(img, (60, 56, 50), (ex + int(w / 2) - 22, ex + h - 30, 44, 30))
        pygame.draw.rect(img, (208, 202, 188), (ex + int(w / 2) - 22, ex + h - 30, 44, 4))

    # -- sprite -------------------------------------------------------------
    def _render(self) -> pygame.Surface:
        w, h = self.w, self.h
        sx, sy = w + 2 * EAVE, h + 2 * EAVE
        surf = pygame.Surface((sx, sy), pygame.SRCALPHA)

        pygame.draw.rect(surf, (16, 30, 16, 95), (EAVE + 5, EAVE + 6, w, h))

        foot = pygame.Rect(EAVE, EAVE, w, h)
        pygame.draw.rect(surf, WALL, foot)

        roof_h = max(24, int(h * 0.68))
        light = _lighten(self.roof, 28)
        dark = _darken(self.roof, 30)
        ridge_y = (EAVE + roof_h) // 2
        pygame.draw.rect(surf, light, (0, 0, sx, ridge_y))
        pygame.draw.rect(surf, dark, (0, ridge_y, sx, EAVE + roof_h - ridge_y))
        for xx in range(4, sx, 8):
            pygame.draw.line(surf, _darken(light, 16), (xx, 0), (xx, ridge_y - 1), 1)
            pygame.draw.line(surf, _darken(dark, 16), (xx, ridge_y + 1), (xx, EAVE + roof_h - 1), 1)
        pygame.draw.line(surf, (62, 44, 36), (0, ridge_y), (sx, ridge_y), 2)
        pygame.draw.rect(surf, (58, 42, 36), (0, 0, sx, EAVE + roof_h), 2)

        chimney_x = int(sx * 0.70)
        pygame.draw.rect(surf, (152, 134, 122), (chimney_x, 2, 12, 17))
        pygame.draw.rect(surf, (92, 78, 70), (chimney_x, 2, 12, 17), 2)
        pygame.draw.rect(surf, (92, 78, 70), (chimney_x - 1, 0, 14, 3))

        # dormer on the lower slope
        dorm_w = 15
        dorm_x = EAVE + w // 2 - dorm_w // 2
        dorm_y = ridge_y + 7
        pygame.draw.rect(surf, (104, 148, 172), (dorm_x, dorm_y, dorm_w, 11))
        pygame.draw.rect(surf, (58, 42, 36), (dorm_x, dorm_y, dorm_w, 11), 2)
        pygame.draw.line(surf, (58, 42, 36), (dorm_x, dorm_y + 5), (dorm_x + dorm_w, dorm_y + 5), 1)

        shade = pygame.Surface((sx, 8), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 76))
        surf.blit(shade, (0, EAVE + roof_h))
        pygame.draw.rect(surf, WALL_DARK, foot, 2)

        wall_h = h - roof_h
        door_w = max(14, int(w * 0.20))
        door_h = max(18, wall_h - 2)
        door_x = EAVE + w // 2 - door_w // 2
        door_y = EAVE + h - door_h
        if self.door_broken:
            pygame.draw.rect(surf, (26, 20, 14), (door_x, door_y, door_w, door_h))
            pygame.draw.rect(surf, (62, 42, 28), (door_x, door_y, door_w, door_h), 2)
            pygame.draw.line(surf, (62, 42, 28), (door_x, door_y),
                             (door_x + door_w, door_y + door_h), 2)
            pygame.draw.line(surf, (62, 42, 28), (door_x + door_w, door_y),
                             (door_x, door_y + door_h), 2)
        else:
            pygame.draw.rect(surf, (116, 76, 46), (door_x, door_y, door_w, door_h))
            pygame.draw.rect(surf, (68, 44, 26), (door_x, door_y, door_w, door_h), 2)
            pygame.draw.line(surf, (68, 44, 26), (door_x + door_w // 2, door_y),
                             (door_x + door_w // 2, door_y + door_h), 1)
            pygame.draw.circle(surf, (228, 206, 128), (door_x + door_w - 4, door_y + door_h // 2), 2)

        win = min(14, max(9, w // 6))
        for side in (-1, 1):
            wx = EAVE + w // 2 + side * (w // 3) - win // 2
            if EAVE + 3 < wx and wx + win < sx - 3:
                wy = EAVE + roof_h + max(3, (wall_h - win) // 2)
                pygame.draw.rect(surf, (104, 148, 172), (wx, wy, win, win))
                pygame.draw.rect(surf, (66, 46, 32), (wx, wy, win, win), 2)
                pygame.draw.line(surf, (66, 46, 32), (wx + win // 2, wy),
                                 (wx + win // 2, wy + win), 1)

        pygame.draw.rect(surf, STONE, (door_x - 4, EAVE + h - 1, door_w + 8, 7))
        pygame.draw.rect(surf, STONE_DARK, (door_x - 4, EAVE + h - 1, door_w + 8, 7), 1)
        pygame.draw.circle(surf, (70, 110, 52), (EAVE + 6, EAVE + h - 4), 6)
        pygame.draw.circle(surf, (92, 134, 68), (EAVE + 10, EAVE + h - 5), 5)

        angle = {(0.0, -1.0): 180, (0.0, 1.0): 0, (1.0, 0.0): 90, (-1.0, 0.0): 270}[self.facing]
        if angle:
            surf = pygame.transform.rotate(surf, angle)
        return surf

    def break_door(self) -> None:
        self.door_broken = True
        self.image = self._render()

    # -- garden -------------------------------------------------------------
    def _make_garden(self):
        if self.rng.random() > 0.6:               # ~60% of houses have one
            return []
        fx, fy = self.facing
        back_x, back_y = -fx, -fy
        distance = self.h / 2.0 + 46.0
        base_x = self.x + back_x * distance
        base_y = self.y + back_y * distance
        count = self.rng.randint(3, 6)
        tiles = []
        for i in range(count):
            offset = (i - (count - 1) / 2.0) * TILE
            if back_x != 0.0:
                gx = int(math.floor(base_x / TILE))
                gy = int(math.floor((base_y + offset) / TILE))
            else:
                gx = int(math.floor((base_x + offset) / TILE))
                gy = int(math.floor(base_y / TILE))
            tiles.append((gx, gy))
        return tiles

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        image = self.image
        screen.blit(image, (self.x - cam_x - image.get_width() / 2,
                            self.y - cam_y - image.get_height() / 2))


def set_forest(forest) -> None:
    """Hand the village generator the woods, so a woodlot can be staked out the
    moment a village is built rather than mid-frame when a logger sets off."""
    global _FOREST
    _FOREST = forest


TRAVELLERS: list = []          # refugees on the road, belonging to no village

# EVERY LIVING VILLAGER, IN ONE LIST. Not sixty-four lists inside sixty-four
# towns that each have to be walked, and not a set of towns to guess at -- one
# flat register of the people themselves, walked once per tick. A man is in it
# because he exists, wherever he is standing.
PEOPLE: list = []

# AND THE HOUSES, THE SAME WAY. A household's larder is the household's -- a
# third owner, neither the town's nor quite one man's -- so it is driven like
# a person is: from its own flat register, by itself.
HOUSES: list = []


def rebuild_houses(registry) -> int:
    """Refill the register of houses, for the same reason as the people's:
    unpickling never calls __init__."""
    HOUSES[:] = [h for v in registry.villages for h in v.houses]
    return len(HOUSES)


def rebuild_people(registry) -> int:
    """Refill the register from the towns, AND PUT EVERY MAN IN ONE PLACE.

    Needed after a load for two reasons. Unpickling does not call __init__, so
    a restored villager never put himself in; and a save stores a man's town
    and his road separately, so a restored traveller could come back listed in
    the town he left as well as on the road. He lives in one place, and this
    is where that is made true rather than assumed.
    """
    claimed: dict = {}
    for v in registry.villages:
        keep = []
        # A TOWN CANNOT HOLD MORE PEOPLE THAN IT WAS BUILT FOR. capacity is the
        # number it was founded with, and can_grow() already refuses to breed
        # past it -- but a restored save could pile strangers on top of it: a
        # record whose id matched nobody was ADDED as a new person, so a save
        # written in the era of the town-building bug came back with six
        # hundred people in a town of fifty. The same rule, applied on the way
        # in, makes that impossible to carry forward.
        room = max(0, int(getattr(v, "capacity", len(v.npcs))))
        for n in v.npcs:
            if n.refuge is not None:
                continue                       # he is on the road, not here
            home = n.village
            if home is not None and home is not v:
                continue                       # he lives somewhere else now
            if id(n) in claimed:
                continue                       # already on another town's roll
            claimed[id(n)] = n
            keep.append(n)
            if len(keep) >= room:
                break
        v.npcs[:] = keep
    PEOPLE[:] = list(claimed.values())
    keep_trav: Any = []
    for n in TRAVELLERS:
        if n not in keep_trav:
            keep_trav.append(n)
    TRAVELLERS[:] = keep_trav
    for n in TRAVELLERS:
        if n not in PEOPLE:
            PEOPLE.append(n)
    return len(PEOPLE)


class Village:
    def __init__(self, gx: int, gy: int, seed: int) -> None:
        code = (gx * 73856093) ^ (gy * 19349663) ^ (seed * 2654435761)
        rng = random.Random(code & 0xFFFFFFFF)
        self.code = code
        self.gx, self.gy = gx, gy
        jx, jy = _center_jitter(rng)
        self.x = (gx + 0.5) * SPACING + jx
        self.y = (gy + 0.5) * SPACING + jy

        self.houses: list[House] = []
        self.government = None          # set below if this is a capital
        self.nation = nations.nation_index(self.x, self.y)
        self.name = village_name(gx, gy, seed)
        self.plundered = False
        self.battle = False
        self.chaos = 0.0
        self.conquered = False
        self.provoked = False
        self.killers: set = set()        # murderers this village has been told of
        self.news: list = []             # what has reached it about the war
        self.demand = None               # a capital's standing offer for word
        self.killer_since: dict = {}     # and when it was told of each
        # the notice board that stands in the square
        self.board = pygame.Rect(int(self.x - 26), int(self.y - 56), 52, 48)
        self.local_food = "wheat"
        self.local_leaf = "plant"
        # A nation's capital is twice the village: twice the ground, twice the
        # houses, twice the fields, twice the works. And it is where the
        # nation's idle gather -- see the population step below.
        self.is_capital = nations.is_capital_cell(self.gx, self.gy, SPACING)
        self.scale = VILLAGE_SCALE * (2.0 if self.is_capital else 1.0)
        self.radius = village_radius(self.gx, self.gy)
        self.plaza_radius = 30.0 * self.scale
        plan_r = 360.0 * self.scale
        nroads = rng.randint(3, 6)
        base = rng.uniform(0.0, 2.0 * math.pi)
        self.roads: list[list[tuple[float, float]]] = []
        for i in range(nroads):
            ang = base + i * 2.0 * math.pi / nroads + rng.uniform(-0.15, 0.15)
            length = plan_r * rng.uniform(0.72, 0.98)
            pts = [(self.x, self.y)]
            for s in range(1, 7):
                t = s / 6.0
                aa = ang + math.sin(t * 3.1 + i * 1.7) * 0.10
                rr = self.plaza_radius * 0.5 + (length - self.plaza_radius * 0.5) * t
                pts.append((self.x + math.cos(aa) * rr, self.y + math.sin(aa) * rr))
            self.roads.append(pts)

        # ~1,000 people across 36 villages: about sixteen houses a village,
        # thirty-two at a capital. Big enough for a mine, a forge, a ledger
        # with real coin in it, and a crown that can afford a war.
        # ~1,000 PEOPLE ACROSS 36 VILLAGES, which is what the comment above
        # has always claimed and what the numbers never delivered: twelve to
        # twenty houses a village gave 460 people, not a thousand. The count is
        # DOUBLED here rather than tuned, because the target is the number this
        # world was designed around and it is the one thing that has been
        # wrong the whole time.
        target = rng.randint(max(8, int(2.0 * self.scale)),
                             max(10, int(3.4 * self.scale)))
        if self.is_capital:
            target = int(target * 1.6)          # a city, not a parish
        placed = {}

        def clash(hx, hy, clearance):
            cell = 200.0
            gx0, gy0 = int(hx // cell), int(hy // cell)
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for px2, py2, pr in placed.get((gx0 + ox, gy0 + oy), ()):
                        if math.hypot(hx - px2, hy - py2) < clearance + pr:
                            return True
            return False

        attempts = 0
        fails = 0
        while len(self.houses) < target and attempts < 20000 and fails < 1200:
            attempts += 1
            road = self.roads[rng.randrange(len(self.roads))]
            seg = rng.randrange(len(road) - 1)
            (ax, ay), (bx, by) = road[seg], road[seg + 1]
            t = rng.random()
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1.0
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
            near_centre = math.hypot(px - self.x, py - self.y) < plan_r * 0.55
            if not near_centre and rng.random() < 0.45:
                fails += 1
                continue                       # sparser out towards the edges
            side = 1.0 if rng.random() < 0.5 else -1.0
            w = rng.randint(92, 150)
            h = rng.randint(88, 140)
            clearance = max(w, h) / 2.0 + EAVE + 22.0
            off = clearance * 0.55 + rng.uniform(4.0, 22.0)
            hx = px + nx * side * off + ux * rng.uniform(-28.0, 28.0)
            hy = py + ny * side * off + uy * rng.uniform(-28.0, 28.0)
            if math.hypot(hx - self.x, hy - self.y) < self.plaza_radius + clearance * 0.5:
                fails += 1
                continue                       # keep the city centre clear
            if clash(hx, hy, clearance):
                fails += 1
                continue
            fails = 0
            if abs(nx * side) >= abs(ny * side):
                facing = (-1.0 if (nx * side) > 0.0 else 1.0, 0.0)
            else:
                facing = (0.0, -1.0 if (ny * side) > 0.0 else 1.0)
            self.houses.append(House(hx, hy, w, h, rng.choice(ROOFS), facing,
                                     code ^ (attempts * 2654435761)))
            placed.setdefault((int(hx // 200.0), int(hy // 200.0)), []).append(
                (hx, hy, clearance))

        if self.is_capital:
            # The Government, standing in the square where it can be seen from
            # every street. Twice a house outside, twice a house inside, and
            # not one window.
            # A fixed, deliberate size -- twice a good house -- rather than
            # twice whichever house happened to be built last, which made the
            # Government a different building in every capital.
            gw, gh = GOV_W, GOV_H
            gov = House(self.x, self.y + 8.0, gw, gh, rng.choice(ROOFS),
                        (0.0, 1.0), code ^ 0x5EED, government=True)
            gov.enterable = True
            gov.interior_seed = code ^ 0x5EEE
            gov.interior = interior.Interior(code ^ 0x5EEE, (0.0, 1.0),
                                             width=interior.W * 2,
                                             height=interior.H * 2,
                                             windows=False, grand=True)
            self.houses.append(gov)
            self.government = gov

        # (self.radius was set from village_radius above -- one rule, one place)

        # -- the pits and the smithy, standing inside the fence -------------
        self.workplaces: list[industry.Workplace] = []
        self.mines: list[industry.Workplace] = []
        self.smith = None
        self.lab = None
        self.brewery = None
        # Everything a village has, a capital has TWICE. Not twice the rate
        # from the same men -- twice the men, twice the forges, twice the
        # benches. Same logic, one bigger number.
        _mult = 2 if self.is_capital else 1
        _kinds = [("mine", rng.randint(industry.MINES_MIN, industry.MINES_MAX) * _mult),
                  ("smith", 1 * _mult)]
        # A laboratory works tobacco and mushrooms. The desert grows agave,
        # which no laboratory can use -- so the desert gets none, and its
        # craving goes unsatisfied. (self.local_leaf is not set until later,
        # so ask the biome directly.)
        _leaf_here = biomes.crop_kinds(
            float(biomes.temperature(self.x, self.y, seed)),
            float(biomes.humidity(self.x, self.y, seed)))[1]
        if _leaf_here != "agave":
            _kinds.append(("lab", 1 * _mult))
        # Every village gets a brewery: wheat and berries here, and agave out
        # in the desert -- which is the only industry that country will ever have.
        _kinds.append(("brewery", 1 * _mult))
        for _kind, _many in _kinds:
            for _n in range(_many):
                for _try in range(400):
                    ang = rng.uniform(0.0, 2.0 * math.pi)
                    # A village rings its plaza. A capital fills its ground: the
                    # same fraction of a doubled radius left two and a half
                    # kilometres of empty field in the middle of every capital,
                    # which is why it looked like a village with no fence.
                    lo, hi = (0.22, 0.86) if self.is_capital else (0.55, 0.82)
                    rr = self.radius * rng.uniform(lo, hi)
                    wx = self.x + math.cos(ang) * rr
                    wy = self.y + math.sin(ang) * rr
                    if clash(wx, wy, 140.0):
                        continue
                    wp = industry.Workplace(_kind, wx, wy,
                                            code ^ rng.randrange(2 ** 31))
                    # (no rate trick: the extra men are the doubling)
                    self.workplaces.append(wp)
                    if _kind == "mine":
                        self.mines.append(wp)
                    elif _kind == "lab":
                        self.lab = wp
                    elif _kind == "brewery":
                        self.brewery = wp
                    else:
                        self.smith = wp
                    placed.setdefault((int(wx // 200.0), int(wy // 200.0)),
                                      []).append((wx, wy, 140.0))
                    break

        self.woodlot()          # pay for the tree search at build time

        fence.install(self, rng)

        self.npcs: list[NPC] = []
        spec = []
        # ~1,000 PEOPLE ACROSS 36 VILLAGES. This is the number that decides
        # it, and it was the wrong one all along: houses are capped by GEOMETRY
        # -- the placement loop refuses to overlap them inside the ring, so
        # doubling the house target just means more failed attempts and the
        # same 460 people. Doubling the PEOPLE per house is what actually
        # doubles the world, and it lands within a few per cent of a thousand.
        for house in self.houses:
            n = 1 + (1 if rng.random() < 0.42 else 0) \
                  + (1 if rng.random() < 0.16 else 0)
            spec.append((house, n))
        if not self.is_capital:
            # A village keeps its breadwinners and sends its surplus up to the
            # capital: the idle populations out here are noticeably thinner.
            for i in range(len(spec)):
                if spec[i][1] > 1 and rng.random() < 0.35:
                    spec[i] = (spec[i][0], spec[i][1] - 1)
        count = sum(n for _h, n in spec)
        # Three of the people are away on patrol duty (they spawn as soldiers).
        spare = min(3, max(0, count - 6))
        while spare > 0 and spec:
            house, n = spec[-1]
            take = min(n, spare)
            spec[-1] = (house, n - take)
            spare -= take
            if spec[-1][1] == 0:
                spec.pop()
        count = sum(n for _h, n in spec)

        # ---- SCALE TO THIS TOWN'S SHARE OF A THOUSAND -------------------
        # The draws above decide WHICH house is crowded. They do not decide how
        # big the world is -- that is a thousand people and it is not left to
        # chance. The roomy houses are filled and the crowded ones thinned until
        # the town holds exactly its share.
        want = max(4, int(round(PEOPLE_PER_HOUSE * len(self.houses))))
        guard = 0
        while count > want and spec and guard < 5000:
            spec.sort(key=lambda hn: -hn[1])
            if spec[0][1] <= 1:
                break
            spec[0] = (spec[0][0], spec[0][1] - 1)
            count -= 1
            guard += 1
        guard = 0
        while count < want and spec and guard < 5000:
            spec.sort(key=lambda hn: hn[1])
            spec[0] = (spec[0][0], spec[0][1] + 1)
            count += 1
            guard += 1
        wear = biomes.npc_wear(float(biomes.temperature(self.x, self.y, seed)),
                               float(biomes.humidity(self.x, self.y, seed)))
        name_rng = random.Random((code ^ 0x9E3779B9) & 0xFFFFFFFF)
        pool = list(FIRST_NAMES)
        name_rng.shuffle(pool)
        idx = 0
        for house, n in spec:
            fx, fy = house.facing
            door = (house.x + fx * (house.h / 2.0 + 10.0),
                    house.y + fy * (house.h / 2.0 + 10.0))
            for _ in range(n):
                sx, sy = self.random_point(rng)
                full_name = f"{pool[idx % len(pool)]} {name_rng.choice(LAST_NAMES)}"
                person = NPC(sx, sy, code ^ (idx * 83492791), name=full_name,
                             npc_id=f"npc_{gx}_{gy}_{idx}",
                             role=name_rng.choice(ROLES), village=self)
                person.home_house = house
                person.home_door = door
                person.wear = wear
                house.occupants.append(person)
                self.npcs.append(person)
                idx += 1

        # Every village has exactly one commander (the one you join an army
        # through), plus a few armed defenders.
        self._name_rng = name_rng
        self._name_pool = pool
        self._name_i = idx
        # THE CAPACITY IS THE ROSTER -- NOT THE NUMBER WE AIMED AT.
        #
        # This was `count`, the SCALE TARGET, and the two are not the same
        # number: the patrol takes three men out to spawn as soldiers and the
        # target was computed before that, so sixteen towns believed they held
        # two more men than they did. A town grows back to its capacity, so the
        # world swelled 1,000 -> 1,032 within a day of starting, and the cap
        # never matched the roster in any file that carried it.
        self.capacity = len(self.npcs)    # the village will grow back to THIS
        # THE FOUR NUMBERS, once, at build time. capacity has been 8-58 while
        # the spec above says three people a house, and the house count is 19
        # to 57 -- so the number that caps the town is not the number the spec
        # produces, and this line says which of the two it is.
        import economy as _econ
        _econ._note("BUILD %-14s houses %3d  spec-people %3d  capacity %3d  npcs %3d  capital %s"
                    % (self.name, len(self.houses), count, self.capacity,
                       len(self.npcs), self.is_capital))
        self._wear = wear
        self.last_death = -1e9
        self._phase = "home"
        self._rng = random.Random((code ^ 0x51ED1E55) & 0xFFFFFFFF)
        self._births = 0
        self.ledger_goods: dict[str, int] = {}    # the government's stores
        self.ledger_grade: dict[str, int] = {}    # ...and the grade of those goods
        self.ledger_lots: dict[str, dict[int, int]] = {}   # units in by grade
        self.ledger_coins = 0                     # the government's coin
        self._tax_frac = 0.0                      # sales tax carried at fractions
        self._seeded = False                      # farm plots seeded yet?
        self.prices = dict(economy.ITEM_VALUE)    # the fixed village prices
        if self.is_capital:
            # The crown bids high for arms, and publicly.
            for _it in ("rifle", "shotgun", "ammo"):
                self.prices[_it] = round(self.prices.get(_it, 100)
                                         * economy.CROWN_ARMS_MULT, 3)
        self.wage_day = -1
        self.market_day = -1
        self._market_timer = 0.0
        self._share_timer = 0.0
        self._meet_timer = 0.0
        self.caravans = 0
        self.duty_day = -1
        self._armed: list = []
        # A capital has a King. He works at nothing, he is paid the most, and
        # he lives off the crown's half of every village's profit.
        self.king = None
        # A MAYOR for the ordinary villages. Not a capital's business -- a
        # capital has a King -- and he needs no hall to do it from: he stands
        # about the square all day being the most important man in the place,
        # on the nation's payroll.
        self.mayor = None
        self._capital = None
        if self.is_capital and len(self.npcs) > 1:
            self.king = self.npcs[-1]
            self.king.role = "King"
            self.king.is_king = True
            self.king.job = "king"
        if not self.is_capital and len(self.npcs) > 2:
            self.mayor = self.npcs[-2]
            self.mayor.role = "Mayor"
            self.mayor.is_mayor = True
            self.mayor.job = "mayor"
            self.mayor.plaza = (self.x, self.y)
        self.commander = self.npcs[0]
        self.commander.role = "Commander"
        self.commander.is_commander = True
        self.commander.defender = True
        self.commander.weapon = "rifle"
        for npc in self.npcs:
            npc.nation = self.nation
            npc.team = ("nation", self.nation)

        defenders = min(count - 1, rng.randint(3, 5))
        for i in range(1, 1 + defenders):
            guard = self.npcs[i]
            guard.defender = True
            guard.role = "Defender"
            guard.weapon = "rifle" if rng.random() < 0.5 else "axe"
            guard.max_health = 70
            guard.health = 70
            if guard.weapon == "rifle" and rng.random() < 0.25:
                guard.gun_kind = guns.SHOTGUN
                guard.mag = guns.MAG[guns.SHOTGUN]

        # -- communal 5x5 crop plots on the inner border ring ----------------
        self.farm_plots: list[tuple[int, int, str]] = []
        self.farm_tiles: dict[tuple[int, int], list[tuple[int, int, str]]] = {}
        self._farm_timer = 0.0
        anchors: list[tuple[float, float]] = []
        nplots = rng.randint(4, 6) * (2 if self.is_capital else 1)
        # Monoculture per plot, but an even split of the two local crop slots.
        food, leaf = biomes.crop_kinds(float(biomes.temperature(self.x, self.y, seed)),
                                       float(biomes.humidity(self.x, self.y, seed)))
        # DOUBLE the food fields; the leaf plots stay exactly as they were.
        # DUAL CULTURE. Every plot grows both: two thirds food, one third leaf.
        # A leaf-only plot has nothing to sell until the leaf is worth
        # something, so the man who farms it has no runway, no coin, and never
        # turns profitable. Food pays his way while the leaf earns the margin.
        kinds = [food] * nplots
        self.local_food = food
        self.local_leaf = leaf
        rng.shuffle(kinds)

        # Find EVERY workable spot on the inner border ring first, then deal the
        # plots out from that pool. The old way sampled fifty random points and
        # gave up, so extra plots silently failed to place -- which meant
        # "double the food fields" was really just stealing the leaf ones.
        spots = []
        seen_cells = set()
        for frac in (0.58, 0.64, 0.70, 0.76, 0.82, 0.88, 0.94):
            rr = self.radius * frac
            steps = max(16, int(2.0 * math.pi * rr / (TILE * 1.5)))
            for i in range(steps):
                ang = (i / steps) * 2.0 * math.pi + rng.uniform(-0.012, 0.012)
                wx = self.x + math.cos(ang) * rr
                wy = self.y + math.sin(ang) * rr
                ctx = int(math.floor(wx / TILE))
                cty = int(math.floor(wy / TILE))
                if (ctx, cty) in seen_cells:
                    continue
                px2 = ctx * TILE + TILE / 2.0
                py2 = cty * TILE + TILE / 2.0
                if math.hypot(px2 - self.x, py2 - self.y) > self.radius - 110.0:
                    continue
                if any(house.rect.inflate(150, 150).collidepoint(px2, py2)
                       for house in self.houses):
                    continue
                seen_cells.add((ctx, cty))
                spots.append((px2, py2, ctx, cty))
        rng.shuffle(spots)
        for kind in kinds:                      # every plot gets a home
            pick = None
            for gap in (7.0 * TILE, 6.0 * TILE, 5.0 * TILE, 0.0):
                for spot in spots:
                    if gap and any(math.hypot(spot[0] - ax, spot[1] - ay) < gap
                                   for ax, ay in anchors):
                        continue
                    pick = spot
                    break
                if pick is not None:
                    break
            if pick is None:
                break                           # the ring is genuinely full
            spots.remove(pick)
            px2, py2, ctx, cty = pick
            anchors.append((px2, py2))
            self.farm_plots.append((ctx, cty, kind))
            cells = [(ctx + dx, cty + dy)
                     for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)]
            food_cells = (len(cells) * 2) // 3        # two thirds to the larder
            self.farm_tiles[(ctx, cty)] = [
                (cx2, cy2, food if i < food_cells else leaf)
                for i, (cx2, cy2) in enumerate(cells)]
        # Every household should have at least one breadwinner, so the jobs go
        # out one per house first; whatever is left is then handed to anybody.
        eligible = [n for n in self.npcs
                    if not n.defender and not n.is_commander
                    and not n.is_king
                    and not n.is_mayor
                    and not n.is_soldier and not n.weapon]
        # FIELDS FIRST. Every plot must have its own farmer before a single
        # man is spared for the woods or the road.
        farms = ["farm"] * len(self.farm_plots)
        fixed = len(self.farm_plots) + len(self.workplaces)
        rest = [wp.kind for wp in self.workplaces]
        # ONE LOGGER PER THREE HOUSES, not one per house. The quota was
        # max(LOGGERS_PER_VILLAGE, houses - fixed) and houses - fixed always
        # won, so the floor never applied and the woods took HALF OF
        # EVERYBODY -- 1,623 of 3,177 people were loggers.
        rest += ["logger"] * max(LOGGERS_PER_VILLAGE,
                                 (len(self.houses) - fixed) // 3)
        rest += ["trader"] * (TRADERS_PER_VILLAGE * _mult)
        rng.shuffle(rest)
        slots = farms + rest          # dealt from the front, so fields go first

        by_house: dict = {}
        for n in eligible:
            if n.home_house is not None:
                by_house.setdefault(id(n.home_house), []).append(n)
        houses = list(by_house)
        rng.shuffle(houses)
        handed: list = []
        for key in houses:                       # one worker per household
            if not slots:
                break
            pool = by_house[key]
            if not pool:
                continue
            handed.append((pool.pop(rng.randrange(len(pool))), slots.pop(0)))
        rest = [n for pool in by_house.values() for n in pool]
        rng.shuffle(rest)
        while slots and rest:                    # then fill the rest of the jobs
            handed.append((rest.pop(), slots.pop(0)))

        field_i = 0
        for worker, job in handed:
            if job == "farm":
                worker.farm_plot = field_i
                worker.leaf_farmer = True     # every plot grows some leaf now
                worker.stock["shovel"] = 1
                worker.tool_uses = economy.TOOL_USES
                field_i += 1
            elif job in ("mine", "smith", "lab", "brewery"):
                wp = next((w for w in self.workplaces
                           if w.worker is None and w.kind == job), None)
                if wp is None:
                    continue
                worker.job = wp.kind
                worker.workplace = wp
                wp.worker = worker
                if wp.kind == "smith":
                    worker.stock["iron"] = economy.IRON_STOCK // 4
            elif job == "logger":
                worker.job = "logger"
                worker.stock["axe"] = 1                  # a woodsman's living
                worker.grade["axe"] = 0
                worker.tool_uses = economy.TOOL_USES
            elif job == "trader":
                worker.job = "trader"

        # A village is not born starving: everyone has a little in the larder
        # and the common granary and purse are stocked below.
        food_item = crop.FOOD_ITEM.get(food, "bread")
        self.leaf_item = crop.LEAF_ITEM.get(leaf, "tobacco")
        for npc in self.npcs:
            npc.stock[food_item] = npc.stock.get(food_item, 0) + rng.randint(1, 3)
            npc.leaf_item = rng.choice(economy.LEAF)   # his own habit, not the village's
        # The common granary and the common purse. The granary holds a few days'
        # bread; the purse must cover the first day's wages before the shop has
        # taken anything back.
        # Local scarcity sets the opening prices: what this village grows is
        # cheap, what it cannot grow is dear. That gap is a trader's living.
        self.prices[food_item] = int(round(economy.ITEM_VALUE[food_item] * 0.70))
        for item in economy.FOOD:
            if item != food_item:
                self.prices[item] = int(round(economy.ITEM_VALUE[item] * 1.45))
        self.prices[self.leaf_item] = int(round(economy.ITEM_VALUE[self.leaf_item] * 0.70))
        for item in economy.LEAF:
            if item != self.leaf_item:
                self.prices[item] = int(round(economy.ITEM_VALUE[item] * 1.45))
        self.ledger_goods[food_item] = 4 * len(self.npcs)
        self.ledger_coins = 40 * len(self.npcs)   # the bank, not just the wage float
        if self.is_capital:
            # A KICKSTART, GIVEN ONCE AT THE FOUNDING. Ten muskets and thirty
            # rounds apiece, so that a crown can put a first column in the
            # field and prove its works on the opening day instead of waiting a
            # season for the forge to catch up. AFTER THIS THE ECONOMY MAKES
            # ITS OWN: the mine feeds the forge, the forge feeds the crown, and
            # the world fills up with guns over the days that follow.
            self.ledger_goods["rifle"] = 10
            self.ledger_goods["ammo"] = 10 * economy.AMMO_PER_RIFLE

    def _seed_fields(self, world, now: float) -> None:
        """Put already-growing crops in the fields, so the first harvest is not
        a full crop cycle away."""
        for ctx, cty, kind in self.farm_plots:
            for tx, ty, tkind in self.farm_tiles.get((ctx, cty), ()):
                # A TILE THAT IS ALREADY GRASS IS STILL EMPTY GROUND. This
                # read `plot_at(tx, ty) is not None`, and EVERY field tile in
                # the world already has a plot object -- with kind "grass" --
                # so it skipped all of them and NO village ever began with a
                # crop standing in its fields.
                #
                # The world then started with about six food a head, three
                # days' worth, against a farm that needs till, water and plant
                # on every tile and then 180 seconds of growing before the
                # first loaf. It lost that race on day two and two thirds of
                # everybody died. Not a distribution bug at all: a production
                # bug, and this one line is the whole of it.
                _p = world.plot_at(tx, ty)
                if _p is not None and getattr(_p, "kind", "grass") != "grass":
                    continue
                age = crop.GROW_SECONDS * self._rng.uniform(0.40, 1.10)
                world.set_plot(tx, ty, tkind, now - age)

    def draw_board(self, target, cam_x: float, cam_y: float) -> None:
        """The village notice board in the square."""
        r = self.board.move(int(-cam_x), int(-cam_y))
        post = (96, 68, 42)
        pygame.draw.rect(target, post, (r.left + 7, r.centery - 2, 6, r.bottom - r.centery + 4))
        pygame.draw.rect(target, post, (r.right - 13, r.centery - 2, 6, r.bottom - r.centery + 4))
        panel = pygame.Rect(r.left, r.top, r.w, r.h - 13)
        pygame.draw.rect(target, (154, 110, 62), panel)
        pygame.draw.rect(target, (86, 60, 34), panel, 2)
        for i, (dx, dy, w, hh) in enumerate(((7, 6, 16, 11), (26, 8, 14, 9), (12, 21, 22, 9))):
            sheet = pygame.Rect(panel.left + dx, panel.top + dy, w, hh)
            pygame.draw.rect(target, (234, 228, 210), sheet)
            pygame.draw.rect(target, (168, 158, 140), sheet, 1)

    def forget_killers(self, now: float) -> bool:
        """The village itself lets the story go, on the same thirty-day clock."""
        if not self.killer_since:
            return False
        gone = [i for i, told_at in self.killer_since.items()
                if now - told_at >= FORGET_AFTER or story_cold(i, now)]
        for i in gone:
            self.killer_since.pop(i, None)
            self.killers.discard(i)
        return bool(gone)

    def __getstate__(self):
        state = self.__dict__.copy()
        # THE WOODLOT IS NOT PART OF THE TOWN. It is a list of TREE objects --
        # and a tree carries a sprite, so writing it dragged the whole wood
        # into the world file as raw surfaces. It is rebuilt from the forest
        # on demand, so it never needs writing at all. This is why the world
        # cache failed and every launch paid the full build: my test of that
        # cache never called set_forest, so it pickled a world the real game
        # could not.
        state["_woodlot"] = None
        return state

    def learn_killers(self, ids, now: float, teller=None) -> bool:
        """News of a murderer reaches this village, and everyone in it.

        Returns True if it was news here. The guards and the army standing at
        the gate are told as well -- knowledge does not stop at the fence.
        """
        ids = {i for i in ids if not story_cold(i, now)}
        if not ids:
            return False
        news = bool(ids - self.killers)
        for i in ids:
            if i not in self.killers:
                self.killer_since[i] = now
            # A FIRST-HAND sighting re-dates the story -- a new crime is a new
            # story. Second-hand news never can: without that, a cold rumour
            # would be brought back to life by the next man who mentioned it.
            if teller is None:
                STORY_BORN[i] = now
            elif i not in STORY_BORN:
                STORY_BORN[i] = now
        self.killers |= ids
        for npc in self.npcs:                    # the whole village is told
            if npc.alive:
                npc.learn(ids, now)
        for g in (getattr(self, "guards", None) or ()):    # ...and its guards
            if getattr(g, "alive", False):
                g.learn(ids, now)
        return news

    def defenders(self) -> list:
        """Every man whose job it is to stand and fight for this place."""
        out = [n for n in self.npcs
               if n.defender
               or n.is_commander]
        out += [g for g in (getattr(self, "guards", None) or ())]
        return out

    def provoke(self) -> None:
        """Someone saw something bad: anyone who can fight does, the rest run.

        This used to check npc.weapon, and weapon was set on four guards and
        the commander and nobody else -- so an ordinary villager with an axe in
        his pack watched a murder and ran for it, which is how one man with an
        axe could walk a town flat. Every man who owns a gun or an axe is
        armed here; the man beside him, who owns neither, is a refugee.
        """
        self.provoked = True
        for npc in self.npcs:
            if not npc.alive:
                continue
            if npc.weapon is None:
                npc.weapon = npc.arm()
            if npc.weapon:
                npc.aggro = True
            else:
                npc.panic = 8.0
        for g in getattr(self, "guards", None) or ():
            if g.alive:
                g.hostile = True
                g.aware = True
                g.aware_timer = 30.0

    def update(self, dt: float, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        """THE TOWN'S OWN BUSINESS: its books, its trade, its roster.

        Nothing here belongs to any individual. A man's hunger, his meals, his
        smoking, his tools, his trade run and his death are his own, in
        NPC.tick() -- and he registers himself in village.PEOPLE, so the world
        walks the people once instead of sixty-four towns walking their own.
        """
        self.forget_killers(now)
        day = int(now / economy.DAY_LENGTH)
        self._day = now / economy.DAY_LENGTH
        if day != getattr(self, "_log_day", -1):
            self._log_day = day
            # THE CAPACITY COLUMN IS THE REAL CEILING. It read
            # getattr(self, "_cap", len(self.npcs)) and `_cap` is set NOWHERE
            # in the codebase, so it always fell back to the population and the
            # line printed "alive 77/77" for a town whose capacity was 289. A
            # capital routed down to four people and slowly refilling itself
            # looked exactly like a town at its limit.
            economy._note(
                "day %d  %-14s alive %d/%d  larders %d  granary %d  wood %d  "
                "cold %d/%d  ledger %d  jobs: f%d m%d s%d lg%d tr%d w%d idle%d"
                % (day, self.name, len(self.npcs), self.capacity,
                   sum(economy.food_of(n) for n in self.npcs),
                   sum(self.ledger_goods.get(k, 0) for k in economy.FOOD),
                   sum(n.stock.get("wood", 0) for n in self.npcs),
                   sum(1 for h in self.houses if getattr(h, "warmth", 1.0) <= 0.0),
                   len(self.houses), self.ledger_coins,
                   sum(1 for n in self.npcs if n.farm_plot is not None),
                   sum(1 for n in self.npcs if n.job == "mine"),
                   sum(1 for n in self.npcs if n.job == "smith"),
                   sum(1 for n in self.npcs if n.job == "logger"),
                   sum(1 for n in self.npcs if n.job == "trader"),
                   sum(1 for n in self.npcs if n.defender or n.is_commander),
                   sum(1 for n in self.npcs if not n.job and n.farm_plot is None
                       and not n.defender and not n.is_commander)))
        if not self._seeded and world is not None:
            self._seeded = True
            self._seed_fields(world, now)
        if phase != self._phase:                 # entering a new part of the day
            self._phase = phase
            if phase == "market":
                economy.market(self)             # the town lays on the auction;
                # ...and WHO PAIRS WITH WHOM IS THEIRS. Each man pairs himself
                # in his own tick (NPC._pair_off) when the market comes round,
                # and clears his own state when it ends. The town used to
                # shuffle its people into couples and then reach into all of
                # them to wipe three fields.
        if phase == "market":                    # the auction runs all mid-day
            self._market_timer -= dt
            if self._market_timer <= 0.0:
                self._market_timer = 4.0
                economy.market(self)
        if day != self.duty_day:                 # the watch changes over
            self.duty_day = day
            self._rotate_duty(day)
        economy.pay_wages(self, day)
        economy.tax_day(self, day)     # the day's books are settled
        economy.crown_dues(self, day)  # a village pays its half to the capital
        economy.pay_crown(self, day)   # and the capital pays its King
        economy.tithe_food(self, day)  # a third of the food gain goes up too
        economy.pay_mayor(self, day)   # and the nation pays its mayor
        # EACH TOWN ELECTS ON ITS OWN DAY, EVERY ELECTION_DAYS.
        # `day % ELECTION_DAYS == 0` made EVERY village in the world vote inside
        # the same world tick -- thirty elections, one after another, in a
        # single frame. Each voter costs four regard() calls, so the tick paid
        # for all of them at once and the game hitched once a fortnight. The
        # village's own code shifts its day, so the work spreads across the
        # fortnight and no tick carries more than two or three towns.
        if day > 0 and (day - self.code) % economy.ELECTION_DAYS == 0:
            economy.hold_election(self, day, PLAYER)   # the town chooses, player included
        self.court_day(day)                    # ten days at court, ten at home
        economy.crown_arms_order(self, day)   # and buys the arms for its war
        economy.pay_garrison(self, day)       # the standing army is paid daily
        # (the houses share their own larders now, from their own register)

        # NO LOOP OVER THE PEOPLE. This used to drive every citizen from here --
        # their hunger, their eating, their smoking, their deaths, their dealings
        # -- twenty times a second, from sixty-four nested loops. A man does all
        # of that in NPC.tick() now, and the town is what he calls when he needs
        # the granary, the bank or the order book. The town looks after the town.


    def _rotate_duty(self, day: int) -> None:
        """Every other day a different half of the villagers takes the watch."""
        group = day % 2
        for npc in self.npcs:
            npc.on_duty = False
            npc.duty = "labour"
        pool = [n for n in self.npcs
                if n.alive and not n.is_commander and not n.defender
                and n.farm_plot is None          # farmers keep farming
                and n.workplace is None          # so do miners and smiths
                and n.duty_group == group]
        self._armed = pool[:5]
        for npc in self._armed:
            npc.duty = "armed"
            npc.on_duty = True          # their soldier body stands in for them
        self._assign_duty_bodies()

    def free_post(self, npc) -> None:
        """Let a man give up his trade and his plot.

        Called whenever somebody stops working here -- he flees, he is
        conquered, he settles somewhere else. Without it the workshop keeps a
        .worker pointer at a man who lives in another village, and since he is
        still ALIVE the vacancy is never refilled: the post rots shut.
        """
        for wp in self.workplaces:
            if wp.worker is npc:
                wp.worker = None
        npc.job = None
        npc.workplace = None
        npc.farm_plot = None
        npc.farm_plots = []

    def candidates_for_crown(self) -> list:
        """WHO MAY FIGHT FOR THE CROWN: the sitting King and the nation's mayors.

        Office is the entry ticket. That is what makes a mayoral election the
        first rung of the ladder rather than the whole of it -- win your town
        and you have the right to stand against the King himself.
        """
        out: list = []
        king = getattr(self, "king", None)
        if king is not None and getattr(king, "alive", False):
            out.append(king)
        reg = getattr(self, "registry", None)
        for v in getattr(reg, "villages", ()) or ():
            if getattr(v, "nation", None) != getattr(self, "nation", None):
                continue
            m = getattr(v, "mayor", None)
            if (m is not None and getattr(m, "alive", False)
                    and m not in out):
                out.append(m)
        return out

    def crown(self, npc) -> None:
        """Put the crown on him, and take it off whoever held it.

        The old King is not exiled -- he is a noble again, and may stand at the
        next Test. The crown was never his; the winning of it was.
        """
        old = getattr(self, "king", None)
        if old is not None and old is not npc and getattr(old, "alive", True):
            old.is_king = False
            old.role = None
            if getattr(old, "job", None) == "king":
                old.job = None
                self.free_post(old)
        npc.is_king = True
        npc.role = "King"
        npc.job = "king"
        npc.plaza = (self.x, self.y)
        self.king = npc

    def court_day(self, day: int) -> None:
        """WHERE THE MAYOR IS SUPPOSED TO BE.

        Half the term at the capital, half in his own square. He is not moved
        there -- his plaza is simply set to the right place and _mosey walks
        him, so the journey takes the days it takes. A mayor is exempt from
        every other errand a villager runs (see NPC.tick), so there is nothing
        to drag him home at night and nothing to fight the road.
        """
        # ONCE A DAY, LIKE EVERY OTHER DAILY CALL IN Village.update.
        #
        # This had NO day guard while every sibling beside it (pay_wages,
        # tax_day, crown_dues, pay_mayor...) returns instantly unless the day
        # has changed. So it ran on EVERY Village.update -- 36 villages x 20 Hz
        # = 720 times a second -- and reached self.capital() every time. And
        # capital() caches with `if cached is not None`, which FAILS for a
        # village whose capital is None: it then re-derives the entire nation
        # lattice, nations._capital_cells(SPACING), for every one of those 720
        # calls a second. That was the frame.
        if getattr(self, "_court_day", -1) == day:
            return
        self._court_day = day
        mayor = getattr(self, "mayor", None)
        if mayor is None or not getattr(mayor, "alive", False):
            return
        cap = self.capital()
        if cap is None or cap is self:
            return
        term = economy.MAYOR_DAYS_AT_COURT
        if (day % (term * 2)) < term:
            mayor.plaza = (self.x, self.y)
            mayor.at_court = False
        else:
            mayor.plaza = (cap.x, cap.y)
            mayor.at_court = True

    def staffing(self) -> list:
        """The trades this village needs, one entry per post.

        Read off the village's OWN fields and workshops -- the same slots the
        job assignment deals out -- so a garrison is exactly as big as the
        village it is holding. Not a hard-coded number: a capital needs twice
        the men because it has twice the buildings.
        """
        mult = 2 if self.is_capital else 1
        fixed = len(self.farm_plots) + len(self.workplaces)
        slots = ["farm"] * len(self.farm_plots)
        slots += [wp.kind for wp in self.workplaces]
        slots += ["logger"] * max(LOGGERS_PER_VILLAGE,
                                  len(self.houses) - fixed)
        slots += ["trader"] * (TRADERS_PER_VILLAGE * mult)
        slots += ["defender"] * len(getattr(self, "guards", ()) or ())
        slots += ["commander"]
        return slots

    def _assign_duty_bodies(self) -> None:
        """Hand today's watch bodies to the villagers who are on duty."""
        arms = self._armed
        for i, guard in enumerate(getattr(self, "guards", None) or ()):
            guard.owner = arms[i % len(arms)] if arms else None
        for i, guard in enumerate(getattr(self, "patrol", None) or ()):
            guard.owner = arms[(i + 5) % len(arms)] if arms else None

    def idlers(self) -> list:
        """Men with no trade at all -- hands a nation could put to work."""
        return [n for n in self.npcs
                if n.alive and n.farm_plot is None and n.job is None
                and n.workplace is None and not n.defender
                and not n.is_commander and not n.is_soldier
                and n.refuge is None
                and not n.levied
                and not n.is_mayor]

    def traders(self) -> int:
        """The traders this town OWNS -- the ones on the road included.

        A caravan man is its trader whether he is in the square or three days
        out, and a town that forgot him would hire a replacement and end up
        with six. He is simply not standing in it.
        """
        n = sum(1 for x in self.npcs if x.job == "trader")
        for x in TRAVELLERS:
            if x.village is self and x.job == "trader":
                n += 1
        return n

    def vacancies(self) -> int:
        """How many trades this village is short of hands for.

        Counted off the same fields _fill_vacancies deals out, so the two can
        never disagree about what a full village looks like.
        """
        free = 0
        taken = {n.farm_plot for n in self.npcs if n.farm_plot is not None}
        free += sum(1 for i in range(len(self.farm_plots)) if i not in taken)
        for wp in self.workplaces:
            w: Any = wp.worker
            if w is None or not w.alive or getattr(w, "village", None) is not self:
                free += 1
        fixed = len(self.farm_plots) + len(self.workplaces)
        want = max(LOGGERS_PER_VILLAGE, len(self.houses) - fixed)
        free += max(0, want - sum(1 for n in self.npcs if n.job == "logger"))
        free += max(0, TRADERS_PER_VILLAGE - self.traders())
        return free

    def open_posts(self) -> list:
        """The trades this village is short of hands for, BY NAME, in the order
        the town would hand them out -- plots, then benches, then the woods,
        then the road.

        vacancies() counts them; this lists them, because a notice board has
        to say WHICH work is going, not how many jobs there are. A man cannot
        choose between "three vacancies".
        """
        out: list = []
        taken = {n.farm_plot for n in self.npcs if n.farm_plot is not None}
        out += ["farm"] * sum(1 for i in range(len(self.farm_plots))
                              if i not in taken)
        for wp in self.workplaces:
            w: Any = wp.worker
            if w is None or not w.alive or getattr(w, "village", None) is not self:
                out.append(wp.kind)
        fixed = len(self.farm_plots) + len(self.workplaces)
        want = max(LOGGERS_PER_VILLAGE, len(self.houses) - fixed)
        out += ["logger"] * max(0, want - sum(1 for n in self.npcs
                                              if n.job == "logger"))
        out += ["trader"] * max(0, TRADERS_PER_VILLAGE - self.traders())
        return out

    def hire(self, player, kind: str) -> bool:
        """THE BOARD OFFERS THE TRADE; THE MAN TAKES IT HIMSELF.

        A player is not an NPC: he cannot be handed a farm_plot index and left
        to the village's own machinery, because his hands are his own and his
        day is his own. What he takes instead is the POST -- a trade, a town,
        and the wage that goes with it. He is then a working man of this
        village: paid by it every day, and owing it the working man's tax.

        Until he takes one he is UNEMPLOYED, and an unemployed man owes
        nothing. See board.BoardPanel.tax_due.
        """
        if kind not in self.open_posts():
            return False
        player.job = kind
        player.settled_at = self
        player.village = self
        if getattr(self, "nation", None) is not None:
            player.nation = self.nation
        player.wage = economy.WAGE          # a day's pay for a day's work
        player._pay_day = -1
        return True

    def offer_post(self, npc) -> bool:
        """THE TOWN SAYS WHAT IS FREE; THE MAN TAKES IT.

        Same posts, same order -- plots, then benches, then the woods, then the
        road -- and the same man ends up with the same kind of trade he would
        have. What changed is who does the doing. The town used to pull idle men
        out of a list and put a shovel in their hands; now a man with no post
        asks his town what is going, once a second, and takes it himself.
        """
        if (not npc.alive or npc.job is not None or npc.farm_plot is not None
                or npc.workplace is not None or npc.levied
                or npc.is_mayor or npc.defender
                or npc.is_commander):
            return False
        taken = {n.farm_plot for n in self.npcs if n.farm_plot is not None}
        for i in range(len(self.farm_plots)):
            if i in taken:
                continue
            npc.farm_plot = i
            npc.leaf_farmer = True                 # dual culture: leaf too
            npc.stock["shovel"] = 1
            npc.grade["shovel"] = 0
            npc.tool_uses = economy.TOOL_USES
            return True
        for wp in self.workplaces:
            if (wp.worker is not None and wp.worker.alive
                    and wp.worker.village is self):
                continue                           # a worker who is actually here
            npc.job = wp.kind
            npc.workplace = wp
            wp.worker = npc
            if wp.kind == "smith":
                npc.stock["iron"] = economy.IRON_STOCK // 4
            return True
        fixed = len(self.farm_plots) + len(self.workplaces)
        want = max(LOGGERS_PER_VILLAGE, len(self.houses) - fixed)
        if sum(1 for n in self.npcs if n.job == "logger") < want:
            npc.job = "logger"
            # A WOODSMAN IS GIVEN AN AXE, the same way a farmer is given a
            # shovel eight lines above. He was given the post and nothing else,
            # and _work_woods needs an axe before it will fell anything: it
            # called _swing_tool("axe"), found no tool and no spare, and
            # returned -- so a logger stood at the same tree for the rest of
            # his life, felled nothing, and never gained a point of axe. No
            # woodsman in this world had ever worked.
            npc.stock["axe"] = 1
            npc.grade["axe"] = 0
            npc.tool_uses = economy.TOOL_USES
            return True
        if self.traders() < TRADERS_PER_VILLAGE:
            npc.job = "trader"                     # the caravan must go on
            return True
        return False

    def _fill_vacancies(self) -> None:
        """Kept for the callers that are still town-side (a garrison settling,
        a refugee arriving). It asks each idle man to take a post, in the
        town's own order, so the outcome is what it always was."""
        for npc in list(self.npcs):
            if (npc.alive and npc.job is None and npc.farm_plot is None
                    and npc.workplace is None):
                if not self.offer_post(npc):
                    break

    # _meet_trades() used to live here: the town scanned every villager's
    # trade timer, then scanned the whole village again for each one that
    # fired. Men do that for themselves now -- NPC.tick checks its own timer
    # and looks for a passer-by -- so the town has no loop over its people at
    # all. The nearest win, first-strictly-nearest in list order, is preserved
    # exactly in NPC._passer_by().

    # -- trade runs ----------------------------------------------------------
    def woodlot(self) -> list:
        """The standing trees around the village, staked out once. Trees grow
        back in the same spot as their stump, so this list never goes stale --
        only the felled flag on each tree changes."""
        lot = getattr(self, "_woodlot", None)
        if lot is not None:
            return lot
        lot = []
        if _FOREST is not None:
            rng = random.Random((self.code ^ 0x5EED) & 0xFFFFFFFF)
            seen = set()
            for i in range(24):
                ang = (i / 24.0) * 2.0 * math.pi + rng.uniform(-0.12, 0.12)
                rr = self.radius + 900.0 + rng.uniform(0.0, 1500.0)
                tx = self.x + math.cos(ang) * rr
                ty = self.y + math.sin(ang) * rr
                for tree in _FOREST.near(tx, ty, 300.0):
                    if id(tree) in seen:
                        continue
                    seen.add(id(tree))
                    lot.append(tree)
        self._woodlot = lot
        return lot

    def capital(self):
        """The capital village of this village's nation, or None."""
        cached = self._capital
        if cached is not None:
            return cached
        registry = getattr(self, "registry", None)
        if registry is None or self.is_capital:
            self._capital = self if self.is_capital else None
            return self._capital
        known = getattr(registry, "_cache", None)
        for (gx, gy), idx in nations._capital_cells(SPACING).items():
            if idx == self.nation:
                # A LOOKUP, NEVER A BUILD. The capital is a lattice cell like
                # any other and the world is laid out before the first step --
                # but this called registry.get(), which CONSTRUCTS a town that
                # is not there: forty people, fifty milliseconds, and a new
                # capital nobody asked for, in the middle of a frame.
                self._capital = (known.get((gx, gy)) if known else None)
                return self._capital
        self._capital = None
        return None

    def trade_routes(self):
        """The neighbours that grow something different -- the caravan's world.

        Planned from the cheap biome peek, then LOOKED UP. It used to build
        them: registry.get() constructs a village that is not there, 50-80 ms,
        one route per 1.5 seconds of WALL CLOCK -- so the builds dribbled out
        for ever and the routes never finished while the player was playing.
        Measured, this function was 189 seconds out of 195: 97% of everything.

        The world is laid out on the loading screen. A cell that is not there
        is a loading-screen gap, and this is not the place to fill it -- the
        planner skips it. The list is built once and kept; it changes only when
        the world does, which is what _routes_ready = False is for.
        """
        if (getattr(self, "_routes_ready", False)
                and hasattr(self, "_trade_routes")):
            return self._trade_routes
        if (not hasattr(self, "_route_plan")
                or not hasattr(self, "_trade_routes")):
            self._trade_routes = []
            self._route_plan = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    cx = (self.gx + dx + 0.5) * SPACING
                    cy = (self.gy + dy + 0.5) * SPACING
                    try:
                        food, leaf = biomes.crop_kinds(
                            float(biomes.temperature(cx, cy, self.code)),
                            float(biomes.humidity(cx, cy, self.code)))
                    except Exception:
                        continue
                    if food != self.local_food or leaf != self.local_leaf:
                        self._route_plan.append((self.gx + dx, self.gy + dy))
        registry = getattr(self, "registry", None)
        known = getattr(registry, "_cache", None) if registry is not None else None
        while self._route_plan:
            gx, gy = self._route_plan.pop(0)
            if not known:
                break
            cand = known.get((gx, gy))       # a LOOKUP -- never a build
            if cand is not None and cand is not self:
                self._trade_routes.append(cand)
        self._routes_ready = True
        return self._trade_routes

    def trade_neighbour(self):
        """The nearest village that grows something different -- the one worth
        walking to. Found once and remembered, because it never changes."""
        cached = getattr(self, "_trade_neighbour", None)
        if cached is not None:
            return cached or None
        registry = getattr(self, "registry", None)
        if registry is None:
            return None
        found = None
        for r in range(1, 5):                 # walk outwards a ring at a time
            ring = []
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    cx = (self.gx + dx + 0.5) * SPACING
                    cy = (self.gy + dy + 0.5) * SPACING
                    food, leaf = biomes.crop_kinds(
                        float(biomes.temperature(cx, cy, self.code)),
                        float(biomes.humidity(cx, cy, self.code)))
                    if food != self.local_food or leaf != self.local_leaf:
                        ring.append((dx, dy))
            for dx, dy in ring:               # confirm against the real village
                cand = registry.get(self.gx + dx, self.gy + dy)
                if (cand.local_food != self.local_food
                        or cand.local_leaf != self.local_leaf):
                    found = cand
                    break
            if found is not None:
                break
        self._trade_neighbour = found or False
        return found

    # _pair_social() used to live here: the town shuffled its people into
    # couples and set three fields on every one of them. Men pair themselves
    # in NPC._pair_off() when the market comes round, and clear up after it
    # themselves -- the same evening, arranged by the people having it.

    def alive_count(self) -> int:
        return sum(1 for n in self.npcs if n.alive)

    def can_grow(self, now: float) -> bool:
        """Room for another villager, and things have been peaceful a while.

        AND ROOM IN THE WORLD. capacity is the village's own ceiling; this is
        the world's. Without it a busy year of births across sixty-four towns
        walks the population wherever it likes, and the frame time with it.
        """
        return (self.alive_count() < self.capacity
                and len(PEOPLE) < WORLD_POP_CAP
                and not self.provoked
                and now - self.last_death > PEACE_DELAY)

    def birth(self, parent) -> None:
        """A child is born to a happy pair, if the village has room."""
        partner = parent.bond_partner
        if partner is None or not partner.alive:
            return
        x = (parent.x + partner.x) * 0.5
        y = (parent.y + partner.y) * 0.5
        first = self._name_pool[self._name_i % len(self._name_pool)]
        self._name_i += 1
        name = "%s %s" % (first, self._name_rng.choice(LAST_NAMES))
        baby = NPC(x, y, self._rng.randrange(2 ** 31), name=name,
                   npc_id="npc_%d_%d_b%d" % (self.gx, self.gy, self._births),
                   role=self._rng.choice(ROLES), village=self)
        baby.home_house = parent.home_house
        baby.home_door = parent.home_door
        baby.wear = self._wear
        baby.nation = self.nation
        baby.leaf_item = baby.rng.choice(economy.LEAF)
        baby.team = ("nation", self.nation)
        baby.target = (x, y)
        if parent.home_house is not None:
            parent.home_house.occupants.append(baby)
        self.npcs.append(baby)
        self._births += 1
        for who in (parent, partner):            # they can pair again next evening
            who.bond = 0.0
            who.bond_partner = None
            who.social_target = None

    def stone_chunks(self):
        """Pre-baked plaza/road stones, bucketed by ground chunk (built once)."""
        cached = getattr(self, "_stone_chunks", None)
        if cached is not None:
            return cached
        chunks: dict = {}
        rng = random.Random(self.code & 0xFFFFFFFF)

        def add(x, y, dense):
            key = (int(x // 256.0), int(y // 256.0))
            chunks.setdefault(key, []).append(
                (x, y, rng.randint(4, 9) if dense else rng.randint(3, 7),
                 rng.randint(118, 172)))

        plaza = self.plaza_radius
        for _ in range(int(plaza * plaza / 210.0)):
            a = rng.uniform(0.0, 2.0 * math.pi)
            rr = plaza * math.sqrt(rng.random())
            add(self.x + math.cos(a) * rr, self.y + math.sin(a) * rr, True)
        for road in getattr(self, "roads", ()):
            for (ax, ay), (bx, by) in zip(road, road[1:]):
                seg = math.hypot(bx - ax, by - ay)
                if seg < 1.0:
                    continue
                ux, uy = (bx - ax) / seg, (by - ay) / seg
                steps = max(1, int(seg / 9.0))
                for s in range(steps):
                    t = s / steps
                    px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                    for _ in range(2):
                        off = rng.uniform(-27.0, 27.0)
                        add(px - uy * off, py + ux * off, False)
        self._stone_chunks = chunks
        return chunks

    def random_point(self, rng):
        """A random point in the village disc, avoiding house footprints."""
        for _ in range(16):
            angle = rng.uniform(0.0, 2.0 * math.pi)
            distance = self.radius * math.sqrt(rng.random())
            x = self.x + math.cos(angle) * distance
            y = self.y + math.sin(angle) * distance
            if not any(house.rect.inflate(64, 64).collidepoint(x, y)
                       for house in self.houses):
                return (x, y)
        return (self.x, self.y)


class Villages:
    def __init__(self, seed: int = 20240501) -> None:
        self.seed = seed
        self._cache: dict[tuple[int, int], Village] = {}
        self.trade_active: set = set()    # villages with a trader on the road
        self.trader_deaths = 0            # traders lost, and lost on the road
        self.trader_kills_away = 0

    @property
    def villages(self) -> list:
        """Every village built so far."""
        return list(self._cache.values())

    def get(self, gx: int, gy: int) -> Village:
        village = self._cache.get((gx, gy))
        if village is None:
            village = Village(gx, gy, self.seed)
            village.registry = self
            self._cache[(gx, gy)] = village
        return village

    # NOTE: prefetch() and warm() used to live here. Both laid out a village
    # during play, one per frame, at 50-81 ms each -- a stutter that walked
    # with the player for the first minutes of a game, because the loading
    # screen was not trusted to have built the world. It is: load_world()
    # builds every cell before the first step, and the man is bounded to the
    # world, so nothing is ever made mid-swing again.

    def send_idle(self, now: float) -> int:
        """A nation moves its idle men to the villages short of hands.

        _fill_vacancies only ever looked INSIDE one village, so a town that
        lost its people could never fill a single post again: the player could
        empty a place, wait, and come back thirty days later to find it still
        and silent and nobody coming. A vacancy is the NATION's problem. Its
        idle are put on the road to whatever town is short, which is why the
        world fills back up behind a massacre -- slowly, and with strangers.
        """
        import war as _war
        moved = 0
        by_nation: dict = {}
        for v in self._cache.values():
            by_nation.setdefault(getattr(v, "nation", None), []).append(v)
        # MEN ALREADY WALKING THERE COUNT AS FILLING THE POST. Without this
        # the nation looked at an emptied town every twelve seconds, saw the
        # same thirty-five vacancies -- the men sent last time were still on
        # the road and not yet in its npc list -- and sent another load. A
        # town of thirty-nine ended up with sixty-four.
        incoming: dict = {}
        for walker in TRAVELLERS:
            d = getattr(walker, "refuge", None)
            if d is not None:
                incoming[d] = incoming.get(d, 0) + 1
        for _nation, towns in by_nation.items():
            idle = [n for v in towns for n in v.idlers()]
            if not idle:
                continue
            for v in sorted(towns, key=lambda t: -t.vacancies()):
                if (getattr(v, "battle", False) or getattr(v, "conquered", False)
                        or getattr(v, "chaos", 0.0) > 0.0):
                    continue                      # not while it is being fought over
                v._fill_vacancies()               # its own men first
                need = v.vacancies() - incoming.get(v, 0)
                while need > 0 and idle:
                    npc = idle.pop()
                    if npc.village is v:
                        continue
                    src = npc.village
                    if src is not None and src.vacancies() > 0:
                        continue                  # his own town needs him more
                    npc.refuge = v                # the road is the road
                    npc.refuge_eta = now + (
                        math.hypot(v.x - npc.x, v.y - npc.y)
                        / _war.REFUGEE_SPEED)
                    if src is not None and npc in src.npcs:
                        src.npcs.remove(npc)
                    if npc not in TRAVELLERS:
                        TRAVELLERS.append(npc)
                    incoming[v] = incoming.get(v, 0) + 1
                    moved += 1
                    need -= 1
        return moved

    def visible(self, cam_x: float, cam_y: float, vw: int, vh: int,
                pad: int = 420) -> list[Village]:
        # Villages sit on a coarse lattice, so the cells that intersect the view
        # can be many kilometres away. Only the ones actually near the view are
        # "visible": this keeps the per-frame simulation to the real bubble and
        # stops far villages being generated at all.
        cx = cam_x + vw / 2.0
        cy = cam_y + vh / 2.0
        slack = max(vw, vh) / 2.0 + pad
        x0 = int(math.floor((cam_x - pad) / SPACING))
        x1 = int(math.floor((cam_x + vw + pad) / SPACING))
        y0 = int(math.floor((cam_y - pad) / SPACING))
        y1 = int(math.floor((cam_y + vh + pad) / SPACING))
        out = []
        for gy in range(y0, y1 + 1):
            for gx in range(x0, x1 + 1):
                vx, vy = village_center(gx, gy, self.seed)
                # Each village's OWN reach. Everything that asks "which
                # villages are near here" -- wolves, ore, fences, the sim --
                # must hear the same answer, and a hard-coded village size hid
                # every capital from all of them.
                r = village_radius(gx, gy) + slack
                if abs(vx - cx) <= r and abs(vy - cy) <= r:
                    out.append(self.get(gx, gy))
        return out


def refugees_on_the_road(now: float, soldiers=()) -> tuple:
    """Every refugee has one order: get to safety.  They finish it, or they
    die on the way -- nobody is waiting for them before a village counts as
    taken, and nobody arrives by magic."""
    arrived = died = 0
    for npc in list(TRAVELLERS):
        dest = npc.refuge
        if dest is None:
            TRAVELLERS.remove(npc)
            continue
        caught = None
        for s in soldiers:
            # A NATIONLESS THING IS NOT A FOREIGN ENEMY. This compared
            # `getattr(s, "nation", None) != npc.nation`, and for a WOLF --
            # which has no nation at all -- `None != 2` is True. Every wolf in
            # the world was therefore an enemy of every refugee, and any
            # soldier whose nation had been unset was an enemy of his own
            # people. Now the killer must BE a soldier, WITH a nation, and a
            # DIFFERENT one.
            if (not s.alive or not getattr(s, "hostile", False)
                    or getattr(s, "kind", "") != "soldier"):
                continue
            nat = getattr(s, "nation", None)
            if nat is None or nat == npc.nation:
                continue
            if math.hypot(s.x - npc.x, s.y - npc.y) < 200.0:
                caught = s
                break
        if caught is not None:
            npc.alive = False
            npc.health = 0
            economy._note("CUT DOWN %-16s on the road to %s by a soldier of nation %s"
                  % (npc.name, getattr(dest, "name", "?"),
                     getattr(caught, "nation", "?")))
            npc.die()            # a refugee cut down on the road settles up too:
            died += 1            # off the register, off the road
            continue
        if now >= npc.refuge_eta:
            npc._arrive_refuge(dest, now)
            arrived += 1
    return arrived, died
