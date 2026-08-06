"""Retrieval domain: hybrid keyword+semantic search fused with RRF.

PR 1 foundation: contracts and deterministic reciprocal rank fusion.
PR 2 query builders: parameterized tenant-filtered FTS + pgvector
statements (``build_keyword_query``, ``build_semantic_query``,
``build_ef_search_statement``). The router, embedder adapter, and main
wiring land in PR 3; tenant predicates are injected by the caller from a
fresh ``AuthorizationScope`` so no tenant identity is ever hard-coded.
"""

from raguard_api.retrieval.contracts import Candidate, FusedResult
from raguard_api.retrieval.fusion import rrf_fusion
from raguard_api.retrieval.queries import (
    build_ef_search_statement,
    build_keyword_query,
    build_semantic_query,
)

__all__ = [
    "Candidate",
    "FusedResult",
    "rrf_fusion",
    "build_keyword_query",
    "build_semantic_query",
    "build_ef_search_statement",
]
