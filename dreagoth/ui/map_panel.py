"""Map panel widget — renders the dungeon grid with fog of war, monsters, treasure."""

from rich.text import Text
from textual.widget import Widget
from textual.reactive import reactive

from dreagoth.dungeon.tiles import Tile, is_door, is_locked, is_magically_locked, has_door_flags, base_tile
from dreagoth.ui.colors import TILE_APPEARANCE, PLAYER_CHAR, PLAYER_STYLE, PLAYER_ARROWS
from dreagoth.ui.first_person_panel import render_fpv, FPV_W, FPV_H


class MapPanel(Widget):
    """Renders the dungeon map with player, monsters, treasure, and fog of war."""

    DEFAULT_CSS = """
    MapPanel {
        width: 1fr;
        height: 1fr;
        overflow: hidden;
    }
    """

    turn = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._game_state = None
        self._show_fpv = False

    def set_game_state(self, state) -> None:
        self._game_state = state

    def refresh_map(self) -> None:
        self.turn += 1

    def toggle_fpv(self) -> None:
        self._show_fpv = not self._show_fpv
        self.turn += 1

    @staticmethod
    def _tile_render(tile_val: int) -> tuple[str, str]:
        """Return (char, style) for a tile value, handling door flags."""
        if has_door_flags(tile_val) and is_door(tile_val):
            if is_magically_locked(tile_val):
                return ("+", "bold bright_magenta")
            elif is_locked(tile_val):
                return ("+", "bold bright_red")
        bt = base_tile(tile_val)
        return TILE_APPEARANCE.get(bt, TILE_APPEARANCE.get(tile_val, ("?", "bright_red")))

    def _viewport(self, map_w: int, map_h: int) -> tuple[int, int, int, int]:
        """Compute viewport (vx, vy, vw, vh) centered on the player.

        Returns the top-left corner and dimensions of the visible region,
        clamped to map bounds.
        """
        gs = self._game_state
        size = self.size
        vw = min(size.width, map_w)
        vh = min(size.height, map_h)

        # Center on player, clamp to map edges
        vx = max(0, min(gs.player_x - vw // 2, map_w - vw))
        vy = max(0, min(gs.player_y - vh // 2, map_h - vh))
        return vx, vy, vw, vh

    def render(self) -> Text:
        gs = self._game_state
        if gs is None or gs.current_depth not in gs.levels:
            return Text("Generating dungeon...")

        level = gs.current_level
        visible = gs.visible
        revealed = gs.ensure_revealed_set(gs.current_depth)

        W, H = level.width, level.height
        vx, vy, vw, vh = self._viewport(W, H)

        # Build entity position lookups for visible tiles
        monster_positions: dict[tuple[int, int], tuple[str, str]] = {}
        npc_positions: dict[tuple[int, int], tuple[str, str]] = {}
        gold_positions: set[tuple[int, int]] = set()
        treasure_positions: set[tuple[int, int]] = set()
        trap_positions: dict[tuple[int, int], tuple[str, str]] = {}
        rope_positions: set[tuple[int, int]] = set()

        if gs.current_depth in gs.entities:
            ents = gs.current_entities
            for m in ents.monsters:
                if not m.is_dead:
                    color = "bold bright_red" if m.is_alert else m.color
                    monster_positions[(m.x, m.y)] = (m.symbol, color)
            for n in ents.npcs:
                npc_positions[(n.x, n.y)] = (n.symbol, n.color)
            for pos in ents.gold_piles:
                gold_positions.add(pos)
            for pos in ents.treasure_piles:
                treasure_positions.add(pos)
            for t in ents.traps:
                if t.detected and not t.triggered:
                    trap_positions[(t.x, t.y)] = ("^", "bold bright_magenta")
                elif t.detected and t.triggered and t.trap_type.value in ("pit", "trap_door"):
                    trap_positions[(t.x, t.y)] = ("o", "grey50")

        # Rope connections on this level
        ropes = gs.rope_connections.get(gs.current_depth, {})
        for pos in ropes:
            rope_positions.add(pos)

        # Check if player has an active light source for warm tint
        has_light = gs.player and gs.player.has_active_light()

        # Use the actual widget content width for the buffer so every
        # character maps 1-to-1 to a Textual cell.
        content_w = self.size.width or vw
        buf = [[(" ", "")] * content_w for _ in range(vh)]
        for row in range(vh):
            y = vy + row
            for col in range(vw):
                x = vx + col
                pos = (x, y)
                if x == gs.player_x and y == gs.player_y:
                    arrow = PLAYER_ARROWS.get(gs.last_direction, PLAYER_CHAR)
                    buf[row][col] = (arrow, PLAYER_STYLE)
                elif pos in visible:
                    if pos in monster_positions:
                        sym, color = monster_positions[pos]
                        buf[row][col] = (sym, f"bold {color}")
                    elif pos in npc_positions:
                        sym, color = npc_positions[pos]
                        buf[row][col] = (sym, f"bold {color}")
                    elif pos in trap_positions:
                        sym, color = trap_positions[pos]
                        buf[row][col] = (sym, color)
                    elif pos in rope_positions:
                        buf[row][col] = ("~", "bold bright_cyan")
                    elif pos in treasure_positions or pos in gold_positions:
                        buf[row][col] = ("$", "bold bright_yellow")
                    else:
                        ch, style = self._tile_render(level[x, y])
                        if has_light and style and "grey" in style:
                            style = style.replace("grey70", "yellow").replace("grey50", "dark_goldenrod")
                        buf[row][col] = (ch, style)
                elif pos in revealed:
                    char, style = self._tile_render(level[x, y])
                    buf[row][col] = (char, f"dim {style}")
                else:
                    buf[row][col] = (" ", "")

        # Overlay FPV in the top-right corner of the widget
        if self._show_fpv:
            fpv = render_fpv(gs)
            if fpv:
                bw = FPV_W + 2   # border adds 2
                bh = FPV_H + 2
                ox = content_w - bw  # right-align to widget edge
                oy = 0
                for r in range(bh):
                    for c in range(bw):
                        bx = ox + c
                        by = oy + r
                        if 0 <= bx < content_w and 0 <= by < vh:
                            if r == 0 and c == 0:
                                buf[by][bx] = ("\u250c", "grey50")
                            elif r == 0 and c == bw - 1:
                                buf[by][bx] = ("\u2510", "grey50")
                            elif r == bh - 1 and c == 0:
                                buf[by][bx] = ("\u2514", "grey50")
                            elif r == bh - 1 and c == bw - 1:
                                buf[by][bx] = ("\u2518", "grey50")
                            elif r == 0 or r == bh - 1:
                                buf[by][bx] = ("\u2500", "grey50")
                            elif c == 0 or c == bw - 1:
                                buf[by][bx] = ("\u2502", "grey50")
                            else:
                                buf[by][bx] = fpv[r - 1][c - 1]

        # Convert buffer to Rich Text
        text = Text()
        for row in range(vh):
            for col in range(content_w):
                ch, style = buf[row][col]
                text.append(ch, style=style)
            if row < vh - 1:
                text.append("\n")
        return text
