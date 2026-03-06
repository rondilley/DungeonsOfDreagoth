"""Room data structure for dungeon generation."""

from dataclasses import dataclass


@dataclass
class Room:
    """A rectangular room in the dungeon."""
    x: int          # Top-left corner X
    y: int          # Top-left corner Y
    width: int      # Interior width
    height: int     # Interior height
    room_id: int = 0

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def center(self) -> tuple[int, int]:
        return (self.center_x, self.center_y)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def intersects(self, other: "Room", buffer: int = 1) -> bool:
        """Check if this room overlaps another (with buffer gap)."""
        return not (
            self.x + self.width + buffer <= other.x
            or other.x + other.width + buffer <= self.x
            or self.y + self.height + buffer <= other.y
            or other.y + other.height + buffer <= self.y
        )
