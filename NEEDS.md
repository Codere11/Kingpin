# WHAT A PERSON NEEDS (measured in a running game, one full day)

Fresh world, 21x clock (one game day in ~28 real seconds), the whole register
sampled before and after: 1,058 people, 527 houses. Nothing simulated outside
the game.

## The measurements

| what | measured | how |
|---|---|---|
| **food** | **1.69 meals per person per day** | hunger burns 101 a day and one meal is 50; the mean man ended the day at +16 instead of +101, so 85 hunger was eaten |
| **a larder** | **5 food items** is what a man wants to hold (`STOCK_FOOD`), and **1 of each kind** he has none of | `economy.wants` on 80 real villagers: bread 1-4, berries 1-4, cactus fruit 1-4 |
| **firewood** | a house burns **5 logs a day** where it can get them | `WOOD_PER_HOUSE = 5.0`; measured warmth burnt across 527 houses = 0.69 a day, i.e. most houses had no wood at all |
| **a woodpile** | a man wants **8 logs in one purchase**, up to a **20-log stack** | `wants(wood) -> 8` for 80 of 80 villagers |
| **cigars** | **everybody's smoke is a cigar**; **1.01 a day per addict**, **0.28 a person a day** | 514 of 1,058 have an addiction (49%), mean 0.27; craving rises 1.0/day x addiction and resets when one is smoked |
| **drink** | 1.01 a day per drinker; want is **1 at a time** | 330 beer / 354 liqueur / 374 mezcal as their drink |
| **raw leaf** | **nobody wants it**: 0 of 80 villagers answered anything but 0 | only the artisan's bench wants leaf: **24** (`LEAF_STOCK`) |
| **iron** | only a smith: wants **15-16** more, up to **48** (`IRON_STOCK`) | `wants(iron)` over the cohort |
| **tools** | **2** when he needs one, 0 otherwise | `wants(axe/shovel)` = 0 for all 80 |
| **seeds** | farmers only, 1 | `wants(wheat_seed)` = 1 for 1 of 80 |

## What "enough" therefore is

The game already knows every one of these numbers -- `economy.wants(buyer,
item)` is the law the NPC market obeys:

    food      ->  up to a larder of 5, buying 1-4 at a time
    wood      ->  up to a 20-log stack, buying 8 at a time
    cigar     ->  1, only when craving >= 0.28
    drink     ->  1, only when craving >= 0.28
    leaf      ->  24, artisan only
    iron      ->  48, smith only
    tools     ->  2, and only if he needs one
    seeds     ->  1, farmer only
    anything else -> 1, at a 3% chance

**The player's sale path is the only thing that does not obey it.** A buyer
stops at his stock target in the town market, but the player can keep selling
him logs: the only limits on that path are the man's purse and small per-click
caps, so a village can end up destitute with a woodpile.

So the fix is one rule: **the player cannot sell a man more than that man
`wants` of the item**. He buys to his target -- two days' worth for food and
fuel, one at a time for a luxury, a bench-full for a trade input -- and then he
says he has enough, whatever is left in his purse.
