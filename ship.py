"""ship.py -- THE CROWN'S SHIP, anchored at the coast and facing the land."""
import os
import pygame

_SURF = None


def load() -> pygame.Surface:
    """The pixel ship, scaled to a sensible world size."""
    global _SURF
    if _SURF is not None:
        return _SURF
    path = os.path.join(os.path.dirname(__file__), "ship.png")
    img = pygame.image.load(path)
    try:
        img = img.convert_alpha()
    except Exception:
        img = img.convert()
    _SURF = pygame.transform.scale(img, (128, 96))
    return _SURF


def draw(surf: pygame.Surface, cam_x: float, cam_y: float,
         wx: float, wy: float) -> None:
    """Blit the ship centred on a world point."""
    s = load()
    surf.blit(s, (int(wx - cam_x - s.get_width() / 2),
                  int(wy - cam_y - s.get_height() / 2)))
