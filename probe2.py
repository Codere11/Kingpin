"""WHAT IS HE ACTUALLY DOING? (the nemesis, inspected directly)"""
import os, sys, time, threading
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
def probe():
    time.sleep(70)
    o=[]
    try:
        w=nemesis.WORLD
        nm=w.active if w else None
        if nm is None: o.append("no nemesis"); open("/tmp/probe2.out","w").write("\n".join(o)); os._exit(0)
        n=nm.npc
        o.append("NAME %s   town %s   alive %s" % (n.name, nm.town.name, n.alive))
        o.append("  job=%r  farm_plot=%r  workplace=%r  trade_state=%r"
                 % (n.job, n.farm_plot, getattr(n,'workplace',None), getattr(n,'trade_state',None)))
        o.append("  stock axe=%s shovel=%s   tool_uses=%s   coins=%d"
                 % (n.stock.get("axe"), n.stock.get("shovel"), getattr(n,'tool_uses',None), n.coins))
        o.append("  skills axe=%.3f farming=%.3f   rank=%d  days_in_trade=%d"
                 % (n.skills.axe, n.skills.farming, nemesis.rank_of(n), nm.days_in_trade))
        # would _work_woods find a tree?
        world=getattr(village,"WORLD",None)
        o.append("  village.WORLD is %s" % ("set" if world else "NOT SET -- probe cannot see the world"))
        if world is not None:
            forest=getattr(world,"trees",None)
            o.append("  world.trees: %s" % ("set" if forest else "NONE"))
            if forest is not None:
                t=n._find_tree(nm.town, forest)
                o.append("  _find_tree -> %s   (None means no standing tree near home)"
                         % ("a tree at (%.0f,%.0f)"%(t.x,t.y) if t else "None"))
        # who else in his town is a logger, and do THEY have axes?
        logs=[x for x in nm.town.npcs if getattr(x,'job',None)=="logger"]
        o.append("  loggers in his town: %d" % len(logs))
        for x in logs[:4]:
            o.append("     %-18s axe=%s tool_uses=%s farming=%.2f"
                     % (x.name, x.stock.get("axe"), getattr(x,'tool_uses',None), x.skills.farming))
    except Exception as e:
        import traceback; o.append(traceback.format_exc()[-900:])
    open("/tmp/probe2.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
