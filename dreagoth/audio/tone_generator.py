"""Programmatic WAV generation for retro-style sound effects.

Uses only stdlib (math, struct, wave) — no pip deps required.
Run as: python -m dreagoth.audio.tone_generator
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22050
SOUNDS_DIR = Path(__file__).parent.parent / "data" / "sounds"


def _generate_tone(
    freq: float, duration_ms: int, volume: float = 0.5,
) -> bytes:
    """Generate a sine wave tone with fade in/out."""
    n_samples = int(SAMPLE_RATE * duration_ms / 1000)
    fade_samples = min(n_samples // 5, int(SAMPLE_RATE * 0.005))
    samples = []
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        val = math.sin(2 * math.pi * freq * t) * volume
        # Fade in
        if i < fade_samples:
            val *= i / fade_samples
        # Fade out
        elif i > n_samples - fade_samples:
            val *= (n_samples - i) / fade_samples
        samples.append(int(val * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


def _generate_noise_burst(duration_ms: int, volume: float = 0.3) -> bytes:
    """Generate white noise burst for impact sounds."""
    n_samples = int(SAMPLE_RATE * duration_ms / 1000)
    fade_samples = min(n_samples // 4, int(SAMPLE_RATE * 0.005))
    samples = []
    for i in range(n_samples):
        val = (random.random() * 2 - 1) * volume
        if i < fade_samples:
            val *= i / fade_samples
        elif i > n_samples - fade_samples:
            val *= (n_samples - i) / fade_samples
        samples.append(int(val * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


def _sweep_tone(
    freq_start: float, freq_end: float, duration_ms: int, volume: float = 0.5,
) -> bytes:
    """Generate a frequency sweep (linear interpolation)."""
    n_samples = int(SAMPLE_RATE * duration_ms / 1000)
    fade_samples = min(n_samples // 5, int(SAMPLE_RATE * 0.005))
    samples = []
    phase = 0.0
    for i in range(n_samples):
        t = i / n_samples
        freq = freq_start + (freq_end - freq_start) * t
        phase += 2 * math.pi * freq / SAMPLE_RATE
        val = math.sin(phase) * volume
        if i < fade_samples:
            val *= i / fade_samples
        elif i > n_samples - fade_samples:
            val *= (n_samples - i) / fade_samples
        samples.append(int(val * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


def _write_wav(path: Path, data: bytes) -> None:
    """Write raw PCM data to a WAV file."""
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(data)


# Sound definitions: (filename, generator_call)
SOUND_DEFS: list[tuple[str, callable]] = [
    ("footstep.wav", lambda: _generate_tone(80, 40, 0.3)),
    ("combat_start.wav", lambda: _generate_tone(150, 200, 0.5)),
    ("combat_hit.wav", lambda: _generate_noise_burst(60, 0.4)),
    ("combat_miss.wav", lambda: _generate_tone(200, 50, 0.3)),
    ("combat_crit.wav", lambda: _sweep_tone(300, 800, 150, 0.6)),
    ("monster_kill.wav", lambda: _sweep_tone(400, 200, 200, 0.5)),
    ("player_death.wav", lambda: _sweep_tone(400, 80, 500, 0.5)),
    ("level_up.wav", lambda: _sweep_tone(300, 900, 300, 0.6)),
    ("pickup_item.wav", lambda: _generate_tone(600, 80, 0.4)),
    ("pickup_gold.wav", lambda: _generate_tone(800, 60, 0.4)),
    ("stairs_descend.wav", lambda: _sweep_tone(400, 150, 250, 0.4)),
    ("stairs_ascend.wav", lambda: _sweep_tone(200, 500, 250, 0.4)),
    ("door_open.wav", lambda: _generate_noise_burst(100, 0.3)),
    ("door_locked.wav", lambda: _generate_tone(100, 150, 0.4)),
    ("spell_cast.wav", lambda: _sweep_tone(500, 1200, 200, 0.5)),
    ("quest_complete.wav", lambda: _sweep_tone(400, 800, 400, 0.5)),
    ("npc_talk.wav", lambda: _generate_tone(440, 100, 0.3)),
    ("ui_error.wav", lambda: _generate_tone(120, 200, 0.4)),
    ("room_enter.wav", lambda: _generate_tone(350, 80, 0.3)),
]


def generate_all(target_dir: Path | None = None) -> list[Path]:
    """Generate all WAV files. Returns list of created paths."""
    out_dir = target_dir or SOUNDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, gen_func in SOUND_DEFS:
        path = out_dir / filename
        data = gen_func()
        _write_wav(path, data)
        paths.append(path)
    return paths


if __name__ == "__main__":
    created = generate_all()
    for p in created:
        print(f"  Created: {p} ({p.stat().st_size} bytes)")
    print(f"\n{len(created)} sound files generated in {SOUNDS_DIR}")
