"""Command bar — bottom status line with optional command input mode."""

from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive

from dreagoth.core.command_parser import parse_command, get_completions


class CommandBar(Widget):
    """Bottom bar showing current status info, with vi-style : command input."""

    DEFAULT_CSS = """
    CommandBar {
        height: 1;
        dock: bottom;
        background: $surface;
        padding: 0 1;
    }
    """

    turn = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._game_state = None
        self._input_mode = False
        self._input_text = ""

    def set_game_state(self, state) -> None:
        self._game_state = state

    def refresh_bar(self) -> None:
        self.turn += 1

    @property
    def input_mode(self) -> bool:
        return self._input_mode

    def activate_input(self) -> None:
        """Enter command input mode."""
        self._input_mode = True
        self._input_text = ""
        self.refresh_bar()

    def deactivate_input(self) -> None:
        """Exit command input mode."""
        self._input_mode = False
        self._input_text = ""
        self.refresh_bar()

    def handle_key(self, key: str) -> str | None:
        """Handle a key in input mode. Returns command string on Enter, None otherwise."""
        if key == "escape":
            self.deactivate_input()
            return None
        elif key == "return" or key == "enter":
            result = self._input_text
            self.deactivate_input()
            return result
        elif key == "backspace":
            self._input_text = self._input_text[:-1]
            self.refresh_bar()
            return None
        elif key == "tab":
            # Tab completion
            completions = get_completions(self._input_text)
            if len(completions) == 1:
                self._input_text = completions[0]
            self.refresh_bar()
            return None
        elif len(key) == 1 and key.isprintable():
            self._input_text += key
            self.refresh_bar()
            return None
        return None

    def render(self) -> Text:
        gs = self._game_state

        if self._input_mode:
            text = Text()
            text.append(":", style="bold bright_cyan")
            text.append(self._input_text, style="white")
            text.append("\u2588", style="bright_cyan")  # cursor
            return text

        if gs is None:
            return Text("")

        text = Text()
        text.append(" Dungeons of Dreagoth II ", style="bold bright_cyan on grey23")
        text.append("  ")
        text.append(f"Level {gs.current_depth}", style="bold white")
        text.append("  ")
        text.append(f"Turn {gs.turn}", style="grey70")
        text.append("  ")
        text.append(f"({gs.player_x}, {gs.player_y})", style="grey50")
        text.append("  ")
        text.append("':' for commands", style="grey37")

        return text
