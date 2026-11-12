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

# THE PEOPLE OF THE REPUBLIC.
#
# One country, four tongues: Russian, Ukrainian, Georgian and Polish, mixed in
# the same villages the way a Soviet republic really was. Given names are
# transliterated into plain letters -- no diacritics -- because a missing glyph
# in a bitmap font is a box, and a man whose name draws as a box is not a man
# with a name.
FIRST_NAMES = [
    # Russian
    "Ivan", "Dmitri", "Sergei", "Nikolai", "Pavel", "Mikhail", "Boris",
    "Yuri", "Andrei", "Grigori", "Fyodor", "Vasily", "Pyotr", "Lev",
    "Arkady", "Stepan", "Konstantin", "Vladimir", "Alexei", "Igor",
    "Vera", "Nadya", "Irina", "Olga", "Tatiana", "Zoya", "Galina", "Larisa",
    # Ukrainian
    "Taras", "Bohdan", "Ostap", "Mykola", "Petro", "Dmytro", "Vasyl",
    "Yurii", "Andriy", "Serhiy", "Oksana", "Kateryna", "Halyna", "Olena",
    "Nadiya", "Svitlana",
    # Georgian
    "Giorgi", "Davit", "Levan", "Zurab", "Irakli", "Vakhtang", "Nodar",
    "Otar", "Shota", "Tengiz", "Nino", "Tamar", "Ketevan", "Manana", "Lela",
    # Polish
    "Stanislaw", "Kazimierz", "Wladyslaw", "Zbigniew", "Tadeusz", "Jerzy",
    "Marek", "Piotr", "Krzysztof", "Andrzej", "Jakub", "Tomasz", "Ryszard",
    "Halina", "Jadwiga", "Krystyna", "Zofia", "Danuta", "Ewa",
]
LAST_NAMES = [
    # Russian
    "Volkov", "Sokolov", "Morozov", "Orlov", "Medvedev", "Kuznetsov",
    "Petrov", "Zaitsev", "Komarov", "Lebedev", "Novikov", "Yegorov",
    "Barsukov", "Zimin", "Karpov",
    # Ukrainian
    "Shevchenko", "Bondarenko", "Kovalenko", "Tkachenko", "Melnyk",
    "Kravchenko", "Oliynyk", "Savchenko", "Rudenko", "Marchenko",
    "Lysenko", "Hrytsenko", "Bondar", "Tkachuk",
    # Georgian
    "Beridze", "Kapanadze", "Giorgadze", "Tsiklauri", "Gelashvili",
    "Abashidze", "Japaridze", "Mgeladze", "Dolidze", "Chkheidze",
    # Polish
    "Kowalski", "Nowak", "Wisniewski", "Wojcik", "Kaminski", "Lewandowski",
    "Zielinski", "Szymanski", "Wozniak", "Dabrowski", "Kozlowski", "Mazur",
    "Krawczyk", "Piotrowski",
]
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
        self.hurt_flash = 0.0
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
        self.carry = {}              # surplus he is walking to the chest
        self.carry_grade = {}        # the grade of each carried item
        self.job = None              # "miner" / "smith" / "gunsmith" / "logger"
        self.workplace = None
        self.gunsmith_product = None   # what this gunsmith makes (set by the player)
        self.smith_product = None      # what this smith makes (set by the player)
        self.mounted = False           # a native warrior riding a horse (4th alarm)
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

    def take_damage(self, amount: int, record: bool = True,
                    tranq: bool = False) -> bool:
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
        self.health -= amount
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
        if self.hurt_flash > 0.0:
            self.hurt_flash -= dt
            if self.hurt_flash < 0.0:
                self.hurt_flash = 0.0
        if self.sly_flash > 0.0:
            self.sly_flash -= dt
            if self.sly_flash < 0.0:
                self.sly_flash = 0.0
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
            if camp is not None and not getattr(camp, "conquered", False):
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

    def _walk_toward(self, tx: float, ty: float, speed: float, dt: float) -> None:
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy) or 1.0
        step = min(d, speed * dt)
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
                self.skills.gain_axe()
                dmg = max(1, round((35.0 / 3.0) * self.skills.axe_damage_scale()))
                if combat is not None:
                    combat.fire(self.x + ux * 16.0, self.y + uy * 16.0,
                                math.atan2(dy, dx), dist + 80.0,
                                owner="enemy", damage=dmg, team=self.team)
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
        if not getattr(camp, "conquered", False):
            g = getattr(camp, "g", None)
            if g is not None:
                player = getattr(g, "player", None)
                if (player is not None and getattr(player, "alive", True)
                        and not getattr(player, "dead", False)):
                    d = math.hypot(player.x - self.x, player.y - self.y)
                    _spot = 320.0 if getattr(self, "weapon", None) == "bow" else 260.0
                    if d < _spot:
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
                            self._native_bowman_step(dt, player,
                                                     getattr(g, "combat", None), g)
                        else:
                            self._fight(dt, player, getattr(g, "combat", None))
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
        """The nearest chest that takes `item` and holds at least n of it."""
        chest = self._chest_accepting(item)
        if chest is None:
            return None
        inv = getattr(chest, "inventory", None)
        if inv is not None and inv.count_of(item) >= n:
            return chest
        return None

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
        chest. The good's grade is the midpoint of his hand and the leaf's."""
        bench = getattr(self, "artisan_bench", None)
        if bench is None:
            self._native_idle(dt)
            return
        product = getattr(bench, "product", None)
        leaf = getattr(bench, "leaf", None)
        if not product or not leaf:
            self._native_idle(dt)
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
            if math.hypot(bench.x - self.x, bench.y - self.y) > 22.0:
                self._step_toward(bench.x, bench.y, dt)
                return
            self.produce_acc += dt
            if self.produce_acc >= ARTISAN_BATCH_SECONDS:
                self.produce_acc = 0.0
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
            self._native_idle(dt)
            return
        if math.hypot(chest.x - self.x, chest.y - self.y) > 22.0:
            self._step_toward(chest.x, chest.y, dt)
            return
        taken, g = self._take_from_chest(chest, leaf, 10)
        if taken <= 0:
            self._native_idle(dt)
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
        if math.hypot(bench.x - self.x, bench.y - self.y) > 24.0:
            self._step_toward(bench.x, bench.y, dt)
            return
        self.skills.gain_research(dt)
        lvl = max(1, int(self.skills.research))
        try:
            import research as _research
            _research.add_points(g, lvl * dt)
        except Exception:
            pass
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
            self._step_toward(chunk.x, chunk.y, dt)
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
        if forge is None:
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
                    self._native_idle(dt)
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
        if math.hypot(forge.x - self.x, forge.y - self.y) > 24.0:
            self._step_toward(forge.x, forge.y, dt)
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= product["seconds"]:
            self.produce_acc = 0.0
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
                self._native_idle(dt)
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
        if math.hypot(loom.x - self.x, loom.y - self.y) > 24.0:
            self._step_toward(loom.x, loom.y, dt)
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= WEAVER_BATCH_SECONDS:
            self.produce_acc = 0.0
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
                self._native_idle(dt)
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
        if math.hypot(stall.x - self.x, stall.y - self.y) > 24.0:
            self._step_toward(stall.x, stall.y, dt)
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= SPICEMAN_SECONDS:
            self.produce_acc = 0.0
            self.carry["chili"] = int(self.carry.get("chili", 0)) - 5
            if self.carry.get("chili", 0) <= 0:
                self.carry.pop("chili", None)
                self.carry_grade.pop("chili", None)
            self.carry["sauce"] = int(self.carry.get("sauce", 0)) + 1
            self._did_work()
            self.skills.gain_farming(0.05)

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
                self._native_idle(dt)
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
        if math.hypot(forge.x - self.x, forge.y - self.y) > 24.0:
            self._step_toward(forge.x, forge.y, dt)
            return
        self.produce_acc = getattr(self, "produce_acc", 0.0) + dt
        if self.produce_acc >= product["seconds"]:
            self.produce_acc = 0.0
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
        """An extra farmer with no post: he chills, strolling around the camp."""
        camp = getattr(self, "native_camp", None)
        speed = getattr(self, "speed", 60.0)
        if getattr(self, "_idle_timer", 0.0) <= 0.0:
            if camp is not None:
                ang = self.rng.uniform(0.0, 2.0 * math.pi)
                r = self.rng.uniform(2.0, 6.0) * TILE
                self.target = (camp.x + math.cos(ang) * r, camp.y + math.sin(ang) * r)
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
        """At night, walk to the nearest bedroll and sleep on it."""
        if g is None:
            return False
        bb = getattr(g, "built_blocks", None) or {}
        best = None
        bd = 1e18
        for (tx, ty), kind in bb.items():
            if kind != "bed":
                continue
            wx = tx * TILE + TILE / 2.0
            wy = ty * TILE + TILE / 2.0
            d = (wx - self.x) ** 2 + (wy - self.y) ** 2
            if d < bd:
                bd = d
                best = (tx, ty)
        if best is None:
            return False
        tx, ty = best
        wx = tx * TILE + TILE / 2.0
        wy = ty * TILE + TILE / 2.0
        if math.hypot(wx - self.x, wy - self.y) > 14.0:
            self._step_toward(wx, wy, dt)
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
        if night:
            return self._sleep_on_bedroll(dt, g)
        if getattr(self, "asleep", False):
            self.asleep = False
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
        if _nat and getattr(self, "native_role", "") == "unemployed":
            self._native_idle(dt)
            return
        if _nat and getattr(self, "native_role", "") == "farmer":
            self._native_share()
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
        self.x += ux * self.speed * speed_scale * dt
        self.y += uy * self.speed * speed_scale * dt
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
                for tree in trees.near(wx, wy, TILE * 0.7):
                    if not getattr(tree, "felled", False):
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
        # A STANDING TREE is felled for its wood.
        trees = getattr(g, "trees", None)
        if trees is not None:
            for tree in trees.near(wx, wy, TILE * 0.7):
                if not getattr(tree, "felled", False):
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

    def _work_orchard(self, dt: float, world, now: float) -> bool:
        """An orchard logger: plant a sapling on a bare tile, let it grow,
        cut a full tree down with the axe (the same chop as the player), and
        replant -- the orchard's own wood ends up in the camp's store."""
        camp = getattr(self, "native_camp", None)
        if camp is None:
            return False
        g = getattr(camp, "g", None)
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
        if cut_tile is None and plant_tile is None:
            # nothing to do: every sapling is still growing
            tx = ctx * TILE + TILE / 2.0
            ty = cty * TILE + TILE / 2.0
            if math.hypot(tx - self.x, ty - self.y) > 40.0:
                self._step_toward(tx, ty, dt, 0.7)
            return True
        ttx, tty = cut_tile if cut_tile is not None else plant_tile
        tx = ttx * TILE + TILE / 2.0
        ty = tty * TILE + TILE / 2.0
        if math.hypot(tx - self.x, ty - self.y) > 14.0:
            self._step_toward(tx, ty, dt)
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
        self._did_work()
        return True

    def _work_field(self, dt: float, world, now: float) -> bool:
        """Tend the assigned field one action at a time: harvest a ripe crop,
        plant fertile soil, water dug soil, or break fresh ground with a
        shovel. Returns True while it is busy with the field."""
        job: Any = self.farm_plot
        village = self.village if self.village is not None else getattr(self, "native_camp", None)
        if job is None or village is None or job >= len(village.farm_plots):
            return False
        ctx, cty, kind = village.farm_plots[job]
        g = getattr(village, "g", None)
        todo: dict = {}
        for ttx, tty, tkind in village.farm_tiles[(ctx, cty)]:
            # CLEAR THE GROUND FIRST: a tree, a wild plant, a placed block, or
            # a workbench in the way is removed before the tile can be farmed.
            if self._field_obstruction(ttx, tty, g, world) is not None:
                todo.setdefault("clear", (ttx, tty, None))
                continue
            plot = world.plot_at(ttx, tty)
            state = plot.kind if plot is not None else None
            if state in crop.FOOD_KINDS or state in crop.LEAF_KINDS or state in crop.FIBRE_KINDS:
                # THE PLANTER'S HAND SETS THE TIME. A master brings a crop in
                # in a minute; a green man takes three.
                _grow = getattr(plot, "grow", None) or crop.GROW_SECONDS
                if (plot.planted_at is not None
                        and now - plot.planted_at >= _grow):
                    todo.setdefault("harvest", (ttx, tty, tkind))
            elif state == "fertile":
                # A CONQUERED FARMER NEEDS THE SEED IN HIS POCKETS to sow; a
                # native farmer sows what the camp's own fields already carry.
                if getattr(self, "conquered", False):
                    _seed = crop.CROP_SEED.get(tkind)
                    if _seed is not None and self._count_item(_seed) <= 0:
                        continue
                todo.setdefault("plant", (ttx, tty, tkind))   # ready for the seed
            elif state == "dirt":
                todo.setdefault("water", (ttx, tty, tkind))   # dug but dry
            else:
                todo.setdefault("till", (ttx, tty, tkind))    # grass: break it open
        can_till = self.tool_uses > 0 or self.stock.get("shovel", 0) > 0
        # ONE ACTION A TICK, AND EVERY PART OF THE FIELD GETS ITS TURN.
        #
        # This always tried harvest first, then plant, water, till -- and
        # `todo` holds one tile per action. Five wheat tiles come ripe in a
        # cycle, so there was nearly always a harvest to take, and the twenty
        # GRASS tiles of the same field were never broken open at all: a farmer
        # worked five tiles out of twenty-five for ever, grew no leaf, and the
        # artisan upstream of him starved for stock. The order now rotates by
        # one each action, so a ripe harvest cannot starve the tilling.
        # HARVEST FIRST, so a ripe field is reaped tile after tile -- about one
        # a second -- and tilling/planting only happens once nothing is ripe.
        _order = ["clear", "harvest", "plant", "water", "till"]
        task = None
        for action in _order:
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
        if action == "clear":
            self._field_clear(ttx, tty, g, world, now)
        elif action == "harvest":
            plot = world.plot_at(ttx, tty)
            if plot is not None:
                if getattr(village, "is_hub", False):
                    _note("FIELD   %s harvests %s at %d,%d"
                          % (getattr(self, "name", "?"), plot.kind, ttx, tty))
                economy.harvest(village, self, plot.kind, self.rng)
                self.skills.gain_farming(0.02)  # reaping hones the hand, slowly
                # the conquered farmer keeps a seed or two for the next sowing
                if getattr(self, "conquered", False):
                    _seed = crop.CROP_SEED.get(plot.kind)
                    if _seed is not None:
                        self._give_item(_seed, 1 + (1 if self.rng.random() < 0.5 else 0))
            world.set_plot(ttx, tty, "grass", None)     # the soil is spent
        elif action == "till":
            if not self._swing_tool():
                return True                     # no shovel: we must buy one
            world.set_plot(ttx, tty, "dirt", None)
        elif action == "water":
            world.set_plot(ttx, tty, "fertile", None)
        else:                                    # plant the seed for that cell
            if getattr(self, "conquered", False):
                _seed = crop.CROP_SEED.get(tkind)
                if _seed is not None and not self._take_item(_seed, 1):
                    return True                 # no seed in his pockets: cannot sow
            world.set_plot(ttx, tty, tkind, now,
                           crop.grow_seconds(self.skills.farming))
        ground = getattr(world, "ground", None)
        if ground is not None:
            # FIRST PRIORITY WHEN WATCHED: a tile that changed ON SCREEN is
            # rebuilt right now, in this frame; a farmer's far-off field is
            # queued to the worker thread as before.
            _immediate = False
            if g is not None:
                _wx = ttx * TILE + TILE / 2.0
                _wy = tty * TILE + TILE / 2.0
                if (g.cam_x - TILE <= _wx <= g.cam_x + g.vw + TILE
                        and g.cam_y - TILE <= _wy <= g.cam_y + g.vh + TILE):
                    _immediate = True
            ground.invalidate_tile(ttx, tty, immediate=_immediate)
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
        if self.lunge_cd <= 0.0 and self._wants_lunge_away(target, distance):
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
                    self.skills.gain_axe()
                    if hasattr(target, "take_damage"):
                        target.take_damage(max(1, round(
                            (35.0 / 3.0) * self.skills.axe_damage_scale())))
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
                        self._shoot(combat, mx, my, angle, distance + 120.0, 80, 80)
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
                self._did_attack()
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
                        _base * self.skills.axe_damage_scale())))
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
        else:
            body = (242, 232, 232) if flash else self.clothing
            # THE OLD MAN WEARS A PLAIN TUNIC, and his hair is grey under the face.
            if getattr(self, "is_stalin", False):
                body = (74, 78, 76) if not flash else (242, 232, 232)
            pygame.draw.circle(screen, body, (int(sx), int(sy)), 10)
            pygame.draw.circle(screen, (44, 40, 36), (int(sx), int(sy)), 10, 2)
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
            colour = {"beer": (168, 112, 40), "govbeer": (150, 104, 46),
                      "liqueur": (150, 60, 96),
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


_CONTRABAND = ("tobacco", "cigar", "beer", "liqueur", "mezcal",
               "dried_mushroom", "red_mushroom", "agave", "wheat_wort",
               "berry_wort", "agave_wort")


class Village:
    # THE GATE QUEUE. Class-level defaults, because a village that came out of
    # the world cache never runs __init__ again -- and the old guard checked
    # only `search_queue`, so a cache-built town had a queue but no
    # `search_now`, and gate_tick raised AttributeError on the frame the player
    # first came near the wall. That is the crash at the settlement entry.
    search_queue: tuple = ()        # per-village: set in __init__, never shared
    provoked_t: float = 0.0         # how long the town stays up in arms
    search_now: object = None
    search_t: float = 0.0
    gate_cd: float = 0.0            # a man's cooling-off after being searched

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
        self.search_queue: list = []      # THE GATE QUEUE IS THIS TOWN'S
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
        # NO BENCH AND NO BREWHOUSE, ANYWHERE, BY LAW. A laboratory works
        # tobacco and a brewery works mash, and neither thing may be grown,
        # dried, mashed or bottled inside a settlement -- so neither building
        # exists in one. The trade did not disappear with the buildings: it
        # moved to the hubs in the wild, and the cravings that paid for it did
        # not shrink by a single man.
        #
        # The professions go with the benches, because every job slot in a
        # village is derived from a workplace: no bench, no post.
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
                             village=self)
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
        # ONE THRONE, IN ONE PLACE. Every capital used to crown a king, which
        # was right when there were three kingdoms and wrong now that there is
        # one state: two of the three capitals are REGIONAL, and a region is
        # administered, not ruled. They get a Governor -- the same office as a
        # mayor, with the top hat and none of the crown.
        _seat = nations.is_main_capital(self.x, self.y)
        if self.is_capital and _seat and len(self.npcs) > 1:
            self.king = self.npcs[-1]
            self.king.role = "Dictator"
            self.king.is_king = True
            self.king.job = "king"
        if (not _seat) and len(self.npcs) > 2:
            self.mayor = self.npcs[-2]
            self.mayor.role = "Governor" if self.is_capital else "Mayor"
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
            guard.max_health = stats.PLAYER_MAX_HEALTH
            guard.health = stats.PLAYER_MAX_HEALTH
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
            # EVERY TILE IS FOOD. This read "two thirds to the larder" and
            # planted the other NINE TILES OF EVERY TWENTY-FIVE as the local
            # leaf -- fifty illegal plants in every settlement, which I then
            # reported as fixed because I had changed the PLOT kind and never
            # the tiles. A settlement grows food. Leaf is grown where the
            # regime is not, and that is the hubs' whole reason to exist.
            self.farm_tiles[(ctx, cty)] = [
                (cx2, cy2, food) for cx2, cy2 in cells]
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
                worker.leaf_farmer = False    # a settlement grows no leaf
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
                pass          # skills are EARNED. Everyone starts at nothing.
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
        # NO LOCAL LEAF, SO NO LOCAL LEAF PRICE. Every leaf is dear here: it
        # comes in over the wall, which is what makes the huts worth walking to.
        for item in economy.LEAF:
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
        self.provoked_t = self.PROVOKE_SECONDS
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

    # TWO MINUTES UP IN ARMS, THEN THE TOWN GOES BACK TO ITS BUSINESS. A
    # provoked village was permanent: nothing ever set it false again, so a man
    # who once stepped over a fence was shot at by every guard made in that town
    # for the rest of the save, with no way to live it down.
    PROVOKE_SECONDS = 120.0

    def calm(self) -> None:
        """TWO MINUTES UP IN ARMS, THEN THE TOWN GOES BACK TO ITS BUSINESS.

        PROVOKE_SECONDS has been set here since the beginning and NOTHING EVER
        COUNTED IT DOWN: one crime, and the town was hostile for the rest of
        the save -- every guard made in it, for ever, with no way to live it
        down. The men who were TOLD what you are keep their grudge (`knows`,
        and main's KNOWS-AGGRO pass re-arms them every frame); the street, and
        everyone who only heard the alarm, go back to work.
        """
        self.provoked = False
        self.provoked_t = 0.0
        for npc in self.npcs:
            if not npc.alive:
                continue
            npc.aggro = False
            npc.panic = 0.0
        for g in (getattr(self, "guards", None) or ()):
            if getattr(g, "alive", False):
                g.hostile = False
                g.aware = False

    # THE GATE IS PHYSICAL. A man queues because he is five tiles from the guard
    # on that gate and his road runs to the other side of the wall -- and the
    # line he stands in is spaced out behind it.
    SEARCH_RANGE = 160.0        # five tiles: close enough to be looked at

    SEARCH_SECONDS = 10.0
    SEARCH_CATCH = 0.55         # a carrier with 20 items is caught this often

    def search_tick(self, dt: float, now: float = 0.0) -> None:
        """ONCE, WHEN A MAN CROSSES THE WALL. Nothing else is ever polled.

        He steps over the fence line -- in or out -- and that is the event: he
        is searched. One man at a time, ten seconds, and while one is being
        looked at the others wait their turn. A man who does not cross is never
        looked at, and no man is ever looked at twice for the same crossing.
        """
        if getattr(self, "is_hub", False):
            return                      # a hut is not the state
        squad = getattr(self, "patrol", None)
        if not squad:
            return
        guard = squad[0]                # the man on the way IN
        if not getattr(guard, "alive", True):
            self.search_now, self.search_t = None, 0.0
            return
        r = getattr(self, "fence_rect", None)
        if r is None:
            return
        if not isinstance(getattr(self, "search_queue", None), list):
            self.search_queue = []

        # ---- THE ONLY THING LOOKED AT: WHO JUST CROSSED ----------------
        for n in self.npcs:
            if not n.alive or getattr(n, "village", None) is self:
                continue                # a resident crosses his own wall freely
            now_in = r.collidepoint(n.x, n.y)
            was_in = getattr(n, "was_inside", None)
            n.was_inside = now_in
            if was_in is None or was_in == now_in:
                continue                # he did not cross: he is not searched
            if n is self.search_now or n in self.search_queue:
                continue
            n.search_t = 0.0
            self.search_queue.append(n)

        # ---- the one being searched: a timer, and nothing else ----------
        if self.search_now is None and self.search_queue:
            self.search_now = self.search_queue.pop(0)
            self.search_t = 0.0
        cur = self.search_now
        if cur is None:
            return
        if not cur.alive:
            self.search_now, self.search_t = None, 0.0
            return
        cur.pause = max(float(getattr(cur, "pause", 0.0)), 0.2)     # he waits
        cur.target = (cur.x, cur.y)
        self.search_t = float(getattr(self, "search_t", 0.0)) + dt
        if self.search_t < self.SEARCH_SECONDS:
            return
        self.search_now, self.search_t = None, 0.0
        units = sum(int(cur.stock.get(k, 0)) for k in _CONTRABAND)
        if units > 0 and random.random() < min(1.0, units / 100.0) * self.SEARCH_CATCH:
            cur.wanted = True
            self.provoke()              # CAUGHT IS AGGRO, and that is all
            _note("SEARCH    %s caught with %d at the gate of %s"
                  % (getattr(cur, "name", "?"), units, self.name))

    def update(self, dt: float, world=None, now: float = 0.0,
               phase: str = "home") -> None:
        """THE TOWN'S OWN BUSINESS: its books, its trade, its roster.

        Nothing here belongs to any individual. A man's hunger, his meals, his
        smoking, his tools, his trade run and his death are his own, in
        NPC.tick() -- and he registers himself in village.PEOPLE, so the world
        walks the people once instead of sixty-four towns walking their own.
        """
        # (the gate search is NOT here -- see search_tick. Looking in one man's
        # pack must not run the wages, the tax, the tithe, the election, the
        # court, the garrison and the market of the whole town, which is what
        # made a ten-second search cost a quarter of a second a frame.)
        self.forget_killers(now)
        # THE ALARM RUNS OUT. See calm().
        if self.provoked:
            self.provoked_t = float(getattr(self, "provoked_t", 0.0)) - dt
            if self.provoked_t <= 0.0:
                self.calm()
        day = int(now / economy.DAY_LENGTH)
        self._day = now / economy.DAY_LENGTH
        # THE MILITIA BREAKS UP BRAWLS: dart every man throwing punches.
        try:
            import brawl as _brawl
            _brawl.town_step(self, now, dt)
        except Exception:
            pass
        # THE HOLDING CELL: a brawler is fed two loaves a day from the state's
        # ledger and serves three days; he cannot fight while inside.
        _d = int(now / economy.DAY_LENGTH)
        for _n in self.npcs:
            _sd = int(getattr(_n, "_sentence_days", 0))
            if _sd <= 0:
                continue
            if getattr(_n, "_fed_day", -1) != _d:
                _n._fed_day = _d
                _n.stock["bread"] = _n.stock.get("bread", 0) + 2
            if getattr(_n, "_sentence_day", -1) != _d:
                _n._sentence_day = _d
                _n._sentence_days = _sd - 1
                if _sd - 1 <= 0:
                    _n.in_cell = False
                    _n._brawl_target = None
                    economy._note("RELEASED %s served the brawl sentence"
                                  % getattr(_n, "name", "?"))
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
                   sum(n.stock.get("wood", 0) for n in self.npcs)
                   + int(self.ledger_goods.get("wood", 0)),
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
            # THE MOOD OF THE TOWN, in buckets: how many men feel what.
            _moods = [float(getattr(n, "mood", 50.0)) for n in self.npcs
                      if getattr(n, "alive", True)]
            economy._note("MOOD day %d  %-14s <20:%d 20-40:%d 40-60:%d 60-80:%d >80:%d"
                          % (day, self.name,
                             sum(1 for m in _moods if m < 20),
                             sum(1 for m in _moods if 20 <= m < 40),
                             sum(1 for m in _moods if 40 <= m < 60),
                             sum(1 for m in _moods if 60 <= m < 80),
                             sum(1 for m in _moods if m >= 80)))
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
        self.court_day(day)                    # ten days at court, ten at home
        economy.crown_arms_order(self, day)   # and buys the arms for its war
        economy.pay_garrison(self, day)       # the standing army is paid daily
        # THE SERVICE'S OWN PAY. Each settlement pays its agents; the seat
        # pays the chief and the men no town employs.
        economy.pay_agents(self, day)
        if getattr(self, "king", None) is not None:
            economy.pay_service_state(self, day, service_carts())
        # AND THE MINT, LAST: what the books paid today, plus a floor, coined
        # out of the granary's own firewood. See economy.mint_day.
        economy.mint_day(self, day)
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
        # AND A FARMER IS GIVEN A FIELD, WHETHER HE ARRIVED WITH THE TRADE OR
        # TOOK IT OFF THIS BOARD. The backstory used to be the only place a
        # plot was handed out, so a man who was hired as a farmer later worked
        # somebody else's field -- and harvesting a village plot that is not
        # yours is a CRIME, so his first harvest got the town up in arms.
        if kind == "farm" and self.farm_plots:
            taken = {getattr(n, "farm_plot", None) for n in self.npcs}
            mine = next((i for i in range(len(self.farm_plots))
                         if i not in taken), None)
            if mine is None:
                mine = 0
            player.farm_plot = mine
            for n in self.npcs:
                if getattr(n, "farm_plot", None) == mine:
                    free = next((i for i in range(len(self.farm_plots))
                                 if i not in taken and i != mine), None)
                    if free is not None:
                        n.farm_plot = free
                    else:
                        n.farm_plot = None
                        n.job = "hand"
        else:
            player.farm_plot = None
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
            npc.leaf_farmer = False                # a settlement grows no leaf
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
            # A MINER IS GIVEN A PICK, the way a farmer is given a shovel and a
            # woodsman an axe. He was handed nothing at all -- and now that the
            # pit swings its tool, a miner with an empty hand digs NO IRON, and
            # with no iron the forge cannot make him a pick. The whole trade
            # deadlocked on the first day: 95 miners, 0 pickaxes, an empty
            # shelf, and a world that could never dig again.
            if wp.kind == "mine":
                npc.stock["pickaxe"] = 1
                npc.grade["pickaxe"] = 0
                npc.tool_uses = economy.TOOL_USES
                npc.tool_kind = "pickaxe"
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
                   village=self)
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
        # FROZEN SETTLEMENTS: the full state of a village that has left the
        # simulated distance, kept so it resumes exactly when the player
        # returns. Keyed by cell, each value is a worldio village record.
        self._frozen: dict[tuple[int, int], dict] = {}
        # THE NEXT PLAIN SETTLEMENT NUMBER. Names are "Settlement 1",
        # "Settlement 2", ...; a restored town keeps its saved number, and the
        # counter is bumped past any number already taken.
        self._name_counter = 0
        self.trade_active: set = set()    # villages with a trader on the road
        self.trader_deaths = 0            # traders lost, and lost on the road
        self.trader_kills_away = 0

    @property
    def villages(self) -> list:
        """Every village built so far."""
        return list(self._cache.values())

    def get(self, gx: int, gy: int) -> Village:
        # THE OLD SOVIET SETTLEMENTS ARE GONE. The world now holds only
        # native settlements -- teepees and fields around a fireplace, built by
        # native.py as the player reaches them. Nothing on the old lattice is
        # laid out any more.
        return None

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
                pad: int = 420, extra=()) -> list[Village]:
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
                # THE WALL COUNTS AS THE TOWN. A settlement's fence is not
                # always centred on its lattice cell -- some are kilometres
                # off -- so culling by the cell alone threw away towns whose
                # walls were on screen. That is why a man standing at a gate
                # saw no guard: the town was never in the visible list, so the
                # guard detail was never raised.
                # NEVER BUILD A TOWN TO ASK WHERE IT IS. `get()` lays a whole
                # village out -- fifty to eighty milliseconds -- and this loop
                # runs for every cell in view on every call, a dozen times a
                # frame. `visible()` is asked by drawing, collision, wolves,
                # ore, the crop loop and the census, so a cell that had not been
                # built yet was rebuilt... or rather, built, mid-frame, over and
                # over: seconds per frame, which is the freeze at the gate. Look
                # in the cache; build only when the cell has actually passed.
                _v0 = self._cache.get((gx, gy))
                _fr = getattr(_v0, "fence_rect", None) if _v0 is not None else None
                _ext = (math.hypot(_fr.w, _fr.h) / 2.0) if _fr is not None else 0.0
                # AND A SANITY CLAMP. The half-diagonal of a fence as a town's
                # REACH multiplied the area a town claims by seven, and a
                # capital by thirty -- so approaching one gate put several whole
                # towns into the per-frame simulation at once. That is the
                # freeze. A fence further than eight kilometres from its own
                # town is not believed either: it is the signature of a world
                # whose positions were overwritten.
                if _fr is not None and (abs(_fr.centerx - vx) > 8000.0
                                        or abs(_fr.centery - vy) > 8000.0):
                    _ext = 0.0
                _ext = min(_ext, 6000.0)
                r = max(village_radius(gx, gy), _ext) + slack
                # WHERE THE WALL IS, NOT WHERE THE CELL IS. A settlement's
                # fence can stand kilometres from its own coordinates, and a
                # man at the gate was therefore culled out of the world with the
                # town he was standing at -- no fence drawn, no guard raised,
                # nobody searching. Test the fence's centre when there is one.
                if _fr is not None:
                    _vx2, _vy2 = float(_fr.centerx), float(_fr.centery)
                else:
                    _vx2, _vy2 = vx, vy
                if abs(_vx2 - cx) <= r and abs(_vy2 - cy) <= r:
                    if _v0 is None:
                        _v0 = self.get(gx, gy)      # now, and only now
                    if _v0 is not None and _v0 not in out:
                        out.append(_v0)
        # AND THE OFF-LATTICE ONES. Everything above finds a town by asking the
        # LATTICE where it is -- `village_center(gx, gy)` -- so a settlement
        # that does not stand on its lattice cell is invisible to every system
        # that walks this method: the exterior draw, the player's collision,
        # the guards, the board, the fences. A hub is exactly such a
        # settlement, and it was being built correctly and then thrown away
        # here, every frame, by a distance test it could never pass.
        # AND THE OFF-LATTICE ONES, ALWAYS. `extra` was something a caller had
        # to remember to pass, which meant three sites saw hubs and the other
        # thirty did not. The list is attached to the registry itself, so every
        # caller -- drawing, collision, wolves, ore, the crop loop, the board,
        # the census -- hears the same answer without being told.
        for v in list(extra) + list(getattr(self, "offlattice", ())):
            if v is None:
                continue
            # HIS OWN YARD IS NOT A SETTLEMENT. It is not culled, not drawn,
            # not stepped, not garrisoned -- his fences and his houses are
            # already the world's, and handing his yard to every system that
            # walks visible_villages crashed the frame (no gx, no patrol).
            if getattr(v, "is_player_hub", False):
                continue
            r = float(getattr(v, "radius", 0.0)) + slack
            if abs(v.x - cx) <= r and abs(v.y - cy) <= r and v not in out:
                out.append(v)
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
            try:
                import deaths
                deaths.record(npc, "CUT DOWN ON THE ROAD",
                              detail="to %s, nation %s"
                              % (getattr(dest, "name", "?"),
                                 getattr(caught, "nation", "?")))
            except Exception:
                pass
            npc.die()            # a refugee cut down on the road settles up too:
            died += 1            # off the register, off the road
            continue
        if now >= npc.refuge_eta:
            npc._arrive_refuge(dest, now)
            arrived += 1
    return arrived, died
