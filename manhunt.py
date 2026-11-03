"""manhunt.py -- THE CROWN ANSWERS THE NAME.

The service's chief does not shrug at the news that somebody leads a criminal
organisation. Once he has the leader's name:

* every soldier of the nation is told the man is **wanted -- until he is
  killed** (not a fine, not a gate search: the standing order), and
* a party of the **ten most battle-hardened soldiers** the crown has is sent
  to the place the news came from -- a yard, a body in a field, wherever the
  player was last seen -- carrying **fifty food and plenty of ammunition**,
  with standing orders to shoot the leader **and every known man of his** on
  sight.

The squad is ten `Soldier`s with `manhunt = True` and a live list of the
player's men (`hunt_ids`), which `creatures.choose_target` reads. They are
ordinary soldiers otherwise: they bleed, they run out of breath, and they can
be killed.
"""

from __future__ import annotations

import stats

import math
import random

import plog
from creatures import Soldier

SQUAD = 10               # the ten best warriors the kingdom has
KIT_AMMO = 60            # rounds ISSUED to a man who has fewer
KIT_FOOD = 50            # rations ISSUED to a man who has fewer
COST_PER_MAN = 150.0     # gold, paid by the crown the moment it sends them
ELITE_AXE = 0.875        # a raised man is top of his band: he is the BEST
ELITE_MOVE = 0.875
ELITE_SHOOT = 0.75

SENT: list = []          # (now, x, y, count, cost) -- what was sent, for the log
SENT_STATE = [0.0]


def _skill(s) -> float:
    """Melee and stamina, which is what makes a warrior worth sending."""
    sk = getattr(s, "skills", None)
    return (getattr(sk, "axe", 0.0) + getattr(sk, "movement", 0.0)
            + 0.5 * getattr(sk, "shooting", 0.0))


MIN_SKILL = 0.5          # below this a man is a levied guard, not a warrior


def best_warriors(enemies, nation, n: int = SQUAD) -> list:
    """The highest melee-and-stamina soldiers of that nation, best first.

    A man already in a marching army is not taken: the army would keep walking
    him and the crown's party would be dragged out of its own dispatch. A man
    who has never swung an axe is not a warrior either -- the crown raises the
    difference at its own seat rather than calling up a levy.
    """
    pool = [e for e in enemies
            if getattr(e, "kind", None) == "soldier"
            and getattr(e, "alive", True)
            and getattr(e, "nation", None) == nation
            and _skill(e) >= MIN_SKILL
            and not getattr(e, "in_army", False)]
    pool.sort(key=_skill, reverse=True)
    return pool[:n]


def _raise(capital, nation, count: int, rng, at_xy) -> list:
    """Men the crown raises at its own seat when the army has none to spare."""
    out = []
    cx = float(getattr(capital, "x", at_xy[0])) if capital is not None else at_xy[0]
    cy = float(getattr(capital, "y", at_xy[1])) if capital is not None else at_xy[1]
    for _ in range(count):
        s = Soldier(cx + rng.uniform(-70, 70), cy + rng.uniform(-70, 70),
                    nation, melee=False, seed=rng.randrange(1 << 30))
        # ELITE: the best band the skills run to, and the health to match.
        s.skills.axe = ELITE_AXE
        s.skills.movement = ELITE_MOVE
        s.skills.shooting = ELITE_SHOOT
        s.max_health = stats.PLAYER_MAX_HEALTH
        s.health = stats.PLAYER_MAX_HEALTH
        s.raised = True                  # counted in the log: the crown's own levy
        out.append(s)
    return out


def _detach(s) -> None:
    """A dispatched man leaves his gate, his patrol and his column behind."""
    s.guard_village = None
    s.guard_loop = None
    s.patrol_center = None
    s.march_target = None
    s.follow = False
    s.hostile = False


def _kit(s) -> None:
    """Guns, ammunition and rations -- ISSUED only where he has not got them."""
    if getattr(s, "weapon", None) not in ("rifle", "shotgun"):
        s.weapon = "rifle"
    if int(getattr(s, "ammo", 0) or 0) < KIT_AMMO:
        s.ammo = KIT_AMMO
    if int(getattr(s, "food", 0) or 0) < KIT_FOOD:
        s.food = KIT_FOOD


def _crown(at_xy, nation, villages) -> object:
    """The seat that pays: the capital of that nation, or its nearest town."""
    towns = [v for v in (villages or ()) if not getattr(v, "is_hub", False)
             and getattr(v, "nation", None) == nation]
    caps = [v for v in towns if getattr(v, "is_capital", False)]
    pool = caps or towns
    if not pool:
        return None
    return min(pool, key=lambda v: (v.x - at_xy[0]) ** 2 + (v.y - at_xy[1]) ** 2)


def dispatch(player, at_xy, nation=None, now: float = 0.0,
             enemies: list | None = None, villages=None,
             seed: int | None = None) -> list:
    """SEND THE TEN BEST. They walk there; the crown pays.

    * the men are chosen from the kingdom's own soldiers by MELEE and STAMINA
      (the skills `axe` and `movement`), and raised at the capital if the army
      has none to spare;
    * each is issued a rifle, ammunition and rations only if he lacks them;
    * the crown is charged at once -- COST_PER_MAN in gold out of the seat's
      ledger. A crown that cannot pay sends fewer men, or none at all;
    * the target is the place the news came from. They MARCH to it: a real
      column on the map, moved by the game's own march code, not spawned
      beside the enemy.
    """
    enemies = enemies if enemies is not None else []
    at_xy = at_xy or (player.x, player.y)
    ax = max(-90000.0, min(90000.0, float(at_xy[0])))
    ay = max(-90000.0, min(90000.0, float(at_xy[1])))
    rng = random.Random(seed if seed is not None else int(now))
    if nation is None:
        near = [v for v in (villages or ()) if not getattr(v, "is_hub", False)]
        if near:
            nation = getattr(min(near, key=lambda v: (v.x - ax) ** 2
                                 + (v.y - ay) ** 2), "nation", None)
        if nation is None:
            nation = getattr(player, "nation", None) or 1
    crown = _crown((ax, ay), nation, villages)

    # WHAT THE CROWN CAN AFFORD. It pays before it sends, not after.
    purse = float(getattr(crown, "ledger_coins", 0.0) or 0.0) if crown else None
    want = SQUAD
    if purse is not None:
        want = min(SQUAD, int(purse // COST_PER_MAN))
    if want <= 0:
        try:
            plog.log("MANHUNT", "the crown cannot pay for a single man",
                     "| ledger", int(purse or 0), "| cost each",
                     int(COST_PER_MAN))
        except Exception:
            pass
        return []

    squad = best_warriors(enemies, nation, want)
    if len(squad) < want:
        squad.extend(_raise(crown, nation, want - len(squad), rng, (ax, ay)))
    ids = {str(getattr(n, "id", "")) for n in (getattr(player, "workers", None) or ())
           if getattr(n, "alive", True)}
    for s in squad:
        _detach(s)
        _kit(s)
        s.manhunt = True                 # shoot-on-sight: see creatures.choose_target
        s.hunt_ids = set(ids)            # the leader and every man of his we know
        s.march_target = (ax, ay)        # THEY WALK TO IT
        s.view_range = max(getattr(s, "view_range", 0.0), 420.0)
        if s not in enemies:
            enemies.append(s)
    cost = COST_PER_MAN * len(squad)
    if crown is not None:
        crown.ledger_coins = max(0.0, float(getattr(crown, "ledger_coins", 0.0)) - cost)
        try:
            import economy
            economy.flow(crown, "pay_manhunt", -cost)
        except Exception:
            pass
    # EVERY SOLDIER OF THE NATION IS TOLD: he is wanted until he is killed.
    player.wanted = True
    SENT.append((now, ax, ay, len(squad), cost))
    try:
        plog.log("MANHUNT", "dispatched", len(squad), "of the kingdom's best to",
                 "%d,%d" % (int(ax), int(ay)),
                 "| from", getattr(crown, "name", "the crown"),
                 "| paid", int(cost),
                 "| ledger now", int(getattr(crown, "ledger_coins", 0) or 0),
                 "| hunting", 1 + len(ids),
                 "| raised", sum(1 for x in squad if getattr(x, "raised", False)),
                 "| best skill %.2f" % (_skill(squad[0]) if squad else 0.0))
    except Exception:
        pass
    return squad


def tick(player, enemies, now: float) -> None:
    """The party's list of names is the player's men, kept current.

    A man hired after the party marched is still a man of the organisation --
    the crown cannot know him, but this list is how the SHOOTERS know him, and
    the player should not be able to hide behind a fresh hire.
    """
    live = {str(getattr(n, "id", ""))
            for n in (getattr(player, "workers", None) or ())
            if getattr(n, "alive", True)}
    for e in enemies:
        if getattr(e, "manhunt", False) and getattr(e, "alive", True):
            e.hunt_ids = live
    # THE PARTY'S OWN HEADCOUNT, FROM THE LIST IT LIVES IN. With this line a
    # party that is sent and then disappears says so itself.
    if int(now) - int(SENT_STATE[0]) >= 5:
        SENT_STATE[0] = now
        try:
            plog.log("MANHUNT-STATE", "alive", any_standing(enemies),
                     "| in the list", sum(1 for e in enemies
                                          if getattr(e, "manhunt", False)),
                     "| enemies", len(enemies),
                     "| near", sum(1 for e in enemies
                                   if getattr(e, "manhunt", False)
                                   and (e.x - player.x) ** 2
                                   + (e.y - player.y) ** 2 < 2000.0 ** 2))
        except Exception:
            pass


def any_standing(enemies) -> int:
    return sum(1 for e in enemies
               if getattr(e, "manhunt", False) and getattr(e, "alive", True))
