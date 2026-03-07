"""Player character — stats, inventory, equipment, leveling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar
from dreagoth.core.dice import ability_roll
from dreagoth.entities.item import Item, roll_dice
from dreagoth.combat.spells import SpellSlots, ActiveBuff


# XP thresholds for each level (index = level-1)
XP_TABLE = [0, 200, 600, 1200, 2400, 5000, 10000, 20000, 40000, 80000]

CLASS_DATA = {
    "fighter": {
        "hit_die": "1d10",
        "base_ac": 10,
        "attack_bonus_per_level": 1,
        "description": "Master of weapons and armor",
    },
    "mage": {
        "hit_die": "1d4",
        "base_ac": 10,
        "attack_bonus_per_level": 0.5,
        "description": "Wielder of arcane magic",
    },
    "thief": {
        "hit_die": "1d6",
        "base_ac": 10,
        "attack_bonus_per_level": 0.75,
        "description": "Master of stealth and cunning",
    },
    "cleric": {
        "hit_die": "1d8",
        "base_ac": 10,
        "attack_bonus_per_level": 0.75,
        "description": "Holy warrior and healer",
    },
}

RACE_DATA = {
    "human": {"str_mod": 0, "dex_mod": 0, "con_mod": 0, "int_mod": 0, "wis_mod": 0, "cha_mod": 0, "description": "Versatile and adaptable"},
    "elf": {"str_mod": 0, "dex_mod": 1, "con_mod": -1, "int_mod": 1, "wis_mod": 0, "cha_mod": 0, "description": "Graceful and keen-sighted"},
    "dwarf": {"str_mod": 0, "dex_mod": 0, "con_mod": 2, "int_mod": 0, "wis_mod": 0, "cha_mod": -1, "description": "Stout and resilient"},
    "halfling": {"str_mod": -1, "dex_mod": 2, "con_mod": 0, "int_mod": 0, "wis_mod": 0, "cha_mod": 0, "description": "Small but lucky"},
}


@dataclass
class Character:
    name: str = "Adventurer"
    char_class: str = "fighter"
    race: str = "human"
    level: int = 1
    xp: int = 0

    # Abilities
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    # Vitals
    hp: int = 10
    max_hp: int = 10

    # Currency (in gold pieces)
    gold: int = 0

    # Inventory and equipment
    inventory: list[Item] = field(default_factory=list)
    weapon: Item | None = None
    armor: Item | None = None
    shield: Item | None = None
    helmet: Item | None = None
    boots: Item | None = None
    gloves: Item | None = None
    ring: Item | None = None
    amulet: Item | None = None

    # Spells
    spell_slots: SpellSlots = field(default_factory=SpellSlots)
    active_buffs: list[ActiveBuff] = field(default_factory=list)

    # Combat state
    is_dead: bool = False

    @staticmethod
    def ability_modifier(score: int) -> int:
        return (score - 10) // 2

    @property
    def str_mod(self) -> int:
        return self.ability_modifier(self.strength)

    @property
    def dex_mod(self) -> int:
        return self.ability_modifier(self.dexterity)

    @property
    def con_mod(self) -> int:
        return self.ability_modifier(self.constitution)

    # All equipment slots that contribute to AC / attack
    EQUIPMENT_SLOTS: ClassVar[tuple[str, ...]] = ("armor", "shield", "helmet", "boots", "gloves", "ring", "amulet")

    @property
    def ac(self) -> int:
        """Armor class (descending, classic D&D): 10 - dex_mod - equipment - buffs.

        Lower AC = harder to hit. Unarmored = 10, Plate + Shield = 2.
        """
        total = 10 - self.dex_mod
        for slot_name in self.EQUIPMENT_SLOTS:
            item = getattr(self, slot_name)
            if item:
                total -= item.ac_bonus
        total -= self.buff_ac_bonus()
        return total

    @property
    def attack_bonus(self) -> int:
        """Total attack bonus: level-based + strength modifier + equipment + buff."""
        class_data = CLASS_DATA[self.char_class]
        level_bonus = int(self.level * class_data["attack_bonus_per_level"])
        equip_bonus = sum(
            getattr(self, s).attack_mod
            for s in self.EQUIPMENT_SLOTS
            if getattr(self, s)
        )
        return level_bonus + self.str_mod + equip_bonus + self.buff_attack_bonus()

    @property
    def damage_dice(self) -> str:
        if self.weapon:
            return self.weapon.damage
        return "1d2"  # Unarmed

    @property
    def xp_to_next(self) -> int:
        if self.level >= len(XP_TABLE):
            return 999999
        return XP_TABLE[self.level] - self.xp

    def roll_damage(self) -> int:
        base = roll_dice(self.damage_dice)
        return max(1, base + self.str_mod)

    def take_damage(self, amount: int) -> int:
        """Apply damage, return actual damage taken."""
        actual = min(amount, self.hp)
        self.hp -= actual
        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
        return actual

    def heal(self, amount: int) -> int:
        """Heal HP, return actual amount healed."""
        actual = min(amount, self.max_hp - self.hp)
        self.hp += actual
        return actual

    def gain_xp(self, amount: int) -> bool:
        """Add XP, return True if leveled up."""
        self.xp += amount
        if self.level < len(XP_TABLE) and self.xp >= XP_TABLE[self.level]:
            self._level_up()
            return True
        return False

    def _level_up(self) -> None:
        self.level += 1
        hit_die = CLASS_DATA[self.char_class]["hit_die"]
        hp_gain = max(1, roll_dice(hit_die) + self.con_mod)
        self.max_hp += hp_gain
        self.hp += hp_gain
        self.spell_slots.update_max(self.char_class, self.level)

    def init_spell_slots(self) -> None:
        """Initialize spell slots based on class and level."""
        self.spell_slots.update_max(self.char_class, self.level)

    def buff_ac_bonus(self) -> int:
        return sum(b.value for b in self.active_buffs if b.effect == "ac")

    def buff_attack_bonus(self) -> int:
        return sum(b.value for b in self.active_buffs if b.effect == "attack")

    def buff_flee_bonus(self) -> int:
        return sum(b.value for b in self.active_buffs if b.effect == "flee")

    def fov_bonus(self) -> int:
        return sum(b.value for b in self.active_buffs if b.effect == "fov_extend")

    def tick_buffs(self) -> None:
        """Decrement turn-based buffs, remove expired ones."""
        remaining = []
        for buff in self.active_buffs:
            if buff.remaining_turns is not None:
                buff.remaining_turns -= 1
                if buff.remaining_turns > 0:
                    remaining.append(buff)
            else:
                remaining.append(buff)
        self.active_buffs = remaining

    def clear_combat_buffs(self) -> None:
        """Remove buffs that last until combat ends (duration=None)."""
        self.active_buffs = [
            b for b in self.active_buffs if b.remaining_turns is not None
        ]

    # Mapping from item slot value to (character field, equip verb)
    _SLOT_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "body": ("armor", "You don the {name}."),
        "shield": ("shield", "You ready the {name}."),
        "head": ("helmet", "You put on the {name}."),
        "boots": ("boots", "You pull on the {name}."),
        "gloves": ("gloves", "You slip on the {name}."),
        "ring": ("ring", "You slide on the {name}."),
        "amulet": ("amulet", "You clasp the {name}."),
    }

    def equip(self, item: Item) -> str | None:
        """Equip an item from inventory. Returns message or None."""
        if item not in self.inventory:
            return None
        if item.is_weapon:
            if item.classes and self.char_class not in item.classes:
                return f"A {self.char_class} cannot wield a {item.name}."
            if self.weapon:
                self.inventory.append(self.weapon)
            self.inventory.remove(item)
            self.weapon = item
            msg = f"You wield the {item.name}."
            # Two-handed weapons force shield unequip
            if item.two_handed and self.shield:
                self.inventory.append(self.shield)
                msg += f" You put away the {self.shield.name}."
                self.shield = None
            return msg
        if item.slot in self._SLOT_MAP:
            # Block shield equip if wielding a two-handed weapon
            if item.slot == "shield" and self.weapon and self.weapon.two_handed:
                return f"You can't use a shield with the {self.weapon.name} (two-handed)."
            if item.classes and self.char_class not in item.classes:
                return f"A {self.char_class} cannot wear {item.name}."
            field_name, msg_template = self._SLOT_MAP[item.slot]
            current = getattr(self, field_name)
            if current:
                self.inventory.append(current)
            self.inventory.remove(item)
            setattr(self, field_name, item)
            return msg_template.format(name=item.name)
        return f"You can't equip {item.name}."

    def use_item(self, item: Item) -> tuple[str, int] | None:
        """Use a consumable item. Returns (message, healed) or None.

        Healing scales with character level: base roll + level bonus.
        """
        if item not in self.inventory or not item.is_consumable:
            return None
        base = roll_dice(item.heal_dice)
        level_bonus = self.level - 1
        healed = self.heal(base + level_bonus)
        self.inventory.remove(item)
        msg = f"You use {item.name}, healing {healed} HP. ({self.hp}/{self.max_hp} HP)"
        return msg, healed

    def pickup(self, item: Item) -> str:
        """Add item to inventory."""
        self.inventory.append(item)
        return f"You pick up {item.name}."


def create_character(name: str, char_class: str, race: str) -> Character:
    """Roll a new character with random ability scores + racial mods."""
    race_mods = RACE_DATA[race]
    con = ability_roll() + race_mods["con_mod"]
    hit_die = CLASS_DATA[char_class]["hit_die"]
    hp = max(1, roll_dice(hit_die) + Character.ability_modifier(con))

    char = Character(
        name=name,
        char_class=char_class,
        race=race,
        strength=ability_roll() + race_mods["str_mod"],
        dexterity=ability_roll() + race_mods["dex_mod"],
        constitution=con,
        intelligence=ability_roll() + race_mods["int_mod"],
        wisdom=ability_roll() + race_mods["wis_mod"],
        charisma=ability_roll() + race_mods["cha_mod"],
        hp=hp,
        max_hp=hp,
        gold=roll_dice("3d6") * 10,
    )
    char.init_spell_slots()
    return char
