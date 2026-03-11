"""Pathfinding for monster movement — BFS on the dungeon grid."""

from __future__ import annotations

from collections import deque

from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.tiles import is_walkable, is_door


def bfs_next_step(
    level: DungeonLevel,
    sx: int, sy: int,
    gx: int, gy: int,
    max_dist: int = 15,
    opened_doors: set[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """BFS from (sx, sy) toward (gx, gy). Returns the next step position.

    Only traverses walkable tiles and opened doors.  Stops searching
    after *max_dist* tiles to keep it fast.  Returns None if no path
    exists within range.
    """
    if sx == gx and sy == gy:
        return None  # Already there

    opened = opened_doors or set()
    start = (sx, sy)
    goal = (gx, gy)

    queue: deque[tuple[int, int]] = deque([start])
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        cx, cy = queue.popleft()

        # Distance check (Manhattan from start)
        if abs(cx - sx) + abs(cy - sy) > max_dist:
            continue

        if (cx, cy) == goal:
            # Reconstruct path and return first step
            pos: tuple[int, int] = goal
            while came_from.get(pos) != start:
                prev = came_from.get(pos)
                if prev is None:
                    return None
                pos = prev
            return pos

        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in came_from:
                continue
            if not level.in_bounds(nx, ny):
                continue
            # Goal is always passable (player is standing there)
            if (nx, ny) == goal:
                came_from[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))
                continue
            tile = level[nx, ny]
            if is_walkable(tile):
                came_from[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))
            elif is_door(tile) and (nx, ny) in opened:
                came_from[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))

    return None  # No path found within range
