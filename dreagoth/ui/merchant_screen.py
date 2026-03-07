"""Merchant buy/sell modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label, OptionList
from textual.widgets.option_list import Option

from dreagoth.entities.item import equipment_db, Item


class MerchantScreen(ModalScreen[None]):
    """Modal screen for buying and selling items with a merchant."""

    CSS = """
    MerchantScreen {
        align: center middle;
    }
    #merchant-box {
        width: 60;
        height: auto;
        max-height: 30;
        border: double #808080;
        padding: 1 2;
        background: $surface;
    }
    #merchant-list {
        height: 1fr;
        max-height: 18;
    }
    #merchant-box Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("tab", "toggle_mode", "Toggle Buy/Sell"),
    ]

    def __init__(self, npc, player) -> None:
        super().__init__()
        self._npc = npc
        self._player = player
        self._mode = "buy"  # "buy" or "sell"

    def compose(self) -> ComposeResult:
        with Static(id="merchant-box"):
            yield Label(f"{self._npc.name} - Merchant", id="merchant-title")
            yield Label(f"Your gold: {self._player.gold}", id="gold-display")
            yield Label("[Tab] Switch mode  [Enter] Select  [Esc] Close", id="merchant-help")
            yield OptionList(id="merchant-list")
            yield Button("Switch to Sell", id="toggle-mode")
            yield Button("Close", variant="default", id="close-btn")

    def on_mount(self) -> None:
        self._refresh_items()

    def _refresh_items(self, restore_index: int = 0) -> None:
        gold_label = self.query_one("#gold-display", Label)
        gold_label.update(f"Your gold: {self._player.gold}")

        toggle = self.query_one("#toggle-mode", Button)
        ol = self.query_one("#merchant-list", OptionList)
        ol.clear_options()

        if self._mode == "buy":
            toggle.label = "Switch to Sell"
            stock = equipment_db.for_merchant_tier(self._npc.inventory_tier)
            if not stock:
                ol.add_option(Option("Nothing for sale.", id="empty"))
                ol.focus()
                return
            for i, item in enumerate(stock):
                ol.add_option(
                    Option(f"{i+1}. {item.display_info}", id=f"buy-{i}")
                )
        else:
            toggle.label = "Switch to Buy"
            inv = self._player.inventory
            if not inv:
                ol.add_option(Option("Nothing to sell.", id="empty"))
                ol.focus()
                return
            for i, item in enumerate(inv):
                sell_price = max(1, item.gold_value // 2)
                ol.add_option(
                    Option(f"{i+1}. {item.display_info} \u2192 {sell_price}G", id=f"sell-{i}")
                )

        # Restore cursor position (clamped to list bounds)
        count = ol.option_count
        if count > 0:
            idx = min(restore_index, count - 1)
            ol.highlighted = idx

        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id
        if opt_id == "empty":
            return
        idx = event.option_index
        if opt_id.startswith("buy-"):
            self._buy(int(opt_id[4:]), idx)
        elif opt_id.startswith("sell-"):
            self._sell(int(opt_id[5:]), idx)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss(None)
        elif event.button.id == "toggle-mode":
            self.action_toggle_mode()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_toggle_mode(self) -> None:
        self._mode = "sell" if self._mode == "buy" else "buy"
        self._refresh_items()

    def _buy(self, index: int, cursor: int = 0) -> None:
        stock = equipment_db.for_merchant_tier(self._npc.inventory_tier)
        if index < len(stock):
            item = stock[index]
            if self._player.gold >= item.gold_value:
                self._player.gold -= item.gold_value
                self._player.inventory.append(Item(
                    id=item.id, name=item.name, category=item.category,
                    price=item.price, currency=item.currency,
                    damage=item.damage, weapon_type=item.weapon_type,
                    range=item.range, classes=list(item.classes),
                    ac_bonus=item.ac_bonus, slot=item.slot,
                    consumable=item.consumable, heal_dice=item.heal_dice,
                ))
        self._refresh_items(restore_index=cursor)

    def _sell(self, index: int, cursor: int = 0) -> None:
        inv = self._player.inventory
        if index < len(inv):
            item = inv[index]
            sell_price = max(1, item.gold_value // 2)
            self._player.gold += sell_price
            self._player.inventory.remove(item)
        self._refresh_items(restore_index=cursor)
