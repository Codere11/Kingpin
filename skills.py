"""Hidden character skills.

Skills are never shown to the player. They only change outcomes -- the quality
of the tobacco you grow, how fast you move, how hard you swing an axe, and how
tightly you shoot. Each one improves simply by being used.
"""

from __future__ import annotations

import math
import random

# -- movement: walking/sprinting speed, and stamina duration -----------------
MOVE_LO = 0.75                 # -25% at zero skill ...

# BARE HANDS. A fist is the same motion and the same skill as an axe -- a
# villager who has swung one all his life swings the other just as well -- but
# flesh is not steel. A blow lands a THIRD of what the axe would, so an
# unarmed man can still win a fight, and will still lose one to anybody
# holding anything. The tournament in the capital is fought this way.
UNARMED_WEAKNESS = 3.0
MOVE_HI = 1.50                 # ... +50% at maximum
# A MASTER'S ROAD IS LONG. These are the distances, swings and shots that a
# working life actually accumulates in about three hundred days -- so a man who
# does the work every day of a long game ends it a master, and a man who does
# not, does not. Everyone starts at zero; the road is simply much longer now.
# (Estimates of a day's exposure are in the comments; they want watching.)
MOVE_NEED = 7500000.0          # px. ~25,000 px a day x 300 days

# -- axe: swing cooldown, and melee damage -----------------------------------
AXE_CD_LO = 2.00               # 1.5 s + 0.5 s at zero skill
AXE_CD_HI = 0.10               # a tenth of a second at maximum
AXE_DMG_LO = 0.75              # -25% damage at zero skill
AXE_NEED = 12000.0             # swings. ~40 a day x 300 days

# -- shooting: aim wobble ----------------------------------------------------
SHOT_SPREAD_LO = math.radians(15.0)   # "somewhere around there" at zero skill
SHOOT_NEED = 3000.0                    # shots. ~10 a day x 300 days

# -- THE ROAD, REWORKED -------------------------------------------------------
# LEARNING THE BASICS IS EASY; EVERYTHING AFTER THAT IS LONG. The first level
# comes in a handful of goes, the second nearly as fast, and by the sixth a man
# is on the slow road for good.
#
# WHO LEARNS THIS WAY. NPCs and the nemesis learn everything this way. The
# PLAYER learns this way ONLY for the axe (chopping and melee) and for walking
# -- for the plough and the rifle he keeps the older, slower road, because a
# player who can reach SSS leaf on his own is playing a different game from the
# men around him.
LEVEL_RATES = (0.30, 0.25, 0.20, 0.15, 0.10)   # levels one to five, per action
TAIL_RATE = 0.01                               # level six, and the rest of a life
LUCK_OTHERS = 0.01        # a chance, on any action, of a whole level at once
LUCK_NEMESIS = 0.05


class Skills:
    # CLASS-LEVEL DEFAULTS, AND NOT OPTIONAL. A world cache written before
    # these existed holds Skills objects with only the four old fields, and an
    # unpickled instance does not run __init__ -- so every one of them came back
    # with no `luck` and no `is_player`, and the first villager to walk a step
    # died with AttributeError. The same shape as the missing `tax_frac` that
    # once killed every miner: a new field must have a default on the CLASS, so
    # that anything restored from an older world still works.
    luck = LUCK_OTHERS
    is_player = False
    research = 0.0
    # A LEVEL WAS JUST CROSSED. Class default, for the same reason as the two
    # above: an unpickled Skills object does not run __init__.
    just_leveled = False

    def __init__(self, is_player: bool = False) -> None:
        self.farming = 0.0            # 0..8, grows with harvesting
        self.movement = 0.0           # 0..1
        self.axe = 0.0                # 0..1
        self.shooting = 0.0           # 0..1
        self.research = 0.0           # 0..10, grows with researching
        self.is_player = is_player    # the old road, except the axe and the feet
        self.luck = LUCK_OTHERS       # the nemesis is handed LUCK_NEMESIS

    # -- WHEN A LEVEL IS CROSSED --------------------------------------------
    def levels_total(self) -> int:
        """All four skills together, counted in LEVELS.

        A level is a band, and each skill says how wide: 0.125 for the three
        that run 0..1, and 1.0 for farming, which runs 0..8. Eight each.
        """
        return (int(self.movement / 0.125) + int(self.axe / 0.125)
                + int(self.shooting / 0.125) + int(self.farming)
                + int(self.research))

    def _note_levels(self, before: int) -> None:
        """Raise the flag if this gain crossed a level.

        THE PLAYER ONLY. This stands on gain_movement, which is called for
        every walking villager on every frame -- a thousand men, sixty times a
        second -- and four divisions apiece to notice something nobody is
        watching. The shine is the player's, so the watching is the player's.
        """
        if before and self.levels_total() > before:
            self.just_leveled = True

    # -- the one way anybody learns -----------------------------------------
    def _step(self, value: float, cap: float, band: float) -> float:
        """ONE ACTION'S WORTH OF LEARNING, and the whole rework in eight lines.

        The rate is set by the LEVEL a man is standing on -- easy at the bottom,
        brutal at the top -- and on any given action there is a small chance of
        skipping a whole level, which is how a man sometimes just... gets it.
        """
        lvl = int(value / band)
        rate = LEVEL_RATES[lvl] if lvl < len(LEVEL_RATES) else TAIL_RATE
        nxt = value + rate
        if random.random() < self.luck:
            nxt = max(nxt, (lvl + 1) * band)
        return min(cap, nxt)

    # -- farming ------------------------------------------------------------
    # The hand learns slowly. Harvests are the only teacher, and a working
    # farmer gets two or three a day -- so eight grades of hands is a career,
    # not a season. This divisor is what makes it so, in ONE place: every
    # caller still says "a harvest is 0.02", and the road is what changed.
    FARM_SLOW = 0.5

    def gain_farming(self, amount: float = 0.12) -> None:
        _b = self.levels_total() if self.is_player else 0
        if self.is_player:               # the player ploughs the OLD road
            self.farming = min(8.0, self.farming + amount * self.FARM_SLOW)
            self._note_levels(_b)
            return
        self.farming = self._step(self.farming, 8.0, 1.0)

    def leaf_grade(self) -> int:
        """What this pair of hands produces: his skill, nothing else."""
        base = min(8, int(self.farming))
        grade = base + random.choice((-1, 0, 0, 0, 1))
        return max(0, min(8, grade))

    def tobacco_grade(self) -> int:
        base = min(8, int(self.farming))
        grade = base + random.choice((-1, 0, 0, 0, 1))
        return max(0, min(8, grade))

    # -- research -----------------------------------------------------------
    def gain_research(self, amount: float = 0.1) -> None:
        """A researcher learns by working at the bench: ten levels of it."""
        _b = self.levels_total() if self.is_player else 0
        self.research = self._step(self.research, 10.0, 1.0)
        if self.is_player:
            self._note_levels(_b)

    # -- movement -----------------------------------------------------------
    def gain_movement(self, distance: float) -> None:
        if distance <= 0.0:
            return
        _b = self.levels_total() if self.is_player else 0
        # NOT ONE ACTION BUT SIXTY A SECOND -- this is called for every moving
        # villager on every frame -- so it uses the module's random directly.
        # A local `import random as _r` here cost a dictionary lookup in
        # sys.modules a thousand times a frame, which is exactly the kind of
        # thing that quietly eats the frame time we won yesterday.
        # AND IT CANNOT USE _step: a per-frame luck roll would fire constantly.
        # directly: a per-frame luck roll would fire constantly. The LEVEL sets
        # a MULTIPLIER on the old distance rule instead, and the luck is scaled
        # by how far he actually moved -- a step across the room is not a walk
        # to the next town.
        lvl = int(self.movement / 0.125)
        rate = LEVEL_RATES[lvl] if lvl < len(LEVEL_RATES) else TAIL_RATE
        self.movement = min(1.0, self.movement
                            + (distance / MOVE_NEED) * (rate / 0.125))
        if random.random() < self.luck * min(1.0, distance / 20.0):
            self.movement = min(1.0, max(self.movement,
                                         (lvl + 1) * 0.125))
        self._note_levels(_b)

    def move_scale(self) -> float:
        """Walking/sprinting multiplier: 0.75 at start, 1.5 mastered."""
        return MOVE_LO + (MOVE_HI - MOVE_LO) * self.movement

    def stamina_scale(self) -> float:
        """Sprint duration multiplier: 0.75 at start, 1.5 mastered."""
        return MOVE_LO + (MOVE_HI - MOVE_LO) * self.movement

    # -- axe ----------------------------------------------------------------
    def gain_axe(self, amount: float = 1.0) -> None:
        # EVERYONE LEARNS THE AXE THE NEW WAY -- the player included.
        _b = self.levels_total() if self.is_player else 0
        self.axe = self._step(self.axe, 1.0, 0.125)
        self._note_levels(_b)

    def axe_cooldown(self) -> float:
        """Seconds between swings: 2.0 at start, 0.1 mastered."""
        return AXE_CD_LO + (AXE_CD_HI - AXE_CD_LO) * self.axe

    def axe_damage_scale(self) -> float:
        """Fraction of full melee damage: 0.75 at start, 1.0 mastered."""
        return AXE_DMG_LO + (1.0 - AXE_DMG_LO) * self.axe

    # -- shooting -----------------------------------------------------------
    def gain_shooting(self, amount: float = 1.0) -> None:
        _b = self.levels_total() if self.is_player else 0
        if self.is_player:               # the player shoots the OLD road
            self.shooting = min(1.0, self.shooting + amount / SHOOT_NEED)
            self._note_levels(_b)
            return
        self.shooting = self._step(self.shooting, 1.0, 0.125)

    def shot_spread(self) -> float:
        """Radians of aim wobble: 10 deg at start, dead-on when mastered."""
        return SHOT_SPREAD_LO * (1.0 - self.shooting)
