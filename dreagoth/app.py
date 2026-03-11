"""Main application — Textual TUI game loop with combat, inventory, and AI DM."""

from __future__ import annotations

import random
import threading

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, Label, Select, OptionList
from textual.widgets.option_list import Option
from rich.text import Text

from dreagoth.core.constants import FOV_RADIUS, STARTING_LEVEL, RACE_DARKVISION
from dreagoth.core.events import bus
from dreagoth.core.game_state import GameState
from dreagoth.character.character import (
    Character, create_character, CLASS_DATA, RACE_DATA,
)
from dreagoth.dungeon.generator import DungeonGenerator
from dreagoth.dungeon.populator import populate_level
from dreagoth.dungeon.fov import compute_fov
from dreagoth.dungeon.tiles import Tile, is_door, is_locked, is_magically_locked, unlock_door, has_door_flags
from dreagoth.combat.combat_engine import CombatState, CombatResult, AttackOutcome
from dreagoth.audio.sound_manager import sound_manager
from dreagoth.combat.spells import spell_db, SpellTemplate, ActiveBuff
from dreagoth.entities.item import equipment_db, Item
from dreagoth.entities.magic_items import roll_magic_loot, generate_startup_uniques
from dreagoth.quest.quest import QuestLog, QuestType, QuestStatus, generate_quest
from dreagoth.core.save_load import save_game, load_game, list_saves, autosave
from dreagoth.ai.dm import dm
from dreagoth.ui.map_panel import MapPanel
from dreagoth.ui.stats_panel import StatsPanel
from dreagoth.ui.log_panel import LogPanel
from dreagoth.ui.command_bar import CommandBar


# ---------------------------------------------------------------------------
# Character creation screen
# ---------------------------------------------------------------------------
class CharacterCreationScreen(ModalScreen[Character | None]):
    """Modal screen for creating a new character or loading a saved game."""

    CSS = """
    CharacterCreationScreen {
        align: center middle;
    }
    #creation-box {
        width: 50;
        height: auto;
        max-height: 32;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #creation-box Label {
        margin-bottom: 1;
    }
    #creation-box Input {
        margin-bottom: 1;
    }
    #creation-box Select {
        margin-bottom: 1;
    }
    #creation-box Button {
        margin-top: 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="creation-box"):
            yield Label("DUNGEONS OF DREAGOTH II", id="title")
            yield Label("Create Your Character")
            yield Input(placeholder="Enter name...", id="name-input")
            yield Label("Class:")
            yield Select(
                [(f"{c.title()} - {d['description']}", c) for c, d in CLASS_DATA.items()],
                id="class-select",
                value="fighter",
            )
            yield Label("Race:")
            yield Select(
                [(f"{r.title()} - {d['description']}", r) for r, d in RACE_DATA.items()],
                id="race-select",
                value="human",
            )
            yield Button("Enter the Dungeon", variant="primary", id="create-btn")
            yield Button("Load Saved Game", id="load-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-btn":
            name_input = self.query_one("#name-input", Input)
            class_select = self.query_one("#class-select", Select)
            race_select = self.query_one("#race-select", Select)
            name = name_input.value.strip() or "Adventurer"
            char_class = class_select.value if class_select.value != Select.BLANK else "fighter"
            race = race_select.value if race_select.value != Select.BLANK else "human"
            char = create_character(name, char_class, race)
            self._give_starting_equipment(char)
            self.dismiss(char)
        elif event.button.id == "load-btn":
            self.app.push_screen(
                SaveLoadScreen("load"), self._on_load_result,
            )

    def _on_load_result(self, result: tuple[str, int] | None) -> None:
        if result is None:
            return  # Cancelled — stay on creation screen
        _, slot = result
        new_gs = load_game(slot)
        if new_gs:
            self.app.game_state = new_gs
            self.dismiss(None)  # Signal load happened
        # If load failed, stay on creation screen

    def _give_starting_equipment(self, char: Character) -> None:
        """Equip class-appropriate starting gear."""
        db = equipment_db
        # Starting weapon
        weapon_map = {
            "fighter": "sword_long",
            "mage": "staff",
            "thief": "dagger",
            "cleric": "mace_footman",
        }
        wpn = db.get(weapon_map.get(char.char_class, "dagger"))
        if wpn:
            char.inventory.append(wpn)
            char.equip(wpn)

        # Starting armor
        armor_map = {
            "fighter": "chain",
            "mage": None,
            "thief": "leather",
            "cleric": "scale",
        }
        armor_id = armor_map.get(char.char_class)
        if armor_id:
            arm = db.get(armor_id)
            if arm:
                char.inventory.append(arm)
                char.equip(arm)

        # Torch, rations, and starting consumables
        for item_id in ("torch", "rations_iron", "bandages", "bandages", "potion_minor"):
            item = db.get(item_id)
            if item:
                char.inventory.append(item)


# ---------------------------------------------------------------------------
# Spell selection screen
# ---------------------------------------------------------------------------
class SpellSelectionScreen(ModalScreen[SpellTemplate | None]):
    """Modal for selecting a spell to cast."""

    CSS = """
    SpellSelectionScreen {
        align: center middle;
    }
    #spell-box {
        width: 50;
        height: auto;
        max-height: 24;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #spell-box Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    def __init__(self, spells: list[SpellTemplate], slots_info: str) -> None:
        super().__init__()
        self._spells = spells
        self._slots_info = slots_info

    def compose(self) -> ComposeResult:
        with Static(id="spell-box"):
            yield Label("Cast a Spell", id="spell-title")
            yield Label(self._slots_info)
            for spell in self._spells:
                label = f"L{spell.level} {spell.name} - {spell.description}"
                yield Button(label, id=f"spell-{spell.id}")
            yield Button("Cancel", variant="default", id="spell-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "spell-cancel":
            self.dismiss(None)
        elif event.button.id.startswith("spell-"):
            spell_id = event.button.id[6:]
            for s in self._spells:
                if s.id == spell_id:
                    self.dismiss(s)
                    return
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Use item screen
# ---------------------------------------------------------------------------
class UseItemScreen(ModalScreen[Item | None]):
    """Modal for selecting a consumable item to use."""

    CSS = """
    UseItemScreen {
        align: center middle;
    }
    #useitem-box {
        width: 60;
        height: auto;
        max-height: 30;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #useitem-list {
        height: 1fr;
        max-height: 20;
    }
    #useitem-box Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, items: list[Item], player_level: int = 1) -> None:
        super().__init__()
        self._items = items
        self._player_level = player_level
        # Group by item id, preserving order
        self._grouped: list[tuple[Item, int]] = []
        seen: dict[str, int] = {}
        for item in items:
            if item.id in seen:
                idx = seen[item.id]
                old_item, old_qty = self._grouped[idx]
                self._grouped[idx] = (old_item, old_qty + 1)
            else:
                seen[item.id] = len(self._grouped)
                self._grouped.append((item, 1))

    def compose(self) -> ComposeResult:
        with Static(id="useitem-box"):
            yield Label("Use Item", id="useitem-title")
            yield OptionList(id="useitem-list")
            yield Button("Cancel", variant="default", id="item-cancel")

    def on_mount(self) -> None:
        ol = self.query_one("#useitem-list", OptionList)
        for item, qty in self._grouped:
            qty_str = f" x{qty}" if qty > 1 else ""
            ol.add_option(Option(
                f"{item.display_info_at(self._player_level)}{qty_str}",
                id=f"use-{item.id}",
            ))
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id
        if opt_id and opt_id.startswith("use-"):
            item_id = opt_id[4:]
            # Find the first matching item in the original list
            for item in self._items:
                if item.id == item_id:
                    self.dismiss(item)
                    return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "item-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Quit confirmation screen
# ---------------------------------------------------------------------------
class QuitScreen(ModalScreen[str | None]):
    """Modal for confirming quit with save option."""

    CSS = """
    QuitScreen {
        align: center middle;
    }
    #quit-box {
        width: 44;
        height: auto;
        max-height: 14;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #quit-box Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("y", "quit_now", "Quit"),
        ("n", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Static(id="quit-box"):
            yield Label("Quit Game?", id="quit-title")
            yield Label("Any unsaved progress will be lost.")
            yield Button("Save & Quit", variant="primary", id="save-quit")
            yield Button("Quit Without Saving", variant="error", id="quit-now")
            yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-quit":
            self.dismiss("save-quit")
        elif event.button.id == "quit-now":
            self.dismiss("quit")
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def action_quit_now(self) -> None:
        self.dismiss("quit")

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Save/Load screen
# ---------------------------------------------------------------------------
class SaveLoadScreen(ModalScreen[tuple[str, int] | None]):
    """Modal for saving or loading games."""

    CSS = """
    SaveLoadScreen {
        align: center middle;
    }
    #saveload-box {
        width: 50;
        height: auto;
        max-height: 20;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #saveload-box Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    def __init__(self, mode: str) -> None:
        super().__init__()
        self._mode = mode  # "save" or "load"

    def compose(self) -> ComposeResult:
        saves = list_saves()
        with Static(id="saveload-box"):
            yield Label(f"{'Save' if self._mode == 'save' else 'Load'} Game")
            for i, save in enumerate(saves):
                if save:
                    label = (
                        f"Slot {i}: {save['name']} L{save['level']} "
                        f"D{save['depth']} T{save['turn']}"
                    )
                else:
                    label = f"Slot {i}: Empty"
                yield Button(label, id=f"slot-{i}")
            yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id.startswith("slot-"):
            slot = int(event.button.id.split("-")[1])
            self.dismiss((self._mode, slot))


# ---------------------------------------------------------------------------
# Main game application
# ---------------------------------------------------------------------------
class DreagothApp(App):
    """Dungeons of Dreagoth II — main game application."""

    TITLE = "Dungeons of Dreagoth II"

    CSS = """
    Screen {
        layout: vertical;
    }
    #top-area {
        height: 1fr;
    }
    #map-panel {
        width: 1fr;
    }
    #stats-panel {
        width: 26;
        border-left: solid #808080;
    }
    #log-panel {
        height: 10;
        border-top: solid #808080;
    }
    #command-bar {
        height: 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("w", "move('forward')", "Forward", show=False),
        Binding("s", "move('back')", "Back", show=False),
        Binding("a", "turn('left')", "Turn Left", show=False),
        Binding("d", "turn('right')", "Turn Right", show=False),
        Binding("up", "move('forward')", "Forward", show=False),
        Binding("down", "move('back')", "Back", show=False),
        Binding("left", "turn('left')", "Turn Left", show=False),
        Binding("right", "turn('right')", "Turn Right", show=False),
        Binding("comma", "use_stairs('up')", "Stairs Up", show=False),
        Binding("full_stop", "use_stairs('down')", "Stairs Down", show=False),
        Binding("f", "combat_attack", "Attack", show=False),
        Binding("r", "combat_flee", "Flee", show=False),
        Binding("i", "show_inventory", "Inventory", show=False),
        Binding("g", "pickup_items", "Get", show=False),
        Binding("c", "cast_spell", "Cast", show=False),
        Binding("t", "talk_npc", "Talk", show=False),
        Binding("j", "show_quest_log", "Quests", show=False),
        Binding("u", "use_item", "Use Item", show=False),
        Binding("v", "toggle_view", "View", show=False),
        Binding("ctrl+s", "save_game", "Save", show=False),
        Binding("ctrl+l", "load_game", "Load", show=False),
        Binding("colon", "command_mode", "Command", show=False),
        Binding("q", "quit_game", "Quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.game_state = GameState()
        self.generator = DungeonGenerator()
        self._loading = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-area"):
            yield MapPanel(id="map-panel")
            yield StatsPanel(id="stats-panel")
        yield LogPanel(id="log-panel")
        yield CommandBar(id="command-bar")

    def on_mount(self) -> None:
        map_panel = self.query_one("#map-panel", MapPanel)
        stats_panel = self.query_one("#stats-panel", StatsPanel)
        command_bar = self.query_one("#command-bar", CommandBar)

        map_panel.set_game_state(self.game_state)
        stats_panel.set_game_state(self.game_state)
        command_bar.set_game_state(self.game_state)

        # Wire up sound effects
        sound_manager.subscribe_to_events()

        # Generate new unique items in the background (uses AI if available)
        threading.Thread(
            target=generate_startup_uniques, daemon=True,
        ).start()

        # Show character creation
        self.push_screen(CharacterCreationScreen(), self._on_character_created)

    def _on_character_created(self, char: Character | None) -> None:
        if char is None:
            # Load game path — game_state already set by CharacterCreationScreen
            new_gs = self.game_state
            self.query_one("#map-panel", MapPanel).set_game_state(new_gs)
            self.query_one("#stats-panel", StatsPanel).set_game_state(new_gs)
            self.query_one("#command-bar", CommandBar).set_game_state(new_gs)
            self._update_fov()
            self._prefetch_room_descriptions(new_gs.current_depth)
            self._log("Game loaded.", style="bold bright_green")
            self._refresh_all()
            self._await_prefetch()
            return

        self.game_state.player = char
        self.game_state.quest_log = QuestLog()

        # Generate first level
        self._generate_level(STARTING_LEVEL)
        self._prefetch_room_descriptions(STARTING_LEVEL)
        sx, sy = self.game_state.current_level.stairs_up
        self.game_state.player_x = sx
        self.game_state.player_y = sy

        self._update_fov()
        self._log(
            f"{char.name} the {char.race.title()} {char.char_class.title()} "
            f"descends into the Dungeons of Dreagoth...",
            style="bold bright_cyan",
        )
        self._log(
            "W=Fwd S=Back A/D=Turn F=Fight R=Run G=Get I=Inv U=Use C=Cast T=Talk V=View :=Cmd",
            style="grey50",
        )

        # AI level theme (non-blocking)
        self._dm_narrate(dm.describe_level_theme, STARTING_LEVEL)

        self._refresh_all()
        self._await_prefetch()

    # ------------------------------------------------------------------
    # Level generation
    # ------------------------------------------------------------------
    def _generate_level(self, depth: int) -> None:
        if depth not in self.game_state.levels:
            level = self.generator.generate(depth)
            self.game_state.levels[depth] = level
            self.game_state.ensure_revealed_set(depth)
            # Populate with monsters and treasure
            entities = populate_level(level, depth)
            self.game_state.entities[depth] = entities
        self.game_state.current_depth = depth

    def _prefetch_room_descriptions(self, depth: int) -> None:
        """Kick off background AI prefetch for all room descriptions on this level."""
        level = self.game_state.levels.get(depth)
        if not level:
            return
        rooms = [
            (i, f"{r.width}x{r.height}")
            for i, r in enumerate(level.rooms)
        ]
        dm.prefetch_level_rooms(depth, rooms)

    def _await_prefetch(self) -> None:
        """Show a loading notice and block movement until room prefetch completes."""
        if dm._prefetch_done.is_set():
            return  # Already done (no AI, cached, or no rooms)

        self._loading = True
        self._log("Generating room descriptions...", style="bold bright_magenta")

        def _wait() -> None:
            dm._prefetch_done.wait()
            self.call_from_thread(self._on_prefetch_complete)

        threading.Thread(target=_wait, daemon=True).start()

    def _on_prefetch_complete(self) -> None:
        self._loading = False
        self._log("The dungeon reveals itself...", style="italic bright_magenta")
        self._refresh_all()

    # ------------------------------------------------------------------
    # FOV and rendering
    # ------------------------------------------------------------------
    def _update_fov(self) -> None:
        gs = self.game_state
        level = gs.current_level
        radius = FOV_RADIUS
        if gs.player:
            radius += RACE_DARKVISION.get(gs.player.race, 0)
            radius += gs.player.fov_bonus()
            radius += gs.player.light_bonus()
        opened = gs.ensure_opened_doors(gs.current_depth)
        visible = compute_fov(level.grid, gs.player_x, gs.player_y, radius, opened)
        gs.visible = visible
        gs.ensure_revealed_set(gs.current_depth).update(visible)

    def _refresh_all(self) -> None:
        self.query_one("#map-panel", MapPanel).refresh_map()
        self.query_one("#stats-panel", StatsPanel).refresh_stats()
        self.query_one("#command-bar", CommandBar).refresh_bar()

    def _log(self, message: str, style: str = "") -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        if style:
            log_panel.write(Text(message, style=style))
        else:
            log_panel.write(message)
        self.game_state.add_message(message)

    def _dm_narrate(self, fn, *args, style: str = "italic grey70") -> None:
        """Run a DM narration function in a background thread.

        The result is posted to the log when ready, keeping the UI
        responsive while the AI API call completes.
        """
        def _bg() -> None:
            result = fn(*args)
            if result:
                self.call_from_thread(self._log, result, style)

        threading.Thread(target=_bg, daemon=True).start()

    def _dm_narrate_npc(self, npc_name: str, fn, *args) -> None:
        """Like _dm_narrate but prefixes the result with the NPC's name."""
        def _bg() -> None:
            result = fn(*args)
            if result:
                self.call_from_thread(
                    self._log, f"{npc_name}: {result}", "bold bright_green",
                )

        threading.Thread(target=_bg, daemon=True).start()

    # ------------------------------------------------------------------
    # Room detection for AI descriptions
    # ------------------------------------------------------------------
    def _check_room_entry(self) -> None:
        """If player entered a new room, trigger AI description."""
        gs = self.game_state
        level = gs.current_level
        visited = gs.ensure_visited_rooms(gs.current_depth)

        for i, room in enumerate(level.rooms):
            if room.contains(gs.player_x, gs.player_y) and i not in visited:
                visited.add(i)
                size = f"{room.width}x{room.height}"
                desc = dm.describe_room(gs.current_depth, i, size)
                if desc:
                    self._log(desc, style="italic grey70")
                bus.publish("room_enter")
                break

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def action_turn(self, direction: str) -> None:
        """Turn the player left or right without moving."""
        gs = self.game_state
        if self._loading:
            return
        if gs.in_combat:
            self._log("You're in combat! F to fight, R to flee.", style="bright_red")
            return
        if gs.player and gs.player.is_dead:
            return

        dx, dy = gs.last_direction
        if direction == "left":
            gs.last_direction = (dy, -dx)   # 90° CCW
        elif direction == "right":
            gs.last_direction = (-dy, dx)   # 90° CW

        self._update_fov()
        self._refresh_all()

    def action_move(self, direction: str) -> None:
        try:
            self._do_move(direction)
        except Exception as exc:
            self._log(f"[ERROR] {exc}", style="bold bright_red")
            self._refresh_all()

    def _do_move(self, direction: str) -> None:
        gs = self.game_state
        if self._loading:
            return
        if gs.in_combat:
            self._log("You're in combat! F to fight, R to flee.", style="bright_red")
            return
        if gs.player and gs.player.is_dead:
            return

        # Relative directions based on player facing
        fdx, fdy = gs.last_direction
        if direction == "forward":
            dx, dy = fdx, fdy
        elif direction == "back":
            dx, dy = -fdx, -fdy
        else:
            # Support cardinal directions for command parser
            deltas = {
                "north": (0, -1), "south": (0, 1),
                "east": (1, 0), "west": (-1, 0),
            }
            dx, dy = deltas.get(direction, (0, 0))
            if (dx, dy) != (0, 0):
                gs.last_direction = (dx, dy)
        nx = gs.player_x + dx
        ny = gs.player_y + dy

        level = gs.current_level

        # Check for NPC at destination
        if gs.current_depth in gs.entities:
            npc = gs.current_entities.npc_at(nx, ny)
            if npc:
                self._interact_npc(npc)
                self._refresh_all()
                return

        # Check for monster at destination
        if gs.current_depth in gs.entities:
            monster = gs.current_entities.monster_at(nx, ny)
            if monster:
                self._start_combat(monster)
                self._refresh_all()
                return

        if level.can_walk(nx, ny):
            gs.player_x = nx
            gs.player_y = ny
            gs.turn += 1
            if gs.player:
                regen_msgs = gs.player.tick_buffs()
                for rmsg in regen_msgs:
                    self._log(rmsg, style="bright_green")

            # Mark door as opened when player walks through it
            tile = level[nx, ny]
            if is_door(tile):
                gs.ensure_opened_doors(gs.current_depth).add((nx, ny))
                bus.publish("door_open")

            self._update_fov()

            # Check what's at the new position
            if tile == Tile.STAIRS_UP:
                self._log("You see stairs leading up. Press < to ascend.")
            elif tile == Tile.STAIRS_DOWN:
                self._log("You see stairs leading down. Press > to descend.")

            # Check for traps
            if self._check_trap(nx, ny):
                self._refresh_all()
                return  # Trap triggered — skip further processing

            # Check for treasure
            self._check_ground_items()

            # AI room description
            self._check_room_entry()

            # Random encounter in corridors
            if tile == Tile.CORRIDOR and random.random() < 0.03:
                self._wandering_monster()

            # Move monsters toward player
            self._move_monsters()

            bus.publish("player_moved", x=nx, y=ny)
            bus.publish("footstep")
        elif level.in_bounds(nx, ny) and self._try_open_door(nx, ny):
            # If the door is now walkable, step through automatically
            if level.can_walk(nx, ny):
                gs.player_x = nx
                gs.player_y = ny
                gs.turn += 1
                if gs.player:
                    regen_msgs = gs.player.tick_buffs()
                    for rmsg in regen_msgs:
                        self._log(rmsg, style="bright_green")
                gs.ensure_opened_doors(gs.current_depth).add((nx, ny))
                self._update_fov()
                self._check_ground_items()
                self._move_monsters()
                bus.publish("player_moved", x=nx, y=ny)
                bus.publish("footstep")
        else:
            self._log("You can't go that way.", style="grey50")

        self._refresh_all()

    # ------------------------------------------------------------------
    # Door interaction
    # ------------------------------------------------------------------
    def _try_open_door(self, x: int, y: int) -> bool:
        """Attempt to open a door. Returns True if resolved (opened or message shown).

        Class-specific interactions:
          - Any class + Thieves' Tools: auto-unlock regular locks
          - Thief: DEX check vs DC 10+depth (regular only)
          - Fighter: STR check vs DC 12+depth (regular only)
          - Mage: auto-cast Knock (L2) if slot available (regular + magic)
          - Cleric: auto-cast Dispel Magic (L3) if slot available (regular + magic)
        """
        gs = self.game_state
        level = gs.current_level
        tile_val = level[x, y]

        if not is_door(tile_val):
            return False

        if not has_door_flags(tile_val):
            return False

        player = gs.player
        magically_locked = is_magically_locked(tile_val)

        # --- Magically locked: spellcasters or scrolls ---
        if magically_locked:
            spell = self._find_unlock_spell(player)
            if spell:
                return self._door_cast_unlock(spell, x, y, tile_val)
            scroll = self._find_unlock_scroll(player)
            if scroll:
                try:
                    return self._door_use_scroll(scroll, x, y, tile_val)
                except Exception:
                    # If scroll use fails, unlock the door anyway
                    level[x, y] = unlock_door(tile_val)
                    gs.ensure_opened_doors(gs.current_depth).add((x, y))
                    if scroll in player.inventory:
                        player.inventory.remove(scroll)
                    self._log(
                        f"You read the {scroll.name} — the lock yields!",
                        style="bold bright_cyan",
                    )
                    bus.publish("door_open")
                    return True
            self._log(
                "The door is magically sealed! You need a Knock or Dispel Magic scroll.",
                style="bright_magenta",
            )
            bus.publish("door_locked")
            return True

        # --- Regular locked door ---
        # 1. Thieves' Tools (any class) — auto-unlock
        has_tools = any(item.id == "thieves_tools" for item in player.inventory)
        if has_tools:
            level[x, y] = unlock_door(tile_val)
            gs.ensure_opened_doors(gs.current_depth).add((x, y))
            self._log("You use your thieves' tools to pick the lock.", style="bright_green")
            bus.publish("door_open")
            return True

        # 2. Class-specific attempts
        if player.char_class == "thief":
            return self._thief_pick_lock(player, x, y, tile_val)
        elif player.char_class == "fighter":
            return self._fighter_bash_door(player, x, y, tile_val)
        elif player.char_class in ("mage", "cleric"):
            spell = self._find_unlock_spell(player)
            if spell:
                return self._door_cast_unlock(spell, x, y, tile_val)
            # Fall through to scroll check below

        # 3. Scroll fallback (any class)
        scroll = self._find_unlock_scroll(player)
        if scroll:
            return self._door_use_scroll(scroll, x, y, tile_val)

        self._log("The door is locked.", style="bright_red")
        bus.publish("door_locked")
        return True

    def _thief_pick_lock(self, player: Character, x: int, y: int, tile_val: int) -> bool:
        """Thief attempts to pick a lock: d20 + DEX mod vs DC 10+depth."""
        from dreagoth.core.dice import d20
        gs = self.game_state
        dc = 10 + gs.current_depth
        roll = d20() + player.dex_mod
        if roll >= dc:
            gs.current_level[x, y] = unlock_door(tile_val)
            gs.ensure_opened_doors(gs.current_depth).add((x, y))
            self._log(f"You pick the lock! (rolled {roll} vs DC {dc})", style="bright_green")
            bus.publish("door_open")
        else:
            self._log(f"You fail to pick the lock. (rolled {roll} vs DC {dc})", style="bright_red")
            bus.publish("door_locked")
        return True

    def _fighter_bash_door(self, player: Character, x: int, y: int, tile_val: int) -> bool:
        """Fighter attempts to bash a door: d20 + STR mod vs DC 12+depth."""
        from dreagoth.core.dice import d20
        gs = self.game_state
        dc = 12 + gs.current_depth
        roll = d20() + player.str_mod
        if roll >= dc:
            gs.current_level[x, y] = unlock_door(tile_val)
            gs.ensure_opened_doors(gs.current_depth).add((x, y))
            self._log(f"You bash the door open! (rolled {roll} vs DC {dc})", style="bright_green")
            bus.publish("door_open")
        else:
            self._log(f"You fail to bash the door. (rolled {roll} vs DC {dc})", style="bright_red")
            bus.publish("door_locked")
        return True

    def _find_unlock_spell(self, player: Character) -> SpellTemplate | None:
        """Return the unlock spell if the player has a slot for it, else None.

        Mage: Knock (level 2), Cleric: Dispel Magic (level 3).
        """
        if player.char_class == "mage":
            spell = spell_db.get("knock")
        elif player.char_class == "cleric":
            spell = spell_db.get("dispel_magic")
        else:
            return None
        if spell and player.spell_slots.available(spell.level) > 0:
            return spell
        return None

    def _door_cast_unlock(self, spell: SpellTemplate, x: int, y: int, tile_val: int) -> bool:
        """Consume a spell slot, unlock the door, and log the action."""
        gs = self.game_state
        level = gs.current_level
        player = gs.player
        # Unlock first, then consume slot
        level[x, y] = unlock_door(tile_val)
        gs.ensure_opened_doors(gs.current_depth).add((x, y))
        player.spell_slots.use(spell.level)
        self._log(f"You cast {spell.name} — the lock yields!", style="bold bright_cyan")
        bus.publish("door_open")
        return True

    def _find_unlock_scroll(self, player: Character) -> "Item | None":
        """Return a scroll that can unlock doors, or None."""
        for item in player.inventory:
            if item.is_scroll and item.spell_id in ("knock", "dispel_magic"):
                return item
        return None

    def _find_nearby_locked_door(self) -> tuple[int, int] | None:
        """Find a locked door adjacent to the player or up to 2 tiles ahead.

        Checks the 4 cardinal neighbors first, then 2 tiles in the
        player's facing direction.  Returns (x, y) of the door or None.
        """
        gs = self.game_state
        level = gs.current_level
        px, py = gs.player_x, gs.player_y

        # Check 4 cardinal neighbors
        for adx, ady in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = px + adx, py + ady
            if level.in_bounds(nx, ny):
                tv = level[nx, ny]
                if is_door(tv) and (is_locked(tv) or is_magically_locked(tv)):
                    return (nx, ny)

        # Check 2 tiles ahead in facing direction
        fdx, fdy = gs.last_direction
        for dist in (1, 2):
            nx, ny = px + fdx * dist, py + fdy * dist
            if level.in_bounds(nx, ny):
                tv = level[nx, ny]
                if is_door(tv) and (is_locked(tv) or is_magically_locked(tv)):
                    return (nx, ny)

        return None

    def _door_use_scroll(self, scroll: "Item", x: int, y: int, tile_val: int) -> bool:
        """Consume a scroll to unlock a door."""
        gs = self.game_state
        level = gs.current_level

        # Unlock the door FIRST, then consume the scroll
        new_tile = unlock_door(tile_val)
        level[x, y] = new_tile
        gs.ensure_opened_doors(gs.current_depth).add((x, y))

        # Verify the write took effect
        actual = level[x, y]
        if actual != new_tile:
            self._log("The magic resists!", style="bright_red")
            return True

        # Now consume the scroll
        if scroll in gs.player.inventory:
            gs.player.inventory.remove(scroll)

        self._log(
            f"You read the {scroll.name} — the lock yields!",
            style="bold bright_cyan",
        )
        bus.publish("door_open")
        return True

    # ------------------------------------------------------------------
    # Stairs
    # ------------------------------------------------------------------
    def action_use_stairs(self, direction: str) -> None:
        gs = self.game_state
        if self._loading:
            return
        if gs.in_combat:
            self._log("You can't use stairs during combat!", style="bright_red")
            return

        level = gs.current_level
        tile = level[gs.player_x, gs.player_y]

        pos = (gs.player_x, gs.player_y)
        ropes = gs.ensure_rope_connections(gs.current_depth)

        if direction == "up":
            if tile in (Tile.STAIRS_UP, Tile.STAIRS_BOTH):
                if gs.current_depth <= 1:
                    self._log("The surface world lies above. You press deeper.", style="grey50")
                else:
                    new_depth = gs.current_depth - 1
                    self._generate_level(new_depth)
                    self._prefetch_room_descriptions(new_depth)
                    stairs = gs.current_level.stairs_down
                    if stairs:
                        gs.player_x, gs.player_y = stairs
                    gs.turn += 1
                    if gs.player:
                        gs.player.spell_slots.rest()
                        gs.player.hp = gs.player.max_hp
                    self._update_fov()
                    self._log(f"You ascend to level {new_depth}.", style="bold bright_cyan")
                    bus.publish("stairs_ascend")
                    autosave(gs)
                    self._refresh_all()
                    self._await_prefetch()
            elif pos in ropes and gs.current_depth > 1:
                # Climb up rope to previous level
                new_depth = gs.current_depth - 1
                landing = ropes[pos]
                self._generate_level(new_depth)
                gs.player_x, gs.player_y = landing
                gs.current_depth = new_depth
                gs.turn += 1
                self._update_fov()
                self._log(f"You climb the rope back up to level {new_depth}.", style="bold bright_cyan")
                bus.publish("stairs_ascend")
                autosave(gs)
                self._refresh_all()
            else:
                self._log("There are no stairs going up here.", style="grey50")

        elif direction == "down":
            if tile in (Tile.STAIRS_DOWN, Tile.STAIRS_BOTH):
                new_depth = gs.current_depth + 1
                self._generate_level(new_depth)
                self._prefetch_room_descriptions(new_depth)
                stairs = gs.current_level.stairs_up
                if stairs:
                    gs.player_x, gs.player_y = stairs
                gs.turn += 1
                if gs.player:
                    gs.player.spell_slots.rest()
                    gs.player.hp = gs.player.max_hp
                self._update_fov()
                self._log(f"You descend to level {new_depth}...", style="bold bright_cyan")
                bus.publish("stairs_descend")
                self._dm_narrate(dm.describe_level_theme, new_depth)
                # Quest progress
                if gs.quest_log:
                    completed = gs.quest_log.on_depth_reached(new_depth)
                    for q in completed:
                        bus.publish("quest_complete")
                        self._log(f"Quest complete: {q.name}!", style="bold bright_yellow")
                autosave(gs)
                self._refresh_all()
                self._await_prefetch()
            elif pos in ropes:
                # Rope already placed — climb down
                landing = ropes[pos]
                new_depth = gs.current_depth + 1
                self._generate_level(new_depth)
                gs.player_x, gs.player_y = landing
                gs.current_depth = new_depth
                gs.turn += 1
                self._update_fov()
                self._log(f"You climb down the rope to level {new_depth}.", style="bold bright_cyan")
                bus.publish("stairs_descend")
                autosave(gs)
                self._refresh_all()
            elif self._try_rope_trap_door():
                pass  # Handled inside
            else:
                self._log("There are no stairs going down here.", style="grey50")

        self._refresh_all()

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------
    def _start_combat(self, monster) -> None:
        gs = self.game_state
        combat = CombatState(player=gs.player, monster=monster)
        gs.combat = combat

        # AI combat start narration (non-blocking)
        self._dm_narrate(dm.narrate_combat_start, monster.name, gs.current_depth,
                         style="italic bright_red")

        combat.start()
        bus.publish("combat_start")
        self._flush_combat_log()

    def _flush_combat_log(self) -> None:
        """Output all new combat log entries."""
        gs = self.game_state
        if not gs.combat:
            return
        for entry in gs.combat.log:
            self._log(entry.text, style=entry.style)
        gs.combat.log.clear()

    def action_combat_attack(self) -> None:
        gs = self.game_state
        if not gs.in_combat:
            return

        gs.combat.player_attack()
        self._flush_combat_log()

        # Sound for attack outcome
        outcome = gs.combat.last_player_outcome
        if outcome == AttackOutcome.CRIT:
            bus.publish("combat_crit")
        elif outcome == AttackOutcome.HIT:
            bus.publish("combat_hit")
        elif outcome in (AttackOutcome.MISS, AttackOutcome.FUMBLE):
            bus.publish("combat_miss")

        if gs.combat.result == CombatResult.PLAYER_WIN:
            self._end_combat_victory()
        elif gs.combat.result == CombatResult.PLAYER_DEAD:
            self._end_combat_death()

        gs.turn += 1
        self._refresh_all()

    def action_combat_flee(self) -> None:
        gs = self.game_state
        if not gs.in_combat:
            return

        gs.combat.try_flee()
        self._flush_combat_log()

        if gs.combat.result == CombatResult.PLAYER_FLED:
            gs.combat = None
        elif gs.combat.result == CombatResult.PLAYER_DEAD:
            self._end_combat_death()

        gs.turn += 1
        self._refresh_all()

    def _end_combat_victory(self) -> None:
        gs = self.game_state
        monster = gs.combat.monster
        xp = monster.xp
        bus.publish("monster_kill")

        # AI kill narration
        weapon_name = gs.player.weapon.name if gs.player.weapon else "fists"
        self._dm_narrate(dm.narrate_kill, monster.name, weapon_name,
                         style="italic bright_green")

        # XP and leveling
        leveled = gs.player.gain_xp(xp)
        if leveled:
            bus.publish("level_up")
            self._log(
                f"LEVEL UP! You are now level {gs.player.level}! "
                f"HP: {gs.player.hp}/{gs.player.max_hp}",
                style="bold bright_yellow",
            )

        # Loot drop
        gold_drop = random.randint(1, 6) * monster.loot_tier
        if gold_drop > 0:
            gs.player.gold += gold_drop
            self._log(f"You find {gold_drop} gold.", style="bright_yellow")

        if monster.loot_tier >= 2 and random.random() < 0.3:
            loot = equipment_db.random_treasure(monster.loot_tier)
            for item in loot:
                msg = gs.player.pickup(item)
                self._log(msg, style="bright_yellow")

        # Magic item drop
        magic_item = roll_magic_loot(gs.current_depth, monster.loot_tier)
        if magic_item:
            msg = gs.player.pickup(magic_item)
            color = magic_item.rarity_color or "bright_yellow"
            self._log(msg, style=f"bold {color}")
            if magic_item.lore:
                self._log(f"  \"{magic_item.lore}\"", style="italic grey70")

        # Quest progress
        if gs.quest_log:
            completed = gs.quest_log.on_monster_killed(monster.template_id)
            for q in completed:
                bus.publish("quest_complete")
                self._log(f"Quest complete: {q.name}!", style="bold bright_yellow")

        # Clean up combat state
        gs.player.clear_combat_buffs()
        gs.current_entities.remove_dead()
        gs.combat = None

    def _end_combat_death(self) -> None:
        gs = self.game_state
        gs.combat = None
        player = gs.player

        cost = min(100 * player.level, player.gold // 10)
        if player.gold > 0:
            # Collect all equipment and inventory items
            dropped_items: list[Item] = []
            for slot_name in ("weapon",) + player.EQUIPMENT_SLOTS:
                item = getattr(player, slot_name)
                if item is not None:
                    dropped_items.append(item)
                    setattr(player, slot_name, None)
            dropped_items.extend(player.inventory)
            player.inventory = []

            # Drop items as treasure pile at death position
            if dropped_items:
                death_pos = (gs.player_x, gs.player_y)
                piles = gs.current_entities.treasure_piles
                if death_pos in piles:
                    piles[death_pos].extend(dropped_items)
                else:
                    piles[death_pos] = dropped_items

            # Deduct gold and resurrect
            player.gold -= cost
            player.is_dead = False
            player.hp = max(1, player.max_hp // 2)
            player.active_buffs.clear()

            # Teleport to stairs up
            stairs = gs.current_level.stairs_up
            if stairs:
                gs.player_x, gs.player_y = stairs

            bus.publish("player_resurrect")
            self._log(
                "The dungeon spirits grant you another chance...",
                style="bold bright_magenta",
            )
            self._log(
                f"Resurrection cost: {cost} gold.",
                style="bright_yellow",
            )
            self._log(
                "Your equipment was left behind — retrace your steps!",
                style="bright_yellow",
            )
            self._update_fov()
            self._refresh_all()
        else:
            bus.publish("player_death")
            self._log(
                "You have perished in the Dungeons of Dreagoth.",
                style="bold bright_red",
            )
            self._log(
                "You have no gold — the spirits demand payment.",
                style="bright_yellow",
            )
            self._log("Press Q to quit.", style="grey50")

    def _handle_player_death(self) -> None:
        """Handle player death outside of combat (traps, poison, etc.).

        Reuses the same resurrection/permadeath logic as combat death.
        """
        gs = self.game_state
        # Set up a fake combat=None state so _end_combat_death works
        gs.combat = None
        self._end_combat_death()

    def _wandering_monster(self) -> None:
        """Chance of a random encounter in corridors."""
        from dreagoth.entities.monster import monster_db
        gs = self.game_state
        monster = monster_db.random_for_level(
            gs.current_depth, gs.player_x, gs.player_y,
        )
        if monster:
            self._start_combat(monster)

    # ------------------------------------------------------------------
    # Trap system
    # ------------------------------------------------------------------
    def _check_trap(self, x: int, y: int) -> bool:
        """Check for a trap at (x, y). Returns True if a trap interrupted movement."""
        from dreagoth.dungeon.traps import (
            check_detection, resolve_trap, TRAP_NAMES, TrapType,
        )

        gs = self.game_state
        if gs.current_depth not in gs.entities:
            return False
        ents = gs.current_entities
        trap = ents.trap_at(x, y)
        if trap is None or trap.triggered:
            return False

        # Already detected — player walks over safely
        if trap.detected:
            name = TRAP_NAMES.get(trap.trap_type, "trap")
            if trap.trap_type in (TrapType.TRAP_DOOR, TrapType.PIT):
                has_rope = gs.player and any(
                    i.id == "rope" for i in gs.player.inventory
                )
                # Check if rope already used here
                ropes = gs.ensure_rope_connections(gs.current_depth)
                if (x, y) in ropes:
                    self._log(
                        f"A rope leads down through the {name}. Press > to climb down.",
                        style="bright_cyan",
                    )
                elif has_rope:
                    self._log(
                        f"You see the {name}. You have rope — press > to climb down safely.",
                        style="bright_cyan",
                    )
                else:
                    self._log(
                        f"You carefully step around the {name}.",
                        style="grey70",
                    )
            return False

        # Perception check
        if gs.player and check_detection(gs.player, trap):
            trap.detected = True
            name = TRAP_NAMES.get(trap.trap_type, "trap")
            self._log(f"You spot a {name}!", style="bold bright_magenta")
            bus.publish("trap_detected")
            if trap.trap_type in (TrapType.TRAP_DOOR, TrapType.PIT):
                has_rope = gs.player and any(
                    i.id == "rope" for i in gs.player.inventory
                )
                if has_rope:
                    self._log(
                        "You have rope — press > to climb down safely.",
                        style="bright_cyan",
                    )
                else:
                    self._log(
                        "Without rope you'd fall. Step carefully.",
                        style="bright_yellow",
                    )
            return False  # Detected just in time, no trigger

        # Trap triggers!
        trap.triggered = True
        result = resolve_trap(trap, gs.current_depth)
        self._log(result.message, style="bold bright_red")
        bus.publish("trap_triggered")

        if result.damage > 0 and gs.player:
            actual = gs.player.take_damage(result.damage)
            self._log(f"You take {actual} damage! ({gs.player.hp}/{gs.player.max_hp} HP)",
                       style="bright_red")
            if gs.player.is_dead:
                self._handle_player_death()
                return True

        if result.poison and gs.player:
            from dreagoth.combat.spells import ActiveBuff
            gs.player.active_buffs.append(ActiveBuff(
                spell_id="trap_poison",
                effect="poison_dot",
                value=0,
                remaining_turns=result.poison_turns,
                regen_dice=result.poison_dice,
            ))
            self._log("You feel poison coursing through your veins!",
                       style="bold green")

        if result.alert_all:
            if gs.current_depth in gs.entities:
                for m in gs.current_entities.monsters:
                    if not m.is_dead:
                        m.is_alert = True
                self._log("All nearby creatures are alerted to your presence!",
                           style="bold bright_yellow")
                bus.publish("monster_alert")

        if result.fall_through:
            self._fall_through_trap_door(x, y)
            return True

        return False

    def _fall_through_trap_door(self, trap_x: int, trap_y: int) -> None:
        """Handle falling through a trap door to the level below."""
        from dreagoth.dungeon.generator import ensure_clear_path
        gs = self.game_state
        new_depth = gs.current_depth + 1

        self._generate_level(new_depth)
        level_below = gs.levels[new_depth]

        # Find a random walkable position on the level below
        landing = self._find_random_walkable(level_below)
        if landing:
            gs.player_x, gs.player_y = landing
        elif level_below.stairs_up:
            gs.player_x, gs.player_y = level_below.stairs_up

        # Ensure a clear path from landing to stairs_up (unlock doors if needed)
        if level_below.stairs_up:
            player_pos = (gs.player_x, gs.player_y)
            if player_pos != level_below.stairs_up:
                ensure_clear_path(level_below, player_pos, level_below.stairs_up)

        gs.current_depth = new_depth
        gs.turn += 1
        # No healing or spell rest — this is a fall, not a rest
        self._update_fov()
        self._log(f"You crash onto level {new_depth}!", style="bold bright_red")
        bus.publish("stairs_descend")
        autosave(gs)

    def _rope_descend_trap_door(self, trap_x: int, trap_y: int) -> None:
        """Climb down a trap door using rope. No damage, creates rope connection."""
        from dreagoth.dungeon.generator import ensure_clear_path
        gs = self.game_state
        new_depth = gs.current_depth + 1
        old_depth = gs.current_depth

        self._generate_level(new_depth)
        level_below = gs.levels[new_depth]

        # Find landing position
        landing = self._find_random_walkable(level_below)
        if not landing:
            if level_below.stairs_up:
                landing = level_below.stairs_up
            else:
                self._log("The rope can't reach a safe landing!", style="bright_red")
                return

        # Store bidirectional rope connections
        ropes_above = gs.ensure_rope_connections(old_depth)
        ropes_below = gs.ensure_rope_connections(new_depth)
        ropes_above[(trap_x, trap_y)] = landing
        ropes_below[landing] = (trap_x, trap_y)

        # Ensure a clear path from landing to stairs_up (unlock doors if needed)
        if level_below.stairs_up and landing != level_below.stairs_up:
            ensure_clear_path(level_below, landing, level_below.stairs_up)

        gs.player_x, gs.player_y = landing
        gs.current_depth = new_depth
        gs.turn += 1
        self._update_fov()
        self._log(f"You climb down the rope to level {new_depth}.", style="bold bright_cyan")
        bus.publish("stairs_descend")
        autosave(gs)

    def _find_random_walkable(self, level) -> tuple[int, int] | None:
        """Find a random walkable position on a level, avoiding stairs and entities."""
        from dreagoth.dungeon.tiles import is_walkable
        candidates = []
        for room in level.rooms:
            for ry in range(room.y, room.y + room.height):
                for rx in range(room.x, room.x + room.width):
                    if level[rx, ry] == Tile.ROOM:
                        candidates.append((rx, ry))
        if candidates:
            random.shuffle(candidates)
            return candidates[0]
        return None

    def _try_rope_trap_door(self) -> bool:
        """If standing on a detected pit/trap door with rope, use rope to descend."""
        from dreagoth.dungeon.traps import TrapType
        gs = self.game_state
        if gs.current_depth not in gs.entities:
            return False
        trap = gs.current_entities.trap_at(gs.player_x, gs.player_y)
        if not trap or trap.trap_type not in (TrapType.TRAP_DOOR, TrapType.PIT) or not trap.detected:
            return False
        if not gs.player:
            return False
        has_rope = any(i.id == "rope" for i in gs.player.inventory)
        if not has_rope:
            self._log("You need rope to climb down safely!", style="bright_yellow")
            return True  # Handled (message shown)
        self._rope_descend_trap_door(gs.player_x, gs.player_y)
        self._refresh_all()
        return True

    def _move_monsters(self) -> None:
        """Update monster detection and movement after the player moves."""
        from dreagoth.core.noise import (
            noise_level, detection_radius,
            count_closed_doors_between, DOOR_NOISE_PENALTY,
        )
        from dreagoth.dungeon.pathfinding import bfs_next_step

        gs = self.game_state
        if gs.current_depth not in gs.entities:
            return

        ents = gs.current_entities
        level = gs.current_level
        player_noise = noise_level(gs.player) if gs.player else 2
        opened = gs.ensure_opened_doors(gs.current_depth)

        # Track occupied positions to prevent monsters stacking
        occupied: set[tuple[int, int]] = {(gs.player_x, gs.player_y)}
        for m in ents.monsters:
            if not m.is_dead:
                occupied.add((m.x, m.y))

        moved_any = False
        for monster in ents.monsters:
            if monster.is_dead:
                continue

            dist = abs(monster.x - gs.player_x) + abs(monster.y - gs.player_y)
            detect_range = detection_radius(monster.speed, player_noise)

            # Closed doors between monster and player muffle sound
            closed_doors = count_closed_doors_between(
                level, monster.x, monster.y,
                gs.player_x, gs.player_y, opened,
            )
            effective_range = max(1, detect_range - closed_doors * DOOR_NOISE_PENALTY)

            # Detection check
            if dist <= effective_range:
                if not monster.is_alert:
                    monster.is_alert = True
                    # Only log if the monster is visible
                    if (monster.x, monster.y) in gs.visible:
                        self._log(
                            f"The {monster.name} notices you!",
                            style="bright_yellow",
                        )
                    else:
                        self._log(
                            "You hear something stirring in the darkness...",
                            style="grey70",
                        )
                    bus.publish("monster_alert")
            else:
                # Lose alert if player moves far enough away
                if monster.is_alert and dist > effective_range + 5:
                    monster.is_alert = False

            # Movement: alert monsters move toward the player
            if not monster.is_alert:
                continue
            if dist <= 1:
                # Adjacent — combat will be triggered on player's next move
                continue

            next_pos = bfs_next_step(
                level, monster.x, monster.y,
                gs.player_x, gs.player_y,
                max_dist=detect_range,
                opened_doors=opened,
            )
            if next_pos and next_pos not in occupied:
                occupied.discard((monster.x, monster.y))
                monster.x, monster.y = next_pos
                occupied.add(next_pos)
                moved_any = True

                # If monster moved adjacent to player, start combat
                new_dist = abs(monster.x - gs.player_x) + abs(monster.y - gs.player_y)
                if new_dist <= 1:
                    self._log(
                        f"A {monster.name} charges at you!",
                        style="bold bright_red",
                    )
                    self._start_combat(monster)
                    return  # Only one combat per turn

        if moved_any:
            ents.rebuild_indices()

    # ------------------------------------------------------------------
    # Items and inventory
    # ------------------------------------------------------------------
    def _check_ground_items(self) -> None:
        """Notify player if there are items on the ground."""
        gs = self.game_state
        if gs.current_depth not in gs.entities:
            return
        ents = gs.current_entities
        pos = (gs.player_x, gs.player_y)
        has_gold = pos in ents.gold_piles
        has_items = pos in ents.treasure_piles
        if has_gold or has_items:
            self._log("You see items here. Press G to pick up.", style="bright_yellow")

    def action_pickup_items(self) -> None:
        gs = self.game_state
        if gs.in_combat or not gs.player:
            return
        if gs.current_depth not in gs.entities:
            return

        ents = gs.current_entities
        pos = (gs.player_x, gs.player_y)
        picked_up = False

        # Gold
        if pos in ents.gold_piles:
            gold = ents.gold_piles.pop(pos)
            gs.player.gold += gold
            self._log(f"You pick up {gold} gold.", style="bright_yellow")
            bus.publish("pickup_gold")
            picked_up = True

        # Items
        if pos in ents.treasure_piles:
            items = ents.treasure_piles.pop(pos)
            item_names = []
            for item in items:
                msg = gs.player.pickup(item)
                if item.rarity != "common":
                    color = item.rarity_color or "bright_yellow"
                    self._log(msg, style=f"bold {color}")
                else:
                    self._log(msg, style="bright_yellow")
                bus.publish("pickup_item")
                item_names.append(item.name)
            # AI treasure narration (non-blocking)
            self._dm_narrate(dm.describe_treasure, item_names, 0)
            picked_up = True

        if not picked_up:
            self._log("Nothing to pick up here.", style="grey50")

        self._refresh_all()

    def action_show_inventory(self) -> None:
        gs = self.game_state
        if not gs.player:
            return
        from dreagoth.ui.inventory_screen import InventoryScreen
        self.push_screen(InventoryScreen(gs.player), self._on_inventory_action)

    def _on_inventory_action(self, result: str | None) -> None:
        if result:
            self._log(result, style="bright_green")
            self._update_fov()
            self._refresh_all()

    # ------------------------------------------------------------------
    # NPC interaction
    # ------------------------------------------------------------------
    def _interact_npc(self, npc) -> None:
        """Handle walking into or talking to an NPC."""
        gs = self.game_state
        bus.publish("npc_talk")
        if npc.role == "merchant":
            from dreagoth.ui.merchant_screen import MerchantScreen
            self.push_screen(MerchantScreen(npc, gs.player))
        elif npc.role == "quest_giver" and gs.quest_log:
            existing = gs.quest_log.quest_for_npc(npc.template_id)
            if existing and existing.status == QuestStatus.COMPLETED:
                # Turn in quest
                existing.status = QuestStatus.TURNED_IN
                self._dm_narrate_npc(
                    npc.name, dm.describe_quest_complete,
                    npc.name, existing.name,
                )
                gs.player.gold += existing.reward.gold
                gs.player.gain_xp(existing.reward.xp)
                self._log(
                    f"Reward: {existing.reward.gold} gold, {existing.reward.xp} XP",
                    style="bright_yellow",
                )
            elif existing and existing.status == QuestStatus.ACTIVE:
                self._log(
                    f"{npc.name}: \"{existing.name}\" is still in progress "
                    f"({existing.progress}/{existing.target_count}).",
                    style="bright_green",
                )
            else:
                # Offer new quest
                quest = generate_quest(gs.current_depth, npc.template_id, gs.quest_log)
                gs.quest_log.add(quest)
                self._dm_narrate_npc(
                    npc.name, dm.describe_quest_offer,
                    npc.name, quest.name, quest.description,
                )
                self._log(
                    f"Quest accepted: {quest.name} — {quest.description}",
                    style="bold bright_yellow",
                )
            npc.talked_to = True
        else:
            self._log(f"You speak with {npc.name}.", style="bright_green")
            self._dm_narrate_npc(
                npc.name, dm.generate_npc_dialogue,
                npc.name, npc.role, npc.personality,
                gs.current_depth, gs.player.name, npc.talked_to,
            )
            npc.talked_to = True

    def action_talk_npc(self) -> None:
        """Talk to an adjacent NPC."""
        gs = self.game_state
        if gs.in_combat or not gs.player:
            return
        if gs.current_depth not in gs.entities:
            return
        ents = gs.current_entities
        for adx, ady in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            ax, ay = gs.player_x + adx, gs.player_y + ady
            npc = ents.npc_at(ax, ay)
            if npc:
                self._interact_npc(npc)
                self._refresh_all()
                return
        self._log("There is nobody to talk to.", style="grey50")

    # ------------------------------------------------------------------
    # Quest log
    # ------------------------------------------------------------------
    def action_show_quest_log(self) -> None:
        gs = self.game_state
        if not gs.quest_log:
            return
        ql = gs.quest_log
        active = ql.active
        completed = ql.completed
        turned_in = ql.turned_in

        self._log("\u2500 Quest Log \u2500", style="bold bright_cyan")
        if active:
            for q in active:
                if q.quest_type == QuestType.EXPLORE_DEPTH:
                    prog = f"depth {q.progress}/{q.target_depth}"
                else:
                    prog = f"{q.progress}/{q.target_count}"
                self._log(f"  [{prog}] {q.name}: {q.description}", style="bright_yellow")
        if completed:
            for q in completed:
                self._log(f"  [DONE] {q.name} — return to NPC", style="bright_green")
        if turned_in:
            for q in turned_in[-3:]:
                self._log(f"  [TURNED IN] {q.name}", style="grey50")
        if not active and not completed and not turned_in:
            self._log("  No quests yet. Talk to NPCs!", style="grey50")

    # ------------------------------------------------------------------
    # Spellcasting
    # ------------------------------------------------------------------
    def action_cast_spell(self) -> None:
        gs = self.game_state
        if not gs.player:
            return
        player = gs.player

        if player.char_class not in ("mage", "cleric"):
            self._log("Only mages and clerics can cast spells.", style="grey50")
            return

        if not player.spell_slots.has_any():
            self._log("You have no spell slots.", style="grey50")
            return

        # Get available spells based on context
        if gs.in_combat:
            spells = spell_db.combat_spells(player.char_class, player.spell_slots)
        else:
            spells = spell_db.castable(player.char_class, player.spell_slots)

        if not spells:
            self._log("No spells available to cast.", style="grey50")
            return

        # Build slots info string
        slots_parts = []
        for lvl in range(1, 4):
            avail = player.spell_slots.available(lvl)
            mx = player.spell_slots.max_slots[lvl - 1]
            if mx > 0:
                slots_parts.append(f"L{lvl}: {avail}/{mx}")
        slots_info = "Spell Slots: " + "  ".join(slots_parts)

        self.push_screen(
            SpellSelectionScreen(spells, slots_info),
            self._on_spell_selected,
        )

    def _on_spell_selected(self, spell: SpellTemplate | None) -> None:
        if spell is None:
            return
        gs = self.game_state
        bus.publish("spell_cast")

        if gs.in_combat:
            gs.combat.player_cast(spell)
            self._flush_combat_log()
            if gs.combat.result == CombatResult.PLAYER_WIN:
                self._end_combat_victory()
            elif gs.combat.result == CombatResult.PLAYER_DEAD:
                self._end_combat_death()
            gs.turn += 1
        else:
            self._cast_utility_spell(spell)

        self._refresh_all()

    def _cast_utility_spell(self, spell: SpellTemplate) -> None:
        """Cast a utility spell outside of combat."""
        gs = self.game_state
        player = gs.player

        if spell.type != "utility":
            # Allow combat spells outside combat only for heals
            if spell.type == "combat_heal":
                if player.spell_slots.use(spell.level):
                    from dreagoth.entities.item import roll_dice as roll_spell_dice
                    healed = player.heal(roll_spell_dice(spell.heal))
                    self._log(f"You cast {spell.name}, healing {healed} HP.", style="bright_green")
                return
            self._log("That spell can only be cast in combat.", style="grey50")
            return

        if not player.spell_slots.use(spell.level):
            self._log("No spell slots remaining!", style="bright_red")
            return

        self._log(f"You cast {spell.name}.", style="bold bright_cyan")

        if spell.effect == "fov_extend":
            buff = ActiveBuff(
                spell_id=spell.id, effect="fov_extend",
                value=spell.value, remaining_turns=spell.duration,
            )
            player.active_buffs.append(buff)
            self._log("Magical light illuminates the darkness!", style="bright_yellow")
            self._update_fov()

        elif spell.effect == "unlock":
            door_pos = self._find_nearby_locked_door()
            if door_pos:
                dx, dy = door_pos
                level = gs.current_level
                level[dx, dy] = unlock_door(level[dx, dy])
                gs.ensure_opened_doors(gs.current_depth).add((dx, dy))
                self._log("The lock clicks open!", style="bright_green")
                self._update_fov()
            else:
                self._log("There is no locked door nearby.", style="grey50")

        elif spell.effect == "detect_magic":
            buff = ActiveBuff(
                spell_id=spell.id, effect="detect_magic",
                value=spell.value, remaining_turns=spell.duration,
            )
            player.active_buffs.append(buff)
            self._log("Your senses heighten to magical auras.", style="bright_magenta")

    # ------------------------------------------------------------------
    # Use consumable items
    # ------------------------------------------------------------------
    def action_use_item(self) -> None:
        gs = self.game_state
        if not gs.player:
            return

        consumables = [i for i in gs.player.inventory if i.is_consumable]
        if not consumables:
            self._log("You have no consumable items.", style="grey50")
            return

        self.push_screen(
            UseItemScreen(consumables, gs.player.level),
            self._on_item_used,
        )

    def _on_item_used(self, item: Item | None) -> None:
        if item is None:
            return
        gs = self.game_state
        bus.publish("use_item")

        if item.is_scroll:
            self._use_scroll(item)
            self._refresh_all()
            return

        if gs.in_combat:
            gs.combat.player_use_item(item)
            self._flush_combat_log()
            if gs.combat.result == CombatResult.PLAYER_DEAD:
                self._end_combat_death()
            gs.turn += 1
        else:
            result = gs.player.use_item(item)
            if result:
                msg, _healed = result
                self._log(msg, style="bright_green")

        self._refresh_all()

    def _use_scroll(self, scroll: Item) -> None:
        """Use a scroll — applies its spell effect and consumes it."""
        gs = self.game_state
        player = gs.player
        spell = spell_db.get(scroll.spell_id)
        if not spell:
            self._log(f"The scroll crumbles to dust — the magic is unknown.", style="grey50")
            player.inventory.remove(scroll)
            return

        # For unlock scrolls, verify a locked door exists nearby before consuming
        if spell.effect == "unlock":
            door_pos = self._find_nearby_locked_door()
            if door_pos is None:
                self._log("There is no locked door nearby.", style="grey50")
                return  # Don't consume the scroll
            # Consume and unlock
            player.inventory.remove(scroll)
            self._log(f"You read the {scroll.name}.", style="bold bright_cyan")
            dx, dy = door_pos
            level = gs.current_level
            level[dx, dy] = unlock_door(level[dx, dy])
            gs.ensure_opened_doors(gs.current_depth).add((dx, dy))
            self._log("The lock clicks open!", style="bright_green")
            self._update_fov()
            return

        # Remove the scroll from inventory
        player.inventory.remove(scroll)
        self._log(f"You read the {scroll.name}.", style="bold bright_cyan")

        # Apply spell effect based on type
        if spell.type == "combat_damage":
            if gs.in_combat:
                from dreagoth.entities.item import roll_dice as roll_spell_dice
                dmg = max(1, roll_spell_dice(spell.damage))
                monster = gs.combat.monster
                actual = monster.take_damage(dmg)
                self._log(
                    f"The spell strikes {monster.name} for {actual} damage!",
                    style="bright_yellow",
                )
                if monster.is_dead:
                    gs.combat.result = CombatResult.PLAYER_WIN
                    self._end_combat_victory()
                else:
                    # Monster retaliates
                    gs.combat._monster_attacks()
                    self._flush_combat_log()
                    if gs.combat.result == CombatResult.PLAYER_DEAD:
                        self._end_combat_death()
                gs.turn += 1
            else:
                self._log("The spell fizzles — there is no target.", style="grey50")

        elif spell.type == "combat_heal":
            from dreagoth.entities.item import roll_dice as roll_spell_dice
            healed = player.heal(roll_spell_dice(spell.heal))
            self._log(f"You are healed for {healed} HP. ({player.hp}/{player.max_hp})", style="bright_green")
            if gs.in_combat:
                gs.combat._monster_attacks()
                self._flush_combat_log()
                if gs.combat.result == CombatResult.PLAYER_DEAD:
                    self._end_combat_death()
                gs.turn += 1

        elif spell.type == "combat_buff":
            buff = ActiveBuff(
                spell_id=spell.id, effect=spell.effect,
                value=spell.value, remaining_turns=spell.duration,
            )
            player.active_buffs.append(buff)
            self._log(f"{spell.description}", style="bright_cyan")
            if gs.in_combat:
                gs.combat._monster_attacks()
                self._flush_combat_log()
                if gs.combat.result == CombatResult.PLAYER_DEAD:
                    self._end_combat_death()
                gs.turn += 1

        elif spell.type == "utility":
            # Reuse the same utility logic as spell casting
            self._apply_scroll_utility(spell)

    def _apply_scroll_utility(self, spell: SpellTemplate) -> None:
        """Apply a utility spell from a scroll."""
        gs = self.game_state
        player = gs.player

        if spell.effect == "fov_extend":
            buff = ActiveBuff(
                spell_id=spell.id, effect="fov_extend",
                value=spell.value, remaining_turns=spell.duration,
            )
            player.active_buffs.append(buff)
            self._log("Magical light illuminates the darkness!", style="bright_yellow")
            self._update_fov()

        elif spell.effect == "unlock":
            door_pos = self._find_nearby_locked_door()
            if door_pos:
                dx, dy = door_pos
                level = gs.current_level
                level[dx, dy] = unlock_door(level[dx, dy])
                gs.ensure_opened_doors(gs.current_depth).add((dx, dy))
                self._log("The lock clicks open!", style="bright_green")
                self._update_fov()
            else:
                self._log("There is no locked door nearby.", style="grey50")

        elif spell.effect == "detect_magic":
            buff = ActiveBuff(
                spell_id=spell.id, effect="detect_magic",
                value=spell.value, remaining_turns=spell.duration,
            )
            player.active_buffs.append(buff)
            self._log("Your senses heighten to magical auras.", style="bright_magenta")

    # ------------------------------------------------------------------
    # View toggle
    # ------------------------------------------------------------------
    def action_toggle_view(self) -> None:
        """Toggle first-person view overlay on the map."""
        self.query_one("#map-panel", MapPanel).toggle_fpv()

    # ------------------------------------------------------------------
    # Save/Load
    # ------------------------------------------------------------------
    def action_save_game(self) -> None:
        self.push_screen(SaveLoadScreen("save"), self._on_saveload)

    def action_load_game(self) -> None:
        self.push_screen(SaveLoadScreen("load"), self._on_saveload)

    def _on_saveload(self, result: tuple[str, int] | None) -> None:
        if result is None:
            return
        mode, slot = result
        gs = self.game_state

        if mode == "save":
            if save_game(gs, slot):
                self._log(f"Game saved to slot {slot}.", style="bold bright_green")
            else:
                self._log("Save failed!", style="bold bright_red")
        elif mode == "load":
            new_gs = load_game(slot)
            if new_gs:
                self.game_state = new_gs
                # Rewire all widgets
                self.query_one("#map-panel", MapPanel).set_game_state(new_gs)
                self.query_one("#stats-panel", StatsPanel).set_game_state(new_gs)
                self.query_one("#command-bar", CommandBar).set_game_state(new_gs)
                self._update_fov()
                self._prefetch_room_descriptions(new_gs.current_depth)
                self._log(f"Game loaded from slot {slot}.", style="bold bright_green")
                self._refresh_all()
                self._await_prefetch()
                return
            else:
                self._log("No save in that slot.", style="bright_red")

        self._refresh_all()

    # ------------------------------------------------------------------
    # Command mode
    # ------------------------------------------------------------------
    def action_command_mode(self) -> None:
        """Enter command input mode."""
        self.query_one("#command-bar", CommandBar).activate_input()

    def on_key(self, event) -> None:
        """Intercept keys when in command input mode."""
        bar = self.query_one("#command-bar", CommandBar)
        if bar.input_mode:
            result = bar.handle_key(event.key)
            if result is not None and result.strip():
                self._dispatch_command(result)
                self._refresh_all()
            event.prevent_default()
            event.stop()

    def _dispatch_command(self, text: str) -> None:
        """Execute a text command."""
        from dreagoth.core.command_parser import parse_command
        cmd, args = parse_command(text)
        if cmd is None:
            self._log(f"Unknown command: {text}", style="bright_red")
            return

        handler = cmd.handler_name
        # Handle parameterized handlers
        if "(" in handler:
            # e.g. "action_move('north')"
            name = handler[:handler.index("(")]
            arg_str = handler[handler.index("(") + 1:handler.index(")")]
            arg = arg_str.strip("'\"")
            method = getattr(self, name, None)
            if method:
                method(arg)
        else:
            method = getattr(self, handler, None)
            if method:
                method()

    def action_look(self) -> None:
        """Look around at the current position."""
        self._check_room_entry()
        self._check_ground_items()

    def action_show_help(self) -> None:
        """Show available commands."""
        from dreagoth.core.command_parser import COMMANDS
        self._log("\u2500 Commands \u2500", style="bold bright_cyan")
        for cmd in COMMANDS:
            aliases = ", ".join(cmd.aliases) if cmd.aliases else ""
            alias_str = f" ({aliases})" if aliases else ""
            self._log(f"  {cmd.name}{alias_str} - {cmd.description}", style="grey70")

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------
    def action_quit_game(self) -> None:
        def _handle_quit(result: str | None) -> None:
            if result == "save-quit":
                autosave(self.game_state)
                self._log("Game saved.", style="bright_green")
                self.exit()
            elif result == "quit":
                self.exit()
            # None = cancelled, do nothing

        self.push_screen(QuitScreen(), callback=_handle_quit)
