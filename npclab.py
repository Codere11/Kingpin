"""npclab.py -- the test-mode-only NPC lab.

This is a fixture, not a settlement the normal game ever sees.  It builds a
small camp near the player with six labelled subjects, and leaves the live
world, the live camps and the normal save alone.  All controls are gated by
engine.test_mode.

Phase 0 deliberately has no traits, breaks, medicine or combat.  It proves
the fields, the overlay and the save round-trip first.
"""

from __future__ import annotations

import math

import pygame

import block
import mood
import native
import persona
import village

# Round-trippable through save/camps.registry_key: ("starter", n) writes
# "starter:n" and reads back as the same tuple.  The camp is marked starter
# only so save/camps.prepare does not add four real starter camps around the
# fixture; camp.lab is the identity that matters.
LAB_KEY = ("starter", 9999)
LAB_SEED = 0x4C414230          # "LAB0"

SUBJECTS = (
    ("T-INTJ", "INTJ"),
    ("T-ISFP", "ISFP"),
    ("T-ESTJ", "ESTJ"),
    ("T-ENFP", "ENFP"),
    ("T-ISTP", "ISTP"),
    ("T-ENTJ", "ENTJ"),
)

PANEL_BG = (18, 18, 22)
PANEL_EDGE = (92, 92, 104)
PANEL_TEXT = (232, 232, 240)
PANEL_DIM = (170, 170, 184)
PANEL_HOT = (242, 202, 92)


def _unique_append(seq, value) -> None:
    if seq is None:
        return
    for old in seq:
        if old is value:
            return
    seq.append(value)


def _find_camp(g):
    camp = getattr(g, "_npc_lab", None)
    if camp is not None:
        return camp
    reg = getattr(g, "native_settlements", None) or {}
    camp = reg.get(LAB_KEY)
    if camp is None:
        for value in reg.values():
            if getattr(value, "lab", False):
                camp = value
                break
    if camp is not None:
        g._npc_lab = camp
    return camp


def _subjects_from(camp):
    out = []
    for name in ("unemployed", "workers", "farmers"):
        for n in (getattr(camp, name, None) or ()):
            if str(getattr(n, "id", "")).startswith("lab_"):
                out.append(n)
    if not out:
        pool = getattr(camp, "people", None)
        if isinstance(pool, list):
            for n in pool:
                if str(getattr(n, "id", "")).startswith("lab_"):
                    out.append(n)
    return out


def _attach(g, camp, subjects) -> None:
    g._npc_lab = camp
    g._npc_subjects = list(subjects)
    g._npc_sel = min(int(getattr(g, "_npc_sel", 0)), max(0, len(subjects) - 1))
    if not hasattr(g, "_npc_lab_overlay"):
        g._npc_lab_overlay = True
    if getattr(g, "_native_people", None) is None:
        g._native_people = []
    for n in subjects:
        _unique_append(g._native_people, n)
        if getattr(g, "_observe_npcs", None) is not None:
            _unique_append(g._observe_npcs, n)


def _clear_spot(g):
    """Pick a dry, open-enough centre for the lab without touching the coast."""
    x0, y0 = float(g.player.x), float(g.player.y)
    for dx, dy in ((760.0, 80.0), (0.0, 760.0), (-760.0, 80.0),
                   (0.0, -760.0), (760.0, 760.0), (-760.0, -760.0)):
        cx, cy = x0 + dx, y0 + dy
        try:
            if g.world.tile_kind(int(cx // block.TILE),
                                 int(cy // block.TILE)) == "ocean":
                continue
        except Exception:
            pass
        return cx, cy
    return x0 + 760.0, y0 + 80.0


def _spawn_subjects(g, camp):
    made = []
    for i, (label, typ) in enumerate(SUBJECTS):
        ang = (2.0 * math.pi * i / len(SUBJECTS)) + 0.25
        x = float(camp.x) + math.cos(ang) * (block.TILE * 5.0)
        y = float(camp.y) + math.sin(ang) * (block.TILE * 5.0)
        n = village.NPC(x, y, LAB_SEED ^ (i * 2654435761),
                        name=label, npc_id="lab_%s" % typ,
                        role="Lab Subject")
        n.native = True
        n.native_role = "unemployed"
        n.job = "unemployed"
        n.native_camp = camp
        n.home = (x, y)
        n.speed = 52.0
        n.base_speed = 52.0
        n.wear = "normal"
        n._save_uid = "person:lab_%s" % typ
        n.mbti = typ
        n.mood = mood.DEFAULT_MOOD
        n.mood_target = mood.DEFAULT_MOOD
        n.traits = []
        n.mood_thoughts = {}
        persona.ensure(n, force=False)
        mood.ensure(n)
        made.append(n)
    return made


def _reset_subjects(subjects):
    for n in subjects:
        home = getattr(n, "home", None)
        if home is not None:
            try:
                n.x, n.y = float(home[0]), float(home[1])
            except Exception:
                pass
        n.mood = mood.DEFAULT_MOOD
        n.mood_target = mood.DEFAULT_MOOD
        n.break_state = "normal"
        n.break_until = 0.0
        n.break_cooldown = 0.0
        n.frustration = 0.0
        n.trauma_points = 0.0
        n.medicines_received = 0
        n.mental_known = False
        persona.ensure(n)


def reset(g):
    """F6: build if needed, then put the subjects back at their marks."""
    camp = _find_camp(g)
    if camp is None:
        camp = _build_camp(g)
        if camp is None:
            return None
    subjects = _subjects_from(camp)
    if subjects:
        _reset_subjects(subjects)
    else:
        subjects = _spawn_subjects(g, camp)
        try:
            camp.unemployed = list(subjects)
        except Exception:
            pass
    _attach(g, camp, subjects)
    g._npc_sel = 0
    g._npc_lab_overlay = True
    _toast(g, "NPC lab reset: %d subjects" % len(subjects))
    return camp


def _build_camp(g):
    cx, cy = _clear_spot(g)
    try:
        camp = native.build(g, cx, cy, LAB_SEED)
    except Exception as exc:
        _toast(g, "NPC lab build failed: %s" % exc)
        try:
            import plog
            plog.log("NPC-LAB-ERROR", repr(exc)[:180])
        except Exception:
            pass
        return None
    camp.name = "NPC Lab"
    camp.lab = True
    camp.is_hub = False
    # True only so save/camps.prepare does not spawn four real starter camps
    # around the fixture.  camp.lab is the identity that matters.
    camp.starter = True
    camp.cell = None
    camp.unemployed = []
    reg = getattr(g, "native_settlements", None)
    if reg is None:
        reg = g.native_settlements = {}
    reg[LAB_KEY] = camp
    subjects = _spawn_subjects(g, camp)
    camp.unemployed = list(subjects)
    _attach(g, camp, subjects)
    _toast(g, "NPC lab built at %d,%d" % (int(cx), int(cy)))
    return camp


def ensure(g):
    """Find or rebuild the lab without resetting it."""
    camp = _find_camp(g)
    if camp is None:
        camp = _build_camp(g)
        if camp is None:
            return None
    subjects = _subjects_from(camp)
    if not subjects:
        subjects = _spawn_subjects(g, camp)
        try:
            camp.unemployed = list(subjects)
        except Exception:
            pass
    _attach(g, camp, subjects)
    return camp


def toggle(g):
    g._npc_lab_overlay = not bool(getattr(g, "_npc_lab_overlay", True))


def next_subject(g):
    ensure(g)
    subjects = getattr(g, "_npc_subjects", [])
    if not subjects:
        return
    g._npc_sel = (int(getattr(g, "_npc_sel", 0)) + 1) % len(subjects)
    n = subjects[g._npc_sel]
    _toast(g, "NPC LAB: %s" % getattr(n, "name", "?"))


def cycle_mood(g):
    ensure(g)
    subjects = getattr(g, "_npc_subjects", [])
    if not subjects:
        return
    n = subjects[int(getattr(g, "_npc_sel", 0)) % len(subjects)]
    got = mood.cycle(n)
    _toast(g, "%s mood %.0f" % (getattr(n, "name", "?"), got))


def _toast(g, text):
    try:
        g.toast(text)
    except Exception:
        pass


def draw(g):
    """The test-only overlay.  Never draws outside test mode."""
    if not getattr(g, "test_mode", False):
        return
    if not bool(getattr(g, "_npc_lab_overlay", False)):
        return
    try:
        font = getattr(g, "font", None)
        if font is None:
            font = pygame.font.SysFont("dejavusans", 14)
        subjects = list(getattr(g, "_npc_subjects", ()) or ())
        sel = int(getattr(g, "_npc_sel", 0))
        n = subjects[sel % len(subjects)] if subjects else None
        lines = [
            ("NPC LAB  TEST ONLY", PANEL_HOT),
            ("F5 hide   F6 reset   F7 next   F8 mood", PANEL_DIM),
        ]
        if n is None:
            lines.append(("no lab: press F6", PANEL_TEXT))
        else:
            lines.append(("%d/%d  %s   MBTI %s"
                          % (sel + 1, len(subjects),
                             getattr(n, "name", "?"),
                             getattr(n, "mbti", "?")), PANEL_TEXT))
            lines.append(("job=%s   mood %.0f / target %.0f   break=%s"
                          % (getattr(n, "job", "?"),
                             float(getattr(n, "mood", 50.0)),
                             float(getattr(n, "mood_target", 50.0)),
                             getattr(n, "break_state", "normal")), PANEL_TEXT))
            lines.append(("traits: %s"
                          % (", ".join(getattr(n, "traits", ()) or ()) or "none"),
                          PANEL_DIM))
            lines.append(("thoughts: %s" % mood.thought_summary(n), PANEL_DIM))
            lines.append(("medicine %d   mental record %s"
                          % (int(getattr(n, "medicines_received", 0) or 0),
                             "yes" if getattr(n, "mental_known", False) else "no"),
                          PANEL_DIM))
        lh = 18
        width = max(360, max(font.size(text)[0] for text, _ in lines) + 24)
        height = 12 + lh * len(lines)
        x, y = 12, 12
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((*PANEL_BG, 232))
        pygame.draw.rect(panel, PANEL_EDGE, panel.get_rect(), 1)
        g.screen.blit(panel, (x, y))
        ty = y + 7
        for text, color in lines:
            img = font.render(text, True, color)
            g.screen.blit(img, (x + 10, ty))
            ty += lh
    except Exception:
        # The lab must never be able to stop the frame it is testing.
        pass
