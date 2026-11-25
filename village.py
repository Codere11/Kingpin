"""Villages and friendly villagers.

Houses are big, cannot be walked through, block line of sight, and many have a
small tobacco plot in the backyard. Villages sit on a deterministic lattice so
one is always a short walk away.

Each house stores two world rectangles:
    rect        the walls (movement collision)
    sight_rect  walls plus roof overhang (what blocks vision)
"""

from __future__ import annotations

import stats
import effects
import persona
import doctor
import mood

import colorsys
import functools
import math
import random

from typing import Any


import pygame
import face
from palette import rich, dim

import os as _os


def service_carts() -> int:
    """THE SERVICE'S OWN FREE TRADERS -- and nobody else's.

    Nationless traders on the road who are TAGGED AS AGENTS. The rest of the
    trade is just criminals: the crown does not pay a man for smuggling, and
    it never did.
    """
    return sum(1 for n in TRAVELLERS
               if getattr(n, "job", None) == "trader"
               and getattr(n, "nation", None) is None
               and getattr(n, "secret_police", False)
               and getattr(n, "alive", True))


def _note(message: str) -> None:
    """The village log. Cython refused to compile this module for hours over
    THIS NAME -- `gate_tick` called `_note` and nothing declared it, so the
    whole file failed to compile and the stale .so shadowed every edit."""
    try:
        with open(_os.path.expanduser("~/.kingpin_saves/village.log"), "a") as fh:
            fh.write(message + "\n")
    except Exception:
        pass

import fence
import crop
import biomes
import economy
import guns
import items
import industry
import interior
import nations
import quality
import skills
import wildcrop
import physics
import steering
import sound
from combat import friendly_in_line, segment_circle_hit
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
ROOFS = [rich(c) for c in ((150, 76, 58), (122, 98, 74), (98, 106, 122), (156, 116, 74),
         (128, 78, 84), (104, 92, 70))]

WALL = rich((228, 212, 184))
WALL_DARK = rich((150, 128, 100))
STONE = rich((176, 168, 152))
STONE_DARK = rich((118, 112, 98))

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

# WHAT ONE FELLED TREE YIELDS, IN LOGS. 10-30, which was the value before the
# hearths were halved: with a house burning five a day the world needs 3,325
# logs and the woods furnish about twice that, so the village store can hold a
# surplus and economy.monetize() -- which coins the town's own firewood to
# raise the sales tax -- has something to coin. Raising the yield AND halving
# the burn would have been two answers to one question.
FELL_LOGS_MIN = 10            # as it always was
FELL_LOGS_MAX = 30            # as it always was
WORLD_POP_CAP = 1200       # HARD CAP on living people in the whole world
                           # (1000 in the towns + the huts' people and
                           # the free traders: a thousand was excluding
                           # the births it was meant to allow)
TRADERS_PER_VILLAGE = 3    # caravans a village keeps on the road
_FOREST = None             # set once by main, so villages can find their woods
_TRADE_GRID = None         # allocated once, rebuilt per village per step
LOG_CHOP_SECONDS = 3.0    # how long a logger takes to drop one tree
ORCHARD_GROW_SECONDS = 180.0   # a sapling to a full tree, like a wild stump
ARTISAN_BATCH_SECONDS = 4.0   # ten leaf into ten finished goods at the bench
WEAVER_BATCH_SECONDS = 10.0   # five cotton into one bolt of cloth at the loom
SPICEMAN_SECONDS = 60.0      # five chilis into one bottle of sauce at the stall
BIRTH_BOND = 18.0                    # seconds of evening friendship before a child
PEACE_DELAY = 30.0                   # no children until this long after a death
NPC_SWING_SECONDS = 0.30            # a native warrior's swing, drawn as an arc

# THE FLAVOUR TITLES ARE GONE.
#
# There was a list of eight occupations here -- "Gunsmith", "Moonshiner",
# "Sheriff", "Preacher" -- and every man was rolled one AT BIRTH, whether or
# not he ever did it. A GUNSMITH WAS USUALLY A LOGGER AND A MOONSHINER USUALLY
# FARMED. NOTHING IN THE GAME EVER READ IT: `grep -rn "\.role\b" *.py |
# grep -v "\.role = "` returns nothing at all, so the field was write-only,
# and the only thing it ever did was make a dump of the world LIE.
#
# The real trade has two honest sources and both already existed:
# NPC.occupation() -- whose docstring says these titles "describe no work he
# has ever done" -- and observer.job_of(). Use those.

# THE REPUBLIC'S PLACES. Short, plain, Soviet-sounding: a factory town, a
# collective farm, a name off a poster. Nothing quaint and nothing long.
SETTLEMENT_NAMES = ("Kirovsk", "Leninsk", "Stalinsk", "Zavodsk", "Krasnograd",
                    "Pervomaysk", "Oktyabrsk", "Sovetsk", "Komsomolsk",
                    "Trudovoy", "Mirny", "Yasny", "Rassvet", "Zarya", "Iskra",
                    "Rodina", "Pobeda", "Mayak", "Sputnik", "Volna",
                    "Kamenka", "Lipovka", "Beryozovka", "Olkhovka", "Dubovka",
                    "Zelenograd", "Krasnoarmeysk", "Novoselki", "Zarechye",
                    "Bereznyaki")
NATION_COLORS = [rich(c) for c in ((176, 62, 58), (62, 96, 176), (74, 138, 74), (170, 138, 52),
                 (140, 74, 158), (58, 148, 152), (190, 104, 46), (96, 96, 108))]


def village_name(gx: int, gy: int, seed: int = 0) -> str:
    """A settlement's base name. The number is assigned by the registry when
    the settlement is first built; this is just the plain word."""
    return "Settlement"


def is_military(npc) -> bool:
    """DOES THIS MAN WEAR THE CAP?

    Levied soldiers, the town's defenders, anybody on duty with a weapon, and
    the crown's standing army. An agent of the secret service is NOT military
    for this purpose -- unless he is also one of the above.
    """
    if npc is None:
        return False
    if getattr(npc, "is_soldier", False):
        return True
    if getattr(npc, "defender", False):
        return True
    if getattr(npc, "on_duty", False):
        return True
    if getattr(npc, "kind", "") == "soldier":
        return True
    if getattr(npc, "role", "") == "Defender":
        return True
    return False


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


@functools.lru_cache(maxsize=32768)
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
    "work_flash",
    "attack_flash",
    "hurt_flash",
    "sly_flash",
    "bleed",
    "drip_timer",
    "panic",
    "flee",
    "flee_dir",
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


_MOUNT_SPRITE = None


def _mounted_horse():
    """The horse sprite a mounted warrior rides, loaded once and shared."""
    global _MOUNT_SPRITE
    if _MOUNT_SPRITE is None:
        import os
        path = os.path.join(os.path.dirname(__file__), "horse.png")
        try:
            img = pygame.image.load(path).convert_alpha()
            _MOUNT_SPRITE = pygame.transform.smoothscale(img, (64, 64))
        except Exception:
            _MOUNT_SPRITE = None
    return _MOUNT_SPRITE


class NPC:
    # Real class defaults for attributes the code reads with
    # getattr(x, name, D). Every site agrees on D, so the default
    # says the same thing -- and the read can be a direct one.
    is_king: Any = False
    # HOW GOOD HE IS AT CARRYING WHAT THE STATE FORBIDS. Everyone has it: a
    # farmer who has never been searched has 0, a caravan trader who runs the
    # road twice a week has a great deal. It is what a guard's search rolls
    # against, and the player's is the same number by the same law.
    smuggling: Any = 0.0
    # HOW MUCH OF A MAN YOU CAN READ. Everybody has it and nobody starts with
    # it. THE CAP IS THE INTERESTING PART: a villager can get to somewhere
    # between 3 and 8 and no further, and only one in ten of them to the top of
    # that -- a whole town of people who are hard to read and harder to fool.
    social: Any = 0.0
    social_cap: Any = 3.0
    is_mayor: Any = False
    levied: Any = False
    # THE SECRET POLICE. A man can be the chief's, or the chief himself. These
    # are MARKS and nothing more: nothing in the game reads them yet. They are
    # class defaults for the usual reason -- an unpickled save never runs
    # __init__, so a field that is only set in __init__ is a field that is
    # missing after a load.
    secret_police: Any = False
    secret_police_chief: Any = False
    # THE OLD MAN HIMSELF. A mark the drawing reads: grey hair and the
    # moustache. Class default, like every other field here, so a man restored
    # from a save is never missing it.
    is_stalin: Any = False
    # THE FORCES. `militia` is the Narodna militsiya: blue cap, dart rifle.
    # `sleep_t` is a tranquilised man -- on the ground, eyes shut, no death.
    militia: Any = False
    sleep_t: Any = 0.0
    shackled: Any = False
    # A MAN CAN BE WANTED BY A TOWN (the gate search writes this). Class
    # default, because a search that never caught anybody would otherwise
    # leave the field absent and the first reader would raise.
    wanted: Any = False
    # A MAN HIRED BY THE PLAYER: his trade, his wage, and whose he is.
    player_worker: Any = False
    aggro_at: Any = None
    attacked_flash: Any = 0.0
    # WHAT THE PLAYER TOLD *HIM*: the id of every order and handoff he holds.
    # A list, so it saves; secret by construction -- nobody else is given it.
    player_orders: Any = None
    _gate_try: Any = 0
    _stuck_t: Any = 0.0
    _detour: Any = None
    wage: Any = 0
    # WHERE HIS WORK IS: a point in the player's yard. A man hired by the
    # player walks to it and stays there -- he has left his town's day behind.
    work_post: Any = None
    # his work at the player's post: what he carries, how far his batch has
    # got, and the last thing he would tell the player about it
    stock: Any = None
    say: Any = None
    work_timer: Any = 0.0
    said_none: Any = False
    made_guns: Any = 0
    # SECRET NEWS. A list of fact ids he has been trusted with (see
    # nemesis.issue). A list, not a set: the save writer only carries simple
    # values, and a set is not one -- it would be silently dropped on load.
    secret_news: Any = None
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
    # work_flash is NOT here on purpose. It is a `cdef public double` in
    # village.pxd -- a C struct member, because it is read and written for
    # every man every frame and a dict lookup is what that file exists to
    # kill. A double and this class both default it to 0.0, so nothing
    # changes, and hit_flash (its twin) is declared exactly the same way.
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

    # -- THE MIND (NPC.md).  Plain data, saved automatically by save/people.
    # Mutable defaults are None on purpose: a list or dict on the class would
    # be shared by every person in the world.  persona.ensure() normalises
    # them to [] / {} for old saves and new people alike.
    mbti: Any = ""
    traits: Any = None
    traits_rolled: Any = False
    trauma_points: Any = 0.0
    medicines_received: Any = 0
    mental_known: Any = False
    mood_thoughts: Any = None
    mood_target: Any = 50.0
    # CONSUMPTION IS NOT A BREAK.  One drink or smoke is an activity; enough
    # of them lower the threshold and eventually become their own state.
    drunk_level: Any = 0.0
    high_level: Any = 0.0
    # The trader's own errand: idle -> collecting -> sailing -> paying.
    trader_state: Any = "idle"
    trader_coin: Any = 0.0
    trader_t: Any = 0.0
    # WHO HE REMEMBERS: the player and up to nine other people.  None is the
    # lazy empty state; relationships.ensure() creates the dict on first use.
    social_memory: Any = None
    break_state: Any = "normal"
    break_until: Any = 0.0
    break_cooldown: Any = 0.0
    frustration: Any = 0.0

    _break_off: Any = 0.0        # consumption raises his breaking point
    _break_off_until: Any = 0.0   # ...and it wears off three minutes later
    _consume_mood_off: Any = 0.0  # the mood the fix added, to remove on expiry
    _seller_of: Any = None        # luxury -> the man who sold it to him

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
        # ONE BODY FOR EVERYBODY, INCLUDING MEN ALREADY IN AN OLD SAVE. Their
        # bodies were written down when a villager had forty health; the extra
        # body is added to what is left of them, so a wounded man stays wounded.
        _cap = stats.PLAYER_MAX_HEALTH
        _old = getattr(self, "max_health", _cap) or _cap
        if _old != _cap:
            self.health = min(_cap, float(getattr(self, "health", _cap)) + (_cap - _old))
            self.max_health = _cap


    def __init__(self, x: float, y: float, seed: int, name: str = "",
                 npc_id: str = "", role: str = "Villager", village=None) -> None:
        self.rng = random.Random(seed & 0xFFFFFFFF)
        self.name = name
        self.id = npc_id
        PEOPLE.append(self)          # he exists, so he is in the register
        self.role = role
        # A NUMBER FOR EVERYONE. Traders learn it on the road, hub folk learn
        # it by necessity, and a man with a fixed post mostly never needs it.
        self.smuggling = 0.0
        self.social = 0.0
        # ONE IN TEN gets to be as good at this as a villager can be.
        self.social_cap = (8.0 if self.rng.random() < 0.10
                           else self.rng.uniform(3.0, 7.4))
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
        self.pause = self.rng.uniform(0.1, 0.5)
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
        # THE PLAYER'S BODY IS THE STANDARD (see stats.py).
        self.max_health = stats.PLAYER_MAX_HEALTH
        self.health = self.max_health
        self.alive = True
        self.mood = 50.0             # 0 = miserable, 100 = bliss; everyone starts at 50
        self.hit_flash = 0.0
        self.work_flash = 0.0
        self.attack_flash = 0.0
        self.swing_anim = 0.0           # a visible weapon sweep (native warriors)
        self.hurt_flash = 0.0
        self.level_flash = 0.0         # the same shine as the player's level-up
        self.sly_flash = 0.0
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
        self.conquered = False        # 'Unconquered' until the player claims him
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
        self.orchard_plot = None     # fixed orchard the logger works
        self._field_task = None      # cached field task, so the scan runs once per action
        self.carry = {}              # surplus he is walking to the chest
        self.carry_grade = {}        # the grade of each carried item
        self.job = None              # "miner" / "smith" / "gunsmith" / "logger"
        self.workplace = None
        self.gunsmith_product = None   # what this gunsmith makes (set by the player)
        self.smith_product = None      # what this smith makes (set by the player)
        self.mounted = False           # a native warrior riding a horse (4th alarm)
        self.reinforced_armor = False  # a bought soldier in reinforced armor
        self.raiding = False           # a native warrior marching on a raid
        self.raid_target = None        # (x, y) the raid is heading for
        self.escort_horse = None       # the cargo horse a soldier rides escort for
        self.produce_acc = 0.0
        self.chop_timer = 0.0
        self._log_tree = None
        self._trunks_cache = None    # cached orchard trunk rects (steering)
        self._trunks_dirty = True
        self._trunks_tick = 0
        self._orchard_task = None    # cached (cut_tile, plant_tile) decision
        self._orchard_task_tick = -999
        self.schedule = "home"       # time-of-day phase right now
        self.bond_partner = None     # who they walk out with in the evening
        self.bond = 0.0              # growing affection
        self.social_target = None
        self._interior_rect = None
        self._interior_colliders = ()
        self.aggro = False
        # A BURST OF SPEED AT A DECISION, not a reflex: seconds of lunge left,
        # and the clock on the next one. Same name as the wolf's, so a man
        # facing a lunge can react to it (`target.lunging` in _fight).
        self.lunging = 0.0
        self.lunge_cd = 0.0
        self.attacked_flash = 0.0     # he swung a moment ago
        # THE MEN HE IS FIGHTING, BY NAME: id(man) -> the man. A feud is with
        # a person, not with "whatever is nearest".
        self.aggro_at: dict = {}
        self.attack_cd = self.rng.uniform(0.3, 0.8)
        self.combat_speed = self.rng.uniform(120.0, 160.0)
        self.strafe_dir = self.rng.choice((-1.0, 1.0))
        self.baby = False             # a newborn, grows up over a day
        self.born_at = 0.0
        self.breeding = False         # facing a mate, hearts in the eyes
        self.breed_partner = None
        self.bedroll = None           # the bedroll tile this person sleeps on
        economy.setup(self)          # goods, coin, hunger, craving, duty
        self._trade_timer = self.rng.uniform(0.5, 2.5)
        # DETERMINISTIC TYPE. The id is stable across loads, so this is the
        # same letters every time; it is not a live-RNG draw.
        persona.ensure(self)

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
        """A villager's round is a soldier's round: `guns.DAMAGE`, 80."""
        _dmg = guns.DAMAGE[self.gun_kind]
        for _ in range(guns.PELLETS[self.gun_kind]):
            a = angle + self.rng.uniform(-0.07, 0.07)
            combat.fire(x, y, a, distance, owner="enemy",
                        damage=_dmg, team=self.team)
        self._snd("shot_rifle" if self.gun_kind == guns.RIFLE else "shot_musket")

    def add_threat(self, who) -> bool:
        """HE KNOWS WHO HIT HIM. One entry per man, added ONCE.

        Returns True when this is a new enemy, so the caller can log the start
        of a feud rather than repeating it sixty times a second.
        """
        if who is None or who is self:
            return False
        if not isinstance(getattr(self, "aggro_at", None), dict):
            self.aggro_at = {}
        key = id(who)
        if key in self.aggro_at:
            return False
        self.aggro_at[key] = who
        self.aggro = True
        self.panic = 0.0
        return True

    def drop_threat(self, who) -> None:
        """THE FEUD IS OVER when that specific man is dead or gone."""
        d = getattr(self, "aggro_at", None)
        if isinstance(d, dict):
            d.pop(id(who), None)
        self.aggro = bool(d)

    def threat_list(self) -> list:
        """The men he is actually fighting -- dead ones dropped as they go."""
        d = getattr(self, "aggro_at", None)
        if not isinstance(d, dict):
            self.aggro = False
            return []
        for key, who in list(d.items()):
            if who is None or not getattr(who, "alive", True):
                d.pop(key, None)
        self.aggro = bool(d)
        return list(d.values())

    def _body_follows_skill(self) -> None:
        """A man who has learned his trade has the body to show for it."""
        try:
            stats.apply_body(self)
        except Exception:
            pass

    def tranq(self, seconds: float = 22.0) -> None:
        """A DART, NOT A BULLET: he does not die, he lies down."""
        self.sleep_t = float(seconds)
        self.health = max(1, int(self.health))
        self.bleed = 0.0
        self.panic = 0.0
        self.attacked = False
        try:
            import plog
            plog.log("TRANQ", getattr(self, "name", "?"), "asleep")
        except Exception:
            pass

    def wake_and_flee(self, threat=None) -> None:
        """Leave the bedroll and run from whatever just hit him."""
        self.asleep = False
        self.sleep_t = 0.0
        self.in_interior = False
        self.bed = None
        self._ground_spot = None
        self._wake_awake = True       # do not lie straight back down tonight
        self._wake_flee = True
        self.panic = max(float(getattr(self, "panic", 0.0)), 9.0)
        self.attacked = True
        self._dir = None
        if threat is not None:
            dx = float(getattr(self, "x", 0.0)) - float(getattr(threat, "x", 0.0))
            dy = float(getattr(self, "y", 0.0)) - float(getattr(threat, "y", 0.0))
            d = math.hypot(dx, dy)
            if d < 0.01:
                dx, dy, d = 1.0, 0.0, 1.0
            a = math.atan2(dy / d, dx / d) + self.rng.uniform(-0.65, 0.65)
            self.flee_dir = (math.cos(a), math.sin(a))
        else:
            a = self.rng.uniform(0.0, 2.0 * math.pi)
            self.flee_dir = (math.cos(a), math.sin(a))
        try:
            import plog
            plog.log("WAKE", getattr(self, "name", "?"),
                     "attacked while asleep",
                     "from", getattr(threat, "name",
                                     getattr(threat, "kind", "?")))
        except Exception:
            pass

    def _run_from_attack(self, dt: float) -> None:
        """Panic flight that does not need a known town threat object."""
        self.panic = max(0.0, float(getattr(self, "panic", 0.0)) - dt)
        if self.panic <= 0.0 or not getattr(self, "flee_dir", None):
            self._wake_flee = False
            self.flee_dir = None
            return
        fx, fy = self.flee_dir
        if not fx and not fy:
            fx, fy = 0.0, 1.0
        speed = max(120.0, float(getattr(self, "base_speed", 50.0)) * 1.8)
        self.x += fx * speed * dt
        self.y += fy * speed * dt
        self.facing = (fx, fy)
        self.moving = True
        try:
            self.skills.gain_movement(speed * dt)
        except Exception:
            pass

    def take_damage(self, amount: int, record: bool = True,
                    tranq: bool = False, attacker=None) -> bool:
        # THE TRUTH-TELLER DOES NOT BLEED. He used to hold a million
        # health to stand in for that, which made one villager's body a
        # lie; the rule is here instead.
        if getattr(self, "is_truth_teller", False):
            return False
        if tranq:
            # SAME DAMAGE, SAME ARITHMETIC -- only the last point differs: a
            # dart that would have killed him puts him to sleep instead.
            self.health = int(self.health) - int(amount)
            if self.health <= 0:
                self.health = 1
                self.tranq()
            return False
        # A DEAD MAN IS NOT KILLED AGAIN. Without this every further blow on a
        # body re-ran the death branch: the same man was "SLAIN" over and over
        # (measured: 487 lines for a handful of people) and `die()` was called
        # as many times.
        if not getattr(self, "alive", True) or getattr(self, "dead", False):
            return True
        # A BLOW WAKES A SLEEPING MAN.  Before this, a wolf could stand over
        # a sleeping villager and chew through him while the body stayed in
        # the sleep branch -- closed eyes, no panic, no movement.  Wake first,
        # then take the wound, then run in the opposite direction.
        if getattr(self, "asleep", False):
            self.wake_and_flee(attacker)
        self.health -= amount
        try:
            persona.add_trauma(self, amount)
        except Exception:
            pass
        self._snd("npc_hurt")
        self.hit_flash = 0.15
        self.hurt_flash = face.HURT_SECONDS   # and his face says so
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
            if not record:
                # THE FRAME'S COPY DIES TOO, and it used to write a second
                # SLAIN line for the same man on the same blow -- the lane's
                # copy is the one that keeps the record.
                self.die()
                return not self.alive
            try:
                import economy as _e
                _e._note("SLAIN    %-16s of %-14s by %d damage (health %d)"
                         % (self.name, getattr(getattr(self, "village", None),
                                               "name", "?"), amount,
                            max(0, self.health)))
            except Exception:
                pass
            try:
                import deaths
                deaths.record(self, "KILLED BY A BLOW", detail="%d damage" % amount)
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
        # THE WORKING FACE RUNS DOWN HERE. It is raised by a work action and
        # not by the working day, so a man wears it while his hands are busy
        # and loses it the moment they stop -- which is what makes it a
        # transition rather than a uniform.
        if self.work_flash > 0.0:
            self.work_flash -= dt
            if self.work_flash < 0.0:
                self.work_flash = 0.0
        # ...and the war face, on the same terms.
        if self.attack_flash > 0.0:
            self.attack_flash -= dt
            if self.attack_flash < 0.0:
                self.attack_flash = 0.0
        if self.swing_anim > 0.0:
            self.swing_anim -= dt
            if self.swing_anim < 0.0:
                self.swing_anim = 0.0
        if self.hurt_flash > 0.0:
            self.hurt_flash -= dt
            if self.hurt_flash < 0.0:
                self.hurt_flash = 0.0
        if self.sly_flash > 0.0:
            self.sly_flash -= dt
            if self.sly_flash < 0.0:
                self.sly_flash = 0.0
        # A REAL LEVEL-UP WEARS THE SAME SHINE AS THE PLAYER'S: the skills
        # raise just_leveled, and this wears it off over 1.6 seconds.
        if getattr(self.skills, "just_leveled", False):
            self.skills.just_leveled = False
            self.level_flash = 1.6
        if self.level_flash > 0.0:
            self.level_flash -= dt
            if self.level_flash < 0.0:
                self.level_flash = 0.0
        # THE MAN'S MIND: the spree, the brawl, the chat -- one place now.
        try:
            import mind as _mind
            _mind.step(self, now, dt,
                       self.village.npcs if self.village is not None else (),
                       combat)
        except Exception:
            pass
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
        if not economy.needs(self, dt, now):
            self.die()               # starved
            return False
        # MOOD, ONCE EVERY TWO SECONDS.  The timer is per man, so hundreds of
        # people do not become hundreds of per-frame thought updates.
        try:
            mood.tick(self, now, dt)
        except Exception:
            pass
        try:
            self._break_action(dt, combat, now)
        except Exception:
            pass
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
        # A NATIVE WARRIOR DOWN: if he was the last, the camp is conquered and
        # its farmers join the player's workforce.
        if getattr(self, "native_role", "") == "warrior":
            camp = getattr(self, "native_camp", None)
            if (camp is not None
                    and not getattr(camp, "conquered", False)
                    and not getattr(camp, "lab", False)):
                warriors = getattr(camp, "warriors", None) or ()
                if warriors and all(not getattr(w, "alive", True) for w in warriors):
                    try:
                        g = getattr(camp, "g", None)
                        if g is not None:
                            import colony as _colony
                            _colony.conquer_camp(g, camp)
                    except Exception:
                        pass
        # A NATIVE (OR CONQUERED) PERSON LEAVES A BODY: the X-eyed corpse,
        # lootable, exactly like the old world's dead.
        if getattr(self, "native", False):
            camp = getattr(self, "native_camp", None)
            g = getattr(camp, "g", None) if camp is not None else None
            if g is not None:
                # WITNESSES CARRY THE DEATH. One pass on death only, never
                # per frame; only nearby living people accumulate trauma.
                try:
                    for _w in list(getattr(g, "_native_people", ()) or ()):
                        if _w is self or not getattr(_w, "alive", True):
                            continue
                        if ((_w.x - self.x) ** 2 + (_w.y - self.y) ** 2
                                <= 520.0 ** 2):
                            persona.add_trauma(_w, 10)
                except Exception:
                    pass
                try:
                    import corpse as _corpse
                    _corpse.spawn(self.x, self.y, getattr(self, "name", "a native"),
                                  float(getattr(g, "now", 0.0)),
                                  tuple(getattr(self, "clothing", (150, 110, 70))),
                                  dict(getattr(self, "stock", {}) or {}),
                                  dict(getattr(self, "grade", {}) or {}),
                                  tuple(getattr(self, "facing", (0.0, 1.0))))
                except Exception:
                    pass
        # A CONQUERED WORKER'S DEATH FREES HIS POST: the sign-post count for
        # his job drops, and he leaves every bucket that held him.
        if getattr(self, "native", False):
            camp = getattr(self, "native_camp", None)
            g = getattr(camp, "g", None) if camp is not None else None
            if getattr(self, "conquered", False):
                job = getattr(self, "job", None)
                if g is not None and job:
                    _attr = {"farmer": "farmers", "logger": "loggers",
                             "artisan": "artisans", "researcher": "researchers",
                             "doctor": "doctors", "trader": "traders",
                             "miner": "miners", "smith": "smiths",
                             "weaver": "weavers", "spiceman": "spicemen",
                             "gunsmith": "gunsmiths"}.get(job)
                    if _attr:
                        for _s in getattr(g, "built_signs", ()) or ():
                            _n = int(getattr(_s, _attr, 0) or 0)
                            if _n > 0:
                                setattr(_s, _attr, _n - 1)
                                break
                for _bucket in ("workers", "loggers", "artisans", "researchers",
                                "doctors", "traders", "miners", "smiths",
                                "weavers", "spicemen", "gunsmiths",
                                "unemployed", "people"):
                    _lst = getattr(camp, _bucket, None) if camp is not None else None
                    if _lst and self in _lst:
                        try:
                            _lst.remove(self)
                        except ValueError:
                            pass
                self.job = None
                self.native_role = "unemployed"
            # every native -- worker or soldier -- leaves the frame's register
            # and draw list, so the dead are never ticked or drawn again.
            if g is not None:
                for _reg in ("_native_people", "_observe_npcs"):
                    _lst = getattr(g, _reg, None)
                    if _lst and self in _lst:
                        try:
                            _lst.remove(self)
                        except ValueError:
                            pass

    def _walk_toward(self, tx: float, ty: float, speed: float, dt: float) -> None:
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy) or 1.0
        step = min(d, speed * dt * mood.move_mult(self))
        self.x += dx / d * step
        self.y += dy / d * step
        if d > 0.5:
            self.facing = (dx / d, dy / d)

    def _line_blocked(self, g, x0, y0, x1, y1) -> bool:
        """True if anything solid stands between the bowman and the player."""
        try:
            from physics import segment_rect_hit
            for r in getattr(g, "occluders", ()) or ():
                if segment_rect_hit(x0, y0, x1, y1, r):
                    return True
        except Exception:
            pass
        return False

    def _native_bowman_step(self, dt: float, player, combat, g) -> None:
        """A bowman: keep his distance, step around anything in the way, and
        loose one arrow a second at the player."""
        dx, dy = player.x - self.x, player.y - self.y
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        self.facing = (ux, uy)
        preferred = 220.0
        blocked = self._line_blocked(g, self.x, self.y, player.x, player.y)
        self.attack_cd -= dt
        if not blocked:
            # one arrow a second, at the axe's own damage
            if self.attack_cd <= 0.0:
                self.attack_cd = 1.0
                self._did_attack()
                self._snd("warrior_attack", min_gap=2.0)
                self.skills.gain_axe()
                dmg = max(1, round((35.0 / 3.0) * self.skills.axe_damage_scale()))
                if combat is not None:
                    combat.fire(self.x + ux * 16.0, self.y + uy * 16.0,
                                math.atan2(dy, dx), dist + 80.0,
                                owner="enemy", damage=dmg, team=self.team)
                    self._snd("shot_bow")
        # KEEP THE GAP, AND CLEAR THE LINE: back off when he is too close,
        # close in when too far, and strafe around whatever blocks the shot.
        if dist < 170.0:
            self.x -= ux * self.combat_speed * dt
            self.y -= uy * self.combat_speed * dt
        elif dist > 260.0:
            self.x += ux * self.combat_speed * dt
            self.y += uy * self.combat_speed * dt
        elif blocked:
            px, py = -uy, ux
            self.x += px * self.combat_speed * 0.8 * dt
            self.y += py * self.combat_speed * 0.8 * dt
        else:
            # in range with a clear shot: sidestep a little, never stand still
            px, py = -uy, ux
            self.x += px * self.combat_speed * 0.25 * dt
            self.y += py * self.combat_speed * 0.25 * dt

    def _native_step(self, dt: float, world=None, now=None) -> None:
        """A native warrior's step: patrol a ring around the fire, and the
        hungry are fed from the camp's store. If the player walks into the
        camp's reach the warrior fights him -- until the camp is conquered."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            return
        self._native_share()
        # HOSTILE TO AN INTRUDER: an unconquered camp defends itself.
        if (not getattr(camp, "conquered", False)
                and not getattr(camp, "lab", False)):
            g = getattr(camp, "g", None)
            if g is not None:
                _spot = 320.0 if getattr(self, "weapon", None) == "bow" else 260.0
                target = None
                best = _spot * _spot
                player = getattr(g, "player", None)
                if (player is not None and getattr(player, "alive", True)
                        and not getattr(player, "dead", False)):
                    _d2 = (player.x - self.x) ** 2 + (player.y - self.y) ** 2
                    if _d2 < best:
                        best, target = _d2, player
                # A WARRIOR FIGHTS A SOLDIER TOO, whoever is nearer.
                for _n in getattr(g, "_native_people", ()) or ():
                    if (not getattr(_n, "alive", True)
                            or getattr(_n, "native_role", "") != "soldier"):
                        continue
                    _d2 = (_n.x - self.x) ** 2 + (_n.y - self.y) ** 2
                    if _d2 < best:
                        best, target = _d2, _n
                # ON A RAID HE ALSO FALLS ON THE WORKERS AND CARGO HORSES.
                if getattr(self, "raiding", False):
                    for _n in getattr(g, "_native_people", ()) or ():
                        if (not getattr(_n, "alive", True)
                                or not getattr(_n, "conquered", False)
                                or getattr(_n, "native_role", "") == "soldier"):
                            continue
                        _d2 = (_n.x - self.x) ** 2 + (_n.y - self.y) ** 2
                        if _d2 < best:
                            best, target = _d2, _n
                    for _h in getattr(g, "horses", ()) or ():
                        if not getattr(_h, "alive", True) or not getattr(_h, "conquered", False):
                            continue
                        _d2 = (_h.x - self.x) ** 2 + (_h.y - self.y) ** 2
                        if _d2 < best:
                            best, target = _d2, _h
                if target is not None:
                    # THE CONFLICT STARTS: a smoke signal rises from the
                    # fire, once, the moment a warrior spots the player --
                    # and every settlement arms its bowmen.
                    if not getattr(camp, "conflict", False):
                        camp.conflict = True
                        _fire = getattr(camp, "fireplace", None)
                        _smoke = getattr(g, "smoke", None)
                        if _fire is not None and _smoke is not None:
                            try:
                                _smoke.signal(float(_fire.x), float(_fire.y))
                            except Exception:
                                pass
                        try:
                            import native as _nat
                            _nat.escalate_war(g, exclude=camp)
                        except Exception:
                            pass
                    if getattr(self, "weapon", None) == "bow":
                        self._native_bowman_step(dt, target,
                                                 getattr(g, "combat", None), g)
                    else:
                        self._fight(dt, target, getattr(g, "combat", None))
                    return
        # MARCHING ON A RAID: walk to the target when nothing is in reach.
        if getattr(self, "raiding", False) and getattr(self, "raid_target", None) is not None:
            _tx, _ty = self.raid_target
            if math.hypot(_tx - self.x, _ty - self.y) > 24.0:
                self._walk_toward(_tx, _ty, getattr(self, "speed", 60.0), dt)
            else:
                # arrived and nothing to fight: the raid is spent, go home.
                self.raiding = False
                self.raid_target = None
            return
        speed = getattr(self, "speed", 60.0)
        ang = getattr(self, "_orbit", 0.0) + 0.30 * dt
        self._orbit = ang
        r = 4.0 * TILE
        self._walk_toward(camp.x + math.cos(ang) * r,
                          camp.y + math.sin(ang) * r, speed, dt)

    def _native_share(self) -> None:
        """The hungry are fed from the camp's store; the fed share what they
        have. One loaf at a time, so nobody hoards while another starves."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            return
        store = getattr(camp, "ledger_goods", None)
        if not isinstance(store, dict) or not store:
            return
        if getattr(self, "hunger", 0.0) > 55.0:
            for item, qty in list(store.items()):
                if qty <= 0:
                    continue
                store[item] = qty - 1
                self.stock[item] = self.stock.get(item, 0) + 1
                self.hunger = max(0.0, getattr(self, "hunger", 0.0) - 8.0)
                self.mood = min(100.0, getattr(self, "mood", 50.0) + 2.0)
                break

    def _camp_people(self):
        """Everyone who lives in this settlement, for the farmer to feed."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            return []
        people = getattr(camp, "people", None)
        if isinstance(people, list):
            return [p for p in people if getattr(p, "alive", True)]
        out = []
        seen = set()
        for attr in ("farmers", "warriors", "handlers", "workers", "loggers",
                     "artisans", "researchers", "doctors", "traders",
                     "miners", "smiths", "weavers", "spicemen",
                     "gunsmiths", "unemployed"):
            for p in (getattr(camp, attr, ()) or ()):
                if getattr(p, "alive", True) and id(p) not in seen:
                    seen.add(id(p))
                    out.append(p)
        return out

    def _snd(self, name: str, volume: float = 1.0,
             min_gap: float = 0.0) -> None:
        """Play a world sound ONLY if this man is on the player's screen."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            return
        sound.play_on_screen(name, self.x, self.y, g.cam_x, g.cam_y,
                             g.vw, g.vh, volume=volume, min_gap=min_gap)

    def _distribute_food(self, dt: float) -> bool:
        """A farmer with a full pack feeds the settlement FIRST: four of the
        food to each person, walked one by one -- and ONE delivery of four is
        DONE. He does not chase a man down again because that man ate one of
        his four. Only when everyone has been delivered to does the remainder
        go to the chest (the horse's larder)."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            return False
        food_item, best, total = None, 0, 0
        for item in economy.FOOD:
            n = int(self.carry.get(item, 0) or 0)
            total += n
            if n > best:
                best, food_item = n, item
        if food_item is None:
            return False
        if not getattr(self, "_feeding_round", False):
            if total < 40:
                return False                 # the pack is not full yet
            self._feeding_round = True
            self._fed_round = set()          # who already got their four
        fed = getattr(self, "_fed_round", set())
        people = [p for p in self._camp_people()
                  if p is not self and id(p) not in fed]
        if not people or int(self.carry.get(food_item, 0) or 0) < 4:
            self._feeding_round = False
            self._fed_round = set()
            self._feeding_done = True        # everyone fed (or pack spent)
            return False
        p = min(people, key=lambda q: (q.x - self.x) ** 2 + (q.y - self.y) ** 2)
        if math.hypot(p.x - self.x, p.y - self.y) > 20.0:
            self._step_toward(p.x, p.y, dt)
            return True
        # THE RECEIVER'S EXISTING OPINION MATTERS.  At neutral it is exactly
        # 50/50; a friend is more likely to thank him, an enemy to complain or
        # refuse.  A starving man still takes the food.
        _accepted = True
        try:
            import relationships as _rel
            _accepted = _rel.share_reaction(
                p, self, "shared_food", float(getattr(camp.g, "now", 0.0)),
                camp.g, item=food_item)
        except Exception:
            pass
        if not _accepted:
            fed.add(id(p))
            self._did_work()
            return True
        p.stock[food_item] = int(getattr(p, "stock", {}).get(food_item, 0)) + 4
        self.carry[food_item] = int(self.carry.get(food_item, 0)) - 4
        if self.carry.get(food_item, 0) <= 0:
            self.carry.pop(food_item, None)
        fed.add(id(p))
        self._did_work()
        return True

    def _camp_chest(self):
        """The nearest chest that will take what he carries. A chest with a
        lid filter only takes its one kind; an 'Any' chest takes everything."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None)
        chests = getattr(g, "built_chests", None) if g is not None else None
        if not chests:
            return None
        carry = getattr(self, "carry", {}) or {}
        def _accepts(c):
            f = getattr(c, "filter", None)
            if f is None:
                return True
            return carry.get(f, 0) > 0
        ok = [c for c in chests if _accepts(c)]
        if not ok:
            return None                 # no chest will take any of it
        return min(ok, key=lambda c: (c.x - self.x) ** 2 + (c.y - self.y) ** 2)

    def _deposit_to_chest(self, dt: float) -> bool:
        """Carry the day's surplus to the chest and put it in, physically.
        Returns True while he is on the way or stowing it. A filtered chest
        only takes its own kind; the rest stays in the pack for another chest."""
        carry = getattr(self, "carry", None)
        if not carry:
            return False
        chest = self._camp_chest()
        if chest is None:
            return False                 # no chest built: keep it in the pack
        if math.hypot(chest.x - self.x, chest.y - self.y) > 22.0:
            self._step_toward(chest.x, chest.y, dt)
            return True
        inv = getattr(chest, "inventory", None)
        f = getattr(chest, "filter", None)
        if inv is not None:
            grades = getattr(self, "carry_grade", {}) or {}
            for item, n in list(carry.items()):
                if f is not None and item != f:
                    continue             # this chest only takes its one kind
                g = grades.get(item)
                _def = items.get(item)
                if getattr(_def, "quality", False) and g is not None:
                    inv.add(item, int(n), quality=int(g))
                else:
                    inv.add(item, int(n))
                carry.pop(item, None)
                grades.pop(item, None)
        if not carry:
            self._did_work()
        return True

    def _take_ingredient(self, item: str, need: int, dt: float) -> bool:
        """Take from the camp ledger first, then a chest.

        True means the doctor should return this frame (walking or picking up).
        """
        if need <= 0:
            return False
        camp = getattr(self, "native_camp", None)
        store = getattr(camp, "ledger_goods", None) if camp is not None else None
        if isinstance(store, dict) and int(store.get(item, 0) or 0) > 0:
            got = min(need, int(store[item]))
            store[item] = int(store[item]) - got
            self.carry[item] = int(self.carry.get(item, 0) or 0) + got
            need -= got
            if need <= 0:
                return False
        chest = self._chest_with(item, need)
        if chest is None:
            return False
        if math.hypot(chest.x - self.x, chest.y - self.y) > 20.0:
            self._step_toward(chest.x, chest.y, dt)
            return True
        taken, _grade = self._take_from_chest(chest, item, need)
        if taken > 0:
            self.carry[item] = int(self.carry.get(item, 0) or 0) + taken
            return True
        return False

    def _chest_accepting(self, item: str):
        """The nearest chest whose filter is None ('Any') or this item."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None)
        chests = getattr(g, "built_chests", None) if g is not None else None
        if not chests:
            return None
        ok = [c for c in chests if getattr(c, "filter", None) in (None, item)]
        if not ok:
            return None
        return min(ok, key=lambda c: (c.x - self.x) ** 2 + (c.y - self.y) ** 2)

    def _chest_with(self, item: str, n: int):
        """The nearest chest that takes `item` and holds at least n of it.
        Searches EVERY chest, not just the first one in the list -- a worker
        used to idle beside an empty 'Any' chest while a full one stood ten
        steps away."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None)
        chests = getattr(g, "built_chests", None) if g is not None else None
        if not chests:
            return None
        best = None
        for c in chests:
            f = getattr(c, "filter", None)
            if f is not None and f != item:
                continue
            inv = getattr(c, "inventory", None)
            if inv is None or inv.count_of(item) < n:
                continue
            d = (c.x - self.x) ** 2 + (c.y - self.y) ** 2
            if best is None or d < best[0]:
                best = (d, c)
        return best[1] if best else None

    def _take_from_chest(self, chest, item: str, n: int):
        """Take up to n of item out of a chest; returns (taken, grade)."""
        inv = getattr(chest, "inventory", None)
        if inv is None:
            return 0, 3
        remaining = n
        grades = []
        for i, stack in enumerate(inv.slots):
            if stack is None or stack.defn.id != item:
                continue
            take = min(remaining, stack.count)
            q = stack.quality if stack.defn.quality else 3
            grades.append((q, take))
            stack.count -= take
            remaining -= take
            if stack.count <= 0:
                inv.slots[i] = None
            if remaining <= 0:
                break
        taken = n - remaining
        if taken <= 0:
            return 0, 3
        tot = sum(c for _, c in grades)
        grade = int(round(sum(q * c for q, c in grades) / max(1, tot)))
        return taken, grade

    def _food_chest(self):
        """The nearest chest that actually holds food, respecting its lid
        filter -- a tobacco-only chest has no food to give."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None)
        chests = getattr(g, "built_chests", None) if g is not None else None
        if not chests:
            return None
        best = None
        for c in chests:
            f = getattr(c, "filter", None)
            if f is not None and f not in economy.FOOD:
                continue
            inv = getattr(c, "inventory", None)
            if inv is None or sum(inv.count_of(i) for i in economy.FOOD) <= 0:
                continue
            d = (c.x - self.x) ** 2 + (c.y - self.y) ** 2
            if best is None or d < best[0]:
                best = (d, c)
        return best[1] if best else None

    def _fetch_food_from_chest(self, dt: float) -> bool:
        """A hungry conquered worker eats from a chest: walk to it, take one
        meal, eat it there. True while he is on the way or eating."""
        if getattr(self, "hunger", 0.0) < economy.EAT_AT:
            return False                 # not hungry
        if economy.food_of(self) > 0:
            return False                 # he still has his own food
        chest = self._food_chest()
        if chest is None:
            return False                 # no chest, or none holds food
        if math.hypot(chest.x - self.x, chest.y - self.y) > 20.0:
            self._step_toward(chest.x, chest.y, dt)
            return True
        inv = getattr(chest, "inventory", None)
        if inv is not None:
            for item in economy.FOOD:
                if inv.count_of(item) <= 0:
                    continue
                taken, _g = self._take_from_chest(chest, item, 1)
                if taken <= 0:
                    continue
                self.hunger = max(0.0, getattr(self, "hunger", 0.0) - economy.EAT_BY)
                self.mood = min(100.0, getattr(self, "mood", 50.0) + 1.0)
                self._did_work()
                return True
        return True                      # at the chest, but it emptied on the walk

    def _work_artisan(self, dt: float) -> None:
        """An artisan on the bench: fetch 10 leaf from a chest, carry it to
        the bench, turn it into 10 finished goods, and walk those back to a
        chest. He SELF-PAIRS: if he has no bench he takes any free one every
        tick (auto-configuring an unset bench), so he never idles beside a
        bench that is standing unused just because a pairing pass was missed."""
        bench = getattr(self, "artisan_bench", None)
        if bench is None:
            g = getattr(getattr(self, "native_camp", None), "g", None)
            if g is not None:
                free = [wp for wp in getattr(g, "placed_work", ()) or ()
                        if getattr(wp, "kind", None) == "lab"
                        and getattr(wp, "artisan", None) is None]
                if free:
                    for wp in free:
                        if getattr(wp, "product", None) is None:
                            try:
                                import biomes as _biomes
                                import crop as _crop
                                _world = getattr(g, "world", None)
                                _t = float(_world.temperature(wp.x, wp.y))
                                _h = float(_world.humidity(wp.x, wp.y))
                                _leaf_crop = _biomes.crop_kinds(_t, _h)[1]
                                _leaf = _crop.LEAF_ITEM.get(_leaf_crop)
                                _prod = _crop.LEAF_PRODUCT.get(_leaf_crop)
                                if _leaf and _prod:
                                    wp.leaf, wp.product = _leaf, _prod
                            except Exception:
                                pass
                        if getattr(wp, "product", None):
                            bench = wp
                            bench.artisan = self
                            self.artisan_bench = bench
                            break
            if bench is None or getattr(bench, "broken", False):
                self._native_idle(dt)      # no bench at all: stay by the fire
                return

        def _wait_at_bench():
            self._wp_go(bench, dt, 22.0)

        product = getattr(bench, "product", None)
        leaf = getattr(bench, "leaf", None)
        if not product or not leaf:
            _wait_at_bench()
            return
        # 1. Deliver the finished article before fetching more leaf.
        if self.carry.get(product, 0) > 0:
            chest = self._chest_accepting(product)
            if chest is None:
                return                 # no chest will take it: hold it
            if math.hypot(chest.x - self.x, chest.y - self.y) > 22.0:
                self._step_toward(chest.x, chest.y, dt)
                return
            inv = getattr(chest, "inventory", None)
            if inv is not None:
                n = int(self.carry.get(product, 0))
                g = self.carry_grade.get(product)
                if getattr(items.get(product), "quality", False) and g is not None:
                    inv.add(product, n, quality=int(g))
                else:
                    inv.add(product, n)
                self.carry.pop(product, None)
                self.carry_grade.pop(product, None)
            return
        # 2. With a full batch of leaf, work the bench.
        if self.carry.get(leaf, 0) >= 10:
            if self._wp_go(bench, dt, 22.0):
                return
            self.produce_acc += dt * mood.work_mult(self)
            if self.produce_acc >= ARTISAN_BATCH_SECONDS:
                self.produce_acc = 0.0
                self._snd("bench", min_gap=0.8)
                self.carry[leaf] = self.carry.get(leaf, 0) - 10
                if self.carry.get(leaf, 0) <= 0:
                    self.carry.pop(leaf, None)
                    self.carry_grade.pop(leaf, None)
                hands = self.skills.leaf_grade()
                given = self.carry_grade.get(leaf, 3)
                g = quality.clamp(int(round((hands + given) / 2.0)))
                self.carry[product] = self.carry.get(product, 0) + 10
                self.carry_grade[product] = g
                self._did_work()
                self.skills.gain_farming(0.05)
            return
        # 3. Fetch 10 leaf from the nearest chest that holds it.
        chest = self._chest_with(leaf, 10)
        if chest is None:
            # NO LEAF ANYWHERE YET: stand at the bench and wait.
            _wait_at_bench()
            return
        if math.hypot(chest.x - self.x, chest.y - self.y) > 22.0:
            self._step_toward(chest.x, chest.y, dt)
            return
        taken, g = self._take_from_chest(chest, leaf, 10)
        if taken <= 0:
            _wait_at_bench()           # emptied on the way: stay on the job
            return
        old_n = int(self.carry.get(leaf, 0) or 0)
        self.carry[leaf] = old_n + taken
        if old_n == 0:
            self.carry_grade[leaf] = g
        else:
            self.carry_grade[leaf] = quality.merge(
                self.carry_grade.get(leaf, 3), old_n, g, taken)

    def _nearest_research_bench(self, g):
        """The research bench this man works at, or None."""
        benches = [wp for wp in getattr(g, "placed_work", ()) or ()
                   if getattr(wp, "kind", None) == "research"]
        if not benches:
            return None
        return min(benches, key=lambda b: (b.x - self.x) ** 2 + (b.y - self.y) ** 2)

    def _work_research(self, dt: float) -> None:
        """A researcher walks to the research bench and works it: one research
        point per second per skill level, and two days of this is one level."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        bench = self._nearest_research_bench(g)
        if bench is None:
            self._native_idle(dt)
            return
        if self._wp_go(bench, dt, 24.0):
            return
        self.skills.gain_research(dt)
        lvl = max(1, int(self.skills.research))
        try:
            import research as _research
            _research.add_points(g, lvl * dt)
        except Exception:
            pass
        self._snd("research", min_gap=6.0)
        self._did_work()

    def _nearest_iron(self, g):
        """The nearest unmined iron chunk, or None."""
        ore_field = getattr(g, "ore_field", None)
        if ore_field is None:
            return None
        best = None
        for chunk in ore_field.near(self.x, self.y, 12000.0):
            d = (chunk.x - self.x) ** 2 + (chunk.y - self.y) ** 2
            if best is None or d < best[0]:
                best = (d, chunk)
        return best[1] if best else None

    def _work_mine(self, dt: float) -> None:
        """A miner walks to the nearest iron chunk, hits it thirty times (one
        ore a hit), and carries the thirty ore to a chest -- or keeps it if
        there is no chest that takes iron."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        import ore as _ore
        # a full load goes to a chest first
        if int(self.carry.get("iron", 0)) >= _ore.STRIKES:
            if self._deposit_to_chest(dt):
                return
        chunk = self._nearest_iron(g)
        if chunk is None:
            self._native_idle(dt)
            return
        if math.hypot(chunk.x - self.x, chunk.y - self.y) > 20.0:
            self._step_toward_excl(chunk.x, chunk.y, dt,
                                   excl=getattr(chunk, "rect", None))
            return
        self.mine_timer = getattr(self, "mine_timer", 0.0) + dt
        if self.mine_timer >= 1.0:                 # one swing a second
            self.mine_timer = 0.0
            chunk.strikes += 1
            self.carry["iron"] = self.carry.get("iron", 0) + 1
            self._did_work()
            self.skills.gain_axe()
            if chunk.strikes >= _ore.STRIKES:
                chunk.mined = True
                g.ore_field.mined.add(chunk.cell)

    def _nearest_workplace(self, g, kind):
        wps = [w for w in getattr(g, "placed_work", ()) or ()
               if getattr(w, "kind", None) == kind]
        if not wps:
            return None
        return min(wps, key=lambda w: (w.x - self.x) ** 2 + (w.y - self.y) ** 2)

    def _wp_door(self, wp):
        """The walk-up point just outside a workplace's footprint. A
        workplace's CENTRE is inside its own collider, so walking at the
        centre made a man orbit the bench -- flipping one way then the other,
        forever, never close enough to work."""
        d = getattr(wp, "door", None)
        if d is not None:
            return float(d[0]), float(d[1])
        return float(wp.x), float(wp.y)

    def _wp_go(self, wp, dt, dist) -> bool:
        """Walk toward the workplace's door; True while still on the way.
        The workplace's OWN box is excluded from steering -- a man going to
        work at a bench must not treat that bench as a wall, or he orbits its
        corner forever and never gets close enough to work."""
        dx, dy = self._wp_door(wp)
        if math.hypot(dx - self.x, dy - self.y) > dist:
            self._step_toward_excl(dx, dy, dt, excl=getattr(wp, "rect", None))
            return True
        return False

    def _wait_at_post(self, wp, dt) -> None:
        """Stand at the assigned workplace while there is nothing to fetch or
        carry -- never drift back to the campfire. That drift was the
        two-task glitch: walk to work, idle by the fire, walk to work..."""
        if wp is not None:
            self._wp_go(wp, dt, 20.0)

    # THE SMITH'S TWO PRODUCTS: what he makes, what he turns it from, and how
    # long one takes. The player picks by clicking him (see SmithPanel).
    SMITH_PRODUCTS = (
        {"id": "iron_bar", "recipe": {"iron": 1}, "seconds": 30.0, "needs": None,
         "name": "Iron bars", "desc": "1 iron ore \u2192 1 bar"},
        {"id": "gear", "recipe": {"iron_bar": 1}, "seconds": 30.0, "needs": "industry",
         "name": "Gears", "desc": "1 iron bar \u2192 1 gear"},
        {"id": "reinforced_armor", "recipe": {"iron_bar": 10, "textile": 10},
         "seconds": 60.0, "needs": "reinforced_armor",
         "name": "Reinforced armor", "desc": "10 bars + 10 textiles \u2192 1 suit"},
    )

    def _pick_patient(self):
        """The nearest person of this camp who is hurt or still unexamined."""
        best, bd = None, 1e18
        for p in self._camp_people():
            if p is self or not getattr(p, "alive", True):
                continue
            hurt = float(getattr(p, "health", 0)) < float(getattr(p, "max_health", 0))
            unexamined = int(getattr(p, "medicines_received", 0) or 0) <= 0
            if not (hurt or unexamined):
                continue
            d = (p.x - self.x) ** 2 + (p.y - self.y) ** 2
            if d < bd:
                best, bd = p, d
        return best

    def _trader_sellable_chest(self, g):
        try:
            import market
            sellable = set(market.sellable(g))
        except Exception:
            return None, ()
        best, bd, best_items = None, 1e18, ()
        for ch in (getattr(g, "built_chests", ()) or ()):
            inv = getattr(ch, "inventory", None)
            if inv is None:
                continue
            items = []
            for stack in inv.slots:
                if stack is not None and stack.defn.id in sellable and stack.count > 0:
                    items.append(stack.defn.id)
            if not items:
                continue
            d = (ch.x - self.x) ** 2 + (ch.y - self.y) ** 2
            if d < bd:
                best, bd, best_items = ch, d, tuple(items)
        return best, best_items

    def _trader_pack(self):
        """The trader carries goods in his REAL pack, so they appear in his card."""
        try:
            import work as _work
            return _work.bag(self)
        except Exception:
            return getattr(self, "pack", None)

    def _trader_load(self):
        load = getattr(self, "trader_load", None)
        if not isinstance(load, dict):
            load = self.trader_load = {}
        return load

    def _trader_migrate_carry(self) -> None:
        """Old traders kept goods in the hidden job `carry` dict. Move them into
        the real pack once, so an existing trip is not invisible."""
        carry = getattr(self, "carry", None)
        if not isinstance(carry, dict) or not carry:
            return
        inv = self._trader_pack()
        load = self._trader_load()
        try:
            import items as _items
            import market as _market
            sellable = set(_market.sellable(getattr(getattr(self, "native_camp", None), "g", None)))
        except Exception:
            sellable = set()
        grades = getattr(self, "carry_grade", {}) or {}
        for item, qty in list(carry.items()):
            qty = int(qty or 0)
            if qty <= 0:
                carry.pop(item, None)
                continue
            if inv is None:
                continue
            take = qty
            try:
                import work as _work
                take = min(qty, _work.can_hold(inv, item, qty))
            except Exception:
                pass
            if take <= 0:
                continue
            grade = int(grades.get(item, 4) or 4)
            if getattr(_items.get(item), "quality", False):
                inv.add(item, take, quality=grade)
            else:
                inv.add(item, take)
            load[item] = int(load.get(item, 0)) + take
            try:
                self.carry_grade[item] = int(grade)
            except Exception:
                pass
            if take >= qty:
                carry.pop(item, None)
                grades.pop(item, None)
            else:
                carry[item] = qty - take

    def _trader_show_coin(self) -> None:
        """Put the return coin in his real pack so the card shows it."""
        inv = self._trader_pack()
        if inv is None:
            return
        coins = int(round(float(getattr(self, "trader_coin", 0.0))))
        if coins <= 0:
            return
        have = int(inv.count_of("coin"))
        if have < coins:
            try:
                inv.add("coin", coins - have)
            except Exception:
                pass

    def _work_trader(self, dt: float) -> None:
        """Gather at least 50 sellable goods, run them to the ship, bring the
        coin back, and hand it to the player when he is nearby.

        The goods live in his actual pack, not a hidden carry dict: click the
        trader and you can see exactly what he has taken.
        """
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        self._trader_migrate_carry()
        load = self._trader_load()
        inv = self._trader_pack()
        self._trader_show_coin()
        state = getattr(self, "trader_state", "idle")
        if state == "sailing":
            self.trader_t = float(getattr(self, "trader_t", 0.0)) - dt
            if self.trader_t > 0.0:
                return
            try:
                import market
                coin = 0.0
                for item, qty in list(load.items()):
                    qty = int(qty or 0)
                    if qty <= 0 or item not in market.sellable(g):
                        load.pop(item, None)
                        continue
                    # Never sell what is no longer in the pack (the player may
                    # have taken it out while the trader was at sea).
                    have = int(inv.count_of(item)) if inv is not None else 0
                    qty = min(qty, have)
                    if qty <= 0:
                        load.pop(item, None)
                        continue
                    grade = int((getattr(self, "carry_grade", {}) or {}).get(item, 4) or 4)
                    # The trader gets 80% of what the player/horse would get.
                    coin += market.sell_value(g, item, qty, grade) * 0.80
                    if inv is not None:
                        inv.consume(item, qty)
                    load.pop(item, None)
                self.trader_load = {}
                self.trader_coin = float(getattr(self, "trader_coin", 0.0)) + coin
                # THE COIN IS REAL TOO: it goes into his pack now, so clicking
                # the trader shows what he brought back before he reaches you.
                self._trader_show_coin()
                self.trader_state = "paying"
                try:
                    g.toast("%s returns from the ship with %d coin"
                            % (getattr(self, "name", "The trader"), int(coin)))
                except Exception:
                    pass
            except Exception:
                self.trader_state = "idle"
            return
        if state == "paying":
            player = getattr(g, "player", None)
            if player is None:
                return
            d = math.hypot(player.x - self.x, player.y - self.y)
            if d > 26.0:
                self._step_toward(player.x, player.y, dt)
                return
            coins = int(round(float(getattr(self, "trader_coin", 0.0))))
            # If the player already took the coin out of his pack, do not pay
            # it a second time.
            if inv is not None and coins > 0:
                coins = min(coins, int(inv.count_of("coin")))
            if coins > 0:
                before = int(g.inventory.count_of("coin"))
                try:
                    g.inventory.add("coin", coins)
                except Exception:
                    pass
                got = max(0, int(g.inventory.count_of("coin")) - before)
                if got > 0:
                    if inv is not None:
                        inv.consume("coin", got)
                    self.trader_coin = max(0.0, float(self.trader_coin) - got)
                    try:
                        g.toast("%s gives you %d coin from the ship"
                                % (getattr(self, "name", "The trader"), got))
                    except Exception:
                        pass
                else:
                    try:
                        g.toast("No room for %d coin" % coins)
                    except Exception:
                        pass
                    return
            else:
                self.trader_coin = 0.0
            if float(getattr(self, "trader_coin", 0.0)) <= 0.0:
                self.trader_coin = 0.0
                self.trader_state = "idle"
            return

        # GATHERING: only sellable goods in chests count.
        total = sum(int(q or 0) for q in load.values())
        if total >= 50:
            self.trader_state = "sailing"
            self.trader_t = 45.0
            try:
                g.toast("%s sets out for the ship with %d goods"
                        % (getattr(self, "name", "The trader"), total))
            except Exception:
                pass
            return
        chest, items = self._trader_sellable_chest(g)
        if chest is None or not items:
            self._wait_at_post(self._nearest_workplace(g, "fireplace"), dt)
            return
        if math.hypot(chest.x - self.x, chest.y - self.y) > 22.0:
            self._step_toward(chest.x, chest.y, dt)
            return
        # Take what is here, up to the 50-piece target, into the REAL pack.
        need = 50 - total
        try:
            import work as _work
        except Exception:
            _work = None
        for item in items:
            if need <= 0:
                break
            want = need
            if _work is not None and inv is not None:
                want = min(need, _work.can_hold(inv, item, need))
            if want <= 0:
                continue
            take, grade = self._take_from_chest(chest, item, want)
            if take > 0:
                try:
                    import items as _items
                    if getattr(_items.get(item), "quality", False):
                        inv.add(item, take, quality=int(grade))
                    else:
                        inv.add(item, take)
                except Exception:
                    pass
                load[item] = int(load.get(item, 0) or 0) + take
                try:
                    self.carry_grade[item] = int(grade)
                except Exception:
                    pass
                need -= take

    def _work_doctor(self, dt: float) -> None:
        """Make medicine, then carry it to the hurt and the unexamined.

        The first medicine is an examination: it sets medicines_received and
        mental_known permanently.  The patient scan is cached and runs once
        every doctor.SCAN_SECONDS, never once per frame for every person.
        """
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        hut = self._nearest_workplace(g, "medicine_hut")
        if hut is None or getattr(hut, "broken", False):
            self._native_idle(dt)
            return

        # 1. Carry medicine to a patient.
        if int(self.carry.get("medicine", 0) or 0) > 0:
            target = getattr(self, "_doc_target", None)
            if target is not None:
                hurt = (float(getattr(target, "health", 0))
                        < float(getattr(target, "max_health", 0)))
                unexamined = int(getattr(target, "medicines_received", 0) or 0) <= 0
                if (not getattr(target, "alive", True)
                        or not (hurt or unexamined)):
                    target = None
                    self._doc_target = None
            if target is None:
                self._doc_scan_t = getattr(self, "_doc_scan_t", 0.0) - dt
                if self._doc_scan_t <= 0.0:
                    self._doc_scan_t = doctor.SCAN_SECONDS
                    target = self._pick_patient()
                    self._doc_target = target
            if target is not None:
                if math.hypot(target.x - self.x, target.y - self.y) > 20.0:
                    self._step_toward(target.x, target.y, dt)
                    return
                self.carry["medicine"] = int(self.carry.get("medicine", 0)) - 1
                if self.carry.get("medicine", 0) <= 0:
                    self.carry.pop("medicine", None)
                try:
                    target.health = target.max_health
                except Exception:
                    pass
                target.medicines_received = int(getattr(target, "medicines_received", 0) or 0) + 1
                target.mental_known = True
                try:
                    mood.add_thought(target, "treated", 4.0, float(g.now),
                                     120.0)
                except Exception:
                    pass
                try:
                    import relationships as _rel
                    _rel.observe(target, self, "heal", float(g.now), g)
                except Exception:
                    pass
                self._doc_target = None
                self._doc_scan_t = 0.0
                self._did_work()
                try:
                    import plog
                    plog.log("MEDICINE", getattr(target, "name", "?"),
                             "treated by", getattr(self, "name", "?"))
                except Exception:
                    pass
                return
            # No patient: keep the dose at the hut rather than wander.
            self._wait_at_post(hut, dt)
            return

        # 2. Gather one tobacco, one dried mushroom, one alcohol.
        for item, need in doctor.RECIPE.items():
            have = int(self.carry.get(item, 0) or 0)
            if have < need:
                if self._take_ingredient(item, need - have, dt):
                    return
        if not any(int(self.carry.get(a, 0) or 0) > 0 for a in doctor.ALCOHOL):
            for alcohol in doctor.ALCOHOL:
                if self._take_ingredient(alcohol, 1, dt):
                    return
                if int(self.carry.get(alcohol, 0) or 0) > 0:
                    break
        missing = any(int(self.carry.get(i, 0) or 0) < n
                      for i, n in doctor.RECIPE.items())
        if missing or not any(int(self.carry.get(a, 0) or 0) > 0
                              for a in doctor.ALCOHOL):
            self._wait_at_post(hut, dt)
            return

        # 3. Work the bench.
        if self._wp_go(hut, dt, 24.0):
            return
        self.produce_acc = (getattr(self, "produce_acc", 0.0)
                            + dt * mood.work_mult(self))
        if self.produce_acc >= doctor.MEDICINE_SECONDS:
            self.produce_acc = 0.0
            for item, need in doctor.RECIPE.items():
                self.carry[item] = int(self.carry.get(item, 0) or 0) - need
                if self.carry.get(item, 0) <= 0:
                    self.carry.pop(item, None)
            for alcohol in doctor.ALCOHOL:
                if int(self.carry.get(alcohol, 0) or 0) > 0:
                    self.carry[alcohol] = int(self.carry[alcohol]) - 1
                    if self.carry[alcohol] <= 0:
                        self.carry.pop(alcohol, None)
                    break
            self.carry["medicine"] = int(self.carry.get("medicine", 0) or 0) + doctor.DOSES_PER_BATCH
            self._did_work()
            self._snd("bench", min_gap=0.8)

    def _work_smith(self, dt: float) -> None:
        """A smith works the forge: iron ore into iron bars, iron bars into
        gears, or bars and textiles into reinforced armor -- whichever the
        player has told him to make. Only once Ironworking is researched."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        try:
            import research as _research
            if _research.state(g, "ironworking") != "done":
                self._native_idle(dt)
                return
        except Exception:
            self._native_idle(dt)
            return
        product = next((p for p in self.SMITH_PRODUCTS
                        if p["id"] == getattr(self, "smith_product", None)), None)
        if product is None:
            self._native_idle(dt)
            return
        if product.get("needs"):
            try:
                import research as _research
                if _research.state(g, product["needs"]) != "done":
                    self._native_idle(dt)
                    return
            except Exception:
                self._native_idle(dt)
                return
        out_item = product["id"]
        recipe = product["recipe"]
        forge = self._nearest_workplace(g, "smith")
        if forge is None or getattr(forge, "broken", False):
            self._native_idle(dt)
            return
        # deliver finished pieces first
        if int(self.carry.get(out_item, 0)) > 0:
            if self._deposit_to_chest(dt):
                return
        # fetch one missing input at a time, from the nearest chest that holds it
        for in_item, need in recipe.items():
            if int(self.carry.get(in_item, 0)) < need:
                chest = self._chest_with(in_item, need)
                if chest is None:
                    self._wait_at_post(forge, dt)
                    return
                if math.hypot(chest.x - self.x, chest.y - self.y) > 20.0:
                    self._step_toward(chest.x, chest.y, dt)
                    return
                taken, _g = self._take_from_chest(
                    chest, in_item, need - int(self.carry.get(in_item, 0)))
                if taken > 0:
                    self.carry[in_item] = int(self.carry.get(in_item, 0)) + taken
                return
        # walk to the forge and work
        if self._wp_go(forge, dt, 24.0):
            return
        self.produce_acc = (getattr(self, "produce_acc", 0.0)
                            + dt * mood.work_mult(self))
        if self.produce_acc >= product["seconds"]:
            self.produce_acc = 0.0
            self._snd("bench", min_gap=0.8)
            for in_item, need in recipe.items():
                self.carry[in_item] = int(self.carry.get(in_item, 0)) - need
                if self.carry.get(in_item, 0) <= 0:
                    self.carry.pop(in_item, None)
                    self.carry_grade.pop(in_item, None)
            out_def = items.get(out_item)
            if getattr(out_def, "quality", False):
                g2 = self.skills.smith_grade()
                old_n = int(self.carry.get(out_item, 0) or 0)
                self.carry[out_item] = old_n + 1
                self.carry_grade[out_item] = quality.merge(
                    self.carry_grade.get(out_item, g2), old_n, g2, 1)
            else:
                self.carry[out_item] = int(self.carry.get(out_item, 0) or 0) + 1
            self._did_work()
            self.skills.gain_smithing()

    def _work_weaver(self, dt: float) -> None:
        """A weaver works the loom: five cotton become one bolt of cloth at
        a time, the cloth graded by his hand. Only once Textiles is
        researched."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        try:
            import research as _research
            if _research.state(g, "textiles") != "done":
                self._native_idle(dt)
                return
        except Exception:
            self._native_idle(dt)
            return
        loom = self._nearest_workplace(g, "weaver")
        if loom is None:
            self._native_idle(dt)
            return
        # deliver finished cloth first
        if int(self.carry.get("textile", 0)) > 0:
            if self._deposit_to_chest(dt):
                return
        # fetch five cotton from a chest
        if int(self.carry.get("cotton", 0)) < 5:
            chest = self._chest_with("cotton", 5)
            if chest is None:
                self._wait_at_post(loom, dt)
                return
            if math.hypot(chest.x - self.x, chest.y - self.y) > 20.0:
                self._step_toward(chest.x, chest.y, dt)
                return
            taken, _g = self._take_from_chest(chest, "cotton",
                                              5 - int(self.carry.get("cotton", 0)))
            if taken > 0:
                self.carry["cotton"] = int(self.carry.get("cotton", 0)) + taken
            return
        # walk to the loom and weave
        if self._wp_go(loom, dt, 24.0):
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= WEAVER_BATCH_SECONDS:
            self.produce_acc = 0.0
            self._snd("bench", min_gap=0.8)
            self.carry["cotton"] = int(self.carry.get("cotton", 0)) - 5
            if self.carry.get("cotton", 0) <= 0:
                self.carry.pop("cotton", None)
            g2 = self.skills.leaf_grade()
            old_n = int(self.carry.get("textile", 0) or 0)
            self.carry["textile"] = old_n + 1
            self.carry_grade["textile"] = quality.merge(
                self.carry_grade.get("textile", g2), old_n, g2, 1)
            self._did_work()
            self.skills.gain_farming(0.05)

    def _work_spiceman(self, dt: float) -> None:
        """A spiceman at the stall: five chilis into one bottle of sauce, a
        minute a bottle. Sauce carries no grade -- it is sauce. Only once
        Spice sauces is researched."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        try:
            import research as _research
            if _research.state(g, "spice_sauce") != "done":
                self._native_idle(dt)
                return
        except Exception:
            self._native_idle(dt)
            return
        stall = self._nearest_workplace(g, "spice")
        if stall is None:
            self._native_idle(dt)
            return
        # deliver finished bottles first
        if int(self.carry.get("sauce", 0)) > 0:
            if self._deposit_to_chest(dt):
                return
        # fetch five chilis from a chest
        if int(self.carry.get("chili", 0)) < 5:
            chest = self._chest_with("chili", 5)
            if chest is None:
                self._wait_at_post(stall, dt)
                return
            if math.hypot(chest.x - self.x, chest.y - self.y) > 20.0:
                self._step_toward(chest.x, chest.y, dt)
                return
            taken, _g = self._take_from_chest(chest, "chili",
                                              5 - int(self.carry.get("chili", 0)))
            if taken > 0:
                self.carry["chili"] = int(self.carry.get("chili", 0)) + taken
            return
        # walk to the stall and bottle it
        if self._wp_go(stall, dt, 24.0):
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= SPICEMAN_SECONDS:
            self.produce_acc = 0.0
            self._snd("bench", min_gap=0.8)
            self.carry["chili"] = int(self.carry.get("chili", 0)) - 5
            if self.carry.get("chili", 0) <= 0:
                self.carry.pop("chili", None)
                self.carry_grade.pop("chili", None)
            self.carry["sauce"] = int(self.carry.get("sauce", 0)) + 1
            self._did_work()
            self.skills.gain_farming(0.05)

    def _work_soldier(self, dt: float) -> None:
        """A bought soldier: reinforced armor, a rifle, and half a lifetime's
        shooting. He sees an unconquered warrior or beast at twice the bow's
        range, holds rifle distance, and steps around anything -- or anyone --
        standing in the shot before he takes it."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        # EAT: a soldier draws from the camp store and the chests, like the
        # workers he defends.
        try:
            self._native_share()
            if self._fetch_food_from_chest(dt):
                return
        except Exception:
            pass
        # reload the rifle when it runs dry
        if self.reload_timer > 0.0:
            self.reload_timer = max(0.0, self.reload_timer - dt)
            if self.reload_timer == 0.0:
                self.mag = guns.MAG.get(self.gun_kind, 3)
        # nearest hostile within 640 -- double the bow's 320
        _range = 640.0
        target = None
        best = _range * _range
        for s in getattr(g, "native_settlements", {}).values():
            if getattr(s, "conquered", False):
                continue
            for w in getattr(s, "warriors", ()) or ():
                if not getattr(w, "alive", True):
                    continue
                d = (w.x - self.x) ** 2 + (w.y - self.y) ** 2
                if d < best:
                    best, target = d, w
        for e in getattr(g, "enemies", ()) or ():
            if not getattr(e, "alive", True):
                continue
            d = (e.x - self.x) ** 2 + (e.y - self.y) ** 2
            if d < best:
                best, target = d, e
        if target is None:
            _eh = getattr(self, "escort_horse", None)
            if _eh is not None and getattr(_eh, "alive", True):
                self._step_toward(_eh.x, _eh.y, dt)
                return
            self._native_idle(dt)
            return
        distance = math.sqrt(best)
        dx = target.x - self.x
        dy = target.y - self.y
        if distance > 0.0:
            self.facing = (dx / distance, dy / distance)
        ux, uy = dx / distance, dy / distance
        mx = self.x + ux * 16.0
        my = self.y + uy * 16.0
        tx, ty = target.x, target.y
        blocked = self._line_blocked(g, mx, my, tx, ty)
        if not blocked:
            blocked = self._shot_hits_friend(g, mx, my, tx, ty)
        # close in when far, back off when near, and strafe around a blocked
        # line -- never fire through a friend or a wall.
        if distance > 260.0:
            self._step_toward(tx, ty, dt)
            return
        if blocked:
            px, py = -uy, ux
            self.x += px * self.combat_speed * 0.8 * dt
            self.y += py * self.combat_speed * 0.8 * dt
            return
        if distance < 140.0:
            self.x -= ux * self.combat_speed * dt
            self.y -= uy * self.combat_speed * dt
        self.attack_cd -= dt
        if self.mag <= 0:
            if self.reload_timer <= 0.0:
                self.reload_timer = guns.reload_time(self.gun_kind, self.skills.shooting)
            return
        if self.attack_cd <= 0.0:
            self.attack_cd = guns.FIRE_CD.get(self.gun_kind, 1.0)
            self.mag -= 1
            self._did_attack()
            self.skills.gain_shooting()
            combat = getattr(g, "combat", None)
            if combat is not None:
                combat.fire(mx, my, math.atan2(dy, dx), distance, owner="player",
                            damage=guns.DAMAGE.get(self.gun_kind, 80),
                            team="player", shooter=self,
                            spread=self.skills.shot_spread())

    def _shot_hits_friend(self, g, x0, y0, x1, y1) -> bool:
        """True if the player, a conquered worker or a fellow soldier stands
        in the line of fire -- the shot is not clean."""
        _p = getattr(g, "player", None)
        if _p is not None and not getattr(_p, "dead", False):
            if segment_circle_hit(x0, y0, x1, y1, _p.x, _p.y,
                                  getattr(_p, "radius", 10) + 6):
                return True
        for _n in getattr(g, "_native_people", ()) or ():
            if _n is self or not getattr(_n, "alive", True):
                continue
            if (getattr(_n, "conquered", False)
                    or getattr(_n, "native_role", "") == "soldier"):
                if segment_circle_hit(x0, y0, x1, y1, _n.x, _n.y,
                                      getattr(_n, "radius", 10) + 6):
                    return True
        return False

    # THE GUNSMITH'S THREE PRODUCTS: what he makes, what it costs in iron
    # bars, how long one takes, and which research unlocks it.
    GUNSMITH_PRODUCTS = (
        {"id": "musket", "bars": 10, "seconds": 600.0, "needs": None,
         "name": "Musket", "desc": "1 shot, 5s reload"},
        {"id": "double_shot", "bars": 15, "seconds": 600.0, "needs": "two_shot",
         "name": "Double-Shot", "desc": "2 shots, 5s reload"},
        {"id": "rifle", "bars": 30, "seconds": 600.0, "needs": "rifle",
         "name": "Rifle", "desc": "3 shots, 1s reload"},
        {"id": "ammo", "bars": 1, "seconds": 30.0, "needs": None,
         "name": "Ammo", "desc": "10 rounds", "amount": 10},
    )

    def _work_gunsmith(self, dt: float) -> None:
        """A gunsmith works the forge into guns: the player has told him what
        to make (click him and choose), and he turns iron bars into that one
        thing, over and over. Only once Gunsmithing is researched."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            self._native_idle(dt)
            return
        try:
            import research as _research
            if _research.state(g, "gunsmithing") != "done":
                self._native_idle(dt)
                return
        except Exception:
            self._native_idle(dt)
            return
        product = next((p for p in self.GUNSMITH_PRODUCTS
                        if p["id"] == getattr(self, "gunsmith_product", None)), None)
        if product is None:
            self._native_idle(dt)
            return
        out_item = product["id"]
        out_n = product.get("amount", 1)
        # deliver what he has already made first
        if int(self.carry.get(out_item, 0)) > 0:
            if self._deposit_to_chest(dt):
                return
        forge = self._nearest_workplace(g, "smith")
        if forge is None:
            self._native_idle(dt)
            return
        # fetch enough iron bars for one batch
        need = product["bars"]
        if int(self.carry.get("iron_bar", 0)) < need:
            chest = self._chest_with("iron_bar", need)
            if chest is None:
                self._wait_at_post(forge, dt)
                return
            if math.hypot(chest.x - self.x, chest.y - self.y) > 20.0:
                self._step_toward(chest.x, chest.y, dt)
                return
            taken, _g = self._take_from_chest(chest, "iron_bar",
                                              need - int(self.carry.get("iron_bar", 0)))
            if taken > 0:
                self.carry["iron_bar"] = int(self.carry.get("iron_bar", 0)) + taken
            return
        # walk to the forge and work
        if self._wp_go(forge, dt, 24.0):
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= product["seconds"]:
            self.produce_acc = 0.0
            self._snd("bench", min_gap=0.8)
            self.carry["iron_bar"] = int(self.carry.get("iron_bar", 0)) - need
            if self.carry.get("iron_bar", 0) <= 0:
                self.carry.pop("iron_bar", None)
            self.carry[out_item] = int(self.carry.get(out_item, 0)) + out_n
            self._did_work()

    def _pockets(self):
        """A conquered worker's real pack (an Inventory), made lazily from the
        stock dict he was born with. Village and native farmers keep using the
        plain stock dict, so this returns None for them."""
        if not getattr(self, "conquered", False):
            return None
        try:
            import work as _work
            return _work.bag(self)
        except Exception:
            return None

    def _count_item(self, item: str) -> int:
        p = self._pockets()
        if p is not None:
            return int(p.count_of(item))
        return int(self.stock.get(item, 0) or 0)

    def _give_item(self, item: str, n: int) -> None:
        if n <= 0:
            return
        p = self._pockets()
        if p is not None:
            p.add(item, int(n))
        else:
            self.stock[item] = self.stock.get(item, 0) + int(n)

    def _take_item(self, item: str, n: int = 1) -> bool:
        """Take n of an item out of the pack/stock. True if it was all there."""
        p = self._pockets()
        if p is not None:
            return bool(p.consume(item, int(n)))
        have = int(self.stock.get(item, 0) or 0)
        if have < n:
            return False
        self.stock[item] = have - int(n)
        return True

    def _native_idle(self, dt: float) -> None:
        """An extra man with no post: he stays by the fire, not wandering off."""
        camp = getattr(self, "native_camp", None)
        speed = getattr(self, "speed", 60.0)
        fx = float(getattr(camp, "x", 0.0)) if camp is not None else 0.0
        fy = float(getattr(camp, "y", 0.0)) if camp is not None else 0.0
        fire = getattr(camp, "fireplace", None) if camp is not None else None
        if fire is not None:
            fx, fy = float(getattr(fire, "x", fx)), float(getattr(fire, "y", fy))
        else:
            g = getattr(camp, "g", None) if camp is not None else None
            if g is not None:
                for wp in getattr(g, "placed_work", ()) or ():
                    if getattr(wp, "kind", "") == "fireplace":
                        fx, fy = float(getattr(wp, "x", fx)), float(getattr(wp, "y", fy))
                        break
        if getattr(self, "_idle_timer", 0.0) <= 0.0:
            ang = self.rng.uniform(0.0, 2.0 * math.pi)
            # ORBIT WELL OUTSIDE THE FIRE'S OWN COLLIDER. The fireplace is a
            # solid workplace, so a ring drawn at 1-2.5 tiles crossed its box
            # and the steering pushed the idler one way then the other.
            r = self.rng.uniform(2.5, 4.0) * TILE
            self.target = (fx + math.cos(ang) * r, fy + math.sin(ang) * r)
            self._idle_timer = self.rng.uniform(2.0, 5.0)
        else:
            self._idle_timer -= dt
        tx, ty = self.target
        if math.hypot(tx - self.x, ty - self.y) > 8.0:
            self._walk_toward(tx, ty, speed * 0.6, dt)

    def _food_box(self):
        """The nearest feed box, or None."""
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        boxes = getattr(g, "built_foodboxes", None) if g is not None else None
        if not boxes:
            return None
        return min(boxes, key=lambda b: (b.x - self.x) ** 2 + (b.y - self.y) ** 2)

    def _carry_food(self) -> bool:
        return any(self.carry.get(item, 0) > 0 for item in economy.FOOD)

    def _sleep_on_bedroll(self, dt: float, g) -> bool:
        """At night, each person takes ONE unoccupied bedroll; when every
        bed is taken the rest sleep on the ground, each at his own spot --
        never two people on one bed, never two people on one spot."""
        if g is None:
            return False
        bb = getattr(g, "built_blocks", None) or {}
        taken = set()
        for _n in getattr(g, "_native_people", ()) or ():
            if _n is not self and getattr(_n, "asleep", False):
                _b = getattr(_n, "bed", None)
                if _b is not None:
                    try:
                        if isinstance(_b, (list, tuple)):
                            taken.add(tuple(tuple(x) if isinstance(x, (list, tuple))
                                            else x for x in _b))
                        else:
                            taken.add(_b)
                    except TypeError:
                        pass
        best = None
        bd = 1e18
        for (tx, ty), kind in bb.items():
            if kind != "bed" or (tx, ty) in taken:
                continue
            d = (tx * TILE - self.x) ** 2 + (ty * TILE - self.y) ** 2
            if d < bd:
                bd = d
                best = (tx, ty)
        if best is not None:
            tx, ty = best
            self.bed = (tx, ty)
            wx = tx * TILE + TILE / 2.0
            wy = ty * TILE + TILE / 2.0
            if math.hypot(wx - self.x, wy - self.y) > 14.0:
                self._step_toward(wx, wy, dt)
                return True
            self.asleep = True
            return True
        # EVERY BED IS TAKEN: sleep on the ground, on his own spot.
        self.bed = None
        if getattr(self, "_ground_spot", None) is None:
            _ang = self.rng.uniform(0.0, 2.0 * math.pi)
            _r = self.rng.uniform(1.5, 3.5) * TILE
            _camp = getattr(self, "native_camp", None)
            _fx = float(getattr(_camp, "x", self.x))
            _fy = float(getattr(_camp, "y", self.y))
            self._ground_spot = (_fx + math.cos(_ang) * _r,
                                 _fy + math.sin(_ang) * _r)
        gx, gy = self._ground_spot
        if math.hypot(gx - self.x, gy - self.y) > 8.0:
            self._step_toward(gx, gy, dt)
            return True
        self.asleep = True
        return True

    def _person_breed_sleep(self, dt: float, night: bool, g) -> bool:
        """The player's own people: babies grow, breeders face each other with
        hearts, and at night they sleep on their bedrolls. True = busy."""
        # a newborn grows into a full person across one day
        if getattr(self, "baby", False) and g is not None:
            if float(getattr(g, "now", 0.0)) - float(getattr(self, "born_at", 0.0)) >= economy.DAY_LENGTH:
                self.baby = False
        if getattr(self, "breeding", False):
            p = getattr(self, "breed_partner", None)
            if p is not None and getattr(p, "alive", True):
                dx, dy = p.x - self.x, p.y - self.y
                d = math.hypot(dx, dy) or 1.0
                self.facing = (dx / d, dy / d)
            return True
        if not night:
            self._wake_awake = False
        if night and not getattr(self, "_wake_awake", False):
            return self._sleep_on_bedroll(dt, g)
        if getattr(self, "asleep", False):
            self.asleep = False
            self.bed = None
            self._ground_spot = None
        return False

    def _draw_person_hearts(self, screen, sx, sy) -> None:
        """Floating hearts over a breeding pair, rising on the game clock."""
        try:
            import wildcrop as _wc
            now = float(getattr(_wc, "_NOW", 0.0))
            fnt = pygame.font.SysFont("dejavusans", 12, bold=True)
            for i in range(2):
                phase = (now * 1.3 + i * 0.5) % 1.0
                hx = int(sx + (i - 0.5) * 12)
                hy = int(sy - 24 - phase * 14)
                h = fnt.render("\u2665", True, (226, 72, 72))
                screen.blit(h, (hx, hy))
        except Exception:
            pass

    def _work_animals(self, dt: float) -> None:
        """The animal handler: keep the feed box stocked, so the livestock eat
        from it. With no box he feeds the hungriest beast directly."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            self._native_idle(dt)
            return
        box = self._food_box()
        if box is None or getattr(box, "inventory", None) is None:
            # NO BOX: feed the hungriest beast directly, the old way.
            animals = [a for a in (getattr(camp, "animals", ()) or ())
                       if getattr(a, "alive", True)]
            best = None
            for a in animals:
                if getattr(a, "food", 0) <= 0 and getattr(a, "hunger", 0.0) >= economy.EAT_AT:
                    if best is None or a.hunger > best.hunger:
                        best = a
            if best is None:
                self._native_idle(dt)
                return
            if math.hypot(best.x - self.x, best.y - self.y) > 24.0:
                self._step_toward(best.x, best.y, dt)
                return
            best.food = getattr(best, "food", 0) + 1
            self._did_work()
            return
        stocked = sum(1 for s in box.inventory.slots
                      if s is not None and s.defn.id in economy.FOOD)
        if stocked >= 8:
            self._native_idle(dt)
            return
        # CARRYING: walk to the box and pour it in.
        if self._carry_food():
            if math.hypot(box.x - self.x, box.y - self.y) > 24.0:
                self._step_toward(box.x, box.y, dt)
                return
            for item in economy.FOOD:
                if self.carry.get(item, 0) > 0:
                    box.inventory.add(item, int(self.carry[item]))
                    self.carry[item] = 0
            self._did_work()
            return
        # FORAGE: find a wild food plant and pick it.
        try:
            import wildcrop as _wc
            world = _wc._WORLD
        except Exception:
            self._native_idle(dt)
            return
        found = _wc._nearest(world, self.x, self.y, 520.0) if world else None
        if found is None:
            self._native_idle(dt)
            return
        tx, ty, _kind = found
        wx = tx * TILE + TILE / 2.0
        wy = ty * TILE + TILE / 2.0
        if math.hypot(wx - self.x, wy - self.y) > 22.0:
            self._step_toward(wx, wy, dt)
            return
        got = _wc.at(world, tx, ty)
        if got is not None:
            kind2, _stage = got
            item = crop.FOOD_ITEM.get(kind2)
            if item is not None:
                world.wild_eaten[(tx, ty)] = _wc._NOW + _wc.REGEN
                self.carry[item] = self.carry.get(item, 0) + 1
                self._did_work()

    def update(self, dt: float, threat=None, colliders=None, combat=None,
               night: bool = False, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        if getattr(self, "sleep_t", 0.0) > 0.0:
            self.sleep_t = max(0.0, self.sleep_t - dt)
            self.moving = False
            return
        # A MAJOR BREAK OWNS THE BODY.  Without this, the normal work/idle
        # update ran after _break_action and walked the man back toward the
        # campfire (or his job) -- so a "breaking spree" looked like he was
        # following whoever happened to be near the fire.  Berserk, spree and
        # depression are driven entirely by _break_action until they end.
        if getattr(self, "break_state", "normal") in ("berserk", "breaking_spree",
                                                      "crop_spree", "depression"):
            return
        if getattr(self, "_brawl_target", None) is not None:
            return
        # ATTACKED IN HIS SLEEP: he is awake now and running before any work,
        # bedroll or social branch can put him back down.
        if getattr(self, "_wake_flee", False):
            self._run_from_attack(dt)
            return
        # THE PLAYER'S OWN PEOPLE: babies grow, breeders face each other, and
        # at night they sleep on their bedrolls.
        if getattr(self, "native", False):
            g = getattr(getattr(self, "native_camp", None), "g", None)
            if self._person_breed_sleep(dt, night, g):
                return
        # NATIVE CAMP PEOPLE: farmers walk out to their fields and work them;
        # warriors patrol a ring around the fire. They live in the register and
        # are driven by their camp, not by a town schedule.
        # NATIVE CAMP PEOPLE. Farmers run the game's own field work (till,
        # water, sow, reap) on the camp's food plots; warriors patrol the fire.
        _nat = getattr(self, "native", False)
        # A HUNGRY CONQUERED WORKER EATS FROM A CHEST, whatever his job.
        if _nat and getattr(self, "conquered", False):
            if self._fetch_food_from_chest(dt):
                return
        if _nat and getattr(self, "native_role", "") == "warrior":
            self._native_step(dt, world, now)
            return
        if _nat and getattr(self, "native_role", "") == "logger":
            if self._deposit_to_chest(dt):
                return
            if world is not None:
                self._work_orchard(dt, world, now)
            return
        if _nat and getattr(self, "native_role", "") == "animal_handler":
            self._work_animals(dt)
            return
        if _nat and getattr(self, "native_role", "") == "artisan":
            self._work_artisan(dt)
            return
        if _nat and getattr(self, "native_role", "") == "researcher":
            self._work_research(dt)
            return
        if _nat and getattr(self, "native_role", "") == "doctor":
            self._work_doctor(dt)
            return
        if _nat and getattr(self, "native_role", "") == "trader":
            self._work_trader(dt)
            return
        if _nat and getattr(self, "native_role", "") == "miner":
            self._work_mine(dt)
            return
        if _nat and getattr(self, "native_role", "") == "smith":
            self._work_smith(dt)
            return
        if _nat and getattr(self, "native_role", "") == "weaver":
            self._work_weaver(dt)
            return
        if _nat and getattr(self, "native_role", "") == "spiceman":
            self._work_spiceman(dt)
            return
        if _nat and getattr(self, "native_role", "") == "gunsmith":
            self._work_gunsmith(dt)
            return
        if _nat and getattr(self, "native_role", "") == "soldier":
            self._work_soldier(dt)
            return
        if _nat and getattr(self, "native_role", "") == "unemployed":
            self._native_idle(dt)
            return
        if _nat and getattr(self, "native_role", "") == "farmer":
            self._native_share()
            if self._distribute_food(dt):
                return
            # THE SURPLUS GOES TO THE CHEST ONLY AFTER THE SETTLEMENT IS FED:
            # four to every person first, the remainder to the horse's larder.
            # A pack with no food in it (leaf, seeds) is deposited as before.
            _has_food = any(int(self.carry.get(i, 0) or 0) > 0 for i in economy.FOOD)
            if getattr(self, "_feeding_done", False) or not _has_food:
                self._feeding_done = False
                if self._deposit_to_chest(dt):
                    return
            if self.farm_plot is None:
                self._native_idle(dt)
                return
            if world is not None:
                if self._work_field(dt, world, now):
                    return
            return
        # THE BODY GROWS WITH THE SKILL, checked once a second and not once a
        # frame: a thousand men a tick is not where a float compare belongs.
        self._body_t = getattr(self, "_body_t", 0.0) - dt
        if self._body_t <= 0.0:
            self._body_t = 1.0
            try:
                stats.apply_body(self)
            except Exception:
                pass
        try:
            self.gate_tick(dt, now)
        except Exception:
            pass
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
        # A MAN HIRED BY THE PLAYER HAS ONE ERRAND: THE YARD. Before sleep,
        # before the watch, before a trade run -- a trader hired mid-run would
        # otherwise go on trading, and a man asleep would sleep through his
        # own hiring. He wakes, he comes indoors no more, and he walks there.
        _post = getattr(self, "work_post", None)
        # THE POST ALONE IS THE SIGNAL. `player_worker` is set in the process
        # that hires him; the lane that walks him is only told where the work
        # is, so requiring both meant he never moved at all.
        if _post is not None:
            self.asleep = False
            self.in_interior = False
            # STRAIGHT AT THE POST -- `steering.steer` already knows how to
            # leave a fenced town by its gate (`fence.cross_dir`). The extra
            # waypoint this used to compute aimed 140 px outside the gate and
            # then treated being within 22 px of THAT as arrival, so he stood
            # 22 px short of it and started again: an orbit on the spot.
            _d = math.hypot(_post[0] - self.x, _post[1] - self.y)
            if _d > 22.0:
                _nav = getattr(self, "_nav", None)
                if _nav is not None:
                    # A PLAN, NOT A NUDGE. The lane gives him an A* window built
                    # by pathfind.build; follow it. Straight-line steering is
                    # the fallback for when there is no plan yet.
                    try:
                        import pathfind as _pf
                        _ux, _uy = _pf.steer(self, _nav, _post[0], _post[1])
                        self.x += _ux * self.speed * dt
                        self.y += _uy * self.speed * dt
                        self.facing = (_ux, _uy)
                        self.skills.gain_movement(self.speed * dt)
                    except Exception:
                        self._step_toward(_post[0], _post[1], dt)
                else:
                    self._step_toward(_post[0], _post[1], dt)
            else:
                self.pause = 1.0
                self.target = (_post[0], _post[1])
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

        # A MAN IN A BRAWL IS CHASING ONE MAN AND NOTHING ELSE. mind.step
        # already moved him toward his punch target this tick; the schedule
        # must not move him a second way in the same tick, or he twitches
        # between the two tasks.
        if getattr(self, "_brawl_target", None) is not None:
            return

        if self.panic > 0.0 and threat is not None:
            self.panic -= dt
            # EVERY MAN HIS OWN DIRECTION. Running straight away from the gun
            # in one body is a parade; a crowd that bursts outward in all
            # directions is one the gunman cannot aim into safely.
            if getattr(self, "flee_dir", None) is None:
                dx, dy = self.x - threat.x, self.y - threat.y
                d = math.hypot(dx, dy) or 1.0
                a = math.atan2(dy, dx) + random.uniform(-1.05, 1.05)
                self.flee_dir = (math.cos(a), math.sin(a))
            fx, fy = self.flee_dir
            self.x += fx * 126.0 * dt
            self.y += fy * 126.0 * dt
            self.facing = (fx, fy)
            return
        self.flee_dir = None

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
                self.pause = self.rng.uniform(0.15, 0.6)
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
        _scale = speed_scale * mood.move_mult(self)
        self.x += ux * self.speed * _scale * dt
        self.y += uy * self.speed * _scale * dt
        self.facing = (ux, uy)
        self.skills.gain_movement(self.speed * _scale * dt)

    def _step_toward_excl(self, tx: float, ty: float, dt: float,
                          excl=None, speed_scale: float = 1.0) -> None:
        """Step toward a target that is ITSELF (or is surrounded by) colliders
        -- an ore chunk, a tree trunk. Excluding those boxes from the steering
        lets the man actually reach it, instead of being pushed one way then
        the other. `excl` may be one rect or a list of them."""
        rects = getattr(self, "_rects", ())
        if excl is not None and rects:
            if not isinstance(excl, (list, tuple, set)):
                excl = (excl,)
            rects = [r for r in rects
                     if not any(r.colliderect(e) for e in excl if e is not None)]
        ux, uy = steering.steer(self, tx, ty, rects, getattr(self, "_fences", ()))
        _scale = speed_scale * mood.move_mult(self)
        self.x += ux * self.speed * _scale * dt
        self.y += uy * self.speed * _scale * dt
        self.facing = (ux, uy)
        self.skills.gain_movement(self.speed * speed_scale * dt)

    def _field_obstruction(self, ttx: int, tty: int, g, world):
        """What stands on this field tile that must be cleared before farming:
        'block', 'station', 'tree' or 'plant' -- or None if the tile is bare."""
        wx = ttx * TILE + TILE / 2.0
        wy = tty * TILE + TILE / 2.0
        if g is not None:
            bb = getattr(g, "built_blocks", None)
            if bb and (ttx, tty) in bb:
                return "block"
            for wp in getattr(g, "placed_work", ()) or ():
                r = getattr(wp, "rect", None)
                if r is not None and r.collidepoint(wx, wy):
                    return "station"
            trees = getattr(g, "trees", None)
            if trees is not None:
                _orch = getattr(getattr(self, "native_camp", None),
                                "orchard_state", None)
                # An orchard tree on this tile is the logger's, not an
                # obstruction. Anything else is a wild tree, found by a few
                # cell lookups -- never trees.near(), which walked the whole
                # planted list for every tile of a big field every tick.
                if not (_orch and (ttx, tty) in _orch):
                    _cell = getattr(trees, "CELL", 180)
                    _cx = int(math.floor(wx / _cell))
                    _cy = int(math.floor(wy / _cell))
                    for _dx in (-1, 0, 1):
                        for _dy in (-1, 0, 1):
                            _tree = trees.tree(_cx + _dx, _cy + _dy)
                            if _tree is None or getattr(_tree, "felled", False):
                                continue
                            if (math.hypot(_tree.x - wx, _tree.y - wy)
                                    <= TILE * 0.7 + _tree.canopy_r):
                                return "tree"
        try:
            import wildcrop as _wc
            if _wc.at(world, ttx, tty) is not None:
                return "plant"
        except Exception:
            pass
        return None

    def _field_clear(self, ttx: int, tty: int, g, world, now: float) -> bool:
        """Clear whatever stands on the tile and take it into the pack: wood
        from a tree, the block he cuts down, the plant's own yield. A workbench
        is demolished for nothing, exactly like the player's demolish."""
        wx = ttx * TILE + TILE / 2.0
        wy = tty * TILE + TILE / 2.0
        if g is None:
            return False
        # A PLACED 1x1 BLOCK goes straight into his pack.
        bb = getattr(g, "built_blocks", None)
        if bb and (ttx, tty) in bb:
            kind = bb.pop((ttx, tty))
            self.stock[kind] = self.stock.get(kind, 0) + 1
            return True
        # A WORKBENCH is demolished for nothing.
        for wp in list(getattr(g, "placed_work", ()) or ()):
            r = getattr(wp, "rect", None)
            if r is not None and r.collidepoint(wx, wy):
                try:
                    g.placed_work.remove(wp)
                except Exception:
                    pass
                return True
        # A STANDING TREE is felled for its wood -- but NOT an orchard tree:
        # those are the logger's, and a farmer cutting them was the
        # "plant then cut immediately" glitch when an orchard sat beside a
        # field and the boundary tile belonged to both.
        trees = getattr(g, "trees", None)
        if trees is not None:
            _orch = getattr(getattr(self, "native_camp", None),
                            "orchard_state", None)
            for tree in trees.near(wx, wy, TILE * 0.7):
                if getattr(tree, "felled", False):
                    continue
                if _orch and (ttx, tty) in _orch:
                    continue
                trees.fell(tree, now)
                amt = self.rng.randint(10, 30)
                self.stock["wood"] = self.stock.get("wood", 0) + amt
                return True
        # A WILD PLANT is picked for whatever it carried.
        try:
            import wildcrop as _wc
            got = _wc.at(world, ttx, tty)
            if got is not None:
                kind, stage = got

                class _Stock:
                    __slots__ = ("npc",)

                    def __init__(self, npc):
                        self.npc = npc

                    def add(self, item, amount, grade=None):
                        self.npc.stock[item] = self.npc.stock.get(item, 0) + int(amount)

                _wc.harvest(world, ttx, tty, kind, stage,
                            _Stock(self), lambda *a, **k: None, None)
                return True
        except Exception:
            pass
        return False

    def _grow_orchard(self, camp, now: float) -> None:
        """Saplings grow toward their full size over ORCHARD_GROW_SECONDS,
        exactly like a wild stump putting up a new tree. Idempotent and
        time-based, so every logger's tick may call it."""
        state = getattr(camp, "orchard_state", None)
        if not state:
            return
        for key, st in list(state.items()):
            tree = st.get("tree")
            if tree is None or getattr(tree, "felled", False):
                continue
            target = float(st.get("target_r", 72.0))
            if tree.canopy_r >= target:
                continue
            planted_at = float(st.get("planted_at", now))
            frac = min(1.0, (now - planted_at) / ORCHARD_GROW_SECONDS)
            r = 24.0 + (target - 24.0) * frac
            if abs(r - tree.canopy_r) < 0.05:
                continue
            tree.canopy_r = r
            try:
                import trees as _trees
                tree.size_class = min(range(len(_trees.SIZES)),
                                     key=lambda i: abs(_trees.SIZES[i] - r))
            except Exception:
                pass
            trunk_w = max(10, int(r * 0.24))
            tree.trunk_rect = pygame.Rect(tree.x - trunk_w / 2.0,
                                          tree.y - trunk_w * 0.6,
                                          trunk_w, trunk_w * 1.5)

    def _orchard_trunks(self, camp):
        """The orchard's trunk rects, CACHED. It used to be rebuilt every
        tick (O(orchard trees)); now it rebuilds only when a tree is planted
        or felled, or every 30 ticks to catch the slow trunk growth."""
        state = getattr(camp, "orchard_state", None) or {}
        _tick = getattr(self, "_trunks_tick", 0)
        _cached = getattr(self, "_trunks_cache", None)
        if (_cached is not None
                and not getattr(self, "_trunks_dirty", True)
                and (_tick - getattr(self, "_trunks_built", -999)) < 30):
            return _cached
        trunks = []
        for _st in state.values():
            _tr = _st.get("tree") if _st else None
            if _tr is not None and not getattr(_tr, "felled", False):
                _trr = getattr(_tr, "trunk_rect", None)
                if _trr is not None:
                    trunks.append(_trr)
        self._trunks_cache = trunks
        self._trunks_dirty = False
        self._trunks_built = _tick
        return trunks

    def _work_orchard(self, dt: float, world, now: float) -> bool:
        """An orchard logger: plant a sapling on a bare tile, let it grow,
        cut a full tree down with the axe (the same chop as the player), and
        replant -- the orchard's own wood ends up in the camp's store."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            return False
        g = getattr(camp, "g", None)
        self._trunks_tick = getattr(self, "_trunks_tick", 0) + 1
        self._grow_orchard(camp, now)
        job = getattr(self, "orchard_plot", None)
        plots = getattr(camp, "orchard_plots", None) or ()
        if job is None or job >= len(plots):
            self._native_idle(dt)
            return True
        ctx, cty = plots[job]
        tiles = camp.orchard_tiles.get((ctx, cty), ())
        state = getattr(camp, "orchard_state", None)
        if state is None:
            state = {}
            camp.orchard_state = state
        # CACHE THE DECISION (which tile to cut / which to plant). It was a
        # full orchard scan every tick; it re-scans only on a tree change or
        # every 120 ticks to catch a sapling reaching full size.
        _tick = getattr(self, "_trunks_tick", 0)
        _task = getattr(self, "_orchard_task", None)
        if (_task is not None
                and not getattr(self, "_trunks_dirty", False)
                and (_tick - getattr(self, "_orchard_task_tick", -999)) < 120):
            cut_tile, plant_tile = _task
        else:
            cut_tile = None
            plant_tile = None
            for (tx, ty) in tiles:
                st = state.get((tx, ty))
                tree = st.get("tree") if st else None
                if tree is None or getattr(tree, "felled", False):
                    if plant_tile is None:
                        plant_tile = (tx, ty)
                elif tree.canopy_r >= float(st.get("target_r", 72.0)):
                    if cut_tile is None:
                        cut_tile = (tx, ty)
            _task = (cut_tile, plant_tile)
            self._orchard_task = _task
            self._orchard_task_tick = _tick
            cut_tile, plant_tile = _task
        # THE LOGGER WALKS FREELY AMONG HIS OWN ORCHARD TREES: every trunk in
        # the orchard is excluded from his steering, so he never orbits one.
        # CACHED (see _orchard_trunks) -- not rebuilt every tick.
        _trunks = self._orchard_trunks(camp)
        if cut_tile is None and plant_tile is None:
            # nothing to do: every sapling is still growing
            tx = ctx * TILE + TILE / 2.0
            ty = cty * TILE + TILE / 2.0
            if math.hypot(tx - self.x, ty - self.y) > 40.0:
                self._step_toward_excl(tx, ty, dt, excl=_trunks, speed_scale=0.7)
            return True
        ttx, tty = cut_tile if cut_tile is not None else plant_tile
        tx = ttx * TILE + TILE / 2.0
        ty = tty * TILE + TILE / 2.0
        if math.hypot(tx - self.x, ty - self.y) > 14.0:
            self._step_toward_excl(tx, ty, dt, excl=_trunks)
            return True
        if cut_tile is not None:
            st = state.get((ttx, tty))
            tree = st.get("tree") if st else None
            if tree is None:
                return True
            self.facing = (0.0, 1.0)
            self.chop_timer += dt
            if self.chop_timer >= LOG_CHOP_SECONDS / (1.0 + self.skills.axe):
                if not self._swing_tool("axe"):
                    return True
                self.chop_timer = 0.0
                self._snd("chop", min_gap=0.5)
                # drop the tree out of the world (no stump: he replants a
                # sapling himself, like a field worker sows the next crop)
                trees_obj = getattr(g, "trees", None) if g is not None else None
                planted = getattr(trees_obj, "_planted", None) if trees_obj is not None else None
                if planted is not None:
                    try:
                        planted.remove(tree)
                    except ValueError:
                        pass
                economy.cut_wood(camp, self,
                                 self.rng.randint(FELL_LOGS_MIN, FELL_LOGS_MAX))
                state.pop((ttx, tty), None)
                self._trunks_dirty = True
                self._did_work()
                self.skills.gain_axe()
            return True
        # PLANT A SAPLING: a smaller version of the tree, straight into the
        # ground -- no tilling, no watering.
        if g is None:
            return True
        trees_obj = getattr(g, "trees", None)
        if trees_obj is None:
            return True
        wx = ttx * TILE + TILE / 2.0
        wy = tty * TILE + TILE / 2.0
        try:
            import biomes as _bio
            _t = float(_bio.temperature(wx, wy, int(getattr(g.world, "seed", 1))))
            snowy = _t < 0.34
        except Exception:
            snowy = False
        species = "conifer" if snowy else "broadleaf"
        try:
            tree = trees_obj.plant(wx, wy, 24.0, variant=self.rng.randrange(8),
                                   species=species, snowy=snowy)
        except TypeError:
            tree = trees_obj.plant(wx, wy, 24.0, species=species, snowy=snowy)
        state[(ttx, tty)] = {"tree": tree, "target_r": self.rng.uniform(56.0, 90.0),
                             "planted_at": now}
        self._trunks_dirty = True
        self._did_work()
        return True

    def _field_pick_task(self, village, ctx, cty, world, now):
        """Scan the field ONCE and pick the next task (clear/harvest/plant/
        water/till). Returns (ttx, tty, action, tkind) or None."""
        g = getattr(village, "g", None)
        todo = {}
        for ttx, tty, tkind in village.farm_tiles[(ctx, cty)]:
            # CLEAR THE GROUND FIRST: a tree, a wild plant, a placed block, or
            # a workbench in the way is removed before the tile can be farmed.
            if self._field_obstruction(ttx, tty, g, world) is not None:
                todo.setdefault("clear", (ttx, tty, None))
                continue
            plot = world.plot_at(ttx, tty)
            state = plot.kind if plot is not None else None
            if state in crop.FOOD_KINDS or state in crop.LEAF_KINDS or state in crop.FIBRE_KINDS:
                _grow = getattr(plot, "grow", None) or crop.GROW_SECONDS
                if (plot.planted_at is not None
                        and now - plot.planted_at >= _grow):
                    todo.setdefault("harvest", (ttx, tty, tkind))
            elif state == "fertile":
                if getattr(self, "conquered", False):
                    _seed = crop.CROP_SEED.get(tkind)
                    if _seed is not None and self._count_item(_seed) <= 0:
                        continue
                todo.setdefault("plant", (ttx, tty, tkind))
            elif state == "dirt":
                todo.setdefault("water", (ttx, tty, tkind))
            else:
                todo.setdefault("till", (ttx, tty, tkind))
        _order = ["clear", "harvest", "plant", "water", "till"]
        for action in _order:
            if action in todo:
                ttx, tty, tkind = todo[action]
                return (ttx, tty, action, tkind)
        return None

    def _work_field(self, dt: float, world, now: float) -> bool:
        """Tend the assigned field one action at a time. The task is CACHED:
        the field is scanned once per action, never once a frame."""
        job: Any = self.farm_plot
        village = self.village if self.village is not None else getattr(self, "native_camp", None)
        if job is None or village is None or job >= len(village.farm_plots):
            return False
        ctx, cty, kind = village.farm_plots[job]
        g = getattr(village, "g", None)
        # ONE REAL AFFINITY HOOK (NPC.md Phase 1): a sensing farmer walks the
        # field and learns the work faster than an intuitive one.  It is a
        # multiplier, not a new rule, and an untyped/legacy farmer is neutral.
        try:
            _work_mult = persona.work_mult(self, "farmer") * mood.work_mult(self)
            _gain_mult = persona.gain_mult_for_job(self, "farmer", "farming")
        except Exception:
            _work_mult = _gain_mult = 1.0

        task = getattr(self, "_field_task", None)
        if task is None:
            task = self._field_pick_task(village, ctx, cty, world, now)
            if task is None:                # nothing to do: wait by the field
                tx, ty = ctx * TILE + TILE / 2.0, cty * TILE + TILE / 2.0
                if math.hypot(tx - self.x, ty - self.y) > 40.0:
                    self._step_toward(tx, ty, dt, 0.7 * _work_mult)
                return True
            if task[2] == "till":
                can_till = self.tool_uses > 0 or self.stock.get("shovel", 0) > 0
                if not can_till:
                    self._go_to_market(dt)
                    return True
            self._field_task = task

        ttx, tty, action, tkind = task
        tx = ttx * TILE + TILE / 2.0
        ty = tty * TILE + TILE / 2.0
        if math.hypot(tx - self.x, ty - self.y) > 12.0:
            self._step_toward(tx, ty, dt, _work_mult)
            return True
        if action == "clear":
            self._field_clear(ttx, tty, g, world, now)
        elif action == "harvest":
            plot = world.plot_at(ttx, tty)
            if plot is not None:
                if getattr(plot, "blight", False):
                    # Diseased plants yield nothing; the farmer clears the tile.
                    world.set_plot(ttx, tty, "grass", None)
                    self._field_task = None
                    self._did_work()
                    self._snd("harvest", min_gap=0.3)
                    return True
                if getattr(village, "is_hub", False):
                    _note("FIELD   %s harvests %s at %d,%d"
                          % (getattr(self, "name", "?"), plot.kind, ttx, tty))
                economy.harvest(village, self, plot.kind, self.rng)
                self._snd("harvest", min_gap=0.3)
                self.skills.gain_farming(0.02 * _gain_mult)  # reaping hones the hand, slowly
                try:
                    persona.maybe_green_thumb(self, self.rng)
                except Exception:
                    pass
                if getattr(self, "conquered", False):
                    _seed = crop.CROP_SEED.get(plot.kind)
                    if _seed is not None:
                        _nseed = 1 + (1 if self.rng.random() < 0.5 else 0)
                        if persona.has_trait(self, "green_thumb"):
                            _nseed += 1
                        self._give_item(_seed, _nseed)
            world.set_plot(ttx, tty, "grass", None)     # the soil is spent
        elif action == "till":
            if not self._swing_tool():
                return True                     # no shovel: we must buy one
            world.set_plot(ttx, tty, "dirt", None)
            self._snd("till", min_gap=0.3)
        elif action == "water":
            world.set_plot(ttx, tty, "fertile", None)
        else:                                    # plant the seed for that cell
            if getattr(self, "conquered", False):
                _seed = crop.CROP_SEED.get(tkind)
                if _seed is not None and not self._take_item(_seed, 1):
                    return True                 # no seed in his pockets: cannot sow
            world.set_plot(ttx, tty, tkind, now,
                           crop.grow_seconds(self.skills.farming))
            self._snd("plant", min_gap=0.3)
        ground = getattr(world, "ground", None)
        if ground is not None:
            _immediate = False
            if g is not None:
                _wx = ttx * TILE + TILE / 2.0
                _wy = tty * TILE + TILE / 2.0
                if (g.cam_x - TILE <= _wx <= g.cam_x + g.vw + TILE
                        and g.cam_y - TILE <= _wy <= g.cam_y + g.vh + TILE):
                    _immediate = True
            ground.invalidate_tile(ttx, tty, immediate=_immediate)
        self._field_task = None      # done: re-scan next tick
        self._did_work()           # planted, watered, reaped or broke ground
        return True
    def _did_work(self) -> None:
        """He has just DONE a piece of work. Raise the working face for a
        moment; tick() runs it down again.

        Deliberately not `if it is the working day`: a man standing idle in a
        field at eleven in the morning is not concentrating, and a man who
        swings once at dawn should show it once. The flag belongs to the act.
        """
        self.work_flash = face.WORK_SECONDS

    def _did_attack(self) -> None:
        """He has just thrown a blow. Raise the war face for a moment.

        Longer than his own swing, so a fight keeps it lit and the peace takes
        it away -- rather than it blinking on and off between swings.

        `attacked_flash` is the same news for the OTHER side of the fight: the
        man in front of him can see the blow going up, and that is the whole
        trigger for throwing himself backwards out of it.
        """
        self.attack_flash = face.WAR_SECONDS
        self.attacked_flash = 0.30

    def _melee_swing(self, combat, angle: float) -> None:
        """Animate a melee swing: a short weapon sweep. Only when the warrior
        is actually on the player's screen -- off-screen fights don't spend a
        frame animating something nobody can see."""
        g = getattr(getattr(self, "native_camp", None), "g", None)
        if g is not None:
            vw = getattr(g, "vw", 0) or 0
            vh = getattr(g, "vh", 0) or 0
            if not (g.cam_x - 80.0 < self.x < g.cam_x + vw + 80.0
                    and g.cam_y - 80.0 < self.y < g.cam_y + vh + 80.0):
                return
        self.swing_anim = NPC_SWING_SECONDS
        if combat is not None:
            try:
                combat.spawn_swing(self.x, self.y, angle, width=0.7)
            except Exception:
                pass

    def _swing_tool(self, item: str = "shovel") -> bool:
        """Wear the tool in hand, taking a spare from the crate when it breaks.
        A finer tool lasts longer -- but never long enough to pay for itself,
        because the price climbs faster than the work does. False means there is
        nothing left to work with, and he must go and buy one."""
        # WHICH TOOL THESE USES BELONG TO. A man keeps his `tool_uses` when he
        # changes trade -- it counted down a shovel he has since put down, and
        # would go on reading "plenty left" for a pickaxe he has never owned.
        # Written here, at the swing, because this is where a tool is picked up.
        self.tool_kind = item
        # TOOLS DO NOT WEAR OUT, FOR ANYBODY, FOR NOW. A man picks up a tool
        # and it is his until he loses it: no uses ticked down, nothing to
        # replace, no trip to the smith to buy one. What still runs out is
        # AMMUNITION -- a rifle spends rounds exactly as it did before (that is
        # guns.py and _round_ready, untouched).
        if self.tool_uses <= 0:
            if self.stock.get(item, 0) <= 0:
                return False
            g = economy.grade_of(self, item)
            self.tool_uses = max(1, int(economy.TOOL_USES * economy.tool_dur_mult(g)))
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
            # A PLAN, NOT A NUDGE: the tree stands outside the gate, and local
            # steering cannot solve a pinch between fence and gate -- a logger
            # orbited the wall and never cut a tree. Follow the A* plan when
            # the lane has built one; otherwise fall back to local steering.
            _nav = getattr(self, "_nav", None)
            if _nav is not None:
                try:
                    import pathfind as _pf
                    ux, uy = _pf.steer(self, _nav, target.x, target.y)
                except Exception:
                    ux, uy = 0.0, 0.0
            else:
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
            economy.cut_wood(self.village, self,
                             self.rng.randint(FELL_LOGS_MIN, FELL_LOGS_MAX))
            # A TREE DOWN IS THE ACT, not the swing that happened to land on
            # this frame. Raising the face in _swing_tool pinned it on: the
            # pit swings once per FRAME, so a miner would have worn the
            # tongue every frame of the day instead of at each piece of work.
            self._did_work()
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
        _drink = getattr(self, "wants_drink", None)
        if (_drink and self.stock.get(_drink, 0) <= 0
                and self.stock.get("govbeer", 0) <= 0
                and self.yearning >= economy.YEARING_BUY):
            needs.append("govbeer")          # the cheap bottle on the shelf
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
        # THE STATE'S SHELF IS OPEN. A thirsty man with the coin buys the
        # government's bottle straight off the ledger -- he does not have to
        # wait for a neighbour to be selling a drink.
        if "govbeer" in needs:
            _have = int(vl.ledger_goods.get("govbeer", 0))
            if _have > 0:
                _price = max(1, economy.ledger_value(vl, "govbeer"))
                if self.coins >= _price:
                    if economy._settle(vl, "govbeer", _price, 1, None, self):
                        return True
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
                # THE WHOLESALE HOUSE. No neighbour has any -- but the TOWN
                # may. A logger's wood is the town's now (see cut_wood), and
                # the ledger is where the people buy it: `_settle` with no
                # seller is the house itself, and the coin goes to the ledger
                # that pays the loggers' wages. Without this a man whose
                # neighbours were all out of firewood simply gave up and spent
                # the night cold, with a store full of logs behind the fence.
                for item in needs:
                    if int(vl.ledger_goods.get(item, 0)) <= 0:
                        continue
                    price = max(1, economy.ledger_value(vl, item))
                    if self.coins < price:
                        continue
                    if economy._settle(vl, item, price, 1, None, self):
                        return True
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
        """FILL THE CART AT THE VILLAGE LEDGER, LOT BY LOT, BY ITS GRADE.

        The granary used to ask one price -- the blend of everyone's grades --
        while handing over the WORST lot first (economy.store_take takes the
        poor leaf before the good). A trader paid good-leaf money and carried
        floor sweepings. Each lot is now priced at its own grade and taken in
        the same order it is priced, and the grade comes aboard with it.
        """
        got = 0
        book = getattr(village, "ledger_lots", None) or {}
        lots = book.get(item) or {}
        if not lots:
            # A shelf with no lot book (an old save): one grade, the shelf's.
            grade = int((getattr(village, "ledger_grade", None) or {}).get(item, 3))
            lots = {grade: int((getattr(village, "ledger_goods", None) or {}).get(item, 0))}
        for grade in sorted(int(g) for g in lots):
            if got >= want:
                break
            have_lot = int(lots.get(grade, 0) or 0)
            if have_lot <= 0:
                continue
            price = max(1, int(round(economy.prospect(village, item, grade))))
            take = int(min(have_lot, want - got,
                           self.coins // max(0.05, price)))
            if take <= 0:
                continue
            economy.store_take(village, item, take)
            village.ledger_coins += take * price
            self.coins -= take * price
            held = int(self.stock.get(item, 0))
            self.stock[item] = held + take
            try:
                import quality as _q
                if not isinstance(getattr(self, "grade", None), dict):
                    self.grade = {}
                self.grade[item] = _q.merge(int(self.grade.get(item, 3)),
                                            held, grade, take)
            except Exception:
                pass
            got += take
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
        self.flee_dir = None
        ang = random.uniform(0.0, 2.0 * math.pi)
        dist = random.uniform(0.25, 0.85) * dest.radius
        self.x = dest.x + math.cos(ang) * dist
        self.y = dest.y + math.sin(ang) * dist
        if self not in dest.npcs:
            dest.npcs.append(self)
        dest.refugees = getattr(dest, "refugees", 0) + 1
        dest._fill_vacancies()        # a hand that arrives is a hand put to work
        # A REFUGEE TELLS THE NEW TOWN WHAT HE KNOWS.
        dest.learn_killers(self.knows, now, teller=self)

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

    LUNGE_SECONDS = 0.20
    LUNGE_MULT = 3.0
    LUNGE_COST = 0.25          # of his own full stamina
    LUNGE_CD = 2.4

    def _wants_lunge_away(self, target, distance: float) -> bool:
        """THE ONE RULE: AN ENEMY IS ATTACKING, CLOSE ENOUGH, AND HE HAS WIND.

        Not a plan and not a dice roll. If the man in front of him has just
        swung (or is coming in), and he is inside that man's reach, and there is
        at least a quarter of his wind left, he throws himself backwards out of
        it. That is the whole of it.
        """
        if getattr(target, "dead", False) or not getattr(target, "alive", True):
            return False
        if distance > 64.0:
            return False                      # not in his reach: nothing to dodge
        if self.stamina < self.max_stamina * self.LUNGE_COST:
            return False                      # too spent to move
        coming = (getattr(target, "swing_anim", 0.0) > 0.0      # the player
                  or getattr(target, "attacked_flash", 0.0) > 0.0  # a man
                  or getattr(target, "lunging", 0.0) > 0.0)        # a lunge
        return bool(coming)

    def _nearest_breakable(self, g, reach=400.0):
        best, bd = None, reach * reach
        for seq_name in ("built_chests", "built_signs", "built_foodboxes",
                         "placed_work"):
            for obj in (getattr(g, seq_name, ()) or ()):
                if getattr(obj, "broken", False):
                    continue
                # The campfire is not a thing to smash; it is the place
                # people stand.  Sprees go for the chest/bench/sign instead.
                if getattr(obj, "kind", None) == "fireplace":
                    continue
                ox = float(getattr(obj, "x", 0.0))
                oy = float(getattr(obj, "y", 0.0))
                d = (ox - self.x) ** 2 + (oy - self.y) ** 2
                if d < bd:
                    best, bd = obj, d
        return best

    def _berserk_target(self, g):
        best, score = None, 1e18
        people = list(self._camp_people())
        try:
            player = getattr(g, "player", None)
            if player is not None and math.hypot(player.x - self.x,
                                                  player.y - self.y) <= 300.0:
                people.append(player)
        except Exception:
            pass
        for other in people:
            if other is self or not getattr(other, "alive", True):
                continue
            if math.hypot(other.x - self.x, other.y - self.y) > 300.0:
                continue
            oid = getattr(other, "id", "player") or "player"
            try:
                import economy
                op = float(economy.opinion_of(self, oid).get(oid, 0.0))
            except Exception:
                op = 0.0
            if op < score:
                best, score = other, op
        return best

    def _break_action(self, dt: float, combat, now: float) -> None:
        """The dangerous break states: berserk and breaking spree."""
        # A SHORT BRAWL FROM AN INSULT.  It is not a major break; it runs for
        # a few seconds and stops when the target yields or the timer ends.
        _brawl = getattr(self, "_brawl_target", None)
        if _brawl is not None:
            if (getattr(_brawl, "alive", True)
                    and now < float(getattr(self, "_brawl_until", 0.0))):
                self._fight(dt, _brawl, combat)
                return
            self._brawl_target = None
        state = getattr(self, "break_state", "normal")
        if state == "depression":
            if now >= float(getattr(self, "break_until", 0.0)):
                mood.clear_break(self, now)
            return
        if state == "crop_spree":
            if now >= float(getattr(self, "break_until", 0.0)):
                mood.clear_break(self, now)
                return
            camp = getattr(self, "native_camp", None)
            g = getattr(camp, "g", None) if camp is not None else None
            if g is None:
                return
            target = getattr(self, "_crop_target", None)
            if target is None:
                tiles = []
                for _key, _lst in (getattr(camp, "farm_tiles", {}) or {}).items():
                    for _t in (_lst or ()):
                        try:
                            tx, ty = int(_t[0]), int(_t[1])
                            if g.world.plot_at(tx, ty) is not None:
                                tiles.append((tx, ty))
                        except Exception:
                            pass
                if not tiles:
                    mood.clear_break(self, now)
                    return
                target = min(tiles,
                             key=lambda t: (t[0] * 32.0 - self.x) ** 2
                             + (t[1] * 32.0 - self.y) ** 2)
                self._crop_target = target
            tx, ty = target
            cx, cy = tx * 32.0 + 16.0, ty * 32.0 + 16.0
            if math.hypot(cx - self.x, cy - self.y) > 22.0:
                self._step_toward(cx, cy, dt)
                return
            self._break_action_t = getattr(self, "_break_action_t", 0.0) - dt
            if self._break_action_t > 0.0:
                return
            self._break_action_t = 1.0
            try:
                if g.world.plot_at(tx, ty) is not None:
                    g.world.set_plot(tx, ty, "grass", None)
                    try:
                        g.ground.invalidate_tile(tx, ty, immediate=True)
                    except Exception:
                        pass
                    self._did_attack()
            except Exception:
                pass
            self._crop_target = None
            return
        if state in ("drunk", "tripping"):
            if now >= float(getattr(self, "break_until", 0.0)):
                mood.clear_break(self, now)
            return
        if state not in ("berserk", "breaking_spree"):
            return
        camp = getattr(self, "native_camp", None)
        g = getattr(camp, "g", None) if camp is not None else None
        if g is None:
            return
        if now >= float(getattr(self, "break_until", 0.0)):
            # A major break ends on its clock even if the victim is still
            # standing; the end is catharsis, not a permanent rampage.
            mood.clear_break(self, now)
            self._break_target = None
            return
        if state == "berserk":
            target = getattr(self, "_break_target", None)
            if target is None or not getattr(target, "alive", True):
                self._break_scan_t = getattr(self, "_break_scan_t", 0.0) - dt
                if self._break_scan_t <= 0.0:
                    self._break_scan_t = 2.0
                    target = self._berserk_target(g)
                    self._break_target = target
            if target is not None and getattr(target, "alive", True):
                self._fight(dt, target, combat)
                return
            if now >= float(getattr(self, "break_until", 0.0)):
                mood.clear_break(self, now)
                self._break_target = None
            return

        # BREAKING SPREE: attack breakables until the timer runs out.
        target = getattr(self, "_break_target", None)
        # A SPREE TARGET MUST BE A BREAKABLE, NOT A PERSON.  Berserk leaves
        # a person in _break_target; without this guard the next spree would
        # keep chasing that person (usually the player) instead of the chest.
        if target is not None and not hasattr(target, "condition"):
            target = None
        if target is None or getattr(target, "broken", False):
            # In the test lab, a selected person can be anywhere in the
            # fixture; still let the spree find its target.  Real settlements
            # keep the 400 px rule.
            _reach = 1200.0 if getattr(camp, "lab", False) else 400.0
            self._break_target = target = self._nearest_breakable(g, _reach)
        if target is None:
            # No breakable left in reach: keep the state until its timer ends,
            # then catharsis.  Do not silently end a major break early.
            if now >= float(getattr(self, "break_until", 0.0)):
                mood.clear_break(self, now)
            return
        if now >= float(getattr(self, "break_until", 0.0)):
            mood.clear_break(self, now)
            return
        if math.hypot(target.x - self.x, target.y - self.y) > 46.0:
            self._step_toward(target.x, target.y, dt)
            return
        self._break_action_t = getattr(self, "_break_action_t", 0.0) - dt
        if self._break_action_t > 0.0:
            return
        self._break_action_t = 1.0
        self._did_attack()
        # Make the hit visible, not a man standing still beside a chest.
        self._melee_swing(combat, math.atan2(target.y - self.y,
                                             target.x - self.x))
        self._snd("npc_attack", min_gap=1.0)
        armed = bool(self.arm())
        damage = 35.0 if armed else 12.0
        target.condition = max(0.0, float(getattr(target, "condition", 100.0)) - damage)
        if target.condition <= 0.0:
            # DESTROYED MEANS DESTROYED.  The object leaves the world and
            # everything it held goes with it -- no repair, no loot, no ghost
            # inventory.  A chest is not a visual state.
            self._spree_broken = int(getattr(self, "_spree_broken", 0) or 0) + 1
            self._break_target = None
            _kind = type(target).__name__
            for _seq_name in ("built_chests", "built_signs", "built_foodboxes",
                              "placed_work"):
                _seq = getattr(g, _seq_name, None)
                if _seq is not None and target in _seq:
                    try:
                        _seq.remove(target)
                    except ValueError:
                        pass
            try:
                if target in (getattr(g.player, "workplaces", ()) or ()):
                    g.player.workplaces.remove(target)
            except Exception:
                pass
            try:
                target.worker = None
            except Exception:
                pass
            try:
                # The chest's contents are destroyed with it, not left on a
                # dead object someone could still reach.
                target.inventory = None
            except Exception:
                pass
            try:
                g.toast("%s destroyed" % _kind)
            except Exception:
                pass
            try:
                import plog
                plog.log("DESTROYED", _kind, "by",
                         getattr(self, "name", "?"))
            except Exception:
                pass

    def _fight(self, dt: float, target, combat) -> None:
        dx, dy = target.x - self.x, target.y - self.y
        self._foe_last = (target.x, target.y)
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = dx / distance, dy / distance
        self.facing = (ux, uy)
        self.attacked_flash = max(0.0, self.attacked_flash - dt)

        # THE DODGE. One rule: the man in front of him is attacking, he is
        # inside that man's reach, and he has the wind -- so he throws himself
        # backwards out of it. A fifth of a second at three times his walk, a
        # quarter of his stamina, and then two and a half seconds before he can
        # do it again (a man cannot dodge twice in one breath).
        if self.lunging > 0.0:
            self.lunging = max(0.0, self.lunging - dt)
            self.x -= ux * self.combat_speed * self.LUNGE_MULT * dt
            self.y -= uy * self.combat_speed * self.LUNGE_MULT * dt
            return
        self.lunge_cd = max(0.0, self.lunge_cd - dt)
        # A NATIVE WARRIOR DOES NOT RUN BACKWARD. He stands his ground and
        # answers with the 45-degree sidestep (combat_actions). The backward
        # lunge stays for villagers fighting beasts.
        if (getattr(self, "native_role", "") != "warrior"
                and self.lunge_cd <= 0.0
                and self._wants_lunge_away(target, distance)):
            self.lunging = self.LUNGE_SECONDS
            self.lunge_cd = self.LUNGE_CD
            self.stamina = max(0.0, self.stamina
                               - self.max_stamina * self.LUNGE_COST)
            try:
                import plog
                plog.log("LUNGE", getattr(self, "name", "?"), "away from",
                         getattr(target, "name", "?"), "dist", int(distance),
                         "stamina", int(self.stamina))
            except Exception:
                pass
            self.x -= ux * self.combat_speed * self.LUNGE_MULT * dt
            self.y -= uy * self.combat_speed * self.LUNGE_MULT * dt
            return
        if self.weapon == "rifle":
            # A RIFLE IS FOR BEASTS, NOT PEOPLE. Against any person -- villager,
            # soldier, the player -- he closes and swings his fists. The rifle
            # comes out only for a wolf at the fence.
            if getattr(target, "kind", "") != "wolf":
                self.x += ux * self.combat_speed * 1.3 * dt
                self.y += uy * self.combat_speed * 1.3 * dt
                self.attack_cd -= dt
                if distance <= 34.0 and self.attack_cd <= 0.0:
                    self.attack_cd = max(0.5, self.skills.axe_cooldown())
                    self._did_attack()
                    self._melee_swing(combat, math.atan2(dy, dx))
                    self._snd("npc_attack", min_gap=1.5)
                    self.skills.gain_axe()
                    if hasattr(target, "take_damage"):
                        target.take_damage(max(1, round(
                            (35.0 / 3.0) * self.skills.axe_damage_scale()
                            * persona.melee_mult(self))))
                return
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
            _n = guns.rounds_now(self, dt, self.attack_cd <= 0.0
                                 and combat is not None and distance <= 460.0)
            for _ in range(_n):
                angle = math.atan2(dy, dx) + random.uniform(-0.03, 0.03)
                mx, my = self.x + ux * 16.0, self.y + uy * 16.0
                ex = mx + math.cos(angle) * (distance + 120.0)
                ey = my + math.sin(angle) * (distance + 120.0)
                if not friendly_in_line(mx, my, ex, ey, self, self.team,
                                        getattr(self, "_soldiers", ()),
                                        getattr(self, "_player", None), self.nation):
                    if self._round_ready():
                        if self.attack_cd <= 0.0:
                            self.attack_cd = random.uniform(0.5, 0.9)
                        self._did_attack()
                        self._snd("npc_attack", min_gap=1.5)
                        self._shoot(combat, mx, my, angle, distance + 120.0, 80, 80)
        else:
            # Axe work. THE SAME REACH AS THE PLAYER: the player's axe reaches
            # 64 px PLUS the target's body, and so does the warrior's -- the
            # player was able to stand just inside his own longer reach and
            # hit the warrior while the warrior's plain 64 px could not reach
            # back. Now whoever is in range hits.
            _reach = 96.0 + getattr(target, "radius", 12.0)
            lunged = getattr(target, "lunging", 0.0) > 0.0
            sprint = self.stamina > 0.0
            step = self.combat_speed * ((1.9 if lunged else 1.6)
                                        if sprint else 1.0) * dt
            burn = 2.0 if lunged else 1.0
            if distance > _reach:                   # too far: close him down
                self.x += ux * step
                self.y += uy * step
                self._wind(False, dt)
            elif distance < _reach - 14.0:
                # He is getting inside the swing. Give a little ground, but
                # keep within reach so the axe still lands.
                self.x -= ux * step
                self.y -= uy * step
                self._wind(sprint, dt, burn)
            else:
                # Jockeying for the gap costs the legs, and the warrior CIRCLES:
                # a sidestep around the player means two warriors attack from
                # different angles, so dodging one does not dodge the other.
                self.stamina = max(0.0, self.stamina - 10.0 * dt)
                self.x += -uy * self.strafe_dir * self.combat_speed * 0.35 * dt
                self.y += ux * self.strafe_dir * self.combat_speed * 0.35 * dt
            self.attack_cd -= dt
            if distance <= _reach and self.attack_cd <= 0.0:
                # THE SWING COMES AS FAST AS HIS SKILL: a master swings a
                # fraction of a second, a green man once a second and a half.
                self.attack_cd = max(0.35, self.skills.axe_cooldown())
                self._did_attack()
                self._melee_swing(combat, math.atan2(dy, dx))
                self._snd("npc_attack", min_gap=1.5)
                if hasattr(target, "take_damage"):
                    self.skills.gain_axe()
                    # A MAN WITH AN AXE SWINGS AN AXE; A MAN WITHOUT ONE SWINGS
                    # HIS FISTS. Same motion, same skill, a third of the
                    # damage -- see skills.UNARMED_WEAKNESS. Before this he
                    # fought bare-handed at full axe weight, so an unarmed
                    # villager hit as hard as an armed one.
                    _armed = (self.stock.get("axe", 0) > 0
                              or self.job == "logger")
                    _base = (10.0 if _armed
                             else 10.0 / skills.UNARMED_WEAKNESS)
                    target.take_damage(max(1, round(
                        _base * self.skills.axe_damage_scale()
                        * persona.melee_mult(self))))
                    # AND HE REMEMBERS THE FACE: twenty points of liking gone.
                    try:
                        import economy as _eco
                        _eco.wronged(target, self, 20.0, getattr(self, "now", 0.0))
                    except Exception:
                        pass

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float,
             show_name: bool = False) -> None:
        sx, sy = self.x - cam_x, self.y - cam_y
        fx, fy = self.facing
        hx, hy = sx + fx * 2, sy + fy * 2 - 2      # head centre
        wear = getattr(self, "wear", "normal")
        flash = self.hit_flash > 0.0
        pygame.draw.ellipse(screen, (20, 36, 20), (sx - 12, sy - 4, 24, 9))
        # A MOUNTED WARRIOR SITS ON A HORSE: the beast is drawn first, the man
        # rides above it.
        if getattr(self, "mounted", False):
            _him = _mounted_horse()
            if _him is not None:
                screen.blit(_him, (int(sx - _him.get_width() / 2),
                                   int(sy - _him.get_height() + 12)))

        # ONE BODY, ONE FACE, NO ACCESSORIES.
        #
        # There were four dressings -- an ordinary coat, a fur coat with an
        # ushanka, an indigo Tuareg robe with a head wrap, and striped cloth --
        # chosen by the biome a man was born in. They are gone: everybody is
        # drawn the same, and the only thing that varies is the colour of his
        # coat. The wear is still recorded on the man (biomes.npc_wear still
        # sets it) in case it is wanted again; it is simply not drawn.
        if getattr(self, "hide_armor", False):
            # HIDE ARMOR: a leather-brown body with a chest band and shoulder
            # pads, over the man underneath.
            pygame.draw.circle(screen, (242, 232, 232) if flash else (120, 82, 46),
                               (int(sx), int(sy)), 10)
            pygame.draw.circle(screen, (52, 36, 24), (int(sx), int(sy)), 10, 2)
            pygame.draw.rect(screen, (88, 60, 34), (int(sx) - 8, int(sy) - 1, 16, 4),
                             border_radius=2)
            for _px in (int(sx) - 8, int(sx) + 6):
                pygame.draw.circle(screen, (96, 66, 38), (_px, int(sy) - 5), 4)
                pygame.draw.circle(screen, (52, 36, 24), (_px, int(sy) - 5), 4, 1)
        elif getattr(self, "reinforced_armor", False):
            # REINFORCED ARMOR: grey iron plates bolted over a cloth body.
            pygame.draw.circle(screen, (242, 232, 232) if flash else (176, 180, 190),
                               (int(sx), int(sy)), 11)
            pygame.draw.circle(screen, (76, 80, 88), (int(sx), int(sy)), 11, 2)
            pygame.draw.line(screen, (76, 80, 88), (int(sx) - 8, int(sy) - 3),
                             (int(sx) + 8, int(sy) - 3), 2)
            pygame.draw.line(screen, (76, 80, 88), (int(sx) - 7, int(sy) + 3),
                             (int(sx) + 7, int(sy) + 3), 2)
            for _px in (int(sx) - 9, int(sx) + 7):
                pygame.draw.circle(screen, (96, 100, 108), (_px, int(sy) - 6), 5)
                pygame.draw.circle(screen, (58, 62, 70), (_px, int(sy) - 6), 5, 1)
        else:
            body = (242, 232, 232) if flash else self.clothing
            # THE OLD MAN WEARS A PLAIN TUNIC, and his hair is grey under the face.
            if getattr(self, "is_stalin", False):
                body = (74, 78, 76) if not flash else (242, 232, 232)
            pygame.draw.circle(screen, body, (int(sx), int(sy)), 10)
            pygame.draw.circle(screen, (44, 40, 36), (int(sx), int(sy)), 10, 2)
        # A MELEE SWING: the axe sweeps through the facing angle while the
        # swing timer runs. Only on-screen warriors reach this draw, and
        # _melee_swing only starts the timer for on-screen fighters.
        if self.swing_anim > 0.0:
            _sw = 1.0 - self.swing_anim / NPC_SWING_SECONDS
            _ang = math.atan2(fy, fx) - 1.15 + 2.3 * _sw
            _hx2 = sx + fx * 6.0
            _hy2 = sy + fy * 6.0
            _ex = _hx2 + math.cos(_ang) * 20.0
            _ey = _hy2 + math.sin(_ang) * 20.0
            pygame.draw.line(screen, (116, 82, 46), (_hx2, _hy2), (_ex, _ey), 3)
            _px, _py = -math.sin(_ang), math.cos(_ang)
            pygame.draw.line(screen, (208, 208, 214),
                             (_ex - _px * 6, _ey - _py * 6),
                             (_ex + _px * 6, _ey + _py * 6), 3)
        head_r = 8
        face.hair(screen, hx, hy, head_r)          # long hair behind the head
        pygame.draw.circle(screen, (216, 172, 132), (int(hx), int(hy)), 8)
        pygame.draw.circle(screen, (150, 112, 82), (int(hx), int(hy)), 8, 1)

        # ONE FACE FOR EVERYBODY, drawn to the head he happens to have -- and
        # the WORKING face while the work is actually happening. The flag is
        # raised by the act and has already been run down by tick(), so the
        # tongue comes and goes with his hands.
        # WHICH FACE, FROM WHAT HAS JUST HAPPENED TO HIM. A blow he threw, a
        # blow he took, or a job he is doing -- most recent wins, and a blow
        # beats a job.
        mood = face.mood_of(self.hurt_flash, self.attack_flash,
                            self.work_flash, self.sly_flash,
                            self.hunger >= face.STARVED_HUNGER)
        if getattr(self, "break_state", "normal") == "depression":
            mood = "sad"
        # ASLEEP: closed eyes, and a breeding pair has hearts for eyes.
        if getattr(self, "asleep", False) or getattr(self, "sleep_t", 0.0) > 0.0:
            mood = "sleep"
        # AND WHAT HE HAS EARNED WITH HIS HANDS, from the two combat skills
        # together -- drawn UNDER the mood, so a veteran keeps his beard.
        vet = face.vet_tier(self.skills.axe, self.skills.shooting)
        face.draw(screen, hx, hy, head_r, fx, fy, mood, vet=vet)
        face.feather(screen, hx, hy, head_r, fx, fy)   # the styled feather
        if getattr(self, "is_stalin", False):
            # THE OLD MAN keeps the moustache; his cap is gone with the republic.
            face.moustache(screen, hx, hy, head_r)
        if is_military(self) or getattr(self, "hide_armor", False):
            # WAR PAINT ACROSS THE EYES, for the soldiers and the armoured.
            face.war_paint(screen, hx, hy, head_r, fx, fy)
        if getattr(self, "asleep", False) or getattr(self, "sleep_t", 0.0) > 0.0:
            try:
                fnt = pygame.font.SysFont("dejavusans", 12, bold=True)
                z = fnt.render("Zzz", True, (226, 226, 236))
                screen.blit(z, (hx + 6, hy - 20))
            except Exception:
                pass
        # A BREEDING PAIR: hearts float, and the eyes themselves are hearts.
        if getattr(self, "breeding", False):
            self._draw_person_hearts(screen, sx, sy)
            try:
                fnt = pygame.font.SysFont("dejavusans", 10, bold=True)
                hh = fnt.render("\u2665", True, (226, 72, 72))
                px, py = -fy, fx
                for s in (-1, 1):
                    screen.blit(hh, (int(hx + px * s * 3 - hh.get_width() / 2),
                                     int(hy + py * s * 3 - 2 - hh.get_height() / 2)))
            except Exception:
                pass
        # AND THE TOP HAT, IF HE IS THE MAYOR. It goes ON, not under: the
        # monocle had to go underneath because its rim cut across an eye, but a
        # hat is above the head and covers nothing but the head's own top row,
        # so there is nothing under it to lose.
        if self.is_mayor:
            face.tophat(screen, hx, hy, head_r)

        # AND THE CROWN, IF THE THRONE IS HIS. Drawn after the face and touched
        # by nothing else: it does not change his expression, his marks, or a
        # single pixel of the face under it, and it stops the moment is_king
        # goes false -- which the war code does when a capital falls.
        if self.is_king:
            face.crown(screen, hx, hy, head_r)


        # THE COMMANDER'S HAT IS GONE. It was an eight-pixel cap painted over
        # the head, so the one man guaranteed to be looked at was the one man
        # whose face could not be seen -- and the face is drawn BEFORE it, so
        # the hat covered the eyes in every frame. is_commander still marks him
        # for the game; he simply wears what everybody else wears.
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
        # THE LEVEL-UP SHINE, OVER HIM, while it lasts -- the same glow the
        # player wears, drawn on screen only (he is in view by being drawn).
        if getattr(self, "level_flash", 0.0) > 0.0:
            effects.draw_level_up(screen, sx, sy, 1.0 - self.level_flash / 1.6)
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
        # THE MOUTH, NOT THE FOREHEAD.  hx/hy is the head centre; the old
        # code used sx/sy and put the cigar at the body centre.
        fxdir = self.facing
        hx2 = hx + fxdir[0] * 6.0
        hy2 = hy + fxdir[1] * 6.0 + 4.0
        pad = 46
        surf = pygame.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
        cx, cy = pad, pad
        dx, dy = hx2 - sx, hy2 - sy

        if item == "cigar":
            pygame.draw.rect(surf, (108, 66, 38, 235),
                             (cx + dx - 2, cy + dy - 2, 12, 4), border_radius=2)
            pygame.draw.circle(surf, (240, 150, 60, 235), (cx + dx + 10, cy + dy), 2)
            for i in range(6):                      # smoke curling upward
                p = prog * 1.2 + i * 0.16
                if p > 1.0:
                    continue
                rad = int(2 + p * 7)
                a = int(96 * (1.0 - p))
                wob = math.sin(p * 7.0) * 5.0
                pygame.draw.circle(surf, (222, 222, 228, a),
                                   (int(cx + dx + wob), int(cy + dy - 4 - p * 26)), rad)

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
            colour = {"beer": (168, 112, 40), "govbeer": (150, 104, 46),
                      "liqueur": (150, 60, 96),
                      "mezcal": (198, 190, 150)}.get(item, (168, 112, 40))
            pygame.draw.rect(bottle, colour + (215,), (1, 7, 12, 14), border_radius=3)
            pygame.draw.rect(bottle, (206, 214, 220, 190), (4, 0, 6, 8))
            pygame.draw.rect(bottle, (210, 210, 216, 150), (1, 7, 12, 14), 1, border_radius=3)
            surf.blit(bottle, (cx + dx - 7, cy + dy - 10))

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


_CONTRABAND = ("tobacco", "cigar", "beer", "liqueur", "mezcal",
               "dried_mushroom", "red_mushroom", "agave", "wheat_wort",
               "berry_wort", "agave_wort")


class Villages:
    """The legacy town registry, kept empty.

    Native settlements live in `g.native_settlements`; the old town lattice is
    not built. The handful of live call sites still ask this object for its
    villages or its visible set, and get empty answers.
    """

    def __init__(self, seed: int = 20240501) -> None:
        self.seed = seed
        self._cache: dict = {}
        self._frozen: dict = {}
        self._name_counter = 0
        self.offlattice: list = []
        self._hubs = None

    @property
    def villages(self) -> list:
        return []

    def get(self, gx: int, gy: int):
        return None

    def send_idle(self, now: float) -> int:
        return 0

    def visible(self, *a, **k) -> list:
        return []

def refugees_on_the_road(now: float, soldiers=()) -> tuple:
    """No town refugees. Native people stay in their own camps."""
    return 0, 0
