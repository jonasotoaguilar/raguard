"""Retrieval domain: hybrid keyword+semantic search fused with RRF.

PR 1 foundation: contracts and deterministic reciprocal rank fusion.
PR 2 query builders: parameterized tenant-filtered FTS + pgvector
statements (``build_keyword_query``, ``build_semantic_query``,
``build_ef_search_statement``). PR 3 endpoint: the OpenAI query embedder
(``embeddings.py``) and the ``POST /api/search`` router (``router.py``),
wired into ``main.py``. PR 4 gates: the cross-tenant isolation integration
gate and the credential-gated e2e provider smoke (``test_retrieval_provider``).
Tenant predicates are injected by the caller from a fresh
``AuthorizationScope`` so no tenant identity is ever hard-coded.
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
