"""War: the crown raises an army and marches it at the neighbours.

The purse decides.  When a capital's ledger is deep enough the King calls up
the idle men of his nation -- the ones with no trade, no plot and no post --
stands them in a column, and sends them at the nearest village flying another
flag.

Fighting is not re-implemented here.  A levied man is turned into an ordinary
Soldier, so the enemy guards shoot him with the same guns, by the same code,
that shoot wolves and raiders.  What this module owns is the muster, the
march, and the reckoning afterwards: who came home, who did not, and who owns
the village now.
"""

import math
import random

import economy
import fence

import creatures

WAR_CHEST = 4000          # a capital will not march on less than this
LEVY_SHARE = 0.70         # of a realm's idle men
MIN_ARMY = 6
PAY_PER_MAN = 25          # a soldier's pay, on the day he comes home
WAR_COOLDOWN = 3          # days of peace between one crown's wars
SPOILS = 0.50             # of a fallen village's ledger, to the conqueror
FALL_REACH = 700.0        # how close the column must be to take the square

STANDING: list = []       # the standing army: bodies at the capital, idle

# -- THE NEWS OF THE WAR ------------------------------------------------------
# What a man knows about the fighting, and for how long. Fifteen days and it is
# stale: "meh, every day some village falls". The crown's own picture is only
# ever what has physically REACHED it.
WAR_NEWS_LIFETIME = 15.0 * 600.0     # fifteen days and a man stops caring
KING_WINDOW = 5.0 * 600.0            # "the last five days of my army"
KING_DEADLINE = 3.0 * 600.0          # three days to bring it in
KING_BOUNTY = 25                     # per report, before the size multiplier
KING_MULT_MAX = 5.0                  # a big column is worth far more than a raid
_AID = [0]


def _next_aid() -> int:
    _AID[0] += 1
    return _AID[0]


def prune_news(holder, now: float) -> None:
    n = getattr(holder, "news", None)
    if n:
        n[:] = [e for e in n if now - e[0] < WAR_NEWS_LIFETIME]


def note_capture(army, target, now: float) -> None:
    """The town falls, and EVERYONE there remembers which column did it.

    Both sides. The column because it was their doing, and the TOWN because
    those are the people who will run for the next village up the road -- and
    they, not the victors, are how the king this place belonged to ever finds
    out he has lost it.
    """
    strength = army.strength()
    item = (float(now), target.name, army.aid, strength, army.nation)
    carriers = [m for m in army.soldiers if getattr(m, "alive", False)]
    carriers += [n for n in target.npcs if getattr(n, "alive", False)]
    for man in carriers:
        if not hasattr(man, "news"):
            man.news = []
        man.news.append(item)
        prune_news(man, now)


def tell(a, b, now: float) -> int:
    """Two parties tell each other the news of the war.

    The same shape as the murderer's story -- knowledge is CARRIED, never
    broadcast -- but on its own clock and with its own shrug. Returns how much
    was news to ``a``.
    """
    an, bn = getattr(a, "news", None), getattr(b, "news", None)
    if an is None or bn is None:
        return 0
    def key(e):
        return (e[1], e[2], round(e[0]))
    have_a = {key(e) for e in an}
    have_b = {key(e) for e in bn}
    gained = 0
    for e in bn:
        if now - e[0] >= WAR_NEWS_LIFETIME or key(e) in have_a:
            continue
        an.append(e)
        have_a.add(key(e))
        gained += 1
    for e in an:
        if now - e[0] >= WAR_NEWS_LIFETIME or key(e) in have_b:
            continue
        bn.append(e)
        have_b.add(key(e))
    prune_news(a, now)
    prune_news(b, now)
    return gained


def post_demand(capital, armies, now: float):
    """The crown wants to know how its OWN war is going."""
    mine = [a for a in armies if a.nation == capital.nation and not a.done]
    if not mine:
        capital.demand = None
        return None
    best = max(mine, key=lambda a: a.strength())
    capital.demand = {"aid": best.aid, "strength": best.strength(),
                      "posted": now, "expires": now + KING_DEADLINE,
                      "window": now - KING_WINDOW}
    return capital.demand


def pay_for_news(capital, npc, now: float) -> int:
    """A trader at the capital is paid for word the crown does not have.

    Only for the column it asked about and only inside the five-day window;
    never twice for the same thing; and the bigger the force, the bigger the
    purse. Anything else is a rumour, and the crown is not a fool.
    """
    demand = getattr(capital, "demand", None)
    if not demand:
        return 0
    if now > demand["expires"]:
        capital.demand = None               # the rider is too late
        return 0
    known = getattr(capital, "news", None)
    if known is None:
        capital.news = known = []
    have = {(e[1], e[2], round(e[0])) for e in known}
    paid = 0
    fresh = []
    for e in list(getattr(npc, "news", [])):
        when, place, aid, strength, nation = e
        if aid != demand["aid"] or when < demand["window"]:
            continue
        k = (place, aid, round(when))
        if k in have:
            continue                        # he will not pay twice
        mult = 1.0 + min(KING_MULT_MAX, strength / 8.0)
        reward = int(round(KING_BOUNTY * mult))
        paid += reward
        npc.coins += reward
        fresh.append(e)
        have.add(k)
    if fresh:
        known.extend(fresh)
        prune_news(capital, now)
        capital.ledger_coins = max(0, int(capital.ledger_coins) - paid)
    return paid
MARCH_SPEED = 240.0       # px/s, the same step a soldier always took
SOLDIER_RATION = 10       # what the crown issues each man at enlistment
RATION_AT = economy.EAT_AT
MIN_MARCHING = 10         # below this the column goes home instead of on
REINFORCE_EVERY = 120.0   # s between drafts from the capital
REINFORCE_BATCH = 12      # men per draft
ARMY_CAP = 170            # a column has a size, and it is not infinite
REINFORCE_COST = 30       # the crown pays this per man, up front
REINFORCE_KEEP = economy.CROWN_BUFFER   # ...but never touches the floor
LAST_STAND = 20.0         # s of held walls before the die-hards break too
REFUGEE_SPEED = 150.0     # px/s on the road, tired, carrying what they can
MESSENGER_PAY = 30        # "we must tell the king" -- and what it is worth

# -- WHO A CROWN MAY TAKE, AND IN WHAT ORDER ---------------------------------
# Not just "any working man". A levy spends what a village can spare, most
# expendable first, and every village keeps the men it cannot do without.
LOGGER_FLOOR = 4          # woodsmen a village always keeps (3-5)
LOGGER_FLOOR_CAPITAL = 8  # ...and a capital keeps twice as many
FARMER_KEEP = 0.5         # at most half the farmers go: they are the bread
FARMER_KEEP_CAPITAL = 0.75  # a capital keeps half again as many back


def crown_food(capital) -> int:
    """Rations the crown has in its own granary, in man-days.

    INT, ALWAYS. It is a count of loaves, and the ledger can hold fractional
    quantities -- so summing them gave a float, `crown_food() // SOLDIER_RATION`
    gave a float, and `pool[:take]` raised "slice indices must be integers" the
    moment a column was either mustered or reinforced. Both of those paths feed
    a list slice, and a slice needs an int no matter how the count was arrived
    at.
    """
    return int(sum(capital.ledger_goods.get(k, 0) for k in economy.FOOD))


def enlist(village, npc) -> None:
    """A man called up stops being a villager.

    He is not a mouth for his home village to feed and he is not a pair of
    hands for it to rely on -- his raids and the crown keep him.
    """
    npc.levied = True
    village.free_post(npc)
    if npc in getattr(village, "npcs", ()):
        village.npcs.remove(npc)


def issue_entrenching_tool(capital, npc) -> bool:
    """EVERY SOLDIER IS ISSUED A SHOVEL ALONGSIDE HIS MUSKET.

    A soldier digs -- earthworks, gabions, graves. And when the campaign is
    over and he SETTLES in the village he took, the shovel is the tool of his
    new trade. Without it he stands on a farm plot with empty hands, and
    _work_field sends a man who cannot till to the market instead of the
    field: the captured village then grows no bread while its own people are
    refugees on the road. That is how a taken town starved behind a full
    granary.

    It is an ISSUE, not a condition of service. The levy takes idle men first
    and an idle man owns no shovel, so demanding one before he could be called
    up would empty the muster roll and no war would ever be declared. The
    crown draws it from its own store, and fails quietly if it has none --
    the man then buys one on the road like anybody else.
    """
    if npc.stock.get("shovel", 0) > 0:
        return True                     # he has one in his hands already
    have = int(capital.ledger_goods.get("shovel", 0))
    if have > 0:
        capital.ledger_goods["shovel"] = have - 1
    npc.stock["shovel"] = npc.stock.get("shovel", 0) + 1
    return True


def issue_rations(capital, soldier, amount: int = SOLDIER_RATION) -> int:
    """The crown feeds its own men, out of its own stores."""
    left = int(amount)
    got = 0
    for item in economy.FOOD:
        if left <= 0:
            break
        have = capital.ledger_goods.get(item, 0)
        if have <= 0:
            continue
        take = min(have, left)
        capital.ledger_goods[item] = have - take
        got += take
        left -= take
    soldier.food = got
    soldier.hunger = 0.0
    return got


def feed(army, dt: float) -> None:
    """Rations. A belly empties in a day; half a loaf fills it again."""
    for s in army.soldiers:
        if not s.alive or getattr(s, "settled", False):
            continue
        s.hunger = getattr(s, "hunger", 0.0) + economy.HUNGER_RATE * dt
        if s.hunger >= RATION_AT and getattr(s, "food", 0) > 0:
            s.food -= 1
            s.hunger = max(0.0, s.hunger - economy.EAT_BY)
        elif s.hunger >= economy.STARVE_AT:
            s.health = 0


def march(army, dt: float) -> int:
    """Walk the column. From the ARMY'S OWN LIST, not from any shared roster."""
    steps = 0
    for s in army.soldiers:
        if not s.alive or getattr(s, "settled", False):
            continue
        mt = s.march_target
        if mt is None:
            continue
        hv = getattr(s, "home_village", None)
        tv = getattr(s, "march_village", None)
        goal = mt
        if hv is not None and hv.fence_rect.collidepoint(s.x, s.y):
            gwx, gwy = fence.gate_world(hv)
            gox, goy = fence.OUTWARD[hv.gate_side]
            lat, dep = getattr(s, "rally_off", (0.0, 0.0))
            goal = (gwx + gox * dep - goy * lat, gwy + goy * dep + gox * lat)
        elif tv is not None and not tv.fence_rect.collidepoint(s.x, s.y):
            side, gxw, gyw = fence.nearest_gate(tv, s.x, s.y)
            ox, oy = fence.OUTWARD[side]
            goal = (gxw - ox * 120.0, gyw - oy * 120.0)
        dx, dy = goal[0] - s.x, goal[1] - s.y
        n = math.hypot(dx, dy)
        if n < 1e-6:
            continue
        step = MARCH_SPEED * (s.skills.move_scale()
                              if getattr(s, "skills", None) else 1.0)
        s.x += dx / n * step * dt
        s.y += dy / n * step * dt
        s.facing = (dx / n, dy / n)
        if getattr(s, "skills", None) is not None:   # a march is walking
            s.stamina = min(s.max_stamina, getattr(s, "stamina", 0.0)
                            + 15.0 * s.skills.stamina_scale() * dt)
        if math.hypot(mt[0] - s.x, mt[1] - s.y) < 130.0:
            s.march_target = None
            s.march_village = None
        steps += 1
    return steps


def friendly_neighbours(registry, village, limit: int = 4,
                        reach: float = 160000.0):
    """Where the people run: the nearest villages still flying their flag."""
    out = []
    for v in registry.villages:
        if v is village or getattr(v, "nation", None) != village.nation:
            continue
        d = math.hypot(v.x - village.x, v.y - village.y)
        if d <= reach:
            out.append((d, v))
    out.sort()
    return [v for _d, v in out[:limit]]


def rout(village, dests, now: float = 0.0, immediate: bool = False) -> int:
    """The civilians run for the gates, in roughly equal shares."""
    if getattr(village, "_routed", False) or not dests:
        return 0
    village._routed = True
    people = [n for n in village.npcs
              if n.alive and not n.defender
              and not getattr(n, "is_commander", False)
              and not getattr(n, "is_king", False)
              and not getattr(n, "is_mayor", False)]
    random.shuffle(people)
    for npc in village.npcs:              # everybody comes out to it
        if getattr(npc, "alive", False):
            npc.asleep = False
            npc.in_interior = False
    import village as _village
    # ONE OF THEM RIDES FOR THE KING. Somebody always says it -- "we must tell
    # him" -- and he does not stop at the next town like the rest of them. He
    # goes the whole way, on his own, and he is paid for it when he arrives.
    king_run = village.capital()
    if king_run is village:
        king_run = None
    for i, npc in enumerate(people):
        dest = dests[i % len(dests)]
        if i == 0 and king_run is not None:
            dest = king_run
            npc.king_run = True        # he carries it for the crown, not for a bed
        npc.refuge = dest
        # A REFUGEE IS ON THE ROAD FROM THAT MOMENT. This used to happen only
        # when `immediate` was set, and not one caller ever set it -- so the
        # run was marked, nobody left the village, refugees_on_the_road never
        # saw them, and no town down the road was ever told what they had
        # watched happen. The flag is kept for callers; the road is not
        # optional.
        if npc in village.npcs:
            village.npcs.remove(npc)
        if npc not in _village.TRAVELLERS:
            _village.TRAVELLERS.append(npc)
        npc.refuge_eta = now + (math.hypot(dest.x - npc.x, dest.y - npc.y)
                                / REFUGEE_SPEED)
        npc.panic = 60.0
        npc.aggro = False
    return len(people)


def raid_luxuries(army, target) -> int:
    """The good stuff, out of the town's own ledger, shared out."""
    wanted = tuple(economy.LEAF) + tuple(economy.LUXURY)
    looted: dict = {}
    for item in wanted:
        have = target.ledger_goods.get(item, 0)
        if have > 0:
            looted[item] = have
            target.ledger_goods[item] = 0
    if not looted:
        return 0
    men = [s for s in army.soldiers
           if s.alive and not getattr(s, "settled", False)]
    order: list = []
    for item, qty in looted.items():
        order.extend([item] * qty)
    random.shuffle(order)
    _pl = getattr(army, "player", None)
    if _pl is not None and not _pl.dead:
        men = men + [_pl]                 # the enlisted player gets his share
    if men:
        for i, item in enumerate(order):
            s_ = men[i % len(men)]
            man = getattr(s_, "home_npc", None)
            if man is not None and man.alive:
                man.stock[item] = man.stock.get(item, 0) + 1
            elif s_ is _pl:
                s_.loot_items = getattr(s_, "loot_items", [])
                s_.loot_items.append(item)
    return len(order)


def resupply(soldier) -> int:
    """A rifleman buys his own rounds. Ammo is a NEED, not a ration."""
    if getattr(soldier, "melee", True) or getattr(soldier, "ammo", 0) >= economy.AMMO_WANT:
        return 0
    man = getattr(soldier, "home_npc", None)
    if man is None or not man.alive:
        return 0
    v = getattr(man, "village", None)
    if v is None:
        return 0
    price = v.prices.get("ammo", economy.ITEM_VALUE.get("ammo", 8))
    want = economy.AMMO_WANT * 2 - getattr(soldier, "ammo", 0)
    afford = int(man.coins // max(0.01, price))
    take = min(int(v.ledger_goods.get("ammo", 0)), want, afford)
    if take > 0:
        v.ledger_goods["ammo"] = int(v.ledger_goods.get("ammo", 0)) - take
        v.ledger_coins += int(round(price * take))
    else:                                  # nothing on the shelf: ask around
        for n in v.npcs:
            if take >= want:
                break
            have = int(n.stock.get("ammo", 0))
            if have <= 0:
                continue
            a_take = min(have, want - take,
                         max(0, int(man.coins // max(0.01, price)) - take))
            if a_take <= 0:
                break
            n.stock["ammo"] = have - a_take
            n.coins += int(round(price * a_take))
            n.book_in = getattr(n, "book_in", 0.0) + price * a_take
            take += a_take
    if take <= 0:
        return 0
    cost = int(round(price * take))
    man.coins -= cost
    man.book_out = getattr(man, "book_out", 0.0) + cost
    soldier.ammo = getattr(soldier, "ammo", 0) + take
    return take


def nearest_enemy(registry, capital):
    """The closest village that answers to somebody else's flag."""
    best, best_d = None, None
    for v in registry.villages:
        if v is capital or getattr(v, "nation", None) == capital.nation:
            continue
        if getattr(v, "is_hub", False):
            continue        # the state does not admit that it exists
        d = math.hypot(v.x - capital.x, v.y - capital.y)
        if best_d is None or d < best_d:
            best, best_d = v, d
    return best


def _settle(npc, target) -> None:
    """A soldier takes off his kit and becomes a neighbour."""
    old = getattr(npc, "village", None)
    if old is not None:
        old.free_post(npc)
        if npc in getattr(old, "npcs", ()):
            old.npcs.remove(npc)
    npc.village = target
    npc.nation = target.nation
    npc.team = ("nation", target.nation)
    npc.job = None
    npc.workplace = None
    npc.farm_plot = None
    npc.farm_plots = []
    npc.levied = False
    npc.refuge = None
    npc.defender = False
    npc.aggro = False
    npc.panic = 0.0
    npc.flee = 0.0
    ang = random.uniform(0.0, 2.0 * math.pi)
    dist = random.uniform(0.30, 0.80) * target.radius
    npc.x = target.x + math.cos(ang) * dist
    npc.y = target.y + math.sin(ang) * dist
    if npc not in target.npcs:
        target.npcs.append(npc)
    target.settlers = getattr(target, "settlers", 0) + 1


def keep_weapon(npc, soldier) -> None:
    """A SETTLED SOLDIER KEEPS HIS WEAPON AND THE ROUNDS HE STILL CARRIES.

    He was never disarmed -- the musket simply never changed hands, and so
    ceased to exist. The rifle was drawn OUT of the crown's ledger at muster
    and nothing ever put it back: that is where the guns that "went missing"
    actually went, one per soldier who ever took a post. Now the man owns it.

    An NPC's weapon is read off his own pack -- see NPC.weapon_of, which
    returns "rifle" for anybody holding one -- so a veteran who keeps his
    musket IS a man with a musket, and what he does with it afterwards is his
    own business. A melee man keeps the axe he was issued, which is a tool as
    well as a weapon.
    """
    weapon = getattr(soldier, "weapon", None)
    if weapon == "rifle":
        import guns as _guns
        kind = ("shotgun" if getattr(soldier, "gun_kind", None) == _guns.SHOTGUN
                else "rifle")
        npc.stock[kind] = npc.stock.get(kind, 0) + 1
        rounds = int(getattr(soldier, "ammo", 0) or 0)
        if rounds > 0:
            npc.stock["ammo"] = npc.stock.get("ammo", 0) + rounds
    elif weapon == "axe":
        npc.stock["axe"] = npc.stock.get("axe", 0) + 1


def occupy(army, target) -> int:
    """The garrison: one man for every post the village has.

    An enlisted PLAYER is in the pool with everyone else, and no better off:
    the men are shuffled and the first posts-worth are taken, so his chance is
    the same as any soldier's. If he is picked he takes the post like the rest
    of them -- and then he owes the village his labour, which is a thing that
    can be deserted just as a campaign can.
    """
    slots = target.staffing()
    pool = [s for s in army.soldiers
            if s.alive and not getattr(s, "settled", False)]
    _pl = getattr(army, "player", None)
    if _pl is not None and not _pl.dead:
        pool = pool + [_pl]
    random.shuffle(pool)
    kept = 0
    for i, _job in enumerate(slots):
        if i >= len(pool):
            break
        soldier = pool[i]
        if soldier is _pl:                      # the player takes the post
            _pl.settled_at = target
            _pl.job = _job
            if _pl in army.soldiers:
                army.soldiers.remove(_pl)
            start_kit(_pl, target, _job)
            kept += 1
            continue
        npc = getattr(soldier, "home_npc", None)
        if npc is None or not npc.alive:
            continue
        soldier.settled = True
        _settle(npc, target)
        # A post without the tools of the trade is a title and nothing else.
        settle_kit(npc, target, _job)
        # AND HE KEEPS HIS MUSKET. Nothing ever took it from him -- it was just
        # never handed over, so it vanished. Now it is his.
        keep_weapon(npc, soldier)
        kept += 1
    if kept:
        target._fill_vacancies()
    return kept


def _kit_for(village, job: str) -> list:
    """The things a man needs in his hands to do a trade at all.

    Split out of start_kit so that a SETTLING SOLDIER can be issued the same
    kit as the player. See settle_kit below.
    """
    import crop as _crop
    bag = []
    food = getattr(village, "local_food", "wheat")
    leaf = getattr(village, "local_leaf", "plant")
    if job == "farm":
        give = [("watering_can", 1), ("shovel", 1)]
        fs = _crop.CROP_SEED.get(food)
        ls = _crop.CROP_SEED.get(leaf)
        if fs:
            give.append((fs, 10))
        if ls:
            give.append((ls, 10))
    elif job == "brewery":
        mash = _crop.FOOD_ITEM.get(food, "bread")
        give = [(food if food in economy.MASH else "wheat",
                 economy.WORT_BATCH)]
    elif job == "lab":
        give = [(economy.LEAF[0] if leaf == "plant" else
                 _crop.LEAF_ITEM.get(leaf, "red_mushroom"), economy.LEAF_STOCK)]
    elif job == "mine":
        give = [("pickaxe", 1)]
    elif job == "smith":
        give = [("iron", economy.IRON_STOCK), ("axe", 1)]
    else:
        give = []
    for item, qty in give:
        bag.append((item, qty))
    return bag


def start_kit(player, village, job: str) -> list:
    """What a man is given to do his new trade.

    A farmer gets the tools of the field and a pocket of the local seed, a
    brewer the makings of one full mash, an artisan the leaf for his bench, a
    smith the iron for his first hammers. Without it the post is a title and
    nothing else -- he is paid the wage and cannot do a stroke of the work.
    """
    bag = _kit_for(village, job)
    for item, qty in bag:
        player.kit_pending = getattr(player, "kit_pending", [])
        player.kit_pending.append((item, qty))
    return bag


def settle_kit(npc, village, job: str) -> list:
    """A SETTLING SOLDIER IS ISSUED HIS KIT, EXACTLY LIKE THE PLAYER.

    start_kit was called on the player's path ALONE. Every NPC the garrison
    settled took his post with empty hands: _settle clears job, workplace,
    farm_plot and farm_plots, and nothing was ever put back. A farmer given a
    plot and no shovel does not till it -- _work_field sends a man who cannot
    till to the market instead -- so a captured village was held by men who
    could not grow one loaf. Its own people were refugees on the road and its
    granary stayed empty, which is why the towns taken in war starved with a
    garrison standing in them.
    """
    bag = _kit_for(village, job)
    for item, qty in bag:
        # HE MAY HAVE MARCHED WITH IT. Every soldier is issued an entrenching
        # shovel, so a settler who takes a farm post already owns the shovel
        # his kit would hand him -- posting him a second one would put a spare
        # on the shelf and leave a real farmer elsewhere without one.
        if item in economy.TOOLS and npc.stock.get(item, 0) > 0:
            continue
        npc.stock[item] = npc.stock.get(item, 0) + qty
    return bag


# A CROWN LOOKS AT ITS MUSTER ROLL THIS OFTEN, AND NO MORE. Declaring a war
# is a daily decision; the pool it is chosen from cost 26 ms to build, so the
# question must not be asked twenty times a second. See declare().
LEVY_INTERVAL = 10.0
_LAST_LEVY = [-1.0e9]


def _nemesis_wants_the_army(npc) -> bool:
    """Is SOLDIER the rung this man is climbing to?

    THE NEMESIS IS NOT DRAFTED UNTIL THE LADDER ASKS FOR HIM. He was -- he got
    a conscription notice like anybody else, so he held a mine post and a
    soldier's office at the same time: one man in two places, and the rank
    readout said "soldier" while he was digging. The ladder decides when the
    army is his next step, and until then the crown may not take him. See
    Nemesis.md, S3.
    """
    try:
        import nemesis as _nem
        world = getattr(_nem, "WORLD", None)
        nm = getattr(world, "active", None)
        if nm is None or nm.npc is not npc:
            return False                      # not him; the rule does not apply
        r = nm.target_rank()
        if r >= len(_nem.RUNGS):
            return False
        return _nem.RUNGS[r] == "soldier"
    except Exception:
        return False


def _takeable(npc) -> bool:
    """Nobody the crown may call up, whatever his trade."""
    if not getattr(npc, "alive", False) or getattr(npc, "levied", False):
        return False
    # HIM, ONLY WHEN THE ARMY IS HIS NEXT RUNG.
    try:
        import nemesis as _nem
        world = getattr(_nem, "WORLD", None)
        nm = getattr(world, "active", None)
        if nm is not None and nm.npc is npc and not _nemesis_wants_the_army(npc):
            return False
    except Exception:
        pass
    if getattr(npc, "weapon", None):            # already a fighting man
        return False
    return not (getattr(npc, "is_mayor", False) or getattr(npc, "is_king", False)
                or getattr(npc, "defender", False)
                or getattr(npc, "is_commander", False))


def _is_farmer(npc) -> bool:
    """A man with a plot is a farmer, whatever his job field says.

    The job assignment hands a farmer his farm_plot and leaves `job` EMPTY --
    and idle_man() tests `farm_plots`, a different attribute. So a farmer with
    a field looked like a man with no work, and the levy took him in the FIRST
    tier instead of the last: the breadbasket called up ahead of the woodsmen.
    """
    return getattr(npc, "farm_plot", None) is not None


def _spare(npc, jobs) -> bool:
    return _takeable(npc) and getattr(npc, "job", None) in jobs


def levy_pool(registry, capital) -> list:
    """The realm's men, IN THE ORDER A CROWN SHOULD SPEND THEM.

    Idle men first, because they cost their village nothing. Then its woodsmen
    -- but never below the floor that keeps the woodlot worked. Then the trades
    whose benches can stand idle for a season, then its traders, then the
    smith. FARMERS LAST AND NEVER MORE THAN HALF: they are the breadbasket, and
    a crown that eats its own harvest has won nothing. A capital is twice the
    size with twice the stores, so it keeps half again as many back. The mayor
    is never touched at all -- somebody must run the place while the men are
    away.

    The tier is the priority: every village's idle men are spent before ANY
    village's loggers, so no town is stripped while its neighbour is untouched.
    """
    towns = [v for v in registry.villages
             if getattr(v, "nation", None) == capital.nation]
    def tier(pick):
        # (village, man) pairs, which is what muster unpacks -- the levy is
        # raised village by village even though it is ORDERED tier by tier.
        out = []
        for v in towns:
            out += [(v, n) for n in pick(v)]
        return out
    def loggers(v):
        men = [n for n in v.npcs if _spare(n, ("logger",))]
        floor = (LOGGER_FLOOR_CAPITAL if getattr(v, "is_capital", False)
                 else LOGGER_FLOOR)
        # THE SURPLUS ABOVE THE FLOOR, not the floor itself. men[n-floor:]
        # takes exactly the men the village was supposed to keep.
        return men[:max(0, len(men) - floor)]
    def farmers(v):
        men = [n for n in v.npcs
               if _takeable(n) and _is_farmer(n) and getattr(n, "job", None) != "logger"]
        keep = (FARMER_KEEP_CAPITAL if getattr(v, "is_capital", False)
                else FARMER_KEEP)
        kept = int(len(men) * keep)
        return men[:max(0, len(men) - kept)]         # what is above the keep
    return (tier(lambda v: [n for n in v.npcs
                            if idle_man(n) and not _is_farmer(n)])
            + tier(loggers)
            + tier(lambda v: [n for n in v.npcs if _spare(n, ("lab", "brewery"))])
            + tier(lambda v: [n for n in v.npcs if _spare(n, ("trader",))])
            + tier(lambda v: [n for n in v.npcs if _spare(n, ("smith",))])
            + tier(farmers))


def muster(registry, capital, target):
    """Call up the men the realm can spare, in order, and arm them."""
    pool = levy_pool(registry, capital)
    if len(pool) < MIN_ARMY:
        return None
    # NO SHUFFLE. The pool is ordered by what a village can spare, and
    # shuffling it threw that away -- a farmer could be called before an idle
    # man, and a woodlot stripped while another town still had idlers. The
    # order IS the policy.
    take = max(MIN_ARMY, int(len(pool) * LEVY_SHARE))
    take = min(take, crown_food(capital) // SOLDIER_RATION)
    if take < MIN_ARMY:
        return None
    # THE RIFLES DECIDE THE SIZE OF THE ARMY: two axemen and a rifleman.
    rifled = min(take // 3, int(capital.ledger_goods.get("rifle", 0)),
                 int(capital.ledger_goods.get("ammo", 0)) // economy.AMMO_PER_RIFLE)
    take = rifled * 3
    if take < MIN_ARMY:
        return None
    veterans = [s for s in STANDING
                if s.alive and getattr(s, "garrison_of", None) is capital][:take]
    army = Army(capital.nation, capital, target)
    army.registry = registry
    for _v in veterans:
        STANDING.remove(_v)
        _vman = getattr(_v, "home_npc", None)
        if _vman is not None and getattr(_vman, "alive", False):
            issue_entrenching_tool(capital, _vman)
        _v.march_target = (target.x, target.y)
        _v.march_village = target
        _v.patrol_center = None
        _v.patrol_r = 0.0
        _v.hostile = True
        army.soldiers.append(_v)
        _man = getattr(_v, "home_npc", None)
        if _man is not None:
            army.levied.append((capital, _man))
    take -= len(veterans)
    for village, npc in pool[:take]:
        enlist(village, npc)
        # A SOLDIER MARCHES WITH A SHOVEL. See issue_entrenching_tool: it is
        # the tool of the trade he takes up when he settles in the town he took.
        issue_entrenching_tool(capital, npc)
        melee = rifled <= 0
        if not melee:
            rifled -= 1
            capital.ledger_goods["rifle"] = int(capital.ledger_goods.get("rifle", 0)) - 1
            capital.ledger_goods["ammo"] = (int(capital.ledger_goods.get("ammo", 0))
                                            - economy.AMMO_PER_RIFLE)
        soldier = creatures.Soldier(
            npc.x, npc.y, capital.nation, melee=melee,
            seed=random.randint(0, 2 ** 31))
        if getattr(npc, "skills", None) is not None:
            soldier.skills = npc.skills
            soldier.max_stamina = 100.0 * npc.skills.stamina_scale()
            soldier.stamina = soldier.max_stamina
        npc.ranged = not melee
        if not melee:
            soldier.ammo = economy.AMMO_PER_RIFLE
        soldier.name = npc.name
        soldier.home_village = village
        soldier.home_npc = npc
        soldier.march_target = (target.x, target.y)
        soldier.march_village = target
        soldier.hostile = True
        soldier.max_health = soldier.health = 95
        soldier.rally_off = (random.uniform(-72.0, 72.0), random.uniform(230.0, 470.0))
        soldier.in_army = True
        issue_rations(capital, soldier)
        army.soldiers.append(soldier)
        army.levied.append((village, npc))
    army.start = len(army.soldiers)
    return army


def declare(registry, day: int, now: float = 0.0) -> list:
    """Once a day, every crown that can afford a war looks for one.

    AND NO MORE THAN ONCE EVERY TEN SECONDS, WHICHEVER IS RARER. This is
    called from the world tick -- twenty times a second -- and every call
    rebuilt the whole recruiting pool from scratch: six tiers, each walking
    every village and every man in the nation, about eight and a half thousand
    predicate calls and thirty thousand getattr, measured at 26 ms a call.

    Worse, a crown that could NOT raise a full company returned None, and
    because the day was only recorded on SUCCESS, it rebuilt the lot again on
    the very next tick, for ever. Twenty-six milliseconds, twenty times a
    second, to reach the same conclusion. Raising an army is a decision a
    crown takes daily; it does not need re-taking every fiftieth of a second.
    """
    if now - _LAST_LEVY[0] < LEVY_INTERVAL:
        return []
    _LAST_LEVY[0] = now
    raised = []
    for v in registry.villages:
        if getattr(v, "is_hub", False):
            continue
        if not getattr(v, "is_capital", False):
            continue
        if v.ledger_coins < WAR_CHEST:
            continue
        if day - getattr(v, "_war_day", -99) < WAR_COOLDOWN:
            continue
        target = nearest_enemy(registry, v)
        if target is None:
            continue
        army = muster(registry, v, target)
        if army is None:
            continue
        v._war_day = day
        raised.append(army)
    return raised



def idle_man(npc) -> bool:
    """The crown's recruiting pool: a man with no work to go to."""
    if not getattr(npc, "alive", False):
        return False
    if getattr(npc, "levied", False) or getattr(npc, "weapon", None):
        return False
    if getattr(npc, "defender", False) or getattr(npc, "is_commander", False):
        return False
    if getattr(npc, "is_king", False):
        return False
    if getattr(npc, "job", None) is not None:
        return False
    if getattr(npc, "workplace", None) is not None:
        return False
    if getattr(npc, "farm_plots", None):
        return False
    return True


class Army:
    """One nation's field column, and the men they used to be.

    When it is done -- win, lose, or walk away -- the survivors go home to
    their villages and pick their lives back up.
    """

    def __init__(self, nation, capital, target) -> None:
        self.nation = nation
        self.capital = capital
        self.target = target
        self.aid = _next_aid()          # the crown's name for this column
        self.soldiers: list = []
        self.levied: list = []          # (village, npc) pairs to repatriate
        self.done = False
        self.result = None
        self.registry = None
        self.held = False
        self.hold = 0.0
        self.taken: list = []           # villages this column has already broken
        self.engage = False             # at a wall, or near another column
        self.returning = False          # marching home, not to a fight
        self.last_name = target.name
        self.last_join = -1e18
        self.start = len(self.soldiers)

    def strength(self) -> int:
        return sum(1 for s in self.soldiers if s.alive)

    def sync_dead(self) -> int:
        """A man who falls on the field does not come home to his village.

        The soldier and the villager are the same person: one is the body on
        the field, the other is the man in the ledger.  If the body dies, the
        man dies -- otherwise the realm would be full of immortals.
        """
        killed = 0
        for soldier in self.soldiers:
            npc = getattr(soldier, "home_npc", None)
            if soldier.alive or npc is None or not npc.alive:
                continue
            # EVERY DEATH IS RECORDED. He fell as a soldier, so the man he
            # was dies with him -- but silently, an army's losses looked like
            # a village emptying for no reason. Only starvation was ever
            # logged; every other death in the world was invisible.
            economy._note("KILLED IN ACTION  %-16s of %s, in the column of %s"
                          % (npc.name, getattr(npc, "village", None) and
                             npc.village.name or "nowhere",
                             getattr(self.capital, "name", "?")))
            try:
                import deaths
                deaths.record(npc, "KILLED IN ACTION",
                              detail="in the column of %s"
                              % getattr(self.capital, "name", "?"))
            except Exception:
                pass
            npc.alive = False
            npc.health = 0
            killed += 1
        return killed

    def send_home(self, result: str) -> None:
        """The campaign is over: the column WALKS back to the capital.

        Not a teleport and not a discharge -- they march home in order, and
        when they arrive they are the standing army, on the streets of the
        capital, still soldiers and still paid.
        """
        if self.done or self.returning:
            return
        _homes: dict = {}
        for _s in self.soldiers:
            if _s.alive and not getattr(_s, "settled", False):
                _s.march_target = (self.capital.x, self.capital.y)
                _s.march_village = self.capital
        self.returning = True
        return


def mayor_pick(army):
    """Who governs the town they just took.

    The best soldier in the column: his combat skills and his stamina
    together. If two men are as good as each other, the richer of them -- and
    if they are equal in both, the toss decides.
    """
    men = [s for s in army.soldiers
           if s.alive and not getattr(s, "settled", False)]
    if not men:
        return None

    def score(s):
        sk = s.skills
        man = getattr(s, "home_npc", None)
        return (sk.axe + sk.shooting + sk.stamina_scale(),
                getattr(man, "coins", 0))

    best = max(score(s) for s in men)
    top = [s for s in men if score(s) == best]
    return random.choice(top)


def next_target(registry, origin, army):
    """The nearest village still flying somebody else's flag."""
    best, best_d = None, None
    for v in registry.villages:
        if (v in army.taken or v is origin
                or getattr(v, "nation", None) == army.nation):
            continue
        d = math.hypot(v.x - origin.x, v.y - origin.y)
        if best_d is None or d < best_d:
            best, best_d = v, d
    return best


def reinforce(registry, army, now: float) -> list:
    """Draft more men and send them after the column.

    A crown at war does not stop at one muster: while it can pay, it keeps
    feeding men down the road to the army. They walk to wherever the column is
    fighting now, so a war that goes well gets stronger instead of fading.
    """
    if now - getattr(army, "last_join", -1e18) < REINFORCE_EVERY:
        return []
    if getattr(army, "done", False) or army.target is None:
        return []
    purse = army.capital.ledger_coins
    # A COLUMN HAS A SIZE. Drafting twelve men every two minutes for ever
    # meant an army of a thousand after an hour, and a frame rate that fell
    # every minute it ran. The crown tops a column back up to strength; it does
    # not pile men onto it.
    standing = sum(1 for s in army.soldiers
                   if s.alive and not getattr(s, "settled", False))
    room = ARMY_CAP - standing
    if room <= 0:
        return []
    # INT, BECAUSE THE PURSE IS NOT. The ledger holds FRACTIONAL coin -- sales
    # tax and prices have carried fractions since they were made fractional --
    # so `(purse - REINFORCE_KEEP) // REINFORCE_COST` returns a FLOAT, min()
    # propagates it, and `pool[:take]` raises "slice indices must be integers".
    # It fired the moment a column was reinforced, which is the second day of
    # any war: the whole game, not just the sim.
    take = int(min(REINFORCE_BATCH, room,
                   (purse - REINFORCE_KEEP) // REINFORCE_COST,
                   crown_food(army.capital) // SOLDIER_RATION))
    if take <= 0:
        return []
    pool = []
    for v in registry.villages:
        if getattr(v, "nation", None) != army.nation:
            continue
        for npc in v.npcs:
            if idle_man(npc):
                pool.append((v, npc))
    if not pool:
        return []
    random.shuffle(pool)
    fresh = []
    for village, npc in pool[:take]:
        enlist(village, npc)
        melee = random.random() < 0.5          # drafted as a rifleman or an axeman
        soldier = creatures.Soldier(
            npc.x, npc.y, army.nation, melee=melee,
            seed=random.randint(0, 2 ** 31))
        if getattr(npc, "skills", None) is not None:
            soldier.skills = npc.skills
            soldier.max_stamina = 100.0 * npc.skills.stamina_scale()
            soldier.stamina = soldier.max_stamina
        npc.ranged = not melee            # a rifleman is paid as one
        if not melee:
            soldier.ammo = economy.AMMO_PER_RIFLE
        soldier.name = npc.name
        soldier.home_village = village
        soldier.home_npc = npc
        soldier.march_target = (army.target.x, army.target.y)
        soldier.march_village = army.target
        soldier.hostile = True
        soldier.max_health = soldier.health = 95
        soldier.rally_off = (random.uniform(-72.0, 72.0), random.uniform(230.0, 470.0))
        soldier.in_army = True
        issue_rations(army.capital, soldier)
        army.soldiers.append(soldier)
        army.levied.append((village, npc))
        fresh.append(soldier)
    army.capital.ledger_coins -= REINFORCE_COST * len(fresh)
    army.last_join = now
    return fresh


def update(armies: list, tick_dt: float = 0.0, now: float = 0.0) -> list:
    """Watch each column: has it taken the village, or has it broken?"""
    events = []
    for army in armies:
        if army.done:
            continue
        if army.returning:
            _home = army.capital
            _left = [s for s in army.soldiers
                     if s.alive and not getattr(s, "settled", False)]
            if not _left or all(math.hypot(s.x - _home.x, s.y - _home.y)
                                < _home.radius for s in _left):
                for s in _left:
                    s.march_target = None
                    s.march_village = None
                    s.patrol_center = (_home.x, _home.y)
                    s.patrol_r = _home.radius * 0.6
                    s.garrison_of = _home
                    s.in_army = True
                    STANDING.append(s)
                    man = getattr(s, "home_npc", None)
                    if man is not None and man.alive:
                        man.job = "soldier"
                        if man.village is not _home:
                            if man not in _home.npcs:
                                _home.npcs.append(man)
                            man.village = _home
                army.done = True
                # RETURN THE EVENTS, NOT None. This was a bare `return`, and
                # the caller unpacks this function's result as
                # `for _army, _res, _info in war.update(...)`. So the game
                # died with "'NoneType' object is not iterable" on the exact
                # frame the first column in history came home and disbanded --
                # the war worked, and the march home killed it.
                return events
        army.sync_dead()
        feed(army, tick_dt)
        march(army, tick_dt)
        target = army.target
        # A column in open country needs no per-frame attention: war.march
        # already walks it, and there is nothing out there to see. One at a
        # wall, or one about to meet another column, needs the full frame rate.
        # This is what keeps a war from costing the frame rate.
        at_wall = False
        cx = cy = 0.0
        n = 0
        for _s in army.soldiers:
            if _s.alive and not getattr(_s, "settled", False):
                cx += _s.x
                cy += _s.y
                n += 1
                if math.hypot(_s.x - target.x, _s.y - target.y) < target.radius + 600.0:
                    at_wall = True
        if n:
            cx /= n
            cy /= n
        near_foe = False
        for _o in armies:
            if _o is army or _o.done or _o.nation == army.nation:
                continue
            if _o.soldiers and math.hypot(cx - _o.soldiers[0].x,
                                          cy - _o.soldiers[0].y) < 5000.0:
                near_foe = True
                break
        for _s in army.soldiers:
            resupply(_s)               # a rifleman's own business, every tick
        army.engage = at_wall or near_foe
        for _s in army.soldiers:
            _s.in_contact = army.engage
        alive = army.strength()
        if alive == 0:
            army.send_home("broken")
            events.append((army, "broken", 0))
            continue
        # The people run for the gates the moment the column is at the wall.
        close = any(math.hypot(s.x - target.x, s.y - target.y)
                    < target.radius + 200.0 for s in army.soldiers if s.alive)
        registry = getattr(army, "registry", None)
        dests = friendly_neighbours(registry, target) if registry else []
        # If the player cannot see this village, its people and its garrison
        # are not simulated -- so the battle is settled here and now instead
        # of waiting forever for someone to come and watch it happen.
        if close:
            army.held = True            # the walls are ours from here on
            fled = rout(target, dests, now)
            if fled:
                events.append((army, "rout", fled))
        # The battle is over only when the village is EMPTY: everybody in it
        # is dead or gone. An undefended village full of people is not taken.
        # Anybody still answering to the OLD flag and standing inside the
        # walls is a defender of it, whether he is a soldier or a farmer.
        inside = [n for n in target.npcs if getattr(n, "alive", False)
                  and getattr(n, "nation", None) == target.nation
                  and target.fence_rect.collidepoint(n.x, n.y)]
        if close and inside:
            army.hold = getattr(army, "hold", 0.0) + tick_dt
            # A handful of men who will not come out and cannot be reached are
            # not a defence, and they know it. Given long enough to watch their
            # village filling up with the enemy, they break and run like the
            # rest -- a last stand of two against a hundred is not a battle.
            if len(inside) <= 3 and army.hold > LAST_STAND:
                for npc in inside:
                    dest = dests[len(army.levied) % len(dests)] if dests else None
                    if dest is None:
                        break
                    npc.refuge = dest
                    npc.refuge_eta = now + math.hypot(dest.x - npc.x,
                                                      dest.y - npc.y) / REFUGEE_SPEED
                    npc.aggro = False
                    npc.defender = False
                    npc.asleep = False
                    npc.in_interior = False     # come out of the house
                    npc.panic = 60.0
        # Once the column has stood inside the walls, the village is theirs the
        # moment the last man of the old flag is out of it -- chasing the last
        # fugitive across a field does not un-take a village.
        if getattr(army, "held", False) and not inside:
            loot = int(target.ledger_coins * SPOILS)
            target.ledger_coins -= loot
            # THE MEN ARE PAID FOR TAKING IT. Between a third and two thirds
            # of the coin, shared out equally, is theirs; the crown keeps the
            # rest. That is what makes a soldier's trade worth learning -- and
            # it is why the men who settle a captured town arrive with money
            # in their pockets and a warrior class with something to inherit.
            men = [s for s in army.soldiers
                   if s.alive and not getattr(s, "settled", False)]
            _pl = getattr(army, "player", None)     # an enlisted player counts
            if _pl is not None and not _pl.dead:
                men = men + [_pl]
            to_men = int(loot * random.uniform(0.30, 0.60))
            if men and to_men > 0:
                per = to_men // len(men)
                if per > 0:
                    for s in men:
                        man = getattr(s, "home_npc", None)
                        if man is not None and man.alive:
                            man.coins += per
                            man.book_in = getattr(man, "book_in", 0.0) + per
                        elif s is _pl:
                            s.loot_pending = getattr(s, "loot_pending", 0) + per
                    to_men = per * len(men)
                else:
                    to_men = 0
            else:
                to_men = 0
            army.capital.ledger_coins += loot - to_men
            # AND THE LARDER. A column that takes a town eats out of it --
            # the stores are shared out among the men who took it, which is
            # what makes a winning campaign self-feeding and a losing one
            # starve.
            raid_luxuries(army, target)
            stores = economy.take_food(target, int(economy.village_food(target)
                                                   * SPOILS))
            if stores:
                men = [s for s in army.soldiers
                       if s.alive and not getattr(s, "settled", False)]
                if men:
                    per = sum(stores.values()) // len(men)
                    if per > 0:
                        for s in men:
                            s.food = getattr(s, "food", 0) + per
            # A CAPITAL FALLING TAKES THE WHOLE KINGDOM WITH IT.
            #
            # Taking a capital used to be taking one town. The king was routed
            # with the crowd, village.king went on pointing at a man who had
            # fled, and every other town of that nation carried on as before --
            # so a nation could lose its capital and its king and simply sit
            # headless for ever, its villages still flying its colours.
            #
            # THE THRONE IS THE NATION. When it falls the realm changes hands:
            # every town of the old nation becomes the conqueror's, every king
            # is deposed, and the crown goes with the capital that was taken.
            _was_capital = bool(getattr(target, "is_capital", False))
            _old_nation = target.nation
            if _was_capital and _old_nation != army.nation:
                _taken = 0
                _reg = getattr(target, "registry", None)
                for _v in (getattr(_reg, "villages", ()) if _reg else ()):
                    if getattr(_v, "nation", None) != _old_nation:
                        continue
                    _v.nation = army.nation
                    _k = getattr(_v, "king", None)
                    if _k is not None:
                        _k.is_king = False
                        _k.role = None
                        if getattr(_k, "job", None) == "king":
                            _k.job = None
                            _v.free_post(_k)
                        _v.king = None
                    for _n in _v.npcs:
                        if getattr(_n, "alive", False):
                            _n.nation = army.nation
                            _n.team = ("nation", army.nation)
                    _taken += 1
                economy._note(
                    "KINGDOM FALLS  %s takes %s and with it %d towns"
                    % (getattr(army.capital, "name", "?"), target.name, _taken))
            target.nation = army.nation
            # THE WAR IS OVER IN THIS VILLAGE. A provoked village can never
            # have another child -- can_grow() refuses while provoked is set,
            # and provoke() never clears it -- so a captured town would be
            # barren forever and could never raise the next generation of
            # idlers. Peace it, bury the dead, and calm the survivors.
            target.provoked = False
            target.last_death = now
            for n in target.npcs:
                n.nation = army.nation
                n.team = ("nation", army.nation)
                n.aggro = False
                n.panic = 0.0
                n.aware = False
            army.last_name = target.name
            gov = mayor_pick(army)           # the best man governs it
            if gov is not None:
                gov.settled = True
                _gov_man = getattr(gov, "home_npc", None)
                if _gov_man is not None and _gov_man.alive:
                    _settle(_gov_man, target)
                    _gov_man.is_mayor = True
                    _gov_man.job = "mayor"
                    _gov_man.role = "Mayor"
                    _gov_man.plaza = (target.x, target.y)
                    target.mayor = _gov_man
            note_capture(army, target, now)  # ...before the garrison leaves it
            kept = occupy(army, target)      # the garrison moves in
            events.append((army, "taken", loot))
            if kept:
                events.append((army, "occupied", kept))
            army.taken.append(target)
            # The column has just swallowed a village. If it still has a
            # fighting strength worth the name, it does not go home to be
            # demobbed -- it turns and marches on the next village that flies
            # somebody else's flag.
            marching = [s for s in army.soldiers
                        if s.alive and not getattr(s, "settled", False)]
            nxt = (next_target(registry, target, army)
                   if len(marching) >= MIN_MARCHING and registry else None)
            if nxt is not None:
                army.target = nxt
                army.held = False
                army.hold = 0.0
                for s in marching:
                    s.march_target = (nxt.x, nxt.y)
                    s.march_village = nxt
                events.append((army, "march", nxt))
            else:
                army.send_home("taken")
            continue
        # Reinforcements: the crown keeps feeding men to a war it can afford.
        if registry is not None and not getattr(army, "done", False):
            fresh = reinforce(registry, army, now)
            if fresh:
                events.append((army, "reinforced", fresh))
    return events
