# Architecture

Technical architecture for Dungeons of Dreagoth II.

## System Overview

```
                         +-------------------+
                         |    DreagothApp    |  Textual App — game loop, input
                         +--------+----------+
                                  |
          +-----------+-----------+-----------+-----------+
          |           |           |           |           |
    +-----+----+ +----+----+ +---+----+ +----+----+ +----+----+
    | GameState | |Generator| |EventBus| |   DM    | | Combat  |
    +-----+----+ +----+----+ +--------+ +----+----+ | Engine  |
          |            |                      |      +----+----+
    +-----+----+ +----+----+           +-----+----+      |
    | Character | | Populat.| cache    | AIClient |  +---+----+
    | Inventory | +----+----+ -first-> | (Claude) |  | Monster |
    +-----+----+      |      |        +----------+  +---+----+
          |      +----+----+ |  +----------+             |
    +-----+----+ | Dungeon | +->| AICache  |       +-----+----+
    |  Items   | |  Level  |    | (SQLite) |       | MonsterDB|
    |EquipDB(56| | (numpy) | +->+----------+       |  (14)    |
    +----------+ +----+----+ |  +----------+       +----------+
                      |      +--| Fallback |
                 +----+----+    +----------+
                 |   FOV   |
                 +----------+
```

## Core Modules

### `core/constants.py`
All tuneable game parameters. Grid is 80x40 (expanded from original 80x24). Key values: `ROOMS_PER_LEVEL=25`, `FOV_RADIUS=8`, room sizes 3-8 x 3-6, `MAX_DUNGEON_DEPTH=10`.

### `core/events.py`
Synchronous pub/sub event bus. Single global instance `bus`. Components subscribe to named events (strings); publishers call `bus.publish("event_name", **data)`. Current events: `player_moved`.

### `core/game_state.py`
Central state dataclass. Fields:
- `player_x`, `player_y`, `current_depth`, `turn` — position and time
- `player: Character` — the player character with stats, inventory, equipment
- `levels: dict[int, DungeonLevel]` — lazily generated dungeon floors
- `entities: dict[int, LevelEntities]` — monsters and treasure per level
- `revealed`, `visible` — FOV/fog-of-war tile sets
- `visited_rooms` — tracks which rooms have been entered (for AI room descriptions)
- `combat: CombatState | None` — active combat encounter

### `core/dice.py`
Standard D&D dice: `d4` through `d100`, plus `ability_roll()` (4d6 drop lowest).

## Dungeon Generation

### Tile System (`dungeon/tiles.py`)

Preserves the original 1991 QBasic hex encoding as a Python `IntEnum`:

```
0x00  EMPTY              0x07  STAIRS_UP          0x14  ROOM
0x01  DOOR_NS            0x08  STAIRS_DOWN        0x15  UNSTABLE_WALL
0x02  DOOR_EW            0x09  STAIRS_BOTH        0x20  CORRIDOR
0x05  SECRET_DOOR_NS     0x10  CHARACTERS         0x94  UNCHARTED_ROOM
0x06  SECRET_DOOR_EW     0x11  MONSTERS           0xFF  WALL
                         0x12  TREASURE
                         0x13  SPECIAL
```

Door flags (OR'd): `0x80` = locked, `0x40` = magically locked.

Helper sets `WALKABLE_TILES` and `TRANSPARENT_TILES` used for movement and FOV checks.

### Grid Storage (`dungeon/dungeon_level.py`)

Each level is an 80x40 `numpy.uint8` array stored as `grid[y, x]` (row-major). The `DungeonLevel` class provides `__getitem__`/`__setitem__` with `(x, y)` interface, `in_bounds()`, and `can_walk()`. Also stores room list and stair positions.

### Generation Algorithm (`dungeon/generator.py`)

Ported from `Old_Code/DUNGEON.TXT` with improvements:

1. **Initialize** — fill grid with `WALL` (0xFF)
2. **Place rooms** — up to 25 per level. Random position/size, collision detection with 1-tile buffer, retry up to 500 times per room. Room interiors set to `ROOM` (0x14)
3. **Connect rooms** — Prim's MST on room centers (Manhattan distance). For each MST edge, carve an L-shaped corridor (randomly horizontal-first or vertical-first). Only overwrites `WALL` tiles
4. **Place stairs** — pick two random distinct rooms, place `STAIRS_UP`/`STAIRS_DOWN` at their centers

**Key improvement over original:** The 1991 code only connected up/down stairs with a DFS path, leaving most rooms unreachable. MST guarantees full connectivity.

### Corridor Carving (`dungeon/corridor.py`)

L-shaped corridors between two points. Randomly chooses horizontal-then-vertical or vertical-then-horizontal. Carves `CORRIDOR` tiles only through `WALL` cells.

### Field of View (`dungeon/fov.py`)

Recursive 8-octant shadowcasting algorithm (RogueBasin reference). Uses octant coordinate transform multipliers to scan all directions symmetrically.

Key detail: slopes use `dy = -j` (negative depth convention). The algorithm tracks start/end slopes per scan row, recursing when walls create shadow boundaries.

Returns a `set[tuple[int, int]]` of visible positions. The app merges this into a persistent `revealed` set for fog-of-war.

### Dungeon Populator (`dungeon/populator.py`)

After a level is generated, `populate_level()` fills it with monsters and treasure:
- Each non-stair room has a 50%+ chance of a monster (scales with depth)
- 30% chance of gold in each room, plus a chance for equipment drops
- Returns a `LevelEntities` dataclass with `monster_at(x, y)` for collision lookup
- Stair rooms are kept empty as safe zones

## Character System

### Character (`character/character.py`, 217 lines)

Core player data and mechanics:

- **4 classes** — Fighter (1d10 HP, +1 atk/level), Mage (1d4 HP, +0.5 atk/level), Thief (1d6 HP), Cleric (1d8 HP). Defined in `CLASS_DATA` dict
- **4 races** — Human (no mods), Elf (+1 DEX/INT, -1 CON), Dwarf (+2 CON, -1 CHA), Halfling (+2 DEX, -1 STR). Defined in `RACE_DATA` dict
- **6 ability scores** — rolled with 4d6-drop-lowest, modified by race
- **AC calculation** — 10 + dex_mod + armor.ac_bonus + shield.ac_bonus
- **Attack bonus** — level * class multiplier + str_mod
- **Equipment slots** — weapon, armor (body), shield. Class restrictions enforced on equip
- **Leveling** — 10-level XP table. Level-up adds hit die + CON mod to max HP

`create_character(name, class, race)` rolls a complete character with starting gold (3d6 * 10). The `CharacterCreationScreen` modal in `app.py` also assigns starting equipment per class.

### Items and Equipment (`entities/item.py`, 120 lines)

- **`Item` dataclass** — id, name, category, price/currency, damage dice (weapons), AC bonus (armor), slot, class restrictions
- **`EquipmentDB` singleton** — loads `data/equipment.json` (56 items: 24 weapons, 14 armor, 5 clothing, 5 provisions, 8 misc)
- **`parse_dice()` / `roll_dice()`** — parses "2d6+1" format strings and rolls them
- **`random_treasure(tier)`** — generates loot appropriate to dungeon depth
- Gold values normalized across currencies (G=gold, S=silver/10, C=copper/100)

## Combat System

### Combat Engine (`combat/combat_engine.py`, 157 lines)

Turn-based D&D-style combat:

```
Combat Start:
  Roll initiative: d20 + dex_mod (player) vs d20 (monster)
  Higher goes first. If monster wins, it gets a free attack.

Each Round:
  Player chooses: Attack (F) or Flee (R)

  Attack:
    Roll d20 + attack_bonus
    Natural 20 = CRITICAL HIT (2x damage)
    Natural 1 = FUMBLE (auto-miss)
    If roll >= monster AC → hit, roll damage dice + str_mod
    If monster HP <= 0 → PLAYER_WIN

  Flee:
    Roll d20 + dex_mod vs DC 10
    Success → PLAYER_FLED (combat ends)
    Failure → monster gets free attack

  Monster Attack:
    Roll d20 + attack_bonus vs player AC
    Same crit/fumble rules
    Special abilities (30% poison, 20% paralyze, 15% drain)
    If player HP <= 0 → PLAYER_DEAD
```

**`CombatState`** tracks the full fight: player, monster, round counter, result enum, and a combat log of styled text entries. The app flushes log entries to the narrative panel after each action.

**`CombatResult`** enum: `ONGOING`, `PLAYER_WIN`, `PLAYER_FLED`, `PLAYER_DEAD`.

### Monsters (`entities/monster.py`, 103 lines)

- **`MonsterTemplate`** — static stats from `data/monsters.json`
- **`Monster`** — live instance with HP, position, damage. Created via `MonsterDB.spawn()`
- **14 types** scaling across levels 1-10:

| Monster | Levels | HP | AC | Damage | Special | XP |
|---------|--------|-----|-----|--------|---------|-----|
| Giant Rat | 1-3 | 1d4 | 7 | 1d3 | — | 5 |
| Giant Bat | 1-3 | 1d4 | 8 | 1d2 | — | 5 |
| Kobold | 1-4 | 1d4 | 7 | 1d4 | — | 7 |
| Goblin | 1-5 | 1d6 | 6 | 1d6 | — | 10 |
| Skeleton | 2-6 | 1d8 | 7 | 1d6 | undead | 15 |
| Zombie | 2-6 | 2d8 | 8 | 1d8 | undead | 20 |
| Orc | 2-7 | 1d8 | 6 | 1d8 | — | 25 |
| Giant Spider | 3-7 | 2d8 | 6 | 1d6 | poison | 30 |
| Hobgoblin | 3-8 | 1d8+1 | 5 | 1d8 | — | 35 |
| Ghoul | 4-8 | 2d8 | 6 | 1d6+1 | paralyze | 50 |
| Ogre | 4-9 | 4d8 | 5 | 1d10 | — | 75 |
| Wight | 5-9 | 4d8 | 5 | 1d8 | drain | 100 |
| Troll | 6-10 | 6d8 | 4 | 2d6 | regen | 150 |
| Minotaur | 7-10 | 6d8 | 4 | 2d6+2 | charge | 200 |

Each monster has a unique single-character symbol and color for the map display.

## AI Dungeon Master

### Design Principles
1. **AI is narration-only** — never affects combat math, movement, or dice
2. **Cache-first** — SQLite prevents duplicate API calls for the same content
3. **Always falls back** — game is 100% playable without an API key

### Architecture

```
DungeonMaster.describe_room(depth, room_id, size)
    │
    ├─ 1. Check AICache (SQLite, keyed by SHA-256 of content_type:context)
    │     └─ HIT → return cached text
    │
    ├─ 2. Try AIClient (Anthropic SDK, Claude Sonnet)
    │     ├─ SUCCESS → cache result, return text
    │     └─ FAIL → fall through
    │
    └─ 3. get_fallback(category) → random template from JSON
```

### Modules

**`ai/client.py`** (79 lines) — Wraps Anthropic SDK. Reads API key from `claude.key.txt` (project root) or `ANTHROPIC_API_KEY` env var. Tracks input/output tokens for cost estimation. Uses Claude Sonnet for speed and cost (~$0.15-0.50 per full playthrough).

**`ai/cache.py`** (52 lines) — SQLite database at `saves/ai_cache.db`. Keys are `"{content_type}:{sha256_hash}"`. Content types: `room_enter`, `combat_start`, `combat_kill`, `combat_crit`, `level_theme`, `treasure_find`.

**`ai/fallback.py`** (30 lines) — Loads `data/fallback_descriptions.json` and returns random entries per category. Lazy-loaded on first call.

**`ai/dm.py`** (151 lines) — `DungeonMaster` singleton orchestrates all AI narration:
- `describe_room()` — triggered on first visit to each room
- `narrate_combat_start()` — when bumping into a monster
- `narrate_kill()` — on monster death (includes weapon name)
- `narrate_crit()` — on critical hits
- `describe_level_theme()` — when descending to a new level
- `describe_treasure()` — when picking up loot

All methods share the same system prompt establishing tone (dark fantasy, second person, 1-3 sentences, no emojis).

## UI Architecture

Built on [Textual](https://textual.textualize.io/), a Python TUI framework built on Rich.

### Layout

```
+--------------------------------------------------+--------------------+
|                   MapPanel                        |    StatsPanel      |
|                  (1fr width)                      |   (26 cols wide)   |
|                                                   |                    |
|  @ player (bright yellow)                         |  Name, L#, race,   |
|  r/g/k/s monsters (colored symbols)              |  class              |
|  $ treasure (bright yellow)                       |  HP bar (colored)   |
|  . rooms, , corridors (grey shades)              |  STR DEX CON        |
|  ▲▼ stairs (bright cyan)                         |  INT WIS CHA        |
|  dim = previously seen, blank = unexplored        |  AC, Atk bonus      |
|                                                   |  Weapon, Armor      |
|                                                   |  Gold, XP           |
|                                                   |  Pack item count    |
|                                                   |  [COMBAT indicator] |
+--------------------------------------------------+--------------------+
|                     LogPanel (10 rows)                                 |
|  AI room descriptions (italic grey)                                   |
|  Combat narration (red/green/yellow)                                  |
|  Item pickups (yellow), level changes (cyan)                          |
+----------------------------------------------------------------------+
| CommandBar (1 row, docked bottom) — level, turn, position             |
+----------------------------------------------------------------------+
```

### Key Bindings

| Key | Action | Context |
|-----|--------|---------|
| W/S/A/D, Arrows | Move | Exploration |
| F | Attack | Combat |
| R | Flee | Combat |
| G | Pick up items | On treasure tile |
| I | Show inventory | Any time |
| < (comma) | Ascend stairs | On up stairs |
| > (period) | Descend stairs | On down stairs |
| Q | Quit | Any time |

### Rendering Pipeline

1. Player input triggers `action_move()`, `action_combat_attack()`, `action_use_stairs()`, etc.
2. Game state updates: position, turn counter, level generation, combat state
3. `compute_fov()` recalculates visible tiles
4. Visible set merged into persistent revealed set
5. AI DM triggers: room entry check, combat narration, level themes
6. Each widget's reactive `turn` property incremented, triggering `render()`
7. `MapPanel.render()` builds Rich `Text` — player, monsters, treasure, tiles by visibility
8. `StatsPanel.render()` builds Rich `Text` — full character sheet with HP bar, abilities, equipment, combat indicator
9. Log entries written to `RichLog` for scrollable history

### Widget Communication

Widgets hold a reference to `GameState` (set via `set_game_state()`). The app calls `refresh_map()`/`refresh_stats()`/`refresh_bar()` which increment reactive counters to trigger re-renders. Log messages go through `RichLog.write()`.

### Modal Screens

**`CharacterCreationScreen`** — Shown on app mount. Collects name (Input), class (Select), race (Select). On submit, calls `create_character()`, assigns starting equipment by class (Fighter=Long Sword+Chain, Mage=Staff, Thief=Dagger+Leather, Cleric=Mace+Scale), then returns character via `dismiss()`.

## Data Flow

### Exploration
```
Key Press → action_move(direction)
  → Check monster at destination → start combat if found
  → Move player, increment turn
  → compute_fov() → visible set → revealed set
  → Check ground items → notify player
  → Check room entry → AI describe_room() if new
  → Random corridor encounter (3% chance)
  → EventBus.publish("player_moved")
  → All widgets refresh
```

### Combat
```
Monster bump or corridor encounter → _start_combat(monster)
  → DM.narrate_combat_start()
  → CombatState.start() (roll initiative)
  → Player presses F → CombatState.player_attack()
    → d20 + attack_bonus vs monster AC
    → On hit: roll damage, check monster death
    → Monster retaliates: d20 + attack_bonus vs player AC
    → Special abilities (poison/paralyze/drain)
  → PLAYER_WIN → gain XP, loot drop, DM.narrate_kill()
  → PLAYER_DEAD → game over message
  → PLAYER_FLED → combat ends, continue exploring
```

### AI Narration
```
Game event (room enter, combat, kill, level change, treasure)
  → DM method called
  → Check SQLite cache (SHA-256 key)
  → If miss: try Claude Sonnet API → cache result
  → If API unavailable: random template from fallback JSON
  → Return text → _log() to narrative panel
```

## Future Architecture (Phases 5-6)

### Phase 5: NPCs + Quests
`entities/npc.py` with AI-driven dialogue and personality. Quest system (fetch/kill/explore) with AI-generated objectives. `combat/spells.py` for Mage/Cleric casting.

### Phase 6: Polish
JSON save/load with versioned migration. ASCII first-person corridor view ported from `DUNGMAKE.TXT`. Locked/magically locked door mechanics, minimap, full command parser. Test suite expansion.
