"""Tests for the audio subsystem."""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from dreagoth.audio.tone_generator import (
    _generate_tone,
    _generate_noise_burst,
    _sweep_tone,
    generate_all,
    SAMPLE_RATE,
)
from dreagoth.audio.sound_manager import (
    SoundManager,
    AudioBackend,
    _detect_backend,
)


class TestToneGenerator:
    """Tests for programmatic WAV generation."""

    def test_generate_tone_returns_bytes(self):
        data = _generate_tone(440, 100, 0.5)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_generate_tone_correct_sample_count(self):
        duration_ms = 100
        data = _generate_tone(440, duration_ms, 0.5)
        expected_samples = int(SAMPLE_RATE * duration_ms / 1000)
        # Each sample is 2 bytes (16-bit)
        assert len(data) == expected_samples * 2

    def test_generate_noise_burst_returns_bytes(self):
        data = _generate_noise_burst(50, 0.3)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_sweep_tone_returns_bytes(self):
        data = _sweep_tone(200, 800, 150, 0.5)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_generate_all_creates_wav_files(self, tmp_path):
        paths = generate_all(tmp_path)
        assert len(paths) == 19
        for p in paths:
            assert p.exists()
            assert p.suffix == ".wav"
            assert p.stat().st_size > 44  # WAV header is 44 bytes

    def test_generated_wav_is_valid(self, tmp_path):
        paths = generate_all(tmp_path)
        with wave.open(str(paths[0]), "r") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == SAMPLE_RATE


class TestBackendDetection:
    """Tests for audio backend detection."""

    def test_detect_playsound3_when_available(self):
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"playsound3": mock_module}):
            backend = _detect_backend()
            assert backend == AudioBackend.PLAYSOUND3

    def test_detect_fallback_without_playsound3(self):
        with patch.dict("sys.modules", {"playsound3": None}):
            backend = _detect_backend()
            assert backend in (AudioBackend.WINSOUND, AudioBackend.APLAY, AudioBackend.BELL)


class TestSoundManager:
    """Tests for SoundManager."""

    def test_enabled_default(self):
        sm = SoundManager()
        assert sm.enabled is True

    def test_disable_toggle(self):
        sm = SoundManager()
        sm.enabled = False
        assert sm.enabled is False

    def test_volume_clamping(self):
        sm = SoundManager()
        sm.volume = 1.5
        assert sm.volume == 1.0
        sm.volume = -0.5
        assert sm.volume == 0.0
        sm.volume = 0.7
        assert sm.volume == 0.7

    def test_play_disabled_is_noop(self):
        sm = SoundManager()
        sm.enabled = False
        # Should not raise
        sm.play("footstep")

    def test_play_unmapped_event_is_noop(self):
        sm = SoundManager()
        # Should not raise
        sm.play("nonexistent_event")

    def test_event_bus_integration(self):
        from dreagoth.core.events import EventBus
        test_bus = EventBus()
        sm = SoundManager()
        sm.enabled = False  # Don't actually play sounds

        calls = []
        sm.play = lambda event_name: calls.append(event_name)

        # Manually subscribe like subscribe_to_events does, but with our test bus
        for event_name in sm._mappings:
            en = event_name
            test_bus.subscribe(en, lambda _en=en, **kw: sm.play(_en))

        test_bus.publish("footstep")
        assert "footstep" in calls

    def test_mappings_loaded(self):
        sm = SoundManager()
        assert len(sm._mappings) == 23
        assert sm._mappings.get("footstep") == "footstep.wav"
        assert sm._mappings.get("combat_start") == "combat_start.wav"
