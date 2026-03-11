"""Tests for save/load system — round-trip serialization."""

import pytest
import shutil
from pathlib import Path

from dreagoth.core.save_load import (
    save_game, load_game, list_saves, autosave,
    SAVE_DIR, _serialize_character, _deserialize_character,
    _serialize_level, _deserialize_level,
    _serialize_quest_log, _deserialize_quest_log,
)
from dreagoth.core.game_state import GameState
from dreagoth.character.character import create_character
from dreagoth.dungeon.generator import DungeonGenerator
from dreagoth.dungeon.populator import populate_level
from dreagoth.combat.spells import SpellSlots, ActiveBuff
from dreagoth.quest.quest import QuestLog, Quest, QuestType, QuestStatus, QuestReward


# Use a test-specific save dir
TEST_SAVE_DIR = SAVE_DIR.parent / "test_saves"


@pytest.fixture(autouse=True)
def clean_test_saves(monkeypatch):
    """Use a separate directory for test saves and clean up after."""
    import dreagoth.core.save_load as sl
    monkeypatch.setattr(sl, "SAVE_DIR", TEST_SAVE_DIR)
    yield
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)


class TestCharacterSerialization:
    def test_round_trip(self):
        char = create_character("Hero", "mage", "elf")
        char.gold = 100
        char.xp = 500
        data = _serialize_character(char)
        restored = _deserialize_character(data)
        assert restored.name == "Hero"
        assert restored.char_class == "mage"
        assert restored.race == "elf"
        assert restored.gold == 100
        assert restored.xp == 500

    def test_preserves_spell_slots(self):
        char = create_character("Wizard", "mage", "human")
        char.spell_slots.update_max("mage", 3)
        char.spell_slots.use(1)
        data = _serialize_character(char)
        restored = _deserialize_character(data)
        assert restored.spell_slots.max_slots == [2, 1, 0]
        assert restored.spell_slots.used_slots[0] == 1

    def test_preserves_buffs(self):
        char = create_character("Mage", "mage", "human")
        char.active_buffs.append(ActiveBuff("light", "fov_extend", 4, 10))
        data = _serialize_character(char)
        restored = _deserialize_character(data)
        assert len(restored.active_buffs) == 1
        assert restored.active_buffs[0].spell_id == "light"
        assert restored.active_buffs[0].remaining_turns == 10


class TestLevelSerialization:
    def test_round_trip(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        data = _serialize_level(level)
        restored = _deserialize_level(data)
        assert restored.depth == 1
        assert restored.width == level.width
        assert restored.height == level.height
        assert len(restored.rooms) == len(level.rooms)
        assert restored.stairs_up == level.stairs_up
        # Grid contents match
        assert (restored.grid == level.grid).all()


class TestQuestLogSerialization:
    def test_round_trip(self):
        ql = QuestLog()
        q = Quest(
            id="q1", name="Kill Rats", description="Kill 3 rats",
            quest_type=QuestType.KILL_MONSTERS, status=QuestStatus.ACTIVE,
            npc_id="captain", target_id="rat", target_count=3, progress=1,
            reward=QuestReward(gold=50, xp=100),
        )
        ql.add(q)
        data = _serialize_quest_log(ql)
        restored = _deserialize_quest_log(data)
        assert len(restored.quests) == 1
        rq = restored.quests[0]
        assert rq.name == "Kill Rats"
        assert rq.progress == 1
        assert rq.reward.gold == 50


class TestSaveLoad:
    def _make_game_state(self):
        gs = GameState()
        gs.player = create_character("SaveTest", "fighter", "dwarf")
        gs.quest_log = QuestLog()
        gen = DungeonGenerator(seed=99)
        level = gen.generate(1)
        gs.levels[1] = level
        gs.entities[1] = populate_level(level, 1)
        gs.current_depth = 1
        gs.player_x, gs.player_y = level.stairs_up
        gs.turn = 42
        gs.revealed[1] = {(5, 5), (6, 6)}
        return gs

    def test_save_and_load(self):
        gs = self._make_game_state()
        assert save_game(gs, 1)
        loaded = load_game(1)
        assert loaded is not None
        assert loaded.player.name == "SaveTest"
        assert loaded.turn == 42
        assert loaded.current_depth == 1
        assert (5, 5) in loaded.revealed[1]

    def test_load_empty_slot(self):
        assert load_game(4) is None

    def test_list_saves(self):
        gs = self._make_game_state()
        save_game(gs, 2)
        saves = list_saves()
        assert saves[2] is not None
        assert saves[2]["name"] == "SaveTest"
        assert saves[0] is None  # unused slot

    def test_autosave(self):
        gs = self._make_game_state()
        assert autosave(gs)
        loaded = load_game(0)
        assert loaded is not None
        assert loaded.player.name == "SaveTest"

    def test_overwrite_save(self):
        gs = self._make_game_state()
        save_game(gs, 1)
        gs.turn = 100
        save_game(gs, 1)
        loaded = load_game(1)
        assert loaded.turn == 100

    def test_multi_level_round_trip(self):
        """Save with 3 explored levels, verify all are restored."""
        gs = GameState()
        gs.player = create_character("Explorer", "thief", "halfling")
        gs.quest_log = QuestLog()
        gen = DungeonGenerator(seed=77)

        # Generate and populate 3 levels
        for depth in (1, 2, 3):
            level = gen.generate(depth)
            gs.levels[depth] = level
            gs.entities[depth] = populate_level(level, depth)
            gs.revealed[depth] = {(i, i) for i in range(5)}
            gs.visited_rooms[depth] = {0, 1}
            gs.opened_doors[depth] = {(10, 10)}

        # Simulate game state: player is on depth 2
        gs.current_depth = 2
        gs.player_x, gs.player_y = gs.levels[2].stairs_up
        gs.turn = 150

        # Mark a monster dead on level 1 (simulates combat that happened)
        ents1 = gs.entities[1]
        if ents1.monsters:
            ents1.monsters[0].is_dead = True
            dead_name = ents1.monsters[0].name

        # Remove a treasure pile on level 1 (simulates picked-up loot)
        original_treasure_count_1 = len(ents1.treasure_piles)
        if ents1.treasure_piles:
            removed_pos = next(iter(ents1.treasure_piles))
            del ents1.treasure_piles[removed_pos]

        # Save and reload
        assert save_game(gs, 3)
        loaded = load_game(3)
        assert loaded is not None

        # All 3 levels present
        assert set(loaded.levels.keys()) == {1, 2, 3}
        assert set(loaded.entities.keys()) == {1, 2, 3}
        assert set(loaded.revealed.keys()) == {1, 2, 3}

        # Player position preserved
        assert loaded.current_depth == 2
        assert loaded.player_x == gs.player_x
        assert loaded.player_y == gs.player_y

        # Grid fidelity per level
        for depth in (1, 2, 3):
            assert (loaded.levels[depth].grid == gs.levels[depth].grid).all(), \
                f"Grid mismatch on depth {depth}"
            assert loaded.levels[depth].stairs_up == gs.levels[depth].stairs_up
            assert loaded.levels[depth].stairs_down == gs.levels[depth].stairs_down
            assert len(loaded.levels[depth].rooms) == len(gs.levels[depth].rooms)

        # Revealed tiles preserved per level
        for depth in (1, 2, 3):
            assert loaded.revealed[depth] == gs.revealed[depth]

        # Visited rooms and opened doors preserved
        for depth in (1, 2, 3):
            assert loaded.visited_rooms[depth] == gs.visited_rooms[depth]
            assert loaded.opened_doors[depth] == gs.opened_doors[depth]

        # Dead monster state preserved on level 1
        loaded_ents1 = loaded.entities[1]
        if dead_name:
            dead_monsters = [m for m in loaded_ents1.monsters if m.is_dead]
            assert len(dead_monsters) >= 1
            assert dead_monsters[0].name == dead_name

        # Removed treasure stays removed on level 1
        assert len(loaded_ents1.treasure_piles) == len(ents1.treasure_piles)

        # Entities on other levels are intact
        for depth in (2, 3):
            assert len(loaded.entities[depth].monsters) == len(gs.entities[depth].monsters)
