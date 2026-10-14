"""DID ANYBODY PRODUCE ANY WOOD? Measured at the exact line that makes it."""
import os, sys, time, threading, collections
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((128,96),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, economy, main, menu

S=collections.Counter()
SAMPLES=[]
_cw=economy.cut_wood
def cut_wood(v, npc, amount):
    before = npc.stock.get("wood", 0)
    r = _cw(v, npc, amount)
    after = npc.stock.get("wood", 0)
    S["calls_through"] += 1
    S["asked"] += amount
    S["landed"] += (after - before)
    S["granary_got"] += int(v.ledger_goods.get("wood", 0))  # crude
    if len(SAMPLES) < 6:
        SAMPLES.append("    cut_wood(%s, %d): npc wood %d -> %d  (+%d)"
                       % (getattr(npc,'job',None), amount, before, after, after-before))
    return r
try:
    economy.cut_wood = cut_wood; S["patched"] = 1
except Exception:
    S["patch_failed"] = 1

def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is None: continue
            if getattr(p,"dead",False): p.respawn()
            p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass

def world_wood():
    alive=[n for n in village.PEOPLE if getattr(n,"alive",True)]
    packs=sum(int(n.stock.get("wood",0)) for n in alive)
    gran=0; seen=set(); burners=0
    for n in alive:
        v=getattr(n,"village",None)
        if v is None or id(v) in seen: continue
        seen.add(id(v)); gran += int(v.ledger_goods.get("wood",0))
    return packs, gran

def probe():
    time.sleep(160)
    o=[]
    o.append("=== cut_wood, instrumented at the line that makes wood ===")
    o.append("  calls that went through it : %d" % S["calls_through"])
    o.append("  wood ASKED for by loggers : %d" % S["asked"])
    o.append("  wood that LANDED in packs : %d" % S["landed"])
    o.append("  samples:"); o += SAMPLES
    p,g = world_wood()
    o.append("=== and in the whole world, right now ===")
    o.append("  wood in packs  : %d" % p)
    o.append("  wood in granaries: %d" % g)
    loggers=[x for x in village.PEOPLE if getattr(x,'job',None)=="logger" and getattr(x,'alive',True)]
    o.append("  loggers alive: %d" % len(loggers))
    if loggers:
        o.append("  their wood: " + ", ".join(str(x.stock.get("wood",0)) for x in loggers[:12]))
        o.append("  their axe skill: " + ", ".join("%.2f"%x.skills.axe for x in loggers[:12]))
    open("/tmp/wood.out","w").write("\n".join(o)); os._exit(0)

threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
