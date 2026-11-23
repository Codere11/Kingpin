"""npclab.py -- the test-mode-only NPC lab.

This is a fixture, not a settlement the normal game ever sees.  It builds a
small camp near the player with eight labelled subjects, and leaves the live
world, the live camps and the normal save alone.  All controls are gated by
engine.test_mode.

Phase 0 deliberately has no traits, breaks, medicine or combat.  It proves
the fields, the overlay and the save round-trip first.
"""

from __future__ import annotations

import math

import pygame

import block
import crop as crop_mod
import mood
import native
import persona
import placement
import village
import world as world_mod

# Round-trippable through save/camps.registry_key: ("starter", n) writes
# "starter:n" and reads back as the same tuple.  The camp is marked starter
# only so save/camps.prepare does not add four real starter camps around the
# fixture; camp.lab is the identity that matters.
LAB_KEY = ("starter", 9999)
LAB_SEED = 0x4C414230          # "LAB0"

# Test subjects get ordinary names.  Their type is a private field, shown
# only on the medical record; it is not part of the name or a label over
# their head.  The key is internal and only keeps the fixture/save order.
SUBJECTS = (
    ("a", "Awan", "INTJ", "idle"),
    ("b", "Kiona", "ISFP", "idle"),
    ("c", "Takoda", "ESTJ", "idle"),
    ("d", "Yuma", "ENFP", "idle"),
    ("e", "Nashoba", "ISTP", "idle"),
    ("f", "Chenoa", "ENTJ", "idle"),
    # The paired farmer test from NPC.md T1: same work, one sensing and one
    # intuitive, on their own one-tile plots.  The second field is the role,
    # never part of the name.
    ("g", "Migina", "ISFJ", "farmer"),
    ("h", "Ohanzee", "INTJ", "farmer"),
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
    found = {}
    for name in ("unemployed", "workers", "farmers"):
        for n in (getattr(camp, name, None) or ()):
            ident = str(getattr(n, "id", ""))
            if ident.startswith("lab_"):
                found[ident] = n
    pool = getattr(camp, "people", None)
    if isinstance(pool, list):
        for n in pool:
            ident = str(getattr(n, "id", ""))
            if ident.startswith("lab_"):
                found[ident] = n
    # CANONICAL ORDER.  The save restores the camp's rosters in their own
    # order; F7 must still walk the same list it built on the first frame.
    return [found["lab_" + key] for key, _name, _typ, _role in SUBJECTS
            if ("lab_" + key) in found]


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


def _coast(g, y):
    try:
        return float(world_mod.coast_x(float(y), int(g.world.seed)))
    except Exception:
        return None


def _dry_at(g, cx, cy, radius=520.0):
    """True when the whole camp footprint is inland, not just its centre.

    The spawn coast runs north-south with ocean to the EAST.  Checking only
    the centre tile was not enough: the camp ring and fields could still reach
    into the water (or the walk there could be blocked by it).
    """
    coast = _coast(g, cy)
    if coast is not None and float(cx) > coast - 900.0:
        return False
    for ox, oy in ((0.0, 0.0),
                   (-radius, 0.0), (radius, 0.0),
                   (0.0, -radius), (0.0, radius),
                   (-radius, -radius), (-radius, radius),
                   (radius, -radius), (radius, radius)):
        try:
            if g.world.tile_kind(int((cx + ox) // block.TILE),
                                 int((cy + oy) // block.TILE)) == "ocean":
                return False
        except Exception:
            pass
    return True


def _clear_spot(g):
    """Pick a dry centre.  West/inland first: east is always the ocean."""
    x0, y0 = float(g.player.x), float(g.player.y)
    # WEST FIRST.  The old order tried east, which is exactly where the coast
    # is; every lab ended up on the far side of impassable water.
    candidates = ((-760.0, 80.0), (-1100.0, 40.0), (-760.0, -520.0),
                  (-760.0, 620.0), (-1400.0, 80.0),
                  (0.0, 760.0), (0.0, -760.0), (760.0, 760.0),
                  (760.0, -760.0))
    for dx, dy in candidates:
        cx, cy = x0 + dx, y0 + dy
        if _dry_at(g, cx, cy):
            return cx, cy
    # Last resort: straight inland, away from the coast, even if close.
    coast = _coast(g, y0)
    if coast is not None:
        return min(x0 - 400.0, coast - 1000.0), y0 + 80.0
    return x0 - 760.0, y0 + 80.0


def _camp_valid(g, camp):
    try:
        return _dry_at(g, float(camp.x), float(camp.y))
    except Exception:
        return True


def _discard(g, camp):
    """Drop a lab that was built in the sea (older F6 did exactly that)."""
    if camp is None:
        return
    doomed = [n for n in (getattr(g, "_native_people", ()) or ())
              if getattr(n, "native_camp", None) is camp]
    doomed += [n for n in (getattr(camp, "unemployed", ()) or ())
               if n not in doomed]
    for n in doomed:
        for seq_name in ("_native_people", "_observe_npcs"):
            seq = getattr(g, seq_name, None) or ()
            if n in seq:
                try:
                    seq.remove(n)
                except ValueError:
                    pass
    for key, value in list((getattr(g, "native_settlements", {}) or {}).items()):
        if value is camp:
            try:
                del g.native_settlements[key]
            except Exception:
                pass
    g._npc_lab = None
    g._npc_subjects = []
    g._npc_sel = 0


def _ensure_breakables(g, camp):
    """One breakable chest west of the fire, so F9's spree has a target."""
    if getattr(camp, "_lab_breakables", False):
        return
    try:
        chest = placement.Chest(float(camp.x) + block.TILE * 4.0,
                                float(camp.y) + block.TILE * 2.0)
        if getattr(g, "built_chests", None) is None:
            g.built_chests = []
        g.built_chests.append(chest)
        camp._lab_breakables = True
    except Exception:
        pass


def _ensure_farm_plots(g, camp):
    """Two isolated one-tile plots west of the lab, owned by the pair."""
    done = getattr(camp, "_lab_farm_plots", None)
    if done is not None:
        return list(done)
    plots = []
    world = g.world
    for i in range(2):
        cx = int((float(camp.x) - (4.0 + i) * block.TILE) // block.TILE)
        cy = int((float(camp.y) + (i * 2 - 1) * block.TILE) // block.TILE)
        try:
            world.set_plot(cx, cy, "grass", None)
        except Exception:
            pass
        kind = getattr(camp, "food_kind", "wheat")
        camp.farm_plots.append((cx, cy, kind))
        camp.farm_tiles[(cx, cy)] = [(cx, cy, kind)]
        plots.append(len(camp.farm_plots) - 1)
    camp._lab_farm_plots = list(plots)
    return plots


def _spawn_subjects(g, camp):
    made = []
    farm_plots = _ensure_farm_plots(g, camp)
    food_item = (getattr(camp, "food_item", None)
                 or crop_mod.FOOD_ITEM.get(getattr(camp, "food_kind", ""),
                                           "bread"))
    farmer_i = 0
    for i, (key, label, typ, role) in enumerate(SUBJECTS):
        ang = (2.0 * math.pi * i / len(SUBJECTS)) + 0.25
        x = float(camp.x) + math.cos(ang) * (block.TILE * 5.0)
        y = float(camp.y) + math.sin(ang) * (block.TILE * 5.0)
        n = village.NPC(x, y, LAB_SEED ^ (i * 2654435761),
                        name=label, npc_id="lab_%s" % key,
                        role="Lab Subject")
        n.native = True
        n.native_role = role
        n.job = "unemployed" if role == "idle" else role
        n.native_camp = camp
        if role == "farmer":
            n.farm_plot = farm_plots[farmer_i % len(farm_plots)]
            farmer_i += 1
            n.stock[food_item] = 60
            n.stock["shovel"] = 1
            n.tool_uses = 100
        n.home = (x, y)
        n.speed = 52.0
        n.base_speed = 52.0
        n.wear = "normal"
        n._save_uid = "person:lab_%s" % key
        n.mbti = typ
        n.mood = mood.DEFAULT_MOOD
        n.mood_target = mood.DEFAULT_MOOD
        n.mood_thoughts = {}
        persona.ensure(n, force=False)
        mood.ensure(n)
        made.append(n)
    return made


def _reset_subjects(subjects):
    canonical = {"lab_" + key: (label, typ)
                 for key, label, typ, _role in SUBJECTS}
    for n in subjects:
        # Keep a lab carried over from an older build in step with the
        # canonical fixture: ordinary name, type private.
        _canon = canonical.get(str(getattr(n, "id", "")))
        if _canon is not None:
            try:
                n.name, n.mbti = _canon
            except Exception:
                pass
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
    if camp is not None and (not _camp_valid(g, camp)
                             or len(_subjects_from(camp)) != len(SUBJECTS)):
        _discard(g, camp)
        camp = None
    if camp is None:
        camp = _build_camp(g)
        if camp is None:
            return None
    _ensure_breakables(g, camp)
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
    _ensure_breakables(g, camp)
    subjects = _spawn_subjects(g, camp)
    camp.unemployed = list(subjects)
    _attach(g, camp, subjects)
    _side = "west" if cx < float(g.player.x) else "east"
    _toast(g, "NPC lab built %s at %d,%d" % (_side, int(cx), int(cy)))
    return camp


def ensure(g):
    """Find or rebuild the lab without resetting it."""
    camp = _find_camp(g)
    if camp is not None and (not _camp_valid(g, camp)
                             or len(_subjects_from(camp)) != len(SUBJECTS)):
        _discard(g, camp)
        camp = None
    if camp is None:
        camp = _build_camp(g)
        if camp is None:
            return None
    _ensure_breakables(g, camp)
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


def force_break(g):
    """F9: cycle the selected or clicked person through sad/annoyed/normal.

    DELIBERATELY DOES NOT CALL ensure().  F6 may rebuild the fixture; F9 must
    only change the person already in front of the player.  Rebuilding here
    removed the old camp's people while their chat clouds were still on screen,
    which looked like every skin vanishing.
    """
    subjects = list(getattr(g, "_npc_subjects", ()) or ())
    n = getattr(g, "persona", None)
    if n is None or not getattr(n, "native", False):
        if not subjects:
            return
        n = subjects[int(getattr(g, "_npc_sel", 0)) % len(subjects)]
    state = mood.force_break(n, float(getattr(g, "now", 0.0)))
    _toast(g, "%s: %s" % (getattr(n, "name", "?"), state))


def give_medicine(g):
    """Test-only administration: the first medicine unlocks the record."""
    ensure(g)
    subjects = getattr(g, "_npc_subjects", [])
    if not subjects:
        return
    # If a card is open on a clicked native (a warrior, for example), treat
    # that person; otherwise treat the F7 selection.
    n = getattr(g, "persona", None)
    if n is None or not getattr(n, "native", False):
        n = subjects[int(getattr(g, "_npc_sel", 0)) % len(subjects)]
    n.medicines_received = int(getattr(n, "medicines_received", 0) or 0) + 1
    n.mental_known = True
    try:
        n.health = n.max_health
    except Exception:
        pass
    _toast(g, "%s examined: medical record unlocked"
           % getattr(n, "name", "?"))


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
            ("F5 hide  F6 reset  F7 next  F8 mood  F9 break  F10 medicine", PANEL_DIM),
        ]
        if n is None:
            lines.append(("no lab: press F6", PANEL_TEXT))
        else:
            lines.append(("%d/%d  %s   job=%s"
                          % (sel + 1, len(subjects),
                             getattr(n, "name", "?"),
                             getattr(n, "job", "?")), PANEL_TEXT))
            known = persona.mental_known(n)
            if not known:
                lines.append(("MEDICAL RECORD: NO", PANEL_DIM))
                lines.append(("F10 gives one medicine and unlocks it", PANEL_DIM))
            else:
                lines.append(("MBTI %s   medicine %d"
                              % (getattr(n, "mbti", "?"),
                                 int(getattr(n, "medicines_received", 0) or 0)),
                              PANEL_TEXT))
                lines.append(("mood %.0f / target %.0f   break=%s"
                              % (float(getattr(n, "mood", 50.0)),
                                 float(getattr(n, "mood_target", 50.0)),
                                 getattr(n, "break_state", "normal")), PANEL_TEXT))
                lines.append(("traits: %s"
                              % (", ".join(getattr(n, "traits", ()) or ()) or "none"),
                              PANEL_DIM))
                lines.append(("thoughts: %s" % mood.thought_summary(n), PANEL_DIM))
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
