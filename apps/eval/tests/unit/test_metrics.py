"""Tests for the PR4 metrics contract (task 3.1, RED).

Relevant-only precision@k/recall@k/hit-rate; empty Rk scores 0.0; empty Rel
excludes the case; neutral fidelity never enters precision; citation validity
is null when no ``[n]`` markers exist.
"""

from __future__ import annotations

from raguard_eval.metrics import (
    citation_markers,
    citation_validity,
    hit_rate_at_k,
    mean_or_none,
    neutral_fidelity,
    precision_at_k,
    recall_at_k,
)


def test_missed_relevant_scores_zero() -> None:
    assert precision_at_k([], ["c-1"]) == 0.0
    assert recall_at_k([], ["c-1"]) == 0.0
    assert hit_rate_at_k([], ["c-1"]) == 0.0


def test_empty_relevant_excluded_from_aggregates() -> None:
    assert recall_at_k(["c-1"], []) is None
    assert hit_rate_at_k(["c-1"], []) is None


def test_neutral_fidelity_never_enters_precision() -> None:
    assert neutral_fidelity([]) == 1.0
    assert neutral_fidelity(["c-1"]) == 0.0
    assert precision_at_k([], []) == 0.0


def test_citation_validity_null_without_markers() -> None:
    assert citation_validity("honest answer with no markers", 2) is None
    assert citation_validity("[1] grounded", 2) == 1.0


def test_partial_overlap_scores_fractions() -> None:
    retrieved = ["c-1", "c-2", "c-9", "c-8"]
    relevant = ["c-1", "c-2", "c-3"]
    assert precision_at_k(retrieved, relevant) == 0.5
    assert recall_at_k(retrieved, relevant) == 2 / 3
    assert hit_rate_at_k(retrieved, relevant) == 1.0
    assert hit_rate_at_k(["c-9"], relevant) == 0.0


def test_citation_validity_counts_only_in_range() -> None:
    assert citation_validity("[1] and [9]", 2) == 0.5
    assert citation_validity("[7]", 2) == 0.0
    assert citation_validity("brackets [] never parse", 2) is None
    assert citation_markers("[2] then [2]") == [2, 2]


def test_mean_or_none_skips_excluded() -> None:
    assert mean_or_none([1.0, None, 0.0]) == 0.5
    assert mean_or_none([]) is None
    assert mean_or_none([None]) is None


def test_duplicate_retrieved_ids_use_set_semantics() -> None:
    assert recall_at_k(["c-1", "c-1", "c-1"], ["c-1", "c-2"]) == 0.5
    assert precision_at_k(["c-1", "c-1", "c-9"], ["c-1", "c-2"]) == 0.5
