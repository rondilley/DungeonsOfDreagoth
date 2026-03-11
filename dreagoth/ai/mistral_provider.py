"""Mistral AI provider — alternative to Anthropic for AI narration."""

from __future__ import annotations

import os
from pathlib import Path

_KEY_FILE = Path(__file__).parent.parent.parent / "mistral.key.txt"


def _load_api_key() -> str | None:
    if _KEY_FILE.exists():
        key = _KEY_FILE.read_text().strip()
        if key and not key.startswith("#"):
            return key
    return os.environ.get("MISTRAL_API_KEY")


class MistralProvider:
    """Mistral AI provider using the Mistral Python SDK."""

    def __init__(self) -> None:
        self._client = None
        self._available = False
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0
        self._model = "mistral-small-latest"
        self._init_client()

    def _init_client(self) -> None:
        api_key = _load_api_key()
        if not api_key:
            return
        try:
            from mistralai import Mistral
            self._client = Mistral(api_key=api_key)
            self._available = True
        except Exception:
            self._available = False

    @property
    def name(self) -> str:
        return "Mistral"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def cost_estimate(self) -> float:
        """Estimated cost in USD (Mistral Small pricing)."""
        input_cost = self._total_input_tokens * 0.1 / 1_000_000
        output_cost = self._total_output_tokens * 0.3 / 1_000_000
        return input_cost + output_cost

    def generate(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str | None:
        """Generate text using Mistral. Returns None on failure."""
        if not self._available:
            return None
        try:
            response = self._client.chat.complete(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            self._call_count += 1
            usage = response.usage
            if usage:
                self._total_input_tokens += usage.prompt_tokens
                self._total_output_tokens += usage.completion_tokens
            return response.choices[0].message.content
        except Exception:
            return None
