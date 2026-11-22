"""people.py -- one man's state, written as plain data and read back.

The NPC class is the hot path and the most decorated object in the game: a
mixture of ordinary fields, Cython cdef fields, caches, references to other
objects, and per-frame visual timers.  The codec reads every *simple* field
(the cdef ones included), and this module names the references and the
transient caches explicitly.  A field added tomorrow is saved automatically
if it is a number, flag, string, or small container.
"""

from __future__ import annotations

import random

from . import codec
from . import context as _context

# Things that are not this man's persistent state: live object references,
# caches rebuilt from the world, per-frame animation timers, and the RNG.
SKIP = {
    "rng", "skills", "pack", "uid", "refs",
    "village", "native_camp", "home_house", "home_door", "workplace",
    "refuge", "social_target", "bond_partner", "breed_partner",
    "artisan_bench",
    "escort_horse", "_log_tree",
    "_field_task", "_trunks_cache", "_trunks_dirty", "_trunks_tick",
    "_trunks_built", "_orchard_task", "_orchard_task_tick",
    "_interior_rect", "_interior_colliders", "_saved", "_market_spot",
    "_dir", "_steer_slot", "_steer_timer", "_stuck_t", "_detour",
    "_gate_try", "_last_phase", "_dead_settled", "_px", "_py",
    "_body_follows_skill", "threats", "threat_list", "_attack_target",
    "hit_flash", "work_flash", "attack_flash", "hurt_flash",
    "level_flash", "sly_flash", "drip_timer", "panic", "pause", "stuck",
    "attack_cd", "reload_timer", "swing_anim", "lunge", "lunge_cd",
    "attacked_flash", "sleep_t", "_dead_here", "_field_claimed",
    "_last_work", "_last_say", "_wander", "_wander_t", "_camp_t",
    "_social_t", "_shop_t", "_idle_t", "_stuck_from", "_fed_round",
    "knows", "witness_to", "no_make", "no_sell", "_rects", "_fences",
    "_player", "_soldiers",
    "_blood", "_target", "_colliders",
}


def snapshot(n) -> dict:
    data = codec.dump_fields(n, skip=SKIP, label="NPC")
    data["uid"] = codec.uid(n, "person")
    data["id"] = getattr(n, "id", "")
    data["skills"] = codec.skills_to_data(getattr(n, "skills", None))
    data["pack"] = codec.inventory_to_data(getattr(n, "pack", None))
    try:
        import work
        data["no_make"] = sorted(work.banned(n))
        data["no_sell"] = sorted(work.not_sold(n))
    except Exception:
        data["no_make"] = []
        data["no_sell"] = []
    data["refs"] = {
        "camp": codec.idref(getattr(n, "native_camp", None), "camp"),
        "house": codec.idref(getattr(n, "home_house", None), "house"),
        "work": codec.idref(getattr(n, "workplace", None), "work"),
        "bond": codec.idref(getattr(n, "bond_partner", None), "person"),
        "breed": codec.idref(getattr(n, "breed_partner", None), "person"),
        "escort": codec.idref(getattr(n, "escort_horse", None), "animal"),
        "bench": codec.idref(getattr(n, "artisan_bench", None), "work"),
    }
    return data


def _find_existing(ctx: "_context.Context", rec: dict, pool):
    want = rec.get("uid")
    if want and want in ctx.people:
        return ctx.people[want]
    ident = rec.get("id")
    if ident:
        for n in pool:
            if getattr(n, "id", None) == ident:
                return n
    return None


def restore(n, rec: dict, ctx: "_context.Context") -> object:
    codec.set_uid(n, rec.get("uid"))
    codec.load_fields(n, rec, skip=SKIP)
    if rec.get("id"):
        try:
            n.id = rec["id"]
        except Exception:
            pass
    codec.skills_restore(getattr(n, "skills", None), rec.get("skills"))
    try:
        n.no_make = set(rec.get("no_make") or ())
        n.no_sell = set(rec.get("no_sell") or ())
    except Exception:
        pass
    if rec.get("pack"):
        try:
            inv = getattr(n, "pack", None)
            if inv is None:
                from inventory import Inventory
                inv = n.pack = Inventory(32)
            codec.inventory_restore(inv, rec["pack"])
        except Exception:
            pass
    refs = rec.get("refs") or {}
    ctx.later(lambda: _resolve(n, refs, ctx))
    return n


def _resolve(n, refs: dict, ctx: "_context.Context") -> None:
    camp = ctx.camps.get(refs.get("camp") or "")
    if camp is not None:
        n.native_camp = camp
    house = ctx.houses.get(refs.get("house") or "")
    if house is not None:
        n.home_house = house
    work = ctx.workplaces.get(refs.get("work") or "")
    if work is not None:
        n.workplace = work
    bench = ctx.workplaces.get(refs.get("bench") or "")
    if bench is not None:
        n.artisan_bench = bench
    bond = ctx.people.get(refs.get("bond") or "")
    if bond is not None:
        n.bond_partner = bond
    breed = (ctx.people.get(refs.get("breed") or "")
             or ctx.animals.get(refs.get("breed") or ""))
    if breed is not None:
        n.breed_partner = breed
    escort = ctx.animals.get(refs.get("escort") or "")
    if escort is not None:
        n.escort_horse = escort
    if getattr(n, "native_camp", None) is None and camp is None:
        # A person with no camp in the save belongs to no live camp; leave the
        # field as it was created rather than inventing a home for him.
        pass


def create(rec: dict, camp, ctx: "_context.Context"):
    """A saved person the rebuilt camp did not produce (a baby, a survivor)."""
    import village as village_mod
    x = float(rec.get("x", getattr(camp, "x", 0.0)))
    y = float(rec.get("y", getattr(camp, "y", 0.0)))
    n = village_mod.NPC(
        x, y,
        random.randrange(1 << 30),
        name=rec.get("name", ""),
        npc_id=rec.get("id", "") or ("restored_%s" % rec.get("uid", "")),
        role=rec.get("role", "Villager"),
    )
    n.native = bool(rec.get("native", True))
    n.native_camp = camp
    ctx.people[rec["uid"]] = n
    restore(n, rec, ctx)
    return n


def remember(n, ctx: "_context.Context") -> None:
    if n is None:
        return
    got = getattr(n, "_save_uid", None)
    if got:
        ctx.people[str(got)] = n
