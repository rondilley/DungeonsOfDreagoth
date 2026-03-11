"""Trap system — types, detection, and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dreagoth.entities.item import roll_dice


class TrapType(Enum):
    PIT = "pit"
    SPIKE = "spike"
    POISON_DART = "poison_dart"
    ALARM = "alarm"
    TRAP_DOOR = "trap_door"


@dataclass
class Trap:
    """A trap placed on the dungeon grid."""
    trap_type: TrapType
    x: int
    y: int
    detected: bool = False
    triggered: bool = False
    difficulty: int = 12  # DC for perception check


# Detection bonuses by class and race
CLASS_DETECT_BONUS: dict[str, int] = {
    "thief": 4,
    "cleric": 2,
    "fighter": 0,
    "mage": 1,
}

RACE_DETECT_BONUS: dict[str, int] = {
    "halfling": 2,
    "elf": 1,
    "dwarf": 0,
    "human": 0,
}

# Weights for trap type selection (trap_door excluded from max depth)
TRAP_WEIGHTS: dict[TrapType, int] = {
    TrapType.PIT: 30,
    TrapType.SPIKE: 25,
    TrapType.POISON_DART: 20,
    TrapType.ALARM: 15,
    TrapType.TRAP_DOOR: 10,
}


@dataclass
class TrapResult:
    """Outcome of triggering a trap."""
    damage: int = 0
    message: str = ""
    poison: bool = False
    poison_dice: str = ""
    poison_turns: int = 0
    alert_all: bool = False
    fall_through: bool = False


def check_detection(character, trap: Trap) -> bool:
    """Roll a passive perception check: d20 + WIS mod + class + race >= DC."""
    from dreagoth.character.character import Character
    wis_mod = Character.ability_modifier(character.wisdom)
    class_bonus = CLASS_DETECT_BONUS.get(character.char_class, 0)
    race_bonus = RACE_DETECT_BONUS.get(character.race, 0)
    roll = roll_dice("1d20")
    total = roll + wis_mod + class_bonus + race_bonus
    return total >= trap.difficulty


def resolve_trap(trap: Trap, depth: int) -> TrapResult:
    """Resolve a triggered trap and return the result."""
    result = TrapResult()

    if trap.trap_type == TrapType.PIT:
        result.damage = max(1, roll_dice("1d6") + depth // 2)
        result.fall_through = True
        result.message = "The floor gives way beneath you and you plummet down!"

    elif trap.trap_type == TrapType.SPIKE:
        result.damage = max(1, roll_dice("1d8") + depth // 2)
        result.message = "Sharp spikes shoot up from the floor!"

    elif trap.trap_type == TrapType.POISON_DART:
        result.damage = max(1, roll_dice("1d4"))
        result.poison = True
        result.poison_dice = "1d2"
        result.poison_turns = 5
        result.message = "A dart flies from the wall, its tip glistening with poison!"

    elif trap.trap_type == TrapType.ALARM:
        result.damage = 0
        result.alert_all = True
        result.message = "A tripwire snaps and a loud gong rings through the corridors!"

    elif trap.trap_type == TrapType.TRAP_DOOR:
        result.damage = max(1, roll_dice("1d6") + depth // 2)
        result.fall_through = True
        result.message = "The floor opens and you plummet into darkness!"

    return result


# Display names for trap types
TRAP_NAMES: dict[TrapType, str] = {
    TrapType.PIT: "pit trap",
    TrapType.SPIKE: "spike trap",
    TrapType.POISON_DART: "poison dart trap",
    TrapType.ALARM: "alarm trap",
    TrapType.TRAP_DOOR: "trap door",
}
