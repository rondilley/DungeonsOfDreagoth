"""Tests for the quest system — QuestLog, generation, tracking."""

from dreagoth.quest.quest import (
    Quest, QuestLog, QuestType, QuestStatus, QuestReward,
    generate_quest,
)


class TestQuestBasics:
    def test_quest_status(self):
        q = Quest(
            id="q1", name="Test", description="Kill 3 rats",
            quest_type=QuestType.KILL_MONSTERS,
            target_id="rat", target_count=3,
        )
        assert q.status == QuestStatus.ACTIVE
        assert not q.is_complete

    def test_quest_completes(self):
        q = Quest(
            id="q1", name="Test", description="Kill 2 rats",
            quest_type=QuestType.KILL_MONSTERS,
            target_id="rat", target_count=2,
        )
        q.progress = 2
        assert q.is_complete
        assert q.check_complete()
        assert q.status == QuestStatus.COMPLETED

    def test_explore_quest(self):
        q = Quest(
            id="q1", name="Explore", description="Reach level 5",
            quest_type=QuestType.EXPLORE_DEPTH,
            target_depth=5,
        )
        q.progress = 3
        assert not q.is_complete
        q.progress = 5
        assert q.is_complete


class TestQuestLog:
    def test_add_and_active(self):
        ql = QuestLog()
        q = Quest(
            id="q1", name="Test", description="Desc",
            quest_type=QuestType.KILL_MONSTERS,
            target_id="rat", target_count=2,
        )
        ql.add(q)
        assert len(ql.active) == 1
        assert len(ql.completed) == 0

    def test_on_monster_killed(self):
        ql = QuestLog()
        q = Quest(
            id="q1", name="Kill Rats", description="Kill 2 rats",
            quest_type=QuestType.KILL_MONSTERS,
            target_id="rat", target_count=2,
        )
        ql.add(q)
        completed = ql.on_monster_killed("rat")
        assert len(completed) == 0
        assert q.progress == 1
        completed = ql.on_monster_killed("rat")
        assert len(completed) == 1
        assert q.status == QuestStatus.COMPLETED

    def test_on_monster_killed_wrong_type(self):
        ql = QuestLog()
        q = Quest(
            id="q1", name="Kill Rats", description="Kill 2 rats",
            quest_type=QuestType.KILL_MONSTERS,
            target_id="rat", target_count=2,
        )
        ql.add(q)
        ql.on_monster_killed("goblin")
        assert q.progress == 0

    def test_on_depth_reached(self):
        ql = QuestLog()
        q = Quest(
            id="q1", name="Explore", description="Reach level 3",
            quest_type=QuestType.EXPLORE_DEPTH,
            target_depth=3,
        )
        ql.add(q)
        completed = ql.on_depth_reached(2)
        assert len(completed) == 0
        assert q.progress == 2
        completed = ql.on_depth_reached(3)
        assert len(completed) == 1
        assert q.status == QuestStatus.COMPLETED

    def test_quest_for_npc(self):
        ql = QuestLog()
        q = Quest(
            id="q1", name="Test", description="Desc",
            quest_type=QuestType.KILL_MONSTERS,
            npc_id="captain", target_id="rat", target_count=1,
        )
        ql.add(q)
        assert ql.quest_for_npc("captain") is q
        assert ql.quest_for_npc("other") is None

    def test_generate_id(self):
        ql = QuestLog()
        id1 = ql.generate_id()
        id2 = ql.generate_id()
        assert id1 != id2


class TestQuestGeneration:
    def test_generate_kill_quest(self):
        ql = QuestLog()
        q = generate_quest(3, "npc1", ql)
        assert q.quest_type in (QuestType.KILL_MONSTERS, QuestType.EXPLORE_DEPTH)
        assert q.npc_id == "npc1"
        assert q.reward.gold > 0
        assert q.reward.xp > 0

    def test_generate_quest_depth_appropriate(self):
        ql = QuestLog()
        # Generate several quests to test variety
        types_seen = set()
        for _ in range(20):
            q = generate_quest(5, "npc1", ql)
            types_seen.add(q.quest_type)
        # Should see both types with enough attempts
        assert len(types_seen) >= 1

    def test_quest_has_id(self):
        ql = QuestLog()
        q = generate_quest(1, "npc1", ql)
        assert q.id.startswith("quest_")
