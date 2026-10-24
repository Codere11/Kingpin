# Pivot

**From three nations at war, to one regime — and the service behind it.**

This is the plan. It is deliberately a *reframing* of what exists rather than a
rebuild: nearly every system already in the game has a totalitarian reading, and
the pivot is mostly a matter of deciding that the reading is the truth.

---

## 0. Why (the diagnosis, written down so it is not lost)

The game is boring at the start not because the tasks are bad but because:

* **Every verb is a production verb and none of them can go wrong in a way that
  costs the player anything.**
* **The world is indifferent.** It simulates beautifully and nobody wants
  anything from him.
* **The war is weather.** Three nations fight; the player has no stake, no side,
  and its outcome never reaches him.
* **The nemesis is a rival, not a person.** He never knows your name.

What the pivot supplies:

* **Pressure that acts on you** — the regime.
* **Something you can lose** — your livelihood is now illegal.
* **An antagonist with a nervous system** — the service, running on the news
  system that already exists.

**The key insight: this pivot does not add verbs. It gives the verbs
consequences.** A still in the woods stops being a crafting station and becomes
a conspiracy.

---

## 1. Government — one state, three capitals

* **One government rules the entire map.** There are no other nations, no
  borders, no war between powers. `nations.nation_index()` returns 0 everywhere.
* **Three capitals remain**, but they are one state's:
  * **1 Main Capital** — the seat. The **Dictator** sits here.
  * **2 Regional Capitals** — administered by **Governors**.
* Everything else — 33 towns — is village-level administration: mayors, boards,
  ledgers, taxes.
* At the start of the game **the regime controls everything**. There is no
  contested territory. The map is not divided; it is *occupied*.

### What this costs

Very little. `nations.py` already places three capital sites and dishes out
nation ids; that becomes one id and one state. The King logic already crowns one
man per capital — that becomes **one crown at the Main Capital only**, and the
other two get Governors.

---

## 2. Inside settlements, only food grows

* **Every village plot grows food.** No tobacco, no leaf, no agave, no
  mushrooms — inside a settlement those are *evidence*.
* This is not a balance change, it is the law of the land expressed in
  agriculture: the state permits what feeds people and forbids what pleases
  them.
* **Effect on the player:** the leaf he needs for his trade cannot be grown
  legally. It comes from the wild, from the hubs, or from a smuggler. His own
  profession is now a black-market activity by definition.

### What this costs

The plot kinds already exist (`farm_plots` carry a `kind`). This is a filter on
what a village will stake, not new machinery.

---

## 3. Wild non-food plants become rare

* Wild leaf and the rest still grow, but **much rarer** — a find, not a
  harvest.
* Enough to start a trade, never enough to run one from. That pushes the player
  toward the hubs, and toward people.

---

## 4. Illegal production hubs

Scattered through the wild, away from settlements and roads:

* **Small: a 5×5 plot.** Of those 25 tiles, **5 are food**, the rest is the
  local version of leaf for that biome.
* **A single house.**
* **A workstation** — an artisan's bench or a brewer's, matching what grows
  there.
* **Four people live there** — the 'criminals' faction:
  1. **a soldier** — always standing at the gate
  2. **a farmer** — works the 5×5
  3. **a trader** — carries the product out
  4. **the artisan or brewer** — works the workstation
* **A fence and a gate around it.** The soldier at the gate is the whole
  readout: this place is defended, and it is not on any map.

### Why this is the right shape

* It is **small enough to be legible** — four people, one gate, one crop.
* It is **a place, not a menu** — you walk to it, you're seen arriving, you are
  remembered leaving.
* It **generates its own stories**: who runs it, who knows about it, who will
  sell it out.
* And it is **the economic answer to the law** — the regime forbids leaf, so
  leaf is grown where the regime isn't.

---

## 5. The three roads (not yet built)

The player decides his posture, and it is emergent rather than scripted:

1. **Violent revolt** — build a force, take a capital.
2. **Takeover from inside** — connections and money. You cannot vote your way
   out; you can buy your way in.
3. **Submission** — live inside the system: comfortable, corrupting, and
   eventually something to lose.

**Submission must not be inert.** It should be *"I built a life inside this"*,
and then the regime asks for more.

---

## 6. The service (not yet built)

* The Dictator is a **figurehead**. The real power is a **secret service**.
* The **nemesis** is that service — possibly its head.
* **Revealed progressively**, never by cutscene: through documents, ledgers,
  faces, and the news.

### Why the news system is the perfect vehicle

It already models who knows what, how fast, and through whom. That is precisely
what an intelligence service *is*. Make the service the real power and the
existing machinery becomes the antagonist's nervous system:

> **Is the man selling me liquor an agent?** — He came from a town you were seen
> in, three days after you were seen there.
>
> **Is my brother-in-arms turned?** — He asked a question only the service would
> care about.

**The paranoia is derived, not scripted.** And the nemesis never has to appear:
every crackdown is evidence of him.

---

## 7. Where I would push back

**The Dictator must stay dangerous.** If learning he is a puppet makes him
*irrelevant*, the reveal deflates instead of recontextualising. He should be
cruel, vain and *effective* — so discovering he is also a prisoner makes him
tragic rather than fake.

**Do not let enforcement kill the heartbeat.** The dole, the wages, the ledgers
and the fields are the living world. A regime that strangles production leaves a
grey map. **The regime should tax the black market, not replace it** — repression
reads best over a world that is still visibly alive.

**The first ten minutes still need a decision.** The three roads are long arcs.
Under a regime the first decision is trivially available and uses existing
systems:

> **Your first act is whether to report your neighbour.**

A man in your trade who owes more than you, doing something small and illegal, a
notice on the board that pays for information. Take the money, stay silent, or
warn him — three postures, one click, in minute one. The news system carries all
three forward.

---

## 8. What is built now, and what is not

**Built in this pass (the easy part):**

* One government: `nations.nation_index()` returns 0 everywhere, `count()` is 1.
* Three capital sites kept: **1 Main Capital + 2 Regional Capitals**, all one
  state.
* **One ruler**: the crown is at the Main Capital only. The other two capitals
  are administered by Governors — they keep their mayor, with the role renamed.
* The regime controls everything from the first frame.

**Written down, not built:** §2 food-only plots, §3 rarer wild plants, §4 the
hubs, §5 the roads, §6 the service.

---

# The Border, the Lie, and the Question

Written down before it is built, because this is the part that decides whether
the world feels like a state or a set dressing.

## 1. A settlement's fence cannot be cut

Not by an axe, not by anything. **The wall is not what keeps people out — the
search at the gate is.** A wall you can hack a hole in makes the gate
decorative, and the gate is the entire apparatus of the regime made concrete.

The player's own built fences are still his to cut down.

## 2. Two guards, at the gates, who do not walk away

Patrols walked a ring a kilometre out — which meant **the one thing a wall is
for, who comes through the gate, was watched by nobody.**

Now: **two guards, one at each gate.** One gate is the way **in**, and its guard
**searches**. The other is the way **out**, and nobody is searched leaving. That
asymmetry is the whole border, and it is also a rule about the world: *people
queue to get in, and walk out freely.*

## 3. The search

* Every NPC entering a settlement must go through **the guard on the in-gate**.
* The search takes **ten seconds**, shown with **the same bar the axe swing
  uses**, drawn **under the soldier doing the searching**.
* Only one man is searched at a time, so **a line forms at the in-gate.**
* This is where the whole economy of the game becomes visible: hordes of people
  queueing to be looked at, and one of them is carrying something.

## 4. Smuggling — the skill

**`smuggling`, 0 to 10.** How good you are at carrying what the state forbids.

    found = min(1, units / 100) * (1 - 0.09 * smuggling)

| | 100 items | 10 items |
|---|---|---|
| **skill 0** | **100% found** | 10% found |
| **skill 10** | **10% found** | 1% found |

* **Gained by getting contraband through a border**, and by **selling it** —
  the skill is bought with the risk and paid in coin.
* **Caught** = the people aggro, **and the news spreads.** The whole town learns
  your name before you have left the gate.

**Hub traders carry 20 produced items per trip** — static for now, until there
is a reason for it not to be.

## 5. The interaction screen (what the trade menu becomes)

The trade menu stops being a shop and becomes **a person.** What you get from it
is what you know about him, and it is gated by a skill of your own.

### 5.1 Social

**`social`** — how much of a person you can read, and how few words it takes.
Low social: you learn nothing, or learn it wrong. High social: his numbers open
up like a ledger.

### 5.2 The two numbers

* **Allegiance** — to the government. **0** is a man who would burn it down;
  **100** is a die-hard.
* **Loyalty** — to *you*. **0** is *"I wouldn't piss on him if he were on fire"*;
  **100** is *"love this person more than myself."* **Starts at 50.**

### 5.3 Perceived and actual

**Every person has a perceived version of each number and an actual one.**

> A criminal wants everyone to think he is an upstanding citizen.

* **If your Social is higher than his**, you see **what he actually is.**
* **If it is not**, you see **what he wants you to see**, and believe it.

That applies **to the player as well**:

* **`P` sets how the player wants to be perceived** — his mask. His *actual*
  allegiance starts at **50**, and moves toward **0** by carrying and selling
  contraband.
* **Whether people see his true self or his mask is decided by his Social
  against theirs.** The searching guard is the first test of it, and the first
  time the player learns that his face is a stat.

**This is what the search is really rolling.** Not whether the tobacco is in the
bag — whether the man in front of you is who he says he is.

---

### Built now

* Hub purse and food **split equally** between its four people, every three
  minutes.
* **Fences around a settlement cannot be cut.**
* **Two guards at the gates** instead of a patrol, standing, **not walking**.
* **`player.smuggling`** and the search law above, wired to a click on a gate
  guard.

### Not built

* The ten-second search bar and the **queue** at the in-gate.
* NPCs being searched on their way in at all (they currently walk through).
* The **Social** skill, Allegiance, Loyalty, the perceived/actual split, and
  `P` for the mask.

---

# §9 — THE WORLD LOOP

## 9.0 FIRST: THE DICTATORSHIP HAS NO ELECTIONS

**Marked for removal.** There are no elections under a dictatorship. The
machinery currently in the game that assumes a republic must go:

| to remove | where it lives |
|---|---|
| `economy.hold_election` and every call to it | `economy.py`, `Village.update` |
| the **vote market** (`buy_vote`, `nearest_voter`, `K`) | `main.py` |
| the **mayor** as an elected office | `economy.pay_mayor`, `mayor.at_court` |
| the **crown contest** — `candidates_for_crown`, `Village.crown`, the King being chosen by towns | `village.py`, `economy` |
| `ELECTION_DAYS` and the mayoral court cycle | `economy.py`, `village.court_day` |

**Replacements, not deletions:**

* A mayor becomes a **Governor appointed by the Dictator** — he is not elected,
  he is *sent*, and he cannot be replaced from below. Loyalty to the crown, not
  to the town.
* The King becomes **the Dictator** (already: only the seat crowns him). He is
  never replaced by a contest. **Only a violent overthrow removes him** — and
  the seat does not fall because a town voted; it falls because an army took it.
* A settlement changes hands **by force, one at a time**. Take it, hold it, and
  it is yours. Until then it is his.

## 9.1 The loop, in order

```
Dictator bans alcohol and drugs
        ↓
player earns money and grows a network   (hubs, carts, gates, informers)
        ↓
player has an army
        ↓
player takes the settlements, one by one, out of the Dictator's hands
        ↓
the seat falls. The Dictator falls. The regime does not.
        ↓
the Chief of the secret police — or whoever takes his place — wages a
constant rebellion against the player
        ↓
assassination attempts · infiltration · hubs and criminal networks turned
against him
        ↓
the rebellion is financed by selling drugs AND guns
        ↓
THE PLAYER'S CHOICE: keep the bans, or lift them
```

**The regime is not destroyed when the Dictator is.** The service survives its
master, and that is the second half of the game.

## 9.2 The ban decision — the price of every choice

The rebellion's income comes from what is forbidden. **Legalising it starves
them — and poisons your own country.** Four positions, each with a real cost:

| position | what it does to the rebellion | what it does to the player |
|---|---|---|
| **Keep both bans** | **a steady, growing income**: drugs and guns both move through the hubs | nothing. It is the old world, with you on the throne. |
| **Legalise alcohol and drugs** | their drug money dries up; they lean harder on arms | the population turns **idle, quarrelsome and short-lived**; deaths by brawl and overdose climb; **your army is worse** — fewer men fit to march; **support is unreliable** — men change sides for a bottle |
| **Legalise guns** | they buy freely on the open market — **the rebellion arms itself faster** | **every dispute becomes a shooting**; murders among townsfolk; the rebellion's attacks get bloodier |
| **Legalise both** | they lose the drug margin, and buy their weapons in daylight | **an intoxicated country with a lot of guns**: idleness, killings, unreliable men, and a rebellion that is well-armed and still rich |

**And keeping the bans has its own cost**: every cart is a crime, every hub a
crime scene, and the service that you *just defeated* knows exactly where the
trade runs. **The ban is what the rebellion feeds on — the player's job is to
choose which poison they take.**

The numbers (to be tuned): each legalisation moves a `temptation` multiplier on
idleness/brawling/deaths, and a `rebellion_income` multiplier on the rebel
ledger. They pull in opposite directions, and there is no position with no cost.

## 9.3 The rebellion as an adversary

It must behave like a **network**, not an army:

* **assassination** — a man in the crowd, a shot from a window, a cup that is
  not yours. It targets **you**, and the men around you.
* **infiltration** — a trader who wants to buy into your hub. A guard who
  volunteers. A townsman who is very keen to be your friend.
* **the criminal network is its treasury** — the hubs you left standing, the
  carters you did not pay, the towns whose bans you kept.
* and it is **patient**: it does not need to beat your army, only to make your
  rule cost more than it earns.

## 9.4 What this means for the systems already built

| system | its role in this loop |
|---|---|
| **hubs** | the player's first economy **and** the rebellion's future income |
| **carts / free traders** | the vein that carries both contraband and rebel coin |
| **gate searches** | the state's tool — and, after the fall, **yours** |
| **smuggling skill** | how much risk a man will take per trip |
| **opinion / social / fear** | what decides whether a man is yours or theirs |
| **news and `knows`** | how a name travels, and how a lie travels with it |
| **elections** | **removed.** Office is appointed, or taken by force. |
