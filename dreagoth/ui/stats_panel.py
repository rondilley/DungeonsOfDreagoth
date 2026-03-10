"""Stats panel widget — displays character stats, HP, equipment, gold."""

from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive


class StatsPanel(Widget):
    """Sidebar showing player stats, HP bar, equipment, and dungeon info."""

    DEFAULT_CSS = """
    StatsPanel {
        width: 24;
        height: 1fr;
        border-left: solid #808080;
        padding: 1;
    }
    """

    turn = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._game_state = None

    def set_game_state(self, state) -> None:
        self._game_state = state

    def refresh_stats(self) -> None:
        self.turn += 1

    def render(self) -> Text:
        gs = self._game_state
        if gs is None:
            return Text("No game")

        text = Text()
        player = gs.player

        if player:
            # Name and class
            text.append(f"{player.name}\n", style="bold bright_cyan")
            text.append(
                f"L{player.level} {player.race.title()} "
                f"{player.char_class.title()}\n",
                style="grey70",
            )
            text.append("\n")

            # HP bar
            hp_pct = player.hp / max(1, player.max_hp)
            hp_color = "bright_green" if hp_pct > 0.5 else "bright_yellow" if hp_pct > 0.25 else "bright_red"
            bar_width = 18
            filled = int(hp_pct * bar_width)
            text.append("HP ", style="grey70")
            text.append("\u2588" * filled, style=hp_color)
            text.append("\u2591" * (bar_width - filled), style="grey23")
            text.append(f"\n   {player.hp}/{player.max_hp}\n", style=hp_color)
            text.append("\n")

            # Abilities
            text.append("STR ", style="grey50")
            text.append(f"{player.strength:2d}", style="white")
            text.append("  DEX ", style="grey50")
            text.append(f"{player.dexterity:2d}\n", style="white")
            text.append("CON ", style="grey50")
            text.append(f"{player.constitution:2d}", style="white")
            text.append("  INT ", style="grey50")
            text.append(f"{player.intelligence:2d}\n", style="white")
            text.append("WIS ", style="grey50")
            text.append(f"{player.wisdom:2d}", style="white")
            text.append("  CHA ", style="grey50")
            text.append(f"{player.charisma:2d}\n", style="white")
            text.append("\n")

            # AC and attack
            text.append("AC ", style="grey50")
            text.append(f"{player.ac}", style="bold white")
            text.append("  Atk ", style="grey50")
            text.append(f"+{player.attack_bonus}\n", style="bold white")

            # Equipment
            _equip_display = [
                ("Wpn", player.weapon, "Fists"),
                ("Arm", player.armor, None),
                ("Shd", player.shield, None),
                ("Hlm", player.helmet, None),
                ("Bts", player.boots, None),
                ("Glv", player.gloves, None),
                ("Rng", player.ring, None),
                ("Aml", player.amulet, None),
            ]
            for label, item, fallback in _equip_display:
                if item:
                    text.append(f"{label} ", style="grey50")
                    style = item.rarity_color or "white"
                    text.append(f"{item.name}\n", style=style)
                elif fallback:
                    text.append(f"{label} ", style="grey50")
                    text.append(f"{fallback}\n", style="grey37")
            text.append("\n")

            # Gold and XP
            text.append("Gold ", style="bright_yellow")
            text.append(f"{player.gold}\n", style="bold bright_yellow")
            text.append("XP   ", style="grey50")
            text.append(f"{player.xp}", style="white")
            text.append(f" (next: {player.xp_to_next})\n", style="grey37")
            text.append("\n")

            # Inventory count
            text.append(f"Pack: {len(player.inventory)} items\n", style="grey50")

            # Spell slots (mage/cleric only)
            if player.spell_slots.has_any():
                text.append("Spells ", style="bright_cyan")
                for lvl in range(1, 4):
                    mx = player.spell_slots.max_slots[lvl - 1]
                    if mx > 0:
                        used = player.spell_slots.used_slots[lvl - 1]
                        avail = mx - used
                        text.append(f"L{lvl} ", style="grey50")
                        text.append("\u25cf" * avail, style="bright_cyan")
                        text.append("\u25cb" * used, style="grey37")
                        text.append(" ", style="")
                text.append("\n")
        else:
            text.append("DUNGEONS OF\n", style="bold bright_cyan")
            text.append("  DREAGOTH II\n\n", style="bold bright_cyan")

        # Dungeon info
        text.append("\u2500" * 20 + "\n", style="grey37")
        text.append("Depth: ", style="grey70")
        text.append(f"Level {gs.current_depth}\n", style="bold white")
        text.append("Turn:  ", style="grey70")
        text.append(f"{gs.turn}\n", style="white")

        # Minimap
        text.append("\n")
        if gs.current_depth in gs.levels:
            level = gs.current_level
            revealed = gs.ensure_revealed_set(gs.current_depth)
            # Pre-compute stair positions for fast lookup
            stair_tiles = frozenset({0x07, 0x08, 0x09})
            stair_positions: set[tuple[int, int]] = set()
            for pos in revealed:
                tx, ty = pos
                if level.in_bounds(tx, ty) and level[tx, ty] in stair_tiles:
                    stair_positions.add(pos)
            # Player minimap cell
            pmx, pmy = gs.player_x // 4, gs.player_y // 4
            # Compress 80x40 to 20x10
            for my in range(10):
                for mx in range(20):
                    if mx == pmx and my == pmy:
                        from dreagoth.ui.colors import PLAYER_ARROWS
                        arrow = PLAYER_ARROWS.get(gs.last_direction, "@")
                        text.append(arrow, style="bold bright_yellow")
                        continue
                    # Check 4x4 block
                    gx, gy = mx * 4, my * 4
                    has_tile = False
                    is_stair = False
                    for sx in range(4):
                        for sy in range(4):
                            pos = (gx + sx, gy + sy)
                            if pos in revealed:
                                has_tile = True
                                if pos in stair_positions:
                                    is_stair = True
                    if is_stair:
                        text.append("*", style="bright_cyan")
                    elif has_tile:
                        text.append("\u2588", style="grey37")
                    else:
                        text.append(" ")
                text.append("\n")

        # Combat state indicator
        if gs.in_combat:
            text.append("\n")
            text.append(" COMBAT ", style="bold white on red")
            text.append(f"\n  vs {gs.combat.monster.name}\n", style="bright_red")
            m = gs.combat.monster
            text.append(f"  HP: {m.hp}/{m.max_hp}\n", style="bright_red")

        return text
