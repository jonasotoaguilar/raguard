"""Per-document visibility predicate (F3).

Semantics (also documented on the ORM and the migration):
- ``visibility='tenant'``: visible to anyone holding ``corpus.view`` in the
  tenant (the behavior that predates F3; the column default).
- ``visibility='restricted'``: visible ONLY when a row in ``document_grants``
  names the caller (``grantee_type='user'``) or one of the caller's roles
  (``grantee_type='role'``) — still gated by ``corpus.view`` at the route.

The clause is SQL composed into the retrieval statements alongside the tenant
predicate, BEFORE ranking, so a restricted chunk without a grant can never be
ranked, fused, cited, or prompted (the non-negotiable retrieval invariant).
The same clause filters the document list/detail reads. Route capabilities
(``corpus.view`` / ``documents.manage``) are enforced separately by the
routers; this module never grants a capability.
"""

import uuid

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.sql.elements import ColumnElement

from raguard_api.documents.models import Document, DocumentGrant
from raguard_api.errors import ValidationError

VISIBILITY_TENANT = "tenant"
VISIBILITY_RESTRICTED = "restricted"
VISIBILITIES = (VISIBILITY_TENANT, VISIBILITY_RESTRICTED)
GRANTEE_TYPES = ("user", "role")


def validate_visibility(value: str) -> str:
    """Return the value when it is a known visibility, else 400."""
    if value not in VISIBILITIES:
        raise ValidationError("Invalid visibility")
    return value


def validate_grantee_type(value: str) -> str:
    """Return the value when it is a known grantee type, else 400."""
    if value not in GRANTEE_TYPES:
        raise ValidationError("Invalid grantee type")
    return value


def visibility_clause(
    *,
    user_id: uuid.UUID,
    role_ids: frozenset[uuid.UUID] | set[uuid.UUID] | tuple | list,
) -> ColumnElement[bool]:
    """SQL predicate: tenant-visible docs, or restricted docs with a grant.

    All ids bind as parameters; only the fixed ``'tenant'``/``'user'``/``'role'``
    tokens appear as literals (same convention as the FTS config constant).
    An empty ``role_ids`` omits the role branch instead of emitting an empty
    ``IN ()``.
    """
    grants = [
        and_(
            DocumentGrant.tenant_id == Document.tenant_id,
            DocumentGrant.document_id == Document.id,
            DocumentGrant.grantee_type == "user",
            DocumentGrant.grantee_id == user_id,
        )
    ]
    roles = frozenset(role_ids or ())
    if roles:
        grants.append(
            and_(
                DocumentGrant.tenant_id == Document.tenant_id,
                DocumentGrant.document_id == Document.id,
                DocumentGrant.grantee_type == "role",
                DocumentGrant.grantee_id.in_(roles),
            )
        )
    grant_exists = exists(select(1).select_from(DocumentGrant).where(or_(*grants)))
    return or_(Document.visibility == VISIBILITY_TENANT, grant_exists)


def scope_visibility_clause(scope) -> ColumnElement[bool]:
    """Build the clause from an ``AuthorizationScope`` (user + role ids)."""
    return visibility_clause(user_id=scope.user_id, role_ids=scope.role_ids)
