# WHO OWNS WHAT — the accounting, resolved

Every line below was read from the source, with the evidence. Where I was
previously "unsure", the answer is here, and the reason it's the answer.

The test for every item: **would this still be true, and still need doing, if
every other villager and the town itself vanished?** Yes → the villager's.
No → the town's. It needs the building but not the people → the house's.

---

# 1. THE VILLAGE

## 1.1 State it owns
| field | evidence / why it is the town's |
|---|---|
| `nation`, `gx`, `gy`, `name`, `code`, `radius`, `scale`, `is_capital`, `capacity` | identity; `nation` is read by guards, the crown, armies |
| `ledger_coins`, `ledger_goods` | the granary and the purse. Every `economy.pay_*` moves these |
| `prices` | the town's own asking prices |
| `houses`, `workplaces`, `farm_plots`, `farm_tiles`, `fences`, `fence_walls`, `gate`, `gate2`, `board`, `plaza`, `plaza_radius`, `roads`, `mines`, `stone_chunks()` | the physical town |
| `guards`, `patrol`, `_armed`, `duty_day` | the standing watch and its roster |
| `provoked`, `battle`, `chaos`, `conquered`, `plundered`, `_routed`, `_exodus`, `last_death` | the town's condition |
| `_seeded`, `_phase`, `_share_timer`, `_market_timer`, `_day`, `_log_day` | the town's own clocks |
| `registry` | the world |

## 1.2 Work it owns
| work | where | why the town |
|---|---|---|
| the daily books | `pay_wages`, `tax_day`, `crown_dues`, `pay_crown`, `tithe_food`, `pay_mayor`, `crown_arms_order`, `pay_garrison` — all `(village, day)`, all guarded by `day` | they move the *ledger* and the crown's treasury |
| its own trade | the ledger's buying and selling, `trade_routes` (its neighbour list) | the town's knowledge of its neighbours |
| the auction | `economy.market(self)` | organising a place and a time is the town's; the trading is the people's |
| the watch roster | `_rotate_duty(day)` + `_assign_duty_bodies()` | needs the whole list; sets `duty`/`on_duty` **on each man** |
| — the watch, in detail | `_rotate_duty` picks five men by `duty_group`, sets `duty="armed"`, `on_duty=True`, and `_assign_duty_bodies` points a **guard body** at each of them (`guard.owner = man`). | The guard is the *town's* body and stands outside the roster; the man it stands for is `on_duty` and therefore **does not step himself** (`NPC.update` returns early). So a man's step can be delegated to a body that is stepped elsewhere. Any refactor of "who steps whom" must keep this pair together. |
| which posts exist | `staffing()`, `vacancies()`, `_fill_vacancies()`, `free_post(npc)` | the posts are the town's plots and workplaces |
| planting its plots | `_seed_fields(world, now)` | the plots are the town's |
| the roster | `birth(parent)`, `alive_count()`, `can_grow(now)` | adding a person to the world is the town's bookkeeping — name pool, id counter, `capacity`, peace check |
| calling a muster | `defenders()`, `provoke()` | the town's decision; applied to each man |
| noticing a death | the `any(not npc.alive …)` sweep and the `npcs` list prune in `update` | the roster shrank |
| the player's taxes | `board` / `tax_due` | the town levies it |

## 1.3 What is in `Village.update` today that is NOT the town's — all of it misfiled
| line | what it does | whose |
|---|---|---|
| `for npc in self.npcs: npc.update(...)` | **the town drives every citizen** | the citizen's own step |
| `economy.tick(self, npc, dt)` | hunger, craving, healing, eating, foraging, consumption, starvation | the man's |
| `economy.household_share(house, 1.0, self)` | the family larder and the fire | **the house's** |
| `_pair_social()` | shuffles the town and pairs people for the evening | the people's — a man finds his own partner; the town only says it is evening |
| the trader-debt bookkeeping on death | `home.caravans -= 1`, `trader_deaths += 1` | the registry's tally; the debt is the man's |

## 1.4 Collective knowledge — RESOLVED
`killers` + `killer_since`, and `news`. Who reads them:
- `main.py:3083-3090` — when the town knows killers, the **soldiers inside its radius are told**.
- `village.py:937` — a trader at a stop does `self.learn(stop.killers, now)`.
- `war.py:134` — `capital.news` is what the crown pays for.

So the town's copy exists for exactly two jobs: **tell a body of men at once**,
and **be the thing a traveller asks**. Both are *sourcing from the living people*.
**Ruling: keep them, but as a summary of what its living people know, refreshed
when someone arrives — never a memory that outlives the men.** `learn_killers`
already writes both the town's copy and every man's, so the town's is a cache.
`forget_killers` should become "recompute from the people".

## 1.5 Dead code with a builder inside it — DELETE
`trade_neighbour()` (village.py:2575) is **never called** — grep finds only its
own body. Inside it:
```python
        for r in range(1, 5):                 # up to 164 cells
                    cand = registry.get(self.gx + dx, self.gy + dy)   # BUILDS
```
Delete it. `trade_routes()` (same job, already fixed) is what is used.

---

# 2. THE INDIVIDUAL VILLAGER

## 2.1 State he owns — every one of these is on `self`, and that is correct
`x`, `y`, `facing`, `_dir`, `_px`, `_py`, `speed`, `base_speed`, `health`,
`max_health`, `hunger`, `stamina`, `stuck`, `pause`, `_steer_timer`,
`_steer_slot` · `coins`, `stock`, `grade`, `book_in`, `book_out`, `loan`,
`loan_clock` · `home_house`, `home_door`, `asleep`, `in_interior`, `_saved`,
`_interior_rect`, `_interior_colliders` · `job`, `workplace`, `farm_plot`,
`farm_plots`, `tool_uses`, `tool_orders`, `tool_reserved`, `tool_keep`, `duty`,
`duty_group`, `on_duty`, `schedule`, `target` · `skills` · `weapon`, `armed`,
`ranged`, `gun_kind`, `mag`, `ammo`, `reload_timer`, `attack_cd`, `combat_speed`,
`melee`, `melee_damage`, `aggro`, `panic`, `flee`, `aware`, `hostile`,
`defender`, `is_commander`, `guard_village`, `patrol_center` · `trade_state`,
`trade_home`, `trade_stop`, `trade_dest`, `trade_item`, `trade_back`,
`trade_stops`, `caravans`, `quality_pref`, `restock_timer`, `trade_demand`,
`paid` · `addiction`, `yearning`, `wants_product`, `wants_drink`, `use_fx` ·
`bond_partner`, `social_target`, `_market_spot` · `knows`, `known_since`,
`witness_to`, `news`, `king_run`, `refuge`, `refuge_eta` · `id`, `name`, `role`,
`rng`, `village`, `home`.

## 2.2 Work he owns — his entire step
Everything in `NPC.update` (366): `forget` · `_tick_gun` · restock · refuge
`_flee_village` · `_predator_near` · `_fight` · the trade run (`_trade_step`,
`_trade_start`, `_trade_end`, `_trade_load/unload`, `_trade_buy/sell`,
`_best_next_stop`, `_take_provisions`) · `_mosey` · panic · `pause` ·
`_socialize` · `_go_to_market` · `_work_field` · `_work_woods` · `_work_place` ·
`industry.produce` · sleeping at the door · `_pick_target` · `steering.steer` ·
movement · `skills.gain_*` · `_seek_goods` · `arm()` · `learn`/`forget`/`witness`.

**And everything in `economy.tick`** (economy.py:1330): hunger, craving,
healing, eating, foraging, the loan clock, consumption, **starvation**. The town
is a service he *calls*: the granary (`dole`), the bank (`tool_loan`,
`forge_loan`, `service_loan`), the order book (`place_orders`).

---

# 3. THE HOUSE — the owner nobody named
`warmth`, `door_broken`, `occupants`, `garden`, `interior`, `image`.
Work: **`economy.household_share(house, dt, village)`** — a family shares a larder
and burns a log at a time. That is why `tick` needs `house.warmth` to know if a
man is cold. Neither the town's nor quite one man's.

---

# 4. THE WORLD
`Villages`: the laid-out towns, `trade_active`, `trader_deaths`, `send_idle`.
`war`: armies, `STANDING`, campaigns, the news of the war, the crown's demand.
`creatures`: enemies, patrols, wolves. `biomes`/`world`/`trees`/`ore`: the ground.

## 4.1 `trade_active` — RESOLVED, and it is a scheduling artefact
Written: `village.py:884` (a trader picks his next stop) and `main.py:3149`
(rebuilt every tick). Read: `main.py:3140` and `3333` — only ever to decide
**which extra villages to step**. It exists because a trader walking to a town
must keep walking when that town is off-screen.
**In the target design it disappears**: the trader steps himself, wherever he is.

---

# 5. THE SYSTEMIC BUG: BUILDERS AT PLAY TIME

The world is supposed to be finished before the first step. Anything that calls
`villages.get()` once play has started is **constructing a village mid-frame** —
50–80 ms each. Live ones:
| where | what | verdict |
|---|---|---|
| `village.py:2523` `capital()` | `registry.get(gx, gy)` | **must be a lookup** |
| `village.py:2599` `trade_neighbour()` | up to 164 builds | **dead code — delete** |
| `main.py:319/349/354/2129` | the save load and `world_from_data` | load time, but must not reach outside the world |
| `main.py:3141/3153` | `trade_active` lookups | keys that came from a trader's own target — already built |
| `worldmap.py:191` | the map's markers | fine while drawing; uses `get` where a lookup will do |
| `main.py:396/408` | the loading screen | correct — this is the one that should build |

**Rule to enforce: after `load_world`, `Villages.get()` is never called again.**

---

# 6. CALL FREQUENCY — the multiplicity, measured
`Village.update` has four call sites: the visible loop, the `trade_active` loop,
the house-interior loop, and the off-screen loop.
Measured with the off-screen loop on: **117 village updates per frame for 64
villages; 9,698 `NPC.update` calls per frame for 3,177 people (3×).**
A village cannot be stepped once and its people three times. One cause is already
found and fixed: the off-screen loop did not skip `trade_active` villages, so
those were stepped twice. **The remainder must be settled before the refactor**,
because once a man triggers his own step, a multiplicity there is invisible.

---

# 7. THE REFACTOR (agreed shape, not started)
1. `NPC.tick(dt, world, now, phase)` — his needs and his whole step, in one call.
   No town in the loop.
2. `Village.update(dt, now, world)` — the daily books, its trade, its roster, its
   condition. **No loop over `self.npcs`.**
3. The people are walked once per tick from **a flat registry of people**, not
   from 64 nested loops. That is what replaces `trade_active`, `visible_villages`
   driving updates, and the house-window loop.
4. `economy.tick` splits: personal half → `NPC.tick`; the service half stays as
   functions he calls.
5. `household_share` → the house.
6. Delete `trade_neighbour` and `trade_active`.
7. Every remaining `villages.get()` at play time becomes a lookup.
