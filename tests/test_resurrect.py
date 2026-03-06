"""Tests for the resurrection system."""

from dreagoth.character.character import Character, create_character
from dreagoth.entities.item import Item, equipment_db
from dreagoth.dungeon.dungeon_level import DungeonLevel
from dreagoth.dungeon.populator import LevelEntities
from dreagoth.core.game_state import GameState


def _make_game_state(gold: int = 500, level: int = 1) -> GameState:
    """Create a minimal GameState with a character ready to die."""
    player = create_character("TestHero", "fighter", "human")
    player.level = level
    player.gold = gold
    player.is_dead = True
    player.hp = 0

    gs = GameState()
    gs.player = player
    gs.player_x = 10
    gs.player_y = 10
    gs.current_depth = 1

    # Minimal dungeon level with stairs
    dl = DungeonLevel(width=80, height=40, depth=1)
    dl.stairs_up = (5, 5)
    gs.levels[1] = dl

    gs.entities[1] = LevelEntities()
    gs.revealed[1] = set()

    return gs


def _resurrect(gs: GameState) -> bool:
    """Simulate the resurrection logic from app._end_combat_death.

    Returns True if player was resurrected, False if permanent death.
    """
    player = gs.player
    cost = min(100 * player.level, player.gold // 10)

    if player.gold > 0:
        dropped_items: list[Item] = []
        if player.weapon is not None:
            dropped_items.append(player.weapon)
            player.weapon = None
        if player.armor is not None:
            dropped_items.append(player.armor)
            player.armor = None
        if player.shield is not None:
            dropped_items.append(player.shield)
            player.shield = None
        dropped_items.extend(player.inventory)
        player.inventory = []

        if dropped_items:
            death_pos = (gs.player_x, gs.player_y)
            piles = gs.current_entities.treasure_piles
            if death_pos in piles:
                piles[death_pos].extend(dropped_items)
            else:
                piles[death_pos] = dropped_items

        player.gold -= cost
        player.is_dead = False
        player.hp = player.max_hp // 2
        player.active_buffs.clear()

        stairs = gs.current_level.stairs_up
        if stairs:
            gs.player_x, gs.player_y = stairs

        gs.combat = None
        return True
    else:
        return False


class TestResurrect:
    def test_player_resurrects_with_enough_gold(self):
        gs = _make_game_state(gold=500, level=1)
        assert _resurrect(gs) is True
        assert gs.player.is_dead is False
        assert gs.player.hp == gs.player.max_hp // 2
        # cost = min(100*1, 500//10) = min(100, 50) = 50
        assert gs.player.gold == 450

    def test_cost_capped_at_10_percent(self):
        """Cost should never exceed 10% of current gold."""
        gs = _make_game_state(gold=200, level=5)
        # min(100*5, 200//10) = min(500, 20) = 20
        _resurrect(gs)
        assert gs.player.gold == 180

    def test_cost_uses_level_formula_when_lower(self):
        """When 100*level < gold//10, use the level formula."""
        gs = _make_game_state(gold=5000, level=1)
        # min(100*1, 5000//10) = min(100, 500) = 100
        _resurrect(gs)
        assert gs.player.gold == 4900

    def test_player_moved_to_stairs(self):
        gs = _make_game_state(gold=500, level=1)
        _resurrect(gs)
        assert (gs.player_x, gs.player_y) == (5, 5)

    def test_buffs_cleared(self):
        from dreagoth.combat.spells import ActiveBuff
        gs = _make_game_state(gold=500, level=1)
        gs.player.active_buffs.append(
            ActiveBuff(spell_id="shield", effect="ac", value=2, remaining_turns=5)
        )
        _resurrect(gs)
        assert gs.player.active_buffs == []


class TestResurrectNotEnoughGold:
    def test_zero_gold_stays_dead(self):
        gs = _make_game_state(gold=0, level=1)
        assert _resurrect(gs) is False
        assert gs.player.is_dead is True

    def test_zero_gold_untouched(self):
        gs = _make_game_state(gold=0, level=1)
        _resurrect(gs)
        assert gs.player.gold == 0

    def test_zero_gold_no_treasure_pile(self):
        gs = _make_game_state(gold=0, level=1)
        gs.player.weapon = equipment_db.get("sword_long")
        _resurrect(gs)
        assert len(gs.current_entities.treasure_piles) == 0

    def test_any_gold_resurrects(self):
        """Even 1 gold is enough to resurrect (cost will be 0)."""
        gs = _make_game_state(gold=1, level=1)
        assert _resurrect(gs) is True
        # min(100, 1//10) = min(100, 0) = 0
        assert gs.player.gold == 1


class TestResurrectEquipmentDrop:
    def test_all_slots_dropped(self):
        gs = _make_game_state(gold=500, level=1)
        weapon = equipment_db.get("sword_long")
        armor = equipment_db.get("chain")
        shield = equipment_db.get("shield_large")
        gs.player.weapon = weapon
        gs.player.armor = armor
        gs.player.shield = shield

        _resurrect(gs)

        death_pos = (10, 10)  # original position
        pile = gs.current_entities.treasure_piles[death_pos]
        assert weapon in pile
        assert armor in pile
        assert shield in pile
        assert len(pile) == 3

    def test_inventory_items_dropped(self):
        gs = _make_game_state(gold=500, level=1)
        potion = equipment_db.get("potion_healing")
        gs.player.inventory = [potion]

        _resurrect(gs)

        death_pos = (10, 10)
        pile = gs.current_entities.treasure_piles[death_pos]
        assert potion in pile

    def test_equipment_slots_cleared(self):
        gs = _make_game_state(gold=500, level=1)
        gs.player.weapon = equipment_db.get("sword_long")
        gs.player.armor = equipment_db.get("chain")
        gs.player.shield = equipment_db.get("shield_large")
        gs.player.inventory = [equipment_db.get("potion_healing")]

        _resurrect(gs)

        assert gs.player.weapon is None
        assert gs.player.armor is None
        assert gs.player.shield is None
        assert gs.player.inventory == []


class TestResurrectNoItems:
    def test_no_items_no_pile(self):
        gs = _make_game_state(gold=500, level=1)
        # No weapon, armor, shield, or inventory
        _resurrect(gs)

        assert len(gs.current_entities.treasure_piles) == 0

    def test_still_resurrects(self):
        gs = _make_game_state(gold=500, level=1)
        _resurrect(gs)

        assert gs.player.is_dead is False
        assert gs.player.hp == gs.player.max_hp // 2
        # cost = min(100, 50) = 50
        assert gs.player.gold == 450
