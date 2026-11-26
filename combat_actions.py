"""combat_actions.py -- THE PLAYER'S OWN WEAPONS.

Firing a gun, swinging the axe, working the pick, and the click that opens a
man. Extracted from main.py, one action at a time.
"""

from __future__ import annotations

import math

import random

import pygame
import plog
import compass
import corpse as corpse_mod
import crop
import economy
import farm
import guns
import items
import ore
import sound
import village as village_mod
import wildcrop
from interior import Interior, fill_loot
from ui import ChestPanel


def _record_kill_weapon(stack, victim, g) -> None:
    if stack is None or victim is None:
        return
    try:
        import itemstory
        itemstory.record(stack, "killed", actor=g.player,
                         place="the field", now=getattr(g, "now", 0.0),
                         detail=getattr(victim, "name", "someone"))
    except Exception:
        pass


def fire(player, inventory, skills, combat, cam_x, cam_y, zoom, toast) -> None:
    stack = inventory.selected_stack()
    if stack is None or stack.defn.id not in (guns.MUSKET, guns.DOUBLE_SHOT,
                                             guns.RIFLE, guns.SHOTGUN, "bow"):
        return
    kind = stack.defn.id
    if kind == "bow":
        # A BOW LOOSES AN ARROW: axe-level damage, one arrow spent, and the
        # shaft flies 35% slower than a bullet.
        if player.gun_cd > 0.0:
            return
        if inventory.count_of("arrow") <= 0:
            toast("No arrows")
            return
        inventory.consume("arrow", 1)
        player.gun_cd = 0.8
        fx, fy = player.facing
        muzzle_x = player.x + fx * 30.0
        muzzle_y = player.y + fy * 30.0
        mouse_x, mouse_y = pygame.mouse.get_pos()
        wmouse_x, wmouse_y = mouse_x / zoom, mouse_y / zoom
        distance = math.hypot((cam_x + wmouse_x) - muzzle_x,
                              (cam_y + wmouse_y) - muzzle_y)
        import main as _m
        dmg = max(1, round(_m.MELEE_DAMAGE * skills.axe_damage_scale()))
        combat.fire(muzzle_x, muzzle_y, player.facing_angle, distance,
                    shooter=player, owner="player", damage=dmg, team="player",
                    spread=skills.shot_spread(), arrow=True, weapon=stack)
        sound.play("shot_bow")
        skills.gain_shooting()
        return
    if player.reloading > 0.0 or player.gun_cd > 0.0:
        return
    if player.mags.get(kind, 0) <= 0:
        # EMPTY: begin the reload at once. The round is drawn from the pack
        # the moment the barrel is ready, in settle_reload.
        if inventory.count_of("ammo") <= 0:
            toast("No ammo")
            return
        player.reload_kind = kind
        player.reload_total = guns.RELOAD_LO.get(kind, 5.0)
        player.reloading = player.reload_total
        sound.play("reload")
        toast("Reloading\u2026")
        return
    player.mags[kind] -= 1
    player.gun_cd = guns.FIRE_CD.get(kind, 0.4)
    fx, fy = player.facing
    px, py = -fy, fx
    muzzle_x = player.x + fx * 30.0 + px * 7.0
    muzzle_y = player.y + fy * 30.0 + py * 7.0
    mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
    wmouse_x, wmouse_y = mouse_x / zoom, mouse_y / zoom  # world space
    distance = math.hypot((cam_x + wmouse_x) - muzzle_x,
                          (cam_y + wmouse_y) - muzzle_y)
    spread = skills.shot_spread()
    for _ in range(guns.PELLETS.get(kind, 1)):
        extra = 0.11 if kind == guns.SHOTGUN else 0.0   # only the shotgun scatters
        combat.fire(muzzle_x, muzzle_y, player.facing_angle, distance,
                    shooter=player, owner="player", damage=guns.DAMAGE[kind],
                    team="player", spread=spread + extra, weapon=stack)
    sound.play("shot_rifle" if kind == guns.RIFLE else "shot_musket")
    skills.gain_shooting()


def use_pickaxe(player, combat, ore_field, inventory, pay_share, mark_dirty,
                toast) -> None:
    import main as _m
    if player.dead or not player.can_swing():
        return
    player.start_swing()
    angle = player.facing_angle
    combat.spawn_swing(player.x, player.y, angle)

    def in_arc(tx, ty, extra=0.0):
        dx, dy = tx - player.x, ty - player.y
        if math.hypot(dx, dy) > _m.AXE_REACH + extra:
            return False
        delta = abs(((math.atan2(dy, dx) - angle + math.pi) % (2.0 * math.pi)) - math.pi)
        return delta <= _m.AXE_ARC

    struck = None
    nearest = 1e9
    for chunk in ore_field.near(player.x, player.y, _m.AXE_REACH + 30.0):
        cx = min(max(player.x, chunk.rect.left), chunk.rect.right)
        cy = min(max(player.y, chunk.rect.top), chunk.rect.bottom)
        distance = math.hypot(player.x - cx, player.y - cy)
        if distance > _m.AXE_REACH or not in_arc(chunk.x, chunk.y, 20.0):
            continue
        if distance < nearest:
            nearest = distance
            struck = chunk
    if struck is None:
        toast("Nothing to mine here")
        return
    struck.strikes += 1
    combat.spawn_impact(struck.x, struck.y, (150, 150, 160))
    # ONE HIT, ONE ORE: the chunk runs dry after thirty.
    inventory.add("iron", 1)
    pay_share("iron", 1)
    if struck.strikes >= ore.STRIKES:
        struck.mined = True
        ore_field.mined.add(struck.cell)
        mark_dirty()
        toast(f"Mined iron   +1  (chunk done)")
    else:
        toast(f"Mining\u2026  {struck.strikes}/{ore.STRIKES}")


def _melee_dodge_counter(g, enemy, angle) -> bool:
    """A melee fighter whose axe skill beats the player's sidesteps the swing
    at 45 degrees and answers with a lunge. The dodge is instant and bigger
    than a step, with a visible dash trail. Returns True when the swing
    missed (the enemy dodged and counterattacked)."""
    import face as _face
    import skills as _skills
    _axe = getattr(getattr(enemy, "skills", None), "axe", 0.0)
    _diff = _axe - g.skills.axe
    if _diff <= 0.0:
        return False
    # THE CHANCE SCALES WITH THE GAP: a master over a green player dodges
    # four swings in five; a slightly better man only now and then.
    if random.random() >= min(0.80, _diff * 0.9):
        return False
    _side = random.choice((-1.0, 1.0))
    _dodge = angle + _side * math.radians(45.0)
    _ox, _oy = enemy.x, enemy.y
    enemy.x += math.cos(_dodge) * 64.0
    enemy.y += math.sin(_dodge) * 64.0
    enemy.facing = (math.cos(_dodge), math.sin(_dodge))
    # VISIBLE AND QUICK: dust where he stood, dust where he lands, and a short
    # dash trail between -- the eye reads the sidestep in one frame.
    try:
        g.combat.spawn_impact(_ox, _oy, (210, 190, 140))
        g.combat.spawn_impact(enemy.x, enemy.y, (210, 190, 140))
        for _i in (1, 2, 3):
            _fx = _ox + (enemy.x - _ox) * _i / 4.0
            _fy = _oy + (enemy.y - _oy) * _i / 4.0
            g.combat.spawn_impact(_fx, _fy, (240, 220, 170))
    except Exception:
        pass
    # COUNTERATTACK: the answer lands from the sidestep, not from the old spot.
    _dx = g.player.x - enemy.x
    _dy = g.player.y - enemy.y
    _d = math.hypot(_dx, _dy) or 1.0
    enemy.x += _dx / _d * 32.0
    enemy.y += _dy / _d * 32.0
    enemy.facing = (_dx / _d, _dy / _d)
    enemy.attack_flash = _face.WAR_SECONDS
    # A soldier carries his own damage; a native axeman swings 10 base (fists
    # are a third -- see skills.UNARMED_WEAKNESS).
    _base = getattr(enemy, "melee_damage", None)
    if _base is None:
        _armed = (getattr(enemy, "weapon", "") == "axe"
                  or getattr(enemy, "stock", {}).get("axe", 0) > 0
                  or getattr(enemy, "job", "") == "logger")
        _base = 10.0 if _armed else 10.0 / _skills.UNARMED_WEAKNESS
    try:
        _dmg = max(1, round(_base * enemy.skills.axe_damage_scale()))
    except Exception:
        _dmg = max(1, round(_base))
    if hasattr(g.player, "take_damage"):
        g.player.take_damage(_dmg)
    try:
        g.blood.spawn(g.player.x, g.player.y, 10, 16.0)
    except Exception:
        pass
    try:
        sound.play_on_screen("hit_flesh", g.player.x, g.player.y,
                             g.cam_x, g.cam_y, g.vw, g.vh)
        sound.play_on_screen("warrior_attack", enemy.x, enemy.y,
                             g.cam_x, g.cam_y, g.vw, g.vh, min_gap=0.3)
    except Exception:
        pass
    try:
        g.toast("Missed!  %s slips aside and answers" % getattr(enemy, "name", "He"))
    except Exception:
        pass
    return True


def use_axe(g, kills) -> int:
    """Swing the axe: men, beasts, trees, fences, and doors in one arc. The
    blow lands NOW -- no wind-up, no stamina tax, no stagger lockout."""
    import main as _m

    if g.player.dead or not g.player.can_swing():
        return kills
    # BARE HANDS. The same swing and the same skill whether or not the axe
    # is in the pack -- a fist simply is not an axe. See
    # g.skills.UNARMED_WEAKNESS: he hits for a quarter, and can still fight.
    _armed = g.inventory.count_of("axe") > 0
    melee = ((_m.MELEE_DAMAGE if _armed
              else _m.MELEE_DAMAGE / g.skills.UNARMED_WEAKNESS)
             * g.skills.axe_damage_scale())
    angle = g.player.facing_angle
    g.player.start_swing()
    g.player._pending_swing = (angle, melee, _armed)
    return resolve_swing(g, kills)


def resolve_swing(g, kills) -> int:
    """The wind-up is done: the committed swing lands NOW."""
    import main as _m
    import player as _player
    _p = getattr(g.player, "_pending_swing", None)
    if _p is None:
        return kills
    g.player._pending_swing = None
    angle, melee, _armed = _p
    stack = g.inventory.selected_stack()
    if stack is None or stack.defn.id != "axe":
        stack = next((_s for _s in g.inventory.slots
                      if _s is not None and _s.defn.id == "axe"), None)
    g.skills.gain_axe()
    g.combat.spawn_swing(g.player.x, g.player.y, angle)
    _flesh = False

    def in_arc(tx, ty, extra=0.0):
        dx, dy = tx - g.player.x, ty - g.player.y
        if math.hypot(dx, dy) > _m.AXE_REACH + extra:
            return False
        delta = abs(((math.atan2(dy, dx) - angle + math.pi) % (2.0 * math.pi)) - math.pi)
        return delta <= _m.AXE_ARC

    for enemy in g.enemies:
        if enemy.alive and in_arc(enemy.x, enemy.y, enemy.radius):
            _was_alive = getattr(enemy, "alive", True)
            enemy.take_damage(melee)
            _flesh = True
            if _was_alive and not getattr(enemy, "alive", True):
                _record_kill_weapon(stack, enemy, g)
                if getattr(enemy, "kind", "") == "bison":
                    g.inventory.add("raw_meat", random.randint(5, 10))
                    g.inventory.add("hide", random.randint(30, 50))
                    g.toast("Killed a bison   +meat +hides")
            g.blood.spawn(enemy.x, enemy.y, 8, 14.0)
            if (g.player.nation is not None
                    and getattr(enemy, "nation", None) == g.player.nation):
                g.banish(g.player.nation)
    for rabbit in g.rabbits:
        if rabbit.alive and in_arc(rabbit.x, rabbit.y, rabbit.radius):
            died = rabbit.take_damage(melee)
            _flesh = True
            g.blood.spawn(rabbit.x, rabbit.y, 8, 12.0)
            if died:
                _record_kill_weapon(stack, rabbit, g)
                amount = random.randint(1, 2)
                g.inventory.add("raw_meat", amount)
                g.toast(f"Caught a rabbit   +{amount} raw meat")
    # A HORSE IS KILLABLE BUT GIVES NOTHING -- for now it is just a creature.
    for horse in getattr(g, "horses", ()):
        if horse.alive and in_arc(horse.x, horse.y, horse.radius):
            died = horse.take_damage(melee)
            _flesh = True
            g.blood.spawn(horse.x, horse.y, 8, 14.0)
            if died:
                _record_kill_weapon(stack, horse, g)
                g.toast("Felled a horse")
    # EVERY MAN THE BLADE REACHES IS CUT -- once each.
    #
    # This walked only the towns in view, so the men of a criminal hut and
    # every traveller on the road stood inside the arc of a swing that
    # could not see them; and a man listed in two towns was cut twice for
    # one blow. One list, from every register in the world, deduplicated.
    _folk = []
    _seen = set()

    def _add_man(_n):
        if _n is None or id(_n) in _seen:
            return
        _seen.add(id(_n))
        _folk.append(_n)

    for _n in list(village_mod.PEOPLE) + list(village_mod.TRAVELLERS):
        _add_man(_n)
    for _h in (getattr(g.hub_world, "hubs", None) or ()):
        for _n in (getattr(_h, "npcs", None) or ()):
            _add_man(_n)
    _add_man(g.truth[0])
    for npc in _folk:
        if npc.alive and in_arc(npc.x, npc.y, npc.radius):
                died = npc.take_damage(melee, record=False, attacker=g.player)
                _flesh = True
                if died:
                    _record_kill_weapon(stack, npc, g)
                g.work_lanes.damage(npc, melee)
                # HE KNOWS THE MAN WHO HIT HIM -- and likes him twenty less.
                try:
                    import economy as _ec2
                    _ec2.wronged(npc, g.player, 20.0, g.now)
                except Exception:
                    pass
                g.blood.spawn(npc.x, npc.y, 18 if died else 8, 22.0 if died else 14.0)
                # SELF-DEFENCE IS NOT A MURDER. A man who came at you with
                # an axe and lost is not a crime, and his neighbours know
                # it -- so nothing here counts against you.
                if (npc.village is not None
                        and not village_mod.self_defence(npc)):
                    npc.village.provoke()
                    if died:
                        # HE SHOUTED BEFORE HE DIED. The village is told,
                        # and the refugees and traders carry it on -- but
                        # only the men who SAW it will never forget.
                        npc.village.learn_killers(
                            (village_mod.PLAYER_ID,), g.now)
                        g.work_lanes.crime(npc.village, (village_mod.PLAYER_ID,))
                        g.see_murder(npc)
                if g.player.nation is not None and npc.nation == g.player.nation:
                    g.banish(g.player.nation)
                if died:
                    kills += 1

    if _flesh:
        sound.play("hit_flesh")

    struck = None
    nearest = 1e9
    for tree in g.trees.near(g.player.x, g.player.y, _m.AXE_REACH + 30.0):
        if tree.felled:
            continue
        rect = tree.trunk_rect
        cx = min(max(g.player.x, rect.left), rect.right)
        cy = min(max(g.player.y, rect.top), rect.bottom)
        distance = math.hypot(g.player.x - cx, g.player.y - cy)
        if distance > _m.AXE_REACH or not in_arc(tree.x, tree.y, 26.0):
            continue
        if distance < nearest:
            nearest = distance
            struck = tree
    if struck is not None:
        # KEEP THE COUNT BY TREE POSITION, not only on the Tree object.  A
        # tree rebuilt from a cache or a save can otherwise start again at 1
        # while the player is halfway through an ironwood trunk.
        _tkey = (round(float(struck.x), 1), round(float(struck.y), 1))
        _hits = getattr(g, "tree_chops", None)
        if not isinstance(_hits, dict):
            _hits = g.tree_chops = {}
        struck.strikes = int(_hits.get(_tkey, struck.strikes)) + 1
        _hits[_tkey] = struck.strikes
        struck.hit_until = float(getattr(g, "now", 0.0)) + 0.5
        sound.play("hit_tree")
        g.combat.spawn_impact(struck.x, struck.y, (120, 90, 50))
        _need = int(getattr(struck, "strikes_needed", _m.AXE_STRIKES))
        # THE CHOP BAR, not a debug toast.  It belongs to the tree being hit
        # and runs down in the HUD while the player keeps swinging.
        try:
            # This is only a marker that the HUD should show the SWING
            # recharge bar; the bar itself reads the player's cooldown.
            g.chop_bar = {"x": float(struck.x), "y": float(struck.y),
                          "t": float(getattr(g, "now", 0.0))}
        except Exception:
            pass
        if struck.strikes >= _need:
            _hits.pop(_tkey, None)
            g.trees.fell(struck, g.now)
            amount = random.randint(10, 30)
            _species = getattr(struck, "species", "")
            if _species in ("palm", "banana_palm", "cocoa_palm"):
                _drop = "tropical_wood"
            elif _species == "ironwood":
                _drop = "ironwood"
            else:
                _drop = "wood"
            g.inventory.add(_drop, amount)
            g.pay_share(_drop, amount)
            _extra = ""
            if _species in ("banana_palm", "cocoa_palm"):
                try:
                    import cropgenetics as _cg
                    _kind = "banana" if _species == "banana_palm" else "cocoa"
                    _fruit = "bananas" if _kind == "banana" else "cocoa"
                    _n = (random.randint(2, 5) if _kind == "banana"
                          else random.randint(2, 4))
                    _fg = _cg.tree_genetics(_kind, struck.x, struck.y,
                                            int(getattr(g.world, "seed", 1)))
                    g.inventory.add(_fruit, _n, quality=(4 if _kind == "cocoa" else None),
                                    genetics=_fg)
                    g.pay_share(_fruit, _n)
                    _extra = "   +%d %s" % (_n, _fruit)
                except Exception:
                    pass
            g.combat.spawn_impact(struck.x, struck.y - 20, (86, 140, 64))
            g.toast(f"Felled a tree   +{amount} {_drop}{_extra}")
            try:
                g.chop_bar = None
            except Exception:
                pass
        else:
            if not getattr(g, "view3d", False):
                g.toast(f"Chopping…  {struck.strikes}/{_need}")

    # Chop down a fence or gate you built yourself.
    for lst in (g.built_fences, g.built_gates):
        hit = None
        best = 1e9
        for rect in lst:
            cx = min(max(g.player.x, rect.left), rect.right)
            cy = min(max(g.player.y, rect.top), rect.bottom)
            d = math.hypot(g.player.x - cx, g.player.y - cy)
            if d <= _m.AXE_REACH and d < best:
                best, hit = d, rect
        if hit is not None:
            lst.remove(hit)
            g.combat.spawn_impact(hit.centerx, hit.centery, (140, 100, 56))
            g.toast("Chopped down your fence")
            g.mark_dirty()
            return kills

    # Chop up a plank you placed: it goes back in your pack.
    for (_tx, _ty) in list(getattr(g, "built_blocks", {})):
        _r = pygame.Rect(_tx * _m.TILE, _ty * _m.TILE, _m.TILE, _m.TILE)
        _cx = min(max(g.player.x, _r.left), _r.right)
        _cy = min(max(g.player.y, _r.top), _r.bottom)
        if math.hypot(g.player.x - _cx, g.player.y - _cy) <= _m.AXE_REACH:
            _bk = g.built_blocks.get((_tx, _ty), "wood")
            if _bk == "ironwood":
                _hits = getattr(g, "built_block_hits", None)
                if _hits is None:
                    _hits = g.built_block_hits = {}
                _hits[(_tx, _ty)] = int(_hits.get((_tx, _ty), 0)) + 1
                if _hits[(_tx, _ty)] < 3:
                    g.combat.spawn_impact(_r.centerx, _r.centery, (140, 140, 136))
                    g.toast("Chopping ironwood…  %d/3" % _hits[(_tx, _ty)])
                    return kills
                _hits.pop((_tx, _ty), None)
            g.built_blocks.pop((_tx, _ty), "wood")
            g.inventory.add(_bk, 1)
            g.combat.spawn_impact(_r.centerx, _r.centery, (140, 100, 56))
            g.toast("Chopped it up  +1 %s" % _bk)
            g.mark_dirty()
            return kills

    # HIT A BUILDING: it is destroyed outright. Only planks and hides come
    # back to the pack; chests, signs, feed boxes and benches are gone.
    for _ch in list(getattr(g, "built_chests", ())):
        if in_arc(_ch.x, _ch.y, 30.0):
            g.built_chests.remove(_ch)
            g.combat.spawn_impact(_ch.x, _ch.y, (140, 100, 56))
            g.toast("Chest destroyed")
            g.mark_dirty()
            return kills
    for _sg in list(getattr(g, "built_signs", ())):
        if in_arc(_sg.x, _sg.y, 20.0):
            g.built_signs.remove(_sg)
            g.combat.spawn_impact(_sg.x, _sg.y, (140, 100, 56))
            g.toast("Sign-post destroyed")
            g.mark_dirty()
            return kills
    for _fb in list(getattr(g, "built_foodboxes", ())):
        if in_arc(_fb.x, _fb.y, 20.0):
            g.built_foodboxes.remove(_fb)
            g.combat.spawn_impact(_fb.x, _fb.y, (140, 100, 56))
            g.toast("Food box destroyed")
            g.mark_dirty()
            return kills
    for _wp in list(getattr(g, "placed_work", ())):
        if in_arc(_wp.x, _wp.y, 34.0):
            try:
                g.placed_work.remove(_wp)
            except Exception:
                pass
            g.combat.spawn_impact(_wp.x, _wp.y, (140, 100, 56))
            g.toast("Workbench destroyed")
            g.mark_dirty()
            return kills

    # A SETTLEMENT'S FENCE IS NOT WOOD, IT IS LAW. It cannot be cut, by an
    # axe or anything else: the wall is not what keeps people out, the
    # SEARCH at the gate is, and a wall you can hack a hole in would make
    # the gate decorative. The g.player's own fences are still his to cut.

    # Break a villager's door open with the axe.
    for village in g.visible_villages:
        for vhouse in village.houses:
            if getattr(vhouse, "door_broken", False):
                continue
            fx, fy = vhouse.facing
            door_x = vhouse.x + fx * (vhouse.h / 2.0 + 4.0)
            door_y = vhouse.y + fy * (vhouse.h / 2.0 + 4.0)
            if not in_arc(door_x, door_y, 22.0):
                continue
            vhouse.enterable = True
            vhouse.interior = Interior(random.randint(0, 2 ** 31),
                                       tuple(vhouse.facing))
            fill_loot(vhouse.interior.chest)
            vhouse.break_door()
            g.commit_crime()
            g.combat.spawn_impact(door_x, door_y, (120, 78, 44))
            g.toast("Broke the door open")
            return kills
    return kills


def click_a_man(g, at=None):
    bopen = g.body_open
    bpanel = g.body_panel

    """CLICK A MAN, OPEN THAT MAN. Nothing else.

    The nearest living man to the point you clicked, within 48 px. If he is
    the truth-teller his questions open; if he is anybody else his trade
    opens. It does not care what you are holding, where you are standing,
    whether a house is open, or which men happen to be on screen -- every
    man in the world is a candidate, because a man you can see is a man in
    a village's list.
    """
    # THE CLICK'S OWN POSITION. The event carries it; the cursor is only a
    # fallback, because a click is where it happened, not where the pointer
    # happens to be when the frame reads it.
    if at is not None:
        mx, my = at
    else:
        mx, my = pygame.mouse.get_pos()
    wx = g.cam_x + mx / g.zoom
    wy = g.cam_y + my / g.zoom
    # A BODY FIRST: it is not a man you can talk to, and `g.open_trade` on a
    # corpse would be nonsense -- but a body is what you loot.
    _body = corpse_mod.nearest(wx, wy)
    if _body is not None:
        bpanel = ChestPanel(g.inventory, _body.pack,
                                top_label=getattr(_body, "name", "a body"))
        bopen = True
        pygame.mouse.set_visible(True)
        plog.log("BODY-OPEN", getattr(_body, "name", "?"), "at",
                 int(math.hypot(_body.x - g.player.x, _body.y - g.player.y)), "px")
        return (True, bopen, bpanel)
    best, bd = None, 1e18
    # HIM FIRST AND ALWAYS. He is a village's man, but a village's list can
    # be rebuilt at load -- so he is a candidate in his own right.
    if g.truth[0] is not None:
        best = g.truth[0]
        bd = math.hypot(best.x - wx, best.y - wy)
    for _v in g.villages.villages:
        for _n in _v.npcs:
            if not getattr(_n, "alive", True) or getattr(_n, "in_interior", False):
                continue
            d = math.hypot(_n.x - wx, _n.y - wy)
            if d < bd:
                best, bd = _n, d
    for _n in list(getattr(village_mod, "TRAVELLERS", ())):
        if not getattr(_n, "alive", True):
            continue
        d = math.hypot(_n.x - wx, _n.y - wy)
        if d < bd:
            best, bd = _n, d
    # THE PLAYER'S OWN CONQUERED PEOPLE are candidates too: they are not in
    # any village's list, so a click on them used to fall through to nothing.
    for _n in list(getattr(g, "_native_people", ())):
        if not getattr(_n, "alive", True) or not getattr(_n, "conquered", False):
            continue
        d = math.hypot(_n.x - wx, _n.y - wy)
        if d < bd:
            best, bd = _n, d
    # NOTHING WITHIN 48 PX? THEN ANY CLICK NEAR HIM OPENS HIM. There is
    # exactly one truth-teller in the world; if you are standing beside him
    # and you click, that click is for him -- no distance arithmetic, no
    # camera/zoom to get wrong, nothing left to fail.
    # THE SHIP IS A LANDMARK, NOT A MAN: a wider click box, and it opens
    # the market (open_ship) -- the SAME click that opens a person opens it.
    _ship = getattr(g, "ship", None)
    if _ship is not None and getattr(_ship, "alive", True):
        _sd = math.hypot(_ship.x - wx, _ship.y - wy)
        if _sd < 64.0 and (best is None or _sd <= bd):
            if hasattr(g, "open_ship"):
                g.open_ship()
            pygame.mouse.set_visible(True)
            plog.log("PICK", "ship", "at", int(_sd))
            return (True, bopen, bpanel)
    if best is None or bd > 48.0:
        # NOTHING WAS CLICKED. This used to open the truth-teller whenever
        # he happened to be within 140 px OF THE PLAYER -- a third of the
        # screen -- so a click on empty ground across the square opened a
        # conversation. A man is opened by clicking HIM.
        plog.log("PICK-NONE", "nearest",
                 int(bd) if best is not None else -1)
        return (False, bopen, bpanel)
    if getattr(best, "is_truth_teller", False):
        g.dialogue_panel.open(best, g.player, g.main_capital()[0])
        g.toast("%s looks at you." % getattr(best, "name", "He"))
    elif getattr(best, "conquered", False):
        # HIS OWN WORKER: pockets first, then trade.
        g.dialogue_panel.open(best, g.player, g.main_capital()[0])
        g.toast("%s is yours." % getattr(best, "name", "He"))
    else:
        g.open_trade(best)
    pygame.mouse.set_visible(True)
    plog.log("PICK", getattr(best, "name", "?"), "at", int(bd),
             "truth", getattr(best, "is_truth_teller", False))
    return (True, bopen, bpanel)


def _clickable_men(g):
    """Every living man who can be clicked: the villagers in view, the
    truth-teller, and the soldiers -- never the wolves."""
    out = [n for v in g.visible_villages for n in v.npcs
           if getattr(n, "alive", True) and not getattr(n, "in_interior", False)]
    if g.truth[0] is not None and g.truth[0] not in out:
        out.append(g.truth[0])
    out += [e for e in g.enemies
            if getattr(e, "kind", "") == "soldier" and getattr(e, "alive", True)]
    return out


def _man_under(g, wx, wy):
    """The living man whose drawn body stands over this world point."""
    for npc in _clickable_men(g):
        if abs(npc.x - wx) < 26.0 and -64.0 < (wy - npc.y) < 22.0:
            return npc
    return None


def on_click(g):
    copen = g.confirm_open

    _st0 = g.inventory.selected_stack()
    plog.log("CLICK", "on_click", "item",
             (_st0.defn.id if _st0 else None), "dead", g.player.dead,
             "house", g.inside_house is not None,
             "at", "%d,%d" % (int(g.player.x), int(g.player.y)))
    if g.player.dead:
        return
    # ---- HIM, BEFORE ANYTHING ELSE -------------------------------------
    # Every other path in this handler can return first: a held item, a
    # house, an axe, the reach gate, the list of men in view. This does not
    # depend on any of them. Click his body and the questions open.
    # ALWAYS FIND HIM. The handle can be stale after a reload; his own
    # town's list and the wanderers' list are both searched, so there is no
    # state in which he exists and this cannot find him.
    _tt0 = g.truth[0]
    if _tt0 is None:
        for _tv in g.villages.villages:
            for _tn in _tv.npcs:
                if getattr(_tn, "is_truth_teller", False):
                    _tt0 = _tn
                    g.truth[0] = _tt0
                    break
            if _tt0 is not None:
                break
    if _tt0 is not None:
        _tmx, _tmy = pygame.mouse.get_pos()
        _twx = g.cam_x + _tmx / g.zoom
        _twy = g.cam_y + _tmy / g.zoom
        _tdx, _tdy = _twx - _tt0.x, _twy - _tt0.y
        # LOGGED ON EVERY CLICK, HIT OR MISS, WITH THE NUMBERS. If this ever
        # fails again, the log says by how much rather than needing a guess.
        plog.log("CLICK-HIM", "click", "%d,%d" % (int(_twx), int(_twy)),
                 "him", "%d,%d" % (int(_tt0.x), int(_tt0.y)),
                 "d", "%d,%d" % (int(_tdx), int(_tdy)))
        # HIS BODY, AND NOT A SQUARE AROUND HIS FEET. The cutout is drawn
        # above the anchor, so the box is the same one every other man is
        # hit with: about his width across, and up to his head.
        if abs(_tdx) <= 26.0 and -64.0 < _tdy < 22.0:
            g.dialogue_panel.open(_tt0, g.player, g.main_capital()[0])
            pygame.mouse.set_visible(True)
            plog.log("TALK", "opened with", getattr(_tt0, "name", "?"),
                     "click", "%d,%d" % (int(_twx), int(_twy)),
                     "him", "%d,%d" % (int(_tt0.x), int(_tt0.y)))
            return
    if g.comm in ("insult", "praise", "threaten"):
        # A WORD, NOT A SWING. The equipped communication overrides the item
        # in hand. Click his body and it is still a chat; click beside him and
        # you speak.
        _cmx, _cmy = pygame.mouse.get_pos()
        _cwx = g.cam_x + _cmx / g.zoom
        _cwy = g.cam_y + _cmy / g.zoom
        _body = _man_under(g, _cwx, _cwy)
        if _body is not None:
            if getattr(_body, "is_truth_teller", False):
                g.dialogue_panel.open(_body, g.player, g.main_capital()[0])
            elif getattr(_body, "attacked", False):
                g.toast(f"{_body.name} won't trade with you")
            else:
                g.open_trade(_body)
            pygame.mouse.set_visible(True)
            return
        import main as _m
        if math.hypot(_cwx - g.player.x, _cwy - g.player.y) <= g.reach + 24.0:
            _ang = math.atan2(_cwy - g.player.y, _cwx - g.player.x)
            _found = None
            _bd = 1e18
            for _n in _clickable_men(g):
                _d = math.hypot(_n.x - g.player.x, _n.y - g.player.y)
                if _d > _m.AXE_REACH + 30.0:
                    continue
                _na = math.atan2(_n.y - g.player.y, _n.x - g.player.x)
                _da = abs((_ang - _na + math.pi) % (2.0 * math.pi) - math.pi)
                if _da <= _m.AXE_ARC and _d < _bd:
                    _found, _bd = _n, _d
            if _found is not None:
                import comm as _comm
                _ok, _left = _comm.use_comm(_found, g.comm, g.now, g)
                g.player.swing_cd = g.player.skill_axe_cd   # the same wait as a fist
                _name = getattr(_found, "name", "him")
                _verb = {"praise": "praised", "insult": "insulted",
                         "threaten": "threatened"}[g.comm]
                if _ok:
                    _comm.spawn_cloud(g.player.x, g.player.y, g.comm)
                    g.toast("You %s %s" % (_verb, _name))
                else:
                    g.toast("You've said your piece to %s today" % _name)
                plog.log("COMM", g.comm, _name, "ok", _ok, "left", _left)
            else:
                g.toast("Nobody there to %s" % g.comm)
        else:
            g.toast("Too far away")
        return
    stack = g.inventory.selected_stack()
    item_id = stack.defn.id if stack else None
    # ANYTHING THE VILLAGERS CALL FOOD, THE PLAYER CAN EAT. This was a
    # list of three hand-written cases -- and berries and cactus fruit were
    # not among them, so a man could starve with a pocket full of them
    # while every villager in the valley ate the same things for supper.
    if item_id in ("banana_bread", "honey_toast", "chili_chocolate",
                   "berry_tart", "meat_pie", "highflower_tea"):
        if g.inventory.consume(item_id, 1):
            import localstyles as _ls
            _ls.apply_player(g.player, item_id, getattr(g, "now", 0.0))
            g.player.eat(g.eat_restore)
            g.toast("Ate the %s" % items.get(item_id).name.lower())
        else:
            g.toast("None left")
        return
    if item_id == "honey_cigar":
        if g.inventory.consume("honey_cigar", 1):
            g.toast("Smoked the honey-cured cigar")
        else:
            g.toast("None left")
        return
    if item_id in ("steel_ale", "steelworm", "bananale", "braggot",
                   "chocolate_stout", "melomel", "cactus_mead"):
        import localstyles as _ls
        if g.inventory.consume(item_id, 1):
            _ls.apply_player(g.player, item_id, getattr(g, "now", 0.0))
            g.toast("Drank the %s" % items.get(item_id).name.lower())
        else:
            g.toast("None left")
        return
    if item_id in economy.FOOD:
        if g.inventory.consume(item_id, 1):
            g.player.eat(g.eat_restore)
            g.toast("Ate some %s" % items.get(item_id).name.lower())
        else:
            g.toast("None of that left")
        return
    if item_id == "cooked_meat":
        if g.inventory.consume("cooked_meat", 1):
            g.player.eat(g.player.max_hunger)
            g.toast("Ate cooked meat   -   full up")
        else:
            g.toast("No cooked meat")
        return
    if item_id == "raw_meat":
        if g.inside_house is not None and g.near_fireplace():
            if g.inventory.consume("raw_meat", 1):
                g.inventory.add("cooked_meat", 1)
                g.toast("Cooked the meat over the g.fire")
            else:
                g.toast("No raw meat")
        else:
            g.toast("Cook raw meat at a fireplace")
        return
    if item_id == "banana_liqueur":
        _gen = getattr(stack, "genetics", None)
        _b = (_gen.get("bonuses") or {}) if isinstance(_gen, dict) else {}
        if g.inventory.consume("banana_liqueur", 1):
            if float(_b.get("speed", 0.0)) > 0.0:
                g.player.quicken(180.0)
                g.toast("Banana liqueur   -   speed +50% for 3 minutes")
            else:
                g.toast("Drank the banana liqueur")
        else:
            g.toast("No banana liqueur left")
        return
    if item_id == "chocolate":
        _gen = getattr(stack, "genetics", None)
        _b = (_gen.get("bonuses") or {}) if isinstance(_gen, dict) else {}
        if g.inventory.consume("chocolate", 1):
            _bonus = float(_b.get("stamina", 0.0))
            if _bonus > 0.0 and g.player.taste_chocolate(_bonus):
                g.toast("Chocolate   -   maximum stamina +%d%%" % int(round(_bonus * 100)))
            elif getattr(g.player, "cocoa_tasted", False):
                g.toast("The chocolate can't change your body again")
            else:
                g.toast("Ate the chocolate")
        else:
            g.toast("No chocolate left")
        return
    if item_id == "chili_mezcal":
        # THE SECOND BREWER'S SECRET: a permanent +35% body, once.
        if g.inventory.consume("chili_mezcal", 1):
            if g.player.gain_max_health(0.35):
                g.toast("Drank the chili mezcal   -   maximum health +35%")
            else:
                g.toast("The chili mezcal has already changed your body")
        else:
            g.toast("No chili mezcal left")
        return
    if item_id == "chili_beer":
        # THE BREWER'S SECRET, DRUNK BY THE PLAYER: equip it and click.
        if g.inventory.consume("chili_beer", 1):
            g.player.health = g.player.max_health
            g.toast("Drank the chili beer   -   health restored")
        else:
            g.toast("No chili beer left")
        return
    if item_id == "compass":
        if g.compass_state.mode == "village":
            g.toast(compass.village_report(g.player.x, g.player.y, g.world.seed))
        elif g.compass_state.mode == "home" and g.compass_state.home is not None:
            g.toast(compass.home_report(g.player.x, g.player.y, g.compass_state.home))
        else:
            g.toast("Press F to choose what to find")
        return
    if g.inside_house is not None:
        _mx, _my = pygame.mouse.get_pos()
        # the room is drawn at the g.world's zoom, so the click is brought
        # into that same frame before it is compared with anything in it
        _bx, _by = g.cam_x + _mx / g.zoom, g.cam_y + _my / g.zoom
        for _kind, _rect in g.inside_house.interior.furniture:
            if _kind == "bed" and _rect.inflate(18, 18).collidepoint(_bx, _by):
                g.try_sleep()
                return
        return
    if item_id in ("musket", "double_shot", "rifle", "shotgun", "bow"):
        g.fire()
        return
    # CLICK DIRECTLY ON A MAN -> CHAT, whatever is in his hands. This is the
    # one click that never swings: a body is a conversation, not a target.
    _mx0, _my0 = pygame.mouse.get_pos()
    _wx0 = g.cam_x + _mx0 / g.zoom
    _wy0 = g.cam_y + _my0 / g.zoom
    _man0 = _man_under(g, _wx0, _wy0)
    if _man0 is not None:
        if getattr(_man0, "is_truth_teller", False):
            g.dialogue_panel.open(_man0, g.player, g.main_capital()[0])
        elif (getattr(_man0, "is_commander", False)
              and not getattr(_man0, "attacked", False)):
            g.confirm.pending = _man0
            if g.player.nation == _man0.nation:
                g.confirm.mode = "leave"
                g.confirm.open(f"Leave the {_man0.village.name} army?")
            else:
                g.confirm.mode = "join"
                g.confirm.open(f"Join the {_man0.village.name} army?")
            copen = True
        elif getattr(_man0, "attacked", False):
            g.toast(f"{_man0.name} won't trade with you")
        elif getattr(_man0, "gate_index", None) is not None:
            g.guard_search(_man0)
        else:
            g.open_trade(_man0)
        pygame.mouse.set_visible(True)
        return
    # TALKING COMES BEFORE THE AXE. `on_click` returned at the axe branch
    # below, so with a weapon in hand -- and the starter kit IS an axe --
    # no man could ever be spoken to. The man who answers questions is
    # clicked first, and the axe still works on everybody else.
    if g.truth[0] is not None:
        _mx, _my = pygame.mouse.get_pos()
        _wx = g.cam_x + _mx / g.zoom
        _wy = g.cam_y + _my / g.zoom
        if (math.hypot(_wx - g.truth[0].x, _wy - g.truth[0].y) < 26.0
                and math.hypot(_wx - g.player.x, _wy - g.player.y) <= g.reach + 40.0):
            g.dialogue_panel.open(g.truth[0], g.player, g.main_capital()[0])
            pygame.mouse.set_visible(True)
            return
    if item_id == "axe":
        g.use_axe()
        return
    if item_id == "pickaxe":
        g.use_pickaxe()
        return

    mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
    wmouse_x, wmouse_y = mouse_x / g.zoom, mouse_y / g.zoom  # g.world space
    wx, wy = g.cam_x + wmouse_x, g.cam_y + wmouse_y   # the g.world mouse

    # THE MAN WHO ANSWERS QUESTIONS IS CLICKED ON HIS BODY, NOT HIS FEET.
    # A cutout figure is drawn ABOVE its anchor point, so a click on the
    # chest is 20-40 px from (x, y) and a 22 px circle around the feet
    # missed him entirely. He is found first, by his silhouette.
    _tt = g.truth[0]
    if _tt is None:
        for _n in list(village_mod.PEOPLE) + list(village_mod.TRAVELLERS):
            if getattr(_n, "is_truth_teller", False):
                _tt = _n
                break
    if _tt is not None and abs(wx - _tt.x) < 30.0 and -70.0 < (wy - _tt.y) < 26.0:
        g.dialogue_panel.open(_tt, g.player, g.main_capital()[0])
        pygame.mouse.set_visible(True)
        return

    # Clicking a villager while not wielding a weapon opens trade.
    if math.hypot(wx - g.player.x, wy - g.player.y) <= g.reach + 24.0:
        _folk = [n for v in g.visible_villages for n in v.npcs]
        if g.truth[0] is not None and g.truth[0] not in _folk:
            _folk.append(g.truth[0])         # he is a man like any other
        # AND THE SOLDIERS. They are not in a village's list -- they are
        # the nation's, and they march -- so they were the one kind of man
        # in the g.world you could not do business with.
        # THE SOLDIERS, NOT THE WOLVES. An enemy list holds both, and a
        # wolf was being offered a trade menu: clicking one went into the
        # economy asking what a wolf WANTS and threw AttributeError, taking
        # the game down. Only a man with a purse is a customer.
        _folk += [e for e in g.enemies
                  if getattr(e, "kind", "") == "soldier"
                  and getattr(e, "alive", True)
                  and not getattr(e, "attacked", False)]
        plog.log("CLICK", "folk", len(_folk), "reach_test", True,
                 "mouse", "%d,%d" % (int(wx), int(wy)),
                 "player", "%d,%d" % (int(g.player.x), int(g.player.y)))
        for npc in _folk:
                _dd = math.hypot(npc.x - wx, npc.y - wy)
                if _dd < 60.0:
                    plog.log("CLICK-NEAR", getattr(npc, "name", "?"),
                             "d", int(_dd), "dx", int(npc.x - wx),
                             "dy", int(npc.y - wy),
                             "truth", getattr(npc, "is_truth_teller", False),
                             "alive", getattr(npc, "alive", None))
                # A cutout is drawn ABOVE its anchor, so the hit area is his
                # body, not a circle at his feet -- the same test for every
                # man in the g.world, villagers included.
                if (getattr(npc, "alive", True)
                        and abs(npc.x - wx) < 26.0
                        and -64.0 < (wy - npc.y) < 22.0):
                    if getattr(npc, "is_truth_teller", False):
                        g.dialogue_panel.open(npc, g.player, g.main_capital()[0])
                        pygame.mouse.set_visible(True)
                        return
                    if (getattr(npc, "is_commander", False)
                            and not getattr(npc, "attacked", False)):
                        g.confirm.pending = npc
                        if g.player.nation == npc.nation:
                            g.confirm.mode = "leave"
                            g.confirm.open(f"Leave the {npc.village.name} army?")
                        else:
                            g.confirm.mode = "join"
                            g.confirm.open(f"Join the {npc.village.name} army?")
                        copen = True
                        pygame.mouse.set_visible(True)
                        return
                    if getattr(npc, "attacked", False):
                        g.toast(f"{npc.name} won't trade with you")
                        return
                    # A GUARD AT A GATE SEARCHES; HE DOES NOT TRADE.
                    if getattr(npc, "gate_index", None) is not None:
                        g.guard_search(npc)
                        return
                    g.open_trade(npc)
                    return

    # HAND-TO-HAND. No weapon branch ran: a click that points at a man
    # (within arm's reach) but is not on his body is an attack. The swing
    # lands with the axe if he owns one, with his fists if he does not --
    # a third of the weight, see skills.UNARMED_WEAKNESS.
    import main as _m
    if math.hypot(wx - g.player.x, wy - g.player.y) <= g.reach + 24.0:
        _ang = math.atan2(wy - g.player.y, wx - g.player.x)
        _found = None
        _bd = 1e18
        for _n in _clickable_men(g):
            _d = math.hypot(_n.x - g.player.x, _n.y - g.player.y)
            if _d > _m.AXE_REACH + 30.0:
                continue
            _na = math.atan2(_n.y - g.player.y, _n.x - g.player.x)
            _da = abs((_ang - _na + math.pi) % (2.0 * math.pi) - math.pi)
            if _da <= _m.AXE_ARC and _d < _bd:
                _found, _bd = _n, _d
        if _found is not None:
            # THE SAME WAIT AS THE AXE. A fist cannot swing while the arm is
            # already coming back; this gate is the player's swing cooldown,
            # nobody else's -- NPCs keep their own attack_cd.
            if not g.player.can_swing():
                plog.log("HAND", "cooldown", "wait",
                         round(float(getattr(g.player, "swing_cd", 0.0)), 2))
                return
            plog.log("HAND", "swing at", getattr(_found, "name", "?"),
                     "d", int(_bd), "armed", g.inventory.count_of("axe") > 0)
            g.use_axe()
            return

    if item_id == "first_aid":
        g.use_first_aid()
        return

    if math.hypot(wx - g.player.x, wy - g.player.y) > g.reach:
        g.toast("Too far away")
        return
    tx = int(math.floor(wx / g.tile))
    ty = int(math.floor(wy / g.tile))

    plot = g.world.plot_at(tx, ty)
    if plot is not None and plot.kind in crop.LEAF_KINDS:
        grade = g.skills.tobacco_grade()
        if farm.harvest(g.world, g.inventory, plot, g.now, g.toast, grade,
                        skill=g.skills.farming,
                        tx=tx, ty=ty, share=g.pay_share,
                        camp=getattr(g, "player_camp", None)):
            try:
                import playlog as _pl
                _pl.record(getattr(g, "root", None), "action",
                           action="harvest", crop=plot.kind)
            except Exception:
                pass
            # The same rate the farmers get. At the old default (0.12) the
            # g.player reached skill 8 in ~67 harvests -- SSS tobacco by day
            # two, against three weeks for the men who do it for a living.
            g.skills.gain_farming(0.02)
            if (tx, ty) in g.village_plots and not g.tile_is_mine(tx, ty):
                g.commit_crime()
        return
    if plot is not None and plot.kind in crop.FOOD_KINDS:
        if farm.harvest(g.world, g.inventory, plot, g.now, g.toast, tx=tx, ty=ty,
                        skill=g.skills.farming,
                        share=g.pay_share,
                        camp=getattr(g, "player_camp", None)):
            try:
                import playlog as _pl
                _pl.record(getattr(g, "root", None), "action",
                           action="harvest", crop=plot.kind)
            except Exception:
                pass
            if (tx, ty) in g.village_plots and not g.tile_is_mine(tx, ty):
                g.commit_crime()
        return
    if plot is not None and plot.kind in crop.FIBRE_KINDS:
        if farm.harvest(g.world, g.inventory, plot, g.now, g.toast,
                        tx=tx, ty=ty, skill=g.skills.farming,
                        share=g.pay_share,
                        camp=getattr(g, "player_camp", None)):
            try:
                import playlog as _pl
                _pl.record(getattr(g, "root", None), "action",
                           action="harvest", crop=plot.kind)
            except Exception:
                pass
            g.skills.gain_farming(0.02)
            if (tx, ty) in g.village_plots and not g.tile_is_mine(tx, ty):
                g.commit_crime()
        return

    wild = wildcrop.at(g.world, tx, ty, g.visible_villages)
    if wild is not None:
        wildcrop.harvest(g.world, tx, ty, wild[0], wild[1], g.inventory, g.toast,
                         share=g.pay_share)
        g.skills.gain_farming(0.02)      # wild or sown, the hand learns alike
        return

    if item_id == "shovel":
        farm.dig(g.world, g.ground, tx, ty, g.toast)
    elif item_id == "watering_can":
        farm.water(g.world, g.ground, tx, ty, g.toast)
    elif item_id in crop.SEED_CROP:
        _sown = farm.plant(g.world, g.ground, g.inventory, tx, ty, g.now, g.toast,
                           item_id, g.skills.farming)
        if _sown:
            try:
                import playlog as _pl
                _pl.record(getattr(g, "root", None), "action",
                           action="plant", seed=item_id)
            except Exception:
                pass
        if _sown and g.tile_is_mine(tx, ty):
            # A PLOT OF HIS OWN, and what a hired farmer can be put to.
            if not isinstance(getattr(g.player, "plots", None), set):
                g.player.plots = set()
            g.player.plots.add((tx, ty))
    return copen
