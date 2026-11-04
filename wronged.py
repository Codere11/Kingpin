import os,sys,time,threading
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, economy
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(4)
    p=village.PLAYER
    man=[n for n in village.PEOPLE if getattr(n,"alive",True)][5]
    before=economy.opinion_of(man, village.PLAYER_ID).get(village.PLAYER_ID, 0.0)
    economy.wronged(man, p, 20.0, 100.0)
    after=economy.opinion_of(man, village.PLAYER_ID).get(village.PLAYER_ID, 0.0)
    economy.wronged(man, p, 20.0, 101.0)     # inside the cooldown
    again=economy.opinion_of(man, village.PLAYER_ID).get(village.PLAYER_ID, 0.0)
    economy.wronged(man, p, 20.0, 120.0)     # cooldown over
    later=economy.opinion_of(man, village.PLAYER_ID).get(village.PLAYER_ID, 0.0)
    print("%s liked the player %s -> %s (a second blow inside 6 s: %s) -> %s (after the cooldown)"
          % (man.name, before, after, again, later), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
