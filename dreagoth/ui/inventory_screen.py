"""Inventory modal screen — equip, unequip, and drop items."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label, OptionList
from textual.widgets.option_list import Option

from dreagoth.entities.item import Item


class InventoryScreen(ModalScreen[str | None]):
    """Modal screen for managing inventory.

    Dismisses with an action message string, or None if closed.
    """

    CSS = """
    InventoryScreen {
        align: center middle;
    }
    #inv-box {
        width: 60;
        height: auto;
        max-height: 30;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #inv-list {
        height: 1fr;
        max-height: 20;
    }
    #inv-box Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def __init__(self, player) -> None:
        super().__init__()
        self._player = player

    def compose(self) -> ComposeResult:
        with Static(id="inv-box"):
            yield Label("Inventory", id="inv-title")
            yield Label("", id="inv-gold")
            yield Label("[Enter] Equip/Unequip  [Esc] Close", id="inv-help")
            yield OptionList(id="inv-list")
            yield Button("Close", variant="default", id="close-btn")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self, restore_index: int = 0) -> None:
        p = self._player
        gold_label = self.query_one("#inv-gold", Label)
        gold_label.update(f"Gold: {p.gold}")

        ol = self.query_one("#inv-list", OptionList)
        ol.clear_options()

        # Equipped items — selecting unequips
        _equipped_display = [
            ("weapon",  "Wielding"),
            ("armor",   "Wearing"),
            ("shield",  "Shield"),
            ("helmet",  "Helmet"),
            ("boots",   "Boots"),
            ("gloves",  "Gloves"),
            ("ring",    "Ring"),
            ("amulet",  "Amulet"),
        ]
        has_equipped = False
        for slot_name, label in _equipped_display:
            item = getattr(p, slot_name, None)
            if item:
                ol.add_option(Option(
                    f"{label + ':':<9s} {item.display_info}",
                    id=f"unequip-{slot_name}",
                ))
                has_equipped = True

        # Visual separator between equipped and backpack
        if has_equipped and p.inventory:
            ol.add_option(Option("\u2500\u2500\u2500 Backpack \u2500\u2500\u2500", id="sep", disabled=True))

        # Backpack items — selecting equips (if equippable) or shows info
        _slot_tags = {
            "": "", "body": " [armor]", "shield": " [shield]",
            "head": " [helmet]", "boots": " [boots]",
            "gloves": " [gloves]", "ring": " [ring]", "amulet": " [amulet]",
        }
        for i, item in enumerate(p.inventory):
            tag = ""
            if item.is_weapon:
                tag = " [weapon]"
            elif item.is_consumable:
                tag = " [use]"
            elif item.slot:
                tag = _slot_tags.get(item.slot, f" [{item.slot}]")
            ol.add_option(Option(f"{item.display_info_at(p.level)}{tag}", id=f"inv-{i}"))

        if not has_equipped and not p.inventory:
            ol.add_option(Option("Nothing in your possession.", id="empty"))

        count = ol.option_count
        if count > 0:
            idx = min(restore_index, count - 1)
            ol.highlighted = idx

        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id
        if opt_id is None or opt_id == "empty":
            return
        idx = event.option_index

        p = self._player

        if opt_id.startswith("unequip-"):
            slot_name = opt_id[8:]  # e.g. "weapon", "armor", "helmet"
            item = getattr(p, slot_name, None)
            if item:
                p.inventory.append(item)
                name = item.name
                setattr(p, slot_name, None)
                self._dismiss_with(f"You remove the {name}.", idx)
        elif opt_id.startswith("inv-"):
            item_idx = int(opt_id[4:])
            if item_idx < len(p.inventory):
                item = p.inventory[item_idx]
                if item.is_equippable:
                    msg = p.equip(item)
                    self._dismiss_with(msg or f"Equipped {item.name}.", idx)
                elif item.is_consumable:
                    result = p.use_item(item)
                    if result:
                        self._dismiss_with(result[0], idx)
                else:
                    # Non-equippable, non-consumable — just stay in screen
                    return

    def _dismiss_with(self, msg: str, cursor: int = 0) -> None:
        """Dismiss and return the message, or stay open if more to do."""
        self.dismiss(msg)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
