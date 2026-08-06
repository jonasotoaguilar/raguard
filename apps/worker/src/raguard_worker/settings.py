"""Arq worker settings and startup wiring (task 3.4).

The runtime command is ``uv run arq raguard_worker.settings.WorkerSettings``.
Pydantic fields are env-configurable; the dispatch timeline is guarded at
instantiation: ``wait < freshness < sweep_age`` (design defaults: 5s wait,
30s freshness, 5-minute sweep age, 100ms poll). The plain class attributes
at the bottom are the Arq worker kwargs the ``arq`` CLI reads from the
settings class (functions, on_startup, max_tries, redis_settings).
"""

import logging
import os
from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import cron
from pydantic_settings import BaseSettings
from raguard_api.documents.storage import S3ObjectStore, create_s3_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from raguard_worker.chunking import make_chunker
from raguard_worker.cleanup import SqlAlchemySweepStore, sweep_stale_unready
from raguard_worker.embeddings import OpenAIEmbedder
from raguard_worker.jobs import SqlAlchemyDispatchStore, ingest_document
from raguard_worker.parsers import PdfMarkdownParser

_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"


def validate_dispatch_bounds(
    *, wait_seconds: float, freshness_seconds: float, sweep_age_seconds: float
) -> None:
    """Startup guard: the dispatch timeline must satisfy wait < freshness < sweep_age."""
    if not (wait_seconds < freshness_seconds < sweep_age_seconds):
        raise ValueError(
            "dispatch bounds violated: "
            f"wait={wait_seconds} freshness={freshness_seconds} sweep_age={sweep_age_seconds}; "
            "require wait < freshness < sweep_age"
        )


async def startup(ctx: dict) -> None:
    """Build and inject the runtime seams into the Arq context (task 3.4/4.3)."""
    settings = WorkerSettings()
    ctx["settings"] = settings
    session_factory = async_sessionmaker(
        create_async_engine(settings.database_url), expire_on_commit=False
    )
    ctx["store"] = SqlAlchemyDispatchStore(session_factory)
    ctx["sweep_store"] = SqlAlchemySweepStore(session_factory)
    ctx["object_store"] = S3ObjectStore(
        create_s3_client(settings), bucket=settings.object_store_bucket
    )
    # PR4b: real adapters wired behind the shared contracts seams (pypdf
    # parser, parameterized chunker, OpenAI embedder, sweep logger).
    ctx["parser"] = PdfMarkdownParser(
        max_pages=settings.max_pdf_pages, max_characters=settings.max_text_characters
    )
    ctx["chunker"] = make_chunker(
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        max_chunks=settings.max_chunks,
    )
    ctx["embedder"] = OpenAIEmbedder(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.provider_timeout_seconds,
    )
    ctx["logger"] = logging.getLogger("raguard_worker")


class WorkerSettings(BaseSettings):
    """Arq worker settings: dispatch bounds plus the Arq wiring attributes."""

    model_config = {"extra": "ignore"}

    redis_url: str = _DEFAULT_REDIS_URL
    database_url: str = "postgresql+psycopg://raguard:change-me@127.0.0.1:5432/raguard"
    object_store_endpoint_url: str = "http://127.0.0.1:9000"
    object_store_bucket: str = "raguard-documents"
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_region: str = "us-east-1"

    dispatch_freshness_seconds: float = 30.0
    dispatch_wait_seconds: float = 5.0
    dispatch_poll_interval_seconds: float = 0.1
    sweep_age_seconds: float = 300.0
    pending_age_seconds: float = 900.0  # PR5: pending rows older than this alert (task 5.2)
    provider_attempts: int = 3
    max_retry_after_seconds: float = 5.0

    # --- PR4b pipeline bounds (design: 500p / 5M chars / 10k chunks / 64 / 30s) ---
    max_pdf_pages: int = 500
    max_text_characters: int = 5_000_000
    chunk_size: int = 1000
    chunk_overlap: int = 100
    max_chunks: int = 10_000
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 64
    provider_timeout_seconds: float = 30.0
    openai_api_key: str = ""
    sweep_batch_size: int = 100

    # --- Arq worker kwargs (class-level; read from WorkerSettings.__dict__) ---
    functions: ClassVar[list] = [ingest_document]
    on_startup: ClassVar[Any] = startup
    max_tries: ClassVar[int] = 10
    cron_jobs: ClassVar[list] = [cron(sweep_stale_unready, minute=set(range(60)))]
    redis_settings: ClassVar[RedisSettings] = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
    )

    def model_post_init(self, __context: Any) -> None:
        validate_dispatch_bounds(
            wait_seconds=self.dispatch_wait_seconds,
            freshness_seconds=self.dispatch_freshness_seconds,
            sweep_age_seconds=self.sweep_age_seconds,
        )
