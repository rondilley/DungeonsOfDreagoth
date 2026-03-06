"""AI Dungeon Master — orchestrates AI narration with cache and fallbacks.

The DM generates atmospheric text for:
  - Room descriptions when entering a new room
  - Combat narration for crits and kills
  - Item lore for discovered equipment
  - Level themes when descending

AI is narration-only — never affects game mechanics.
Every call has a template fallback so the game works 100% offline.
"""

from __future__ import annotations

import re
import threading

from dreagoth.ai.client import ai_client
from dreagoth.ai.cache import ai_cache
from dreagoth.ai.fallback import get_fallback

SYSTEM_PROMPT = (
    "You are the Dungeon Master for a dark fantasy dungeon crawler called "
    "'Dungeons of Dreagoth'. Write brief, atmospheric descriptions in second "
    "person present tense. Keep responses to 1-3 sentences. Be vivid but concise. "
    "Never use emojis. Match the tone of classic D&D dungeon modules."
)

# Max length for user-provided text injected into prompts
_MAX_PROMPT_INPUT = 40
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9 '\-]")


def _sanitize_for_prompt(text: str) -> str:
    """Strip non-alphanumeric chars and cap length for safe prompt injection."""
    return _SAFE_NAME_RE.sub("", text)[:_MAX_PROMPT_INPUT]


class DungeonMaster:
    """AI DM that generates narration with cache-first strategy."""

    def __init__(self) -> None:
        self._prefetch_done = threading.Event()
        self._prefetch_done.set()  # No prefetch in progress initially
        self._prefetched_depths: set[int] = set()

    def describe_room(self, depth: int, room_id: int, room_size: str) -> str:
        """Generate a room description. Cache-first, then fallback.

        Never blocks — if the prefetch hasn't finished yet the caller
        gets a template fallback instantly.  The prefetched descriptions
        will be used on subsequent visits or revisits.
        """
        context = f"depth={depth},room={room_id},size={room_size}"

        cached = ai_cache.get("room_enter", context)
        if cached:
            return cached

        return get_fallback("room_enter")

    def prefetch_level_rooms(
        self, depth: int, rooms: list[tuple[int, str]],
    ) -> None:
        """Pre-generate descriptions for all rooms on a level in one API call.

        Args:
            depth: Dungeon depth.
            rooms: List of (room_id, "WxH" size string) tuples.

        Runs in a background thread. Caches each room description individually
        so that describe_room() gets instant cache hits.
        """
        if not ai_client.available or not rooms:
            return

        if depth in self._prefetched_depths:
            return

        # Mark immediately so we never retry this depth
        self._prefetched_depths.add(depth)

        # Filter out rooms already cached
        uncached: list[tuple[int, str]] = []
        for room_id, size in rooms:
            context = f"depth={depth},room={room_id},size={size}"
            if not ai_cache.get("room_enter", context):
                uncached.append((room_id, size))

        if not uncached:
            return

        # Signal that a prefetch is in progress
        self._prefetch_done.clear()

        def _do_prefetch() -> None:
            try:
                room_list = "\n".join(
                    f"  Room #{rid}: size {sz}" for rid, sz in uncached
                )
                prompt = (
                    f"Dungeon level {depth} has {len(uncached)} rooms. "
                    f"The dungeon grows more dangerous with depth. "
                    f"Level 1 is damp cellars, level 5+ is ancient evil.\n\n"
                    f"{room_list}\n\n"
                    f"For each room, write a 1-3 sentence atmospheric description. "
                    f"Format your response as a numbered list matching the room numbers:\n"
                    f"Room #<number>: <description>"
                )
                # Allow more tokens for batch response
                max_tokens = min(150 * len(uncached), 4096)
                result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=max_tokens)
                if result:
                    self._parse_and_cache_rooms(result, depth, uncached)
            finally:
                self._prefetch_done.set()

        thread = threading.Thread(target=_do_prefetch, daemon=True)
        thread.start()

    def _parse_and_cache_rooms(
        self, text: str, depth: int, rooms: list[tuple[int, str]],
    ) -> None:
        """Parse a batch AI response and cache individual room descriptions."""
        room_map = {rid: size for rid, size in rooms}

        # Split on "Room #N:" headers
        pattern = re.compile(r"Room\s*#(\d+)\s*:\s*")
        parts = pattern.split(text)
        # parts = [preamble, id1, desc1, id2, desc2, ...]
        for i in range(1, len(parts) - 1, 2):
            try:
                rid = int(parts[i])
            except ValueError:
                continue
            desc = parts[i + 1].strip()
            if not desc or rid not in room_map:
                continue
            # Strip trailing blank lines and cap at 3 sentences
            desc = desc.split("\n")[0].strip()
            context = f"depth={depth},room={rid},size={room_map[rid]}"
            ai_cache.put("room_enter", context, desc)

    def narrate_combat_start(self, monster_name: str, depth: int) -> str:
        context = f"combat_start:{monster_name}:depth={depth}"
        cached = ai_cache.get("combat_start", context)
        if cached:
            return cached

        if ai_client.available:
            prompt = (
                f"A {monster_name} attacks the adventurer on dungeon level {depth}. "
                f"Describe the start of combat in 1-2 vivid sentences."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=100)
            if result:
                ai_cache.put("combat_start", context, result)
                return result

        return get_fallback("combat_start")

    def narrate_kill(self, monster_name: str, weapon_name: str) -> str:
        context = f"kill:{monster_name}:{weapon_name}"
        cached = ai_cache.get("combat_kill", context)
        if cached:
            return cached

        if ai_client.available:
            prompt = (
                f"The adventurer kills a {monster_name} with their {weapon_name}. "
                f"Describe the killing blow in 1 vivid sentence."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=80)
            if result:
                ai_cache.put("combat_kill", context, result)
                return result

        return get_fallback("combat_kill")

    def narrate_crit(self, attacker: str, target: str) -> str:
        context = f"crit:{attacker}:{target}"
        cached = ai_cache.get("combat_crit", context)
        if cached:
            return cached

        if ai_client.available:
            prompt = (
                f"{attacker} scores a critical hit against {target}! "
                f"Describe this devastating blow in 1 sentence."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=80)
            if result:
                ai_cache.put("combat_crit", context, result)
                return result

        return get_fallback("combat_crit")

    def describe_level_theme(self, depth: int) -> str:
        context = f"level_theme:depth={depth}"
        cached = ai_cache.get("level_theme", context)
        if cached:
            return cached

        if ai_client.available:
            prompt = (
                f"The adventurer descends to dungeon level {depth}. "
                f"Describe the atmosphere and theme of this level in 1-2 sentences. "
                f"Deeper levels are more ancient and dangerous."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=100)
            if result:
                ai_cache.put("level_theme", context, result)
                return result

        return get_fallback("level_theme")

    def generate_npc_dialogue(
        self, npc_name: str, role: str, personality: str,
        depth: int, player_name: str, talked_before: bool,
    ) -> str:
        context = f"npc:{npc_name}:depth={depth}:talked={talked_before}"
        cached = ai_cache.get("npc_dialogue", context)
        if cached:
            return cached

        if ai_client.available:
            first = "greets" if not talked_before else "speaks again to"
            safe_player = _sanitize_for_prompt(player_name)
            prompt = (
                f"{npc_name} ({role}, personality: {personality}) "
                f"{first} {safe_player} on dungeon level {depth}. "
                f"Write 1-2 sentences of dialogue in character."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=120)
            if result:
                ai_cache.put("npc_dialogue", context, result)
                return result

        return get_fallback("npc_dialogue")

    def describe_quest_offer(self, npc_name: str, quest_name: str, quest_desc: str) -> str:
        context = f"quest_offer:{npc_name}:{quest_name}"
        cached = ai_cache.get("quest_offer", context)
        if cached:
            return cached

        if ai_client.available:
            prompt = (
                f"{npc_name} offers a quest: '{quest_name}' — {quest_desc}. "
                f"Write 1-2 sentences of the NPC presenting this task."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=100)
            if result:
                ai_cache.put("quest_offer", context, result)
                return result

        return get_fallback("quest_offer")

    def describe_quest_complete(self, npc_name: str, quest_name: str) -> str:
        context = f"quest_complete:{npc_name}:{quest_name}"
        cached = ai_cache.get("quest_complete", context)
        if cached:
            return cached

        if ai_client.available:
            prompt = (
                f"{npc_name} congratulates the adventurer on completing "
                f"the quest '{quest_name}'. Write 1-2 sentences in character."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=100)
            if result:
                ai_cache.put("quest_complete", context, result)
                return result

        return get_fallback("quest_complete")

    def describe_treasure(self, item_names: list[str], gold: int) -> str:
        context = f"treasure:{','.join(item_names)}:gold={gold}"
        cached = ai_cache.get("treasure_find", context)
        if cached:
            return cached

        if ai_client.available:
            items_str = ", ".join(item_names) if item_names else "no items"
            prompt = (
                f"The adventurer finds treasure: {items_str} and {gold} gold. "
                f"Describe the discovery in 1 sentence."
            )
            result = ai_client.generate(SYSTEM_PROMPT, prompt, max_tokens=80)
            if result:
                ai_cache.put("treasure_find", context, result)
                return result

        return get_fallback("treasure_find")


# Singleton
dm = DungeonMaster()
