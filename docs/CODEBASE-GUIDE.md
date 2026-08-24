# CODEBASE-GUIDE.md

Navigational index for humans and agents working in this monorepo. Not a README. Not the architecture map — see [ARCHITECTURE.md](../ARCHITECTURE.md) for the system map and [PRD.md](../PRD.md) for product intent.

## Who this is for

Contributors and agents who need the right file without rereading the repo. If you are making a change, start here, then open the linked subsystem file or test file — do not hunt through `apps/` manually.

## 90-second mental model

raguard is a self-hosted, multi-tenant RAG over PDF/Markdown: `apps/api` (FastAPI) authenticates via thin JWT, resolves authorization fresh per request via a single `AuthorizationScope`, serves authorized ingestion, hybrid retrieval (FTS + pgvector HNSW fused with RRF), and bounded chat with `[n]` citation verification; `apps/worker` (Arq) does the async ingestion pipeline (parse, chunk, embed, atomic index). The one rule not to break is **retrieval-level authorization**: no chunk the caller is not authorized to see may reach generation, citations, or any response envelope — enforced in the retrieval queries before the prompt is built, with citation membership verification after.

> Detail lives in [docs/codebase/mental-model.md](codebase/mental-model.md). Keep this index scannable.

## Guide pages

| Page | Use when |
|------|----------|
| [Mental model](codebase/mental-model.md) | You need the invariants, primary flows, and subsystem boundaries first |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | You need the full system map, diagrams, decisions, and deployment topology |
| [PRD.md](../PRD.md) | You need product scope, acceptance criteria, and open decisions |
| [DESIGN.md](../DESIGN.md) | You need visual system tokens and UI direction |

## Recommended reading path

1. This page — get oriented in 90 seconds.
2. [docs/codebase/mental-model.md](codebase/mental-model.md) — invariants and primary runtime flows.
3. [ARCHITECTURE.md](../ARCHITECTURE.md) — diagrams, component tables, ADRs, failure modes.
4. The start-here file for your task:
   - Auth/RBAC: `apps/api/src/raguard_api/authorization/resolver.py` + `scope.py` + `auth/dependencies.py`
   - Retrieval: `apps/api/src/raguard_api/retrieval/service.py` + `fusion.py` + `queries.py`
   - Chat: `apps/api/src/raguard_api/chat/router.py` + `citations.py` + `prompts.py`
   - Documents/ingestion: `apps/api/src/raguard_api/documents/router.py` + `apps/worker/src/raguard_worker/jobs.py`
   - App wiring: `apps/api/src/raguard_api/main.py`

## Start-here paths (verified against `main` `707245a`)

| Area | Start-here file(s) | What you find |
|------|--------------------|---------------|
| API factory & error envelope | `apps/api/src/raguard_api/main.py`, `apps/api/src/raguard_api/errors.py` | Router wiring (`auth`, `org`, `documents`, `retrieval`, `chat`), consistent `{error: {code, message}}` |
| Auth & JWT | `apps/api/src/raguard_api/auth/jwt.py`, `apps/api/src/raguard_api/auth/router.py`, `apps/api/src/raguard_api/auth/dependencies.py`, `apps/api/src/raguard_api/auth/passwords.py` | `POST /api/auth/login`, HS256 thin JWT (sub/tid/iss/aud/iat/exp/jti), Argon2id passwords |
| Identity & bootstrap | `apps/api/src/raguard_api/identity/models.py`, `apps/api/src/raguard_api/identity/bootstrap.py`, `apps/api/raguard-bootstrap` | `tenants`, `users`, `roles`, `memberships`, first-tenant bootstrap `pg_advisory_xact_lock` |
| Authorization (single resolver) | `apps/api/src/raguard_api/authorization/resolver.py`, `apps/api/src/raguard_api/authorization/scope.py`, `apps/api/src/raguard_api/authorization/capabilities.py` | Fresh-per-request `AuthorizationResolver` → `AuthorizationScope` → `tenant_predicate`, capability matrix |
| Documents & storage/queue adapters | `apps/api/src/raguard_api/documents/router.py`, `apps/api/src/raguard_api/documents/models.py`, `apps/api/src/raguard_api/documents/storage.py`, `apps/api/src/raguard_api/documents/queue.py` | `POST /api/documents` + `GET /api/documents`, `S3ObjectStore`, `ArqJobQueue`, `DocumentStatus` |
| Retrieval (hybrid, RRF) | `apps/api/src/raguard_api/retrieval/router.py`, `apps/api/src/raguard_api/retrieval/service.py`, `apps/api/src/raguard_api/retrieval/fusion.py`, `apps/api/src/raguard_api/retrieval/queries.py`, `apps/api/src/raguard_api/retrieval/embeddings.py`, `apps/api/src/raguard_api/config.py` | `POST /api/search`, shared `retrieve_chunks`, `rrf_fusion(k=60)`, `build_keyword_query`/`build_semantic_query` with `halfvec(1536)` + `hnsw.ef_search` |
| Chat (bounded, citations) | `apps/api/src/raguard_api/chat/router.py`, `apps/api/src/raguard_api/chat/citations.py`, `apps/api/src/raguard_api/chat/prompts.py`, `apps/api/src/raguard_api/chat/contracts.py`, `apps/api/src/raguard_api/chat/providers/openai.py` | `POST /api/chat`, neutral `{answer: null, citations: []}`, static `SYSTEM_PROMPT` + `UNTRUSTED_SOURCES_*`, `verify_citations`, `OpenAICompleter` bounded retries |
| Org administration | `apps/api/src/raguard_api/org/router.py` | `GET/PATCH /api/org/*`, role/membership listing via tenant-scoped predicates |
| Worker pipeline | `apps/worker/src/raguard_worker/jobs.py`, `apps/worker/src/raguard_worker/parsers.py`, `apps/worker/src/raguard_worker/chunking.py`, `apps/worker/src/raguard_worker/embeddings.py`, `apps/worker/src/raguard_worker/cleanup.py`, `apps/worker/src/raguard_worker/settings.py` | Arq job `ingest_document`, bounded retries/cleanup, `WorkerSettings` bounds |
| DB & migrations | `apps/api/src/raguard_api/db.py`, `apps/api/alembic/versions/0001_identity_tables.py`, `apps/api/alembic/versions/0002_documents_chunks.py` | Async SQLAlchemy, `0001` identity tables, `0002` documents/chunks with HNSW + GIN indexes |
| Infra & config | `infra/compose.yaml`, `infra/Caddyfile`, `.env.example`, `apps/api/src/raguard_api/config.py` | Local stack (postgres pgvector, redis, minio, worker, caddy proxy profile), environment bounds |
| Specs & ADRs | `openspec/specs/`, `openspec/changes/archive/`, `docs/adr/` | Canonical specs (tenant-identity, jwt-authentication, authorization-rbac, documents, retrieval, chat), archive, ADRs 0001–0006 |
| Web | `apps/web/` | Scaffold only — Vite/React/TanStack Router/Query, Vitest, Playwright; no application source yet |

## Subsystem ownership

| Subsystem | Owner path | Boundary |
|-----------|------------|----------|
| `apps/api` — API monolith | `apps/api/src/raguard_api/` | Owns HTTP surface, authorization, retrieval, chat, document enqueue, org admin; stateless, tenant-scoped via `AuthorizationScope` |
| `apps/worker` — ingestion worker | `apps/worker/src/raguard_worker/` | Owns async parse/chunk/embed/index, bounded retries, cleanup; single coupling via PostgreSQL + Redis queue + S3 object store |
| `apps/web` — frontend | `apps/web/` | Owns UI shell when built; today tooling only; same-domain `/api` via Caddy |
| `infra` — deployment | `infra/compose.yaml`, `infra/Caddyfile` | Owns local topology and proxy; no app logic |
| `docs` — decisions & navigation | `docs/adr/`, `docs/CODEBASE-GUIDE.md`, `docs/codebase/` | Owns durable choices and navigational index, not product behavior |

## Primary flows (see mental model for diagrams)

| Flow | Entry → exit | Key files |
|------|-------------|-----------|
| Login | `POST /api/auth/login` → HttpOnly JWT cookie | `auth/router.py`, `auth/jwt.py`, `auth/passwords.py` |
| Document ingestion | `POST /api/documents` → S3 put → `pending` row → Arq enqueue → worker `ingest_document` → atomic chunk insert → `indexed`/`failed` | `documents/router.py`, `documents/storage.py`, `documents/queue.py`, `worker/jobs.py` |
| Hybrid retrieval | `POST /api/search` → fresh `AuthorizationScope` → `retrieve_chunks` (embed once, parallel FTS `simple` + vector `halfvec(1536)`/`hnsw.ef_search`, tenant predicate before ranking, RRF fusion, top-k bound) → `{results}` | `retrieval/router.py`, `retrieval/service.py`, `retrieval/queries.py`, `retrieval/fusion.py` |
| Bounded chat | `POST /api/chat` → fresh scope + `chat.use` gate → `retrieve_chunks` → neutral short-circuit if empty → `build_completion_prompt` (static prompt + delimited untrusted JSON) → `OpenAICompleter.complete` → `verify_citations` `[n]` → `{answer, citations}`; any provider/citation failure → 503 envelope | `chat/router.py`, `chat/prompts.py`, `chat/citations.py`, `chat/providers/openai.py`, `retrieval/service.py` |

## Test locations

| Layer | Command | Where |
|-------|---------|-------|
| Unit (no DB) | `uv run pytest -m "not e2e" --collect-only` lists 378 items | `apps/api/tests/unit/test_*.py` — capabilities, JWT, passwords, retrieval queries/fusion, chat prompts/citations/providers, document adapters/models |
| Integration (real PostgreSQL) | `uv run pytest -m "not e2e"` (249 passed, 127 skipped at `707245a`; `e2e` deselected) | `apps/api/tests/integration/test_*.py` — `test_retrieval_*`, `test_chat_routes.py`, `test_chat_release_gates.py`, `test_retrieval_isolation.py`, `test_isolation_gates.py`, `test_release_gates.py`, `test_documents_routes.py`, `test_org_routes.py`, `test_login.py`, `test_bootstrap.py`, etc. |
| E2E / provider smoke (credential-gated) | `uv run pytest -m e2e` (requires `OPENAI_API_KEY`) | `apps/api/tests/e2e/test_retrieval_provider.py`, `apps/api/tests/e2e/test_chat_e2e.py` |
| JS/TS | `pnpm test` | `apps/web/` — Vitest (`--passWithNoTests` when no test files) |
| Lint/format | `pnpm exec biome check .`, `uv run ruff check .`, `uv run ruff format --check .` | Repo-wide |
| Migration drift | `alembic -c apps/api/alembic.ini check` (wrapped by project checks) | `apps/api/alembic/` |
| Compose config | `docker compose -f infra/compose.yaml config` | `infra/` |

> Tests inject `FakeEmbedder`/`FakeCompleter` via router factories — non-e2e tests make zero provider network calls.

## Where to make common changes

| You want to… | Edit | Verify with |
|--------------|------|-------------|
| Change auth or token claims | `auth/jwt.py`, `auth/dependencies.py`, `authorization/resolver.py` | `uv run pytest -m "not e2e" -k "login or auth or app_factory"` |
| Change RBAC / capabilities | `authorization/capabilities.py`, `identity/models.py` (CHECK allowlist), `org/router.py`, `authorization/resolver.py` | `test_capabilities.py`, `test_org_routes.py`, `test_isolation_gates.py`, `test_release_gates.py` |
| Change retrieval ranking or fusion | `retrieval/queries.py`, `retrieval/fusion.py`, `retrieval/service.py`, `config.py` (bounds) | `test_retrieval_*`, `test_rrf_fusion.py`, `test_retrieval_service.py` |
| Change chat prompt or citation rules | `chat/prompts.py`, `chat/citations.py`, `chat/contracts.py`, `chat/providers/openai.py` | `test_chat_*`, `test_chat_release_gates.py` |
| Change document validation or enqueue | `documents/router.py`, `documents/models.py`, `documents/storage.py`, `documents/queue.py` | `test_documents_*` |
| Change worker pipeline / chunking | `worker/jobs.py`, `worker/chunking.py`, `worker/parsers.py`, `worker/embeddings.py` | `uv run pytest -m "not e2e"` + manual compose run |
| Add a new API route | `main.py` (wire), new `*/router.py` using `create_scope_dependency` resolver | `test_app_factory.py` + new `integration/test_*_routes.py` |
| Change DB schema | `identity/models.py` or `documents/models.py` + new `alembic/versions/*.py` | `test_migration.py`, `test_constraints.py` |
| Change infra topology | `infra/compose.yaml`, `infra/Caddyfile`, `.env.example` | `docker compose -f infra/compose.yaml config` |

## Existing references

| Doc | Role |
|-----|------|
| [README.md](../README.md) | First success — setup, run, validate |
| [PRD.md](../PRD.md) | Product intent, scope, invariants, acceptance |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | System map, flows, ADRs |
| [DESIGN.md](../DESIGN.md) | UI design direction (draft) |
| [docs/codebase/mental-model.md](codebase/mental-model.md) | Detailed mental model — invariants, flows, ownership |
| [docs/adr/](../adr/) | ADRs 0001–0006 |
| [openspec/specs/](../openspec/specs/) | Canonical specs |
| [openspec/changes/archive/](../openspec/changes/archive/) | SDD archive |

## Checklist

- [x] Every linked path exists on `main` at `707245a` (verified by `git ls-files` and `codegraph status`)
- [x] Detail page links back here (`docs/codebase/mental-model.md` → `docs/CODEBASE-GUIDE.md`)
- [x] No second index under `docs/` (`docs/CODEBASE-GUIDE.md` is the single index)
- [x] Guide stays concise — detailed explanation lives in `mental-model.md`

## Next step

Open [docs/codebase/mental-model.md](codebase/mental-model.md) for the full invariant and flow detail, then jump to the start-here file for your task.
