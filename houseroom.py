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
