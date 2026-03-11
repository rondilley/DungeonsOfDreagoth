"""AI client — provider chain: Anthropic → Mistral → local LLM → template fallback.

The singleton ``ai_client`` exposes the same ``available`` / ``generate()``
interface that the rest of the codebase relies on.  Internally it delegates
to the first provider whose API key is configured and whose SDK imported
successfully.  When no API keys are available, falls back to a local GGUF
model via llama-cpp-python (auto-downloads based on hardware).
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Anthropic provider (built-in, same code as the original AIClient)
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """Anthropic Claude provider."""

    def __init__(self) -> None:
        self._client = None
        self._available = False
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0
        self._init_client()

    def _init_client(self) -> None:
        key_file = _PROJECT_ROOT / "claude.key.txt"
        api_key: str | None = None
        if key_file.exists():
            key = key_file.read_text().strip()
            if key and not key.startswith("#"):
                api_key = key
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
            self._available = True
        except Exception:
            self._available = False

    @property
    def name(self) -> str:
        return "Anthropic"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def cost_estimate(self) -> float:
        input_cost = self._total_input_tokens * 3.0 / 1_000_000
        output_cost = self._total_output_tokens * 15.0 / 1_000_000
        return input_cost + output_cost

    def generate(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str | None:
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


# ---------------------------------------------------------------------------
# Provider chain
# ---------------------------------------------------------------------------

class AIClient:
    """Provider chain — delegates to the first available AI backend.

    Tries providers in order: Anthropic → Mistral.
    Exposes the same ``available`` / ``generate()`` / ``cost_estimate``
    interface so existing code doesn't need to change.
    """

    def __init__(self) -> None:
        self._providers: list = []
        self._active = None  # currently active provider
        self._init_providers()

    def _init_providers(self) -> None:
        # 1. Anthropic (always try first)
        anthropic_prov = AnthropicProvider()
        self._providers.append(anthropic_prov)

        # 2. Mistral (lazy import so missing SDK doesn't crash the game)
        try:
            from dreagoth.ai.mistral_provider import MistralProvider
            mistral_prov = MistralProvider()
            self._providers.append(mistral_prov)
        except Exception:
            pass

        # 3. Local LLM via llama-cpp-python (when no API keys available)
        try:
            from dreagoth.ai.llama_provider import LlamaCppProvider
            llama_prov = LlamaCppProvider()
            self._providers.append(llama_prov)
        except Exception:
            pass

        # Pick first available
        for prov in self._providers:
            if prov.available:
                self._active = prov
                break

    @property
    def available(self) -> bool:
        return self._active is not None

    @property
    def provider_name(self) -> str:
        """Name of the active provider, or 'None'."""
        return self._active.name if self._active else "None"

    @property
    def cost_estimate(self) -> float:
        """Aggregate cost across all providers that were used."""
        return sum(p.cost_estimate for p in self._providers)

    def generate(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str | None:
        """Generate text using the active provider. Returns None on failure.

        If the active provider fails, tries the next available one.
        """
        if not self._active:
            return None

        result = self._active.generate(system, prompt, max_tokens)
        if result is not None:
            return result

        # Active provider failed — try remaining providers
        for prov in self._providers:
            if prov is self._active or not prov.available:
                continue
            result = prov.generate(system, prompt, max_tokens)
            if result is not None:
                self._active = prov  # Switch to working provider
                return result

        return None


# Singleton
ai_client = AIClient()
