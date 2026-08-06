"""Deterministic reciprocal rank fusion (task 1.1/1.4).

RRF sums ``1 / (k + rank)`` per signal; a chunk ranked by both signals
accumulates both contributions. Ties on fused score break by ascending chunk
id, so the merged list is fully deterministic across repeated runs (spec:
deterministic hybrid fusion, k=60 default).
"""

import uuid
from collections.abc import Sequence

from raguard_api.retrieval.contracts import Candidate, FusedResult


def _contribute(
    candidate: Candidate,
    signal: str,
    rank: int,
    k: int,
    scores: dict[uuid.UUID, float],
    ranks: dict[uuid.UUID, dict[str, int]],
    by_chunk: dict[uuid.UUID, Candidate],
) -> None:
    by_chunk.setdefault(candidate.chunk_id, candidate)
    scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (k + rank)
    ranks.setdefault(candidate.chunk_id, {})[signal] = rank


def rrf_fusion(
    keyword: Sequence[Candidate],
    semantic: Sequence[Candidate],
    *,
    k: int = 60,
) -> list[FusedResult]:
    """Fuse two per-signal candidate lists into one deterministic ranking.

    Rank 1 is the first element of each list; a chunk present in both lists
    sums ``1/(k+rank)`` from each signal. Results sort by fused score
    descending, then chunk id ascending.
    """
    if k < 1:
        raise ValueError(f"rrf k out of bounds: {k}; require k >= 1")
    scores: dict[uuid.UUID, float] = {}
    ranks: dict[uuid.UUID, dict[str, int]] = {}
    by_chunk: dict[uuid.UUID, Candidate] = {}
    for rank, candidate in enumerate(keyword, start=1):
        _contribute(candidate, "keyword", rank, k, scores, ranks, by_chunk)
    for rank, candidate in enumerate(semantic, start=1):
        _contribute(candidate, "semantic", rank, k, scores, ranks, by_chunk)
    results = [
        FusedResult(
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            document_name=candidate.document_name,
            position=candidate.position,
            content=candidate.content,
            keyword_rank=ranks[candidate.chunk_id].get("keyword"),
            semantic_rank=ranks[candidate.chunk_id].get("semantic"),
            score=scores[candidate.chunk_id],
        )
        for candidate in by_chunk.values()
    ]
    return sorted(results, key=lambda result: (-result.score, result.chunk_id))
