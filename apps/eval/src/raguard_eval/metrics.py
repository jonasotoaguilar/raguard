"""Relevant-only ranking metrics for the offline evaluation harness.

Precision/recall/hit-rate score ``relevant`` cases only: empty ``Rk`` is
``0.0`` (never ``1.0``), and empty ``Rel`` returns ``None`` so the caller
excludes the case from aggregates. Neutral cases use ``neutral_fidelity``
and never enter precision. Citation validity is ``valid/total`` when
``[n]`` markers exist, else ``None`` (excluded; honest empties are counted
separately by the caller and never inflate quality).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_MARKER = re.compile(r"\[(\d+)\]")


def precision_at_k(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    """|Rk ∩ Rel| / |Rk|; empty Rk is 0.0, never 1.0."""
    retrieved_set = set(retrieved)
    if len(retrieved_set) == 0:
        return 0.0
    return len(retrieved_set & set(relevant)) / len(retrieved_set)


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str]) -> float | None:
    """|Rk ∩ Rel| / |Rel|; None when Rel is empty (case excluded)."""
    if len(relevant) == 0:
        return None
    if len(retrieved) == 0:
        return 0.0
    return len(set(retrieved) & set(relevant)) / len(set(relevant))


def hit_rate_at_k(retrieved: Sequence[str], relevant: Sequence[str]) -> float | None:
    """1.0 iff Rk ∩ Rel is non-empty; None when Rel is empty (excluded)."""
    if len(relevant) == 0:
        return None
    rel = set(relevant)
    return 1.0 if any(chunk_id in rel for chunk_id in retrieved) else 0.0


def neutral_fidelity(retrieved: Sequence[str]) -> float:
    """1.0 iff a neutral case retrieved nothing, else 0.0."""
    return 1.0 if len(retrieved) == 0 else 0.0


def citation_markers(completion_text: str) -> list[int]:
    """All ``[n]`` marker indices in first-occurrence order."""
    return [int(index) for index in _MARKER.findall(completion_text)]


def citation_validity(completion_text: str, retrieved_count: int) -> float | None:
    """Valid ``[n]`` / total ``[n]``; None when no markers exist (excluded)."""
    markers = citation_markers(completion_text)
    if not markers:
        return None
    return sum(1 for index in markers if 1 <= index <= retrieved_count) / len(markers)


def mean_or_none(values: Sequence[float | None]) -> float | None:
    """Mean over non-None values; None when every value is excluded."""
    kept = [value for value in values if value is not None]
    if not kept:
        return None
    return sum(kept) / len(kept)
