import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, interior as inmod
menu.run = lambda s,c: (1, True)
T0=time.time(); CARD=[None]
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None:
        if time.time()-T0>150: print("no world", flush=True); os._exit(1)
        time.sleep(0.3)
    time.sleep(3)
    p=village.PLAYER
    towns={}
    for n in village.PEOPLE:
        v=getattr(n,"village",None)
        if v is not None and not getattr(v,"is_hub",False): towns[id(v)]=v
    v=[t for t in towns.values() if getattr(t,"houses",None)][0]
    h=sorted(v.houses, key=lambda h:(h.x-p.x)**2+(h.y-p.y)**2)[0]
    h.enterable=True; h.interior=inmod.Interior(777, tuple(h.facing))
    fx,fy=h.facing
    p.x,p.y=h.x+fx*(h.h/2.0+6.0), h.y+fy*(h.h/2.0+6.0)
    time.sleep(2.0)
    it=h.interior
    print("IN: room=%s player=%.0f,%.0f | chest_rect=%s" % (None, p.x, p.y, tuple(it.chest_rect)), flush=True)
    # stand on the chest and press E, as the game does
    p.x, p.y = it.chest_rect.centerx, it.chest_rect.centery
    time.sleep(0.3)
    ev=pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)
    pygame.event.post(ev)
    time.sleep(1.5)
    print("after E: player %.0f,%.0f (chest %d,%d) still inside: %s | crash=%s"
          % (p.x, p.y, it.chest_rect.centerx, it.chest_rect.centery,
             abs(p.x-it.chest_rect.centerx) < 200, os.path.exists("saves/crash.log")), flush=True)
    # and place a workshop through the game's own path
    try:
        r=it.place_workshop(it.W*0.35, it.H*0.45)
        print("workshop placed at %s | can_use=%s" % (tuple(r), hasattr(it,"workshop_near")), flush=True)
    except Exception as e:
        print("PLACE FAILED", e, flush=True)
    time.sleep(1.0)
    print("still alive: crash=%s" % os.path.exists("saves/crash.log"), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
