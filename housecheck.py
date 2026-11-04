import os,sys,time,threading,math,gc
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, houseroom
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    print("SPAWN: player at %.0f,%.0f (outdoors)" % (p.x, p.y), flush=True)
    towns={}
    for n in village.PEOPLE:
        v=getattr(n,"village",None)
        if v is not None and not getattr(v,"is_hub",False): towns[id(v)]=v
    v=list(towns.values())[0]
    hs=[h for h in getattr(v,"houses",()) if getattr(h,"enterable",False)]
    print("houses at %s: %d" % (v.name, len(hs)), flush=True)
    if not hs:
        import random
        hs=[h for h in getattr(v,"houses",())]
        hs.sort(key=lambda h:(h.x-p.x)**2+(h.y-p.y)**2)
        h=hs[0]
        h.enterable=True
        try:
            h.interior = object()      # the door is open; the room does the rest
        except Exception:
            pass
    else:
        h=hs[0]
    fx,fy=h.facing
    door=(h.x+fx*(h.h/2.0+6.0), h.y+fy*(h.h/2.0+6.0))
    p.x,p.y=door
    time.sleep(2.0)
    room=None
    for o in gc.get_objects():
        if o.__class__.__name__=="HouseRoom": room=o; break
    print("ENTERED: room %s | player at %.0f,%.0f | room inside? %s"
          % (None if room is None else (room.W, room.H), p.x, p.y,
             bool(room is not None and 0<=p.x<=room.W and 0<=p.y<=room.H)), flush=True)
    print("crash log:", os.path.exists("saves/crash.log"), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
