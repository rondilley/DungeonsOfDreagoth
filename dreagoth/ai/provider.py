"""AI provider protocol — common interface for all AI backends."""

from __future__ import annotations

from typing import Protocol


class AIProvider(Protocol):
    """Interface that all AI providers must implement."""

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    def available(self) -> bool:
        """True if this provider is ready to generate text."""
        ...

    def generate(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str | None:
        """Generate text. Returns None on failure."""
        ...
