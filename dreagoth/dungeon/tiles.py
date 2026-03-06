"""Tile types preserving original QBasic hex codes from Dungeons of Dreagoth (1991).

Original encoding from DUNGEON.TXT:
  0x00 = Empty 10'x10' Area          0xFF = Wall section
  0x01 = Door (N/S traffic)          0x02 = Door (E/W traffic)
  0x05 = Secret Door (N/S)           0x06 = Secret Door (E/W)
  0x07 = Stairway UP                 0x08 = Stairway DOWN
  0x09 = Stairway UP & DOWN          0x10 = Characters
  0x11 = Monsters                    0x12 = Treasure
  0x13 = Special                     0x14 = Room section
  0x15 = Unstable wall               0x20 = Corridor
  0x94 = Uncharted room section
  Flags: 0x80 = Locked, 0x40 = Magically Locked
"""

from enum import IntEnum


class Tile(IntEnum):
    EMPTY = 0x00
    DOOR_NS = 0x01
    DOOR_EW = 0x02
    SECRET_DOOR_NS = 0x05
    SECRET_DOOR_EW = 0x06
    STAIRS_UP = 0x07
    STAIRS_DOWN = 0x08
    STAIRS_BOTH = 0x09
    CHARACTERS = 0x10
    MONSTERS = 0x11
    TREASURE = 0x12
    SPECIAL = 0x13
    ROOM = 0x14
    UNSTABLE_WALL = 0x15
    CORRIDOR = 0x20
    UNCHARTED_ROOM = 0x94
    WALL = 0xFF


# Door flag bits (OR'd with door tile values)
LOCKED_FLAG = 0x80
MAGICALLY_LOCKED_FLAG = 0x40

# Tiles the player can walk on
WALKABLE_TILES = frozenset({
    Tile.EMPTY, Tile.DOOR_NS, Tile.DOOR_EW,
    Tile.STAIRS_UP, Tile.STAIRS_DOWN, Tile.STAIRS_BOTH,
    Tile.ROOM, Tile.CORRIDOR, Tile.UNCHARTED_ROOM,
    Tile.TREASURE, Tile.SPECIAL, Tile.CHARACTERS,
})

# Tiles that light/sight can pass through
# Doors are NOT transparent by default — they block sight until opened
TRANSPARENT_TILES = frozenset({
    Tile.EMPTY,
    Tile.STAIRS_UP, Tile.STAIRS_DOWN, Tile.STAIRS_BOTH,
    Tile.ROOM, Tile.CORRIDOR, Tile.UNCHARTED_ROOM,
    Tile.TREASURE, Tile.SPECIAL, Tile.CHARACTERS,
})


DOOR_TILES = frozenset({
    Tile.DOOR_NS, Tile.DOOR_EW,
    Tile.SECRET_DOOR_NS, Tile.SECRET_DOOR_EW,
})


def base_tile(tile_value: int) -> int:
    """Strip flag bits, returning the base tile type."""
    return tile_value & 0x3F


def is_door(tile_value: int) -> bool:
    """Check if a tile is any kind of door (base tile, ignoring flags)."""
    return base_tile(tile_value) in DOOR_TILES


def is_locked(tile_value: int) -> bool:
    """Check if a door has the locked flag."""
    return bool(tile_value & LOCKED_FLAG)


def is_magically_locked(tile_value: int) -> bool:
    """Check if a door has the magically locked flag."""
    return bool(tile_value & MAGICALLY_LOCKED_FLAG)


def has_door_flags(tile_value: int) -> bool:
    """Check if a tile has any door flags set."""
    return bool(tile_value & (LOCKED_FLAG | MAGICALLY_LOCKED_FLAG))


def unlock_door(tile_value: int) -> int:
    """Strip both lock flags from a door tile."""
    return tile_value & 0x3F


def is_walkable(tile_value: int) -> bool:
    if has_door_flags(tile_value) and is_door(tile_value):
        return False
    return tile_value in WALKABLE_TILES


def is_transparent(tile_value: int) -> bool:
    if has_door_flags(tile_value) and is_door(tile_value):
        return False
    return tile_value in TRANSPARENT_TILES
