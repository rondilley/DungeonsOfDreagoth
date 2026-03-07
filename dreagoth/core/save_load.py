"""Save/load system — JSON serialization for full game state."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import numpy as np

from dreagoth.core.game_state import GameState
from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.room import Room
from dreagoth.dungeon.populator import LevelEntities
from dreagoth.character.character import Character
from dreagoth.combat.spells import SpellSlots, ActiveBuff
from dreagoth.entities.item import Item, equipment_db
from dreagoth.entities.monster import Monster, monster_db
from dreagoth.entities.npc import NPC
from dreagoth.quest.quest import Quest, QuestLog, QuestType, QuestStatus, QuestReward

SAVE_DIR = Path(__file__).parent.parent.parent / "saves"
SAVE_VERSION = 2
NUM_SLOTS = 5

# Safety limits for deserialized data
_MAX_GRID_DIM = 200  # Max width/height for dungeon grids
_MAX_HP = 9999
_MAX_GOLD = 999_999
_MAX_XP = 999_999
_MAX_LEVEL = 20
_MAX_INVENTORY = 100
_MAX_QUESTS = 50
_MAX_MONSTERS = 200
_MAX_NPCS = 50


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def _ensure_dir() -> None:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)


def _validate_slot(slot: int) -> None:
    """Raise ValueError if slot is out of range."""
    if not isinstance(slot, int) or slot < 0 or slot >= NUM_SLOTS:
        raise ValueError(f"Invalid save slot: {slot} (must be 0-{NUM_SLOTS - 1})")


def _slot_path(slot: int) -> Path:
    _validate_slot(slot)
    return SAVE_DIR / f"save_slot_{slot}.json"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_item(item: Item) -> dict:
    return {"id": item.id}


def _deserialize_item(data: dict) -> Item | None:
    return equipment_db.get(data["id"])


def _serialize_character(char: Character) -> dict:
    return {
        "name": char.name,
        "char_class": char.char_class,
        "race": char.race,
        "level": char.level,
        "xp": char.xp,
        "strength": char.strength,
        "dexterity": char.dexterity,
        "constitution": char.constitution,
        "intelligence": char.intelligence,
        "wisdom": char.wisdom,
        "charisma": char.charisma,
        "hp": char.hp,
        "max_hp": char.max_hp,
        "gold": char.gold,
        "inventory": [_serialize_item(i) for i in char.inventory],
        "weapon": _serialize_item(char.weapon) if char.weapon else None,
        "armor": _serialize_item(char.armor) if char.armor else None,
        "shield": _serialize_item(char.shield) if char.shield else None,
        "helmet": _serialize_item(char.helmet) if char.helmet else None,
        "boots": _serialize_item(char.boots) if char.boots else None,
        "gloves": _serialize_item(char.gloves) if char.gloves else None,
        "ring": _serialize_item(char.ring) if char.ring else None,
        "amulet": _serialize_item(char.amulet) if char.amulet else None,
        "is_dead": char.is_dead,
        "spell_slots": {
            "max_slots": char.spell_slots.max_slots,
            "used_slots": char.spell_slots.used_slots,
        },
        "active_buffs": [
            {
                "spell_id": b.spell_id, "effect": b.effect,
                "value": b.value, "remaining_turns": b.remaining_turns,
                "regen_dice": b.regen_dice,
            }
            for b in char.active_buffs
        ],
    }


def _deserialize_character(data: dict) -> Character:
    # Validate class and race against known values
    from dreagoth.character.character import CLASS_DATA, RACE_DATA
    char_class = data["char_class"]
    race = data["race"]
    if char_class not in CLASS_DATA:
        raise ValueError(f"Unknown class: {char_class}")
    if race not in RACE_DATA:
        raise ValueError(f"Unknown race: {race}")

    char = Character(
        name=str(data["name"])[:40],  # Cap name length
        char_class=char_class,
        race=race,
        level=_clamp(int(data["level"]), 1, _MAX_LEVEL),
        xp=_clamp(int(data["xp"]), 0, _MAX_XP),
        strength=_clamp(int(data["strength"]), 1, 30),
        dexterity=_clamp(int(data["dexterity"]), 1, 30),
        constitution=_clamp(int(data["constitution"]), 1, 30),
        intelligence=_clamp(int(data["intelligence"]), 1, 30),
        wisdom=_clamp(int(data["wisdom"]), 1, 30),
        charisma=_clamp(int(data["charisma"]), 1, 30),
        hp=_clamp(int(data["hp"]), 0, _MAX_HP),
        max_hp=_clamp(int(data["max_hp"]), 1, _MAX_HP),
        gold=_clamp(int(data["gold"]), 0, _MAX_GOLD),
        is_dead=bool(data["is_dead"]),
    )
    # Inventory (capped)
    for item_data in data["inventory"][:_MAX_INVENTORY]:
        item = _deserialize_item(item_data)
        if item:
            char.inventory.append(item)
    # Equipment
    if data.get("weapon"):
        char.weapon = _deserialize_item(data["weapon"])
    if data.get("armor"):
        char.armor = _deserialize_item(data["armor"])
    if data.get("shield"):
        char.shield = _deserialize_item(data["shield"])
    if data.get("helmet"):
        char.helmet = _deserialize_item(data["helmet"])
    if data.get("boots"):
        char.boots = _deserialize_item(data["boots"])
    if data.get("gloves"):
        char.gloves = _deserialize_item(data["gloves"])
    if data.get("ring"):
        char.ring = _deserialize_item(data["ring"])
    if data.get("amulet"):
        char.amulet = _deserialize_item(data["amulet"])
    # Spell slots
    ss = data.get("spell_slots", {})
    char.spell_slots = SpellSlots(
        max_slots=ss.get("max_slots", [0, 0, 0]),
        used_slots=ss.get("used_slots", [0, 0, 0]),
    )
    # Buffs
    for b in data.get("active_buffs", []):
        char.active_buffs.append(ActiveBuff(
            spell_id=b["spell_id"], effect=b["effect"],
            value=b["value"], remaining_turns=b["remaining_turns"],
            regen_dice=b.get("regen_dice", ""),
        ))
    return char


def _serialize_room(room: Room) -> dict:
    return {
        "x": room.x, "y": room.y,
        "width": room.width, "height": room.height,
        "room_id": room.room_id,
    }


def _serialize_level(level: DungeonLevel) -> dict:
    return {
        "depth": level.depth,
        "width": level.width,
        "height": level.height,
        "grid": level.grid.tolist(),
        "rooms": [_serialize_room(r) for r in level.rooms],
        "stairs_up": list(level.stairs_up) if level.stairs_up else None,
        "stairs_down": list(level.stairs_down) if level.stairs_down else None,
    }


def _deserialize_level(data: dict) -> DungeonLevel:
    w = _clamp(int(data["width"]), 1, _MAX_GRID_DIM)
    h = _clamp(int(data["height"]), 1, _MAX_GRID_DIM)
    level = DungeonLevel(int(data["depth"]), w, h)
    grid_data = data["grid"]
    if not isinstance(grid_data, list) or len(grid_data) != h:
        raise ValueError("Grid data dimensions mismatch")
    level.grid = np.array(grid_data, dtype=np.uint8).reshape(h, w)
    for rd in data["rooms"][:100]:  # Cap rooms
        level.rooms.append(Room(
            x=int(rd["x"]), y=int(rd["y"]),
            width=int(rd["width"]), height=int(rd["height"]),
            room_id=int(rd["room_id"]),
        ))
    if data["stairs_up"]:
        level.stairs_up = tuple(data["stairs_up"])
    if data["stairs_down"]:
        level.stairs_down = tuple(data["stairs_down"])
    return level


def _serialize_monster(m: Monster) -> dict:
    return {
        "template_id": m.template_id,
        "hp": m.hp, "max_hp": m.max_hp,
        "x": m.x, "y": m.y,
        "is_dead": m.is_dead,
    }


def _deserialize_monster(data: dict) -> Monster | None:
    tid = data["template_id"]
    if tid not in monster_db.templates:
        return None
    t = monster_db.templates[tid]
    return Monster(
        template_id=tid, name=t.name,
        hp=data["hp"], max_hp=data["max_hp"],
        ac=t.ac, attack_bonus=t.attack_bonus, damage=t.damage,
        xp=t.xp, special=t.special, loot_tier=t.loot_tier,
        symbol=t.symbol, color=t.color,
        x=data["x"], y=data["y"], is_dead=data["is_dead"],
    )


def _serialize_npc(n: NPC) -> dict:
    return {
        "template_id": n.template_id,
        "x": n.x, "y": n.y,
        "talked_to": n.talked_to,
        "quest_id": n.quest_id,
    }


def _deserialize_npc(data: dict) -> NPC | None:
    from dreagoth.entities.npc import npc_db
    tid = data["template_id"]
    if tid not in npc_db.templates:
        return None
    npc = npc_db.spawn(tid, data["x"], data["y"])
    npc.talked_to = data.get("talked_to", False)
    npc.quest_id = data.get("quest_id")
    return npc


def _serialize_entities(ents: LevelEntities) -> dict:
    return {
        "monsters": [_serialize_monster(m) for m in ents.monsters],
        "treasure_piles": {
            f"{x},{y}": [_serialize_item(i) for i in items]
            for (x, y), items in ents.treasure_piles.items()
        },
        "gold_piles": {
            f"{x},{y}": gold
            for (x, y), gold in ents.gold_piles.items()
        },
        "npcs": [_serialize_npc(n) for n in ents.npcs],
    }


def _deserialize_entities(data: dict) -> LevelEntities:
    ents = LevelEntities()
    for md in data.get("monsters", [])[:_MAX_MONSTERS]:
        m = _deserialize_monster(md)
        if m:
            ents.monsters.append(m)
    for key, items_data in data.get("treasure_piles", {}).items():
        parts = key.split(",")
        if len(parts) != 2:
            continue
        x, y = int(parts[0]), int(parts[1])
        items = [_deserialize_item(d) for d in items_data[:_MAX_INVENTORY]]
        ents.treasure_piles[(x, y)] = [i for i in items if i]
    for key, gold in data.get("gold_piles", {}).items():
        parts = key.split(",")
        if len(parts) != 2:
            continue
        x, y = int(parts[0]), int(parts[1])
        ents.gold_piles[(x, y)] = _clamp(int(gold), 0, _MAX_GOLD)
    for nd in data.get("npcs", [])[:_MAX_NPCS]:
        n = _deserialize_npc(nd)
        if n:
            ents.npcs.append(n)
    ents.rebuild_indices()
    return ents


def _serialize_quest(q: Quest) -> dict:
    return {
        "id": q.id,
        "name": q.name,
        "description": q.description,
        "quest_type": q.quest_type.name,
        "status": q.status.name,
        "npc_id": q.npc_id,
        "target_id": q.target_id,
        "target_count": q.target_count,
        "target_depth": q.target_depth,
        "progress": q.progress,
        "reward": {
            "gold": q.reward.gold,
            "xp": q.reward.xp,
            "item_id": q.reward.item_id,
        },
    }


def _deserialize_quest(data: dict) -> Quest:
    try:
        qtype = QuestType[data["quest_type"]]
    except KeyError:
        qtype = QuestType.KILL_MONSTERS  # Fallback for removed types
    return Quest(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        quest_type=qtype,
        status=QuestStatus[data["status"]],
        npc_id=data.get("npc_id", ""),
        target_id=data.get("target_id", ""),
        target_count=data.get("target_count", 1),
        target_depth=data.get("target_depth", 0),
        progress=data.get("progress", 0),
        reward=QuestReward(
            gold=data["reward"]["gold"],
            xp=data["reward"]["xp"],
            item_id=data["reward"].get("item_id"),
        ),
    )


def _serialize_quest_log(ql: QuestLog) -> dict:
    return {
        "quests": [_serialize_quest(q) for q in ql.quests],
        "next_id": ql._next_id,
    }


def _deserialize_quest_log(data: dict) -> QuestLog:
    ql = QuestLog()
    for qd in data.get("quests", [])[:_MAX_QUESTS]:
        ql.quests.append(_deserialize_quest(qd))
    ql._next_id = data.get("next_id", len(ql.quests) + 1)
    return ql


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_game(gs: GameState, slot: int) -> bool:
    """Save game to a slot. Returns True on success."""
    _ensure_dir()
    try:
        data = {
            "version": SAVE_VERSION,
            "timestamp": datetime.now().isoformat(),
            "player_x": gs.player_x,
            "player_y": gs.player_y,
            "current_depth": gs.current_depth,
            "turn": gs.turn,
            "player": _serialize_character(gs.player) if gs.player else None,
            "levels": {
                str(d): _serialize_level(lv) for d, lv in gs.levels.items()
            },
            "entities": {
                str(d): _serialize_entities(ents) for d, ents in gs.entities.items()
            },
            "revealed": {
                str(d): [list(t) for t in tiles]
                for d, tiles in gs.revealed.items()
            },
            "visited_rooms": {
                str(d): list(rooms) for d, rooms in gs.visited_rooms.items()
            },
            "opened_doors": {
                str(d): [list(pos) for pos in doors]
                for d, doors in gs.opened_doors.items()
            },
            "quest_log": _serialize_quest_log(gs.quest_log) if gs.quest_log else None,
        }
        with open(_slot_path(slot), "w") as f:
            json.dump(data, f)
        return True
    except Exception:
        return False


def load_game(slot: int) -> GameState | None:
    """Load game from a slot. Returns None on failure."""
    path = _slot_path(slot)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)

        _migrate(data)

        gs = GameState()
        gs.player_x = data["player_x"]
        gs.player_y = data["player_y"]
        gs.current_depth = data["current_depth"]
        gs.turn = data["turn"]

        if data["player"]:
            gs.player = _deserialize_character(data["player"])

        for d_str, lv_data in data.get("levels", {}).items():
            gs.levels[int(d_str)] = _deserialize_level(lv_data)

        for d_str, ent_data in data.get("entities", {}).items():
            gs.entities[int(d_str)] = _deserialize_entities(ent_data)

        for d_str, tiles_data in data.get("revealed", {}).items():
            gs.revealed[int(d_str)] = {tuple(t) for t in tiles_data}

        for d_str, rooms_data in data.get("visited_rooms", {}).items():
            gs.visited_rooms[int(d_str)] = set(rooms_data)

        for d_str, doors_data in data.get("opened_doors", {}).items():
            gs.opened_doors[int(d_str)] = {tuple(pos) for pos in doors_data}

        if data.get("quest_log"):
            gs.quest_log = _deserialize_quest_log(data["quest_log"])
        else:
            gs.quest_log = QuestLog()

        return gs
    except Exception:
        return None


def list_saves() -> list[dict | None]:
    """Return metadata for all save slots."""
    _ensure_dir()
    result = []
    for slot in range(NUM_SLOTS):
        path = _slot_path(slot)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                player = data.get("player", {})
                result.append({
                    "slot": slot,
                    "name": player.get("name", "Unknown") if player else "Unknown",
                    "level": player.get("level", 1) if player else 1,
                    "depth": data.get("current_depth", 1),
                    "turn": data.get("turn", 0),
                    "timestamp": data.get("timestamp", ""),
                })
            except Exception:
                result.append(None)
        else:
            result.append(None)
    return result


def autosave(gs: GameState) -> bool:
    """Autosave to slot 0."""
    return save_game(gs, 0)


def _migrate(data: dict) -> None:
    """Migrate save data from older versions if needed."""
    version = data.get("version", 0)
    if version < 2:
        # v1 → v2: add new equipment slots to character
        player = data.get("player")
        if player:
            for slot in ("helmet", "boots", "gloves", "ring", "amulet"):
                player.setdefault(slot, None)
    data["version"] = SAVE_VERSION
