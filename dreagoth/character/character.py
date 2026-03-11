"""Player character — stats, inventory, equipment, leveling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar
from dreagoth.core.dice import ability_roll
from dreagoth.entities.item import Item, roll_dice
from dreagoth.combat.spells import SpellSlots, ActiveBuff


# XP thresholds for each level (index = level-1)
XP_TABLE = [
    0,           # level  1
    200,         # level  2
    600,         # level  3
    1_200,       # level  4
    2_400,       # level  5
    5_000,       # level  6
    10_000,      # level  7
    20_000,      # level  8
    40_000,      # level  9
    80_000,      # level 10
    150_000,     # level 11
    280_000,     # level 12
    500_000,     # level 13
    800_000,     # level 14
    1_200_000,   # level 15
    1_800_000,   # level 16
    2_500_000,   # level 17
    3_500_000,   # level 18
    5_000_000,   # level 19
    7_000_000,   # level 20
    9_500_000,   # level 21
    12_500_000,  # level 22
    16_000_000,  # level 23
    20_000_000,  # level 24
    25_000_000,  # level 25
]

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

    # Light source tracking (turns remaining on equipped light, 0 = not burning)
    light_remaining: int = 0

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

    def light_bonus(self) -> int:
        """FOV bonus from equipped light source (torch/lantern in shield slot)."""
        if self.shield and self.shield.is_light_source and self.light_remaining > 0:
            return self.shield.light_radius
        return 0

    def has_active_light(self) -> bool:
        """True if carrying an active light source (torch, lantern, or Light spell)."""
        if self.shield and self.shield.is_light_source and self.light_remaining > 0:
            return True
        return any(b.effect == "fov_extend" for b in self.active_buffs)

    def tick_buffs(self) -> list[str]:
        """Decrement turn-based buffs, process regen, remove expired ones.

        Returns list of log messages (e.g. regen healing).
        """
        messages: list[str] = []
        remaining = []
        for buff in self.active_buffs:
            if buff.effect == "regen" and buff.regen_dice:
                healed = self.heal(roll_dice(buff.regen_dice))
                if healed > 0:
                    messages.append(
                        f"Regen: +{healed} HP ({self.hp}/{self.max_hp})"
                    )
            elif buff.effect == "poison_dot" and buff.regen_dice:
                dmg = max(1, roll_dice(buff.regen_dice))
                actual = self.take_damage(dmg)
                if actual > 0:
                    messages.append(
                        f"Poison: -{actual} HP ({self.hp}/{self.max_hp})"
                    )
            if buff.remaining_turns is not None:
                buff.remaining_turns -= 1
                if buff.remaining_turns > 0:
                    remaining.append(buff)
            else:
                remaining.append(buff)
        self.active_buffs = remaining

        # Tick equipped light source
        if self.shield and self.shield.is_light_source and self.light_remaining > 0:
            self.light_remaining -= 1
            if self.light_remaining <= 0:
                self.light_remaining = 0
                name = self.shield.name
                self.shield = None
                messages.append(f"Your {name} has burned out!")
            elif self.light_remaining == 20:
                messages.append("Your light flickers — it won't last much longer!")

        return messages

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
                if self.shield.is_light_source and self.light_remaining > 0:
                    self.light_remaining = 0
                    msg += f" Your {self.shield.name} goes out."
                else:
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
                if field_name == "shield" and current.is_light_source and self.light_remaining > 0:
                    # A lit light source is consumed when put away
                    self.light_remaining = 0
                else:
                    self.inventory.append(current)
            self.inventory.remove(item)
            setattr(self, field_name, item)
            # Initialize light source burn timer
            if field_name == "shield" and item.is_light_source:
                self.light_remaining = item.light_duration
            msg = msg_template.format(name=item.name)
            if item.is_light_source:
                msg = f"You light the {item.name}. It illuminates the darkness!"
            return msg
        return f"You can't equip {item.name}."

    def use_item(self, item: Item) -> tuple[str, int] | None:
        """Use a consumable item. Returns (message, healed) or None.

        Healing scales with character level: base roll + level bonus.
        Food items apply a regen buff instead of instant healing.
        """
        if item not in self.inventory or not item.is_consumable:
            return None
        self.inventory.remove(item)
        # Regen items: apply heal-over-time buff
        if item.regen_dice and item.regen_turns:
            buff = ActiveBuff(
                spell_id=f"food_{item.id}",
                effect="regen",
                value=0,
                remaining_turns=item.regen_turns,
                regen_dice=item.regen_dice,
            )
            self.active_buffs.append(buff)
            msg = (f"You eat {item.name}. "
                   f"(regen {item.regen_dice}/turn for {item.regen_turns} turns)")
            return msg, 0
        # Instant healing items
        base = roll_dice(item.heal_dice)
        level_bonus = self.level - 1
        healed = self.heal(base + level_bonus)
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
