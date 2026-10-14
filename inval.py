"""HOW MANY GROUND TILES ARE THROWN AWAY PER SECOND?"""
import os, sys, time, threading, collections
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((320,240),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
S={"flips":0}
_f=pygame.display.flip
def flip(): S["flips"]+=1; _f()
pygame.display.flip=flip
import village, economy, main, menu
main.WIDTH=320; main.HEIGHT=240
C=collections.Counter()
_iv=None
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None:
                if getattr(p,"dead",False): p.respawn()
                p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def probe():
    time.sleep(60)
    import wildcrop
    g=getattr(getattr(wildcrop,"_WORLD",None),"ground",None)
    if g is None:
        open("/tmp/inval.out","w").write("no ground"); os._exit(0)
    inv=g.invalidate_tile
    def wrapped(tx,ty):
        C["invalidate"]+=1
        return inv(tx,ty)
    try: g.invalidate_tile=wrapped; C["patched"]=1
    except Exception: C["patch_fail"]=1
    f0=S["flips"]; t0=time.time()
    time.sleep(20)
    dt=time.time()-t0; df=S["flips"]-f0
    o=["invalidate_tile calls in %.1fs : %d   (%.0f a second)" % (dt, C["invalidate"], C["invalidate"]/dt),
       "frames rendered in that time     : %d   (%.1f fps)" % (df, df/dt),
       "FARMERS: %d   of %d alive" % (sum(1 for n in village.PEOPLE if getattr(n,"farm_plot",None) is not None and getattr(n,"alive",True)),
                                      sum(1 for n in village.PEOPLE if getattr(n,"alive",True))),
       "LOGGERS: %d" % sum(1 for n in village.PEOPLE if getattr(n,"job",None)=="logger" and getattr(n,"alive",True))]
    open("/tmp/inval.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
