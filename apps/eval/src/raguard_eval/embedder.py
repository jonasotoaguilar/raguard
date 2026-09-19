"""Deterministic offline SHA-256 token embedder for the evaluation harness.

Each text is lowercased and split into ``[a-z0-9]+`` tokens. Every token
occurrence hashes with SHA-256 to one axis (``digest % EMBEDDING_DIMENSION``);
repeated or colliding tokens accumulate before the vector is L2-normalized.
Texts with no tokens produce the documented zero vector. Pure stdlib and
fully offline: no provider clients, keys, or network calls.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from hashlib import sha256

from raguard_api.documents.contracts import EMBEDDING_DIMENSION

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Sha256TokenEmbedder:
    """Offline content-hash embedder satisfying the ``Embedder`` protocol."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each text into an ``EMBEDDING_DIMENSION``-long vector."""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        for token in _TOKEN_RE.findall(text.lower()):
            digest = sha256(token.encode("utf-8")).digest()
            axis = int.from_bytes(digest, "big") % EMBEDDING_DIMENSION
            counts[axis] = counts.get(axis, 0.0) + 1.0
        vector = [0.0] * EMBEDDING_DIMENSION
        if not counts:
            return vector
        norm = math.sqrt(sum(value * value for value in counts.values()))
        for axis, value in counts.items():
            vector[axis] = value / norm
        return vector
