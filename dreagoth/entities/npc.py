"""NPC data models and spawning."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class NPCTemplate:
    """Static NPC definition loaded from JSON."""
    id: str
    name: str
    role: str  # merchant, quest_giver, sage, wanderer
    personality: str
    min_level: int
    max_level: int
    symbol: str
    color: str
    inventory_tier: str | None
    dialogue_tags: list[str]


@dataclass
class NPC:
    """A live NPC instance in the dungeon."""
    template_id: str
    name: str
    role: str
    personality: str
    symbol: str
    color: str
    inventory_tier: str | None
    dialogue_tags: list[str]
    x: int = 0
    y: int = 0
    talked_to: bool = False
    quest_id: str | None = None


class NPCDB:
    """Database of NPC templates loaded from JSON."""

    def __init__(self) -> None:
        self.templates: dict[str, NPCTemplate] = {}
        self._eligible_cache: dict[int, list[NPCTemplate]] = {}
        self._load()

    def _load(self) -> None:
        path = DATA_DIR / "npcs.json"
        with open(path) as f:
            data = json.load(f)
        for n in data["npcs"]:
            t = NPCTemplate(**n)
            self.templates[t.id] = t
        self._max_defined_level = max(t.max_level for t in self.templates.values())

    def spawn(self, template_id: str, x: int, y: int) -> NPC:
        t = self.templates[template_id]
        return NPC(
            template_id=t.id, name=t.name, role=t.role,
            personality=t.personality, symbol=t.symbol, color=t.color,
            inventory_tier=t.inventory_tier, dialogue_tags=list(t.dialogue_tags),
            x=x, y=y,
        )

    def eligible_for_level(self, depth: int) -> list[NPCTemplate]:
        # Clamp to highest defined level so deep floors still have NPCs
        clamped = min(depth, self._max_defined_level)
        if depth not in self._eligible_cache:
            self._eligible_cache[depth] = [
                t for t in self.templates.values()
                if t.min_level <= clamped <= t.max_level
            ]
        return self._eligible_cache[depth]

    def random_for_level(self, depth: int, x: int, y: int) -> NPC | None:
        eligible = self.eligible_for_level(depth)
        if not eligible:
            return None
        template = random.choice(eligible)
        return self.spawn(template.id, x, y)


# Singleton
npc_db = NPCDB()
