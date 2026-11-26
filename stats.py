"""stats.py -- ONE BODY FOR EVERYBODY.

The player's body is the standard. Whatever a man's skills, a rifle round and
an axe blow do the same arithmetic to him as to the player: everyone in the
world -- villagers, defenders, levied soldiers, standing armies, the crown's
raised men, bandits -- has this much health and no more.
"""

PLAYER_MAX_HEALTH = 115
# A FIGHTER'S BODY GROWS WITH HIS TRADE. Nobody starts tougher than the
# player; a man who has mastered the axe or the gun has 180 to lose -- so the
# same 80-health round that kills a levy leaves a veteran standing.
SKILL_MAX_HEALTH = 180


def body_for(who) -> float:
    """The most health this man's SKILL earns him, 115 .. 180."""
    sk = getattr(who, "skills", None)
    if sk is None:
        base = float(PLAYER_MAX_HEALTH)
    else:
        frac = max(float(getattr(sk, "axe", 0.0) or 0.0),
                   float(getattr(sk, "shooting", 0.0) or 0.0))
        frac = max(0.0, min(1.0, frac))
        base = (float(PLAYER_MAX_HEALTH)
                + (float(SKILL_MAX_HEALTH) - float(PLAYER_MAX_HEALTH)) * frac)
    # A one-time chili-mezcal bonus follows the body through every later
    # recomputation, instead of being erased the next time armour changes.
    try:
        base *= max(0.1, float(getattr(who, "health_mult", 1.0) or 1.0))
    except Exception:
        pass
    return base


def apply_body(who) -> float:
    """Give him the body his skills have earned, keeping what is left of him.

    Called wherever skill can rise: a man who has just spent three days at the
    dummy gains the body to go with the arm, and he does not heal by it -- the
    extra is added to whatever health he has left.
    """
    want = body_for(who)
    old = float(getattr(who, "max_health", want) or want)
    if abs(want - old) >= 0.5:
        who.max_health = want
        who.health = min(want, float(getattr(who, "health", want) or 0.0)
                         + max(0.0, want - old))
    return want
