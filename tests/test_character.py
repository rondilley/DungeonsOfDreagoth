"""Tests for character, equipment, combat, and consumables systems."""

from dreagoth.character.character import Character, create_character, CLASS_DATA, RACE_DATA
from dreagoth.entities.item import Item, EquipmentDB, roll_dice, parse_dice, equipment_db
from dreagoth.entities.monster import MonsterDB
from dreagoth.combat.combat_engine import CombatState, CombatResult


class TestDiceParsing:
    def test_parse_simple(self):
        assert parse_dice("1d6") == (1, 6, 0)

    def test_parse_with_bonus(self):
        assert parse_dice("2d8+3") == (2, 8, 3)

    def test_roll_range(self):
        for _ in range(100):
            val = roll_dice("2d6")
            assert 2 <= val <= 12

    def test_roll_with_bonus(self):
        for _ in range(100):
            val = roll_dice("1d4+2")
            assert 3 <= val <= 6


class TestEquipmentDB:
    def test_loads(self):
        db = EquipmentDB()
        assert len(db.items) > 0

    def test_categories(self):
        db = EquipmentDB()
        assert len(db.by_category("weapons")) > 0
        assert len(db.by_category("armor")) > 0

    def test_get_item(self):
        db = EquipmentDB()
        sword = db.get("sword_long")
        assert sword is not None
        assert sword.name == "Long Sword"
        assert sword.damage == "1d8"

    def test_weapons_for_class(self):
        db = EquipmentDB()
        fighter_wpns = db.weapons_for_class("fighter")
        mage_wpns = db.weapons_for_class("mage")
        assert len(fighter_wpns) > len(mage_wpns)

    def test_random_treasure(self):
        db = EquipmentDB()
        # Should not crash even with edge cases
        db.random_treasure(0)
        db.random_treasure(4)


class TestCharacter:
    def test_create(self):
        char = create_character("Test", "fighter", "human")
        assert char.name == "Test"
        assert char.char_class == "fighter"
        assert char.level == 1
        assert char.hp > 0
        assert char.gold > 0

    def test_ability_modifier(self):
        assert Character.ability_modifier(10) == 0
        assert Character.ability_modifier(16) == 3
        assert Character.ability_modifier(8) == -1

    def test_equip_weapon(self):
        char = create_character("Test", "fighter", "human")
        sword = Item(id="test_sword", name="Test Sword", category="weapons",
                     price=10, damage="1d8", weapon_type="melee",
                     classes=["fighter"])
        char.inventory.append(sword)
        msg = char.equip(sword)
        assert char.weapon == sword
        assert sword not in char.inventory
        assert msg is not None

    def test_equip_armor(self):
        char = create_character("Test", "fighter", "human")
        armor = Item(id="test_armor", name="Test Armor", category="armor",
                     price=10, ac_bonus=5, slot="body",
                     classes=["fighter"])
        char.inventory.append(armor)
        char.equip(armor)
        assert char.armor == armor
        assert armor not in char.inventory

    def test_take_damage(self):
        char = create_character("Test", "fighter", "human")
        char.hp = 10
        char.max_hp = 10
        char.take_damage(3)
        assert char.hp == 7
        assert not char.is_dead

    def test_death(self):
        char = create_character("Test", "fighter", "human")
        char.hp = 5
        char.take_damage(10)
        assert char.hp == 0
        assert char.is_dead

    def test_heal(self):
        char = create_character("Test", "fighter", "human")
        char.max_hp = 20
        char.hp = 10
        healed = char.heal(5)
        assert healed == 5
        assert char.hp == 15

    def test_heal_capped(self):
        char = create_character("Test", "fighter", "human")
        char.max_hp = 20
        char.hp = 18
        healed = char.heal(10)
        assert healed == 2
        assert char.hp == 20

    def test_gain_xp_no_level(self):
        char = create_character("Test", "fighter", "human")
        char.xp = 0
        result = char.gain_xp(50)
        assert result is False
        assert char.level == 1

    def test_gain_xp_level_up(self):
        char = create_character("Test", "fighter", "human")
        char.xp = 0
        old_max_hp = char.max_hp
        result = char.gain_xp(250)
        assert result is True
        assert char.level == 2
        assert char.max_hp > old_max_hp

    def test_racial_mods(self):
        # Dwarf gets +2 CON
        scores = []
        for _ in range(50):
            char = create_character("Test", "fighter", "dwarf")
            scores.append(char.constitution)
        # Average should be higher than base (10.5 + 2)
        avg = sum(scores) / len(scores)
        assert avg > 10  # Very likely with +2 mod

    def test_all_classes(self):
        for cls in CLASS_DATA:
            char = create_character("Test", cls, "human")
            assert char.char_class == cls
            assert char.hp > 0

    def test_all_races(self):
        for race in RACE_DATA:
            char = create_character("Test", "fighter", race)
            assert char.race == race


class TestMonsterDB:
    def test_loads(self):
        db = MonsterDB()
        assert len(db.templates) == 14

    def test_spawn(self):
        db = MonsterDB()
        m = db.spawn("goblin", 5, 5)
        assert m.name == "Goblin"
        assert m.hp > 0
        assert m.x == 5 and m.y == 5

    def test_eligible_for_level(self):
        db = MonsterDB()
        l1 = db.eligible_for_level(1)
        l10 = db.eligible_for_level(10)
        # Level 1 should have basic monsters
        names_l1 = [t.name for t in l1]
        assert "Giant Rat" in names_l1
        assert "Minotaur" not in names_l1
        # Level 10 should have tough monsters
        names_l10 = [t.name for t in l10]
        assert "Minotaur" in names_l10

    def test_random_for_level(self):
        db = MonsterDB()
        m = db.random_for_level(1, 10, 10)
        assert m is not None
        assert m.hp > 0


class TestCombat:
    def _make_combatants(self):
        char = create_character("Hero", "fighter", "human")
        char.hp = 50
        char.max_hp = 50
        char.strength = 16

        from dreagoth.entities.monster import monster_db
        monster = monster_db.spawn("goblin", 5, 5)
        return char, monster

    def test_combat_starts(self):
        char, monster = self._make_combatants()
        combat = CombatState(player=char, monster=monster)
        combat.start()
        assert combat.round == 1
        assert len(combat.log) > 0

    def test_player_attack(self):
        char, monster = self._make_combatants()
        combat = CombatState(player=char, monster=monster)
        combat.start()
        combat.log.clear()
        combat.player_attack()
        assert len(combat.log) > 0

    def test_combat_resolves(self):
        """Fight until someone wins or dies."""
        char, monster = self._make_combatants()
        combat = CombatState(player=char, monster=monster)
        combat.start()
        for _ in range(100):
            if combat.result != CombatResult.ONGOING:
                break
            combat.player_attack()
        assert combat.result != CombatResult.ONGOING

    def test_flee(self):
        char, monster = self._make_combatants()
        combat = CombatState(player=char, monster=monster)
        combat.start()
        # Try fleeing multiple times
        for _ in range(20):
            if combat.result != CombatResult.ONGOING:
                break
            combat.try_flee()
        # Should eventually flee or die
        assert combat.result != CombatResult.ONGOING


class TestConsumables:
    def test_consumables_load_from_db(self):
        potion = equipment_db.get("potion_minor")
        assert potion is not None
        assert potion.consumable is True
        assert potion.heal_dice == "1d4+1"
        assert potion.is_consumable

    def test_all_consumables_present(self):
        ids = ["bandages", "potion_minor", "healing_herbs", "potion_healing", "potion_greater"]
        for item_id in ids:
            item = equipment_db.get(item_id)
            assert item is not None, f"Missing consumable: {item_id}"
            assert item.consumable is True

    def test_existing_items_not_consumable(self):
        sword = equipment_db.get("sword_long")
        assert sword is not None
        assert sword.consumable is False
        assert not sword.is_consumable

    def test_use_item_heals_and_removes(self):
        char = create_character("Test", "fighter", "human")
        char.max_hp = 20
        char.hp = 10
        potion = Item(id="potion_minor", name="Minor Healing Potion",
                      category="consumables", price=5,
                      consumable=True, heal_dice="1d4+1")
        char.inventory.append(potion)
        result = char.use_item(potion)
        assert result is not None
        msg, healed = result
        assert healed >= 2  # 1d4+1 min is 2
        assert healed <= 5  # 1d4+1 max is 5
        assert char.hp == 10 + healed
        assert potion not in char.inventory

    def test_use_item_non_consumable_returns_none(self):
        char = create_character("Test", "fighter", "human")
        sword = Item(id="sword_long", name="Long Sword", category="weapons",
                     price=15, damage="1d8", weapon_type="melee",
                     classes=["fighter"])
        char.inventory.append(sword)
        result = char.use_item(sword)
        assert result is None
        assert sword in char.inventory

    def test_heal_capped_at_max_hp(self):
        char = create_character("Test", "fighter", "human")
        char.max_hp = 20
        char.hp = 19
        potion = Item(id="potion_greater", name="Greater Healing Potion",
                      category="consumables", price=40,
                      consumable=True, heal_dice="3d4+3")
        char.inventory.append(potion)
        result = char.use_item(potion)
        assert result is not None
        _msg, healed = result
        assert char.hp == 20
        assert healed == 1

    def test_consumables_in_treasure_pool(self):
        """Consumables should appear in random treasure at appropriate tiers."""
        db = EquipmentDB()
        # Tier 0: max_value=20, bandages(2G) and minor potion(5G) should be in pool
        pool_ids = {item.id for item in db.items.values() if item.gold_value <= 20}
        assert "bandages" in pool_ids
        assert "potion_minor" in pool_ids

    def test_provisions_merchant_sells_consumables(self):
        db = EquipmentDB()
        stock = db.for_merchant_tier("provisions")
        stock_ids = {item.id for item in stock}
        assert "bandages" in stock_ids
        assert "potion_minor" in stock_ids

    def test_combat_player_use_item(self):
        char = create_character("Hero", "fighter", "human")
        char.hp = 20
        char.max_hp = 50
        potion = Item(id="potion_healing", name="Healing Potion",
                      category="consumables", price=15,
                      consumable=True, heal_dice="2d4+2")
        char.inventory.append(potion)

        from dreagoth.entities.monster import monster_db
        monster = monster_db.spawn("goblin", 5, 5)
        combat = CombatState(player=char, monster=monster)
        combat.start()
        combat.log.clear()
        old_round = combat.round

        used = combat.player_use_item(potion)
        assert used is True
        assert potion not in char.inventory
        assert combat.round == old_round + 1  # Round incremented
        assert len(combat.log) >= 2  # Heal msg + monster retaliation
        # First log entry should be the heal message
        assert "heal" in combat.log[0].text.lower()

    def test_display_info_shows_heal(self):
        potion = equipment_db.get("potion_minor")
        assert "[heal 1d4+1]" in potion.display_info


class TestRoomPrefetch:
    def test_parse_and_cache_rooms(self):
        from dreagoth.ai.dm import DungeonMaster
        from dreagoth.ai.cache import ai_cache

        dm_inst = DungeonMaster()
        rooms = [(0, "8x6"), (1, "5x4"), (2, "10x8")]
        text = (
            "Room #0: The damp stone walls glisten with moisture. "
            "A faint dripping echoes.\n"
            "Room #1: A small chamber littered with bones.\n"
            "Room #2: A vast hall with crumbling pillars stretching into darkness."
        )
        dm_inst._parse_and_cache_rooms(text, depth=99, rooms=rooms)

        # Each room should now be cached
        for rid, size in rooms:
            context = f"depth=99,room={rid},size={size}"
            cached = ai_cache.get("room_enter", context)
            assert cached is not None, f"Room #{rid} not cached"
            assert len(cached) > 10

    def test_parse_skips_unknown_room_ids(self):
        from dreagoth.ai.dm import DungeonMaster
        from dreagoth.ai.cache import ai_cache

        dm_inst = DungeonMaster()
        rooms = [(0, "5x5")]
        text = "Room #0: A room.\nRoom #999: Should be ignored."
        dm_inst._parse_and_cache_rooms(text, depth=98, rooms=rooms)

        context = f"depth=98,room=0,size=5x5"
        assert ai_cache.get("room_enter", context) is not None
        context_bad = f"depth=98,room=999,size=5x5"
        assert ai_cache.get("room_enter", context_bad) is None
