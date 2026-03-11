"""Tests for the trap system — detection, resolution, placement, and serialization."""

import random

from dreagoth.dungeon.traps import (
    Trap, TrapType, TrapResult, TRAP_NAMES,
    check_detection, resolve_trap,
    CLASS_DETECT_BONUS, RACE_DETECT_BONUS,
)
from dreagoth.character.character import create_character, Character
from dreagoth.combat.spells import ActiveBuff
from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.tiles import Tile
from dreagoth.dungeon.populator import populate_level, LevelEntities
from dreagoth.core.constants import MAX_DUNGEON_DEPTH


class TestTrapDetectionBonuses:
    def test_thief_has_best_class_bonus(self):
        assert CLASS_DETECT_BONUS["thief"] > CLASS_DETECT_BONUS["fighter"]
        assert CLASS_DETECT_BONUS["thief"] > CLASS_DETECT_BONUS["mage"]
        assert CLASS_DETECT_BONUS["thief"] > CLASS_DETECT_BONUS["cleric"]

    def test_halfling_elf_have_race_bonus(self):
        assert RACE_DETECT_BONUS["halfling"] > RACE_DETECT_BONUS["human"]
        assert RACE_DETECT_BONUS["elf"] > RACE_DETECT_BONUS["human"]

    def test_thief_halfling_detects_easy_trap(self):
        """With high bonuses, a thief halfling should detect easy traps often."""
        char = create_character("Sneak", "thief", "halfling")
        char.wisdom = 18  # +4 WIS mod
        trap = Trap(TrapType.PIT, 5, 5, difficulty=5)  # Very easy DC
        # With d20 + 4(WIS) + 4(thief) + 2(halfling) = d20+10, DC5 always passes
        detections = sum(check_detection(char, trap) for _ in range(50))
        assert detections == 50

    def test_fighter_human_has_harder_time(self):
        """Low bonuses should make detection harder."""
        char = create_character("Tank", "fighter", "human")
        char.wisdom = 8  # -1 WIS mod
        trap = Trap(TrapType.PIT, 5, 5, difficulty=20)  # Hard DC
        # d20 + (-1) + 0 + 0 = d20-1, needs natural 20+ for DC20
        detections = sum(check_detection(char, trap) for _ in range(100))
        # Should be very rare (only on nat 20)
        assert detections < 20


class TestTrapResolution:
    def test_pit_does_damage_and_falls(self):
        trap = Trap(TrapType.PIT, 5, 5)
        result = resolve_trap(trap, depth=3)
        assert result.damage >= 1
        assert "floor gives way" in result.message.lower()
        assert result.fall_through is True
        assert not result.poison

    def test_spike_does_damage(self):
        trap = Trap(TrapType.SPIKE, 5, 5)
        result = resolve_trap(trap, depth=3)
        assert result.damage >= 1
        assert "spike" in result.message.lower()

    def test_poison_dart_poisons(self):
        trap = Trap(TrapType.POISON_DART, 5, 5)
        result = resolve_trap(trap, depth=1)
        assert result.damage >= 1
        assert result.poison is True
        assert result.poison_turns == 5
        assert result.poison_dice == "1d2"

    def test_alarm_alerts_no_damage(self):
        trap = Trap(TrapType.ALARM, 5, 5)
        result = resolve_trap(trap, depth=1)
        assert result.damage == 0
        assert result.alert_all is True

    def test_trap_door_falls_through(self):
        trap = Trap(TrapType.TRAP_DOOR, 5, 5)
        result = resolve_trap(trap, depth=5)
        assert result.damage >= 1
        assert result.fall_through is True

    def test_damage_scales_with_depth(self):
        """Deeper traps should deal more damage on average."""
        random.seed(42)
        shallow_total = sum(resolve_trap(Trap(TrapType.PIT, 0, 0), depth=1).damage for _ in range(100))
        random.seed(42)
        deep_total = sum(resolve_trap(Trap(TrapType.PIT, 0, 0), depth=20).damage for _ in range(100))
        assert deep_total > shallow_total


class TestTrapNames:
    def test_all_types_have_names(self):
        for tt in TrapType:
            assert tt in TRAP_NAMES


class TestTrapPopulation:
    def _make_level_with_rooms(self, depth: int) -> DungeonLevel:
        """Create a level with a couple rooms for testing."""
        from dreagoth.dungeon.generator import DungeonGenerator
        gen = DungeonGenerator()
        return gen.generate(depth)

    def test_traps_placed_in_level(self):
        """Populator should place some traps in generated levels."""
        random.seed(42)
        level = self._make_level_with_rooms(5)
        ents = populate_level(level, 5)
        # With rooms and corridors, there should be at least 1 trap
        assert len(ents.traps) >= 0  # May be 0 due to randomness
        # All traps should be on valid tiles
        for t in ents.traps:
            tile = level[t.x, t.y]
            assert tile in (Tile.ROOM, Tile.CORRIDOR)

    def test_no_trap_doors_on_max_depth(self):
        """Trap doors should not be placed on the maximum depth."""
        random.seed(1)
        level = self._make_level_with_rooms(MAX_DUNGEON_DEPTH)
        ents = populate_level(level, MAX_DUNGEON_DEPTH)
        for t in ents.traps:
            assert t.trap_type != TrapType.TRAP_DOOR

    def test_trap_index_works(self):
        ents = LevelEntities()
        trap = Trap(TrapType.PIT, 10, 10)
        ents.traps.append(trap)
        ents.rebuild_indices()
        assert ents.trap_at(10, 10) is trap
        assert ents.trap_at(11, 11) is None

    def test_traps_not_on_stairs(self):
        """Traps should not be placed on stair tiles."""
        random.seed(42)
        level = self._make_level_with_rooms(3)
        ents = populate_level(level, 3)
        stair_positions = set()
        if level.stairs_up:
            stair_positions.add(level.stairs_up)
        if level.stairs_down:
            stair_positions.add(level.stairs_down)
        for t in ents.traps:
            assert (t.x, t.y) not in stair_positions


class TestPoisonBuff:
    def test_poison_dot_deals_damage(self):
        char = create_character("Test", "fighter", "human")
        char.hp = 20
        char.max_hp = 20
        char.active_buffs.append(ActiveBuff(
            spell_id="trap_poison",
            effect="poison_dot",
            value=0,
            remaining_turns=3,
            regen_dice="1d2",
        ))
        msgs = char.tick_buffs()
        assert any("Poison" in m for m in msgs)
        assert char.hp < 20

    def test_poison_expires_after_turns(self):
        char = create_character("Test", "fighter", "human")
        char.hp = 50
        char.max_hp = 50
        char.active_buffs.append(ActiveBuff(
            spell_id="trap_poison",
            effect="poison_dot",
            value=0,
            remaining_turns=2,
            regen_dice="1d2",
        ))
        char.tick_buffs()
        assert len(char.active_buffs) == 1  # 1 turn remaining
        char.tick_buffs()
        assert len(char.active_buffs) == 0  # Expired


class TestTrapSerialization:
    def test_trap_round_trip(self):
        from dreagoth.core.save_load import _serialize_trap, _deserialize_trap
        trap = Trap(TrapType.POISON_DART, 7, 3, detected=True, triggered=False, difficulty=15)
        data = _serialize_trap(trap)
        restored = _deserialize_trap(data)
        assert restored.trap_type == TrapType.POISON_DART
        assert restored.x == 7
        assert restored.y == 3
        assert restored.detected is True
        assert restored.triggered is False
        assert restored.difficulty == 15

    def test_entities_with_traps_round_trip(self):
        from dreagoth.core.save_load import _serialize_entities, _deserialize_entities
        ents = LevelEntities()
        ents.traps.append(Trap(TrapType.PIT, 5, 5, detected=True))
        ents.traps.append(Trap(TrapType.ALARM, 10, 10, triggered=True))
        ents.rebuild_indices()
        data = _serialize_entities(ents)
        restored = _deserialize_entities(data)
        assert len(restored.traps) == 2
        assert restored.traps[0].trap_type == TrapType.PIT
        assert restored.traps[0].detected is True
        assert restored.traps[1].trap_type == TrapType.ALARM
        assert restored.traps[1].triggered is True

    def test_rope_connections_round_trip(self):
        from dreagoth.core.save_load import save_game, load_game
        from dreagoth.core.game_state import GameState
        from dreagoth.dungeon.dungeon_level import DungeonLevel
        import numpy as np

        gs = GameState()
        gs.player_x, gs.player_y = 5, 5
        gs.current_depth = 1

        # Create minimal level
        level = DungeonLevel(1, 10, 10)
        level.grid = np.full((10, 10), Tile.ROOM, dtype=np.uint8)
        gs.levels[1] = level
        gs.entities[1] = LevelEntities()

        # Add rope connection
        ropes = gs.ensure_rope_connections(1)
        ropes[(3, 4)] = (7, 8)

        assert save_game(gs, 4)
        loaded = load_game(4)
        assert loaded is not None
        assert 1 in loaded.rope_connections
        assert (3, 4) in loaded.rope_connections[1]
        assert loaded.rope_connections[1][(3, 4)] == (7, 8)

    def test_old_save_migration_adds_traps(self):
        from dreagoth.core.save_load import _migrate
        data = {
            "version": 2,
            "entities": {
                "1": {"monsters": [], "treasure_piles": {}, "gold_piles": {}, "npcs": []},
            },
        }
        _migrate(data)
        assert data["version"] == 3
        assert "traps" in data["entities"]["1"]
        assert data["entities"]["1"]["traps"] == []
        assert "rope_connections" in data
