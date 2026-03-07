"""Spell system — templates, slots, buffs, and SpellDB singleton."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# Spell slots per character level (index 0 = level 1).
# Each row is [level_1_slots, level_2_slots, level_3_slots].
MAGE_SLOTS: list[list[int]] = [
    [1, 0, 0],  # char level 1
    [2, 0, 0],  # char level 2
    [2, 1, 0],  # char level 3
    [3, 1, 0],  # char level 4
    [3, 2, 0],  # char level 5
    [3, 2, 1],  # char level 6
    [4, 2, 1],  # char level 7
    [4, 3, 1],  # char level 8
    [4, 3, 2],  # char level 9
    [4, 3, 2],  # char level 10
]

CLERIC_SLOTS: list[list[int]] = [
    [1, 0, 0],  # char level 1
    [2, 0, 0],  # char level 2
    [2, 1, 0],  # char level 3
    [2, 1, 0],  # char level 4
    [3, 2, 0],  # char level 5
    [3, 2, 1],  # char level 6
    [3, 2, 1],  # char level 7
    [3, 3, 1],  # char level 8
    [4, 3, 2],  # char level 9
    [4, 3, 2],  # char level 10
]


@dataclass
class SpellTemplate:
    """Static spell definition loaded from JSON."""
    id: str
    name: str
    spell_class: str  # "mage" or "cleric"
    level: int  # 1-3
    type: str  # combat_damage, combat_heal, combat_buff, utility
    description: str = ""
    damage: str = ""
    heal: str = ""
    effect: str = ""  # ac, attack, flee, fov_extend, detect_magic, unlock
    value: int = 0
    duration: int | None = None  # None = until combat ends (buffs) or instant
    undead_only: bool = False


@dataclass
class ActiveBuff:
    """An active spell buff on the player."""
    spell_id: str
    effect: str  # ac, attack, flee, fov_extend, detect_magic, regen
    value: int
    remaining_turns: int | None  # None = until combat ends
    regen_dice: str = ""  # for regen buffs: dice rolled per turn


@dataclass
class SpellSlots:
    """Tracks spell slot usage for a character."""
    max_slots: list[int] = field(default_factory=lambda: [0, 0, 0])
    used_slots: list[int] = field(default_factory=lambda: [0, 0, 0])

    def available(self, spell_level: int) -> int:
        """Available slots at a given spell level (1-3)."""
        idx = spell_level - 1
        if idx < 0 or idx >= 3:
            return 0
        return self.max_slots[idx] - self.used_slots[idx]

    def use(self, spell_level: int) -> bool:
        """Use a slot. Returns False if none available."""
        if self.available(spell_level) <= 0:
            return False
        self.used_slots[spell_level - 1] += 1
        return True

    def rest(self) -> None:
        """Restore all spell slots."""
        self.used_slots = [0, 0, 0]

    def update_max(self, char_class: str, char_level: int) -> None:
        """Update max slots based on class and character level."""
        table = _slot_table(char_class)
        if table is None:
            self.max_slots = [0, 0, 0]
            return
        idx = min(char_level, len(table)) - 1
        self.max_slots = list(table[idx])

    def has_any(self) -> bool:
        """True if the character has any spell slots at all."""
        return any(m > 0 for m in self.max_slots)


def _slot_table(char_class: str) -> list[list[int]] | None:
    if char_class == "mage":
        return MAGE_SLOTS
    elif char_class == "cleric":
        return CLERIC_SLOTS
    return None


class SpellDB:
    """Database of spell templates loaded from JSON."""

    def __init__(self) -> None:
        self.spells: dict[str, SpellTemplate] = {}
        self._by_class: dict[str, list[SpellTemplate]] = {}
        self._load()

    def _load(self) -> None:
        path = DATA_DIR / "spells.json"
        with open(path) as f:
            data = json.load(f)
        for s in data["spells"]:
            template = SpellTemplate(**s)
            self.spells[template.id] = template
            self._by_class.setdefault(template.spell_class, []).append(template)

    def get(self, spell_id: str) -> SpellTemplate | None:
        return self.spells.get(spell_id)

    def for_class(self, char_class: str) -> list[SpellTemplate]:
        return self._by_class.get(char_class, [])

    def castable(self, char_class: str, slots: SpellSlots) -> list[SpellTemplate]:
        """Spells the character can cast right now (has slots for)."""
        return [
            s for s in self.for_class(char_class)
            if slots.available(s.level) > 0
        ]

    def combat_spells(self, char_class: str, slots: SpellSlots) -> list[SpellTemplate]:
        """Castable combat spells (damage, heal, buff)."""
        return [
            s for s in self.castable(char_class, slots)
            if s.type.startswith("combat_")
        ]

    def utility_spells(self, char_class: str, slots: SpellSlots) -> list[SpellTemplate]:
        """Castable utility spells."""
        return [
            s for s in self.castable(char_class, slots)
            if s.type == "utility"
        ]


# Singleton
spell_db = SpellDB()
