"""Bounded numbered-citation verification (PR 2).

``[n]`` markers index the exact ordered retrieval tuple the prompt was built
from; any index outside ``1..len(chunks)`` rejects the whole response. Markers
deduplicate by first occurrence and map deterministically; missing markers are
valid honest empty citations.
"""

import re
from collections.abc import Sequence

from raguard_api.chat.contracts import Citation
from raguard_api.retrieval.contracts import FusedResult

_MARKER = re.compile(r"\[(\d+)\]")


class CitationVerificationError(Exception):
    """A citation marker does not resolve to the authorized retrieved set."""


def verify_citations(completion: str, chunks: Sequence[FusedResult]) -> list[Citation]:
    """Resolve bounded ``[n]`` markers to verified citations, or raise.

    Malformed brackets (``[1,2]``, ``[-1]``, ``[abc]``) never parse as markers.
    """
    markers = [int(index) for index in _MARKER.findall(completion)]
    if any(not 1 <= index <= len(chunks) for index in markers):
        raise CitationVerificationError(f"citation index out of range: require 1..{len(chunks)}")
    return [Citation.from_fused_result(chunks[index - 1]) for index in dict.fromkeys(markers)]
