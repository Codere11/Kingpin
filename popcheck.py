import os, sys, time, threading
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((128,96),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, main, menu
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is not None:
                p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def probe():
    time.sleep(170)
    alive=[n for n in village.PEOPLE if getattr(n,"alive",True)]
    towns=set(id(n.village) for n in alive if getattr(n,"village",None))
    open("/tmp/pop.out","w").write(
        "PEOPLE: %d alive\nTOWNS: %d\nAVERAGE: %.1f a town\nHOUSES (total): %d\n" % (
            len(alive), len(towns), len(alive)/max(1,len(towns)),
            sum(len(v.houses) for v in (n.village for n in alive) if v)))
    os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
