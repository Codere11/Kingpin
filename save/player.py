"""player.py -- the man: his body, his pack, his skills, and where he stands.

The old save wrote seven fields and then the bootstrap put him back on the
beach anyway.  This writes every plain field on the Player (armour, magazines,
debt, origin, stamina state included), the whole inventory and the held stack,
all six skills, and a location that names the world, a house or a horse.
"""

from __future__ import annotations

from . import codec
from . import context as _context

SKIP = {
    "skills", "pack", "_shadow", "uid", "inventory", "held", "location",
    "village", "army", "squad", "hub_chest", "hub", "stalls",
    "workplaces", "workers", "plots", "yard_plots",
    "_pending_swing", "hit_flash", "attack_flash", "hurt_flash",
    "level_flash", "swing_anim", "wind_up", "recover", "stagger",
    "lunge_t", "lunge_dir", "lunge_cd", "reloading", "reload_total",
    "reload_done", "gun_cd", "sprinting", "moving", "death_timer",
    "searched_village", "search_village", "search_progress",
    "gate_guard", "waved_by", "passed_guard", "aggro_village",
    "was_inside_v", "search_guard", "wanted", "town_price_for",
    "riding", "aboard",
}


def _location(g, p) -> dict:
    try:
        house = getattr(g, "inside_house", None)
    except Exception:
        house = None
    if house is not None:
        fx, fy = getattr(house, "facing", (0.0, 1.0))
        wx = float(house.x + fx * (house.h / 2.0 + 30.0))
        wy = float(house.y + fy * (house.h / 2.0 + 30.0))
        return {"mode": "house", "house": codec.idref(house, "house"),
                "x": float(p.x), "y": float(p.y),
                "world": [wx, wy]}
    try:
        mine = getattr(g, "inside_mine", None)
    except Exception:
        mine = None
    if mine is not None:
        out = list(getattr(g, "mine_out", (p.x, p.y)))
        return {"mode": "mine", "out": out,
                "x": float(p.x), "y": float(p.y),
                "world": [float(out[0]), float(out[1])]}
    ride = getattr(g, "riding", None)
    if ride is not None:
        return {"mode": "horse", "horse": codec.idref(ride, "animal"),
                "x": float(p.x), "y": float(p.y),
                "world": [float(ride.x), float(ride.y)]}
    return {"mode": "world", "x": float(p.x), "y": float(p.y),
            "world": [float(p.x), float(p.y)]}


def snapshot(g) -> dict:
    p = g.player
    data = codec.dump_fields(p, skip=SKIP, label="Player")
    data["uid"] = codec.uid(p, "player")
    data["skills"] = codec.skills_to_data(getattr(p, "skills", None))
    data["inventory"] = codec.inventory_to_data(getattr(g, "inventory", None))
    data["held"] = codec.stack_to_data(getattr(getattr(g, "panel", None),
                                               "held", None))
    data["location"] = _location(g, p)
    return data


def apply(g, data, ctx: "_context.Context") -> None:
    p = g.player
    data = data or {}
    codec.load_fields(p, data, skip=SKIP)
    p.dead = False
    p.hit_flash = 0.0
    p.attack_flash = 0.0
    p.hurt_flash = 0.0
    p.wind_up = 0.0
    p.recover = 0.0
    p.stagger = 0.0

    codec.skills_restore(getattr(g, "skills", None), data.get("skills"))
    codec.inventory_restore(getattr(g, "inventory", None), data.get("inventory"))
    try:
        g.player.pack = g.inventory
    except Exception:
        pass
    try:
        g.panel.held = codec.data_to_stack(data.get("held"))
    except Exception:
        pass

    loc = data.get("location") or {}
    mode = loc.get("mode", "world")
    if mode == "house":
        house = ctx.houses.get(loc.get("house") or "")
        if house is not None:
            # The interior system is not the live path; stand him at the door.
            fx, fy = getattr(house, "facing", (0.0, 1.0))
            p.x = float(house.x + fx * (house.h / 2.0 + 30.0))
            p.y = float(house.y + fy * (house.h / 2.0 + 30.0))
        g.inside_house = None
        g.inside_mine = None
    elif mode == "mine":
        out = loc.get("out") or [p.x, p.y]
        g.mine_out = (float(out[0]), float(out[1]))
        p.x, p.y = g.mine_out
        g.inside_house = None
        g.inside_mine = None
    elif mode == "horse":
        horse = ctx.animals.get(loc.get("horse") or "")
        if horse is not None:
            p.x, p.y = float(horse.x), float(horse.y)
            ctx.later(lambda: _set_riding(g, horse))
        g.inside_house = None
        g.inside_mine = None
    else:
        p.x = float(loc.get("x", p.x))
        p.y = float(loc.get("y", p.y))
        g.inside_house = None
        g.inside_mine = None
    p.dead = False


def _set_riding(g, horse) -> None:
    try:
        g.riding = horse
    except Exception:
        pass
