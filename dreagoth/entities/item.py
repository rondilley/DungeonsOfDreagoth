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
    # Special enhancements (unique/epic items): key → value
    #   life_steal: int        — heal % of melee damage dealt
    #   crit_bonus: int        — added to crit chance (e.g. crit on 19-20)
    #   poison_immune: 1       — immune to poison effects
    #   damage_resist: int     — flat damage reduction on incoming hits
    #   bonus_fov: int         — extend field-of-view radius
    #   trap_detect: int       — bonus to trap detection rolls
    #   bonus_spell_slot: int  — extra spell slots (level 1)
    #   regen_per_turn: str    — passive HP regen dice each turn (e.g. "1d2")
    #   bonus_xp: int          — % bonus XP from kills
    #   fire_damage: str       — bonus fire damage dice on hit (e.g. "1d4")
    specials: dict[str, int | str] = field(default_factory=dict)

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

    # Human-readable labels for special enhancements
    _SPECIAL_LABELS: ClassVar[dict[str, str]] = {
        "life_steal": "Life Steal {v}%",
        "crit_bonus": "Crit +{v}",
        "poison_immune": "Poison Immune",
        "damage_resist": "DR {v}",
        "bonus_fov": "FOV +{v}",
        "trap_detect": "Trap Detect +{v}",
        "bonus_spell_slot": "Spell Slot +{v}",
        "regen_per_turn": "Regen {v}/turn",
        "bonus_xp": "XP +{v}%",
        "fire_damage": "Fire +{v}",
    }

    def _specials_short(self) -> list[str]:
        """Short display strings for each special enhancement."""
        result = []
        for key, val in self.specials.items():
            template = self._SPECIAL_LABELS.get(key, f"{key} {{}}")
            result.append(template.format(v=val))
        return result

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
        for sp in self._specials_short():
            parts.append(f"[{sp}]")
        parts.append(f"({self.price}{self.currency})")
        return " ".join(parts)

    @property
    def display_info(self) -> str:
        return self.display_info_at(1)

    def inspect_lines(self, level: int = 1) -> list[str]:
        """Return detailed multi-line description for the inspect screen."""
        lines: list[str] = []
        rcolor = self.rarity_color or "white"
        lines.append(f"[bold {rcolor}]{self.name}[/bold {rcolor}]")
        if self.rarity != "common":
            lines.append(f"  Rarity: [{rcolor}]{self.rarity.title()}[/{rcolor}]")
        if self.lore:
            lines.append(f"  [italic grey70]\"{self.lore}\"[/italic grey70]")
        lines.append("")

        # Base stats
        if self.damage:
            lines.append(f"  Damage: {self.damage}")
        if self.two_handed:
            lines.append("  Two-handed")
        if self.ac_bonus:
            lines.append(f"  AC bonus: -{self.ac_bonus}")
        if self.attack_mod:
            lines.append(f"  Attack bonus: +{self.attack_mod}")
        if self.classes:
            lines.append(f"  Classes: {', '.join(c.title() for c in self.classes)}")
        if self.slot:
            lines.append(f"  Slot: {self.slot.title()}")
        if self.heal_dice:
            lines.append(f"  Heals: {self._heal_str(level)}")
        if self.light_radius:
            lines.append(f"  Light: +{self.light_radius} FOV radius")

        # Special enhancements
        if self.specials:
            lines.append("")
            lines.append(f"  [bold bright_cyan]Special Properties:[/bold bright_cyan]")
            for key, val in self.specials.items():
                label = self._SPECIAL_LABELS.get(key, f"{key}: {{v}}")
                lines.append(f"    [bright_cyan]{label.format(v=val)}[/bright_cyan]")

        lines.append("")
        lines.append(f"  Value: {self.price} {self.currency}")
        return lines


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
