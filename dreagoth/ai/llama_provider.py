"""Local LLM provider via llama-cpp-python — runs when no API keys are available.

Automatically detects hardware (GPU VRAM, system RAM) and selects an
appropriate GGUF model.  Downloads the model from HuggingFace on first use
to ``~/.dreagoth/models/``.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Where we store downloaded models
_MODELS_DIR = Path.home() / ".dreagoth" / "models"

# Model registry: (repo_id, filename, min_ram_gb, needs_gpu, description)
# Ordered from best to most constrained — first match wins.
_MODEL_REGISTRY: list[dict] = [
    {
        "id": "gpu-7b",
        "repo": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
        "file": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "min_ram_gb": 6,
        "needs_gpu": True,
        "n_gpu_layers": -1,  # offload all layers
        "ctx_size": 2048,
        "desc": "Mistral 7B Q4_K_M (GPU)",
    },
    {
        "id": "cpu-7b",
        "repo": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
        "file": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "min_ram_gb": 8,
        "needs_gpu": False,
        "n_gpu_layers": 0,
        "ctx_size": 2048,
        "desc": "Mistral 7B Q4_K_M (CPU)",
    },
    {
        "id": "cpu-3b",
        "repo": "bartowski/Llama-3.2-3B-Instruct-GGUF",
        "file": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 4,
        "needs_gpu": False,
        "n_gpu_layers": 0,
        "ctx_size": 2048,
        "desc": "Llama 3.2 3B Q4_K_M (CPU)",
    },
    {
        "id": "cpu-1b",
        "repo": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "file": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 2,
        "needs_gpu": False,
        "n_gpu_layers": 0,
        "ctx_size": 2048,
        "desc": "Llama 3.2 1B Q4_K_M (CPU)",
    },
]


def _detect_gpu() -> bool:
    """Check if an NVIDIA GPU is available."""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_ram_gb() -> float:
    """Return total system RAM in GB."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 4.0  # Conservative default


def _select_model(has_gpu: bool, ram_gb: float) -> dict | None:
    """Select the best model for the detected hardware."""
    for model in _MODEL_REGISTRY:
        if model["needs_gpu"] and not has_gpu:
            continue
        if ram_gb < model["min_ram_gb"]:
            continue
        return model
    return None


def _ensure_model(model: dict, progress_callback=None) -> Path | None:
    """Download model if not already present. Returns path or None on failure."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = _MODELS_DIR / model["file"]

    if model_path.exists():
        return model_path

    try:
        from huggingface_hub import hf_hub_download
        logger.info("Downloading %s from %s ...", model["file"], model["repo"])
        if progress_callback:
            progress_callback(f"Downloading {model['desc']}...")

        path = hf_hub_download(
            repo_id=model["repo"],
            filename=model["file"],
            local_dir=str(_MODELS_DIR),
        )
        return Path(path)
    except Exception as e:
        logger.warning("Model download failed: %s", e)
        return None


class LlamaCppProvider:
    """Local LLM provider using llama-cpp-python."""

    def __init__(self, progress_callback=None) -> None:
        self._llm = None
        self._available = False
        self._model_info: dict | None = None
        self._call_count = 0
        self._progress_callback = progress_callback
        self._init_model()

    def _init_model(self) -> None:
        """Detect hardware, select model, download if needed, and load."""
        try:
            from llama_cpp import Llama
        except ImportError:
            logger.info("llama-cpp-python not installed")
            return

        # Allow override via env var
        override_path = os.environ.get("DREAGOTH_LOCAL_MODEL")
        if override_path and Path(override_path).exists():
            self._load_model(Path(override_path), n_gpu_layers=0, ctx_size=2048)
            self._model_info = {"desc": f"Custom ({Path(override_path).name})"}
            return

        has_gpu = _detect_gpu()
        ram_gb = _get_ram_gb()
        logger.info("Hardware: GPU=%s, RAM=%.1fGB", has_gpu, ram_gb)

        model = _select_model(has_gpu, ram_gb)
        if model is None:
            logger.warning("No suitable model found for hardware")
            return

        self._model_info = model
        model_path = _ensure_model(model, self._progress_callback)
        if model_path is None:
            return

        self._load_model(
            model_path,
            n_gpu_layers=model["n_gpu_layers"],
            ctx_size=model["ctx_size"],
        )

    def _load_model(self, path: Path, n_gpu_layers: int, ctx_size: int) -> None:
        """Load the GGUF model into llama-cpp."""
        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=str(path),
                n_gpu_layers=n_gpu_layers,
                n_ctx=ctx_size,
                verbose=False,
            )
            self._available = True
            desc = self._model_info["desc"] if self._model_info else path.name
            logger.info("Loaded local model: %s", desc)
        except Exception as e:
            logger.warning("Failed to load model: %s", e)
            self._available = False

    @property
    def name(self) -> str:
        if self._model_info:
            return f"Local ({self._model_info['desc']})"
        return "Local LLM"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def cost_estimate(self) -> float:
        return 0.0  # Local inference is free

    def generate(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 200,
    ) -> str | None:
        """Generate text using the local LLM. Returns None on failure."""
        if not self._available or self._llm is None:
            return None
        try:
            # Use chat completion format (works with instruct models)
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
            )
            self._call_count += 1
            choice = response["choices"][0]
            return choice["message"]["content"]
        except Exception as e:
            logger.warning("Local LLM generation failed: %s", e)
            return None
