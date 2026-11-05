"""savegame.py -- WRITE AND READ THE PLAYER'S WORLD.

One payload, built from a small namespace of the live game, written as pickle
and read back onto a freshly laid out world. Extracted from main.py.
"""

from __future__ import annotations

import random

import pygame
import plog
import nemesis
import industry
import persist
import stall as stall_mod
import corpse as corpse_mod
import folders as folders_mod
import work as work
import worldio
import war
import village as village_mod
from creatures import Soldier
from interior import Interior
from village import House


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


def restore(g) -> None:
    """Put a save back onto the live world. Mutates g's objects in place and
    leaves the new camera on g.cam_x / g.cam_y for the caller to take."""
    data = persist.read_binary()
    if data is None:
        data = persist.read()            # an older save, in JSON
    # THE WORLD FIRST, so everything below can rely on it, and so a load
    # is a load: the people, their skills, their coin, their towns.
    worldio.world_from_data(g.villages, data.get("world"))
    # ONE MAN, ONE PLACE. A save stores his town and his road separately,
    # so a restored traveller could come back on the roll of the town he
    # left as well as on the road. This is where that is made true.
    village_mod.rebuild_people(g.villages)
    village_mod.rebuild_houses(g.villages)
    for _v in g.villages._cache.values():
        for _n in _v.npcs:
            if not (_n.alive and _n.job == "soldier" and not _n.levied):
                continue
            _sol = Soldier(_n.x, _n.y, _v.nation,
                           melee=not getattr(_n, "ranged", False),
                           seed=random.randint(0, 2 ** 31))
            _sol.name = _n.name
            _sol.skills = _n.skills
            _sol.home_npc = _n
            _sol.home_village = _v
            _sol.patrol_center = (_v.x, _v.y)
            _sol.patrol_r = _v.radius * 0.6
            _sol.garrison_of = _v
            _sol.in_army = True
            war.STANDING.append(_sol)
            g.enemies.append(_sol)
    for entry in data.get("houses", []):
        try:
            # A CAMP BUILDING IN THE SAVE IS NOT HIS: the camp is rebuilt
            # from the seed, so an older save's copy of the barn or its
            # barracks would stand there twice.
            if (abs(float(entry.get("x", 0.0))) > 400000.0
                    or abs(float(entry.get("y", 0.0))) > 400000.0):
                continue
            house = House(entry["x"], entry["y"], entry["w"], entry["h"],
                          tuple(entry["roof"]), tuple(entry["facing"]),
                          entry["seed"])
            house.build_seed = entry["seed"]
            house.interior_seed = entry.get("interior_seed", 0)
            interior = Interior(house.interior_seed, tuple(house.facing))
            chest = interior.chest
            for i, datum in enumerate(entry.get("chest", [])):
                if i < len(chest.slots):
                    chest.slots[i] = persist.data_to_stack(datum)
            for wx, wy in entry.get("workshops", []):
                interior.place_workshop(wx, wy)
            for wx, wy in entry.get("labs", []):
                interior.place_lab(wx, wy)
            for wx, wy in entry.get("brews", []):
                interior.place_brew(wx, wy)
            for wx, wy, _k, _n, _r, _g in entry.get("barrels", []):
                _b = interior.place_barrel(wx, wy)
                _b["kind"] = _k or None
                _b["count"] = int(_n)
                _b["ready_at"] = float(_r)
                _b["grade"] = int(_g)
            house.enterable = True       # your own houses stay open
            house.door_broken = True
            house.interior = interior
            g.built_houses.append(house)
        except Exception:
            continue

    p = data.get("player")
    if p:
        g.player.x = float(p.get("x", g.player.x))
        g.player.y = float(p.get("y", g.player.y))
        # A SAVE FROM AN OLDER BUILD may hold room coordinates (700,700)
        # -- which in the world is the middle of the map. Those are not a
        # world position at all, so he is put back at the camp instead.
        _sx = float(p.get("x", g.player.x))
        _sy = float(p.get("y", g.player.y))
        if abs(_sx) < 5000.0 and abs(_sy) < 5000.0:
            try:
                import gulag as _gl
                _sx, _sy = _gl.middle()[0] + 220.0, _gl.middle()[1] + 260.0
                plog.log("SAVE-POS-FIX", "interior coordinates in the save;"
                         " restored at the camp")
            except Exception:
                pass
        g.player.x, g.player.y = _sx, _sy
        g.player.health = max(1.0, float(p.get("health", g.player.health)))
        g.player.hunger = float(p.get("hunger", g.player.hunger))
        g.player.stamina = float(p.get("stamina", g.player.stamina))
        g.player.bleed = float(p.get("bleed", 0.0))
        g.player.dead = False
        nation = p.get("nation")
        g.player.nation = int(nation) if nation is not None else None
        g.inventory.selected = int(p.get("selected", 0))
        g.cam_x = g.player.x - g.width / (2.0 * g.zoom)
        g.cam_y = g.player.y - g.height / 2.0
    if data.get("inventory"):
        for i, datum in enumerate(data["inventory"]):
            if i < len(g.inventory.slots):
                g.inventory.slots[i] = persist.data_to_stack(datum)
    g.panel.held = persist.data_to_stack(data.get("held"))
    for fx0, fy0, fw, fh in data.get("fences", []):
        g.built_fences.append(pygame.Rect(int(fx0), int(fy0), int(fw), int(fh)))
    for gx0, gy0, gw, gh in data.get("gates", []):
        g.built_gates.append(pygame.Rect(int(gx0), int(gy0), int(gw), int(gh)))
    # THE TRAIN, RIGHT WHERE IT WAS, WITH WHOEVER WAS ON IT.
    _trd = data.get("train")
    if _trd and g.train[0] is not None:
        _tr = g.train[0]
        _route = [(float(a), float(b)) for a, b in _trd.get("route", [])]
        if _route:
            _tr.route = _route
            _tr.i = min(int(_trd.get("i", 0)), max(0, len(_route) - 2))
            _tr.t = float(_trd.get("t", 0.0))
            _tr.angle = float(_trd.get("angle", 0.0))
            _tr.x = float(_trd.get("x", _tr.x))
            _tr.y = float(_trd.get("y", _tr.y))
            _tr.done = bool(_trd.get("done", False))
            _tr.travelled = float(_trd.get("travelled", 0.0))
            _tr.aboard = list(_trd.get("aboard", []) or [])
        if _trd.get("player_aboard"):
            g.player.aboard = True
            g.player.x, g.player.y = _tr.x, _tr.y
        plog.log("TRAIN-RESTORED", "at", int(_tr.x), int(_tr.y),
                 "aboard", len(getattr(_tr, "aboard", []) or []),
                 "player", bool(getattr(g.player, "aboard", False)))
    # ---- THE YARD, BACK ----
    # Plots, benches and the hub they make of his ground, plus the men he
    # pays. Everything is cleared first, so loading twice in one session
    # does not double the yard.
    g.built_plots.clear()
    g.placed_work.clear()
    g.player.workplaces = []
    g.player.plots = set()
    g.player.workers = []
    g.hub_world.hubs[:] = [h for h in g.hub_world.hubs
                         if not getattr(h, "is_player_hub", False)]
    nemesis.PLACES[:] = [p for p in nemesis.PLACES
                         if not getattr(p, "is_player_hub", False)]
    for _rec in data.get("yard_plots", []):
        _r = pygame.Rect(*[int(v) for v in _rec])
        g.built_plots.append(_r)
        g.player.plots.add((_r.x, _r.y))
        g.player.yard_plots = [tuple(_rp) for _rp in g.built_plots]
    for _rec in data.get("yard_work", []):
        try:
            _kind, _x, _y = _rec
            if abs(float(_x)) > 400000.0 or abs(float(_y)) > 400000.0:
                continue          # the camp is rebuilt, never restored
            if _kind == "stall":
                continue                 # restored from `stalls`, below
            _wp = industry.Workplace(_kind, float(_x), float(_y),
                                     abs(hash((_kind, _x, _y)))
                                     & 0x7FFFFFFF)
            _wp.worker = None
            _wp.owner = g.player
            g.placed_work.append(_wp)
            g.player.workplaces.append(_wp)
        except Exception as _we:
            plog.log("YARD-WORK-ERROR", repr(_we)[:160])
    # THE CAMP, PUT BACK AFTER THE SAVE HAS CLEARED THE YARD.
    try:
        import gulag as _g2
        for _o in _g2.works():
            if _o not in g.placed_work:
                g.placed_work.append(_o)
        _b2 = _g2.prison()
        if _b2 is not None and _b2 not in g.placed_work:
            g.placed_work.append(_b2)
        for _o in _g2.houses():
            if _o not in g.built_houses:
                g.built_houses.append(_o)
        for _o in _g2.walls():
            if _o not in g.camp_walls:
                g.camp_walls.append(_o)
        try:
            import holding as _h2
            for _c in _h2.cells():
                if _c not in g.placed_work:
                    g.placed_work.append(_c)
        except Exception:
            pass
    except Exception as _ae:
        plog.log("CAMP-ATTACH-ERR", repr(_ae)[:140])
    for _rec in data.get("yard_hub", []):
        _h = g.hub_world.add_player_hub(
            g.player, pygame.Rect(*[int(v) for v in _rec]), [], [])
        if _h is not None:
            nemesis.PLACES.append(_h)
            g.player.work_post = (_h.x, _h.y + 40)
            g.player.hub = _h
    # THE STALLS, after the hubs (a stall looks for its yard).
    try:
        g.player.stalls = []
        for _st in stall_mod.from_data(g.player, data.get("stalls"),
                                       g.hub_world.hubs):
            _hub = getattr(_st, "hub", None)
            if (_hub is None
                    or not _hub.fence_rect.colliderect(_st.rect)):
                plog.log("STALL-DROPPED", "at",
                         "%d,%d" % (int(_st.x), int(_st.y)),
                         "-- not inside a hub of his")
                stall_mod.stalls_of(g.player).remove(_st)
                continue
            g.placed_work.append(_st)
    except Exception as _se:
        plog.log("STALL-RESTORE-ERROR", repr(_se)[:200])
    # THE DEAD, BACK WHERE THEY FELL. Aged as they were: a man three days
    # dead comes back as a body two days old, not a fresh one.
    try:
        corpse_mod.from_data(data.get("corpses"))
        folders_mod.from_data(data.get("folders"))
    except Exception as _ce:
        plog.log("CORPSE-RESTORE-ERROR", repr(_ce)[:160])
    _want_workers = set(data.get("workers", ()) or ())
    if _want_workers:
        for _v in list(g.villages._cache.values()):
            for _n in _v.npcs:
                if getattr(_n, "id", None) in _want_workers and _n.alive:
                    g.player.workers.append(_n)
                    # ...and they march to the yard they were hired for.
                    _n.work_post = getattr(g.player, "work_post", None)
    _market = set(data.get("market_workers", ()) or ())
    _nomake = data.get("worker_no_make", {}) or {}
    _nosell = data.get("worker_no_sell", {}) or {}
    for _n in (getattr(g.player, "workers", ()) or ()):
        if getattr(_n, "id", None) in _market:
            _n.to_market = True
        for _it in _nomake.get(str(getattr(_n, "id", "")), ()) or ():
            work.set_banned(_n, _it, True)
        for _it in _nosell.get(str(getattr(_n, "id", "")), ()) or ():
            work.set_not_sold(_n, _it, True)
    plog.log("YARD", "plots", len(g.built_plots), "work", len(g.placed_work),
             "hubs", len([h for h in g.hub_world.hubs
                          if getattr(h, "is_player_hub", False)]),
             "workers", len(g.player.workers),
             "stalls", len(stall_mod.stalls_of(g.player)))
    if data.get("skills"):
        sk = data["skills"]
        g.skills.farming = float(sk.get("farming", 0.0))
        g.skills.movement = float(sk.get("movement", 0.0))
        g.skills.axe = float(sk.get("axe", 0.0))
        g.skills.shooting = float(sk.get("shooting", 0.0))
    g.now = float(data.get("now", g.now))
    g.kills = int(data.get("kills", g.kills))
    for tx, ty, kind, planted in data.get("plots", []):
        g.world.set_plot(int(tx), int(ty), kind,
                       None if planted is None else float(planted))
    for tx, ty in data.get("wild", []):
        g.world.wild_removed.add((int(tx), int(ty)))
    for _rec in (data.get("wild_eaten", ()) or ()):
        try:
            g.world.wild_eaten[(int(_rec[0]), int(_rec[1]))] = float(_rec[2])
        except Exception:
            continue
    # ...and the stumps that were standing when he left: same trees, same
    # age, so the clock that brings them back has not been reset.
    _stumps = data.get("stumps", ()) or ()
    for _rec in _stumps:
        try:
            _sx, _sy, _at = float(_rec[0]), float(_rec[1]), float(_rec[2])
        except Exception:
            continue
        _t = next((_c for _c in g.trees.near(_sx, _sy, 60.0)
                   if abs(_c.x - _sx) < 1.0 and abs(_c.y - _sy) < 1.0), None)
        if _t is not None and not _t.felled:
            _t.felled = True
            _t.felled_at = _at
            trees.remember_stump(_t)
    if _stumps:
        plog.log("STUMPS", "restored", len(_stumps))
    ch = data.get("compass_home")
    if ch:
        compass_state.home = (float(ch[0]), float(ch[1]))
    for cx, cy in data.get("ore", []):
        ore_field.mined.add((int(cx), int(cy)))
    for tx, ty, kind in data.get("tiles", []):
        g.world.set_tile(int(tx), int(ty), kind)
    # The ground was already built from the seed before any of this was
    # restored, so every worked tile and every built floor in the world was
    # missing from it. Rebuild what the g.player can see, once, now -- rather
    # than letting a queued job trickle in behind a blur.
    # THE GROUND IS BUILT UNDER THE MAN BEING WATCHED TOO.
    #
    # refresh_around() was called with g.player.x/g.player.y, and the camera now
    # goes to the watched man -- so at his position the ground had never
    # been generated at all and the view was BLACK. Same mistake as the
    # vision eye below, in a different cache.
    _wt = g.observer_.target
    if _wt is not None and getattr(_wt, "alive", False):
        g.ground.refresh_around(_wt.x, _wt.y, g.width, g.height)
    else:
        g.ground.refresh_around(g.player.x, g.player.y, g.width, g.height)
    for key, st in data.get("villages", {}).items():
        try:
            gx, gy = (int(v) for v in key.split(","))
            v = g.villages.get(gx, gy)
            v.conquered = bool(st.get("conquered", False))
            v.plundered = bool(st.get("plundered", False))
            v.chaos = float(st.get("chaos", 0.0))
            nation = st.get("nation")
            if nation:
                v.nation = int(nation)
            for i in st.get("broken", []):
                if 0 <= i < len(v.houses) and not v.houses[i].door_broken:
                    h = v.houses[i]
                    h.enterable = True
                    h.interior = Interior(random.randint(0, 2 ** 31),
                                          tuple(h.facing))
                    fill_loot(h.interior.chest)
                    h.break_door()
            if st.get("gaps"):
                v.fence_gaps = [(int(s), float(c), float(hw))
                                for s, c, hw in st["gaps"]]
            # EVERY TOWN'S FENCE IS RE-CUT ON LOAD. The walls are
            # precomputed rectangles, and a save or cache written when a
            # town had TWO openings kept two openings for ever -- the
            # extra gates existed in gate_list and in the code and were
            # walled shut on screen.
            try:
                fence.rebuild(v)
            except Exception:
                pass
            if v.conquered:
                for npc in v.npcs:
                    npc.nation = v.nation
                    npc.team = ("nation", v.nation)
            if v.chaos > 0.0:
                g.active_chaos.append(v)
        except Exception:
            continue
    squad_data = data.get("squad", [])
    if squad_data and g.player.nation is not None:
        squad = make_squad(g.player.nation, g.player.x, g.player.y, len(squad_data),
                           color=nation_color(g.player.nation))
        for soldier, entry in zip(squad, squad_data):
            soldier.x = float(entry.get("x", soldier.x))
            soldier.y = float(entry.get("y", soldier.y))
            march = entry.get("march")
            if march:
                soldier.march_target = (float(march[0]), float(march[1]))
        g.enemies.extend(squad)
        g.player.squad = squad
