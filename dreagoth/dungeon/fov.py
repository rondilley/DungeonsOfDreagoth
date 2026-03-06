"""Field of View — recursive shadowcasting algorithm.

Computes visible tiles from a position using 8-octant symmetric shadowcasting.
Based on the standard roguelike algorithm from RogueBasin.
"""

import numpy as np

from dreagoth.dungeon.tiles import is_transparent

# Octant coordinate transform multipliers
# Each column represents one octant's (xx, xy, yx, yy) multipliers
_MULT = (
    (1, 0, 0, -1, -1, 0, 0, 1),   # xx
    (0, 1, -1, 0, 0, -1, 1, 0),   # xy
    (0, 1, 1, 0, 0, -1, -1, 0),   # yx
    (1, 0, 0, 1, -1, 0, 0, -1),   # yy
)


def compute_fov(
    grid: np.ndarray,
    px: int,
    py: int,
    radius: int,
    opened_doors: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """Compute all tiles visible from (px, py) within given radius.

    opened_doors: positions of doors that have been opened and should be
    treated as transparent even though the base tile blocks sight.
    """
    height, width = grid.shape
    visible: set[tuple[int, int]] = {(px, py)}
    if opened_doors is None:
        opened_doors = set()

    for octant in range(8):
        _cast_light(
            grid, px, py, radius, 1, 1.0, 0.0,
            _MULT[0][octant], _MULT[1][octant],
            _MULT[2][octant], _MULT[3][octant],
            height, width, visible, opened_doors,
        )

    return visible


def _cast_light(
    grid: np.ndarray,
    cx: int, cy: int,
    radius: int,
    row: int,
    start_slope: float,
    end_slope: float,
    xx: int, xy: int, yx: int, yy: int,
    height: int, width: int,
    visible: set[tuple[int, int]],
    opened_doors: set[tuple[int, int]],
) -> None:
    if start_slope < end_slope:
        return

    radius_sq = radius * radius
    new_start = 0.0

    for j in range(row, radius + 1):
        # dy is negative — represents depth into the octant
        dy = -j
        dx = dy - 1
        blocked = False

        while dx <= 0:
            dx += 1
            # Transform (dx, dy) into map coordinates via octant multipliers
            map_x = cx + dx * xx + dy * xy
            map_y = cy + dx * yx + dy * yy

            if not (0 <= map_x < width and 0 <= map_y < height):
                continue

            # Slopes for this cell's left and right edges
            l_slope = (dx - 0.5) / (dy + 0.5)
            r_slope = (dx + 0.5) / (dy - 0.5)

            if start_slope < r_slope:
                continue
            elif end_slope > l_slope:
                break

            # Cell is visible if within radius
            if dx * dx + dy * dy < radius_sq:
                visible.add((map_x, map_y))

            # Opened doors are transparent even though the tile itself isn't
            if (map_x, map_y) in opened_doors:
                cell_opaque = False
            else:
                cell_opaque = not is_transparent(int(grid[map_y, map_x]))

            if blocked:
                if cell_opaque:
                    new_start = r_slope
                else:
                    blocked = False
                    start_slope = new_start
            elif cell_opaque:
                if j < radius:
                    blocked = True
                    _cast_light(
                        grid, cx, cy, radius, j + 1,
                        start_slope, l_slope,
                        xx, xy, yx, yy,
                        height, width, visible, opened_doors,
                    )
                    new_start = r_slope

        if blocked:
            break
