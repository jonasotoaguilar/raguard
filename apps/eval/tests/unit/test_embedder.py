"""Tests for the ODD-1 deterministic offline SHA-256 token embedder (RED).

Locks: lowercase ``[a-z0-9]+`` tokenization, exact ``EMBEDDING_DIMENSION``
length, repeated/colliding token accumulation before normalization,
deterministic output, L2 norm 1.0 for non-empty token sequences, and a
zero vector for empty/whitespace/punctuation-only input. The class must
satisfy the synchronous ``Embedder`` protocol with no network calls.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from raguard_api.documents.contracts import EMBEDDING_DIMENSION, Embedder
from raguard_eval.embedder import Sha256TokenEmbedder


def _axis(token: str) -> int:
    return int.from_bytes(sha256(token.encode("utf-8")).digest(), "big") % EMBEDDING_DIMENSION


def _expected_vector(text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    counts: dict[int, float] = {}
    for token in tokens:
        axis = _axis(token)
        counts[axis] = counts.get(axis, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values()))
    vector = [0.0] * EMBEDDING_DIMENSION
    if norm == 0.0:
        return vector
    for axis, value in counts.items():
        vector[axis] = value / norm
    return vector


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def test_embedded_texts_have_exact_dimension() -> None:
    vectors = Sha256TokenEmbedder().embed(["alpha beta", ""])
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIMENSION
        assert len(vector) == 1024
        assert all(isinstance(value, float) for value in vector)


def test_empty_batch_embeds_to_empty_list() -> None:
    assert Sha256TokenEmbedder().embed([]) == []


def test_tokenization_lowercases_and_splits_on_non_alphanumerics() -> None:
    embedder = Sha256TokenEmbedder()
    (upper,) = embedder.embed(["Alpha BETA"])
    (lower,) = embedder.embed(["alpha beta"])
    assert upper == lower
    (punctuated,) = embedder.embed(["hello, world!"])
    (plain,) = embedder.embed(["hello world"])
    assert punctuated == plain
    assert (embedder.embed(["abc123"]))[0] == (embedder.embed(["ABC123"]))[0]


def test_output_is_deterministic_across_calls_and_instances() -> None:
    first = Sha256TokenEmbedder().embed(["alpha beta", "gamma"])[0]
    second = Sha256TokenEmbedder().embed(["alpha beta", "gamma"])[0]
    assert first == second
    assert first == _expected_vector("alpha beta")


def test_repeated_tokens_accumulate_before_normalization() -> None:
    (single,) = Sha256TokenEmbedder().embed(["alpha beta"])
    (repeated,) = Sha256TokenEmbedder().embed(["alpha alpha beta"])
    assert repeated == _expected_vector("alpha alpha beta")
    assert repeated != single
    axis_alpha = _axis("alpha")
    axis_beta = _axis("beta")
    assert axis_alpha != axis_beta
    assert math.isclose(repeated[axis_alpha], 2.0 / math.sqrt(5.0), rel_tol=1e-9)
    assert math.isclose(repeated[axis_beta], 1.0 / math.sqrt(5.0), rel_tol=1e-9)
    assert repeated[axis_alpha] > repeated[axis_beta]


def test_single_token_collapses_to_unit_axis() -> None:
    (once,) = Sha256TokenEmbedder().embed(["alpha"])
    (twice,) = Sha256TokenEmbedder().embed(["alpha alpha"])
    assert once == twice
    assert once[_axis("alpha")] == 1.0
    assert sum(1 for value in once if value != 0.0) == 1


def test_non_empty_vectors_have_unit_l2_norm() -> None:
    for text in ("alpha beta", "alpha alpha beta", "hello, world! 123"):
        (vector,) = Sha256TokenEmbedder().embed([text])
        assert math.isclose(_norm(vector), 1.0, rel_tol=1e-9)


def test_empty_whitespace_or_punctuation_only_gives_zero_vector() -> None:
    vectors = Sha256TokenEmbedder().embed(["", "   ", "\t\n ", "!!! ??? ..."])
    zero = [0.0] * EMBEDDING_DIMENSION
    for vector in vectors:
        assert vector == zero


def test_batch_texts_embed_independently_in_order() -> None:
    vectors = Sha256TokenEmbedder().embed(["alpha", "beta"])
    assert vectors[0] == _expected_vector("alpha")
    assert vectors[1] == _expected_vector("beta")
    assert vectors[0] != vectors[1]


def test_satisfies_synchronous_embedder_protocol() -> None:
    embedder = Sha256TokenEmbedder()
    assert isinstance(embedder, Embedder)
    vectors = embedder.embed(["alpha beta"])
    assert isinstance(vectors, list)


def test_embedder_module_makes_no_network_or_provider_imports() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "raguard_eval" / "embedder.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "httpx", "requests", "urllib", "socket"):
        assert forbidden not in text.lower()
