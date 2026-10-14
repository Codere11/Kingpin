import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((320,240),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(160,120); pygame.mouse.get_pressed=lambda:(0,0,0)
S={"f":0}
_f=pygame.display.flip
def flip(): S["f"]+=1; _f()
pygame.display.flip=flip
import village, main, menu
main.WIDTH=320; main.HEIGHT=240
def keeper():
    while True:
        time.sleep(0.5)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None:
                if getattr(p,"dead",False): p.respawn()
                p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def probe():
    t0=time.time(); last=0
    while True:
        time.sleep(30)
        el=time.time()-t0; f=S["f"]
        alive=sum(1 for n in village.PEOPLE if getattr(n,"alive",True))
        best=-1.0
        for n in village.PEOPLE:
            v=getattr(n,"village",None)
            if v is not None:
                d=float(getattr(v,"_day",-1.0))
                if d>best: best=d
        with open("/tmp/fpslong.out","a") as fh:
            fh.write("+%5.0fs  fps %5.1f   alive %4d   game day %.3f\n" % (el,(f-last)/30.0,alive,best))
        last=f
        if el>330: os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
