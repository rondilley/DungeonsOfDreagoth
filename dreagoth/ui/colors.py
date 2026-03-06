"""Color and style definitions for dungeon tile rendering."""

from dreagoth.dungeon.tiles import Tile

# Map tile -> (character, Rich style)
TILE_APPEARANCE: dict[int, tuple[str, str]] = {
    Tile.WALL:           ("\u2588", "grey37"),          # █ solid block
    Tile.ROOM:           ("\u00b7", "grey70"),           # · dot
    Tile.CORRIDOR:       ("\u00b7", "grey50"),           # · dot dimmer
    Tile.STAIRS_UP:      ("\u25b2", "bold bright_cyan"), # ▲
    Tile.STAIRS_DOWN:    ("\u25bc", "bold bright_cyan"), # ▼
    Tile.STAIRS_BOTH:    ("\u2666", "bold bright_cyan"), # ♦
    Tile.DOOR_NS:        ("+", "bold yellow"),
    Tile.DOOR_EW:        ("+", "bold yellow"),
    Tile.SECRET_DOOR_NS: ("\u2588", "grey37"),           # Looks like wall
    Tile.SECRET_DOOR_EW: ("\u2588", "grey37"),
    Tile.TREASURE:       ("$", "bold bright_yellow"),
    Tile.MONSTERS:       ("M", "bold bright_red"),
    Tile.SPECIAL:        ("!", "bold bright_magenta"),
    Tile.CHARACTERS:     ("@", "bold bright_green"),
    Tile.EMPTY:          (" ", ""),
    Tile.UNSTABLE_WALL:  ("\u2591", "grey42"),           # ░
    Tile.UNCHARTED_ROOM: ("\u00b7", "grey62"),
}

PLAYER_CHAR = "@"
PLAYER_STYLE = "bold bright_yellow"

# Direction (dx, dy) -> arrow character for player facing
PLAYER_ARROWS: dict[tuple[int, int], str] = {
    (0, -1): "^",   # North
    (0, 1):  "v",   # South
    (1, 0):  ">",   # East
    (-1, 0): "<",   # West
}

FOG_DIM = "dim"
