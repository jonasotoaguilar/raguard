"""Retrieval contracts: candidate rows and fused results (task 1.4).

The public surface mirrors the search response envelope: chunk identity,
document context, position, content, and per-signal ranks. Internal state —
tenant ids, raw distances, provider details — never appears here; fusion and
the future router compose only these dataclasses.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candidate:
    """One ranked row from a single retrieval signal (keyword or semantic)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    position: int
    content: str


@dataclass(frozen=True, slots=True)
class FusedResult:
    """One fused result: both signal ranks plus the deterministic RRF score."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    position: int
    content: str
    keyword_rank: int | None
    semantic_rank: int | None
    score: float
