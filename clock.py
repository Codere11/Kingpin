"""IS `now` ADVANCING? Count the frames and read EVERY village's clock."""
import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((320,240),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
S={"flips":0,"t0":time.time()}
_f=pygame.display.flip
def flip():
    S["flips"]+=1
    _f()
pygame.display.flip=flip
import village, economy, nemesis, main, menu
main.WIDTH=320; main.HEIGHT=240
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
    t0=time.time(); last=0
    while True:
        time.sleep(15)
        try:
            days=[]
            for n in village.PEOPLE:
                v=getattr(n,"village",None)
                if v is not None:
                    days.append(float(getattr(v,"_day",-1)))
            if not days: days=[-1]
            el=time.time()-t0
            fr=S["flips"]
            line=("+%6.1fs  frames %7d (%.1f fps)   max _day %.3f   min _day %.3f   villages %d"
                  % (el, fr, fr/max(0.1,el), max(days), min(days), len(days)))
            with open("/tmp/clock.out","a") as fh: fh.write(line+"\n")
        except Exception as e:
            with open("/tmp/clock.out","a") as fh: fh.write("ERR %r\n"%e)
        if time.time()-t0 > 150:
            os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException:
    import traceback; open("/tmp/clock.out","a").write(traceback.format_exc()[-600:])
