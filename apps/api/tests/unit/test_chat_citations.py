"""Unit tests for bounded numbered-citation verification (task 2.3 RED)."""

import uuid

import pytest
from raguard_api.chat.citations import CitationVerificationError, verify_citations
from raguard_api.retrieval.contracts import FusedResult

pytestmark = pytest.mark.unit

CHUNK_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
CHUNK_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
DOC_A = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
DOC_B = uuid.UUID("00000000-0000-0000-0000-0000000000bb")

CHUNKS = [
    FusedResult(CHUNK_A, DOC_A, "a.pdf", 1, "a chunk", 1, None, 0.5),
    FusedResult(CHUNK_B, DOC_B, "b.pdf", 2, "b chunk", None, 1, 0.4),
]


def test_markers_resolve_to_the_exact_retrieval_tuple():
    citations = verify_citations("Answer [1] and [2].", CHUNKS)

    assert [c.chunk_id for c in citations] == [CHUNK_A, CHUNK_B]
    assert (citations[0].document_name, citations[0].position) == ("a.pdf", 1)
    assert citations[1].content == "b chunk"


@pytest.mark.parametrize("completion", ["Only [3].", "Only [0].", "Only [99]."])
def test_out_of_set_marker_rejects_the_whole_response(completion):
    with pytest.raises(CitationVerificationError):
        verify_citations(completion, CHUNKS)


def test_missing_markers_yield_honest_empty_citations():
    assert verify_citations("No sources were needed.", CHUNKS) == []
    assert verify_citations("", CHUNKS) == []


def test_duplicate_markers_deduplicate_by_first_occurrence():
    citations = verify_citations("See [2], then [1], then [2] again.", CHUNKS)

    assert [c.chunk_id for c in citations] == [CHUNK_B, CHUNK_A]


def test_malformed_brackets_do_not_parse_as_markers():
    assert verify_citations("See [1,2] or [-1] or [abc].", CHUNKS) == []


def test_mapping_is_deterministic():
    completion = "Answer [2] and [1]."

    assert verify_citations(completion, CHUNKS) == verify_citations(completion, CHUNKS)
