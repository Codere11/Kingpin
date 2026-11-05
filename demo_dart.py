import os,sys,time,threading,math,gc
os.environ["KINGPIN_WORKERS"]="1"
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, detain, holding
from creatures import Soldier
menu.run = lambda s,c: (1, False)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(6)
    p = village.PLAYER
    sol=[o for o in gc.get_objects() if isinstance(o,Soldier)]
    mil=[s for s in sol if getattr(s,"is_militia",False) and getattr(s,"alive",True)
         and getattr(s,"gate_post",None) is not None]
    cells = holding.cells()
    print("militia %d | cells %d" % (len(mil), len(cells)), flush=True)
    if not mil or not cells:
        print("no militia or no cells", flush=True); os._exit(1)
    g = mil[0]
    p.wanted = True
    p.x, p.y = g.x, g.y + 60.0
    p.health = 115
    p.god = False
    # two real darts, through the game's own combat loop
    combat_obj=None
    for o in gc.get_objects():
        if o.__class__.__name__=="Combat": combat_obj=o; break
    def dart():
        ang = math.atan2(p.y-g.y, p.x-g.x)
        combat_obj.fire(g.x, g.y, ang, 200.0, owner="enemy", damage=80,
                        team=getattr(g,"nation",None), shooter=g, dart=True)
    dart(); time.sleep(0.6); dart()
    t0=time.time(); asleep=False; arrested=False
    while time.time()-t0 < 60:
        time.sleep(0.5)
        if getattr(p,"sleep_t",0.0)>0: asleep=True
        if detain.player_cell() is not None: arrested=True
        if arrested: break
    print("ASLEEP %s (hp %s, alive %s) | ARRESTED %s (cell %s)"
          % (asleep, p.health, getattr(p,"dead",False), arrested,
             None if detain.player_cell() is None else (int(detain.player_cell().x), int(detain.player_cell().y))), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
