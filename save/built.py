"""built.py -- the things the player made.

Houses and their interiors, fences, gates, staked plots, workplaces, 1x1
blocks, chests, sign-posts and feed boxes.  Objects get a stable ``_save_uid``
the first time they are written, and every reference (a worker at a bench, a
man's home) points at that id.
"""

from __future__ import annotations

from . import codec
from . import context as _context
from . import store


# -- snapshot ----------------------------------------------------------------
def _house(h) -> dict:
    interior = getattr(h, "interior", None)
    chest = getattr(interior, "chest", None) if interior is not None else None
    return {
        "uid": codec.uid(h, "house"),
        "x": float(h.x), "y": float(h.y),
        "w": int(h.w), "h": int(h.h),
        "roof": list(h.roof), "facing": list(h.facing),
        "seed": int(getattr(h, "build_seed", 0)),
        "interior_seed": int(getattr(h, "interior_seed", 0)),
        "warmth": float(getattr(h, "warmth", 1.0)),
        "door_broken": bool(getattr(h, "door_broken", False)),
        "enterable": bool(getattr(h, "enterable", False)),
        "chest": codec.inventory_to_data(chest),
        "workshops": [[r.centerx, r.centery]
                      for r in getattr(interior, "workshops", ())],
        "labs": [[r.centerx, r.centery]
                 for r in getattr(interior, "lab_tables", ())],
        "brews": [[r.centerx, r.centery]
                  for r in getattr(interior, "brew_tables", ())],
        "barrels": [[b["rect"].centerx, b["rect"].centery,
                     b.get("kind") or "", int(b.get("count", 0)),
                     float(b.get("ready_at", 0.0)), int(b.get("grade", 0))]
                    for b in getattr(interior, "barrels", ())],
    }


def snapshot(g) -> dict:
    houses = []
    for h in list(getattr(g, "built_houses", ()) or ()):
        if getattr(h, "camp", False):
            continue
        try:
            houses.append(_house(h))
        except Exception:
            continue

    work = []
    for wp in list(getattr(g, "placed_work", ()) or ()):
        if (getattr(wp, "is_stall", False)
                or getattr(wp, "camp", False)
                or getattr(wp, "native", False)):
            continue
        try:
            work.append({
                "uid": codec.uid(wp, "work"),
                "kind": getattr(wp, "kind", ""),
                "x": float(wp.x), "y": float(wp.y),
                "seed": int(getattr(wp, "_rng_seed", 0)),
                "worker": codec.idref(getattr(wp, "worker", None), "person"),
                "artisan": codec.idref(getattr(wp, "artisan", None), "person"),
                "leaf": getattr(wp, "leaf", None),
                "product": getattr(wp, "product", None),
                "condition": float(getattr(wp, "condition", 100.0)),
                "max_condition": float(getattr(wp, "max_condition", 100.0)),
                "broken": bool(getattr(wp, "broken", False)),
            })
        except Exception:
            continue

    chests = []
    for ch in list(getattr(g, "built_chests", ()) or ()):
        chests.append({
            "uid": codec.uid(ch, "chest"),
            "tx": int(ch.tx), "ty": int(ch.ty),
            "filter": getattr(ch, "filter", None),
            "inventory": codec.inventory_to_data(getattr(ch, "inventory", None)),
            "condition": float(getattr(ch, "condition", 100.0)),
            "max_condition": float(getattr(ch, "max_condition", 100.0)),
            "broken": bool(getattr(ch, "broken", False)),
        })

    signs = []
    for sg in list(getattr(g, "built_signs", ()) or ()):
        signs.append({
            "uid": codec.uid(sg, "sign"),
            "x": float(sg.x), "y": float(sg.y),
            "farmers": int(getattr(sg, "farmers", 0)),
            "loggers": int(getattr(sg, "loggers", 0)),
            "artisans": int(getattr(sg, "artisans", 0)),
            "researchers": int(getattr(sg, "researchers", 0)),
            "miners": int(getattr(sg, "miners", 0)),
            "smiths": int(getattr(sg, "smiths", 0)),
            "condition": float(getattr(sg, "condition", 100.0)),
            "max_condition": float(getattr(sg, "max_condition", 100.0)),
            "broken": bool(getattr(sg, "broken", False)),
        })

    foodboxes = []
    for fb in list(getattr(g, "built_foodboxes", ()) or ()):
        foodboxes.append({
            "uid": codec.uid(fb, "foodbox"),
            "x": float(fb.x), "y": float(fb.y),
            "inventory": codec.inventory_to_data(getattr(fb, "inventory", None)),
            "condition": float(getattr(fb, "condition", 100.0)),
            "max_condition": float(getattr(fb, "max_condition", 100.0)),
            "broken": bool(getattr(fb, "broken", False)),
        })

    designs = []
    for fd in list(getattr(g, "field_designations", ()) or ()):
        designs.append({
            "rect": codec.rect_to_data(fd["rect"]),
            "type": fd.get("type", "field"),
            "kind": fd.get("kind", ""),
        })

    return {
        "houses": houses,
        "work": work,
        "chests": chests,
        "signs": signs,
        "foodboxes": foodboxes,
        "fences": [codec.rect_to_data(r) for r in
                   (getattr(g, "built_fences", ()) or ())],
        "gates": [codec.rect_to_data(r) for r in
                  (getattr(g, "built_gates", ()) or ())],
        "plots": [codec.rect_to_data(r) for r in
                  (getattr(g, "built_plots", ()) or ())],
        "blocks": [[int(tx), int(ty), str(kind)]
                   for (tx, ty), kind in
                   (getattr(g, "built_blocks", {}) or {}).items()],
        "designations": designs,
    }


# -- restore -----------------------------------------------------------------
def restore(g, data, ctx: "_context.Context") -> None:
    import pygame
    import industry
    import placement
    from interior import Interior
    from village import House

    data = data or {}
    g.built_houses[:] = []
    g.placed_work[:] = []
    g.built_fences[:] = []
    g.built_gates[:] = []
    g.built_plots[:] = []
    g.built_blocks.clear()
    g.built_chests[:] = []
    g.built_signs[:] = []
    g.built_foodboxes[:] = []
    g.field_designations[:] = []
    g.camp_walls[:] = []
    g.player.workplaces = []
    g.player.plots = set()
    g.player.yard_plots = []

    for rec in data.get("houses", ()) or ():
        try:
            house = House(float(rec["x"]), float(rec["y"]),
                          int(rec["w"]), int(rec["h"]),
                          tuple(rec["roof"]), tuple(rec["facing"]),
                          int(rec.get("seed", 0)))
            codec.set_uid(house, rec.get("uid"))
            house.build_seed = int(rec.get("seed", 0))
            house.interior_seed = int(rec.get("interior_seed", 0))
            house.warmth = float(rec.get("warmth", 1.0))
            house.door_broken = bool(rec.get("door_broken", False))
            house.enterable = bool(rec.get("enterable", True))
            interior = Interior(house.interior_seed, tuple(house.facing))
            codec.inventory_restore(interior.chest, rec.get("chest"))
            for wx, wy in rec.get("workshops", ()) or ():
                interior.place_workshop(wx, wy)
            for wx, wy in rec.get("labs", ()) or ():
                interior.place_lab(wx, wy)
            for wx, wy in rec.get("brews", ()) or ():
                interior.place_brew(wx, wy)
            for wx, wy, kind, count, ready, grade in rec.get("barrels", ()) or ():
                b = interior.place_barrel(wx, wy)
                b["kind"] = kind or None
                b["count"] = int(count)
                b["ready_at"] = float(ready)
                b["grade"] = int(grade)
            house.interior = interior
            g.built_houses.append(house)
            if rec.get("uid"):
                ctx.houses[rec["uid"]] = house
        except Exception as exc:
            store.log("house restore FAILED: %r" % (exc,))
            continue

    for rec in data.get("fences", ()) or ():
        g.built_fences.append(codec.rect_from_data(rec))
    for rec in data.get("gates", ()) or ():
        g.built_gates.append(codec.rect_from_data(rec))
    for rec in data.get("plots", ()) or ():
        r = codec.rect_from_data(rec)
        g.built_plots.append(r)
        g.player.plots.add((r.x, r.y))
    g.player.yard_plots = [(r.x, r.y, r.w, r.h) for r in g.built_plots]

    for rec in data.get("blocks", ()) or ():
        g.built_blocks[(int(rec[0]), int(rec[1]))] = str(rec[2])

    for rec in data.get("work", ()) or ():
        try:
            wp = industry.Workplace(rec["kind"], float(rec["x"]),
                                    float(rec["y"]), int(rec.get("seed", 0)))
            codec.set_uid(wp, rec.get("uid"))
            wp.worker = None
            wp.owner = g.player
            if rec.get("leaf") is not None:
                wp.leaf = rec["leaf"]
            if rec.get("product") is not None:
                wp.product = rec["product"]
            wp.condition = float(rec.get("condition", 100.0))
            wp.max_condition = float(rec.get("max_condition", 100.0))
            wp.broken = bool(rec.get("broken", False))
            g.placed_work.append(wp)
            g.player.workplaces.append(wp)
            if rec.get("uid"):
                ctx.workplaces[rec["uid"]] = wp
            if rec.get("worker"):
                _uid = rec["worker"]
                ctx.later(lambda _w=wp, _u=_uid: _set_worker(_w, _u, ctx))
            if rec.get("artisan"):
                _uid = rec["artisan"]
                ctx.later(lambda _w=wp, _u=_uid: _set_artisan(_w, _u, ctx))
        except Exception as exc:
            store.log("work restore FAILED: %r" % (exc,))
            continue

    for rec in data.get("chests", ()) or ():
        # Older builds briefly wrote an unauthorized "camp store" chest.
        # Do not recreate it.
        if rec.get("camp_store"):
            continue
        try:
            ch = placement.Chest(float(rec["tx"]) * 32 + 16.0,
                                 float(rec["ty"]) * 32 + 16.0)
            ch.condition = float(rec.get("condition", 100.0))
            ch.max_condition = float(rec.get("max_condition", 100.0))
            ch.broken = bool(rec.get("broken", False))
            codec.set_uid(ch, rec.get("uid"))
            ch.filter = rec.get("filter")
            codec.inventory_restore(ch.inventory, rec.get("inventory"))
            ch.owner = g.player
            g.built_chests.append(ch)
            if rec.get("uid"):
                ctx.chests[rec["uid"]] = ch
        except Exception:
            continue

    for rec in data.get("signs", ()) or ():
        try:
            sg = placement.SignPost(float(rec["x"]), float(rec["y"]))
            sg.condition = float(rec.get("condition", 100.0))
            sg.max_condition = float(rec.get("max_condition", 100.0))
            sg.broken = bool(rec.get("broken", False))
            codec.set_uid(sg, rec.get("uid"))
            for key in ("farmers", "loggers", "artisans", "researchers",
                        "miners", "smiths"):
                setattr(sg, key, int(rec.get(key, 0)))
            sg.owner = g.player
            g.built_signs.append(sg)
            if rec.get("uid"):
                ctx.signs[rec["uid"]] = sg
        except Exception:
            continue

    for rec in data.get("foodboxes", ()) or ():
        try:
            fb = placement.FoodBox(float(rec["x"]), float(rec["y"]))
            fb.condition = float(rec.get("condition", 100.0))
            fb.max_condition = float(rec.get("max_condition", 100.0))
            fb.broken = bool(rec.get("broken", False))
            codec.set_uid(fb, rec.get("uid"))
            codec.inventory_restore(fb.inventory, rec.get("inventory"))
            fb.owner = g.player
            g.built_foodboxes.append(fb)
            if rec.get("uid"):
                ctx.foodboxes[rec["uid"]] = fb
        except Exception:
            continue

    for rec in data.get("designations", ()) or ():
        try:
            g.field_designations.append({
                "rect": codec.rect_from_data(rec["rect"]),
                "type": rec.get("type", "field"),
                "kind": rec.get("kind", ""),
            })
        except Exception:
            continue


def _set_worker(wp, uid: str, ctx: "_context.Context") -> None:
    p = ctx.people.get(uid)
    if p is not None:
        wp.worker = p


def _set_artisan(wp, uid: str, ctx: "_context.Context") -> None:
    p = ctx.people.get(uid)
    if p is not None:
        wp.artisan = p
        p.artisan_bench = wp


def finalize(g, ctx: "_context.Context") -> None:
    # The yard lists are derived from the work list, never stored separately.
    g.player.workplaces = [wp for wp in g.placed_work
                           if getattr(wp, "owner", None) is g.player
                           and not getattr(wp, "native", False)
                           and not getattr(wp, "camp", False)]
