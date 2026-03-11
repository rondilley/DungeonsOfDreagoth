"""Noise and stealth system — determines how easily monsters detect the player.

Noise level depends on character class, race, and equipped armor weight.
Lower noise = harder to detect.  Thieves and halflings are quietest;
fighters in plate are loudest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dreagoth.character.character import Character

# Base noise by class (higher = louder)
CLASS_NOISE: dict[str, int] = {
    "fighter": 3,
    "cleric": 2,
    "mage": 1,
    "thief": 0,
}

# Race modifier (added to base)
RACE_NOISE: dict[str, int] = {
    "human": 0,
    "elf": -1,
    "dwarf": 1,
    "halfling": -1,
}

# Armor weight tiers based on ac_bonus
# ac_bonus 0-2 = light, 3-4 = medium, 5+ = heavy
_ARMOR_NOISE = [
    (5, 3),   # heavy: plate, splinted, banded (ac_bonus >= 5)
    (3, 2),   # medium: scale, chain, ring (ac_bonus >= 3)
    (1, 1),   # light: leather, padded, studded (ac_bonus >= 1)
]


def armor_noise(player: Character) -> int:
    """Noise penalty from equipped body armor."""
    if not player.armor:
        return 0
    ac = player.armor.ac_bonus
    for threshold, noise in _ARMOR_NOISE:
        if ac >= threshold:
            return noise
    return 0


def light_noise(player: Character) -> int:
    """Extra detection range from carrying a light source.

    Torches, lanterns, and Light spells make you easier to spot.
    """
    if player.has_active_light():
        return 3
    return 0


def noise_level(player: Character) -> int:
    """Calculate total noise level for a character.

    Returns an integer >= 0.  Higher = louder = easier to detect.
    Includes sound (class, race, armor) plus visibility (light sources).
    """
    base = CLASS_NOISE.get(player.char_class, 2)
    race_mod = RACE_NOISE.get(player.race, 0)
    armor_mod = armor_noise(player)
    light_mod = light_noise(player)
    return max(0, base + race_mod + armor_mod + light_mod)


def detection_radius(monster_speed: int, player_noise: int) -> int:
    """How far a monster can detect a player.

    Based on monster speed (faster monsters are more alert) and player noise.
    Returns radius in tiles, clamped to [3, 12].
    """
    radius = monster_speed // 3 + player_noise
    return max(3, min(12, radius))


def count_closed_doors_between(
    level,
    x0: int, y0: int,
    x1: int, y1: int,
    opened_doors: set[tuple[int, int]],
) -> int:
    """Count closed doors along a Bresenham line from (x0,y0) to (x1,y1).

    Each closed door significantly muffles sound.
    """
    from dreagoth.dungeon.tiles import is_door

    doors = 0
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    cx, cy = x0, y0

    while True:
        if (cx, cy) != (x0, y0) and (cx, cy) != (x1, y1):
            tile = level[cx, cy]
            if is_door(tile) and (cx, cy) not in opened_doors:
                doors += 1
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy

    return doors


# Each closed door reduces effective detection range by this many tiles
DOOR_NOISE_PENALTY = 4
