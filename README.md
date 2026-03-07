# Dungeons of Dreagoth II

A modern Python sequel to *Dungeons of Dreagoth* (1991), a QBasic dungeon crawler. Procedurally generated dungeons, D&D-style mechanics, and an AI Dungeon Master powered by Claude for atmospheric narration — fully playable offline with template fallbacks.

## Quick Start

```bash
# Requires Python 3.12+
pip install -e ".[dev]"
python -m dreagoth
```

## Controls

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `W` / `Up` | Move forward | `S` / `Down` | Move backward |
| `A` / `Left` | Turn left | `D` / `Right` | Turn right |
| `F` | Attack (combat) | `R` | Flee (combat) |
| `G` | Pick up items | `I` | Inventory |
| `C` | Cast spell (Mage/Cleric) | `U` | Use consumable item |
| `T` | Talk to adjacent NPC | `J` | Quest log |
| `<` `,` | Stairs up (heals + rests) | `>` `.` | Stairs down (heals + rests) |
| `V` | Toggle map/first-person | `Ctrl+S` | Save game |
| `Ctrl+L` | Load game | `:` | Command input mode |
| `Q` | Quit (confirm: Save & Quit / Quit / Cancel) | | |

## Features

- **Dungeon Generation** — Procedural 80x40 grid ported from 1991 QBasic, 25 rooms/level, MST-connected corridors, multi-level stair traversal, locked and magically locked doors
- **Fog of War** — Recursive 8-octant shadowcasting FOV, extended by Light spell
- **Character System** — 4 classes (Fighter/Mage/Thief/Cleric), 4 races (Human/Elf/Dwarf/Halfling), D&D ability scores (4d6 drop lowest), racial modifiers
- **Equipment** — 76 items across weapons, armor, accessories, clothing, provisions, consumables, and misc. 8 equipment slots (weapon, armor, shield, helmet, boots, gloves, ring, amulet), class restrictions, gold economy
- **Combat** — Turn-based D&D-style: d20 attack rolls, initiative, critical hits (2x damage on nat 20), fumbles (nat 1), monster special abilities (poison, paralyze, drain, regen)
- **Monsters** — 14 types scaling with dungeon depth: Giant Rats and Kobolds on level 1 up to Trolls and Minotaurs on level 10. Loot drops and XP rewards
- **Spells** — 12 spells (6 Mage, 6 Cleric) with 3-level slot progression. Combat spells and utility buffs (Light extends FOV). Slots restored on stair rest
- **NPCs** — 8 NPC types: 3 merchants (buy/sell with depth-tiered stock), 2 quest givers, 1 sage, 2 wanderers. AI-generated dialogue with fallback templates
- **Quests** — Kill monsters and explore depth quest types with progress tracking and AI-narrated offers/completions
- **AI Dungeon Master** — Claude-powered atmospheric narration for rooms, combat, kills, crits, level themes, treasure, and NPC dialogue. SQLite cache prevents duplicate API calls. Template fallbacks for 100% offline play. Prefetch on level descent
- **Save/Load** — JSON serialization with 5 manual slots + autosave. Items stored by ID for compact saves
- **First-Person View** — ASCII corridor renderer (Tab toggles with map view), minimap in stats panel
- **Command Parser** — 21 commands with aliases and tab completion, Vi-style `:` input mode
- **Resurrection** — Gold-based revival on death: equipment dropped as treasure pile, respawn at stairs with half HP. No gold = permanent death
- **Audio** — Event-driven retro sound effects (19 WAV tones, stdlib-generated). Fallback chain: playsound3 → winsound → aplay → bell → silent
- **TUI** — Rich terminal interface with map/first-person panel, character stats sidebar (HP bar, abilities, equipment, minimap, spell slots), scrollable narrative log, and command bar

## Tech Stack

| Component | Technology |
|-----------|------------|
| TUI | [Textual](https://textual.textualize.io/) / [Rich](https://rich.readthedocs.io/) |
| Dungeon grid | numpy uint8 arrays |
| AI DM | Anthropic SDK (Claude Sonnet) |
| Schema validation | pydantic |
| Audio | playsound3 (optional), winsound, aplay (ALSA), stdlib WAV generation |
| Persistence | SQLite (AI cache), JSON (save games) |
| Tests | pytest |

## Project Structure

```
dreagoth/
  core/          # Engine: constants, dice, events, game_state, save_load, command_parser
  dungeon/       # Generation: tiles, rooms, corridors, FOV, generator, populator
  character/     # Player: character creation, classes, races, leveling
  combat/        # Turn-based D&D combat engine, spells
  entities/      # Items (76), monsters (14), NPCs (8), equipment database
  ai/            # AI DM: Anthropic client, narration, SQLite cache, fallbacks
  quest/         # Quest system: kill monsters, explore depth
  audio/         # Sound manager, retro tone generator
  ui/            # TUI: map, first-person, stats, log, command bar, modal screens
  data/          # equipment.json, monsters.json, npcs.json, spells.json, sounds.json
Old_Code/        # Original 1991 QBasic source files
saves/           # Save game slots (JSON) and AI cache (SQLite)
tests/           # 184 tests across 10 files
```

## Original Source

The 1991 QBasic source lives in `Old_Code/`:

| File | Contents |
|------|----------|
| `DUNGEON.TXT` | Dungeon generator with DFS corridor pathfinding |
| `DUNGEON1.TXT` | Simpler generator variant (no pathfinding) |
| `DUNGMAKE.TXT` | First-person corridor renderer (DRAW commands) |
| `EQUIP.TXT` | 134-item equipment database (7 categories) |

## Running Tests

```bash
pytest tests/ -v
```

## Architecture

See [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) for technical details.

## License

Private project.
