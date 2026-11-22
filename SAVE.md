# SAVE CONTRACT — SettleWest

This is the rulebook for the save system in `save/`. Read it before adding a
field, a settlement, a built object, a system, or a new kind of animal.

The old system (`savegame.py`, `chunksave.py`, `worldio.py`) is **gone**. It
pickled live objects and a hand-picked `SimpleNamespace`, wrote the pickle into
`save_0.json`, and read a JSON seed from the same file — so the seed was lost
and the native camps (the actual game) were never saved. Do not reintroduce a
pickled object graph or a hand-written payload dict.

---

## 1. One save, one manifest, many chunks

```
saves/slot_N/
    save.json            manifest: small, atomic, checksummed
    save.prev.json       the manifest replaced last time (manual recovery)
    new_game.json        seed chosen at the title screen, before play
    chunks/
        g<generation>/built.json       houses, chests, fences, plots, work, blocks, signs
        g<generation>/animals.json     horses, bison, wolves, rabbits + saddle bags
        g<generation>/camps/<uid>.json one self-contained native settlement
        g<generation>/terrain/<rx>_<ry>.json  8 km region of plots/trees/ore/wild
```

- Write chunks first, manifest last. Both are `tmp + fsync + os.replace`.
- Each chunk is canonical JSON, gzip-compressed, keyed by SHA-1 in the
  manifest. A chunk whose bytes did not change keeps its old path (nothing is
  rewritten); a changed chunk gets a path under `g<generation>/`, so the
  previous manifest never points at overwritten bytes. Cleanup keeps the
  current and previous manifests' files, and removes older generations.
- `save.prev.json` is a manifest backup, not a second save slot.
- `saves/_legacy/` holds files moved out of the way from the old format.
  It can be deleted by hand; it is never read.

`save/store.py` owns all disk I/O. `save/schema.py` owns the versions.

---

## 2. Versions and migrations

- `SCHEMA_VERSION` — the shape of the state document. Bump for any changed key
  or meaning. Add a migration to `schema._MIGRATIONS`.
- `WORLD_VERSION` — the generated world's layout rules (camp spacing, field
  sizes, camp contents). A save laid out by different rules is refused, not
  half-read. Bump it when `native.build` or world geometry changes in a way
  that makes saved positions mean different ground.
- Refuse a save from a newer schema. Never silently ignore a bad checksum or
  a corrupt chunk: log and abort, preserving the file.

Old saves are **dropped** by decision. `_legacy/` keeps them for reference.

---

## 3. Stable identity

Never save `id(obj)`, a list index, or an object graph.

- Every persisted object gets `_save_uid` (`codec.uid(obj, prefix)`), assigned
  the first time it is written and restored from the save afterwards.
  - camps: `camp:<hex>`
  - people: `person:<hex>`
  - built objects: `house:<hex>`, `work:<hex>`, `chest:<hex>`, `sign:<hex>`,
    `foodbox:<hex>`
  - animals: `animal:<hex>`
  - hand-planted trees: `tree:<hex>` (`Tree.__slots__` includes it)
- References across domains are saved as these ids: `native_camp`, `workplace`,
  `home_house`, `bond_partner`, `breed_partner`, `escort_horse`, `worker`,
  `riding`, `player_camps`, `orchard_state["tree"]`.
- Assign ids during the snapshot with `codec.idref(obj, prefix)` when the
  reference may be written before its owner's step. Snapshot steps have a
  fixed order; `idref` makes the id stable across that order.

---

## 4. What is saved, and by whom

| Provider | State |
|---|---|
| `save/meta.py` | seed, spawn, ship berth, `now`, kills, war alarms, conquered count |
| `save/player.py` | every plain Player field (armour, magazines, debt, origin, body, facing), all six skills, pack, held stack, location (world / house door / mine exit / horse) |
| `save/systems.py` | research cards/active/points, market base/sold/history/day, ship hold, compass, player camps, riding |
| `save/built.py` | houses + interiors (chests, benches, barrels), fences, gates, plots, workplaces + workers, 1×1 blocks, chests, sign-posts, feed boxes, field designations |
| `save/terrain.py` | plots and planting times, tile overrides, wild picked/eaten/forced, wild permanent clearing (derived from camps/blocks), felled stumps, hand-planted trees, ore mined + strikes |
| `save/camps.py` | every native settlement: conquered state, nation, ledgers, fields, orchards, job rosters, people, animals, breeding, the camp's own world state |
| `save/people.py` | one person: every simple field (Cython `cdef` included), skills, pack/stock, job, role, health, home/work/bond references |
| `save/animals.py` | horse/bison/wolf/rabbit simple fields, saddle-bag inventory, breed/escort references |

### Deliberately derived, not saved

- render surfaces, sprite caches, `rng` objects, `_field_task`, `_trunks_*`,
  `_interior_rect`, `_saved`, threat lists, per-frame flashes/timers.
- `wild_cleared` (a camp's ring / a placed block). `native.build` re-marks camp
  rings; `built_blocks` re-marks player blocks on load.
- old village lattice, hubs, war columns, trains, stalls, corpses, folders,
  secret-police marks. These are legacy and are dropped by decision.

### Known legacy not persisted

`g.hub_world`, `g._TEST_TRAIN`, `g.armies`, `g.patrols`, `g.player.squad`,
`g.active_chaos`, corpse/folder registries, legacy `Village`/`House` state.
They reset on load. If one becomes live gameplay again, give it a provider
rather than a hand-written dict.

---

## 5. Load order (fixed)

1. Read and validate the manifest (seed, versions, checksum).
2. Build `World`, trees, ore, empty legacy villages from the seed.
3. Read all chunks.
4. Put the player's **saved world position** in place. The home/starter camps
   are built around it; never overwrite it with the spawn.
5. `built.restore` (houses and player work exist first).
6. `terrain.apply` (saved plots/trees/ore replace the generated ones).
7. `camps.prepare` (rebuild every saved camp at its saved x/y/seed; then
   `native.ensure_near` for camps the save has never seen).
8. `animals.restore_all`.
9. `camps.apply` (people, lists, orchards, breeding, animals).
10. `player.apply` (location mode, pack, skills).
11. `systems.apply` (research/market/ship/compass/camps).
12. `built.finalize`; resolve deferred references.
13. Camera and ground refresh around the player. Start the loop.

`native.build` must not overwrite a saved plot (`world.plot_at` guard) and
must not clear hand-planted trees or stumps when rebuilding a **saved** camp
(`clear_planted=False, clear_stumps=False`). It still clears wild caches and
re-marks the camp ring.

---

## 6. When a save happens

- **Autosave every 5 minutes**, composed a few milliseconds per frame and
  written on a worker thread. It overwrites the same slot; there is no
  accumulating autosave file.
- **Safe exit** (window close, pause → exit, end of `main`) finishes any
  snapshot and writes synchronously.
- Action-driven `g.save_now()` calls only *request* a lazy save; they are
  coalesced and debounced. They do not write in the action's frame.
- Never save while dead/game-over; the autosave timer skips those states.
- Time advances only while playing. There is no offline simulation.

A save is one generation. Chunks are written first and the manifest last with
their hashes, so a crash leaves the previous save usable.

---

## 7. Rules for future development

1. **Every new simple field is saved automatically** by `codec.dump_fields`.
   If it must *not* be saved, add its name to the provider's `SKIP` set with a
   reason. The audit log (`saves/save_audit.log`) names every non-plain field
   that was skipped.
2. **Every new object reference needs an id and a resolver.** Add the field to
   the provider's `SKIP`, write `codec.idref(obj, prefix)` in `snapshot`, and
   resolve it in `apply`/`finalize` through `Context`. If you skip this, the
   audit will show the field as "not plain data" and the reference will be
   lost.
3. **Every new persisted class needs `_save_uid` support.** If it uses
   `__slots__`, add `"_save_uid"` to the slots. If it is a Cython `cdef class`,
   make sure it has `__dict__` (as `NPC` does) or add the field to the pxd.
4. **Never write a hand-picked payload.** A new system gets a provider in
   `save/`, with its own `snapshot`, `apply`, and `SKIP`. Do not extend a
   `SimpleNamespace` in `main.py`.
5. **Never use list indices or `id()` as a saved reference.**
6. **Bump and migrate.** Any shape change gets a `SCHEMA_VERSION` bump and a
   migration + fixture. Any layout change gets a `WORLD_VERSION` bump.
7. **Run the round-trip before building.** `build.sh` runs
   `tools/save_selftest.py make` and `verify`; it refuses to build if the
   world does not come back. Use it after every save change.
8. **The test must cover the new thing.** Add the field to the self-test's
   expected snapshot and prove it round-trips, not just that the file exists.
9. **No pickle of live game objects.** Plain data only.
