import os,sys,time,threading,math,gc
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, rail
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    tr=[o for o in gc.get_objects() if o.__class__.__name__=="Train"][0]
    tr.to_camp(__import__("gulag").gate_point())
    p.aboard=True
    worst=0.0; n=0
    t0=time.time()
    while time.time()-t0 < 12:
        d=rail.dist(tr.x,tr.y)
        worst=max(worst,d); n+=1
        time.sleep(0.1)
    print("LIVE: %d samples of the engine's own position | worst %.2f px from the track" % (n,worst), flush=True)
    print("engine travelled %.0f px | route legs %d" % (tr.travelled, len(tr.route)), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
