"""view3d.py -- a small, deliberately simple first-person view of the world.

This is the M0 3D spike, not the shipping renderer.  It reads the world the
simulation has already built and draws it as a flat-ground first-person scene
with billboards.  Nothing here owns game state, changes a save, or asks the
economy or the NPCs to do anything differently.

The important contract:

    * one world unit is one pixel, as everywhere else in the game
    * the eye sits EYE_Z above the ground
    * the ground is sampled from the existing GroundRenderer
    * NPCs, animals, trees, houses and workplaces are camera-facing billboards

The C++ renderer can replace this later behind the same idea: the simulation
keeps x/y, the view reads a scene, and the HUD stays in pygame.
"""

from __future__ import annotations

import math
import os

import numpy as np
import pygame

import face
import items

# Internal frame.  The window is filled by scaling this up, so the first
# version pays for 480x270 rays rather than 1280x720 ones.
IW, IH = 480, 270
FOV = math.radians(78.0)
FOCAL = IW / (2.0 * math.tan(FOV * 0.5))
EYE_Z = 56.0                 # 1.75 m if a tile (32 px) is one metre
DRAW_DIST = 9000.0
NEAR = 24.0
MAX_SPRITE_PX = 900

# Menu state that hands the mouse back to pygame.  If any of these is open,
# the 3D view keeps drawing behind it but does not eat the mouse.
_BLOCKERS = (
    "inventory_open", "trade_open", "build_menu_open", "chest_open",
    "workshop_open", "confirm_open", "pause_open", "map_open",
    "worker_panel_open", "npc_card_open", "horse_panel_open", "board_open",
    "smith_open", "artisan_open", "naming_open", "market_open",
    "research_open", "game_over",
)


def _blocked(g) -> bool:
    return any(bool(getattr(g, name, False)) for name in _BLOCKERS) \
        or getattr(g, "inside_house", None) is not None \
        or getattr(g, "inside_mine", None) is not None \
        or getattr(g, "placing", None) is not None \
        or bool(getattr(g, "field_design", False)) \
        or bool(getattr(g, "comm_mode", False)) \
        or bool(getattr(getattr(g, "dialogue_panel", None), "open_", False))


def active(g) -> bool:
    return bool(getattr(g, "view3d", False)) and not _blocked(g)


def _release_mouse(g) -> None:
    if not getattr(g, "_v3_grab", False):
        return
    try:
        pygame.mouse.set_relative_mode(False)
    except Exception:
        pass
    try:
        pygame.event.set_grab(False)
    except Exception:
        pass
    g._v3_grab = False


def _grab_mouse(g) -> None:
    if getattr(g, "_v3_grab", False):
        return
    try:
        pygame.mouse.set_visible(False)
        pygame.mouse.set_relative_mode(True)
    except Exception:
        try:
            pygame.event.set_grab(True)
        except Exception:
            pass
    g._v3_grab = True


def toggle(g) -> None:
    if getattr(g, "view3d", False):
        g.view3d = False
        _release_mouse(g)
        pygame.mouse.set_visible(False)
        _toast(g, "Top-down view")
        return
    if _blocked(g):
        _toast(g, "Close the open panel first")
        return
    g.view3d = True
    fx, fy = getattr(g.player, "facing", (0.0, 1.0))
    g.v3d_yaw = math.atan2(float(fy), float(fx)) if (fx or fy) else 0.0
    g.v3d_pitch = 0.0
    _grab_mouse(g)
    _toast(g, "First-person view   [V] back to top-down")


def _toast(g, text: str) -> None:
    try:
        g.toast(text)
    except Exception:
        pass


def tick(g, dt: float) -> None:
    """Mouse look.  Called once at the top of the frame, before movement."""
    if not active(g):
        _release_mouse(g)
        return
    _grab_mouse(g)
    dx, dy = pygame.mouse.get_rel()
    if dx or dy:
        g.v3d_yaw = (float(getattr(g, "v3d_yaw", 0.0)) + dx * 0.0032) % (2.0 * math.pi)
        p = float(getattr(g, "v3d_pitch", 0.0)) - dy * 0.0028
        g.v3d_pitch = max(-1.15, min(1.15, p))


def move_basis(g):
    """(forward, right) in the game's world plane, for relative WASD."""
    y = float(getattr(g, "v3d_yaw", 0.0))
    return ((math.cos(y), math.sin(y)), (-math.sin(y), math.cos(y)))


# ---------------------------------------------------------------------------
# ground sampling
# ---------------------------------------------------------------------------
class _GroundSampler:
    """A cheap colour map around the player.

    It is not a heightmap or a mesh.  It is the existing ground surface,
    sampled on a coarse local lattice, which is enough for the M0 view and
    avoids per-pixel chunk lookups in the frame.
    """

    N = 96
    SPAN = 8192.0

    def __init__(self) -> None:
        self.grid = None
        self.cx = 0.0
        self.cy = 0.0
        self.t = -1e9

    def ensure(self, g, now: float) -> None:
        px, py = float(g.player.x), float(g.player.y)
        if (self.grid is not None
                and math.hypot(px - self.cx, py - self.cy) < self.SPAN * 0.18
                and now - self.t < 0.75):
            return
        n = self.N
        span = self.SPAN
        grid = np.empty((n, n, 3), dtype=np.uint8)
        chunk = 256
        for iy in range(n):
            wy = py + (iy / (n - 1.0) - 0.5) * span
            cy = int(wy // chunk)
            for ix in range(n):
                wx = px + (ix / (n - 1.0) - 0.5) * span
                cx = int(wx // chunk)
                surf = g.ground.get(cx, cy)
                if surf is not None:
                    lx = int(wx - cx * chunk) & 255
                    ly = int(wy - cy * chunk) & 255
                    try:
                        grid[iy, ix] = surf.get_at((lx, ly))[:3]
                        continue
                    except Exception:
                        pass
                col = g.ground._coarse_color(cx, cy)
                grid[iy, ix] = col
        self.grid = grid
        self.cx, self.cy, self.t = px, py, now

    def at(self, wx, wy):
        if self.grid is None:
            return None
        n = self.N
        u = (wx - self.cx) / self.SPAN + 0.5
        v = (wy - self.cy) / self.SPAN + 0.5
        ix = np.clip((u * (n - 1)).astype(np.int32), 0, n - 1)
        iy = np.clip((v * (n - 1)).astype(np.int32), 0, n - 1)
        return self.grid[iy, ix]


def _sky_colours(g):
    night = bool(getattr(g, "night", False))
    if night:
        return (10, 14, 30), (34, 42, 62)
    return (92, 132, 172), (196, 206, 196)


def _ground_frame(g, sampler: _GroundSampler) -> pygame.Surface:
    """Rasterise the floor plane and sky into the internal frame."""
    night = bool(getattr(g, "night", False))
    sky_top, sky_bottom = _sky_colours(g)
    arr = np.empty((IW, IH, 3), dtype=np.uint8)

    yy = np.arange(IH, dtype=np.float32)
    xx = np.arange(IW, dtype=np.float32)
    X, Y = np.meshgrid(xx, yy, indexing="ij")
    sx = (X - IW * 0.5) / FOCAL
    sy = (IH * 0.5 - Y) / FOCAL

    yaw = float(getattr(g, "v3d_yaw", 0.0))
    pitch = float(getattr(g, "v3d_pitch", 0.0))
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    fwd = np.array((cy_ * cp, sy_ * cp, sp), dtype=np.float32)
    right = np.array((-sy_, cy_, 0.0), dtype=np.float32)
    up = np.array((-sp * cy_, -sp * sy_, cp), dtype=np.float32)

    dx = fwd[0] + right[0] * sx + up[0] * sy
    dy = fwd[1] + right[1] * sx + up[1] * sy
    dz = fwd[2] + right[2] * sx + up[2] * sy

    # sky gradient, in screen space
    grad = (Y / float(max(1, IH - 1)))[..., None]
    sky = np.array(sky_top, np.float32) * (1.0 - grad) + \
        np.array(sky_bottom, np.float32) * grad
    arr[:] = np.clip(sky, 0, 255).astype(np.uint8)

    hit = dz < -1e-4
    if np.any(hit):
        t = np.zeros_like(dz, dtype=np.float32)
        np.divide(-EYE_Z, dz, out=t, where=hit)
        # The last few degrees above the horizon give enormous hit distances;
        # leave those to the sky/fog rather than sampling the map at infinity.
        hit &= t < DRAW_DIST * 1.6
        wx = float(g.player.x) + dx * t
        wy = float(g.player.y) + dy * t
        wx = np.nan_to_num(wx, nan=float(g.player.x), posinf=float(g.player.x),
                           neginf=float(g.player.x))
        wy = np.nan_to_num(wy, nan=float(g.player.y), posinf=float(g.player.y),
                           neginf=float(g.player.y))
        cols = sampler.at(wx, wy)
        if cols is not None:
            fog = np.clip((t - 1500.0) / 9000.0, 0.0, 0.72)
            hz = np.array(sky_bottom, np.float32)
            cols = cols.astype(np.float32) * (1.0 - fog[..., None]) + \
                hz * fog[..., None]
            if night:
                cols *= 0.58
            arr[hit] = np.clip(cols[hit], 0, 255).astype(np.uint8)

    return pygame.surfarray.make_surface(arr)


# ---------------------------------------------------------------------------
# billboard art
# ---------------------------------------------------------------------------
_NPC_CACHE: dict = {}
_ANIMAL_CACHE: dict = {}


def _npc_mood(npc) -> str:
    try:
        mood = face.mood_of(
            float(getattr(npc, "hurt_flash", 0.0)),
            float(getattr(npc, "attack_flash", 0.0)),
            float(getattr(npc, "work_flash", 0.0)),
            float(getattr(npc, "sly_flash", 0.0)),
            float(getattr(npc, "hunger", 0.0)) >= face.STARVED_HUNGER)
    except Exception:
        mood = "normal"
    if getattr(npc, "break_state", "normal") == "depression":
        mood = "sad"
    if getattr(npc, "asleep", False) or getattr(npc, "sleep_t", 0.0) > 0.0:
        mood = "sleep"
    return mood


def _npc_sprite(npc, back: bool) -> pygame.Surface:
    clothing = tuple(getattr(npc, "clothing", (88, 76, 62)) or (88, 76, 62))
    skin = tuple(getattr(npc, "skin", (216, 172, 132)) or (216, 172, 132))
    armor = ("hide" if getattr(npc, "hide_armor", False) else
             "iron" if getattr(npc, "iron_armor", False) else
             "reinforced" if getattr(npc, "reinforced_armor", False) else
             "")
    stalin = bool(getattr(npc, "is_stalin", False))
    flash = float(getattr(npc, "hit_flash", 0.0)) > 0.0
    mood = "normal" if back else _npc_mood(npc)
    try:
        vet = face.vet_tier(getattr(npc.skills, "axe", 0.0),
                            getattr(npc.skills, "shooting", 0.0))
    except Exception:
        vet = 0
    swing = float(getattr(npc, "swing_anim", 0.0))
    swing_bucket = int(max(0.0, min(1.0, 1.0 - swing / 0.45)) * 8.0) if swing > 0.0 else -1
    key = (clothing, skin, armor, stalin, bool(back), mood, vet, flash, swing_bucket)
    got = _NPC_CACHE.get(key)
    if got is not None:
        return got

    w, h = 40, 72
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    # shadow in the sprite is left to the ground; feet meet the anchor
    body = (74, 78, 76) if stalin else clothing
    if armor == "hide":
        body = (120, 82, 46)
    elif armor == "iron":
        body = (132, 138, 146)
    elif armor == "reinforced":
        body = (176, 180, 190)
    if flash:
        body = (238, 226, 226)
    # legs
    pygame.draw.rect(s, (44, 38, 32), (cx - 10, 50, 7, 20), border_radius=2)
    pygame.draw.rect(s, (44, 38, 32), (cx + 3, 50, 7, 20), border_radius=2)
    # torso
    pygame.draw.ellipse(s, body, (cx - 14, 26, 28, 32))
    pygame.draw.ellipse(s, (30, 26, 22), (cx - 14, 26, 28, 32), 2)
    # arms
    pygame.draw.line(s, body, (cx - 13, 32), (cx - 18, 51), 6)
    pygame.draw.line(s, body, (cx + 13, 32), (cx + 18, 51), 6)
    # armour bands
    if armor:
        col = (70, 46, 28) if armor == "hide" else (64, 68, 76)
        pygame.draw.line(s, col, (cx - 12, 38), (cx + 12, 38), 3)
        pygame.draw.line(s, col, (cx - 11, 45), (cx + 11, 45), 2)
    # A WEAPON SWEEP, drawn in the card so every NPC fight reads at a glance.
    if (not back) and swing_bucket >= 0:
        _p = swing_bucket / 8.0
        _ang = math.radians(-105.0 + 210.0 * _p)
        _hx, _hy = cx + 11, 38
        _ex = _hx + math.cos(_ang) * 24.0
        _ey = _hy + math.sin(_ang) * 24.0
        pygame.draw.line(s, (116, 82, 46), (_hx, _hy), (_ex, _ey), 3)
        _px, _py = -math.sin(_ang), math.cos(_ang)
        pygame.draw.line(s, (208, 208, 214),
                         (_ex - _px * 6, _ey - _py * 6),
                         (_ex + _px * 6, _ey + _py * 6), 3)
    # head
    if not back:
        try:
            face.hair(s, cx, 18, 10)
        except Exception:
            pass
    pygame.draw.circle(s, skin, (cx, 18), 10)
    pygame.draw.circle(s, (150, 108, 78), (cx, 18), 10, 1)
    if back or stalin:
        pygame.draw.arc(s, (34, 26, 20), (cx - 10, 8, 20, 18), 0.15, math.pi - 0.15, 3)
    if not back:
        try:
            face.draw(s, cx, 18, 9, 0.0, 1.0, mood, skin, vet)
        except Exception:
            pygame.draw.circle(s, (46, 34, 28), (cx - 4, 17), 1)
            pygame.draw.circle(s, (46, 34, 28), (cx + 4, 17), 1)
        try:
            if getattr(npc, "iron_helmet", False) or getattr(npc, "iron_armor", False):
                face.iron_helmet(s, cx, 18, 10)
            face.feather(s, cx, 18, 10)
            if getattr(npc, "kind", "") == "soldier":
                face.war_paint(s, cx, 18, 10)
        except Exception:
            pass
    _NPC_CACHE[key] = s
    return s


def _animal_sprite(e, yaw: float):
    kind = getattr(e, "kind", "")
    fx, fy = getattr(e, "facing", (0.0, 1.0))
    if abs(fx) + abs(fy) < 0.01:
        fx, fy = 0.0, 1.0
    # The animal art is already eight pre-rendered directions.  Pick the
    # direction relative to the camera, as a billboard should.
    d = int(round((math.atan2(fy, fx) - yaw) / (math.pi / 4.0))) % 8
    hit = float(getattr(e, "hit_flash", 0.0)) > 0.0
    try:
        if kind == "wolf":
            import wolfart
            species = getattr(e, "species", "wolf")
            if species not in ("white_wolf", "hyena"):
                species = "wolf"
            img = wolfart.frame(species, d, 0, 0.92, hit=hit,
                                lunge=bool(getattr(e, "lunging", 0.0)))
            return img, wolfart.AX, wolfart.AY, float(img.get_height())
        if kind == "rabbit":
            import rabbitart
            img = rabbitart.frame(getattr(e, "fur", "brown"), d, 0, 0.92, hit=hit)
            return img, rabbitart.AX, rabbitart.AY, float(img.get_height())
        if kind == "horse":
            import horseart
            zoom = 0.64 if getattr(e, "baby", False) else 0.90
            img = horseart.frame(getattr(e, "coat", "brown"), d, 0, zoom, hit=hit)
            return img, horseart.AX, horseart.AY, float(img.get_height())
        if kind == "bison":
            import bisonart
            zoom = 0.64 if getattr(e, "baby", False) else 1.0
            img = bisonart.frame(d, 0, zoom, hit=hit,
                                 charge=bool(getattr(e, "aggro", False)),
                                 baby=bool(getattr(e, "baby", False)))
            return img, bisonart.AX, bisonart.AY, float(img.get_height())
    except Exception:
        pass
    # Soldiers and other simple enemies: use their existing top-down art on a
    # transparent card.  This is a placeholder, not the final sprite system.
    s = pygame.Surface((72, 88), pygame.SRCALPHA)
    try:
        e.draw(s, float(e.x) - 36.0, float(e.y) - 70.0)
    except Exception:
        pass
    return s, 36.0, 84.0, 80.0


# ---------------------------------------------------------------------------
# projection / draw
# ---------------------------------------------------------------------------
def _cam(g):
    yaw = float(getattr(g, "v3d_yaw", 0.0))
    pitch = float(getattr(g, "v3d_pitch", 0.0))
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    fwd = np.array((cy * cp, sy * cp, sp), dtype=np.float32)
    right = np.array((-sy, cy, 0.0), dtype=np.float32)
    up = np.array((-sp * cy, -sp * sy, cp), dtype=np.float32)
    return fwd, right, up


def _project(fwd, right, up, ex, ey, px, py, pz):
    dx, dy, dz = px - ex, py - ey, pz - EYE_Z
    cz = fwd[0] * dx + fwd[1] * dy + fwd[2] * dz
    if cz <= NEAR:
        return None
    cx = right[0] * dx + right[1] * dy + right[2] * dz
    cy = up[0] * dx + up[1] * dy + up[2] * dz
    return (IW * 0.5 + FOCAL * cx / cz,
            IH * 0.5 - FOCAL * cy / cz, cz)


def _collect(g, yaw: float):
    """Return (sprite, x, y, world_h, anchor_x, anchor_y, label) cards."""
    out = []
    ex, ey = float(g.player.x), float(g.player.y)
    px, py = ex, ey
    lim = DRAW_DIST
    # People -- one flat register, not every town's list.
    try:
        import village as _village
        people = list(getattr(_village, "PEOPLE", ()))
    except Exception:
        people = []
        for v in getattr(g, "visible_villages", ()) or ():
            people.extend(getattr(v, "npcs", ()) or ())
    for npc in people:
        if not getattr(npc, "alive", True) or getattr(npc, "in_interior", False):
            continue
        d = math.hypot(float(npc.x) - ex, float(npc.y) - ey)
        if d > lim:
            continue
        # Front when the man faces the camera, back when he walks away.
        tfx, tfy = ex - float(npc.x), ey - float(npc.y)
        ffx, ffy = getattr(npc, "facing", (0.0, 1.0))
        front = (ffx * tfx + ffy * tfy) >= -0.01
        walking = getattr(npc, "activity", "") == "walk" or getattr(npc, "moving", False)
        card = _npc_sprite(npc, back=not front)
        out.append((card, float(npc.x), float(npc.y), 68.0, 20.0, 72.0,
                    getattr(npc, "name", "")))
    # Wild things and soldiers.
    for e in list(getattr(g, "enemies", ()) or ()):
        if not getattr(e, "alive", True):
            continue
        d = math.hypot(float(e.x) - ex, float(e.y) - ey)
        if d > lim:
            continue
        card, ax, ay, wh = _animal_sprite(e, yaw)
        out.append((card, float(e.x), float(e.y), wh, ax, ay, ""))
    for e in list(getattr(g, "rabbits", ()) or ()):
        d = math.hypot(float(e.x) - ex, float(e.y) - ey)
        if d > lim:
            continue
        card, ax, ay, wh = _animal_sprite(e, yaw)
        out.append((card, float(e.x), float(e.y), wh, ax, ay, ""))
    for e in list(getattr(g, "horses", ()) or ()):
        d = math.hypot(float(e.x) - ex, float(e.y) - ey)
        if d > lim:
            continue
        card, ax, ay, wh = _animal_sprite(e, yaw)
        out.append((card, float(e.x), float(e.y), wh, ax, ay, ""))
    # Trees.
    trees = (getattr(g, "view3d_trees", None)
             or getattr(g, "view_trees", ())
             or getattr(g, "draw_trees", ()) or ())
    for t in list(trees):
        if math.hypot(float(t.x) - ex, float(t.y) - ey) > lim:
            continue
        try:
            img, _at = t.blit_world()
            out.append((img, float(t.x), float(t.y), float(img.get_height()),
                        float(getattr(t, "sx", img.get_width() / 2)),
                        float(getattr(t, "sy", img.get_height())), ""))
        except Exception:
            pass
    # Houses and workplaces.
    houses = []
    for v in getattr(g, "visible_villages", ()) or ():
        houses.extend(getattr(v, "houses", ()) or ())
    houses.extend(getattr(g, "built_houses", ()) or ())
    for h in houses:
        if math.hypot(float(h.x) - ex, float(h.y) - ey) > lim:
            continue
        img = getattr(h, "image", None)
        if img is None:
            continue
        out.append((img, float(h.x), float(h.y), float(img.get_height()),
                    img.get_width() / 2.0, float(img.get_height()), ""))
    for wp in list(getattr(g, "placed_work", ()) or ()):
        if math.hypot(float(wp.x) - ex, float(wp.y) - ey) > lim:
            continue
        img = getattr(wp, "image", None)
        if img is None:
            continue
        out.append((img, float(wp.x), float(wp.y), float(img.get_height()),
                    img.get_width() / 2.0, float(img.get_height()), ""))
    return out


def draw(g) -> None:
    """Draw the internal 3D frame and scale it to the window."""
    screen = g.screen
    w, h = screen.get_size()
    sampler = getattr(g, "_v3_sampler", None)
    if sampler is None:
        sampler = g._v3_sampler = _GroundSampler()
    sampler.ensure(g, float(getattr(g, "now", 0.0)))
    frame = _ground_frame(g, sampler)

    fwd, right, up = _cam(g)
    ex, ey = float(g.player.x), float(g.player.y)
    yaw = float(getattr(g, "v3d_yaw", 0.0))
    cards = _collect(g, yaw)

    drawables = []
    for img, wx, wy, wh, ax, ay, label in cards:
        base = _project(fwd, right, up, ex, ey, wx, wy, 0.0)
        top = _project(fwd, right, up, ex, ey, wx, wy, wh)
        if base is None or top is None:
            continue
        bx, by, cz = base
        _tx, ty, _tz = top
        if cz > DRAW_DIST:
            continue
        sh = abs(by - ty)
        if sh < 1.0:
            continue
        sh = min(sh, MAX_SPRITE_PX)
        scale = sh / float(max(1, img.get_height()))
        dw = max(1, int(round(img.get_width() * scale)))
        dh = max(1, int(round(img.get_height() * scale)))
        if bx < -dw or bx > IW + dw or by < -dh or by > IH + 64:
            continue
        drawables.append((cz, img, bx, by, dw, dh, ax * scale, ay * scale, label))

    # Painter's order: far first.  No z-buffer, but at this scale a simple
    # depth sort is enough and keeps the first pass understandable.
    drawables.sort(key=lambda d: d[0], reverse=True)
    for cz, img, bx, by, dw, dh, ax, ay, label in drawables:
        try:
            pic = pygame.transform.scale(img, (dw, dh))
            frame.blit(pic, (int(bx - ax), int(by - ay)))
        except Exception:
            pass

    # A little vignette makes the flat plane read as a view rather than a
    # diagram, and softens the edges at close range.
    try:
        shade = pygame.Surface((IW, IH), pygame.SRCALPHA)
        pygame.draw.rect(shade, (0, 0, 0, 0), (0, 0, IW, IH))
        for i in range(18):
            a = int(5 + i * 2.2)
            pygame.draw.rect(shade, (0, 0, 0, a), (i, i, IW - 2 * i, IH - 2 * i), 1)
        frame.blit(shade, (0, 0))
    except Exception:
        pass

    pygame.transform.scale(frame, (w, h), screen)
    _shot = os.environ.get("KINGPIN_V3_SHOT")
    if _shot:
        g._v3_frames = int(getattr(g, "_v3_frames", 0)) + 1
        if g._v3_frames == 45:
            try:
                pygame.image.save(screen, _shot)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# HUD and panels
# ---------------------------------------------------------------------------
def _crosshair(screen) -> None:
    cx, cy = screen.get_width() // 2, screen.get_height() // 2
    col = (238, 238, 238)
    pygame.draw.circle(screen, col, (cx, cy), 5, 1)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(screen, col, (cx + dx * 10, cy + dy * 10),
                         (cx + dx * 4, cy + dy * 4), 1)


def _draw_toast(g, screen) -> None:
    if getattr(g, "toast_time", 0.0) <= 0.0:
        return
    try:
        g.toast_time = max(0.0, g.toast_time - g.dt)
        fade = min(1.0, g.toast_time / 0.5)
        label = g.font.render(g.toast_text, True, (240, 226, 172))
        label.set_alpha(int(255 * fade))
        plate = pygame.Surface((label.get_width() + 22, 26), pygame.SRCALPHA)
        pygame.draw.rect(plate, (18, 18, 22, 200), plate.get_rect(), border_radius=6)
        plate.set_alpha(int(255 * fade))
        x = g.vw // 2 - label.get_width() // 2
        screen.blit(plate, (x - 11, int(g.vh * 0.68) - 3))
        screen.blit(label, (x, int(g.vh * 0.68)))
    except Exception:
        pass


def _viewmodel(g, screen) -> None:
    """The held thing, first-person: a readable weapon/tool card at the edge."""
    stack = getattr(g, "inventory", None).selected_stack() if getattr(g, "inventory", None) else None
    if stack is None:
        return
    try:
        size = 150
        icon = items.icon_for(stack, size)
        p = g.player
        now = pygame.time.get_ticks() / 1000.0
        moving = bool(getattr(p, "moving", False))
        bob_x = math.sin(now * 8.0) * (3.0 if moving else 1.2)
        bob_y = abs(math.cos(now * 8.0)) * (4.0 if moving else 1.5)
        swing = float(getattr(p, "swing_progress", 0.0) or 0.0)
        # Swing down and inward, then recover.  It is a card, not a rig yet,
        # but the motion is the same motion the top-down hand uses.
        swing_x = -74.0 * math.sin(swing * math.pi)
        swing_y = 116.0 * math.sin(swing * math.pi)
        reloading = float(getattr(p, "reloading", 0.0) or 0.0)
        if reloading > 0.0:
            bob_y += 10.0
        if stack.defn.id in ("axe", "pickaxe", "shovel"):
            icon = pygame.transform.rotate(icon, -18.0 + 96.0 * swing)
        # A hand behind the card, so the object reads as held.
        hx = screen.get_width() - 150 + bob_x + swing_x
        hy = screen.get_height() - 80 + bob_y + swing_y
        pygame.draw.ellipse(screen, (126, 86, 54),
                            (int(hx) - 28, int(hy) + 24, 56, 30))
        pygame.draw.ellipse(screen, (74, 48, 30),
                            (int(hx) - 28, int(hy) + 24, 56, 30), 2)
        screen.blit(icon, icon.get_rect(center=(int(hx), int(hy))))
    except Exception:
        pass


def draw_hud(g) -> None:
    screen = g.screen
    if not getattr(g, "hud_hidden", False) and not getattr(g.player, "dead", False):
        _viewmodel(g, screen)
    if not getattr(g, "hud_hidden", False) and not getattr(g.player, "dead", False):
        try:
            g.damage = 1.0 - g.player.health / g.player.max_health
            g.vignette.draw(screen, g.damage, g.now,
                            getattr(g.player, "hit_flash", 0.0) / 0.15)
        except Exception:
            pass
    if not getattr(g, "hud_hidden", False):
        _crosshair(screen)
        try:
            g.hotbar.draw(screen)
            g.hotbar.draw_stamina(screen, g.player.stamina / g.player.max_stamina,
                                  getattr(g.player, "exhausted", False))
            g.hotbar.draw_hunger(screen, g.player.hunger / g.player.max_hunger)
        except Exception:
            pass
        try:
            font = g.font
            txt = font.render("[V] top-down", True, (220, 216, 198))
            screen.blit(txt, (g.vw - txt.get_width() - 16, g.vh - 28))
        except Exception:
            pass
    _draw_toast(g, screen)

    # The existing panels are screen-space; keep them as they are.
    try:
        if getattr(g, "dialogue_panel", None) is not None and g.dialogue_panel.open_:
            g.dialogue_panel.draw(screen)
    except Exception:
        pass
    for attr, draw_name in (
        ("inventory_open", "panel"),
        ("build_menu_open", "build_menu"),
        ("chest_open", "chest_panel"),
        ("trade_open", "trade_menu"),
        ("workshop_open", "workshop_menu"),
        ("pause_open", "pause_menu"),
        ("research_open", "research_panel"),
        ("market_open", "market_panel"),
        ("board_open", "board_panel"),
        ("horse_panel_open", "horse_panel"),
    ):
        if not getattr(g, attr, False):
            continue
        obj = getattr(g, draw_name, None)
        if obj is None:
            continue
        try:
            if draw_name == "board_panel":
                obj.player = g.player
                obj.town_api = getattr(g, "_BOARD_API", None)
                obj.inv = g.inventory
                obj.chest = None
                obj.tax_day = int(getattr(g, "now", 0.0) / 600.0)
                obj.draw(screen, getattr(g, "board_village", None))
            else:
                obj.draw(screen)
        except Exception:
            pass
    try:
        if getattr(g, "map_open", False):
            import map as mapmod
            mapmod.draw(screen, g.world, g.player, g._nearest_town(),
                        g.hub_world.hubs,
                        settlements=list(g.villages.villages),
                        natives=list(getattr(g, "native_settlements", {}).values()),
                        ship=(g.ship_pos() if hasattr(g, "ship_pos") else None))
    except Exception:
        pass
    try:
        g.draw_persona_card()
    except Exception:
        pass
