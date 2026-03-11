"""Game constants — grid dimensions, generation params, gameplay settings."""

# Grid dimensions (expanded from original 80x24)
GRID_WIDTH = 80
GRID_HEIGHT = 40

# Room generation
ROOMS_PER_LEVEL = 25
MIN_ROOM_WIDTH = 3
MAX_ROOM_WIDTH = 8
MIN_ROOM_HEIGHT = 3
MAX_ROOM_HEIGHT = 6
ROOM_BUFFER = 1  # Min gap between rooms
MAX_ROOM_ATTEMPTS = 500  # Retries per room before giving up

# Player
FOV_RADIUS = 8
STARTING_LEVEL = 1
MAX_DUNGEON_DEPTH = 25

# Race darkvision bonus (added to FOV_RADIUS)
RACE_DARKVISION: dict[str, int] = {
    "human": 0,
    "elf": 2,      # Keen elven sight
    "dwarf": 3,    # Dwarves are at home in the dark
    "halfling": 1,  # Slightly better than human
}

# Directions (dx, dy)
NORTH = (0, -1)
SOUTH = (0, 1)
EAST = (1, 0)
WEST = (-1, 0)
DIRECTIONS = {"north": NORTH, "south": SOUTH, "east": EAST, "west": WEST}
