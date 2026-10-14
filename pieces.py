"""EVERY PIECE OF THE 22.7 MICROSECONDS, TIMED ONE AT A TIME."""
import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((320,240),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, economy, main, menu
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None:
                if getattr(p,"dead",False): p.respawn()
                p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass

def timeit(label, fn, n, warm=50):
    try:
        for _ in range(warm): fn()
    except Exception as e:
        return "  %-28s FAILED %r" % (label, e)
    t=time.perf_counter()
    for _ in range(n):
        try: fn()
        except Exception: pass
    return "  %-28s %8.3f us   (x1043 x20Hz = %6.1f ms/s)" % (
        label, (time.perf_counter()-t)/n*1e6, (time.perf_counter()-t)/n*1e6*1043*20/1000.0)

def probe():
    time.sleep(115)
    o=[]
    alive=[n for n in village.PEOPLE if getattr(n,"alive",True)]
    import wildcrop
    world=getattr(wildcrop,"_WORLD",None)
    n0=alive[0] if alive else None
    if n0 is None or world is None:
        open("/tmp/pieces.out","w").write("no world reachable"); os._exit(0)
    home=n0.village
    other=next((x for x in home.npcs if x is not n0 and x.alive), n0)
    o.append("man: %s of %s     men alive: %d" % (n0.name, home.name, len(alive)))
    o.append("")
    o.append("=== THE WHOLE STEP ===")
    o.append(timeit("NPC.tick (full)", lambda: n0.tick(0.05, world, 100.0, "home", None, False, (), None), 2000))
    o.append(timeit("NPC.update (full)", lambda: n0.update(0.05, None, None, None, False, world, 100.0, "home"), 2000))
    o.append("")
    o.append("=== THE PIECES NPC.tick CALLS ===")
    o.append(timeit("economy.needs", lambda: economy.needs(n0, 0.05), 8000))
    o.append(timeit("economy.dole (if it fires)", lambda: economy.dole(home, n0), 3000))
    o.append(timeit("economy.place_orders", lambda: economy.place_orders(home, n0), 3000))
    o.append(timeit("economy.tool_loan", lambda: economy.tool_loan(home, n0), 3000))
    o.append(timeit("economy.forge_loan", lambda: economy.forge_loan(home, n0), 3000))
    o.append(timeit("economy.service_loan", lambda: economy.service_loan(home, n0), 3000))
    o.append(timeit("economy.pair_trade", lambda: economy.pair_trade(home, n0, other), 2000))
    o.append(timeit("economy.grow_opinion", lambda: economy.grow_opinion(n0, other), 5000))
    o.append(timeit("npc._pair_off", lambda: n0._pair_off(), 3000))
    o.append(timeit("npc._passer_by", lambda: n0._passer_by(), 3000))
    o.append(timeit("npc._seek_goods", lambda: n0._seek_goods(0.05), 3000))
    o.append(timeit("npc._step_toward", lambda: n0._step_toward(home.x, home.y, 0.05), 3000))
    o.append(timeit("npc._work_field", lambda: n0._work_field(0.05, world, 100.0), 2000))
    o.append(timeit("npc._work_woods", lambda: n0._work_woods(0.05, 100.0, world), 2000))
    o.append(timeit("npc._mosey", lambda: n0._mosey(0.05), 3000))
    o.append(timeit("npc._fight", lambda: n0._fight(0.05, other, None), 2000))
    o.append(timeit("skills.gain_movement", lambda: n0.skills.gain_movement(0.8), 8000))
    o.append(timeit("skills.gain_axe", lambda: n0.skills.gain_axe(), 8000))
    o.append(timeit("skills.gain_farming", lambda: n0.skills.gain_farming(0.02), 8000))
    o.append("")
    o.append("=== THE SMALL READERS ===")
    o.append(timeit("economy.food_of", lambda: economy.food_of(n0), 8000))
    o.append(timeit("economy.house_wood", lambda: economy.house_wood(n0.home_house), 8000))
    o.append(timeit("economy.surplus", lambda: economy.surplus(n0, "bread"), 8000))
    o.append(timeit("economy.wants", lambda: economy.wants(n0, "bread"), 8000))
    o.append(timeit("economy.urgency", lambda: economy.urgency(n0, "bread"), 8000))
    o.append(timeit("economy.store_add", lambda: economy.store_add(home, "wood", 1), 8000))
    o.append(timeit("economy.store_take", lambda: economy.store_take(home, "wood", 1), 8000))
    o.append(timeit("npc.occupation()", lambda: n0.occupation(), 8000))
    o.append(timeit("economy._note (a log line!)", lambda: economy._note("probe"), 3000))
    open("/tmp/pieces.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
main.WIDTH=320; main.HEIGHT=240
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
