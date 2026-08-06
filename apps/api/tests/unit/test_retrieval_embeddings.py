"""Unit tests for the API OpenAI embedding adapter (task 2.2 RED).

The adapter must satisfy the shared ``Embedder`` protocol with exactly
``EMBEDDING_DIMENSION`` (1536) vectors so query embeddings bind cleanly
against ``halfvec(1536)``; forward the configured model; reject dimension
mismatches; and build the OpenAI client lazily through an injectable factory
so construction and non-e2e tests never touch the network.
"""

import pytest
from raguard_api.documents.contracts import EMBEDDING_DIMENSION, Embedder
from raguard_api.retrieval.embeddings import OpenAIEmbedder

pytestmark = pytest.mark.unit


def _vector(seed: int) -> list[float]:
    return [float((seed + dim) % 7) / 10 for dim in range(EMBEDDING_DIMENSION)]


class _Item:
    def __init__(self, embedding):
        self.embedding = embedding


class _EmbeddingsAPI:
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls: list[dict] = []

    def create(self, *, model, input):
        self.calls.append({"model": model, "input": list(input)})
        return type("Response", (), {"data": [_Item(v) for v in self.vectors]})()


class _FakeClient:
    def __init__(self, vectors):
        self.embeddings = _EmbeddingsAPI(vectors)


def test_embed_returns_dimension_exact_vectors_through_protocol():
    vectors = [_vector(0), _vector(1)]
    embedder = OpenAIEmbedder(
        api_key="sk-test",
        model="text-embedding-3-small",
        timeout_seconds=30.0,
        client=_FakeClient(vectors),
    )

    assert isinstance(embedder, Embedder)
    assert embedder.embed(["first", "second"]) == vectors
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIMENSION


def test_embed_forwards_configured_model_and_texts():
    client = _FakeClient([_vector(0)])
    embedder = OpenAIEmbedder(
        api_key="sk-test", model="custom-model", timeout_seconds=5.0, client=client
    )

    embedder.embed(["hello"])

    assert client.embeddings.calls == [{"model": "custom-model", "input": ["hello"]}]


def test_embed_rejects_dimension_mismatch():
    embedder = OpenAIEmbedder(
        api_key="sk-test",
        model="m",
        timeout_seconds=5.0,
        client=_FakeClient([[0.1, 0.2, 0.3]]),
    )

    with pytest.raises(ValueError, match="dimension mismatch"):
        embedder.embed(["query"])


def test_client_is_built_lazily_through_factory():
    calls: list[tuple[str, float]] = []

    def factory(*, api_key, timeout_seconds):
        calls.append((api_key, timeout_seconds))
        return _FakeClient([_vector(0)])

    embedder = OpenAIEmbedder(
        api_key="sk-lazy", model="m", timeout_seconds=9.0, client_factory=factory
    )
    assert calls == []  # construction never touches the provider

    embedder.embed(["q"])

    assert calls == [("sk-lazy", 9.0)]


def test_timeout_must_be_positive():
    with pytest.raises(ValueError, match="timeout"):
        OpenAIEmbedder(api_key="sk", model="m", timeout_seconds=0.0)
