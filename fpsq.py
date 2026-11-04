import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    fr=[0]
    try:
        import fps as fpsmod
        print("fps module:", [n for n in dir(fpsmod) if not n.startswith("_")][:8], flush=True)
    except Exception as e:
        print("no fps module", e, flush=True)
    p=village.PLAYER
    print("player speed consts: %s %s" % (p.speed, p.sprint_speed), flush=True)
    t0=time.time(); n=0
    while time.time()-t0 < 6:
        time.sleep(0.2); n+=1
    p0=(p.x,p.y)
    time.sleep(0.05)
    print("sample ok", flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
