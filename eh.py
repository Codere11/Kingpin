import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, interior as inmod
menu.run = lambda s,c: (1, True)
T0=time.time()
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None:
        if time.time()-T0>150: print("no world", flush=True); os._exit(1)
        time.sleep(0.3)
    print("world up %.0fs" % (time.time()-T0), flush=True)
    time.sleep(3)
    p=village.PLAYER
    towns={}
    for n in village.PEOPLE:
        v=getattr(n,"village",None)
        if v is not None and not getattr(v,"is_hub",False): towns[id(v)]=v
    v=[t for t in towns.values() if getattr(t,"houses",None)][0]
    h=sorted(v.houses, key=lambda h:(h.x-p.x)**2+(h.y-p.y)**2)[0]
    h.enterable=True
    h.interior=inmod.Interior(999, tuple(h.facing))
    fx,fy=h.facing
    p.x,p.y=h.x+fx*(h.h/2.0+6.0), h.y+fy*(h.h/2.0+6.0)
    time.sleep(2.5)
    print("after the door: player %.0f,%.0f types %s,%s" % (p.x,p.y,type(p.x).__name__,type(p.y).__name__), flush=True)
    time.sleep(1.5)
    print("alive: crash file %s" % os.path.exists("saves/crash.log"), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
