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
import mesh3d

# Internal frame.  The window is filled by scaling this up, so the first
# version pays for a small ray/raster frame rather than 1280x720 ones.
IW, IH = 280, 158
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
    "research_open", "sign_open", "stall_open", "body_open", "folder_open",
    "gunsmith_open", "smith_panel_open", "barracks_open", "compass_open",
    "game_over",
)


def _blocked(g) -> bool:
    return any(bool(getattr(g, name, False)) for name in _BLOCKERS) \
        or getattr(g, "inside_house", None) is not None \
        or getattr(g, "inside_mine", None) is not None \
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


def _update_shots(g, dt: float) -> None:
    shots = getattr(g, "_v3_shots", None)
    if isinstance(shots, list) and shots:
        keep = []
        for s in shots:
            s["prev"] = (s["x"], s["y"], s["z"])
            try:
                if _advance_shot(g, s, dt):
                    continue
            except Exception:
                continue
            keep.append(s)
        g._v3_shots = keep
    flashes = getattr(g, "_v3_flashes", None)
    if isinstance(flashes, list) and flashes:
        for f in flashes:
            f[3] = float(f[3]) - dt
        g._v3_flashes = [f for f in flashes if f[3] > 0.0]
    # A bow charges while the button is held; release looses the arrow.
    try:
        stack = g.inventory.selected_stack()
        bow = stack is not None and stack.defn.id == "bow"
    except Exception:
        bow = False
    if getattr(g, "_v3_bow_charging", False):
        if not bow:
            g._v3_bow_charging = False
            g._v3_bow_charge = 0.0
        elif pygame.mouse.get_pressed()[0]:
            g._v3_bow_charge = min(1.1, float(getattr(g, "_v3_bow_charge", 0.0)) + dt)
        else:
            power = min(1.0, float(getattr(g, "_v3_bow_charge", 0.0)) / 1.1)
            g._v3_bow_charging = False
            g._v3_bow_charge = 0.0
            if power > 0.12:
                _fire3d(g, arrow=True, power=power)


def _draw_shots(g, frame) -> None:
    fwd, right, up = _cam(g)
    ex, ey = float(g.player.x), float(g.player.y)
    for s in getattr(g, "_v3_shots", ()) or ():
        try:
            p0 = _project(fwd, right, up, ex, ey,
                          float(s["prev"][0]), float(s["prev"][1]), float(s["prev"][2]))
            p1 = _project(fwd, right, up, ex, ey,
                          float(s["x"]), float(s["y"]), float(s["z"]))
            if p0 is None or p1 is None:
                continue
            x0, y0, _z0 = p0
            x1, y1, _z1 = p1
            if s.get("arrow"):
                pygame.draw.line(frame, (218, 206, 178), (x0, y0), (x1, y1), 2)
                dx, dy = x1 - x0, y1 - y0
                n = math.hypot(dx, dy) or 1.0
                dx, dy = dx / n, dy / n
                px, py = -dy, dx
                pygame.draw.polygon(frame, (236, 236, 226),
                                    [(x1, y1),
                                     (x1 - dx * 7 + px * 3, y1 - dy * 7 + py * 3),
                                     (x1 - dx * 7 - px * 3, y1 - dy * 7 - py * 3)])
                # fletching at the tail, so it reads as an arrow even in flight
                tx, ty = x0 - dx * 4, y0 - dy * 4
                pygame.draw.line(frame, (226, 218, 196),
                                 (tx, ty), (tx - dx * 6 + px * 4, ty - dy * 6 + py * 4), 2)
                pygame.draw.line(frame, (226, 218, 196),
                                 (tx, ty), (tx - dx * 6 - px * 4, ty - dy * 6 - py * 4), 2)
            else:
                pygame.draw.line(frame, (255, 214, 104), (x0, y0), (x1, y1), 3)
                pygame.draw.line(frame, (255, 250, 208), (x0, y0), (x1, y1), 1)
        except Exception:
            pass
    for x, y, z, ttl, _arrow in getattr(g, "_v3_flashes", ()) or ():
        p = _project(fwd, right, up, ex, ey, float(x), float(y), float(z))
        if p is None:
            continue
        sx, sy, _ = p
        k = max(0.0, min(1.0, float(ttl) / 0.08))
        rad = int(4 + 13 * k)
        pygame.draw.circle(frame, (255, 226, 124), (int(sx), int(sy)), rad)
        pygame.draw.circle(frame, (255, 250, 220), (int(sx), int(sy)), max(1, rad // 2))


def tick(g, dt: float) -> None:
    """Mouse look.  Called once at the top of the frame, before movement."""
    if not active(g):
        _release_mouse(g)
        return
    _grab_mouse(g)
    try:
        _update_shots(g, dt)
    except Exception:
        pass
    dx, dy = pygame.mouse.get_rel()
    if dx or dy:
        g.v3d_yaw = (float(getattr(g, "v3d_yaw", 0.0)) + dx * 0.0032) % (2.0 * math.pi)
        p = float(getattr(g, "v3d_pitch", 0.0)) - dy * 0.0028
        g.v3d_pitch = max(-1.15, min(1.15, p))
    # Right-click cancels a placement/designation; otherwise right-click still
    # aims a gun.
    try:
        if getattr(g, "placing", None) is not None and pygame.mouse.get_pressed()[2]:
            g.placing = None
            try:
                g.plot_start[0] = None
            except Exception:
                pass
        if getattr(g, "field_design", False) and pygame.mouse.get_pressed()[2]:
            g.field_design = False
            g.field_start[0] = None
    except Exception:
        pass
    # RIGHT-CLICK AIM.  A gun is pulled from the hip into the sight line while
    # the button is held; releasing it eases back.  The actual shot still uses
    # the camera yaw/pitch, so the 3D barrel and the crosshair agree.
    try:
        stack = g.inventory.selected_stack()
        kind = stack.defn.id if stack is not None else ""
        pressed = pygame.mouse.get_pressed()
        want = bool(kind in _GUN_IDS and len(pressed) > 2 and pressed[2])
        aim = float(getattr(g, "_v3_gun_aim", 0.0) or 0.0)
        if want:
            aim = min(1.0, aim + dt * 6.8)
        else:
            aim = max(0.0, aim - dt * 10.0)
        g._v3_gun_aiming = want
        g._v3_gun_aim = aim
    except Exception:
        pass


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

    N = 56
    SPAN = 3600.0

    def __init__(self) -> None:
        self.grid = None
        self.cx = 0.0
        self.cy = 0.0
        self.t = -1e9
        self._coarse = {}

    def ensure(self, g, now: float) -> None:
        px, py = float(g.player.x), float(g.player.y)
        if (self.grid is not None
                and math.hypot(px - self.cx, py - self.cy) < self.SPAN * 0.18
                and now - self.t < 1.25):
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
                col = self._coarse.get((cx, cy))
                if col is None:
                    col = g.ground._coarse_color(cx, cy)
                    self._coarse[(cx, cy)] = col
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


def _ground_frame(g) -> pygame.Surface:
    """Sky above the horizon and a flat distant ground base below it.

    The actual near ground is block geometry in mesh3d.  This function is only
    the backdrop: no screen-space tile sampling, so it cannot disagree with
    the block grid when the camera turns.
    """
    night = bool(getattr(g, "night", False))
    sky_top, sky_bottom = _sky_colours(g)
    try:
        cx = int(float(g.player.x) // 256)
        cy = int(float(g.player.y) // 256)
        base = g.ground._coarse_color(cx, cy)
    except Exception:
        base = (70, 104, 58)
    if night:
        base = tuple(int(v * 0.58) for v in base)
    ground_near = tuple(int(v * 0.76) for v in base)
    arr = np.empty((IW, IH, 3), dtype=np.uint8)
    yy = np.arange(IH, dtype=np.float32)
    pitch = float(getattr(g, "v3d_pitch", 0.0))
    horizon = IH * 0.5 + FOCAL * math.tan(pitch)
    horizon = max(-IH, min(IH * 2.0, horizon))
    grad = np.clip(yy / float(max(1, IH - 1)), 0.0, 1.0)
    sky = (np.array(sky_top, np.float32) * (1.0 - grad)[:, None]
           + np.array(sky_bottom, np.float32) * grad[:, None])
    # Below the horizon: a dark, foggy distant ground colour.  The block
    # grid covers the near field; this is just what shows at the edge.
    fog = np.clip((yy - horizon) / max(1.0, IH - horizon), 0.0, 1.0)[:, None]
    grd = (np.array(sky_bottom, np.float32) * (1.0 - fog)
           + np.array(ground_near, np.float32) * fog)
    mask = (yy >= horizon)[:, None]
    colors = np.where(mask, grd, sky)
    arr[:] = np.clip(colors[None, :, :], 0, 255).astype(np.uint8)
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
    wear = str(getattr(npc, "wear", "normal") or "normal")
    mayor = bool(getattr(npc, "is_mayor", False))
    king = bool(getattr(npc, "is_king", False))
    flash = float(getattr(npc, "hit_flash", 0.0)) > 0.0
    mood = "normal" if back else _npc_mood(npc)
    try:
        vet = face.vet_tier(getattr(npc.skills, "axe", 0.0),
                            getattr(npc.skills, "shooting", 0.0))
    except Exception:
        vet = 0
    swing = float(getattr(npc, "swing_anim", 0.0))
    swing_bucket = int(max(0.0, min(1.0, 1.0 - swing / 0.45)) * 8.0) if swing > 0.0 else -1
    key = (clothing, skin, armor, stalin, wear, mayor, king, bool(back),
           mood, vet, flash, swing_bucket)
    got = _NPC_CACHE.get(key)
    if got is not None:
        return got

    # A tall card so the swing can actually leave the shoulder.  The body is
    # not a separate overlay: the arm is part of this figure.
    w, h = 100, 140
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
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
    pygame.draw.rect(s, (44, 38, 32), (cx - 13, 102, 9, 34), border_radius=3)
    pygame.draw.rect(s, (44, 38, 32), (cx + 4, 102, 9, 34), border_radius=3)
    # torso
    pygame.draw.ellipse(s, body, (cx - 20, 62, 40, 56))
    pygame.draw.ellipse(s, (30, 26, 22), (cx - 20, 62, 40, 56), 2)
    if armor:
        col = (70, 46, 28) if armor == "hide" else (64, 68, 76)
        pygame.draw.line(s, col, (cx - 17, 78), (cx + 17, 78), 4)
        pygame.draw.line(s, (min(255, col[0] + 18), min(255, col[1] + 12),
                             min(255, col[2] + 8)),
                         (cx - 16, 89), (cx + 16, 89), 2)
    # left arm always; right arm only when not swinging
    pygame.draw.line(s, body, (cx - 18, 74), (cx - 26, 102), 9)
    if swing_bucket < 0:
        pygame.draw.line(s, body, (cx + 18, 74), (cx + 26, 102), 9)
    # head
    if not back:
        try:
            face.hair(s, cx, 45, 15)
        except Exception:
            pass
    pygame.draw.circle(s, skin, (cx, 45), 15)
    pygame.draw.circle(s, (150, 108, 78), (cx, 45), 15, 2)
    if back or stalin:
        pygame.draw.arc(s, (34, 26, 20), (cx - 15, 30, 30, 28), 0.15, math.pi - 0.15, 4)
    if not back:
        try:
            face.draw(s, cx, 45, 13, 0.0, 1.0, mood, skin, vet)
        except Exception:
            pygame.draw.circle(s, (46, 34, 28), (cx - 5, 43), 2)
            pygame.draw.circle(s, (46, 34, 28), (cx + 5, 43), 2)
        try:
            # The same local dress the 2D figure carries: snow fur bands,
            # desert sombreros, the mayor's top hat, the king's crown, iron
            # helmets, feathers and war paint.
            if getattr(npc, "iron_helmet", False) or getattr(npc, "iron_armor", False):
                face.iron_helmet(s, cx, 45, 15)
            face.feather(s, cx, 45, 15)
            if wear == "fur":
                face.headband(s, cx, 45, 15)
            elif wear == "tuareg":
                face.sombrero(s, cx, 45, 15)
            if (getattr(npc, "kind", "") in ("soldier", "warrior")
                    or getattr(npc, "hide_armor", False)
                    or getattr(npc, "iron_armor", False)):
                face.war_paint(s, cx, 45, 15)
            if mayor:
                face.tophat(s, cx, 45, 15)
            if king:
                face.crown(s, cx, 45, 15)
            if stalin:
                face.moustache(s, cx, 45, 15)
        except Exception:
            pass
    # THE SWING IS HIS OWN RIGHT ARM.  Shoulder, hand and weapon are one
    # connected figure, not a third arm floating beside the body.
    if (not back) and swing_bucket >= 0:
        p = swing_bucket / 8.0
        ang = math.radians(-150.0 + 290.0 * p)
        shoulder = (cx + 18, 74)
        hand = (shoulder[0] + math.cos(ang) * 34.0,
                shoulder[1] + math.sin(ang) * 34.0)
        pygame.draw.line(s, body, shoulder, hand, 12)
        pygame.draw.circle(s, body, shoulder, 7)
        pygame.draw.circle(s, skin, (int(hand[0]), int(hand[1])), 7)
        hx, hy = shoulder[0] + math.cos(ang) * 62.0, shoulder[1] + math.sin(ang) * 62.0
        pygame.draw.line(s, (110, 72, 40), hand, (hx, hy), 7)
        px, py = -math.sin(ang), math.cos(ang)
        blade = [(hx - px * 12, hy - py * 12),
                 (hx + px * 12, hy + py * 12),
                 (hx + math.cos(ang) * 18 - px * 8,
                  hy + math.sin(ang) * 18 - py * 8),
                 (hx + math.cos(ang) * 18 + px * 8,
                  hy + math.sin(ang) * 18 + py * 8)]
        pygame.draw.polygon(s, (205, 211, 220), blade)
        pygame.draw.polygon(s, (245, 246, 250), blade, 2)
        for i in range(1, 7):
            a = ang - i * 0.13
            tx = shoulder[0] + math.cos(a) * 52.0
            ty = shoulder[1] + math.sin(a) * 52.0
            pygame.draw.line(s, (238, 226, 170, max(6, 38 - i * 5)),
                             (shoulder[0], shoulder[1]),
                             (int(tx), int(ty)), 1)
    _NPC_CACHE[key] = s
    return s


def _animal_sprite(e, yaw: float, force_front: bool = False):
    kind = getattr(e, "kind", "")
    fx, fy = getattr(e, "facing", (0.0, 1.0))
    if abs(fx) + abs(fy) < 0.01:
        fx, fy = 0.0, 1.0
    # EIGHT PRE-RENDERED VIEWS, BILLBOARD-CORRECTED.
    # The art is authored in screen directions (2 = toward the viewer,
    # 6 = away).  Convert the animal's world facing into that space instead
    # of using the raw top-down direction.
    rel = math.atan2(fy, fx) - yaw
    d = int(round(rel / (math.pi / 4.0) + 6.0)) % 8
    if force_front:
        d = 2
    hit = float(getattr(e, "hit_flash", 0.0)) > 0.0
    try:
        if kind == "wolf":
            import wolfart
            species = getattr(e, "species", "wolf")
            if species not in ("white_wolf", "hyena"):
                species = "wolf"
            img = wolfart.frame(species, d, 0, 0.92, hit=hit,
                                lunge=bool(getattr(e, "lunging", 0.0)))
            return img, wolfart.AX, wolfart.AY, float(img.get_height()) * 1.38
        if kind == "rabbit":
            import rabbitart
            img = rabbitart.frame(getattr(e, "fur", "brown"), d, 0, 0.92, hit=hit)
            return img, rabbitart.AX, rabbitart.AY, float(img.get_height()) * 1.18
        if kind == "horse":
            import horseart
            zoom = 0.64 if getattr(e, "baby", False) else 0.90
            img = horseart.frame(getattr(e, "coat", "brown"), d, 0, zoom, hit=hit)
            return img, horseart.AX, horseart.AY, float(img.get_height()) * 1.28
        if kind == "bison":
            import bisonart
            zoom = 0.64 if getattr(e, "baby", False) else 1.0
            img = bisonart.frame(d, 0, zoom, hit=hit,
                                 charge=bool(getattr(e, "aggro", False)),
                                 baby=bool(getattr(e, "baby", False)))
            return img, bisonart.AX, bisonart.AY, float(img.get_height()) * 1.30
    except Exception:
        pass
    # Soldiers and other simple enemies: use their existing top-down art on a
    # transparent card.  This is a placeholder, not the final sprite system.
    s = pygame.Surface((72, 88), pygame.SRCALPHA)
    try:
        e.draw(s, float(e.x) - 36.0, float(e.y) - 70.0)
    except Exception:
        pass
    return s, 36.0, 84.0, 98.0


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


def _eye_xy(g, update: bool = True):
    """A softly followed eye position for rendering.

    Simulation position is authoritative, but drawing every simulation step
    directly made running and horse riding visibly step and hitch whenever a
    frame took longer than the last.  The camera eases toward the player on
    the horizontal plane; teleports and large corrections snap immediately.
    """
    px, py = float(g.player.x), float(g.player.y)
    cx = getattr(g, "_v3_cam_x", None)
    cy = getattr(g, "_v3_cam_y", None)
    if cx is None or cy is None:
        cx, cy = px, py
    elif math.hypot(px - cx, py - cy) > 180.0:
        cx, cy = px, py
    elif update:
        dt = max(0.0, min(0.075, float(getattr(g, "dt", 0.016))))
        # Fast enough not to feel like lag, slow enough to absorb frame-time
        # variation.  Riding gets a little more response than walking.
        rate = 34.0 if getattr(g, "riding", None) is not None else 28.0
        a = 1.0 - math.exp(-rate * dt)
        cx += (px - cx) * a
        cy += (py - cy) * a
        if abs(px - cx) + abs(py - cy) < 0.04:
            cx, cy = px, py
    if update:
        g._v3_cam_x, g._v3_cam_y = cx, cy
    return cx, cy


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
    """Return actor billboards only; the world above ground is mesh3d now."""
    out = []
    ex, ey = float(g.player.x), float(g.player.y)
    lim = DRAW_DIST
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
        tfx, tfy = ex - float(npc.x), ey - float(npc.y)
        ffx, ffy = getattr(npc, "facing", (0.0, 1.0))
        front = (ffx * tfx + ffy * tfy) >= -0.01
        swinging = float(getattr(npc, "swing_anim", 0.0)) > 0.0
        card = _npc_sprite(npc, back=(not front) and not swinging)
        out.append((card, float(npc.x), float(npc.y), 82.0, 50.0, 138.0,
                    getattr(npc, "name", "")))
    for e in list(getattr(g, "enemies", ()) or ()):
        if not getattr(e, "alive", True):
            continue
        if math.hypot(float(e.x) - ex, float(e.y) - ey) > lim:
            continue
        _atk = (float(getattr(e, "attack_flash", 0.0)) > 0.0
                or float(getattr(e, "lunging", 0.0)) > 0.0
                or bool(getattr(e, "aggro", False)))
        card, ax, ay, wh = _animal_sprite(e, yaw, force_front=_atk)
        out.append((card, float(e.x), float(e.y), wh, ax, ay, ""))
    for e in list(getattr(g, "rabbits", ()) or ()):
        if math.hypot(float(e.x) - ex, float(e.y) - ey) > lim:
            continue
        card, ax, ay, wh = _animal_sprite(e, yaw)
        out.append((card, float(e.x), float(e.y), wh, ax, ay, ""))
    for e in list(getattr(g, "horses", ()) or ()):
        if math.hypot(float(e.x) - ex, float(e.y) - ey) > lim:
            continue
        card, ax, ay, wh = _animal_sprite(e, yaw)
        out.append((card, float(e.x), float(e.y), wh, ax, ay, ""))
    return out

def _candidate_people(g):
    seen = set()
    out = []
    pools = []
    try:
        import village
        pools.append(getattr(village, "PEOPLE", ()))
    except Exception:
        pass
    for v in getattr(g, "visible_villages", ()) or ():
        pools.append(getattr(v, "npcs", ()))
    pools.append(getattr(g, "_native_people", ()) or ())
    try:
        pools.append([g._TRUTH[0]] if g._TRUTH[0] is not None else [])
    except Exception:
        pass
    for pool in pools:
        for n in pool or ():
            if n is None or id(n) in seen:
                continue
            seen.add(id(n))
            if not getattr(n, "alive", True) or getattr(n, "in_interior", False):
                continue
            out.append(n)
    return out


def _aim_npc(g):
    fwd, right, up = _cam(g)
    ex, ey = float(g.player.x), float(g.player.y)
    best = None
    best_score = 1e9
    for n in _candidate_people(g):
        d = math.hypot(float(n.x) - ex, float(n.y) - ey)
        if d > 170.0:
            continue
        p = _project(fwd, right, up, ex, ey, float(n.x), float(n.y), 55.0)
        if p is None:
            continue
        sx, sy, _cz = p
        off = math.hypot(sx - IW * 0.5, sy - IH * 0.5)
        if off > 105.0:
            continue
        score = d + off * 0.7
        if score < best_score:
            best, best_score = n, score
    return best


def _aim_tile(g):
    fwd, _right, _up = _cam(g)
    if fwd[2] >= -1e-4:
        return None
    t = -EYE_Z / fwd[2]
    wx = float(g.player.x) + fwd[0] * t
    wy = float(g.player.y) + fwd[1] * t
    if math.hypot(wx - float(g.player.x), wy - float(g.player.y)) > 240.0:
        return None
    return int(wx // 32), int(wy // 32)


_GUN_IDS = ("musket", "double_shot", "rifle", "shotgun")


def _billboard_hit_dims(g, e, base_radius: float, base_height: float):
    """Match the thing that is actually drawn, not an old body-sized guess.

    Animal cards are deliberately larger than their old top-down bodies, and
    the rabbit is the clearest case: a 64-unit-tall billboard was being shot
    at with a 26-unit-tall hit cylinder, so an aimed shot could pass cleanly
    over its head and land behind it.  Read the same sprite dimensions the
    renderer uses and turn them into a capsule around the target.
    """
    try:
        yaw = float(getattr(g, "v3d_yaw", 0.0))
        card, _ax, _ay, world_h = _animal_sprite(e, yaw)
        world_w = (float(world_h) * float(card.get_width())
                   / max(1.0, float(card.get_height())))
        radius = max(float(base_radius), world_w * 0.48)
        height = max(float(base_height), float(world_h))
        return radius, height
    except Exception:
        return float(base_radius), float(base_height)



def _screen_target_under_crosshair(g):
    """Find the visible billboard the crosshair is actually on.

    This is the final guard against a pure world-space ray disagreeing with a
    camera-facing billboard: the sprite the player can see is a rectangle on
    the screen, so use that same rectangle.  The returned target and vertical
    aim point let a fired shot go through the visible body rather than just
    past its old, much smaller world-space capsule.
    """
    try:
        fwd, right, up = _cam(g)
        ex, ey = _eye_xy(g, update=False)
        cx, cy = IW * 0.5, IH * 0.5
        best = None
        best_d = 1e18

        def consider(e, card, ax, ay, world_h):
            nonlocal best, best_d
            base = _project(fwd, right, up, ex, ey, float(e.x), float(e.y), 0.0)
            top = _project(fwd, right, up, ex, ey, float(e.x), float(e.y), float(world_h))
            if base is None or top is None:
                return
            sh = abs(float(base[1]) - float(top[1]))
            if sh < 2.0:
                return
            scale = sh / max(1.0, float(card.get_height()))
            dw = float(card.get_width()) * scale
            dh = float(card.get_height()) * scale
            x0 = float(base[0]) - float(ax) * scale
            y0 = float(base[1]) - float(ay) * scale
            if x0 - 2.0 <= cx <= x0 + dw + 2.0 and y0 - 2.0 <= cy <= y0 + dh + 2.0:
                d = math.hypot(float(e.x) - ex, float(e.y) - ey)
                if d < best_d:
                    best_d = d
                    best = (e, float(world_h))

        for n in _candidate_people(g):
            # NPC cards are 100x140 with the feet anchor at 138.
            consider(n, pygame.Surface((100, 140), pygame.SRCALPHA),
                     50.0, 138.0, 82.0)
        for e in list(getattr(g, "enemies", ()) or ()):
            if not getattr(e, "alive", True):
                continue
            card, ax, ay, wh = _animal_sprite(e, float(getattr(g, "v3d_yaw", 0.0)))
            consider(e, card, ax, ay, wh)
        for e in list(getattr(g, "rabbits", ()) or ()):
            if getattr(e, "alive", True):
                card, ax, ay, wh = _animal_sprite(e, float(getattr(g, "v3d_yaw", 0.0)))
                consider(e, card, ax, ay, wh)
        for e in list(getattr(g, "horses", ()) or ()):
            if getattr(e, "alive", True):
                card, ax, ay, wh = _animal_sprite(e, float(getattr(g, "v3d_yaw", 0.0)))
                consider(e, card, ax, ay, wh)
        return best
    except Exception:
        return None


def _entity_hit_targets(g):
    targets = []
    for n in _candidate_people(g):
        # The NPC card is 100x140; use a matching capsule rather than the
        # old 17x78 torso-sized box.
        targets.append((n, 30.0, 138.0))
    for e in list(getattr(g, "enemies", ()) or ()):
        if not getattr(e, "alive", True):
            continue
        kind = getattr(e, "kind", "")
        h = 82.0 if kind == "bison" else (58.0 if kind == "wolf" else 70.0)
        r = float(getattr(e, "radius", 12)) + 8.0
        r, h = _billboard_hit_dims(g, e, r, h)
        targets.append((e, r, h))
    for e in list(getattr(g, "rabbits", ()) or ()):
        if getattr(e, "alive", True):
            r, h = _billboard_hit_dims(g, e, 14.0, 54.0)
            targets.append((e, r, h))
    for e in list(getattr(g, "horses", ()) or ()):
        if getattr(e, "alive", True):
            r, h = _billboard_hit_dims(g, e, 18.0, 80.0)
            targets.append((e, r, h))
    return targets


def _segment_cylinder(x0, y0, z0, x1, y1, z1, tx, ty, radius, height):
    vx, vy = x1 - x0, y1 - y0
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        return None
    t = ((tx - x0) * vx + (ty - y0) * vy) / l2
    if t < 0.0 or t > 1.0:
        return None
    px, py = x0 + vx * t, y0 + vy * t
    if (px - tx) ** 2 + (py - ty) ** 2 > radius * radius:
        return None
    z = z0 + (z1 - z0) * t
    if z < 0.0 or z > height:
        return None
    return t


def _damage_shot_target(g, target, dmg, weapon):
    try:
        if getattr(target, "alive", True) is False or getattr(target, "dead", False):
            return
    except Exception:
        pass
    try:
        try:
            target.take_damage(max(1, int(round(dmg))), record=False,
                               attacker=g.player)
        except TypeError:
            target.take_damage(max(1, int(round(dmg))))
    except Exception:
        return
    try:
        g.combat.spawn_impact(float(target.x), float(target.y), (168, 44, 34))
        g.blood.spawn(float(target.x), float(target.y), 7, 14.0)
    except Exception:
        pass
    try:
        import itemstory
        itemstory.record(weapon, "killed", actor=g.player,
                         place="the field", now=getattr(g, "now", 0.0),
                         detail=getattr(target, "name", "someone"))
    except Exception:
        pass
    # NPCs remember who shot them.
    try:
        import economy as _ec
        _ec.wronged(target, g.player, 20.0, getattr(g, "now", 0.0))
    except Exception:
        pass


def _advance_shot(g, shot, dt):
    step = min(float(shot["speed"]) * dt,
               max(0.0, float(shot["max"]) - float(shot["travel"])))
    if step <= 0.0:
        return True
    x0, y0, z0 = shot["x"], shot["y"], shot["z"]
    x1 = x0 + shot["dx"] * step
    y1 = y0 + shot["dy"] * step
    z1 = z0 + shot["dz"] * step
    # Ground
    if z1 <= 0.8 and shot["dz"] < -1e-5:
        _t = (z0 - 0.8) / (z0 - z1)
        _t = max(0.0, min(1.0, _t))
        try:
            g.combat.spawn_impact(x0 + (x1 - x0) * _t,
                                  y0 + (y1 - y0) * _t, (132, 106, 72))
        except Exception:
            pass
        shot["x"], shot["y"], shot["z"] = x1, y1, 0.8
        return True
    best = None
    best_t = 2.0
    for target, radius, height in _entity_hit_targets(g):
        t = _segment_cylinder(x0, y0, z0, x1, y1, z1,
                              float(target.x), float(target.y), radius, height)
        if t is not None and t < best_t:
            best, best_t = target, t
    if best is not None:
        _damage_shot_target(g, best, shot["dmg"], shot["weapon"])
        shot["x"], shot["y"], shot["z"] = x1, y1, z1
        return True
    shot["x"], shot["y"], shot["z"] = x1, y1, z1
    shot["travel"] = float(shot["travel"]) + step
    return shot["travel"] >= float(shot["max"])


def _fire3d(g, arrow=False, power=1.0) -> bool:
    try:
        stack = g.inventory.selected_stack()
    except Exception:
        stack = None
    if stack is None:
        return False
    kind = stack.defn.id
    p = g.player
    if arrow and kind != "bow":
        return False
    if not arrow and kind not in _GUN_IDS:
        return False
    try:
        if arrow:
            if p.gun_cd > 0.0:
                return False
            if g.inventory.count_of("arrow") <= 0:
                g.toast("No arrows")
                return False
            g.inventory.consume("arrow", 1)
            p.gun_cd = 0.8
            import guns
            speed, max_dist = 975.0, 2200.0
            import main as _m
            dmg = max(1.0, _m.MELEE_DAMAGE * g.skills.axe_damage_scale()
                      * (0.55 + 0.45 * max(0.0, min(1.0, power))))
        else:
            if p.reloading > 0.0 or p.gun_cd > 0.0:
                return False
            import guns
            if p.mags.get(kind, 0) <= 0:
                if g.inventory.count_of("ammo") <= 0:
                    g.toast("No ammo")
                    return False
                p.reload_kind = kind
                p.reload_total = guns.RELOAD_LO.get(kind, 5.0)
                p.reloading = p.reload_total
                g.toast("Reloading…")
                return True
            p.mags[kind] -= 1
            p.gun_cd = guns.FIRE_CD.get(kind, 0.4)
            speed, max_dist = 1800.0, 2600.0
            dmg = guns.DAMAGE[kind]
    except Exception as _e:
        try:
            import plog
            plog.log("VIEW3D-FIRE3D", repr(_e)[:180])
        except Exception:
            pass
        return False
    yaw = float(getattr(g, "v3d_yaw", 0.0))
    pitch = float(getattr(g, "v3d_pitch", 0.0))
    cp, sp = math.cos(pitch), math.sin(pitch)
    fwd = (math.cos(yaw) * cp, math.sin(yaw) * cp, sp)
    p.facing = (math.cos(yaw), math.sin(yaw))
    # A shot fired while the crosshair is visibly on a billboard should hit
    # that billboard, not merely pass near its old world-space capsule.  This
    # small correction is derived from the same projected rectangle the
    # renderer draws; with no target under the crosshair, the camera ray is
    # used unchanged.
    _ct = _screen_target_under_crosshair(g)
    if _ct is not None:
        _t, _th = _ct
        _tx, _ty, _tz = float(_t.x), float(_t.y), max(4.0, _th * 0.50)
        _ox = float(p.x) + fwd[0] * 26.0
        _oy = float(p.y) + fwd[1] * 26.0
        _oz = EYE_Z - 5.0 + fwd[2] * 26.0
        _dx, _dy, _dz = _tx - _ox, _ty - _oy, _tz - _oz
        _dn = math.sqrt(_dx * _dx + _dy * _dy + _dz * _dz)
        if _dn > 0.001:
            fwd = (_dx / _dn, _dy / _dn, _dz / _dn)
            try:
                import plog
                plog.log("V3-SHOT-AIM", "target", getattr(_t, "kind", "person"),
                         "d", round(_dn, 1), "z", round(_tz, 1))
            except Exception:
                pass
    ox = float(p.x) + fwd[0] * 26.0
    oy = float(p.y) + fwd[1] * 26.0
    oz = EYE_Z - 5.0 + fwd[2] * 26.0
    shots = getattr(g, "_v3_shots", None)
    if not isinstance(shots, list):
        shots = g._v3_shots = []
    shots.append({"x": ox, "y": oy, "z": oz,
                  "dx": fwd[0], "dy": fwd[1], "dz": fwd[2],
                  "speed": speed, "max": max_dist, "travel": 0.0,
                  "dmg": dmg, "arrow": bool(arrow), "weapon": stack,
                  "prev": (ox, oy, oz)})
    flashes = getattr(g, "_v3_flashes", None)
    if not isinstance(flashes, list):
        flashes = g._v3_flashes = []
    flashes.append([ox, oy, oz, 0.08, bool(arrow)])
    try:
        import sound
        sound.play("shot_bow" if arrow else
                   ("shot_rifle" if kind == "rifle" else "shot_musket"))
        g.skills.gain_shooting()
    except Exception:
        pass
    return True


def _open_npc_card(g, npc) -> bool:
    try:
        import work
        from ui import ChestPanel
        g.persona = npc
        g.npc_card_open = True
        g._wn = npc
        try:
            if g.worker_panel is not None:
                g.worker_panel.close()
        except Exception:
            pass
        g.worker_panel = ChestPanel(g.inventory, work.bag(npc), top_rows=4,
                                    top_label=getattr(npc, "name", "PACK"))
        g.worker_panel_open = True
        g.npc_tab = "inventory"
        pygame.mouse.set_visible(True)
        _release_mouse(g)
        try:
            import player_mind as _pm
            _pm.observe(g, "initiated")
        except Exception:
            pass
        return True
    except Exception:
        return False


def _field_click_from_crosshair(g) -> bool:
    """Choose field/orchard corners with the crosshair."""
    tile = _aim_tile(g)
    if tile is None:
        _toast(g, "Aim at the ground to designate")
        return True
    wx, wy = float(tile[0] * 32), float(tile[1] * 32)
    if not getattr(g, "field_start", None) or g.field_start[0] is None:
        g.field_start[0] = (wx, wy)
        g.field_raw[0] = (wx, wy)
        g.field_del[0] = False
        _toast(g, "First corner set")
        return True
    sx, sy = g.field_start[0]
    tx0, ty0 = int(sx // 32), int(sy // 32)
    tx1, ty1 = int(wx // 32), int(wy // 32)
    r = pygame.Rect(min(tx0, tx1) * 32, min(ty0, ty1) * 32,
                    (abs(tx0 - tx1) + 1) * 32,
                    (abs(ty0 - ty1) + 1) * 32)
    g.field_start[0] = None
    g.field_raw[0] = None
    try:
        if getattr(g, "field_mode", "") == "orchard":
            g.field_designations.append(
                {"rect": r, "type": "orchard", "kind": "orchard"})
            _toast(g, "Orchard designated  (%d x %d)" % (r.w, r.h))
        else:
            _t = g.world.temperature(r.centerx, r.centery)
            _h = g.world.humidity(r.centerx, r.centery)
            _kind = (g.first_field_kind(_t, _h, r.centerx, r.centery)
                     if getattr(g, "first_field_kind", None) else "wheat")
            g.field_designations.append(
                {"rect": r, "type": "field", "kind": _kind})
            _toast(g, "Field designated  (%d x %d)" % (r.w, r.h))
        if getattr(g, "sync_player_camp", None):
            g.sync_player_camp(g)
    except Exception:
        _toast(g, "Could not designate there")
    return True


def _place_from_crosshair(g) -> bool:
    """Turn the crosshair's ground tile into the build menu's placement point."""
    tile = _aim_tile(g)
    if tile is None:
        _toast(g, "Nothing in reach to build on")
        return True
    x, y = float(tile[0] * 32), float(tile[1] * 32)
    if getattr(g, "placing", None) == "demolish":
        try:
            _said = g.demolish_at(x + 16.0, y + 16.0)
            _toast(g, _said or "Nothing of yours there")
        except Exception:
            pass
        g.placing = None
        return True
    g._place_override = (x, y)
    try:
        g.try_place()
    except Exception as _pe:
        try:
            import plog
            plog.log("VIEW3D-PLACE", repr(_pe)[:180])
        except Exception:
            pass
        _toast(g, "Could not place there")
    finally:
        g._place_override = None
    return True


def interact(g) -> bool:
    """Crosshair click: axe attack, NPC card, or block placement."""
    try:
        stack = g.inventory.selected_stack()
    except Exception:
        stack = None
    held = stack.defn.id if stack is not None else ""
    if getattr(g, "placing", None) is not None:
        return _place_from_crosshair(g)
    if held == "bow":
        # Draw the bow while the button is held; release to loose the arrow.
        g._v3_bow_charging = True
        g._v3_bow_charge = 0.0
        return True
    if held in _GUN_IDS:
        _fire3d(g, arrow=False)
        return True
    # A HELD AXE IS A WEAPON, NOT A CONVERSATION.  Clicking a person swings
    # even if the crosshair happens to be on them.
    if held == "axe":
        # The event runs before the world tick; make the swing use the yaw
        # the crosshair is actually on, not last frame's facing.
        yaw = float(getattr(g, "v3d_yaw", 0.0))
        g.player.facing = (math.cos(yaw), math.sin(yaw))
        g.aim = g.player.facing
        # `on_click` normally passes a small proxy with these two names.
        # The 3D path calls use_axe on the real game object, where they live
        # under the private names.
        try:
            g.work_lanes = g._WORK
        except Exception:
            pass
        try:
            g.truth = g._TRUTH
        except Exception:
            pass
        try:
            import combat_actions
            combat_actions.use_axe(g, 0)
        except Exception as _atk:
            try:
                import plog
                plog.log("VIEW3D-AXE", repr(_atk)[:180])
            except Exception:
                pass
            try:
                g.player.start_swing()
            except Exception:
                pass
        return True
    npc = _aim_npc(g)
    if npc is not None:
        return _open_npc_card(g, npc)
    if stack is not None and held in ("pickaxe", "shovel"):
        try:
            g.work_lanes = g._WORK
        except Exception:
            pass
        try:
            g.truth = g._TRUTH
        except Exception:
            pass
        try:
            import combat_actions
            combat_actions.use_axe(g, 0)
        except Exception:
            pass
        return True
    if stack is not None:
        item_id = stack.defn.id
        try:
            import block
            if item_id in block.BUILDABLE:
                tile = _aim_tile(g)
                if tile is None:
                    _toast(g, "Nothing in reach to build on")
                    return True
                if block.place_block(g, tile[0], tile[1], item_id):
                    _toast(g, "Placed %s" % item_id.replace("_", " "))
                else:
                    _toast(g, "No room or none left")
                return True
        except Exception:
            pass
    return False


def _draw_placement_ghost(g, frame) -> None:
    """A green footprint under the crosshair while a build choice is armed."""
    if getattr(g, "placing", None) is None:
        return
    try:
        tile = _aim_tile(g)
        if tile is None:
            return
        wx, wy = tile[0] * 32.0, tile[1] * 32.0
        _facing, rect, _sight = g.placement_box(wx, wy)
        fwd, right, up = _cam(g)
        ex, ey = _eye_xy(g, update=False)

        def corner(x, y, z):
            return _project(fwd, right, up, ex, ey, x, y, z)

        for z, color in ((1.0, (150, 238, 126)), (26.0, (104, 190, 92))):
            pts = [corner(rect.left, rect.top, z),
                   corner(rect.right, rect.top, z),
                   corner(rect.right, rect.bottom, z),
                   corner(rect.left, rect.bottom, z)]
            if all(p is not None for p in pts):
                pygame.draw.lines(frame, color, True,
                                  [(int(p[0]), int(p[1])) for p in pts], 2)
        # corner posts make the footprint read as a volume, not a decal
        for x, y in ((rect.left, rect.top), (rect.right, rect.top),
                     (rect.right, rect.bottom), (rect.left, rect.bottom)):
            a, b = corner(x, y, 1.0), corner(x, y, 26.0)
            if a is not None and b is not None:
                pygame.draw.line(frame, (136, 220, 112),
                                 (int(a[0]), int(a[1])),
                                 (int(b[0]), int(b[1])), 1)
    except Exception:
        pass


def draw(g) -> None:
    """Draw the internal 3D frame and scale it to the window."""
    screen = g.screen
    w, h = screen.get_size()
    frame = _ground_frame(g)
    fwd, right, up = _cam(g)
    ex, ey = _eye_xy(g)
    yaw = float(getattr(g, "v3d_yaw", 0.0))
    scene = mesh3d.build_scene(g, fwd, right, up, ex, ey)
    for img, wx, wy, wh, ax, ay, label in _collect(g, yaw):
        scene.add_shadow(wx, wy, max(7.0, wh * 0.22))
        scene.add_sprite(img, wx, wy, wh, ax=ax, ay=ay)
    scene.draw(frame)
    try:
        _draw_shots(g, frame)
    except Exception:
        pass
    _draw_placement_ghost(g, frame)

    # A little vignette makes the flat plane read as a view rather than a
    # diagram, and softens the edges at close range.
    try:
        shade = pygame.Surface((IW, IH), pygame.SRCALPHA)
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
    try:
        mesh3d.draw_viewmodel(g, screen)
    except Exception:
        pass


def _draw_chop_bar(g, screen) -> None:
    """The player's swing recharge, shown while chopping wood.

    This is NOT progress through the tree's hit points.  It is the same
    cooldown the top-down action bar shows: after a swing the bar fills, and
    when it is full the player can strike again.
    """
    b = getattr(g, "chop_bar", None)
    if not isinstance(b, dict):
        return
    try:
        age = float(getattr(g, "now", 0.0)) - float(b.get("t", 0.0))
        if age < 0.0 or age > 4.0:
            return
        p = g.player
        cd = max(0.0, float(getattr(p, "swing_cd", 0.0)))
        total = max(0.001, float(getattr(p, "skill_axe_cd", 1.0)))
        prog = 1.0 - min(1.0, cd / total)
        ready = prog >= 0.999
        vw, vh = screen.get_width(), screen.get_height()
        bw = min(420, max(220, vw // 3))
        bh = 18
        x = (vw - bw) // 2
        y = int(vh * 0.80)
        fade = 1.0 if age < 2.8 else max(0.0, 1.0 - (age - 2.8) / 1.2)
        plate = pygame.Surface((bw + 26, 52), pygame.SRCALPHA)
        pygame.draw.rect(plate, (18, 18, 22, int(210 * fade)),
                         plate.get_rect(), border_radius=7)
        pygame.draw.rect(plate, (150, 112, 62, int(220 * fade)),
                         plate.get_rect(), 2, border_radius=7)
        try:
            label = "READY" if ready else "SWING"
            lab = g.font.render(label, True,
                                (196, 238, 166) if ready else (242, 222, 168))
            lab.set_alpha(int(255 * fade))
            plate.blit(lab, (13, 4))
        except Exception:
            pass
        bx, by = 12, 29
        pygame.draw.rect(plate, (42, 34, 26, int(230 * fade)),
                         (bx, by, bw, bh), border_radius=4)
        fill = int(round(bw * prog))
        if fill > 0:
            col = (124, 196, 106) if ready else (198, 112, 54)
            pygame.draw.rect(plate, (col[0], col[1], col[2], int(245 * fade)),
                             (bx, by, fill, bh), border_radius=4)
            pygame.draw.rect(plate, (250, 230, 150, int(245 * fade)),
                             (bx, by, fill, 3), border_radius=4)
        plate.set_alpha(int(255 * fade))
        screen.blit(plate, (x - 13, y - 3))
    except Exception:
        pass


_CHAT_FONT = None


def _draw_artisan_panel(g, screen) -> None:
    if not (getattr(g, "artisan_open", False)
            and getattr(g, "artisan_bench", None) is not None):
        return
    try:
        vw, vh = screen.get_size()
        w, h = 460, 240
        panel = pygame.Rect((vw - w) // 2, (vh - h) // 2, w, h)
        left = pygame.Rect(vw // 2 - 70, panel.y + 68, 26, 26)
        right = pygame.Rect(vw // 2 + 44, panel.y + 68, 26, 26)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (26, 26, 30), panel, border_radius=10)
        pygame.draw.rect(screen, (150, 118, 78), panel, 2, border_radius=10)
        font = getattr(g, "font", None) or pygame.font.SysFont("dejavusans", 18)
        title = font.render("ARTISAN'S BENCH", True, (238, 224, 190))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.top + 12))
        leaf = getattr(g.artisan_bench, "leaf", None)
        prod = getattr(g.artisan_bench, "product", None)
        makes = font.render("makes %s from %s" % (prod or "-", leaf or "-"),
                            True, (232, 200, 118))
        screen.blit(makes, (panel.centerx - makes.get_width() // 2, panel.top + 42))
        for rr in (left, right):
            pygame.draw.rect(screen, (70, 60, 44), rr, border_radius=4)
            pygame.draw.rect(screen, (150, 118, 78), rr, 1, border_radius=4)
        for rr, sym in ((left, "<"), (right, ">")):
            txt = font.render(sym, True, (226, 200, 150))
            screen.blit(txt, (rr.centerx - txt.get_width() // 2,
                              rr.centery - txt.get_height() // 2))
        art = getattr(g.artisan_bench, "artisan", None)
        who = getattr(art, "name", "no artisan assigned") if art is not None else "no artisan assigned"
        wtxt = font.render("artisan: %s" % who, True, (216, 212, 200))
        screen.blit(wtxt, (panel.centerx - wtxt.get_width() // 2, panel.top + 104))
        hint = font.render("takes 10 leaf from a chest, makes 10 goods      [E] close",
                           True, (196, 226, 168))
        screen.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 28))
    except Exception:
        pass


def _draw_smith_panel(g, screen) -> None:
    if not (getattr(g, "smith_open", False)
            and getattr(g, "smith_shop", None) is not None):
        return
    try:
        vw, vh = screen.get_size()
        worker = g.smith_shop.worker
        orders = list(getattr(worker, "tool_orders", ()) or ())
        panel = pygame.Rect(vw // 2 - 220, vh // 2 - 150, 440, 300)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (26, 26, 30), panel, border_radius=10)
        pygame.draw.rect(screen, (150, 118, 78), panel, 2, border_radius=10)
        font = getattr(g, "font", None) or pygame.font.SysFont("dejavusans", 18)
        titles = {"smith": "THE FORGE", "mine": "THE PIT HEAD",
                  "lab": "THE LABORATORY", "brewery": "THE BREWHOUSE"}
        head = titles.get(getattr(worker, "kind", "") if worker else "", "THE BENCH")
        village = getattr(worker, "village", None) if worker else None
        head += "   -   %s's" % (getattr(village, "name", "the village") if village else "the village")
        screen.blit(font.render(head, True, (238, 224, 190)), (panel.x + 14, panel.y + 12))
        screen.blit(font.render("iron in stock: %d"
                                % int(getattr(worker, "stock", {}).get("iron", 0)),
                                True, (232, 200, 118)), (panel.x + 14, panel.y + 38))
        yy = panel.y + 66
        if not orders:
            screen.blit(font.render("nothing booked", True, (150, 146, 138)),
                        (panel.x + 14, yy))
        for who, want in orders[:9]:
            screen.blit(font.render("%s wants a %s" % (getattr(who, "name", "someone"), want),
                                    True, (216, 212, 200)), (panel.x + 14, yy))
            yy += 22
        if worker is not None:
            held = {k: int(v) for k, v in getattr(worker, "stock", {}).items()
                    if k in ("axe", "shovel", "pickaxe") and v}
            if held:
                screen.blit(font.render("on the shelf: " + ", ".join(
                    "%d %s" % (q, i) for i, q in held.items()), True,
                    (200, 200, 190)), (panel.x + 14, panel.bottom - 44))
        kind = getattr(g.smith_shop, "kind", "")
        hint = {"smith": "[Space] forge a tool", "mine": "[Space] break out iron",
                "lab": "[Space] work the leaf",
                "brewery": ("[Space] draw the brew"
                            if getattr(g.player, "brew", None) is not None
                            else "[Space] start a mash")}.get(kind, "")
        screen.blit(font.render("%s      [E] close   " % hint, True, (196, 226, 168)),
                    (panel.x + 14, panel.bottom - 24))
        if getattr(g, "work_msg", ""):
            screen.blit(font.render(g.work_msg, True, (240, 206, 130)),
                        (panel.x + 14, panel.bottom - 46))
    except Exception:
        pass


def _draw_naming(g, screen) -> None:
    """The settlement-naming card, over the first-person view."""
    if not getattr(g, "naming_open", False):
        return
    try:
        vw, vh = screen.get_size()
        panel = pygame.Rect(vw // 2 - 230, vh // 2 - 80, 460, 160)
        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (26, 26, 30), panel, border_radius=10)
        pygame.draw.rect(screen, (150, 118, 78), panel, 2, border_radius=10)
        font = getattr(g, "font", None) or pygame.font.SysFont("dejavusans", 18)
        title = font.render("NAME YOUR SETTLEMENT", True, (238, 224, 190))
        screen.blit(title, (panel.centerx - title.get_width() // 2,
                            panel.top + 14))
        placeholder = str(getattr(g, "naming_placeholder", "") or "Settlement")
        text = str(getattr(g, "naming_text", "") or "")
        shown = text if text else placeholder
        entry = font.render(shown, True,
                            (232, 220, 180) if text else (150, 140, 120))
        box = pygame.Rect(panel.centerx - 160, panel.top + 48, 320, 34)
        pygame.draw.rect(screen, (12, 12, 16), box, border_radius=6)
        pygame.draw.rect(screen, (150, 118, 78), box, 1, border_radius=6)
        screen.blit(entry, (box.left + 10,
                            box.centery - entry.get_height() // 2))
        hint = font.render('type a name, then Enter      [Esc] keep "%s"' % placeholder,
                           True, (196, 226, 168))
        screen.blit(hint, (panel.centerx - hint.get_width() // 2,
                           panel.bottom - 30))
    except Exception:
        pass


def draw_view_fade(g, screen) -> None:
    """A short black cover used when fields/orchards switch modes."""
    try:
        a = max(0, min(255, int(getattr(g, "_view_fade_alpha", 0) or 0)))
        if a <= 0:
            return
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, a))
        screen.blit(shade, (0, 0))
    except Exception:
        pass


def _draw_chat_cloud(g, screen) -> None:
    """One nearby speaker, one cloud, above their head, for at least 5 s."""
    global _CHAT_FONT
    try:
        import comm
        clouds = list(getattr(comm, "_clouds", ()) or ())
    except Exception:
        return
    if not clouds:
        return
    fwd, right, up = _cam(g)
    ex, ey = _eye_xy(g, update=False)
    sw, sh = screen.get_size()
    best = None
    best_d = 240.0
    for _cloud in clouds:
        x, y, kind, text, ttl = _cloud[:5]
        _speaker = _cloud[5] if len(_cloud) > 5 else None
        # Follow the speaker's CURRENT position.  A cloud used to be pinned to
        # the x/y sampled when the line started, so an NPC who took a step
        # walked out from under his own sentence.
        if _speaker is not None and getattr(_speaker, "alive", True):
            x, y = _speaker.x, _speaker.y
        d = math.hypot(float(x) - ex, float(y) - ey)
        if d > best_d:
            continue
        # The first-person projection is in the small internal frame's
        # coordinates.  Chat is drawn later, on the window-sized HUD; without
        # this conversion a 280-pixel x became a 280-pixel x on a 1280-pixel
        # screen and every cloud floated far up/left of its speaker.
        p = _project(fwd, right, up, ex, ey, float(x), float(y), 82.0)
        if p is None:
            continue
        sx, sy, _cz = p
        sx = sx * sw / float(IW)
        sy = sy * sh / float(IH)
        if sx < -160 or sx > sw + 160:
            continue
        best = (x, y, kind, text, ttl, sx, sy)
        best_d = d
    if best is None:
        return
    try:
        import comm
        if _CHAT_FONT is None:
            _CHAT_FONT = pygame.font.SysFont("dejavusans", 18, bold=True)
        surf, rect = comm._cloud_surf(_CHAT_FONT, best[2], best[3], best[4])
        scale = 1.25
        surf = pygame.transform.smoothscale(
            surf, (max(1, int(surf.get_width() * scale)),
                   max(1, int(surf.get_height() * scale))))
        rect = surf.get_rect()
        # Directly above the head: the projected point is the NPC's head
        # height (82 world units), not an arbitrary screen-space offset.
        rect.center = (int(best[5]), int(best[6]) - 10)
        screen.blit(surf, rect)
    except Exception:
        pass


def draw_hud(g) -> None:
    screen = g.screen
    try:
        # Keep the persona card's subject/margins in step with the 2D HUD.
        g.draw_persona()
    except Exception:
        pass
    if not getattr(g, "hud_hidden", False) and not getattr(g.player, "dead", False):
        _viewmodel(g, screen)
    if not getattr(g, "hud_hidden", False) and not getattr(g.player, "dead", False):
        try:
            g.damage = 1.0 - g.player.health / g.player.max_health
            g.vignette.draw(screen, g.damage, g.now,
                            getattr(g.player, "hit_flash", 0.0) / 0.15)
        except Exception:
            pass
    try:
        if not getattr(g.player, "dead", False):
            # A real screen-level fallback: watch the skill total itself, not
            # only player.level_flash.  If a learning path forgot the flag, or
            # a slow frame eats the 1.6 s flash before it is presented, the
            # screen shine still starts on the frame the level actually rose.
            _skills = getattr(g, "skills", None)
            _total = int(_skills.levels_total()) if _skills is not None else 0
            _seen = getattr(g, "_v3_level_seen", None)
            if _seen is None:
                g._v3_level_seen = _total
            elif _total > int(_seen):
                g._v3_level_screen_at = pygame.time.get_ticks() / 1000.0
                g._v3_level_seen = _total
            else:
                g._v3_level_seen = _total
            _started = float(getattr(g, "_v3_level_screen_at", 0.0) or 0.0)
            _elapsed = pygame.time.get_ticks() / 1000.0 - _started
            _flash = float(getattr(g.player, "level_flash", 0.0) or 0.0)
            if _flash > 0.0:
                _elapsed = 1.6 * (1.0 - _flash / g.player.LEVEL_FLASH)
                if _started <= 0.0:
                    g._v3_level_screen_at = (pygame.time.get_ticks() / 1000.0
                                             - _elapsed)
            if 0.0 <= _elapsed < 1.6:
                import effects as _effects
                _effects.draw_level_screen(screen, _elapsed / 1.6)
    except Exception:
        pass
    if not getattr(g, "hud_hidden", False):
        _crosshair(screen)
        try:
            g.hotbar.draw(screen)
            g.hotbar.draw_action(screen, g.player)
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
        try:
            if getattr(g, "placing", None) is not None:
                _hint = "Left click: place        Right click: cancel"
            else:
                _wp = g.near_workplace()
                _kind = getattr(_wp, "kind", "") if _wp is not None else ""
                _hint = ""
                if _kind == "workshop":
                    _hint = "[E] Use workbench"
                elif _kind == "lab":
                    _hint = "[E] Use artisan bench"
                elif _kind in ("smith", "brewery", "research", "weaver", "spice",
                               "medicine_hut", "fireplace"):
                    _hint = "[E] Use %s" % _kind.replace("_", " ")
            if _hint:
                _lab = g.font.render(_hint, True, (236, 226, 188))
                screen.blit(_lab, (screen.get_width() // 2 - _lab.get_width() // 2,
                                    screen.get_height() - 150))
        except Exception:
            pass
    _draw_toast(g, screen)
    _draw_chat_cloud(g, screen)
    # The recharge bar now lives in the hotbar stack, above stamina.

    # The existing panels are screen-space; keep them as they are.
    if getattr(g, "worker_panel_open", False) and getattr(g, "worker_panel", None) is not None:
        try:
            _tab = getattr(g, "npc_tab", "inventory")
            if _tab == "mind":
                g.draw_mind_panel()
            elif _tab == "relations":
                g.draw_relations_panel()
            else:
                g.worker_panel.draw(screen)
                g.draw_npc_tabs()
        except Exception:
            pass
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
        ("sign_open", "sign_panel"),
        ("stall_open", "stall_panel"),
        ("body_open", "body_panel"),
        ("folder_open", "folder_panel"),
        ("gunsmith_open", "gunsmith_panel"),
        ("smith_panel_open", "smith_panel"),
        ("barracks_open", "barracks_panel"),
        ("compass_open", "compass_menu"),
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
    _draw_smith_panel(g, screen)
    _draw_artisan_panel(g, screen)
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
    _draw_naming(g, screen)
    draw_view_fade(g, screen)
