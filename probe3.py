"""CALL _work_woods DIRECTLY AND SEE WHAT IT ACTUALLY DOES."""
import os, sys, time, threading, math
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((128,96),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, economy, nemesis, main, menu
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is None: continue
            if getattr(p,"dead",False): p.respawn()
            p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
class FakeWorld: pass
def probe():
    time.sleep(70)
    o=[]
    try:
        w=nemesis.WORLD; nm=w.active if w else None
        n=nm.npc
        o.append("nemesis %s  job=%r farm_plot=%r" % (n.name, n.job, n.farm_plot))
        fw=FakeWorld(); fw.trees=village._FOREST
        o.append("village._FOREST is %s" % ("set" if village._FOREST else "NONE"))
        lot=n.village.woodlot()
        o.append("woodlot(): %d trees, %d standing" % (len(lot), sum(1 for t in lot if not t.felled)))
        t=n._find_tree(n.village)
        o.append("_find_tree -> %s" % ("a tree %.0f px away" % math.hypot(t.x-n.x,t.y-n.y) if t else "None"))
        o.append("axe before %.3f   chop_timer %.2f   tool_uses %s  stock axe %s"
                 % (n.skills.axe, getattr(n,'chop_timer',-1), getattr(n,'tool_uses',None), n.stock.get("axe")))
        moved=0
        for i in range(600):
            x0,y0=n.x,n.y
            n._work_woods(0.05, n.village and 0.0 or 0.0, fw) if False else n._work_woods(0.05, 0.0, fw)
            if abs(n.x-x0)+abs(n.y-y0) > 0.01: moved+=1
        t2=n._find_tree(n.village)
        o.append("after 600 calls of _work_woods(0.05)  (=30 s of game time):")
        o.append("   axe %.3f   chop_timer %.2f   frames he MOVED: %d/600"
                 % (n.skills.axe, getattr(n,'chop_timer',-1), moved))
        o.append("   distance to nearest tree now: %s"
                 % ("%.0f px" % math.hypot(t2.x-n.x,t2.y-n.y) if t2 else "None"))
        o.append("   wood in his pack: %s" % n.stock.get("wood"))
    except Exception as e:
        import traceback; o.append(traceback.format_exc()[-1200:])
    open("/tmp/probe3.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
