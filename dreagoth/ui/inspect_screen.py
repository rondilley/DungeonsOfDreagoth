"""Inspect item modal screen — shows detailed item properties and lore."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label, OptionList
from textual.widgets.option_list import Option

from dreagoth.entities.item import Item


class InspectScreen(ModalScreen[None]):
    """Modal screen for inspecting items — shows stats, specials, and lore."""

    CSS = """
    InspectScreen {
        align: center middle;
    }
    #inspect-box {
        width: 60;
        height: auto;
        max-height: 30;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #inspect-list {
        height: 1fr;
        max-height: 20;
    }
    #inspect-detail {
        height: auto;
        max-height: 14;
        padding: 0 1;
        margin-top: 1;
        border: solid #555555;
    }
    #inspect-box Button {
        width: 100%;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def __init__(self, player) -> None:
        super().__init__()
        self._player = player

    def compose(self) -> ComposeResult:
        with Static(id="inspect-box"):
            yield Label("[bold]Inspect Items[/bold]  (select to view details)", id="inspect-title")
            yield OptionList(id="inspect-list")
            yield Static("", id="inspect-detail")
            yield Button("Close", variant="default", id="close-btn")

    def on_mount(self) -> None:
        self._build_list()

    def _all_items(self) -> list[tuple[str, Item]]:
        """Collect all equipped + inventory items with labels."""
        items: list[tuple[str, Item]] = []
        p = self._player
        _equipped = [
            ("weapon", "Wielding"),
            ("armor", "Wearing"),
            ("shield", "Shield"),
            ("helmet", "Helmet"),
            ("boots", "Boots"),
            ("gloves", "Gloves"),
            ("ring", "Ring"),
            ("amulet", "Amulet"),
        ]
        for slot_name, label in _equipped:
            item = getattr(p, slot_name, None)
            if item:
                items.append((f"{label}: ", item))

        seen: set[str] = set()
        for item in p.inventory:
            if item.id not in seen:
                items.append(("", item))
                seen.add(item.id)
        return items

    def _build_list(self) -> None:
        ol = self.query_one("#inspect-list", OptionList)
        ol.clear_options()
        items = self._all_items()
        if not items:
            ol.add_option(Option("No items to inspect.", id="empty", disabled=True))
        else:
            for i, (prefix, item) in enumerate(items):
                color = item.rarity_color
                name = item.name
                if color:
                    display = f"{prefix}[{color}]{name}[/{color}]"
                else:
                    display = f"{prefix}{name}"
                if item.specials:
                    display += " [bright_cyan]*[/bright_cyan]"
                ol.add_option(Option(display, id=f"item-{i}"))
        ol.focus()
        # Show first item details
        if items:
            ol.highlighted = 0
            self._show_detail(items[0][1])

    def _show_detail(self, item: Item) -> None:
        detail = self.query_one("#inspect-detail", Static)
        lines = item.inspect_lines(self._player.level)
        detail.update("\n".join(lines))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        opt_id = event.option.id
        if not opt_id or opt_id == "empty":
            return
        idx = int(opt_id.split("-")[1])
        items = self._all_items()
        if 0 <= idx < len(items):
            self._show_detail(items[idx][1])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # Same as highlight — just show detail
        self.on_option_list_option_highlighted(event)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
