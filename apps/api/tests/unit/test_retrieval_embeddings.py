"""Unit tests for the API embedding adapters and provider factory (ODD-1 RED).

The shared contract standardizes on exactly ``EMBEDDING_DIMENSION`` (1024)
vectors so query embeddings bind cleanly against ``halfvec(1024)``. OpenAI
must request 1024 dimensions explicitly; Ollama uses the native ``/api/embed``
contract (``{"model", "input"}`` -> ``{"embeddings"}``) over a lazily-built
bounded httpx client. Both adapters build their clients lazily through
injectable factories so construction and non-e2e tests never touch the
network, and the factory selects the adapter from settings (OpenAI default).
"""

import pytest
from raguard_api.config import Settings
from raguard_api.documents.contracts import EMBEDDING_DIMENSION, Embedder
from raguard_api.retrieval.embeddings import (
    OllamaEmbedder,
    OpenAIEmbedder,
    create_embedder,
)

pytestmark = pytest.mark.unit

assert EMBEDDING_DIMENSION == 1024


def _vector(seed: int) -> list[float]:
    return [float((seed + dim) % 7) / 10 for dim in range(EMBEDDING_DIMENSION)]


class _Item:
    def __init__(self, embedding):
        self.embedding = embedding


class _EmbeddingsAPI:
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        return type("Response", (), {"data": [_Item(v) for v in self.vectors]})()


class _FakeOpenAIClient:
    def __init__(self, vectors):
        self.embeddings = _EmbeddingsAPI(vectors)


class _FakeOllamaResponse:
    def __init__(self, vectors):
        self._vectors = vectors

    def raise_for_status(self):
        return None

    def json(self):
        return {"model": "qwen3-embedding:0.6b", "embeddings": self._vectors}


class _FakeOllamaClient:
    def __init__(self, vectors):
        self.vectors = vectors
        self.posts: list[dict] = []

    def post(self, path, *, json):
        self.posts.append({"path": path, "json": dict(json)})
        return _FakeOllamaResponse(self.vectors)


def test_embed_returns_dimension_exact_vectors_through_protocol():
    vectors = [_vector(0), _vector(1)]
    embedder = OpenAIEmbedder(
        api_key="sk-test",
        model="text-embedding-3-small",
        timeout_seconds=30.0,
        client=_FakeOpenAIClient(vectors),
    )

    assert isinstance(embedder, Embedder)
    assert embedder.embed(["first", "second"]) == vectors
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIMENSION


def test_openai_embed_requests_1024_dimensions():
    client = _FakeOpenAIClient([_vector(0)])
    embedder = OpenAIEmbedder(
        api_key="sk-test", model="text-embedding-3-small", timeout_seconds=5.0, client=client
    )

    embedder.embed(["hello"])

    assert client.embeddings.calls == [
        {"model": "text-embedding-3-small", "input": ["hello"], "dimensions": 1024}
    ]


def test_embed_forwards_configured_model_and_texts():
    client = _FakeOpenAIClient([_vector(0)])
    embedder = OpenAIEmbedder(
        api_key="sk-test", model="custom-model", timeout_seconds=5.0, client=client
    )

    embedder.embed(["hello"])

    assert client.embeddings.calls[0]["model"] == "custom-model"
    assert client.embeddings.calls[0]["input"] == ["hello"]


def test_embed_rejects_dimension_mismatch():
    embedder = OpenAIEmbedder(
        api_key="sk-test",
        model="m",
        timeout_seconds=5.0,
        client=_FakeOpenAIClient([[0.1, 0.2, 0.3]]),
    )

    with pytest.raises(ValueError, match="dimension mismatch"):
        embedder.embed(["query"])


def test_client_is_built_lazily_through_factory():
    calls: list[tuple[str, float]] = []

    def factory(*, api_key, timeout_seconds):
        calls.append((api_key, timeout_seconds))
        return _FakeOpenAIClient([_vector(0)])

    embedder = OpenAIEmbedder(
        api_key="sk-lazy", model="m", timeout_seconds=9.0, client_factory=factory
    )
    assert calls == []  # construction never touches the provider

    embedder.embed(["q"])

    assert calls == [("sk-lazy", 9.0)]


def test_timeout_must_be_positive():
    with pytest.raises(ValueError, match="timeout"):
        OpenAIEmbedder(api_key="sk", model="m", timeout_seconds=0.0)


# ---------------------------------------------------------------------------
# Ollama adapter: native /api/embed, lazy bounded client, 1024 validation
# ---------------------------------------------------------------------------


def test_ollama_embed_posts_native_contract_and_validates_dimensions():
    vectors = [_vector(0), _vector(1)]
    client = _FakeOllamaClient(vectors)
    embedder = OllamaEmbedder(
        base_url="http://127.0.0.1:11434",
        model="qwen3-embedding:0.6b",
        timeout_seconds=30.0,
        client=client,
    )

    assert isinstance(embedder, Embedder)
    assert embedder.embed(["first", "second"]) == vectors
    assert client.posts == [
        {
            "path": "/api/embed",
            "json": {"model": "qwen3-embedding:0.6b", "input": ["first", "second"]},
        }
    ]


def test_ollama_embed_rejects_dimension_mismatch():
    embedder = OllamaEmbedder(
        base_url="http://127.0.0.1:11434",
        model="m",
        timeout_seconds=5.0,
        client=_FakeOllamaClient([[0.1, 0.2]]),
    )

    with pytest.raises(ValueError, match="dimension mismatch"):
        embedder.embed(["query"])


def test_ollama_client_is_built_lazily_through_factory():
    calls: list[tuple[str, float]] = []

    def factory(*, base_url, timeout_seconds):
        calls.append((base_url, timeout_seconds))
        return _FakeOllamaClient([_vector(0)])

    embedder = OllamaEmbedder(
        base_url="http://ollama:11434",
        model="m",
        timeout_seconds=9.0,
        client_factory=factory,
    )
    assert calls == []

    embedder.embed(["q"])

    assert calls == [("http://ollama:11434", 9.0)]


@pytest.mark.parametrize("base_url", ["", "  ", "ftp://host", "not-a-url"])
def test_ollama_rejects_invalid_base_url(base_url):
    with pytest.raises(ValueError, match="ollama_base_url"):
        OllamaEmbedder(base_url=base_url, model="m", timeout_seconds=5.0)


def test_ollama_timeout_must_be_positive():
    with pytest.raises(ValueError, match="timeout"):
        OllamaEmbedder(base_url="http://127.0.0.1:11434", model="m", timeout_seconds=0.0)


def test_ollama_model_must_not_be_blank():
    with pytest.raises(ValueError, match="model"):
        OllamaEmbedder(base_url="http://127.0.0.1:11434", model="  ", timeout_seconds=5.0)


# ---------------------------------------------------------------------------
# Factory: provider selection from settings, OpenAI default
# ---------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret="a" * 32, **overrides)


def test_factory_defaults_to_openai():
    assert isinstance(create_embedder(settings=_settings()), OpenAIEmbedder)


def test_factory_selects_ollama_from_settings():
    embedder = create_embedder(settings=_settings(embedding_provider="ollama"))

    assert isinstance(embedder, OllamaEmbedder)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="embedding_provider"):
        _settings(embedding_provider="cohere")
