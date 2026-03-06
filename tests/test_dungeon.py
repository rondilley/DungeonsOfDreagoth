"""Tests for dungeon generation core systems."""

import numpy as np

from dreagoth.core.dice import roll, d6, d20, ability_roll
from dreagoth.core.constants import GRID_WIDTH, GRID_HEIGHT, ROOMS_PER_LEVEL
from dreagoth.dungeon.tiles import Tile, is_walkable, is_transparent
from dreagoth.dungeon.room import Room
from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.generator import DungeonGenerator
from dreagoth.dungeon.corridor import carve_l_corridor
from dreagoth.dungeon.fov import compute_fov


class TestDice:
    def test_roll_range(self):
        for _ in range(100):
            result = roll(1, 6)
            assert 1 <= result <= 6

    def test_multi_roll(self):
        for _ in range(100):
            result = roll(3, 6)
            assert 3 <= result <= 18

    def test_d20(self):
        for _ in range(100):
            assert 1 <= d20() <= 20

    def test_ability_roll(self):
        for _ in range(100):
            score = ability_roll()
            assert 3 <= score <= 18


class TestTiles:
    def test_hex_values(self):
        assert Tile.WALL == 0xFF
        assert Tile.EMPTY == 0x00
        assert Tile.STAIRS_UP == 0x07
        assert Tile.STAIRS_DOWN == 0x08
        assert Tile.ROOM == 0x14
        assert Tile.CORRIDOR == 0x20

    def test_walkable(self):
        assert is_walkable(Tile.ROOM)
        assert is_walkable(Tile.CORRIDOR)
        assert is_walkable(Tile.STAIRS_UP)
        assert is_walkable(Tile.STAIRS_DOWN)
        assert not is_walkable(Tile.WALL)
        assert not is_walkable(Tile.UNSTABLE_WALL)

    def test_transparent(self):
        assert is_transparent(Tile.ROOM)
        assert is_transparent(Tile.CORRIDOR)
        assert not is_transparent(Tile.WALL)


class TestRoom:
    def test_center(self):
        room = Room(10, 10, 6, 4)
        assert room.center_x == 13
        assert room.center_y == 12

    def test_contains(self):
        room = Room(5, 5, 4, 3)
        assert room.contains(5, 5)
        assert room.contains(8, 7)
        assert not room.contains(4, 5)
        assert not room.contains(9, 5)

    def test_intersects(self):
        r1 = Room(5, 5, 4, 3)
        r2 = Room(10, 10, 4, 3)
        assert not r1.intersects(r2)

        r3 = Room(8, 7, 4, 3)
        assert r1.intersects(r3)

    def test_intersects_with_buffer(self):
        r1 = Room(5, 5, 4, 3)
        r2 = Room(9, 5, 4, 3)  # 0 tile gap — within buffer=1
        assert r1.intersects(r2, buffer=1)
        r3 = Room(10, 5, 4, 3)  # 1 tile gap — exactly satisfies buffer=1
        assert not r1.intersects(r3, buffer=1)


class TestDungeonLevel:
    def test_init(self):
        level = DungeonLevel(1)
        assert level.width == GRID_WIDTH
        assert level.height == GRID_HEIGHT
        assert level.grid.shape == (GRID_HEIGHT, GRID_WIDTH)
        assert level.grid[0, 0] == Tile.WALL

    def test_getset(self):
        level = DungeonLevel(1)
        level[5, 3] = Tile.ROOM
        assert level[5, 3] == Tile.ROOM

    def test_bounds(self):
        level = DungeonLevel(1)
        assert level.in_bounds(0, 0)
        assert level.in_bounds(79, 39)
        assert not level.in_bounds(-1, 0)
        assert not level.in_bounds(80, 0)
        assert not level.in_bounds(0, 40)


class TestCorridor:
    def test_carve_l_corridor(self):
        grid = np.full((20, 20), Tile.WALL, dtype=np.uint8)
        carve_l_corridor(grid, 2, 2, 10, 10)

        # Should have carved a path — check endpoints are corridor
        # The path goes through either (2,2)->(10,2)->(10,10)
        # or (2,2)->(2,10)->(10,10)
        # Either way, start and end should be corridor
        assert grid[2, 2] == Tile.CORRIDOR
        assert grid[10, 10] == Tile.CORRIDOR


class TestGenerator:
    def test_generates_rooms(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        assert len(level.rooms) > 0
        assert len(level.rooms) <= ROOMS_PER_LEVEL

    def test_has_stairs(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        assert level.stairs_up is not None
        assert level.stairs_down is not None

    def test_stairs_walkable(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        ux, uy = level.stairs_up
        dx, dy = level.stairs_down
        assert level[ux, uy] == Tile.STAIRS_UP
        assert level[dx, dy] == Tile.STAIRS_DOWN

    def test_rooms_dont_overlap(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        for i, r1 in enumerate(level.rooms):
            for r2 in level.rooms[i + 1:]:
                assert not r1.intersects(r2, buffer=0), \
                    f"Rooms {r1.room_id} and {r2.room_id} overlap"

    def test_deterministic_with_seed(self):
        level1 = DungeonGenerator(seed=123).generate(1)
        level2 = DungeonGenerator(seed=123).generate(1)
        assert np.array_equal(level1.grid, level2.grid)


class TestFOV:
    def test_player_always_visible(self):
        grid = np.full((20, 20), Tile.WALL, dtype=np.uint8)
        grid[10, 10] = Tile.ROOM
        visible = compute_fov(grid, 10, 10, 8)
        assert (10, 10) in visible

    def test_wall_blocks_vision(self):
        grid = np.full((20, 20), Tile.ROOM, dtype=np.uint8)
        # Create a wall barrier
        for y in range(20):
            grid[y, 10] = Tile.WALL
        visible = compute_fov(grid, 5, 10, 8)
        # Should not see past the wall
        assert (5, 10) in visible
        # Wall itself is visible
        assert (10, 10) in visible
        # Past the wall should not be visible
        assert (12, 10) not in visible

    def test_open_room_visibility(self):
        grid = np.full((20, 20), Tile.ROOM, dtype=np.uint8)
        visible = compute_fov(grid, 10, 10, 5)
        # Should see adjacent tiles
        assert (11, 10) in visible
        assert (10, 11) in visible
        assert (9, 10) in visible
        assert (10, 9) in visible

    def test_closed_door_blocks_vision(self):
        """A closed door is visible but blocks sight beyond it."""
        grid = np.full((20, 20), Tile.ROOM, dtype=np.uint8)
        grid[10, 8] = Tile.DOOR_NS  # Door at (8, 10) in game coords
        visible = compute_fov(grid, 10, 10, 8)
        # Door itself is visible
        assert (8, 10) in visible
        # Tiles beyond the door are blocked
        assert (6, 10) not in visible

    def test_opened_door_allows_vision(self):
        """An opened door lets sight through."""
        grid = np.full((20, 20), Tile.ROOM, dtype=np.uint8)
        grid[10, 8] = Tile.DOOR_NS  # Door at (8, 10)
        opened = {(8, 10)}
        visible = compute_fov(grid, 10, 10, 8, opened_doors=opened)
        # Door is visible
        assert (8, 10) in visible
        # Tiles beyond the door are now visible
        assert (6, 10) in visible
