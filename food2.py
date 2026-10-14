"""DID ANYBODY PRODUCE ANY FOOD? Measured at economy.harvest itself."""
import os, sys, time, threading, collections
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((128,96),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, economy, crop, main, menu

S=collections.Counter(); SAMPLES=[]
_h=economy.harvest
def harvest(v, npc, kind, rng):
    before = sum(int(npc.stock.get(f,0)) for f in economy.FOOD)
    gb = int(v.ledger_goods.get("bread",0))+int(v.ledger_goods.get("berries",0))+int(v.ledger_goods.get("cactus_fruit",0))
    r = _h(v, npc, kind, rng)
    after = sum(int(npc.stock.get(f,0)) for f in economy.FOOD)
    ga = int(v.ledger_goods.get("bread",0))+int(v.ledger_goods.get("berries",0))+int(v.ledger_goods.get("cactus_fruit",0))
    S["calls"]+=1
    S["to_pack"] += (after-before); S["to_granary"] += (ga-gb)
    S["kind_"+str(kind)]+=1
    if len(SAMPLES)<8:
        SAMPLES.append("    harvest(%s): pack +%d, granary +%d" % (kind, after-before, ga-gb))
    return r
try: economy.harvest = harvest; S["patched"]=1
except Exception: S["patch_failed"]=1

def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None: p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass

def probe():
    time.sleep(150)
    o=[]
    o.append("=== economy.harvest, instrumented at the line that makes food ===")
    o.append("  harvests that happened : %d" % S["calls"])
    o.append("  food into packs        : %d" % S["to_pack"])
    o.append("  food into granaries    : %d" % S["to_granary"])
    o.append("  by crop: " + ", ".join("%s=%d"%(k[5:],v) for k,v in S.items() if k.startswith("kind_")))
    o += SAMPLES
    alive=[n for n in village.PEOPLE if getattr(n,"alive",True)]
    farmers=[n for n in alive if getattr(n,"farm_plot",None) is not None]
    armed=[n for n in farmers if getattr(n,"tool_uses",0)>0 or n.stock.get("shovel",0)>0]
    o.append("")
    o.append("  alive %d   farmers %d   with a shovel %d" % (len(alive), len(farmers), len(armed)))
    # how many tiles are actually growing anything?
    cnt=collections.Counter(); seen=set()
    for n in farmers:
        v=n.village
        if v is None or id(v) in seen: continue
        seen.add(id(v))
        w=getattr(v,"_world",None)
    o.append("  food in the world now: %d" % sum(int(n.stock.get(f,0)) for n in alive for f in economy.FOOD))
    open("/tmp/food2.out","w").write("\n".join(o)); os._exit(0)

threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
