"""Provider-neutral OpenAI embedding adapter behind the Embedder protocol (task 4.3).

``OpenAIEmbedder`` calls the OpenAI embeddings API in bounded batches of 64
texts and validates every returned vector against the shared
``EMBEDDING_DIMENSION`` (halfvec(1536)) so a provider misconfiguration fails
fast into the job's ``limit`` retry path instead of reaching the database.
The OpenAI client is built lazily through an injectable ``client_factory``
(default ``create_openai_client``, which bounds calls at 30 seconds and
disables SDK retries — the worker owns its bounded retry budget), so tests
inject a fake client and no provider network is ever touched in non-e2e.
"""

from collections.abc import Callable, Sequence

from raguard_api.documents.contracts import EMBEDDING_DIMENSION


def create_openai_client(*, api_key: str, timeout_seconds: float):
    """Build the real OpenAI client: bounded timeout, no SDK-level retries."""
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)


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
            response = client.embeddings.create(model=self._model, input=batch)
            for item in response.data:
                vector = list(item.embedding)
                if len(vector) != EMBEDDING_DIMENSION:
                    raise ValueError(
                        "embedding dimension mismatch: "
                        f"got {len(vector)}, expected {EMBEDDING_DIMENSION}"
                    )
                vectors.append(vector)
        return vectors
