"""ARE THE FARMERS ARMED, AND IS ANYTHING GROWING?"""
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
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is None: continue
            if getattr(p,"dead",False): p.respawn()
            p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def probe():
    time.sleep(75)
    try:
        alive=[n for n in village.PEOPLE if getattr(n,"alive",True)]
        farmers=[n for n in alive if getattr(n,"farm_plot",None) is not None]
        armed=[n for n in farmers if getattr(n,"tool_uses",0)>0 or n.stock.get("shovel",0)>0]
        states=collections.Counter()
        seen=set()
        for n in farmers:
            v=n.village
            if v is None or id(v) in seen: continue
            seen.add(id(v))
            for c in v.farm_plots:
                for t in v.farm_tiles.get((c[0],c[1]),()):
                    p=v.__dict__.get("_w")
                    pl=n.village.registry if False else None
        # plot states straight off the world
        world=None
        for n in alive:
            if getattr(n,"village",None) is not None:
                world=getattr(n.village,"_world",None); break
        o=["alive %d   farmers %d   WITH A SHOVEL %d (%.0f%%)"
           % (len(alive), len(farmers), len(armed), 100.0*len(armed)/max(1,len(farmers)))]
        # granary food right now
        g=0; em=0; tn=0
        seen=set()
        for n in alive:
            v=n.village
            if v is None or id(v) in seen: continue
            seen.add(id(v)); tn+=1
            f=sum(int(v.ledger_goods.get(x,0)) for x in economy.FOOD)
            g+=f
            if f<=0: em+=1
        pk=sum(int(n.stock.get(x,0)) for n in alive for x in economy.FOOD)
        o.append("granary %d   packs %d   TOTAL %d   (%d of %d towns empty)"
                 % (g,pk,g+pk,em,tn))
        # what state are the field tiles in?
        import crop as _c
        cnt=collections.Counter()
        if world is not None:
            for n in alive:
                v=n.village
                if v is None: continue
                for c in v.farm_plots:
                    for t in v.farm_tiles.get((c[0],c[1]),()):
                        pl=world.plot_at(t[0],t[1])
                        cnt[pl.kind if pl else "none"]+=1
        o.append("field tiles: " + ", ".join("%s=%d"%(k,v) for k,v in cnt.most_common(8)))
        open("/tmp/shovel.out","w").write("\n".join(o))
    except Exception as e:
        import traceback; open("/tmp/shovel.out","w").write(traceback.format_exc()[-900:])
    os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
