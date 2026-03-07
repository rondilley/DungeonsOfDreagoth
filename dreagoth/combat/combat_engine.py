"""Turn-based D&D-style combat engine."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto

from dreagoth.core.dice import d20
from dreagoth.character.character import Character
from dreagoth.entities.monster import Monster
from dreagoth.entities.item import roll_dice
from dreagoth.combat.spells import SpellTemplate, ActiveBuff


class CombatResult(Enum):
    ONGOING = auto()
    PLAYER_WIN = auto()
    PLAYER_FLED = auto()
    PLAYER_DEAD = auto()


class AttackOutcome(Enum):
    HIT = auto()
    MISS = auto()
    CRIT = auto()
    FUMBLE = auto()


@dataclass
class CombatLog:
    """One line of combat narration."""
    text: str
    style: str = ""


@dataclass
class CombatState:
    """Active combat encounter between player and a monster."""
    player: Character
    monster: Monster
    round: int = 0
    result: CombatResult = CombatResult.ONGOING
    log: list[CombatLog] = field(default_factory=list)
    player_initiative: int = 0
    monster_initiative: int = 0
    last_player_outcome: AttackOutcome | None = None

    def _add_log(self, text: str, style: str = "") -> None:
        self.log.append(CombatLog(text, style))

    def start(self) -> None:
        """Roll initiative and begin combat."""
        self.player_initiative = d20() + self.player.dex_mod
        self.monster_initiative = d20()
        self.round = 1
        self._add_log(
            f"A {self.monster.name} attacks!",
            style="bold bright_red",
        )
        if self.player_initiative >= self.monster_initiative:
            self._add_log("You act first.", style="bright_cyan")
        else:
            self._add_log(f"The {self.monster.name} acts first!", style="bright_red")
            self._monster_attack()

    @staticmethod
    def _hits(attack_roll: int, attack_bonus: int, target_ac: int) -> bool:
        """THAC0-style hit check (descending AC).

        To hit: d20 + attack_bonus >= 20 - target_AC.
        Lower target AC = harder to hit.
        """
        return attack_roll + attack_bonus >= 20 - target_ac

    def player_attack(self) -> None:
        """Player attacks the monster."""
        if self.result != CombatResult.ONGOING:
            return

        attack_roll = d20()
        is_crit = attack_roll == 20
        is_fumble = attack_roll == 1

        if is_fumble:
            self.last_player_outcome = AttackOutcome.FUMBLE
            self._add_log("You swing wildly and miss!", style="grey50")
        elif is_crit or self._hits(attack_roll, self.player.attack_bonus, self.monster.ac):
            damage = self.player.roll_damage()
            if is_crit:
                damage *= 2
                self.last_player_outcome = AttackOutcome.CRIT
                self._add_log(f"CRITICAL HIT!", style="bold bright_yellow")
            else:
                self.last_player_outcome = AttackOutcome.HIT
            self.monster.take_damage(damage)
            if self.monster.is_dead:
                self._add_log(
                    f"You slay the {self.monster.name}! (+{self.monster.xp} XP)",
                    style="bold bright_green",
                )
                self.result = CombatResult.PLAYER_WIN
                return
            else:
                self._add_log(
                    f"You hit the {self.monster.name} for {damage} damage. "
                    f"({self.monster.hp}/{self.monster.max_hp} HP)",
                )
        else:
            self.last_player_outcome = AttackOutcome.MISS
            self._add_log(f"You miss the {self.monster.name}.", style="grey50")

        # Monster's turn
        if self.result == CombatResult.ONGOING:
            self._monster_attack()

        self.round += 1

    def _monster_attack(self) -> None:
        """Monster attacks the player."""
        attack_roll = d20()
        is_crit = attack_roll == 20

        if attack_roll == 1:
            self._add_log(
                f"The {self.monster.name} fumbles its attack!",
                style="grey50",
            )
        elif is_crit or self._hits(attack_roll, self.monster.attack_bonus, self.player.ac):
            damage = self.monster.roll_damage()
            if is_crit:
                damage *= 2
                self._add_log(
                    f"The {self.monster.name} lands a CRITICAL HIT!",
                    style="bold bright_red",
                )

            # Special abilities
            if self.monster.special == "poison" and random.random() < 0.3:
                damage += roll_dice("1d4")
                self._add_log("Poison courses through your veins!", style="bright_green")
            elif self.monster.special == "paralyze" and random.random() < 0.2:
                self._add_log("You feel your limbs stiffening!", style="bright_cyan")
            elif self.monster.special == "drain" and random.random() < 0.15:
                self._add_log("You feel your life force draining!", style="bright_magenta")

            self.player.take_damage(damage)
            if self.player.is_dead:
                self._add_log(
                    f"The {self.monster.name} kills you!",
                    style="bold bright_red",
                )
                self.result = CombatResult.PLAYER_DEAD
            else:
                self._add_log(
                    f"The {self.monster.name} hits you for {damage} damage. "
                    f"({self.player.hp}/{self.player.max_hp} HP)",
                    style="bright_red",
                )
        else:
            self._add_log(
                f"The {self.monster.name} misses you.",
                style="grey50",
            )

    def player_cast(self, spell: SpellTemplate) -> None:
        """Player casts a spell during combat."""
        if self.result != CombatResult.ONGOING:
            return

        if not self.player.spell_slots.use(spell.level):
            self._add_log("No spell slots remaining!", style="bright_red")
            return

        self._add_log(f"You cast {spell.name}!", style="bold bright_cyan")

        if spell.type == "combat_damage":
            if spell.undead_only and self.monster.special != "undead":
                self._add_log(
                    f"{spell.name} has no effect on the {self.monster.name}.",
                    style="grey50",
                )
            else:
                damage = roll_dice(spell.damage)
                if spell.undead_only:
                    damage = int(damage * 1.5)  # Extra vs undead
                self.monster.take_damage(damage)
                if self.monster.is_dead:
                    self._add_log(
                        f"The {self.monster.name} is destroyed! (+{self.monster.xp} XP)",
                        style="bold bright_green",
                    )
                    self.result = CombatResult.PLAYER_WIN
                    return
                else:
                    self._add_log(
                        f"{spell.name} deals {damage} damage to the {self.monster.name}. "
                        f"({self.monster.hp}/{self.monster.max_hp} HP)",
                        style="bright_cyan",
                    )

        elif spell.type == "combat_heal":
            base = roll_dice(spell.heal)
            level_bonus = self.player.level - 1
            healed = self.player.heal(base + level_bonus)
            self._add_log(
                f"You heal {healed} HP. ({self.player.hp}/{self.player.max_hp} HP)",
                style="bright_green",
            )

        elif spell.type == "combat_buff":
            buff = ActiveBuff(
                spell_id=spell.id,
                effect=spell.effect,
                value=spell.value,
                remaining_turns=None,  # Lasts until combat ends
            )
            self.player.active_buffs.append(buff)
            effect_desc = {
                "ac": f"AC -{spell.value}",
                "attack": f"Attack +{spell.value}",
                "flee": f"Flee +{spell.value}",
            }.get(spell.effect, spell.effect)
            self._add_log(f"{spell.name}: {effect_desc}!", style="bright_cyan")

        # Monster retaliates
        if self.result == CombatResult.ONGOING:
            self._monster_attack()

        self.round += 1

    def player_use_item(self, item) -> bool:
        """Player uses a consumable item during combat. Returns True if used."""
        if self.result != CombatResult.ONGOING:
            return False

        result = self.player.use_item(item)
        if result is None:
            self._add_log("You can't use that!", style="bright_red")
            return False

        msg, _healed = result
        self._add_log(msg, style="bright_green")

        # Monster retaliates
        if self.result == CombatResult.ONGOING:
            self._monster_attack()

        self.round += 1
        return True

    def try_flee(self) -> bool:
        """Attempt to flee. Dex check vs monster speed."""
        flee_roll = d20() + self.player.dex_mod + self.player.buff_flee_bonus()
        if flee_roll >= 10:
            self._add_log("You flee from combat!", style="bright_yellow")
            self.result = CombatResult.PLAYER_FLED
            return True
        else:
            self._add_log("You fail to escape!", style="bright_red")
            self._monster_attack()
            self.round += 1
            return False
