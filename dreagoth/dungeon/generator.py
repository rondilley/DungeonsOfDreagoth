"""Dungeon generator — port of QBasic DUNGEON.TXT with modern improvements.

Original algorithm (1991):
  1. Fill 80x24 grid with 0xFF (wall)
  2. Place up/down stairs randomly
  3. Generate 25 rooms with collision detection
  4. Connect stairs with DFS pathfinding

Python sequel improvements:
  - 80x40 grid for more vertical space
  - A* / MST-based corridor connection (all rooms reachable)
  - Configurable room sizes and counts
"""

import random
from collections import deque

from dreagoth.core.constants import (
    GRID_WIDTH, GRID_HEIGHT,
    ROOMS_PER_LEVEL,
    MIN_ROOM_WIDTH, MAX_ROOM_WIDTH,
    MIN_ROOM_HEIGHT, MAX_ROOM_HEIGHT,
    ROOM_BUFFER, MAX_ROOM_ATTEMPTS,
)
from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.room import Room
from dreagoth.dungeon.tiles import (
    Tile, LOCKED_FLAG, MAGICALLY_LOCKED_FLAG,
    is_door, is_walkable, unlock_door,
)
from dreagoth.dungeon.corridor import carve_l_corridor


class DungeonGenerator:
    """Generates a complete dungeon level."""

    def __init__(self, seed: int | None = None) -> None:
        if seed is not None:
            random.seed(seed)

    def generate(self, depth: int) -> DungeonLevel:
        level = DungeonLevel(depth, GRID_WIDTH, GRID_HEIGHT)

        # 1. Place rooms
        self._place_rooms(level)

        # 2. Connect rooms with corridors (MST)
        self._connect_rooms(level)

        # 3. Place doors at room entrances
        self._place_doors(level, depth)

        # 4. Place stairs inside rooms
        self._place_stairs(level, depth)

        # 5. Guarantee a path from stairs_up to stairs_down
        self._ensure_stair_path(level)

        return level

    def _place_rooms(self, level: DungeonLevel) -> None:
        """Place up to ROOMS_PER_LEVEL non-overlapping rooms."""
        for room_idx in range(ROOMS_PER_LEVEL):
            room = self._try_place_room(level, room_idx)
            if room:
                self._carve_room(level, room)
                level.rooms.append(room)

    def _try_place_room(self, level: DungeonLevel, room_id: int) -> Room | None:
        """Try to place a room, retrying on collision."""
        for _ in range(MAX_ROOM_ATTEMPTS):
            w = random.randint(MIN_ROOM_WIDTH, MAX_ROOM_WIDTH)
            h = random.randint(MIN_ROOM_HEIGHT, MAX_ROOM_HEIGHT)
            # Keep rooms away from grid edges (1-tile border)
            x = random.randint(2, level.width - w - 2)
            y = random.randint(2, level.height - h - 2)

            candidate = Room(x, y, w, h, room_id)

            # Check for overlap with existing rooms
            if not any(candidate.intersects(r, ROOM_BUFFER) for r in level.rooms):
                return candidate
        return None

    def _carve_room(self, level: DungeonLevel, room: Room) -> None:
        """Carve room tiles into the grid."""
        for ry in range(room.y, room.y + room.height):
            for rx in range(room.x, room.x + room.width):
                level[rx, ry] = Tile.ROOM

    def _connect_rooms(self, level: DungeonLevel) -> None:
        """Connect all rooms using minimum spanning tree + L-shaped corridors."""
        if len(level.rooms) < 2:
            return

        # Prim's algorithm for MST on room centers
        connected = {0}
        remaining = set(range(1, len(level.rooms)))

        while remaining:
            best_dist = float("inf")
            best_pair = (0, 0)

            for ci in connected:
                cx, cy = level.rooms[ci].center
                for ri in remaining:
                    rx, ry = level.rooms[ri].center
                    dist = abs(cx - rx) + abs(cy - ry)
                    if dist < best_dist:
                        best_dist = dist
                        best_pair = (ci, ri)

            ci, ri = best_pair
            connected.add(ri)
            remaining.discard(ri)

            # Carve corridor between room centers
            r1, r2 = level.rooms[ci], level.rooms[ri]
            carve_l_corridor(
                level.grid,
                r1.center_x, r1.center_y,
                r2.center_x, r2.center_y,
            )

    def _place_doors(self, level: DungeonLevel, depth: int) -> None:
        """Place doors at room/corridor boundaries.

        All candidate positions across every room are collected, then
        grouped into global connected components (4-adjacent flood fill)
        so that clusters — even spanning two rooms — produce only a
        single door (the one closest to the cluster centroid).
        """
        # 1. Convert corridor tiles in room-to-room gaps to ROOM.
        #    Iterate until stable because converting one tile can expose
        #    the next tile in a corridor chain as a new gap.
        self._convert_room_gaps(level)

        # 2. Collect ALL door candidates globally, remembering which
        #    room each came from (for orientation).
        candidate_room: dict[tuple[int, int], Room] = {}
        for room in level.rooms:
            for bx in range(room.x - 1, room.x + room.width + 1):
                for by in range(room.y - 1, room.y + room.height + 1):
                    if room.contains(bx, by):
                        continue
                    if not level.in_bounds(bx, by):
                        continue
                    if level[bx, by] != Tile.CORRIDOR:
                        continue
                    for adx, ady in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                        if room.contains(bx + adx, by + ady):
                            candidate_room[(bx, by)] = room
                            break

        if not candidate_room:
            return

        # 2. Group into global connected components (4-adjacent)
        components = self._flood_fill_components(list(candidate_room))

        # 3. Place one door per component (closest to centroid)
        for comp in components:
            cx = sum(p[0] for p in comp) / len(comp)
            cy = sum(p[1] for p in comp) / len(comp)
            best = min(comp, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            bx, by = best
            room = candidate_room[(bx, by)]

            # Determine door orientation
            if bx < room.x or bx >= room.x + room.width:
                door_tile = Tile.DOOR_EW
            else:
                door_tile = Tile.DOOR_NS

            # Apply lock / secret flags based on depth
            flags = 0
            roll = random.random()
            if depth >= 3 and roll < 0.02 + 0.02 * depth:
                flags = MAGICALLY_LOCKED_FLAG
            elif roll < 0.10 + 0.03 * depth:
                flags = LOCKED_FLAG
            elif roll < 0.05 + 0.02 * depth:
                if door_tile == Tile.DOOR_NS:
                    door_tile = Tile.SECRET_DOOR_NS
                else:
                    door_tile = Tile.SECRET_DOOR_EW

            level[bx, by] = int(door_tile) | flags

    @staticmethod
    def _convert_room_gaps(level: DungeonLevel) -> None:
        """Convert corridor tiles between rooms to ROOM tiles.

        A corridor tile with ROOM on opposite sides (N/S or E/W) is a
        gap between adjacent rooms, not a real hallway.  Converting it
        to ROOM can expose the *next* corridor in the chain as a new gap,
        so we iterate until no more conversions are made.
        """
        changed = True
        while changed:
            changed = False
            for y in range(level.height):
                for x in range(level.width):
                    if level[x, y] != Tile.CORRIDOR:
                        continue
                    if DungeonGenerator._is_room_gap(level, x, y):
                        level[x, y] = Tile.ROOM
                        changed = True

    @staticmethod
    def _is_room_gap(level: DungeonLevel, x: int, y: int) -> bool:
        """True if (x, y) has ROOM tiles on opposite sides (N/S or E/W).

        This detects 1-tile wall gaps between adjacent rooms where a
        corridor has punched through but no real hallway exists.
        """
        def is_room(nx: int, ny: int) -> bool:
            return level.in_bounds(nx, ny) and level[nx, ny] == Tile.ROOM

        return (
            (is_room(x - 1, y) and is_room(x + 1, y))
            or (is_room(x, y - 1) and is_room(x, y + 1))
        )

    @staticmethod
    def _flood_fill_components(
        positions: list[tuple[int, int]],
    ) -> list[list[tuple[int, int]]]:
        """Group positions into 4-connected components."""
        pos_set = set(positions)
        visited: set[tuple[int, int]] = set()
        components: list[list[tuple[int, int]]] = []
        for p in positions:
            if p in visited:
                continue
            # BFS flood fill
            comp: list[tuple[int, int]] = []
            queue = [p]
            visited.add(p)
            while queue:
                cur = queue.pop()
                comp.append(cur)
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    nb = (cur[0] + dx, cur[1] + dy)
                    if nb in pos_set and nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            components.append(comp)
        return components

    def _place_stairs(self, level: DungeonLevel, depth: int) -> None:
        """Place up and down stairs in random rooms."""
        if len(level.rooms) < 2:
            return

        # Shuffle rooms and pick two distinct ones for stairs
        indices = list(range(len(level.rooms)))
        random.shuffle(indices)

        # Up stairs (always present)
        up_room = level.rooms[indices[0]]
        ux, uy = up_room.center
        level[ux, uy] = Tile.STAIRS_UP
        level.stairs_up = (ux, uy)

        # Down stairs (present on all but the deepest level)
        down_room = level.rooms[indices[1]]
        dx, dy = down_room.center
        level[dx, dy] = Tile.STAIRS_DOWN
        level.stairs_down = (dx, dy)

    def _ensure_stair_path(self, level: DungeonLevel) -> None:
        """BFS from stairs_up to stairs_down; unlock any doors on the path.

        Treats all walkable tiles AND all doors (even locked) as passable
        so the BFS finds the shortest path. Any locked/magically-locked
        doors along that path are unlocked — all other locked doors remain.
        """
        if level.stairs_up is None or level.stairs_down is None:
            return

        start = level.stairs_up
        goal = level.stairs_down

        def passable(x: int, y: int) -> bool:
            if not level.in_bounds(x, y):
                return False
            tv = level[x, y]
            return is_walkable(tv) or is_door(tv)

        # BFS
        queue: deque[tuple[int, int]] = deque([start])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

        while queue:
            cx, cy = queue.popleft()
            if (cx, cy) == goal:
                break
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in came_from and passable(nx, ny):
                    came_from[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))
        else:
            # No path found (should not happen with MST corridors)
            return

        # Reconstruct path and unlock any locked doors along it
        pos: tuple[int, int] | None = goal
        while pos is not None:
            x, y = pos
            tv = level[x, y]
            if is_door(tv) and tv != unlock_door(tv):
                level[x, y] = unlock_door(tv)
            pos = came_from.get(pos)
