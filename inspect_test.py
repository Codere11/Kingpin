"""Does pressing I change a PIXEL? State is not a picture."""
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
FR=[0]; SHOTS={}
_rf=pygame.display.flip
def _f():
    FR[0]+=1
    try:
        SHOTS[FR[0]]=pygame.display.get_surface().copy()
    except Exception: pass
    return _rf()
pygame.display.flip=_f
import menu, observer, main
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
def sig(f):
    s=SHOTS.get(f)
    if s is None: return None
    w,h=s.get_size()
    tot=0; n=0
    for x in range(0,w,17):
        for y in range(0,h,13):
            c=s.get_at((x,y)); tot+=c.r+c.g+c.b; n+=1
    return tot

def probe():
    wf(40)
    ob=INSTS[0] if INSTS else None
    f0=FR[0]; s0=sig(f0)
    key(pygame.K_i); wf(5)
    f1=FR[0]; s1=sig(f1)
    print("observer.open after I     :", ob.open if ob else "NO OBSERVER")
    print("pixel checksum before I   :", s0)
    print("pixel checksum after  I   :", s1)
    print("THE SCREEN CHANGED        :", s0 != s1)
    print("\n=== %s ===" % ("THE PANEL IS DRAWN" if (s0!=s1) else "STILL NOTHING ON SCREEN"))
    sys.stdout.flush(); os._exit(0 if s0!=s1 else 1)
threading.Thread(target=probe,daemon=True).start()
try: main.main()
except BaseException:
    import traceback; traceback.print_exc()
