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
import nemesis
import ore
import village as village_mod
import wildcrop
from interior import Interior, fill_loot
from ui import ChestPanel


def fire(player, inventory, skills, combat, cam_x, cam_y, zoom, toast) -> None:
    stack = inventory.selected_stack()
    if stack is None or stack.defn.id not in (guns.RIFLE, guns.SHOTGUN):
        return
    kind = stack.defn.id
    if player.reloading > 0.0 or player.gun_cd > 0.0:
        return
    if player.mags.get(kind, 0) <= 0:
        toast("Empty \u2014 press R to reload")
        return
    player.mags[kind] -= 1
    player.gun_cd = guns.FIRE_CD[kind]
    fx, fy = player.facing
    px, py = -fy, fx
    muzzle_x = player.x + fx * 30.0 + px * 7.0
    muzzle_y = player.y + fy * 30.0 + py * 7.0
    mouse_x, mouse_y = pygame.mouse.get_pos()          # window space
    wmouse_x, wmouse_y = mouse_x / zoom, mouse_y / zoom  # world space
    distance = math.hypot((cam_x + wmouse_x) - muzzle_x,
                          (cam_y + wmouse_y) - muzzle_y)
    spread = skills.shot_spread()
    for _ in range(guns.PELLETS[kind]):
        extra = 0.0 if kind == guns.RIFLE else 0.11   # shotgun scatters
        combat.fire(muzzle_x, muzzle_y, player.facing_angle, distance,
                    shooter=player, owner="player", damage=guns.DAMAGE[kind],
                    team="player", spread=spread + extra)
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
    if struck.strikes >= ore.STRIKES:
        struck.mined = True
        ore_field.mined.add(struck.cell)
        amount = random.randint(ore.YIELD_LO, ore.YIELD_HI)
        inventory.add("iron", amount)
        pay_share("iron", amount)
        mark_dirty()
        toast(f"Mined iron   +{amount}")
    else:
        toast(f"Mining\u2026  {struck.strikes}/{ore.STRIKES}")


def use_axe(g, kills) -> int:
    """Swing the axe: men, beasts, trees, fences, and doors in one arc."""
    import main as _m

    if g.player.dead or not g.player.can_swing():
        return kills
    g.player.start_swing()
    g.skills.gain_axe()
    # BARE HANDS. The same swing and the same skill whether or not the axe
    # is in the pack -- a fist simply is not an axe. See
    # g.skills.UNARMED_WEAKNESS: he hits for a quarter, and can still fight.
    _armed = g.inventory.count_of("axe") > 0
    melee = ((_m.MELEE_DAMAGE if _armed
              else _m.MELEE_DAMAGE / g.skills.UNARMED_WEAKNESS)
             * g.skills.axe_damage_scale())
    angle = g.player.facing_angle
    g.combat.spawn_swing(g.player.x, g.player.y, angle)

    def in_arc(tx, ty, extra=0.0):
        dx, dy = tx - g.player.x, ty - g.player.y
        if math.hypot(dx, dy) > _m.AXE_REACH + extra:
            return False
        delta = abs(((math.atan2(dy, dx) - angle + math.pi) % (2.0 * math.pi)) - math.pi)
        return delta <= _m.AXE_ARC

    for enemy in g.enemies:
        if enemy.alive and in_arc(enemy.x, enemy.y, enemy.radius):
            _was_alive = getattr(enemy, "alive", True)
            if (getattr(enemy, "is_militia", False)
                    or getattr(enemy, "militia", False)):
                try:
                    import detain as _da
                    _da.militia_attacked(g.player, enemy, list(g.enemies),
                                         list(village_mod.PEOPLE))
                except Exception:
                    pass
            enemy.take_damage(melee)
            if _was_alive and not getattr(enemy, "alive", True):
                try:
                    import detain as _dk
                    _dk.militia_killed(g.player, enemy, list(g.enemies),
                                       list(village_mod.PEOPLE))
                except Exception:
                    pass
            g.blood.spawn(enemy.x, enemy.y, 8, 14.0)
            if (g.player.nation is not None
                    and getattr(enemy, "nation", None) == g.player.nation):
                g.banish(g.player.nation)
    for rabbit in g.rabbits:
        if rabbit.alive and in_arc(rabbit.x, rabbit.y, rabbit.radius):
            died = rabbit.take_damage(melee)
            g.blood.spawn(rabbit.x, rabbit.y, 8, 12.0)
            if died:
                amount = random.randint(1, 2)
                g.inventory.add("raw_meat", amount)
                g.toast(f"Caught a rabbit   +{amount} raw meat")
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
                died = npc.take_damage(melee, record=False)
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
        struck.strikes += 1
        g.combat.spawn_impact(struck.x, struck.y, (120, 90, 50))
        if struck.strikes >= _m.AXE_STRIKES:
            g.trees.fell(struck, g.now)
            amount = random.randint(10, 30)
            g.inventory.add("wood", amount)
            g.pay_share("wood", amount)
            g.combat.spawn_impact(struck.x, struck.y - 20, (86, 140, 64))
            g.toast(f"Felled a tree   +{amount} wood")
        else:
            g.toast(f"Chopping…  {struck.strikes}/{_m.AXE_STRIKES}")

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
    # NOTHING WITHIN 48 PX? THEN ANY CLICK NEAR HIM OPENS HIM. There is
    # exactly one truth-teller in the world; if you are standing beside him
    # and you click, that click is for him -- no distance arithmetic, no
    # camera/zoom to get wrong, nothing left to fail.
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
    else:
        g.open_trade(best)
    pygame.mouse.set_visible(True)
    plog.log("PICK", getattr(best, "name", "?"), "at", int(bd),
             "truth", getattr(best, "is_truth_teller", False))
    return (True, bopen, bpanel)


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
    stack = g.inventory.selected_stack()
    item_id = stack.defn.id if stack else None
    # ANYTHING THE VILLAGERS CALL FOOD, THE PLAYER CAN EAT. This was a
    # list of three hand-written cases -- and berries and cactus fruit were
    # not among them, so a man could starve with a pocket full of them
    # while every villager in the valley ate the same things for supper.
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
    if item_id in ("rifle", "shotgun"):
        g.fire()
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
                        tx=tx, ty=ty, share=g.pay_share):
            # LEAF IS ILLEGAL. Any agent close enough to have watched it
            # g.now knows it, and says so to the next one he meets.
            nemesis.note_offence_seen(g.player, "grew",
                                      crop.LEAF_ITEM.get(plot.kind,
                                                         plot.kind))
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
                        share=g.pay_share):
            if (tx, ty) in g.village_plots and not g.tile_is_mine(tx, ty):
                g.commit_crime()
        return

    wild = wildcrop.at(g.world, tx, ty, g.visible_villages)
    if wild is not None:
        wildcrop.harvest(g.world, tx, ty, wild[0], wild[1], g.inventory, g.toast,
                         share=g.pay_share)
        if wild[0] in crop.LEAF_KINDS:
            nemesis.note_offence_seen(g.player, "grew",
                                      crop.LEAF_ITEM.get(wild[0], wild[0]))
        g.skills.gain_farming(0.02)      # wild or sown, the hand learns alike
        return

    if item_id == "shovel":
        farm.dig(g.world, g.ground, tx, ty, g.toast)
    elif item_id == "watering_can":
        farm.water(g.world, g.ground, tx, ty, g.toast)
    elif item_id in crop.SEED_CROP:
        _sown = farm.plant(g.world, g.ground, g.inventory, tx, ty, g.now, g.toast,
                           item_id, g.skills.farming)
        if _sown and g.tile_is_mine(tx, ty):
            # A PLOT OF HIS OWN, and what a hired farmer can be put to.
            if not isinstance(getattr(g.player, "plots", None), set):
                g.player.plots = set()
            g.player.plots.add((tx, ty))
    return copen
