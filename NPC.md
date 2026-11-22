# NPC.md — MBTI, TRAITS, MOOD, BREAKS, DOCTOR, AND PLAYER PERSONALITY

This is the design and build contract for the NPC rework. It is deliberately
written before the code, because this system touches every man in the world,
the save file, the job system, conversations, combat, built objects, the UI,
and the player. It is to be built in **phases**, and **each phase is physically
tested in test mode by the player before the next phase begins**.

The rule for this work:

> **We do not move to the next phase until the current mechanic has been
> played, seen, and confirmed in test mode.**

No "it should work". Every phase has a scenario, exact player actions, and an
expected visible result.

**Confirmed decisions:**

1. The Doctor’s station is a **Medicine Hut**, not a clinic.
2. No player traits in this pass. The player’s MBTI is live: it has a rolled
   starting type, then decays and is overwritten by what the player actually
   does; letters can flip mid-playthrough.
3. The real-world MBTI distribution in §2.5 is approved.
4. The S/N job table in §2.2 is the working default (Smith/Gunsmith S;
   Artisan/Researcher/Doctor N).
5. NPC types are a weighted random draw. The player is “first random, then
   whatever the player does” — a rolled prior that live behaviour outweighs.

---

# 1. THE MODEL IN ONE PARAGRAPH

Every person — NPC and player — has a four-letter **MBTI-like mind type** and,
for NPCs, a set of **traits**. The mind type decides how a person starts
conversations, which jobs they are naturally good or bad at, how they hold and
release frustration, and how they respond to being wronged. Traits are born
(Smart, Stupid, Strong) or earned in life (Green Thumb, Traumatized) and have
explicit MBTI rules. Mood is a RimWorld-like collection of thoughts — insulted,
hungry, slept outside, craving — that push a target mood up or down. When mood
stays low, a person suffers **minor breaks** (sad, annoyed) and then **major
breaks** (berserk, breaking spree). A **Doctor** turns tobacco, dried mushroom
and any alcohol into **medicine**, delivers it to settlement people, heals them
fully, and permanently unlocks that person's **mental state panel** for the
player. The player's own MBTI is not chosen: it is inferred from how the player
actually behaves across the playthrough.

---

# 2. THE MBTI-LIKE AXES

The four axes are used mechanically, not just as labels.

## 2.1 I / E — how conversation starts

- **E (Extraversion):** initiates conversations. In NPC-to-NPC social code, an
  E man speaks first on his cooldown. He is also more likely to speak to the
  player unprompted.
- **I (Introversion):** mostly responds. An I man does not start NPC-to-NPC
  chat on his own; he answers when spoken to. He is much less likely to
  initiate a cloud at the player, but still responds when the player talks to
  him or when another NPC engages him.

For the player, E/I is inferred from **initiated conversations vs. conversations
the player only answered**.

## 2.2 S / N — what kind of work suits the mind

Sensing minds are concrete and hands-on. Intuitive minds are abstract and
systemic.

**Job affinity is a single table**; a person gets a bonus on their own side and
a penalty on the opposite side.

| Job | Primary axis |
|---|---|
| farmer | **S** |
| logger | **S** |
| soldier | **S** |
| miner | **S** |
| weaver | **S** |
| spiceman | **S** |
| animal_handler | **S** |
| smith | **S** |
| gunsmith | **S** |
| artisan | **N** |
| researcher | **N** |
| doctor | **N** |
| manager (future) | **N** |
| brewer (future) | **N** |
| trader (legacy) | **N** |
| mayor / king (legacy) | **N** |

Effects, before trait multipliers:

- **Match:** +15% work speed, +25% skill gain in the job's skills.
- **Opposite:** −15% work speed, −25% skill gain.
- **Neutral / no job:** no effect.

This is one table (`JOB_AXIS`), so any classification can be changed in one
line. If a job should be neutral, remove it from the table.

## 2.3 F / T — how frustration is held and released

- **Feeling (F):** breaks **more often but less severely**. Lower threshold for
  minor breaks; major breaks are rarer; minor breaks recover faster. F types
  are also **better artisans** (+15% artisan work speed and +5% output quality).
- **Thinking (T):** bottles frustration longer. Higher tolerance before minor
  breaks; major breaks are rarer but **stronger** when they happen: +50% break
  intensity and +30% break duration. T types accumulate a `frustration` value
  from insults/wrongs, which raises major-break intensity.

Exact thresholds and probabilities are in §4.

## 2.4 J / P — grudges and mercy

- **Judging (J):** holds a grudge. Opinion penalties from being wronged/insulted
  are 25% larger and last longer. Breaks recover slightly slower.
- **Perceiving (P):** lets it go. Mood and break recovery are 20% faster; opinion
  penalties are normal.

For the player, J/P is inferred from **retaliation vs. mercy toward conquered
NPCs who attack or slight him**.

## 2.5 Real-world distribution

Each NPC is assigned a type at generation, deterministically from their stable
id, so a reload never rerolls them. The weights are the commonly cited US
adult MBTI distribution, rounded to sum to exactly 100. They live in one table
and can be tuned.

| Type | % | Type | % |
|---|---:|---|---:|
| ISFJ | 13.8 | ESFJ | 12.3 |
| ISTJ | 11.6 | ESTJ | 8.7 |
| ISFP | 8.8 | ESFP | 8.2 |
| ENFP | 8.1 | ISTP | 5.4 |
| INFP | 4.4 | ESTP | 4.3 |
| INTP | 3.3 | ENTP | 3.2 |
| ENFJ | 2.5 | INTJ | 2.1 |
| ENTJ | 1.8 | INFJ | 1.5 |

Axis totals implied by the table (for verification):

- I ≈ 50.9%, E ≈ 49.1%
- S ≈ 73.1%, N ≈ 26.9%
- F ≈ 59.6%, T ≈ 40.4%
- J ≈ 54.3%, P ≈ 45.7%

**NPC types are a weighted random draw at generation and do not change.** The
**player does not get a rolled type that stays**; the player starts from a rolled
prior and is then rewritten by behaviour (see §6). This is the distinction:
NPCs are “first it’s random”; the player is “then whatever the player does”.

The physical sample in the lab is one of each type; a separate automated test
draws 100,000 people from the same table and checks the totals.

---

# 3. TRAITS

Traits are additional to MBTI. They are classified as **born** or **learned**.
Only NPCs get traits in this pass; the player gets MBTI tracking only. (Player
traits can be added later without changing this model.)

## 3.1 Core traits in this rework

| Trait | Kind | MBTI rule | Effect | Acquisition |
|---|---|---|---|---|
| **Smart** | born | any MBTI; cannot also have Stupid | all skill gain ×1.25 | rolled at spawn (6%) |
| **Stupid** | born | any MBTI; cannot also have Smart | all skill gain ×0.75 | rolled at spawn (6%) |
| **Strong** | born | any MBTI | melee (axe) skill gain ×1.30 | rolled at spawn (8%) |
| **Green Thumb** | learned | **S only; N can never get it** | harvest gives +20% crops (minimum +1) and +1 seed | chance on each harvest for a farmer; chance rises with farming skill |
| **Traumatized** | learned | any MBTI; F accumulates faster, T slower | break thresholds ×0.75; mood loss from violence ×1.25 | accumulated from being hit and from witnessing deaths |

Born probabilities are independent except Smart/Stupid are mutually exclusive.
A person can have one born trait, or none.

Green Thumb acquisition:

- only while `job == farmer` and `farm_plot is not None`;
- only if `farming >= 1.0`;
- only if the person does not already have Green Thumb;
- chance per harvest: `0.002 + 0.0015 * farming` (about 0.35% at farming 1,
  ~1.4% at farming 8);
- never for N types.

Traumatized acquisition:

- `trauma_points += max(1, damage) * (1.5 for F, 0.75 for T, 1.0 otherwise)`
  when hit;
- `trauma_points += 10 * the same factor` when a person dies within 520 px;
- at `trauma_points >= 100`, gain Traumatized and never roll it again;
- `take_damage` and the death-witness path are the only writers.

Rules that are deliberately **excluded** for now:

- No trait removes another trait.
- No medicine removes Traumatized (that is a future therapy feature).
- No MBTI type is excluded from Smart/Stupid/Strong/Traumatized.
- Green Thumb is the only hard MBTI gate in this pass.

Future trait slots (not implemented yet, reserved so the registry is ready):
Compassionate (F only), Stoic (T only), Disciplined (J only), Improviser (P
only), Visionary (N only). They are listed here so the compatibility rules are
extended in the same table, not bolted on sideways.

## 3.2 Where effects are applied

- **Skill gain:** `persona.skill_gain_mult(npc, skill)` multiplies every
  `skills.gain_*` call made by an NPC. It combines Smart/Stupid/Strong and the
  job-affinity bonus/penalty.
- **Harvest:** `persona.harvest_count(npc, count)` and
  `persona.harvest_seeds(npc, seeds)` apply Green Thumb.
- **Break thresholds / intensity:** `persona.break_thresholds(npc)` and
  `persona.break_intensity(npc)` apply Traumatized, F/T, and J/P.
- **Job speed/output:** `persona.work_mult(npc, job)` is called by every native
  work branch and by the doctor; F's artisan bonus is applied there.

---

# 4. MOOD AND BREAKS

The existing `mood` field (0–100, starts at 50) stays, but it becomes a
**computed target plus a smoothed current value**, fed by explicit thoughts.

## 4.1 Thoughts

`mood_thoughts` is a dictionary: `id -> {delta, expires_at, stacks}`.
`mood_target = 50 + sum(delta × stacks)`, clamped 0–100. `mood` moves toward
`mood_target` at 2 points per second, so a sudden insult is visible but not an
instant teleport.

| Thought | Delta | Duration | Max stacks | Trigger |
|---|---:|---|---:|---|
| `praise` | +8 | 1 day | 2 | player or NPC praise |
| `insulted` | −8 | 1 day | 3 | insult |
| `threatened` | −12 | 1 day | 2 | threat |
| `fed` | +3 | 6 h | 1 | a meal |
| `good_meal` | +5 | 6 h | 1 | cooked meat / fine food |
| `hungry` | up to −12 | continuous | 1 | hunger > 60 |
| `starving` | −20 | continuous | 1 | hunger ≥ 85 |
| `slept_outside` | −6 | 12 h | 2 | slept on the ground |
| `slept_in_bed` | +4 | 12 h | 1 | slept on a bedroll |
| `recreation_unsatisfied` | −6 | 1 day | 3 | yearning ≥ 0.5 and no luxury |
| `recreation_satisfied` | +10 | 6 h | 1 | smoked/drank a luxury |
| `medicine` | +10 | 1 day | 1 | doctor treated him |
| `catharsis` | +20 | 1 day | 1 | a break ended |
| `witnessed_death` | −10 | 2 days | 3 | saw a death nearby (when grief is wired) |
| `unpaid` | −10 | 1 day | 2 | legacy wage system |

The first five negative thoughts and the four positive ones are the core loop.
The user's requested sources are all represented: **insulted**, **low food**
(hungry/starving), **slept outside**, and **unsatisfied recreation** (drugs
now, recreational buildings later).

## 4.2 Break thresholds

Base:

- **minor break threshold:** 32
- **major break threshold:** 16

Adjustments before trait multipliers:

- Feeling: minor +8 (breaks more often), major +2 (slightly easier), minor
  duration −20%.
- Thinking: minor −6 (bottles longer), major −6 (explodes only when very low),
  major duration +30%, intensity +50%.
- J: break recovery +10% longer; P: recovery 20% faster.
- Traumatized: multiply both thresholds by 0.75.

Break roll:

- every 20 s, while not already in a break and not in cooldown;
- if `mood <= major_threshold`: roll major first;
- else if `mood <= minor_threshold`: roll minor;
- F: minor 60%, major 15%;
- T: minor 25%, major 35%;
- neutral: minor 40%, major 25%;
- cooldown after a break: 300 s.

## 4.3 Minor breaks

**Sad**

- movement speed ×0.65;
- work speed ×0.50;
- lasts 180–300 s (F −20%);
- ends early only if mood climbs above the minor threshold + 10.

**Annoyed**

- movement normal, work ×0.75;
- every 10 s insults the lowest-opinion person within 120 px whose opinion is
  below 30 (a much lower tolerance than a normal 0);
- lasts 180–300 s;
- generates `insulted` thoughts and opinion loss in the target.

The minor break chosen is weighted by type: I/F lean sad; E/T lean annoyed;
P leans sad; J leans annoyed.

## 4.4 Major breaks

**Berserk**

- targets the living person he likes least within 300 px; if none, the nearest
  person;
- fights with whatever he has: axe/gun if armed (guns only if the target is a
  person and the weapon is usable), otherwise fists;
- damage is `persona.break_intensity(npc)` × the normal unarmed/armed blow;
- ends when the target is down or after 300 s (T +30%);
- witnesses lose opinion, the victim is `wronged`, and the camp’s soldiers /
  the player’s soldiers may respond.

**Breaking spree**

- targets the nearest **breakable** object within 400 px: chest, food box,
  sign-post, workplace, Medicine Hut, bench;
- attacks it once per second with the weapon in hand or fists;
- a broken chest keeps its contents and remains lootable; it just cannot accept
  new deposits;
- a broken workstation/bench stops production until repaired;
- a broken sign cannot be edited; a broken food box cannot be stocked;
- ends after 3 objects or 120 s, or when there is nothing breakable in reach.

T’s major break intensity is +50%; F’s is −25%. T also carries accumulated
`frustration` (from insults/wrongs) into intensity, then resets it when the
break ends.

## 4.5 Breakable objects

Add to `Chest`, `FoodBox`, `SignPost`, `Workplace`:

- `max_condition = 100`, `condition = 100`, `broken = False`;
- break-spree damage 35 per hit (fists 12);
- at 0 → `broken = True`;
- repair interaction near a broken object with the relevant materials
  (10 wood for chest/food box/sign; 10 wood + 10 iron for a workplace);
- `condition`/`broken` are saved by the built-object provider.

No contents are destroyed. This is important: a break must create a mess, not
silently delete the player’s goods.

## 4.6 What mood does not do

Mood does not directly change wages, trade prices, health, or job assignment.
It drives breaks, and breaks drive those consequences. This keeps one causal
chain rather than five overlapping modifiers.

---

# 5. THE DOCTOR

## 5.1 Job and station

Add `doctor` as a native job:

- listed in the sign-post panel;
- one doctor per **Medicine Hut** (new 2×2 buildable). This is the chosen
  station: a small hut with a bench and shelves, not a town infirmary. If you prefer
  no new building later, the lab bench can be swapped in, but the default is the
  Medicine Hut.
- `JOB_AXIS["doctor"] = "N"`.

The Medicine Hut is player-built, costed like a lab/forge, and saved like any
other workplace. A doctor with no Medicine Hut idles and says so.

## 5.2 Medicine

New item `medicine` (stackable, no quality for now).

Recipe:

- 1 tobacco
- 1 dried mushroom
- 1 any alcohol (`beer`, `liqueur`, `mezcal`, `govbeer`)
- → 1 medicine

The doctor takes ingredients from the nearest chest or the camp ledger, works
the Medicine Hut bench for a short batch, and carries the medicine. No
ingredients = no medicine; he reports it once, not every frame.

## 5.3 Delivery

The doctor’s loop:

1. find the nearest camp person who is either injured (`health < max_health`)
   or has never received medicine (`medicines_received == 0`);
2. walk to them (within 20 px);
3. consume one medicine;
4. set `health = max_health`;
5. `medicines_received += 1`;
6. `mental_known = True` (permanent);
7. add a `medicine` thought;
8. return for the next person.

He treats only people of his own settlement and the player’s soldiers attached
to it, not unconquered enemies or animals. If everyone is healthy and treated,
he idles at the Medicine Hut.

## 5.4 Mental state panel

For any person with `medicines_received > 0` (ever), the player can see:

- current mood and target mood;
- active mood thoughts;
- MBTI letters;
- traits;
- break state/thresholds;
- job and job affinity;
- medicine count.

Where it appears:

- the existing PersonaCard when the player opens a worker’s pack or the
  person’s inspection panel;
- for the player, always (player MBTI, no traits in this pass);
- a “No medical record” line for untreated NPCs.

The medicine reveals the mind; it does not create it. The player can meet a
person, treat them later, and then see what was always there.

---

# 6. PLAYER PERSONALITY

The player’s MBTI is inferred, not selected, and it **updates live**. It is a
running record of **what he is most like during this playthrough**. It is
displayed in the player’s PersonaCard (and a small test-mode HUD), with four
bars and four letters.

The player also starts from a **rolled prior**: a random type from the same
distribution, with a weight of `PERSONALITY_PRIOR = 5` events on each axis.
That is what “first it’s random” means. It is not a permanent identity: every
counter decays with a half-life of one in-game day (600 seconds), so recent
actions outweigh old ones and the letters can flip. A player who starts I and
then begins initiating conversations will become E once the new `initiated`
weight overtakes the decayed `responded` weight.

```
PERSONALITY_HALF_LIFE = 600.0   # one in-game day
PERSONALITY_PRIOR     = 5.0     # the rolled starting type's weight per axis
```

Every counter below is a **float**. Each tick:

```
counter *= 0.5 ** (dt / PERSONALITY_HALF_LIFE)
```

A type is shown when an axis has at least 5 total live weight; below that the
axis shows `?`. The rolled prior supplies that first 5, so there is a starting
type; after a day of play, the prior has halved, and behaviour has taken over.

## 6.1 Counters

`PlayerPersonality` stores float counters and the rolled `start_type`:

- `start_type` — the random type rolled at new game; used only as the initial
  prior, never as a permanent label.
- `initiated` — player opens dialogue, uses comm, hires/fires, gives a job
  order, or otherwise starts a conversation/order.
- `responded` — an NPC speaks to the player (`comm.npc_to_player` cloud); this
  is the NPC initiating. The player’s reply/engagement is not required for the
  count, because the axis is “who starts conversations”.
- `sensing` — chopping, farming, building/placing, mining, crafting, manual
  smithing.
- `intuitive` — talking with people, opening the build screen, collecting from
  chests, selling to the ship, using the research panel.
- `f_contacts` / `t_contacts` — direct interactions with NPCs, credited to the
  NPC’s F or T side; once per NPC per 60 s to stop click-spam.
- `conquered_provoked` — a conquered NPC insults/threatens/attacks the player.
- `conquered_retaliated` — the player attacks/insults/threatens that NPC within
  20 s.
- `conquered_merciful` — the 20 s window passes with no retaliation.

## 6.2 Letters

- E if `initiated > responded`, else I.
- S if `sensing > intuitive`, else N.
- F if `f_contacts > t_contacts`, else T.
- J if `retaliated >= merciful` (and at least 3 events), else P.
- If an axis has fewer than 5 events, show `?` for that axis; the bar still
  shows the lean.
- Ties are resolved to the second letter (I/N/T/P) until more data arrives.

The panel shows percentages as well as letters, e.g.:

```
PERSONALITY (this playthrough)
E 58%   S 62%   F 47%   J 55%
E  S  T  J
```

The letters are the dominant side at the moment, not a permanent identity.
They are recalculated every tick from the decayed counters. If an axis has no
evidence left (total live weight < 5), it shows `?`; the next action can revive
it. This is why the panel can say `I` for a while and then flip to `E` after a
run of player-initiated conversations.

## 6.3 Persistence

All decayed counters and `start_type` are saved in the player provider. A new
game rolls `start_type` and seeds the four matching counters at
`PERSONALITY_PRIOR`; all others start at zero. The panel shows the rolled type
immediately, then tracks live behaviour. On load, the saved counters continue
decaying from where they were.

---

# 7. DATA AND SAVE MODEL

## 7.1 New NPC fields (class defaults, so old saves load)

```
mbti: str = ""
traits: list = []              # ["smart", "green_thumb", ...]
trauma_points: float = 0.0
medicines_received: int = 0
mental_known: bool = False
mood_thoughts: dict = {}       # id -> {"delta","expires_at","stacks"}
mood_target: float = 50.0
break_state: str = "normal"    # normal|sad|annoyed|berserk|breaking_spree
break_until: float = 0.0
break_cooldown: float = 0.0
frustration: float = 0.0
```

All are plain data and are saved automatically by `save/people.py`. The
existing `mood`, `opinion`, `player_opinion`, `dictator_love`, `news`, etc.
stay as they are.

## 7.2 New built-object fields

`condition`, `max_condition`, `broken` on chests, food boxes, signs and
workplaces; added to `save/built.py` snapshot/restore.

## 7.3 Player personality

A `personality` dict under `save/player.py` or `save/systems.py`:
`start_type`, `initiated`, `responded`, `sensing`, `intuitive`, `f_contacts`,
`t_contacts`, `conquered_provoked`, `conquered_retaliated`,
`conquered_merciful`. All counters are floats and decay with
`PERSONALITY_HALF_LIFE = 600.0`; `start_type` is the rolled prior only.

## 7.4 Migration

- Bump `SCHEMA_VERSION` to 2.
- Migration is additive: old people get `mbti = ""`; on load,
  `persona.ensure(npc)` assigns a deterministic type from the NPC’s stable id,
  and sets the new fields to defaults.
- Old built objects get `condition = 100`, `broken = False`.
- New saves write all fields normally.
- Extend `tools/save_selftest.py` with MBTI, traits, mood thoughts, break
  state, medicine count and object condition.

## 7.5 Why deterministic

`persona.assign(npc)` derives the type from `npc.id` (or a stable seed for
people without an id) and the distribution table. It does not use the live RNG
and does not use `id(obj)`. The same person is the same type after every load.

---

# 8. CODE LAYOUT

New modules:

```
persona.py     MBTI table, assignment, job affinity, traits, player personality
mood.py        thoughts, mood target, thresholds, break state machine, breakable objects
doctor.py      medicine recipe, doctor production/delivery
npclab.py      test-mode-only scenario builder and debug overlay
```

Minimal hooks in existing files:

- `village.py` — NPC class defaults; `update`/work branches call job-affinity
  and doctor role; `_fight`/`take_damage` feed trauma; `die` feeds witnessed
  death; break states respected by movement/work.
- `mind.py` — replace/augment spree/brawl with `mood.step`; keep the existing
  intent but move thresholds/effects into `mood.py`.
- `economy.py` — mood thoughts for hunger/starving/craving; Green Thumb harvest
  multiplier; `wronged`/opinion J/P modifiers.
- `comm.py` — I/E initiation rules; thought-based praise/insult/threaten;
  player personality contact counters.
- `work.py` / `colony.py` — job affinity multipliers; doctor job assignment.
- `ui.py` — mental state block in PersonaCard; Doctor in SignPanel; player
  personality block; condition/repair display.
- `build.py` / `placement.py` — Medicine Hut; breakable condition/repair.
- `items.py` — medicine item and icon.
- `save/` — new fields, built condition, player personality, migration.
- `engine.py` — test-lab keys and overlay; repair interaction.
- `build.sh` — run the existing save selftest; add `tools/persona_selftest.py`.

Because `village.py`, `economy.py` and `skills.py` are Cython, any change there
requires `./build.sh`; the build must pass before a physical test.

---

# 9. TEST MODE: THE NPC LAB

All physical testing happens in **TEST MODE**, using `saves_test`, never the
real save. The lab is built by a test-mode-only module, `npclab.py`.

## 9.1 What the lab contains

Near the player, on a fixed seed and a fixed layout:

- one **lab camp** with a fireplace and bedrolls;
- 16 test subjects, one per MBTI type, named `T-INTJ`, `T-ISFP`, etc.;
- two paired farmers (one S, one N) on identical fields;
- a farmer S and a farmer N for Green Thumb;
- a Medicine Hut, lab bench, forge, dummy and target;
- chests with medicine ingredients and ordinary supplies;
- a food box and an unhappy/starving subject;
- three breakable chests and a breakable bench;
- one conquered worker and one hostile unconquered warrior for combat/retaliation.

The lab is a test fixture. It does not affect a normal save.

## 9.2 Test keys (test mode only)

| Key | Action |
|---|---|
| **F6** | Rebuild/reset the lab and select the first subject |
| **F7** | Cycle the selected subject |
| **F8** | Cycle the selected subject’s mood: 70 → 50 → 35 → 25 → 15 → 5 |
| **F9** | Force the next break: sad → annoyed → berserk → breaking spree |
| **F10** | Cycle test grants: next trait, next medicine, reveal mental state |
| **F5** | Toggle the lab overlay/details |

The test-mode overlay shows for the selected subject:

```
T-INTJ   job=artisan   S/N: N (+15% / +25% skill)
mood 24 / target 18    break: normal
traits: Smart, Green Thumb
thoughts: insulted -8 x2, hungry -6, slept_outside -6
medicine: 1   mental record: yes
```

and for the player:

```
PLAYER  E 58%  S 62%  F 47%  J 55%   E S T J
init 12 / respond 9   sense 40 / intuit 24   F 7 / T 6   retaliate 2 / mercy 1
```

Breakable objects show `condition 100/100` or `BROKEN` in test mode.

## 9.3 Automated checks (not a substitute for playing)

- `tools/persona_selftest.py`: 100,000 deterministic draws from the MBTI table
  must match the axis totals; trait gates must reject N/Green Thumb; job
  multipliers must be exact; player letters must resolve correctly at
  thresholds.
- `tools/save_selftest.py`: extends the existing round-trip with MBTI, traits,
  mood thoughts, break state, medicine count and object condition.

---

# 10. BUILD PHASES AND PHYSICAL TEST SCRIPTS

Each phase ends with a build, a test-mode scenario, and **your confirmation**.
Do not start the next phase before that.

## Phase 0 — Foundation and lab (no gameplay balance yet)

Build:

- `persona.py`, `mood.py`, `doctor.py`, `npclab.py` skeleton;
- new NPC fields with class defaults;
- save fields and migration;
- test-mode lab, overlay, F5–F10 keys;
- `persona_selftest.py`.

**Physical test T0 — the lab exists**

1. Start TEST MODE.
2. Press F6. Expect a labeled lab near you: 16 MBTI names, chests, Medicine Hut,
   bench, forge, fields, bedrolls.
3. Press F7/F5. Expect the selected subject’s name and MBTI to cycle and the
   overlay to show the same letters.
4. Press F8. Expect the mood number and target to change.
5. Save, quit to title, re-enter test mode and load. Expect the lab and the
   displayed mind fields to still be there (or be rebuilt deterministically).

Pass condition: the lab is visible, labeled, and controllable; no normal save
is touched.

## Phase 1 — MBTI assignment, distribution, job affinity

Build:

- deterministic weighted assignment;
- `JOB_AXIS` and `persona.work_mult`/skill-gain hooks;
- player-visible MBTI on selected subjects.

**Physical test T1 — types and job fit**

1. F6. Walk the line of 16 subjects. Every name must match the letters shown.
2. Open the mind overlay on the two paired farmers (S vs N). Give both the
   same field and let them work at test speed.
3. Compare their output and farming skill over the same number of harvests.
   Expect the S farmer to lead in both.
4. Check the artisan: F artisan should lead a T artisan of equal skill.
5. Run `tools/persona_selftest.py`; expect distribution and gate checks to
   pass.

Pass condition: the type shown, the type used by the job multiplier, and the
observed performance all agree.

## Phase 2 — Traits

Build:

- born traits;
- Green Thumb acquisition/effect;
- Traumatized acquisition/threshold effect;
- trait gates and trait display.

**Physical test T2 — born and earned**

1. F6. Find the Smart, Stupid and Strong subjects. Put Smart and Stupid on the
   same job and compare skill gain; Strong should gain axe skill faster.
2. Put the S farmer on a field and speed time up. F10 can grant/check Green
   Thumb; on a harvest, verify +crops and +1 seed. Try granting Green Thumb to
   an N subject: it must be refused.
3. Hit the Traumatized candidate repeatedly (or let it witness a test death)
   until the trait appears. Verify its break threshold is lower in the overlay.
4. Save/reload; traits must persist.

Pass condition: every trait does exactly what its row says, and the gates hold.

## Phase 3 — Mood thoughts and thresholds

Build:

- thought registry and mood target;
- hunger/starving, slept outside, insulted/threatened, recreation thoughts;
- overlay listing thoughts and target.

**Physical test T3 — mood moves for the right reasons**

1. F6. Select a subject and read mood/target/thoughts.
2. Insult him with G. Expect an `insulted` thought and a lower target.
3. Let him go hungry; expect `hungry`/`starving` to appear and deepen.
4. Let him sleep on the ground; expect `slept_outside`.
5. Give him a luxury or let him consume one; expect `recreation_satisfied`
   and a higher target.
6. Feed him/sleep in a bedroll; expect positive thoughts.
7. F8 cycles mood and the overlay must show both current and target moving
   toward each other, not jumping.

Pass condition: every requested mood source is visible, stackable where
specified, and expires when it should.

## Phase 4 — Minor breaks

Build:

- sad and annoyed states;
- slowdowns, insult behaviour, durations, recovery;
- F/T frequency difference.

**Physical test T4 — sad and annoyed**

1. F6. Select a worker with a job and a disliked neighbour.
2. F8 down to the minor band. F9 forces sad. Expect visibly slower movement
   and much slower work; watch the work counter.
3. F9 again for annoyed. Expect him to insult the disliked neighbour on a
   cooldown; check the target’s opinion and mood drop.
4. Compare an F and a T subject forced to the same low mood: F should break
   minor more often; T should resist longer.
5. Let the break expire; expect normal speed/work and a `catharsis` thought.

Pass condition: minor breaks are visible, readable, and temporary.

## Phase 5 — Major breaks and breakable objects

Build:

- berserk and breaking spree;
- target selection, weapon use, object condition;
- broken objects, contents preservation, repair;
- F/T intensity and duration; J/P recovery.

**Physical test T5 — the explosion**

1. F6. Select a subject with a disliked neighbour; F8 to the major band; F9
   forces berserk. Expect him to close and attack with fists or weapon.
2. Watch the victim’s health and opinion. Expect the break to end when the
   victim is down or the timer runs out.
3. Select another subject near the breakable chests/bench; force breaking
   spree. Expect him to attack the nearest chest/bench, the condition to fall,
   and the object to show BROKEN. Verify chest contents are still there.
4. Repair the object with the repair interaction; expect condition restored and
   production/storage to resume.
5. Compare T vs F: T major should be rarer but stronger; F should have more
   minor breaks instead.
6. Check a witness/opinion consequence and, if present, a soldier response.

Pass condition: the break is a real, cancellable/endable event, not a permanent
state, and nothing is silently deleted.

## Phase 6 — Doctor, medicine, mental state

Build:

- medicine item/recipe;
- Medicine Hut and doctor job;
- delivery and full heal;
- `mental_known` and persona panel.

**Physical test T6 — the doctor**

1. F6. Injure two subjects; leave one healthy but untreated.
2. Put a doctor on the Medicine Hut and ingredients in the chest: tobacco, dried
   mushroom, beer/liqueur/mezcal.
3. Watch him make medicine and walk it to each person.
4. Verify both injured people are healed to full; verify the untreated healthy
   person still gets a medicine and is marked.
5. Open the treated person’s PersonaCard: mood, MBTI and traits visible.
   Open an untreated person’s: “No medical record”.
6. Verify the record persists after save/reload.

Pass condition: medicine is produced from exactly the recipe, delivered,
heals fully, and permanently unlocks the mind panel.

## Phase 7 — Player personality

Build:

- decayed counters for E/I, S/N, F/T, J/P and a rolled `start_type` prior;
- live recalculation every tick and letter flips;
- player personality block in PersonaCard and test HUD;
- save/reset behaviour.

**Physical test T7 — what kind of player are you**

1. Start a new lab game. Note the rolled starting type and the four bars. The
   prior gives each axis a starting 5.
2. Initiate several conversations/orders. Expect E to rise and, after enough
   actions, flip an initial I to E.
3. Let several NPC clouds reach you without initiating. Expect the respond
   counter to rise and an E lean to move back toward I.
4. Chop/build/farm for a while; then talk/open the build screen/collect/sell.
   Expect S and N to move in opposite directions and one to overtake the other.
5. Talk mainly to F-type subjects; then mainly to T-type subjects. Expect the
   F/T bar to follow.
6. Provoke a conquered subject (or use F9 on one) and retaliate; then repeat
   and ignore/forgive. Expect J/P to follow.
7. Wait about ten in-game minutes. Expect old counters to halve and the panel
   to reflect the recent behaviour more strongly than the start.
8. Save/reload; the decayed bars, letters and `start_type` must persist.

Pass condition: the displayed personality is a faithful summary of the actions
actually taken, not a hidden fixed choice.

## Phase 8 — Integration and save

Build:

- save migration and all new fields;
- extend save selftest;
- no regressions in the existing MBTI-off normal game.

**Physical test T8 — the whole thing**

1. In the lab, set a subject mid-mood, with traits, a break in progress, and a
   medicine record.
2. Save, quit, relaunch, load.
3. Verify mood/thoughts/traits/MBTI/break state/medicine record/object
   conditions/player personality all match.
4. Run `./build.sh`; the save round-trip and persona checks must pass.
5. Play a normal (non-test) game for a few minutes to confirm the new systems
   do not fire in unintended places.

Pass condition: the world comes back exactly, and the normal game still plays.

---

# 11. DELIBERATE NON-GOALS FOR THIS PASS

- No player traits; player MBTI only, and it updates live from a rolled prior.
- No treatment of Traumatized by medicine.
- No recreation buildings yet; drugs are the only recreation.
- No new types of break beyond sad/annoyed/berserk/breaking spree.
- No MBTI-based dialogue lines yet; the mind is shown, not spoken.
- No changes to the legacy town simulation; it remains dormant.
- No economy rework; wages/trade/prices stay as they are.

These are listed so they do not creep into the first implementation.

---

# 12. ONE-LINE SUMMARY FOR EACH PHASE

| Phase | Build | Player physically verifies |
|---|---|---|
| 0 | Lab, fields, save skeleton | F6 lab exists, F7/F8 work, save/load |
| 1 | MBTI + job affinity | 16 types, S vs N farmer output, F artisan |
| 2 | Traits | Smart/Stupid/Strong, Green Thumb, Traumatized, gates |
| 3 | Mood thoughts | insulted, hungry, slept outside, recreation, target/current |
| 4 | Minor breaks | sad slowdown, annoyed insults, F vs T |
| 5 | Major breaks | berserk, breaking spree, broken objects, repair |
| 6 | Doctor | Medicine Hut, medicine recipe, delivery, full heal, mental panel |
| 7 | Player MBTI | rolled prior, live-decaying E/I, S/N, F/T, J/P bars and flips |
| 8 | Save/integration | reload exact, build passes, normal game unaffected |

**No phase begins until the previous phase has been played and confirmed.**
