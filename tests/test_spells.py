"""Tests for the spell system — SpellDB, SpellSlots, casting mechanics."""

from dreagoth.combat.spells import (
    SpellDB, SpellSlots, SpellTemplate, ActiveBuff,
    spell_db, MAGE_SLOTS, CLERIC_SLOTS,
)
from dreagoth.character.character import Character, create_character
from dreagoth.combat.combat_engine import CombatState, CombatResult
from dreagoth.entities.monster import monster_db


class TestSpellDB:
    def test_loads_spells(self):
        assert len(spell_db.spells) == 12

    def test_mage_spells(self):
        mage_spells = spell_db.for_class("mage")
        assert len(mage_spells) == 6
        names = {s.name for s in mage_spells}
        assert "Magic Missile" in names
        assert "Fireball" in names

    def test_cleric_spells(self):
        cleric_spells = spell_db.for_class("cleric")
        assert len(cleric_spells) == 6
        names = {s.name for s in cleric_spells}
        assert "Cure Wounds" in names
        assert "Turn Undead" in names

    def test_fighter_has_no_spells(self):
        assert spell_db.for_class("fighter") == []

    def test_get_by_id(self):
        mm = spell_db.get("magic_missile")
        assert mm is not None
        assert mm.name == "Magic Missile"
        assert mm.type == "combat_damage"
        assert mm.damage == "1d4+1"

    def test_get_nonexistent(self):
        assert spell_db.get("nonexistent") is None


class TestSpellSlots:
    def test_initial_empty(self):
        slots = SpellSlots()
        assert slots.available(1) == 0
        assert not slots.has_any()

    def test_mage_level_1(self):
        slots = SpellSlots()
        slots.update_max("mage", 1)
        assert slots.max_slots == [1, 0, 0]
        assert slots.available(1) == 1
        assert slots.available(2) == 0
        assert slots.has_any()

    def test_cleric_level_6(self):
        slots = SpellSlots()
        slots.update_max("cleric", 6)
        assert slots.max_slots == [3, 2, 1]

    def test_use_and_rest(self):
        slots = SpellSlots()
        slots.update_max("mage", 3)
        assert slots.available(1) == 2
        assert slots.use(1)
        assert slots.available(1) == 1
        assert slots.use(1)
        assert slots.available(1) == 0
        assert not slots.use(1)
        slots.rest()
        assert slots.available(1) == 2

    def test_fighter_has_no_slots(self):
        slots = SpellSlots()
        slots.update_max("fighter", 5)
        assert not slots.has_any()

    def test_castable_spells(self):
        slots = SpellSlots()
        slots.update_max("mage", 1)
        castable = spell_db.castable("mage", slots)
        # Level 1 mage should have level-1 mage spells
        assert all(s.level == 1 for s in castable)
        assert len(castable) >= 1


class TestSpellCasting:
    def _make_combat(self):
        char = create_character("Test", "mage", "human")
        char.hp = 20
        char.max_hp = 20
        monster = monster_db.spawn("rat", 5, 5)
        return CombatState(player=char, monster=monster)

    def test_combat_damage_spell(self):
        combat = self._make_combat()
        combat.start()
        combat.log.clear()
        spell = spell_db.get("magic_missile")
        initial_hp = combat.monster.hp
        combat.player_cast(spell)
        # Spell should have been cast (log entry exists)
        assert len(combat.log) >= 1
        assert "Magic Missile" in combat.log[0].text

    def test_combat_heal_spell(self):
        combat = self._make_combat()
        combat.player.char_class = "cleric"
        combat.player.spell_slots.update_max("cleric", 1)
        combat.start()
        combat.log.clear()
        combat.player.hp = 5
        spell = spell_db.get("cure_wounds")
        combat.player_cast(spell)
        assert any("heal" in entry.text.lower() for entry in combat.log)

    def test_no_slots_fails(self):
        combat = self._make_combat()
        combat.player.spell_slots = SpellSlots(max_slots=[0, 0, 0])
        combat.start()
        combat.log.clear()
        spell = spell_db.get("magic_missile")
        combat.player_cast(spell)
        assert any("No spell slots" in entry.text for entry in combat.log)


class TestBuffs:
    def test_buff_ac_bonus(self):
        char = create_character("Test", "mage", "human")
        base_ac = char.ac
        char.active_buffs.append(ActiveBuff("shield", "ac", 4, None))
        assert char.ac == base_ac + 4

    def test_buff_attack_bonus(self):
        char = create_character("Test", "cleric", "human")
        base_atk = char.attack_bonus
        char.active_buffs.append(ActiveBuff("bless", "attack", 2, None))
        assert char.attack_bonus == base_atk + 2

    def test_tick_buffs_decrements(self):
        char = create_character("Test", "mage", "human")
        char.active_buffs.append(ActiveBuff("light", "fov_extend", 4, 3))
        char.tick_buffs()
        assert len(char.active_buffs) == 1
        assert char.active_buffs[0].remaining_turns == 2
        char.tick_buffs()
        char.tick_buffs()
        assert len(char.active_buffs) == 0

    def test_clear_combat_buffs(self):
        char = create_character("Test", "mage", "human")
        char.active_buffs.append(ActiveBuff("shield", "ac", 4, None))  # combat
        char.active_buffs.append(ActiveBuff("light", "fov_extend", 4, 10))  # timed
        char.clear_combat_buffs()
        assert len(char.active_buffs) == 1
        assert char.active_buffs[0].spell_id == "light"
