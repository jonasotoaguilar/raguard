"""Ollama chat completion adapter (ODD-2): lazy client, bounded output, bounded retries.

The completer satisfies the ``ChatCompleter`` protocol for the ``POST /api/chat``
router over the native Ollama ``POST /api/chat`` contract: static system/user
messages, explicit ``stream: false``, and the output bound as
``options.num_predict``. The httpx client is built lazily through an injectable
factory with the shared provider timeout, so construction and offline tests never
touch the network. The application retry policy mirrors the OpenAI adapter
(timeout/connection/429/5xx only, bounded exponential waits via the shared
helpers), and every failure surfaces as the typed, detail-free
``CompletionError`` the router maps to the safe 503 envelope.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from raguard_api.chat.contracts import CompletionPrompt
from raguard_api.chat.providers.openai import (
    CompletionError,
    backoff_delay_seconds,
    retryable_http_status,
)
from raguard_api.documents.contracts import validate_ollama_base_url

_OLLAMA_CHAT_PATH = "/api/chat"
_MAX_OUTPUT_TOKENS_MAX = 2000
_MAX_RETRIES = 2
_GENERIC_FAILURE = "completion provider failed"


def create_ollama_client(*, base_url: str, timeout_seconds: float) -> httpx.Client:
    """Build a bounded httpx client for the Ollama native API."""
    return httpx.Client(base_url=base_url, timeout=timeout_seconds)


def _retryable(exc: Exception) -> bool:
    """Only timeout/connection/429/5xx failures are worth a bounded retry."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and retryable_http_status(
        exc.response.status_code
    )


def _parse_message_text(payload: Any) -> str:
    """Extract the assistant text from an /api/chat payload; fail fast when malformed."""
    message = payload["message"]
    text = message["content"]
    if not isinstance(text, str):
        raise ValueError("ollama chat response content is not text")
    return text


class OllamaCompleter:
    """``ChatCompleter`` implementation over the native Ollama chat API."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_output_tokens: int,
        timeout_seconds: float,
        retries: int,
        client: Any = None,
        client_factory: Callable[..., Any] = create_ollama_client,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        validate_ollama_base_url(base_url)
        if not model.strip():
            raise ValueError("ollama_chat_model must not be blank")
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
        self._base_url = base_url
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
            base_url=self._base_url, timeout_seconds=self._timeout_seconds
        )
        attempts = 0
        while True:
            try:
                response = client.post(
                    _OLLAMA_CHAT_PATH,
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": prompt.system_prompt},
                            {"role": "user", "content": prompt.user_prompt},
                        ],
                        "stream": False,
                        "options": {"num_predict": self._max_output_tokens},
                    },
                )
                response.raise_for_status()
            except Exception as exc:
                if not _retryable(exc) or attempts >= self._retries:
                    raise CompletionError(_GENERIC_FAILURE) from None
                self._sleep(backoff_delay_seconds(attempts))
                attempts += 1
                continue
            try:
                return _parse_message_text(response.json())
            except (KeyError, TypeError, ValueError, AttributeError):
                raise CompletionError(_GENERIC_FAILURE) from None
