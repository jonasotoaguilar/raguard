"""Retrieval domain: hybrid keyword+semantic search fused with RRF (PR 1).

Pure foundation only: contracts and deterministic reciprocal rank fusion.
The parameterized FTS + pgvector query builders land in PR 2; the router,
embedder adapter, and main wiring land in PR 3; tenant predicates are
injected by the caller from a fresh ``AuthorizationScope`` so no tenant
identity is ever hard-coded.
"""

from raguard_api.retrieval.contracts import Candidate, FusedResult
from raguard_api.retrieval.fusion import rrf_fusion

__all__ = [
    "Candidate",
    "FusedResult",
    "rrf_fusion",
]
