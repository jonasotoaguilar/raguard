"""Protected /api/documents routes: authorized upload and tenant-scoped reads (task 2.4).

Upload requires ``documents.manage`` and validates the configured size bound,
the PDF/Markdown type allowlist, the extension, and the PDF signature before
anything is persisted. The commit order is design-fixed: put the
tenant-prefixed object, commit an unready ``pending`` row, enqueue the
deterministic ``ingest:{document_id}`` job, then commit ``dispatch_ready``
before responding. Any failure after the object put compensates (object then
row) with bounded jittered retries; exhaustion alerts and keeps the stale
unready row as the sweep-owned marker, so no path leaves an orphan. Reads
require ``corpus.view`` and compose the parameterized tenant predicate;
cross-tenant targets are neutral 404s.
"""

import asyncio
import logging
import random
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.capabilities import CORPUS_VIEW, DOCUMENTS_MANAGE
from raguard_api.authorization.resolver import (
    AuthorizationResolver,
    create_scope_dependency,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.config import Settings
from raguard_api.documents.contracts import DocumentStatus
from raguard_api.documents.models import Document
from raguard_api.documents.queue import _job_id
from raguard_api.documents.storage import document_object_key
from raguard_api.errors import (
    AuthorizationError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_TYPES = ("application/pdf", "text/markdown")
ALLOWED_UPLOAD_EXTENSIONS = (".pdf", ".md", ".markdown")
PDF_SIGNATURE = b"%PDF-"
_COMPENSATION_ATTEMPTS = 3
_COMPENSATION_MAX_JITTER = 0.05
_PUBLIC_COLUMNS = (Document.id, Document.name, Document.status, Document.failure_reason)


def safe_basename(filename: str | None) -> str:
    """Strip any client-supplied path and reject unsafe names (task 2.4 bound)."""
    if not filename:
        raise ValidationError("Filename is required")
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not basename or basename in {".", ".."} or "/" in basename or "\x00" in basename:
        raise ValidationError("Invalid filename")
    return basename


def validate_upload(
    *, content_type: str | None, filename: str | None, data: bytes, max_bytes: int
) -> str:
    """Validate size/type/extension/signature bounds and return the safe basename.

    Pure and unit-testable: raises ValidationError (400) on any bound violation
    before storage or queueing is ever touched (spec: nothing persisted).
    """
    basename = safe_basename(filename)
    if len(data) > max_bytes:
        raise ValidationError("File exceeds the maximum upload size")
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise ValidationError("Unsupported file type")
    if Path(basename).suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError("Unsupported file extension")
    if content_type == "application/pdf" and not data.startswith(PDF_SIGNATURE):
        raise ValidationError("Invalid PDF signature")
    return basename


async def _delete_object_with_retries(
    store: Any, key: str, *, attempts: int = _COMPENSATION_ATTEMPTS
) -> bool:
    """Bounded jittered object delete; True when deleted, False on exhaustion (task 2.5)."""
    for attempt in range(attempts):
        try:
            await asyncio.to_thread(store.delete, key)
            return True
        except Exception:
            if attempt == attempts - 1:
                return False
            await asyncio.sleep(random.uniform(0, _COMPENSATION_MAX_JITTER * (attempt + 1)))
    return False


async def _remove_object(store: Any, document: Document) -> None:
    """Cleanup for a row that never committed: delete the object or alert."""
    if not await _delete_object_with_retries(store, document.storage_key):
        logger.error(
            "object cleanup exhausted document_id=%s key=%s", document.id, document.storage_key
        )


async def _compensate(*, session: AsyncSession, store: Any, document: Document) -> None:
    """Delete the object then the row; on exhaustion keep the row as the sweep marker."""
    if await _delete_object_with_retries(store, document.storage_key):
        await session.delete(document)
        await session.commit()
    else:
        logger.error(
            "compensation exhausted: stale unready row left as sweep marker document_id=%s key=%s",
            document.id,
            document.storage_key,
        )


def _public_document(row) -> dict:
    """Public document envelope: id/name/status/allowlisted reason, never keys."""
    return {
        "id": str(row.id),
        "name": row.name,
        "status": row.status,
        "failure_reason": row.failure_reason,
    }


def create_documents_router(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: Any,
    queue: Any,
) -> APIRouter:
    resolver = AuthorizationResolver(session_factory=session_factory)
    GetScope = Annotated[AuthorizationScope, Depends(create_scope_dependency(resolver))]

    def require_capability(capability: str):
        """Dependency: allow only scopes holding the capability (403 otherwise)."""

        def _require(scope: GetScope) -> AuthorizationScope:
            if not scope.has_capability(capability):
                raise AuthorizationError("Insufficient permissions")
            return scope

        return _require

    router = APIRouter(prefix="/api/documents", tags=["documents"])

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    @router.post("", status_code=201)
    async def upload_document(
        scope: Annotated[AuthorizationScope, Depends(require_capability(DOCUMENTS_MANAGE))],
        session: Annotated[AsyncSession, Depends(_session)],
        file: Annotated[UploadFile, File()],
    ) -> dict:
        data = await file.read(settings.max_upload_bytes + 1)
        basename = validate_upload(
            content_type=file.content_type,
            filename=file.filename,
            data=data,
            max_bytes=settings.max_upload_bytes,
        )
        document_id = uuid.uuid4()
        key = document_object_key(
            tenant_id=scope.tenant_id, document_id=document_id, basename=basename
        )
        try:
            await asyncio.to_thread(store.put, key, data)
        except Exception as exc:
            logger.warning("object store put failed tenant_id=%s key=%s", scope.tenant_id, key)
            raise ServiceUnavailableError("Storage unavailable") from exc

        document = Document(
            id=document_id,
            tenant_id=scope.tenant_id,
            name=basename,
            status=DocumentStatus.pending.value,
            storage_key=key,
        )
        session.add(document)
        try:
            await session.commit()
        except Exception as exc:
            await _remove_object(store, document)
            raise ServiceUnavailableError("Storage unavailable") from exc
        try:
            await asyncio.to_thread(queue.enqueue, _job_id(document_id), document_id)
            document.dispatch_ready = True
            await session.commit()
        except Exception as exc:
            await _compensate(session=session, store=store, document=document)
            raise ServiceUnavailableError("Queue unavailable") from exc
        return _public_document(document)

    @router.get("")
    async def list_documents(
        scope: Annotated[AuthorizationScope, Depends(require_capability(CORPUS_VIEW))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        rows = (
            await session.execute(
                select(*_PUBLIC_COLUMNS)
                .where(
                    scope.tenant_predicate(Document.tenant_id),
                    Document.status.in_([status.value for status in DocumentStatus]),
                )
                .order_by(Document.created_at.desc())
            )
        ).all()
        return {"documents": [_public_document(row) for row in rows]}

    @router.get("/{document_id}")
    async def get_document(
        document_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CORPUS_VIEW))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        row = (
            await session.execute(
                select(*_PUBLIC_COLUMNS).where(
                    scope.tenant_predicate(Document.tenant_id), Document.id == document_id
                )
            )
        ).first()
        if row is None:
            raise NotFoundError("Document not found")
        return _public_document(row)

    return router
