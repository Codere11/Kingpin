import os,sys,time,threading,math
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu
menu.run = lambda s,c: (1, True)
class K(dict):
    def __getitem__(self, k): return self.get(k, False)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    p.x, p.y = 0.0, 0.0
    keys=K(); keys[pygame.K_d]=True          # walk east
    x0=p.x
    for _ in range(60):
        p.update(1/60.0, keys, (1.0,0.0), 1.0)
    print("PLAYER measured %.1f px/s over one simulated second (constant %s)" % ((p.x-x0), p.speed), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
