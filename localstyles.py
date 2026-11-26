"""localstyles.py -- the small products a place invents.

A style is not a new economy.  It is an extra ingredient sitting in a chest
beside an ordinary producer.  The producer keeps working exactly as before;
occasionally the local version comes out instead.
"""
from __future__ import annotations

# base product -> [(extra item, variant item), ...]
BREW_STYLES = {
    "beer": (("hardberries", "steel_ale"),
             ("bananas", "bananale"),
             ("raw_honey", "braggot"),
             ("cocoa", "chocolate_stout")),
    "mezcal": (("hardberries", "steelworm"),),
    "mead": (("berries", "melomel"),
             ("cactus_fruit", "cactus_mead")),
}
BREAD_STYLES = (("bananas", "banana_bread"),
                ("raw_honey", "honey_toast"),
                ("berries", "berry_tart"),
                ("cooked_meat", "meat_pie"))
# artisan base -> extra -> variant
ARTISAN_STYLES = {
    "chocolate": (("chili", "chili_chocolate"),),
    "cigar": (("raw_honey", "honey_cigar"),),
    "highflower_joint": (("raw_honey", "highflower_tea"),),
}

STYLE_LABEL = {
    "steel_ale": "iron_bar",
    "steelworm": "iron_bar",
    "bananale": "bananas",
    "braggot": "raw_honey",
    "chocolate_stout": "cocoa",
    "banana_bread": "bananas",
    "honey_toast": "raw_honey",
    "chili_chocolate": "chili",
    "honey_cigar": "raw_honey",
    "highflower_tea": "highflower",
    "berry_tart": "berries",
    "meat_pie": "cooked_meat",
    "melomel": "berries",
    "cactus_mead": "cactus_fruit",
}

STYLE_DRINKS = {"steel_ale", "steelworm", "bananale", "braggot",
                "chocolate_stout", "melomel", "cactus_mead"}
STYLE_FOOD = {"banana_bread", "honey_toast", "chili_chocolate",
              "berry_tart", "meat_pie", "highflower_tea"}
STYLE_SMOKE = {"honey_cigar"}


def apply_npc(npc, item, now: float) -> None:
    """Effects for a person who actually consumes a local style."""
    try:
        import mood
        if item == "banana_bread":
            mood.add_thought(npc, "local:banana_bread", 8.0, now, 600.0)
        elif item == "honey_toast":
            mood.add_thought(npc, "local:honey_toast", 5.0, now, 600.0)
        elif item == "braggot":
            mood.add_thought(npc, "local:braggot", 10.0, now, 600.0)
        elif item == "chocolate_stout":
            mood.add_thought(npc, "local:chocolate_stout", 5.0, now, 600.0)
            _had_temp = float(getattr(npc, "speed_boost_t", 0.0)) > 0.0
            npc.speed_boost_t = max(float(getattr(npc, "speed_boost_t", 0.0)), 600.0)
            npc.speed_boost_mult = (max(float(getattr(npc, "speed_boost_mult", 1.10)), 1.10)
                                     if _had_temp else 1.10)
        elif item == "berry_tart":
            mood.add_thought(npc, "local:berry_tart", 6.0, now, 600.0)
        elif item == "meat_pie":
            mood.add_thought(npc, "local:meat_pie", 5.0, now, 600.0)
            npc.health = min(npc.max_health, float(npc.health) + 15.0)
        elif item == "chili_chocolate":
            mood.add_thought(npc, "local:chili_chocolate", 5.0, now, 600.0)
            npc.stamina = min(npc.max_stamina, float(npc.stamina) + 10.0)
        elif item == "honey_cigar":
            mood.add_thought(npc, "local:honey_cigar", 12.0, now, 600.0)
        elif item == "highflower_tea":
            npc.stamina_boost_t = max(float(getattr(npc, "stamina_boost_t", 0.0)), 600.0)
            npc.stamina_boost_mult = max(float(getattr(npc, "stamina_boost_mult", 1.0)), 1.10)
            mood.add_thought(npc, "local:highflower_tea", 4.0, now, 600.0)
        elif item == "melomel":
            mood.add_thought(npc, "local:melomel", 10.0, now, 600.0)
            npc.speed_boost_t = max(float(getattr(npc, "speed_boost_t", 0.0)), 180.0)
            npc.speed_boost_mult = max(float(getattr(npc, "speed_boost_mult", 1.0)), 1.05)
        elif item == "cactus_mead":
            npc.heat_resist_t = max(float(getattr(npc, "heat_resist_t", 0.0)), 600.0)
            npc.stamina = min(npc.max_stamina, float(npc.stamina) + 20.0)
            mood.add_thought(npc, "local:cactus_mead", 4.0, now, 600.0)
        elif item == "steel_ale":
            npc.damage_resist_t = max(float(getattr(npc, "damage_resist_t", 0.0)), 180.0)
            npc.damage_resist = max(float(getattr(npc, "damage_resist", 0.0)), 0.50)
        elif item == "steelworm":
            npc.damage_resist_perm = max(float(getattr(npc, "damage_resist_perm", 0.0)), 0.30)
            npc.damage_resist = max(float(getattr(npc, "damage_resist", 0.0)),
                                    npc.damage_resist_perm)
        elif item == "bananale":
            if not getattr(npc, "bananale_used", False):
                npc.bananale_used = True
                npc.base_speed = float(getattr(npc, "base_speed", npc.speed)) * 1.30
                npc.speed = npc.base_speed * npc.skills.move_scale()
    except Exception:
        pass


def apply_player(player, item, now: float = 0.0) -> bool:
    """Effects for the player; returns False when this body already had it."""
    if item == "banana_bread":
        # The player has no mood bar; the loaf is still food.
        return True
    if item == "chocolate_stout":
        _had_temp = player.speed_boost_t > 0.0
        player.speed_boost_t = max(player.speed_boost_t, 600.0)
        player.speed_boost_mult = (max(player.speed_boost_mult, 1.10)
                                   if _had_temp else 1.10)
        return True
    if item == "berry_tart":
        return True
    if item == "meat_pie":
        player.eat(45.0)
        player.health = min(player.max_health, player.health + 15.0)
        return True
    if item == "chili_chocolate":
        player.stamina = min(player.max_stamina, player.stamina + 10.0)
        return True
    if item == "honey_cigar":
        return True
    if item == "highflower_tea":
        player.stamina_boost_t = max(player.stamina_boost_t, 600.0)
        player.stamina_boost_mult = max(player.stamina_boost_mult, 1.10)
        return True
    if item == "melomel":
        player.speed_boost_t = max(player.speed_boost_t, 180.0)
        player.speed_boost_mult = max(player.speed_boost_mult, 1.05)
        return True
    if item == "cactus_mead":
        player.heat_resist_t = max(player.heat_resist_t, 600.0)
        player.stamina = min(player.max_stamina, player.stamina + 20.0)
        return True
    if item == "steel_ale":
        player.damage_resist_t = max(player.damage_resist_t, 180.0)
        player.damage_resist = max(player.damage_resist, 0.50)
        return True
    if item == "steelworm":
        if getattr(player, "steelworm_used", False):
            return False
        player.steelworm_used = True
        player.damage_resist_perm = max(player.damage_resist_perm, 0.30)
        player.damage_resist = max(player.damage_resist, player.damage_resist_perm)
        return True
    if item == "bananale":
        if getattr(player, "bananale_used", False):
            return False
        player.bananale_used = True
        player.speed_perm = max(player.speed_perm, 1.30)
        return True
    return True
