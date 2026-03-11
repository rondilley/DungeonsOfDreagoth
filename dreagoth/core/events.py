"""Simple synchronous event bus for decoupled pub/sub communication."""

from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> None:
        try:
            self._handlers[event].remove(handler)
        except ValueError:
            pass  # Handler not found — already unsubscribed

    def publish(self, event: str, **data: Any) -> None:
        for handler in list(self._handlers[event]):  # Copy to allow mutation
            try:
                handler(**data)
            except Exception:
                pass  # Don't let one broken handler kill all listeners


# Global event bus instance
bus = EventBus()
