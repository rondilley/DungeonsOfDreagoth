"""Tests for door mechanics — helpers, walkability, generation, dedup, stair path."""

from collections import deque

from dreagoth.dungeon.tiles import (
    Tile, LOCKED_FLAG, MAGICALLY_LOCKED_FLAG,
    is_door, is_locked, is_magically_locked, has_door_flags,
    unlock_door, base_tile, is_walkable, is_transparent,
)
from dreagoth.dungeon.generator import DungeonGenerator
from dreagoth.combat.spells import spell_db


class TestDoorHelpers:
    def test_base_tile(self):
        assert base_tile(Tile.DOOR_NS) == Tile.DOOR_NS
        assert base_tile(Tile.DOOR_EW | LOCKED_FLAG) == Tile.DOOR_EW
        assert base_tile(Tile.DOOR_NS | MAGICALLY_LOCKED_FLAG) == Tile.DOOR_NS

    def test_is_door(self):
        assert is_door(Tile.DOOR_NS)
        assert is_door(Tile.DOOR_EW)
        assert is_door(Tile.SECRET_DOOR_NS)
        assert is_door(Tile.SECRET_DOOR_EW)
        assert not is_door(Tile.WALL)
        assert not is_door(Tile.ROOM)

    def test_is_door_with_flags(self):
        assert is_door(Tile.DOOR_NS | LOCKED_FLAG)
        assert is_door(Tile.DOOR_EW | MAGICALLY_LOCKED_FLAG)

    def test_is_locked(self):
        assert is_locked(Tile.DOOR_NS | LOCKED_FLAG)
        assert not is_locked(Tile.DOOR_NS)
        assert not is_locked(Tile.ROOM)

    def test_is_magically_locked(self):
        assert is_magically_locked(Tile.DOOR_NS | MAGICALLY_LOCKED_FLAG)
        assert not is_magically_locked(Tile.DOOR_NS | LOCKED_FLAG)

    def test_unlock_door(self):
        locked = Tile.DOOR_NS | LOCKED_FLAG
        unlocked = unlock_door(locked)
        assert unlocked == Tile.DOOR_NS
        assert not is_locked(unlocked)

    def test_unlock_magic_door(self):
        magic = Tile.DOOR_EW | MAGICALLY_LOCKED_FLAG
        unlocked = unlock_door(magic)
        assert unlocked == Tile.DOOR_EW
        assert not is_magically_locked(unlocked)

    def test_has_door_flags(self):
        assert has_door_flags(Tile.DOOR_NS | LOCKED_FLAG)
        assert has_door_flags(Tile.DOOR_NS | MAGICALLY_LOCKED_FLAG)
        assert not has_door_flags(Tile.DOOR_NS)


class TestDoorWalkability:
    def test_unlocked_door_walkable(self):
        assert is_walkable(Tile.DOOR_NS)
        assert is_walkable(Tile.DOOR_EW)

    def test_locked_door_not_walkable(self):
        assert not is_walkable(Tile.DOOR_NS | LOCKED_FLAG)
        assert not is_walkable(Tile.DOOR_EW | LOCKED_FLAG)

    def test_magic_locked_not_walkable(self):
        assert not is_walkable(Tile.DOOR_NS | MAGICALLY_LOCKED_FLAG)

    def test_closed_door_not_transparent(self):
        """All doors block sight until opened."""
        assert not is_transparent(Tile.DOOR_NS)
        assert not is_transparent(Tile.DOOR_EW)

    def test_locked_door_not_transparent(self):
        assert not is_transparent(Tile.DOOR_NS | LOCKED_FLAG)

    def test_wall_still_not_walkable(self):
        assert not is_walkable(Tile.WALL)

    def test_room_still_walkable(self):
        assert is_walkable(Tile.ROOM)


class TestDoorGeneration:
    def test_doors_placed(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(5)
        # Scan for any door tiles
        door_count = 0
        for y in range(level.height):
            for x in range(level.width):
                tile_val = level[x, y]
                if is_door(tile_val):
                    door_count += 1
        assert door_count > 0, "Level should have at least some doors"


class TestDoorPlacement:
    """Doors must connect a room to a corridor, not sit between two rooms."""

    def test_doors_not_between_two_rooms(self):
        """Every door must have at least one CORRIDOR neighbor."""
        for seed in range(10):
            gen = DungeonGenerator(seed=seed)
            level = gen.generate(3)
            for y in range(level.height):
                for x in range(level.width):
                    if not is_door(level[x, y]):
                        continue
                    has_corridor = False
                    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                        nx, ny = x + dx, y + dy
                        if level.in_bounds(nx, ny) and level[nx, ny] == Tile.CORRIDOR:
                            has_corridor = True
                            break
                    assert has_corridor, (
                        f"Seed {seed}: door at ({x},{y}) has no corridor neighbor"
                    )


class TestDoorDedup:
    """No two doors should be 4-adjacent on the same room border."""

    def _find_adjacent_door_pairs(self, level):
        """Return list of (pos1, pos2) where two doors are 4-adjacent."""
        doors = set()
        for y in range(level.height):
            for x in range(level.width):
                if is_door(level[x, y]):
                    doors.add((x, y))
        pairs = []
        for (x, y) in doors:
            for dx, dy in ((1, 0), (0, 1)):
                nb = (x + dx, y + dy)
                if nb in doors:
                    pairs.append(((x, y), nb))
        return pairs

    def test_no_adjacent_doors_multiple_seeds(self):
        for seed in range(10):
            gen = DungeonGenerator(seed=seed)
            level = gen.generate(3)
            pairs = self._find_adjacent_door_pairs(level)
            assert pairs == [], (
                f"Seed {seed}: adjacent door pairs found: {pairs}"
            )

    def test_doors_still_placed(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(3)
        door_count = sum(
            1 for y in range(level.height)
            for x in range(level.width)
            if is_door(level[x, y])
        )
        assert door_count > 0


class TestStairPath:
    """stairs_up must always be reachable from stairs_down via walkable tiles."""

    @staticmethod
    def _bfs_reachable(level, start, goal):
        """BFS using only is_walkable tiles. Returns True if goal reached."""
        queue = deque([start])
        visited = {start}
        while queue:
            cx, cy = queue.popleft()
            if (cx, cy) == goal:
                return True
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in visited and level.in_bounds(nx, ny) and is_walkable(level[nx, ny]):
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        return False

    def test_stair_path_guaranteed(self):
        for seed in range(10):
            gen = DungeonGenerator(seed=seed)
            level = gen.generate(5)
            assert level.stairs_up is not None
            assert level.stairs_down is not None
            assert self._bfs_reachable(level, level.stairs_up, level.stairs_down), (
                f"Seed {seed}: no walkable path from stairs_up to stairs_down"
            )


class TestClassDoorInteraction:
    """Verify that Knock and Dispel Magic spells exist for door unlocking."""

    def test_knock_is_mage_l2_unlock(self):
        knock = spell_db.get("knock")
        assert knock is not None
        assert knock.spell_class == "mage"
        assert knock.level == 2
        assert knock.effect == "unlock"

    def test_dispel_magic_is_cleric_l3_unlock(self):
        dm = spell_db.get("dispel_magic")
        assert dm is not None
        assert dm.spell_class == "cleric"
        assert dm.level == 3
        assert dm.effect == "unlock"
