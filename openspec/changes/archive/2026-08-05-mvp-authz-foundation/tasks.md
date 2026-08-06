# Tasks: MVP Authz Foundation

## Review Workload Forecast

Estimated changed lines: 1,100–1,500 cumulative (PR 4 measured ~960 authored)
400-line budget risk: High
Chained PRs recommended: Yes
Delivery strategy: auto-chain
Chain strategy: stacked-to-main
Decision needed before apply: No
800-line session budget does not override 400-line repository gate.

Strict TDD: enabled (RED→GREEN→REFACTOR)

> Phase 1a/1b and Phase 2 (2.1–2.8) are implemented uncommitted in the worktree (751 + 658 ledger lines; reset ≠ approval; no reimplementation or discard). Native runtime blocked PR 2 at 658 authored lines > 400-line gate; delivery re-sliced into PR 2a + PR 2b, both ≤400, stacked-to-main. Native runtime blocked PR 3 at 835 authored lines (126 authorization core + 246 unit tests + 182 org router + 281 integration test) > 400-line gate; PR 3 delivery re-sliced into PR 3a + 3b + 3c, each ≤400 authored lines, stacked-to-main. Native runtime blocked PR 4 at ~960 measured authored lines (203 bootstrap tests + 239 release-gate tests + 110 security-boundary tests + 145 bootstrap.py + 17 CLI + 24 main.py + 22 ci.yml + 16 .env.example) > 400-line gate; PR 4 delivery re-sliced into PR 4a + 4b + 4c + 4d, each ≤400 measured, stacked-to-main, deps 4a→4b→4c→4d. All current implementation (Phases 1a–4) remains in the worktree; delivery is re-sliced, not reimplemented or discarded. Do not accept size:exception.

### Work Units (stacked-to-main, ≤400 each)

- **PR 1a** ORM foundation: `apps/api/src/raguard_api/{db.py,identity/}` + `__init__.py`, `apps/api/alembic.ini`, `alembic/{env.py,script.py.mako}`, both `pyproject.toml`s (alembic dep; pytest pythonpath), new `tests/unit/test_models_metadata.py`; deps none. Test: `uv run pytest apps/api/tests/unit/test_models_metadata.py`. Harness: N/A (no DB/migration in 1a). Rollback: delete 1a files; revert 2 pyproject lines.
- **PR 1b** Migration+constraints: `alembic/versions/0001_identity_tables.py`, `tests/conftest.py`, `tests/integration/{test_migration,test_constraints}.py`, `uv.lock` (generated); deps PR 1a. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_migration.py apps/api/tests/integration/test_constraints.py` (10 passed). Harness: compose PG :55432; `alembic upgrade/downgrade/check`. Rollback: `downgrade base` drops 4 tables; delete 1b files.
- **PR 2a** Auth primitives: `src/raguard_api/{errors.py,config.py}`, `auth/{__init__,passwords,jwt}.py`, `tests/unit/{test_passwords,test_jwt}.py`, `.env.example`, `apps/api/pyproject.toml` (argon2-cffi), generated `uv.lock`; deps PR 1b. Test: `uv run pytest apps/api/tests/unit/test_passwords.py apps/api/tests/unit/test_jwt.py` (13 passed). Harness: N/A (unit-only gate — slice has no DB/HTTP integration boundary). Rollback: delete 2a files; revert pyproject line + `.env.example` block; `uv lock` regen; 2b/PR3/PR4 untouched.
- **PR 2b** Auth boundary/login: `auth/{dependencies,router}.py`, `tests/integration/test_login.py`; deps PR 2a. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_login.py` (7 passed). Harness: real PG :55432 via `migrated_db` + httpx ASGITransport; Set-Cookie `raguard_session` HttpOnly/SameSite=lax/Path=/api (+Secure in secure mode) asserted. Rollback: delete 2b files only; 2a already merged stays.
- **PR 3a** Authorization core: `src/raguard_api/authorization/{__init__,capabilities,scope,resolver}.py` (126) + `tests/unit/{test_capabilities,test_scope,test_resolver}.py` (246) = 372; deps PR 2b. Test: `uv run pytest apps/api/tests/unit/test_capabilities.py apps/api/tests/unit/test_scope.py apps/api/tests/unit/test_resolver.py` (17 passed). Harness: N/A (unit-only gate — no DB/HTTP integration boundary in slice). Rollback: delete `authorization/` + 3 unit files; PR 2a/2b stay.
- **PR 3b** Org route surface: `src/raguard_api/org/{__init__,router}.py` (182) + `tests/integration/test_org_routes.py` (~180, route-behavior subset split from 281-line `test_authorization.py`) = ~362; deps PR 3a. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_org_routes.py`. Harness: real PG :55432 via `migrated_db` + httpx ASGITransport minimal app. Rollback: delete `org/` + `test_org_routes.py`; 3a merged stays.
- **PR 3c** Authorization release gates: `tests/integration/test_authorization_release_gates.py` (~101, remaining split coverage; no new production route scope) = ~101; deps PR 3b. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_authorization_release_gates.py`. Harness: real PG :55432; PRD KPI 2 gates. Rollback: delete release-gates test file only; 3a/3b production stays.
- **PR 4a** Bootstrap ≤400 (381): `src/raguard_api/identity/bootstrap.py` (145) + `apps/api/raguard-bootstrap` (17, +x) + `tests/integration/test_bootstrap.py` (203) + `.env.example` delta (16: bootstrap vars +10, JWT placeholder 3+3 — placeholder owned by 4a, not 4d); deps PR 3c. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_bootstrap.py` → 13 passed. Harness: real PG :55432 via `migrated_db`; `uv run apps/api/raguard-bootstrap` CLI — first run exit 0 rows 1|1|2|1, rerun exit 0 unchanged, invalid env exit 2, stderr secret-free. Rollback: delete the 3 files; revert `.env.example` delta; 3c merged stays.
- **PR 4b** Release-gate relocation ≤400 (~338), delivery-only: `tests/integration/test_release_gates.py` = 4 gates moved verbatim from `test_authorization_release_gates.py` (~150) on the 3c minimal org-only harness (no `raguard_api.main` import — main lands in 4d) + delete old file (188); deps PR 4a. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_release_gates.py` → 4 passed. Harness: real PG :55432 via `migrated_db` + httpx ASGITransport minimal app (auth+org routers). Rollback: restore `test_authorization_release_gates.py` (188, content in cumulative mapping); delete `test_release_gates.py`; zero production edits.
- **PR 4c** Isolation boundary ≤400 (~199): 2 isolation gates in the independent split file `tests/integration/test_isolation_gates.py` (166, reserved in 4b.1 — boundary decision: split file preserved instead of appended to `test_release_gates.py`, equivalent boundary documented in 4c.3) + `tests/unit/test_security_boundary.py` (110); deps PR 4b. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_isolation_gates.py apps/api/tests/unit/test_security_boundary.py` → 9 passed (2+7); combined with release-gates file → 13 passed (4 carried + 2 new + 7 unit). Harness: minimal app for the gates (override seam kept); security-boundary unit layer N/A (no DB). Rollback: delete `test_isolation_gates.py` + `test_security_boundary.py`; 4b stays.
- **PR 4d** App factory + CI ≤400 (~91): `src/raguard_api/main.py` (24) + `.github/workflows/ci.yml` (+22) + NEW `tests/integration/test_app_factory.py` (~45 smoke — boundary adjustment: replaces the factory-harness coverage the current gate file has, keeps 4b/4c main-free, gives 4d an independent focused command; 0 coverage loss); deps PR 4c. Test: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_app_factory.py` → ~4 passed; full gate 93 passed. Harness: real PG :55432 + httpx ASGITransport on `create_app` — 401 envelope no-cookie, 404 unknown path; `alembic check` zero drift. Rollback: delete `main.py` + smoke test; revert `ci.yml`; gates/bootstrap untouched.

## Phase 1a: ORM Foundation (PR 1a)

- [x] 1a.1 RED `apps/api/tests/unit/test_models_metadata.py`: tables, unique constraints, composite FK/index columns, allowlist; no Alembic import
- [x] 1a.2 GREEN `apps/api/src/raguard_api/db.py`: Base + async engine/session factories
- [x] 1a.3 GREEN `apps/api/src/raguard_api/identity/models.py`: Tenant/User/Role/Membership + constraints + indexes; package `__init__.py`
- [x] 1a.4 GREEN `apps/api/alembic.ini` + `alembic/env.py` (models import, %(here)s) + `alembic/script.py.mako`
- [x] 1a.5 GREEN `apps/api/pyproject.toml` (alembic dep) + root `pyproject.toml` (pythonpath)
- [x] 1a.6 REFACTOR unit test stays green; no migration/fixture/integration yet

## Phase 1b: Migration + Integration Constraints (PR 1b)

- [x] 1b.1 RED `apps/api/tests/integration/test_migration.py`: up 4 tables + exact index columns; down drops only identity (sentinel)
- [x] 1b.2 RED `apps/api/tests/integration/test_constraints.py`: email/role-name uniqueness; allowlist; cross-tenant grant denied; one membership per user/tenant
- [x] 1b.3 GREEN `apps/api/alembic/versions/0001_identity_tables.py`: up 4 tables + 6 constraints + 2 indexes; safe down order
- [x] 1b.4 GREEN `apps/api/tests/conftest.py`: shared `migrated_db` fixture (disposable DB, alembic runner)
- [x] 1b.5 GREEN `uv.lock` regenerated (alembic 1.19.0 + mako + markupsafe; generated, not authored)
- [x] 1b.6 REFACTOR `alembic check` no-op; 10/10 integration green; model/migration drift check

## Phase 2a: Auth Primitives — Errors, Config, Passwords, JWT (PR 2a)

> Deps: PR 1b. Already implemented; delivery re-sliced, not reimplemented. Acceptance: `uv run pytest apps/api/tests/unit/test_passwords.py apps/api/tests/unit/test_jwt.py` → 13 passed, exit 0. Rollback: delete `src/raguard_api/{errors.py,config.py}` + `auth/{__init__,passwords,jwt}.py` + `tests/unit/{test_passwords,test_jwt}.py`; revert `apps/api/pyproject.toml` argon2 line + `.env.example` block; `uv lock` regen. Unit-only gate (no DB/HTTP slice boundary — N/A harness).

- [x] 2a.1 RED `apps/api/tests/unit/test_passwords.py`: verify ok; wrong pw fails; malformed hash → False (no raise/leak); salted unique `$argon2id$`; needs_rehash drift
- [x] 2a.2 RED `apps/api/tests/unit/test_jwt.py`: required 7 claims + fixed HS256 + no roles/capabilities/tenant claims; round-trip; expired; forged; tampered; malformed; wrong iss/aud; missing claim
- [x] 2a.3 GREEN `apps/api/src/raguard_api/errors.py`: envelope 400/401/403/404/409/503/500 + request_id; handlers map APIError/validation/500, no secrets
- [x] 2a.4 GREEN `apps/api/src/raguard_api/config.py` + `.env.example`: settings (jwt_secret min 32, 15-min expiry, cookie/origin vars); `apps/api/pyproject.toml` +argon2-cffi; `uv.lock` regenerated
- [x] 2a.5 GREEN `apps/api/src/raguard_api/auth/__init__.py` + `auth/passwords.py` (Argon2id + rehash) + `auth/jwt.py` (HS256, sub/tid DB-derived, iss/aud/iat/exp/jti)
- [x] 2a.6 REFACTOR ruff + format clean; unit suite green; no dependencies/router/login yet

## Phase 2b: Auth Boundary — Login Route + Verification Dependency (PR 2b)

> Deps: PR 2a. Already implemented; delivery re-sliced, not reimplemented. Acceptance: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_login.py` → 7 passed, exit 0. Harness: real PG :55432 via `migrated_db` fixture + httpx ASGITransport; login → Set-Cookie `raguard_session=…; HttpOnly; SameSite=lax; Path=/api` (+Secure in secure mode), token absent from body. Rollback: delete `auth/{dependencies,router}.py` + `tests/integration/test_login.py`; 2a files already merged stay.

- [x] 2b.1 RED `apps/api/tests/integration/test_login.py`: token+cookie attrs ×2 (Secure on/off); wrong pw vs unknown email byte-identical 401; client-supplied `X-Tenant-Id` ignored; foreign Origin → 403 no cookie; multi-membership → generic 401; invalid cookie → 401
- [x] 2b.2 GREEN `apps/api/src/raguard_api/auth/dependencies.py`: `get_token_claims` cookie-only, decode fixed HS256, missing/invalid → 401; tenant only from verified `tid`
- [x] 2b.3 GREEN `apps/api/src/raguard_api/auth/router.py`: `create_auth_router(settings, session_factory)` — `POST /api/auth/login`; Origin allowlist (403); canonical email; Argon2id verify; unambiguous membership; rehash-on-login; Secure HttpOnly cookie; no token in body
- [x] 2b.4 REFACTOR ASGITransport single event loop harness stable; ruff + format clean; no main wiring

## Phase 3a: Authorization Core — Capabilities, Scope, Resolver (PR 3a)

> Deps: PR 2b. Implemented and verified in worktree; delivery re-sliced, not reimplemented. Acceptance: `uv run pytest apps/api/tests/unit/test_capabilities.py apps/api/tests/unit/test_scope.py apps/api/tests/unit/test_resolver.py` → 17 passed, exit 0. Unit-only gate (no DB/HTTP slice boundary — N/A harness). Rollback: delete `authorization/` + 3 unit files; PR 2a/2b stay.

- [x] 3.1 RED `apps/api/tests/unit/test_capabilities.py`: admin all 5; member exactly corpus.view + chat.use; matrix ↔ DB CHECK allowlist; unknown role → no grants
- [x] 3.2 RED `apps/api/tests/unit/test_scope.py`: parameterized binds over Membership.tenant_id/Role.tenant_id; no tenant literal; missing capability → false
- [x] 3.3 RED `apps/api/tests/unit/test_resolver.py`: fresh per request; role change visible; no cache; compiled params == [sub, tid]; missing membership → 401
- [x] 3.5 GREEN `apps/api/src/raguard_api/authorization/capabilities.py` + `scope.py`: constants from models allowlist; frozen slots `AuthorizationScope` + `tenant_predicate` (bind-parameterized, never SQL strings)
- [x] 3.6 GREEN `apps/api/src/raguard_api/authorization/resolver.py`: stateless single resolve; fresh session per request; `create_scope_dependency`
- [x] 3a.6 REFACTOR frozen dataclass scope; module slimmed; ruff + format clean; 17/17 unit green

## Phase 3b: Org Route Surface (PR 3b)

> Deps: PR 3a. Implemented and verified in worktree; remaining work is delivery-only test-file split. Acceptance: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_org_routes.py` → green, exit 0. Harness: real PG :55432 via `migrated_db` + httpx ASGITransport minimal app (org router only, no PR 4 main wiring). Rollback: delete `org/` + `test_org_routes.py`; 3a merged stays.

- [x] 3.4 RED `apps/api/tests/integration/test_authorization.py` route-behavior subset: protected ops per route; envelope 400/401/403/404; client `X-Tenant-Id` ignored; role PATCH allowlist → 400
- [x] 3.7 GREEN `apps/api/src/raguard_api/org/__init__.py` + `org/router.py`: `create_org_router(session_factory)` — GET/PATCH users, roles, memberships; every route GetScope → require_capability; all queries scoped by scope.tenant_id; cross-tenant → neutral 404; no client tenant path/body/query/header
- [x] 3b.3 DELIVERY split: extract route-behavior subset → `apps/api/tests/integration/test_org_routes.py` (~180 lines, ≤200); rerun focused gate green; keep `test_authorization.py` until 3c split lands

## Phase 3c: Authorization Release Gates (PR 3c)

> Deps: PR 3b. Implemented and verified in worktree; remaining work is delivery-only test-file split. Acceptance: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_authorization_release_gates.py` → green, exit 0. Harness: real PG :55432; PRD KPI 2 release-gate scenarios. Rollback: delete `test_authorization_release_gates.py` only; 3a/3b production stays.

- [x] 3c.1 RED `apps/api/tests/integration/test_authorization.py` release-gate scenarios: cross-tenant read/mutation denied + DB row unchanged; cross-role escalation 403 + role row unchanged; client-tenant-override ignored; neutral 404 no existence disclosure
- [x] 3c.2 GREEN existing resolver/routes satisfy all gates; no new production route scope
- [x] 3c.3 DELIVERY split: extract remaining release-gate coverage → `apps/api/tests/integration/test_authorization_release_gates.py` (~101 lines, ≤200); delete original 281-line `test_authorization.py`; re-run full integration suite; 0 coverage discarded

## Phase 4: Bootstrap + Security + CI (PR 4) — implemented [x]; delivery re-sliced → 4a/4b/4c/4d

> Measured ~960 authored changed lines > 400-line gate → re-sliced into PR 4a/4b/4c/4d (no size:exception). Tasks below remain [x] (prior completion preserved); the delivery slices below carry the remaining work at PR creation. Implementation remains in the worktree.

- [x] 4.1 RED `apps/api/tests/integration/test_bootstrap.py`: idempotent rerun; existing data kept
- [x] 4.2 RED `apps/api/tests/integration/test_release_gates.py`: isolation suite — no untrusted-document influence; authz from verified identity/current role state only
- [x] 4.3 RED `apps/api/tests/unit/test_security_boundary.py`: authz only from verified identity/current role state
- [x] 4.4 GREEN `apps/api/src/raguard_api/identity/bootstrap.py` + `raguard-bootstrap`: env-validated, atomic, idempotent
- [x] 4.5 GREEN `apps/api/src/raguard_api/main.py`: wire routers + handlers
- [x] 4.6 GREEN `.github/workflows/ci.yml`: PostgreSQL 17 service; integration gate
- [x] 4.7 GREEN `.env.example`: bootstrap + JWT vars
- [x] 4.8 REFACTOR consolidate release gates

## Phase 4a: Bootstrap (PR 4a) — 381 measured ≤400

> Deps: PR 3c. Content implemented in worktree; slice verified at PR creation. Focused: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_bootstrap.py` → 13 passed, exit 0. Harness: real PG :55432 via `migrated_db`; `uv run apps/api/raguard-bootstrap` CLI smoke — first run exit 0 rows 1|1|2|1, rerun exit 0 unchanged (idempotent), invalid env exit 2, stderr secret-free. Rollback: delete `bootstrap.py` + `raguard-bootstrap` + `test_bootstrap.py`; revert `.env.example` delta; 3c merged stays.

- [x] 4a.1 VERIFY-RED `apps/api/tests/integration/test_bootstrap.py` (203, 13 cases): env validation generic messages; canonical normalization; atomic first-tenant/default-roles/admin; idempotent rerun; existing-data no-op; concurrent runs (advisory lock); CLI exit 0/0/2; logs exclude secrets — RED confirmed (ImportError bootstrap absent)
- [x] 4a.2 VERIFY-GREEN `src/raguard_api/identity/bootstrap.py` (145) + `apps/api/raguard-bootstrap` (17, +x) + `.env.example` bootstrap block (+10) + compliant JWT placeholder (3+3, ≥32 non-secret): env-only secrets, `pg_advisory_xact_lock`, atomic rollback, no-op without writes
- [x] 4a.3 VERIFY-REFACTOR `read_bootstrap_env` single source; generic error strings; lock key constant; focused 13 passed; CLI smoke green; no secret in stderr/caplog

## Phase 4b: Release-Gate Relocation (PR 4b) — ~338 measured ≤400, delivery-only

> Deps: PR 4a. Delivery-only relocation of existing coverage (3b/3c verbatim-move precedent); zero assertion changes, zero coverage loss, zero production edits. Focused: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_release_gates.py` → 4 passed, exit 0. Harness: real PG :55432 via `migrated_db` + httpx ASGITransport minimal app (auth+org routers; NO `raguard_api.main` import — factory re-locked in 4d smoke). Rollback: restore `test_authorization_release_gates.py` (188, content in cumulative mapping); delete `test_release_gates.py`.

- [x] 4b.1 DELIVERY split: deliver `test_release_gates.py` with the 4 verbatim 3c gates (cross-tenant read neutral 404; cross-tenant membership mutation denied + row unchanged; member escalation 403 + role row unchanged; client-supplied tenant ignored) on the minimal auth+org harness (no `raguard_api.main` import); 2 isolation gates reserved in `test_isolation_gates.py` (4c ownership)
- [x] 4b.2 DELIVERY delete `apps/api/tests/integration/test_authorization_release_gates.py` (188) — already absent (batch 8 consolidation); gates preserved verbatim; 0 coverage discarded
- [x] 4b.3 VERIFY focused 4 passed; AST-extracted gate bodies byte-identical vs consolidated baseline; full integration re-run green (43 passed, full gate 89 passed); no production diff

## Phase 4c: Isolation Boundary (PR 4c) — ~199 measured ≤400

> Deps: PR 4b. Content implemented in worktree; VERIFY-RED/GREEN/REFACTOR this batch (RED confirmed batch 8 — gates authored before main.py existed). Boundary decision (orchestrator-sanctioned): the 2 isolation gates stay in the independent, already-reserved `test_isolation_gates.py` split file instead of being appended to `test_release_gates.py` (4c.3 as planned); equivalent boundary documented — focused command covers both boundary files, 0 coverage loss, main-free harness preserved, factory wiring re-locked in 4d smoke. Focused: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_isolation_gates.py apps/api/tests/unit/test_security_boundary.py` → 9 passed (2 integration + 7 unit), exit 0; combined with `test_release_gates.py` → 13 passed (4 carried + 2 new + 7 unit). Harness: minimal app for the gates (`dependency_overrides[get_settings]` seam kept); `test_security_boundary.py` unit layer N/A (no DB boundary). Rollback: delete `test_isolation_gates.py` + `test_security_boundary.py`; 4b stays.

- [x] 4c.1 VERIFY-RED 2 new isolation gates (in `test_isolation_gates.py`, 166 with shared harness): injection-shaped capability tokens → member 403, admin 400 via allowlist, role row unchanged; extra document-like body fields ignored; same-token DB role upgrade → 200, downgrade → 403 — RED confirmed batch 8 (gates authored before main.py existed); GREEN re-verified this batch
- [x] 4c.2 VERIFY-GREEN `test_security_boundary.py` (110, 7 cases: TokenClaims rejects extra identity fields; frozen scope; no grant-source field; injection-shaped role names get no grants; scope == exact DB capability set) + existing resolver/routes satisfy both gates; no new production scope
- [x] 4c.3 REFACTOR reorg: boundary decision — preserve the independent `test_isolation_gates.py` split file (already planned/reserved in 4b.1; cleaner than appending) instead of appending the 2 gates to `test_release_gates.py`; harness stays minimal-app (no main import); focused 9 on boundary files / 13 combined passed; factory-wiring coverage re-locked in 4d smoke; 0 coverage loss

## Phase 4d: App Factory + CI (PR 4d) — ~91 measured ≤400

> Deps: PR 4c. Boundary adjustment: NEW `test_app_factory.py` smoke locks factory wiring (the current gate file's factory harness moves here; 4b/4c stay main-free) and gives 4d an independent focused command. JWT env placeholder owned by 4a (4a = 381 ≤ 400 — no shedding needed). Focused: `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_app_factory.py` → ~4 passed, exit 0. Harness: real PG :55432 + httpx ASGITransport on `create_app` — 401 envelope no-cookie, 404 unknown path; `alembic check` "No new upgrade operations detected". Rollback: delete `main.py` + `test_app_factory.py`; revert `ci.yml`; gates/bootstrap untouched.
> Delivered (batch 12): `test_app_factory.py` = 100 lines, 4 smoke tests; main.py 24→26 lines (+`dependency_overrides[get_settings]` seam — in-boundary fix: factory settings now reach the auth dependency `get_token_claims`, mirroring the 4b/4c harness seam; without it the no-cookie smoke got 500 pydantic ValidationError instead of 401); ci.yml unchanged (authored batch 8, verified structurally). Surface test enumerates routes via `original_router` (FastAPI 0.141.1 `_IncludedRouter` wrapper), not private route objects.

- [x] 4d.1 RED `apps/api/tests/integration/test_app_factory.py` (~45): no-cookie `/api/org/users` → 401 `authentication_failed` envelope; unknown path → 404; login route mounted — RED confirmed this batch: with main.py absent → `ModuleNotFoundError: No module named 'raguard_api.main'` at collection; RED also surfaced the missing settings seam (500 not 401)
- [x] 4d.2 GREEN `apps/api/src/raguard_api/main.py` (24): `create_app(*, settings, session_factory)` → `register_error_handlers` + auth router + org router; no logout, no new product scope; settings threaded via `dependency_overrides[get_settings]`
- [x] 4d.3 GREEN `.github/workflows/ci.yml` (+22): `postgres:17` service (55432→5432, pg_isready), job env mirrors compose/conftest contract, integration-gate step
- [x] 4d.4 REFACTOR full gate: `uv run pytest -m 'not e2e' && pnpm test` → 93 passed (89 + smoke); ruff + format + biome clean; `alembic check` zero drift

## Gate

- [x] `uv run pytest -m 'not e2e' && pnpm test`; ≤400 lines/PR (4a 381, 4b ~338, 4c ~199, 4d ~91); issue referenced; no PRD/ARCHITECTURE/DESIGN/ADR/compose/pr-check edits

## Remediation: Validation Secret Redaction (verify #4876 critical finding)

> Scoped correction for the failed independent verify #4876: `errors.py` serialized raw `RequestValidationError.errors()` including `input`, echoing a malformed supplied password object through the 400 envelope. Fix: allowlist-only validation details (loc/type/msg) — never raw `input`, `ctx`, or `url`. Strict TDD: RED 2 failed → GREEN 2 passed; full gate 95 passed (93 + 2 new). Independent re-verification passed with 25/25 scenarios compliant; Gate is complete.

- [x] R.1 RED `apps/api/tests/integration/test_login.py`: parametrized malformed password (object + list) → 400 envelope must not echo supplied value, keep only loc/type/msg, still yield field/type diagnostics — RED confirmed: `input` leaked in `details[0]` (2 failed)
- [x] R.2 GREEN `apps/api/src/raguard_api/errors.py`: `_sanitize_validation_details` allowlist keeps stable loc/type/msg; handler uses it — focused 9/9, full gate 95/95
- [x] R.3 REFACTOR ruff/format/biome/pnpm clean; no envelope shape change for existing consumers (only `error.code` asserted elsewhere)
