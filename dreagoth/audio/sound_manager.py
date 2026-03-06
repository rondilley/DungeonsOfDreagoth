"""Sound manager with fallback chain: playsound3 → winsound → bell → silent."""

from __future__ import annotations

import json
import sys
import threading
from enum import Enum, auto
from pathlib import Path


class AudioBackend(Enum):
    PLAYSOUND3 = auto()
    WINSOUND = auto()
    BELL = auto()
    SILENT = auto()


SOUNDS_DIR = Path(__file__).parent.parent / "data" / "sounds"
SOUNDS_JSON = Path(__file__).parent.parent / "data" / "sounds.json"


def _detect_backend() -> AudioBackend:
    """Detect best available audio backend."""
    try:
        import playsound3  # noqa: F401
        return AudioBackend.PLAYSOUND3
    except ImportError:
        pass
    try:
        import winsound  # noqa: F401
        return AudioBackend.WINSOUND
    except ImportError:
        pass
    # Bell works on most terminals
    return AudioBackend.BELL


class SoundManager:
    """Event-driven sound manager. Never crashes the game."""

    def __init__(self) -> None:
        self._backend = _detect_backend()
        self._enabled = True
        self._volume = 0.5
        self._lock = threading.Lock()
        self._mappings: dict[str, str] = {}
        self._sounds_verified = False
        self._load_mappings()

    def _load_mappings(self) -> None:
        """Load event→filename mappings from sounds.json."""
        if SOUNDS_JSON.exists():
            try:
                with open(SOUNDS_JSON) as f:
                    self._mappings = json.load(f)
            except Exception:
                self._mappings = {}

    @property
    def backend(self) -> AudioBackend:
        return self._backend

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))

    def _ensure_sounds_exist(self) -> None:
        """Auto-generate WAV files if missing. Only checks once."""
        if self._sounds_verified:
            return
        self._sounds_verified = True
        if not SOUNDS_DIR.exists() or not any(SOUNDS_DIR.glob("*.wav")):
            try:
                from dreagoth.audio.tone_generator import generate_all
                generate_all()
            except Exception:
                pass

    def play(self, event_name: str) -> None:
        """Play sound for an event. No-op if disabled or unmapped."""
        if not self._enabled:
            return
        if self._backend == AudioBackend.SILENT:
            return

        filename = self._mappings.get(event_name)
        if not filename:
            return

        self._ensure_sounds_exist()
        path = SOUNDS_DIR / filename

        if self._backend == AudioBackend.BELL:
            self._play_bell()
            return

        if not path.exists():
            return

        if self._backend == AudioBackend.WINSOUND:
            # winsound.SND_ASYNC returns immediately — no thread needed
            self._play_winsound(path)
        else:
            t = threading.Thread(target=self._play_file, args=(path,), daemon=True)
            t.start()

    def _play_winsound(self, path: Path) -> None:
        """Play via winsound with SND_ASYNC (non-blocking, instant return)."""
        try:
            import winsound
            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception:
            pass

    def _play_file(self, path: Path) -> None:
        """Play a WAV file via playsound3 (blocking, runs in daemon thread)."""
        with self._lock:
            try:
                import playsound3
                playsound3.playsound(str(path))
            except Exception:
                pass  # Audio must never crash the game

    def _play_bell(self) -> None:
        """Terminal bell fallback."""
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    def subscribe_to_events(self) -> None:
        """Auto-subscribe to all mapped event names on the global event bus."""
        from dreagoth.core.events import bus
        for event_name in self._mappings:
            bus.subscribe(event_name, lambda _en=event_name, **kw: self.play(_en))


# Singleton
sound_manager = SoundManager()
