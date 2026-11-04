import os,sys,time,threading,math,gc
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, build
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    towns={}
    for n in village.PEOPLE:
        v=getattr(n,"village",None)
        if v is not None and not getattr(v,"is_hub",False): towns[id(v)]=v
    v=[t for t in towns.values() if getattr(t,"houses",None)][0]
    h=sorted(v.houses, key=lambda h:(h.x-p.x)**2+(h.y-p.y)**2)[0]
    h.enterable=True
    try:
        import interior as _in
        h.interior = _in.Interior(1234, tuple(h.facing))
    except Exception as _e:
        print("interior stub failed:", _e, flush=True)
    fx,fy=h.facing
    door=(h.x+fx*(h.h/2.0+6.0), h.y+fy*(h.h/2.0+6.0))
    p.x,p.y=door
    time.sleep(2.0)
    room=[o for o in gc.get_objects() if o.__class__.__name__=="HouseRoom"]
    print("ROOM: %s | player %.0f,%.0f" % (None if not room else (room[0].W,room[0].H), p.x, p.y), flush=True)
    # the build menu inside
    bm=build.BuildMenu(p.pack if hasattr(p,"pack") else None)
    bm.open("inside"); panel, rects, vis = bm._layout(1280,720)
    print("INSIDE LIST: %s" % [build.BUILDINGS[i]["id"] for i in vis], flush=True)
    bm.open("outside"); panel, rects, vis = bm._layout(1280,720)
    print("OUTSIDE LIST: %d buildings, %d rows, panel %dx%d"
          % (len(vis), len(set(r.top for r in rects)), panel.width, panel.height), flush=True)
    print("crash:", os.path.exists("saves/crash.log"), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
