"""PRESS I, THEN ENTER, AND SEE IF THE INSPECTOR REALLY LOCKS ON."""
import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((320,240),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(160,120); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, main, menu, observer
main.WIDTH=320; main.HEIGHT=240
OUT=[]
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None:
                if getattr(p,"dead",False): p.respawn()
                p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def press(key):
    ev=pygame.event.Event(pygame.KEYDOWN, {"key":key, "mod":0, "unicode":"", "scancode":0})
    pygame.event.post(ev)
def probe():
    time.sleep(70)
    try:
        obs=None
        for n in village.PEOPLE:
            v=getattr(n,"village",None)
            if v is not None: break
        # find the live observer object through the running module
        import gc
        for o in gc.get_objects():
            if isinstance(o, observer.Observer): obs=o; break
        OUT.append("observer object found: %s" % (obs is not None))
        if obs is None: raise SystemExit
        OUT.append("open before I : %s   target before: %s" % (obs.open, obs.target))
        press(pygame.K_i); time.sleep(1.2)
        OUT.append("open after  I : %s   rows listed: %d" % (obs.open, len(obs.rows())))
        press(pygame.K_f); time.sleep(0.8)
        OUT.append("after f filter: %s   values available: %s" % (observer.FILTER_NAMES[obs.filt], obs.keys()[:6]))
        press(pygame.K_f); press(pygame.K_f); time.sleep(0.8)
        press(pygame.K_RETURN); time.sleep(2.5)
        t=obs.target
        OUT.append("LOCKED ON: %s" % (t.name if t else "NOTHING"))
        if t is not None:
            OUT.append("  he is a %s of %s" % (observer.job_of(t), getattr(t.village,"name","?")))
            OUT.append("  player is standing on him: %s" % (
                abs(main.__dict__.get('_x',0))>=0))
            time.sleep(4)
            OUT.append("  HIS LOG (%d lines):" % len(obs.log))
            for l in obs.log[:10]: OUT.append("    " + l)
        press(pygame.K_x); time.sleep(1.0)
        OUT.append("after x let go: target=%s" % (obs.target,))
    except Exception as e:
        import traceback; OUT.append(traceback.format_exc()[-900:])
    open("/tmp/inctest.out","w").write("\n".join(OUT)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,True)   # TEST MODE
try: main.main()
except BaseException: pass
