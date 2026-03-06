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

    def render(self) -> Text:
        gs = self._game_state
        if gs is None or gs.current_depth not in gs.levels:
            return Text("Generating dungeon...")

        level = gs.current_level
        visible = gs.visible
        revealed = gs.ensure_revealed_set(gs.current_depth)

        # Build entity position lookups for visible tiles
        monster_positions: dict[tuple[int, int], tuple[str, str]] = {}
        npc_positions: dict[tuple[int, int], tuple[str, str]] = {}
        gold_positions: set[tuple[int, int]] = set()
        treasure_positions: set[tuple[int, int]] = set()

        if gs.current_depth in gs.entities:
            ents = gs.current_entities
            for m in ents.monsters:
                if not m.is_dead:
                    monster_positions[(m.x, m.y)] = (m.symbol, m.color)
            for n in ents.npcs:
                npc_positions[(n.x, n.y)] = (n.symbol, n.color)
            for pos in ents.gold_piles:
                gold_positions.add(pos)
            for pos in ents.treasure_piles:
                treasure_positions.add(pos)

        # Build 2D buffer: (char, style) per cell
        W, H = level.width, level.height
        buf = [[None] * W for _ in range(H)]
        for y in range(H):
            for x in range(W):
                pos = (x, y)
                if x == gs.player_x and y == gs.player_y:
                    arrow = PLAYER_ARROWS.get(gs.last_direction, PLAYER_CHAR)
                    buf[y][x] = (arrow, PLAYER_STYLE)
                elif pos in visible:
                    if pos in monster_positions:
                        sym, color = monster_positions[pos]
                        buf[y][x] = (sym, f"bold {color}")
                    elif pos in npc_positions:
                        sym, color = npc_positions[pos]
                        buf[y][x] = (sym, f"bold {color}")
                    elif pos in treasure_positions or pos in gold_positions:
                        buf[y][x] = ("$", "bold bright_yellow")
                    else:
                        buf[y][x] = self._tile_render(level[x, y])
                elif pos in revealed:
                    char, style = self._tile_render(level[x, y])
                    buf[y][x] = (char, f"dim {style}")
                else:
                    buf[y][x] = (" ", "")

        # Overlay FPV in the top-right corner
        if self._show_fpv:
            fpv = render_fpv(gs)
            if fpv:
                # Border adds 2 to each dimension
                bw = FPV_W + 2
                bh = FPV_H + 2
                ox = W - bw  # top-right corner
                oy = 0
                for r in range(bh):
                    for c in range(bw):
                        mx = ox + c
                        my = oy + r
                        if 0 <= mx < W and 0 <= my < H:
                            if r == 0 and c == 0:
                                buf[my][mx] = ("\u250c", "grey50")
                            elif r == 0 and c == bw - 1:
                                buf[my][mx] = ("\u2510", "grey50")
                            elif r == bh - 1 and c == 0:
                                buf[my][mx] = ("\u2514", "grey50")
                            elif r == bh - 1 and c == bw - 1:
                                buf[my][mx] = ("\u2518", "grey50")
                            elif r == 0 or r == bh - 1:
                                buf[my][mx] = ("\u2500", "grey50")
                            elif c == 0 or c == bw - 1:
                                buf[my][mx] = ("\u2502", "grey50")
                            else:
                                buf[my][mx] = fpv[r - 1][c - 1]

        # Convert buffer to Rich Text
        text = Text()
        for y in range(H):
            for x in range(W):
                ch, style = buf[y][x]
                text.append(ch, style=style)
            if y < H - 1:
                text.append("\n")
        return text
