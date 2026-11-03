"""gulag.py -- THE CAMP IN THE FROZEN NORTH-EAST.

A walled compound two settlement-widths in from the corner of the world:

* ONE fence, ONE gate. The railway comes in through that gate and stops at the
  middle of the camp -- the line is the camp's only way in.
* Thirty iron mines in a neat grid on the west side, fifty pines in rows on the
  east, both laid so that a handful of men with shotguns and rifles standing on
  the perimeter path can see every metre of the inside.
* ONE long wooden shack with no beds, for a hundred prisoners, and a spacier
  barracks block for twenty guards.
* ANYONE INSIDE WHO IS NOT A GUARD IS SHOT. The guards are the crown's, they
  carry loaded guns, and stepping over the fence line is the whole of the
  crime.
"""

from __future__ import annotations

import math

import pygame

MAP_HALF = 500000.0
try:
    import village as _village
    INNER_RADIUS = float(getattr(_village, "RADIUS_BASE", 2580.0))
except Exception:
    INNER_RADIUS = 2580.0
INNER_WIDTH = 2.0 * INNER_RADIUS
MARGIN = 2.0 * INNER_WIDTH
SITE = (MAP_HALF - MARGIN, -(MAP_HALF - MARGIN))

HALF_SIZE = 2700.0          # the compound is 5,400 px across
WALL = 12.0                 # fence thickness
GATE_W = 240.0              # the one opening
PRISONERS = 100
GUARDS = 20
MINES = 30
TREES = 50
SHACK = pygame.Rect(-2000, 260, 1600, 460)      # one long shed, no beds
BARRACKS = pygame.Rect(-2000, -1100, 900, 420)  # the guards' block

FENCE = (92, 74, 54)
FENCE_DARK = (54, 42, 30)
SNOW = (226, 230, 236)
SNOW_SHADE = (198, 204, 214)
WOOD = (108, 78, 50)
WOOD_DARK = (62, 44, 28)
IRON = (86, 90, 96)
PINE = (44, 66, 52)
PINE_DARK = (28, 44, 34)

_STATE = {"turn": 0, "cool": 0.0, "built": False, "mines": [], "trees": [], "posts": [],
          "guards": [], "gate": None, "gate_side": 3, "inside": 0,
          "houses": [], "works": [], "walls": []}


def middle() -> tuple:
    return SITE


def rect() -> pygame.Rect:
    return pygame.Rect(int(SITE[0] - HALF_SIZE), int(SITE[1] - HALF_SIZE),
                       int(HALF_SIZE * 2), int(HALF_SIZE * 2))


def inside(x: float, y: float, pad: float = 0.0) -> bool:
    return (abs(float(x) - SITE[0]) <= HALF_SIZE + pad
            and abs(float(y) - SITE[1]) <= HALF_SIZE + pad)


def gate_point() -> tuple:
    """WHERE THE LINE COMES IN: the middle of the only opening, in the west wall."""
    g = _STATE["gate"]
    if g is None:
        return (SITE[0] - HALF_SIZE, SITE[1])
    return g


def build() -> None:
    """Lay the camp out once. Nothing here depends on the seed."""
    if _STATE["built"]:
        return
    sx, sy = SITE
    # THE ONLY GATE, in the west wall: the railway comes from the settled
    # country, which is west and south of here.
    _STATE["gate"] = (sx - HALF_SIZE, sy)
    # THE BARN'S FOOTPRINT COMES FIRST, so nothing is ever laid across its
    # doorway: it is bigger than the plot it stands on, and the mine grid was
    # being tested against the plot instead of the building.
    _BW = max(900, int(SHACK.w * 1.15))
    _BH = max(420, int(SHACK.h * 1.2))
    _barn_rect = pygame.Rect(int(shack_rect().centerx - _BW / 2),
                             int(shack_rect().centery - _BH / 2), _BW, _BH)
    # the approach: from the south door, a corridor wide enough to walk and
    # long enough to reach the yard
    _door_x = _barn_rect.centerx
    _approach = pygame.Rect(int(_door_x - 160), _barn_rect.bottom,
                            320, 460)
    _STATE["barn_rect"] = _barn_rect
    _STATE["approach"] = _approach
    # MINES: thirty REAL mine buildings, a 6 x 5 grid on the west side.
    mines, works = [], []
    try:
        import industry as _industry
        for j in range(6):
            for i in range(8):
                wx = sx - 2250.0 + i * 300.0
                wy = sy - 1600.0 + j * 340.0
                _mr = pygame.Rect(int(wx - 68), int(wy - 56), 136, 112)
                if (_mr.inflate(120, 120).colliderect(_barn_rect)
                        or _mr.inflate(120, 120).colliderect(barracks_rect())
                        or _mr.inflate(100, 100).colliderect(_approach)):
                    continue    # never against a wall, never across a doorway
                if len(mines) >= MINES:
                    break
                mines.append((wx, wy))
                if len(mines) >= MINES:
                    break
                works.append(_industry.Workplace("mine", wx, wy,
                                                 (id(sx) ^ (i * 31 + j)) & 0x7FFFFFFF))
    except Exception:
        for j in range(5):
            for i in range(6):
                mines.append((sx - 2000.0 + i * 300.0, sy - 950.0 + j * 330.0))
    _STATE["mines"] = mines
    _STATE["works"] = works
    # THE TWO BUILDINGS ARE HOUSES OF THE GAME'S OWN KIND: walls that stop a
    # man, a roof that stops an eye, and a door he can walk through into an
    # interior. Nothing painted on the ground.
    houses = []
    try:
        import village as _v
        import interior as _interior
        from village import House as _House, ROOFS as _ROOFS
        # ONE LONG SHED, BUILT AS A ROW OF HOUSES. A single 3,000-pixel-wide
        # house is a single 2.7-million-pixel sprite blitted every frame -- the
        # hitch you felt walking up to it. Six bays side by side with the same
        # roof read as one building and cost a sixth each.
        def row(rec, bays, seed0, government=False, keep=1.6):
            out = []
            bw = rec.w // bays
            for i in range(bays):
                bx = rec.left + bw // 2 + i * bw
                h = _House(float(bx), float(rec.centery), bw,
                           max(220, int(rec.h * keep)), _ROOFS[0], (0.0, 1.0),
                           seed0 + i, government=government)
                h.build_seed = seed0 + i
                h.interior_seed = seed0 + 7        # the bays are one room
                h.interior = _interior.Interior(h.interior_seed, tuple(h.facing))
                h.enterable = True
                h.camp = True             # rebuilt from the seed, never saved
                out.append(h)
            return out
        houses.extend(row(barracks_rect(), 2, 90002, government=True, keep=1.0))
        _bw, _bh = max(900, int(SHACK.w * 1.15)), max(420, int(SHACK.h * 1.2))
        _STATE["prison"] = Prison(shack_rect().centerx, shack_rect().centery,
                                  _bw, _bh)
        try:
            import plog
            plog.log("BARN", "built", _bw, "x", _bh, "at",
                     int(shack_rect().centerx), int(shack_rect().centery))
        except Exception:
            pass
    except Exception as _he:
        try:
            import plog
            plog.log("GULAG-HOUSE-ERROR", repr(_he)[:150])
        except Exception:
            pass
    _STATE["houses"] = houses
    # THE FENCE: five wall pieces with ONE gap where the railway comes in.
    r = rect()
    t = int(WALL)
    gx_, gy_ = _STATE["gate"]
    walls = [
        pygame.Rect(r.left, r.top, r.w, t),
        pygame.Rect(r.left, r.bottom - t, r.w, t),
        pygame.Rect(r.left, r.top, t, int(gy_ - GATE_W / 2 - r.top)),
        pygame.Rect(r.left, int(gy_ + GATE_W / 2), t,
                    int(r.bottom - (gy_ + GATE_W / 2))),
        pygame.Rect(r.right - t, r.top, t, r.h),
    ]
    _STATE["walls"] = [w for w in walls if w.w > 0 and w.h > 0]
    # TREES: 5 rows of 10 on the east side, spaced like an orchard
    trees = []
    for j in range(5):
        for i in range(10):
            trees.append((sx + 640.0 + i * 150.0, sy - 900.0 + j * 380.0))
    _STATE["trees"] = trees
    # PERIMETER POSTS: 8 evenly spread, each facing the middle, so a handful of
    # men cover the whole inside -- and two more inside the gate.
    posts = []
    for k in range(8):
        ang = 2.0 * math.pi * k / 8.0
        posts.append((sx + math.cos(ang) * (HALF_SIZE - 60.0),
                      sy + math.sin(ang) * (HALF_SIZE - 60.0)))
    # THE GATE POSTS STAND CLEAR OF THE TRACK: the rails come in through the
    # middle of the opening, so the two men at the gate are set well to either
    # side of it.
    posts.append((sx - HALF_SIZE + 120.0, sy + 190.0))
    posts.append((sx - HALF_SIZE + 120.0, sy - 190.0))
    _STATE["posts"] = posts
    _STATE["built"] = True


def shack_rect() -> pygame.Rect:
    r = SHACK.copy()
    r.move_ip(int(SITE[0]), int(SITE[1]))
    return r


def barracks_rect() -> pygame.Rect:
    r = BARRACKS.copy()
    r.move_ip(int(SITE[0]), int(SITE[1]))
    return r


def prison():
    return _STATE.get("prison")


def houses() -> list:
    return list(_STATE["houses"])


def works() -> list:
    return list(_STATE["works"])


def walls() -> list:
    return list(_STATE["walls"])


def posts() -> list:
    return list(_STATE["posts"])


def mine_spots() -> list:
    return list(_STATE["mines"])


def tree_spots() -> list:
    return list(_STATE["trees"])


def plant_trees(forest) -> int:
    """FIFTY REAL TREES, in the rows the warders planted them in."""
    build()
    if getattr(_STATE, "planted", False):
        return 0
    n = 0
    for i, (tx, ty) in enumerate(_STATE["trees"]):
        try:
            forest.plant(tx, ty, 74.0, i % 4, "conifer", True)
            n += 1
        except Exception:
            pass
    _STATE["planted"] = True
    return n


class PrisonRoom:
    """THE PRISON HALL, drawn the way a MINE is drawn.

    A mine is instant because it is: a room object with W, H, clamp(), update(),
    a pre-rendered picture and a draw that is one blit. This is the same thing
    with a different picture -- frozen earth, ninety straw beddings, blood. The
    picture is made once, in __init__, and never again.
    """

    W, H = 1500, 780
    is_prison = True        # there is no seam to swing at in here

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.flash = 0.0
        self.image = self._render(seed)

    def _render(self, seed: int) -> pygame.Surface:
        import random as _r
        W, H = self.W, self.H
        rng = _r.Random((seed or 1) & 0x7FFFFFFF)
        surf = pygame.Surface((W, H))
        surf.fill((12, 11, 11))                     # the void beyond the walls
        wall = 26
        inner = pygame.Rect(wall, wall, W - 2 * wall, H - 2 * wall)
        # FROZEN DIRT: brown earth, hard-packed, with rime in the hollows.
        pygame.draw.rect(surf, (88, 72, 54), inner)
        for _ in range(9000):                       # clods and trodden patches
            x = rng.randrange(inner.left, inner.right)
            y = rng.randrange(inner.top, inner.bottom)
            r_ = rng.randrange(62, 106)
            g_ = int(r_ * 0.82)
            b_ = int(r_ * 0.62)
            pygame.draw.rect(surf, (r_, g_, b_), (x, y,
                                                  rng.randrange(3, 11),
                                                  rng.randrange(2, 7)))
        for _ in range(2600):                       # FROST in the dirt
            x = rng.randrange(inner.left, inner.right)
            y = rng.randrange(inner.top, inner.bottom)
            v = rng.randrange(206, 246)
            pygame.draw.rect(surf, (v, v, v - 4), (x, y, 1, 1))
        for _ in range(500):                        # and thin rime patches
            x = rng.randrange(inner.left, inner.right - 14)
            y = rng.randrange(inner.top, inner.bottom - 8)
            pygame.draw.ellipse(surf, (198, 202, 208),
                                (x, y, rng.randrange(6, 16), rng.randrange(3, 7)))
        # BLOOD, WATERED AND SOAKED IN: broad, irregular, half-diluted stains
        for _ in range(26):
            x = rng.randrange(inner.left + 60, inner.right - 80)
            y = rng.randrange(inner.top + 60, inner.bottom - 80)
            big = rng.randrange(34, 92)
            # a soaked ring first (most dilute), then the stain over it
            for k, col in ((1.35, (108, 68, 58)), (1.0, (96, 50, 44)),
                           (0.72, (84, 38, 34))):
                w_ = int(big * k)
                pts = []
                for a in range(12):
                    ang = a * 6.283185 / 12.0
                    rr = w_ * rng.uniform(0.62, 1.0)
                    pts.append((x + rr * rng.uniform(0.9, 1.1) * 0.6,
                                y + rr * rng.uniform(0.9, 1.1) * 0.42))
                pygame.draw.polygon(surf, col, pts)
            for _k in range(rng.randrange(2, 6)):   # runnels and spatter
                ax = x + rng.randrange(-big, big)
                ay = y + rng.randrange(-big // 2, big // 2)
                pygame.draw.line(surf, (94, 52, 46), (ax, ay),
                                 (ax + rng.randrange(-40, 40),
                                  ay + rng.randrange(-18, 18)), rng.randrange(1, 4))
        # NINETY STRAW BEDDINGS, ten to a row
        self.beddings = []
        cols, rows = 10, 9
        sx = (inner.w - 180) // cols
        sy = (inner.h - 220) // rows
        for j in range(rows):
            for i in range(cols):
                bx = inner.left + 100 + i * sx
                by = inner.top + 100 + j * sy
                self.beddings.append((bx, by))
                pygame.draw.ellipse(surf, (150, 126, 78), (bx - 32, by - 16, 64, 32))
                pygame.draw.ellipse(surf, (120, 100, 62), (bx - 32, by - 16, 64, 32), 1)
                for _ in range(20):                 # torn straw
                    ax = bx + rng.randrange(-30, 30)
                    ay = by + rng.randrange(-14, 14)
                    pygame.draw.line(surf, (182, 158, 100), (ax, ay),
                                     (ax + rng.randrange(-11, 11),
                                      ay + rng.randrange(-6, 6)), 1)
        # the wall planks around it, and the door gap at the bottom
        pygame.draw.rect(surf, (86, 68, 50), (0, 0, W, wall))
        pygame.draw.rect(surf, (86, 68, 50), (0, H - wall, W, wall))
        pygame.draw.rect(surf, (86, 68, 50), (0, 0, wall, H))
        pygame.draw.rect(surf, (86, 68, 50), (W - wall, 0, wall, H))
        for xx in range(0, W, 26):
            pygame.draw.line(surf, (66, 52, 38), (xx, 0), (xx, wall), 1)
            pygame.draw.line(surf, (66, 52, 38), (xx, H - wall), (xx, H), 1)
        # THE DOOR, SEEN FROM INSIDE: daylight coming in from the yard.
        dx0 = W // 2 - 60
        self.door_rect = pygame.Rect(dx0, H - wall - 6, 120, wall + 6)
        pygame.draw.rect(surf, (232, 236, 242), self.door_rect)
        # ...and the light spilling across the threshold into the hall
        for i, a in enumerate((70, 52, 36, 22, 12)):
            band = pygame.Rect(dx0 - i * 8, H - wall - 6 - (i + 1) * 12,
                               120 + i * 16, (i + 1) * 12)
            light = pygame.Surface(band.size, pygame.SRCALPHA)
            light.fill((236, 240, 246, a))
            surf.blit(light, band.topleft)
        pygame.draw.rect(surf, (150, 154, 160), self.door_rect, 2)
        return surf

    # -- the mine-room interface -------------------------------------------
    def update(self, dt: float) -> None:
        self.flash = max(0.0, self.flash - dt)

    def clamp(self, x: float, y: float) -> tuple:
        return (min(max(x, 40.0), self.W - 40.0),
                min(max(y, 40.0), self.H - 40.0))

    def hits_chunk(self, x: float, y: float) -> bool:
        return False                    # there is nothing to mine in a prison

    def swing(self, yields=(0, 0)):
        return 0

    def draw(self, screen, cam_x: float, cam_y: float, vw: int = 0,
             vh: int = 0) -> None:
        w = vw or screen.get_width()
        h = vh or screen.get_height()
        screen.fill((10, 10, 12), (0, 0, w, h))
        screen.blit(self.image, (int(-cam_x), int(-cam_y)))


_DARK = {}


def darken(screen, alpha: int = 132) -> None:
    """A FLAT VEIL over the room: dark, even, and nothing to follow."""
    key = (screen.get_size(), alpha)
    surf = _DARK.get(key)
    if surf is None:
        surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        surf.fill((6, 6, 8, alpha))
        _DARK[key] = surf
    screen.blit(surf, (0, 0))


def shade(screen, px: float, py: float, radius: int = 340) -> None:
    """DARK, BUT YOU CAN SEE WHERE YOU ARE GOING.

    A wide hole of light around the man, falling away to black. The gradient is
    made once and kept; every frame is four black rectangles and one blit.
    """
    key = radius
    grad = _SHADE.get(key)
    if grad is None:
        size = radius * 2
        grad = pygame.Surface((size, size), pygame.SRCALPHA)
        for r in range(radius, 0, -3):
            a = int(215 * (1.0 - (r / float(radius)) ** 1.6))
            pygame.draw.circle(grad, (4, 4, 6, max(0, min(215, a))),
                               (radius, radius), r)
        _SHADE[key] = grad
    vw, vh = screen.get_size()
    x, y = int(px), int(py)
    top = max(0, y - radius)
    bottom = min(vh, y + radius)
    left = max(0, x - radius)
    right = min(vw, x + radius)
    for rect in ((0, 0, vw, top), (0, bottom, vw, vh - bottom),
                 (0, top, left, bottom - top), (right, top, vw - right, bottom - top)):
        if rect[2] > 0 and rect[3] > 0:
            screen.fill((4, 4, 6), rect)
    screen.blit(grad, (x - radius, y - radius))


class Prison:
    """THE BARN: a workplace you walk up to and go into, exactly like a mine."""

    kind = "prison"

    def __init__(self, x: float, y: float, w: int = 1900, h: int = 700,
                 seed: int = 70001) -> None:
        self.x, self.y = float(x), float(y)
        self.w, self.h = int(w), int(h)
        self.rect = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
        self.base_y = y + h / 2.0
        self.sight_rect = self.rect.inflate(48, 48)
        self.door = (x, y + h / 2.0 + 14.0)
        self.worker = None
        self.owner = None
        self.camp = True
        self.seed = seed
        self.room = PrisonRoom(seed)
        self.image = self._render()

    def _render(self) -> pygame.Surface:
        w, h = self.w, self.h
        pad = 26
        s = pygame.Surface((w + pad * 2, h + pad * 4), pygame.SRCALPHA)
        ox, oy = pad, pad * 2
        pygame.draw.ellipse(s, (18, 18, 20, 110), (ox + 16, oy + h - 10, w - 32, 22))
        pygame.draw.rect(s, (118, 104, 84), (ox, oy, w, h))
        for yy in range(oy + 6, oy + h, 12):
            pygame.draw.line(s, (94, 82, 66), (ox + 2, yy), (ox + w - 3, yy), 1)
        for xx in range(ox + 40, ox + w, 120):
            pygame.draw.rect(s, (74, 64, 50), (xx, oy, 10, h))
        pygame.draw.rect(s, (48, 40, 30), (ox, oy, w, h), 4)
        mid = oy - 60
        pygame.draw.polygon(s, (74, 66, 56),
                            [(ox - 30, oy), (ox + w + 30, oy),
                             (ox + w - 40, mid), (ox + 40, mid)])
        pygame.draw.polygon(s, (40, 36, 30),
                            [(ox - 30, oy), (ox + w + 30, oy),
                             (ox + w - 40, mid), (ox + 40, mid)], 3)
        for xx in range(ox + 30, ox + w - 20, 36):
            pygame.draw.line(s, (58, 52, 44), (xx, oy - 2), (xx + 8, mid + 8), 1)
        dw = 150
        pygame.draw.rect(s, (16, 15, 14), (ox + w // 2 - dw // 2, oy + h - 150, dw, 150))
        pygame.draw.rect(s, (60, 50, 38), (ox + w // 2 - dw // 2, oy + h - 150, dw, 150), 4)
        for xx in range(ox + 90, ox + w - 60, 190):
            pygame.draw.rect(s, (28, 26, 24), (xx, oy + 60, 44, 26))
            for bx in range(xx + 6, xx + 44, 10):
                pygame.draw.line(s, (140, 144, 150), (bx, oy + 60), (bx, oy + 86), 1)
        return s

    def draw(self, screen, cam_x: float, cam_y: float) -> None:
        screen.blit(self.image, (self.x - cam_x - self.image.get_width() / 2,
                                 self.y - cam_y - self.image.get_height() / 2))


def make_guards(frame_soldier_factory, nation=1) -> list:
    """TWENTY MEN, ONE ON EACH PERIMETER POST, armed with what the cage needs."""
    build()
    out = []
    posts = list(_STATE["posts"])
    # TWENTY MEN ON TEN POSTS: two to a post, a step apart, so every angle of
    # the wall is covered by two guns rather than one.
    while len(posts) < GUARDS:
        i = len(posts) % len(_STATE["posts"])
        bx, by = _STATE["posts"][i]
        posts.append((bx + 26.0, by + 18.0))
    for i, (px, py) in enumerate(posts[:GUARDS]):
        try:
            s = frame_soldier_factory(px, py, nation)
        except Exception:
            continue
        # NEVER ON THE PERMANENT WAY: the rail comes in through the gate, and a
        # guard standing on the sleepers is a guard standing where the train is.
        try:
            import rail as _rail
            _tries = 0
            while _rail.blocked(px, py, 30.0) and _tries < 8:
                py += 70.0
                _tries += 1
        except Exception:
            pass
        s.gulag = True
        s.is_militia = True            # camp warders are militia
        s.guard_post = (px, py)
        s.home = (px, py)
        s.target = (px, py)
        s.x, s.y = px, py
        s.name = "a guard of the camp" if i else "the warden"
        s.weapon = "rifle"                 # militia: darts, one round a pull
        s.gun_kind = s.weapon
        s.ammo = 200
        try:
            import guns as _guns
            s.mag = _guns.MAG[s.gun_kind]      # WITHOUT THIS THEY CANNOT FIRE
            s.reload_timer = 0.0
        except Exception:
            pass
        try:
            s.skills.shooting = 1.0
            s.skills.axe = 0.5
        except Exception:
            pass
        out.append(s)
    _STATE["guards"] = out
    return out


def is_guard(who) -> bool:
    return bool(getattr(who, "gulag", False))


def intruders(townsmen=(), players=()) -> list:
    """EVERYBODY INSIDE WHO HAS NO BUSINESS BEING THERE."""
    out = []
    for who in list(townsmen) + [p for p in players if p is not None]:
        if getattr(who, "dead", False) or not getattr(who, "alive", True):
            continue
        if is_guard(who):
            continue
        if inside(getattr(who, "x", 0.0), getattr(who, "y", 0.0)):
            out.append(who)
    return out


def tick(player, enemies, townsmen=(), combat=None, dt: float = 0.0) -> int:
    """ANYBODY OVER THE LINE IS SHOT. Called once a frame.

    The guards fire HERE and not through the general combat code: two of them
    to a post, twenty guns on one man, is a frame's worth of bullets if every
    one of them fires at once. One guard fires per turn, a few turns a second,
    so a man caught in the yard is under fire from the moment he steps in and
    the frame never stalls for it.
    """
    build()
    if not _STATE["guards"]:
        return 0
    # NOBODY OUTSIDE THE CAMP IS WORTH SCANNING FOR. This walked the whole
    # register -- a thousand people -- on every frame of the game, in the
    # middle of the country as much as in the yard: that is the five or six
    # milliseconds the frame lost everywhere.
    try:
        if not inside(getattr(player, "x", 0.0), getattr(player, "y", 0.0),
                      HALF_SIZE + 600.0):
            if not _STATE.get("inside"):
                return 0
    except Exception:
        pass
    caught = intruders(townsmen, [player])
    _STATE["inside"] = len(caught)
    for who in caught:
        for g in _STATE["guards"]:
            if not getattr(g, "alive", True):
                continue
            try:
                g.hostile = True
                g.aggro = True
                g.add_threat(who)
                # face him: no steering, no pathfinding, just eyes on the man
                dx, dy = who.x - g.x, who.y - g.y
                d = math.hypot(dx, dy) or 1.0
                g.facing = (dx / d, dy / d)
            except Exception:
                pass
    if not caught or combat is None:
        return len(caught)
    # ONE GUARD FIRES PER TURN, ROUND ROBIN, AND ONLY A FEW TURNS A SECOND.
    # A turn per FRAME is sixty volleys a second: twelve pellets each is seven
    # hundred bullets in the air, which is the ninety-millisecond frames.
    cool = float(_STATE.get("cool", 0.0) or 0.0) - float(dt)
    _STATE["cool"] = cool
    if cool > 0.0:
        return len(caught)
    _STATE["cool"] = 0.22                      # about four and a half a second
    _STATE["turn"] = int(_STATE.get("turn", 0)) + 1
    guard = _STATE["guards"][_STATE["turn"] % len(_STATE["guards"])]
    if not getattr(guard, "alive", True):
        return len(caught)
    who = caught[0]
    dx, dy = who.x - guard.x, who.y - guard.y
    dist = math.hypot(dx, dy) or 1.0
    if dist > 900.0:
        return len(caught)
    try:
        if not guard._round_ready():
            return len(caught)
        import random as _r
        ang = math.atan2(dy, dx) + _r.uniform(-0.04, 0.04)
        mx = guard.x + dx / dist * 18.0
        my = guard.y + dy / dist * 18.0
        guard._shoot(combat, mx, my, ang, dist + 200.0, 80, 80)
        guard.attack_flash = 0.3
    except Exception:
        pass
    return len(caught)


# ---------------------------------------------------------------- the art --
_SPR: dict = {}
_DBG = {"n": 0, "snow": 0.0, "all": 0.0}


def _pine_sprite() -> pygame.Surface:
    got = _SPR.get("pine")
    if got is not None:
        return got
    w, h = 34, 56
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (24, 30, 34, 90), (4, h - 10, w - 8, 8))
    pygame.draw.rect(s, WOOD_DARK, (w // 2 - 2, h - 16, 4, 14))
    for i, (dy, half) in enumerate(((0, 8), (10, 12), (20, 15))):
        top = dy
        pygame.draw.polygon(s, PINE, [(w // 2 - half, top + 18), (w // 2, top),
                                      (w // 2 + half, top + 18)])
        pygame.draw.polygon(s, PINE_DARK, [(w // 2 - half, top + 18), (w // 2, top),
                                           (w // 2 + half, top + 18)], 1)
    _SPR["pine"] = s
    return s


def _mine_sprite() -> pygame.Surface:
    got = _SPR.get("mine")
    if got is not None:
        return got
    w, h = 56, 62
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (24, 22, 20, 110), (6, h - 16, w - 12, 14))
    # the shed
    pygame.draw.rect(s, (74, 66, 58), (8, h - 30, w - 16, 22))
    pygame.draw.rect(s, (40, 34, 28), (8, h - 30, w - 16, 22), 2)
    pygame.draw.polygon(s, (52, 46, 40), [(6, h - 30), (w // 2, h - 44), (w - 6, h - 30)])
    # the headframe
    pygame.draw.line(s, IRON, (w // 2 - 14, h - 30), (w // 2, 6), 3)
    pygame.draw.line(s, IRON, (w // 2 + 14, h - 30), (w // 2, 6), 3)
    pygame.draw.line(s, (150, 154, 160), (w // 2 - 7, h - 42), (w // 2 + 7, h - 42), 2)
    pygame.draw.circle(s, (28, 26, 24), (w // 2, 8), 5)
    pygame.draw.circle(s, (150, 154, 160), (w // 2, 8), 5, 1)
    # the shaft mouth
    pygame.draw.rect(s, (16, 15, 14), (w // 2 - 8, h - 24, 16, 16))
    _SPR["mine"] = s
    return s


def _building_sprite(w: int, h: int, barred: bool, storeys: int = 1) -> pygame.Surface:
    key = ("b", w, h, barred, storeys)
    got = _SPR.get(key)
    if got is not None:
        return got
    pad = 18
    s = pygame.Surface((w + pad * 2, h + pad * 3), pygame.SRCALPHA)
    ox, oy = pad, pad * 2
    # shadow and walls
    pygame.draw.ellipse(s, (20, 20, 22, 90), (ox + 10, oy + h - 6, w - 20, 16))
    pygame.draw.rect(s, (120, 96, 66), (ox, oy, w, h))
    for yy in range(oy + 4, oy + h, 9):                 # plank courses
        pygame.draw.line(s, (98, 78, 52), (ox + 1, yy), (ox + w - 2, yy), 1)
    pygame.draw.rect(s, (58, 44, 30), (ox, oy, w, h), 3)
    # roof: two pitches with a ridge, overhanging the walls
    over = 16
    mid = oy - 26
    pygame.draw.polygon(s, (86, 66, 44),
                        [(ox - over, oy), (ox + w + over, oy),
                         (ox + w + over - 26, mid), (ox + 26, mid)])
    pygame.draw.polygon(s, (62, 46, 30),
                        [(ox - over, oy), (ox + w + over, oy),
                         (ox + w + over - 26, mid), (ox + 26, mid)], 2)
    pygame.draw.line(s, (48, 36, 24), (ox + 26, mid + 1),
                     (ox + w + over - 26, mid + 1), 2)
    for xx in range(ox + 20, ox + w + over - 20, 26):    # shingles
        pygame.draw.line(s, (74, 56, 38), (xx, oy - 4), (xx + 6, mid + 6), 1)
    # door, with a step
    dw, dh = 46, min(70, h - 24)
    pygame.draw.rect(s, (52, 38, 24), (ox + w // 2 - dw // 2, oy + h - dh, dw, dh))
    pygame.draw.rect(s, (30, 22, 14), (ox + w // 2 - dw // 2, oy + h - dh, dw, dh), 2)
    pygame.draw.circle(s, (188, 160, 96), (ox + w // 2 + dw // 2 - 9, oy + h - dh // 2), 2)
    # windows along the front
    cols = max(2, w // 170)
    step = w // (cols + 1)
    for c in range(cols):
        wx = ox + step * (c + 1) - 18
        for st in range(storeys):
            wy = oy + 22 + st * (h // max(1, storeys))
            pygame.draw.rect(s, (34, 30, 26), (wx, wy, 36, 26))
            if barred:
                pygame.draw.rect(s, (150, 154, 160), (wx, wy, 36, 26), 1)
                for bx in (wx + 8, wx + 18, wx + 28):
                    pygame.draw.line(s, (150, 154, 160), (bx, wy + 1),
                                     (bx, wy + 25), 1)
            else:
                pygame.draw.rect(s, (96, 118, 130), (wx + 2, wy + 2, 32, 22))
                pygame.draw.rect(s, (58, 44, 30), (wx + 2, wy + 2, 32, 22), 1)
    _SPR[key] = s
    return s


def _fence_piece(length: int, vertical: bool) -> pygame.Surface:
    key = ("f", length, vertical)
    got = _SPR.get(key)
    if got is not None:
        return got
    t = int(WALL)
    if vertical:
        s = pygame.Surface((t, length), pygame.SRCALPHA)
        pygame.draw.rect(s, FENCE, (0, 0, t, length))
        for yy in range(0, length, 14):                  # palings
            pygame.draw.line(s, FENCE_DARK, (1, yy), (t - 2, yy), 2)
        pygame.draw.line(s, (132, 108, 78), (2, 0), (2, length), 2)
        pygame.draw.line(s, (54, 42, 30), (t - 2, 0), (t - 2, length), 2)
        for yy in (length // 3, 2 * length // 3):        # rails across
            pygame.draw.line(s, (86, 66, 44), (0, yy), (t, yy), 4)
    else:
        s = pygame.Surface((length, t), pygame.SRCALPHA)
        pygame.draw.rect(s, FENCE, (0, 0, length, t))
        for xx in range(0, length, 14):
            pygame.draw.line(s, FENCE_DARK, (xx, 1), (xx, t - 2), 2)
        pygame.draw.line(s, (132, 108, 78), (0, 2), (length, 2), 2)
        pygame.draw.line(s, (54, 42, 30), (0, t - 2), (length, t - 2), 2)
        for xx in (length // 3, 2 * length // 3):
            pygame.draw.line(s, (86, 66, 44), (xx, 0), (xx, t), 4)
    _SPR[key] = s
    return s


def draw(screen, cam_x: float, cam_y: float, view: pygame.Rect) -> None:
    """WHAT THE CAMP ADDS TO THE GROUND: trodden snow, and that is all.

    The fence, the two buildings, the thirty mines and the fifty trees are all
    real objects in the game's own lists (built_fences, built_houses,
    placed_work, the forest) and are drawn by the code that draws those. This
    only paints the yard, and only the part of it on screen.
    """
    build()
    r = rect()
    if not view.colliderect(r.inflate(400, 400)):
        return
    sx, sy = SITE
    inner = pygame.Rect(int(sx - HALF_SIZE + WALL), int(sy - HALF_SIZE + WALL),
                        int(2 * (HALF_SIZE - WALL)), int(2 * (HALF_SIZE - WALL)))
    seen = inner.clip(view).clip(screen.get_rect())
    if seen.w > 0 and seen.h > 0:
        screen.fill(SNOW, (seen.x - cam_x, seen.y - cam_y, seen.w, seen.h))
