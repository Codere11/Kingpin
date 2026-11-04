import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu
menu.run = lambda s,c: (1, True)
T0=time.time()
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None:
        time.sleep(0.3)
        if time.time()-T0 > 120: print("world never loaded", flush=True); os._exit(1)
    print("world up after %.0f s | player %.0f,%.0f" % (time.time()-T0, village.PLAYER.x, village.PLAYER.y), flush=True)
    time.sleep(3)
    print("frame alive, player %.0f,%.0f" % (village.PLAYER.x, village.PLAYER.y), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
