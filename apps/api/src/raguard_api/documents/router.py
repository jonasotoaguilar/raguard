"""Protected /api/documents routes: authorized upload, tenant-scoped reads, deletion (F1).

Upload requires ``documents.manage`` and validates the configured size bound,
the PDF/Markdown type allowlist, the extension, and the PDF signature before
anything is persisted. The commit order is design-fixed: put the
tenant-prefixed object, commit an unready ``pending`` row, enqueue the
deterministic ``ingest:{document_id}`` job, then commit ``dispatch_ready``
before responding. Any failure after the object put compensates (object then
row) with bounded jittered retries; exhaustion alerts and keeps the stale
unready row as the sweep-owned marker, so no path leaves an orphan. Reads
require ``corpus.view`` and compose the parameterized tenant predicate;
cross-tenant targets are neutral 404s. Deletion requires ``documents.manage``
and removes the row, its chunks, and the object (best-effort) under the same
neutral 404; repeat deletes stay 404.
"""

import asyncio
import logging
import random
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.capabilities import CORPUS_VIEW, DOCUMENTS_MANAGE
from raguard_api.authorization.resolver import (
    AuthorizationResolver,
    create_scope_dependency,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.config import Settings
from raguard_api.documents.contracts import DocumentStatus
from raguard_api.documents.models import Chunk, Document, DocumentGrant
from raguard_api.documents.queue import _job_id
from raguard_api.documents.storage import document_object_key
from raguard_api.documents.visibility import (
    scope_visibility_clause,
    validate_grantee_type,
    validate_visibility,
)
from raguard_api.errors import (
    AuthorizationError,
    ConflictError,
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
_PUBLIC_COLUMNS = (
    Document.id,
    Document.name,
    Document.status,
    Document.failure_reason,
    Document.visibility,
)


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
    """Public document envelope: id/name/status/reason/visibility, never keys."""
    return {
        "id": str(row.id),
        "name": row.name,
        "status": row.status,
        "failure_reason": row.failure_reason,
        "visibility": row.visibility,
    }


def _public_grant(row: DocumentGrant) -> dict:
    """Public grant envelope: id/type/grantee, never tenant internals."""
    return {
        "id": str(row.id),
        "grantee_type": row.grantee_type,
        "grantee_id": str(row.grantee_id),
    }


class VisibilityUpdate(BaseModel):
    visibility: str = Field(min_length=1)


class GrantCreate(BaseModel):
    grantee_type: str = Field(min_length=1)
    grantee_id: uuid.UUID


async def _owned_document(
    session: AsyncSession, scope: AuthorizationScope, document_id: uuid.UUID
) -> Document:
    """Tenant-scoped document or neutral 404 (no existence disclosure)."""
    row = (
        await session.execute(
            select(Document).where(
                scope.tenant_predicate(Document.tenant_id), Document.id == document_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Document not found")
    return row


async def _require_grantee_in_tenant(
    session: AsyncSession,
    scope: AuthorizationScope,
    *,
    grantee_type: str,
    grantee_id: uuid.UUID,
) -> None:
    """Grantee must belong to the tenant: membership for users, tenant role for roles.

    Unknown grantees are a neutral 404 (same envelope as a missing grant) so
    the endpoint never discloses whether an arbitrary id exists elsewhere.
    """
    from raguard_api.identity.models import Membership, Role

    if grantee_type == "user":
        exists = (
            await session.execute(
                select(Membership.id).where(
                    Membership.tenant_id == scope.tenant_id,
                    Membership.user_id == grantee_id,
                )
            )
        ).first()
    else:
        exists = (
            await session.execute(
                select(Role.id).where(Role.tenant_id == scope.tenant_id, Role.id == grantee_id)
            )
        ).first()
    if exists is None:
        raise NotFoundError("Grantee not found")


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
                    scope_visibility_clause(scope),
                    Document.status.in_([status.value for status in DocumentStatus]),
                )
                .order_by(Document.created_at.desc())
            )
        ).all()
        return {"documents": [_public_document(row) for row in rows]}

    @router.delete("/{document_id}", status_code=204)
    async def delete_document(
        document_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(DOCUMENTS_MANAGE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> Response:
        """Delete a document: row + chunks + object, idempotent, neutral 404 (F1).

        The tenant predicate keeps cross-tenant targets a neutral 404 with
        the same wording as the reads. Chunks go first (no DB cascade),
        then the row commits; per-document grants never block the tenant admin
        (F3) — the composite FK ``ON DELETE CASCADE`` removes them with the
        row. The object delete is best-effort with the
        bounded retry budget — a missing object is a no-op (idempotent) and
        exhaustion only logs, so a storage blip never strands the row.
        Repeating DELETE on a gone document answers the neutral 404.
        No job cancel exists: ``JobQueue`` exposes only ``enqueue``, so an
        accepted ``ingest:{document_id}`` ghost may still fire — the worker
        ACKs a missing row without recreating data (jobs.dispatch_action).
        """
        row = (
            await session.execute(
                select(Document).where(
                    scope.tenant_predicate(Document.tenant_id), Document.id == document_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Document not found")
        storage_key = row.storage_key
        await session.execute(
            delete(Chunk).where(
                Chunk.document_id == document_id, Chunk.tenant_id == scope.tenant_id
            )
        )
        await session.delete(row)
        await session.commit()
        if not await _delete_object_with_retries(store, storage_key):
            logger.error(
                "delete object cleanup exhausted document_id=%s key=%s",
                document_id,
                storage_key,
            )
        return Response(status_code=204)

    @router.get("/{document_id}")
    async def get_document(
        document_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CORPUS_VIEW))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        # F3: restricted documents without a user/role grant are excluded here,
        # so cross-tenant and non-granted targets share the neutral 404.
        row = (
            await session.execute(
                select(*_PUBLIC_COLUMNS).where(
                    scope.tenant_predicate(Document.tenant_id),
                    scope_visibility_clause(scope),
                    Document.id == document_id,
                )
            )
        ).first()
        if row is None:
            raise NotFoundError("Document not found")
        return _public_document(row)

    @router.patch("/{document_id}/visibility")
    async def set_visibility(
        document_id: uuid.UUID,
        payload: VisibilityUpdate,
        scope: Annotated[AuthorizationScope, Depends(require_capability(DOCUMENTS_MANAGE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        visibility = validate_visibility(payload.visibility)
        document = await _owned_document(session, scope, document_id)
        document.visibility = visibility
        await session.commit()
        return _public_document(document)

    @router.get("/{document_id}/grants")
    async def list_grants(
        document_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(DOCUMENTS_MANAGE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        await _owned_document(session, scope, document_id)
        rows = (
            await session.execute(
                select(DocumentGrant)
                .where(
                    DocumentGrant.tenant_id == scope.tenant_id,
                    DocumentGrant.document_id == document_id,
                )
                .order_by(DocumentGrant.created_at.asc(), DocumentGrant.id.asc())
            )
        ).scalars()
        return {"grants": [_public_grant(row) for row in rows]}

    @router.post("/{document_id}/grants", status_code=201)
    async def create_grant(
        document_id: uuid.UUID,
        payload: GrantCreate,
        scope: Annotated[AuthorizationScope, Depends(require_capability(DOCUMENTS_MANAGE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        grantee_type = validate_grantee_type(payload.grantee_type)
        await _owned_document(session, scope, document_id)
        await _require_grantee_in_tenant(
            session, scope, grantee_type=grantee_type, grantee_id=payload.grantee_id
        )
        existing = (
            await session.execute(
                select(DocumentGrant.id).where(
                    DocumentGrant.tenant_id == scope.tenant_id,
                    DocumentGrant.document_id == document_id,
                    DocumentGrant.grantee_type == grantee_type,
                    DocumentGrant.grantee_id == payload.grantee_id,
                )
            )
        ).first()
        if existing is not None:
            raise ConflictError("Grant already exists")
        grant = DocumentGrant(
            tenant_id=scope.tenant_id,
            document_id=document_id,
            grantee_type=grantee_type,
            grantee_id=payload.grantee_id,
        )
        session.add(grant)
        await session.commit()
        await session.refresh(grant)
        return _public_grant(grant)

    @router.delete("/{document_id}/grants/{grant_id}", status_code=204)
    async def delete_grant(
        document_id: uuid.UUID,
        grant_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(DOCUMENTS_MANAGE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> Response:
        await _owned_document(session, scope, document_id)
        grant = (
            await session.execute(
                select(DocumentGrant).where(
                    DocumentGrant.id == grant_id,
                    DocumentGrant.tenant_id == scope.tenant_id,
                    DocumentGrant.document_id == document_id,
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            raise NotFoundError("Grant not found")
        await session.delete(grant)
        await session.commit()
        return Response(status_code=204)

    return router
