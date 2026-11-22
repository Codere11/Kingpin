"""hubs.py -- THE PLAYER'S OWN FENCED GROUND, and nothing else.

The old world's criminal huts, free traders, caravans, night courts and hut
rosters are gone. What remains is the one part of the old hub system the native
game actually uses: the player's own yard, created when he fences ground, and
the land rule that lets him build inside it and nowhere else.
"""

from __future__ import annotations

import math

import pygame


def in_player_hub(rect, hubs) -> bool:
    """Is this ground inside a yard of the player's own?"""
    for h in hubs or ():
        if getattr(h, "is_player_hub", False) and h.fence_rect.colliderect(rect):
            return True
    return False


def land_ok(rect, villages, hubs, px: float, py: float, clearance=140.0) -> bool:
    """HIS OWN GROUND, OR OPEN COUNTRY -- NEVER SOMEBODY ELSE'S.

    Only the player's fenced yard and real settlements matter. A conquered
    native settlement is his ground; the old town lattice is gone.
    """
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
        import os
        path = os.path.expanduser("~/.kingpin_saves/village.log")
        with open(path, "a") as fh:
            fh.write(message + "\n")
    except Exception:
        pass


class PlayerHub:
    """THE PLAYER'S OWN HUB: a yard he closed in the wild, and his.

    Not a settlement. No men, no bench, no field. What makes it a hub is that
    HE fenced it: the walls are his own fences, and this object is the name the
    world can point at.
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
    """The player's yards, and nothing else. Not a registry of settlements."""

    def __init__(self, world, villages) -> None:
        self._world = world
        self._villages = villages
        self.hubs: list = []
        self._caravans: list = []
        self.build(world, villages)

    def build(self, world, villages) -> None:
        # Attached to the registry only so the yard can be reached as a hub.
        try:
            villages.offlattice = self.hubs
            villages._hubs = self
        except Exception:
            pass
        self._caravans = []

    def build_caravans(self, world) -> None:
        return None

    def update(self, dt: float, now: float, phase: str = "home",
               combat=None, threat_of=None, colliders=()) -> None:
        return None

    def drive_carts(self, dt: float, now: float) -> None:
        return None

    def _refill(self, dt: float, now: float) -> None:
        return None

    def add_player_hub(self, owner, yard, ring, gates=()):
        """THE YARD HE CLOSED BECOMES HIS HUB, once, and by name."""
        for h in self.hubs:
            if getattr(h, "is_player_hub", False):
                if h.fence_rect.colliderect(yard.inflate(300, 300)):
                    return None                 # that ground is already his
        hub = PlayerHub(owner, yard, ring, gates)
        self.hubs.append(hub)
        _note("PLAYER HUB  %s  at (%.0f,%.0f)  %dx%d"
              % (hub.name, hub.x, hub.y, yard.w, yard.h))
        return hub

    def draw(self, screen, cam_x: float, cam_y: float, vw: int, vh: int) -> None:
        for hub in self.hubs:
            hub.draw(screen, cam_x, cam_y, vw, vh)

    def all_npcs(self) -> list:
        return []
