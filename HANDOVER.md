# HANDOVER — SettleWest

Read this first. It is the map of the codebase, written from skimming the code,
not from memory. The game was previously **GetWorld → StratWest → SettleWest**;
the old world (towns, war, hubs, gulag) has been removed from the live tree;
what remains is the colonization game.

---

## 1. WHAT THE GAME IS NOW (one paragraph)

Top-down 2D **colonization**. You wake on a beach beside a **ship**. The world
is dotted with **native settlements** (a fireplace, bedrolls, fields, orchards,
two warriors). You **conquer** them, and their people become your **workforce**
(farmers, loggers, miners, smiths, weavers, spicemen, gunsmiths, researchers,
soldiers). You **research** a tech tree with coin. You **sell manufactured
goods** to the ship's **free market**. Escalation comes from **war alarms**
(smoke signals) that arm every other settlement's warriors.

The progression spine: **conquer → assign jobs → research → sell to ship.**

---

## 2. BUILD & RUN

```
./build.sh      # cythonise village/economy/skills, then PyInstaller
./run.sh        # dev run (python main.py)
./SettleWest    # the windowed exe he plays
```

Hard rules:

* **After editing `village.py` / `economy.py` / `skills.py` you MUST `./build.sh`.**
  A stale compiled `.so` silently shadows the `.py` and your edit does nothing.
* **`build.sh` exits non-zero on a Cython failure on purpose** — do not bypass.
* **Every field needs a class default.** Restored objects may not run
  `__init__`, so a new field with no class default crashes restored objects.
* **Saves are plain data, not pickle.** Read `SAVE.md` before adding a field,
  a reference, a camp, a building or a new system. The round-trip runs inside
  `./build.sh` and refuses a build that cannot save and load itself.
* **Class constants are read through `self.`** in cythonised modules; a bare
  `CONSTANT` inside a method is a Cython "undeclared name" error.
* **The exe is windowed: stdout is swallowed.** Anything you need to see goes to
  a file (`plog.log`, `~/.kingpin_saves/*.log`).
* **`build.sh` bundles every `*.png` and `Sounds/*.ogg`** beside the exe.

---

## 3. THE FRAME LOOP (`engine.py`)

`main.main()` builds the whole `g` object, shows `menu.run()`, then calls
`engine.run(g)`. `engine.run` is the single loop:

* event handling (`pygame.event.get`), one big `if/elif` chain;
* **the world walks one list each frame: `g._native_people`** (native camp
  people and the player's conquered workers). Old town/hub lanes are not the
  live path;
* ground streaming via a worker thread (`world.GroundRenderer`);
* render → `_present` upscale.

The two most important render/input facts:

* **There are two map draw call sites** (in-house and overworld) and two
  `skill_axe_cd` assignments — grep, don't assume one.
* **The live mouse branch is the `elif MOUSEBUTTONDOWN` after the menu branches.**
  The **ship click** lives at the top of it, **before the weapon check**, so it
  works with any item in hand.

---

## 4. MAIN SYSTEMS — WHERE THINGS LIVE

| System | File | What it is |
|---|---|---|
| World model + ground | `world.py` | tiles logically, noise-field ground visually; chunks (256px), worker thread; `coast_x`; `GroundRenderer._generate` |
| Native settlements | `native.py` | build camps (fireplace, bedrolls, 2 warriors, farmers, fields, orchards, animals); `ensure_near`, war alarms, raids |
| People | `village.py` | the **NPC** class (workers, warriors, farmers); `NPC.tick/update/_native_step/_fight/_work_*`; combat, jobs, feeding |
| Conquest | `colony.py` | `conquer_camp`; per-camp jobs (`sync_jobs`, `sync_camp`); breeding, babies, soldiers |
| Economy | `economy.py` | hunger/satiety, needs, wages, prices, loot, `wronged` |
| Market | `market.py` | ship sell; `sellable()`, `sell_value()`, daily price drift; goods anchored per-10-units |
| Research | `research.py` | tech tree (`CARDS`); coin to start + points from researchers |
| Skills | `skills.py` | hidden skills (axe, shooting, movement, farming, research, smithing); drive damage/cooldown/speed |
| Player | `player.py` | movement, stamina, swing, take_damage, armor, god (test mode) |
| Player weapons | `combat_actions.py` | `use_axe`/`resolve_swing`, pickaxe, `fire`, `click_a_man`, `on_click` |
| Creatures | `creatures.py` | wolves, rabbits, bison, horses; the old `Soldier` (melee/ranged) |
| Crops | `crop.py` | biome food/leaf slots; `GROW_SECONDS=180`; leaf kinds incl. chili |
| Trees | `trees.py` | lattice trees, canopy/trunk, chopping |
| Ore | `ore.py` + `industry.py` | iron chunks; mine + smithy (tools) |
| Biomes | `biomes.py` | temperature/humidity/mix, npc wear |
| UI | `ui.py` (panels), `items.py` (icons), `build.py`+`placement.py` (build menu), `menu.py` (title) |
| Map | `map.py` | one fixed world image, zoom/pan view |
| Ship | `main.py` `ship_pos()` / `open_market()` | spawn coast +56 offshore; click opens market; gold HUD edge-arrow points to it |
| Saves | `save/` (manifest + gzip chunks), `persist.py` (dirs/crash log) | `saves/slot_N/save.json` + `chunks/`; contract in `SAVE.md` |
| NPC mind | `NPC.md` | MBTI, traits, mood, breaks, doctor, player personality; phase-gated |
| NPC foundation | `persona.py`, `mood.py`, `doctor.py` | deterministic types, pure mood/doctor data; farmer S/N hook live; card gated by medicine |
| NPC lab | `npclab.py` | test-mode fixture: eight labelled subjects incl. S/N farmers, F5–F8, F10 medicine; mind hidden until record |
| Sound | `sound.py` | one-shot, on-screen gated |
| Guns | `guns.py` | musket/double/rifle + ammo |
| Vision/light | `vision.py`, `life.py` | cone of sight, night glow (cached) |

### How they connect (the important edges)

* **Conquest** = `colony.conquer_camp`; a conquered settlement keeps its own
  people/jobs/fields (multi-camp). `g.player_camps` lists them.
* **Workers are native NPCs** (`village.NPC` with `native_role`), driven by
  `_work_field/_work_orchard/_work_artisan/...` from `NPC.update`.
* **Ship sell** = `g.ship_hold` (an `Inventory`), the `ShipMarketPanel` drags
  pack↔hold, `market.sell_value` pays coin. Sellable = manufactured goods only.
* **Research** unlocks market goods (hide/iron/textiles/sauce) and animals.
* **Combat**: player swings in `combat_actions.resolve_swing`; native warriors
  fight in `village.NPC._fight`. Axe reach is **96px + body radius on both
  sides**. No parry/block, no stagger/wind-up. Warriors flank (strafe) and
  animate swings (`_melee_swing`).
* **The ship is at the spawn coast** (`coast_x(spawn_y)+56, spawn_y`); spawn is
  at `±3000` y, not 0 — that is why "the ship" is easy to lose; the HUD arrow
  exists for this reason.

---

## 5. LEGACY / OLD WORLD (cleanup done)

The old pre-pivot simulation has been removed from the live tree. Deleted:
`war.py`, `rail.py`, `gulag.py`, `nemesis.py`, `orders.py`, `caravans.py`,
`gate.py`, `train.py`, `detain.py`, `holding.py`, `prison.py`, `folders.py`,
`board.py`, `boardapi.py`, `manhunt.py`, `newsbubble.py`, `interact.py`,
`governance` helpers, `socio.py`, `grief.py`, `brawl.py`, `question.py`,
`worldmap.py`, `resettle.py`, `govbeer.py`.

`village.py` no longer contains the `Village` class; `Villages` is an empty
registry. `hubs.py` is only the player's fenced yard. `worldbuild.py` is only
wild spawns/loot/targeting. `mind.py` is only the luxury-consumption mood hook.

Compatibility stubs remain for `lanes.py` / `lanes_mp.py` because the frame
still calls an empty worker-lane object; they run nothing. `stall.py` is the
player's market stall, not the old town simulation. `economy.py`, `work.py`,
`dialogue.py` and `trade.py` contain reusable native/interaction code and some
dormant town helpers; they are not the old simulation and are kept.

`enemy.py` and `fence.py` are shared live modules (animals; steering/pathfinding)
and must stay.

---

## 6. NUMBERS YOU WILL NEED

* Axe reach **96** (+ body radius), arc 78°, `MELEE_DAMAGE=35`.
* Player/npc base health **115**, grows to **180** with axe/shooting skill.
* `crop.GROW_SECONDS = 180` — nothing harvestable in the first 3 minutes.
* `hunger` is **satiety** (rises); `EAT_AT=50`, starve at 0.
* Ship sell: cigars etc. ~1 coin per 10 units at base grade.
* War alarms: 1 arms a bowman, 2 arms both, 3 maxes axe warriors (hide armor),
  4 mounts them.
* `SETTLEWEST_DEMO=1` → fixed seed `20240501` for new games.

---

## 7. HOW THE USER WORKS

* **Read the code before changing it.** Never "I think it's probably X".
* **Verify by measurement** (pixels, logs, real game), never by "should work".
* **Short, surgical changes.** One at a time. No 30-minute scripts.
* **Rebuild after any source change; then he relaunches the exe.**
* **He designs; you implement.** Do not invent mechanics.
* **Answer his questions directly** when he asks — do not keep coding past a
  question.
