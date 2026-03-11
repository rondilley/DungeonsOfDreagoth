"""Monster data models and spawning."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from dreagoth.entities.item import roll_dice

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class MonsterTemplate:
    id: str
    name: str
    min_level: int
    max_level: int
    hp_dice: str
    ac: int
    attack_bonus: int
    damage: str
    xp: int
    speed: int
    special: str | None
    loot_tier: int
    symbol: str
    color: str


@dataclass
class Monster:
    """A live monster instance in the dungeon."""
    template_id: str
    name: str
    hp: int
    max_hp: int
    ac: int
    attack_bonus: int
    damage: str
    xp: int
    special: str | None
    loot_tier: int
    symbol: str
    color: str
    speed: int = 9
    x: int = 0
    y: int = 0
    is_dead: bool = False
    is_alert: bool = False

    def roll_damage(self) -> int:
        return max(1, roll_dice(self.damage))

    def take_damage(self, amount: int) -> int:
        actual = min(amount, self.hp)
        self.hp -= actual
        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
        return actual


class MonsterDB:
    """Database of monster templates loaded from JSON."""

    def __init__(self) -> None:
        self.templates: dict[str, MonsterTemplate] = {}
        self._eligible_cache: dict[int, list[MonsterTemplate]] = {}
        self._load()

    def _load(self) -> None:
        path = DATA_DIR / "monsters.json"
        with open(path) as f:
            data = json.load(f)
        for m in data["monsters"]:
            t = MonsterTemplate(**m)
            self.templates[t.id] = t
        self._max_defined_level = max(t.max_level for t in self.templates.values())

    def spawn(self, template_id: str, x: int, y: int) -> Monster:
        t = self.templates[template_id]
        hp = max(1, roll_dice(t.hp_dice))
        return Monster(
            template_id=t.id, name=t.name,
            hp=hp, max_hp=hp, ac=t.ac,
            attack_bonus=t.attack_bonus, damage=t.damage,
            xp=t.xp, special=t.special, loot_tier=t.loot_tier,
            symbol=t.symbol, color=t.color, speed=t.speed,
            x=x, y=y,
        )

    def eligible_for_level(self, depth: int) -> list[MonsterTemplate]:
        # Clamp to highest defined level so deep floors still have monsters
        clamped = min(depth, self._max_defined_level)
        if depth not in self._eligible_cache:
            self._eligible_cache[depth] = [
                t for t in self.templates.values()
                if t.min_level <= clamped <= t.max_level
            ]
        return self._eligible_cache[depth]

    def random_for_level(self, depth: int, x: int, y: int) -> Monster | None:
        eligible = self.eligible_for_level(depth)
        if not eligible:
            return None
        template = random.choice(eligible)
        return self.spawn(template.id, x, y)


monster_db = MonsterDB()
