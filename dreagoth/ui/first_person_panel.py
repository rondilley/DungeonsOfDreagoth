"""First-person dungeon view renderer — compact overlay for the map panel."""

from __future__ import annotations

from dreagoth.dungeon.tiles import (
    Tile, is_walkable, is_door, is_locked, is_magically_locked,
    has_door_flags, base_tile,
)

# Interior dimensions (excluding border)
FPV_W = 26
FPV_H = 14

# Corridor opening at each depth: (left, right, top, bottom)
_LAYERS = [
    (2, 23, 0, 13),    # depth 0 — nearest
    (5, 20, 2, 11),    # depth 1
    (9, 16, 4, 9),     # depth 2
    (11, 14, 5, 8),    # depth 3 — farthest
]

_SHADES = ["grey62", "grey50", "grey37", "grey27"]
_WALL = "\u2588"  # █


def _tile_cat(tile_val: int) -> str:
    bt = base_tile(tile_val) if has_door_flags(tile_val) else tile_val
    if bt in (Tile.WALL, Tile.UNSTABLE_WALL):
        return "wall"
    if is_door(tile_val):
        if has_door_flags(tile_val):
            if is_magically_locked(tile_val):
                return "door_magic"
            if is_locked(tile_val):
                return "door_locked"
        return "door_open"
    if bt == Tile.STAIRS_UP:
        return "stairs_up"
    if bt == Tile.STAIRS_DOWN:
        return "stairs_down"
    if bt == Tile.STAIRS_BOTH:
        return "stairs_both"
    if bt == Tile.TREASURE:
        return "treasure"
    if bt == Tile.SPECIAL:
        return "special"
    return "open"


def _side_cat(tile_val: int) -> str:
    if not is_walkable(tile_val):
        return "side_door" if is_door(tile_val) else "wall"
    return "open"


def _fill(buf, top, bot, left, right, ch, sty):
    for r in range(max(0, top), min(FPV_H, bot + 1)):
        for c in range(max(0, left), min(FPV_W, right + 1)):
            buf[r][c] = (ch, sty)


def _set(buf, r, c, ch, sty):
    if 0 <= r < FPV_H and 0 <= c < FPV_W:
        buf[r][c] = (ch, sty)


def _raycast(gs) -> list[dict]:
    level = gs.current_level
    px, py = gs.player_x, gs.player_y
    dx, dy = gs.last_direction
    ldx, ldy = -dy, dx
    rdx, rdy = dy, -dx

    slices: list[dict] = []
    for dist in range(1, 5):
        fx, fy = px + dx * dist, py + dy * dist
        if not level.in_bounds(fx, fy):
            slices.append({"cat": "wall", "left": "wall", "right": "wall",
                           "monster": None, "npc": None, "treasure": False})
            break

        cat = _tile_cat(level[fx, fy])
        lx, ly = fx + ldx, fy + ldy
        rx, ry = fx + rdx, fy + rdy
        lcat = _side_cat(level[lx, ly]) if level.in_bounds(lx, ly) else "wall"
        rcat = _side_cat(level[rx, ry]) if level.in_bounds(rx, ry) else "wall"

        monster = npc = None
        loot = False
        if gs.current_depth in gs.entities:
            ents = gs.current_entities
            m = ents.monster_at(fx, fy)
            if m and not m.is_dead:
                monster = (m.symbol, m.color, m.name)
            n = ents.npc_at(fx, fy)
            if n:
                npc = (n.symbol, n.color, n.name)
            if (fx, fy) in ents.gold_piles or (fx, fy) in ents.treasure_piles:
                loot = True

        slices.append({"cat": cat, "left": lcat, "right": rcat,
                       "monster": monster, "npc": npc, "treasure": loot})
        if cat == "wall" or cat.startswith("door_"):
            break
    return slices


def _draw_perspective(buf, outer, inner, shade):
    """Draw ceiling/floor perspective trapezoids between two depth layers."""
    oli, ori, oti, obi = outer
    ili, iri, iti, ibi = inner

    # Ceiling trapezoid (top connecting region)
    if iti > oti:
        for r in range(oti, iti):
            t = (r - oti) / (iti - oti)
            el = int(oli + t * (ili - oli))
            er = int(ori + t * (iri - ori))
            for c in range(max(0, el), min(FPV_W, er + 1)):
                buf[r][c] = (_WALL, shade)

    # Floor trapezoid (bottom connecting region)
    if obi > ibi:
        for r in range(ibi + 1, obi + 1):
            t = (r - ibi) / (obi - ibi)
            el = int(ili + t * (oli - ili))
            er = int(iri + t * (ori - iri))
            for c in range(max(0, el), min(FPV_W, er + 1)):
                buf[r][c] = (_WALL, shade)


def _draw_door(buf, li, ri, ti, bi, cat, shade):
    """Draw a closed door at a depth."""
    _fill(buf, ti, bi, li, ri, _WALL, shade)
    for c in range(li, ri + 1):
        _set(buf, ti, c, "\u2500", shade)
        _set(buf, bi, c, "\u2500", shade)
    cx = (li + ri) // 2
    dw = max(1, (ri - li) // 4)
    dtop = ti + max(1, (bi - ti) // 3)
    if cat == "door_magic":
        dch, dsty = "#", "bold bright_magenta"
    elif cat == "door_locked":
        dch, dsty = "#", "bold bright_red"
    else:
        dch, dsty = "+", "bold yellow"
    for r in range(dtop, bi + 1):
        for c in range(cx - dw, cx + dw + 1):
            if li <= c <= ri:
                _set(buf, r, c, dch, dsty)


def _draw_feature(buf, li, ri, ti, bi, ch, sty, di):
    """Draw a floor feature (stairs, treasure) at a depth."""
    cx = (li + ri) // 2
    size = max(1, 3 - di)
    floor_r = bi - 1 if bi - ti > 4 else (ti + bi) // 2
    for dc in range(-size + 1, size):
        c = cx + dc
        if li <= c <= ri:
            _set(buf, floor_r, c, ch, sty)


def _draw_entity(buf, li, ri, ti, bi, ch, sty, di):
    """Draw a monster or NPC at a depth."""
    cx = (li + ri) // 2
    height = max(2, (bi - ti) // 2 - di)
    ebot = bi - 1
    etop = max(ti + 1, ebot - height + 1)
    width = max(1, 2 - di)
    for r in range(etop, ebot + 1):
        for dc in range(-width, width + 1):
            c = cx + dc
            if li <= c <= ri:
                _set(buf, r, c, ch, sty)


def render_fpv(gs) -> list[list[tuple[str, str]]] | None:
    """Render the first-person view as a 2D buffer of (char, style) tuples.

    Returns None if no game state available. Buffer is FPV_H x FPV_W.
    """
    if gs is None or gs.current_depth not in gs.levels:
        return None

    slices = _raycast(gs)
    mid = FPV_H // 2

    # Init buffer: ceiling (dark) and floor (grey dots)
    buf: list[list[tuple[str, str]]] = []
    for r in range(FPV_H):
        row = []
        for c in range(FPV_W):
            if r < mid:
                row.append((" ", "on grey7"))
            else:
                ch = "\u00b7" if (r + c) % 3 == 0 else " "
                row.append((ch, "grey23"))
        buf.append(row)

    # Draw depth slices back-to-front
    for di in range(len(slices) - 1, -1, -1):
        sl = slices[di]
        layer = _LAYERS[min(di, 3)]
        li, ri, ti, bi = layer
        shade = _SHADES[min(di, 3)]
        cat = sl["cat"]

        # Perspective connecting lines to the next-outer layer
        if di == 0:
            outer = (0, FPV_W - 1, 0, FPV_H - 1)
        else:
            outer = _LAYERS[min(di - 1, 3)]
        _draw_perspective(buf, outer, layer, shade)

        # -- Back wall / door / features --
        if cat == "wall":
            _fill(buf, ti, bi, li, ri, _WALL, shade)
            for c in range(li, ri + 1):
                _set(buf, ti, c, "\u2500", shade)
                _set(buf, bi, c, "\u2500", shade)
        elif cat.startswith("door_"):
            _draw_door(buf, li, ri, ti, bi, cat, shade)
        else:
            feat_map = {
                "stairs_up": ("\u25b2", "bold bright_cyan"),
                "stairs_down": ("\u25bc", "bold bright_cyan"),
                "stairs_both": ("\u2666", "bold bright_cyan"),
                "special": ("!", "bold bright_magenta"),
            }
            feat = feat_map.get(cat)
            if feat:
                _draw_feature(buf, li, ri, ti, bi, feat[0], feat[1], di)

        # -- Entities --
        if sl["monster"]:
            sym, color, _ = sl["monster"]
            _draw_entity(buf, li, ri, ti, bi, sym, f"bold {color}", di)
        elif sl["npc"]:
            sym, color, _ = sl["npc"]
            _draw_entity(buf, li, ri, ti, bi, sym, f"bold {color}", di)
        elif sl["treasure"] and cat == "open":
            _draw_feature(buf, li, ri, ti, bi, "$", "bold bright_yellow", di)

        # -- Left side wall --
        if sl["left"] == "wall":
            _fill(buf, ti, bi, 0, li - 1, _WALL, shade)
        elif sl["left"] == "side_door":
            _fill(buf, ti, bi, 0, li - 1, _WALL, shade)
            dtop = ti + (bi - ti) // 4
            dbot = bi - (bi - ti) // 6
            for r in range(dtop, dbot + 1):
                _set(buf, r, li - 1, "+", "bold yellow")
        else:
            # Open side passage — dark opening
            _fill(buf, ti + 1, bi - 1, 0, li - 1, " ", "on grey3")
            # Passage frame
            for c in range(0, min(li, FPV_W)):
                _set(buf, ti, c, "\u2500", "grey50")
                _set(buf, bi, c, "\u2500", "grey50")

        # -- Right side wall --
        if sl["right"] == "wall":
            _fill(buf, ti, bi, ri + 1, FPV_W - 1, _WALL, shade)
        elif sl["right"] == "side_door":
            _fill(buf, ti, bi, ri + 1, FPV_W - 1, _WALL, shade)
            dtop = ti + (bi - ti) // 4
            dbot = bi - (bi - ti) // 6
            for r in range(dtop, dbot + 1):
                _set(buf, r, ri + 1, "+", "bold yellow")
        else:
            # Open side passage — dark opening
            _fill(buf, ti + 1, bi - 1, ri + 1, FPV_W - 1, " ", "on grey3")
            for c in range(ri + 1, FPV_W):
                _set(buf, ti, c, "\u2500", "grey50")
                _set(buf, bi, c, "\u2500", "grey50")

    return buf
