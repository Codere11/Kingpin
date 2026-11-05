"""houseroom.py -- A HOUSE, DRAWN BY ITS OWN INTERIOR.

The house already HAS proper art: floor, rug, walls, window, fireplace, the
bed, the table, the shelves, the plant, the chest -- and the benches the man
places. This wrapper only gives the interior the mine-room interface the frame
knows how to draw (after the zoom, blown up to the window), and lets the
interior paint itself every frame, so placed things appear and the chest is
always where it belongs.
"""

from __future__ import annotations

import pygame


class HouseRoom:
    is_house = True
    is_prison = False

    def __init__(self, house=None, interior=None, seed: int = 0) -> None:
        self.house = house
        self.interior = interior
        if interior is not None:
            self.W = int(interior.W)
            self.H = int(interior.H)
        else:
            self.W, self.H = 900, 600
        self.door_rect = getattr(interior, "door_rect",
                                 pygame.Rect(self.W // 2 - 60, self.H - 30, 120, 30))
        self.flash = 0.0

    def update(self, dt: float) -> None:
        self.flash = max(0.0, self.flash - dt)

    def clamp(self, x: float, y: float) -> tuple:
        if self.interior is not None:
            try:
                return self.interior.clamp(x, y)
            except Exception:
                pass
        return (min(max(x, 40.0), self.W - 40.0),
                min(max(y, 40.0), self.H - 40.0))

    def hits_chunk(self, x: float, y: float) -> bool:
        return False

    def swing(self, yields=(0, 0)):
        return 0

    def draw(self, screen, cam_x: float, cam_y: float, vw: int = 0,
             vh: int = 0) -> None:
        w = vw or screen.get_width()
        h = vh or screen.get_height()
        screen.fill((10, 10, 12), (0, 0, w, h))
        if self.interior is not None:
            try:
                self.interior.draw(screen, cam_x, cam_y)
                return
            except Exception:
                pass
        # no interior: nothing to show but the dark of the walls


def render_backdrop(house, pygame, vw, vh, ground, static_layer, trees,
                    villages, built_houses):
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


def enter_house(house, player, plog, combat, vw, vh, night_factor, pygame,
                random, toast):
    interior = getattr(house, "interior", None)
    if interior is None:
        return None, None, None, None
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
    player.x, player.y = interior.spawn
    player.bleed = 0.0
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
    for npc in getattr(house, "occupants", ()):
        if not npc.alive or not night:
            continue
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
    return house, 0.7, cam_x, cam_y


def exit_house(inside_house, player, night_factor, plog):
    house = inside_house
    if house is None:
        return None, None
    night = night_factor() > 0.38
    for npc in getattr(house, "occupants", ()):
        if not npc.in_interior:
            continue
        npc.in_interior = False
        if npc._saved is not None:
            npc.x, npc.y = npc._saved
            npc._saved = None
        npc.asleep = night
        npc._dir = None
    fx, fy = house.facing
    player.x = house.x + fx * (house.h / 2.0 + 30.0)
    player.y = house.y + fy * (house.h / 2.0 + 30.0)
    plog.log("EXIT-HOUSE", "out to", int(player.x), int(player.y))
    return None, 0.7
