"""THE TEST OF STRENGTHS.

Every KING_ELECTION_DAYS the realm settles the crown by force of arms. The
sitting King and every mayor of the nation are called to the capital, they
stand in the square in front of whoever cares to watch, and they fight --
UNARMED, in pairs, one bout at a time, until one man is left standing. He is
the King.

A bout STOPS at economy.TOURNAMENT_FLOOR health. Nobody is butchered at a
coronation: a man who has taken a beating concedes, both men are patched up,
and the winner goes on to the next round. The loser keeps his life, his office
and his purse, and goes home.

THE FIGHTING IS THE GAME'S OWN. The men are ordinary villagers drawn in the
ordinary way, they are driven by NPC._fight -- the same routine that decides
every axe-fight in the world -- and they are watched through the same camera.
Nothing here fakes a duel: it only decides WHO fights WHOM, keeps them in the
ring, and stops them at the floor.
"""

from __future__ import annotations

import math
import random

import economy


class Tournament:
    """One Test of Strengths, in one capital."""

    def __init__(self, capital, candidates: list) -> None:
        self.capital = capital
        self.out = {}          # seconds each man has been outside the ring
        self.arena = (capital.x, capital.y)
        # The ring. A capital's square is a square, not a duelling ground, so
        # the ring is cut out of it generously -- wide enough that a man can
        # give ground without stepping into the crowd.
        self.radius = max(170.0, capital.plaza_radius * 3.0)
        # THE FLOOR IS A SHARE OF THE MAN, NOT A NUMBER. A villager has 40
        # health, not 100 -- so a flat floor of 50 put every fighter BELOW it
        # before the first blow, every bout ended on its opening tick, and the
        # bracket "ran" ten fights in which nobody ever swung. TOURNAMENT_FLOOR
        # is 50 out of a nominal 100, which is HALF: half of whatever body the
        # man actually has. The same rule then means the same thing for a
        # mayor, a soldier and a King.
        self.field = [c for c in candidates if getattr(c, "alive", False)]
        random.shuffle(self.field)         # the draw is by lot, not by rank
        self.round = 0
        self.bout: list = []
        self.pending = list(self.field)
        self.done = False
        self.winner = None
        self.player = None
        for i, m in enumerate(self.field):
            self.place(m, i, len(self.field))
            m.duel_tournament = self

    # -- the ring ------------------------------------------------------------
    def place(self, npc, i: int, n: int) -> None:
        """Put him on his mark, facing the middle, with nothing in his hands."""
        ang = (i / max(1, n)) * math.tau
        npc.x = self.arena[0] + math.cos(ang) * self.radius * 0.55
        npc.y = self.arena[1] + math.sin(ang) * self.radius * 0.55
        npc.weapon = None                  # BARE HANDS: the whole point
        npc.aggro = False
        npc.panic = 0.0
        npc.asleep = False
        npc.in_interior = False
        npc.refuge = None

    def inside(self, npc) -> bool:
        """Is he within the ring?

        Missing from the first cut of this file -- tick_outside called it on
        the opening tick of the opening bout and the whole Test died with an
        AttributeError, which is exactly the sort of thing only a real run
        finds.
        """
        return (math.hypot(npc.x - self.arena[0], npc.y - self.arena[1])
                <= self.radius)

    OUT_SECONDS = 10.0                 # this long outside and the bout is lost

    def tick_outside(self, man, dt: float) -> bool:
        """KEEP THE RING. Returns True when he has been out too long.

        Shoved past the edge is a thing that happens in a fight; standing out
        there for ten seconds is not fighting any more. Applies to everybody
        in the ring -- the NPCs and the player alike, because the rule is the
        ring's and not the man's.
        """
        key = id(man)
        if self.inside(man):
            self.out[key] = 0.0
            return False
        self.out[key] = self.out.get(key, 0.0) + dt
        return self.out[key] >= self.OUT_SECONDS

    def confine(self, npc, dt: float) -> None:
        """A man who is shoved out of the ring walks back in.

        He does not leave the fight and he is not counted out -- being pushed
        past the edge is a thing that happens in a fight, not a forfeit.
        """
        dx = npc.x - self.arena[0]
        dy = npc.y - self.arena[1]
        d = math.hypot(dx, dy)
        if d <= self.radius:
            return
        ux, uy = -dx / d, -dy / d
        npc.x += ux * npc.speed * 1.5 * dt
        npc.y += uy * npc.speed * 1.5 * dt
        npc.facing = (ux, uy)

    def end_bout(self, loser, winner) -> None:
        """The bout is over. BOTH MEN ARE PATCHED UP -- and ONLY here.

        BETWEEN ROUNDS, AND NOWHERE ELSE. A man carries no wound into the next
        bout: the winner is whole again before he is paired, which is what
        makes the bracket a test of the fighters rather than of the order the
        lot happened to draw. Nobody is healed DURING a bout, so a beaten man
        stays beaten until it ends.
        """
        loser.health = max(1, int(loser.health))
        winner.health = winner.max_health
        winner.stamina = getattr(winner, "max_stamina", 100.0)
        loser.stamina = getattr(loser, "max_stamina", 100.0)
        if hasattr(loser, "attack_cd"):
            loser.attack_cd = 0.0
        self.out[id(loser)] = 0.0
        self.out[id(winner)] = 0.0
        self.pending.append(winner)
        loser.duel_tournament = None
        self.bout = []
        if len(self.pending) < 2:
            self.finish()

    @staticmethod
    def floor_for(npc) -> float:
        """Where THIS man's bout stops: economy.TOURNAMENT_FLOOR out of 100."""
        return max(1.0, npc.max_health * (economy.TOURNAMENT_FLOOR / 100.0))

    # -- the bracket ---------------------------------------------------------
    def next_bout(self) -> bool:
        """Take the next pair. Returns False when the tournament is over."""
        if len(self.pending) < 2:
            self.done = True
            self.winner = self.pending[0] if self.pending else None
            return False
        a = self.pending.pop(0)
        b = self.pending.pop(0)
        ang = random.uniform(0.0, math.tau)
        for m, sign in ((a, 1.0), (b, -1.0)):
            m.x = self.arena[0] + math.cos(ang) * self.radius * 0.5 * sign
            m.y = self.arena[1] + math.sin(ang) * self.radius * 0.5 * sign
            m.health = m.max_health          # patched up between rounds
            m.stamina = m.max_stamina
            m.attack_cd = 0.0
            m.weapon = None
            m.duel_tournament = self
        self.bout = [a, b]
        self.round += 1
        self.capital.crier = ("Round %d: %s against %s"
                              % (self.round, a.name, b.name))
        economy._note("TOURNAMENT  %s   round %d   %s (%d hp) vs %s (%d hp)"
                      % (self.capital.name, self.round, a.name, a.max_health,
                         b.name, b.max_health))
        return True

    def tick(self, dt: float, combat) -> None:
        if self.done:
            return
        if not self.bout:
            if not self.next_bout():
                self.finish()
                return
        a, b = self.bout
        if not (a.alive and b.alive):
            self.bout = []
            self.pending.append(a if a.alive else b)
            return
        # BOTH MEN FIGHT, WITH THE GAME'S OWN ROUTINE. _fight is what every
        # villager in the world uses on a wolf; the tournament only supplies
        # the target and keeps them in the ring.
        player = getattr(self, "player", None)
        out_loser = None
        for me, other in ((a, b), (b, a)):
            # THE PLAYER FIGHTS HIMSELF. His side of the bout is run by his own
            # hands and his own keys -- there is nothing for the tournament to
            # do but watch, keep the clock and judge him by the same rules.
            if me is not player:
                self.confine(me, dt)
                # NO MAN TAKES THE FIELD ANGRY. A contestant is fighting a
                # drawn opponent under the King's law, not defending himself
                # against a threat -- and an NPC on the field who started
                # treating his rival as a threat would have the whole square's
                # guards and the crowd's neighbours joining in. The ring is
                # shut: inside it only the two men in it fight.
                me.weapon = None
                me.aggro = False
                me.panic = 0.0
                me._fight(dt, other, combat)
            if self.tick_outside(me, dt):
                out_loser = me
        if out_loser is not None:
            other = b if out_loser is a else a
            economy._note("TOURNAMENT  %s is OUT OF THE RING for %ds -- beaten"
                          % (out_loser.name, int(self.OUT_SECONDS)))
            self.end_bout(out_loser, other)
            return
        # THE FLOOR. He who first drops to it has lost the bout.
        loser = winner = None
        if a.health <= self.floor_for(a):
            loser, winner = a, b
        elif b.health <= self.floor_for(b):
            loser, winner = b, a
        if loser is not None:
            economy._note("TOURNAMENT  %s beats %s  (%d hp left of %d, floor %.0f)"
                          % (winner.name, loser.name, int(loser.health),
                             loser.max_health, self.floor_for(loser)))
            self.end_bout(loser, winner)

    # -- the crown -----------------------------------------------------------
    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        self.winner = self.pending[0] if self.pending else None
        for m in self.field:
            m.duel_tournament = None
            m.aggro = False
            if getattr(m, "alive", False):
                m.health = m.max_health       # everybody walks out of it
        if self.winner is None:
            return
        self.capital.crown(self.winner)
        self.capital.crier = "%s is King" % self.winner.name
        economy._note("TOURNAMENT  %s WINS THE CROWN of %s"
                      % (self.winner.name, self.capital.name))
