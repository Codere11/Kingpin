"""savegame.py -- WRITE AND READ THE PLAYER'S WORLD.

One payload, built from a small namespace of the live game, written as pickle
and read back onto a freshly laid out world. Extracted from main.py.
"""

from __future__ import annotations

import persist
import stall as stall_mod
import corpse as corpse_mod
import folders as folders_mod
import work as work
import worldio


def write(g) -> None:
    houses = []
    for house in g.built_houses:
        if getattr(house, "camp", False):
            continue
        interior = getattr(house, "interior", None)
        chest = getattr(interior, "chest", None) if interior is not None else None
        houses.append({
            "x": house.x, "y": house.y, "w": house.w, "h": house.h,
            "roof": list(house.roof), "facing": list(house.facing),
            "seed": getattr(house, "build_seed", 0),
            "interior_seed": getattr(house, "interior_seed", 0),
            "chest": ([persist.stack_to_data(s) for s in chest.slots]
                      if chest is not None else []),
            "workshops": ([[r.centerx, r.centery] for r in interior.workshops]
                          if interior is not None else []),
            "labs": ([[r.centerx, r.centery] for r in interior.lab_tables]
                     if interior is not None else []),
            "brews": ([[r.centerx, r.centery] for r in interior.brew_tables]
                      if interior is not None else []),
            "barrels": ([[b["rect"].centerx, b["rect"].centery,
                          b.get("kind") or "", int(b.get("count", 0)),
                          float(b.get("ready_at", 0.0)), int(b.get("grade", 0))]
                         for b in interior.barrels]
                        if interior is not None else []),
        })
    village_state = {}
    for (gx, gy), v in g.villages._cache.items():
        broken = [i for i, h in enumerate(v.houses)
                  if getattr(h, "door_broken", False)]
        if v.conquered or v.plundered or v.chaos > 0.0 or broken:
            village_state["%d,%d" % (gx, gy)] = {
                "conquered": bool(v.conquered),
                "plundered": bool(v.plundered),
                "chaos": float(v.chaos),
                "nation": int(v.nation),
                "broken": broken,
                "gaps": [[int(s), float(c), float(hw)]
                         for s, c, hw in v.fence_gaps],
            }
    squad = []
    for s in g.player.squad:
        if getattr(s, "alive", False):
            squad.append({"x": s.x, "y": s.y,
                          "march": list(s.march_target) if s.march_target else None})
    payload = {
        "seed": g.world.seed,
        "houses": houses,
        "player": {
            "x": (g.inside_house.x if g.inside_house is not None else g.player.x),
            "y": ((g.inside_house.y + g.inside_house.h / 2.0 + 20.0)
                  if g.inside_house is not None else g.player.y),
            "health": g.player.health, "hunger": g.player.hunger,
            "stamina": g.player.stamina, "bleed": g.player.bleed,
            "nation": (int(g.player.nation) if g.player.nation is not None
                       else None),
            "selected": g.inventory.selected,
        },
        "inventory": [persist.stack_to_data(s) for s in g.inventory.slots],
        "held": persist.stack_to_data(g.panel.held),
        "skills": {"farming": g.skills.farming, "movement": g.skills.movement,
                   "axe": g.skills.axe, "shooting": g.skills.shooting},
        "now": g.now,
        "kills": g.kills,
        "plots": [[tx, ty, plot.kind, plot.planted_at]
                  for (tx, ty), plot in g.world.plots.items()],
        "wild": [[tx, ty] for (tx, ty) in g.world.wild_removed],
        "wild_eaten": [[tx, ty, float(when)]
                       for (tx, ty), when in
                       (getattr(g.world, "wild_eaten", {}) or {}).items()],
        "stumps": [[round(t.x, 1), round(t.y, 1), float(t.felled_at)]
                   for t in g.trees.stumps()],
        "compass_home": (list(g.compass_state.home)
                         if g.compass_state.home is not None else None),
        "ore": [[cx, cy] for (cx, cy) in g.ore_field.mined],
        "tiles": [[tx, ty, kind] for (tx, ty), kind in g.world._overrides.items()],
        "villages": village_state,
        "squad": squad,
        "fences": [[r.x, r.y, r.w, r.h] for r in g.built_fences],
        "gates": [[r.x, r.y, r.w, r.h] for r in g.built_gates],
        "yard_plots": [[r.x, r.y, r.w, r.h] for r in g.built_plots],
        "yard_work": [[wp.kind, wp.x, wp.y] for wp in g.placed_work
                      if not getattr(wp, "is_stall", False)
                      and not getattr(wp, "camp", False)
                      and abs(getattr(wp, "x", 0.0)) < 400000.0
                      and abs(getattr(wp, "y", 0.0)) < 400000.0],
        "stalls": stall_mod.to_data(g.player),
        "corpses": corpse_mod.to_data(),
        "folders": folders_mod.to_data(),
        "market_workers": [getattr(n, "id", None)
                           for n in (getattr(g.player, "workers", ()) or ())
                           if getattr(n, "to_market", False)],
        "worker_no_make": {str(getattr(n, "id", "")): sorted(work.banned(n))
                           for n in (getattr(g.player, "workers", ()) or ())
                           if work.banned(n)},
        "worker_no_sell": {str(getattr(n, "id", "")): sorted(work.not_sold(n))
                           for n in (getattr(g.player, "workers", ()) or ())
                           if work.not_sold(n)},
        "yard_hub": [[h.fence_rect.x, h.fence_rect.y,
                      h.fence_rect.w, h.fence_rect.h]
                     for h in g.hub_world.hubs
                     if getattr(h, "is_player_hub", False)],
        "workers": [getattr(n, "id", None)
                    for n in (getattr(g.player, "workers", ()) or ())
                    if getattr(n, "alive", False)],
        "train": (None if g.train[0] is None else {
            "route": [[float(a), float(b)] for a, b in g.train[0].route],
            "i": int(g.train[0].i),
            "t": float(g.train[0].t),
            "angle": float(g.train[0].angle),
            "x": float(g.train[0].x),
            "y": float(g.train[0].y),
            "done": bool(g.train[0].done),
            "travelled": float(g.train[0].travelled),
            "aboard": list(getattr(g.train[0], "aboard", []) or []),
            "player_aboard": bool(getattr(g.player, "aboard", False)),
        }),
        "world": worldio.world_to_data(g.villages),
    }
    if not persist.write_binary(payload):
        persist.write(payload)
