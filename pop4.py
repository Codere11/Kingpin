"""THE FOUR NUMBERS. Where do a town's people go?"""
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
            if p is not None: p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def probe():
    time.sleep(170)
    o=[]
    try:
        towns={}
        for n in village.PEOPLE:
            v=getattr(n,"village",None)
            if v is not None: towns[id(v)]=v
        towns=list(towns.values())
        o.append("towns known: %d   PEOPLE total: %d" % (len(towns), len(village.PEOPLE)))
        o.append("%-16s %6s %6s %6s %6s %6s" % ("village","houses","cap","npcs","alive","PEOPLE"))
        tot=[0,0,0,0,0]
        for v in sorted(towns, key=lambda t:-len(t.houses))[:8]:
            pe=sum(1 for n in village.PEOPLE if getattr(n,"village",None) is v)
            o.append("%-16s %6d %6d %6d %6d %6d"
                     % (v.name, len(v.houses), int(getattr(v,"capacity",-1)),
                        len(v.npcs), v.alive_count(), pe))
            tot[0]+=len(v.houses); tot[1]+=len(v.npcs); tot[2]+=v.alive_count(); tot[3]+=pe
        o.append("")
        o.append("sample totals: houses %d  npcs %d  alive %d  PEOPLE %d" % tuple(tot[:4]))
        o.append("people per house: %.2f     npcs per house: %.2f"
                 % (tot[2]/max(1,tot[0]), tot[1]/max(1,tot[0])))
        o.append("WORLD_POP_CAP = %d" % village.WORLD_POP_CAP)
        o.append("TRAVELLERS on the road: %d" % len(getattr(village,"TRAVELLERS",()) or ()))
    except Exception as e:
        import traceback; o.append(traceback.format_exc()[-800:])
    open("/tmp/pop4.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
