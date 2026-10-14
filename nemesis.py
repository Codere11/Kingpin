"""THE NEMESIS.

One man in the world wants what the player wants, and he is NOT SPECIAL.

He is an ordinary citizen with an ambition and a rank table. He obeys every law
the player obeys: he takes a post the way anybody does, buys a vote through
economy.sell_vote, stands in the ring through tournament.Tournament, and is
levied by war.levy_pool. He cannot do one thing the player cannot do.

Everything in this file is from Nemesis.md. The section numbers are given so
the code and the design can be read against each other.

THE THREE THINGS HE HAS THAT NOBODY ELSE HAS
--------------------------------------------
1.  A RANK TABLE (S3). He thinks some trades are better than others, and he
    only ever moves UP.
2.  THE REFUSAL (S3). He can decline a post below him and hold out for one
    above -- everyone else takes what the town offers.
3.  SCHEMING (S3). He may take a post from the man holding it. The displaced
    man goes idle and, importantly, REMEMBERS -- he is a grudge, and a grudge
    is a source of clues.

WHAT HE DELIBERATELY DOES NOT HAVE
----------------------------------
No buff. No extra coin. No omniscience. He knows what a man in his position
could know and nothing else (S4, S5).
"""

from __future__ import annotations

import math
import random


# -- S3: WHAT A TRADE IS WORTH, WORST TO BEST ---------------------------------
# As HE sees it: the money it pays now, and what it opens next. He does not
# follow a script, he follows this order -- which is why two of him in two
# games take different roads. They start at different rungs.
# THE ONE NEMESIS, reachable from outside main() so a long-run simulation can
# watch him without reaching into the game's guts. Set by NemesisWorld.__init__.
WORLD = None

RANK = {
    None: 0,
    "logger": 1, "farm": 2, "mine": 3, "smith": 4, "brewery": 5, "lab": 6,
    "trader": 7, "soldier": 8, "mayor": 9, "king": 10,
}

# HE DOES NOT WAIT FOR A MASTER'S HANDS. Three hundred days is a career, and a
# man who spent his whole life in one trade would never climb at all. He moves
# on when the trade has taught him ENOUGH TO BE GOOD AT IT -- a quarter of the
# road, sixty or seventy days -- and leaves the last of it to the man who stays.
# THE LADDER IN ORDER, derived from RANK so the two can never disagree.
_RUNGS = [None] * (max(RANK.values()) + 1)
for _k, _v in RANK.items():
    _RUNGS[_v] = _k
RUNGS = tuple(_RUNGS)

SCHEME_MAX = RANK["trader"]      # above this a post is not his to take:
                                 # a soldier enlists, a mayor is elected, a
                                 # king is fought for.

MASTERED = 0.25          # of the way to the cap, not of the way to mastery


def rank_of(npc) -> int:
    """Where he stands, by office first and trade second."""
    if getattr(npc, "is_king", False):
        return RANK["king"]
    if getattr(npc, "is_mayor", False):
        return RANK["mayor"]
    if getattr(npc, "is_soldier", False) or getattr(npc, "levied", False):
        return RANK["soldier"]
    return RANK.get(getattr(npc, "job", None), 0) if npc.farm_plot is None \
        else max(RANK["farm"], RANK.get(getattr(npc, "job", None), 0))


def trade_mastered(npc, kind) -> bool:
    """HAS THIS TRADE TAUGHT HIM ALL IT CAN? (S3)

    Not time served -- SKILL SATURATED. A logger learns everything a logger can
    know in eight swings' worth of the scale, and then he is standing still.
    Trades that teach nothing (the pit, the smithy) are never mastered: they
    pay a wage, and a man leaves them for the money, not for the ceiling.
    """
    sk = getattr(npc, "skills", None)
    if sk is None:
        return False
    if kind == "farm" or kind in ("brewery", "lab"):
        return sk.farming >= 8.0 * MASTERED
    if kind == "logger":
        return sk.axe >= 1.0 * MASTERED
    if kind == "trader":
        return sk.movement >= 1.0 * MASTERED
    return False


def _far_towns(registry, villages, player, count: int = 1) -> list:
    """A small village A LONG WAY OFF (S2, S14).

    Not the player's home and not next door: the point is that the two lives
    run in parallel and cross by accident, never by arrangement.
    """
    towns = [v for v in getattr(registry, "villages", ()) or ()
             if 3 <= len(getattr(v, "npcs", ())) and not v.is_capital]
    if not towns:
        return []
    px, py = getattr(player, "x", 0.0), getattr(player, "y", 0.0)
    towns.sort(key=lambda v: -((v.x - px) ** 2 + (v.y - py) ** 2))
    # From the far half, prefer the SMALL ones: fewer voters is a cheaper
    # election, and a cheap ladder is strategy, not a buff.
    far = towns[:max(1, len(towns) // 2)]
    far.sort(key=lambda v: len(v.npcs))
    return far[:count]


class Nemesis:
    """One man, with a plan he never tells anybody about."""

    def __init__(self, npc, town):
        self.npc = npc
        self.town = town
        self.born_day = -1
        # WHAT HE HAS TRIED, AND WHETHER IT WORKED (S3, S14). This is the whole
        # of his "learning": in-world, save-able, and cheap. No nets.
        self.attempts: dict = {}          # strategy -> [tries, wins]
        self.days_in_trade = 0            # how long he has stood on this rung
        self.grudges: dict = {}           # name -> what they did to him
        # WHAT HE KNOWS (S4, S5). Names, not flags: a man learns a NAME.
        self.knows_player = False
        self.player_name = None
        self._clue_at = -999.0
        self._last_rung = rank_of(npc)
        # S7: THE OMEN AND THE ATTEMPT.
        self.omen_day = -1                # the day a warning was spoken
        self.strike_day = -1              # the day chosen for it
        self.strikes = 0                  # how many attempts have landed

    # -- S3: the climb -------------------------------------------------------
    def target_rank(self) -> int:
        """The next rung he wants, and it is always exactly one up."""
        return min(RANK["king"], self._last_rung + 1)

    def wants_out(self) -> bool:
        """He has learned all this trade can teach him (S3)."""
        npc = self.npc
        if getattr(npc, "is_king", False) or getattr(npc, "is_mayor", False):
            return False
        kind = "farm" if npc.farm_plot is not None else getattr(npc, "job", None)
        if kind is None:
            return True                   # idle: anything is better
        if kind in ("mine", "smith"):
            # THE PIT AND THE SMITHY TEACH NOTHING (S3). They pay a wage, and a
            # man leaves them FOR THE MONEY -- ten days of it is the reason.
            # Without this he would never leave at all, because a trade that
            # teaches nothing can never be "mastered".
            return self.days_in_trade >= 10
        return trade_mastered(npc, kind)

    def would_take(self, kind: str) -> bool:
        """Is this rung an UPGRADE? He never moves down (S3)."""
        return RANK.get(kind, 0) > self._last_rung

    def cushion(self) -> bool:
        """He only holds out if he can afford to (S3, open question 1).

        A man who refuses every post starves and stops being anything. He
        accepts what he is offered when his purse is thin, and holds out only
        when he can pay for the wait.
        """
        return getattr(self.npc, "coins", 0) >= 120

    def can_scheme(self, kind: str) -> bool:
        """S3: one rung at a time. A logger scheming into a smithy is a story;
        a logger scheming straight into the mayoralty is a joke."""
        return self.would_take(kind) and kind in ("farm", "logger", "mine",
                                                  "smith", "brewery", "lab",
                                                  "trader")

    # -- S4/S5: what he knows ------------------------------------------------
    def learn_of_player(self, name: str) -> None:
        """He has the player's NAME. That is the only fact that matters: you
        cannot hunt a profession (S4)."""
        if not self.knows_player:
            self.knows_player = True
            self.player_name = name

    def clue(self, day: float, player_rank: int) -> str | None:
        """WHAT THE PLAYER HEARS, AND IN WHAT DETAIL (S4, S5).

        THE NAME IS KNOWLEDGE OF THE LEADER. The trailer is anonymous. So if
        the player is ahead he gets a trade and no name -- he cannot act on it,
        which is the point: the powerful do not notice the climber.
        """
        mine = rank_of(self.npc)
        who = self.npc.name.split()[0]
        kind = self.npc.job or ("farm" if self.npc.farm_plot is not None
                                else "no trade")
        if mine > player_rank:
            # HE IS AHEAD: he is famous, and the player gets everything.
            return random.choice([
                "%s. He is a %s now, and he is going higher." % (who, kind),
                "They say %s is rising fast -- a %s, and not for long." % (who, kind),
                "%s. A %s, and the ambitious kind." % (who, kind),
            ])
        if mine == player_rank:
            return random.choice([
                "There is a %s somewhere, going up in the world." % kind,
                "A %s, they say, who will not stay one." % kind,
            ])
        # THE PLAYER IS AHEAD: trade only, no name, no place. A nobody.
        return random.choice([
            "There is a man rising fast in the world.",
            "They say a %s out east is making a name for himself." % kind,
            "A man who means to go far -- nobody knows his name yet.",
        ])

    # -- S7: the omen --------------------------------------------------------
    def schedule_strike(self, day: int, rng: random.Random) -> None:
        """S7: a random day in the next ten. Sometimes tomorrow, sometimes
        day nine -- and the player is never told which."""
        self.omen_day = day
        self.strike_day = day + rng.randint(1, 10)


# -- S7: THE OMENS ------------------------------------------------------------
# ALWAYS GIVEN, NEVER NECESSARILY HEARD. The warning is always spoken; whether
# it reaches the player depends on who he is standing near -- exactly like the
# news and the clues. Not so he can always detect it: so that when he dies he
# can find the five omens he ignored.
REAL_OMENS = (
    "I had a bad dream last night... A lion has killed another lion while he was asleep.",
    "Careless kings do not last long in this world.",
    "Some men rise, and then they stop rising. All at once.",
    "I knew a man who was somebody. He slept badly, at the end.",
)
CROWN_OMENS = (
    "The King is cracking down on potential enemies... Finally some order.",
    "They say the King has a list. Nobody has seen it.",
    "Men have gone quiet lately. Important men.",
)
# THE DRUNK IS NOT PLAYING DICE (S7). A true omen and a drunk's ravings are
# INDISTINGUISHABLE, and that is deliberate: a distinguishable omen is a puzzle,
# and puzzles get solved. The uncertainty is not noise around the signal --
# the uncertainty IS the content.
DRUNK_OMENS = (
    "Careless kingsss do not last long... in this world...",
    "A lion! A LION, I tell you!",
    "Everythingends. Everything. Mark me.",
    "The King. The King and his... list. List of... what was I saying.",
)
# S7: THE RATE DRIFTS WITH HIM. Early, almost every omen is a drunk and the
# player learns to shrug. Late, the omens are frequent AND real, because the
# man has stopped guessing and started hunting.
DRUNK_ODDS = (0.85, 0.70, 0.50, 0.30)


def _player_rank(player) -> int:
    """Where the PLAYER stands, by the same table (S4)."""
    if getattr(player, "job", None) == "king":
        return RANK["king"]
    if getattr(player, "job", None) == "mayor":
        return RANK["mayor"]
    return RANK.get(getattr(player, "job", None), 0)


class NemesisWorld:
    """The one nemesis, and everything that keeps him climbing."""

    def __init__(self, registry, villages, player):
        self.rng = random.Random(0x4E3E5155)
        self.player = player
        self.registry = registry
        self.villages = villages
        self.active = None
        self.dead_day = -999
        self.last_clue_day = -999
        self.lines: list = []          # things the player is told, in order
        self._last_day = -1            # the game day he last ticked -- a clock
                                       # the simulation outside can read
        global WORLD
        WORLD = self

    def _note(self, text: str) -> None:
        try:
            import economy
            economy._note(text)
        except Exception:
            pass

    # -- birth (S2, S8, S14) -------------------------------------------------
    def seed(self, day: int) -> bool:
        """AN ORDINARY MAN, A LONG WAY OFF, IN A SMALL TOWN.

        Small because fewer voters is a cheaper election -- choosing a good
        starting position is strategy, not a buff. A long way off because the
        two lives must cross by accident and never by arrangement.
        """
        towns = _far_towns(self.registry, self.villages, self.player, 1)
        if not towns:
            return False
        town = towns[0]
        men = [n for n in town.npcs
               if getattr(n, "alive", False)
               and not getattr(n, "is_mayor", False)
               and not getattr(n, "is_king", False)
               and not getattr(n, "is_commander", False)]
        if not men:
            return False
        man = self.rng.choice(men)
        self.active = Nemesis(man, town)
        # THE NEMESIS LEARNS FASTER THAN THE WORLD (5% against 1%). It is the
        # one advantage he has, and it is small -- but it is what lets a man
        # with no head start be worth watching.
        try:
            man.skills.luck = 5 * 0.01
        except Exception:
            pass
        self.active.born_day = day
        # S8: he knows the man AHEAD of him. If the player is already somebody,
        # the new one has heard of him -- no briefing, just the rule.
        if _player_rank(self.player) >= RANK["mayor"]:
            self.active.learn_of_player("the player")
        self._note("NEMESIS BORN   %s, a %s of %s"
                   % (man.name, getattr(man, "job", None) or "idler", town.name))
        return True

    # -- the day -------------------------------------------------------------
    def tick(self, day: int, now: float) -> list:
        """Returns any lines the player is told today."""
        self.lines = []
        if day == self._last_day:
            return self.lines
        self._last_day = day
        nm = self.active
        if nm is None:
            return self.lines
        man = nm.npc
        if not getattr(man, "alive", False):
            # S8: the world progresses as normal, UNTIL ANOTHER ONE IS BORN.
            self._note("NEMESIS DEAD   %s" % man.name)
            self.active = None
            self.dead_day = day
            return self.lines
        nm.days_in_trade += 1
        self._climb(nm)
        self._word(nm, day)
        self._strike(nm, day, now)
        return self.lines

    # -- S3: the climb -------------------------------------------------------
    def _climb(self, nm) -> None:
        man, town = nm.npc, nm.town
        if not nm.wants_out():
            return
        # A BETTER POST, BEFORE THE TOWN OFFERS HIM A WORSE ONE. He does not
        # take what he is given; he takes what he wants and the man holding it
        # becomes idle. That is what scheming is.
        # AN OCCUPIED POST IS THE POINT. This asked `k in town.open_posts()`,
        # and open_posts() returns VACANCIES -- so he could only ever scheme
        # into a post that was already empty, which is not scheming at all. The
        # whole privilege is that the DISPLACED MAN GOES IDLE: he takes a post
        # off the man holding it. In a fully-staffed village -- which is most
        # of them -- the old test could never find anything, and he stood still
        # for ever. The sim found this on day one.
        # ONE RUNG AT A TIME, AND THE NEXT ONE -- NOT THE BEST ONE HE CAN
        # SEE. The old search walked the list from the top down and took the
        # first thing above him, so a farmer went straight to a caravan post:
        # he never learned the axe in the woods, the iron at the bench or the
        # mash in the tun. He climbs IN ORDER and gathers the trade of each
        # rung on the way up (S3).
        #
        # AND HE WALKS UP UNTIL HE FINDS A RUNG THIS TOWN HAS. A village with no
        # mine has no mine post to take, and a man who insists on the next rung
        # by name stands idle in the square for ever waiting for a trade that
        # does not exist here. Asking for the next one BY NAME broke his very
        # first move, which the sim caught inside a minute.
        kind = None
        holder = None
        vacancy = False
        for rung in range(nm.target_rank(), min(len(RUNGS), SCHEME_MAX + 1)):
            k = RUNGS[rung]
            if k is None or RANK.get(k, 0) > SCHEME_MAX:
                continue
            h = self._holder(town, k)
            if h is None and k not in town.open_posts():
                continue                    # this town has no such trade at all
            kind, holder = k, h
            vacancy = (h is None)
            break
        if kind is None:
            return                          # nothing above him exists here yet
        if holder is man:
            return
        if vacancy:
            # nothing to scheme: the rung is simply empty
            # AND THE TOOLS OF THE TRADE, WHICHEVER WAY HE GETS THE POST.
            #
            # This trusted `town.offer_post(man)` to hand them over -- and when
            # it returned False, the `else` set job="logger" and gave him
            # NOTHING. He then stood at a tree for days with empty hands:
            # _swing_tool("axe") found no axe and no spare, _work_woods
            # returned, he never felled, never gained a point of axe, and could
            # never master logging to leave the rung. The whole climb was stuck
            # on rung one and the log cheerfully said "takes the logger post".
            self._take_post(man, town, kind)
            nm._last_rung = RANK.get(kind, nm._last_rung)
            nm.days_in_trade = 0
            self._note("NEMESIS RISES  %s takes the vacant %s post in %s"
                       % (man.name, kind, town.name))
            return
        holder = self._holder(town, kind)
        if holder is man:
            return
        if holder is None:
            # nothing to scheme: the rung is simply empty
            self._take_post(man, town, kind)
            nm._last_rung = RANK.get(kind, nm._last_rung)
            self._note("NEMESIS RISES  %s takes the vacant %s post in %s"
                       % (man.name, kind, town.name))
            return
        # THE DISPLACED MAN GOES IDLE -- AND REMEMBERS (S3). Every rung leaves
        # one more man in the world who can sell him out.
        town.free_post(holder)
        held = getattr(holder, "name", "?")
        nm.grudges[held] = "put out of the %s" % kind
        self._take_post(man, town, kind)
        nm._last_rung = RANK.get(kind, nm._last_rung)
        nm.days_in_trade = 0
        self._note("NEMESIS RISES  %s takes the %s post from %s in %s"
                   % (man.name, kind, held, town.name))

    @staticmethod
    def _take_post(man, town, kind) -> None:
        """GIVE HIM THE POST HE TOOK, AND EVERYTHING THE POST OF NEEDS.

        The nemesis is a THIEF, so he is always already holding a trade when he
        takes the next one -- and every path here handed the post over through
        `town.offer_post(man)`, whose first line refuses any man with a job, a
        plot or a bench. So he fell into the `else`, was given the job TITLE,
        and nothing else: no shovel, no axe, no pickaxe, and no workplace at
        all. _work_woods found no axe and returned, _work_place sat down in the
        square because `self.workplace` was None, and he stood there for ever
        with a trade he could not work.

        It is why the climb stalled on its first rung in every clean run: one
        post taken, no skill gained, no coin earned, and a man going quietly
        broke. The log said "takes the mine post from Delma Boone" the whole
        time. A title is not a living.
        """
        import economy
        town.free_post(man)                     # one man, one post
        man.job = kind
        if kind == "farm":
            taken = {n.farm_plot for n in getattr(town, "npcs", ())
                     if n is not man and n.farm_plot is not None}
            for i in range(len(town.farm_plots)):
                if i not in taken:
                    man.farm_plot = i
                    man.leaf_farmer = True     # dual culture: leaf too
                    break
            man.stock["shovel"] = 1
            man.grade["shovel"] = 0
            man.tool_uses = economy.TOOL_USES
            return
        if kind == "logger":
            man.stock["axe"] = 1
            man.grade["axe"] = 0
            man.tool_uses = economy.TOOL_USES
            return
        if kind == "trader":
            man.trade_state = "none"
            return
        # THE PIT AND THE BENCH: he needs somewhere TO BE. offer_post sets
        # `workplace`; the old else never did, so the man had a trade and no
        # door to turn up at.
        wp = next((w for w in getattr(town, "workplaces", ())
                   if getattr(w, "kind", None) == kind
                   and (w.worker is None
                        or not getattr(w.worker, "alive", False)
                        or w.worker is man)), None)
        if wp is not None:
            man.workplace = wp
            wp.worker = man
        if kind == "smith":
            man.stock["iron"] = economy.IRON_STOCK // 4
        if kind == "mine":
            man.stock["pickaxe"] = 1
            man.grade["pickaxe"] = 0
            man.tool_uses = economy.TOOL_USES

    @staticmethod
    def _holder(town, kind):
        for n in getattr(town, "npcs", ()):
            if not getattr(n, "alive", False) or n is None:
                continue
            if kind == "trader" and n.job == "trader":
                return n
            if kind == "logger" and n.job == "logger":
                return n
            if kind == "farm" and n.farm_plot is not None:
                return n
            if getattr(n, "workplace", None) is not None \
                    and getattr(n.workplace, "kind", None) == kind:
                return n
        return None

    # -- S5, S6: word of him -------------------------------------------------
    def _word(self, nm, day: int) -> None:
        """CLUES DRIP, DO NOT POUR. One every so often, and the detail is set
        by who is ahead -- see Nemesis.clue."""
        if day - self.last_clue_day < 6:
            return
        self.last_clue_day = day
        pr = _player_rank(self.player)
        # S6: MISINFORMATION. Rare, random, and unreliable -- a rumour is not a
        # status update. Sometimes the man he names is a plain old NPC.
        if self.rng.random() < 0.20:
            others = [n for n in self.villages.villages
                      if n is not nm.town and len(getattr(n, "npcs", ()))]
            if others:
                t = self.rng.choice(others)
                men = [n for n in t.npcs if getattr(n, "alive", False)]
                if men:
                    m = self.rng.choice(men)
                    self.lines.append(
                        "%s is a really ambitious man. He is a %s now!"
                        % (m.name, getattr(m, "job", None) or "nobody much"))
                    return
        text = nm.clue(day, pr)
        if text:
            self.lines.append(text)

    # -- S7: the omen, and the attempt ---------------------------------------
    def _strike(self, nm, day: int, now: float) -> None:
        man, player = nm.npc, self.player
        mine, theirs = rank_of(man), _player_rank(player)
        # He only comes for somebody worth being. A nobody is not worth a
        # bullet, and he does not yet know the player's name.
        if not nm.knows_player and mine <= theirs:
            if mine > RANK["farm"]:
                nm.learn_of_player("the player")
            return
        if nm.strike_day < 0:
            if self.rng.random() < 0.02:          # rare
                nm.schedule_strike(day, self.rng)
                crown = _player_rank(player) >= RANK["mayor"]
                pool = CROWN_OMENS if crown else REAL_OMENS
                self._note("NEMESIS OMEN   spoken on day %d, strike day %d"
                           % (day, nm.strike_day))
                self.lines.append(self.rng.choice(pool))
            elif self.rng.random() < 0.05:
                # THE DRUNK (S7). Indistinguishable, and nothing happens.
                self.lines.append(self.rng.choice(DRUNK_OMENS))
            return
        if day < nm.strike_day:
            return
        # THE DAY. He only comes if the player is EXPOSED -- asleep, or alone.
        nm.strike_day = -1
        asleep = getattr(player, "asleep", False)
        far = math.hypot(man.x - player.x, man.y - player.y)
        if not asleep and far > 900.0:
            self._note("NEMESIS ABORTS  player was not exposed")
            return
        nm.strikes += 1
        self._note("NEMESIS STRIKE  attempt %d on %s" % (nm.strikes, man.name))
        self.lines.append("Something wakes you in the dark.")
        try:
            player.take_damage(30)
        except Exception:
            player.health = getattr(player, "health", 100) - 30
