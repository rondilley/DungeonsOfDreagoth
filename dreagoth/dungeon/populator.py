"""Dungeon populator — places monsters, treasure, and items in levels."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.tiles import Tile, is_door
from dreagoth.entities.monster import Monster, monster_db
from dreagoth.entities.item import Item, equipment_db
from dreagoth.entities.magic_items import roll_magic_loot
from dreagoth.entities.npc import NPC, npc_db


@dataclass
class LevelEntities:
    """All entities placed on a dungeon level."""
    monsters: list[Monster] = field(default_factory=list)
    treasure_piles: dict[tuple[int, int], list[Item]] = field(default_factory=dict)
    gold_piles: dict[tuple[int, int], int] = field(default_factory=dict)
    npcs: list[NPC] = field(default_factory=list)

    # Position indices — call rebuild_indices() after mutations
    _monster_index: dict[tuple[int, int], Monster] = field(
        default_factory=dict, repr=False
    )
    _npc_index: dict[tuple[int, int], NPC] = field(
        default_factory=dict, repr=False
    )

    def rebuild_indices(self) -> None:
        """Rebuild position lookup dicts. Call after adding/removing entities."""
        self._monster_index = {
            (m.x, m.y): m for m in self.monsters if not m.is_dead
        }
        self._npc_index = {(n.x, n.y): n for n in self.npcs}

    def monster_at(self, x: int, y: int) -> Monster | None:
        m = self._monster_index.get((x, y))
        if m and not m.is_dead:
            return m
        return None

    def npc_at(self, x: int, y: int) -> NPC | None:
        return self._npc_index.get((x, y))

    def remove_dead(self) -> None:
        self.monsters = [m for m in self.monsters if not m.is_dead]
        self.rebuild_indices()


def _adjacent_to_door(level: DungeonLevel, x: int, y: int) -> bool:
    """True if any 4-adjacent tile is a door."""
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        nx, ny = x + dx, y + dy
        if level.in_bounds(nx, ny) and is_door(level[nx, ny]):
            return True
    return False


def _find_npc_position(
    level: DungeonLevel, room: "Room",
) -> tuple[int, int] | None:
    """Pick a ROOM tile inside *room* that isn't on or adjacent to a door.

    Tries random positions first (fast for large rooms), then falls back to
    an exhaustive scan so small rooms still work.
    """
    from dreagoth.dungeon.room import Room  # avoid circular at module level

    for _ in range(20):
        rx = random.randint(room.x, room.x + room.width - 1)
        ry = random.randint(room.y, room.y + room.height - 1)
        if level[rx, ry] == Tile.ROOM and not _adjacent_to_door(level, rx, ry):
            return (rx, ry)

    # Exhaustive fallback
    for ry in range(room.y, room.y + room.height):
        for rx in range(room.x, room.x + room.width):
            if level[rx, ry] == Tile.ROOM and not _adjacent_to_door(level, rx, ry):
                return (rx, ry)
    return None


def populate_level(level: DungeonLevel, depth: int) -> LevelEntities:
    """Place monsters and treasure throughout the level."""
    entities = LevelEntities()

    for room in level.rooms:
        # Skip stair rooms (safe zones)
        if level.stairs_up and room.contains(*level.stairs_up):
            continue
        if level.stairs_down and room.contains(*level.stairs_down):
            continue

        # Chance to spawn a monster in each room
        if random.random() < 0.5 + depth * 0.03:
            rx = random.randint(room.x, room.x + room.width - 1)
            ry = random.randint(room.y, room.y + room.height - 1)
            monster = monster_db.random_for_level(depth, rx, ry)
            if monster:
                entities.monsters.append(monster)

        # Chance for treasure
        if random.random() < 0.3:
            tx = random.randint(room.x, room.x + room.width - 1)
            ty = random.randint(room.y, room.y + room.height - 1)
            gold = random.randint(1, 10) * depth
            entities.gold_piles[(tx, ty)] = gold
            if random.random() < 0.2 + depth * 0.05:
                loot = equipment_db.random_treasure(min(4, depth // 2))
                if loot:
                    entities.treasure_piles[(tx, ty)] = loot
            # Chance for a magic item in the chest
            magic_item = roll_magic_loot(depth, min(4, depth // 2))
            if magic_item:
                entities.treasure_piles.setdefault((tx, ty), []).append(magic_item)

    # Place 1-3 NPCs in non-stair, non-monster rooms
    npc_rooms = [
        room for room in level.rooms
        if not (level.stairs_up and room.contains(*level.stairs_up))
        and not (level.stairs_down and room.contains(*level.stairs_down))
    ]
    # Filter out rooms that already have monsters
    monster_positions = {(m.x, m.y) for m in entities.monsters}
    safe_rooms = [
        room for room in npc_rooms
        if not any(
            (mx, my) in monster_positions
            for mx in range(room.x, room.x + room.width)
            for my in range(room.y, room.y + room.height)
        )
    ]
    npc_count = min(random.randint(1, 3), len(safe_rooms))
    if safe_rooms:
        chosen = random.sample(safe_rooms, npc_count)
        used_template_ids: set[str] = set()
        for room in chosen:
            pos = _find_npc_position(level, room)
            if pos is None:
                continue
            nx, ny = pos
            eligible = [
                t for t in npc_db.eligible_for_level(depth)
                if t.id not in used_template_ids
            ]
            if not eligible:
                continue
            template = random.choice(eligible)
            npc = npc_db.spawn(template.id, nx, ny)
            used_template_ids.add(template.id)
            entities.npcs.append(npc)

    entities.rebuild_indices()
    return entities
