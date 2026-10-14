"""THE PER-MAN COST, MEASURED AND DISASSEMBLED."""
import os, sys, time, threading, dis, io, collections
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

def bc(fn, name):
    """Bytecode instruction count and attribute traffic for one function."""
    try:
        f=getattr(fn,"__func__",fn)
        code=getattr(f,"__code__",None)
        if code is None: return "%s: no bytecode (compiled C)" % name
        ins=list(dis.get_instructions(code))
        c=collections.Counter(i.opname for i in ins)
        return ("%-22s %5d instructions   LOAD_ATTR %3d   STORE_ATTR %2d   calls %3d"
                % (name, len(ins), c["LOAD_ATTR"]+c["LOAD_METHOD"],
                   c["STORE_ATTR"], c["CALL"]+c["CALL_FUNCTION"]+c["CALL_METHOD"]))
    except Exception as e:
        return "%s: %r" % (name, e)

def probe():
    time.sleep(110)
    o=[]
    alive=[n for n in village.PEOPLE if getattr(n,"alive",True)]
    n0=alive[0]
    o.append("=== BYTECODE: what ONE man's step is made of ===")
    o.append(bc(village.NPC.tick, "NPC.tick"))
    o.append(bc(village.NPC.update, "NPC.update"))
    o.append(bc(economy.needs, "economy.needs"))
    o.append(bc(village.NPC._step_toward, "_step_toward"))
    o.append(bc(village.NPC._work_field, "_work_field"))
    o.append(bc(village.NPC._work_woods, "_work_woods"))
    o.append(bc(village.NPC._mosey, "_mosey"))
    o.append(bc(village.NPC._seek_goods, "_seek_goods"))
    o.append(bc(village.NPC._fight, "_fight"))
    o.append(bc(economy.grow_opinion, "grow_opinion"))
    o.append(bc(economy.regard, "regard"))
    o.append(bc(economy.house_wood, "house_wood"))
    o.append(bc(economy.food_of, "food_of"))
    o.append(bc(economy.surplus, "surplus"))
    o.append(bc(economy.wants, "wants"))
    # timing: how long does one man cost?
    import random
    combat=None; colliders=None; world=None
    for n in alive:
        v=getattr(n,"village",None)
        if v is not None and getattr(v,"_world",None) is not None: world=v._world; break
    t=time.perf_counter(); N=3000
    try:
        for i in range(N):
            m=alive[i % len(alive)]
            m.tick(0.05, world, 100.0, "home", combat, False, colliders, None)
        per=(time.perf_counter()-t)/N*1e6
        o.append("")
        o.append("=== TIME: one full NPC.tick = %.1f us   (x1043 men x20 Hz = %.1f ms/frame)"
                 % (per, per*1043*20/1000.0))
    except Exception as e:
        o.append("timing failed: %r" % (e,))
    t=time.perf_counter(); N=5000
    try:
        for i in range(N):
            economy.needs(alive[i % len(alive)], 0.05)
        per2=(time.perf_counter()-t)/N*1e6
        o.append("        economy.needs alone  = %.2f us" % per2)
    except Exception as e:
        o.append("needs timing failed: %r" % (e,))
    t=time.perf_counter()
    for i in range(5000):
        n=alive[i % len(alive)]
        n.skills.gain_movement(0.8)
    o.append("        gain_movement alone  = %.2f us" % ((time.perf_counter()-t)/5000*1e6))
    o.append("        men alive            = %d" % len(alive))
    open("/tmp/permen.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
main.WIDTH=320; main.HEIGHT=240
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
