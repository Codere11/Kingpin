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
            quality: int | None = None) -> int | None:
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
                        remaining -= take
                        if first is None:
                            first = i
            while remaining > 0:
                slot = self._first_empty()
                if slot is None:
                    break
                take = min(defn.max_stack, remaining)
                self.slots[slot] = ItemStack(defn, take, q_here)
                remaining -= take
                if first is None:
                    first = slot
        else:
            while remaining > 0:
                slot = self._first_empty()
                if slot is None:
                    break
                self.slots[slot] = ItemStack(defn, 1)
                remaining -= 1
                if first is None:
                    first = slot
        return first

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

    def selected_stack(self) -> ItemStack | None:
        return self.slots[self.selected]

    def selected_def(self) -> items.ItemDef | None:
        stack = self.selected_stack()
        return stack.defn if stack else None
