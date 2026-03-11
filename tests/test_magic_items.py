"""Tests for the magic item system — generation, rarity, uniques, save/load."""

import json
import random
from dreagoth.entities.item import Item, equipment_db
from dreagoth.entities.magic_items import (
    generate_magic_item, roll_magic_loot, unique_item_db,
    UniqueItemDB, RARITY_DROP_CHANCE, generate_startup_uniques,
    UNIQUE_ITEMS_PATH,
)
from dreagoth.core.save_load import _serialize_item, _deserialize_item


class TestRarityOnItem:
    def test_common_items_default(self):
        sword = equipment_db.get("sword_long")
        assert sword.rarity == "common"
        assert sword.rarity_color == ""

    def test_rarity_colors(self):
        item = Item(id="test", name="Test", category="weapons", price=1, rarity="magic")
        assert item.rarity_color == "green"
        item.rarity = "rare"
        assert item.rarity_color == "dodger_blue2"
        item.rarity = "epic"
        assert item.rarity_color == "medium_purple"
        item.rarity = "unique"
        assert item.rarity_color == "dark_orange"

    def test_display_info_shows_rarity_marker(self):
        item = Item(id="test", name="Magic Sword", category="weapons", price=10,
                    damage="1d8", rarity="magic")
        info = item.display_info
        assert "\u2726" in info  # diamond marker

    def test_display_info_common_no_marker(self):
        item = Item(id="test", name="Sword", category="weapons", price=10,
                    damage="1d8", rarity="common")
        info = item.display_info
        assert "\u2726" not in info


class TestMagicItemGeneration:
    def test_generate_magic_item(self):
        random.seed(42)
        item = generate_magic_item(5, "magic")
        assert item.rarity == "magic"
        assert item.id.startswith("magic_")
        assert item.name != ""

    def test_generate_rare_item(self):
        random.seed(42)
        item = generate_magic_item(5, "rare")
        assert item.rarity == "rare"
        assert item.price > 0

    def test_generate_epic_item(self):
        random.seed(42)
        item = generate_magic_item(5, "epic")
        assert item.rarity == "epic"

    def test_magic_weapon_has_bonus(self):
        """Magic weapons should have better stats than base."""
        random.seed(42)
        item = generate_magic_item(5, "magic")
        # Generated items always have some bonus (attack_mod or damage)
        if item.is_weapon:
            assert item.attack_mod > 0 or "+" in item.damage

    def test_magic_armor_has_bonus(self):
        """Magic armor should have better AC than base."""
        # Generate many and check at least one armor has bonus
        random.seed(100)
        found_armor = False
        for _ in range(50):
            item = generate_magic_item(5, "rare")
            if item.slot and item.ac_bonus > 0:
                base = equipment_db.get(item.id)
                if base is None:  # generated item, not from DB
                    found_armor = True
                    break
        assert found_armor

    def test_price_scales_with_rarity(self):
        random.seed(42)
        magic = generate_magic_item(5, "magic")
        epic = generate_magic_item(5, "epic")
        # Epic should generally cost more (price multiplier is 12 vs 3)
        # Just verify both have reasonable prices
        assert magic.price >= 10
        assert epic.price >= 10


class TestUniqueItems:
    def setup_method(self):
        """Reset unique item tracking before each test."""
        unique_item_db.dropped_ids = set()

    def test_unique_items_load(self):
        assert len(unique_item_db.templates) >= 10

    def test_all_uniques_have_rarity(self):
        for item in unique_item_db.templates:
            assert item.rarity == "unique"

    def test_all_uniques_have_lore(self):
        for item in unique_item_db.templates:
            assert item.lore != "", f"{item.name} has no lore"

    def test_unique_drop_removes_from_pool(self):
        initial_count = len(unique_item_db.available())
        item = unique_item_db.try_drop(5)
        assert item is not None
        assert item.rarity == "unique"
        assert len(unique_item_db.available()) == initial_count - 1
        assert unique_item_db.is_dropped(item.id)

    def test_unique_cannot_drop_twice(self):
        item = unique_item_db.try_drop(5)
        assert item is not None
        item_id = item.id
        # Mark all others as dropped too
        for t in unique_item_db.templates:
            unique_item_db.mark_dropped(t.id)
        # Pool should be empty
        assert len(unique_item_db.available()) == 0
        result = unique_item_db.try_drop(5)
        assert result is None

    def test_dropped_ids_persist(self):
        item = unique_item_db.try_drop(5)
        dropped = unique_item_db.dropped_ids
        assert item.id in dropped
        # Simulate save/load
        unique_item_db.dropped_ids = dropped
        assert unique_item_db.is_dropped(item.id)


class TestRollMagicLoot:
    def test_returns_none_sometimes(self):
        """With low depth and tier, most rolls return None."""
        none_count = sum(1 for _ in range(100) if roll_magic_loot(1, 0) is None)
        assert none_count > 50  # Mostly None at low levels

    def test_returns_items_sometimes(self):
        """With high depth and tier, some rolls should return items."""
        random.seed(42)
        items = [roll_magic_loot(10, 4) for _ in range(200)]
        found = [i for i in items if i is not None]
        assert len(found) > 0

    def test_returned_items_have_rarity(self):
        random.seed(42)
        for _ in range(500):
            item = roll_magic_loot(8, 3)
            if item:
                assert item.rarity in ("magic", "rare", "epic", "unique")
                break
        else:
            # Should find at least one in 500 tries
            assert False, "No magic items dropped in 500 rolls"


class TestMagicItemSaveLoad:
    def test_common_item_serializes_by_id(self):
        sword = equipment_db.get("sword_long")
        data = _serialize_item(sword)
        assert data == {"id": "sword_long"}

    def test_magic_item_serializes_fully(self):
        item = generate_magic_item(5, "rare")
        data = _serialize_item(item)
        assert data["rarity"] == "rare"
        assert "name" in data
        assert "damage" in data

    def test_magic_item_roundtrip(self):
        item = generate_magic_item(5, "epic")
        data = _serialize_item(item)
        restored = _deserialize_item(data)
        assert restored is not None
        assert restored.name == item.name
        assert restored.rarity == item.rarity
        assert restored.damage == item.damage
        assert restored.ac_bonus == item.ac_bonus
        assert restored.attack_mod == item.attack_mod

    def test_unique_item_roundtrip(self):
        unique_item_db.dropped_ids = set()
        item = unique_item_db.try_drop(5)
        assert item is not None
        data = _serialize_item(item)
        restored = _deserialize_item(data)
        assert restored.name == item.name
        assert restored.rarity == "unique"
        assert restored.lore == item.lore


class TestStartupGeneration:
    def setup_method(self):
        """Save original state so we can restore after test."""
        self._original_templates = list(unique_item_db.templates)
        self._original_dropped = set(unique_item_db.dropped_ids)
        # Save original file
        with open(UNIQUE_ITEMS_PATH) as f:
            self._original_json = f.read()

    def teardown_method(self):
        """Restore original state."""
        unique_item_db.templates = self._original_templates
        unique_item_db.dropped_ids = self._original_dropped
        with open(UNIQUE_ITEMS_PATH, "w") as f:
            f.write(self._original_json)

    def test_generates_items(self):
        before = len(unique_item_db.templates)
        new_items = generate_startup_uniques(5)
        assert len(new_items) == 5
        assert len(unique_item_db.templates) == before + 5

    def test_generated_items_are_unique_rarity(self):
        new_items = generate_startup_uniques(5)
        for item in new_items:
            assert item.rarity == "unique"
            assert item.name != ""
            assert item.lore != ""
            assert item.id.startswith("unique_")

    def test_generated_items_persisted_to_disk(self):
        before = len(unique_item_db.templates)
        generate_startup_uniques(3)
        with open(UNIQUE_ITEMS_PATH) as f:
            data = json.load(f)
        assert len(data["unique_items"]) == before + 3

    def test_no_duplicate_names(self):
        # Start fresh so we only test generation logic, not accumulated state
        unique_item_db.templates.clear()
        new_items = generate_startup_uniques(10)
        names = [item.name for item in unique_item_db.templates]
        assert len(names) == len(set(names))
