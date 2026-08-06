"""Integration tests: first-tenant bootstrap — atomicity, idempotency, concurrency (task 4.1).

Drives the not-yet-existing ``raguard_api.identity.bootstrap`` module: env
validation before any write, one atomic transaction under a transaction
advisory lock creating the first tenant, the default roles, and the admin
membership, idempotent reruns, and no-op behavior when identity data already
exists. Also locks the CLI contract: secrets come only from the environment,
are never echoed in logs or output, and exit codes are 0 (success/no-op),
2 (invalid environment), or 1 (runtime failure).
"""

import asyncio
import logging

import pytest
from raguard_api.auth.passwords import verify_password
from raguard_api.identity import bootstrap
from raguard_api.identity.models import Membership, Role, Tenant, User
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

TENANT_NAME = "Acme Corp"
ADMIN_EMAIL = "admin@acme.example"
ADMIN_PASSWORD = "bootstrap-admin-secret"
ALL_CAPS = {
    "org.settings.manage",
    "users.manage",
    "documents.manage",
    "corpus.view",
    "chat.use",
}


async def _counts(session_factory):
    async with session_factory() as session:
        counts = []
        for table in (Tenant, User, Role, Membership):
            counts.append(
                (await session.execute(select(func.count()).select_from(table))).scalar_one()
            )
        return tuple(counts)


async def _run(session_factory, **overrides):
    return await bootstrap.run_bootstrap(
        session_factory=session_factory,
        tenant_name=overrides.get("tenant_name", TENANT_NAME),
        admin_email=overrides.get("admin_email", ADMIN_EMAIL),
        admin_password=overrides.get("admin_password", ADMIN_PASSWORD),
    )


async def _database_url(migrated_db) -> str:
    return migrated_db.engine.url.render_as_string(hide_password=False)


async def test_bootstrap_creates_first_tenant_default_roles_and_admin(migrated_db):
    assert await _run(migrated_db.session_factory) is True
    assert await _counts(migrated_db.session_factory) == (1, 1, 2, 1)
    async with migrated_db.session_factory() as session:
        tenant = (await session.execute(select(Tenant))).scalar_one()
        assert tenant.name == TENANT_NAME
        admin = (await session.execute(select(User))).scalar_one()
        assert admin.email == ADMIN_EMAIL
        assert verify_password(ADMIN_PASSWORD, admin.password_hash) is True
        roles = {
            name: set(capabilities)
            for name, capabilities in (
                await session.execute(select(Role.name, Role.capabilities))
            ).all()
        }
        assert roles == {
            "admin": ALL_CAPS,
            "member": {"corpus.view", "chat.use"},
        }
        membership = (await session.execute(select(Membership))).scalar_one()
        assert membership.tenant_id == tenant.id
        assert membership.user_id == admin.id


async def test_bootstrap_rerun_is_idempotent_and_preserves_rows(migrated_db):
    assert await _run(migrated_db.session_factory) is True
    async with migrated_db.session_factory() as session:
        before = (await session.execute(select(User))).scalar_one().password_hash
    assert await _run(migrated_db.session_factory) is False
    assert await _counts(migrated_db.session_factory) == (1, 1, 2, 1)
    async with migrated_db.session_factory() as session:
        after = (await session.execute(select(User))).scalar_one().password_hash
    assert after == before  # no duplicate rows, no re-hash, no reset


async def test_bootstrap_with_existing_identity_data_is_a_noop(migrated_db):
    # Identity provisioned through admin APIs, not bootstrap.
    async with migrated_db.session_factory() as session:
        tenant = Tenant(name="Existing Org")
        session.add(tenant)
        await session.flush()
        role = Role(tenant_id=tenant.id, name="member", capabilities=["corpus.view", "chat.use"])
        user = User(email="existing@example.com", password_hash="x")
        session.add_all([role, user])
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role_id=role.id))
        await session.commit()
        existing_ids = (tenant.id, user.id, role.id)
    assert await _run(migrated_db.session_factory) is False
    assert await _counts(migrated_db.session_factory) == (1, 1, 1, 1)
    async with migrated_db.session_factory() as session:
        row = (await session.execute(select(Tenant))).scalar_one()
        assert (row.id, row.name) == (existing_ids[0], "Existing Org")
        emails = (await session.execute(select(User.email))).scalars().all()
        assert emails == ["existing@example.com"]  # bootstrap admin never inserted


async def test_concurrent_bootstrap_runs_create_exactly_one_set(migrated_db):
    results = await asyncio.gather(
        _run(migrated_db.session_factory),
        _run(migrated_db.session_factory),
    )
    assert set(results) == {True, False}  # advisory lock serialized the pair
    assert await _counts(migrated_db.session_factory) == (1, 1, 2, 1)


@pytest.mark.parametrize(
    "env",
    [
        {
            "BOOTSTRAP_TENANT_NAME": "   ",
            "BOOTSTRAP_ADMIN_EMAIL": ADMIN_EMAIL,
            "BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD,
        },
        {
            "BOOTSTRAP_TENANT_NAME": TENANT_NAME,
            "BOOTSTRAP_ADMIN_EMAIL": "not-an-email",
            "BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD,
        },
        {
            "BOOTSTRAP_TENANT_NAME": TENANT_NAME,
            "BOOTSTRAP_ADMIN_EMAIL": ADMIN_EMAIL,
            "BOOTSTRAP_ADMIN_PASSWORD": "short",
        },
        {
            "BOOTSTRAP_TENANT_NAME": TENANT_NAME,
            "BOOTSTRAP_ADMIN_EMAIL": ADMIN_EMAIL,
            "BOOTSTRAP_ADMIN_PASSWORD": "",
        },
    ],
)
def test_bootstrap_env_validation_rejects_invalid_values(env):
    with pytest.raises(bootstrap.BootstrapConfigError) as excinfo:
        bootstrap.read_bootstrap_env(env)
    assert "short" not in str(excinfo.value)
    assert "not-an-email" not in str(excinfo.value)


def test_bootstrap_env_validation_normalizes_tenant_and_email():
    tenant_name, email, _password = bootstrap.read_bootstrap_env(
        {
            "BOOTSTRAP_TENANT_NAME": "  Acme Corp  ",
            "BOOTSTRAP_ADMIN_EMAIL": "  Admin@Acme.Example ",
            "BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD,
        }
    )
    assert tenant_name == "Acme Corp"
    assert email == "admin@acme.example"


async def test_bootstrap_cli_creates_rows_and_rerun_exits_zero_unchanged(migrated_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", await _database_url(migrated_db))
    monkeypatch.setenv("BOOTSTRAP_TENANT_NAME", TENANT_NAME)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", ADMIN_PASSWORD)
    first = await asyncio.to_thread(bootstrap.main)
    second = await asyncio.to_thread(bootstrap.main)
    assert (first, second) == (0, 0)
    assert await _counts(migrated_db.session_factory) == (1, 1, 2, 1)


async def test_bootstrap_cli_invalid_env_exits_2_without_writes(migrated_db, monkeypatch, capsys):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("BOOTSTRAP_TENANT_NAME", TENANT_NAME)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", ADMIN_EMAIL)
    exit_code = await asyncio.to_thread(bootstrap.main)
    assert exit_code == 2
    assert await _counts(migrated_db.session_factory) == (0, 0, 0, 0)
    assert ADMIN_PASSWORD not in capsys.readouterr().err  # rejected secret never echoed


async def test_bootstrap_logs_exclude_credentials_and_emails(migrated_db, caplog):
    with caplog.at_level(logging.INFO):
        await _run(migrated_db.session_factory)
    assert ADMIN_EMAIL not in caplog.text
    assert ADMIN_PASSWORD not in caplog.text


async def test_bootstrap_rolls_back_atomically_on_constraint_violation(migrated_db):
    async with migrated_db.session_factory() as session:
        session.add(User(email=ADMIN_EMAIL, password_hash="x"))
        await session.commit()
    with pytest.raises(IntegrityError):
        await _run(migrated_db.session_factory)
    assert await _counts(migrated_db.session_factory) == (0, 1, 0, 0)  # nothing partial left
