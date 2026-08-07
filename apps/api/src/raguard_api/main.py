"""FastAPI app factory wiring the auth, org, documents, retrieval, and chat routers (task 4.4).

Builds the application from a settings object and a session factory: standard
error handlers plus the auth (login), org administration, documents
ingestion, retrieval search, and grounded chat routers. The documents router
receives real adapters (boto3 S3 and Arq/Redis) constructed from settings,
the retrieval router receives a lazily-connecting OpenAI embedder, and the
chat router a lazy OpenAI completer; connections are lazy, so factory tests
stay offline.
"""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.auth.router import create_auth_router
from raguard_api.chat.providers.openai import OpenAICompleter
from raguard_api.chat.router import create_chat_router
from raguard_api.config import Settings, get_settings
from raguard_api.documents.queue import ArqJobQueue
from raguard_api.documents.router import create_documents_router
from raguard_api.documents.storage import S3ObjectStore, create_s3_client
from raguard_api.errors import register_error_handlers
from raguard_api.org.router import create_org_router
from raguard_api.retrieval.embeddings import OpenAIEmbedder
from raguard_api.retrieval.router import create_retrieval_router


def create_app(*, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    """Build the raguard API application with the standard error envelope."""
    app = FastAPI(title="raguard API", version="0.1.0")
    register_error_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(create_auth_router(settings=settings, session_factory=session_factory))
    app.include_router(create_org_router(session_factory=session_factory))
    store = S3ObjectStore(create_s3_client(settings), bucket=settings.object_store_bucket)
    queue = ArqJobQueue(
        redis_url=settings.job_queue_redis_url,
        function_name=settings.job_queue_function_name,
    )
    app.include_router(
        create_documents_router(
            session_factory=session_factory, settings=settings, store=store, queue=queue
        )
    )
    embedder = OpenAIEmbedder(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        timeout_seconds=settings.provider_timeout_seconds,
    )
    app.include_router(
        create_retrieval_router(
            session_factory=session_factory, settings=settings, embedder=embedder
        )
    )
    completer = OpenAICompleter(
        api_key=settings.openai_api_key,
        model=settings.chat_model,
        max_output_tokens=settings.chat_max_output_tokens,
        timeout_seconds=settings.provider_timeout_seconds,
        retries=settings.chat_retries,
    )
    app.include_router(
        create_chat_router(
            session_factory=session_factory,
            settings=settings,
            embedder=embedder,
            completer=completer,
        )
    )
    return app
