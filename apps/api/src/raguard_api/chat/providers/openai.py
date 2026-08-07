"""OpenAI completion adapter (PR 3): lazy client, bounded output, bounded retries.

The completer satisfies the ``ChatCompleter`` protocol for the ``POST /api/chat``
router. The SDK client is built lazily through an injectable factory with
``max_retries=0`` and the shared provider timeout. The application retry policy
retries only timeout/connection/429/5xx failures, at most ``retries`` times with
bounded exponential waits, then raises the typed, detail-free ``CompletionError``
the router maps to the safe 503 envelope.
"""

import time
from collections.abc import Callable
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from raguard_api.chat.contracts import CompletionPrompt

_BACKOFF_BASE_SECONDS = 0.25
_BACKOFF_MAX_SECONDS = 2.0
_MAX_OUTPUT_TOKENS_MAX = 2000
_MAX_RETRIES = 2
_GENERIC_FAILURE = "completion provider failed"


class CompletionError(Exception):
    """Typed provider failure for the router's safe 503 envelope (detail-free)."""


def create_openai_client(*, api_key: str, timeout_seconds: float) -> OpenAI:
    """Build the real OpenAI client: bounded timeout, no SDK-level retries."""
    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)


def _retryable(exc: Exception) -> bool:
    """Only timeout/connection/429/5xx failures are worth a bounded retry."""
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


class OpenAICompleter:
    """``ChatCompleter`` implementation over the OpenAI Responses API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int,
        timeout_seconds: float,
        retries: int,
        client: Any = None,
        client_factory: Callable[..., Any] = create_openai_client,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 1 <= max_output_tokens <= _MAX_OUTPUT_TOKENS_MAX:
            raise ValueError(
                "chat_max_output_tokens out of bounds: "
                f"{max_output_tokens}; require 1..{_MAX_OUTPUT_TOKENS_MAX}"
            )
        if not 0 <= retries <= _MAX_RETRIES:
            raise ValueError(f"chat_retries out of bounds: {retries}; require 0..{_MAX_RETRIES}")
        if timeout_seconds <= 0:
            raise ValueError(
                f"provider_timeout_seconds out of bounds: {timeout_seconds}; require > 0"
            )
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._timeout_seconds = timeout_seconds
        self._retries = retries
        self._client = client
        self._client_factory = client_factory
        self._sleep = sleep_fn

    def complete(self, prompt: CompletionPrompt) -> str:
        """Complete ``prompt`` with bounded output and bounded application retries."""
        client = self._client or self._client_factory(
            api_key=self._api_key, timeout_seconds=self._timeout_seconds
        )
        attempts = 0
        while True:
            try:
                return client.responses.create(
                    model=self._model,
                    input=[
                        {"role": "system", "content": prompt.system_prompt},
                        {"role": "user", "content": prompt.user_prompt},
                    ],
                    max_output_tokens=self._max_output_tokens,
                ).output_text
            except Exception as exc:
                if not _retryable(exc) or attempts >= self._retries:
                    raise CompletionError(_GENERIC_FAILURE) from None
                self._sleep(min(_BACKOFF_BASE_SECONDS * 2**attempts, _BACKOFF_MAX_SECONDS))
                attempts += 1
