"""Test-mode world map: a 100,000 x 100,000 region centred on spawn.

Forests from the real tree noise, every village with a name, a faint political
tint showing the three nations' territory, and zoom in/out.
"""

from __future__ import annotations

import math
import threading

import numpy as np
import pygame

import nations
import biomes
from noise import fbm
from village import SPACING, nation_color

HALF = 100000.0
MIN_ZOOM, MAX_ZOOM = 1.0, 14.0


class WorldMap:
    def __init__(self, seed: int, half: float = HALF, size: int = 800,
                 background: bool = False) -> None:
        self.seed = seed
        self.half = half
        self.size = size
        self.zoom = 1.0
        self.center_x = 0.0
        self.center_y = 0.0
        self.build_cx = 0.0        # the centre the current map image was built around
        self.build_cy = 0.0
        self.base = None
        self._lock = threading.Lock()
        self._font_key = None
        if background:
            self.start_build()      # render it now, while the player is playing
        else:
            self.base = self._build()

    def start_build(self) -> None:
        """Render the map on a worker thread so opening it is instant."""
        if self.base is not None:
            return
        threading.Thread(target=self._build_worker, daemon=True).start()

    def _build_worker(self) -> None:
        surf = self._build()
        with self._lock:
            self.base = surf

    def ready(self) -> bool:
        return self.base is not None

    def reset(self, x: float, y: float) -> None:
        self.center_x = x
        self.center_y = y
        self._clamp()
        # THE MAP FOLLOWS THE PLAYER. If he has walked past the edge of the
        # built image, rebuild it around him (on the worker thread).
        if (abs(x - self.build_cx) > self.half
                or abs(y - self.build_cy) > self.half):
            self.build_cx = x
            self.build_cy = y
            self.base = None
            self.start_build()

    def _clamp(self) -> None:
        span = self.half / self.zoom
        lo, hi = -self.half + span, self.half - span
        self.center_x = min(max(self.center_x, lo), hi)
        self.center_y = min(max(self.center_y, lo), hi)

    def update(self, dt: float) -> None:
        """WASD / arrows pan the map."""
        keys = pygame.key.get_pressed()
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        up = keys[pygame.K_w] or keys[pygame.K_UP]
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]
        if not (right or left or up or down):
            return
        speed = (self.half / self.zoom) * 1.1
        self.center_x += (float(right) - float(left)) * speed * dt
        self.center_y += (float(down) - float(up)) * speed * dt   # up = north
        self._clamp()

    def _build(self) -> pygame.Surface:
        n, half = self.size, self.half
        xs = np.linspace(self.build_cx - half, self.build_cx + half, n,
                         dtype=np.float32)
        ys = np.linspace(self.build_cy - half, self.build_cy + half, n,
                         dtype=np.float32)
        xgrid, ygrid = np.meshgrid(xs, ys)
        forest = fbm(xgrid * 0.0006, ygrid * 0.0006, self.seed + 1, octaves=4)
        clump = fbm(xgrid * 0.0045, ygrid * 0.0045, self.seed + 2, octaves=3)
        temp = biomes.temperature(xgrid, ygrid, self.seed)
        hum = biomes.humidity(xgrid, ygrid, self.seed)
        base_rgb = biomes.blend_array("lite", temp, hum).astype(np.float32)
        t = np.clip((forest - 0.35) / 0.15, 0.0, 1.0)
        t = t * t * (3.0 - 2.0 * t)
        density = np.clip(0.12 + t * (0.55 + 0.45 * clump), 0.0, 1.0)[..., None]
        base_rgb = base_rgb * (1.0 - 0.34 * density)      # darker where wooded
        # THE COAST: ocean to the east, sand beach at the shoreline.
        import world as _world
        _coast = _world.coast_x(ygrid, self.seed)
        _ocean = xgrid > _coast
        _sand = (~_ocean) & (xgrid > (_coast - _world.SAND_W))
        base_rgb[_ocean] = (40, 92, 140)
        base_rgb[_sand] = (202, 178, 130)
        tint = np.array(nations.COLORS, dtype=np.float32)[nations.overlay(xgrid, ygrid)]
        alpha = 0.20                        # faint, vague political wash
        rgb = (base_rgb * (1.0 - alpha) + tint * alpha).astype(np.uint8)
        return pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))

    def _fonts(self, px: int) -> None:
        if self._font_key != px:
            self.title_font = pygame.font.SysFont("dejavusans", max(14, px), bold=True)
            self.font = pygame.font.SysFont("dejavusans", max(11, int(px * 0.72)), bold=True)
            self.small = pygame.font.SysFont("dejavusans", max(9, int(px * 0.58)))
            self._font_key = px

    @staticmethod
    def _nice_step(raw: float) -> float:
        if raw <= 0:
            return 1000.0
        mag = 10.0 ** math.floor(math.log10(raw))
        for m in (1, 2, 5, 10):
            if raw <= m * mag:
                return m * mag
        return 10.0 * mag

    def zoom_event(self, event) -> bool:
        """Wheel or +/- changes zoom. Returns True if the zoom changed."""
        if event.type == pygame.MOUSEWHEEL:
            self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * (1.3 if event.y > 0 else 1/1.3)))
            self._clamp()
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.zoom = min(MAX_ZOOM, self.zoom * 1.3)
                self._clamp()
                return True
            if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.zoom = max(MIN_ZOOM, self.zoom / 1.3)
                self._clamp()
                return True
        return False

    def draw(self, screen: pygame.Surface, villages, player,
             armies=None) -> None:
        vw, vh = screen.get_size()
        mp = max(140, min(vw - 60, vh - 120))
        mx = (vw - mp) // 2
        my = (vh - mp) // 2 + 14
        self._fonts(vw // 90)

        span = self.half / self.zoom
        self._clamp()
        cx, cy = self.center_x, self.center_y
        scale = mp / (2.0 * span)

        with self._lock:
            base = self.base
        if base is None:
            self._fonts(20)
            msg = self.title_font.render("charting the world\u2026", True, (210, 205, 190))
            screen.blit(msg, (screen.get_width() // 2 - msg.get_width() // 2,
                              screen.get_height() // 2 - msg.get_height() // 2))
            return

        def w2s(wx, wy):
            # North (-y) is up, south (+y) is down; east (+x) is to the right.
            return (mx + (wx - (cx - span)) * scale,
                    my + (wy - (cy - span)) * scale)

        shade = pygame.Surface((vw, vh), pygame.SRCALPHA)
        shade.fill((6, 9, 12, 224))
        screen.blit(shade, (0, 0))

        bw = bh = self.size
        sx0 = (cx - span + self.half) / (2.0 * self.half) * bw
        sy0 = (cy - span + self.half) / (2.0 * self.half) * bh
        sw = (2.0 * span) / (2.0 * self.half) * bw
        sh = sw * (bh / bw)
        sub = base.subsurface(pygame.Rect(int(sx0), int(sy0),
                                               max(1, int(sw)), max(1, int(sh))))
        screen.blit(pygame.transform.smoothscale(sub, (mp, mp)), (mx, my))
        pygame.draw.rect(screen, (210, 190, 130), (mx, my, mp, mp), 2)

        step = self._nice_step(span / 3.0)
        gx = math.floor((cx - span) / step) * step
        while gx <= cx + span:
            px = w2s(gx, 0)[0]
            pygame.draw.line(screen, (255, 255, 255, 26), (px, my), (px, my + mp), 1)
            gx += step
        gy = math.floor((cy - span) / step) * step
        while gy <= cy + span:
            py = w2s(0, gy)[1]
            pygame.draw.line(screen, (255, 255, 255, 26), (mx, py), (mx + mp, py), 1)
            gy += step

        g0 = int(math.floor((cx - span) / SPACING)) - 1
        g1 = int(math.floor((cx + span) / SPACING)) + 1
        edge = span * 1.15
        ordered = []
        for gxx in range(g0, g1 + 1):
            for gyy in range(g0, g1 + 1):
                v = villages.get(gxx, gyy)
                if v is None:
                    continue
                if (abs(v.x - cx) <= edge and abs(v.y - cy) <= edge):
                    ordered.append(v)
        ordered.sort(key=lambda v: v.y)

        name_rects: list[pygame.Rect] = []
        for v in ordered:
            px, py = w2s(v.x, v.y)
            mr = min(16, max(4, int(v.radius * scale * 0.5)))
            pygame.draw.circle(screen, (0, 0, 0), (int(px), int(py)), mr + 2)
            pygame.draw.circle(screen, nation_color(v.nation), (int(px), int(py)), mr)
            pygame.draw.circle(screen, (255, 255, 255), (int(px), int(py)), mr, 1)
            for text in ("%s  (%d)" % (v.name, len(v.houses)), v.name.split()[0]):
                label = self.font.render(text, True, (248, 246, 236))
                pw, ph = label.get_width() + 10, label.get_height() + 4
                placed = None
                for spot in range(4):
                    if spot == 0:
                        lx, ly = px - pw / 2, py - mr - ph - 3
                    elif spot == 1:
                        lx, ly = px - pw / 2, py + mr + 3
                    elif spot == 2:
                        lx, ly = px + mr + 3, py - ph / 2
                    else:
                        lx, ly = px - mr - 3 - pw, py - ph / 2
                    rect = pygame.Rect(int(lx), int(ly), pw, ph)
                    if (rect.left < mx or rect.top < my or rect.right > mx + mp
                            or rect.bottom > my + mp):
                        continue
                    if any(rect.colliderect(r) for r in name_rects):
                        continue
                    placed = rect
                    break
                if placed is not None:
                    name_rects.append(placed)
                    plate = pygame.Surface((pw, ph), pygame.SRCALPHA)
                    pygame.draw.rect(plate, (12, 14, 16, 208), plate.get_rect(),
                                     border_radius=4)
                    screen.blit(plate, placed.topleft)
                    screen.blit(label, (placed.x + 5, placed.y + 2))
                    break

        # -- the war, as it stands this instant --------------------------
        # Every column of fighting men is drawn where it actually is, so the
        # map is the war: main thrusts, and the reinforcement lines trailing
        # in behind them, which are separate blobs of men on the same road.
        if armies:
            for army in armies:
                if getattr(army, "done", False):
                    continue
                live = [s for s in army.soldiers
                        if s.alive and not getattr(s, "settled", False)]
                if not live:
                    continue
                col = nation_color(army.nation)
                tgt = army.target
                groups: dict = {}
                for s in live:                      # cluster by the ground they hold
                    groups.setdefault((int(s.x // 4000.0), int(s.y // 4000.0)),
                                      []).append(s)
                for _key, men in groups.items():
                    ax = sum(m.x for m in men) / len(men)
                    ay = sum(m.y for m in men) / len(men)
                    apx, apy = w2s(ax, ay)
                    if not (mx - 40 < apx < mx + mp + 40 and my - 40 < apy < my + mp + 40):
                        continue
                    n = len(men)
                    rr = 4 + min(9, int(n ** 0.5))
                    pygame.draw.circle(screen, (10, 10, 12), (int(apx), int(apy)), rr + 3)
                    pygame.draw.circle(screen, col, (int(apx), int(apy)), rr)
                    pygame.draw.circle(screen, (255, 255, 255), (int(apx), int(apy)), rr, 2)
                    # crossed swords: unmistakably an army, not a village
                    for sgn in (1, -1):
                        pygame.draw.line(screen, (255, 255, 255),
                                         (apx - 5, apy - 5 * sgn), (apx + 5, apy + 5 * sgn), 2)
                    lab = self.small.render(str(n), True, (255, 255, 255))
                    plate = pygame.Surface((lab.get_width() + 8,
                                            lab.get_height() + 2), pygame.SRCALPHA)
                    pygame.draw.rect(plate, (10, 10, 12, 216), plate.get_rect(),
                                     border_radius=3)
                    screen.blit(plate, (apx + rr + 3, apy - lab.get_height() // 2 - 1))
                    screen.blit(lab, (apx + rr + 7, apy - lab.get_height() // 2))

        sx, sy = w2s(0.0, 0.0)
        pygame.draw.line(screen, (120, 230, 255), (sx - 9, sy), (sx + 9, sy), 2)
        pygame.draw.line(screen, (120, 230, 255), (sx, sy - 9), (sx, sy + 9), 2)

        px, py = w2s(player.x, player.y)
        pygame.draw.circle(screen, (60, 60, 60), (int(px), int(py)), 6)
        pygame.draw.circle(screen, (255, 236, 120), (int(px), int(py)), 4)
        you = self.small.render("YOU", True, (255, 236, 120))
        screen.blit(you, (px + 8, py - 6))

        title = self.title_font.render(
            "WORLD MAP   100,000 x 100,000   (TEST MODE)   zoom x%.1f" % self.zoom,
            True, (244, 238, 214))
        screen.blit(title, (vw // 2 - title.get_width() // 2, 10))

        lx = mx + 12
        for i in range(nations.count()):
            col = nation_color(i)
            pygame.draw.rect(screen, col, (lx, 34, 14, 14))
            pygame.draw.rect(screen, (240, 236, 224), (lx, 34, 14, 14), 1)
            t = self.small.render(nations.name(i), True, (244, 238, 214))
            screen.blit(t, (lx + 19, 34))
            lx += 26 + t.get_width()

        pygame.draw.circle(screen, (232, 96, 72), (lx + 7, 41), 6)
        pygame.draw.circle(screen, (255, 255, 255), (lx + 7, 41), 6, 2)
        for sgn in (1, -1):
            pygame.draw.line(screen, (255, 255, 255), (lx + 3, 37 * 1.0 + 4 - 4 * sgn),
                             (lx + 11, 41 + 4 * sgn), 1)
        t = self.small.render("army (number = men)", True, (244, 238, 214))
        screen.blit(t, (lx + 19, 34))

        bar = step * scale
        bx, by = mx + 12, my + mp - 20
        pygame.draw.rect(screen, (12, 14, 16, 190), (bx - 6, by - 16, bar + 130, 22))
        pygame.draw.line(screen, (255, 255, 255), (bx, by), (bx + bar, by), 3)
        info = self.small.render("%s units     WASD/arrows = pan   wheel/+- = zoom   M/Esc = close"
                                 % format(int(step), ","), True, (232, 228, 214))
        screen.blit(info, (bx + 4, by - 14))
