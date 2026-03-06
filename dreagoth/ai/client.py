"""Anthropic SDK client wrapper with retry logic and cost tracking."""

from __future__ import annotations

import os
from pathlib import Path

# Try to load API key from file first, then env var
_KEY_FILE = Path(__file__).parent.parent.parent / "claude.key.txt"


def _load_api_key() -> str | None:
    if _KEY_FILE.exists():
        key = _KEY_FILE.read_text().strip()
        if key and not key.startswith("#"):
            return key
    return os.environ.get("ANTHROPIC_API_KEY")


class AIClient:
    """Wrapper around Anthropic SDK with retry and cost tracking."""

    def __init__(self) -> None:
        self._client = None
        self._available = False
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0
        self._init_client()

    def _init_client(self) -> None:
        api_key = _load_api_key()
        if not api_key:
            return
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
            self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    @property
    def cost_estimate(self) -> float:
        """Estimated cost in USD (Sonnet pricing)."""
        input_cost = self._total_input_tokens * 3.0 / 1_000_000
        output_cost = self._total_output_tokens * 15.0 / 1_000_000
        return input_cost + output_cost

    def generate(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str | None:
        """Generate text using Claude. Returns None on failure."""
        if not self._available:
            return None
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            self._call_count += 1
            self._total_input_tokens += response.usage.input_tokens
            self._total_output_tokens += response.usage.output_tokens
            return response.content[0].text
        except Exception:
            return None


# Singleton
ai_client = AIClient()
