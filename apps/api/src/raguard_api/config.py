"""Application settings from environment (task 2.5).

Field names map to uppercase environment variables (JWT_SECRET,
SESSION_COOKIE_SECURE, ALLOWED_ORIGINS as JSON, ...). ``jwt_secret`` has no
default: production must fail fast when the signing key is unset. Retrieval
fields are bounded at instantiation (task 1.5): any out-of-range value, any
ef_search below the candidate count, and any semantic max distance outside
the pgvector cosine-distance range (0, 2] fail startup, mirroring the
worker's dispatch-bound guard.
"""

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


def validate_chat_bounds(
    *, model: str, max_output_tokens: int, retries: int, timeout_seconds: float
) -> None:
    """Startup guard: chat provider settings must satisfy the design bounds (task 3.2)."""
    if not model.strip():
        raise ValueError("chat_model must not be blank")
    if not 1 <= max_output_tokens <= 2000:
        raise ValueError(
            f"chat_max_output_tokens out of bounds: {max_output_tokens}; require 1..2000"
        )
    if not 0 <= retries <= 2:
        raise ValueError(f"chat_retries out of bounds: {retries}; require 0..2")
    if not timeout_seconds > 0:
        raise ValueError(f"provider_timeout_seconds out of bounds: {timeout_seconds}; require > 0")


def validate_retrieval_bounds(
    *,
    rrf_k: int,
    candidates: int,
    top_k: int,
    top_k_max: int,
    ef_search: int,
    max_distance: float,
    max_query_length: int,
) -> None:
    """Startup guard: retrieval settings must satisfy the design bounds (task 1.5)."""
    if not 1 <= rrf_k <= 1000:
        raise ValueError(f"rrf_k out of bounds: {rrf_k}; require 1..1000")
    if not 1 <= candidates <= 200:
        raise ValueError(f"retrieval_candidates out of bounds: {candidates}; require 1..200")
    if not 1 <= top_k <= top_k_max:
        raise ValueError(f"retrieval_top_k out of bounds: {top_k}; require 1..{top_k_max}")
    if not 1 <= top_k_max <= 50:
        raise ValueError(f"retrieval_top_k_max out of bounds: {top_k_max}; require 1..50")
    if not 1 <= ef_search <= 1000:
        raise ValueError(f"retrieval_ef_search out of bounds: {ef_search}; require 1..1000")
    if ef_search < candidates:
        raise ValueError(
            "retrieval bounds violated: "
            f"ef_search={ef_search} candidates={candidates}; require ef_search >= candidates"
        )
    if not 0 < max_distance <= 2.0:
        raise ValueError(
            "retrieval_semantic_max_distance out of bounds: "
            f"{max_distance}; require 0 < value <= 2.0 (pgvector cosine distance)"
        )
    if not 1 <= max_query_length <= 10_000:
        raise ValueError(
            f"retrieval_max_query_length out of bounds: {max_query_length}; require 1..10000"
        )


class Settings(BaseSettings):
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "raguard"
    jwt_audience: str = "raguard-api"
    jwt_expiry_minutes: int = 15
    session_cookie_name: str = "raguard_session"
    session_cookie_path: str = "/api"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    allowed_origins: list[str] = ["http://localhost:5173"]
    object_store_endpoint_url: str = "http://127.0.0.1:9000"
    object_store_bucket: str = "raguard-documents"
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_region: str = "us-east-1"
    job_queue_redis_url: str = "redis://127.0.0.1:6379/0"
    job_queue_function_name: str = "ingest_document"
    max_upload_bytes: int = 20 * 1024 * 1024

    # --- Retrieval defaults/bounds (design: RRF k=60, candidates 50, top_k 10,
    # ef_search 100, semantic max distance 0.5, max query 2000 chars, embedding
    # model shared with worker). Semantic max distance is pgvector cosine
    # distance (0..2; 0 identical, 1 orthogonal, 2 opposite). The 0.5 default
    # keeps chunks with meaningful directional agreement (cosine similarity
    # >= 0.5) while excluding near-orthogonal/opposite nearest neighbors, so a
    # populated tenant with no real match returns the neutral empty result. ---
    rrf_k: int = 60
    retrieval_candidates: int = 50
    retrieval_top_k: int = 10
    retrieval_top_k_max: int = 50
    retrieval_ef_search: int = 100
    retrieval_semantic_max_distance: float = 0.5
    retrieval_max_query_length: int = 2000
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str = ""
    provider_timeout_seconds: float = 30.0

    # --- Chat completion defaults/bounds (design: gpt-4o-mini, max 500 output
    # tokens, at most 2 application retries; the completer disables SDK retries
    # and reuses provider_timeout_seconds). Failures surface as typed errors
    # for the router's safe 503 envelope. ---
    chat_model: str = "gpt-4o-mini"
    chat_max_output_tokens: int = 500
    chat_retries: int = 2

    model_config = {"extra": "ignore"}

    def model_post_init(self, __context: Any) -> None:
        validate_chat_bounds(
            model=self.chat_model,
            max_output_tokens=self.chat_max_output_tokens,
            retries=self.chat_retries,
            timeout_seconds=self.provider_timeout_seconds,
        )
        validate_retrieval_bounds(
            rrf_k=self.rrf_k,
            candidates=self.retrieval_candidates,
            top_k=self.retrieval_top_k,
            top_k_max=self.retrieval_top_k_max,
            ef_search=self.retrieval_ef_search,
            max_distance=self.retrieval_semantic_max_distance,
            max_query_length=self.retrieval_max_query_length,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
