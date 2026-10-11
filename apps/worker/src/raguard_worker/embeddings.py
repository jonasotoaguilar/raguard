"""Provider-neutral embedding adapters behind the Embedder protocol (ODD-1).

``OpenAIEmbedder`` calls the OpenAI embeddings API in bounded batches and
requests ``EMBEDDING_DIMENSION`` (1024) explicitly; ``OllamaEmbedder`` posts
each batch to the native ``POST /api/embed`` contract (``{"model", "input"}``
-> ``{"embeddings"}``) over a lazily-built bounded httpx client (no Ollama
SDK). Every returned vector is validated against the shared dimension
(``halfvec(1024)``) so a provider misconfiguration fails fast into the job's
``limit`` retry path instead of reaching the database. Clients are built
lazily through injectable factories, so tests inject fakes and no provider
network is ever touched in non-e2e. ``create_embedder`` selects the adapter
from settings (OpenAI default).
"""

from collections.abc import Callable, Sequence
from typing import Any

from raguard_api.documents.contracts import EMBEDDING_DIMENSION, Embedder, validate_ollama_base_url

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
        batch_size: int,
        timeout_seconds: float,
        client=None,
        client_factory: Callable[..., object] = create_openai_client,
    ) -> None:
        if batch_size < 1 or timeout_seconds <= 0:
            raise ValueError("embedding bounds violated: require batch_size >= 1 and timeout > 0")
        self._api_key = api_key
        self._model = model
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.client_factory = client_factory

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in batches of at most ``batch_size`` provider calls."""
        client = self._client or self.client_factory(
            api_key=self._api_key, timeout_seconds=self._timeout_seconds
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            response = client.embeddings.create(
                model=self._model, input=batch, dimensions=EMBEDDING_DIMENSION
            )
            vectors.extend(_checked_vectors([item.embedding for item in response.data]))
        return vectors


class OllamaEmbedder:
    """Embedder protocol implementation over the native Ollama /api/embed API."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        batch_size: int,
        timeout_seconds: float,
        client=None,
        client_factory: Callable[..., object] = create_ollama_client,
    ) -> None:
        validate_ollama_base_url(base_url)
        if batch_size < 1 or timeout_seconds <= 0:
            raise ValueError("embedding bounds violated: require batch_size >= 1 and timeout > 0")
        if not model.strip():
            raise ValueError("embedding bounds violated: require a non-blank model")
        self._base_url = base_url
        self._model = model
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._client_factory = client_factory

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in batches of at most ``batch_size`` /api/embed calls."""
        client = self._client or self._client_factory(
            base_url=self._base_url, timeout_seconds=self._timeout_seconds
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            response = client.post(_OLLAMA_EMBED_PATH, json={"model": self._model, "input": batch})
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            vectors.extend(_checked_vectors(payload["embeddings"]))
        return vectors


def create_embedder(*, settings) -> Embedder:
    """Select the ingestion embedder from settings; OpenAI remains the default."""
    provider = settings.embedding_provider
    if provider == "ollama":
        return OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embedding_model,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    if provider == "openai":
        return OpenAIEmbedder(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    raise ValueError(f"embedding_provider unknown: {provider!r}")
