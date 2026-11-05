import os,sys,time,threading,math,gc
os.environ["KINGPIN_WORKERS"]="1"
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, holding
from creatures import Soldier
menu.run = lambda s,c: (1, False)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None:
        time.sleep(0.3)
    time.sleep(5)
    p = village.PLAYER
    sol=[o for o in gc.get_objects() if isinstance(o,Soldier)]
    guards=[s for s in sol if getattr(s,"is_militia",False) and getattr(s,"alive",True)
            and getattr(s,"gate_post",None) is not None]
    cells = holding.cells()
    if not guards or not cells:
        print("no guard/cell", flush=True); return
    g = guards[0]
    # ONLY THE PLAYER AND THIS ONE MILITIAMAN: every other soldier is moved
    # far away so nobody else can get a shot in. This is only for this test.
    for s in sol:
        if s is not g:
            s.x += 100000.0
            s.y += 100000.0
            s.home = (s.x, s.y)
            s.target = (s.x, s.y)
            s.hostile = False
    p.wanted = False            # nobody else takes a shot at him
    p.x, p.y = g.x, g.y + 60.0
    p.health = 115
    p.god = True              # only the darts count in this test
    p.tranq_health = p.TRANQ_HEALTH
    combat_obj = [o for o in gc.get_objects() if o.__class__.__name__=="Combat"][0]
    def dart():
        a = math.atan2(p.y-g.y, p.x-g.x)
        combat_obj.fire(g.x, g.y, a, 200.0, owner="enemy", damage=80,
                        team=getattr(g,"nation",None), shooter=g, dart=True)
    print("firing two darts at the player, live", flush=True)
    dart(); time.sleep(0.4); dart()
threading.Thread(target=probe,daemon=True).start()
main.main()
