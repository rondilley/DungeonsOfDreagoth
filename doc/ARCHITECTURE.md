# Architecture

Technical architecture for Dungeons of Dreagoth II.

## System Overview

```mermaid
graph TD
    App[DreagothApp<br/>Textual App — game loop, input]

    App --> GS[GameState]
    App --> Gen[Generator]
    App --> EB[EventBus]
    App --> DM[DungeonMaster]
    App --> CE[CombatEngine]
    App --> MonAI[Monster AI<br/>Detection + BFS]

    GS --> Char[Character<br/>Inventory, Light]
    GS --> SL[Save/Load<br/>JSON, 5 slots, v3]
    Char --> Items[Items<br/>EquipmentDB 84]
    Char --> MagicItems[Magic Items<br/>UniqueItemDB]

    Gen --> Pop[Populator]
    Pop --> DL[DungeonLevel<br/>numpy 80x40]
    Pop --> NPCs[NPC DB 11]
    Pop --> Traps[Trap System<br/>5 types]
    DL --> FOV[FOV<br/>Shadowcasting +<br/>Darkvision + Light]

    DM -->|cache-first| AIC[AIClient<br/>Claude Sonnet]
    DM -->|cache hit| Cache[AICache<br/>SQLite]
    DM -->|API fail| FB[Fallback<br/>Templates]

    CE --> Mon[Monster<br/>MonsterDB 30]
    CE --> Spells[SpellDB 12<br/>Mage + Cleric]
    CE --> Quests[QuestLog<br/>Kill / Explore]

    MonAI --> Noise[Noise System<br/>Class + Race + Armor<br/>+ Light + Doors]
    MonAI --> BFS[BFS Pathfinding<br/>Opened doors only]

    App --> Audio[SoundManager<br/>Event-driven]
```

## Core Modules

### `core/constants.py`
All tuneable game parameters. Grid is 80x40 (expanded from original 80x24). Key values: `ROOMS_PER_LEVEL=25`, `FOV_RADIUS=8`, room sizes 3-8 x 3-6. Dungeon depth is unlimited — monsters and NPCs scale through level 14+. `RACE_DARKVISION` dict: human=0, elf=2, dwarf=3, halfling=1.

### `core/events.py`
Synchronous pub/sub event bus. Single global instance `bus`. Components subscribe to named events (strings); publishers call `bus.publish("event_name", **data)`. Exception-safe: handler errors are caught and don't kill other handlers. Publish iterates over a list copy to allow handler self-removal during iteration. Safe unsubscribe (no crash on missing handler).

### `core/game_state.py`
Central state dataclass. Fields:
- `player_x`, `player_y`, `current_depth`, `turn` — position and time
- `player: Character` — the player character with stats, inventory, equipment, light tracking
- `levels: dict[int, DungeonLevel]` — lazily generated dungeon floors
- `entities: dict[int, LevelEntities]` — monsters, treasure, NPCs, and traps per level
- `revealed`, `visible` — FOV/fog-of-war tile sets
- `visited_rooms` — tracks which rooms have been entered (for AI room descriptions)
- `combat: CombatState | None` — active combat encounter
- `rope_connections: dict[int, dict[tuple, tuple]]` — bidirectional trap door rope links
- `opened_doors` — set of door positions per depth that have been opened

### `core/dice.py`
Standard D&D dice: `d4` through `d100`, plus `ability_roll()` (4d6 drop lowest).

### `core/save_load.py`
JSON serialization to `saves/` directory. 5 manual slots + autosave (slot 0). Items stored by ID (not value) to keep saves small and auto-apply balance changes. Version field for migration (currently v3). Validates spell slots (clamped to 0-7), rope connection landings (must be 2-element), trap types (invalid types skipped). Serializes traps, rope connections, light_remaining, monster alert state, and magic item properties.

### `core/command_parser.py`
25 commands with aliases and tab completion. Vi-style `:` activates input mode in CommandBar.

### `core/noise.py`
Noise and stealth system determining how easily monsters detect the player:
- **Class base noise:** fighter=3, cleric=2, mage=1, thief=0
- **Race modifier:** human=0, elf=-1, dwarf=+1, halfling=-1
- **Armor weight:** heavy (AC>=5)=+3, medium (AC>=3)=+2, light (AC>=1)=+1
- **Light sources:** +3 if carrying active light (torch, lantern, or Light spell)
- **Closed door attenuation:** each closed door between monster and player reduces effective detection range by 4 tiles (via Bresenham line check)
- **Detection radius:** `monster_speed // 3 + player_noise`, clamped to [3, 12]

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

Door flags (OR'd): `0x80` = locked, `0x40` = magically locked. Helpers: `is_door()`, `is_locked()`, `is_magically_locked()`, `unlock_door()`, `base_tile()`. Flag-aware `is_walkable()` / `is_transparent()`.

### Grid Storage (`dungeon/dungeon_level.py`)

Each level is an 80x40 `numpy.uint8` array stored as `grid[y, x]` (row-major). The `DungeonLevel` class provides `__getitem__`/`__setitem__` with `(x, y)` interface, `in_bounds()`, and `can_walk()`. Also stores room list and stair positions.

### Generation Algorithm (`dungeon/generator.py`)

Ported from `Old_Code/DUNGEON.TXT` with improvements:

```mermaid
flowchart TD
    A[Initialize grid with WALL 0xFF] --> B[Place rooms]
    B -->|up to 25 per level<br/>random pos/size<br/>collision detect w/ 1-tile buffer| C[Connect rooms via Prim's MST]
    C -->|Manhattan distance<br/>L-shaped corridors| D[Place stairs]
    D -->|two random distinct rooms<br/>STAIRS_UP / STAIRS_DOWN| E[Place doors]
    E -->|between rooms and corridors<br/>locked / magically locked| F[Level complete]
```

**Key improvement over original:** The 1991 code only connected up/down stairs with a DFS path, leaving most rooms unreachable. MST guarantees full connectivity.

### Corridor Carving (`dungeon/corridor.py`)

L-shaped corridors between two points. Randomly chooses horizontal-then-vertical or vertical-then-horizontal. Carves `CORRIDOR` tiles only through `WALL` cells.

### Field of View (`dungeon/fov.py`)

Recursive 8-octant shadowcasting algorithm (RogueBasin reference). Uses octant coordinate transform multipliers to scan all directions symmetrically.

Key detail: slopes use `dy = -j` (negative depth convention). The algorithm tracks start/end slopes per scan row, recursing when walls create shadow boundaries.

Returns a `set[tuple[int, int]]` of visible positions. The app merges this into a persistent `revealed` set for fog-of-war.

**FOV radius calculation:** base `FOV_RADIUS` (8) + race darkvision bonus + Light spell buff + equipped light source bonus (torch +3, lantern +4). Opened doors are treated as transparent.

### Trap System (`dungeon/traps.py`)

5 trap types with distinct effects:
- **Pit** — fall damage (1d6 per depth tier)
- **Spike** — piercing damage (1d8 + depth bonus)
- **Poison Dart** — damage + poison DOT buff (1d4/turn for 5 turns)
- **Alarm** — alerts all monsters on level
- **Trap Door** — fall to next level with damage, or safe descent using rope

**Detection:** d20 + WIS modifier + class bonus (thief +4, cleric +2, mage +1) + race bonus (halfling +2, elf +1) vs trap difficulty (10 + depth, max 20).

**Trap doors:** Create bidirectional rope connections stored in `GameState.rope_connections`. Ropes allow safe ascent/descent between levels at trap door positions. No trap doors placed on max dungeon depth.

### Dungeon Populator (`dungeon/populator.py`)

After a level is generated, `populate_level()` fills it with monsters, treasure, NPCs (1-3 per level), and traps:
- Each non-stair room has a 50%+ chance of a monster (scales with depth)
- 30% chance of gold in each room, plus a chance for equipment and magic item drops
- 20%+2%/depth chance of a trap per room, plus up to 3 corridor traps
- Returns a `LevelEntities` dataclass with `monster_at(x, y)` / `npc_at(x, y)` / `trap_at(x, y)` for collision lookup
- Stair rooms are kept empty as safe zones
- Occupied positions tracked to prevent entity overlap

## Character System

### Character (`character/character.py`)

Core player data and mechanics:

- **4 classes** — Fighter (1d10 HP, +1 atk/level), Mage (1d4 HP, +0.5 atk/level), Thief (1d6 HP), Cleric (1d8 HP). Defined in `CLASS_DATA` dict
- **4 races** — Human (no mods), Elf (+1 DEX/INT, -1 CON), Dwarf (+2 CON, -1 CHA), Halfling (+2 DEX, -1 STR). Defined in `RACE_DATA` dict
- **6 ability scores** — rolled with 4d6-drop-lowest, modified by race
- **AC calculation** — Descending (classic D&D): 10 - dex_mod - equipment ac_bonus - buffs. Lower = better
- **Attack bonus** — level * class multiplier + str_mod + sum of equipment attack_mod + buffs. THAC0-style: d20 + attack_bonus >= 20 - target_AC
- **8 equipment slots** — weapon, armor (body), shield, helmet (head), boots, gloves, ring, amulet. Class restrictions enforced on equip. Slot-to-field mapping in `_SLOT_MAP`
- **Light sources** — Torch/lantern equip in shield slot. `light_remaining` tracks burn turns. `light_bonus()` returns FOV extension. `has_active_light()` checks equipped light or Light spell buff. Lit torches are consumed (not returned to inventory) when replaced or unequipped. Two-handed weapons force shield unequip, extinguishing light
- **Leveling** — 25-level XP table. Level-up adds hit die + CON mod to max HP
- **Spell slots** — 3-level slot progression for Mage and Cleric classes
- **Buff system** — `tick_buffs()` handles regen, poison DOT, light burndown, and spell duration tracking

`create_character(name, class, race)` rolls a complete character with starting gold (3d6 * 10). The `CharacterCreationScreen` modal also assigns starting equipment per class.

### Items and Equipment (`entities/item.py`)

- **`Item` dataclass** — id, name, category, price/currency, damage dice (weapons), AC bonus (armor/accessories), attack_mod (accessories), slot, class restrictions, consumable/heal_dice fields, regen_dice/regen_turns for food heal-over-time, light_radius/light_duration for light sources, rarity/lore for magic items
- **`EquipmentDB` singleton** — loads `data/equipment.json` (84 items: weapons, armor, accessories, clothing, provisions, consumables, misc). Provisions (rations, ale) are consumable food with regen buffs. Misc includes rope, lanterns, torches, thieves' tools, holy water
- **`parse_dice()` / `roll_dice()`** — parses "2d6+1" format strings and rolls them
- **`random_treasure(tier)`** — generates loot appropriate to dungeon depth
- **`for_merchant_tier()`** — filters items for NPC shops. Provisions tier includes misc items (rope, supplies)
- Gold values normalized across currencies (G=gold, S=silver/10, C=copper/100)

### Magic Items (`entities/magic_items.py`)

- **`UniqueItemDB`** — persistent database of unique items, saved to `saves/unique_items.json`
- **`generate_startup_uniques(count)`** — creates unique items on game start using AI (with fallback name generation). 20 skeleton templates across weapons, armor, and accessories. Guarantees name uniqueness
- **`roll_magic_loot(depth, tier)`** — chance to drop a magic item from the unique pool, scaling with depth
- Unique items have `rarity="unique"`, custom names, and one-sentence lore descriptions

## Combat System

### Combat Engine (`combat/combat_engine.py`)

Turn-based D&D-style combat:

```mermaid
flowchart TD
    Start([Monster bump or<br/>corridor encounter]) --> Init[Roll initiative<br/>d20 + dex_mod vs d20]
    Init -->|Monster wins| MonFirst[Monster gets free attack]
    Init -->|Player wins| Choice

    MonFirst --> Choice{Player chooses}

    Choice -->|F — Attack| Atk[Roll d20 + attack_bonus]
    Choice -->|R — Flee| Flee[Roll d20 + dex_mod vs DC 10]
    Choice -->|C — Cast| Cast[Select and cast spell]

    Atk -->|Nat 20| Crit[CRITICAL HIT — 2x damage]
    Atk -->|Nat 1| Fumble[FUMBLE — auto miss]
    Atk -->|Roll >= AC| Hit[Hit — roll damage + str_mod]
    Atk -->|Roll < AC| Miss[Miss]

    Crit --> CheckMon{Monster HP <= 0?}
    Hit --> CheckMon
    Fumble --> MonAtk
    Miss --> MonAtk

    CheckMon -->|Yes| Win([PLAYER_WIN<br/>XP + loot])
    CheckMon -->|No| MonAtk[Monster attacks<br/>d20 + atk vs player AC]

    MonAtk --> Special{Special ability?}
    Special -->|30% poison| Poison[Poison damage]
    Special -->|20% paralyze| Para[Paralyze]
    Special -->|15% drain| Drain[Level drain]
    Special -->|regen| Regen[Monster regenerates HP]
    Special -->|No| CheckPlayer

    Poison --> CheckPlayer{Player HP <= 0?}
    Para --> CheckPlayer
    Drain --> CheckPlayer
    Regen --> CheckPlayer

    CheckPlayer -->|Yes| Dead([PLAYER_DEAD<br/>Resurrection or game over])
    CheckPlayer -->|No| Choice

    Flee -->|Success| Fled([PLAYER_FLED<br/>Combat ends])
    Flee -->|Fail| MonAtk
    Cast --> CheckMon
```

**Resurrection:** On death, if the player has gold, resurrection costs `min(100*level, gold//10)`. Equipment is dropped at the death position as a treasure pile. Player respawns at stairs_up with half HP (minimum 1). 0 gold = permanent death. Non-combat death (traps, poison DOT) handled by `_handle_player_death()`.

**`CombatState`** tracks the full fight: player, monster, round counter, result enum, and a combat log of styled text entries.

**`CombatResult`** enum: `ONGOING`, `PLAYER_WIN`, `PLAYER_FLED`, `PLAYER_DEAD`.

### Monsters (`entities/monster.py`)

- **`MonsterTemplate`** — static stats from `data/monsters.json`
- **`Monster`** — live instance with HP, position, speed, `is_alert` state. Created via `MonsterDB.spawn()`
- **30 types** scaling across levels 1-14:

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
| Ogre | 4-10 | 4d8 | 5 | 1d10 | — | 75 |
| Wight | 5-11 | 4d8 | 5 | 1d8 | drain | 100 |
| Troll | 6-12 | 6d8 | 4 | 2d6 | regen | 150 |
| Minotaur | 7-12 | 6d8 | 4 | 2d6+2 | charge | 200 |
| Gargoyle | 8-13 | 4d8+4 | 3 | 2d6 | — | 200 |
| Wraith | 8-14 | 5d8 | 3 | 1d8+2 | drain | 250 |
| Owlbear | 9-13 | 5d8+5 | 4 | 2d6+1 | — | 225 |
| Basilisk | 9-14 | 6d8 | 3 | 2d6 | paralyze | 300 |
| Vampire | 10-14 | 8d8 | 2 | 2d6+2 | drain | 500 |
| Hill Giant | 10-14 | 8d8 | 3 | 2d8 | — | 400 |
| Spectre | 11-14 | 7d8 | 2 | 2d6 | drain | 450 |
| Young Black Dragon | 12-14 | 10d8 | 1 | 3d6 | poison | 750 |

Each monster has a unique single-character symbol, color, and speed for the map display. Speed affects detection radius and pathfinding range.

### Monster AI

Monsters detect and pursue the player based on noise:

1. **Detection:** Manhattan distance <= effective detection range (base range attenuated by closed doors)
2. **Alert state:** Detected monsters become alert (turn red on map). Alert monsters de-alert when player moves far enough away
3. **Movement:** Alert monsters pathfind toward player via BFS through walkable tiles and opened doors only. Closed doors block monster movement
4. **Combat initiation:** When a monster moves adjacent to the player, combat begins automatically

### Spells (`combat/spells.py`)

- **`SpellDB` singleton** — loads `data/spells.json` (12 spells: 6 mage, 6 cleric)
- **`SpellSlots`** — 3-level slot progression, restored on stair rest
- **`ActiveBuff`** — time-limited combat/utility buffs (e.g., Light extends FOV radius). Also used for food regen: `effect="regen"` with `regen_dice` rolled each turn via `tick_buffs()`. Poison DOT uses `effect="poison_dot"`
- `player_cast()` handles spell combat integration

## NPCs and Quests

### NPCs (`entities/npc.py`)

- **`NPCDB` singleton** — loads `data/npcs.json` (11 templates: 4 merchants, 2 quest givers, 2 sages, 3 wanderers)
- **`NPC`** — tracks position, `talked_to`, `quest_id`
- AI DM generates dialogue; fallback templates for offline play
- NPCs placed in non-stair, non-monster rooms, away from doors

### Merchants

OptionList-based merchant screen for buying/selling. Items filtered by `for_merchant_tier()` based on merchant type:
- **Weapons merchant** — all weapons
- **Provisions merchant** — provisions, clothing, consumables, and misc items (rope, lanterns, torches, supplies)
- **Armor merchant** — armor and accessories
- **Magic merchant** — accessories, scrolls, and expensive misc items

Purchased items use canonical `equipment_db` references to preserve all item properties.

### Quests (`quest/quest.py`)

- **`QuestType`** — `KILL_MONSTERS`, `EXPLORE_DEPTH`
- **`QuestLog`** — progress tracking with completion checks
- `generate_quest()` creates depth-appropriate random quests
- AI DM narrates quest offers and completions

## AI Dungeon Master

### Design Principles
1. **AI is narration-only** — never affects combat math, movement, or dice
2. **Cache-first** — SQLite prevents duplicate API calls for the same content
3. **Always falls back** — game is 100% playable without an API key

### Architecture

```mermaid
flowchart LR
    Event[Game Event<br/>room / combat / kill<br/>level / treasure / NPC] --> DM[DungeonMaster]

    DM --> Cache{AICache<br/>SQLite<br/>SHA-256 key}
    Cache -->|HIT| Return[Return cached text]
    Cache -->|MISS| API[AIClient<br/>Claude Sonnet]
    API -->|SUCCESS| Store[Cache result + return]
    API -->|FAIL| FB[Fallback<br/>random template from JSON]
    FB --> Return
    Store --> Return
```

### Prefetch

`_prefetched_depths` set prevents redundant API calls on revisited levels. When descending, prefetch blocks movement with a loading notice until complete.

### Modules

**`ai/client.py`** — Wraps Anthropic SDK. Reads API key from `claude.key.txt` (project root) or `ANTHROPIC_API_KEY` env var. Tracks input/output tokens for cost estimation. Uses Claude Sonnet for speed and cost.

**`ai/cache.py`** — SQLite database at `saves/ai_cache.db`. Keys are `"{content_type}:{sha256_hash}"`. Content types: `room_enter`, `combat_start`, `combat_kill`, `combat_crit`, `level_theme`, `treasure_find`.

**`ai/fallback.py`** — Loads `data/fallback_descriptions.json` and returns random entries per category. Lazy-loaded on first call.

**`ai/dm.py`** — `DungeonMaster` singleton orchestrates all AI narration:
- `describe_room()` — triggered on first visit to each room
- `narrate_combat_start()` — when bumping into a monster
- `narrate_kill()` — on monster death (includes weapon name)
- `narrate_crit()` — on critical hits
- `describe_level_theme()` — when descending to a new level
- `describe_treasure()` — when picking up loot
- NPC dialogue — AI-generated conversation with personality
- Quest narration — AI-generated quest offers and completions

All methods share the same system prompt establishing tone (dark fantasy, second person, 1-3 sentences, no emojis).

## Audio System

### Sound Manager (`audio/sound_manager.py`)

Event-driven singleton connected via the event bus. Fallback chain: playsound3 → winsound → aplay → bell → silent.

- **playsound3** — cross-platform, optional pip extra `[audio]`
- **winsound** — Windows built-in, non-blocking via `SND_ASYNC`
- **aplay** — ALSA utils, available on nearly all Linux systems with no pip dependencies
- **bell** — terminal bell (`\a`), last-resort audible fallback
- **silent** — no audio output

**`audio/tone_generator.py`** — creates 19 retro WAV files using stdlib only. Config in `data/sounds.json` (23 event-to-sound mappings including trap_detected and trap_triggered). Optional `[audio]` pip extra for playsound3.

## UI Architecture

Built on [Textual](https://textual.textualize.io/), a Python TUI framework built on Rich.

### Layout

```mermaid
block-beta
    columns 5

    Map["MapPanel (+ FPV overlay top-right)<br/>1fr width"]:3
    Stats["StatsPanel<br/>26 cols<br/>Name, HP bar, stats,<br/>AC, equipment, gold,<br/>minimap, spell slots"]:2

    Log["LogPanel (10 rows)<br/>AI descriptions, combat narration, item pickups"]:5

    Cmd["CommandBar (1 row) — level, turn, position, command input via :"]:5
```

### Rendering Pipeline

```mermaid
sequenceDiagram
    participant P as Player Input
    participant A as App (action handlers)
    participant G as GameState
    participant F as FOV
    participant DM as DungeonMaster
    participant W as Widgets

    P->>A: Key press (WASD, F, G, etc.)
    A->>G: Update state (position, combat, etc.)
    A->>F: compute_fov() with darkvision + light bonus
    F-->>G: visible set → merged into revealed
    A->>DM: Room entry / combat / kill check
    DM-->>A: Narration text
    A->>W: Increment reactive turn counter
    W->>W: render() — MapPanel (with light tint), StatsPanel, LogPanel
```

### Widget Communication

Widgets hold a reference to `GameState` (set via `set_game_state()`). The app calls `refresh_map()`/`refresh_stats()`/`refresh_bar()` which increment reactive counters to trigger re-renders. Log messages go through `RichLog.write()`.

### Modal Screens

- **`CharacterCreationScreen`** — Name, class, race selection. Starting equipment per class. Load Game button for returning players
- **`SpellSelectionScreen`** — Choose spell to cast from available slots
- **`SaveLoadScreen`** — 5 manual slots + autosave
- **`MerchantScreen`** — OptionList-based buy/sell interface with mode toggle
- **`InventoryScreen`** — OptionList-based equip/unequip/use with item stacking (identical items grouped by ID with quantity)
- **`UseItemScreen`** — OptionList-based consumable item selection with item stacking
- **`QuitScreen`** — Quit confirmation with Save & Quit, Quit Without Saving, and Cancel options

### Map Rendering

The `MapPanel` renders the dungeon with:
- **Fog of war:** visible tiles in full color, revealed tiles dimmed, unexplored tiles hidden
- **Light tinting:** when player has active light source, visible room/corridor tiles tint warm yellow/goldenrod
- **Entity overlays:** monsters (colored symbols, red when alert), NPCs, detected traps (^), rope connections (~), treasure ($)
- **FPV overlay:** first-person ASCII view composited into the top-right corner of the panel (toggled with V)
- **Viewport scrolling:** camera centered on player, clamped to map bounds

### Key Bindings

| Key | Action | Context |
|-----|--------|---------|
| W/S/A/D, Arrows | Move / Turn | Exploration |
| F | Attack | Combat |
| R | Flee | Combat |
| C | Cast spell | Combat (Mage/Cleric) |
| G | Pick up items | On treasure tile |
| I | Show inventory | Any time |
| U | Use consumable | Any time |
| T | Talk to NPC | Adjacent to NPC |
| J | Quest log | Any time |
| V | Toggle map/first-person | Any time |
| < (comma) | Ascend stairs (heals) | On up stairs or rope |
| > (period) | Descend stairs (heals) | On down stairs or trap door with rope |
| Ctrl+S | Save game | Any time |
| Ctrl+L | Load game | Any time |
| : | Command input mode | Any time |
| Q | Quit (confirmation modal: Save & Quit / Quit / Cancel) | Any time |

## Data Flow

### Exploration

```mermaid
flowchart TD
    K[Key Press] --> Move[action_move direction]
    Move --> ChkNPC{NPC at<br/>destination?}
    ChkNPC -->|Yes| Talk[Interact with NPC]
    ChkNPC -->|No| ChkMon{Monster at<br/>destination?}
    ChkMon -->|Yes| Combat[Start combat]
    ChkMon -->|No| ChkWalk{Walkable?}
    ChkWalk -->|No| ChkDoor{Locked door?}
    ChkDoor -->|Yes| TryOpen[Try open/pick/bash]
    ChkDoor -->|No| Blocked[Can't go that way]
    ChkWalk -->|Yes| DoMove[Move player, increment turn]
    DoMove --> ChkTrap{Trap at<br/>position?}
    ChkTrap -->|Yes| Detect{Detection<br/>check?}
    Detect -->|Pass| TrapDetected[Trap revealed on map]
    Detect -->|Fail| TrapTrigger[Trap activates]
    ChkTrap -->|No| FOV
    TrapDetected --> FOV
    TrapTrigger --> FOV
    FOV[compute_fov → visible → revealed]
    FOV --> MonAI[Monster detection + movement]
    MonAI --> ChkGround{Items on<br/>ground?}
    ChkGround -->|Yes| Notify[Notify player]
    ChkGround -->|No| ChkRoom
    Notify --> ChkRoom{New room?}
    ChkRoom -->|Yes| AI[AI describe_room]
    ChkRoom -->|No| Pub
    AI --> Pub[EventBus.publish player_moved]
    Pub --> Refresh[All widgets refresh]
```

### AI Narration

```mermaid
flowchart LR
    E[Game event] --> DM[DM method]
    DM --> C{SQLite cache<br/>SHA-256 key}
    C -->|Hit| Log[Log to narrative panel]
    C -->|Miss| API{Claude Sonnet API}
    API -->|Success| Cache[Cache result] --> Log
    API -->|Fail| FB[Random fallback template] --> Log
```
