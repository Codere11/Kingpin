import os,sys,time,threading,math
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, economy, build
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    folks=[n for n in village.PEOPLE if getattr(n,"alive",True)][:4]
    v, fid, far = folks[0], folks[1], folks[2]
    for n in (v,fid,far):
        n.x, n.y = 0.0, 0.0
    far.x, far.y = 0.0, 5000.0          # out of sight
    economy.opinion_of(fid, v.id)[v.id] = 85.0   # a friend of the victim
    economy.opinion_of(far, v.id)[v.id] = 85.0   # a friend, but far off
    economy.opinion_of(v, village.PLAYER_ID)[village.PLAYER_ID] = 0.0
    economy.opinion_of(fid, village.PLAYER_ID)[village.PLAYER_ID] = 0.0
    economy.opinion_of(far, village.PLAYER_ID)[village.PLAYER_ID] = 0.0
    economy.wronged(v, p, 20.0, 500.0)
    print("victim likes attacker: %.0f" % economy.opinion_of(v, village.PLAYER_ID).get(village.PLAYER_ID,0.0), flush=True)
    print("friend who SAW it:    %.0f" % economy.opinion_of(fid, village.PLAYER_ID).get(village.PLAYER_ID,0.0), flush=True)
    print("friend 5000 px away:  %.0f" % economy.opinion_of(far, village.PLAYER_ID).get(village.PLAYER_ID,0.0), flush=True)
    panel, rects, vis = build.BuildMenu.__dict__["_layout"](None, 1280, 720) if False else (None,None,None)
    bm = build.BuildMenu(p.pack if hasattr(p,"pack") else None)
    bm.free = True
    for where in ("outside","inside"):
        bm.open(where)
        panel, rects, vis = bm._layout(1280, 720)
        xs=[r.left for r in rects]; ys=[r.top for r in rects]
        print("%s: %d buildings | panel %dx%d at (%d,%d) | cells x %d..%d y %d..%d | rows %d"
              % (where, len(vis), panel.width, panel.height, panel.left, panel.top,
                 min(xs), max(r.right for r in rects), min(ys), max(r.bottom for r in rects),
                 len(set(ys))), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
