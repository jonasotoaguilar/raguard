"""API-side embedding adapters behind the shared Embedder (ODD-1).

Same model contract for both providers: exactly ``EMBEDDING_DIMENSION``
(1024) vectors so query vectors bind cleanly against ``halfvec(1024)``.
``OpenAIEmbedder`` requests 1024 dimensions explicitly; ``OllamaEmbedder``
uses the native ``POST /api/embed`` contract (``{"model", "input"}`` ->
``{"embeddings"}``) over a lazily-built bounded httpx client (no Ollama SDK).
Clients are built lazily on the first call through injectable factories, so
construction and every non-e2e test stay offline; a dimension mismatch fails
fast instead of reaching the database. ``create_embedder`` selects the
adapter from settings (OpenAI default).
"""

from collections.abc import Callable, Sequence
from typing import Any

from raguard_api.documents.contracts import (
    EMBEDDING_DIMENSION,
    Embedder,
    validate_ollama_base_url,
)

_OLLAMA_EMBED_PATH = "/api/embed"


def create_openai_client(*, api_key: str, timeout_seconds: float):
    """Build the real OpenAI client: bounded timeout, no SDK-level retries."""
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)


def create_ollama_client(*, base_url: str, timeout_seconds: float):
    """Build a bounded httpx client for the Ollama native API (lazy import)."""
    import httpx

    return httpx.Client(base_url=base_url, timeout=timeout_seconds)


def _checked_vectors(vectors: Sequence[Sequence[float]]) -> list[list[float]]:
    """Copy provider vectors, failing fast on any dimension mismatch."""
    checked: list[list[float]] = []
    for vector in vectors:
        values = list(vector)
        if len(values) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"embedding dimension mismatch: got {len(values)}, expected {EMBEDDING_DIMENSION}"
            )
        checked.append(values)
    return checked


class OpenAIEmbedder:
    """Embedder protocol implementation over the OpenAI embeddings API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client=None,
        client_factory: Callable[..., object] = create_openai_client,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("embedding bounds violated: require timeout > 0")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._client_factory = client_factory

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in one provider call and validate every vector."""
        client = self._client or self._client_factory(
            api_key=self._api_key, timeout_seconds=self._timeout_seconds
        )
        response = client.embeddings.create(
            model=self._model, input=list(texts), dimensions=EMBEDDING_DIMENSION
        )
        return _checked_vectors([item.embedding for item in response.data])


class OllamaEmbedder:
    """Embedder protocol implementation over the native Ollama /api/embed API."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client=None,
        client_factory: Callable[..., object] = create_ollama_client,
    ) -> None:
        validate_ollama_base_url(base_url)
        if timeout_seconds <= 0:
            raise ValueError("embedding bounds violated: require timeout > 0")
        if not model.strip():
            raise ValueError("embedding bounds violated: require a non-blank model")
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._client_factory = client_factory

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in one /api/embed call and validate every vector."""
        client = self._client or self._client_factory(
            base_url=self._base_url, timeout_seconds=self._timeout_seconds
        )
        response = client.post(
            _OLLAMA_EMBED_PATH, json={"model": self._model, "input": list(texts)}
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return _checked_vectors(payload["embeddings"])


def create_embedder(*, settings) -> Embedder:
    """Select the query embedder from settings; OpenAI remains the default."""
    provider = settings.embedding_provider
    if provider == "ollama":
        return OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embedding_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    if provider == "openai":
        return OpenAIEmbedder(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    raise ValueError(f"embedding_provider unknown: {provider!r}")
