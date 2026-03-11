"""Central game state — player, levels, entities, combat, turn tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dreagoth.dungeon.dungeon_level import DungeonLevel
    from dreagoth.dungeon.populator import LevelEntities
    from dreagoth.character.character import Character
    from dreagoth.combat.combat_engine import CombatState
    from dreagoth.quest.quest import QuestLog


@dataclass
class GameState:
    player_x: int = 0
    player_y: int = 0
    current_depth: int = 1
    turn: int = 0

    # Character
    player: "Character | None" = None

    # Dungeon levels and exploration
    levels: dict[int, "DungeonLevel"] = field(default_factory=dict)
    entities: dict[int, "LevelEntities"] = field(default_factory=dict)
    revealed: dict[int, set[tuple[int, int]]] = field(default_factory=dict)
    visible: set[tuple[int, int]] = field(default_factory=set)
    visited_rooms: dict[int, set[int]] = field(default_factory=dict)
    opened_doors: dict[int, set[tuple[int, int]]] = field(default_factory=dict)

    # Rope connections from trap doors: depth -> {(x,y): (land_x, land_y) on depth+1}
    rope_connections: dict[int, dict[tuple[int, int], tuple[int, int]]] = field(
        default_factory=dict
    )

    # Player facing direction (dx, dy) for first-person view
    last_direction: tuple[int, int] = (0, -1)

    # Combat
    combat: "CombatState | None" = None

    # Quests
    quest_log: "QuestLog | None" = None

    # Messages
    messages: list[str] = field(default_factory=list)

    @property
    def current_level(self) -> "DungeonLevel":
        return self.levels[self.current_depth]

    @property
    def current_entities(self) -> "LevelEntities":
        return self.entities[self.current_depth]

    @property
    def in_combat(self) -> bool:
        return self.combat is not None

    def add_message(self, msg: str) -> None:
        self.messages.append(msg)
        # Keep only the most recent messages to prevent unbounded growth
        if len(self.messages) > 500:
            self.messages = self.messages[-200:]

    def ensure_revealed_set(self, depth: int) -> set[tuple[int, int]]:
        if depth not in self.revealed:
            self.revealed[depth] = set()
        return self.revealed[depth]

    def ensure_visited_rooms(self, depth: int) -> set[int]:
        if depth not in self.visited_rooms:
            self.visited_rooms[depth] = set()
        return self.visited_rooms[depth]

    def ensure_opened_doors(self, depth: int) -> set[tuple[int, int]]:
        if depth not in self.opened_doors:
            self.opened_doors[depth] = set()
        return self.opened_doors[depth]

    def ensure_rope_connections(self, depth: int) -> dict[tuple[int, int], tuple[int, int]]:
        if depth not in self.rope_connections:
            self.rope_connections[depth] = {}
        return self.rope_connections[depth]
