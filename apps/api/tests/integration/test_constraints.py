"""Integration tests: identity constraints (task 1.2).

Covers global email uniqueness, tenant-scoped role names, the capabilities
allowlist, the composite tenant+role FK (cross-tenant grants denied), and the
one-membership-per-user/tenant rule.
"""

import pytest
from raguard_api.documents.contracts import EMBEDDING_DIMENSION
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import ALLOWED_CAPABILITIES, Membership, Role, Tenant, User
from sqlalchemy import func, select
from sqlalchemy.exc import DataError, IntegrityError

pytestmark = pytest.mark.integration


async def _insert(db, *objects) -> None:
    async with db.session_factory() as session:
        session.add_all(objects)
        await session.commit()


async def _count(db, model) -> int:
    async with db.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _seed_tenant(db, name: str) -> Tenant:
    tenant = Tenant(name=name)
    await _insert(db, tenant)
    return tenant


async def _seed_user(db, email: str) -> User:
    user = User(email=email, password_hash="test-hash")
    await _insert(db, user)
    return user


async def _seed_role(db, tenant: Tenant, name: str, capabilities: list[str]) -> Role:
    role = Role(tenant_id=tenant.id, name=name, capabilities=capabilities)
    await _insert(db, role)
    return role


async def test_email_unique_globally(migrated_db):
    await _insert(migrated_db, User(email="a@example.com", password_hash="hash-a"))

    with pytest.raises(IntegrityError):
        await _insert(migrated_db, User(email="a@example.com", password_hash="hash-b"))

    assert await _count(migrated_db, User) == 1


async def test_distinct_emails_allowed(migrated_db):
    await _insert(
        migrated_db,
        User(email="a@example.com", password_hash="hash-a"),
        User(email="b@example.com", password_hash="hash-b"),
    )
    assert await _count(migrated_db, User) == 2


async def test_role_name_unique_within_tenant(migrated_db):
    tenant_a = await _seed_tenant(migrated_db, "Tenant A")
    tenant_b = await _seed_tenant(migrated_db, "Tenant B")

    await _seed_role(migrated_db, tenant_a, "editor", ["corpus.view"])
    await _seed_role(migrated_db, tenant_b, "editor", ["corpus.view"])

    with pytest.raises(IntegrityError):
        await _seed_role(migrated_db, tenant_a, "editor", ["chat.use"])

    async with migrated_db.session_factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Role)
                .where(Role.tenant_id == tenant_a.id, Role.name == "editor")
            )
        ).scalar_one()
    assert count == 1


async def test_capabilities_restricted_to_allowlist(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")

    await _seed_role(migrated_db, tenant, "member", ["corpus.view", "chat.use"])

    with pytest.raises(IntegrityError):
        await _seed_role(migrated_db, tenant, "rogue", ["delete.everything"])
    with pytest.raises(IntegrityError):
        await _seed_role(
            migrated_db, tenant, "rogue-mixed", [*ALLOWED_CAPABILITIES, "invented.capability"]
        )

    await _seed_role(migrated_db, tenant, "empty", [])
    assert await _count(migrated_db, Role) == 2


async def test_cross_tenant_role_grant_denied(migrated_db):
    tenant_a = await _seed_tenant(migrated_db, "Tenant A")
    tenant_b = await _seed_tenant(migrated_db, "Tenant B")
    user = await _seed_user(migrated_db, "user@example.com")
    role_b = await _seed_role(migrated_db, tenant_b, "admin", list(ALLOWED_CAPABILITIES))

    with pytest.raises(IntegrityError):
        await _insert(
            migrated_db, Membership(tenant_id=tenant_a.id, user_id=user.id, role_id=role_b.id)
        )

    assert await _count(migrated_db, Membership) == 0


async def test_membership_with_same_tenant_role_succeeds(migrated_db):
    tenant_a = await _seed_tenant(migrated_db, "Tenant A")
    user = await _seed_user(migrated_db, "user@example.com")
    role_a = await _seed_role(migrated_db, tenant_a, "member", ["corpus.view", "chat.use"])

    await _insert(
        migrated_db, Membership(tenant_id=tenant_a.id, user_id=user.id, role_id=role_a.id)
    )
    assert await _count(migrated_db, Membership) == 1


async def test_one_membership_per_user_tenant(migrated_db):
    tenant_a = await _seed_tenant(migrated_db, "Tenant A")
    tenant_b = await _seed_tenant(migrated_db, "Tenant B")
    user = await _seed_user(migrated_db, "user@example.com")
    member_a = await _seed_role(migrated_db, tenant_a, "member", ["corpus.view"])
    admin_a = await _seed_role(migrated_db, tenant_a, "admin", list(ALLOWED_CAPABILITIES))
    member_b = await _seed_role(migrated_db, tenant_b, "member", ["corpus.view"])

    await _insert(
        migrated_db, Membership(tenant_id=tenant_a.id, user_id=user.id, role_id=member_a.id)
    )

    with pytest.raises(IntegrityError):
        await _insert(
            migrated_db, Membership(tenant_id=tenant_a.id, user_id=user.id, role_id=admin_a.id)
        )

    await _insert(
        migrated_db, Membership(tenant_id=tenant_b.id, user_id=user.id, role_id=member_b.id)
    )
    assert await _count(migrated_db, Membership) == 2


def _embedding(dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """Deterministic non-zero vector of the requested dimension."""
    return [(dim_index + 1) / 1000 for dim_index in range(dim)]


async def _seed_document(db, tenant: Tenant, *, name: str, storage_key: str, **fields) -> Document:
    document = Document(tenant_id=tenant.id, name=name, storage_key=storage_key, **fields)
    await _insert(db, document)
    return document


async def _seed_chunk(
    db, tenant: Tenant, document: Document, *, position: int, content: str = "chunk text"
) -> Chunk:
    chunk = Chunk(
        tenant_id=tenant.id,
        document_id=document.id,
        position=position,
        content=content,
        embedding=_embedding(),
    )
    await _insert(db, chunk)
    return chunk


async def test_document_pending_row_succeeds_and_starts_unready(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")

    await _seed_document(migrated_db, tenant, name="report.pdf", storage_key="tenant-a/report.pdf")

    async with migrated_db.session_factory() as session:
        row = (
            await session.execute(select(Document).where(Document.tenant_id == tenant.id))
        ).scalar_one()
    assert row.status == "pending"
    assert row.failure_reason is None
    assert row.dispatch_ready is False


async def test_document_status_outside_enum_rejected(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")

    with pytest.raises(IntegrityError):
        await _seed_document(migrated_db, tenant, name="x.pdf", storage_key="k", status="archived")

    assert await _count(migrated_db, Document) == 0


async def test_document_failure_reason_outside_allowlist_rejected(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")

    with pytest.raises(IntegrityError):
        await _seed_document(
            migrated_db,
            tenant,
            name="x.pdf",
            storage_key="k",
            status="failed",
            failure_reason="exploded",
        )

    assert await _count(migrated_db, Document) == 0


async def test_document_allowlisted_failure_reason_accepted(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")

    await _seed_document(
        migrated_db,
        tenant,
        name="x.pdf",
        storage_key="k",
        status="failed",
        failure_reason="source_missing",
    )

    async with migrated_db.session_factory() as session:
        row = (
            await session.execute(select(Document).where(Document.tenant_id == tenant.id))
        ).scalar_one()
    assert (row.status, row.failure_reason) == ("failed", "source_missing")


async def test_chunk_position_unique_per_document(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")
    document = await _seed_document(migrated_db, tenant, name="a.pdf", storage_key="k")

    await _seed_chunk(migrated_db, tenant, document, position=1)

    with pytest.raises(IntegrityError):
        await _seed_chunk(migrated_db, tenant, document, position=1)

    await _seed_chunk(migrated_db, tenant, document, position=0)
    assert await _count(migrated_db, Chunk) == 2


async def test_same_position_allowed_across_documents(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")
    first = await _seed_document(migrated_db, tenant, name="a.pdf", storage_key="k1")
    second = await _seed_document(migrated_db, tenant, name="b.pdf", storage_key="k2")

    await _seed_chunk(migrated_db, tenant, first, position=0)
    await _seed_chunk(migrated_db, tenant, second, position=0)

    assert await _count(migrated_db, Chunk) == 2


async def test_cross_tenant_chunk_attachment_denied(migrated_db):
    tenant_a = await _seed_tenant(migrated_db, "Tenant A")
    tenant_b = await _seed_tenant(migrated_db, "Tenant B")
    document_a = await _seed_document(migrated_db, tenant_a, name="a.pdf", storage_key="k")

    with pytest.raises(IntegrityError):
        await _seed_chunk(migrated_db, tenant_b, document_a, position=0)

    assert await _count(migrated_db, Chunk) == 0


async def test_chunk_embedding_dimension_enforced(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")
    document = await _seed_document(migrated_db, tenant, name="a.pdf", storage_key="k")

    await _seed_chunk(migrated_db, tenant, document, position=0)

    with pytest.raises((IntegrityError, DataError)):
        await _insert(
            migrated_db,
            Chunk(
                tenant_id=tenant.id,
                document_id=document.id,
                position=1,
                content="wrong dimension",
                embedding=_embedding(dim=4),
            ),
        )

    assert await _count(migrated_db, Chunk) == 1


async def test_chunk_search_vector_generated_from_content(migrated_db):
    tenant = await _seed_tenant(migrated_db, "Tenant A")
    document = await _seed_document(migrated_db, tenant, name="a.pdf", storage_key="k")

    await _seed_chunk(migrated_db, tenant, document, position=0, content="Hello world")

    async with migrated_db.session_factory() as session:
        result = await session.execute(
            select(Chunk.search_vector).where(Chunk.document_id == document.id)
        )
        search_vector = result.scalar_one()
    assert search_vector == "'hello':1 'world':2"
