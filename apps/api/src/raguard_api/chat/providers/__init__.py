"""OpenAI chat completion provider (PR 3): bounded, lazy, typed failures."""

from raguard_api.chat.providers.openai import (
    CompletionError,
    OpenAICompleter,
    create_openai_client,
)

__all__ = ["CompletionError", "OpenAICompleter", "create_openai_client"]
