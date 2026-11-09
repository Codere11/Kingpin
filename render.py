"""THE WORLD RENDER PASS, pulled out of main's frame."""
import pygame
import plog


_ge2_seen = [False]


def draw_exterior(g, cx, cy, show_names=False, target=None):
    target = target if target is not None else g.screen
    g.static_layer.draw(target, cx, cy, g.vw, g.vh)
    g.blood.draw(target, cx, cy, g.vw, g.vh)
    world_villages = g.villages.visible(cx, cy, g.vw, g.vh,
                                      extra=g.hub_world.hubs)
    world_trees = g.trees.visible(cx, cy, g.vw, g.vh)
    view = g.pygame.Rect(cx - 150, cy - 150, g.vw + 300, g.vh + 300)
    for village in world_villages:
        g.fence.draw(target, cx, cy, village, view)
    for rect in g.built_fences:
        if view.colliderect(rect):
            g.fence.draw_segment(target, cx, cy, rect)
    for rect in g.camp_walls:
        if view.colliderect(rect):
            g.fence.draw_segment(target, cx, cy, rect)
    for rect in g.built_gates:
        if view.colliderect(rect):
            g.fence.draw_gate(target, cx, cy, rect)
    # THE CAMP, drawn on the ground.
    try:
        import gulag as _gulag_d
        _gulag_d.draw(target, cx, cy, view)
    except Exception as _ge2:
        if not getattr(main, "_ge2_seen", False):
            render._ge2_seen = True
            import traceback as _tb2
            plog.log("GULAG-DRAW-ERROR", repr(_ge2)[:120])
            plog.log("GULAG-TRACE", _tb2.format_exc()[:900])
    # THE RAILWAY, on the ground under everything that stands on it.
    try:
        import rail as _rail
        _rail.ensure(g.villages.villages)
        _rail.draw(target, cx, cy, g.vw, g.vh)
    except Exception as _re:
        plog.log("RAIL-ERROR", repr(_re)[:120])
    # ...AND THEN THE ENGINE, ON TOP OF ITS OWN TRACK. Riding, though, the
    # ground is painted first and the track goes over it: from the train
    # the rail is the thing that matters, not the grass under it.
    if not getattr(g.player, "aboard", False):
        try:
            g._TEST_TRAIN[0].draw(target, cx, cy)
            g._TEST_TRAIN[0].draw_knocked(target, cx, cy)
        except Exception:
            pass
    items = []
    # THE DEAD ARE ON THE GROUND. Bodies are sorted into the same painter's
    # list as the living, so a man walking in front of a corpse stands in
    # front of it and one behind it does not. Nothing ever called
    # corpse.draw: a body could be clicked and looted and was never ONCE
    # put on the g.screen.
    for _c in g.corpse_mod.CORPSES:
        if not view.collidepoint(_c.x, _c.y):
            continue
        items.append((_c.y, lambda c=_c: c.draw(target, cx, cy, g.now)))
    for (x, y, planted_at, kind, biome) in g.crop.visible_plants(g.world, cx, cy,
                                                               g.vw, g.vh):
        if not view.collidepoint(x, y):
            continue
        items.append((y, lambda x=x, y=y, p=planted_at, k=kind, b=biome:
                      g.crop.draw_crop(target, x, y, k, g.now - p, cx, cy, b)))
    _stump = g.trees.stump()
    for (x, y, kind, stage) in g.wildcrop.visible(g.world, world_villages,
                                                cx, cy, g.vw, g.vh):
        if not view.collidepoint(x, y):
            continue
        age = (stage + 0.4) * g.crop.GROW_SECONDS / 4.0
        items.append((y, lambda x=x, y=y, e=age, k=kind:
                      g.crop.draw_crop(target, x, y, k, e, cx, cy, None)))
    for tree in world_trees:
        items.append((tree.y, lambda t=tree, s=_stump:
                      t.draw(target, cx, cy, s)))
    for chunk in g.ore_field.visible(cx, cy, g.vw, g.vh):
        if view.collidepoint(chunk.x, chunk.y):
            items.append((chunk.y,
                          lambda c=chunk: g.ore_field.draw(target, cx, cy, c)))
    for enemy in g.enemies:
        if view.collidepoint(enemy.x, enemy.y):
            items.append((enemy.y, lambda e=enemy: e.draw(target, cx, cy)))
    for rabbit in g.rabbits:
        if view.collidepoint(rabbit.x, rabbit.y):
            items.append((rabbit.y, lambda r=rabbit: r.draw(target, cx, cy)))
    # ...AND THE PLAYER'S OWN, drawn whether or not any village is in
    # sight. This block used to sit INSIDE the village loop, so a house
    # built out in the open was never drawn at all: solid, enterable, and
    # invisible.
    for house in g.built_houses:
        if not view.colliderect(house.sight_rect):
            continue
        items.append((house.base_y, lambda h=house: h.draw(target, cx, cy)))
    for village in world_villages:
        items.append((village.board.bottom,
                      lambda v=village: v.draw_board(target, cx, cy)))
        for wp in village.workplaces:
            if not view.colliderect(wp.sight_rect):
                continue
            items.append((wp.base_y, lambda w=wp: w.draw(target, cx, cy)))
        for house in village.houses:
            if not view.colliderect(house.sight_rect):
                continue
            items.append((house.base_y, lambda h=house: h.draw(target, cx, cy)))
        for npc in village.npcs:
            if npc.asleep or npc.in_interior:
                continue
            if npc is g._TRUTH[0]:
                continue        # drawn once, with the g.world, below
            if not view.collidepoint(npc.x, npc.y):
                continue
            near = show_names and ((npc.x - g.player.x) ** 2
                                   + (npc.y - g.player.y) ** 2) < 260.0 ** 2
            items.append((npc.y, lambda n=npc, s=near:
                          n.draw(target, cx, cy, s)))
    if g._TRUTH[0] is not None:
        _tn = g._TRUTH[0]
        try:
            g._draws["n"] = g._draws.get("n", 0) + 1
            if g._draws["n"] % 120 == 1:
                plog.log("TRUTH-DRAW", "at", "%d,%d" % (int(_tn.x), int(_tn.y)),
                         "view", view.collidepoint(_tn.x, _tn.y),
                         "player", "%d,%d" % (int(g.player.x), int(g.player.y)))
        except Exception:
            pass
        if view.collidepoint(_tn.x, _tn.y):
            _tnear = show_names and ((_tn.x - g.player.x) ** 2
                                     + (_tn.y - g.player.y) ** 2) < 260.0 ** 2
            items.append((_tn.y, lambda n=_tn, s=_tnear:
                          n.draw(target, cx, cy, s)))
    # THE OBSERVATION CAMP: a few natives and a soldier standing by the spawn.
    for _n in getattr(g, "_observe_npcs", ()):
        if view.collidepoint(_n.x, _n.y):
            items.append((_n.y, lambda n=_n: n.draw(target, cx, cy, False)))
    for _s in getattr(g, "_observe_soldiers", ()):
        if view.collidepoint(_s.x, _s.y):
            items.append((_s.y, lambda s=_s: s.draw(target, cx, cy)))
    items.sort(key=lambda item: item[0])
    for _y, draw in items:
        draw()
    # THE CROWN'S SHIP, drawn LAST so nothing on the ground ever covers it.
    try:
        import ship as _ship
        import world as _world
        _ship.draw(target, cx, cy,
                   _world.coast_x(0.0, getattr(g.world, "seed", 0)) + 56.0, 0.0)
    except Exception as _ship_err:
        try:
            import plog as _plog
            _plog.log("SHIP-DRAW-ERROR", repr(_ship_err)[:160])
        except Exception:
            pass
    # THE 1x1 GRID MESH when a buildable is in the hand -- UNDER the blocks,
    # so a placed row covers its own seam lines and stays one solid wall. It
    # also shows while designating a settlement field.
    try:
        import block as _block
        _sel = g.inventory.selected_stack()
        _sel_id = _sel.defn.id if _sel else None
        if _sel_id in _block.BUILDABLE or getattr(g, "field_design", False):
            _block.draw_grid(target, cx, cy, g.vw, g.vh, g.wmouse_x, g.wmouse_y)
    except Exception:
        pass
    # MINECRAFT-STYLE BLOCKS, snapped to the 1x1 squares.
    try:
        import block as _block
        _block.draw_blocks(target, getattr(g, "built_blocks", {}), cx, cy, view)
    except Exception:
        pass
    if getattr(g.player, "aboard", False):
        # RIDING: the permanent way is drawn OVER the ground, and the
        # engine over the rail.
        try:
            import rail as _rail_r
            _rail_r.ensure(g.villages.villages)
            _rail_r.draw(target, cx, cy, g.vw, g.vh)
        except Exception:
            pass
        try:
            g._TEST_TRAIN[0].draw(target, cx, cy)
            g._TEST_TRAIN[0].draw_knocked(target, cx, cy)
        except Exception:
            pass


def draw_boot(surface, title, prog, pygame) -> None:
    w, h = surface.get_size()
    surface.fill((14, 12, 16))
    f_big = pygame.font.SysFont("dejavusansmono", max(14, h // 22), bold=True)
    f_small = pygame.font.SysFont("dejavusansmono", max(10, h // 44))
    head = f_big.render(title, True, (226, 188, 98))
    surface.blit(head, (w // 2 - head.get_width() // 2, int(h * 0.38)))
    bar = pygame.Rect(int(w * 0.22), int(h * 0.52), int(w * 0.56), max(6, h // 40))
    pygame.draw.rect(surface, (34, 30, 26), bar)
    fill = bar.copy()
    fill.w = max(2, int(bar.w * max(0.02, min(1.0, prog))))
    pygame.draw.rect(surface, (226, 188, 98), fill)
    pygame.draw.rect(surface, (110, 90, 54), bar, 1)
    note = f_small.render("settling in", True, (122, 110, 98))
    surface.blit(note, (w // 2 - note.get_width() // 2, bar.bottom + 10))
    pygame.display.flip()
