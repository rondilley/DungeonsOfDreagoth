"""Trap system — types, detection, and resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from dreagoth.entities.item import roll_dice


class TrapType(Enum):
    PIT = "pit"
    SPIKE = "spike"
    POISON_DART = "poison_dart"
    ALARM = "alarm"
    TRAP_DOOR = "trap_door"
    TELEPORT = "teleport"
    WEB_SNARE = "web_snare"
    SLEEP_GAS = "sleep_gas"
    MANA_DRAIN = "mana_drain"
    FLAME_JET = "flame_jet"
    WEAKENING_CURSE = "weakening_curse"


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

# Weights for trap type selection.
# Fall-through traps (pit, trap_door) are rare; excluded from max depth.
TRAP_WEIGHTS: dict[TrapType, int] = {
    TrapType.SPIKE: 20,
    TrapType.POISON_DART: 15,
    TrapType.ALARM: 12,
    TrapType.FLAME_JET: 15,
    TrapType.WEB_SNARE: 14,
    TrapType.SLEEP_GAS: 10,
    TrapType.TELEPORT: 8,
    TrapType.WEAKENING_CURSE: 8,
    TrapType.MANA_DRAIN: 6,
    TrapType.PIT: 5,
    TrapType.TRAP_DOOR: 3,
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
    teleport: bool = False
    held_turns: int = 0       # web snare: can't move for N turns
    sleep_turns: int = 0      # sleep gas: can't act for N turns
    mana_drain: int = 0       # spell slots drained
    str_penalty: int = 0      # weakening curse: temporary STR reduction
    str_penalty_turns: int = 0
    burn_scroll: bool = False  # flame jet: chance to burn a scroll


def check_detection(character, trap: Trap) -> bool:
    """Roll a passive perception check: d20 + WIS mod + class + race + equip >= DC."""
    from dreagoth.character.character import Character
    wis_mod = Character.ability_modifier(character.wisdom)
    class_bonus = CLASS_DETECT_BONUS.get(character.char_class, 0)
    race_bonus = RACE_DETECT_BONUS.get(character.race, 0)
    equip_bonus = character.equip_special("trap_detect") if hasattr(character, "equip_special") else 0
    roll = roll_dice("1d20")
    total = roll + wis_mod + class_bonus + race_bonus + equip_bonus
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

    elif trap.trap_type == TrapType.TELEPORT:
        result.damage = 0
        result.teleport = True
        result.message = "An arcane glyph flares beneath your feet — the world blurs!"

    elif trap.trap_type == TrapType.WEB_SNARE:
        result.damage = 0
        result.held_turns = roll_dice("1d3") + 1  # 2-4 turns
        result.message = "Thick spider silk entangles you!"

    elif trap.trap_type == TrapType.SLEEP_GAS:
        result.damage = 0
        result.sleep_turns = roll_dice("1d3") + 1  # 2-4 turns
        result.message = "A hiss of gas — your eyelids grow heavy..."

    elif trap.trap_type == TrapType.MANA_DRAIN:
        result.damage = 0
        result.mana_drain = roll_dice("1d2")  # drain 1-2 slots
        result.message = "A dark sigil pulses — you feel magical energy drain away!"

    elif trap.trap_type == TrapType.FLAME_JET:
        result.damage = max(1, roll_dice("2d6") + depth // 2)
        result.burn_scroll = True
        result.message = "Jets of flame blast from hidden nozzles in the walls!"

    elif trap.trap_type == TrapType.WEAKENING_CURSE:
        result.damage = 0
        result.str_penalty = roll_dice("1d3") + 1  # -2 to -4 STR
        result.str_penalty_turns = 20 + depth * 2
        result.message = "Dark energy radiates from a cursed tile — your muscles weaken!"

    return result


# Display names for trap types
TRAP_NAMES: dict[TrapType, str] = {
    TrapType.PIT: "pit trap",
    TrapType.SPIKE: "spike trap",
    TrapType.POISON_DART: "poison dart trap",
    TrapType.ALARM: "alarm trap",
    TrapType.TRAP_DOOR: "trap door",
    TrapType.TELEPORT: "teleportation rune",
    TrapType.WEB_SNARE: "web snare",
    TrapType.SLEEP_GAS: "gas vent",
    TrapType.MANA_DRAIN: "mana drain sigil",
    TrapType.FLAME_JET: "flame jet",
    TrapType.WEAKENING_CURSE: "weakening curse",
}
