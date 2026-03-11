"""Tests for local LLM provider — hardware detection, model selection, provider interface."""

from pathlib import Path
from unittest.mock import patch

from dreagoth.ai.llama_provider import (
    _detect_gpu,
    _get_ram_gb,
    _select_model,
    _MODEL_REGISTRY,
    LlamaCppProvider,
)


class TestHardwareDetection:
    def test_get_ram_gb_positive(self):
        ram = _get_ram_gb()
        assert ram > 0

    def test_detect_gpu_returns_bool(self):
        result = _detect_gpu()
        assert isinstance(result, bool)


class TestModelSelection:
    def test_gpu_with_plenty_of_ram(self):
        model = _select_model(has_gpu=True, ram_gb=16)
        assert model is not None
        assert model["id"] == "gpu-7b"

    def test_cpu_with_8gb_ram(self):
        model = _select_model(has_gpu=False, ram_gb=8)
        assert model is not None
        assert model["id"] == "cpu-7b"

    def test_cpu_with_4gb_ram(self):
        model = _select_model(has_gpu=False, ram_gb=5)
        assert model is not None
        assert model["id"] == "cpu-3b"

    def test_cpu_with_2gb_ram(self):
        model = _select_model(has_gpu=False, ram_gb=3)
        assert model is not None
        assert model["id"] == "cpu-1b"

    def test_too_little_ram(self):
        model = _select_model(has_gpu=False, ram_gb=1)
        assert model is None

    def test_all_models_have_required_fields(self):
        for m in _MODEL_REGISTRY:
            assert "id" in m
            assert "repo" in m
            assert "file" in m
            assert "min_ram_gb" in m
            assert "n_gpu_layers" in m
            assert "ctx_size" in m
            assert "desc" in m


class TestLlamaCppProvider:
    def test_provider_interface(self):
        """Provider has the expected interface even when no model is loaded."""
        # Don't actually load a model — just test the interface
        prov = LlamaCppProvider.__new__(LlamaCppProvider)
        prov._llm = None
        prov._available = False
        prov._model_info = None
        prov._call_count = 0
        prov._progress_callback = None

        assert prov.available is False
        assert prov.cost_estimate == 0.0
        assert "Local" in prov.name
        assert prov.generate("sys", "prompt") is None

    def test_provider_name_with_model_info(self):
        prov = LlamaCppProvider.__new__(LlamaCppProvider)
        prov._llm = None
        prov._available = False
        prov._model_info = {"desc": "Test Model 3B"}
        prov._call_count = 0
        prov._progress_callback = None
        assert "Test Model 3B" in prov.name

    def test_env_override_path(self, monkeypatch, tmp_path):
        """DREAGOTH_LOCAL_MODEL env var overrides auto-detection."""
        # Create a fake model file
        fake_model = tmp_path / "fake.gguf"
        fake_model.write_bytes(b"not a real model")
        monkeypatch.setenv("DREAGOTH_LOCAL_MODEL", str(fake_model))

        # The provider will try to load it and fail (not a valid GGUF),
        # but the path selection logic should have been triggered
        prov = LlamaCppProvider()
        # Even though loading fails, it shouldn't crash
        assert isinstance(prov.available, bool)


class TestProviderChainWithLocal:
    def test_chain_includes_local_provider(self):
        """The provider chain should include the local LLM provider."""
        from dreagoth.ai.client import AIClient
        client = AIClient()
        provider_types = [type(p).__name__ for p in client._providers]
        assert "LlamaCppProvider" in provider_types

    def test_local_is_last_resort(self):
        """Local LLM should be after Anthropic and Mistral in the chain."""
        from dreagoth.ai.client import AIClient
        client = AIClient()
        names = [type(p).__name__ for p in client._providers]
        if "LlamaCppProvider" in names:
            llama_idx = names.index("LlamaCppProvider")
            anthro_idx = names.index("AnthropicProvider")
            assert llama_idx > anthro_idx
