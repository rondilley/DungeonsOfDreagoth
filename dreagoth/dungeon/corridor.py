"""Corridor carving — connects rooms using L-shaped corridors."""

import random

import numpy as np

from dreagoth.dungeon.tiles import Tile


def carve_l_corridor(
    grid: np.ndarray,
    x1: int, y1: int,
    x2: int, y2: int,
) -> None:
    """Carve an L-shaped corridor between two points.

    Randomly chooses horizontal-first or vertical-first.
    Only overwrites WALL tiles to preserve existing rooms/corridors.
    """
    if random.random() < 0.5:
        _carve_horizontal(grid, x1, x2, y1)
        _carve_vertical(grid, y1, y2, x2)
    else:
        _carve_vertical(grid, y1, y2, x1)
        _carve_horizontal(grid, x1, x2, y2)


def _carve_horizontal(grid: np.ndarray, x1: int, x2: int, y: int) -> None:
    lo, hi = min(x1, x2), max(x1, x2)
    for x in range(lo, hi + 1):
        if grid[y, x] == Tile.WALL:
            grid[y, x] = Tile.CORRIDOR


def _carve_vertical(grid: np.ndarray, y1: int, y2: int, x: int) -> None:
    lo, hi = min(y1, y2), max(y1, y2)
    for y in range(lo, hi + 1):
        if grid[y, x] == Tile.WALL:
            grid[y, x] = Tile.CORRIDOR
