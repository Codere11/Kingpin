"""WATCH THE TRAIN: the player is put aboard at once and the engine runs for
the camp. Close the window when you have seen enough."""
import os, sys, time, threading
os.environ["KINGPIN_WORKERS"]="1"
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu
import plog
menu.run = lambda s, c: (1, True)
def probe():
    import wildcrop
    while getattr(village, "PLAYER", None) is None or wildcrop._WORLD is None:
        time.sleep(0.3)
    time.sleep(3)
    p = village.PLAYER
    p.aboard = True                 # he is on the train
    p.wanted = True
    plog.log("DEMO", "the player is aboard; the express to the camp begins")
    print("the player is aboard -- watch the engine run for the camp", flush=True)
threading.Thread(target=probe, daemon=True).start()
main.main()
