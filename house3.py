import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, interior as inmod, houseroom
menu.run = lambda s,c: (1, True)
def probe():
    print("probe thread up", flush=True)
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    it=inmod.Interior(4242, (1.0,0.0))
    room=houseroom.HouseRoom(None, 1280, 720, interior=it)
    surf=pygame.Surface((1280,720))
    try:
        room.draw(surf, 0.0, 0.0, 1280, 720)
        print("ROOM DRAW: ok, %dx%d" % (room.W, room.H), flush=True)
    except Exception as e:
        print("ROOM DRAW FAILED:", e, flush=True)
    print("CHEST: %s at %s" % (getattr(it,"chest",None) is not None,
                               tuple(getattr(it,"chest_rect",(0,0,0,0)))), flush=True)
    try:
        r=it.place_workshop(it.W*0.5, it.H*0.5)
        print("PLACE WORKSHOP inside: %s" % (tuple(r) if r else None,), flush=True)
    except Exception as e:
        print("PLACE FAILED:", e, flush=True)
    try:
        it.place_lab(it.W*0.35, it.H*0.6); it.place_brew(it.W*0.65, it.H*0.6)
        it.place_barrel(it.W*0.8, it.H*0.7)
        print("PLACE lab/brew/barrel: ok", flush=True)
    except Exception as e:
        print("PLACE FAILED:", e, flush=True)
    room.draw(surf, 0.0, 0.0, 1280, 720)
    print("ROOM DRAW with furniture: ok", flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
