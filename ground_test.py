"""Short: after watching a man, are the ground chunks under HIM built?"""
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
FR=[0]
_rf=pygame.display.flip
def _f(): FR[0]+=1; return _rf()
pygame.display.flip=_f
import menu, observer, main, village as V, world as W
main.WIDTH=400; main.HEIGHT=300
menu.run=lambda s,c:(0, True)
INSTS=[]
_oi=observer.Observer.__init__
def _i(self): _oi(self); INSTS.append(self)
observer.Observer.__init__=_i
G=[None]
_og=W.GroundRenderer
_oug=W.GroundRenderer.__init__
def _gi(self, *a, **k):
    _oug(self, *a, **k); G[0]=self
W.GroundRenderer.__init__=_gi
def wf(n,limit=200):
    t0=FR[0]; t=time.time()
    while FR[0]-t0<n:
        if time.time()-t>limit: return False
        time.sleep(0.15)
    return True
def key(k): pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
def probe():
    wf(40)
    ob=INSTS[0]; g=G[0]
    key(pygame.K_i); wf(3)
    key(pygame.K_RETURN); wf(12)          # short: just past the rebuild
    tgt=ob.target
    want=list(g.visible_chunks(tgt.x - 400/2.0, tgt.y - 300/2.0, 400, 300))
    have=[c for c in want if c in g._cache]
    print("watching          :", getattr(tgt,"name",None),"of",
          getattr(getattr(tgt,"village",None),"name","?"))
    print("chunks in view    :", len(want))
    print("chunks BUILT      :", len(have))
    pct = 100.0*len(have)/max(1,len(want))
    print("built             : %.0f%%" % pct)
    ok = len(have) == len(want)
    print("\n=== %s ===" % ("THE GROUND IS FULLY BUILT WHERE HE IS" if ok
                            else "CHUNKS ARE STILL MISSING"))
    sys.stdout.flush(); os._exit(0 if ok else 1)
threading.Thread(target=probe,daemon=True).start()
try: main.main()
except BaseException:
    import traceback; traceback.print_exc()
