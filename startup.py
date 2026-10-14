"""TIME EVERY PHASE OF STARTUP, so the 2-second hitch names itself."""
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
main.WIDTH=320; main.HEIGHT=240
LOG=[]
def wrap(mod, name, label):
    f=getattr(mod, name, None)
    if f is None: return
    def g(*a, **k):
        t=time.perf_counter(); r=f(*a,**k); d=(time.perf_counter()-t)*1000
        LOG.append("%-28s %8.1f ms" % (label, d))
        return r
    try: setattr(mod, name, g); LOG.append("(wrapped %s)" % label)
    except Exception as e: LOG.append("(cannot wrap %s: %r)" % (label, e))
wrap(main, "load_world", "load_world (the loading screen)")
wrap(main, "save_cached_world", "save_cached_world (pickle!)")
wrap(village, "rebuild_people", "rebuild_people")
wrap(main, "rebuild_people", "rebuild_people(main)")
for nm in ("set_plot", "plot_at"):
    pass
S={"f":0,"t0":None,"last":None}
_f=pygame.display.flip
def flip():
    S["f"]+=1
    now=time.perf_counter()
    if S["t0"] is None: S["t0"]=now
    if S["last"] is not None:
        d=(now-S["last"])*1000
        if d > 60: LOG.append("  FRAME %5d took %8.1f ms  (t+%.1fs)" % (S["f"], d, now-S["t0"]))
    S["last"]=now
    if S["f"]==400:
        open("/tmp/startup.out","w").write("\n".join(LOG)); os._exit(0)
    _f()
pygame.display.flip=flip
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None:
                if getattr(p,"dead",False): p.respawn()
                p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
threading.Thread(target=keeper,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
