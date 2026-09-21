"""Unit tests for the bounded chat settings (task 3.2 RED).

The design fixes defaults (chat_model="gpt-4o-mini", chat_max_output_tokens=500,
chat_retries=2) and requires startup rejection of out-of-range chat bounds
(max_output_tokens 1..2000, retries 0..2, shared provider timeout > 0).
"""

import pytest
from raguard_api.config import Settings

pytestmark = pytest.mark.unit

JWT_SECRET = "a" * 32


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret=JWT_SECRET, **overrides)


def test_chat_defaults_match_design():
    settings = _settings()

    assert settings.chat_model == "gpt-4o-mini"
    assert settings.chat_max_output_tokens == 500
    assert settings.chat_retries == 2
    assert settings.chat_provider == "openai"
    assert settings.ollama_chat_model == "qwen3:1.7b"


def test_chat_fields_are_environment_configurable(monkeypatch):
    monkeypatch.setenv("CHAT_MODEL", "gpt-4o")
    monkeypatch.setenv("CHAT_MAX_OUTPUT_TOKENS", "800")
    monkeypatch.setenv("CHAT_RETRIES", "1")

    settings = _settings()

    assert settings.chat_model == "gpt-4o"
    assert settings.chat_max_output_tokens == 800
    assert settings.chat_retries == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chat_max_output_tokens", 0),
        ("chat_max_output_tokens", 2001),
        ("chat_retries", -1),
        ("chat_retries", 3),
        ("provider_timeout_seconds", 0),
    ],
)
def test_startup_rejects_out_of_range_chat_values(field, value):
    with pytest.raises(ValueError):
        _settings(**{field: value})


def test_chat_bounds_are_inclusive():
    settings = _settings(chat_max_output_tokens=2000, chat_retries=0)

    assert settings.chat_max_output_tokens == 2000
    assert settings.chat_retries == 0


@pytest.mark.parametrize("model", ["", "   "])
def test_chat_model_must_not_be_blank(model):
    with pytest.raises(ValueError, match="chat_model"):
        _settings(chat_model=model)


def test_chat_provider_fields_are_environment_configurable(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen3:1.7b")

    settings = _settings()

    assert settings.chat_provider == "ollama"
    assert settings.ollama_chat_model == "qwen3:1.7b"


def test_startup_rejects_unknown_chat_provider():
    with pytest.raises(ValueError, match="chat_provider"):
        _settings(chat_provider="cohere")


def test_ollama_chat_provider_requires_validated_base_url():
    with pytest.raises(ValueError, match="ollama_base_url"):
        _settings(chat_provider="ollama", ollama_base_url="ftp://host")


def test_ollama_chat_model_must_not_be_blank():
    with pytest.raises(ValueError, match="ollama_chat_model"):
        _settings(chat_provider="ollama", ollama_chat_model="   ")
