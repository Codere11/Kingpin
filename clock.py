import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    import lanes_mp
    t0=time.time()
    n0=getattr(lanes_mp, "_NOW", None)
    p=village.PLAYER
    n0=getattr(p, "clock", None)
    import nemesis
    g0=nemesis.NOW if hasattr(nemesis,"NOW") else None
    time.sleep(5.0)
    print("wall 5.0 s | nemesis.NOW delta %s" % (None if g0 is None else round((nemesis.NOW-g0),2)), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
