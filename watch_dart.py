import os,sys,time,threading,math,gc
os.environ["KINGPIN_WORKERS"]="1"
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu
from creatures import Soldier
menu.run = lambda s,c: (1, False)      # mortal, real game
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None:
        time.sleep(0.3)
    time.sleep(4)
    p = village.PLAYER
    sol=[o for o in gc.get_objects() if isinstance(o,Soldier)]
    guards=[s for s in sol if getattr(s,"is_militia",False) and getattr(s,"alive",True)
            and getattr(s,"gate_post",None) is not None]
    if not guards:
        print("no gate guard found", flush=True); return
    g = guards[0]
    # stand right in front of him, wanted, so he puts you down with darts
    p.wanted = True
    p.x, p.y = g.x, g.y + 70.0
    p.health = 115
    p.god = False
    g.hostile = True
    g.aware = True
    g.aware_timer = 60.0
    print("watch: the guard is about to dart the player", flush=True)
    # keep him planted in front of the guard until he drops
    t0=time.time()
    while time.time()-t0 < 20 and getattr(p,"sleep_t",0.0) <= 0 and not getattr(p,"dead",False):
        p.x, p.y = g.x, g.y + 70.0
        time.sleep(0.05)
threading.Thread(target=probe,daemon=True).start()
main.main()
