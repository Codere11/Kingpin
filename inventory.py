"""Simple slot inventory."""

from __future__ import annotations

from dataclasses import dataclass

import items
from quality import clamp, merge


@dataclass
class ItemStack:
    defn: items.ItemDef
    count: int = 1
    quality: int | None = None
    # SOMETHING THIS PARTICULAR STACK CARRIES, for things that are not just a
    # count: a Secret Folder is one dead agent's messages, and which agent's is
    # the whole point.
    payload: object = None
    # A unique thing's plain-data biography: maker, origin, owner, history.
    provenance: dict | None = None
    # Bulk crop lots carry the PLANT KIND and (later) a genetics record.
    plant_kind: str | None = None
    genetics: dict | None = None


class Inventory:
    def __init__(self, capacity: int = 8) -> None:
        self.capacity = capacity
        self.slots: list[ItemStack | None] = [None] * capacity
        self.selected = 0

    def _first_empty(self) -> int | None:
        for i, stack in enumerate(self.slots):
            if stack is None:
                return i
        return None

    def add(self, item_id: str, count: int = 1,
            quality: int | None = None, maker=None, origin=None,
            owner=None, now: float = 0.0, plant_kind: str | None = None,
            genetics: dict | None = None) -> int | None:
        """Add items, stacking up to max_stack and spilling into new slots."""
        defn = items.get(item_id)
        if item_id == "coin":
            # COIN IS WHOLE. Prices are fractional on purpose -- a village
            # ledger keeps its fractions -- but a purse does not hold
            # 16.234314 coins, and it should never print like one.
            count = int(round(count))
            if count <= 0:
                return count
        if defn.quality and quality is None:
            quality = 0
        # A GRADE IS PART OF WHAT A THING IS. Two lots of tobacco of different
        # quality are two different lots and must be two different stacks --
        # they used to be merged into one and the merged stack was given the
        # AVERAGE of the grades, so a D and an F became a single E and nobody
        # would buy it. The good leaf was not lost; it was diluted, and there
        # was no row to sell it on because there was no stack to sell from.
        q_here = clamp(quality) if defn.quality else None
        remaining = count
        first = None

        if defn.stackable:
            for i, stack in enumerate(self.slots):
                if remaining <= 0:
                    break
                if stack is not None and stack.defn.id == item_id:
                    if defn.quality and stack.quality != q_here:
                        continue             # a different grade: its own stack
                    room = defn.max_stack - stack.count
                    if room > 0:
                        take = min(room, remaining)
                        if defn.quality:
                            base = stack.quality if stack.quality is not None else quality
                            stack.quality = merge(base, stack.count, quality, take)
                        stack.count += take
                        if stack.plant_kind is None:
                            stack.plant_kind = plant_kind
                        # A STRAIN THAT MIXES WITH ANYTHING ELSE BECOMES
                        # ORDINARY.  This is the player-facing rule and it
                        # must apply both ways: local + regular, or two
                        # different settlements.
                        if genetics is not None:
                            if stack.genetics is None:
                                stack.genetics = genetics
                            elif stack.genetics != genetics:
                                stack.genetics = None
                        elif stack.genetics is not None:
                            stack.genetics = None
                        remaining -= take
                        if first is None:
                            first = i
            while remaining > 0:
                slot = self._first_empty()
                if slot is None:
                    break
                take = min(defn.max_stack, remaining)
                stack = ItemStack(defn, take, q_here)
                stack.plant_kind = plant_kind
                stack.genetics = genetics
                self.slots[slot] = stack
                remaining -= take
                if first is None:
                    first = slot
        else:
            while remaining > 0:
                slot = self._first_empty()
                if slot is None:
                    break
                stack = ItemStack(defn, 1)
                stack.plant_kind = plant_kind
                stack.genetics = genetics
                # Tools, weapons, armour and other non-stacking objects get a
                # biography the moment they enter the world.  Bulk goods stay
                # as cheap counts.
                try:
                    import itemstory
                    if itemstory.is_unique(item_id):
                        stack.provenance = itemstory.make(
                            item_id, maker=maker, origin=origin,
                            owner=owner, now=now)
                        itemstory.record(stack, "made", actor=maker,
                                         place=origin, now=now)
                        itemstory.remember(owner, stack)
                except Exception:
                    pass
                self.slots[slot] = stack
                remaining -= 1
                if first is None:
                    first = slot
        return first

    def add_stack(self, stack, owner=None, now: float = 0.0):
        """Put a real ItemStack into this inventory, keeping its provenance.

        Bulk goods can still merge by count; a unique object must not be
        recreated by add() because that would erase its biography.
        """
        if stack is None or int(getattr(stack, "count", 0)) <= 0:
            return None
        if stack.defn.stackable:
            first = self.add(stack.defn.id, int(stack.count),
                              getattr(stack, "quality", None),
                              owner=owner, now=now,
                              plant_kind=getattr(stack, "plant_kind", None),
                              genetics=getattr(stack, "genetics", None))
            return first
        slot = self._first_empty()
        if slot is None:
            return None
        self.slots[slot] = stack
        try:
            import itemstory
            if owner is not None:
                itemstory.set_owner(stack, owner)
        except Exception:
            pass
        return slot

    def select(self, index: int) -> None:
        if 0 <= index < self.capacity:
            self.selected = index

    def count_of(self, item_id: str) -> int:
        return sum(s.count for s in self.slots if s is not None and s.defn.id == item_id)

    def consume(self, item_id: str, amount: int = 1) -> bool:
        """Remove ``amount`` of an item. Returns True if fully consumed."""
        remaining = amount
        for i, stack in enumerate(self.slots):
            if stack is None or stack.defn.id != item_id:
                continue
            take = min(remaining, stack.count)
            stack.count -= take
            remaining -= take
            if stack.count <= 0:
                self.slots[i] = None
            if remaining <= 0:
                return True
        return remaining <= 0

    def take_lot(self, item_id: str, amount: int):
        """Consume up to amount and return (taken, genetics).

        If the consumed amount spans different strains, the genetics is
        dropped: mixed lots are ordinary, exactly as when stacks merge.
        """
        remaining = int(amount)
        taken = 0
        gen = None
        mixed = False
        for i, stack in enumerate(self.slots):
            if stack is None or stack.defn.id != item_id:
                continue
            take = min(remaining, stack.count)
            if take <= 0:
                break
            sg = getattr(stack, "genetics", None)
            if gen is None:
                gen = sg
            elif sg != gen:
                mixed = True
            stack.count -= take
            taken += take
            remaining -= take
            if stack.count <= 0:
                self.slots[i] = None
            if remaining <= 0:
                break
        if mixed:
            gen = None
        return taken, gen

    def selected_stack(self) -> ItemStack | None:
        return self.slots[self.selected]

    def selected_def(self) -> items.ItemDef | None:
        stack = self.selected_stack()
        return stack.defn if stack else None
