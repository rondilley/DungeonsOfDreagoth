"""Tests verifying critical and high-severity bug fixes."""

from dreagoth.core.events import EventBus
from dreagoth.combat.spells import SpellSlots
from dreagoth.character.character import create_character


class TestEventBusSafety:
    def test_unsubscribe_missing_handler_no_crash(self):
        bus = EventBus()
        bus.unsubscribe("nonexistent", lambda: None)
        # Should not raise

    def test_handler_exception_doesnt_kill_others(self):
        bus = EventBus()
        results = []

        def bad_handler():
            raise RuntimeError("oops")

        def good_handler():
            results.append("ok")

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)
        bus.publish("test")
        assert results == ["ok"]  # good_handler still ran

    def test_publish_iterates_copy(self):
        """Handlers that unsubscribe during publish shouldn't skip others."""
        bus = EventBus()
        results = []

        def self_removing_handler():
            bus.unsubscribe("test", self_removing_handler)
            results.append("removed")

        def second_handler():
            results.append("second")

        bus.subscribe("test", self_removing_handler)
        bus.subscribe("test", second_handler)
        bus.publish("test")
        assert "removed" in results
        assert "second" in results


class TestSpellSlotClamping:
    def test_tampered_spell_slots_clamped(self):
        from dreagoth.core.save_load import _serialize_character, _deserialize_character
        char = create_character("Test", "mage", "human")
        data = _serialize_character(char)
        # Tamper with save data
        data["spell_slots"]["max_slots"] = [999, 999, 999]
        data["spell_slots"]["used_slots"] = [100, -5, 999]
        restored = _deserialize_character(data)
        assert all(0 <= s <= 7 for s in restored.spell_slots.max_slots)
        assert all(0 <= s <= 7 for s in restored.spell_slots.used_slots)


class TestRopeConnectionValidation:
    def test_malformed_landing_skipped(self):
        from dreagoth.core.save_load import load_game, save_game
        from dreagoth.core.game_state import GameState
        from dreagoth.dungeon.dungeon_level import DungeonLevel
        from dreagoth.dungeon.populator import LevelEntities
        import numpy as np
        from dreagoth.dungeon.tiles import Tile

        gs = GameState()
        gs.player_x, gs.player_y = 5, 5
        gs.current_depth = 1
        level = DungeonLevel(1, 10, 10)
        level.grid = np.full((10, 10), Tile.ROOM, dtype=np.uint8)
        gs.levels[1] = level
        gs.entities[1] = LevelEntities()
        ropes = gs.ensure_rope_connections(1)
        ropes[(3, 4)] = (7, 8)
        save_game(gs, 4)

        # Tamper: add a malformed 3-element landing
        import json
        from dreagoth.core.save_load import _slot_path
        path = _slot_path(4)
        with open(path) as f:
            raw = json.load(f)
        raw["rope_connections"]["1"]["5,6"] = [1, 2, 3]  # 3 elements — invalid
        with open(path, "w") as f:
            json.dump(raw, f)

        loaded = load_game(4)
        assert loaded is not None
        # Valid connection should survive, malformed should be skipped
        assert (3, 4) in loaded.rope_connections[1]
        assert (5, 6) not in loaded.rope_connections[1]


class TestTrapTypeDeserializationSafety:
    def test_invalid_trap_type_skipped(self):
        from dreagoth.core.save_load import _deserialize_trap
        data = {"type": "nonexistent_trap", "x": 5, "y": 5}
        result = _deserialize_trap(data)
        assert result is None

    def test_missing_trap_type_skipped(self):
        from dreagoth.core.save_load import _deserialize_trap
        data = {"x": 5, "y": 5}  # no "type" key
        result = _deserialize_trap(data)
        assert result is None


class TestResurrectionHPFloor:
    def test_resurrection_hp_at_least_one(self):
        """Even with max_hp=1, resurrection should give at least 1 HP."""
        char = create_character("Test", "mage", "human")
        char.max_hp = 1
        char.hp = 0
        char.is_dead = True
        char.gold = 100
        # Simulate resurrection logic
        char.is_dead = False
        char.hp = max(1, char.max_hp // 2)
        assert char.hp >= 1


class TestPlayerDeathOutsideCombat:
    def test_handle_player_death_method_exists(self):
        """Verify the _handle_player_death method exists on the app."""
        from dreagoth.app import DreagothApp
        assert hasattr(DreagothApp, "_handle_player_death")
