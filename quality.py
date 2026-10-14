"""Tobacco quality grades F .. SSS."""

from __future__ import annotations

GRADES = ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]

# coins per tobacco, by grade: better leaf fetches a better price.
SELL_VALUE = [0.34, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]


def sell_coins(index: int, count: int) -> int:
    return int(round(count * SELL_VALUE[clamp(index)]))


def clamp(index: int) -> int:
    return max(0, min(len(GRADES) - 1, int(index)))


def letter(index: int) -> str:
    return GRADES[clamp(index)]


def merge(q1: int, c1: int, q2: int, c2: int) -> int:
    """Quality of a stack formed from c1 of q1 plus c2 of q2 (count-weighted)."""
    if c1 + c2 <= 0:
        return clamp(q1)
    return clamp(round((q1 * c1 + q2 * c2) / (c1 + c2)))
