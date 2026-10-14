"""IS ANYBODY, ANYWHERE, ACTUALLY CUTTING WOOD? And is he reaching the woods?"""
import os, sys, time, threading, math, collections
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((128,96),0)
class _K:
    def __init__(s,d): s.d=d
    def __getitem__(s,k): return k in s.d
pygame.key.get_pressed=lambda:_K(set()); pygame.mouse.get_pos=lambda:(64,48); pygame.mouse.get_pressed=lambda:(0,0,0)
import village, economy, nemesis, main, menu
C=collections.Counter()
_cw=economy.cut_wood
def cut_wood(village_, npc, amount):
    C["cut_wood"]+=1; C["who:"+str(getattr(npc,'job',None))]+=1
    return _cw(village_, npc, amount)
try: economy.cut_wood = cut_wood; C["patched"]+=1
except Exception as e: C["patchfail"]+=1
_ww = village.NPC._work_woods if hasattr(village.NPC,"_work_woods") else None
def keeper():
    while True:
        time.sleep(1)
        try:
            p=getattr(village,"PLAYER",None)
            if p is None: continue
            if getattr(p,"dead",False): p.respawn()
            p.god=True; p.hunger=getattr(p,"max_hunger",100.0); p.health=getattr(p,"max_health",100)
        except Exception: pass
def probe():
    time.sleep(150)
    o=[]
    try:
        o.append("cut_wood calls in ~1.3 game minutes: %d" % C["cut_wood"])
        o.append("  by trade: " + ", ".join("%s=%d"%(k[4:],v) for k,v in C.items() if k.startswith("who:")))
        w=nemesis.WORLD; nm=w.active if w else None
        if nm:
            n=nm.npc
            o.append("nemesis: job=%r  axe stock=%s tool_uses=%s  axe skill=%.3f  wood in pack=%s"
                     % (n.job, n.stock.get("axe"), getattr(n,"tool_uses",None), n.skills.axe, n.stock.get("wood")))
            t=n._find_tree(n.village)
            o.append("  nearest woodlot tree: %s   distance %.0f px   village radius %.0f"
                     % ("yes" if t else "NONE", math.hypot(t.x-n.x,t.y-n.y) if t else -1, n.village.radius))
            # is a LOGGER, anywhere in the world, working?
            loggers=[x for x in village.PEOPLE if getattr(x,'job',None)=="logger" and getattr(x,'alive',True)]
            wand=sum(1 for x in loggers if x.stock.get("axe",0)>0 or getattr(x,'tool_uses',0)>0)
            o.append("loggers in the world: %d,  with an axe: %d" % (len(loggers), wand))
            o.append("  their axe skill: max %.3f  mean %.3f" % (
                max((x.skills.axe for x in loggers), default=0),
                sum(x.skills.axe for x in loggers)/max(1,len(loggers))))
    except Exception as e:
        import traceback; o.append(traceback.format_exc()[-900:])
    open("/tmp/probe4.out","w").write("\n".join(o)); os._exit(0)
threading.Thread(target=keeper,daemon=True).start()
threading.Thread(target=probe,daemon=True).start()
menu.run=lambda screen,clock:(0,False)
try: main.main()
except BaseException: pass
