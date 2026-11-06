"""comm.py -- THE THREE WAYS TO SPEAK TO A MAN, and what they do.

G toggles the Communication panel: Insult, Praise, Threaten. One of them can
be equipped like an item and used on a person exactly like a fist -- click his
direction, within reach, not on his body. Each is capped at three uses a day
against any one person, so a man cannot be praised or insulted into nonsense.
"""
import pygame
import math

import economy

KINDS = ("insult", "praise", "threaten")
# (opinion the target holds of the player, the target's mood)
EFFECT = {
    "praise": (10.0, 10.0),
    "insult": (-10.0, -10.0),
    "threaten": (-15.0, -15.0),
}
CAP_PER_DAY = 3

_fonts = {}


def _font(size: int, bold: bool):
    key = (size, bold)
    f = _fonts.get(key)
    if f is None:
        f = pygame.font.SysFont("dejavusans", size, bold=bold)
        _fonts[key] = f
    return f


def _thumbs(screen, x, y):
    """A little like-hand: a fist with the thumb up."""
    skin = (216, 172, 124)
    pygame.draw.circle(screen, skin, (int(x - 2), int(y + 3)), 6)
    pygame.draw.line(screen, skin, (int(x + 2), int(y - 2)), (int(x + 7), int(y - 9)), 4)


def draw_symbol(screen, kind, x, y):
    """The symbol as the player holds it."""
    if kind == "insult":
        img = _font(15, True).render("F#!K", True, (10, 10, 10))
        screen.blit(img, img.get_rect(center=(int(x), int(y))))
    elif kind == "praise":
        _thumbs(screen, x, y)
    elif kind == "threaten":
        img = _font(26, True).render("!", True, (216, 30, 30))
        screen.blit(img, img.get_rect(center=(int(x), int(y))))


def draw_panel(screen, font, vw, vh, selected):
    """The Communication panel, open while G is held down."""
    w, h = 200, 128
    x = vw // 2 - w // 2
    y = vh // 2 - h // 2
    pygame.draw.rect(screen, (20, 18, 22), (x, y, w, h), border_radius=8)
    pygame.draw.rect(screen, (70, 64, 56), (x, y, w, h), 2, border_radius=8)
    for i, kind in enumerate(KINDS):
        ry = y + 12 + i * 36
        if selected == kind:
            pygame.draw.rect(screen, (54, 48, 40), (x + 8, ry - 8, w - 16, 30),
                             border_radius=5)
        draw_symbol(screen, kind, x + 34, ry + 6)
        label = font.render(kind.title(), True,
                            (244, 236, 214) if selected == kind else (170, 168, 174))
        screen.blit(label, (x + 56, ry))
        key = font.render(str(i + 1), True, (120, 116, 122))
        screen.blit(key, (x + 16, ry))


def use_comm(target, kind, now):
    """Apply insult/praise/threaten to one man. Returns (True, left) if it
    landed, (False, 0) if this man has already heard it three times today."""
    if kind not in EFFECT or target is None:
        return False, 0
    day = int(now / economy.DAY_LENGTH)
    used = getattr(target, "comm_used", None)
    if used is None:
        used = {}
        target.comm_used = used
    key = "player"
    rec = used.get(key)
    if rec is not None and rec[0] == day and rec[1] >= CAP_PER_DAY:
        return False, 0
    if rec is None or rec[0] != day:
        rec = [day, 0]
    rec[1] += 1
    used[key] = rec
    op, mood = EFFECT[kind]
    opd = economy.opinion_of(target, "player")
    cur = float(opd.get("player", 0.0))
    opd["player"] = max(-100.0, min(100.0, cur + op))
    target.mood = max(0.0, min(100.0, float(getattr(target, "mood", 50.0)) + mood))
    return True, CAP_PER_DAY - rec[1]


def bar_rects(vw, vh):
    slot = 58
    pad = 8
    n = 3
    panel_w = n * slot + (n + 1) * pad
    x0 = (vw - panel_w) // 2
    y0 = vh - slot - 2 * pad - 16
    return [pygame.Rect(x0 + pad + i * (slot + pad), y0 + pad, slot, slot)
            for i in range(n)]


def bar_slot_at(pos, vw, vh):
    for i, r in enumerate(bar_rects(vw, vh)):
        if r.collidepoint(pos):
            return i
    return None


def draw_bar(screen, font, vw, vh, selected):
    """The Communication hotbar: three slots where the pack normally is."""
    for i, kind in enumerate(KINDS):
        r = bar_rects(vw, vh)[i]
        pygame.draw.rect(screen, (26, 24, 28), r, border_radius=6)
        border = (222, 176, 88) if selected == kind else (70, 64, 56)
        pygame.draw.rect(screen, border, r, 2, border_radius=6)
        draw_symbol(screen, kind, r.centerx, r.centery)


_clouds = []          # [world_x, world_y, kind, seconds_left]
CLOUD_SECONDS = 3.0


def spawn_cloud(x, y, kind):
    """A chat cloud over a man: what was just said to him."""
    _clouds.append([float(x), float(y), kind, CLOUD_SECONDS])


def tick_clouds(dt):
    if not _clouds:
        return
    for c in _clouds:
        c[3] -= dt
    _clouds[:] = [c for c in _clouds if c[3] > 0.0]


def draw_clouds(screen, cam_x, cam_y):
    for x, y, kind, ttl in _clouds:
        sx = x - cam_x
        sy = y - cam_y
        _draw_cloud(screen, sx, sy, kind, ttl)


def _draw_cloud(screen, sx, sy, kind, ttl):
    """A rounded speech bubble above the man, with the message on it."""
    bw, bh = 66, 36
    bx = int(sx) - bw // 2
    by = int(sy) - 64
    fade = max(0.0, min(1.0, ttl / 0.4))          # fade the last 0.4 s
    surf = pygame.Surface((bw + 8, bh + 12), pygame.SRCALPHA)
    # tail first, then the bubble over it
    pygame.draw.polygon(surf, (250, 244, 232),
                        [(bw // 2 - 4, bh + 2), (bw // 2 + 4, bh + 2), (bw // 2, bh + 10)])
    pygame.draw.rect(surf, (250, 244, 232), (2, 2, bw, bh), border_radius=12)
    pygame.draw.rect(surf, (64, 60, 56), (2, 2, bw, bh), 2, border_radius=12)
    surf.set_alpha(int(255 * fade))
    screen.blit(surf, (bx - 4, by))
    draw_symbol(screen, kind, bx + bw // 2, by + bh // 2 + 2)


# -- NPC TO NPC ------------------------------------------------------------
# A man speaks to a neighbour on his own: the opinion he holds decides whether
# it is praise, an insult or a threat, and the odds lean with the opinion.
NEARBY_PX = 90.0
SCAN_SECONDS = 2.0
CHAT_PER_PERSON_CD = 30.0       # cannot speak to the SAME man this often
CHAT_ALL_CD = 180.0             # after five chats, rest this long before any


def npc_chances(op):
    """(praise, insult, threaten) percent chances from the opinion he holds
    (-100..+100; 0 is neutral, the user's 50)."""
    d = op / 5.0
    praise = 30.0 + 6.0 * d
    insult = 15.0 - 3.0 * d
    threaten = 15.0 - 3.0 * d
    return (max(0.0, min(100.0, praise)),
            max(0.0, min(100.0, insult)),
            max(0.0, min(100.0, threaten)))


def _apply(speaker, target, kind):
    op, mood = EFFECT[kind]
    sid = getattr(speaker, "id", None)
    if sid is not None:
        opd = economy.opinion_of(target, sid)
        cur = float(opd.get(sid, 0.0))
        opd[sid] = max(-100.0, min(100.0, cur + op))
    target.mood = max(0.0, min(100.0, float(getattr(target, "mood", 50.0)) + mood))


def npc_try_chat(speaker, others, now):
    """One man tries to speak to one nearby man. Returns (target, kind) or None."""
    if now < float(getattr(speaker, "_chat_all_until", 0.0)):
        return None
    cds = getattr(speaker, "_chat_cds", None)
    if cds is None:
        cds = {}
        speaker._chat_cds = cds
    rng = speaker.rng
    cands = []
    for o in others:
        if o is speaker or not getattr(o, "alive", True):
            continue
        if getattr(o, "in_interior", False) or getattr(o, "asleep", False):
            continue
        oid = getattr(o, "id", None)
        if oid is None:
            continue
        if math.hypot(o.x - speaker.x, o.y - speaker.y) > NEARBY_PX:
            continue
        if now < float(cds.get(oid, 0.0)):
            continue
        op = float(economy.opinion_of(speaker, oid).get(oid, 0.0))
        cands.append((o, oid, op))
    if not cands:
        return None
    o, oid, op = cands[rng.randrange(len(cands))]
    praise, insult, threaten = npc_chances(op)
    r = rng.random() * 100.0
    if r < praise:
        kind = "praise"
    elif r < praise + insult:
        kind = "insult"
    elif r < praise + insult + threaten:
        kind = "threaten"
    else:
        return None
    cds[oid] = now + CHAT_PER_PERSON_CD
    n = int(getattr(speaker, "_chat_n", 0)) + 1
    speaker._chat_n = n
    if n >= 5:
        speaker._chat_all_until = now + CHAT_ALL_CD
        speaker._chat_n = 0
    _apply(speaker, o, kind)
    return (o, kind)
