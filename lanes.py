"""Lanes: the world cut into pieces, each owned by exactly one core.

THE CUT
-------
The frame is 68-83% one loop -- `for _n in PEOPLE: n.tick()` -- and 13-26% the
towns. Both live inside per-town data. The only things that cross a fence are a
short, named list: traders on the road, armies, refugees, news, prices, the
crown, the player.

So the world is cut at the fence, and LANE 0 IS THE MAIN PROCESS: the towns the
player is part of, the render, the terrain, the player. Lanes 1..n are workers,
each holding a share of the other towns and stepping them on its own core.

THE INVARIANT -- and it is the whole safety argument
----------------------------------------------------
ONE MAN, ONE PLACE, and here it is stronger: ONE MAN, ONE LANE, AND EVERY MAN
IN A LANE. A town belongs to exactly one lane. Every living man belongs to
exactly one lane: his town's, or the lane that owns the road he is walking.

Why this is safe: the moment two lanes may write one granary, the game is
corrupt -- not slow, corrupt. Two cores inside one Python dict is not a race
you win by being careful. So the cut is not a performance trick bolted onto the
simulation; it is a partition of OWNERSHIP, and `audit()` exists to prove that
the partition holds, because a partition that leaks is worse than no split.

WHY A MAN IS OWNED BY HIS TOWN AND NOT BY HIS FEET
--------------------------------------------------
A traveller is between towns most of the time. Ownership by position would mean
handing him over every few frames. Ownership by HOME means he is handed over
once, when he leaves, and once, when he arrives -- and `village.py` already does
exactly that: leaving a town appends him to TRAVELLERS and frees his post;
arriving removes him from TRAVELLERS and puts him back on the roll. The seam is
already written; this module just names which lane it lands in.

WHAT THIS MODULE DELIBERATELY IS NOT
------------------------------------
It does not know about processes, pipes or forks. It is the CUT, and nothing
else, so it can be tested without any of them -- and so that the one-process
path can use the same cut, which is how it gets verified before any process is
involved.
"""

from __future__ import annotations

LANE_MAIN = 0


class Partition:
    """Every town and every man, split into lanes. Recut as the player moves."""

    def __init__(self, nlanes: int = 1) -> None:
        self.nlanes = max(1, int(nlanes))
        self.towns: list[list] = [[] for _ in range(self.nlanes)]
        self.people: list[list] = [[] for _ in range(self.nlanes)]
        # homes and houses travel WITH their town, for the same reason people
        # do: a household's larder is the household's, and `Village.update`
        # reads it through the town.
        self._town_lane: dict[int, int] = {}

    # -- the cut -----------------------------------------------------------
    def recut(self, all_towns, main_towns=(), road_owner=None) -> None:
        """Lay the world out across the lanes.

        main_towns are the towns the player is part of: the ones on screen and
        the one he is standing in. They stay on the main lane, always -- a town
        the player is looking at must be stepped where the player is, or the
        picture and the world disagree.
        """
        self.towns = [[] for _ in range(self.nlanes)]
        self.people = [[] for _ in range(self.nlanes)]
        self._town_lane = {}

        main_ids = {id(t) for t in main_towns}
        others = [t for t in all_towns if id(t) not in main_ids]

        for t in all_towns:
            if id(t) in main_ids:
                self._place(t, LANE_MAIN)

        if self.nlanes == 1:
            for t in others:
                self._place(t, LANE_MAIN)
        else:
            # BALANCE BY HOUSES, because a house is what a lane pays for: a
            # town of 57 houses costs far more a frame than one of 12, and
            # round-robin would hand one worker the three capitals.
            load = [0] * self.nlanes
            for t in sorted(others, key=lambda v: -len(getattr(v, "houses", ()))):
                k = min(range(1, self.nlanes), key=lambda i: load[i])
                self._place(t, k)
                load[k] += len(getattr(t, "houses", ()))

        # THE ROAD. A man between towns is owned by the lane that owns the road
        # he is on, and the road has exactly one owner -- otherwise two lanes
        # walk the same trader and he arrives twice.
        if road_owner is None:
            road_owner = LANE_MAIN
        self.road_owner = road_owner
        self._place_road()

    def _place(self, town, lane: int) -> None:
        lane = max(0, min(lane, self.nlanes - 1))
        self.towns[lane].append(town)
        self._town_lane[id(town)] = lane
        for n in getattr(town, "npcs", ()):
            if getattr(n, "alive", False):
                self.people[lane].append(n)

    def _place_road(self) -> None:
        """The men on the road go to the road's lane -- once each.

        A traveller is NOT in any town's npcs while he walks (leaving a town
        appends him to TRAVELLERS and takes him off the roll), so he is not
        already placed. But a trader whose home town is in lane 3 and whose road
        belongs to lane 0 would be double-owned if we took both, so the road is
        placed LAST and every man already placed is skipped by identity.
        """
        try:
            import village as _v
            road = list(_v.TRAVELLERS)
        except Exception:
            return
        seen = {id(n) for lane in self.people for n in lane}
        dest = self.people[self.road_owner]
        for n in road:
            if id(n) in seen:
                continue
            if getattr(n, "alive", False):
                dest.append(n)
                seen.add(id(n))

    # -- the question the frame asks --------------------------------------
    def towns_for(self, lane: int) -> list:
        return self.towns[lane]

    def people_for(self, lane: int) -> list:
        return self.people[lane]

    def lane_of_town(self, town) -> int:
        return self._town_lane.get(id(town), LANE_MAIN)

    # -- the proof ---------------------------------------------------------
    def audit(self, all_towns, road=(), all_people=None) -> dict:
        """Every town once, every living man once, and nothing left over.

        This is the test that matters. A split world that loses a man is a
        world that quietly gets smaller; one that ticks a man twice is a world
        where a farmer does two days' work in one and the granary disagrees
        with itself. Neither announces itself, so it is counted.

        `all_people` is the AUTHORITY -- village.PEOPLE, the flat register the
        frame has always walked. The audit is against that and not against the
        towns, because the question is not "did I place the men I found" but
        "did I place every man the game has". A man in the register and in no
        lane is a man who has stopped living, and he will never say so.
        """
        t_seen: dict[int, int] = {}
        n_seen: dict[int, int] = {}
        for lane in self.towns:
            for t in lane:
                t_seen[id(t)] = t_seen.get(id(t), 0) + 1
        for lane in self.people:
            for n in lane:
                n_seen[id(n)] = n_seen.get(id(n), 0) + 1

        towns_missing = [t for t in all_towns if id(t) not in t_seen]
        if all_people is not None:
            authority = list(all_people)
        else:
            authority = list(road)
        people_missing = [n for n in authority
                          if getattr(n, "alive", False) and id(n) not in n_seen]
        return {
            "lanes": self.nlanes,
            "towns": sum(len(l) for l in self.towns),
            "people": sum(len(l) for l in self.people),
            "authority": len(authority),
            "towns_twice": sum(1 for c in t_seen.values() if c > 1),
            "people_twice": sum(1 for c in n_seen.values() if c > 1),
            "towns_missing": len(towns_missing),
            "people_missing": len(people_missing),
            "per_lane_towns": [len(l) for l in self.towns],
            "per_lane_people": [len(l) for l in self.people],
        }

    def ok(self, all_towns, road=(), all_people=None) -> bool:
        a = self.audit(all_towns, road, all_people)
        return (a["towns_twice"] == 0 and a["people_twice"] == 0
                and a["towns_missing"] == 0 and a["people_missing"] == 0)
