import os,sys,time,threading,math
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, rail, gulag, holding
menu.run = lambda s,c: (1, True)
def dev(pts):
    worst=0.0
    for i in range(len(pts)-1):
        ax,ay=pts[i]; bx,by=pts[i+1]
        for k in range(6):
            t=k/5.0
            worst=max(worst, rail.dist(ax+(bx-ax)*t, ay+(by-ay)*t))
    return worst
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(5)
    gx,gy=gulag.gate_point()
    tour=rail.tour()
    print("tour: %d points | worst point %.1f px from the track" % (len(tour), dev(tour)), flush=True)
    worst=0.0
    for c in holding.cells()[:6]:
        worst=max(worst, dev(rail.graph_path(c.x, c.y, gx, gy)))
    print("express paths from 6 cells: worst %.1f px from the track" % worst, flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
