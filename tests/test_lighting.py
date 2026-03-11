"""Tests for the FOV/lighting system — darkvision, torches, light spells, noise."""

from dreagoth.character.character import create_character, Character
from dreagoth.combat.spells import ActiveBuff
from dreagoth.core.constants import FOV_RADIUS, RACE_DARKVISION
from dreagoth.core.noise import noise_level, light_noise
from dreagoth.entities.item import equipment_db


class TestRaceDarkvision:
    def test_elf_has_darkvision(self):
        assert RACE_DARKVISION["elf"] == 2

    def test_dwarf_has_best_darkvision(self):
        assert RACE_DARKVISION["dwarf"] > RACE_DARKVISION["elf"]
        assert RACE_DARKVISION["dwarf"] > RACE_DARKVISION["human"]

    def test_human_has_no_darkvision(self):
        assert RACE_DARKVISION["human"] == 0

    def test_halfling_has_some_darkvision(self):
        assert RACE_DARKVISION["halfling"] > RACE_DARKVISION["human"]

    def test_all_races_have_darkvision_entry(self):
        for race in ("human", "elf", "dwarf", "halfling"):
            assert race in RACE_DARKVISION


class TestTorchEquipment:
    def test_torch_has_light_radius(self):
        torch = equipment_db.get("torch")
        assert torch is not None
        assert torch.light_radius == 3
        assert torch.light_duration == 500

    def test_lantern_has_light_radius(self):
        lantern = equipment_db.get("lantern")
        assert lantern is not None
        assert lantern.light_radius == 4
        assert lantern.light_duration == 1000

    def test_torch_is_light_source(self):
        torch = equipment_db.get("torch")
        assert torch.is_light_source is True

    def test_torch_goes_in_shield_slot(self):
        torch = equipment_db.get("torch")
        assert torch.slot == "shield"

    def test_equip_torch_sets_light_remaining(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        msg = char.equip(torch)
        assert char.shield == torch
        assert char.light_remaining == 500
        assert "illuminates" in msg.lower()

    def test_equip_torch_blocked_by_two_handed(self):
        char = create_character("Test", "fighter", "human")
        # Give a two-handed weapon
        two_h = equipment_db.get("two_hand_sword")
        if two_h:
            char.weapon = two_h
            torch = equipment_db.get("torch")
            char.inventory.append(torch)
            msg = char.equip(torch)
            assert "can't" in msg.lower() or "two-handed" in msg.lower()
            assert char.shield is None

    def test_light_bonus_with_torch(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        assert char.light_bonus() == 3

    def test_light_bonus_zero_without_torch(self):
        char = create_character("Test", "fighter", "human")
        assert char.light_bonus() == 0

    def test_light_bonus_zero_when_burned_out(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        char.light_remaining = 0
        assert char.light_bonus() == 0


class TestLightBurnDown:
    def test_torch_ticks_down(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        initial = char.light_remaining
        char.tick_buffs()
        assert char.light_remaining == initial - 1

    def test_torch_burns_out(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        char.light_remaining = 1
        msgs = char.tick_buffs()
        assert char.light_remaining == 0
        assert char.shield is None
        assert any("burned out" in m for m in msgs)

    def test_torch_flicker_warning(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        char.light_remaining = 21
        msgs = char.tick_buffs()
        # Ticked from 21 to 20 — should show flicker warning
        assert char.light_remaining == 20
        assert any("flicker" in m for m in msgs)

    def test_unequip_resets_light(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        assert char.light_remaining == 500
        # Equip a regular shield over it
        shield = equipment_db.get("sm_shield")
        if shield:
            char.inventory.append(shield)
            char.equip(shield)
            assert char.light_remaining == 0


    def test_lit_torch_consumed_on_unequip(self):
        """A burning torch should not return to inventory when replaced."""
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        assert char.shield == torch
        inv_count_before = len(char.inventory)
        # Equip a shield over the burning torch
        shield = equipment_db.get("sm_shield")
        if shield:
            char.inventory.append(shield)
            char.equip(shield)
            # Torch should NOT be back in inventory (consumed)
            assert char.shield == shield
            assert char.light_remaining == 0
            torch_count = sum(1 for i in char.inventory if i.id == "torch")
            assert torch_count == 0


class TestHasActiveLight:
    def test_torch_is_active_light(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        assert char.has_active_light() is True

    def test_no_light_by_default(self):
        char = create_character("Test", "fighter", "human")
        assert char.has_active_light() is False

    def test_light_spell_is_active_light(self):
        char = create_character("Test", "mage", "human")
        char.active_buffs.append(ActiveBuff(
            spell_id="light", effect="fov_extend",
            value=4, remaining_turns=50,
        ))
        assert char.has_active_light() is True

    def test_burned_out_torch_not_active(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        char.light_remaining = 0
        assert char.has_active_light() is False


class TestLightNoise:
    def test_light_adds_noise(self):
        char = create_character("Test", "fighter", "human")
        char.armor = None
        # No light — fighter(3) + human(0) + no armor(0) = 3
        base = noise_level(char)
        assert base == 3
        # Add a torch
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        lit = noise_level(char)
        assert lit == base + 3  # light_noise returns 3

    def test_light_spell_adds_noise(self):
        char = create_character("Test", "fighter", "human")
        char.armor = None
        base = noise_level(char)
        char.active_buffs.append(ActiveBuff(
            spell_id="light", effect="fov_extend",
            value=4, remaining_turns=50,
        ))
        lit = noise_level(char)
        assert lit == base + 3

    def test_no_light_no_extra_noise(self):
        char = create_character("Test", "thief", "halfling")
        char.armor = None
        assert light_noise(char) == 0

    def test_light_noise_value(self):
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        assert light_noise(char) == 3


class TestLightSerialization:
    def test_light_remaining_saved(self):
        from dreagoth.core.save_load import _serialize_character, _deserialize_character
        char = create_character("Test", "fighter", "human")
        torch = equipment_db.get("torch")
        char.inventory.append(torch)
        char.equip(torch)
        char.light_remaining = 150

        data = _serialize_character(char)
        assert data["light_remaining"] == 150

        restored = _deserialize_character(data)
        assert restored.light_remaining == 150

    def test_old_save_defaults_light_remaining_zero(self):
        from dreagoth.core.save_load import _deserialize_character
        data = {
            "name": "Test", "char_class": "fighter", "race": "human",
            "level": 1, "xp": 0,
            "strength": 10, "dexterity": 10, "constitution": 10,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
            "hp": 10, "max_hp": 10, "gold": 50, "is_dead": False,
            "inventory": [], "weapon": None, "armor": None,
            "shield": None, "helmet": None, "boots": None,
            "gloves": None, "ring": None, "amulet": None,
        }
        restored = _deserialize_character(data)
        assert restored.light_remaining == 0


class TestFOVWithDarkvision:
    def test_dwarf_sees_further(self):
        """Dwarf should have higher effective FOV radius."""
        dwarf_bonus = RACE_DARKVISION["dwarf"]
        human_bonus = RACE_DARKVISION["human"]
        assert FOV_RADIUS + dwarf_bonus > FOV_RADIUS + human_bonus

    def test_elf_sees_further_than_human(self):
        elf_bonus = RACE_DARKVISION["elf"]
        human_bonus = RACE_DARKVISION["human"]
        assert FOV_RADIUS + elf_bonus > FOV_RADIUS + human_bonus
