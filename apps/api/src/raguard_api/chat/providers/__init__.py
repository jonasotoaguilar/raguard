"""Chat completion providers (PR 3, ODD-2): bounded, lazy, typed failures."""

from raguard_api.chat.contracts import ChatCompleter
from raguard_api.chat.providers.ollama import OllamaCompleter, create_ollama_client
from raguard_api.chat.providers.openai import (
    CompletionError,
    OpenAICompleter,
    backoff_delay_seconds,
    create_openai_client,
    retryable_http_status,
)

__all__ = [
    "CompletionError",
    "ChatCompleter",
    "OllamaCompleter",
    "OpenAICompleter",
    "backoff_delay_seconds",
    "create_completer",
    "create_ollama_client",
    "create_openai_client",
    "retryable_http_status",
]


def create_completer(*, settings) -> ChatCompleter:
    """Select the chat completer from settings; OpenAI remains the default."""
    provider = settings.chat_provider
    if provider == "ollama":
        return OllamaCompleter(
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            max_output_tokens=settings.chat_max_output_tokens,
            timeout_seconds=settings.provider_timeout_seconds,
            retries=settings.chat_retries,
        )
    if provider == "openai":
        return OpenAICompleter(
            api_key=settings.openai_api_key,
            model=settings.chat_model,
            max_output_tokens=settings.chat_max_output_tokens,
            timeout_seconds=settings.provider_timeout_seconds,
            retries=settings.chat_retries,
        )
    raise ValueError(f"chat_provider unknown: {provider!r}")
