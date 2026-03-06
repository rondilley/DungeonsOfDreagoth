"""Item and equipment data models."""

from __future__ import annotations

import json
import re
import random
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def parse_dice(dice_str: str) -> tuple[int, int, int]:
    """Parse '2d6+1' into (count, sides, bonus)."""
    m = re.match(r"(\d+)d(\d+)(?:\+(\d+))?", dice_str)
    if not m:
        return (0, 0, 0)
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def roll_dice(dice_str: str) -> int:
    """Roll a dice string like '2d6+1'."""
    count, sides, bonus = parse_dice(dice_str)
    if sides == 0:
        return bonus
    return sum(random.randint(1, sides) for _ in range(count)) + bonus


@dataclass
class Item:
    id: str
    name: str
    category: str
    price: int
    currency: str = "G"  # G=gold, S=silver, C=copper
    # Weapon fields
    damage: str = ""
    weapon_type: str = ""  # melee, ranged, ammo
    range: int = 0
    classes: list[str] = field(default_factory=list)
    # Armor fields
    ac_bonus: int = 0
    slot: str = ""  # body, shield, head
    # Consumable fields
    consumable: bool = False
    heal_dice: str = ""

    @property
    def gold_value(self) -> int:
        """Normalized value in gold pieces."""
        if self.currency == "G":
            return self.price
        elif self.currency == "S":
            return max(1, self.price // 10)
        else:
            return max(1, self.price // 100)

    @property
    def is_weapon(self) -> bool:
        return self.category == "weapons"

    @property
    def is_armor(self) -> bool:
        return self.category == "armor"

    @property
    def is_consumable(self) -> bool:
        return self.consumable

    @property
    def display_info(self) -> str:
        parts = [self.name]
        if self.damage:
            parts.append(f"[{self.damage}]")
        if self.heal_dice:
            parts.append(f"[heal {self.heal_dice}]")
        if self.ac_bonus:
            parts.append(f"AC+{self.ac_bonus}")
        parts.append(f"({self.price}{self.currency})")
        return " ".join(parts)


class EquipmentDB:
    """Database of all equipment loaded from JSON."""

    def __init__(self) -> None:
        self.items: dict[str, Item] = {}
        self._by_category: dict[str, list[Item]] = {}
        self._treasure_cache: dict[int, list[Item]] = {}
        self._load()

    def _load(self) -> None:
        path = DATA_DIR / "equipment.json"
        with open(path) as f:
            data = json.load(f)
        for category, items_data in data.items():
            self._by_category[category] = []
            for item_dict in items_data:
                item = Item(**item_dict)
                self.items[item.id] = item
                self._by_category[category].append(item)

    def get(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def by_category(self, category: str) -> list[Item]:
        return self._by_category.get(category, [])

    def weapons_for_class(self, char_class: str) -> list[Item]:
        return [i for i in self.by_category("weapons") if char_class in i.classes]

    def armor_for_class(self, char_class: str) -> list[Item]:
        return [i for i in self.by_category("armor") if char_class in i.classes]

    def for_merchant_tier(self, tier: str) -> list[Item]:
        """Get items a merchant of a given tier would sell."""
        if tier == "weapons":
            return self.by_category("weapons")
        elif tier == "provisions":
            items = (self.by_category("provisions")
                     + self.by_category("clothing")
                     + self.by_category("consumables"))
            return sorted(items, key=lambda i: i.gold_value)
        elif tier == "magic":
            # Magic merchants sell expensive misc items and holy items
            return [
                i for i in self.items.values()
                if i.category in ("misc",) and i.gold_value >= 5
            ]
        return []

    def random_treasure(self, tier: int) -> list[Item]:
        """Generate random loot based on dungeon tier (0-4)."""
        if tier not in self._treasure_cache:
            max_value = (tier + 1) * 20
            self._treasure_cache[tier] = [
                item for item in self.items.values()
                if item.gold_value <= max_value
            ]
        pool = self._treasure_cache[tier]
        if not pool:
            return []
        count = random.randint(0, min(2, tier + 1))
        return random.sample(pool, min(count, len(pool)))


# Singleton
equipment_db = EquipmentDB()
