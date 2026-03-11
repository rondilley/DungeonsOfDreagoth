"""Tests for scroll items — consumable single-use spells for any class."""

from dreagoth.entities.item import Item, EquipmentDB, equipment_db
from dreagoth.character.character import create_character
from dreagoth.combat.spells import spell_db


class TestScrollItemsInDB:
    def test_scrolls_load(self):
        db = EquipmentDB()
        scrolls = db.by_category("scrolls")
        assert len(scrolls) == 8

    def test_scroll_has_spell_id(self):
        scroll = equipment_db.get("scroll_knock")
        assert scroll is not None
        assert scroll.spell_id == "knock"
        assert scroll.consumable is True
        assert scroll.is_scroll is True

    def test_all_scroll_spell_ids_valid(self):
        db = EquipmentDB()
        for scroll in db.by_category("scrolls"):
            assert scroll.spell_id, f"Scroll {scroll.id} has no spell_id"
            spell = spell_db.get(scroll.spell_id)
            assert spell is not None, f"Scroll {scroll.id} references unknown spell {scroll.spell_id}"

    def test_scrolls_are_consumable(self):
        db = EquipmentDB()
        for scroll in db.by_category("scrolls"):
            assert scroll.consumable, f"Scroll {scroll.id} is not consumable"
            assert scroll.is_scroll, f"Scroll {scroll.id} is_scroll is False"

    def test_non_scroll_has_no_spell_id(self):
        sword = equipment_db.get("sword_long")
        assert sword.spell_id == ""
        assert sword.is_scroll is False

    def test_display_info_shows_spell(self):
        scroll = equipment_db.get("scroll_fireball")
        info = scroll.display_info
        assert "spell: fireball" in info


class TestScrollMerchant:
    def test_magic_merchant_sells_scrolls(self):
        db = EquipmentDB()
        stock = db.for_merchant_tier("magic")
        scroll_ids = {i.id for i in stock if i.is_scroll}
        assert "scroll_knock" in scroll_ids
        assert "scroll_fireball" in scroll_ids

    def test_provisions_merchant_no_scrolls(self):
        db = EquipmentDB()
        stock = db.for_merchant_tier("provisions")
        assert not any(i.is_scroll for i in stock)


class TestScrollSaveLoad:
    def test_scroll_round_trip(self):
        from dreagoth.core.save_load import _serialize_item, _deserialize_item
        scroll = equipment_db.get("scroll_knock")
        # Common items serialize by ID only
        data = _serialize_item(scroll)
        assert data == {"id": "scroll_knock"}
        restored = _deserialize_item(data)
        assert restored.spell_id == "knock"
        assert restored.is_scroll is True


class TestScrollUsability:
    def test_fighter_can_hold_scroll(self):
        char = create_character("Fighter", "fighter", "human")
        scroll = equipment_db.get("scroll_knock")
        char.inventory.append(scroll)
        assert scroll in char.inventory

    def test_scroll_appears_in_consumable_list(self):
        char = create_character("Thief", "thief", "halfling")
        scroll = equipment_db.get("scroll_fireball")
        char.inventory.append(scroll)
        consumables = [i for i in char.inventory if i.is_consumable]
        assert scroll in consumables

    def test_scroll_is_not_equippable(self):
        scroll = equipment_db.get("scroll_knock")
        assert not scroll.is_equippable
