"""Text command parser with tab completion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Command:
    """A text command that maps to a game action."""
    name: str
    aliases: list[str]
    description: str
    handler_name: str


# All available commands
COMMANDS: list[Command] = [
    Command("forward", ["fwd"], "Move forward", "action_move('forward')"),
    Command("back", ["backward"], "Move backward", "action_move('back')"),
    Command("left", ["turnleft"], "Turn left", "action_turn('left')"),
    Command("right", ["turnright"], "Turn right", "action_turn('right')"),
    Command("north", ["n"], "Move north", "action_move('north')"),
    Command("south", ["s"], "Move south", "action_move('south')"),
    Command("east", ["e"], "Move east", "action_move('east')"),
    Command("west", ["w"], "Move west", "action_move('west')"),
    Command("up", ["<", "ascend"], "Go up stairs", "action_use_stairs('up')"),
    Command("down", [">", "descend"], "Go down stairs", "action_use_stairs('down')"),
    Command("attack", ["fight", "f", "hit"], "Attack in combat", "action_combat_attack"),
    Command("flee", ["run", "escape"], "Flee from combat", "action_combat_flee"),
    Command("inventory", ["inv", "i", "pack"], "Show inventory", "action_show_inventory"),
    Command("get", ["pickup", "grab", "g"], "Pick up items", "action_pickup_items"),
    Command("cast", ["spell", "magic"], "Cast a spell", "action_cast_spell"),
    Command("talk", ["speak", "chat"], "Talk to adjacent NPC", "action_talk_npc"),
    Command("quests", ["journal", "quest", "log"], "Show quest log", "action_show_quest_log"),
    Command("save", [], "Save game", "action_save_game"),
    Command("load", [], "Load game", "action_load_game"),
    Command("view", ["toggle"], "Toggle map/first-person", "action_toggle_view"),
    Command("help", ["?", "commands"], "Show commands", "action_show_help"),
    Command("quit", ["exit", "q"], "Quit game", "action_quit_game"),
    Command("look", ["l", "examine"], "Look around", "action_look"),
    Command("stats", ["status", "info"], "Show character stats", "action_look"),
    Command("use", ["consume", "drink", "apply"], "Use a consumable item", "action_use_item"),
]

# Build lookup for fast resolution
_LOOKUP: dict[str, Command] = {}
for _cmd in COMMANDS:
    _LOOKUP[_cmd.name] = _cmd
    for _alias in _cmd.aliases:
        _LOOKUP[_alias] = _cmd


def parse_command(text: str) -> tuple[Command | None, list[str]]:
    """Parse a command string. Returns (Command, args) or (None, [])."""
    parts = text.strip().lower().split()
    if not parts:
        return None, []
    name = parts[0]
    args = parts[1:]
    cmd = _LOOKUP.get(name)
    return cmd, args


def get_completions(prefix: str) -> list[str]:
    """Get command name completions for a prefix."""
    prefix = prefix.lower()
    matches = []
    seen = set()
    for cmd in COMMANDS:
        if cmd.name.startswith(prefix) and cmd.name not in seen:
            matches.append(cmd.name)
            seen.add(cmd.name)
    return sorted(matches)


def get_all_command_names() -> list[str]:
    """Get all primary command names."""
    return [cmd.name for cmd in COMMANDS]
