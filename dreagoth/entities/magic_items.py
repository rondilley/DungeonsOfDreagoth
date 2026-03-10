"""Magic item generator — random enchanted loot with rarity tiers.

On game start, `generate_startup_uniques()` creates 10 new unique items
(with AI-generated names and lore when available) and persists them to
the unique_items.json data file.
"""

from __future__ import annotations

import json
import random
import re
import uuid
from pathlib import Path

from dreagoth.entities.item import Item, equipment_db

DATA_DIR = Path(__file__).parent.parent / "data"
UNIQUE_ITEMS_PATH = DATA_DIR / "unique_items.json"

# Drop chances per rarity (rolled on each eligible loot event)
RARITY_DROP_CHANCE = {
    "magic": 0.15,    # 15%
    "rare": 0.05,     # 5%
    "epic": 0.015,    # 1.5%
    "unique": 0.005,  # 0.5%
}

# Attribute bonus ranges by rarity: (min, max) for each stat
RARITY_BONUS = {
    "magic":  {"ac": (1, 2), "attack": (1, 2), "damage": (1, 1)},
    "rare":   {"ac": (1, 3), "attack": (1, 3), "damage": (1, 2)},
    "epic":   {"ac": (2, 4), "attack": (2, 4), "damage": (1, 3)},
}

# Prefixes per rarity for naming
WEAPON_PREFIXES = {
    "magic": ["Keen", "Sharp", "Fine", "Gleaming", "Tempered"],
    "rare": ["Blazing", "Thundering", "Runic", "Enchanted", "Spectral"],
    "epic": ["Infernal", "Celestial", "Draconic", "Abyssal", "Primordial"],
}

ARMOR_PREFIXES = {
    "magic": ["Reinforced", "Hardened", "Warded", "Sturdy", "Blessed"],
    "rare": ["Enchanted", "Runeforged", "Spectral", "Glimmering", "Arcane"],
    "epic": ["Dragonforged", "Celestial", "Abyssal", "Primordial", "Mythic"],
}

ACCESSORY_PREFIXES = {
    "magic": ["Minor", "Lesser", "Faint", "Glowing", "Warm"],
    "rare": ["Greater", "Potent", "Radiant", "Shimmering", "Mystic"],
    "epic": ["Supreme", "Transcendent", "Exalted", "Divine", "Ancient"],
}


def _pick_prefix(rarity: str, item: Item) -> str:
    if item.is_weapon:
        pool = WEAPON_PREFIXES.get(rarity, WEAPON_PREFIXES["magic"])
    elif item.slot in ("ring", "amulet"):
        pool = ACCESSORY_PREFIXES.get(rarity, ACCESSORY_PREFIXES["magic"])
    else:
        pool = ARMOR_PREFIXES.get(rarity, ARMOR_PREFIXES["magic"])
    return random.choice(pool)


def _scale_damage(base_damage: str, bonus: int) -> str:
    """Add a flat bonus to a damage dice string like '1d8' -> '1d8+2'."""
    m = re.match(r"(\d+d\d+)(?:\+(\d+))?", base_damage)
    if not m:
        return base_damage
    dice = m.group(1)
    existing = int(m.group(2) or 0)
    total = existing + bonus
    if total > 0:
        return f"{dice}+{total}"
    return dice


def generate_magic_item(depth: int, rarity: str) -> Item:
    """Generate a random magic item appropriate for the given depth and rarity."""
    candidates = []
    max_value = (depth + 1) * 30
    for item in equipment_db.items.values():
        if item.category in ("weapons", "armor", "accessories"):
            if item.gold_value <= max_value:
                candidates.append(item)
    if not candidates:
        candidates = [i for i in equipment_db.items.values()
                      if i.category in ("weapons", "armor", "accessories")]

    base = random.choice(candidates)
    bonuses = RARITY_BONUS[rarity]

    prefix = _pick_prefix(rarity, base)
    name = f"{prefix} {base.name}"
    item_id = f"magic_{uuid.uuid4().hex[:8]}"

    ac_bonus = base.ac_bonus
    attack_mod = base.attack_mod
    damage = base.damage

    if base.is_weapon:
        atk_lo, atk_hi = bonuses["attack"]
        attack_mod += random.randint(atk_lo, atk_hi)
        dmg_lo, dmg_hi = bonuses["damage"]
        dmg_bonus = random.randint(dmg_lo, dmg_hi)
        if damage:
            damage = _scale_damage(damage, dmg_bonus)
    elif base.ac_bonus > 0 or base.slot:
        ac_lo, ac_hi = bonuses["ac"]
        ac_bonus += random.randint(ac_lo, ac_hi)
        if rarity in ("rare", "epic") and random.random() < 0.3:
            atk_lo, atk_hi = bonuses["attack"]
            attack_mod += random.randint(atk_lo, atk_hi)

    price_mult = {"magic": 3, "rare": 6, "epic": 12}[rarity]
    price = max(base.price * price_mult, 10)

    return Item(
        id=item_id,
        name=name,
        category=base.category,
        price=price,
        currency="G",
        damage=damage,
        weapon_type=base.weapon_type,
        range=base.range,
        classes=list(base.classes),
        ac_bonus=ac_bonus,
        attack_mod=attack_mod,
        slot=base.slot,
        two_handed=base.two_handed,
        rarity=rarity,
    )


class UniqueItemDB:
    """Tracks unique items — each can only drop once per save."""

    def __init__(self) -> None:
        self.templates: list[Item] = []
        self._dropped_ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        path = UNIQUE_ITEMS_PATH
        if not path.exists():
            return
        with open(path) as f:
            data = json.load(f)
        for entry in data["unique_items"]:
            item = Item(**entry)
            self.templates.append(item)

    def _save(self) -> None:
        """Persist current templates to disk."""
        entries = []
        for item in self.templates:
            entry: dict = {
                "id": item.id, "name": item.name,
                "category": item.category, "price": item.price,
                "currency": item.currency, "rarity": item.rarity,
                "lore": item.lore,
            }
            if item.damage:
                entry["damage"] = item.damage
            if item.weapon_type:
                entry["weapon_type"] = item.weapon_type
            if item.range:
                entry["range"] = item.range
            if item.classes:
                entry["classes"] = item.classes
            if item.ac_bonus:
                entry["ac_bonus"] = item.ac_bonus
            if item.attack_mod:
                entry["attack_mod"] = item.attack_mod
            if item.slot:
                entry["slot"] = item.slot
            if item.two_handed:
                entry["two_handed"] = item.two_handed
            entries.append(entry)
        with open(UNIQUE_ITEMS_PATH, "w") as f:
            json.dump({"unique_items": entries}, f, indent=2)
            f.write("\n")

    def add_item(self, item: Item) -> None:
        """Add a new unique item to the pool and persist."""
        self.templates.append(item)

    def available(self) -> list[Item]:
        """Items that haven't dropped yet."""
        return [i for i in self.templates if i.id not in self._dropped_ids]

    def try_drop(self, depth: int) -> Item | None:
        """Attempt to drop a unique item. Returns None if nothing drops."""
        pool = self.available()
        if not pool:
            return None
        item = random.choice(pool)
        self._dropped_ids.add(item.id)
        return item

    def mark_dropped(self, item_id: str) -> None:
        self._dropped_ids.add(item_id)

    def is_dropped(self, item_id: str) -> bool:
        return item_id in self._dropped_ids

    @property
    def dropped_ids(self) -> set[str]:
        return set(self._dropped_ids)

    @dropped_ids.setter
    def dropped_ids(self, ids: set[str]) -> None:
        self._dropped_ids = set(ids)


# Singleton
unique_item_db = UniqueItemDB()


def roll_magic_loot(depth: int, loot_tier: int) -> Item | None:
    """Roll for a magic item drop. Higher depth and loot_tier increase chances."""
    depth_mult = 1.0 + depth * 0.05
    tier_mult = 1.0 + loot_tier * 0.15

    for rarity in ("unique", "epic", "rare", "magic"):
        base_chance = RARITY_DROP_CHANCE[rarity]
        chance = base_chance * depth_mult * tier_mult

        if random.random() < chance:
            if rarity == "unique":
                item = unique_item_db.try_drop(depth)
                if item:
                    return item
                continue
            return generate_magic_item(depth, rarity)

    return None


# ---------------------------------------------------------------------------
# Startup unique item generation
# ---------------------------------------------------------------------------

# Skeletons for random unique items — balanced across all slots and classes
_UNIQUE_SKELETONS = [
    # Weapons — melee 1H
    {"cat": "weapons", "damage": "1d8+3", "wt": "melee", "classes": ["fighter"],
     "price": 400, "hint": "a legendary sword"},
    {"cat": "weapons", "damage": "2d4+3", "wt": "melee", "classes": ["fighter", "cleric"],
     "price": 350, "hint": "a holy warhammer"},
    {"cat": "weapons", "damage": "1d6+4", "wt": "melee", "classes": ["fighter", "thief"],
     "price": 350, "hint": "a shadowy dagger"},
    {"cat": "weapons", "damage": "1d4+3", "wt": "melee", "classes": ["mage"],
     "price": 300, "attack_mod": 2, "hint": "an arcane-infused weapon"},
    {"cat": "weapons", "damage": "1d6+3", "wt": "melee", "classes": ["cleric"],
     "price": 400, "hint": "a divine mace or flail"},
    # Weapons — 2H
    {"cat": "weapons", "damage": "2d6+3", "wt": "melee", "classes": ["fighter"],
     "price": 600, "two_handed": True, "hint": "a massive two-handed weapon"},
    {"cat": "weapons", "damage": "1d8+3", "wt": "melee", "classes": ["mage"],
     "price": 450, "attack_mod": 3, "two_handed": True, "hint": "a wizard's staff"},
    # Weapons — ranged
    {"cat": "weapons", "damage": "1d8+2", "wt": "ranged", "classes": ["fighter", "thief"],
     "price": 400, "range": 70, "two_handed": True, "hint": "a legendary bow"},
    # Body armor
    {"cat": "armor", "slot": "body", "ac_bonus": 7, "classes": ["fighter"],
     "price": 600, "hint": "legendary plate armor"},
    {"cat": "armor", "slot": "body", "ac_bonus": 4, "classes": ["fighter", "thief", "cleric"],
     "price": 350, "hint": "enchanted leather or chain"},
    {"cat": "armor", "slot": "body", "ac_bonus": 3, "classes": ["mage"],
     "price": 400, "hint": "magical robes"},
    # Shield
    {"cat": "armor", "slot": "shield", "ac_bonus": 3, "classes": ["fighter", "cleric"],
     "price": 450, "hint": "a legendary shield"},
    # Helmet
    {"cat": "armor", "slot": "head", "ac_bonus": 3, "classes": ["fighter"],
     "price": 400, "hint": "a helm of power"},
    {"cat": "armor", "slot": "head", "ac_bonus": 2, "classes": ["fighter", "mage", "thief", "cleric"],
     "price": 350, "hint": "a crown or circlet"},
    # Boots
    {"cat": "armor", "slot": "boots", "ac_bonus": 2, "classes": ["fighter", "mage", "thief", "cleric"],
     "price": 350, "hint": "magical boots"},
    # Gloves
    {"cat": "armor", "slot": "gloves", "ac_bonus": 2, "attack_mod": 2,
     "classes": ["fighter", "cleric"], "price": 450, "hint": "gauntlets of power"},
    # Ring
    {"cat": "accessories", "slot": "ring", "ac_bonus": 2, "attack_mod": 1,
     "classes": ["fighter", "mage", "thief", "cleric"], "price": 500, "hint": "a ring of power"},
    {"cat": "accessories", "slot": "ring", "ac_bonus": 2,
     "classes": ["fighter", "mage", "thief", "cleric"], "price": 400, "hint": "a ring of warding"},
    # Amulet
    {"cat": "accessories", "slot": "amulet", "ac_bonus": 3,
     "classes": ["fighter", "mage", "thief", "cleric"], "price": 500, "hint": "a powerful amulet"},
    {"cat": "accessories", "slot": "amulet", "ac_bonus": 2, "attack_mod": 1,
     "classes": ["fighter", "mage", "thief", "cleric"], "price": 450, "hint": "an ancient pendant"},
]

# Fallback name fragments for when AI is unavailable
_FALLBACK_PREFIXES = [
    "Ancient", "Cursed", "Blessed", "Forgotten", "Sundered", "Dread",
    "Hollow", "Ashen", "Crimson", "Obsidian", "Wraith-touched", "Storm-forged",
    "Blood-sworn", "Frost-bound", "Shadow-wrought", "Bone-carved", "Iron-bound",
    "Void-kissed", "Flame-tempered", "Thunder-marked",
]
_FALLBACK_WEAPON_NAMES = [
    "Blade", "Edge", "Fang", "Talon", "Sting", "Cleaver", "Reaver",
    "Bane", "Wrath", "Fury", "Thorn", "Shard", "Splinter",
]
_FALLBACK_ARMOR_NAMES = [
    "Ward", "Bulwark", "Aegis", "Guard", "Mantle", "Shell",
    "Bastion", "Rampart", "Carapace", "Barrier",
]
_FALLBACK_ACCESSORY_NAMES = [
    "Sigil", "Eye", "Heart", "Seal", "Mark", "Charm",
    "Rune", "Whisper", "Echo", "Remnant",
]
_FALLBACK_LORE = [
    "Pulled from the cold hands of a fallen hero in the deep.",
    "Its maker's name was erased from all histories.",
    "Dreagoth's priests once used this in their darkest rituals.",
    "The metal hums with a power that defies explanation.",
    "Found lodged in the skull of something that should not exist.",
    "It vibrates faintly, as if remembering a war long ended.",
    "The last adventurer who carried this was never seen again.",
    "Forged in an age when gods still walked these halls.",
    "The dwarven runes etched upon it are written in no known dialect.",
    "It grows warm in the presence of the undead.",
    "Older than the dungeon itself, or so the sages claim.",
    "Every previous owner met a violent end — but not from this.",
    "The gemstone at its center contains a trapped scream.",
    "It was buried with a king who refused to stay dead.",
    "The enchantment flickers, as though something inside is waking.",
    "Legend says it was shattered once, yet here it is, whole.",
    "The shadows it casts do not match its shape.",
    "It smells faintly of sulfur and forgotten oaths.",
    "A single drop of blood remains on it that will not wipe clean.",
    "The inscription reads: 'For the worthy, or the desperate.'",
]

_AI_SYSTEM_PROMPT = (
    "You are a creative writer for a dark fantasy dungeon crawler RPG called "
    "'Dungeons of Dreagoth II'. The game is set in a vast, cursed underground "
    "dungeon complex. Generate a unique item name and a one-sentence lore description.\n\n"
    "Rules:\n"
    "- The name should be 2-4 words, evocative and memorable\n"
    "- The lore should be exactly one sentence, dark fantasy tone, max 100 characters\n"
    "- Do NOT use generic names like 'Magic Sword' or 'Enchanted Shield'\n"
    "- Names should feel like legendary D&D artifacts\n"
    "- Reference the dungeon's history, fallen heroes, dark gods, or ancient civilizations\n"
    "- Output ONLY valid JSON: {\"name\": \"...\", \"lore\": \"...\"}\n"
    "- No markdown, no explanation, just the JSON object"
)


def _parse_ai_response(text: str) -> dict | None:
    """Extract name/lore JSON from AI response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if "name" in data and "lore" in data:
            return data
    except json.JSONDecodeError:
        m = re.search(r'\{[^}]+\}', text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def _fallback_name_lore(skeleton: dict) -> tuple[str, str]:
    """Generate a fallback name and lore without AI."""
    prefix = random.choice(_FALLBACK_PREFIXES)
    cat = skeleton["cat"]
    if cat == "weapons":
        suffix = random.choice(_FALLBACK_WEAPON_NAMES)
    elif cat == "accessories":
        suffix = random.choice(_FALLBACK_ACCESSORY_NAMES)
    else:
        suffix = random.choice(_FALLBACK_ARMOR_NAMES)
    name = f"{prefix} {suffix}"
    lore = random.choice(_FALLBACK_LORE)
    return name, lore


def _skeleton_to_item(skeleton: dict, name: str, lore: str) -> Item:
    """Convert a skeleton dict + AI-generated name/lore into an Item."""
    item_id = "unique_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return Item(
        id=item_id,
        name=name,
        category=skeleton["cat"],
        price=skeleton["price"],
        currency="G",
        damage=skeleton.get("damage", ""),
        weapon_type=skeleton.get("wt", ""),
        range=skeleton.get("range", 0),
        classes=skeleton.get("classes", []),
        ac_bonus=skeleton.get("ac_bonus", 0),
        attack_mod=skeleton.get("attack_mod", 0),
        slot=skeleton.get("slot", ""),
        two_handed=skeleton.get("two_handed", False),
        rarity="unique",
        lore=lore,
    )


def generate_startup_uniques(count: int = 10) -> list[Item]:
    """Generate new unique items on game start. Uses AI if available.

    Items are added to the UniqueItemDB and persisted to disk.
    Returns the list of newly generated items.
    """
    from dreagoth.ai.client import ai_client

    existing_names = {item.name for item in unique_item_db.templates}
    skeletons = random.sample(
        _UNIQUE_SKELETONS,
        min(count, len(_UNIQUE_SKELETONS)),
    )

    new_items: list[Item] = []
    for skeleton in skeletons:
        name = None
        lore = None

        if ai_client.available:
            classes = ", ".join(skeleton.get("classes", []))
            slot = skeleton.get("slot", "weapon")
            hint = skeleton["hint"]
            avoid = ", ".join(list(existing_names)[-15:]) if existing_names else "none"
            prompt = (
                f"Item type: {slot} ({hint})\n"
                f"Usable by: {classes}\n"
                f"Already used names (avoid these): {avoid}\n"
                f"Output JSON: {{\"name\": \"...\", \"lore\": \"...\"}}"
            )
            response = ai_client.generate(_AI_SYSTEM_PROMPT, prompt, max_tokens=150)
            if response:
                parsed = _parse_ai_response(response)
                if parsed:
                    name = parsed["name"]
                    lore = parsed["lore"]

        if not name:
            # Keep generating fallback names until we get one that's not taken
            for _ in range(20):
                name, lore = _fallback_name_lore(skeleton)
                if name not in existing_names:
                    break

        existing_names.add(name)
        item = _skeleton_to_item(skeleton, name, lore)
        new_items.append(item)
        unique_item_db.add_item(item)

    # Persist all templates (existing + new) to disk
    unique_item_db._save()
    return new_items
