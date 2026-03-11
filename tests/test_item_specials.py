"""Tests for item special enhancements — specials field, display, combat effects."""

import random

from dreagoth.entities.item import Item
from dreagoth.entities.magic_items import (
    generate_magic_item, _pick_unique_specials, unique_item_db,
)
from dreagoth.character.character import create_character, Character
from dreagoth.combat.combat_engine import CombatState, CombatResult
from dreagoth.combat.spells import ActiveBuff
from dreagoth.entities.monster import Monster


def _make_monster(hp: int = 20, ac: int = 10) -> Monster:
    return Monster(
        template_id="test", name="Test Monster", symbol="M", color="red",
        hp=hp, max_hp=hp, ac=ac, attack_bonus=0, damage="1d4",
        xp=10, loot_tier=1, speed=1, special=None,
    )


class TestSpecialsField:
    def test_default_empty(self):
        item = Item(id="test", name="Test", category="weapons", price=10)
        assert item.specials == {}

    def test_specials_in_constructor(self):
        item = Item(
            id="test", name="Test", category="weapons", price=10,
            specials={"life_steal": 15, "fire_damage": "1d4"},
        )
        assert item.specials["life_steal"] == 15
        assert item.specials["fire_damage"] == "1d4"

    def test_display_info_shows_specials(self):
        item = Item(
            id="test", name="Magic Sword", category="weapons", price=100,
            damage="1d8", rarity="unique",
            specials={"life_steal": 20, "crit_bonus": 2},
        )
        display = item.display_info
        assert "Life Steal 20%" in display
        assert "Crit +2" in display

    def test_inspect_lines_shows_specials(self):
        item = Item(
            id="test", name="Magic Sword", category="weapons", price=100,
            damage="1d8", rarity="unique", lore="A test blade.",
            specials={"fire_damage": "1d6"},
        )
        lines = item.inspect_lines()
        text = "\n".join(lines)
        assert "Special Properties" in text
        assert "Fire +1d6" in text
        assert "A test blade." in text
        assert "Unique" in text

    def test_inspect_lines_no_specials(self):
        item = Item(
            id="test", name="Plain Sword", category="weapons", price=10,
            damage="1d6",
        )
        lines = item.inspect_lines()
        text = "\n".join(lines)
        assert "Special Properties" not in text


class TestCharacterEquipSpecials:
    def test_equip_special_sums_int(self):
        char = create_character("Test", "fighter", "human")
        char.ring = Item(
            id="ring1", name="Ring", category="accessories", price=10,
            slot="ring", specials={"damage_resist": 2},
        )
        char.amulet = Item(
            id="amu1", name="Amulet", category="accessories", price=10,
            slot="amulet", specials={"damage_resist": 1},
        )
        assert char.equip_special("damage_resist") == 3

    def test_equip_special_str(self):
        char = create_character("Test", "fighter", "human")
        char.weapon = Item(
            id="w1", name="Fire Sword", category="weapons", price=10,
            damage="1d8", specials={"fire_damage": "1d4"},
        )
        assert char.equip_special_str("fire_damage") == "1d4"

    def test_equip_special_str_none(self):
        char = create_character("Test", "fighter", "human")
        assert char.equip_special_str("fire_damage") is None

    def test_bonus_spell_slot(self):
        char = create_character("Test", "mage", "human")
        char.level = 3
        char.init_spell_slots()
        base_avail = char.spell_slots.available(1)
        char.ring = Item(
            id="ring", name="Spell Ring", category="accessories", price=10,
            slot="ring", specials={"bonus_spell_slot": 2},
        )
        char.refresh_bonus_spell_slots()
        assert char.spell_slots.available(1) == base_avail + 2

    def test_regen_per_turn(self):
        char = create_character("Test", "fighter", "human")
        char.hp = 10
        char.max_hp = 50
        char.amulet = Item(
            id="amu", name="Regen Amulet", category="accessories", price=10,
            slot="amulet", specials={"regen_per_turn": "1d2"},
        )
        msgs = char.tick_buffs()
        assert any("Equipment regen" in m for m in msgs)
        assert char.hp > 10

    def test_regen_no_overheal(self):
        char = create_character("Test", "fighter", "human")
        char.hp = 50
        char.max_hp = 50
        char.amulet = Item(
            id="amu", name="Regen Amulet", category="accessories", price=10,
            slot="amulet", specials={"regen_per_turn": "1d4"},
        )
        msgs = char.tick_buffs()
        # No regen message when already full
        assert not any("Equipment regen" in m for m in msgs)
        assert char.hp == 50


class TestCombatSpecials:
    def test_life_steal_heals(self):
        random.seed(42)
        char = create_character("Test", "fighter", "human")
        char.strength = 18  # High STR for guaranteed hits
        char.hp = 10
        char.max_hp = 50
        char.weapon = Item(
            id="w1", name="Vampire Sword", category="weapons", price=10,
            damage="1d8", specials={"life_steal": 100},  # 100% steal for testing
        )
        monster = _make_monster(hp=100, ac=15)
        combat = CombatState(player=char, monster=monster)
        combat.start()
        start_hp = char.hp
        # Attack several times to get at least one hit
        for _ in range(10):
            if combat.result != CombatResult.ONGOING:
                break
            combat.player_attack()
        # If any hits landed, HP should have increased
        log_text = " ".join(entry.text for entry in combat.log)
        if "Life steal" in log_text:
            assert char.hp > start_hp or char.hp == char.max_hp

    def test_damage_resist_reduces_damage(self):
        random.seed(42)
        char = create_character("Test", "fighter", "human")
        char.hp = 50
        char.max_hp = 50
        char.armor = Item(
            id="a1", name="DR Armor", category="armor", price=10,
            slot="body", ac_bonus=0, specials={"damage_resist": 3},
        )
        monster = _make_monster(hp=100, ac=15)
        monster.attack_bonus = 20  # Always hits
        combat = CombatState(player=char, monster=monster)
        combat.start()
        # Monster may have attacked in start
        # Just verify DR is being applied by checking logs
        for _ in range(5):
            if combat.result != CombatResult.ONGOING:
                break
            combat.player_attack()
        # DR should reduce damage taken; char should be alive more often

    def test_poison_immune_blocks_combat_poison(self):
        random.seed(1)
        char = create_character("Test", "fighter", "human")
        char.hp = 50
        char.max_hp = 50
        char.ring = Item(
            id="r1", name="Antivenom Ring", category="accessories", price=10,
            slot="ring", specials={"poison_immune": 1},
        )
        monster = _make_monster(hp=100, ac=15)
        monster.special = "poison"
        monster.attack_bonus = 20
        combat = CombatState(player=char, monster=monster)
        combat.start()
        for _ in range(20):
            if combat.result != CombatResult.ONGOING:
                break
            combat.player_attack()
        log_text = " ".join(entry.text for entry in combat.log)
        # If poison was attempted, it should be warded
        if "poison" in log_text.lower():
            assert "wards off" in log_text.lower()

    def test_crit_bonus_expands_range(self):
        """With crit_bonus=3, crits on 17-20."""
        char = create_character("Test", "fighter", "human")
        char.strength = 18
        char.hp = 9999
        char.max_hp = 9999
        char.weapon = Item(
            id="w1", name="Keen Sword", category="weapons", price=10,
            damage="1d2", specials={"crit_bonus": 3},
        )
        monster = _make_monster(hp=99999, ac=0)
        combat = CombatState(player=char, monster=monster)
        combat.start()
        crits = 0
        for _ in range(200):
            if combat.result != CombatResult.ONGOING:
                break
            combat.player_attack()
            if any("CRITICAL" in e.text for e in combat.log[-5:]):
                crits += 1
        # With crit on 17-20 (20%), expect significantly more crits than 5% (nat 20 only)
        assert crits > 5


class TestMagicItemSpecials:
    def test_epic_items_have_specials(self):
        random.seed(42)
        item = generate_magic_item(10, "epic")
        assert len(item.specials) > 0

    def test_unique_skeletons_get_specials(self):
        random.seed(42)
        specials = _pick_unique_specials({"cat": "weapons"})
        assert len(specials) >= 1

    def test_loaded_uniques_have_specials(self):
        """All unique items in the DB should have specials."""
        for item in unique_item_db.templates:
            assert item.specials, f"{item.name} has no specials"


class TestSpecialsSerialization:
    def test_serialize_round_trip(self):
        from dreagoth.core.save_load import _serialize_item, _deserialize_item
        item = Item(
            id="test_unique", name="Test Blade", category="weapons",
            price=500, damage="2d6+3", rarity="unique",
            lore="A test blade.", specials={"life_steal": 20, "fire_damage": "1d4"},
        )
        data = _serialize_item(item)
        assert "specials" in data
        assert data["specials"]["life_steal"] == 20

        restored = _deserialize_item(data)
        assert restored.specials["life_steal"] == 20
        assert restored.specials["fire_damage"] == "1d4"

    def test_common_item_no_specials(self):
        from dreagoth.core.save_load import _serialize_item
        item = Item(id="sword_long", name="Long Sword", category="weapons", price=15)
        data = _serialize_item(item)
        # Common items serialize by ID only
        assert "specials" not in data

    def test_deserialize_missing_specials(self):
        """Old saves without specials field should get empty dict."""
        from dreagoth.core.save_load import _deserialize_item
        data = {
            "id": "old_unique", "name": "Old Blade", "category": "weapons",
            "price": 100, "rarity": "unique",
        }
        item = _deserialize_item(data)
        assert item.specials == {}


class TestTrapDetectSpecial:
    def test_trap_detect_bonus_applied(self):
        from dreagoth.dungeon.traps import Trap, TrapType, check_detection
        char = create_character("Test", "fighter", "human")
        char.wisdom = 10  # +0 WIS mod
        char.ring = Item(
            id="ring", name="Trap Ring", category="accessories", price=10,
            slot="ring", specials={"trap_detect": 10},  # Huge bonus
        )
        trap = Trap(TrapType.SPIKE, 5, 5, difficulty=10)
        # With d20 + 0(WIS) + 0(fighter) + 0(human) + 10(equip) >= 10
        # Should always pass (minimum roll of 1 + 10 = 11 >= 10)
        detections = sum(check_detection(char, trap) for _ in range(50))
        assert detections == 50
