import os,sys,time,threading,math
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, rail, gulag, holding
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(5)
    gx,gy=gulag.gate_point()
    c=holding.cells()[0]
    pts=rail.graph_path(c.x,c.y,gx,gy)
    legs=[math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1)]
    print("path points %d | total %.0f px | legs: %d longest %.0f px" % (len(pts), sum(legs), len(legs), max(legs) if legs else 0), flush=True)
    worst=0.0; mid=None
    for i in range(len(pts)-1):
        ax,ay=pts[i]; bx,by=pts[i+1]
        for k in range(4):
            t=k/3.0
            d=rail.dist(ax+(bx-ax)*t, ay+(by-ay)*t)
            if d>worst: worst=d; mid=(ax+(bx-ax)*t, ay+(by-ay)*t)
    print("worst %.0f px off at %s" % (worst, tuple(int(v) for v in mid) if mid else None), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
