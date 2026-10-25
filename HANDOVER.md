# HANDOVER — read this first, then the code

A fresh session on **Kingpin** (Python + pygame-ce, top-down 2D open world).
This file is the things that are **not discoverable by reading the code**: the
traps, the rules of the build, and how the user works. Read it, then read the
code it points at.

---

## 0. HOW THE USER WORKS (this matters more than any code)

* **Read the code before changing it.** He has said this dozens of times. Every
  "I think it's probably X" that was followed by a change cost hours.
* **Verify by measurement, never by state.** Pixels for rendering, the game's
  own log files for behaviour. Never "it should work now".
* **Do not run 30-minute exploratory scripts.** He explodes. Short, surgical,
  one change at a time. Ask before long runs.
* **Never claim "fixed" from a harness.** Only from the real running game or
  from him.
* **He designs; you implement.** Do not invent mechanics. When he says "I will
  design it", write nothing but what he specifies.
* **Every build ends in "quit and relaunch"** — he must restart the exe.
* **Do not change gameplay while optimising.** He explicitly reverted a
  performance pass because throttling traders to 10 Hz made them move in
  24-pixel jumps. Speed work needs his approval and must not alter behaviour.
* Files he reads: `Pivot.md` (design + what's next), `Nemesis.md`,
  `ACCOUNTING.md`, this one.

---

## 1. BUILD

```
./build.sh      # cythonise village/economy/skills, then PyInstaller  (~4 min)
./run.sh        # dev run
./Kingpin       # the exe he plays
```

* **`build.sh` exits 1 on a Cython failure, on purpose.** It used to print
  "continuing in pure Python" and ship a **stale `.so` that shadowed every
  `village.py` edit for hours**. If it fails, fix the code — do not bypass it.
* **Compiled modules: `village.py`, `economy.py`, `skills.py`.**
  `village.pxd` declares the NPC as a **C struct**. **Never `cythonize -i
  village.py` alone** — `economy.py` cimports it.
* **Class constants are read through `self.`** inside methods. A bare
  `PROVOKE_SECONDS` in a method is a Cython `undeclared name` error.
* **The exe is a windowed build: stdout is swallowed.** Anything you need to
  see must go to a file (`plog.log`, `~/.kingpin_saves/*.log`).

---

## 2. THE RULES THAT COST THE MOST BUGS

1. **Every field needs a class default.** A save, and any unpickled object,
   never runs `__init__`. (This crashed the gate code on its first frame:
   `player.gate_guard` did not exist.)
2. **`_restore()` copies `x`/`y` onto a village.** A save from another world
   moved every town **22 km** from its seed position — fences, gates and guards
   were then computed for a place the town was not. `world_from_data` now
   re-places towns from `village_center()`; do not remove that.
3. **Never build a village to ask where it is.** `villages.visible()` once
   called `self.get(gx, gy)` per cell and laid out whole villages mid-frame —
   **46-second frames**. It reads `_cache` only.
4. **`pygame.transform.scale(src, size, dest)` raises ValueError** if `dest` is
   not that size. Use `main._present()`, which reads the window's real size.
5. **A cutout is drawn centred on its `(x, y)`** — body circle r=10, head r=8
   just above (`NPC.draw`). Hit boxes must cover the body, not a circle at the
   feet.
6. **Panels must be drawn in the OUTDOOR HUD block** (`main.py`, the
   `if trade_open: … if inventory_open: …` group around line 5977). A panel
   drawn in the house branch opens outdoors and is **never painted** — that is
   what made a working click look dead for hours.
7. **A panel must not own every event.** A dialogue branch with no event filter
   swallowed the mouse and the wheel: inventory scrolling and NPC clicking both
   died. It owns only its own keys now.
8. **`main.py` has more than one event chain.** Verify which mouse branch is
   live before patching (the live one is the `elif MOUSEBUTTONDOWN` **after**
   the menu branches — grep `click_a_man`).
9. **Do not teleport the player in a headless test** — `clamp_world()` pins him
   to ±`WORLD_HALF`, so tests silently measure the wrong place. That wasted
   hours of "it doesn't work" that was the harness.
10. **`hunger` is satiety** and it *rises*; `EAT_AT` 50, `STARVE_AT` 100.
    `crop.GROW_SECONDS` is 180 s, so **nothing can be harvested in the first
    3 minutes** — a run shorter than that proves nothing.

---

## 3. WHERE THE GAME IS NOW (state)

**Systems that work:** world from seed; 36 settlements; vision cone; skills;
crops and farm cycle; villages, houses, fences, gates; the dole; wolves;
trader routes on the road; war and conquest; the mine; saves.

**The pivot (`Pivot.md`):** one totalitarian state, **Ashmark** (nation 0), one
seat + two regional capitals, a **black market** in 25 off-lattice **hubs**
(nation 1), no elections (they are **marked for removal** in §9.0 — a
dictatorship has none; office is appointed or taken by force).

**Hubs:** exactly **three men — soldier, farmer, artisan** — one 5×5 field
(5 food, 20 leaf), a fence and two gates, a bench, a house, a common ledger.
The farmer's leaf goes to the bench; what the bench makes goes on the shelf.

**Carts:** `caravans.py` — free, **nationless** traders, one per hub. They buy
what a hut's shelf holds (a **fifth of what would certainly catch them**: 6
items at skill 0, 60 at skill 10), walk to a settlement's **gate**, are searched
by the guard (`gate.search_visitor`), and either sell to the townspeople (and
the town's own purse for what nobody can afford) or are caught and lose the load.

**The gate law (`gate.py`):** 30 contraband = certain capture at skill 0; 300 at
skill 10; the roll is `units / threshold`. Hubs never search.

**The Truth-Teller:** one NPC created at startup, standing where he was born
(never following), invincible, a real settlement and a real trade. Clicking him
opens `dialogue.py`: three questions, answered truthfully —
trade / what he thinks of the Dictator (0–100; base 60 townsman, 30 hut man) /
what he thinks of you (**0–100, every man starts at 50**) with the laconic
answers *"I like you." / "I don't know." / "Fuck off."*

**Known broken (in `Pivot.md`):** the gate search happens **once per person**,
not on every approach. Nothing clears `player.waved_by` / `npc.searched_by`.

---

## 4. WHAT THE USER WANTS NEXT

`Pivot.md` §9 is the arc he settled on:

```
bans → earn and grow a network → an army → take the settlements by force →
the Dictator falls, the regime does not → the Chief of the secret police
wages a permanent rebellion (assassination, infiltration, criminal money) →
the player chooses: keep the bans (feeds the rebellion) or legalise
drugs/guns (starves it, poisons the country)
```

And the immediate building block he asked for: **NPC commands** — the player as
a leader whose orders are obeyed, refused, faked, or betrayed according to the
man's situation (`Pivot.md` §5 is the interaction-screen sketch).

**What does not exist yet:** any command/order system, fear of the state,
loyalty to the player, informers, or any dialogue other than the Truth-Teller's.
