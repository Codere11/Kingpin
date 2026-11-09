"""THE FRAME LOOP, moved whole out of main()."""
import os
import sys
import time
import threading
import comm
import socio
import grief


def run(g):
    import main as _main_module
    _g = globals()
    for _kk, _vv in vars(_main_module).items():
        if not _kk.startswith("__"):
            _g[_kk] = _vv

    _house_check = 0.0

    while g.running:
        g._HEART[0] = time.time()
        g._boot_t0 = pygame.time.get_ticks()
        # THE FLAG COMES DOWN WHEN A FRAME WAS QUICK. Measure the PREVIOUS one:
        # at the top of a frame you cannot know how long this one will take.
        if g._boot_prev[0] is not None and g._boot_t0 - g._boot_prev[0] < 45:
            g._boot_slow[0] = False
        g._boot_prev[0] = g._boot_t0
        if g._boot_left[0] > 0 or g._boot_slow[0]:
            # AND IT STAYS UP UNTIL THE FRAMES STOP BEING SLOW. Ten frames was
            # a guess, and the heaviest work does not happen in the first ten:
            # the screen came down and then the window froze behind it. The
            # bar now comes down when the loop can keep up, not on a count.
            g.draw_boot(pygame.display.get_surface(), g._boot_title,
                      min(0.97, (10 - min(10, g._boot_left[0])) / 10.0 + 0.05))
            if g._boot_left[0] > 0:
                g._boot_left[0] -= 1
        g._framet0 = time.perf_counter()
        g._pt1 = g._pt2 = g._pt3 = g._framet0      # phase marks, if no phase runs
        # THE HIDDEN DART BAR DOES NOT REFILL. A dart is a dose; the bar is
        # how much of the dose is still in him. Refilling it between shots was
        # why ten darts never put the player down -- each 80-dart had its bite
        # healed back almost as fast as it landed.
        # THE MAN IS AT A PAIR OF NUMBERS, always. A tuple that reached
        # player.x/y used to take the whole frame down at the first `- vh/2`.
        try:
            if not isinstance(g.player.x, (int, float)):
                g._bad = (g.player.x, g.player.y)
                g.player.x = float(g._bad[0][0] if isinstance(g._bad[0], (tuple, list))
                                 else g._bad[0])
                g.player.y = float(g._bad[1][0] if isinstance(g._bad[1], (tuple, list))
                                 else g._bad[1]) if isinstance(g._bad[1], (int, float))                     else float(g._bad[1][1] if isinstance(g._bad[1], (tuple, list)) else 0.0)
                plog.log("POS-FIX", "player position was", repr(g._bad),
                         "->", int(g.player.x), int(g.player.y))
            elif not isinstance(g.player.y, (int, float)):
                g.player.y = float(g.player.y[0] if isinstance(g.player.y, (tuple, list))
                                 else 0.0)
                plog.log("POS-FIX", "player y was a container ->", int(g.player.y))
        except Exception as _px:
            plog.log("POS-FIX-FAIL", repr(_px)[:120])
        g.dt = min(g.clock.tick(FPS) / 1000.0, 0.05)
        g._PH["f"] += 1
        g.dt = min(g.dt * g.time_scale, 0.5)          # test-mode speed-up
        g.vw, g.vh = g.screen.get_size()
        g.mouse_x, g.mouse_y = pygame.mouse.get_pos()          # window space
        g.wmouse_x, g.wmouse_y = g.mouse_x / g.zoom, g.mouse_y / g.zoom  # world space

        # MOOD FROM MONEY: once a day, spread over the next minutes.
        try:
            socio.tick(list(village_mod.PEOPLE), g.now, g.dt)
        except Exception as _so:
            plog.log("SOCIO-ERR", repr(_so)[:120])
        # CHAT CLOUDS: what was just said to a man, fading over a few seconds.
        comm.tick_clouds(g.dt)
        # SEEING A CORPSE: -15 mood, once per body, spread over a minute.
        try:
            grief.tick(list(village_mod.PEOPLE), g.dt)
        except Exception as _gr:
            plog.log("GRIEF-ERR", repr(_gr)[:120])
        # A NEARBY MAN MAY SPEAK TO THE PLAYER: praise, insult or threaten.
        try:
            comm.tick_npc_to_player(list(village_mod.PEOPLE), g.player, g.dt)
        except Exception as _np:
            plog.log("NPC-TO-PLAYER-ERR", repr(_np)[:120])

        # THE LANES HAVE FINISHED A TICK: take their state before anything
        # reads a man or draws one. Never blocks -- a lane that is late is one
        # tick of latency, not a stall.
        dialogue.set_now(g.now)
        try:
            import trade as _trade_mod
            _trade_mod.set_now(g.now)
        except Exception:
            pass
        g._WORK.apply(g.world, g.combat)
        if (g._PH["f"] & 15) == 0:
            g._W_ON = g._WORK.ok()
            if g._WORK.enabled and not g._W_ON:
                g._WORK.stop()          # one lane died: step both here again
                g._WORK.enabled = False

        g._had_event = False
        for event in pygame.event.get():
            g._had_event = True
            # ---- THE KEY LOG. A one-line record of every key this build's
            # event loop actually receives, appended to
            # ~/.kingpin_saves/keys.log. It exists because I kept claiming the
            # inspector worked on the strength of my own synthetic events while
            # the real game did nothing, and guessing at the difference cost
            # hours. Now the game says what it heard.
            if event.type == pygame.KEYDOWN:
                try:
                    g._kf = os.path.expanduser("~/.kingpin_saves/keys.log")
                    with open(g._kf, "a") as _fh:
                        _fh.write("%s key=%s name=%s observer=%s test=%s\n"
                                  % (time.strftime("%H:%M:%S"),
                                     event.key,
                                     pygame.key.name(event.key),
                                     getattr(g.observer_, "open", "?"),
                                     g.time_scale > 1.0))
                except Exception:
                    pass
            if event.type == pygame.QUIT:
                g.save_now()
                g.running = False
            elif g.observer_.handle(event, g.player):
                # THE INSPECTOR ANSWERS FIRST, ABOVE EVERY MENU.
                #
                # Every branch below is an `elif`, so whichever one matches
                # EATS the key. With the pack open (`elif inventory_open:`) or
                # any other panel, I never reached the observer at all -- which
                # is why pressing TAB and then I did nothing: the pack had the
                # keyboard. The inspector is how the world is looked at, and
                # the world does not stop for a menu.
                pass
            elif (g.test_mode and event.type == pygame.KEYDOWN
                  and event.key == pygame.K_l):
                # TEST MODE ONLY. L puts ONE LEVEL on a random skill, so the
                # level-up shine can be looked at without earning it -- which
                # at MOVE_NEED = 7,500,000 px would otherwise be about three
                # hundred days of walking.
                #
                # A LEVEL IS A BAND, and each skill says how wide: 0.125 for
                # the three that run 0..1, and 1.0 for farming, which runs 0..8.
                # Both are eight levels, so this is ONE rule for all four.
                #
                # ALL FOUR, ON EVERY PRESS. A random one of four meant three
                # presses in four left the skill you were watching exactly
                # where it was, and a level-up you cannot see is not a test.
                g._done = []
                for _name, _band, _cap in (("movement", 0.125, 1.0),
                                           ("axe", 0.125, 1.0),
                                           ("shooting", 0.125, 1.0),
                                           ("farming", 1.0, 8.0)):
                    g._new = min(_cap,
                               (int(getattr(g.skills, _name) / _band) + 1) * _band)
                    setattr(g.skills, _name, g._new)
                    g._done.append("%s %d" % (_name[:4].title(), int(g._new / _band)))
                g.player.level_flash = g.player.LEVEL_FLASH
                g.toast("LEVEL UP    " + "   ".join(g._done))
            elif (g.test_mode and event.type == pygame.MOUSEBUTTONDOWN
                  and event.button == 1 and g.speed_button().collidepoint(event.pos)):
                g.speed_i = (g.speed_i + 1) % len(g.SPEEDS)
                g.time_scale = g.SPEEDS[g.speed_i]
                g.toast("Speed x%d" % int(g.time_scale))
            elif g.inside_mine is not None and getattr(g.inside_mine, "kind", "") != "house":
                # UNDERGROUND, THE WORLD IS NOT THERE. The mine uses its own
                # little coordinates, so a swing at the face was being read as
                # a swing at the world at those same numbers -- felling a tree
                # that stands hundreds of yards away above your head. Nothing
                # out there answers to the mouse while you are down here.
                #
                # BUT A MAN'S PACK IS STILL HIS. Everything was swallowed with
                # a bare `pass`, so the number keys did nothing and the mine
                # was a room you could not take your pickaxe out in -- the one
                # tool it is worked with. The hotbar and the pack answer to him
                # down here; nothing of the world does.
                if event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
                    g.hotbar.select_visible(event.key - pygame.K_1)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_0:
                    g._empty = g.hotbar.first_empty()
                    if g._empty is not None:
                        g.hotbar.select_visible(g._empty)
                        g.toast("Empty hands")
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
                    g.hotbar.handle_event(event)
                elif (event.type == pygame.KEYDOWN
                      and event.key in (pygame.K_i, pygame.K_TAB)):
                    g.inventory_open = not g.inventory_open
                    pygame.mouse.set_visible(g.inventory_open)
            elif event.type == pygame.VIDEORESIZE:
                g.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                g.vw, g.vh = event.w, event.h
            elif g.game_over:
                g.action = g.overlay.handle_event(event, g.vw, g.vh)
                if g.action == "respawn":
                    g.respawn()
                elif g.action == "quit":
                    g.save_now()
                    g.running = False
            elif g.smith_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.smith_open = False
                    pygame.mouse.set_visible(False)
                elif (event.type == pygame.KEYDOWN
                      and event.key in (pygame.K_SPACE, pygame.K_RETURN)):
                    g.work_msg = g.work_action("")
            elif g.board_open:
                if g.board_panel.handle_event(event):
                    g.board_open = False
                    pygame.mouse.set_visible(False)
            elif g.inventory_open:
                if event.type == pygame.KEYDOWN and event.key in (
                        pygame.K_e, pygame.K_ESCAPE, pygame.K_TAB):
                    g.inventory_open = False
                    g.panel.close()
                    pygame.mouse.set_visible(False)
                else:
                    g.panel.handle_event(event)
            elif g.stall_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.stall_open = False
                    g.mark_dirty()
                    g.save_now()
                    pygame.mouse.set_visible(False)
                else:
                    g.stall_panel.handle_event(event)
            elif g.folder_open:
                if g.folder_panel.handle_event(event):
                    g.folder_open = False
                    pygame.mouse.set_visible(False)
            elif g.body_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.body_panel.close()
                    g.body_open = False
                    g.mark_dirty()
                    pygame.mouse.set_visible(False)
                else:
                    g.body_panel.handle_event(event)
            elif g.worker_panel_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.worker_panel.close()
                    g.worker_panel_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.worker_panel.handle_event(event)
            elif g.chest_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.chest_panel.close()
                    g.save_now()
                    g.chest_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.chest_panel.handle_event(event)
            elif g.workshop_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.workshop_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.made = g.workshop_menu.handle_event(event)
                    if g.made is not None:
                        g.cost = g.made["cost"]
                        if not g.test_mode:
                            for item, qty in g.cost.items():
                                g.inventory.consume(item, qty)
                        g.inventory.add(g.made["id"], g.made.get("yield", 1))
                        g.save_now()
                        g.cost_txt = " + ".join(f"{q} {k}" for k, q in g.cost.items())
                        g.toast(f"Crafted {g.made['name']}"
                              + ("" if g.test_mode else f"   -{g.cost_txt}"))
            elif g.compass_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_f,
                                                                  pygame.K_ESCAPE):
                    g.compass_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.choice = g.compass_menu.handle_event(event)
                    if g.choice == "sethome":
                        g.compass_state.home = (g.player.x, g.player.y)
                        g.compass_open = False
                        pygame.mouse.set_visible(False)
                        g.save_now()
                        g.toast("Home set")
                    elif g.choice in ("village", "home"):
                        g.compass_state.mode = g.choice
                        g.compass_open = False
                        pygame.mouse.set_visible(False)
                        g.toast("Click to read the compass")
            elif g.confirm_open:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    g.confirm_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.answer = g.confirm.handle_event(event)
                    if g.answer is True:
                        if getattr(g.confirm, "mode", "join") == "leave":
                            g.leave_army()
                        else:
                            g.join_army(g.confirm.pending)
                        g.confirm_open = False
                        pygame.mouse.set_visible(False)
                    elif g.answer is False:
                        g.confirm_open = False
                        pygame.mouse.set_visible(False)
            elif g.pause_open:
                g.action = g.pause_menu.handle_event(event)
                if g.action == "close":
                    g.pause_open = False
                    pygame.mouse.set_visible(False)
                elif g.action == "respawn":
                    g.pause_open = False
                    g.respawn()
                    g.player.x, g.player.y = 0.0, 0.0
                    g.cam_x = g.player.x - WIDTH / (2.0 * ZOOM)
                    g.cam_y = g.player.y - HEIGHT / 2.0
                    pygame.mouse.set_visible(False)
                elif g.action == "exit":
                    g.save_now()
                    g.running = False
            elif g.map_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_m,
                                                                  pygame.K_ESCAPE):
                    g.map_open = False
                elif g.world_map is not None:
                    g.world_map.zoom_event(event)
            elif g.trade_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_e,
                                                                  pygame.K_ESCAPE):
                    g.trade_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.trade_menu.handle_event(event)
            elif g.build_menu_open:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_b,
                                                                  pygame.K_ESCAPE):
                    g.build_menu_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.choice = g.build_menu.handle_event(event)
                    if g.choice is not None:
                        g.build_menu_open = False
                        if g.choice in ("field", "orchard"):
                            # SETTLEMENT MODE: freeze the player, free the camera,
                            # and let him drag out a field/orchard designation.
                            g.field_design = True
                            g.field_mode = g.choice
                            g.field_start[0] = None
                            pygame.mouse.set_visible(True)
                        else:
                            g.placing = g.choice
                            g.fence_horizontal = True
            elif g.placing is not None:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE,
                                                                  pygame.K_b):
                    g.placing = None
                    pygame.mouse.set_visible(False)
                elif (event.type == pygame.KEYDOWN and event.key == pygame.K_r
                        and g.placing in ("fence", "gate")):
                    g.fence_horizontal = not g.fence_horizontal
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    g.placing = None
                    g.plot_start[0] = None
                    pygame.mouse.set_visible(False)
                elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                      and g.placing == "plot"):
                    g.plot_start[0] = g.placement_pos()      # one corner
                elif (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                      and g.placing == "plot"):
                    g._commit_plot()                        # ...and the other
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    g.try_place()
            elif g.field_design:
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE,
                                                                  pygame.K_b):
                    g.field_design = False
                    g.field_start[0] = None
                    g.zoom = ZOOM          # back to the normal world zoom
                    pygame.mouse.set_visible(False)
                elif event.type == pygame.MOUSEWHEEL:
                    _old = g.zoom
                    g.zoom = min(8.0, max(0.8, g.zoom * (1.25 if event.y > 0 else 1 / 1.25)))
                    _wx = g.cam_x + g.mouse_x / _old
                    _wy = g.cam_y + g.mouse_y / _old
                    g.cam_x = _wx - g.mouse_x / g.zoom
                    g.cam_y = _wy - g.mouse_y / g.zoom
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_EQUALS,
                                                                    pygame.K_PLUS,
                                                                    pygame.K_KP_PLUS):
                    _old = g.zoom
                    g.zoom = min(8.0, g.zoom * 1.25)
                    _wx = g.cam_x + g.mouse_x / _old
                    _wy = g.cam_y + g.mouse_y / _old
                    g.cam_x = _wx - g.mouse_x / g.zoom
                    g.cam_y = _wy - g.mouse_y / g.zoom
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_MINUS,
                                                                    pygame.K_KP_MINUS):
                    _old = g.zoom
                    g.zoom = max(0.8, g.zoom / 1.25)
                    _wx = g.cam_x + g.mouse_x / _old
                    _wy = g.cam_y + g.mouse_y / _old
                    g.cam_x = _wx - g.mouse_x / g.zoom
                    g.cam_y = _wy - g.mouse_y / g.zoom
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # snap the first corner to the 1x1 mesh
                    _wx = g.cam_x + g.wmouse_x
                    _wy = g.cam_y + g.wmouse_y
                    g.field_start[0] = (int(_wx // 32) * 32,
                                        int(_wy // 32) * 32)
                    g.field_raw[0] = (_wx, _wy)
                    g.field_del[0] = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    # right-drag: CUT the fields this rectangle touches
                    _wx = g.cam_x + g.wmouse_x
                    _wy = g.cam_y + g.wmouse_y
                    g.field_start[0] = (int(_wx // 32) * 32,
                                        int(_wy // 32) * 32)
                    g.field_raw[0] = (_wx, _wy)
                    g.field_del[0] = True
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if g.field_start[0] is None:
                        continue        # a button-up with no matching press
                    _ex = g.cam_x + g.wmouse_x
                    _ey = g.cam_y + g.wmouse_y
                    _raw = g.field_raw[0]
                    _moved = math.hypot(_ex - _raw[0], _ey - _raw[1]) if _raw is not None else 999.0
                    if _moved < 6.0:
                        # A CLICK on an existing FIELD cycles what it grows;
                        # an orchard has no crop choice.
                        for fd in g.field_designations:
                            if fd["rect"].collidepoint(_ex, _ey):
                                if fd.get("type") != "orchard":
                                    fd["kind"] = (g.next_field_kind(fd["kind"])
                                                   if g.next_field_kind else "wheat")
                                    g.toast("Field grows: %s" % fd["kind"])
                                    if g.sync_player_camp:
                                        g.sync_player_camp(g)
                                break
                        g.field_start[0] = None
                        g.field_raw[0] = None
                    else:
                        # A DRAG designates a new field (bread base) or orchard.
                        _sx, _sy = g.field_start[0]
                        _tx0, _ty0 = int(_sx // 32), int(_sy // 32)
                        _tx1, _ty1 = int(_ex // 32), int(_ey // 32)
                        _r = pygame.Rect(min(_tx0, _tx1) * 32,
                                         min(_ty0, _ty1) * 32,
                                         (abs(_tx0 - _tx1) + 1) * 32,
                                         (abs(_ty0 - _ty1) + 1) * 32)
                        if _r.w > 8 and _r.h > 8:
                            if g.field_mode == "orchard":
                                g.field_designations.append({"rect": _r, "type": "orchard", "kind": "orchard"})
                                g.toast("Orchard designated  (%d x %d)" % (_r.w, _r.h))
                            else:
                                g.field_designations.append({"rect": _r, "type": "field", "kind": "wheat"})
                                g.toast("Field designated  (%d x %d)" % (_r.w, _r.h))
                            if g.sync_player_camp:
                                g.sync_player_camp(g)
                        g.field_start[0] = None
                        g.field_raw[0] = None
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                    if g.field_start[0] is not None:
                        _sx, _sy = g.field_start[0]
                        _ex = g.cam_x + g.wmouse_x
                        _ey = g.cam_y + g.wmouse_y
                        _tx0, _ty0 = int(_sx // 32), int(_sy // 32)
                        _tx1, _ty1 = int(_ex // 32), int(_ey // 32)
                        _r = pygame.Rect(min(_tx0, _tx1) * 32,
                                         min(_ty0, _ty1) * 32,
                                         (abs(_tx0 - _tx1) + 1) * 32,
                                         (abs(_ty0 - _ty1) + 1) * 32)
                        # CUT OUT ONLY THE DRAGGED PIECE, not the whole field.
                        _out, _n = [], 0
                        for fd in g.field_designations:
                            f = fd["rect"]
                            _ix = max(f.x, _r.x); _iy = max(f.y, _r.y)
                            _ix2 = min(f.right, _r.right); _iy2 = min(f.bottom, _r.bottom)

                            def _piece(pr):
                                return {"rect": pr, "type": fd.get("type", "field"),
                                        "kind": fd.get("kind", "wheat")}

                            if _ix < _ix2 and _iy < _iy2:
                                _n += 1
                                if _iy > f.y:
                                    _out.append(_piece(pygame.Rect(f.x, f.y, f.w, _iy - f.y)))
                                if _iy2 < f.bottom:
                                    _out.append(_piece(pygame.Rect(f.x, _iy2, f.w, f.bottom - _iy2)))
                                if _ix > f.x:
                                    _out.append(_piece(pygame.Rect(f.x, _iy, _ix - f.x, _iy2 - _iy)))
                                if _ix2 < f.right:
                                    _out.append(_piece(pygame.Rect(_ix2, _iy, f.right - _ix2, _iy2 - _iy)))
                            else:
                                _out.append(fd)
                        g.field_designations = _out
                        if _n:
                            g.toast("Cleared %d area%s" % (_n, "" if _n == 1 else "s"))
                            if g.sync_player_camp:
                                g.sync_player_camp(g)
                        g.field_start[0] = None
                        g.field_raw[0] = None
                        g.field_del[0] = False
                # swallow every other key/click while designating
                continue
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_e:
                plog.log("E-KEY", "board", g.near_board() is not None,
                         "stall", g.near_stall() is not None,
                         "chest", g.near_chest() is not None,
                         "work", getattr(g.near_workplace(), "kind", None),
                         "house", g.inside_house is not None,
                         "at", int(g.player.x), int(g.player.y))
                if (g.near_workplace() is not None
                      and getattr(g.near_workplace(), "kind", None) in ("mine", "prison")):
                    plog.log("ENTER-TRY", getattr(g.near_workplace(), "kind", "?"),
                             "door", getattr(g.near_workplace(), "door", None),
                             "player", int(g.player.x), int(g.player.y))
                    _wp = g.near_workplace()
                    if getattr(_wp, "room", None) is None:
                        _wp.room = mine.MineRoom(g.world.seed ^ id(_wp))
                    g.mine_out = (g.player.x, g.player.y)
                    g.inside_mine = _wp
                    g.player._mine_latch = True      # let go of E first
                    g.player.x, g.player.y = g.inside_mine.room.W / 2.0, \
                        g.inside_mine.room.H - 70.0
                    g.cam_x = g.player.x - g.vw / 2.0
                    g.cam_y = g.player.y - g.vh / 2.0
                    pygame.mouse.set_visible(False)
                g._bv = g.near_board()
                if g._bv is not None:
                    g.board_village = g._bv
                    g.board_open = True
                    g.board_panel.scroll = 0
                    pygame.mouse.set_visible(True)
                elif g.near_stall() is not None:
                    # THE COUNTER IS A CHEST, AND WHATEVER IS IN IT IS FOR SALE.
                    g.stall_open = True
                    g.stall_panel = MarketPanel(g.inventory, g.near_stall())
                    pygame.mouse.set_visible(True)
                elif g.near_chest():
                    g.chest_open = True
                    g.chest_panel = ChestPanel(g.inventory, g.inside_house.interior.chest)
                    pygame.mouse.set_visible(True)
                elif g.near_brew():
                    g.mash_at_table()           # mash what you carry into wort
                elif (g.inside_house is not None
                        and g.inside_house.interior.barrel_near(g.player.x, g.player.y)
                        is not None):
                    g.use_barrel()              # fill it, or draw what it made
                elif g.near_lab():
                    g.craft_at_table()          # one article a press, and you learn
                elif g.near_workplace() is not None:
                    g.smith_shop = g.near_workplace()
                    g.smith_open = True
                    g.work_msg = ""
                    pygame.mouse.set_visible(True)
                elif g.near_workshop():
                    g.workshop_open = True
                    pygame.mouse.set_visible(True)
                else:
                    g.inventory_open = True
                    pygame.mouse.set_visible(True)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                g.build_menu.open("inside" if g.inside_house is not None else "outside")
                g.build_menu_open = True
                pygame.mouse.set_visible(True)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                g.stack = g.inventory.selected_stack()
                if g.stack is not None and g.stack.defn.id == "compass":
                    g.compass_menu.open(g.compass_state.home is not None)
                    g.compass_open = True
                    pygame.mouse.set_visible(True)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                g.comm_mode = not g.comm_mode
                if not g.comm_mode:
                    g.comm = None      # leaving the words puts the hands back empty
                pygame.mouse.set_visible(g.comm_mode)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                g.stack = g.inventory.selected_stack()
                kind = g.stack.defn.id if g.stack else None
                if (kind in (guns.RIFLE, guns.SHOTGUN) and g.player.reloading <= 0.0
                        and g.player.mags.get(kind, 0) < guns.MAG[kind]):
                    if g.inventory.count_of("ammo") > 0:
                        g.player.reloading = guns.reload_time(kind, g.skills.shooting)
                        g.player.reload_total = g.player.reloading   # for the bar
                        g.player.reload_kind = kind
                        g.toast("Reloading\u2026")
                    else:
                        g.toast("No ammo to reload with")
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE
                  and not (g.inventory_open or g.trade_open or g.board_open
                           or g.chest_open or g.stall_open or g.worker_panel_open
                           or g.workshop_open or g.smith_open or g.confirm_open
                           or g.map_open or g.pause_open or g.build_menu_open
                           or g.dialogue_panel.open_ or g.placing is not None)):
                # SPACE: LUNGE. A quarter of the wind, in the way he is holding
                # -- a step he cannot take twice in a breath.
                if g.player.lunge(pygame.key.get_pressed()):
                    try:
                        g._lx, g._ly = g.player.lunge_dir
                        g.combat.spawn_impact(g.player.x - g._lx * 18.0,
                                            g.player.y - g._ly * 18.0,
                                            (206, 196, 168))
                    except Exception:
                        pass
                else:
                    g.toast("No wind for a lunge" if g.player.lunge_cd <= 0.0
                          else "Not yet")
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_m
                  and not g.inventory_open and not g.trade_open and not g.board_open):
                # FOR EVERYBODY. The chart was test-mode only, which meant the
                # one thing a man on a road needs -- where am I and where is the
                # nearest town -- was a debug tool.
                g.map_open = not g.map_open
                if g.map_open and g.world_map is not None:
                    g.world_map.reset(g.player.x, g.player.y)   # the map follows him
                pygame.mouse.set_visible(g.map_open)
            elif (g.dialogue_panel.open_
                  and ((event.type == pygame.KEYDOWN
                        and event.key in (pygame.K_1, pygame.K_2, pygame.K_3,
                                          pygame.K_4, pygame.K_5, pygame.K_6,
                                          pygame.K_7, pygame.K_8, pygame.K_9,
                                          pygame.K_KP1, pygame.K_KP2,
                                          pygame.K_KP3, pygame.K_KP4,
                                          pygame.K_KP5, pygame.K_KP6,
                                          pygame.K_KP7, pygame.K_KP8,
                                          pygame.K_KP9,
                                          pygame.K_ESCAPE, pygame.K_q))
                       or (event.type == pygame.MOUSEBUTTONDOWN
                           and event.button == 1
                           and g.dialogue_panel.hit(event.pos)))):
                # ONLY ITS OWN FOUR KEYS. This branch used to take EVERY event
                # while the panel was open -- so one click opened it and from
                # then on the mouse, the wheel and the pack were dead: no NPC
                # could be clicked and the inventory could not be scrolled.
                # A conversation must never own the input system.
                _d = g.dialogue_panel.handle_event(event)
                if _d == "close":
                    pygame.mouse.set_visible(False)
                elif _d == "pack":
                    g._wn = g.dialogue_panel.npc
                    if g._wn is not None and getattr(g._wn, "pack", None) is not None:
                        g.worker_panel = ChestPanel(
                            g.inventory, work.bag(g._wn),
                            top_rows=4, top_label=getattr(g._wn, "name", "PACK"))
                        g.worker_panel_open = True
                        pygame.mouse.set_visible(True)
                elif _d == "trade":
                    g._dn = g.dialogue_panel.npc
                    g.dialogue_panel.close()
                    pygame.mouse.set_visible(False)
                    if g._dn is not None:
                        g.open_trade_menu(g._dn)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                # ESC USED TO PAUSE UNCONDITIONALLY, even with a menu already
                # open -- so a panel that would not close left a man with no
                # way out at all. ESC now closes what is open, and only opens
                # the pause menu when nothing is.
                if (g.inventory_open or g.trade_open or g.board_open or g.chest_open
                        or g.worker_panel_open or g.stall_open or g.body_open
                        or g.folder_open
                        or g.smith_open or g.workshop_open or g.confirm_open
                        or g.map_open or g.build_menu_open or g.placing is not None):
                    g.close_modals()
                elif g.pause_open:
                    g.pause_open = False
                    pygame.mouse.set_visible(False)
                else:
                    g.pause_open = True
                    pygame.mouse.set_visible(True)
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_TAB):
                # THE PACK NEEDED A KEY ABOVE GROUND AND NEVER HAD ONE.
                # inventory_open was only ever toggled inside the mine's key
                # block, so above ground the pack could not be opened at all --
                # and I never noticed, because I was pressing I for the
                # inspector and the inspector DOES answer it (main.py, the
                # observer branch). TAB is free here, so TAB opens the pack.
                g.inventory_open = not g.inventory_open
                pygame.mouse.set_visible(g.inventory_open)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_0:
                g.empty = g.hotbar.first_empty()
                if g.empty is not None:
                    g.hotbar.select_visible(g.empty)
                    g.comm = None
                    g.toast("Empty hands")
            elif event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
                if g.comm_mode and event.key - pygame.K_1 < 3:
                    g.comm = comm.KINDS[event.key - pygame.K_1]
                    g.toast("Equipped %s" % g.comm.title())
                else:
                    g.hotbar.select_visible(event.key - pygame.K_1)
                    g.comm = None
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
                if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                        and g.dialogue_panel.open_
                        and not g.dialogue_panel.hit(event.pos)):
                    g.dialogue_panel.close()          # click AWAY: put it away
                    pygame.mouse.set_visible(False)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    g._held = g.inventory.selected_stack()
                    g._held_id = g._held.defn.id if g._held else None
                    # A BUILDABLE IN THE HAND: LEFT CLICK PLACES A 1x1 BLOCK.
                    import block as _block
                    if g._held_id in _block.BUILDABLE and g.hotbar.slot_at(event.pos) is None:
                        try:
                            _wx = g.cam_x + event.pos[0] / ZOOM
                            _wy = g.cam_y + event.pos[1] / ZOOM
                            _tx = int(_wx // _block.TILE)
                            _ty = int(_wy // _block.TILE)
                            if _block.place_block(g, _tx, _ty, g._held_id):
                                g.toast("Placed a %s" % g._held_id)
                            else:
                                g.toast("No room or none left")
                        except Exception:
                            pass
                        g.consumed = True
                        break
                    if g._held_id == "secret_folder":
                        # A DEAD AGENT'S MAIL, OPENED BY A CLICK IN THE HAND.
                        g._pay = getattr(g._held, "payload", None)
                        if g._pay:
                            g.folder_panel = FolderPanel(g._pay)
                            g.folder_open = True
                            pygame.mouse.set_visible(True)
                            plog.log("FOLDER-OPEN", g._pay)
                            break
                    # A BODY IS LOOTED, NOT SWUNG AT. Whatever is in his hand
                    # -- axe included -- a click on a corpse opens the corpse.
                    g._bw = (g.cam_x + event.pos[0] / ZOOM,
                           g.cam_y + event.pos[1] / ZOOM)
                    g._body = corpse_mod.nearest(g._bw[0], g._bw[1])
                    if g._body is not None:
                        g.body_panel = ChestPanel(
                            g.inventory, g._body.pack,
                            top_label=getattr(g._body, "name", "a body"))
                        g.body_open = True
                        pygame.mouse.set_visible(True)
                        plog.log("BODY-OPEN", getattr(g._body, "name", "?"))
                        break
                    # A WEAPON IS AN ATTACK, NOT A CONVERSATION.
                    if g._held_id not in ("axe", "pickaxe", "rifle", "shotgun"):
                        if g.click_a_man(event.pos):
                            break
                g.consumed = g.hotbar.handle_event(event)
                if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                        and g.comm_mode):
                    _ci = comm.bar_slot_at(event.pos, g.vw, g.vh)
                    if _ci is not None:
                        g.comm = comm.KINDS[_ci]
                        g.toast("Equipped %s" % g.comm.title())
                        g.consumed = True
                if (not g.consumed and event.type == pygame.MOUSEBUTTONDOWN
                        and event.button == 1):
                    g.on_click()

        if g.sleep_timer > 0.0:                  # sleeping through the night
            g.sleep_timer -= g.dt
            if g.sleep_timer <= 0.0:
                g.now = g.next_morning(g.now)
                g.save_now()
                g.toast("You slept until morning")
            g.screen.fill((0, 0, 0))
            pygame.display.flip()
            continue
        # Autosave: whatever else happens, progress is never more than this far
        # behind (covers a crash on exit losing the session).
        g.save_timer -= g.dt
        if g.save_timer <= 0.0 and not g.game_over and not g.player.dead:
            g.save_timer = 20.0
            if g.save_dirty:
                g.save_dirty = False
                g.save_now()
        g.door_cooldown = max(0.0, g.door_cooldown - g.dt)
        g.work_cd = max(0.0, g.work_cd - g.dt)
        # WHY IS HE NOT MOVING? Every frame that any of these is set skips the
        # world update entirely -- and `board_open` zeroes the keys outright --
        # so a man can be frozen solid with the HUD happily drawing on top. If
        # the log has a BLOCKED line, the line names what did it.
        if (g.inventory_open or g.trade_open or g.build_menu_open or g.chest_open
                or g.workshop_open or g.confirm_open or g.pause_open or g.map_open
                or g.placing is not None or g.inside_house is not None
                or g.inside_mine is not None or g.board_open or g.smith_open):
            g._blk += g.dt
            # A MENU LEFT ALONE FOR TWENTY SECONDS RELEASES THE WORLD. Not a
            # fix for any particular panel -- a guarantee that no panel, known
            # or not yet written, can hold the game still for good.
            g._stuck = 0.0 if g._had_event else g._stuck + g.dt
            if g._stuck >= 20.0:
                g._stuck = 0.0
                g.close_modals("Closed: that menu had stopped responding")
            if g._blk >= 1.0:
                g._blk = 0.0
                plog.log("BLOCKED", "inv", g.inventory_open, "trade", g.trade_open,
                         "board", g.board_open, "chest", g.chest_open,
                         "smith", g.smith_open, "work", g.workshop_open,
                         "confirm", g.confirm_open, "pause", g.pause_open,
                         "map", g.map_open, "placing", g.placing is not None,
                         "house", g.inside_house is not None,
                         "mine", g.inside_mine is not None,
                         "dead", g.player.dead, "hp", int(g.player.health),
                         "at", "%d,%d" % (int(g.player.x), int(g.player.y)))
        else:
            g._blk = 0.0

        if (g.inside_house is not None and g.inside_mine is None
                and not g.game_over and not g.pause_open
                and not g.map_open and not g.confirm_open
                and not g.build_menu_open and g.placing is None):
            g._branch = 'house'
            g._HF[0] += 1
            g._now_hf = time.perf_counter()
            if g._now_hf - g._HF[1] >= 2.0:
                plog.log("HOUSE-FPS", "%.1f fps indoors"
                         % (g._HF[0] / max(1e-6, g._now_hf - g._HF[1])))
                g._HF[0], g._HF[1] = 0, g._now_hf
            g.keys = pygame.key.get_pressed()
            if g.board_open or g.smith_open:                       # reading the board: stand still
                g.keys = _NO_KEYS
            # THE ROOM IS ZOOMED, SO THE AIM MUST BE. Reading the window
            # mouse against a zoomed camera skews every look by the zoom --
            # pointing left of centre actually aimed right, and the whole room
            # could only be half looked at.
            g.aim = (g.wmouse_x - (g.player.x - g.cam_x),
                   g.wmouse_y - (g.player.y - g.cam_y))
            g.player.skill_speed = g.skills.move_scale()
            g.award_levels()
            g.player.skill_stamina = g.skills.stamina_scale()
            g.player.skill_axe_cd = g.skills.axe_cooldown()
            g._px0, g._py0 = g.player.x, g.player.y
            g.player.update(g.dt, g.keys, g.aim, 1.0)
            g.skills.gain_movement(math.hypot(g.player.x - g._px0, g.player.y - g._py0))
            g.clamp_world()          # the world ends where the loading screen did
            g.settle_reload()
            house = g.inside_house
            g.interior = house.interior
            g.player.x, g.player.y = resolve_circle_rects(
                g.player.x, g.player.y, g.player.radius, g.interior.colliders)
            g.cam_x = min(max(g.player.x - g.vw / 2.0, 0.0), max(0.0, g.interior.W - g.vw))
            g.cam_y = min(max(g.player.y - g.vh / 2.0, 0.0), max(0.0, g.interior.H - g.vh))
            if g.interior.W <= g.vw:
                g.cam_x = g.interior.W / 2.0 - g.vw / 2.0
            if g.interior.H <= g.vh:
                g.cam_y = g.interior.H / 2.0 - g.vh / 2.0
            if g.door_cooldown <= 0.0 and g.interior.door_rect.colliderect(
                    pygame.Rect(g.player.x - 8, g.player.y - 8, 16, 16)):
                g.exit_house()
            else:
                # Keep the outside world alive, so the window view is live.
                g.now += g.dt
                # LOCKED ON: the player IS the camera, and he stands where the
                # watched man stands. Every existing line that reads player.x
                # then follows the target -- the camera, the visible villages,
                # the ground -- with nothing else changed. The ground around
                # the PLAYER is never built, because the camera left him.
                if g.observer_.target is not None and g.observer_.target.alive:
                    # THE PLAYER IS NOT MOVED. He stays exactly where he was --
                    # pinning him onto the target and letting the camera follow
                    # the player was the whole confusion. Only the CAMERA goes
                    # to the watched man; see the cam_x/cam_y above.
                    g.player.god = True
                    g.observer_.tick(g.now)
                creatures_set_time(g.now)
                wildcrop.set_time(g.now)
                wildcrop.set_world(g.world)
                # A ROOM IS NOT THE WORLD. Standing in a house used to re-cut
                # the visible villages, re-collect every collider and step the
                # whole neighbourhood every frame -- exactly what a mine does
                # not do, which is why a mine never stutters and a doorway did.
                # The world is stepped in its own lanes; from indoors it is
                # only the clock that has to keep running.
                g.night = g.night_factor() > 0.38
                g.sim_villages = []
                g.sim_colliders = []
                g.world_accum += g.dt
                g.world_tick = g.world_accum >= WORLD_STEP
                if g.world_tick:
                    g.world_dt = g.world_accum
                    g.world_accum = 0.0
                    if g._W_ON:
                        g._WORK.tick(g.now, g.world_dt, g.day_phase(), g.night, g.player,
                                   g.enemies)
                for village in g.sim_villages:
                    if not g.world_tick or g._W_ON:
                        break
                    # THE BUBBLE, NOT THE VIEW. `visible()` is a DRAWING cull --
                # a fence is big, so it returns every town whose wall is
                # anywhere near the frame. Stepping each of those costs a dozen
                # economy passes, and several towns at once is what made the
                # frame die at a gate. A town's books run when the man is near
                # the town.
                if (abs(village.x - g.player.x) < village.radius + 3000.0
                        and abs(village.y - g.player.y) < village.radius + 3000.0):
                    # THE SEARCH, EVERY FRAME: one guard, the men near him,
                    # and nothing else in the world.
                    try:
                        import gate as gate_mod
                        g._r2 = gate_mod.tick_town(g.world_dt, village)
                        if g._r2 is not None and g._r2[0] == "caught":
                            village.provoke()
                        elif g._r2 is not None:
                            pass
                    except Exception:
                        pass
                    # THE TOWN'S BOOKS, TEN TIMES A SECOND. They are all
                    # day-guarded anyway; asking sixty times a second whether
                    # the day has changed was most of the town phase's cost.
                    g._bk = g._town_acc.get(id(village), 0.0) + g.world_dt
                    if g._bk >= 0.1:
                        g._town_acc[id(village)] = 0.0
                        village.update(g._bk, g.world, g.now, g.day_phase())
                    else:
                        g._town_acc[id(village)] = g._bk
                for enemy in g.enemies:
                    if enemy.alive:
                        enemy.update(g.dt, house, g.combat, [], 1.0, 1.0, False)
                        enemy.x, enemy.y = resolve_circle_rects(
                            enemy.x, enemy.y, enemy.radius, g.sim_colliders)
                g.combat.update(g.dt)
                g.blood.update(g.dt)
                # the ground worker still keeps the house's own chunks ready
                g.ground.update(4, house.x - g.vw / 2.0, house.y - g.vh / 2.0, g.vw, g.vh)
        elif (g.inside_house is None and g.inside_mine is None
              and not g.game_over and not g.inventory_open and not g.build_menu_open
              and not g.chest_open and not g.trade_open and not g.workshop_open
              and not g.confirm_open and not g.pause_open and not g.map_open
              and g.placing is None):
            g._branch = 'world'
            if abs(g.player.x) < 3000.0 and abs(g.player.y) < 3000.0:
                # He is standing on room coordinates in the open world.
                g._wx, g._wy = getattr(g.player, "world_xy", (0.0, 0.0))
                if g._wx or g._wy:
                    g.player.x, g.player.y = g._wx, g._wy
                    plog.log("WORLD-POS-FIX", "room coordinates in the world;"
                             " put back at", int(g._wx), int(g._wy))
            g.now += g.dt
            creatures_set_time(g.now)
            wildcrop.set_time(g.now)
            wildcrop.set_world(g.world)
            g.night = g.night_factor() > 0.38

            g.keys = pygame.key.get_pressed()
            if g.board_open or g.field_design:      # reading the board / designating: stand still
                g.keys = _NO_KEYS
            g.aim = (g.wmouse_x - (g.player.x - g.cam_x),
                   g.wmouse_y - (g.player.y - g.cam_y))   # the world mouse, not the window's
            g.foliage = g.trees.foliage(g.player.x, g.player.y)
            g.player.skill_speed = g.skills.move_scale()
            g.award_levels()
            g.player.skill_stamina = g.skills.stamina_scale()
            g.player.skill_axe_cd = g.skills.axe_cooldown()
            g._px0, g._py0 = g.player.x, g.player.y
            # THE HEARTBEAT. Written from INSIDE the overworld update, every two
            # seconds of game time, so that "the world froze" has evidence: if
            # these lines stop while the game is still drawing the HUD, the
            # overworld branch is not being reached -- and the last line before
            # they stop says where the loop was.
            g._hb += g.dt
            if g._hb >= 2.0:
                g._hb = 0.0
                plog.log("HEARTBEAT", "x", int(g.player.x), "y", int(g.player.y),
                         "dt", round(g.dt, 3), "board", g.board_open,
                         "dead", g.player.dead,
                         "hp", int(g.player.health))
            if getattr(g.player, "aboard", False):
                _tr = g._TEST_TRAIN[0]
                if _tr is not None:
                    if not g._EXPRESS[0]:
                        # AN EXPRESS, NOT A TOUR: somebody is aboard and the
                        # camp is where he is going.
                        try:
                            import gulag as _gl_x
                            import train as _tmx
                            import rail as _railx
                            g._glx, g._gly = _gl_x.gate_point()
                            g._len = _tr.to_camp((g._glx, g._gly))
                            g._EXPRESS[0] = True
                            plog.log("EXPRESS", "the engine runs for the camp |",
                                     int(g._len), "px of track |",
                                     round(g._len / _tmx.TRAIN_SPEED / 60.0, 1),
                                     "minutes")
                        except Exception as _xe:
                            plog.log("EXPRESS-ERR", repr(_xe)[:140])
                    g.player.x, g.player.y = _tr.x, _tr.y
                    g.cam_x = g.player.x - g.vw / 2.0
                    g.cam_y = g.player.y - g.vh / 2.0
                    try:
                        import gulag as _gl_end
                        if ((_tr.x - _gl_end.gate_point()[0]) ** 2
                                + (_tr.y - _gl_end.gate_point()[1]) ** 2) < 600.0 ** 2:
                            # THE END OF THE LINE IS THE CAMP
                            g._detain_release = True
                            try:
                                import detain as _dr
                                _dr.release_kit(g.player, None)
                                # the tour resumes; the express is over
                                try:
                                    import rail as _railr
                                    _tr.set_route(_railr.tour())
                                    g._EXPRESS[0] = False
                                except Exception:
                                    pass
                                plog.log("DROP-OFF", "the player is put down at the camp",
                                         "with the other", len(getattr(_tr, "aboard", []) or []),
                                         "prisoners")
                            except Exception:
                                pass
                    except Exception:
                        pass
            if getattr(g.player, "sleep_t", 0.0) > 0.0:
                g.player.sleep_t = max(0.0, g.player.sleep_t - g.dt)
                g.keys = _NO_KEYS
            g.player.update(g.dt, g.keys, g.aim, 1.0 - 0.25 * g.foliage)
            if getattr(g.player, "aboard", False):
                _tr = g._TEST_TRAIN[0]
                if _tr is not None:
                    if not g._EXPRESS[0]:
                        # AN EXPRESS, NOT A TOUR: somebody is aboard and the
                        # camp is where he is going.
                        try:
                            import gulag as _gl_x
                            import train as _tmx
                            import rail as _railx
                            g._glx, g._gly = _gl_x.gate_point()
                            g._len = _tr.to_camp((g._glx, g._gly))
                            g._EXPRESS[0] = True
                            plog.log("EXPRESS", "the engine runs for the camp |",
                                     int(g._len), "px of track |",
                                     round(g._len / _tmx.TRAIN_SPEED / 60.0, 1),
                                     "minutes")
                        except Exception as _xe:
                            plog.log("EXPRESS-ERR", repr(_xe)[:140])
                    g.player.x, g.player.y = _tr.x, _tr.y
                    g.cam_x = g.player.x - g.vw / 2.0
                    g.cam_y = g.player.y - g.vh / 2.0
                    try:
                        import gulag as _gl_end
                        if ((_tr.x - _gl_end.gate_point()[0]) ** 2
                                + (_tr.y - _gl_end.gate_point()[1]) ** 2) < 600.0 ** 2:
                            # THE END OF THE LINE IS THE CAMP
                            g._detain_release = True
                            try:
                                import detain as _dr
                                _dr.release_kit(g.player, None)
                                # the tour resumes; the express is over
                                try:
                                    import rail as _railr
                                    _tr.set_route(_railr.tour())
                                    g._EXPRESS[0] = False
                                except Exception:
                                    pass
                                plog.log("DROP-OFF", "the player is put down at the camp",
                                         "with the other", len(getattr(_tr, "aboard", []) or []),
                                         "prisoners")
                            except Exception:
                                pass
                    except Exception:
                        pass
            if getattr(g.player, "sleep_t", 0.0) > 0.0:
                try:
                    g._z = g.font.render("Zzz", True, (232, 232, 240))
                    g.screen.blit(g._z, (g.vw // 2 + 14, g.vh // 2 - 44))
                except Exception:
                    pass
            if g._chain is not None:
                try:
                    if g._chain["hub"] is None:
                        g._chain["hub"] = g.hub_world.hubs[0]
                        g._chain["t0"] = g.now
                        g._csay("CHAIN watching hub %s" % g._chain["hub"].name)
                    g._hubx = g._chain["hub"]      # NOT `_hb`: that is the
                    # heartbeat timer, and overwriting it with a Hub object
                    # raised a TypeError on the very next frame -- which is why
                    # this report printed its first line and then nothing.
                    g._live = [n for n in g._hubx.npcs if n.alive]
                    g._farm = next((n for n in g._live if n.job == "farm"), None)
                    g._art = next((n for n in g._live if n.job in ("lab", "brewery")), None)
                    g._trd = next((n for n in g._live if n.job == "trader"), None)
                    g._LEAF = ("tobacco", "red_mushroom", "agave", "plant", "mushroom")
                    g._MADE = ("cigar", "dried_mushroom", "beer", "liqueur", "mezcal")
                    g._food = sum(int((g._farm.stock if g._farm else {}).get(x, 0))
                                for x in economy.FOOD) if g._farm else 0
                    g._shelf = sum(int(g._hubx.ledger_goods.get(x, 0)) for x in economy.FOOD)
                    g._leaf = (sum(int((g._art.stock if g._art else {}).get(k, 0)) for k in g._LEAF)
                             if g._art else 0)
                    g._made = (sum(int((g._art.stock if g._art else {}).get(k, 0)) for k in g._MADE)
                             if g._art else 0)
                    g._carry = (sum(int((g._trd.stock if g._trd else {}).get(k, 0)) for k in g._MADE)
                              if g._trd else 0)
                    g._st = g._chain["seen"]
                    g._st["food"] = max(g._st.get("food", 0), g._food + g._shelf)
                    g._st["leaf"] = max(g._st.get("leaf", 0), g._leaf)
                    g._st["made"] = max(g._st.get("made", 0), g._made)
                    g._st["carry"] = max(g._st.get("carry", 0), g._carry)
                    g._st["trip"] = g._st.get("trip", 0) or bool(g._hubx._carrier)
                    g._st["stage"] = g._hubx._stage
                    g._st["ledger"] = int(g._hubx.ledger_coins)
                    g._chain["f"] += 1
                    g._chain["t"] = time.perf_counter() - g._chain["wall0"]
                    # A STATUS LINE EVERY MINUTE: the actual contents, item by
                    # item. Without this the test could only say "the leaf did
                    # not arrive" -- never where it went.
                    if g._chain["t"] - g._chain.get("last_say", -1.0) >= 15.0:
                        g._chain["last_say"] = g._chain["t"]
                        g._csay("CHAIN %4.0fs  farmer.food=%d shelf.food=%d  "
                              "farmer.leaf=%s  shelf=%s  artisan=%s  trader=%d"
                              % (g._chain["t"], g._food, g._shelf,
                                 {k: int(g._farm.stock.get(k, 0)) for k in g._LEAF
                                  if int(g._farm.stock.get(k, 0)) > 0} if g._farm else {},
                                 {k: int(v) for k, v in g._hubx.ledger_goods.items() if v},
                                 {k: int(g._art.stock.get(k, 0)) for k in
                                  (g._LEAF + g._MADE) if int(g._art.stock.get(k, 0)) > 0}
                                 if g._art else {},
                                 g._carry))
                    g._deadline = {1: 300.0, 2: 600.0, 3: 900.0, 4: 1200.0,
                                 5: 1500.0, 6: 2400.0, 7: 2700.0, 8: 3300.0,
                                 9: 3900.0}
                    g._need = {1: ("food", 1), 2: ("leaf", 1), 3: ("made", 1),
                             4: ("carry", 20), 5: ("trip", True)}
                    g._say = {1: "the farmer harvests any food at all",
                            2: "the farmer hands leaf to the artisan",
                            3: "the artisan makes a finished product",
                            4: "the artisan gives 20 finished goods to the trader",
                            5: "the trader leaves on a trip with 20",
                            6: "the trader reaches a town gate",
                            7: "the guard searches him at the gate",
                            8: "he sells to the town",
                            9: "he comes home and the hut's purse grows"}
                    while g._chain["link"] <= 9:
                        _k = g._chain["link"]
                        g._ok = False
                        if _k in g._need:
                            g._key, g._val = g._need[_k]
                            g._ok = (g._st.get(g._key, 0) >= g._val) if g._val is not True else bool(g._st.get(g._key))
                        elif _k == 6:
                            g._ok = g._st.get("stage") in ("home",) and bool(g._st.get("trip"))
                        elif _k == 7:
                            g._ok = g._st.get("ledger", 0) > 0 or g._st.get("stage") == "home"
                        elif _k in (8, 9):
                            g._ok = g._st.get("stage") == "idle" and g._st.get("trip")
                        if g._ok:
                            plog.log("CHAIN OK", _k, g._say[_k])
                            g._csay("CHAIN OK  %d: %s" % (_k, g._say[_k]))
                            g._chain["link"] = _k + 1
                            continue
                        if g._chain["t"] > g._deadline[_k]:
                            g._csay("CHAIN FAILED AT LINK %d: %s" % (_k, g._say[_k]))
                            g._csay("   state: food=%s leaf=%s made=%s carry=%s "
                                  "trip=%s stage=%s ledger=%s"
                                  % (g._st.get("food"), g._st.get("leaf"),
                                     g._st.get("made"), g._st.get("carry"),
                                     g._st.get("trip"), g._st.get("stage"),
                                     g._st.get("ledger")))
                            plog.log("CHAIN FAILED", _k, g._say[_k], g._st)
                            pygame.quit()
                            raise SystemExit(9)
                        break
                    if g._chain["link"] > 9:
                        g._csay("CHAIN COMPLETE: every link fired")
                        plog.log("CHAIN COMPLETE")
                        pygame.quit()
                        raise SystemExit(0)
                except SystemExit:
                    raise
                except Exception as _ce:
                    g._csay("CHAIN MONITOR ERROR:", repr(_ce)[:160])
            if g._observe_spot is not None:
                g.player.god = True
                g.player.hunger = 100.0
                g.player.x, g.player.y = g._observe_spot      # fixed: nothing moves him
            g.skills.gain_movement(math.hypot(g.player.x - g._px0, g.player.y - g._py0))
            g.clamp_world()          # the world ends where the loading screen did
            g.settle_reload()

            g.visible_villages = g.villages.visible(g.cam_x, g.cam_y, g.vw, g.vh,
                                             extra=g.hub_world.hubs)

            # ---- RE-CUT THE WORLD, ONCE A SECOND ---------------------
            # The towns in front of the player must be stepped where he is, so
            # the cut follows him. Remaking it is cheap (it is a walk over the
            # towns and the register) but not free, so it is not per-frame.
            # RE-CUT ONLY WHEN THE VIEW ACTUALLY CHANGED. This was once a
            # second, every second, for the whole life of the game -- and
            # re-cutting walks every town and every soul. Measured on a
            # startup, the first re-cut inside the loop took NINETY SECONDS
            # of a frozen window. Nothing about the partition depends on the
            # clock: it depends on WHICH towns are in front of him, so it is
            # cut when that set changes and at no other time.
            g._lane_ids = tuple(sorted(id(v) for v in g.visible_villages))
            g._lane_timer -= g.dt
            # ---- FREEZE SETTLEMENTS THAT LEFT THE SIMULATED DISTANCE -------
            # A village further than FREEZE_RADIUS is serialized and dropped
            # from the live world; its full state sits in villages._frozen and
            # is overlaid when the player walks back to its cell.
            g._freeze_timer = getattr(g, "_freeze_timer", 5.0) - g.dt
            if g._freeze_timer <= 0.0:
                g._freeze_timer = 5.0
                try:
                    import worldbuild as _wb
                    import math as _m
                    _rad = getattr(g, "FREEZE_RADIUS", 3.0 * g.SPACING)
                    _froze = _wb.freeze_far_villages(g.villages, g.player.x,
                                                      g.player.y, _rad)
                    if _froze:
                        # force a re-cut next frame so the lanes drop the frozen
                        g._lane_seen = None
                        g._lane_timer = 0.0
                except Exception:
                    pass
                # Native settlements appear as the player reaches their cells.
                try:
                    import native as _nat
                    _nat.ensure_near(g, g.player.x, g.player.y,
                                     _nat.NATIVE_RADIUS)
                except Exception:
                    pass
            if g._lane_timer <= 0.0 and g._lane_ids != g._lane_seen:
                g._lane_seen = g._lane_ids
                g._lane_timer = 4.0
                g._all_t = list(g.villages.villages)
                g._LANES.recut(g._all_t, main_towns=g.visible_villages)
                if g._LANES.ok(g._all_t, village_mod.TRAVELLERS,
                             village_mod.PEOPLE):
                    g._LANE_TOWNS = g._LANES.towns_for(0)
                    g._LANE_PEOPLE = g._LANES.people_for(0)
                else:
                    # A LANE LOST A MAN, and this used to answer by stepping
                    # THE WHOLE WORLD instead: every town and every soul, from
                    # scratch, once a second. MEASURED, it is what froze the
                    # game for eighty-five seconds after the first frame and
                    # never stopped freezing.
                    #
                    # The cut is a partition of ownership and it is nearly
                    # right -- a handful of men fall outside it and the old
                    # answer was to throw the whole partition away for their
                    # sake. The repair is to HAND THE MISSING MEN BACK to the
                    # lane rather than to abandon it: same set in, a set
                    # difference out, and nobody is dropped.
                    g._LANE_TOWNS = g._LANES.towns_for(0)
                    g._LANE_PEOPLE = g._LANES.people_for(0)
                    g._seen = set(map(id, g._LANE_PEOPLE))
                    g._missing = [m for m in village_mod.PEOPLE if id(m) not in g._seen]
                    if g._missing:
                        g._LANE_PEOPLE = list(g._LANE_PEOPLE) + g._missing
                    if not g._lane_warned:
                        g._lane_warned = True
                        print("LANES: cut lost %d men -- handed back, not "
                              "re-cutting the world" % len(g._missing))
            g.view_trees = g.trees.visible(g.cam_x, g.cam_y, g.vw, g.vh)
            g.view_ore = g.ore_field.visible(g.cam_x, g.cam_y, g.vw, g.vh)
            for village in g.visible_villages:        # 5 border guards per village
                # A HUB IS NOT A TOWN AND GETS NO GARRISON. `visible()` now
                # hands back the off-lattice hubs too, so this loop was putting
                # five wall guards AND a two-man gate patrol on every hut --
                # more soldiers in a criminal camp than in a market town. A hub
                # has exactly one armed man: the soldier's post at his gate.
                if (not getattr(village, "is_hub", False)
                        and getattr(village, "guards", None) is None
                        and math.hypot(village.x - g.player.x,
                                       village.y - g.player.y) < 6000.0):
                    g.loop = village.fence_rect.inflate(-218, -218)
                    g.guards = []
                    # Guards are posted along the wall, so a capital twice the
                    # size keeps twice as many -- same rule, read off the
                    # village's own scale.
                    # NOBODY WALKS THE PERIMETER. Two men, at the two gates,
                    # standing still -- one searching the way in, one watching
                    # the way out. The ring of five was a patrol nobody asked
                    # for; the gate is the only way through a wall.
                    g.many = 0
                    for gi in range(g.many):
                        g.phase = gi / float(g.many)
                        g.gx0, g.gy0, g.gnx, g.gny = fence.perimeter_point(g.loop, g.phase)
                        g.guard = Soldier(g.gx0, g.gy0,
                                        village.nation, melee=False,
                                        seed=random.randint(0, 2 ** 31),
                                        color=nation_color(village.nation))
                        g.guard.guard_loop = g.loop
                        g.guard.guard_phase = g.phase
                        g.guard.guard_village = village
                        g.guard.hostile = getattr(village, "provoked", False)
                        g.guard.home = (g.guard.x, g.guard.y)
                        g.guards.append(g.guard)
                    village.guards = g.guards
                    g.enemies.extend(g.guards)
                # ... plus a 3-soldier patrol of the whole territory border.
                # HIS YARD IS NOT A GARRISON. No patrol, no roster, no duty:
                # the whole block below is the town's standing watch, and a
                # hub he built has no watch. (This is what crashed the game on
                # the first plot: `patrol_timer` on a PlayerHub.)
                g.squad = getattr(village, "patrol", None)
                if getattr(village, "is_player_hub", False):
                    continue
                if g.squad is None:
                    if math.hypot(village.x - g.player.x,
                                  village.y - g.player.y) < 30000.0:
                        village.patrol = g.make_village_patrol(
                            village, 2 if getattr(village, "is_hub", False) else 4)
                        village.patrol_timer = 30.0
                        g.enemies.extend(village.patrol)
                elif not any(s.alive for s in g.squad):
                    village.patrol_timer -= g.dt
                    if village.patrol_timer <= 0.0:      # squad wiped: respawn
                        village.patrol = g.make_village_patrol(
                            village, 2 if getattr(village, "is_hub", False) else 4)
                        village.patrol_timer = 30.0
                        g.enemies.extend(village.patrol)
                village._assign_duty_bodies()
            g.house_colliders = [house.rect for village in g.visible_villages
                               for house in village.houses]
            g.house_colliders += [house.rect for house in g.built_houses]
            g.house_colliders += [w for village in g.visible_villages
                                for w in village.fence_walls]
            g.house_colliders += g.built_fences
            g.house_colliders += g.camp_walls
            g.house_colliders += [v.board for v in g.visible_villages]
            g.house_colliders += [wp.rect for v in g.visible_villages
                                for wp in v.workplaces]
            g.house_colliders += [wp.rect for wp in g.placed_work]
            g.house_colliders += [c.rect for c in g.view_ore]
            g.colliders = g.house_colliders + [tree.trunk_rect for tree in g.view_trees
                                           if not tree.felled]
            # THE CARTS, EVERY FRAME AND AT THE FRAME'S OWN PACE. A cart is a
            # vehicle: at 240 px/s it moves four pixels a frame, which is
            # smooth; on the 20 Hz world tick it would move twelve at a time --
            # the "jumping" the throttled build was reverted for. What made it
            # expensive was never the clock, it was the empty-shelf scan (see
            # caravans.Caravan), and that is gated by a retry clock now.
            #
            # AND `dt`, NOT `world_dt`. `world_dt` is only ever assigned on the
            # world tick, so every frame was handed the same 0.05 s step: the
            # carts walked at 720 px/s instead of SPEED = 240. See Hubs.update
            # for the hubs themselves, which now keep the world's clock.
            if not g._W_ON:
                try:
                    g.hub_world.drive_carts(g.dt, g.now)
                except Exception:
                    pass
            g.grid_timer -= g.dt
            if g.grid is None or g.grid_timer <= 0.0:
                g.grid_timer = 0.12
                g.grid = StaticGrid(96.0)      # index obstacles; query per NPC/tree
                for village in g.visible_villages:
                    for house in village.houses:
                        g.grid.add(house.rect)
                    for wall in village.fence_walls:
                        g.grid.add(wall)
                    g.grid.add(village.board)
                    for wp in village.workplaces:
                        g.grid.add(wp.rect)
                for wp in g.placed_work:
                    g.grid.add(wp.rect)
                for house in g.built_houses:
                    g.grid.add(house.rect)
                for rect in g.built_fences:
                    g.grid.add(rect)
                # THE CAMP WALL, IN THE GRID THE PLAYER IS PUSHED OUT OF.
                # It was in the collider *list* and not in this grid, and the
                # player's movement is resolved against the grid -- so the wall
                # was drawn, stood in the list, and could be walked straight
                # through like paint on the floor.
                for rect in g.camp_walls:
                    g.grid.add(rect)
                for tree in g.view_trees:
                    if not tree.felled:
                        g.grid.add(tree.trunk_rect)
                for c in g.view_ore:
                    g.grid.add(c.rect)
            g.solids = [(house.rect, (150, 140, 120)) for village in g.visible_villages
                      for house in village.houses]
            g.solids += [(house.rect, (150, 140, 120)) for house in g.built_houses]
            g.solids += [(w, (140, 104, 60)) for village in g.visible_villages
                       for w in village.fence_walls]
            g.solids += [(rect, (140, 104, 60)) for rect in g.built_fences]
            g.solids += [(rect, (140, 104, 60)) for rect in g.camp_walls]
            # Fence walls a bullet may pass over when fired from right beside them.
            g.fence_ids = {id(w) for village in g.visible_villages
                         for w in village.fence_walls}
            g.fence_ids |= {id(r) for r in g.built_fences}
            g.solids += [(tree.trunk_rect, (118, 88, 48)) for tree in g.view_trees
                       if not tree.felled]
            g.solids += [(c.rect, (104, 104, 116)) for c in g.view_ore]
            # AND THE HUBS' WALLS. A hub is not in `villages`, so nothing that
            # walks the village list -- drawing, collision, crops -- knew it
            # was there, and the player walked straight through its fence.
            try:
                for _hub in g.hub_world.hubs:
                    if not view.colliderect(_hub.fence_rect):
                        continue
                    g.solids += [(w, (150, 108, 64)) for w in _hub.fence_walls]
                    g.solids += [(h.rect, (150, 140, 120)) for h in _hub.houses]
                    g.solids += [(wp.rect, (96, 92, 88)) for wp in _hub.workplaces]
            except Exception:
                pass
            g.solids += [(v.board, (120, 86, 52)) for v in g.visible_villages]
            g.solids += [(wp.rect, (96, 92, 88)) for v in g.visible_villages
                       for wp in v.workplaces]
            g.solids += [(wp.rect, (96, 92, 88)) for wp in g.placed_work]
            # PLACED BLOCKS ARE SOLID: they collide like any wall.
            try:
                import block as _block
                g._block_cols = []
                for (btx, bty) in getattr(g, "built_blocks", {}):
                    _br = pygame.Rect(btx * _block.TILE, bty * _block.TILE,
                                      _block.TILE, _block.TILE)
                    if _br.inflate(60, 60).collidepoint(g.player.x, g.player.y):
                        g._block_cols.append(_br)
            except Exception:
                g._block_cols = []
            if not g.player.dead:
                g.player.x, g.player.y = resolve_circle_rects(
                    g.player.x, g.player.y, g.player.radius,
                    list(g.grid.near(g.player.x, g.player.y, g.player.radius + 6.0))
                    + g._block_cols)
            # THE OCEAN IS IMPASSABLE: the shore is the eastern edge of the
            # world. Walk into the sea and he is pushed back to the sand.
            try:
                import world as _world
                _c = _world.coast_x(g.player.y, g.world.seed)
                if g.player.x > _c:
                    g.player.x = _c - g.player.radius
            except Exception:
                pass

            for patrol in g.patrols:
                g.best = None
                g.bd = 3200.0
                for other in g.patrols:
                    if other is patrol or other.nation == patrol.nation:
                        continue
                    g.d = math.hypot(other.x - patrol.x, other.y - patrol.y)
                    if g.d < g.bd:
                        g.bd = g.d
                        g.best = (other.x, other.y)
                patrol.war_target = g.best
                patrol.update(g.dt)
            for rabbit in g.rabbits:
                rabbit.update(g.dt, None if g.player.dead else g.player, g.grid)
            g.enemy_grid.build([e for e in g.enemies if e.alive])
            # THE BEASTS, PICKED OUT ONCE A FRAME. _predator_near() used to walk
            # the whole enemy list -- every wolf AND every soldier -- per man,
            # per tick, to find one wolf inside 420 px. A plain list, not a
            # grid: the grid measured SLOWER than the scan while the list was
            # short, and this is never slower and cannot grow with the wars.
            g.world.wolves = [e for e in g.enemies
                            if e.alive and getattr(e, "kind", "") == "wolf"]
            # The people of a besieged village must be TARGETABLE, not just
            # shootable: soldiers pick who to shoot from this grid, so leaving
            # the siege out of it meant a garrison could be shot at but never
            # chosen -- and a village could therefore never be emptied.
            # WHICH VILLAGES ARE UNDER SIEGE, taken straight from the armies
            # that are besieging them -- not from a variable computed
            # somewhere else a frame earlier. The people of a village being
            # stormed must be TARGETABLE, or an invading column stands in the
            # square unable to see anyone.
            g.sieges = [a.target for a in g.armies
                      if not a.done and a.target is not None]
            g._folk_list = [n for v in g.visible_villages
                          + [x for x in g.sieges if x not in g.visible_villages]
                          for n in v.npcs
                          if n.alive and not n.in_interior]
            if g._TRUTH[0] is not None and g._TRUTH[0] not in g._folk_list:
                g._folk_list.append(g._TRUTH[0])    # shootable, healable, seen
            g.folk_grid.build(g._folk_list)
            # THE WORLD KNOWS YOUR FACE -- AND LEARNS IT ONCE.
            #
            # This pass used to walk every man within 760 px, EVERY FRAME, set
            # `aggro = True` on each of them again, and write a log line for
            # each: 88,283 lines in one session (89,394 in the whole file), 350
            # file writes a second, and a man who could never calm down while
            # the player was in sight. The learning lives in the lane now
            # (`threat_of`): a man who knows the face adds him to his own list
            # of feuds ONCE, and the list is what he fights.
            # THE LIST THE WORLD WALKS, assembled HERE, at the loop, out of
            # the armies themselves. An army that is merely *meant* to be in
            # some shared roster is an army that does not shoot and is not
            # noticed by the village it is standing in -- which is exactly
            # what happened. Built here, from the armies, it cannot be absent.
            g.enemies[:] = [e for e in g.enemies if not getattr(e, "in_army", False)]
            for _a in g.armies:
                if _a.done:
                    continue
                for _s in _a.soldiers:
                    if _s.alive and not getattr(_s, "settled", False):
                        g.enemies.append(_s)
            # ...and the standing army: bodies on the capital's streets
            for _s in war.STANDING:
                if _s.alive:
                    g.enemies.append(_s)
            for enemy in g.enemies:
                if enemy.alive:
                    # A marching column out in the open is walked by war.march
                    # and needs nothing else this frame. Only a column in
                    # contact -- at a wall, or meeting another -- costs the
                    # frame rate. Same war, a fraction of the work.
                    if (getattr(enemy, "in_army", False)
                            and not getattr(enemy, "in_contact", False)):
                        continue
                    if (getattr(enemy, "guard_village", None) is not None
                            and math.hypot(enemy.x - g.player.x,
                                           enemy.y - g.player.y) > 4200.0):
                        continue                # made once; only walks while you're near
                    if (getattr(enemy, "patrol_center", None) is not None
                            and math.hypot(enemy.x - g.player.x,
                                           enemy.y - g.player.y) > 13000.0):
                        continue                # patrols only walk while near
                    # The ground does not move. Rebuilding one soldier's view
                    # of the trees, the village lattice, the occluders and the
                    # colliders every frame cost 106 ms with four hundred men
                    # on the field. It is the same answer for everybody in the
                    # same stretch of ground, so it is worked out once and
                    # handed round.
                    g._ekey = (int(enemy.x // g.ENV_CELL), int(enemy.y // g.ENV_CELL),
                             g._BUILD_VER[0], len(g.built_houses), len(g.built_fences),
                             len(g.built_gates))
                    g._cached = g.ENV_CACHE.get(g._ekey)
                    if g._cached is None:
                        g.enemy_foliage = g.trees.foliage(enemy.x, enemy.y)
                        g.e_trees = g.trees.near(enemy.x, enemy.y, 480.0)
                        g.e_villages = g.villages.visible(enemy.x - 700.0,
                                                      enemy.y - 700.0, 1400, 1400)
                        g.e_occluders = [house.sight_rect for v in g.e_villages
                                       for house in v.houses]
                        g.e_occluders += [tree.trunk_rect for tree in g.e_trees
                                        if not tree.felled]
                        g.e_occluders += [house.sight_rect for house in g.built_houses]
                        # COLLISION IS LOCAL. A man is 14 px across: the only
                        # walls that can touch him are the ones beside him.
                        # Handing every soldier the whole village -- ninety
                        # houses, every wall run, fifty trunks -- made steering
                        # crawl and stall, and cost 400 x 100 rect tests twice
                        # a frame. He gets the ones within a few paces.
                        g.cbox = pygame.Rect(int(enemy.x) - 210, int(enemy.y) - 210,
                                           420, 420)
                        g.e_colliders = [house.rect for v in g.e_villages
                                       for house in v.houses
                                       if house.rect.colliderect(g.cbox)]
                        g.e_colliders += [house.rect for house in g.built_houses
                                        if house.rect.colliderect(g.cbox)]
                        g.e_colliders += [w for v in g.e_villages
                                        for w in v.fence_walls
                                        if w.colliderect(g.cbox)]
                        g.e_colliders += [r for r in g.built_fences
                                        if r.colliderect(g.cbox)]
                        # trunks close enough to be walked into, not the grove
                        g.e_colliders += [tree.trunk_rect
                                        for tree in g.trees.near(enemy.x, enemy.y,
                                                               190.0)
                                        if not tree.felled]
                        g._cached = (g.enemy_foliage, g.e_trees, g.e_villages,
                                   g.e_occluders, g.e_colliders)
                        if len(g.ENV_CACHE) > 4000:
                            g.ENV_CACHE.clear()
                        g.ENV_CACHE[g._ekey] = g._cached
                    g.enemy_foliage, g.e_trees, g.e_villages, g.e_occluders, g.e_colliders = g._cached
                    if enemy.kind == "wolf":       # gates keep wolves out, not people
                        g.e_colliders = g.e_colliders + g.built_gates
                    enemy._rects = g.e_colliders
                    enemy._fences = g.e_villages
                    enemy.friendly = (g.player.nation is not None
                                      and getattr(enemy, "nation", None)
                                      == g.player.nation)
                    # Only the men near enough to be in the way of a shot.
                    # Handing every soldier the whole army list meant each
                    # shot scanned four hundred men -- 160,000 segment tests
                    # a frame, and the frame rate on the floor.
                    enemy._soldiers = g.enemy_grid.near(enemy.x, enemy.y, 560.0)
                    enemy._player = g.player
                    enemy._blood = g.blood
                    g.mt = getattr(enemy, "march_target", None)
                    if g.mt is not None and not getattr(enemy, "in_army", False):
                        g.hv = getattr(enemy, "home_village", None)
                        g.goal = g.mt
                        # AN ARMY GOES IN BY THE GATE. Marching at the middle
                        # of a walled village just walks men into the palisade:
                        # they pile up outside, the people are 2600 px away at
                        # the square, and neither side can see the other -- so
                        # the siege never starts at all. The column heads for
                        # the nearest gate, gets inside, and then goes for the
                        # square.
                        g.tv = getattr(enemy, "march_village", None)
                        if g.tv is not None and not g.tv.fence_rect.collidepoint(
                                enemy.x, enemy.y):
                            g.gside, g.gxw, g.gyw = fence.nearest_gate(g.tv, enemy.x, enemy.y)
                            g.gox, g.goy = fence.OUTWARD[g.gside]
                            g.goal = (g.gxw - g.gox * 120.0, g.gyw - g.goy * 120.0)
                        if g.hv is not None and g.hv.fence_rect.collidepoint(enemy.x,
                                                                        enemy.y):
                            g.gwx, g.gwy = fence.gate_world(g.hv)
                            g.gox, g.goy = fence.gate_outward(g.hv)
                            g.goal = (g.gwx + g.gox * 110.0, g.gwy + g.goy * 110.0)
                        g.ux, g.uy = steering.steer(enemy, g.goal[0], g.goal[1],
                                                g.e_colliders, g.e_villages)
                        enemy.x += g.ux * 240.0 * g.dt
                        enemy.y += g.uy * 240.0 * g.dt
                        enemy.facing = (g.ux, g.uy)
                        if math.hypot(g.mt[0] - enemy.x, g.mt[1] - enemy.y) < 130.0:
                            enemy.march_target = None
                            enemy.march_village = None
                    # Re-picking a target is the most expensive thing a
                    # soldier does, and a man does not need to re-decide who
                    # he is shooting twenty times a second. Four times is
                    # plenty; a corpse or an empty field forces an immediate
                    # rethink.
                    enemy._retarget = getattr(enemy, "_retarget", 0.0) - g.dt
                    g.tgt = getattr(enemy, "_target", None)
                    if (enemy._retarget <= 0.0 or g.tgt is None
                            or not getattr(g.tgt, "alive", True)
                            or getattr(g.tgt, "dead", False)):
                        g.tgt = g.choose_target(enemy, g.e_villages)
                        enemy._target = g.tgt
                        enemy._retarget = 0.2
                    enemy.update(g.dt, g.tgt, g.combat, g.e_occluders,
                                 1.0 - 0.25 * g.enemy_foliage,
                                 1.0 - 0.2 * g.enemy_foliage,
                                 colliders=g.e_colliders)
                    enemy.x, enemy.y = resolve_circle_rects(
                        enemy.x, enemy.y, enemy.radius, g.e_colliders)
                    # A MILITIAMAN WHO SEES A MAN CONSUME GOES AND ASKS.
                    if (getattr(enemy, "is_militia", False)
                            or getattr(enemy, "militia", False)):
                        try:
                            import question as _q
                            _tv = getattr(enemy, "guard_village", None)
                            _ppl = getattr(_tv, "npcs", ()) if _tv is not None else ()
                            if _ppl:
                                _q.tick(enemy, _ppl, g.now, g.dt, g.e_occluders,
                                        g.combat, g.player)
                        except Exception:
                            pass

            for village in g.visible_villages:
                for npc in village.npcs:
                    npc._soldiers = g.enemies
                    npc._player = g.player
            # The world tick -- villagers, crops and village state -- runs a
            # few times a second, not every frame. Only combat needs the full
            # frame rate. The accumulated dt keeps time honest.
            g.world_accum += g.dt
            g.world_tick = g.world_accum >= WORLD_STEP
            if g.world_tick:
                g.world_dt = g.world_accum
                g.world_accum = 0.0
                # THE HUBS, ON THE WORLD TICK -- the same clock, and the same
                # step, as every man in every town (see the _LANE_PEOPLE loop
                # below). `hub_world.update` used to be called EVERY FRAME
                # with `world_dt`, a value only this branch ever assigns: so
                # twenty-five hubs, three men each and a whole ledger ran on
                # every rendered frame with a 0.05 s step -- 2 to 3 times their
                # own speed, and the largest single block left in the frame
                # (12.3 ms/f profiled). A settlement's day does not depend on
                # being watched; it depends on the world's clock.
                if g._W_ON:
                    # THE TWO LANES TAKE THE TICK: the hubs to process 1, the
                    # settlements to process 2 (workers.tick hands it over).
                    g._WORK.tick(g.now, g.world_dt, g.day_phase(), g.night, g.player,
                               g.enemies)
                else:
                    try:
                        g.hub_world.update(g.world_dt, g.now, g.day_phase(), g.combat,
                                         g.nearest_hostile)
                    except Exception:
                        pass
                # The crown's wars. A capital whose purse is deep enough calls
                # up its nation's idle men once a day; the column then marches,
                # fights, and either takes the village or comes home.
                g._wd = int(g.now / DAY_LENGTH)
                for _army in war.declare(g.villages, g._wd, g.now):
                    g.armies.append(_army)
                    g.toast("%s calls up %d men and marches on %s"
                          % (_army.capital.name, _army.start,
                             _army.target.name))
                # RECONCILE. Every living soldier of every army must be in the
                # list the world walks, every tick, no matter which path put him
                # there. Trusting a single extend() at muster time meant the
                # whole war could sit in a field and never be simulated at all.
                g._arr, g._die = ((0, 0) if g._W_ON else
                              village_mod.refugees_on_the_road(g.now, g.enemies))

                # THE TEST OF STRENGTHS. The King and the mayors fight for the
                # crown in the capital, unarmed, in front of the town. One at a
                # time, on the day, and the winner wears it.
                g.hear_news()                     # the news arrives where you are
                g.tick_news(g.dt)

                # TAXES -- AND ONLY THE PLAYER PAYS THEM THIS WAY. The
                # villagers have their own books (economy.tax_day) and are
                # untouched by any of this. A PLAYER who has taken a post owes
                # the village a hundred coin every three days, unless he is
                # under arms or the mayor. Fail and he is not a trader, or a
                # logger, or a smith: he is nobody -- and if he is standing in
                # the village when they work it out, they will shoot.
                # NO COIN LEVY AND NO BANISHMENT FOR THE PLAYER. He pays the
                # same tax as every villager -- a fifth of what he produces,
                # in kind, taken out of his pack as he works (see pay_share).
                # A flat 100 coin every three days was a WEALTH tax charged to
                # a man who had just been hired: at WAGE = 10 a day a board
                # post earned 30 and owed 100, so taking a job was a net loss
                # and then an exile for being poor. There is nothing to check
                # any more, because the share is taken before he can forget it.

                # DESERTION. A soldier who wanders off from his column -- or
                # from the village he was given -- has left the service, and
                # the nation says so. A TRADER is exempt from the distance
                # rule: a trader's whole trade is being somewhere else, and he
                # settles up with the ledger instead.
                g._desert = False
                if _pl_serving := (g.player.nation is not None):
                    g._home = None
                    if g.player.settled_at is not None:
                        g._home = (g.player.settled_at.x, g.player.settled_at.y,
                                 g.player.settled_at.radius + g.DESERT_PX)
                    elif getattr(g.player, "army", None) is not None:
                        g._live = [s for s in g.player.army.soldiers
                                 if s.alive and not getattr(s, "settled", False)]
                        if g.player.army.done or not g._live:
                            g.player.army = None
                        else:
                            g._home = (sum(s.x for s in g._live) / len(g._live),
                                     sum(s.y for s in g._live) / len(g._live),
                                     g.DESERT_PX)
                    if g._home is not None and g._home[2] > 0.0:
                        g._far = math.hypot(g.player.x - g._home[0],
                                          g.player.y - g._home[1]) > g._home[2]
                        g.player._away = g.player._away + g.world_dt if g._far else 0.0
                        if (g.player._away > g.DESERT_SECONDS
                                and (g.player.job or "") != "trader"):
                            g._desert = True
                if g._desert:
                    g.toast("You have deserted.   %s wants nothing to do with you"
                          % nation_name(g.player.nation))
                    g.banish(g.player.nation)
                    g.player.nation = None
                    g.player.army = None
                    g.player.wage = 0
                    g.player.settled_at = None
                    g.player.job = None
                    g.player._away = 0.0
                # A CIVILIAN'S WAGE. A man who took a post off a village
                # notice board is paid by the village that hired him -- every
                # day, out of its OWN ledger, with no crown war chest standing
                # between them. A soldier is still paid by his capital below;
                # this is for the farmer, the logger, the smith and the rest.
                g._employer = getattr(g.player, "settled_at", None)
                g._trade = getattr(g.player, "job", None)
                if (g._employer is not None and g._trade in _BOARD_TRADES
                        and getattr(g.player, "army", None) is None
                        and getattr(g.player, "_pay_day", -1) != g._wd):
                    g.player._pay_day = g._wd
                    g._wage = int(getattr(g.player, "wage", 0))
                    if g._wage > 0 and g._employer.ledger_coins >= g._wage:
                        g._employer.ledger_coins -= g._wage
                        g.inventory.add("coin", g._wage)
                        g.toast("Pay   +%d coin   %s" % (g._wage, g._employer.name))
                # A SOLDIER'S PAY, for a soldier who is a player.
                if (g.player.nation is not None and getattr(g.player, "wage", 0) > 0
                        and getattr(g.player, "_pay_day", -1) != g._wd):
                    g.player._pay_day = g._wd
                    for _v in g.villages.villages:
                        if not (_v.is_capital and _v.nation == g.player.nation):
                            continue
                        if _v.ledger_coins - economy.CROWN_BUFFER >= g.player.wage:
                            _v.ledger_coins -= g.player.wage
                            g.inventory.add("coin", g.player.wage)
                            g.toast("Pay   +%d coin" % g.player.wage)
                        break
                # ...and whatever share of the plunder is waiting for him.
                g._pend = getattr(g.player, "loot_pending", 0)
                if g._pend > 0:
                    g.player.loot_pending = 0
                    g.inventory.add("coin", g._pend)
                    g.toast("Your share of the plunder   +%d coin" % g._pend)
                for _it in list(getattr(g.player, "loot_items", ())):
                    g.inventory.add(_it, 1)
                    g.toast("Looted   +1 %s" % _it)
                g.player.loot_items = []
                # THE TOOLS OF THE TRADE, handed over when a post is taken.
                for _it, _qty in list(getattr(g.player, "kit_pending", ())):
                    g.inventory.add(_it, _qty)
                if getattr(g.player, "kit_pending", None):
                    g.toast("Tools for the %s   -   %s"
                          % (g.player.job or "post",
                             ", ".join("%d %s" % (q, i)
                                       for i, q in g.player.kit_pending)))
                    g.player.kit_pending = []
                for _army, _res, _info in war.update(g.armies, g.world_dt, g.now):
                    if _res == "taken":
                        g.toast("%s has fallen to %s   +%d coins of spoils"
                              % (_army.last_name, _army.capital.name, _info))
                    elif _res == "march":
                        g.toast("%s's army marches on %s"
                              % (_army.capital.name, _info.name))
                    elif _res == "reinforced":
                        g.enemies.extend(_info)
                        g.toast("%d men march out to join %s's army"
                              % (len(_info), _army.capital.name))
                    elif _res == "broken":
                        g.toast("%s's army is broken and straggles home"
                              % _army.capital.name)
                # a soldier who has settled in a taken village, or gone home,
                # is no longer a body on the map
                for _army in g.armies:
                    for _s in list(_army.soldiers):
                        if _s in g.enemies and (getattr(_s, "settled", False)
                                              or getattr(_s, "disbanded", False)):
                            g.enemies.remove(_s)
                g.armies = [a for a in g.armies if not a.done]
            # Villages with an army at the gate are live ground: their guards
            # shoot, their people run for the gates, the fight happens in the
            # world where the player can ride over and watch it. Without this
            # a siege could never resolve, because a village that nobody is
            # looking at does not tick.
            # EVERY TOWN, EVERY TICK -- NOT ONLY THE ONES ON SCREEN.
            #
            # This read `visible_villages + sieges`, and the comment above it
            # admitted the consequence out loud: "a village that nobody is
            # looking at does not tick." So wages, tax, the granary, the
            # the daily census and the births ran only in the three
            # or four towns inside the camera -- while EVERY MAN in the world
            # ticked (see the PEOPLE loop below). The people were alive and
            # their towns were frozen: prices never moved, nobody was paid,
            # nothing was harvested into a store that was not on screen.
            #
            # The world is laid out before the first step (load_world), so this
            # is a lookup and not a build, and a town's update is day-guarded
            # almost everywhere it matters.
            # ON TRIAL: every town steps now, to prove the loan loop is dead.
            # one game day -- the same man borrowing 32 coin over and over
            # inside hundredths of a day, the ledger drained, and the world
            # went 1043 -> 128. `place_orders` and `tool_loan` were only ever
            # run for towns that ticked; making every town tick runs them for
            # every man in the world, and the "one loan at a time" guard does
            # not hold. THE GOAL IS STILL EVERY TOWN, EVERY TICK -- but the
            # loan path has to be fixed first or the world starves of it.
            g._pt0 = time.perf_counter()
            for village in g._LANE_TOWNS:
                if not g.world_tick or g._W_ON:
                    break
                if village in g.sieges:
                    g.world.enemies = g.enemies
                # THE TOWN DECIDES FOR ITSELF WHETHER A WAR IS AT ITS GATE.
                # It no longer picks a threat for its people -- a man finds
                # what he can see for himself (see nearest_hostile below).
                g.hostile_near = False
                for e in g.enemies:
                    if (e.alive and e.kind == "soldier"
                            and e.nation != village.nation):
                        if math.hypot(e.x - village.x, e.y - village.y) < village.radius:
                            g.hostile_near = True
                            break
                if (not g.player.dead and g.player.nation is not None
                        and g.player.nation != village.nation
                        and math.hypot(g.player.x - village.x,
                                       g.player.y - village.y) < village.radius):
                    g.hostile_near = True
                # AN ARMY AT THE GATE IS A PROVOCATION. This was computed and
                # then thrown away -- there was no provoke() call at all -- so
                # a village being stormed never turned hostile: its guards
                # never raised a weapon and its people never fought back. It is
                # why an invading column could stand in the square indefinitely
                # with four defenders 280 px away doing nothing.
                if g.hostile_near and not village.provoked:
                    village.provoke()
                # THE ARMY AT THE GATE IS TOLD WITH EVERYBODY ELSE. A column
                # standing in a town hears what the townsfolk hear, and a
                # murderer it has been told about becomes its business.
                if village.killers:
                    for _e in g.enemies:
                        if _e.alive and getattr(_e, "kind", "") == "soldier":
                            _e.forget(g.now)
                        if (_e.alive and getattr(_e, "kind", "") == "soldier"
                                and math.hypot(_e.x - village.x,
                                               _e.y - village.y) < village.radius):
                            if _e.learn(village.killers, g.now):
                                _e.hostile = True
                                _e.aware = True
                                _e.aware_timer = 60.0
                # ALL THE SOLDIERS ARE DEAD: the town empties. This is the
                # mouth of the whole system -- the people who watched you do it
                # run to the next town, and tell them on the way in.
                if (village.provoked and not getattr(village, "_exodus", False)
                        and not any(b.alive for b in village.defenders())):
                    village._exodus = True
                    g._dests = war.friendly_neighbours(g.villages, village)
                    if g._dests:
                        war.rout(village, g._dests, g.now)
                # THE BUBBLE, NOT THE VIEW. `visible()` is a DRAWING cull --
                # a fence is big, so it returns every town whose wall is
                # anywhere near the frame. Stepping each of those costs a dozen
                # economy passes, and several towns at once is what made the
                # frame die at a gate. A town's books run when the man is near
                # the town.
                if (abs(village.x - g.player.x) < village.radius + 3000.0
                        and abs(village.y - g.player.y) < village.radius + 3000.0):
                    # THE SEARCH, EVERY FRAME: one guard, the men near him,
                    # and nothing else in the world.
                    try:
                        import gate as gate_mod
                        g._r2 = gate_mod.tick_town(g.world_dt, village)
                        if g._r2 is not None and g._r2[0] == "caught":
                            village.provoke()
                        elif g._r2 is not None:
                            pass
                    except Exception:
                        pass
                    # THE TOWN'S BOOKS, TEN TIMES A SECOND. They are all
                    # day-guarded anyway; asking sixty times a second whether
                    # the day has changed was most of the town phase's cost.
                    g._bk = g._town_acc.get(id(village), 0.0) + g.world_dt
                    if g._bk >= 0.1:
                        g._town_acc[id(village)] = 0.0
                        village.update(g._bk, g.world, g.now, g.day_phase())
                    else:
                        g._town_acc[id(village)] = g._bk
                g.key = (village.gx, village.gy)
                if g.key not in g.seeded_villages:       # plant their back gardens
                    g.seeded_villages.add(g.key)
                    g._vt = float(biomes.temperature(village.x, village.y, g.world.seed))
                    g._vh = float(biomes.humidity(village.x, village.y, g.world.seed))
                    g.food, g.leaf = biomes.crop_kinds(g._vt, g._vh)
                    for house in village.houses:
                        for tx, ty in house.garden:
                            # FOOD AND NOTHING ELSE. A backyard used to be an
                            # even mix of the local crops -- half of every
                            # garden in the world was tobacco, and every
                            # household was quietly a supplier. Inside a
                            # settlement the state permits what feeds people.
                            # Leaf is grown where the state is not.
                            kind = g.food
                            # A PLOT IS DRAWN BY THE CROP RENDERER, NOT BY THE
                            # GROUND CHUNK. Invalidating the chunk here threw it
                            # away and re-composed the layer for every planted
                            # tile -- three hundred and ninety of them on the
                            # frame the town arrived. The ground under a field
                            # does not change when something is planted in it.
                            g.world.set_plot(tx, ty, kind, -1000.0)
                            # NOT IMMEDIATE. `invalidate_tile` THROWS THE CHUNK
                            # AWAY and generates a fresh 256x256 one -- noise,
                            # temperature, humidity, numpy clip -- and a town
                            # seeds a garden tile for every house and every
                            # tile of every field: about three hundred and
                            # ninety chunk rebuilds in ONE frame. Measured: 46
                            # to 49 seconds, on the frame a town first came into
                            # the simulation. The worker thread does these.

                            g.village_plots.add((tx, ty))
                    # The communal 5x5 crop plots on the inner border ring.
                    for ctx, cty, kind in getattr(village, "farm_plots", ()):
                        # dual culture: every cell carries its own crop kind
                        for tx, ty, tkind in village.farm_tiles[(ctx, cty)]:
                            g.world.set_plot(tx, ty, tkind, g.now - 6.0)

                            g.village_plots.add((tx, ty))

            g._pt1 = time.perf_counter()
            g._PH["v"] += g._pt1 - g._pt0
            g._pt2 = g._pt1                         # in case world_tick is off
            # A village with a trader on the road to it keeps ticking even when
            # it is far away -- otherwise it has nothing to sell him.
            if g.world_tick:
                g.visible_keys = {(v.gx, v.gy) for v in g.visible_villages}
                # Rebuild the list of villages that need ticking: only the ones
                # a trader is actually walking to. This was add-only, so the set
                # grew without end and every world tick simulated more and more
                # distant villages -- the lag crept in as the caravans ran.
                g.live = set()
                g.pool = list(g.visible_villages)
                # NO trade_active SET. It existed only to decide which extra
                # towns needed stepping so a trader's target kept walking
                # off-screen. Every town is stepped now, and every man walks
                # himself, so there is nothing to guess at.
            # Characters are solid: villagers spread apart, and the player
            # cannot walk through anyone.
            g.npcs = [npc for village in g.visible_villages
                    for npc in village.npcs
                    if npc.alive and not npc.asleep and not npc.in_interior]
            g.sim_view = pygame.Rect(g.cam_x - 220, g.cam_y - 220, g.vw + 440, g.vh + 440)
            g.active = []
            for npc in g.npcs:
                g.on_screen = g.sim_view.collidepoint(npc.x, npc.y)
                npc._rects = g.grid if g.on_screen else ()
                npc._fences = g.visible_villages if g.on_screen else ()
                npc.friendly = (g.player.nation is not None
                                and npc.nation == g.player.nation)
                if g.on_screen:
                    g.active.append(npc)
            if g._W_ON:
                # A LANE OWNS THE MEN'S POSITIONS. Resolving their collisions
                # here as well would be two writers to one fact.
                g.active = []
            else:
                resolve_circle_pairs(g.active, NPC_SPACING)
                for npc in g.active:
                    npc.x, npc.y = resolve_circle_rects(
                        npc.x, npc.y, npc.radius,
                        g.grid.near(npc.x, npc.y, npc.radius + 6.0))
            for enemy in g.enemies:
                if enemy.alive:
                    resolve_circle_out_of(enemy, g.active)
            if not g.player.dead:
                resolve_circle_out_of(g.player, g.active)
                for enemy in g.enemies:
                    if enemy.alive:
                        resolve_circle_out_of(g.player, [enemy])
                g.player.x, g.player.y = resolve_circle_rects(
                    g.player.x, g.player.y, g.player.radius,
                    g.grid.near(g.player.x, g.player.y, g.player.radius + 6.0))

            g.combat.update(g.dt)

            # -- hit resolution ---------------------------------------------
            g.combatants = [] if g.player.dead else [(g.player, "player")]
            for enemy in g.enemies:
                if enemy.alive:
                    g.combatants.append((enemy, enemy.team))
            for rabbit in g.rabbits:
                if rabbit.alive:
                    g.combatants.append((rabbit, rabbit.team))
            for village in g.visible_villages + [v for v in g.sieges
                                               if v not in g.visible_villages]:
                for npc in village.npcs:
                    if npc.alive and not npc.asleep and not npc.in_interior:
                        g.combatants.append((npc, ("nation", npc.nation)))
            g.body_grid = TeamGrid(300.0)
            g.body_grid.build([o for o, _t in g.combatants])
            g.dict_team = {id(o): t for o, t in g.combatants}
            for bullet in g.combat.bullets:
                if bullet.remove:
                    continue
                # A shot travels a few pixels in a frame; only bodies within
                # reach of that little segment can possibly be hit. Sweeping
                # every bullet against every man on the field was 67 ms.
                g._mx = (bullet.prev_x + bullet.x) * 0.5
                g._my = (bullet.prev_y + bullet.y) * 0.5
                g._reach = (math.hypot(bullet.x - bullet.prev_x,
                                     bullet.y - bullet.prev_y) * 0.5 + 48.0)
                for obj in g.body_grid.near(g._mx, g._my, g._reach):
                    g.team = g.dict_team.get(id(obj))
                    if g.team is None:
                        continue
                    if g.team == bullet.team:
                        continue
                    if not segment_circle_hit(bullet.prev_x, bullet.prev_y,
                                              bullet.x, bullet.y,
                                              obj.x, obj.y, obj.radius):
                        continue
                    # A CARAVAN IS NOT A TARGET, and a stray round does not
                    # change that. The player's own shots are his business.
                    if bullet.shooter is not g.player and is_trader(obj):
                        continue
                    if obj is g.player:
                        g._sh = bullet.shooter
                        if g._sh is not None and g._sh is not g.player:
                            plog.log("SHOT", getattr(g._sh, "name", "?"),
                                     getattr(g._sh, "kind", getattr(g._sh, "job", "?")),
                                     "nation", getattr(g._sh, "nation", None),
                                     "dmg", bullet.damage,
                                     "hp_before", int(g.player.health),
                                     "dart", getattr(bullet, "dart", False),
                                     "wanted", getattr(g.player, "wanted", False),
                                     "aggro", getattr(g._sh, "aggro", None),
                                     "dist", int(math.hypot(g._sh.x - g.player.x,
                                                            g._sh.y - g.player.y)))
                        if getattr(bullet, "dart", False):
                            # A DART DRAINS A SEPARATE, HIDDEN BAR. His real
                            # health is never touched by the militia. When the
                            # bar empties, he goes down -- asleep, alive.
                            g.player.tranq_health = getattr(g.player, "tranq_health",
                                                          g.player.TRANQ_HEALTH) - bullet.damage
                            if g.player.tranq_health <= 0:
                                g.player.tranq_health = g.player.TRANQ_HEALTH
                                g.player.tranq()
                        else:
                            g.player.take_damage(bullet.damage)
                        g.blood.spawn(g.player.x, g.player.y, 7, 14.0)
                        bullet.remove = True
                        break
                    if (bullet.shooter is g.player
                            and (getattr(obj, "is_militia", False)
                                 or getattr(obj, "militia", False))):
                        try:
                            import detain as _db
                            _db.militia_attacked(g.player, obj, list(g.enemies),
                                                 list(village_mod.PEOPLE))
                        except Exception:
                            pass
                    g._dart = (getattr(bullet, "dart", False)
                             and getattr(obj, "kind", "") not in ("wolf", "rabbit"))
                    if (not getattr(bullet, "dart", False)
                            and getattr(obj, "kind", "") == "villager"):
                        _sh3 = bullet.shooter
                        plog.log("CIVILIAN-BULLET", getattr(_sh3, "name", "?"),
                                 "kind", getattr(_sh3, "kind", "?"),
                                 "militia", getattr(_sh3, "is_militia", False),
                                 "hit", getattr(obj, "name", "?"))
                    g.died = obj.take_damage(bullet.damage, tranq=g._dart)
                    if getattr(obj, "kind", "") == "villager":
                        g._WORK.damage(obj, bullet.damage)
                    try:
                        g._sh2 = bullet.shooter
                        if g._sh2 is not None and g._sh2 is not obj:
                            import economy as _ec
                            _ec.wronged(obj, g._sh2, 20.0, g.now)
                    except Exception:
                        pass
                    if g.died:
                        g._loot(bullet.shooter, obj)
                    g.blood.spawn(obj.x, obj.y,
                                20 if g.died else 7, 24.0 if g.died else 14.0)
                    if (bullet.team == "player" and g.player.nation is not None
                            and getattr(obj, "nation", None) == g.player.nation):
                        g.banish(g.player.nation)
                    if obj.kind == "rabbit":
                        if g.died:
                            g.amount = random.randint(1, 2)
                            g.inventory.add("raw_meat", g.amount)
                            g.toast(f"Shot a rabbit   +{g.amount} raw meat")
                    elif obj.kind == "bison":
                        if g.died:
                            g.inventory.add("raw_meat", random.randint(5, 10))
                            g.inventory.add("hide", random.randint(30, 50))
                            g.toast("Shot a bison   +meat +hides")
                    elif obj.kind == "villager":
                        if (obj.village is not None
                                and not village_mod.self_defence(obj)):
                            if g.died and bullet.shooter is g.player:
                                obj.village.learn_killers(
                                    (village_mod.PLAYER_ID,), g.now)
                                g._see_murder(obj)
                            obj.village.provoke()
                        if g.died:
                            g.kills += 1
                    bullet.remove = True
                    break

                if bullet.remove:
                    continue
                # Bullets stop on solid world geometry: tree trunks and walls.
                g.bx0 = min(bullet.prev_x, bullet.x) - 1.0
                g.bx1 = max(bullet.prev_x, bullet.x) + 1.0
                g.by0 = min(bullet.prev_y, bullet.y) - 1.0
                g.by1 = max(bullet.prev_y, bullet.y) + 1.0
                for rect, colour in g.solids:
                    if (rect.right < g.bx0 or rect.left > g.bx1
                            or rect.bottom < g.by0 or rect.top > g.by1):
                        continue
                    if segment_rect_hit(bullet.prev_x, bullet.prev_y,
                                        bullet.x, bullet.y, rect):
                        if id(rect) in g.fence_ids:
                            # Shooter was standing at the fence: the shot clears it.
                            g.fx = max(rect.left - bullet.origin_x, 0.0,
                                     bullet.origin_x - rect.right)
                            g.fy = max(rect.top - bullet.origin_y, 0.0,
                                     bullet.origin_y - rect.bottom)
                            if math.hypot(g.fx, g.fy) <= 150.0:
                                continue
                        g.combat.spawn_impact(bullet.x, bullet.y, colour)
                        bullet.remove = True
                        break

            # -- the dead do not come back; the world stays populated -------
            for enemy in g.enemies[:]:
                if not enemy.alive:
                    g.blood.spawn(enemy.x, enemy.y, 22, 26.0)
                    g.enemies.remove(enemy)
                    g.kills += 1
            for rabbit in g.rabbits[:]:
                if not rabbit.alive:
                    g.rabbits.remove(rabbit)
            for village in g.visible_villages:
                if any(not npc.alive for npc in village.npcs):
                    village.last_death = g.now          # births wait for peace
                    village.npcs = [npc for npc in village.npcs if npc.alive]

            g.patrols[:] = [p for p in g.patrols if any(m.alive for m in p.members)]
            g.spawn_timer -= g.dt
            if g.spawn_timer <= 0.0:
                g.spawn_timer = 5.0
                g.live_soldiers = sum(1 for e in g.enemies
                                    if e.kind == "soldier" and e.alive)
                g.live_wolves = sum(1 for e in g.enemies
                                  if e.kind == "wolf" and e.alive)
                if g.live_wolves < 4:
                    g.spawn_wolf()
                if sum(1 for r in g.rabbits if r.alive) < 6:
                    g.spawn_rabbit()
                if sum(1 for e in g.enemies
                       if getattr(e, "kind", "") == "bison" and e.alive) < 6:
                    g.spawn_bison()
            # A NATION FILLS ITS OWN HOLES. Every few seconds each nation looks
            # down its list of towns, and sends men with no trade to the ones
            # short of hands. A village that has been emptied therefore fills
            # back up -- slowly, with strangers, while the player is elsewhere.
            # ---------------- THE PEOPLE, ONCE EACH ----------------------
            # Not the visible ones, not the off-screen ones, not the ones some
            # town thinks a trader might be walking toward -- the people. One
            # flat register, walked once per tick, each man stepping himself.
            # The town is what he calls when he wants the granary or the bank.
            if g.world_tick:
                g._dead_here = False
                # A SNAPSHOT, because a birth appends to that very list. Walking
                # it live meant a child born mid-walk extended the walk, and a
                # village pair bearing children could keep it going for ever --
                # which is the hang. A child born now takes his first step next
                # tick, like everybody else who was not here at the start of it.
                # DAY_PHASE IS ONE ANSWER FOR EVERYBODY. It was evaluated
                # inside this loop, once per man, and day_phase() itself calls
                # night_factor() -- so the phase of the day and the height of
                # the sun were recomputed 590 times a frame, for a value that
                # cannot differ between one man and the next. One call, one
                # tick, handed to every man. Measured 1.9 ms a frame.
                g._pt2 = time.perf_counter()
                g._PH["m"] += g._pt2 - g._pt1
                g._phase = g.day_phase()
                # The frame walks the lane people when the workers are off, and
                # ALWAYS walks the native camp people -- they belong to no town
                # and no worker lane, so they would otherwise stand still.
                _frame = list(g._LANE_PEOPLE) if not g._W_ON else []
                _seen = set(map(id, _frame))
                for _n in getattr(g, "_native_people", ()):
                    if id(_n) not in _seen:
                        _frame.append(_n)
                        _seen.add(id(_n))
                for _n in _frame:
                    if not _n.alive:
                        g._dead_here = True
                        continue
                    try:
                        if not _n.tick(g.world_dt, g.world, g.now, g._phase,
                                       g.combat, g.night, g.colliders, g.nearest_hostile):
                            g._dead_here = True
                    except Exception:
                        # ONE MAN'S BUG IS NOT A DEATH SENTENCE. This set
                        # alive = False, which silently EXECUTED a man for a
                        # programming error -- it killed 73 miners over a
                        # missing attribute, and then more than half the world.
                        # He is skipped for this tick instead, and each distinct
                        # error is printed once so it can actually be found.
                        import traceback as _tb
                        _e = _tb.format_exc()
                        if _e not in _NPC_ERRORS:
                            _NPC_ERRORS.add(_e)
                            sys.stderr.write("\n--- NPC TICK ERROR (man skipped, not killed) ---\n" + _e)
                            sys.stderr.flush()
                if g._dead_here:
                    village_mod.PEOPLE[:] = [n for n in village_mod.PEOPLE
                                             if n.alive]

            g._pt3 = time.perf_counter()
            g._PH["n"] += g._pt3 - g._pt2
            if time.time() - g._PH["t"] >= 30.0:
                g._fr = max(1, g._PH["f"])
                g._tot = max(1e-9, g._PH["v"] + g._PH["m"] + g._PH["n"])
                sys.stderr.write(
                    "PHASE  towns %6.2f ms/f (%4.1f%%)   men %6.2f ms/f (%4.1f%%)"
                    "   between %6.2f ms/f   [%.0f fps]\n"
                    % (g._PH["v"] / g._fr * 1000.0, 100.0 * g._PH["v"] / g._tot,
                       g._PH["n"] / g._fr * 1000.0, 100.0 * g._PH["n"] / g._tot,
                       g._PH["m"] / g._fr * 1000.0,
                       g._fr / max(1e-9, time.time() - g._PH["t"])))
                sys.stderr.flush()
                g._PH.update(v=0.0, m=0.0, n=0.0, f=0, t=time.time())

            # ---------------- THE HOUSES, ONCE A SECOND ------------------
            # A household's larder is the household's. Same once-a-second it
            # was always done at, driven now from the register of houses rather
            # than from inside whichever town happens to contain them.
            g.house_timer -= g.dt
            if g.house_timer <= 0.0:
                g.house_timer = 1.0
                for _h in list(village_mod.HOUSES):
                    _h.tick(1.0)

            # AGENTS TELL EACH OTHER. Twice a second is enough for a meeting
            # in a square; the test is a distance, not a line of sight.
            g._tell_timer -= g.dt
            if g._tell_timer <= 0.0:
                g._tell_timer = 0.5
                nemesis.spread_on_contact()

            # WHERE THE MEN WALK TO. The frame owns the yard; the lane owns
            # the men, so the post is relayed -- and cleared when one is let go.
            _wp = getattr(g.player, "work_post", None)
            g._now_held = {id(n): n for n in (getattr(g.player, "workers", ()) or ())}
            for _k, _n in list(g._posted.items()):
                if _k not in g._now_held:
                    g._WORK.post(_n, None)
                    g._posted.pop(_k, None)
            for _k, _n in g._now_held.items():
                if g._posted.get(_k, "unset") != _wp:
                    g._WORK.post(_n, _wp)
                    g._posted[_k] = _wp
            # ---- THE WALK, PHASE BY PHASE -------------------------------
            # A hired man is a man in a town who then has to WALK to the yard.
            # This is the whole journey in the log: he starts, he is a
            # measured distance from the post every twenty seconds, and he
            # arrives -- so "did he actually come?" is never a guess.
            if _wp is not None:
                for _k, _n in g._now_held.items():
                    if not getattr(_n, "alive", True):
                        g._walk_log.pop(_k, None)
                        continue
                    _d = math.hypot(_n.x - _wp[0], _n.y - _wp[1])
                    g._seen = g._walk_log.get(_k)
                    if _d <= 40.0:
                        if g._seen is not None:
                            # _seen is [first_seen, last_logged] -- a list, and
                            # subtracting it crashed the frame on the very
                            # arrival it was written to celebrate.
                            plog.log("PHASE-ARRIVED", getattr(_n, "name", "?"),
                                     "after", int(g.now - g._seen[0]), "s", "at",
                                     "%d,%d" % (int(_n.x), int(_n.y)))
                            g._walk_log.pop(_k, None)
                    elif g._seen is None:
                        g._walk_log[_k] = [g.now, g.now]
                        plog.log("PHASE-WALK", getattr(_n, "name", "?"),
                                 "starts", int(_d), "px from the post")
                    elif g.now - g._seen[1] >= 20.0:
                        g._seen[1] = g.now
                        plog.log("PHASE-WALK", getattr(_n, "name", "?"),
                                 "distance", int(_d), "px after",
                                 int(g.now - g._seen[0]), "s")

            try:
                nemesis.set_now(g.now)
            except Exception:
                pass
            # ---- ANYBODY OVER THE CAMP FENCE IS SHOT --------------------
            try:
                import gulag as _gulag_t
                g._n_in = _gulag_t.tick(g.player, g.enemies, village_mod.PEOPLE,
                                      combat=g.combat, dt=g.dt)
                if g._n_in and int(g.now) - int(getattr(_gulag_t, "_said", -99)) >= 3:
                    _gulag_t._said = g.now
                    plog.log("GULAG-INTRUDER", g._n_in, "inside the fence")
            except Exception:
                pass
            # ---- THE STATE'S BEER COMES OFF THE TRAIN -------------------
            try:
                import govbeer as _govbeer
                if g._TEST_TRAIN[0] is not None:
                    _govbeer.tick(g._TEST_TRAIN[0], g.villages.villages, g.dt, g.now)
            except Exception as _gbe:
                plog.log("GOVBEER-ERR", repr(_gbe)[:140])
            # ---- GUNFIRE SCATTERS A CROWD ------------------------------
            try:
                g._panic_t[0] += g.dt
                if g._panic_t[0] >= 0.25:
                    g._panic_t[0] = 0.0
                    g._fresh = [b for b in g.combat.bullets if b.travelled < 40.0]
                    for _b in g._fresh[:3]:
                        g._WORK.panic_at(_b.origin_x, _b.origin_y, 620.0)
            except Exception as _pn:
                plog.log("PANIC-ERR", repr(_pn)[:120])
            # ---- THE CAMP'S PEOPLE --------------------------------------
            try:
                import prison as _prison
                _prison.tick(g.player, g.enemies, list(village_mod.PEOPLE), g.dt, g.now, g.combat)
            except Exception as _pe:
                plog.log("PRISON-ERROR", repr(_pe)[:140])
            # ---- THE RESETTLEMENT CAMPAIGN ------------------------------
            try:
                import resettle as _reset
                _reset.tick(g.villages.villages, g.now, g.dt)
            except Exception as _re3:
                plog.log("RESETTLE-ERROR", repr(_re3)[:140])
            # ---- ARREST AND DETENTION -----------------------------------
            try:
                import detain as _detain
                # a tranquilised player is carried in by the nearest militia
                if getattr(g.player, "sleep_t", 0.0) > 0.0 and not getattr(g.player, "aboard", False):
                    g._pc = _detain.player_cell()
                    if g._pc is None:
                        g._near = _detain._militia_near(g.player, g.enemies,
                                                      village_mod.PEOPLE,
                                                      g.player.x, g.player.y, 900.0)
                        g._cell = _detain._nearest_cell(g.player.x, g.player.y)
                        if g._near and g._cell is not None:
                            _detain.arrest_player(g.player, g._cell)
                            # HE IS CARRIED INSIDE, NOT LEFT ON THE ROOF.
                            g._croom = getattr(g._cell, "room", None)
                            if g._croom is not None:
                                g.inside_mine = g._cell
                                g.player._mine_latch = True
                                g.player.x = g._croom.W / 2.0
                                g.player.y = g._croom.H - 40.0
                                g.cam_x = g.player.x - g.vw / 2.0
                                g.cam_y = g.player.y - g.vh / 2.0
                                pygame.mouse.set_visible(True)
                                plog.log("ENTER-CELL", "the player is inside the cell at",
                                         int(g._cell.x), int(g._cell.y))
                _detain.player_tick(g.player, g._TEST_TRAIN[0], g.dt)
                # the train plans its calls where people are actually waiting
                if int(g.now * 2) != int(getattr(_detain, "_plan_at", -1)):
                    _detain._plan_at = g.now * 2
                    _detain.pickup_order(g._TEST_TRAIN[0])
                _detain.tick(g.player, g.enemies, village_mod.PEOPLE, g.dt, g.now)
                g._tr0 = g._TEST_TRAIN[0]
                if g._tr0 is not None and not g._tr0.done:
                    _detain.board_train(g._tr0, g.player, g.now)
            except Exception as _de:
                plog.log("DETAIN-ERROR", repr(_de)[:140])
            # ---- THE TEST TRAIN -----------------------------------------
            try:
                _tr = g._TEST_TRAIN[0]
                if _tr is not None and not _tr.done:
                    _tr.update(g.world_dt if g.world_tick else g.dt)
                    try:
                        import train as _tm2
                        _tm2.KNOCK[:] = [k for k in _tm2.KNOCK
                                         if not k.settled or k.life < 8.0]
                        for _k in _tm2.KNOCK:
                            _k.update(g.dt, g.blood, corpse_mod)
                        _tr.hit_people(list(village_mod.PEOPLE), list(g.enemies),
                                       g.player, g.blood)
                    except Exception as _ke:
                        plog.log("TRAIN-KILL-ERR", repr(_ke)[:120])
                    if int(g.now * 4) != int(getattr(_tr, "_ck", -1)):
                        _tr._ck = g.now * 4
                        g._towns_near = [v for v in g.villages.villages
                                       if abs(v.x - _tr.x) < 9000.0
                                       and abs(v.y - _tr.y) < 9000.0]
                        _tr.check(g.world, g._towns_near, g.built_houses,
                                  g.placed_work, g.camp_walls)
            except Exception as _te2:
                plog.log("TRAIN-ERROR", repr(_te2)[:160])
            # ---- THE CROWN ANSWERS THE NAME -----------------------------
            try:
                g._lead = nemesis.FACTS.get(nemesis.LEADER_ID)
                if g._lead is not None:
                    if not manhunt.SENT:
                        manhunt.dispatch(g.player, g._lead.get("at"), now=g.now,
                                         enemies=g.enemies,
                                         villages=g.villages.villages)
                    manhunt.tick(g.player, g.enemies, g.now)
                    if int(g.now) - int(getattr(manhunt, "_said", -999)) >= 5:
                        manhunt._said = g.now
                        plog.log("MANHUNT-STATE",
                                 "standing", manhunt.any_standing(g.enemies),
                                 "of", len(g.enemies), "soldiers",
                                 "| at", int(g.player.x), int(g.player.y))
            except Exception as _exc:
                plog.log("MANHUNT-ERR", repr(_exc))
            if int(g.now) % 60 == 0:
                try:
                    folders_mod.prune(g.now)
                except Exception:
                    pass

            # ---- THE DEAD STAY WHERE THEY FALL --------------------------
            g._last_death = getattr(g._WORK, "_last_death", None)
            for _rec in g._WORK.take_deaths():
                _rec = tuple(_rec) + (False, [], False, [])
                (_dx, _dy, _who, g._pack, g._grade, g._cloth, g._agent, g._facts,
                 g._worker, g._bag) = _rec[:10]
                g._fid = None
                if g._agent:
                    # THE FOLDER IN HIS POCKET: everything the service told him.
                    g._fid = folders_mod.new_folder(_who, g._facts, g.now)
                    plog.log("FOLDER", _who, "carried",
                             len(folders_mod.FOLDERS[g._fid]["msgs"]), "message(s)")
                corpse_mod.spawn(_dx, _dy, _who, g.now, g._cloth,
                                 g._bag or g._pack, g._grade, folder=g._fid)
                plog.log("CORPSE", _who, "fell at",
                         "%d,%d" % (int(_dx), int(_dy)),
                         "carrying", len(g._bag) or len(g._pack))
                if g._worker:
                    # A BODY IS EVIDENCE. An agent who comes upon one of the
                    # player's dead learns that the yard has a leader.
                    try:
                        for _a in nemesis.agents():
                            if not getattr(_a, "alive", True):
                                continue
                            if ((_a.x - _dx) ** 2 + (_a.y - _dy) ** 2
                                    > nemesis.SEEN_PX ** 2):
                                continue
                            if nemesis.note_leader(_a, at=(_dx, _dy)):
                                plog.log("LEADER", getattr(_a, "name", "?"),
                                         "saw the body of", _who,
                                         "and learned who leads the yard")
                            break
                    except Exception:
                        pass
            for _gone in corpse_mod.update(g.now):
                plog.log("CORPSE", _gone.name, "is bones and gone")

            # THE STALL GOES ACROSS THE FENCE, once a second: the carts that
            # might walk to it are in the hub lane, and a counter they cannot
            # see is a counter nobody comes to.
            g._stall_now = g.hub_stall()
            g.player.hub_stall = g._stall_now
            g.player.town_price_for = g._town_price_for
            g._WORK.stall = (g._stall_now.relay()
                           if g._stall_now is not None else None)

            # THE MEN WORK THE POST THEY WALKED TO. The frame owns the yard
            # and its chest, so the work -- and what is made, and what will
            # not fit -- happens here, where the chest is.
            g._chest = g.salary_chest()
            g.player.hub_chest = g._chest
            # `dt`, NOT `world_dt`: the men work once per FRAME, and
            # `world_dt` is the step of the world tick that is about to run --
            # the last one, five times a frame's length. Every trade was
            # therefore working about three times faster than a day says.
            for _kind, _man, _what in work.produce(
                    g.player, g._chest, g.dt, world=g.world, ground=g.ground,
                    plots=(getattr(g.player, "yard_plots", None)
                           or [tuple(r) for r in g.built_plots]), now=g.now):
                if _kind == "made":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             getattr(_man, "job", "?"), "made", _what)
                elif _kind == "full":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "chest FULL, kept", _what)
                    g.toast("%s: nowhere to put the %s"
                          % (getattr(_man, "name", "he"),
                             ", ".join(i.replace("_", " ") for i in _what)))
                elif _kind == "idle":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "has nothing to work with")
                elif _kind == "stopped":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "told to leave off", _what)
                elif _kind == "farm":
                    plog.log("FARM", getattr(_man, "name", "?"), _what,
                             "at", "%d,%d" % (int(_man.x), int(_man.y)))
                elif _kind == "nochess":
                    plog.log("WORK", getattr(_man, "name", "?"),
                             "made", _what, "-- NO CHEST in the hub")

            # HIS OWN MEN ARE PAID OUT OF THE CHEST IN HIS HUB, once a day.
            g._pay = work.payroll(g.player, int(g.now / DAY_LENGTH), g.salary_chest(),
                                g.hub_stall())
            for _q in g._pay.get("unpaid", ()):
                g.toast("%s was not paid.   He remembers it." % getattr(_q, "name", "he"))
            for _q in g._pay.get("quit", ()):
                g.toast("%s was not paid.   He walks."
                      % getattr(_q, "name", "He"))
            for _who, _has in (g._pay.get("seeds") or {}).items():
                if not _has:
                    g.toast("%s has no seed to sow -- put some in the chest" % _who)
            # AND A BITTER ONE IS NOT SACKED: he stays on the payroll, and the
            # first service man to come near him turns him. Nothing is said to
            # the player -- that is the point of it.
            work.turn_the_bitter(g.player, nemesis.agents())

            g.settle_timer -= g.dt
            if g.settle_timer <= 0.0:
                g.settle_timer = 12.0
                if not g._W_ON:
                    g.villages.send_idle(g.now)
            # A CARAVAN AND A COLUMN. Traders work the same roads the armies
            # march on, and the free-trade policy is the only thing that lets
            # them cross a war unshot -- so this is where word of a campaign
            # gets off the road and into the hands that want it.
            for _tr in list(village_mod.TRAVELLERS):
                if (not getattr(_tr, "alive", False)
                        or getattr(_tr, "job", None) != "trader"
                        or getattr(_tr, "trade_state", "none") == "none"):
                    continue
                for _a in g.armies:
                    if _a.done or getattr(_a, "engage", False):
                        continue          # never during a battle: they scatter
                    g._lead = _a.soldiers[0] if _a.soldiers else None
                    if g._lead is None or not g._lead.alive:
                        continue
                    if math.hypot(_tr.x - g._lead.x, _tr.y - g._lead.y) > 300.0:
                        continue
                    g._meet_army(_tr, _a, g.now)
            # THE CROWN ASKS, once a day: its strongest column's last five
            # days, and three days for a rider to bring the answer.
            g.demand_timer -= g.dt
            if g.demand_timer <= 0.0:
                g.demand_timer = DAY_LENGTH
                for _v in g.villages.villages:
                    # ONLY WHEN THERE IS NO OFFER OUT. Re-posting every day
                    # made the crown's offer perpetual, and a deadline that
                    # never arrives is not a deadline.
                    _d = getattr(_v, "demand", None)
                    if (getattr(_v, "is_capital", False)
                            and (_d is None or g.now > _d["expires"])):
                        war.post_demand(_v, g.armies, g.now)   # a lapsed offer is
                        # replaced: the crown asks again, and again, until it
                        # is told. Without this it asked once and went quiet.
            # A HUNTING PARTY IS NEVER CULLED BY DISTANCE. It is sent to a
            # place, not to the player: it stands there until it is met or
            # killed. Without this line the ten men were created, logged, and
            # deleted in the same frame whenever the player was not already
            # within 6.5 km of the spot the crown picked.
            g.enemies[:] = [e for e in g.enemies
                          if getattr(e, "follow", False)
                          or getattr(e, "manhunt", False)
                          or getattr(e, "gulag", False)
                          or getattr(e, "guard_village", None) is not None
                          or getattr(e, "patrol_center", None) is not None
                          or math.hypot(e.x - g.player.x, e.y - g.player.y) < 6500.0]
            g.rabbits[:] = [r for r in g.rabbits
                          if math.hypot(r.x - g.player.x, r.y - g.player.y) < 3200.0]

            # -- battle, plunder, conquest ----------------------------------
            if g.player.nation is not None:
                for village in g.visible_villages:
                    if village.conquered or village.nation == g.player.nation:
                        continue
                    if village.chaos > 0.0:                 # already plundering
                        continue
                    g.near = math.hypot(g.player.x - village.x,
                                      g.player.y - village.y) < village.radius
                    if not g.near:
                        g.near = any(s.alive and math.hypot(s.x - village.x,
                                                          s.y - village.y)
                                   < village.radius for s in g.player.squad)
                    if g.near or village.battle:
                        if any(n.alive and n.defender for n in village.npcs):
                            village.battle = True
                            village.provoke()
                        else:                           # won: 3 minutes to loot
                            village.battle = False
                            village.plundered = True
                            village.chaos = 180.0
                            g.active_chaos.append(village)
                            for h in village.houses:
                                if not getattr(h, "door_broken", False):
                                    h.enterable = True
                                    h.interior = Interior(random.randint(0, 2 ** 31),
                                                          tuple(h.facing))
                                    fill_loot(h.interior.chest)
                                    h.break_door()
                            g.loot = random.randint(5, 20)
                            g.inventory.add("coin", g.loot)
                            g.inventory.add("tobacco", random.randint(6, 16), 6)
                            g.toast(f"Battle won!   Plunder for 180s   +{g.loot} coins")

            # -- wounded characters leave a blood trail ---------------------
            if g.player.bleed > 0.0 and not g.player.dead:
                g.player_drip -= g.dt
                if g.player_drip <= 0.0:
                    g.blood.drip(g.player.x, g.player.y, 2)
                    g.player_drip = 0.28
            else:
                g.player_drip = 0.0
            for enemy in g.enemies:
                if enemy.bleed > 0.0:
                    enemy.drip_timer -= g.dt
                    if enemy.drip_timer <= 0.0:
                        g.blood.drip(enemy.x, enemy.y, 2)
                        enemy.drip_timer = 0.30
            for village in g.visible_villages:
                for npc in village.npcs:
                    if npc.bleed > 0.0:
                        npc.drip_timer -= g.dt
                        if npc.drip_timer <= 0.0:
                            g.blood.drip(npc.x, npc.y, 2)
                            npc.drip_timer = 0.30

            g.blood.update(g.dt)

            # THE CAMERA FOLLOWS WHAT IS BEING WATCHED -- INCLUDING THE EASE.
            #
            # This eased toward player.x/player.y, which UNDID the watching
            # override set below it: the camera was put on the watched man and
            # then dragged back toward the parked player sixty thousand pixels
            # away, a little every frame. The ground streamed after a point that
            # was crawling off the man, so the view drifted and the scenery
            # arrived in the wrong place. The smoothing belongs to whoever the
            # view belongs to.
            g._wt = g.observer_.target
            g._watch = g._wt is not None and getattr(g._wt, "alive", False)
            g._fx = g._wt.x if g._watch else g.player.x
            g._fy = g._wt.y if g._watch else g.player.y
            # WHEN THE WATCH CHANGES, BUILD THE GROUND UNDER HIM **NOW**.
            #
            # The worker streams chunks behind the camera and it keeps up with a
            # man walking. It does NOT keep up with a camera that has just
            # jumped a hundred thousand pixels to another village, so the view
            # showed whatever happened to be built -- which is why watching
            # somebody looked wrong at the edges and nothing like the quality
            # around the player. This is exactly what refresh_around() is for
            # ("build the ground under the player NOW, for loading a save"), and
            # it bumps the ground's version so StaticLayer recomposes from the
            # fresh chunks instead of the stale ones.
            g._wt = g.observer_.target
            if g._wt is not g._watched_last:
                g._watched_last = g._wt
                if g._wt is not None and getattr(g._wt, "alive", False):
                    g.ground.refresh_around(g._wt.x, g._wt.y, WIDTH, HEIGHT)

            # SETTLEMENT VIEW: the camera is the player's pan, not a follower.
            if not g.field_design:
                g.cam_x += (g._fx - g.vw / 2 - g.cam_x) * min(1.0, g.dt * 9.0)
                g.cam_y += (g._fy - g.vh / 2 - g.cam_y) * min(1.0, g.dt * 9.0)

            g.ground.update(6, g.cam_x, g.cam_y, g.vw, g.vh)   # worker builds ahead of us
            g.trees.update(g.now)                        # stumps grow back

            # THE BARN IS ENTERED BY WALKING THROUGH ITS DOOR, the way a house
            # is -- and lands in the mine's own room branch, so the drawing and
            # the way out are the mine's.
            g.prison_cd = max(0.0, g.prison_cd - g.dt)
            if g.inside_house is None and g.inside_mine is None and g.prison_cd <= 0.0:
                try:
                    import gulag as _gbar
                    g._bar = _gbar.prison()
                except Exception:
                    g._bar = None
                g._doors = []
                if g._bar is not None:
                    g._doors.append(g._bar)
                try:
                    import holding as _hwalk
                    g._doors.extend(_hwalk.cells())
                except Exception:
                    pass
                g._hit = None
                for _d in g._doors:
                    g._dx2 = g.player.x - _d.door[0]
                    g._dy2 = g.player.y - _d.door[1]
                    if g._dx2 * g._dx2 + g._dy2 * g._dy2 < 26.0 * 26.0:
                        g._hit = _d
                        break
                if g._hit is not None:
                    g.mine_out = (g.player.x, g.player.y)
                    g.inside_mine = g._hit
                    g.player._mine_latch = True
                    g.player.x = g._hit.room.W / 2.0
                    g.player.y = g._hit.room.H - 70.0
                    g.cam_x = g.player.x - g.vw / 2.0
                    g.cam_y = g.player.y - g.vh / 2.0
                    pygame.mouse.set_visible(True)
                    plog.log("ENTER-CELL", getattr(g._hit, "kind", "?"), "at",
                             int(g._hit.x), int(g._hit.y))
                    continue
                if g._bar is not None:
                    g._ddx = g.player.x - g._bar.door[0]
                    g._ddy = g.player.y - g._bar.door[1]
                    if g._ddx * g._ddx + g._ddy * g._ddy < 26.0 * 26.0:
                        g.mine_out = (g.player.x, g.player.y)
                        g.inside_mine = g._bar
                        g.player._mine_latch = True
                        g.player.x = g._bar.room.W / 2.0
                        g.player.y = g._bar.room.H - 90.0
                        g.cam_x = g.player.x - g.vw / 2.0
                        g.cam_y = g.player.y - g.vh / 2.0
                        pygame.mouse.set_visible(True)   # the cursor stays
                        plog.log("ENTER-BARN", "through the door at",
                                 int(g._bar.door[0]), int(g._bar.door[1]))
                        continue

            if False:   # THE INTERIOR SYSTEM IS GONE: houses and mines are not entered
                g.candidates = list(g.built_houses)
                for village in g.visible_villages:
                    g.candidates.extend(village.houses)
                for house in g.candidates:
                    if not getattr(house, "enterable", False):
                        continue
                    g.interior = getattr(house, "interior", None)
                    if g.interior is None:
                        continue
                    g.fx, g.fy = house.facing
                    g.door_x = house.x + g.fx * (house.h / 2.0 + 6.0)
                    g.door_y = house.y + g.fy * (house.h / 2.0 + 6.0)
                    if ((g.player.x - g.door_x) ** 2 + (g.player.y - g.door_y) ** 2
                            < 24.0 ** 2):
                        try:
                            import houseroom as _hr
                            g._room_h = _hr.HouseRoom(house, g.interior)
                        except Exception as _hre:
                            plog.log("HOUSEROOM-ERR", repr(_hre)[:140])
                            break
                        g.mine_out = (g.door_x + g.fx * 60.0, g.door_y + g.fy * 60.0)
                        g.inside_mine = g._HouseBar(house, g._room_h, g.mine_out)
                        g.inside_house = house
                        g.player._mine_latch = True
                        g.player.world_xy = (float(g.door_x), float(g.door_y))
                        # LIKE THE GULAG: HE LANDS BESIDE THE DOOR. The exit is a
                        # 24-pixel collision now, not a wide radius, so standing
                        # 30 px up from the door cannot fire it -- but he is one
                        # step from the way out, not a walk across the room.
                        g._sp = getattr(g.interior, "spawn",
                                      (g.interior.W / 2.0, g.interior.H - 48.0))
                        g.player.x, g.player.y = float(g._sp[0]), float(g._sp[1])
                        g.player.bleed = 0.0
                        g.combat.bullets.clear()
                        g.prison_cd = 0.7
                        g.door_cooldown = 0.7      # grace: not thrown straight out
                        pygame.mouse.set_visible(True)
                        plog.log("ENTER-HOUSE", getattr(house, "name", "?"),
                                 "through the door at", int(g.door_x), int(g.door_y),
                                 "room", g.interior.W, g.interior.H)
                        break

            if g.player.dead:
                g.game_over = True
                pygame.mouse.set_visible(True)

        # -- underground ------------------------------------------------------
        # A mine is its own little world: solid rock all round, no window, no
        # view out, and a seam in the middle that never runs out. Handled here
        # and returned from, so nothing in the open air can be disturbed by it.
        if g.inside_mine is not None:
            g._branch = 'mine'
            g._room = g.inside_mine.room
            g._room.update(g.dt)
            g.mine_cd = max(0.0, g.mine_cd - g.dt)
            g.door_cooldown = max(0.0, g.door_cooldown - g.dt)
            g._keys = pygame.key.get_pressed()
            if getattr(g._room, "is_house", False):
                g._door = getattr(g._room, "door_rect", None)
                if g._door is not None:
                    g._dd = math.hypot(g.player.x - g._door.centerx,
                                     g.player.y - g._door.centery)
                    if g._dd < 140.0:
                        g._HCH = getattr(main, "_house_check", 0.0)
                        main._house_check = g._HCH + g.dt
                        if main._house_check >= 0.5:
                            main._house_check = 0.0
                            plog.log("HOUSE-DOOR", "player", int(g.player.x),
                                     int(g.player.y), "door", int(g._door.centerx),
                                     int(g._door.centery), "dist", int(g._dd),
                                     "in", g.inside_house is not None,
                                     "mine", g.inside_mine is not None)
            # THE KEY THAT OPENED IT MUST BE RELEASED FIRST. This block reads
            # key STATE, not key events, so the E that took you down was still
            # held on the next frame and slammed the door behind you -- a dark
            # flash and a wiggle, then back in the daylight. Every other menu
            # in the game uses KEYDOWN, which fires once; this one waits for
            # the finger to come off E before it will listen to it again.
            # THE WAY OUT IS THE WAY IN: walk back into the doorway.
            if getattr(g._room, "is_prison", False) or getattr(g._room, "is_house", False):
                _dr = getattr(g._room, "door_rect", None)
                # THE DOORWAY IS A DOORWAY, NOT A HAIRLINE. The old test asked
                # a 16-pixel box to overlap the frame exactly; a man walking at
                # a run stepped clear past it between two frames and never left.
                # Distance to the middle of the doorway: get anywhere near it
                # and you are out.
                if (_dr is not None
                        and math.hypot(g.player.x - _dr.centerx,
                                       g.player.y - _dr.centery) < 40.0):
                    g.inside_mine = None
                    g.inside_house = None
                    g.player.x, g.player.y = g.mine_out
                    g.player.world_xy = (float(g.mine_out[0]), float(g.mine_out[1]))
                    g.prison_cd = 1.0
                    g.door_cooldown = 0.7
                    pygame.mouse.set_visible(False)
                    plog.log("EXIT-HOUSE", "door", int(_dr.centerx),
                             int(_dr.centery), "-> outside", int(g.mine_out[0]),
                             int(g.mine_out[1]))
                    continue
            if getattr(g._room, "is_house", False) or getattr(g._room, "is_cell", False):
                pass        # a cell's door is the state's, not E's
            elif getattr(g.player, "_mine_latch", False):
                if not g._keys[pygame.K_e]:
                    g.player._mine_latch = False
            elif g._keys[pygame.K_e] or g._keys[pygame.K_ESCAPE]:
                g.inside_mine = None                 # back up the shaft
                g.inside_house = None
                g.player.x, g.player.y = g.mine_out
                g.prison_cd = 1.0                    # step off the threshold first
                pygame.mouse.set_visible(False)
                continue
            # A HOUSE IS DRAWN EXACTLY LIKE THE GULAG: 1:1, centred, the whole
            # floor on screen including the door. No buffer, no second scale --
            # that buffer was cutting the bottom hundred pixels of the room off,
            # so the doorway was below the visible floor and he could never
            # walk into it.
            g.cam_x = g._room.W / 2.0 - g.vw / 2.0
            g.cam_y = g._room.H / 2.0 - g.vh / 2.0
            g._draw_w, g._draw_h = g.vw, g.vh
            g.wmouse_x = g.mouse_x
            g.wmouse_y = g.mouse_y
            g._aim = (g.wmouse_x - (g.player.x - g.cam_x), g.wmouse_y - (g.player.y - g.cam_y))
            g.player.skill_speed = g.skills.move_scale()
            g.award_levels()
            g.player.skill_stamina = g.skills.stamina_scale()
            g.player.update(g.dt, g._keys, g._aim, 1.0)
            if getattr(g._room, "is_house", False):
                try:
                    g.player.x, g.player.y = resolve_circle_rects(
                        g.player.x, g.player.y, g.player.radius,
                        getattr(g.inside_house, "interior").colliders)
                except Exception:
                    g.player.x, g.player.y = g._room.clamp(g.player.x, g.player.y)
            else:
                g.player.x, g.player.y = g._room.clamp(g.player.x, g.player.y)
            if getattr(g._room, "is_cell", False):
                try:
                    import detain as _det_c
                    _det_c.player_tick(g.player, g._TEST_TRAIN[0], g.dt)
                except Exception:
                    pass
                if getattr(g.player, "aboard", False):
                    g.inside_mine = None
                    g.inside_house = None
                    pygame.mouse.set_visible(False)
                    continue
            # SWING AT THE FACE. Fifteen of these to the open seam's three,
            # and it is still there afterwards -- the seam never runs out.
            if (pygame.mouse.get_pressed()[0] and g.mine_cd <= 0.0
                    and not getattr(g._room, "is_prison", False)
                    and not getattr(g._room, "is_house", False)):
                g.mine_cd = 0.35
                g._hold = g.inventory.selected_stack()
                if g._hold is None or g._hold.defn.id != "pickaxe":
                    # IRON IS NOT AXED OUT OF ROCK. The open seams have always
                    # demanded a pickaxe, because only the pickaxe's own swing
                    # goes looking for ore -- but the mine took any click at
                    # all, so a man could break iron out of the face with an
                    # axe, or with his bare hands.
                    g.toast("You need a pickaxe for the seam")
                elif not g._room.hits_chunk(g.player.x, g.player.y):
                    g.toast("Get closer to the seam")
                elif not g.player.can_swing():
                    pass                      # still getting his wind back
                else:
                    g.player.start_swing()      # the same wind-up as anywhere
                    g.combat.spawn_swing(g.player.x, g.player.y, g.player.facing_angle)
                    g._got = g._room.swing((ore.YIELD_LO, ore.YIELD_HI))
                    if g._got:
                        g.inventory.add("iron", g._got)
                        g.pay_share("iron", g._got)
                        g.toast("Broke out %d iron" % g._got)
            g._room.draw(g.screen, g.cam_x, g.cam_y, g._draw_w, g._draw_h)
            if getattr(g._room, "is_house", False):
                g.draw_placing()
            if getattr(g._room, "is_prison", False):
                # SIMPLY DARK: one flat veil over the room, nothing else. No
                # hole to follow the man, no rectangles to leave edges.
                try:
                    import gulag as _gdark
                    _gdark.darken(g.screen)
                except Exception:
                    pass
            g._sel = g.inventory.selected_stack()
            if not getattr(g.player, "aboard", False):
                g.player.draw(g.screen, g.cam_x, g.cam_y, g._sel.defn.id if g._sel else None)
            g.observer_.draw(g.screen)
            try:
                if g.chest_open:
                    g.chest_panel.draw(g.screen)
                if g.workshop_open:
                    g.workshop_menu.draw(g.screen)
                if g.inventory_open:
                    g.panel.draw(g.screen)
                if g.build_menu_open:
                    g.build_menu.draw(g.screen)
                if g.trade_open:
                    g.trade_menu.draw(g.screen)
                if g.pause_open:
                    g.pause_menu.draw(g.screen)
            except Exception as _pe2:
                plog.log("ROOM-PANEL-ERR", repr(_pe2)[:120])
            g.hotbar.draw(g.screen)
            g.hotbar.draw_stamina(g.screen, g.player.stamina / g.player.max_stamina,
                                g.player.exhausted)
            g.hotbar.draw_hunger(g.screen, g.player.hunger / g.player.max_hunger)
            if g.toast_time > 0.0:
                g.toast_time = max(0.0, g.toast_time - g.dt)
                g._lab = g.font.render(g.toast_text, True, TOAST_COLOR)
                g._lab.set_alpha(int(255 * min(1.0, g.toast_time / 0.5)))
                g.screen.blit(g._lab, (g.vw // 2 - g._lab.get_width() // 2, int(g.vh * 0.68)))
            pygame.display.flip()
            continue


        # -- draw world ------------------------------------------------------
        g.tick_conquest(g.dt)
        g.update_hud()
        if g.map_open and g.world_map is not None:
            g.world_map.update(g.dt)
            # The map is live: while it is open the armies alone continue the
            # march, so their markers walk across it. Nothing else in the world
            # is simulated -- no villages, no economy, no vision -- because
            # running all of that with the map up is what froze the game solid.
            if g.test_mode and g.armies:
                for _army in g.armies:
                    if _army.done:
                        continue
                    for _s in _army.soldiers:
                        g.mt = getattr(_s, "march_target", None)
                        if g.mt is None or not _s.alive:
                            continue
                        g.ux, g.uy = steering.steer(_s, g.mt[0], g.mt[1], [], [])
                        _s.x += g.ux * 240.0 * g.dt
                        _s.y += g.uy * 240.0 * g.dt
                war.update(g.armies, g.dt, g.now)
        if g.inside_house is not None and g.inside_mine is None:
            g.interior = g.inside_house.interior
            # THE INTERIOR IS DRAWN AT THE SAME ZOOM AS THE WORLD. It was still
            # composed in a full-window frame while its camera came from the
            # narrowed one, so the room hung off-centre with the man not in the
            # middle of it. Borrow the view for the room -- the walls, the
            # window, the people, the man -- and hand the window back for the
            # HUD, exactly as the outdoors does.
            # THE ROOM IS DRAWN AT 1:1, STRAIGHT TO THE SCREEN, LIKE A MINE.
            # It used to be rendered into a 4/9 surface and smooth-scaled back
            # up every frame: a full-window resample per frame for a picture
            # that never changes.
            g.real_screen = g.screen
            g.cam_x = min(max(g.player.x - g.vw / 2.0, 0.0),
                        max(0.0, g.interior.W - g.vw))
            g.cam_y = min(max(g.player.y - g.vh / 2.0, 0.0),
                        max(0.0, g.interior.H - g.vh))
            # INSIDE A HOUSE THERE IS NO OUTSIDE. Black beyond the walls --
            # not a painted world. The room, the furniture, the chest, the
            # workshop, the residents and the vision mask are all exactly as
            # they were; only the view out of the windows is gone, and with it
            # the only reason this branch ever touched the world outside.
            g.screen.fill((0, 0, 0))
            # ONE BLIT OF A ROOM PAINTED ONCE -- exactly how a mine does it.
            try:
                g.interior.draw_baked(g.screen, g.cam_x, g.cam_y)
            except AttributeError:
                g.interior.draw(g.screen, g.cam_x, g.cam_y)
            # THE SAME GREEN OUTLINE AS OUTDOORS, while he is placing furniture.
            g.draw_placing()
            g.eye_x = g.player.x - g.cam_x + g.player.facing[0] * 5.0
            g.eye_y = g.player.y - g.cam_y + g.player.facing[1] * 5.0
            if not getattr(g.interior, "windows", True):
                # A WINDOWLESS HALL: nothing to look through, so no cone to
                # rasterise and no dark to lay over it.
                g.draw_below = False
            g.inside_occluders = [pygame.Rect(r.x - g.cam_x, r.y - g.cam_y, r.w, r.h)
                                for r in g.interior.occluders]
            # THE ROOM'S LIGHT CONE IS NOT REBUILT EVERY FRAME. `build` walks
            # the occluders and rasterises a mask -- and it was being done sixty
            # times a second while the eye moved by a pixel, which is the hitch
            # going into any building. Same mask while the eye is in the same
            # eighth-of-a-metre cell and the head has not turned.
            # A HOUSE IS LIT. The old vision cone laid a darkness over the
            # room except a sliver around the man's head -- which is why a
            # house looked like an empty dark box. The room is drawn bright,
            # furniture and all; no mask, no night veil over it.
            g.selected = g.inventory.selected_stack()
            for npc in getattr(g.inside_house, "occupants", ()):
                if npc.alive and npc.in_interior:      # residents move about
                    npc.draw(g.screen, g.cam_x, g.cam_y, True)
        g._sel0 = g.inventory.selected_stack()      # never rely on a name that a
        # branch may not have assigned: `selected` was unbound on the frames the
        # player was not inside a house, and this is the line that draws him.
        if not getattr(g.player, "aboard", False):
            g.player.draw(g.screen, g.cam_x, g.cam_y, g._sel0.defn.id if g._sel0 else None)
        if getattr(g.player, "search_progress", 0.0) > 0.0:
            # THE BAR HANGS UNDER THE MAN DOING THE SEARCHING, not in the middle
            # of the screen. Pivot.md S3: he is ten seconds at it, and the
            # patience of the queue is the whole point of the gate.
            g._sv = getattr(g.player, "search_village", None)
            g._bx = g._by = None
            for _s in (getattr(g._sv, "patrol", ()) or ()):
                if getattr(_s, "gate_index", None) == 0 or len(
                        getattr(g._sv, "patrol", ()) or ()) == 1:
                    g._bx, g._by = _s.x - g.cam_x, _s.y - g.cam_y
                    break
            if g._bx is None:
                g._bx, g._by = g.screen.get_width() * 0.5, g.screen.get_height() * 0.5
            Player._draw_action_bar(g.screen, g._bx, g._by,
                                    min(1.0, g.player.search_progress / 10.0))
            # own coordinates (box.x - cam_x), so it has to be drawn before the
            # frame is blown up -- drawn afterwards it landed at a quarter of
            # its size and a third of a screen from the cursor.
            g.draw_placing()
            # ...and back to the window for everything that is not the room.
            g.screen = g.real_screen
            g.draw_hunger_gray()
            if not g.inventory_open:
                draw_crosshair(g.screen, g.mouse_x, g.mouse_y)
            g.hotbar.draw(g.screen)
            g.hotbar.draw_stamina(g.screen, g.player.stamina / g.player.max_stamina,
                                g.player.exhausted)
            g.hotbar.draw_hunger(g.screen, g.player.hunger / g.player.max_hunger)
            if g.toast_time > 0.0:
                g.toast_time = max(0.0, g.toast_time - g.dt)
                g.fade = min(1.0, g.toast_time / 0.5)
                g.label = g.font.render(g.toast_text, True, TOAST_COLOR)
                g.label.set_alpha(int(255 * g.fade))
                g.plate = pygame.Surface((g.label.get_width() + 22, 26), pygame.SRCALPHA)
                pygame.draw.rect(g.plate, (18, 18, 22, 200), g.plate.get_rect(), border_radius=6)
                g.plate.set_alpha(int(255 * g.fade))
                g.tt = g.vw // 2 - g.label.get_width() // 2
                g.screen.blit(g.plate, (g.tt - 11, int(g.vh * 0.68) - 3))
                g.screen.blit(g.label, (g.tt, int(g.vh * 0.68)))
            if g.smith_open and g.smith_shop is not None:
                g._w = g.smith_shop.worker
                g._orders = list(getattr(g._w, "tool_orders", ()) or ())
                _r = pygame.Rect(g.vw // 2 - 220, g.vh // 2 - 150, 440, 300)
                g._shade = pygame.Surface((g.vw, g.vh), pygame.SRCALPHA)
                g._shade.fill((0, 0, 0, 170))
                g.screen.blit(g._shade, (0, 0))
                pygame.draw.rect(g.screen, (26, 26, 30), _r, border_radius=10)
                pygame.draw.rect(g.screen, (150, 118, 78), _r, 2, border_radius=10)
                g._titles = {"smith": "THE FORGE", "mine": "THE PIT HEAD",
                           "lab": "THE LABORATORY", "brewery": "THE BREWHOUSE"}
                g.screen.blit(g.font.render(
                    "%s   -   %s's" % (g._titles.get(g._w.kind if g._w else "", "THE BENCH"),
                                       g.smith_shop.worker.village.name
                                       if g.smith_shop.worker else "the village"),
                    True, (238, 224, 190)), (_r.x + 14, _r.y + 12))
                g.screen.blit(g.font.render("iron in stock: %d"
                                        % int(getattr(g._w, "stock", {}).get("iron", 0)),
                                        True, (232, 200, 118)), (_r.x + 14, _r.y + 38))
                g._y = _r.y + 66
                if not g._orders:
                    g.screen.blit(g.font.render("nothing booked", True, (150, 146, 138)),
                                (_r.x + 14, g._y))
                for _who, _want in g._orders[:9]:
                    _t = "%s wants a %s" % (getattr(_who, "name", "someone"), _want)
                    g.screen.blit(g.font.render(_t, True, (216, 212, 200)), (_r.x + 14, g._y))
                    g._y += 22
                if g._w is not None:
                    g._held = {k: int(v) for k, v in getattr(g._w, "stock", {}).items()
                             if k in ("axe", "shovel", "pickaxe") and v}
                    if g._held:
                        g.screen.blit(g.font.render("on the shelf: " + ", ".join(
                            "%d %s" % (q, i) for i, q in g._held.items()), True,
                            (200, 200, 190)), (_r.x + 14, _r.bottom - 44))
                _kind = g.smith_shop.kind
                g._hint = {"smith": "[Space] forge a tool",
                         "mine": "[Space] break out iron",
                         "lab": "[Space] work the leaf",
                         "brewery": ("[Space] draw the brew"
                                     if getattr(g.player, "brew", None) is not None
                                     else "[Space] start a mash")}.get(_kind, "")
                g.screen.blit(g.font.render("%s      [E] close   " % g._hint,
                                        True, (196, 226, 168)),
                            (_r.x + 14, _r.bottom - 24))
                if g.work_msg:
                    g.screen.blit(g.font.render(g.work_msg, True, (240, 206, 130)),
                                (_r.x + 14, _r.bottom - 46))
            if g.board_open and g.board_village is not None:
                g.board_panel.player = g.player
                g.board_panel.town_api = g._BOARD_API if g._W_ON else None
                if g._W_ON:
                    g._WORK.watch(g.board_panel._nearest(g.board_village, 3))
                g.board_panel.inv = g.inventory
                g.board_panel.chest = (g.inside_house.interior.chest
                                     if g.inside_house is not None
                                     else (g.built_houses[0].interior.chest
                                           if g.built_houses
                                           and g.built_houses[0].interior else None))
                g.board_panel.tax_day = int(g.now / DAY_LENGTH)
                g.board_panel.notice_t = max(0.0, g.board_panel.notice_t - g.dt)
                g.board_panel.draw(g.screen, g.board_village)
            g.draw_speed_button()
            if g.build_menu_open:
                g.build_menu.draw(g.screen)
            if g.compass_open:
                g.compass_menu.draw(g.screen)
            if g.dialogue_panel.open_:
                try:
                    g.dialogue_panel.draw(g.screen)
                except Exception:
                    import traceback as _tb
                    _tb.print_exc()
            if g.inventory_open:
                g.panel.draw(g.screen)
            if g.folder_open:
                g.folder_panel.draw(g.screen)
                plog.log("FOLDER-DRAW", "panel", int(g.folder_panel.page),
                         "at", int(g.screen.get_width()))
            if g.body_open:
                g.body_panel.draw(g.screen)
            if g.stall_open:
                g.stall_panel.draw(g.screen)
            if g.worker_panel_open:
                g.worker_panel.draw(g.screen)
            if g.chest_open:
                g.chest_panel.draw(g.screen)
            if g.workshop_open:
                g.workshop_menu.draw(g.screen)
            if g.trade_open:
                g.trade_menu.draw(g.screen)
            elif g.near_chest():
                g.hint = g.font.render("[E]  Open chest", True, (240, 232, 200))
                g.screen.blit(g.hint, (g.vw // 2 - g.hint.get_width() // 2, int(g.vh * 0.80)))
            elif g.near_workshop():
                g.hint = g.font.render("[E]  Use workshop", True, (240, 232, 200))
                g.screen.blit(g.hint, (g.vw // 2 - g.hint.get_width() // 2, int(g.vh * 0.80)))
            elif g.near_workplace() is not None:
                _k = g.near_workplace().kind
                _what = {"mine": "Go down the mine",
                         "smith": "The forge",
                         "lab": "The laboratory",
                         "brewery": "The brewhouse"}.get(_k, "Work here")
                g.hint = g.font.render("[E]  %s" % _what, True, (240, 232, 200))
                g.screen.blit(g.hint, (g.vw // 2 - g.hint.get_width() // 2, int(g.vh * 0.80)))
            if g.pause_open:
                g.pause_menu.draw(g.screen)
            if g.map_open:
                try:
                    g._wh = 0
                    for _e in pygame.event.get(pygame.MOUSEWHEEL):
                        g._wh += _e.y
                    mapmod.handle_input(g.dt, g.player, wheel=g._wh)
                    mapmod.draw(g.screen, g.world, g.player, g._nearest_town(),
                                g.hub_world.hubs,
                                settlements=list(g.villages.villages),
                                natives=list(getattr(g, "native_settlements", {}).values()))
                except Exception:
                    import traceback as _tb; _tb.print_exc()
            pygame.display.flip()
            continue

        # ---- THE ZOOM ------------------------------------------------------
        # The world is built in a surface two thirds the window's size and
        # blown up onto it: fewer pixels to compose every frame, and everything
        # on screen half again as large. `screen` and `vw/vh` are borrowed for
        # the duration, so every line of the world -- ground, trees, people,
        # the vision mask, blood -- lands in the smaller frame without one of
        # them being rewritten. They are handed back before the HUD, which
        # belongs at the window's own size.
        # INDOORS THE ROOM IS THE FRAME. The world's zoom borrow exists to
        # compose the outdoors in a smaller surface -- and its `_present` call
        # at the end of the frame scaled that (stale, black) surface back over
        # the window, wiping the room that had just been drawn. That is the
        # empty void: a correct room, painted over.
        g._inside_now = g.inside_house is not None or g.inside_mine is not None
        # A HOUSE IS COMPOSED SMALL AND BLOWN UP, like the world, so its floor
        # fills the window and the mouse maps at the same scale. A MINE draws
        # straight to the window at 1:1, as it always has.
        g.scr_w, g.scr_h = g.vw, g.vh
        g.real_screen = g.screen
        if g.inside_mine is not None:
            g.vw, g.vh = g.scr_w, g.scr_h
        else:
            g.vw, g.vh = (max(2, int(g.scr_w / g.zoom)), max(2, int(g.scr_h / g.zoom)))
            if g.view_surf is None or g.view_surf.get_size() != (g.vw, g.vh):
                g.view_surf = pygame.Surface((g.vw, g.vh))
            g.screen = g.view_surf
        # THE CAMERA FOLLOWS THE MAN BEING WATCHED, NOT THE PLAYER.
        # (Only outdoors: a room sets its own camera from its own size.)
        #
        # It followed player.x/player.y, and watching had been implemented by
        # MOVING THE PLAYER onto the watched man every frame -- so the player
        # was dragged about the world with the camera tied to him, and the man
        # being watched was only ever in shot because the player had been
        # teleported onto his head. The player is PARKED where he stands; the
        # camera is the thing that moves.
        g._look = g.observer_.target
        if g._inside_now:
            pass                      # the room's own branch sets the camera
        elif g.field_design:
            # SETTLEMENT MODE: the player is parked; the camera pans freely.
            _ks = pygame.key.get_pressed()
            _dx = (1 if (_ks[pygame.K_d] or _ks[pygame.K_RIGHT]) else 0) \
                - (1 if (_ks[pygame.K_a] or _ks[pygame.K_LEFT]) else 0)
            _dy = (1 if (_ks[pygame.K_s] or _ks[pygame.K_DOWN]) else 0) \
                - (1 if (_ks[pygame.K_w] or _ks[pygame.K_UP]) else 0)
            _sp = 900.0 * g.dt * (ZOOM / g.zoom)
            g.cam_x += _dx * _sp
            g.cam_y += _dy * _sp
        elif g._look is not None and getattr(g._look, "alive", False):
            g.cam_x = g._look.x - g.vw / 2.0
            g.cam_y = g._look.y - g.vh / 2.0
        else:
            g.cam_x = g.player.x - g.vw / 2.0
            g.cam_y = g.player.y - g.vh / 2.0
        # HE STANDS AT THE PLAYER'S SHOULDER, EVERY FRAME, AWAKE, ALIVE. The pin
        # and the `_TRUTH` hand-off belong HERE, outside the camera branch --
        # and `asleep` must be cleared, because an NPC is born asleep at night
        # and the draw pass used to skip a sleeping man.
        if g._truth is not None:
            # HE DOES NOT FOLLOW. He was pinned to the player's shoulder every
            # frame, so he slid along the road beside him -- "fixed to where I
            # move" instead of a man standing in one place. He is placed ONCE,
            # at the spot he was born on, and held there like a post.
            g._truth.x = g._truth_home[0]
            g._truth.y = g._truth_home[1]
            g._truth.asleep = False
            g._truth.in_interior = False
            g._truth.alive = True
            g._truth.health = g._truth.max_health
            g._truth.pause = 1.0
            g._TRUTH[0] = g._truth
        # THE WORLD IS NOT DRAWN WHILE HE IS INDOORS OR UNDERGROUND. This call
        # painted the wilderness over the room's frame -- which is why entering
        # the barn showed the middle of the map instead of the hall.
        if not g._inside_now:
            g.draw_exterior(g.cam_x, g.cam_y, True)
            comm.draw_clouds(g.screen, g.cam_x, g.cam_y)
        try:
            # HIS OWN BENCHES, FORGES AND SHAFTS. A village's workplaces are
            # part of its ground; his are his, and have to be drawn.
            for _wp in (() if g._inside_now else g.placed_work):
                _wp.draw(g.screen, g.cam_x, g.cam_y)
            # HIS PLOTS ARE ALWAYS MARKED, and while the build menu is open or
            # he is placing something they are LIT -- so he can see the ground
            # he has already staked before he stakes more.
            g._lit = g.build_menu_open or g.placing is not None
            for _r in (() if g._inside_now else g.built_plots):
                g._sr = pygame.Rect(int(_r.x - g.cam_x), int(_r.y - g.cam_y),
                                  _r.w, _r.h)
                if g._lit:
                    g._glow = pygame.Surface((max(1, g._sr.w), max(1, g._sr.h)),
                                           pygame.SRCALPHA)
                    g._glow.fill((248, 206, 96, 54))
                    g.screen.blit(g._glow, g._sr.topleft)
                    pygame.draw.rect(g.screen, (250, 214, 110), g._sr, 3)
                else:
                    pygame.draw.rect(g.screen, (92, 72, 42), g._sr, 2)
        except Exception:
            pass
        try:
            if not g._inside_now:
                g.hub_world.draw(g.screen, g.cam_x, g.cam_y, g.vw, g.vh)
        except Exception:
            pass
        if not g._inside_now:
            g.draw_news(g.screen, g.cam_x, g.cam_y, g.vw, g.vh)   # the bubble, over his head
        g.draw_villages = g.villages.visible(g.cam_x, g.cam_y, g.vw, g.vh,
                                         extra=g.hub_world.hubs)
        # THE BAR UNDER THE GUARD, for the man HE is searching -- ten seconds
        # on the same bar the axe swing uses.
        for _v2 in (() if g._inside_now else g.draw_villages):
            g._sq = getattr(_v2, "search_now", None)
            if g._sq is None:
                continue
            for _g3 in (getattr(_v2, "patrol", ()) or ()):
                Player._draw_action_bar(
                    g.screen, _g3.x - g.cam_x, _g3.y - g.cam_y,
                    min(1.0, float(getattr(_v2, "search_t", 0.0)) / 10.0))
                break

        g.draw_trees = g.trees.visible(g.cam_x, g.cam_y, g.vw, g.vh)
        # ---- THE GATE ------------------------------------------------------
        # Everything about it lives in gate.py now: close -> he comes to you ->
        # ten seconds, bar under him -> one roll -> aggro or through. This block
        # only reports what the module decided.
        try:
            import gate as gate_mod
            # A MAN RIDING THE TRAIN IS NOT AT A GATE. No guard steps up to
            # him, nobody searches him, nobody shouts.
            _res = (None if (g._inside_now or getattr(g.player, "aboard", False))
                    else gate_mod.tick(g.dt, g.player, g.villages.villages, g.inventory))
            if _res is not None:
                _kind, g._town, g._units = _res
                plog.log("SEARCHED", _kind, "units", g._units,
                         "town", getattr(g._town, "name", "?"))
                if _kind == "caught":
                    # HE MAKES SPACE, THEN SHOOTS: the toast is the player
                    # being told, and the town only erupts when the round goes.
                    g.toast("Searched. %d found. Run." % g._units)
                    nemesis.note_caught(g.player, g._town, g._units)
                    gate_mod.begin_caught(g.player, g._town, g._units)
                elif _kind == "fled":
                    g.toast("You broke away from the guard. He shouts.")
                    g.commit_crime(g._town)
                elif g._units > 0:
                    g.toast("Searched clean   (smuggling %.1f)" % g.player.smuggling)
                else:
                    g.toast("Searched and waved through")
            if gate_mod.tick_caught(g.dt, g.player) == "shot":
                gate_mod.fire_shot(g.player, g.combat)
                g.commit_crime(g._town)
                gate_mod.caught_over()
            g._pg = gate_mod.progress()
            if g._pg > 0.0 and gate_mod.guard_of() is not None:
                g._gg = gate_mod.guard_of()
                Player._draw_action_bar(g.screen, g._gg.x - g.cam_x, g._gg.y - g.cam_y, g._pg)
        except Exception:
            import traceback as _tb
            _tb.print_exc()

        # CROSSING A WALL WITHOUT BEING WAVED THROUGH IS AGGRO -- and the crime
        # is the CROSSING, not standing inside. This read "he is inside the
        # fence and not waved by", so a game that now BEGINS in a square
        # convicted the player on his first frame: every armed man in the town
        # was aggro before he had taken a step. A man who wakes up inside is
        # inside; a man who steps over the line without a pass is a criminal.
        try:
            g._here = None
            for _v in g.villages.villages:
                g._fr = getattr(_v, "fence_rect", None)
                if g._fr is None or getattr(_v, "is_hub", False):
                    continue
                if g._fr.collidepoint(g.player.x, g.player.y):
                    g._here = _v
                    break
            g._was = getattr(g.player, "was_inside_v", None)
            g.player.was_inside_v = g._here
            if g._here is None:
                # A PASS LASTS WHILE HE IS AT THE GATE. Clearing it the moment
                # he stepped outside the wall searched him again on the way
                # back in, and again -- three times a minute at one gate. The
                # guard remembers him until he has actually GONE AWAY: out of
                # the town's reach, when he is a stranger again.
                g._pass = g._was or getattr(g.player, "waved_by", None)
                if g._pass is not None and gate.pass_expired(g.player, g._pass):
                    g.player.waved_by = None
                    g.player.aggro_village = None
            elif g._here is not g._was:
                if getattr(g.player, "waved_by", None) is not g._here:
                    if getattr(g.player, "aggro_village", None) is not g._here:
                        g.player.aggro_village = g._here
                        g.toast("You crossed the wall unsearched. The street turns.")
                        g.commit_crime(g._here)
        except Exception:
            pass

        # Houses and tree trunks block line of sight; canopies soften it.
        g.reach = g.vision.max_dist
        g.occluders = [house.sight_rect for village in g.draw_villages
                     for house in village.houses
                     if (house.x - g.player.x) ** 2 + (house.y - g.player.y) ** 2
                     < (g.reach + max(house.w, house.h)) ** 2]
        g.occluders += [house.sight_rect for house in g.built_houses
                      if (house.x - g.player.x) ** 2 + (house.y - g.player.y) ** 2
                      < (g.reach + max(house.w, house.h)) ** 2]
        # Placed planks block sight like tree trunks.
        for (_tx, _ty) in getattr(g, "built_blocks", {}):
            _br = pygame.Rect(_tx * TILE, _ty * TILE, TILE, TILE)
            if _br.colliderect(pygame.Rect(g.player.x - g.reach, g.player.y - g.reach,
                                           g.reach * 2, g.reach * 2)):
                g.occluders.append(_br)
        g.near_trees = sorted(g.draw_trees,
                            key=lambda t: (t.x - g.player.x) ** 2 + (t.y - g.player.y) ** 2)
        g.soft: list[pygame.Rect] = []
        for i, tree in enumerate(g.near_trees[:80]):
            if tree.felled:
                continue
            if ((tree.x - g.player.x) ** 2 + (tree.y - g.player.y) ** 2
                    > (g.reach + tree.canopy_r) ** 2):
                continue
            if i < 45:
                g.occluders.append(tree.trunk_rect)
            r = tree.canopy_r
            g.soft.append(pygame.Rect(tree.x - r, tree.y - r, r * 2, r * 2))

        g.screen_occluders = [pygame.Rect(r.x - g.cam_x, r.y - g.cam_y, r.w, r.h)
                            for r in g.occluders]
        g.screen_soft = [pygame.Rect(r.x - g.cam_x, r.y - g.cam_y, r.w, r.h)
                       for r in g.soft]

        # THE EYES BELONG TO THE MAN BEING WATCHED.
        #
        # This cast the mask from player.x/player.y, so with the camera sixty
        # thousand pixels away on somebody else the cone lit a place that was
        # not on screen and everything else was black -- which is what the
        # black screen was. A watcher also sees the WHOLE scene rather than one
        # man's 175 degrees: that is what watching is for.
        g._wt = g.observer_.target
        g._watch = g._wt is not None and getattr(g._wt, "alive", False)
        g._src = g._wt if g._watch else g.player
        if g._watch:
            g._ang = math.atan2(g._src.facing[1], g._src.facing[0])  # NPC has no
        else:                                                  # facing_angle
            g._ang = g.player.facing_angle
        g.eye_x = g._src.x - g.cam_x + g._src.facing[0] * 5.0
        g.eye_y = g._src.y - g.cam_y + g._src.facing[1] * 5.0
        g.foliage = g.trees.foliage(g._src.x, g._src.y)
        g._cone0 = g.vision.cone_deg
        if g._watch or g.field_design:
            g.vision.cone_deg = 360.0
        # SETTLEMENT VIEW IS LIT FROM ABOVE: no first-person cone, no night,
        # the whole visible world (plus the pan's edge) rendered plain.
        if not g.field_design:
            g.mask = g.vision.build(g.vw, g.vh, g.eye_x, g.eye_y, g._ang,
                                g.screen_occluders, g.screen_soft, 1.0 - 0.25 * g.foliage)
            g.screen.blit(g.mask, (0, 0))
        if g._watch or g.field_design:
            g.vision.cone_deg = g._cone0
        if not g.field_design:
            g.draw_night()

        g.selected = g.inventory.selected_stack()
        g._sel0 = g.inventory.selected_stack()      # never rely on a name that a
        # branch may not have assigned: `selected` was unbound on the frames the
        # player was not inside a house, and this is the line that draws him.
        if not getattr(g.player, "aboard", False):
            g.player.draw(g.screen, g.cam_x, g.cam_y, g._sel0.defn.id if g._sel0 else None)
        g.combat.draw(g.screen, g.cam_x, g.cam_y)
        g.draw_hunger_gray()

        if g.game_over:
            # THE WINDOW IS THE WINDOW. While the world is drawn, the name
            # `screen` points at the small offscreen view surface, and the two
            # lines that put it back -- and upscale the world into it -- live in
            # the else-branch below. Dying skipped them, so the game-over panel
            # was painted onto a surface nothing ever showed while the window
            # kept the last frame it had. That is what "it freezes instead of
            # showing a game over screen" was: a correct panel, drawn offscreen.
            g.screen = g.real_screen
            if g.inside_mine is None:
                _present(g.screen, g.view_surf, g.scr_w, g.scr_h)
            g.overlay.draw(g.screen, [
                f"Kills: {g.kills}",
                f"Tobacco: {g.inventory.count_of('tobacco')}",
                f"Seeds: {g.inventory.count_of('seed_bag')}",
            ])
        else:
            if not g.player.dead:
                g.damage = 1.0 - g.player.health / g.player.max_health
                g.vignette.draw(g.screen, g.damage, g.now, g.player.hit_flash / 0.15)

            g.eye_world_x = g.player.x + g.player.facing[0] * 5.0
            g.eye_world_y = g.player.y + g.player.facing[1] * 5.0
            for enemy in g.enemies:
                g.ex, g.ey = enemy.x - g.cam_x, enemy.y - g.cam_y
                if g.ex < -24 or g.ey < -24 or g.ex > g.vw + 24 or g.ey > g.vh + 24:
                    continue
                if not g.vision.is_visible(g.eye_world_x, g.eye_world_y, g.player.facing_angle,
                                         enemy.x, enemy.y, occluders=g.occluders):
                    draw_alert(g.screen, g.ex, g.ey, g.now, enemy.phase)

            g.draw_placing()
            try:
                g.draw_field_design()
            except Exception:
                pass

            if not g.inventory_open:
                draw_crosshair(g.screen, g.wmouse_x, g.wmouse_y)

            # ---- ...and back to the window ---------------------------------
            g.screen = g.real_screen
            if g.inside_mine is None:
                _present(g.screen, g.view_surf, g.scr_w, g.scr_h)
            g.vw, g.vh = g.scr_w, g.scr_h
            if g.comm_mode:
                comm.draw_bar(g.screen, g.font, g.vw, g.vh, g.comm)
            else:
                g.hotbar.draw(g.screen)
            # THE INSPECTOR IS DRAWN ABOVE GROUND TOO.
            #
            # observer_.draw() lived ONLY inside the MINE's render block, so
            # above ground the panel opened -- your key log shows observer=True
            # six times -- and not one pixel was painted. It is drawn here, on
            # the real screen, after the world has been scaled up, because
            # Observer.draw works in window coordinates.
            #
            # And it is checked by PIXELS now. For hours I verified this by
            # reading observer.open, which was True the whole time, and told
            # you it worked three times on that basis. State is not a picture.
            g.observer_.draw(g.screen)
            g.hotbar.draw_stamina(g.screen, g.player.stamina / g.player.max_stamina,
                                g.player.exhausted)
            g.hotbar.draw_hunger(g.screen, g.player.hunger / g.player.max_hunger)

            if g.toast_time > 0.0:
                g.toast_time = max(0.0, g.toast_time - g.dt)
                g.fade = min(1.0, g.toast_time / 0.5)
                g.label = g.font.render(g.toast_text, True, TOAST_COLOR)
                g.label.set_alpha(int(255 * g.fade))
                g.plate = pygame.Surface((g.label.get_width() + 22, 26), pygame.SRCALPHA)
                pygame.draw.rect(g.plate, (18, 18, 22, 200), g.plate.get_rect(), border_radius=6)
                g.plate.set_alpha(int(255 * g.fade))
                g.px = g.vw // 2 - g.label.get_width() // 2
                g.py = int(g.vh * 0.68)
                g.screen.blit(g.plate, (g.px - 11, g.py - 3))
                g.screen.blit(g.label, (g.px, g.py))
            if g.smith_open and g.smith_shop is not None:
                g._w = g.smith_shop.worker
                g._orders = list(getattr(g._w, "tool_orders", ()) or ())
                _r = pygame.Rect(g.vw // 2 - 220, g.vh // 2 - 150, 440, 300)
                g._shade = pygame.Surface((g.vw, g.vh), pygame.SRCALPHA)
                g._shade.fill((0, 0, 0, 170))
                g.screen.blit(g._shade, (0, 0))
                pygame.draw.rect(g.screen, (26, 26, 30), _r, border_radius=10)
                pygame.draw.rect(g.screen, (150, 118, 78), _r, 2, border_radius=10)
                g._titles = {"smith": "THE FORGE", "mine": "THE PIT HEAD",
                           "lab": "THE LABORATORY", "brewery": "THE BREWHOUSE"}
                g.screen.blit(g.font.render(
                    "%s   -   %s's" % (g._titles.get(g._w.kind if g._w else "", "THE BENCH"),
                                       g.smith_shop.worker.village.name
                                       if g.smith_shop.worker else "the village"),
                    True, (238, 224, 190)), (_r.x + 14, _r.y + 12))
                g.screen.blit(g.font.render("iron in stock: %d"
                                        % int(getattr(g._w, "stock", {}).get("iron", 0)),
                                        True, (232, 200, 118)), (_r.x + 14, _r.y + 38))
                g._y = _r.y + 66
                if not g._orders:
                    g.screen.blit(g.font.render("nothing booked", True, (150, 146, 138)),
                                (_r.x + 14, g._y))
                for _who, _want in g._orders[:9]:
                    _t = "%s wants a %s" % (getattr(_who, "name", "someone"), _want)
                    g.screen.blit(g.font.render(_t, True, (216, 212, 200)), (_r.x + 14, g._y))
                    g._y += 22
                if g._w is not None:
                    g._held = {k: int(v) for k, v in getattr(g._w, "stock", {}).items()
                             if k in ("axe", "shovel", "pickaxe") and v}
                    if g._held:
                        g.screen.blit(g.font.render("on the shelf: " + ", ".join(
                            "%d %s" % (q, i) for i, q in g._held.items()), True,
                            (200, 200, 190)), (_r.x + 14, _r.bottom - 44))
                _kind = g.smith_shop.kind
                g._hint = {"smith": "[Space] forge a tool",
                         "mine": "[Space] break out iron",
                         "lab": "[Space] work the leaf",
                         "brewery": ("[Space] draw the brew"
                                     if getattr(g.player, "brew", None) is not None
                                     else "[Space] start a mash")}.get(_kind, "")
                g.screen.blit(g.font.render("%s      [E] close   " % g._hint,
                                        True, (196, 226, 168)),
                            (_r.x + 14, _r.bottom - 24))
                if g.work_msg:
                    g.screen.blit(g.font.render(g.work_msg, True, (240, 206, 130)),
                                (_r.x + 14, _r.bottom - 46))
            if g.board_open and g.board_village is not None:
                g.board_panel.player = g.player
                g.board_panel.town_api = g._BOARD_API if g._W_ON else None
                if g._W_ON:
                    g._WORK.watch(g.board_panel._nearest(g.board_village, 3))
                g.board_panel.inv = g.inventory
                g.board_panel.chest = (g.inside_house.interior.chest
                                     if g.inside_house is not None
                                     else (g.built_houses[0].interior.chest
                                           if g.built_houses
                                           and g.built_houses[0].interior else None))
                g.board_panel.tax_day = int(g.now / DAY_LENGTH)
                g.board_panel.notice_t = max(0.0, g.board_panel.notice_t - g.dt)
                g.board_panel.draw(g.screen, g.board_village)
            g.draw_speed_button()

        if g.trade_open:
            g.trade_menu.draw(g.screen)
        if g.build_menu_open:
            g.build_menu.draw(g.screen)
        # THE CONVERSATION. It was drawn ONLY inside the house branch, so
        # outdoors it opened and was never painted -- a click that changed the
        # state and showed nothing. Every other panel is drawn here, in the
        # frame the player is actually looking at.
        if g.dialogue_panel.open_:
            g.dialogue_panel.draw(g.screen)
        if g.inventory_open:
            g.panel.draw(g.screen)
        if g.confirm_open:
            g.confirm.draw(g.screen)
        # THE CONTAINERS AND THE DEAD MAN'S MAIL, OUTDOORS. Every one of these
        # was drawn only inside the house branch, so above ground a chest, a
        # hired man's pack, a stall, a body or a folder opened to a state
        # change and NOTHING ON SCREEN.
        if g.chest_open:
            g.chest_panel.draw(g.screen)
        if g.worker_panel_open:
            g.worker_panel.draw(g.screen)
        if g.stall_open:
            g.stall_panel.draw(g.screen)
        if g.body_open:
            g.body_panel.draw(g.screen)
        if g.folder_open:
            g.folder_panel.draw(g.screen)
        if g.compass_open:
            g.compass_menu.draw(g.screen)
        if g.pause_open:
            g.pause_menu.draw(g.screen)
        if g.map_open:
            try:
                g._wh2 = 0
                for _e in pygame.event.get(pygame.MOUSEWHEEL):
                    g._wh2 += _e.y
                mapmod.handle_input(g.dt, g.player, wheel=g._wh2)
                mapmod.draw(g.screen, g.world, g.player, g._nearest_town(),
                            g.hub_world.hubs,
                            settlements=list(g.villages.villages),
                            natives=list(getattr(g, "native_settlements", {}).values()))
            except Exception:
                pass

        # ---- THE PLAYER TRACE, EVERY FRAME ------------------------------
        try:
            g._ks = pygame.key.get_pressed()
            _b = (1 if g._ks[pygame.K_w] or g._ks[pygame.K_UP] else 0) | \
                 (2 if g._ks[pygame.K_s] or g._ks[pygame.K_DOWN] else 0) | \
                 (4 if g._ks[pygame.K_a] or g._ks[pygame.K_LEFT] else 0) | \
                 (8 if g._ks[pygame.K_d] or g._ks[pygame.K_RIGHT] else 0)
            g._lp = g._lastpt[0]
            g._mv = -1.0 if g._lp is None else ((g.player.x - g._lp[0]) ** 2
                                            + (g.player.y - g._lp[1]) ** 2) ** 0.5
            try:
                g._visn = len(g.visible_villages)
            except Exception:
                g._visn = -1
            g._trace.append((
                "%dms" % int((time.perf_counter() - g._framet0) * 1000.0),
                "br=%s" % g._branch, "dt=%.3f" % g.dt, "key=%d" % _b,
                "mv=%.1f" % g._mv,
                "at=%d,%d" % (int(g.player.x), int(g.player.y)),
                "hp=%d" % int(g.player.health), "dead=%s" % g.player.dead,
                "want=%s" % getattr(g.player, "wanted", False),
                "srch=%.1f" % float(getattr(g.player, "search_progress", 0.0)),
                "sv=%s" % getattr(getattr(g.player, "searched_village", None), "name", "-"),
                "house=%s" % (g._inside_h()),
                "vis=%d" % g._visn, "wanted=%s" % getattr(g.player, "wanted", False),
            ))
            g._lastpt[0] = (g.player.x, g.player.y)
            if _b and g._mv >= 0.0 and g._mv < 0.6:
                g._still += 1
            else:
                g._still = 0
            if g._still == 40:
                g._dump_trace("STUCK: %d frames with a movement key held and no movement"
                            % g._still)
        except Exception:
            pass

        # ---- THE SLOW-FRAME RECORD -------------------------------------
        # If this frame took more than a quarter of a second, say so, with the
        # breakdown and the one number that matters -- how many towns were being
        # simulated at the time. A freeze is a frame that never ends, and now it
        # leaves a receipt.
        try:
            g._fend = time.perf_counter()
            g._fms = (g._fend - g._framet0) * 1000.0
            if g._fms > 250.0:
                g._vis_n = 0
                try:
                    g._vis_n = len(g.visible_villages)
                except Exception:
                    g._vis_n = -1
                g._ng = -1
                try:
                    g._ng = int(min(abs(v.x - g.player.x) + abs(v.y - g.player.y)
                                  for v in g.villages.villages))
                except Exception:
                    pass
                plog.log("SLOWFRAME", "%dms" % int(g._fms),
                         "towns %dms" % int((g._pt1 - g._framet0) * 1000.0),
                         "men %dms" % int((g._pt2 - g._pt1) * 1000.0),
                         "rest %dms" % int((g._pt3 - g._pt2) * 1000.0),
                         "draw %dms" % int((g._fend - g._pt3) * 1000.0),
                         "visible_towns", g._vis_n,
                         "nearest_town_px", g._ng,
                         "at", "%d,%d" % (int(g.player.x), int(g.player.y)),
                         "dead", g.player.dead)
                g._dump_trace("SLOW FRAME %dms" % int(g._fms))
        except Exception:
            pass
        pygame.display.flip()
