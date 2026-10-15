"""Press I then G: does the world inventory draw, with non-zero totals?"""
import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE="/home/maksich/Documents/Kingpin"; sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((500,400),0)
pygame.mouse.get_pos=lambda:(250,200); pygame.mouse.get_pressed=lambda:(0,0,0)
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
import menu, observer, main
main.WIDTH=500; main.HEIGHT=400
menu.run=lambda s,c:(0, True)
INSTS=[]
_oi=observer.Observer.__init__
def _i(self): _oi(self); INSTS.append(self)
observer.Observer.__init__=_i
def wf(n,limit=200):
    t0=FR[0]; t=time.time()
    while FR[0]-t0<n:
        if time.time()-t>limit: return False
        time.sleep(0.15)
    return True
def key(k): pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
def sig():
    s=LAST.get("s")
    if s is None: return 0
    w,h=s.get_size(); t=0
    for x in range(0,w,13):
        for y in range(0,h,11):
            c=s.get_at((x,y)); t+=c.r+c.g+c.b
    return t
def probe():
    wf(40)
    ob=INSTS[0]
    key(pygame.K_i); wf(3)
    s_before=sig()
    key(pygame.K_g); wf(6)
    s_after=sig()
    goods=ob.world_goods()
    print("goods mode on        :", ob.goods)
    print("items in the world   :", len(goods))
    top=sorted(goods.items(), key=lambda kv:-kv[1])[:6]
    print("biggest              :", ", ".join("%s=%d"%(k,v) for k,v in top))
    print("screen changed       :", s_before!=s_after)
    ok = ob.goods and len(goods)>3 and s_before!=s_after
    print("\n=== %s ===" % ("THE WORLD INVENTORY WORKS" if ok else "IT DOES NOT"))
    sys.stdout.flush(); os._exit(0 if ok else 1)
threading.Thread(target=probe,daemon=True).start()
try: main.main()
except BaseException:
    import traceback; traceback.print_exc()
