#!/usr/bin/env python3
"""Headless save round-trip.

    python tools/save_selftest.py make
    python tools/save_selftest.py verify

The first run boots a new game, changes a representative slice of the world
(player, skills, pack, ship hold, research, market, a conquered camp with a
worker, a plot, a felled tree, ore, a built house with a chest, a workplace,
a fence, a field designation and a horse), saves synchronously, and writes the
expected values to /tmp/sw_expected.json.

The second run boots the same build, loads that save, and compares.  It is the
test that matters: not "the file was written", but "the world came back".
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["KINGPIN_OBSERVE"] = "1"       # no title menu, test mode, slot 0

EXPECTED = "/tmp/sw_expected.json"
REPORT = "/tmp/sw_verify.json"


def _coin(inv):
    return sum(int(s.count) for s in inv.slots
               if s is not None and s.defn.id == "coin")


def _snapshot(g):
    camp = g.native_settlement
    people = sorted(([getattr(n, "id", ""),
                      round(float(getattr(n, "x", 0.0)), 2),
                      round(float(getattr(n, "y", 0.0)), 2),
                      int(getattr(n, "health", 0)),
                      getattr(n, "job", None),
                      bool(getattr(n, "conquered", False)),
                      getattr(n, "kind", None)]
                     for n in (getattr(camp, "farmers", ()) or ())),
                    key=lambda r: r[0])
    house = next((h for h in g.built_houses
                  if getattr(h, "name", "") != ""), None)
    work = next((w for w in g.placed_work
                 if getattr(w, "kind", "") == "smith"), None)
    horse = next((h for h in g.horses if getattr(h, "conquered", False)), None)
    plots = sorted([[tx, ty, p.kind, p.planted_at]
                    for (tx, ty), p in g.world.plots.items()])
    stumps = sorted([[round(t.x, 1), round(t.y, 1)]
                     for t in g.trees.stumps()])
    mined = sorted([list(c) for c in g.ore_field.mined])
    return {
        "seed": int(g.world.seed),
        "now": round(float(g.now), 3),
        "kills": int(g.kills),
        "war_alarms": int(g.war_alarms),
        "conquered_count": int(g.conquered_count),
        "player": {
            "x": round(float(g.player.x), 3), "y": round(float(g.player.y), 3),
            "health": round(float(g.player.health), 3),
            "hunger": round(float(g.player.hunger), 3),
            "stamina": round(float(g.player.stamina), 3),
            "armor": g.player.armor,
            "facing": [round(float(v), 3) for v in g.player.facing],
        },
        "skills": {k: round(float(getattr(g.skills, k)), 4)
                   for k in ("farming", "movement", "axe", "shooting",
                             "research", "smithing")},
        "coins": _coin(g.inventory),
        "cigar": int(g.inventory.count_of("cigar")),
        "iron": int(g.inventory.count_of("iron")),
        "ship_bar": int(g.ship_hold.count_of("iron_bar")),
        "ship_coin": int(g.ship_hold.count_of("coin")),
        "active_card": g.research_active,
        "card_animals": g.research_cards.get("animals"),
        "research_points": round(float(g.research_points), 3),
        "market_cigar": round(float(g.market["base"].get("cigar", 0.0)), 5),
        "market_sold": int(g.market["sold_today"].get("cigar", 0)),
        "compass": (list(g.compass_state.home)
                    if g.compass_state.home else None),
        "camp_uid": getattr(camp, "_save_uid", None),
        "camp_conquered": bool(getattr(camp, "conquered", False)),
        "camp_people": people,
        "mind": (None if not (getattr(camp, "farmers", ()) or ()) else {
            "mbti": getattr(camp.farmers[0], "mbti", ""),
            "traits": sorted(getattr(camp.farmers[0], "traits", ()) or ()),
            "trauma_points": round(float(getattr(camp.farmers[0],
                                               "trauma_points", 0.0)), 3),
            "medicines_received": int(getattr(camp.farmers[0],
                                               "medicines_received", 0)),
            "mental_known": bool(getattr(camp.farmers[0], "mental_known", False)),
            "mood_target": round(float(getattr(camp.farmers[0],
                                                "mood_target", 50.0)), 3),
            "mood_thoughts": dict(getattr(camp.farmers[0],
                                          "mood_thoughts", {}) or {}),
            "break_state": getattr(camp.farmers[0], "break_state", "normal"),
            "frustration": round(float(getattr(camp.farmers[0],
                                                "frustration", 0.0)), 3),
        }),
        "camp_workers": [getattr(n, "id", "") for n in
                         (getattr(camp, "workers", ()) or ())],
        "camp_no_make": (sorted(__import__("work").banned(camp.farmers[0]))
                         if getattr(camp, "farmers", None) else []),
        "camp_no_sell": (sorted(__import__("work").not_sold(camp.farmers[0]))
                         if getattr(camp, "farmers", None) else []),
        "camp_ledger": sorted([[k, int(v)] for k, v in
                               (getattr(camp, "ledger_lots", {}).get(
                                   "cigar", {}) or {}).items()]),
        "camp_pool": (len(camp.people) if isinstance(
            getattr(camp, "people", None), list) else -1),
        "camp_farm_plots": len(getattr(camp, "farm_plots", ()) or ()),
        "camp_farm_tiles": len(getattr(camp, "farm_tiles", ()) or ()),
        "orchard": sorted([[int(tx), int(ty),
                            round(float(st["tree"].canopy_r), 2)]
                           for (tx, ty), st in
                           (getattr(camp, "orchard_state", {}) or {}).items()
                           if st and st.get("tree") is not None]),
        "plots": plots,
        "stumps": stumps,
        "ore": mined,
        "house": (None if house is None else {
            "uid": getattr(house, "_save_uid", None),
            "x": round(float(house.x), 1), "y": round(float(house.y), 1),
            "chest_coins": _coin(house.interior.chest),
        }),
        "work": (None if work is None else {
            "uid": getattr(work, "_save_uid", None),
            "kind": work.kind, "x": round(float(work.x), 1),
            "y": round(float(work.y), 1),
        }),
        "fences": len(g.built_fences),
        "gates": len(g.built_gates),
        "blocks": len(g.built_blocks),
        "designations": len(g.field_designations),
        "chests": len(g.built_chests),
        "signs": len(g.built_signs),
        "foodboxes": len(g.built_foodboxes),
        "riding": getattr(getattr(g, "riding", None), "_save_uid", None),
        "riding_ok": (getattr(g, "riding", None) is horse),
        "bond_ok": (len(getattr(camp, "farmers", ()) or ()) < 2
                    or camp.farmers[0].bond_partner is camp.farmers[1]),
        "home_house_ok": (len(getattr(camp, "farmers", ()) or ()) < 1
                          or camp.farmers[0].home_house is house),
        "work_worker_ok": (work is None or getattr(work, "worker", None)
                           is (camp.farmers[2] if len(camp.farmers) >= 3 else None)),
        "bond": (None if len(getattr(camp, "farmers", ()) or ()) < 2
                 else [getattr(camp.farmers[0], "_save_uid", None),
                       getattr(camp.farmers[1], "_save_uid", None)]),
        "work_worker": getattr(getattr(work, "worker", None), "_save_uid", None),
        "horse": (None if horse is None else {
            "uid": getattr(horse, "_save_uid", None),
            "coat": horse.coat, "kind": horse.kind,
            "x": round(float(horse.x), 1), "y": round(float(horse.y), 1),
            "coins": round(float(getattr(horse, "coins", 0.0)), 3),
            "pack_iron": int(horse.pack.count_of("iron")) if horse.pack else 0,
        }),
        "player_camps": [getattr(c, "_save_uid", None)
                         for c in (g.player_camps or ())],
    }


def _make(g):
    import placement
    import industry
    import inventory
    import items
    from village import House, ROOFS

    camp = g.native_settlement
    g.player.x = float(camp.x) + 40.0
    g.player.y = float(camp.y) + 40.0
    g.player.facing = (0.3, 0.4)
    g.player.health = 77.0
    g.player.hunger = 42.0
    g.player.stamina = 13.5
    g.player.equip_armor("hide_armor")
    g.player.health = 77.0
    for name, value in (("farming", 2.5), ("movement", 0.22),
                        ("axe", 0.37), ("shooting", 0.4),
                        ("research", 3.0), ("smithing", 1.5)):
        setattr(g.skills, name, value)
    g.player.skills = g.skills

    g.inventory.add("coin", 123)
    g.inventory.add("cigar", 7, quality=5)
    g.inventory.add("iron", 12)
    g.inventory.select(2)
    g.panel.held = inventory.ItemStack(items.get("axe"), 1)

    g.ship_hold.add("iron_bar", 5)
    g.ship_hold.add("coin", 9)

    g.research_cards["animals"] = "done"
    g.research_cards["hide_armor"] = "researching"
    g.research_active = "hide_armor"
    g.research_points = 55.5
    g.market["base"]["cigar"] = 0.22
    g.market["sold_today"]["cigar"] = 37
    g.market["history"]["cigar"].append(0.21)
    g.compass_state.home = (1234.5, -678.0)
    g.compass_state.mode = "home"

    g.now = 12345.5
    g.kills = 9
    g.war_alarms = 2

    g.conquer_camp(g, camp)
    g.conquered_count = 1
    if getattr(camp, "farmers", None):
        worker = camp.farmers[0]
        worker.conquered = True
        worker.job = "farmer"
        worker.native_role = "farmer"
        camp.workers.append(worker)
        # NPC mind fields: the round-trip must carry the new data too.
        worker.mbti = "INTJ"
        worker.traits = ["smart"]
        worker.trauma_points = 12.5
        worker.medicines_received = 2
        worker.mental_known = True
        worker.mood_target = 44.0
        worker.mood_thoughts = {"hungry": {"delta": -6.0, "stacks": 2}}
        worker.break_state = "annoyed"
        worker.frustration = 3.0

    px, py = float(g.player.x), float(g.player.y)
    tx, ty = int(px // 32) + 3, int(py // 32) + 4
    g.world.set_plot(tx, ty, "wheat", g.now - 60.0)
    g.world.set_tile(tx + 1, ty, "dirt")
    g.world.wild_removed.add((tx + 2, ty))

    t = g.trees.plant(px + 260.0, py + 260.0, 70.0, 1, "conifer", True)
    g.trees.fell(t, g.now)
    try:
        ore = g.ore_field.near(px, py, 2600.0)
        if ore:
            ore[0].strikes = 13
            g.ore_field.mined.add(ore[0].cell)
    except Exception:
        pass

    h = House(px + 320.0, py + 220.0, 180, 140, ROOFS[0],
              (0.0, 1.0), 4242)
    h.enterable = True
    from interior import Interior
    h.interior_seed = 4243
    h.interior = Interior(h.interior_seed, tuple(h.facing))
    g.built_houses.append(h)
    h.interior.chest.add("coin", 7)
    h.interior.chest.add("bread", 3)

    wp = industry.Workplace("smith", px + 120.0, py - 80.0, 777)
    wp.owner = g.player
    g.placed_work.append(wp)
    if not isinstance(g.player.workplaces, list):
        g.player.workplaces = []
    g.player.workplaces.append(wp)

    chest = placement.Chest(px + 80.0, py + 80.0)
    chest.inventory.add("wood", 4)
    g.built_chests.append(chest)
    sign = placement.SignPost(px + 60.0, py + 120.0)
    sign.farmers = 1
    g.built_signs.append(sign)
    fb = placement.FoodBox(px + 140.0, py + 120.0)
    fb.inventory.add("bread", 2)
    g.built_foodboxes.append(fb)
    import pygame
    g.built_fences.append(pygame.Rect(int(px - 100), int(py - 100), 32, 32))
    g.built_gates.append(pygame.Rect(int(px + 100), int(py - 100), 32, 32))
    g.built_plots.append(pygame.Rect(tx * 32, ty * 32, 64, 64))
    g.built_blocks[(int(px // 32), int(py // 32))] = "wood"
    g.field_designations.append({
        "rect": pygame.Rect(tx * 32, ty * 32, 96, 96),
        "type": "field", "kind": "wheat",
    })

    otx, oty = tx + 8, ty + 8
    otree = g.trees.plant(otx * 32.0 + 16.0, oty * 32.0 + 16.0,
                          72.0, 2, "conifer", True)
    camp.orchard_plots = [(otx, oty)]
    camp.orchard_tiles = {(otx, oty): [(otx, oty)]}
    camp.orchard_state = {(otx, oty): {"tree": otree, "target_r": 72.0,
                                        "planted_at": g.now - 50.0}}

    horse = __import__("creatures").Horse(px + 200.0, py + 200.0, "black")
    horse.conquered = True
    horse.coins = 4.5
    horse.pack = inventory.Inventory(8)
    horse.pack.add("iron", 6)
    g.horses.append(horse)

    # Cross-references: a worker at a bench, a bond, a house, and a man on
    # a horse.  These are the things an index-based save loses.
    camp.ledger_goods["cigar"] = 12
    camp.ledger_lots["cigar"] = {4: 7, 6: 5}
    camp.ledger_grade["cigar"] = 5
    if getattr(camp, "farmers", None):
        import work
        work.banned(camp.farmers[0]).add("cigar")
        work.not_sold(camp.farmers[0]).add("beer")
    if len(camp.farmers) >= 3:
        camp.farmers[0].bond_partner = camp.farmers[1]
        camp.farmers[0].home_house = h
        wp.worker = camp.farmers[2]
    g.riding = horse
    g.player.x, g.player.y = float(horse.x), float(horse.y)

    # The uids are assigned by the first snapshot; do it here so the expected
    # values include the same stable ids the verify run will see.
    from save import codec as _codec
    _codec.uid(camp, "camp")
    _codec.uid(h, "house")
    _codec.uid(wp, "work")
    _codec.uid(chest, "chest")
    _codec.uid(sign, "sign")
    _codec.uid(fb, "foodbox")
    _codec.uid(horse, "animal")
    for _n in (getattr(camp, "farmers", ()) or ()):
        _codec.uid(_n, "person")

    expected = _snapshot(g)
    with open(EXPECTED, "w") as fh:
        json.dump(expected, fh, indent=1, sort_keys=True)
    import save as savemod
    savemod.save_now(g, "selftest")
    print("MAKE: wrote %s" % EXPECTED)
    print("MAKE: seed=%s camps=%d people=%d plots=%d"
          % (expected["seed"], 1, len(expected["camp_people"]),
             len(expected["plots"])))


def _verify(g):
    with open(EXPECTED) as fh:
        expected = json.load(fh)
    actual = _snapshot(g)
    with open(REPORT, "w") as fh:
        json.dump(actual, fh, indent=1, sort_keys=True)
    problems = []

    def compare(path, want, got):
        if want != got:
            problems.append("%s: want %r got %r" % (path, want, got))

    for key in expected:
        compare(key, expected[key], actual.get(key))
    if problems:
        print("VERIFY: %d PROBLEM(S)" % len(problems))
        for line in problems[:40]:
            print("  " + line)
        raise SystemExit(1)
    print("VERIFY: OK -- %d fields match" % len(expected))
    print("VERIFY: report %s" % REPORT)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "make"
    import persist
    import save as savemod
    persist.set_test(True)
    persist.set_slot(0)
    if mode == "make":
        savemod.delete(0)
    import engine
    import main as gamemain

    def fake_run(g):
        if mode == "make":
            _make(g)
        else:
            _verify(g)

    engine.run = fake_run
    gamemain.main()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()
        raise
