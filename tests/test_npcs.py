"""Tests for the NPC system — NPCDB, spawning, populator integration."""

from dreagoth.entities.npc import NPCDB, NPC, NPCTemplate, npc_db
from dreagoth.dungeon.generator import DungeonGenerator
from dreagoth.dungeon.populator import populate_level
from dreagoth.dungeon.tiles import Tile, is_door


class TestNPCDB:
    def test_loads_npcs(self):
        assert len(npc_db.templates) == 8

    def test_has_merchants(self):
        merchants = [t for t in npc_db.templates.values() if t.role == "merchant"]
        assert len(merchants) == 3

    def test_has_quest_givers(self):
        quest_givers = [t for t in npc_db.templates.values() if t.role == "quest_giver"]
        assert len(quest_givers) == 2

    def test_spawn(self):
        npc = npc_db.spawn("sage", 10, 20)
        assert npc.name == "Theron the Sage"
        assert npc.x == 10
        assert npc.y == 20
        assert npc.talked_to is False
        assert npc.quest_id is None

    def test_eligible_for_level(self):
        eligible_l1 = npc_db.eligible_for_level(1)
        assert len(eligible_l1) >= 4  # Most NPCs available at level 1
        # Wanderer 2 (min_level=4) should not be eligible
        ids = [t.id for t in eligible_l1]
        assert "wanderer_2" not in ids

    def test_eligible_deep(self):
        eligible_l10 = npc_db.eligible_for_level(10)
        ids = [t.id for t in eligible_l10]
        assert "wanderer_2" in ids
        # Wanderer 1 (max_level=5) should not be eligible
        assert "wanderer_1" not in ids

    def test_random_for_level(self):
        npc = npc_db.random_for_level(5, 3, 3)
        assert npc is not None
        assert isinstance(npc, NPC)


class TestNPCPopulator:
    def test_npcs_spawned_in_level(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(3)
        entities = populate_level(level, 3)
        assert len(entities.npcs) >= 1
        assert len(entities.npcs) <= 3

    def test_npc_at_lookup(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        entities = populate_level(level, 1)
        if entities.npcs:
            npc = entities.npcs[0]
            found = entities.npc_at(npc.x, npc.y)
            assert found is not None
            assert found.name == npc.name

    def test_npc_at_empty(self):
        gen = DungeonGenerator(seed=42)
        level = gen.generate(1)
        entities = populate_level(level, 1)
        assert entities.npc_at(0, 0) is None

    def test_npcs_not_on_or_adjacent_to_doors(self):
        """NPCs must not sit on doors or block doorways."""
        for seed in range(10):
            gen = DungeonGenerator(seed=seed)
            level = gen.generate(3)
            entities = populate_level(level, 3)
            for npc in entities.npcs:
                tile = level[npc.x, npc.y]
                assert not is_door(tile), (
                    f"Seed {seed}: NPC {npc.name} placed on door at ({npc.x},{npc.y})"
                )
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    nx, ny = npc.x + dx, npc.y + dy
                    if level.in_bounds(nx, ny):
                        assert not is_door(level[nx, ny]), (
                            f"Seed {seed}: NPC {npc.name} at ({npc.x},{npc.y}) "
                            f"adjacent to door at ({nx},{ny})"
                        )

    def test_no_duplicate_npcs_per_level(self):
        """Each NPC template should appear at most once per level."""
        for seed in range(20):
            gen = DungeonGenerator(seed=seed)
            level = gen.generate(3)
            entities = populate_level(level, 3)
            template_ids = [n.template_id for n in entities.npcs]
            assert len(template_ids) == len(set(template_ids)), (
                f"Seed {seed}: duplicate NPC templates: {template_ids}"
            )

    def test_npcs_on_room_tiles(self):
        """NPCs must be placed on ROOM tiles, not corridors or hallways."""
        for seed in range(10):
            gen = DungeonGenerator(seed=seed)
            level = gen.generate(3)
            entities = populate_level(level, 3)
            for npc in entities.npcs:
                assert level[npc.x, npc.y] == Tile.ROOM, (
                    f"Seed {seed}: NPC {npc.name} at ({npc.x},{npc.y}) "
                    f"on tile {level[npc.x, npc.y]:#x}, expected ROOM"
                )
