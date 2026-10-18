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
