import os,sys,time,threading,math,gc
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, train as tm, creatures
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    tr=[o for o in gc.get_objects() if o.__class__.__name__=="Train"][0]
    t0=time.time(); d0=tr.travelled
    time.sleep(3.0)
    dt=time.time()-t0
    print("TRAIN: %.0f px/s measured (constant %s)" % ((tr.travelled-d0)/dt, tm.TRAIN_SPEED), flush=True)
    print("PLAYER: walk %s, sprint %s px/s" % (p.speed, p.sprint_speed), flush=True)
    n=[x for x in village.PEOPLE if getattr(x,"alive",True)][0]
    print("VILLAGER: base_speed %s, current %s px/s" % (n.base_speed, getattr(n,"speed",None)), flush=True)
    print("WOLF: %s px/s (constant)" % creatures.WOLF_SPEED, flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
