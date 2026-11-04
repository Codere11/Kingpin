import os,sys,time,threading,math
sys.path.insert(0,"/home/maksich/Documents/Kingpin"); os.chdir("/home/maksich/Documents/Kingpin")
import pygame, village, main, menu, rail, gulag, holding
from collections import defaultdict, deque
menu.run = lambda s,c: (1, True)
def probe():
    import wildcrop
    while getattr(village,"PLAYER",None) is None or wildcrop._WORLD is None: time.sleep(0.3)
    time.sleep(5)
    segs = rail._SEGS
    print("segments", len(segs), flush=True)
    at = defaultdict(list)
    for i,(ax,ay,bx,by,bb) in enumerate(segs):
        at[(round(ax/24.0), round(ay/24.0))].append(i)
        at[(round(bx/24.0), round(by/24.0))].append(i)
    conn = defaultdict(set)
    for k,lst in at.items():
        for a in lst:
            for b in lst:
                if a!=b: conn[a].add(b)
    comp = {}
    cid = 0
    for i in range(len(segs)):
        if i in comp: continue
        dq=deque([i]); comp[i]=cid
        while dq:
            j=dq.popleft()
            for k in conn[j]:
                if k not in comp: comp[k]=cid; dq.append(k)
        cid += 1
    sizes = {}
    for k,v in comp.items(): sizes[v]=sizes.get(v,0)+1
    print("components:", len(sizes), "sizes:", sorted(sizes.values(), reverse=True)[:6], flush=True)
    gx,gy = gulag.gate_point()
    s_gate,_ = rail._nearest_on_segs(gx,gy)
    c = holding.cells()[0]
    s_cell,_ = rail._nearest_on_segs(c.x,c.y)
    print("camp gate nearest seg %d in comp %d | cell nearest seg %d in comp %d"
          % (s_gate, comp.get(s_gate,-1), s_cell, comp.get(s_cell,-1)), flush=True)
    os._exit(0)
threading.Thread(target=probe,daemon=True).start(); main.main()
