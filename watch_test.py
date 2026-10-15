"""Watching a man: is the view BLACK? Measured by mean pixel brightness."""
import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE="/home/maksich/Documents/Kingpin"; sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((400,300),0)
pygame.mouse.get_pos=lambda:(200,150); pygame.mouse.get_pressed=lambda:(0,0,0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set())
FR=[0]; LAST={}
_rf=pygame.display.flip
def _f():
    FR[0]+=1
    try: LAST["s"]=pygame.display.get_surface().copy()
    except Exception: pass
    return _rf()
pygame.display.flip=_f
import menu, observer, main, village as V
main.WIDTH=400; main.HEIGHT=300
menu.run=lambda s,c:(0, True)
INSTS=[]
_oi=observer.Observer.__init__
def _i(self): _oi(self); INSTS.append(self)
observer.Observer.__init__=_i
def wf(n,limit=300):
    t0=FR[0]; t=time.time()
    while FR[0]-t0<n:
        if time.time()-t>limit: return False
        time.sleep(0.2)
    return True
def key(k): pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
def bright():
    s=LAST.get("s")
    if s is None: return -1
    w,h=s.get_size(); tot=0; n=0
    for x in range(2,w,11):
        for y in range(2,h,11):
            c=s.get_at((x,y)); tot+=(c.r+c.g+c.b)//3; n+=1
    return tot/max(1,n)
def probe():
    wf(40)
    ob=INSTS[0]
    b_normal = bright()
    print("mean brightness, normal play : %6.1f" % b_normal)
    key(pygame.K_i); wf(4)
    key(pygame.K_RETURN); wf(40)          # watch him, let the ground build
    tgt=ob.target
    b_watch = bright()
    print("watching                     :", getattr(tgt,"name",None),
          "of", getattr(getattr(tgt,"village",None),"name","?"))
    print("mean brightness, watching    : %6.1f" % b_watch)
    ok = b_watch > 12.0
    print("\n=== %s ===" % ("THE VIEW IS LIT" if ok else "THE VIEW IS BLACK"))
    sys.stdout.flush(); os._exit(0 if ok else 1)
threading.Thread(target=probe,daemon=True).start()
try: main.main()
except BaseException:
    import traceback; traceback.print_exc()
