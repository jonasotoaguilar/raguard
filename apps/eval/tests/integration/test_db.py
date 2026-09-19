"""Integration tests for ODD-2: disposable migrated database and dataset seed (RED).

Locks: unique ``raguard_eval_<hex12>`` names, Alembic-head migration via
``apps/api/alembic.ini`` independent of cwd, ``DROP DATABASE … WITH (FORCE)``
cleanup in ``finally`` on success and on failure, seed topology/embeddings
preservation with an external chunk-id to UUID mapping, and no credential or
raw-embedding leakage into logs or serialized output.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import Membership, Role, Tenant, User
from raguard_eval.db import (
    EVAL_DATABASE_NAME_RE,
    evaluation_database,
    generate_eval_database_name,
)
from raguard_eval.errors import DatasetInvalid
from raguard_eval.seed import seed_evaluation_database
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

KINDS = ["relevant", "neutral", "cross-tenant", "capability-denied", "adversarial"]


def _manifest() -> dict:
    return {"schema_version": 1, "dataset_id": "mvp-v1", "draft_precision_at_10": 0.70}


def _corpus() -> dict:
    return {
        "tenants": [{"id": "t-a"}, {"id": "t-b"}],
        "documents": [
            {"id": "d-1", "tenant_id": "t-a"},
            {"id": "d-2", "tenant_id": "t-b"},
        ],
        "chunks": [
            {"id": "c-1", "tenant_id": "t-a", "document_id": "d-1", "content": "alpha bravo"},
            {
                "id": "c-2",
                "tenant_id": "t-a",
                "document_id": "d-1",
                "content": "charlie delta",
            },
            {"id": "c-3", "tenant_id": "t-b", "document_id": "d-2", "content": "echo foxtrot"},
        ],
    }


def _actors() -> dict:
    return {
        "actors": [
            {"id": "actor-a", "tenant_id": "t-a", "capabilities": ["chat.use"]},
            {"id": "actor-b", "tenant_id": "t-b", "capabilities": []},
        ]
    }


def _case(cid: str, kind: str) -> dict:
    rel = {"relevant": ["c-1"], "adversarial": ["c-1"], "cross-tenant": ["c-3"]}.get(kind, [])
    return {
        "id": cid,
        "kind": kind,
        "actor_id": "actor-b" if kind == "capability-denied" else "actor-a",
        "query": f"query for {cid}",
        "relevant_chunk_ids": rel,
    }


def _write_dataset(root: Path, actors: dict | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(_manifest()))
    (root / "corpus.json").write_text(json.dumps(_corpus()))
    (root / "actors.json").write_text(json.dumps(actors or _actors()))
    rows = [_case(f"case-{kind}", kind) for kind in KINDS]
    (root / "cases.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return root


async def _database_exists(admin_url: str, name: str) -> bool:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            return row.scalar_one_or_none() is not None
    finally:
        await engine.dispose()


def test_generated_names_match_eval_pattern_and_are_unique() -> None:
    names = {generate_eval_database_name() for _ in range(25)}
    assert len(names) == 25
    for name in names:
        assert EVAL_DATABASE_NAME_RE.match(name), name
        assert re.fullmatch(r"raguard_eval_[0-9a-f]{12}", name), name


def test_alembic_ini_resolves_independent_of_cwd(tmp_path: Path, monkeypatch) -> None:
    from raguard_eval import db as db_module

    monkeypatch.chdir(tmp_path)
    ini = Path(db_module.ALEMBIC_INI_PATH)
    assert ini.is_absolute()
    assert ini.is_file()
    assert ini.name == "alembic.ini"
    assert ini.parent.name == "api"


def test_db_and_seed_modules_never_emit_credentials_or_embeddings() -> None:
    root = Path(__file__).resolve().parents[4] / "apps" / "eval" / "src" / "raguard_eval"
    for module in ("db.py", "seed.py"):
        source = (root / module).read_text(encoding="utf-8")
        lowered = source.lower()
        assert "print(" not in lowered
        assert "logging" not in lowered
        assert "caplog" not in lowered
        assert "to_dict" not in lowered
        assert "model_dump" not in lowered
        assert "json.dumps" not in lowered
    db_source = (root / "db.py").read_text(encoding="utf-8")
    assert db_source.count("repr=False") >= 2


async def test_lifecycle_creates_migrated_database_and_drops_it_after_exit() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from raguard_eval import db as db_module

    script = ScriptDirectory.from_config(Config(str(db_module.ALEMBIC_INI_PATH)))
    heads = set(script.get_heads())
    assert len(heads) >= 1
    try:
        async with evaluation_database() as db:
            assert EVAL_DATABASE_NAME_RE.match(db.database_name)
            admin_url = db_module.eval_admin_url()
            assert await _database_exists(admin_url, db.database_name) is True
            async with db.engine.connect() as conn:
                applied = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).all()
                assert {row[0] for row in applied} == heads
                tenants = (await conn.execute(text("SELECT count(*) FROM tenants"))).scalar_one()
                assert tenants == 0
            live_name = db.database_name
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL unavailable ({exc.__class__.__name__}); start the local stack")
    assert await _database_exists(admin_url, live_name) is False


async def test_migrate_failure_still_drops_created_database(monkeypatch) -> None:
    from raguard_eval import db as db_module

    seen: dict[str, str] = {}

    async def _failing_upgrade(database_url: str) -> None:
        seen["url"] = database_url
        raise RuntimeError("migrate boom")

    monkeypatch.setattr(db_module, "_upgrade_to_head", _failing_upgrade)
    with pytest.raises(RuntimeError, match="migrate boom"):
        try:
            async with evaluation_database():
                pytest.fail("migration failure must not yield a database")
        except OperationalError as exc:
            pytest.skip(f"PostgreSQL unavailable ({exc.__class__.__name__}); start the local stack")
    admin_url = db_module.eval_admin_url()
    abandoned = make_url(seen["url"]).database
    assert abandoned is not None and EVAL_DATABASE_NAME_RE.match(abandoned)
    assert await _database_exists(admin_url, abandoned) is False


async def test_cleanup_forces_drop_when_body_raises() -> None:
    from raguard_eval import db as db_module

    live_name = None
    with pytest.raises(RuntimeError, match="seed boom"):
        try:
            async with evaluation_database() as db:
                live_name = db.database_name
                admin_url = db_module.eval_admin_url()
                assert await _database_exists(admin_url, live_name) is True
                raise RuntimeError("seed boom")
        except OperationalError as exc:
            pytest.skip(f"PostgreSQL unavailable ({exc.__class__.__name__}); start the local stack")
    assert live_name is not None
    assert await _database_exists(admin_url, live_name) is False


async def test_seed_preserves_topology_embeddings_and_chunk_mapping(tmp_path: Path) -> None:
    from raguard_eval import db as db_module

    dataset_dir = _write_dataset(tmp_path / "dataset")
    try:
        async with evaluation_database() as db:
            seeded = await seed_evaluation_database(db.session_factory, dataset_dir)

            assert set(seeded.chunk_ids) == {"c-1", "c-2", "c-3"}
            assert set(seeded.actor_user_ids) == {"actor-a", "actor-b"}

            await _assert_seed_topology(db, seeded)
            live_name = db.database_name
            admin_url = db_module.eval_admin_url()
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL unavailable ({exc.__class__.__name__}); start the local stack")
    assert await _database_exists(admin_url, live_name) is False


async def _assert_seed_topology(db, seeded) -> None:
    from raguard_eval.embedder import Sha256TokenEmbedder

    async with db.session_factory() as session:
        assert (await session.execute(select(func.count()).select_from(Tenant))).scalar_one() == 2
        assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 2
        assert (await session.execute(select(func.count()).select_from(Role))).scalar_one() == 2
        assert (
            await session.execute(select(func.count()).select_from(Membership))
        ).scalar_one() == 2
        assert (await session.execute(select(func.count()).select_from(Document))).scalar_one() == 2
        assert (await session.execute(select(func.count()).select_from(Chunk))).scalar_one() == 3

        tenants = {t.name: t for t in (await session.execute(select(Tenant))).scalars()}
        users = {u.email: u for u in (await session.execute(select(User))).scalars()}
        roles = {r.name: r for r in (await session.execute(select(Role))).scalars()}
        memberships = (await session.execute(select(Membership))).scalars().all()
        documents = {d.name: d for d in (await session.execute(select(Document))).scalars()}

        tenant_a = next(t for n, t in tenants.items() if "t-a" in n)
        tenant_b = next(t for n, t in tenants.items() if "t-b" in n)
        assert tenant_a.id != tenant_b.id

        assert set(roles["eval-actor-a"].capabilities) == {"chat.use"}
        assert roles["eval-actor-b"].capabilities == []
        assert roles["eval-actor-a"].tenant_id == tenant_a.id
        assert roles["eval-actor-b"].tenant_id == tenant_b.id
        for membership in memberships:
            role = next(r for r in roles.values() if r.id == membership.role_id)
            user = next(u for u in users.values() if u.id == membership.user_id)
            assert membership.tenant_id == role.tenant_id
            expected_tenant = tenant_a.id if user.email.startswith("actor-a") else tenant_b.id
            assert membership.tenant_id == expected_tenant

        assert documents["d-1"].tenant_id == tenant_a.id
        assert documents["d-2"].tenant_id == tenant_b.id

        embedder = Sha256TokenEmbedder()
        expected_content = {
            "c-1": "alpha bravo",
            "c-2": "charlie delta",
            "c-3": "echo foxtrot",
        }
        expected_tenant = {"c-1": tenant_a.id, "c-2": tenant_a.id, "c-3": tenant_b.id}
        for external_id, content in expected_content.items():
            row_id = seeded.chunk_ids[external_id]
            stored = (await session.execute(select(Chunk).where(Chunk.id == row_id))).scalar_one()
            assert stored.content == content
            assert stored.tenant_id == expected_tenant[external_id]
            document = (
                await session.execute(select(Document).where(Document.id == stored.document_id))
            ).scalar_one()
            assert document.tenant_id == stored.tenant_id
            (expected_vector,) = embedder.embed([content])
            assert len(stored.embedding) == 1536
            # halfvec stores float16: same nonzero axes, values within rounding.
            assert list(stored.embedding) == pytest.approx(expected_vector, rel=1e-3, abs=1e-3)
            assert {i for i, v in enumerate(stored.embedding) if v != 0.0} == {
                i for i, v in enumerate(expected_vector) if v != 0.0
            }
            norm = math.sqrt(sum(v * v for v in stored.embedding))
            assert norm == pytest.approx(1.0, rel=1e-3, abs=1e-3)

        for actor_id, user_id in seeded.actor_user_ids.items():
            stored_user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one()
            assert stored_user.email == f"{actor_id}@eval.invalid"


async def test_seed_rejects_capability_outside_production_allowlist(tmp_path: Path) -> None:
    actors = _actors()
    actors["actors"][0]["capabilities"] = ["chat.use", "root.everything"]
    dataset_dir = _write_dataset(tmp_path / "dataset", actors=actors)
    try:
        async with evaluation_database() as db:
            with pytest.raises(DatasetInvalid, match="unsupported capabilities"):
                await seed_evaluation_database(db.session_factory, dataset_dir)
            async with db.session_factory() as session:
                for table in (Tenant, User, Role, Membership, Document, Chunk):
                    count = (
                        await session.execute(select(func.count()).select_from(table))
                    ).scalar_one()
                    assert count == 0
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL unavailable ({exc.__class__.__name__}); start the local stack")
