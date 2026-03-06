"""Dice rolling utilities — faithful to D&D conventions."""

import random


def roll(n: int, sides: int) -> int:
    """Roll n dice with given number of sides, return total."""
    return sum(random.randint(1, sides) for _ in range(n))


def d4(n: int = 1) -> int:
    return roll(n, 4)


def d6(n: int = 1) -> int:
    return roll(n, 6)


def d8(n: int = 1) -> int:
    return roll(n, 8)


def d10(n: int = 1) -> int:
    return roll(n, 10)


def d12(n: int = 1) -> int:
    return roll(n, 12)


def d20(n: int = 1) -> int:
    return roll(n, 20)


def d100(n: int = 1) -> int:
    return roll(n, 100)


def ability_roll() -> int:
    """Roll 4d6, drop lowest — standard D&D ability score generation."""
    rolls = sorted([random.randint(1, 6) for _ in range(4)])
    return sum(rolls[1:])
