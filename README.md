# Dungeons of Dreagoth II

A modern Python sequel to *Dungeons of Dreagoth* (1991), a QBasic dungeon crawler. Procedurally generated dungeons, D&D-style mechanics, and an AI Dungeon Master powered by Claude for atmospheric narration — fully playable offline with template fallbacks.

## Quick Start

```bash
# Requires Python 3.12+
pip install -e ".[dev]"
python -m dreagoth
```

## Controls

| Key | Action |
|-----|--------|
| `W` / `Up` | Move north |
| `S` / `Down` | Move south |
| `A` / `Left` | Move west |
| `D` / `Right` | Move east |
| `F` | Attack (in combat) |
| `R` | Flee (in combat) |
| `G` | Pick up items |
| `I` | Show inventory |
| `<` (comma) | Ascend stairs |
| `>` (period) | Descend stairs |
| `Q` | Quit |

## Features

### Implemented
- **Dungeon Generation** — Procedural 80x40 grid ported from 1991 QBasic, 25 rooms/level, MST-connected corridors, multi-level stair traversal
- **Fog of War** — Recursive 8-octant shadowcasting FOV
- **Character System** — 4 classes (Fighter/Mage/Thief/Cleric), 4 races (Human/Elf/Dwarf/Halfling), D&D ability scores (4d6 drop lowest), racial modifiers
- **Equipment** — 56 items across weapons, armor, clothing, provisions, and misc. Equipment slots (weapon/armor/shield), class restrictions, gold economy
- **Combat** — Turn-based D&D-style: d20 attack rolls, initiative, critical hits (2x damage on nat 20), fumbles (nat 1), monster special abilities (poison, paralyze, drain, regen)
- **Monsters** — 14 types scaling with dungeon depth: Giant Rats and Kobolds on level 1 up to Trolls and Minotaurs on level 10. Loot drops and XP rewards
- **AI Dungeon Master** — Claude-powered atmospheric narration for room descriptions, combat starts, killing blows, critical hits, level themes, and treasure discovery. SQLite cache prevents duplicate API calls. Template fallbacks for 100% offline play
- **TUI** — Rich terminal interface with map panel, character stats sidebar (HP bar, abilities, equipment, gold, XP), scrollable narrative log, and status bar

### Planned
- **Phase 5:** NPCs, quest system, dialogue, spellcasting
- **Phase 6:** Save/load, first-person corridor view, door mechanics, full command parser

## Tech Stack

| Component | Technology |
|-----------|------------|
| TUI | [Textual](https://textual.textualize.io/) / [Rich](https://rich.readthedocs.io/) |
| Dungeon grid | numpy uint8 arrays |
| AI DM | Anthropic SDK (Claude Sonnet) |
| Schema validation | pydantic |
| Persistence | SQLite (AI cache + save games) |
| Tests | pytest |

## Project Structure

```
dreagoth/
  core/          # Engine: constants, dice, events, game_state
  dungeon/       # Generation: tiles, rooms, corridors, FOV, generator, populator
  character/     # Player: character creation, classes, races, leveling
  combat/        # Turn-based D&D combat engine
  entities/      # Items (56), monsters (14), equipment database
  ai/            # AI DM: Anthropic client, narration, SQLite cache, fallbacks
  ui/            # TUI: map, stats, log, command bar panels
  data/          # equipment.json, monsters.json, fallback_descriptions.json
Old_Code/        # Original 1991 QBasic source files
tests/           # 53 tests
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
