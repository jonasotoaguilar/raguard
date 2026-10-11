"""Unit tests for worker embedding provider settings (ODD-1 RED).

The worker mirrors the API provider surface: ``embedding_provider``
(``openai`` default, ``ollama`` opt-in), a validated Ollama base URL, and the
local embedding model default. Startup rejects unknown providers and invalid
base URLs when Ollama is selected.
"""

import pytest
from raguard_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit


def test_embedding_provider_defaults_match_api():
    settings = WorkerSettings()

    assert settings.embedding_provider == "openai"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_embedding_model == "qwen3-embedding:0.6b"


def test_embedding_provider_is_environment_configurable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")

    settings = WorkerSettings()

    assert settings.embedding_provider == "ollama"
    assert settings.ollama_base_url == "http://ollama:11434"


def test_startup_rejects_unknown_embedding_provider():
    with pytest.raises(ValueError, match="embedding_provider"):
        WorkerSettings(embedding_provider="cohere")


@pytest.mark.parametrize("base_url", ["", "  ", "ftp://host", "not-a-url"])
def test_startup_rejects_invalid_ollama_base_url(base_url):
    with pytest.raises(ValueError, match="ollama_base_url"):
        WorkerSettings(embedding_provider="ollama", ollama_base_url=base_url)
