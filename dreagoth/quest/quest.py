"""Quest system — types, tracking, and generation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto


class QuestType(Enum):
    KILL_MONSTERS = auto()
    EXPLORE_DEPTH = auto()


class QuestStatus(Enum):
    ACTIVE = auto()
    COMPLETED = auto()
    TURNED_IN = auto()


@dataclass
class QuestReward:
    gold: int = 0
    xp: int = 0
    item_id: str | None = None


@dataclass
class Quest:
    """A single quest with objectives and progress tracking."""
    id: str
    name: str
    description: str
    quest_type: QuestType
    status: QuestStatus = QuestStatus.ACTIVE
    npc_id: str = ""

    # Objectives
    target_id: str = ""  # monster template_id, item_id, or ""
    target_count: int = 1
    target_depth: int = 0  # for EXPLORE_DEPTH
    progress: int = 0

    reward: QuestReward = field(default_factory=QuestReward)

    @property
    def is_complete(self) -> bool:
        if self.quest_type == QuestType.EXPLORE_DEPTH:
            return self.progress >= self.target_depth
        return self.progress >= self.target_count

    def check_complete(self) -> bool:
        """Update status if complete. Returns True if just completed."""
        if self.status == QuestStatus.ACTIVE and self.is_complete:
            self.status = QuestStatus.COMPLETED
            return True
        return False


class QuestLog:
    """Tracks all active and completed quests."""

    def __init__(self) -> None:
        self.quests: list[Quest] = []
        self._next_id: int = 1

    def add(self, quest: Quest) -> None:
        self.quests.append(quest)

    @property
    def active(self) -> list[Quest]:
        return [q for q in self.quests if q.status == QuestStatus.ACTIVE]

    @property
    def completed(self) -> list[Quest]:
        return [q for q in self.quests if q.status == QuestStatus.COMPLETED]

    @property
    def turned_in(self) -> list[Quest]:
        return [q for q in self.quests if q.status == QuestStatus.TURNED_IN]

    def on_monster_killed(self, template_id: str) -> list[Quest]:
        """Update kill quests. Returns list of newly completed quests."""
        newly_complete = []
        for q in self.active:
            if q.quest_type == QuestType.KILL_MONSTERS and q.target_id == template_id:
                q.progress += 1
                if q.check_complete():
                    newly_complete.append(q)
        return newly_complete

    def on_depth_reached(self, depth: int) -> list[Quest]:
        """Update explore quests. Returns list of newly completed quests."""
        newly_complete = []
        for q in self.active:
            if q.quest_type == QuestType.EXPLORE_DEPTH:
                q.progress = max(q.progress, depth)
                if q.check_complete():
                    newly_complete.append(q)
        return newly_complete

    def quest_for_npc(self, npc_id: str) -> Quest | None:
        """Find an active or completed quest from a specific NPC."""
        for q in self.quests:
            if q.npc_id == npc_id and q.status in (QuestStatus.ACTIVE, QuestStatus.COMPLETED):
                return q
        return None

    def generate_id(self) -> str:
        qid = f"quest_{self._next_id}"
        self._next_id += 1
        return qid


# Monster targets for kill quests by depth range
_KILL_TARGETS = [
    (1, 3, ["rat", "bat", "kobold"]),
    (2, 5, ["goblin", "skeleton", "zombie"]),
    (3, 7, ["orc", "spider_giant"]),
    (4, 8, ["hobgoblin", "ghoul"]),
    (5, 10, ["ogre", "wight", "troll", "minotaur"]),
]

# Names for generated quests
_KILL_NAMES = [
    "Pest Control", "Monster Bounty", "Clear the Depths",
    "Hunter's Task", "Extermination Order",
]
_EXPLORE_NAMES = [
    "Depths Unknown", "Into the Abyss", "Cartographer's Request",
    "Scouting Mission", "Deep Reconnaissance",
]


def generate_quest(depth: int, npc_id: str, quest_log: QuestLog) -> Quest:
    """Generate a random quest appropriate for the given depth."""
    qtype = random.choice([QuestType.KILL_MONSTERS, QuestType.EXPLORE_DEPTH])

    qid = quest_log.generate_id()

    if qtype == QuestType.KILL_MONSTERS:
        # Find eligible targets
        eligible = []
        for min_d, max_d, targets in _KILL_TARGETS:
            if min_d <= depth <= max_d:
                eligible.extend(targets)
        if not eligible:
            eligible = ["rat", "goblin"]
        target = random.choice(eligible)
        count = random.randint(2, 4)
        name = random.choice(_KILL_NAMES)

        return Quest(
            id=qid, name=name,
            description=f"Slay {count} {target.replace('_', ' ')}s",
            quest_type=QuestType.KILL_MONSTERS,
            npc_id=npc_id,
            target_id=target, target_count=count,
            reward=QuestReward(
                gold=count * 10 * depth,
                xp=count * 15 * depth,
            ),
        )
    else:
        target_depth = depth + random.randint(1, 3)
        name = random.choice(_EXPLORE_NAMES)

        return Quest(
            id=qid, name=name,
            description=f"Reach dungeon level {target_depth}",
            quest_type=QuestType.EXPLORE_DEPTH,
            npc_id=npc_id,
            target_depth=target_depth,
            reward=QuestReward(
                gold=target_depth * 20,
                xp=target_depth * 25,
            ),
        )
