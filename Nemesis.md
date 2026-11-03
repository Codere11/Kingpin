# The Nemesis

A design document. Everything below was argued out, and the reasoning is kept
because the reasoning is the part that took the time.

---

## 1. The premise

**One man in the world wants what the player wants, and he is not special.**

He is an ordinary citizen with an ambition, and he obeys every law the player
obeys. He is not buffed, not scripted, not omniscient, and has no ability the
player cannot earn. **If the player watches him closely enough, he cannot tell
him apart from anybody else** — which is the whole point, and it is also the
requirement for the endgame vision, where players and NPCs are
indistinguishable.

The player never learns he has a nemesis. There is no screen for it. **The only
manual is what the player survives and what other players tell him.**

---

## 2. Why not "buff him at the start"

The obvious design — give him a head start — fails on three counts:

- **It makes him a cutscene, not a rival.** A man who wins because he was given
  a start is an event that happens to you.
- **It makes him beatable by inspection.** The moment a player suspects a
  special case exists, the drama is gone.
- **It breaks indistinguishability**, which is the foundation of everything
  else.

**He doesn't need power. He needs TIME and POSITION.**

- **Time:** the player gets one run. The world gives the nemesis unlimited
  attempts. He loses an election and stands again in fifteen days. He loses the
  ring and is back in fifty. **He keeps his coin, his office and his life when
  he loses — all three are already true.**
- **Position:** he starts somewhere *cheap*. A small village is a cheaper
  election (fewer voters to buy at `ELECTION_BRIBE`). A village with a mine or
  a forge makes money faster. **Choosing a good starting position is strategy,
  not cheating — the player could learn to do the same.**

---

## 3. The climb

### He starts as a random tradesman

Every playthrough, a different start: **a soldier one game, a trader the next,
an idle the third, a logger or a brewer the fifth.** No predetermined ladder.
His road emerges from where he begins.

### He gathers skills strategically, and moves when the trade is exhausted

The engine is the skill system, which already measures saturation:

| trade | skill it hones | cap | cost to master |
|---|---|---|---|
| farm | `farming` | 8 | harvests |
| logger | `axe` | 1.0 | 80 swings (`AXE_NEED`) |
| brewery / lab | `farming` | 8 | batches |
| trader | `movement` | 1.0 | 16,000 px (`MOVE_NEED`) |
| soldier | `axe` + `shooting` | 1.0 | 80 swings, 110 shots (`SHOOT_NEED`) |
| mine, smith | *nothing* | — | a wage, not a trade |

**When the current trade can teach him no more, he wants out.** Not time
served — *skill saturated*. A logger learns everything a logger can know in 80
swings, and then he is standing still.

### He always changes for the better

A rank table of his own — money and reach, not prestige:

```
none 0 · logger 1 · farm 2 · mine 3 · smith 4 · brewery 5 · lab 6
trader 7 · soldier 8 · mayor 9 · king 10
```

He moves up only when he can **pay for the rung** — the mash for a brewery, the
leaf for a bench, the kit, and later the votes. **Money is the gate, which is
why farming comes first: it is the only trade that turns soil into coin without
capital.**

The illustrative arc: **farming → artisan/brewer (he has money) → combat →
raiding → mayor → king.**

### Scheming — his one privilege

**He may take any job he wants from anyone. The displaced man becomes idle.**

Mechanically this is nearly free: `Village.free_post(npc)` releases a trade and
plot, and `offer_post` re-posts the displaced man automatically — *"a man with
no post asks his town what is going, once a second, and takes it himself."* No
invariant breaks. Nothing rots.

**But the reason it is right is that it leaves a witness.** The man he pushed
out *knows*. He remembers. **Every rung he climbs leaves one more man in the
world who can sell him out** — and a man who spits when he says the name is
exactly how the player finds out.

**Rules:**
- **Always upward.** Scheming is just how "change for the better" is
  implemented when the post he wants is already held.
- **Always one rung at a time.** A logger scheming his way into a smithy is a
  story; a logger scheming straight into the mayoralty is a joke.
- **Every scheming creates a grudge**, and a grudge is a source of clues.

---

## 4. The knowledge rule — the heart of it

> **The name is knowledge of the LEADER. The trailer is anonymous.**

| | the player is **ahead** | the player is **behind** |
|---|---|---|
| what he hears | **profession only** — *"a logger, somewhere east"* | **name, trade, place** — *"Gavin. King now."* |
| and the nemesis hears | **name, trade, place** — *"you"* | **profession only** |

**The lead does not make you safer. It is what makes you findable.**

### Why this is the best rule in the document

Two specified things combine:

1. **Fame travels downhill only.** The trailer learns the leader's name; the
   leader never learns the trailer's.
2. **A name is what a murder needs.** You cannot hunt a profession. You cannot
   lie in wait for *"a logger, somewhere east."*

**So the man at the top of the world is blind in exactly the way that matters.**
He has people, power, an army, and no idea who is coming. The man below him —
anonymous, patient, with an axe — knows his name, his house and his routine.

> **The powerful do not notice the climber until it is too late.**

**And it mirrors.** The moment the player falls behind, he learns the name, and
he can go hunting. **Falling behind is how you get your weapon back.**

---

## 5. The clues — nameless, dripping, deniable

The public news is *precise* (`(village, army, nation)`, factual,
verifiable). **The clues are the exact opposite: ungrounded hearsay.** The
player cannot look them up. He can only accumulate.

### Specificity is the dial

| detail | what he hears |
|---|---|
| **rumour** | *"There is a man… rising fast in the world."* |
| **trade** | *"They say a smith in the east is making a name for himself."* |
| **place** | *"A man in Iron Hollow — a smith, they say — he's going far."* |
| **name** | *"Gavin. Mayor of Iron Hollow. Took the post off a man who still spits when he says it."* |

**Only the last is actionable, and it should be the rarest.** Everything before
it is a rumour the player files away and can do nothing with.

### Who says it

**Someone who would know** — a trader who has been that way, a fellow
tradesman, **or a man he displaced.** This reuses the gossip machinery rather
than inventing one.

### The latency

**"It gets faster the closer they are"** is the information-latency model the
game already has. `war.tell` moves knowledge man to man at trader speed — the
same reason a crown's demand expired three days after posting while the news
took ten to arrive. **The clue delay is distance over trader speed. No new
system.**

### The asymmetry

**You never hear rumours about yourself. Everybody else does.**

**Consequence: the player cannot stay hidden by staying quiet.** The more he
rises, the more the nemesis learns, automatically. And the lead-winner gets
better clues for free, because **fame is a function of rank** — everyone talks
about the King; the King has people to tell him about a smith.

---

## 6. Misinformation

**Rare, random, and unreliable. A rumour is not a status update.**

> *"Martin is a really ambitious man. He became a mayor now!"* — and Martin is a
> plain old NPC.

**And the teller may be the nemesis himself** — the trader who sold you a gun
on day 12, the soldier you raided a village with on day 32.

### The trust metric is already built

`opinion` — **+1 per trade, each way, capped at 100** — was built for elections,
so a man who deals honestly becomes *known* for it. **It is therefore already a
trust score, and the player reads it as one.**

> **The trader who sold you a gun on day 12 is precisely the man whose opinion
> of you is highest. So the nemesis's single best move in the entire game is to
> be that man.**

The betrayal is not a cutscene. **It is a byproduct of a mechanic built for a
different purpose.**

### Motives make noise intriguing instead of annoying

- **The mistaken** — heard wrong. Innocent, and wrong about other things too.
- **The malicious** — the nemesis, or his agent, pointing you at Martin on
  purpose. **He uses you as the weapon.**
- **The bitter** — the man he displaced. Names the wrong man out of confusion,
  or the right one out of spite.

**The nemesis gets fooled by his own sources too.** One rule, pointed both ways.

### The player's tool: triangulation

- **A false rumour tends to be one voice.** Nobody repeats it, because there is
  nothing to repeat.
- **A true rise keeps appearing** — different men, different places, different
  trades.

> *"I killed Martin for nothing, now it's Trevor… but Gavin started as an idle
> and now I hear he's becoming king. Hmm."*

**Confidence is agreement across independent sources**, and the player learns to
weigh the teller.

### The cost of being wrong is already brutal

Killing an innocent Martin is not a reload. Everything fires at once:

- `village.provoke()` — the town turns on you
- `learn_killers((PLAYER_ID,))` — **the village never forgets**, and the murder
  travels the world by `war.tell`
- `banish(player.nation)` — your own nation, if the mood takes it

**So a false kill costs your standing, paints your name across the continent as
a killer, and tells the nemesis you are hunting** — that you are dangerous *and
that you can be steered*. **From then on he doesn't have to come for you. He
can just point.**

---

## 7. The omen, and the attempt

### Always given, never necessarily heard

**Before every genuine attempt, an omen is spoken** — by a random NPC:

> *"I had a bad dream last night… A lion has killed another lion while he was
> asleep."*
> *"Careless kings do not last long in this world."*

When the nemesis already knows who the player is:

> *"King is cracking down on potential enemies… Finally some order."*
> — the public layer of a private act, and **verifiable**. If he is eliminating
> rivals and you are a rival, you are on a list, and the list was drawn before
> you heard of it. **He found you first.**

**The rule: the warning is always SPOKEN. Whether it REACHES the player depends
on who he is standing near — exactly like the news and the clues.** A man three
provinces away has the dream, tells it, and it dies on the road.

> **Not so the player can always detect it — so that when he dies, he can find
> the five omens he ignored.**

**That is the difference between suspense and unfairness.** *"He'd been telling
me for six days and I slept alone anyway"* versus *"the game killed me."* Same
uncertain data, completely different feeling — and the second makes people quit.

### The drunk is not playing dice

**A true omen and a drunk's ravings are INDISTINGUISHABLE.** This is deliberate
and it is not a flaw.

- **A distinguishable omen is a puzzle, and puzzles get solved.** Once the
  player learns "check the source", it becomes a routine, and a solved puzzle
  produces a wiki entry.
- **An indistinguishable one is a decision under uncertainty**, which can never
  be solved, only argued about.

> **The uncertainty is not noise around the signal. The uncertainty IS the
> content.**

**And it produces culture.** Players will share strategies on how best to treat
it. That is the difference between a mechanic and a *culture* — nobody writes
lore about a lookup table.

### The rate drifts with him

"Once every x times" is only learnable if x moves:

- **Early** — almost every omen is a drunk. The player learns to shrug.
- **Middle** — one in five is real, and someone he knows gets hurt.
- **Late** — the omens are frequent *and* real, because the man has stopped
  guessing and started hunting.

**The player learns the distribution through play, never from the game** — and
learns it approximately, which is the only honest way. By day 200 he has a feel
for it and is still wrong sometimes. **That feel is his, not the interface's.**

### And caution must cost something

**If "be careful" means "stay inside a few days", the uncertainty collapses** —
the optimal play is always be careful, and the omen becomes a tax on the
calendar.

**The safe option must cost the thing you want:**

- **Sleep in a crowd and you lose the day** you would have spent climbing,
  trading, campaigning.
- **Carry a rifle everywhere and you cannot be a farmer.**
- **Stay in the room and the realm runs itself** — elections happen, the ring is
  held, the news goes on.

> **"Staying in the room" is not free. If a peasant rebellion is spreading after
> you have conquered most of the map, the scales turn against you while you
> hide. You must manage the assassination AND the war AND the rebellion AND all
> the King's business.**

**Every omen is a genuine trade: today's progress against your life.**

### The timing

**Once an omen is given, a random day in the next ten is chosen for the
attempt** — sometimes the very next night, sometimes day 9, sometimes day 4 or
7. And sometimes it is only a drunk on the street and nothing happens at all.

### The attempt

Conditions, all of them visible:

1. **He knows who you are.**
2. **You are exposed** — asleep, alone, in the open. **The player's own habits
   choose the risk.**
3. **He has the means** — a rifle and rounds, or an axe.

**The first attempt is a warning, not a die roll.** The player is awakened by a
gunshot wound, or set upon by a man with an axe. **One more and he is dead.**

> **The first shot is the reveal.** Before it he is a rumour; after it he has a
> name, a face and a purpose. The game changes from *rise in the world* to
> *there is a man coming for my chair, and I can go and find him.*

**The mirror holds.** Once the player has the name, he can hunt too. Whoever
knows first has the advantage — **and that must cut both ways or it is theatre.**

### The counters are the ones that already exist

**Do not add a "safe house" verb.**

- **Arms** — a rifle and rounds.
- **Allies** — companions are witnesses; a man is far harder to murder with
  someone standing next to him.
- **Not sleeping alone.**
- **Leaving.** A hunter is tied to the place he knows.
- **Finding the source** — the omen is a *lead*, not just a warning. **The best
  play is investigation, not defence.**

**The game has been quietly teaching him that a lone king asleep in an empty
house is a dead king.**

### The escalation problem

**What happens when the player counters it perfectly every time?** If the answer
is "he is safe", the nemesis becomes a joke after one successful defence.

**So the omen's character escalates as he closes:**

- **Far off** — a dream. *"A lion…"* (dismissible)
- **Closer** — the crackdown, the list, men going quiet. (verifiable, names
  nobody)
- **Close** — **an omen that already knows the player's habits.** *"They say the
  King has asked who sleeps alone in this town."*

**Now the warning is still always given, and hearing it does not save you** —
because the man has already done his reconnaissance on *you*.

---

## 8. Succession

**If the nemesis is killed, the world progresses as normal — UNTIL ANOTHER ONE
IS BORN.**

**And the new one knows all about the player, when the player knows nothing of a
random logger in a faraway province who is planning to take his place.**

### This needs no new rule — it falls out of the knowledge rule

- **He knows the player because the player is notable.** A King is spoken of
  everywhere. **Nobody has to brief him.**
- **The player knows nothing because he is not.** A logger in a far province is
  not a topic of conversation.

**So there is no "seeding system" that grants knowledge.** There is only the
rule: **you know the man ahead of you; you cannot know the man behind you.**
The succession is what that rule looks like when the player is winning.

### Each generation starts harder, for free

- **Nemesis I** — a logger, far away, and the player is a nobody. **Both blind.
  A fair race.** This one *earns* it, and it teaches the player the systems.
- **Nemesis II** — born after the player kills the first. **The player is
  somebody now, so Nemesis II knows him from day one.** The player is the
  hunted. **And it may be someone he already knows.**
- **Nemesis III** — born into a world where the player is King. **He has studied
  him** — and he starts higher, because the ambitious men of the world have
  watched what it takes.

> **No difficulty curve is written. The rule generates one: the better the
> player does, the more he has to lose, and the less he can see.**

**How long is "until another one is born"?** Tie it to the player's own ascent —
**no new nemesis until the player rises a rung, so every promotion buys the next
hunter. Rising is what summons him.**

---

## 9. Companions

**Companions are what make the nemesis personal.** A distant rival you race is a
strategy game. **A friend who was racing you the whole time is a story.**

**And the game already knows who your friends are.** `opinion` — +1 per trade,
each way — records every point of every relationship. **"Who the player's
companions are" is not a new system: it is `sort()` on a dict that already
exists.** The men whose opinion of you is highest *are* the men you have spent
your time with — the farmer from day 1, the trader you ground with from days 3
to 10 and met again on day 37.

> **The nemesis's best disguise is not a mask. It is forty days of honest
> trading.**

**One rule: the companion-nemesis must not be the FIRST one.** The first teaches
the player how the world works. **The betrayal has to land on someone who
understands the systems well enough to feel stupid**, or it is a cheap trick.

---

## 10. The world he needs — interactivity

**The nemesis is only interesting in a world with pressure and with verbs.**
These are prerequisites, roughly in build order:

### 10.1 Drought → peasant rebellion *(the missing piece)*

**Right now war only kills soldiers.** The famine that was measured killed 498
people (747 → 249) and **nobody did anything about it.** The starving died
without acting. **That is not a pressure, it is a leak.**

**A rebellion is the difference between a disaster and a situation.** Pieces in
place:

- **Drought** — a season flag suppressing harvests (`crop_yield`, `GROW_SECONDS`)
- **The granary empties** — already measured: `Iron Crossing: granary
  {'wood': 18}` with a hundred loaves in people's packs
- **`DOLE_LAST` fails** — the floor under the economy gives way, which is what
  it was built to signal
- **And that is when they act** — not starve. `village.provoke()`, the aggro
  system, `learn_killers`

**The rebellion targets the wealthy: it takes the ledger — which belongs to the
mayor, and half of which the crown took (`crown_dues`).**

- Player is a nobody → he watches it. Texture.
- Player is the mayor → **it is aimed at him.**
- Player is the King → **it is his tax they are burning.**

**A drought is a question only a man with a position can fail.**

### 10.2 Hiring — the player as employer

`hire()` exists, but it is the *town* hiring the *player*. **The inverse is
small and its consequences are large:** `npc.employer = player`, a wage paid
daily out of the player's pocket.

**The moment the player pays a man, he has a liability** — wages every day,
harvest or not. **A drought makes every hired man a drain instead of an asset.**

### 10.3 Mercenaries → storm the capital → proclaim yourself King

**This gives the throne a second door.** Right now the crown is a sporting prize
(the tournament). **A coup makes it political.**

- **Mercenaries are not levies.** `levy_pool`/`muster` draw from your own
  nation's population — villages lose workers. **Mercenaries are paid, foreign,
  owed nothing, and nobody's village is emptied to raise them.**
- **The capital has a garrison** — `staffing()` includes `defender` slots and a
  commander.
- **`occupy` and `crown()` already exist.** The investiture is written; it just
  needs an army at the gate instead of a bracket.

**Open question: what makes a coup legitimate?** If it always crowns you, the
tournament is pointless. **Proposal: win the ring and the realm accepts you; win
a coup and half the mayors refuse you, and you spend fifty days putting down the
ones who will not bend. Same chair, different price.**

### 10.4 Founding a nation

Every village has a `nation` id the war machinery reads, so a new id works.
**But a nation is not a declaration, it is a place.** Two options:

- **Take an existing village and re-flag it** — a `_settle`-style operation,
  almost free. **Build this first.**
- **Found a settlement** — clear ground, houses, settlers. The original vision,
  and a large piece of work.

---

## 11. Design commitments

1. **Never explain any of it.** No danger icon, no tutorial line, no tooltip.
   **The only manual is what the player survives and what other players tell
   him.** The moment you explain it, you delete the community's reason to exist.
2. **Knowledge is the progression.** Not levels, not gear. The player who has
   died three times to this system carries that knowledge into the next world
   even though the character does not.
3. **No scripted meetings.** The crossing is emergent — the ring, war, trade,
   refugees, elections. Every one of those already exists.
4. **Nothing he does is beyond the player.** Every rung is a rung any villager
   could climb: `offer_post`, `free_post`, `sell_vote`, `hold_election`,
   `Tournament`, `levy_pool`. **The day it works for him, it works for any NPC
   you hand a plan to.**
5. **The leader is the vulnerable one, and success is what makes him
   findable.**

> **The rebellion and the nemesis say the same sentence: rising makes you a
> target.**
>
> A drought makes the rich man's granary the mob's destination. A name makes the
> notable man the hunter's destination. **Both punish success, and neither
> punishes it unfairly — both can be seen coming if you are paying attention.**

---

## 12. Open questions

1. **What counts as "the lead"?** Proposal: `(rank, coin)` — the same tuple
   `hold_election` already uses to break a tie, so standing has one definition
   in the whole game. But **is a rich smith ahead of a poor mayor?**
2. **Should the player ever get the name while ahead — at a cost?** Proposal:
   **the first attempt IS the reveal.** The shot is the price of the name.
3. **Can the player choose NOT to rise?** If a man stays a farmer for three
   hundred days, is he safe? **He should be — and that means the nemesis's rise
   is unopposed, and one day the news arrives that his province has a new lord.
   A quiet life should be a valid, losing and interesting way to play.**
4. **Can the player plant a rumour?** He can kill, trade and vote, but he cannot
   yet *speak*. **If he could lie, the trap would cut both ways and the game
   becomes genuinely strategic.** This needs a way for the player to talk to a
   man, which does not exist.
5. **Is the nemesis killable, and is that an ending?** Yes. **The nation
   outlives him and fragments; the world gets a little quieter.**
6. **Can the world kill him** — a wolf, a war, the tournament? **A nemesis the
   world can kill is more real, but most playthroughs would lose the arc.**

---

## 13. What already exists

| need | already in the code |
|---|---|
| trust / relationship | `opinion` (+1 per trade, cap 100), `regard` |
| the electoral rung | `sell_vote`, `hold_election`, `install_mayor`, `election_candidates` |
| the crown | `Tournament`, `candidates_for_crown`, `Village.crown` |
| scheming | `offer_post`, `free_post`, `_fill_vacancies` |
| skill saturation | `skills.py` — `farming` 0..8, `axe`/`movement`/`shooting` 0..1 |
| latency & news | `war.tell`, `note_capture`, `prune_news`, `WAR_NEWS_LIFETIME` |
| the cost of a false kill | `village.provoke`, `learn_killers`, `banish`, `_see_murder` |
| the knowledge model | `NPC.witness`, `known_since`, `knows`, `forget` |
| war | `levy_pool`, `muster`, `occupy`, `Army`, `nearest_enemy`, `declare` |
| the economy to rebel over | `crown_dues`, `ledger_goods`, `dole`, `store_take` |
| telling the player | the news speech bubble, the toast |

---

## 14. The first experiment

**One ordinary man, seeded in a small far-side village, with three things:**

1. **A rank table** and a refusal — he can decline a post below him and hold out
   for one above.
2. **A memory of what he tried and whether it worked.**
3. **The same laws as everybody else.** No buff. No omniscience. No scripted
   meeting.

**Then run 300 days and read the log:**

- **Does he take a post, save, and win an election within ~150 days?** If not,
  the ladder is too steep — **tune `ELECTION_BRIBE` or the village size, never
  his stats.**
- **Does his name start appearing in `war.tell` news?**
- **Does he enter the ring?**

**That is the experiment that tells us whether the concept is sound** — and it is
the one thing a 30-day run can never answer.

---

## 15. The world tells you first

**A mechanic for later, recorded here so it isn't lost.**

**The nemesis never gets a marker, an icon or a line of UI.** But the *world* should
carry the warning — because the world is the one thing the player already trusts
to be honest.

### The blood moon

**When he rises a rung, or in the days before a strike, the night is RED instead
of black.** Not a red sky — *the dark itself*, the way a night with a fire over
the hill looks. The player will notice it long before he understands it.

### And the rest of the sky

- **Lightning**, over a village he is not standing in.
- **Sound** — a low note, a bell, a dog going mad three streets away. *We have
  not touched audio at all, and that is correct for now; the visual channel is
  already there and costs nothing.*
- **Animals**, eventually: the wolves restive, the birds gone.

### Why this is better than an icon

1. **It is diegetic.** Nothing is telling the player anything; the world is
   simply *like that* tonight.
2. **It is deniable.** A red moon might be a season, a storm, or nothing at all.
   **That is the same property the drunk has** (S7) — and it is what keeps the
   player deciding instead of knowing.
3. **It does not explain itself**, so it produces folklore — *"red sky, sleep
   indoors"* passed from player to player. **The community writes the manual.
   That is the whole point of S11.**
4. **It scales with him.** Early, a warning is a drunk's words in the street.
   Late, the sky itself changes. **The world's dread grows as he does.**

### The one rule: ALWAYS the signal, never accurate about WHEN

**The blood moon is never noise.** If it rises, something is coming — that is
not in doubt, and the player should learn to be certain of it.

**What is uncertain is WHEN.** Could be tomorrow. Could be seven days. Could be
the night after next, or the fifth night, and the player will sleep badly for
all of them.

**This is a different channel from the drunk (S7), and the two are deliberately
opposite:**

| | does it mean anything? | when? |
|---|---|---|
| **the drunk in the street** | **unknown** — usually nothing | — |
| **the blood moon** | **always** | **unknown — tomorrow, or seven days** |

**The drunk makes you wonder whether. The moon makes you wait.** One is doubt,
the other is dread, and between them a player never gets to relax.

**And it cannot be turned into a tracker**, because knowing that something is
coming tells you nothing about where to stand — only that you have a week to
decide what to do about it. **The uncertainty is moved from whether to when,
which is a much worse thing to live with.**

### Where it would hook in

- **`night_factor()`** already exists and decides how dark it is — a blood moon
  is a second return value, or a tint applied where the night is drawn.
- **The darkness is a colour**: black becomes something like `(58, 14, 14)`,
  which reads as red without becoming a red screen.
- **Lightning** is a one-frame white flash at a position — cheap, and it needs no
  new machinery beyond where effects already spawn.

---

# Part II — the two trees (design, not built)

Recorded 29 Oct, from the user. This is a *design*, to be argued with before
anything is written.

## 16. Peacetime and war are two different games

**The state answers in the register in which it is attacked.**

| | **Peacetime** — the player is building an income | **War** — the player is taking settlements |
|---|---|---|
| who answers | the **service**: the chief, his agents, the dossier | the **state**: the crown, the army, the levy |
| what it is | a **police matter** | a **civil war** |
| what it looks like | watching, relaying, a dossier, gates, an envoy, a raid on a yard | columns, sieges, requisitions, garrisons, a province in revolt |
| what can be lost | goods, men, your cover, your stall, a worker turned | ground, towns, the yard, whole squads |
| the other side's rules | there are rules: warrants, budgets, a chief who must justify men | **everything goes** |
| how it ends | you are ruined, bought, or you cut the head off the service | you win a province, or the army takes everything |

**The point of the split:** the same crimes should feel *completely different*
depending on how far the player has pushed. Stealing leaf and selling it is a
policeman's problem; burning a town's garrison is the army's. A service that
tries to police a civil war is what makes totalitarian worlds feel silly — and
an army that intervenes in a smuggling case is what makes them feel cheap.

**What flips it (proposal, for the user to decide):**

* Peacetime → War when the player **takes a settlement** (occupies it, or kills
  its garrison and holds the gate) — or joins a nation's war with his own men.
* War → Peacetime when the player is **driven out** (no towns held, no nation
  backing) and the crown considers the revolt finished. The dossier survives the
  peace; the war does not erase it.
* The **service keeps working in war**, but as *military intelligence*: it stops
  raiding your yard and starts mapping your army — your commanders, your
  holdings, your supply. Which is the next section.

## 17. The tree — and the one he keeps of you

### The shape

Both sides are a **tree of people**, not a progress bar. The player sees the
service's tree as far as he has *learned* it; the chief sees the player's
organisation the same way. Nodes are men, edges are *who reports to whom*:

```
                    [ ? ]  the chief — identity unknown
                    /   \
             [agent]     [agent]
             /     \         \
      [agent]     [turned]   [ ? ]     <- an unknown branch: a man you
                                          have not met, turned or killed
```

* **A node you have not learned is `[ ? ]`** — a shape on the chart with no name,
  known to exist only because *someone* reports to it (a courier left a place, a
  prisoner named a patch).
* **Learning a node** = interrogating an agent, turning him, or finding his name
  in another's head (`KNOWERS` already answers "who knows this fact").
* **The root is the chief**, and his identity is the last thing the tree gives
  up. You climb by **killing, turning and interrogating** — and by *following*
  (a courier's route is an edge made visible).

### The chief's tree of you

He starts with nothing but the places your crimes happened. His tree grows by
the same rules:

* he **knows a place** (the fact names it) — a yard, a town where your men sell;
* he **knows a man** (a worker of yours, seen at that place; a trader you always
  deal with);
* he **knows you** only when enough of your nodes are confirmed — and *that* is
  what turns the police ladder from "the yard in the wild" into "the man who
  owns it".

Which gives the game its spine: **two organisations are mapping each other at
once**, and the first to own the other's root wins — you by killing or turning
the chief, him by opening the warrant on you (or, in war, by mapping your
commanders).

### Nodes morph — that is the whole point

The trees are **not static**: every recruitment, every death, every turning
changes the shape.

* **His side:** a killed agent's patch is **re-assigned**; the tree re-wires, and
  a gap you thought you had made is filled by a man you have never seen. A
  **turned** agent shows as *yours* on your chart (and as *his* on his, until he
  learns otherwise).
* **Your side:** a new worker, a new hub, a new stall is a new node — and your
  bitter men can be turned from under you (`turn_the_bitter` already does the
  first half of this). A man you fire **stays on his tree** as somebody who knows
  your yard.
* **A turned node is the strongest thing on either side**: he keeps his post, his
  patch, and his place in the other tree — so he reports both ways. That is why
  turning must be **harder than killing** (leverage, not a coin flip) and why it
  is the reward: one turned agent is worth five dead ones.

### Turning — how it should work (proposal)

Killing an agent is a fight. Turning one is a **negotiation with a man who is
afraid of his own chief**:

| lever | why he breaks |
|---|---|
| money | his wage is 30 a day from a town's purse; you can beat it, once |
| grudge | he blames the chief for a dead brother, a ruined town, a unpaid month |
| fear | you know his name and where his family sleeps — *he knows you know* |
| evidence | you show him the dossier on **himself** — the chief was going to hang him too |
| faith | in war, the province you hold is the one that pays him now |

And the price of a failed turning must be real: the man walks away and tells the
chief *everything the conversation revealed* — including that you know his name.

### Misinformation and interrogation — the mental game

**Interrogation (both directions).** A held man talks, and what he says is a
*fact* in the same system that already exists (`FACTS`/`KNOWERS`):

* **agents interrogate townsmen** — who sold what, where, to whom. (This is how
  the chief builds *his* tree of you.)
* **the player and his men interrogate agents** — names, patches, couriers, the
  shape of the branch above them. `KNOWERS` already knows who holds which fact;
  the missing thing is the *act* of taking it from a living man.

**Misinformation.** The tree is made of *beliefs*, so it can be poisoned:

* a **false fact** (a forged place, a false name, a planted witness) that the
  chief acts on: a raid on the wrong yard, a courier sent the wrong way, an
  agent arrested by his own side;
* a **false node**: your own man posing as an agent, so a branch of his tree
  reports to you;
* and the counter: **verify**. The service should be able to spend men checking
  a fact — and a player who lies too often should be caught lying, which is
  worse than being caught smuggling.

**The design rule to keep it honest:** every belief in either tree must be
traceable to *the head it lives in*. No node exists because the UI says so; it
exists because a man knows it, and if that man dies, the knowledge dies with him
(unless he told someone — which is what couriers and interrogations are for).

## 18. Open questions for the user

1. **Who recruits his agents?** The chief alone, or does each agent recruit in his
   own town (so the tree grows by itself and can be cut branch by branch)?
2. **What does the player see, on screen?** A chart screen ("the Service") opened
   from the journal, or a physical thing — a wall in a safehouse, a notebook that
   fills in as he learns?
3. **How does a turning begin?** A dialogue option on a man he has beaten or
   captured (needs the fight), or a conversation with leverage (needs the
   knowledge first)?
4. **Can the chief be replaced by his own tree?** If you turn the man *below*
   him, does that man become the chief when the chief dies — meaning the tree
   survives decapitation, and you have to turn your way *up* rather than kill
   your way in?
5. **War mode and the trees:** in civil war, is the tree the army's chain of
   command (so killing a colonel breaks a column), or does the service keep its
   own shadow tree beside it?
6. **Misinformation's cost:** should a lie cost money, a favour, or a man (a
   witness who must be produced and can be found out)?
