"""Unit tests for deterministic reciprocal rank fusion (task 1.1 RED).

Covers the spec's deterministic hybrid fusion requirement: a chunk ranked by
both signals accumulates both contributions (1/(k+rank) per signal), fused
ties order by ascending chunk id, and repeated runs produce identical lists.
The fusion layer is pure — no SQL, no database — so these tests run offline.
"""

import uuid

import pytest
from raguard_api.retrieval.contracts import Candidate
from raguard_api.retrieval.fusion import rrf_fusion

pytestmark = pytest.mark.unit

K = 60


def _candidate(chunk_id: uuid.UUID) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        document_name="report.pdf",
        position=1,
        content=f"chunk of {chunk_id}",
    )


def test_dual_signal_chunk_sums_contributions_and_outranks_single_signal():
    dual = _candidate(uuid.uuid4())
    keyword_only = _candidate(uuid.uuid4())
    semantic_only = _candidate(uuid.uuid4())

    fused = rrf_fusion(
        keyword=[dual, keyword_only],
        semantic=[semantic_only, _candidate(uuid.uuid4()), dual],
        k=K,
    )

    by_id = {result.chunk_id: result for result in fused}
    assert by_id[dual.chunk_id].score == pytest.approx(1 / (K + 1) + 1 / (K + 3))
    assert by_id[keyword_only.chunk_id].score == pytest.approx(1 / (K + 2))
    assert by_id[semantic_only.chunk_id].score == pytest.approx(1 / (K + 1))
    # The dual-signal chunk outranks every single-signal chunk.
    assert fused[0].chunk_id == dual.chunk_id
    assert by_id[dual.chunk_id].score > by_id[keyword_only.chunk_id].score
    assert by_id[dual.chunk_id].score > by_id[semantic_only.chunk_id].score


def test_dual_signal_chunk_records_both_signal_ranks():
    chunk = _candidate(uuid.uuid4())
    filler = _candidate(uuid.uuid4())

    fused = rrf_fusion(keyword=[chunk], semantic=[filler, chunk], k=K)

    by_id = {result.chunk_id: result for result in fused}
    assert by_id[chunk.chunk_id].keyword_rank == 1
    assert by_id[chunk.chunk_id].semantic_rank == 2


def test_equal_scores_order_by_ascending_chunk_id():
    first = _candidate(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    second = _candidate(uuid.UUID("00000000-0000-0000-0000-000000000002"))

    # Equal fused scores: first is keyword rank 1, second is semantic rank 1.
    fused = rrf_fusion(keyword=[first], semantic=[second], k=K)

    assert [result.chunk_id for result in fused] == [first.chunk_id, second.chunk_id]
    assert fused[0].score == pytest.approx(fused[1].score)


def test_same_score_but_reversed_ids_still_orders_ascending():
    first = _candidate(uuid.UUID("00000000-0000-0000-0000-000000000002"))
    second = _candidate(uuid.UUID("00000000-0000-0000-0000-000000000001"))

    fused = rrf_fusion(keyword=[first], semantic=[second], k=K)

    assert [result.chunk_id for result in fused] == [second.chunk_id, first.chunk_id]


def test_repeated_runs_produce_identical_results():
    chunks = [_candidate(uuid.uuid4()) for _ in range(5)]

    first = rrf_fusion(keyword=chunks[:3], semantic=chunks[2:], k=K)
    second = rrf_fusion(keyword=chunks[:3], semantic=chunks[2:], k=K)

    assert first == second


def test_custom_k_changes_relative_contribution():
    first = _candidate(uuid.uuid4())
    second = _candidate(uuid.uuid4())

    # With k=1 the rank gap dominates: keyword rank 1 (1/2) beats semantic rank 2 (1/3).
    fused = rrf_fusion(keyword=[first], semantic=[_candidate(uuid.uuid4()), second], k=1)

    by_id = {result.chunk_id: result for result in fused}
    assert by_id[first.chunk_id].score == pytest.approx(0.5)
    assert by_id[second.chunk_id].score == pytest.approx(1 / 3)
    assert by_id[first.chunk_id].score > by_id[second.chunk_id].score


def test_fusion_rejects_k_below_one():
    chunk = _candidate(uuid.uuid4())

    with pytest.raises(ValueError, match="k"):
        rrf_fusion(keyword=[chunk], semantic=[], k=0)
