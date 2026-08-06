"""API-side OpenAI embedding adapter behind the shared Embedder (task 2.2).

Same model contract as the worker (``EMBEDDING_MODEL``, default
``text-embedding-3-small``, exactly ``EMBEDDING_DIMENSION`` dimensions) so
query vectors bind cleanly against ``halfvec(1536)``. The OpenAI client is
built lazily on the first call through an injectable factory (bounded
timeout, no SDK retries), so construction and every non-e2e test stay
offline; a dimension mismatch fails fast instead of reaching the database.
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
        response = client.embeddings.create(model=self._model, input=list(texts))
        vectors: list[list[float]] = []
        for item in response.data:
            vector = list(item.embedding)
            if len(vector) != EMBEDDING_DIMENSION:
                raise ValueError(
                    "embedding dimension mismatch: "
                    f"got {len(vector)}, expected {EMBEDDING_DIMENSION}"
                )
            vectors.append(vector)
        return vectors
