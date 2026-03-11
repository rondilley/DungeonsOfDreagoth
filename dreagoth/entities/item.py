"""Item and equipment data models."""

from __future__ import annotations

import json
import re
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

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
    # Armor / accessory fields
    ac_bonus: int = 0
    attack_mod: int = 0
    slot: str = ""  # body, shield, head, boots, gloves, ring, amulet
    # Weapon modifier
    two_handed: bool = False
    # Consumable fields
    consumable: bool = False
    heal_dice: str = ""
    regen_dice: str = ""   # heal-over-time per turn (e.g. "1d2")
    regen_turns: int = 0   # how many turns the regen lasts
    # Scroll: references a spell_id from spells.json (consumable, single-use)
    spell_id: str = ""
    # Light source fields
    light_radius: int = 0     # FOV bonus when equipped/active
    light_duration: int = 0   # turns until burnout (0 = permanent like lantern)
    # Rarity: common (white), magic (green), rare (blue), epic (purple), unique (orange)
    rarity: str = "common"
    lore: str = ""

    @property
    def gold_value(self) -> int:
        """Normalized value in gold pieces."""
        if self.currency == "G":
            return self.price
        elif self.currency == "S":
            return max(1, self.price // 10)
        else:
            return max(1, self.price // 100)

    RARITY_COLORS: ClassVar[dict[str, str]] = {
        "common": "",
        "magic": "green",
        "rare": "dodger_blue2",
        "epic": "medium_purple",
        "unique": "dark_orange",
    }

    @property
    def rarity_color(self) -> str:
        return self.RARITY_COLORS.get(self.rarity, "")

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
    def is_scroll(self) -> bool:
        return self.category == "scrolls" and bool(self.spell_id)

    @property
    def is_light_source(self) -> bool:
        return self.light_radius > 0

    @property
    def is_equippable(self) -> bool:
        """True if this item can be equipped in any slot."""
        return self.is_weapon or bool(self.slot)

    def _heal_str(self, level: int = 1) -> str:
        """Format heal dice with level scaling bonus."""
        if not self.heal_dice:
            return ""
        bonus = level - 1
        if bonus <= 0:
            return self.heal_dice
        # Parse existing bonus from dice string and add level bonus
        count, sides, base_bonus = parse_dice(self.heal_dice)
        total_bonus = base_bonus + bonus
        if total_bonus > 0:
            return f"{count}d{sides}+{total_bonus}"
        return f"{count}d{sides}"

    def display_info_at(self, level: int = 1) -> str:
        """Display info with heal values scaled to the given character level."""
        parts = [self.name]
        if self.rarity != "common":
            parts.insert(0, f"[{self.rarity_color}]\u2726[/{self.rarity_color}]")
        if self.two_handed:
            parts.append("[2H]")
        if self.damage:
            parts.append(f"[{self.damage}]")
        if self.heal_dice:
            parts.append(f"[heal {self._heal_str(level)}]")
        if self.regen_dice:
            parts.append(f"[regen {self.regen_dice}/turn x{self.regen_turns}]")
        if self.spell_id:
            parts.append(f"[spell: {self.spell_id}]")
        if self.light_radius:
            parts.append(f"[light +{self.light_radius}]")
        if self.ac_bonus:
            parts.append(f"AC-{self.ac_bonus}")
        if self.attack_mod:
            parts.append(f"Atk+{self.attack_mod}")
        parts.append(f"({self.price}{self.currency})")
        return " ".join(parts)

    @property
    def display_info(self) -> str:
        return self.display_info_at(1)


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
                     + self.by_category("consumables")
                     + self.by_category("misc"))
            return sorted(items, key=lambda i: i.gold_value)
        elif tier == "armor":
            return (self.by_category("armor")
                    + self.by_category("accessories"))
        elif tier == "magic":
            # Magic merchants sell accessories, scrolls, and expensive misc items
            return (self.by_category("accessories")
                    + self.by_category("scrolls")
                    + [i for i in self.items.values()
                       if i.category in ("misc",) and i.gold_value >= 5])
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
