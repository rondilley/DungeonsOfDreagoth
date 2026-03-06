"""Template-based fallback descriptions for offline play."""

from __future__ import annotations

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

_FALLBACKS: dict[str, list[str]] = {}


def _load() -> None:
    global _FALLBACKS
    if _FALLBACKS:
        return
    path = DATA_DIR / "fallback_descriptions.json"
    with open(path) as f:
        _FALLBACKS = json.load(f)


def get_fallback(category: str) -> str:
    """Get a random fallback description for the given category."""
    _load()
    options = _FALLBACKS.get(category, [])
    if not options:
        return ""
    return random.choice(options)
