"""Tests for monster detection, noise system, pathfinding, and movement AI."""

import numpy as np

from dreagoth.core.noise import (
    noise_level, detection_radius, armor_noise,
    CLASS_NOISE, RACE_NOISE,
)
from dreagoth.character.character import create_character
from dreagoth.entities.item import equipment_db
from dreagoth.entities.monster import monster_db, Monster
from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.tiles import Tile
from dreagoth.dungeon.pathfinding import bfs_next_step


class TestNoiseSystem:
    def test_class_noise_values(self):
        assert CLASS_NOISE["thief"] < CLASS_NOISE["fighter"]
        assert CLASS_NOISE["mage"] < CLASS_NOISE["cleric"]

    def test_thief_halfling_quietest(self):
        char = create_character("Sneak", "thief", "halfling")
        char.armor = None  # No armor
        n = noise_level(char)
        assert n == 0  # thief(0) + halfling(-1) = -1, clamped to 0

    def test_fighter_dwarf_loudest(self):
        char = create_character("Tank", "fighter", "dwarf")
        plate = equipment_db.get("plate")
        char.armor = plate
        n = noise_level(char)
        # fighter(3) + dwarf(1) + plate(ac7 -> heavy=3) = 7
        assert n == 7

    def test_no_armor_no_penalty(self):
        char = create_character("Mage", "mage", "elf")
        char.armor = None
        n = noise_level(char)
        # mage(1) + elf(-1) + no armor(0) = 0
        assert n == 0

    def test_leather_armor_light(self):
        char = create_character("Scout", "thief", "human")
        leather = equipment_db.get("leather")
        char.armor = leather
        an = armor_noise(char)
        assert an == 1  # leather ac_bonus=2 -> light

    def test_chain_armor_heavy(self):
        char = create_character("Cleric", "cleric", "human")
        chain = equipment_db.get("chain")
        char.armor = chain
        an = armor_noise(char)
        assert an == 3  # chain ac_bonus=5 -> heavy

    def test_noise_never_negative(self):
        char = create_character("Ghost", "thief", "halfling")
        char.armor = None
        assert noise_level(char) >= 0


class TestDetectionRadius:
    def test_fast_monster_big_radius(self):
        # speed=15, noise=3
        r = detection_radius(15, 3)
        assert r == 8  # 15//3 + 3 = 8

    def test_slow_monster_small_radius(self):
        r = detection_radius(6, 0)
        assert r == 3  # 6//3 + 0 = 2, clamped to 3

    def test_clamped_max(self):
        r = detection_radius(15, 10)
        assert r == 12  # 15//3 + 10 = 15, clamped to 12

    def test_clamped_min(self):
        r = detection_radius(6, 0)
        assert r == 3  # minimum


class TestPathfinding:
    def _make_corridor(self):
        """Create a simple horizontal corridor level."""
        level = DungeonLevel(1, 20, 5)
        # Corridor along y=2
        for x in range(20):
            level[x, 2] = Tile.CORRIDOR
        return level

    def test_straight_line_path(self):
        level = self._make_corridor()
        # Monster at (2,2), player at (5,2)
        step = bfs_next_step(level, 2, 2, 5, 2)
        assert step == (3, 2)  # Move one tile toward player

    def test_no_path_through_wall(self):
        level = DungeonLevel(1, 10, 10)
        level[2, 2] = Tile.ROOM
        level[5, 5] = Tile.ROOM
        # No corridor connecting them
        step = bfs_next_step(level, 2, 2, 5, 5)
        assert step is None

    def test_path_around_wall(self):
        level = DungeonLevel(1, 10, 10)
        # L-shaped corridor
        for x in range(1, 6):
            level[x, 2] = Tile.CORRIDOR
        for y in range(2, 6):
            level[5, y] = Tile.CORRIDOR
        step = bfs_next_step(level, 1, 2, 5, 5)
        assert step == (2, 2)  # First step east along corridor

    def test_same_position_returns_none(self):
        level = self._make_corridor()
        step = bfs_next_step(level, 3, 2, 3, 2)
        assert step is None

    def test_max_dist_limits_search(self):
        level = self._make_corridor()
        step = bfs_next_step(level, 0, 2, 19, 2, max_dist=5)
        # Path exists but is beyond max_dist
        assert step is None

    def test_path_through_opened_door(self):
        level = DungeonLevel(1, 10, 5)
        for x in range(8):
            level[x, 2] = Tile.CORRIDOR
        # Place a locked door — locked flag makes it non-walkable
        level[4, 2] = Tile.DOOR_NS | 0x80  # LOCKED_FLAG
        # Without opened doors, path should be blocked
        step = bfs_next_step(level, 2, 2, 6, 2)
        assert step is None
        # With opened doors, path should work
        step = bfs_next_step(level, 2, 2, 6, 2, opened_doors={(4, 2)})
        assert step == (3, 2)


class TestMonsterAlertState:
    def test_monster_starts_not_alert(self):
        m = monster_db.spawn("goblin", 5, 5)
        assert m.is_alert is False

    def test_monster_has_speed(self):
        m = monster_db.spawn("goblin", 5, 5)
        assert m.speed == 9  # Goblin speed from JSON

    def test_fast_monster_speed(self):
        m = monster_db.spawn("bat", 5, 5)
        assert m.speed == 15  # Bat is fast

    def test_alert_state_serialization(self):
        from dreagoth.core.save_load import _serialize_monster, _deserialize_monster
        m = monster_db.spawn("goblin", 5, 5)
        m.is_alert = True
        data = _serialize_monster(m)
        assert data["is_alert"] is True
        restored = _deserialize_monster(data)
        assert restored.is_alert is True

    def test_alert_defaults_false_on_old_save(self):
        from dreagoth.core.save_load import _deserialize_monster
        # Simulate old save without is_alert
        data = {
            "template_id": "goblin",
            "hp": 5, "max_hp": 5,
            "x": 3, "y": 3,
            "is_dead": False,
        }
        restored = _deserialize_monster(data)
        assert restored.is_alert is False


class TestDoorNoiseAttenuation:
    def test_no_doors_no_penalty(self):
        from dreagoth.core.noise import count_closed_doors_between
        level = DungeonLevel(1, 20, 5)
        for x in range(20):
            level[x, 2] = Tile.CORRIDOR
        doors = count_closed_doors_between(level, 2, 2, 10, 2, set())
        assert doors == 0

    def test_closed_door_counted(self):
        from dreagoth.core.noise import count_closed_doors_between
        level = DungeonLevel(1, 20, 5)
        for x in range(20):
            level[x, 2] = Tile.CORRIDOR
        level[5, 2] = Tile.DOOR_NS | 0x80  # closed locked door
        doors = count_closed_doors_between(level, 2, 2, 10, 2, set())
        assert doors == 1

    def test_opened_door_not_counted(self):
        from dreagoth.core.noise import count_closed_doors_between
        level = DungeonLevel(1, 20, 5)
        for x in range(20):
            level[x, 2] = Tile.CORRIDOR
        level[5, 2] = Tile.DOOR_NS | 0x80
        doors = count_closed_doors_between(level, 2, 2, 10, 2, {(5, 2)})
        assert doors == 0

    def test_two_closed_doors(self):
        from dreagoth.core.noise import count_closed_doors_between
        level = DungeonLevel(1, 20, 5)
        for x in range(20):
            level[x, 2] = Tile.CORRIDOR
        level[5, 2] = Tile.DOOR_NS | 0x80
        level[8, 2] = Tile.DOOR_NS  # plain closed door (not opened)
        doors = count_closed_doors_between(level, 2, 2, 10, 2, set())
        assert doors == 2

    def test_door_penalty_reduces_detection(self):
        from dreagoth.core.noise import DOOR_NOISE_PENALTY
        # With base detection of 6 and 1 closed door, effective range shrinks
        base_range = 6
        effective = max(1, base_range - 1 * DOOR_NOISE_PENALTY)
        assert effective < base_range
        assert effective >= 1
