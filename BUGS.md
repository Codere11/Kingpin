# BUGS — the session of 28 Oct, ~11:00–11:30 (in-game, built exe)

Logged from the game's own files, not from memory:

* `~/.kingpin_saves/player.log` — 89,394 lines, 6.4 MB
* `~/.kingpin_saves/village.log` — 278,786 lines, 17 MB
* `saves/crash.log` — **does not exist** (the freeze wrote no traceback)

Player report, in his order: got a crazy amount of wood → a soldier searched him
and found something → he killed the soldier before it could act → he sold
almost all the wood → a wolf came, people shot it → **a massive massacre, everyone
attacking everyone, except him** → he hit several men a lot and they neither died
nor fought back → he tried to break into a house → **the game froze**.

---

## B1. Three runaway loggers (proven, counted)

| logger | lines | written | source |
|---|---|---|---|
| `KNOWS-AGGRO` | **88,283** of 89,394 lines | every frame, per man | `main.py:5264` |
| `HANDOFF shelf -> <man> 5 leaf` | **175,773** | every tick, per hub | `hubs.py:631` |
| `FLOW` / `MINT` / day census | the rest of 278,786 | per event / per day | economy |

What `KNOWS-AGGRO` does (main.py, the "the world knows your face" pass): for
every man within 760 px who has the player in `knows`, **every single frame**:

```python
plog.log("KNOWS-AGGRO", ...)      # one line per man per frame
_n.aggro = True                   # re-armed, for ever, while he is in range
```

Each `plog.log` opens, appends and closes the file. 88k lines ≈ 350 file
writes a second, plus 175k more from the hub economy. That is a real source of
hitching, and it makes the log useless for exactly the session we need to read.

**Why it matters beyond the mess:** the aggro is re-armed every frame with no
memory, so a man who "knows" you can never calm down while you are in sight —
see B2.

---

## B2. The massacre (evidence, and what is missing)

Timeline from `player.log`:

```
200.26  SEARCHED  caught units 25 town Willow Crossing
200.26  CAUGHT Faye Crowder CAUGHT AT THE GATE OF Willow Crossing WITH 25
200.26  AGGRO Willow Crossing known_to 1
201.31  CLICK on_click item axe ... at 29760,-25802        <- he attacks
...     (clicks continue)
204.38  BLOCKED inv True trade False board ... hp 115
~201+   KNOWS-AGGRO flood begins (88k lines)
413.24  AGGRO Willow Crossing known_to 1
413.71  CLICK on_click item axe dead False house True at 320,372   <- inside a house
450.89  HEARTBEAT x 26416 y -26153 dt 0.016    <- last line before the freeze
```

So: he was **caught at the gate with 25 units**, the town was provoked
(`known_to 1`), and from that moment every man within 760 px who had heard of
him was set `aggro = True` every frame.

`village.py` then runs, for any man with `aggro`:

```python
if self.aggro and threat is not None and not getattr(threat, "dead", False):
    self._fight(dt, threat, combat)
```

`threat` comes from `threat_of(self)` handed in by the lane. **What the logs
cannot tell us is who each man fought and who died** — there is no death log for
NPCs at all. That is the first thing to add (B6), because "everyone attacks
everyone" can only come from one of three places and they are all testable:

1. `threat_of` returning a **different man** for different NPCs (e.g. the
   nearest man with a different `nation`, and townsmen of the same town have
   `nation = None` while soldiers have a nation) → villagers fight villagers;
2. `aggro = True` set **without a valid threat**, and some other pass (panic,
   `provoke`, gate law) choosing a target;
3. damage landing on the **wrong man** (see B3) → men die at random → the
   survivors aggro the nearest thing, which is each other.

The wolf phase is normal (`people shot him`) and is not part of this.

---

## B3. Hitting men does nothing (he hit several, they neither died nor fought)

He swung repeatedly at men around `29,760,-25,802` (`CLICK on_click item axe`,
~20 strikes). **No damage, no death, no reaction was logged anywhere** — and the
reason may be that damage is routed by *index* into a list, and dropped in
silence when the man is not in it:

`lanes_mp.py:453`

```python
def damage(self, npc, amount):
    for lane in (self.settle, self.hub):
        i = lane.index.get(id(npc))          # frame object -> index in that lane
        if i is not None:
            self._events.append(("dmg", lane.name, i, int(amount)))
            return                            # <- if no lane has him: NOTHING
```

`lane.index` is built from the list of men handed to that lane at fork
(`lanes_mp.py:494`). If the man he struck is **not in either list** — a
traveller, a cart's man, a soldier from `enemies`, a man who was added after the
fork — the blow is dropped and **nothing is written to any log**. If the list's
order ever differs from the lane's `men`, the blow lands on a different man.

That single line explains both halves of his report: *the man he hit never
died*, and *men died that he never touched* → the massacre.

---

## B4. The freeze

No traceback, no `crash.log`: the process stopped between frame 450.89 and the
next frame, so this is a **hang**, not an exception. Last recorded state:
`HEARTBEAT ... dt 0.016`, player at `26416,-26153`, and 40 s earlier a click
logged with `house True` at interior coordinates `320,372` — he was inside (or
entering) a house.

Three candidates, in the order I would test them:

1. **Log I/O and the mass of dying men** (B1/B2) turning a heavy frame into a
   stuck one — cheap to rule in/out by rate-limiting the logs.
2. **Lane back-pressure**: the frame keeps sending tick messages to the two
   child processes; if a lane stops reading (busy in a long hub economy pass —
   the 175k HANDOFFs suggest it is), the pipe fills, and `Workers.tick` keeps
   queueing into its outbox until `MAX_BACKLOG` (4 MB) while the game runs.
3. **The interior path**: entering/breaking a house builds an `Interior` and
   its occupants; a door-break path that never returns is a classic hang.

We cannot tell which from the logs, because a hang leaves nothing. That is why
B6 first.

---

## B5. "A crazy amount of wood" — NOT VERIFIED

I could not find any wood quantity, sale or ledger movement in the logs — the
`player.log` has no board/sell lines and the `village.log` is so flooded with
HANDOFF that a sale would be invisible. **What he did to get the wood is
unknown.** If he tells me the action (felling? the board? a search? a chest?
a purchase?) I can follow that path. Do not guess-fix this one.

---

## B6. What must be added to see any of this next time (diagnostics, not gameplay)

1. **A death log** — `plog.log("DIED", name, job, town, killed_by, at x,y)` on
   every NPC death, and `plog.log("HIT", attacker, victim, dmg, hp_left)`.
   Without these, "who killed whom" is unanswerable.
2. **A dropped-damage log (rate-limited)** — when `Workers.damage` cannot route
   a blow: `plog.log("DMG-DROPPED", name, id, lane_names)`. One line, not per
   frame.
3. **A log rate limiter in `plog`** — per (kind, subject) at most one line a
   second, plus a global cap of N lines per minute (and `KNOWS-AGGRO` demoted
   to a state-change log: log when a man *starts* or *stops* hunting, not every
   frame).
4. **A hang dump** — `faulthandler.enable()` plus a watchdog thread that dumps
   all thread stacks after 5 s without a frame. Then a freeze names the line it
   is stuck on instead of leaving silence.

---

## B7. Discussion — the questions that decide the fixes

**A. Who may a man with `aggro` fight?**
He should fight *the player* and only the player. If `threat_of` can return
anyone else, that is where the massacre starts. Proposal: `aggro` carries a
target id, set once when it is armed, and `_fight` refuses any other target.

**B. What does "knows your face" mean, and when does it stop?**
Today: re-armed every frame while within 760 px, for ever. Proposal: arming is
an *event* (the man sees you, or is told about you, once), it decays after some
minutes, and it is re-evaluated only when he has actually seen you again. That
kills the flood *and* the permanent siege.

**C. Damage routing.**
Route by the man's **id** to the lane that owns him (both lanes hold `by_id`
already), and never drop silently. If the id is unknown to both lanes, log it
once — that is a bug in itself (a man the frame can hit but no lane owns).

**D. Search → execution.**
Being caught at a gate should not make the whole town permanently aware and
armed within one frame. Decide what a soldier does when he finds 25 units
(take them? fine? fight you? call the watch?) and what the town remembers.

**E. Logs must never be a gameplay cost.** Nothing in the frame may log per
entity per frame. This alone would have made the session above readable.

---

## FIXED, after the decisions above (built, `build.sh` exit 0)

His instructions: (A) an aggroed man fights **whoever aggroed him**, each until
that particular man is dead or gone — not "whatever is nearest"; (B) knowing a
face is learned **once**, not every frame; (C) **the exact person attacked takes
the damage**; (D) a soldier who finds contraband **attacks immediately**.

* **C — damage by identity.** `Workers.damage` now addresses the man by **id**
  and the lane that owns him (`lane.ids`), and a blow that cannot be routed is
  logged (`DMG-DROPPED`) once per man per 5 s instead of disappearing.
  *Measured in-game: ten swings at one man took him 40 → 13 health; the 21
  other men of that town were untouched (0 deaths).*
* **A — a feud is with a person.** `NPC.aggro_at` holds the specific men who
  attacked him (`add_threat` / `drop_threat` / `threat_list`); the lane's
  `threat_of` returns the nearest man **from that list** and nobody else. The
  old rule ("hostile / wanted / provoked → the player, whatever the situation")
  is now only how a face is *learned* once.
* **B — learned once.** The per-frame `KNOWS-AGGRO` pass in `main.py` is
  **deleted**. A man who knows the player adds him to his own feud list once,
  and one line is written (`AGGRO … now hunts the player`).
  *Measured: KNOWS-AGGRO lines in a fresh session, **0** (was 88,283).*
* **No more killing the dead.** `take_damage` refuses an already-dead man; every
  further blow used to re-run the death branch (measured in his session: the
  same two people "SLAIN" over and over, 487 lines).
* **D — caught men act.** Being caught sets `player.wanted` and provokes the
  town; the guard's `threat_of` now *learns* the player from that state and
  fights him the next tick, instead of depending on a flag read elsewhere.
* **The 175,773-line handoff flood** is rate-limited to once a minute per bench.
* **The axe hurts EVERY man it reaches, once each.** The swing walked only the
  towns in view, so the men of a criminal hut and every traveller on the road
  stood inside the arc of a blow that could not see them, and a man listed in
  two towns was cut twice. It now builds one list from every register in the
  world (`PEOPLE`, `TRAVELLERS`, every hub's men, the truth-teller),
  deduplicated by identity, and every man inside the arc is hit. The frame's
  copy damages itself with `record=False` so one blow writes ONE death instead
  of two (frame copy + lane copy).
  *Measured in-game: a blow that reached one man took him 40 → 27 health; the
  loop that carries it is unconditional over every man in the arc. The harness
  cannot aim the arc (this machine will not warp the cursor, so the swing's
  facing comes from a fixed point), which is why a crowd cannot be lined up in
  front of it for a screenshot-proof count.*

**Measured after the fixes** (one short session): exact-man damage ✓, no
neighbour deaths ✓, zero `KNOWS-AGGRO` lines ✓, one `AGGRO` line per man who
learns ✓, no duplicate `SLAIN` ✓.

## B0. THE FREEZE ON BREAKING IN (open, top of the list)

**Symptom (his words):** *breaking in freezes the game.* Twice now, both times
around a house: he breaks a door open (or walks into a house) and the game stops
dead.

**What the logs show:** nothing. No `crash.log`, no traceback anywhere; the last
line is an ordinary `HEARTBEAT`. The process is alive and the frame never
returns, so it is a **hang, not an exception** — nothing is written because
nothing throws.

**Where it could be (candidates, in order, none yet proven):**

1. `use_axe()`'s door-break branch (`main.py`, "Break a villager's door open
   with the axe") — it builds `Interior(random seed)`, `fill_loot(chest)`,
   `break_door()` and calls `commit_crime()` on the same frame as the swing.
2. The **entry** path: `enter_house()` moves the player to `interior.spawn`,
   sets the camera from the interior size, and puts the house's occupants
   inside (`npc.in_interior`, `_interior_rect`, `_interior_colliders`).
3. The **interior frame** itself: its own draw/collision branch, which is a
   different renderer from the world and is only ever exercised by walking into
   a house.
4. A **pipe deadlock** with the two worker processes (frame blocked writing or
   waiting while a lane is blocked reading) — the freeze leaves the log silent,
   which fits.

**What is now in place to catch it:** a hang watchdog (built) that watches a
per-frame heartbeat and, when the frame has not moved for six seconds, writes
**every thread's stack with line numbers** to `saves/hang.log`.

**Next step:** the next freeze is not a mystery — read `saves/hang.log`. It will
name the line. Until that file exists, any "fix" for this is a guess.

## B8. A GUARD IS TOO EASY TO KILL (open)

**Symptom (his words):** *guard too easy to kill.*

**The numbers, straight out of the code:**

| thing | value | where |
|---|---|---|
| a village man's health — **a guard is one of these** | **40** | `village.py:506` |
| the player's axe, per swing | **16 × `skills.axe_damage_scale()`** | `main.py:116` |
| so a guard dies in | **3 axe swings** (2 once the skill scales up) | — |
| a guard's own blow | **10** damage, once a second | `village.py` `_fight` |
| the player's health | **115** | `player.py` |
| a real soldier's health | 115 (160 for the player's veterans) | `creatures.py:106`, `:653` |

So the man standing at the gate is not a soldier at all: he is an ordinary
villager with a watch duty. `villages.defenders()` just hands the town's
`guards` and `defender`s over, and `_assign_duty_bodies` gives them an `owner`
(an armed body) but **no health, no armour and no gun** — `arm()` returns a
rifle only if the man happens to own one or is `ranged`. He comes at an armed
player with fists or an axe, 40 health, 10 damage a second.

**The open design question:** is a guard a militia man (cheap, 40 health, and a
town that cannot defend itself) or a soldier (115 health, a rifle, and breaking
into a town becomes a real fight)? And should a man on watch be given the
town's own arms when he takes the duty — the game already has `self._armed`
(the town's arsenal) being handed out as `guard.owner`?

Logged, not changed.

## B9. SELLING TO ONE MAN CAN BANKRUPT HIM (open, with a proposed fix)

**Symptom (his words):** *selling, for example, wood to a villager right now
allows the player to simply bankrupt him.*

**What the code does today.** The trade menu sells `min(stack, his want,
what he can afford)` (`trade._sell_amount`) — so a man is drained to his last
coin by design, and the size of a "want" is whatever `economy.wants()` says:

| he wants | how much the game lets him buy in one go |
|---|---|
| wood | `min(8, short)` — a stack, not a woodpile (`economy.wants`, `STOCK_WOOD`) |
| food | up to a larder of **5** (`STOCK_FOOD`), a taste of each kind (`VARIETY_MIN`) |
| tools | **2** — a spare while the old one is nearly dead |
| iron (a smith) | the shortfall to `IRON_STOCK`, capped by his coin float |
| leaf (an artisan) / mash (a brewer) | the bench/tun full (`LEAF_STOCK`, `WORT_STOCK`) |
| arms | a trader only — never a villager |

So a *single* wood sale is already capped at 8. **Either the leak is a path that
does not go through `wants()` at all** — the notice board's ledger buy, or a
cart buying from the stall and reselling (a cart's `target` is its own purse,
not anyone's need) — **or it is repeat sales across days**, which is not a cap
problem but a *how often can a man be sold to* problem. That needs pinning down
against the log before anything is changed.

**His proposed fix, logged as given:** *a person only buys a maximum of two
days' worth of food/wood, and everything else is refused.*

**What that means in the game's own numbers** (for discussion, not yet built):
a hearth burns `WOOD_PER_HOUSE = 5` logs a day, so **2 days = 10 logs** and a
man keeps a day's reserve (`FUEL_KEEP`); a larder is `STOCK_FOOD = 5`, and the
food half of the rule would be **two days of what he and his household eat**
(`food_of()` already exists), after which the row says *"I have no room for
more"* instead of paying. The same shape would apply to every item: **a need per
day, a cap of two days, and a refusal** — instead of a purse that empties.

The deeper fix this points at: **a man's purse should not be the player's
harvest.** A buyer with needs is a customer; a buyer whose coins you can count
is a piñata.

## Still open

* **The freeze — INSTRUMENTED, not yet fixed.** It has happened twice, both
  times around a house, and it writes nothing: the process is alive and the log
  simply stops. I could not reproduce it from a harness (my forced break-in put
  the player outside the world bounds and the world clamp moved him, so that
  attempt proved nothing). So the game now carries a **hang watchdog**: a thread
  that watches a per-frame heartbeat, and if the frame has not moved for six
  seconds it writes **every thread's stack, with line numbers, to
  `saves/hang.log`**. The next freeze will name its own line instead of costing
  an evening of guessing — send me that file (or just say it happened and I
  will read it).
* **Does the man chase and hit back?** The `AGGRO` line proves he learns the
  player; whether he closes and swings needs a test where the harness can aim
  (this machine will not warp the cursor, so swings at a man only connect by
  luck of the arc).
* **"A crazy amount of wood"** — still unverified; unknown action.
* Every other `plog.log` per entity per frame (there may be more) deserves the
  same rate limiter as `plog` should own (B6.3).

## 2026-XX-XX -- FOUND BY PHYSICAL TESTING (the folder / leader / manhunt chain)

Fixed because the real game proved them broken, not the harness:

- **The body panel and the folder panel could not be opened.** `body_open` and
  `folder_open` were *read* in the draw and the input loop and **never set** --
  the click branches had never been written. Clicking a corpse did nothing;
  a Secret Folder in the hand did nothing. Both now open on a left click, and a
  body opens whatever is in his hand (an axe is not swung at a corpse).
- **Corpses were never drawn.** `corpse_mod.draw` was called by nobody: a body
  could be clicked and looted and never once appeared on screen. Bodies are now
  sorted into the world's painter list by depth.
- **Only some panels drew outdoors.** `chest_panel`, `worker_panel`,
  `stall_panel`, `body_panel` and `folder_panel` were drawn ONLY inside the
  house branch, so above ground they opened to a state change and nothing on
  screen. All of them are drawn in the outdoor pass now.
- **A hired man's pack was lost on death.** The death record carried `stock`
  only; his goods live in `bag`. Workers' bodies were empty. The bag now
  travels to the corpse, stack by stack, with quality and payload.
- **The service's standing facts had no text.** A folder showed
  "agent npc_-3_-3_30 hub False place Golden Bend". Place/roster/chief facts
  now read as sentences: "THE SERVICE OPERATES IN GOLDEN BEND -- I am posted
  there."
- **The hunting party could be sent off the map** (`at` was the outer-ring
  place). The dispatch point is clamped to +-90,000.
- **The folder's place facts.** A body now carries one per place he was told
  about (60 of them); the first page is a list of postings, which is honest but
  long -- a cap or a "places" section is a design decision, not a bug.

THE PARTY THAT VANISHED -- FOUND AND FIXED (three separate faults, each one
enough to make the manhunt a no-op):

- **The distance cull ate them.** main.py's per-frame cull keeps an enemy only
  if it is `follow`, holds a gate, patrols, or is within 6,500 px of the
  PLAYER. The party spawns 620 px from the *place*, not from the player, so any
  time the Kingpin was not already standing there the ten men were created,
  logged `MANHUNT dispatched 10 men ...`, and deleted in the same frame. The
  party is now exempt from that cull: it is sent to a place and stands there.
- **In test mode the party hunted the observer.** `creatures.choose_target` is
  handed `watcher` instead of `player` when the game runs in TEST MODE, and the
  manhunt branch used that argument: ten armed men marched to the yard and
  stared at nothing (`targeting: nothing`, 0 damage). The branch now reads
  `creature._player` -- the real Kingpin -- and the same run measured
  `targeting: THE PLAYER` from 274 px and **779 damage** in 21 s.
- **E with a body open opened the pack and froze the world.** The body/folder
  panels are not in the `BLOCKED` guard list, so an E press that missed its
  panel fell through to the general interact handler, set `inventory_open`, and
  the world branch stopped running (`BLOCKED inv True` in the log, `now`
  stopped advancing). A probe that then waited for a frame was waiting for a
  frozen game. (Logged, not yet fixed: a panel that is open should swallow E.)

The party is signed off as measured in the real game: 10 alive, marching to
the clamped dispatch point, acquiring the player by sight, and hurting him.

## THE DISPATCH IS NOW A MARCH (his correction, implemented)

It used to be a spawn: ten soldiers conjured in a 620 px ring around the target,
carrying numbers written onto the object, with no cost and no road. That was
wrong in every part of "dispatch".

What it does now (`manhunt.dispatch`), measured in the running game:

- **THE TEN BEST WARRIORS IN THE KINGDOM.** Chosen from that nation's own
  soldiers by **melee and stamina** -- the skills `axe` and `movement`, with
  `shooting` at half weight -- and only men above `MIN_SKILL = 0.5` count; a
  levied guard who has never swung an axe is not a warrior. If the nation has
  fewer than ten worthy men, the crown **raises the rest at its own seat** with
  top-band skills (axe .875, movement .875, shooting .75, 170 hp).
  Logged: `| raised 10 | best skill 2.12`.
- **KIT ISSUED, NOT CONJURED.** A rifle, 60 rounds and 50 rations, given only
  to a man who does not already have them (`_kit`).
- **THE CROWN PAYS AT ONCE.** `COST_PER_MAN = 150` gold per man, deducted the
  same frame from the seat's `ledger_coins` and booked with `economy.flow(...,
  "pay_manhunt", -cost)`. A crown that cannot afford ten sends fewer; one that
  cannot afford one sends nobody. Logged:
  `from Raven Reach | paid 1500 | ledger now 1048`.
- **THEY WALK.** They are detached from their gate/patrol/column
  (`_detach`) and given `march_target` = the place the news came from; the
  game's own march code moves them at column speed. Measured: sent from
  **11,921 px away**, closing **6,285 px in 30 s**, alive the whole way.
- **THEN THEY HUNT.** Within sight of the place they acquire the Kingpin and
  every named man of his (`targeting: THE PLAYER`, 779 damage measured in the
  earlier run once they were on top of him).

## SOLDIERS, THE DUMMY AND THE RANGE (built, and measured in the game)

- **A soldier is a trade.** `work.TRADES` has `("soldier", "soldier")`, paid
  **double a farmer** (`pay("soldier") == 2 * pay("farm")`, measured 40 vs 20).
  A soldier's post is a training building: `slots("soldier")` counts dummies
  and targets, one man to a post.
- **HE IS HIRED FOR HIS WAGE LIKE ANY OTHER MAN -- arming him is the player's
  business, whenever he feels like it.** His pack is a container the player can
  open, so an axe or a gun and rounds go in later, not as a condition of the
  hire. Measured: hired with nothing in his pocket (`his bag: []`, `kit: None`,
  wage 40) -> no training at all, and he says *"I have no weapon to train
  with."* A man who walks in with his own axe is already armed.
- **HE FIGHTS WITH WHAT HE CARRIES**, re-read every frame: shotgun -> rifle ->
  axe, and **an empty gun is a club**, so no rounds and an axe in the bag means
  the axe (`soldier_kit`). **His post follows the weapon**: put an axe in his
  pack and he goes to the dummy, add a rifle and rounds and he moves himself to
  the target -- measured: `kit: axe -> post dummy` (axe 3.01 days), then
  `kit: rifle -> post target`, one round spent, `shot 0.0000 -> 0.0200`.
- **Training dummy** (40 wood) and **archery target** (60 wood), both built
  outside, both `industry.Workplace` kinds with their own art, and both
  animated: the dummy takes a blow every 1.2 s (axe biting in, straw jumping),
  the target takes a round with dust and a spark.
- **Melee: three days from nothing to master.** Measured in the running game:
  `axe 0.0000 -> 0.0153 in 28 s = 0.000554/s -> 3.01 days for a full point`.
- **Ranged: five days, one shot a minute, ten rounds a day.** Measured:
  `ammo 60 -> 59 | shot 0.0000 -> 0.0200` for one shot; 10 shots a day x 0.02
  = 1.0 in exactly 5 days. The range draws from his pouch, then the chest.
- The dummy/target kinds are new to `industry.Workplace` (sizes, `_render_*`,
  `train_flash` / `shot_flash`), and `build.py` has the two entries and icons.

### FOUND ON THE WAY: EVERY TRADE WAS WORKING THREE TIMES TOO FAST

`work.produce(...)` was called **once per frame** with `world_dt` -- the step
of the world tick, not the frame's. At 60 fps and a 0.05 s tick, a day of work
passed in about three and a half real minutes instead of ten. Measured through
the soldier's training rate: 0.82 days for a full melee point instead of 3.
The call now passes the frame's own `dt`; the same measurement gives 3.01 days.
Every batch recipe (90 s batches, crops, smithing) was running at the wrong
clock because of it.

## ONE BODY FOR EVERYBODY (player health standard, applied)

The player's body is **`stats.PLAYER_MAX_HEALTH = 115`** and that is now the
only body in the world. Measured in a running game (1830 `village.NPC`
instances, 72 `Soldier`s, 185 defenders, 116 agents, 756 plain villagers, the
truth-teller, the player):

    villager   115 | defender   115 | agent 115 | Soldier 115 | Player 115
    truth-teller 115 (and 5000 damage does not move him: the rule is a flag
    now, not a million hit points)

Changed to the standard: villagers 40, defenders 70, levied/standing soldiers
95, the player's own squad 160, the crown's raised men 170, bandits 100, and
the truth-teller's 1,000,000. **Old saves are lifted on load**: a man written
down with 40 health gets the extra body added to what is left of him
(`village.NPC.__setstate__`), so a wounded man stays wounded but every man now
has 115 to lose.

Not changed, deliberately: **wolves** (52, and 70 for the bigger kind) and
**rabbits** (12) -- they are animals, not people. Say the word and they match
too.

## GUNS ARE DANGEROUS NOW (measured)

    guns.DAMAGE  = {rifle: 80, shotgun: 80}      # ONE ROUND TAKES 80 HEALTH
    guns.PELLETS = {rifle: 1,  shotgun: 12}      # a fistful, not three
    guns.FIRE_CD = {rifle: 0.0, shotgun: 0.62}   # a rifle has NO cool-down
    guns.RELOAD_LO/HI[shotgun] = 2.0 / 2.0      # the pump takes two seconds
                                                # at any skill

- A round takes **80 health**, measured on a real man: `health 400 -> 320`.
  A levy (115) goes down in two; a master of the axe or gun (180) in three.
- **The shotgun reloads in 2.00 seconds**, at any skill (the rifle stays 3.0 s
  at nothing and 1.0 s at master). Measured in the game: `R` on an empty
  shotgun took **1.946 s** wall-clock to load three rounds (the game's own
  clock says 2.00; the difference is the frame the press lands in).
- **A rifle has no firing cool-down**: one click, one round, as fast as the
  player clicks. Measured: two clicks 50 ms apart spent **two rounds**
  (`magazine 10 -> 8`, `cool-down 0.00`). The shotgun still has to be pumped.
- **The shotgun fires twelve projectiles**, each doing the same 80. At
  point-blank that is enough to drop anything in the world; at range the spread
  means only part of the pattern lands. NPCs fire the same gun, so this cuts
  both ways.
- **It costs the frame nothing.** A six-second barrage of 271 trigger pulls
  (3,252 projectiles spawned) held the frame at `dt 0.016-0.018` -- sixty
  frames a second throughout, read off the game's own HEARTBEAT.
- **SKILL IS BODY.** `stats.body_for` gives 115 at no skill and **180** at
  master of the axe or the gun, linear in `max(axe, shooting)`. Measured:
  `novice 115 | master of the axe 180 | master of the gun 180`. It applies to
  the player, every villager (checked once a second in `NPC.update`), every
  soldier (each frame), every trained worker (on each gain), and it is added to
  whatever health is left -- training does not heal a man, it just gives him
  more to lose.

## FOUND AT THE GATE: HE MAKES SPACE AND SHOOTS (verified in the game)

The search guard no longer starts shooting with a hand still in the man's pack.
On a find (`gate.begin_caught`):

1. **The player is told** -- `toast("Searched. N found. Run.")`, the message
   above the inventory, at t = 0.
2. **The guard steps back** -- one clean 34 px step (a per-frame nudge lost the
   argument with his own feet), still facing the man, and his own attack clock
   is held at the fuse so no other round can leave early.
3. **At 0.5 s he fires**, from his own gun and his own magazine
   (`gate.fire_shot` -> the guard's `_shoot`), and only then does the town
   erupt (`commit_crime` moves out of the find and onto the shot).

Measured, in a fresh world, at a real gate:

    CAUGHT-FOUND  Ash Springs 400 unit(s) | the guard makes space and fires in 0.5 s
    CAUGHT-SPACE  the guard of Ash Springs stepped back 34 px
    CAUGHT-SHOT   the guard fires at Ash Springs after 0.52 s and 79 px
    CAUGHT-SHOT   the guard fired from 79 px | mag now 9
    FIRST SHOT:   health 115 -> 35 | 0.543 s after he found it

Two things this exposed, both fixed:

- **The guard the frame does not simulate never fires.** Town soldiers are
  sometimes walked by a lane and not by the frame the player is in, so leaving
  the first round to "his own update" meant no round at all -- measured: he
  stood there, hostile, `fire_cd 0.0`, `mag 10`, and never pulled the trigger.
  The fuse's round is now fired by the guard himself, through the game's own
  `_shoot`, wherever he lives.
- **The searching guard is remembered across `reset()`** (`gate._LAST_GUARD`),
  which is why the standoff used to lose him and shoot nobody.

A guard carrying a shotgun kills a full-health player with that first shell
(12 x 80 at 79 px, measured 115 -> 0 in an earlier run) -- which is the gun
being dangerous, not a bug.

## A MAN BUYS ONLY WHAT HE NEEDS IN A DAY (the new rule, measured)

The town market already stopped at `economy.wants`, but the player's sale path
trusted the buyer's stock -- and a man the frame is not walking has whatever
stock he had when he was last near the player. So the same eight logs could be
sold to the same man all day, and a village could end destitute with a
woodpile.

The trade menu now keeps a **per-buyer, per-day budget** (`trade.daily_left`,
`trade.record_sale`, reset on the game clock's day boundary):

    3 days' worth of a good   15 wood, 6 bread, 3 cigars, 24 iron, 10 ammo...
    1 tool (or gun)           1 axe, 1 pickaxe, 1 shovel, 1 rifle a day
    30 seeds in all           30 wheat seed, whatever the kinds

"a day's worth" comes from what was measured in a running game (see NEEDS.md):
2 food a day (measured 1.69), 5 logs a house, 1 cigar or drink an addict,
8 leaf at the bench, 8 iron at the forge, 10 rounds at the range.

Measured in the game, with a buyer given a bottomless purse and endless demand:

    wood        player had 500 | after twelve attempts he still has 485  (sold 15)
    wheat_seed  he bought none -- an idler wants no seed -- budget left 30
    axe         he bought none -- he needs no tool -- budget left 1
    coin        his purse went from 100000 to 99985, and not a coin more

and the ledger on its own:

    a fresh day:  wood 15, bread 6, cigar 3, iron 24, seeds 30, tool 1
    after 15 wood / 30 seeds / 1 axe:  wood 0, seeds 0, tool 0 -- bread still 6
    next day:     wood 15, seeds 30, tool 1 again
