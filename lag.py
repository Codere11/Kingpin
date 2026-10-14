"""WHERE IS THE FRAME GOING? Counting every suspect from tonight."""
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
import village, economy, nemesis, main, menu
C=collections.Counter()
# 1. is _seed_fields running once, or every frame?
_sf=village.Village._seed_fields
def seed_fields(self, world, now):
    C["seed_fields"]+=1
    C["seed_tiles"]+=sum(len(self.farm_tiles.get((c[0],c[1]),())) for c in self.farm_plots)
    return _sf(self, world, now)
try: village.Village._seed_fields=seed_fields; C["patched_seed"]=1
except Exception as e: C["seed_patch_fail"]=1
# 2. Village.update -- how often?
_vu=village.Village.update
def vupdate(self, *a, **k):
    C["village_update"]+=1
    return _vu(self,*a,**k)
try: village.Village.update=vupdate; C["patched_vu"]=1
except Exception: C["vu_patch_fail"]=1
# 3. gain_movement -- per frame per walker
_gm=None
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
    t0=time.time(); f0=0
    while True:
        time.sleep(20)
        el=time.time()-t0; fr=S["flips"]
        alive=sum(1 for n in village.PEOPLE if getattr(n,"alive",True))
        with open("/tmp/lag.out","a") as fh:
            fh.write("+%5.0fs  fps %5.1f   alive %4d   seed_fields %d (%d tiles)   village.update %d\n"
                     % (el, (fr-f0)/20.0, alive, C["seed_fields"], C["seed_tiles"], C["village_update"]))
        f0=fr
        if el>100: os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
main.WIDTH=320; main.HEIGHT=240
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
