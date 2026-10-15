"""THE TOOL CHAIN, STEP BY STEP, IN SECONDS. Order -> forge -> shelf -> buy."""
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
HERE="/home/maksich/Documents/Kingpin"; sys.path.insert(0,HERE); os.chdir(HERE)
import pygame
_sm=pygame.display.set_mode; pygame.display.set_mode=lambda *a,**k:_sm((160,120),0)
import menu, persist, main, village as V, economy as E, industry
main.WIDTH=160; main.HEIGHT=120; menu.run=lambda s,c:(0,False)
pygame.init(); screen=pygame.display.set_mode((160,120)); clock=pygame.time.Clock()
_save=persist.read(); world=main.World(seed=int(_save.get("seed",20240501)))
ground=main.GroundRenderer(world); world.ground=ground
try: ground.scatter=main.Scatter(world.seed, world)
except Exception: pass
villages=main.Villages(world.seed); trees=main.Trees(world.seed)
world.trees=trees; main.set_forest(trees)
c=main.load_cached_world(world.seed)
if c is not None: villages=c
else:
    main.load_world(screen,clock,villages,world); main.set_world_population(villages)
V.rebuild_people(villages); V.rebuild_houses(villages)
now=0.0; ok=True
def check(label, cond, detail=""):
    global ok
    print("  %-4s %-46s %s" % ("OK" if cond else "FAIL", label, detail), flush=True)
    if not cond: ok=False

# pick a village with a smith and an unarmed miner
v=next(v for v in villages.villages
       if any(n.job=="smith" for n in v.npcs)
       and any((n.job=="mine" or getattr(getattr(n,"workplace",None),"kind",None)=="mine")
               for n in v.npcs))
smith=next(n for n in v.npcs if n.job=="smith")
miner=next(n for n in v.npcs if (n.job=="mine"
            or getattr(getattr(n,"workplace",None),"kind",None)=="mine"))
miner.stock["pickaxe"]=0; miner.tool_uses=90; miner.tool_kind="shovel"   # stale from a shovel
print("village %s   smith %s   miner %s" % (v.name, smith.name, miner.name))

print("\n1. wears_tool / needs_tool")
check("miner wears a pickaxe", E.wears_tool(miner,"pickaxe"))
check("with a stale tool_uses he does NOT need one YET (that is the trap)",
      not E.needs_tool(miner,"pickaxe"),
      "tool_uses=%d tool_kind=%s -- place_orders must reset the kind" % (
          miner.tool_uses, getattr(miner,"tool_kind",None)))

print("\n2. place_orders: does the book get it?")
before=len(getattr(smith,"tool_orders",()))
E.place_orders(v, miner)
check("an order was placed", len(smith.tool_orders)>before,
      "book=%s" % [k for _w,k in smith.tool_orders])
check("the miner is marked", miner.tool_order=="pickaxe", "tool_order=%s" % miner.tool_order)
E.place_orders(v, miner)
check("and he cannot order twice", len(smith.tool_orders)==before+1,
      "book=%d" % len(smith.tool_orders))

print("\n3. forge_next: what does the forge choose?")
check("forge_next says pickaxe", industry.forge_next(v)=="pickaxe",
      "got %r" % industry.forge_next(v))

print("\n4. smith_shift: does it make one, with material?")
v.ledger_goods["iron"]=int(v.ledger_goods.get("iron",0))+40
v.ledger_goods["pickaxe"]=0
smith.produce_acc=0.0
industry.smith_shift(smith, 60.0, now)
shelf=v.ledger_goods.get("pickaxe",0)
check("a pickaxe reached the TOWN SHELF", shelf>=1, "shelf=%d" % shelf)
check("the order was ANSWERED", miner.tool_order is None,
      "tool_order=%s" % miner.tool_order)
check("iron was spent", int(v.ledger_goods.get("iron",0))<40+4,
      "iron=%s" % v.ledger_goods.get("iron"))

print("\n5. no order -> no work (material alone is not enough)")
smith.produce_acc=0.0
n0=v.ledger_goods.get("pickaxe",0)
industry.smith_shift(smith, 60.0, now)
check("the forge stood down with no orders",
      v.ledger_goods.get("pickaxe",0)==n0 or industry.forge_next(v) is not None,
      "shelf %d -> %d, next=%r" % (n0, v.ledger_goods.get("pickaxe",0), industry.forge_next(v)))

print("\n6. the shelf brake: no order while the shelf has one")
miner.tool_order=None
miner.tool_uses=0; miner.tool_kind="pickaxe"; miner.stock["pickaxe"]=0
n1=len(smith.tool_orders)
E.place_orders(v, miner)
check("he does NOT order what is already on the shelf",
      len(smith.tool_orders)==n1, "book %d -> %d" % (n1, len(smith.tool_orders)))

print("\n7. and he can BUY it, with coin")
miner.coins=500
price=max(1, E.ledger_value(v,"pickaxe"))
got=E._settle(v, "pickaxe", price, 1, None, miner)
check("he bought it off the ledger", got==1,
      "price=%d qty=%d coins_left=%d" % (price, got, miner.coins))
check("it is in his hand", miner.stock.get("pickaxe",0)>0,
      "stock=%d" % miner.stock.get("pickaxe",0))
check("the store was paid", v.ledger_coins>0, "ledger=%d" % int(v.ledger_coins))

print("\n8. DOES THE PICKAXE WEAR OUT? (the pit never swung one)")
miner.stock["pickaxe"]=1
miner.tool_uses=E.TOOL_USES
miner.tool_kind="pickaxe"
b0=miner.tool_uses
for _i in range(10):
    industry.produce(miner, 1.0, now)
check("tool_uses falls when he digs", miner.tool_uses < b0,
      "%d -> %d" % (b0, miner.tool_uses))
miner.tool_uses = E.TOOL_WORN - 1
miner.stock["pickaxe"] = 0
v.ledger_goods["pickaxe"] = 0
miner.tool_order = None
E.place_orders(v, miner)
check("and at the line he ORDERS a new one", miner.tool_order=="pickaxe",
      "tool_order=%s" % miner.tool_order)

print("\n9. NO PICK, NO ROCK")
miner.stock["pickaxe"]=0
miner.tool_uses=0
miner.tool_order=None
v.ledger_goods["pickaxe"]=0
i0=int(v.ledger_goods.get("iron",0))
miner.produce_acc=99.0
industry.produce(miner, 1.0, now)
check("a miner with no pick digs nothing", int(v.ledger_goods.get("iron",0))==i0,
      "iron %d -> %d" % (i0, int(v.ledger_goods.get("iron",0))))

print("\n=== %s ===" % ("THE CHAIN HOLDS" if ok else "SOMETHING IS BROKEN"))
sys.stdout.flush(); os._exit(0 if ok else 1)
