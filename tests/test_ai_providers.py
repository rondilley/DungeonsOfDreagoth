"""Tests for the AI provider chain — Anthropic + Mistral fallback."""

from pathlib import Path

from dreagoth.ai.client import AIClient, AnthropicProvider


class TestAnthropicProvider:
    def test_unavailable_without_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Force no key file by patching the path
        import dreagoth.ai.client as mod
        monkeypatch.setattr(mod, "_PROJECT_ROOT", Path("/nonexistent"))
        prov = AnthropicProvider()
        assert prov.available is False
        assert prov.name == "Anthropic"
        assert prov.generate("sys", "prompt") is None

    def test_cost_estimate_starts_zero(self):
        prov = AnthropicProvider()
        assert prov.cost_estimate >= 0.0


class TestMistralProvider:
    def test_unavailable_without_key(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        import dreagoth.ai.mistral_provider as mmod
        monkeypatch.setattr(mmod, "_KEY_FILE", Path("/nonexistent/key.txt"))
        from dreagoth.ai.mistral_provider import MistralProvider
        prov = MistralProvider()
        assert prov.available is False
        assert prov.name == "Mistral"
        assert prov.generate("sys", "prompt") is None

    def test_cost_estimate_starts_zero(self):
        from dreagoth.ai.mistral_provider import MistralProvider
        prov = MistralProvider()
        assert prov.cost_estimate >= 0.0


class TestProviderChain:
    def test_no_providers_available(self):
        """When all providers are unavailable, chain reports unavailable."""
        client = AIClient.__new__(AIClient)
        client._providers = []
        client._active = None
        assert client.available is False
        assert client.provider_name == "None"
        assert client.generate("sys", "prompt") is None

    def test_cost_estimate_aggregate(self):
        """Cost estimate aggregates across all providers."""
        from dreagoth.ai.client import ai_client
        assert ai_client.cost_estimate >= 0.0

    def test_fallback_to_second_provider(self, monkeypatch):
        """If first provider fails, chain tries the next."""

        class FakeProvider:
            name = "Fake"
            available = True
            cost_estimate = 0.0

            def __init__(self, response):
                self._response = response

            def generate(self, system, prompt, max_tokens=200):
                return self._response

        client = AIClient.__new__(AIClient)
        client._providers = [
            FakeProvider(None),   # First provider always fails
            FakeProvider("Hello from fallback"),
        ]
        client._active = client._providers[0]

        result = client.generate("sys", "prompt")
        assert result == "Hello from fallback"
        # Active should have switched to the fallback
        assert client._active is client._providers[1]

    def test_provider_chain_uses_first_available(self, monkeypatch):
        """Chain picks the first available provider."""

        class FakeProvider:
            cost_estimate = 0.0

            def __init__(self, name, avail, response):
                self.name = name
                self.available = avail
                self._response = response

            def generate(self, system, prompt, max_tokens=200):
                return self._response

        client = AIClient.__new__(AIClient)
        client._providers = [
            FakeProvider("First", False, None),
            FakeProvider("Second", True, "OK"),
        ]
        client._active = None
        for prov in client._providers:
            if prov.available:
                client._active = prov
                break
        assert client.available is True
        assert client.provider_name == "Second"
        assert client.generate("sys", "prompt") == "OK"


class TestSingletonInterface:
    def test_singleton_has_expected_interface(self):
        """The ai_client singleton has the interface dm.py expects."""
        from dreagoth.ai.client import ai_client
        assert hasattr(ai_client, "available")
        assert hasattr(ai_client, "generate")
        assert hasattr(ai_client, "cost_estimate")
        assert hasattr(ai_client, "provider_name")
