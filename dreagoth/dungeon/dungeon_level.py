"""DungeonLevel — numpy uint8 grid wrapping a single dungeon floor."""

from __future__ import annotations

import numpy as np

from dreagoth.core.constants import GRID_WIDTH, GRID_HEIGHT
from dreagoth.dungeon.tiles import Tile, is_walkable
from dreagoth.dungeon.room import Room


class DungeonLevel:
    """One floor of the dungeon, stored as an 80x40 numpy grid."""

    def __init__(self, depth: int, width: int = GRID_WIDTH, height: int = GRID_HEIGHT) -> None:
        self.depth = depth
        self.width = width
        self.height = height
        # Grid stored as [y, x] for row-major access; initialized to WALL
        self.grid: np.ndarray = np.full((height, width), Tile.WALL, dtype=np.uint8)
        self.rooms: list[Room] = []
        self.stairs_up: tuple[int, int] | None = None
        self.stairs_down: tuple[int, int] | None = None

    def __getitem__(self, pos: tuple[int, int]) -> int:
        x, y = pos
        return int(self.grid[y, x])

    def __setitem__(self, pos: tuple[int, int], value: int) -> None:
        x, y = pos
        self.grid[y, x] = value

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def can_walk(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and is_walkable(self[x, y])
