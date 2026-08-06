# Exploration: mvp-retrieval-rrf

> **Phase**: sdd-explore | **Date**: 2026-08-06 | **Author**: Jonathan Soto (jonasotoaguilar)
> **Status**: Ready for proposal — recommended next MVP slice, validated against repository evidence, archived changes, and OpenSpec main specs.
> **Artifact store**: hybrid (OpenSpec + Engram, topic key `sdd/mvp-retrieval-rrf/explore`)

## Executive Summary

The retrieval slice is the **API-layer completion of an already-built storage layer**. Migration `0002_documents_chunks.py` already created the `chunks` table with `embedding halfvec(1536)` (HNSW cosine index, `m=16, ef_construction=64`) and a persisted generated `search_vector tsvector` (`to_tsvector('simple'::regconfig, content)`, GIN index); the worker's `ingest_document` job already inserts complete chunk rows (content + embedding), so both retrieval signals are physically populated today. The composite `(tenant_id, document_id)` FK on `chunks` already prevents cross-tenant chunk attachment, and `AuthorizationScope.tenant_predicate()` already emits parameterized SQL predicates (ADR-0002 seam). What does not exist anywhere in the repository: any FTS query (`ts_rank`), any vector query (`<=>`), any RRF fusion, and any search route — the retrieval hot path from ARCHITECTURE.md is entirely unbuilt, and the web app is tooling-only. The smallest coherent end-to-end slice that completes retrieval **without touching chat/generation/citations** is **`mvp-retrieval-rrf`**: a retrieval endpoint (`POST /api/search`) that resolves the request scope, embeds the query with the same provider/model the worker uses (`text-embedding-3-small`, 1536 dims, ADR-0005), runs the two tenant-filtered SQL signals (FTS `ts_rank` and pgvector `<=>`) in parallel, fuses them with RRF (`k=60`, ~50 candidates per signal, configurable, per ADR-0003), and returns the top-k authorized chunks with document context. **Zero migration, zero worker changes** — the slice is a new `retrieval` API module plus settings and tests. The prerelease `pg_textsearch` extension is explicitly rejected (ADR-0003 Option B) and is not revived; built-in PostgreSQL FTS is the mandated keyword signal.

## Current State

- **Chunk storage is complete and retrieval-ready** (`apps/api/alembic/versions/0002_documents_chunks.py`, mirrored by `apps/api/src/raguard_api/documents/models.py`):
  - `chunks`: `id`, `tenant_id` (FK), `document_id` (FK), `position`, `content`, `embedding` (`HALFVEC(1536)`, NOT NULL), `search_vector` (generated `TSVECTOR` = `to_tsvector('simple'::regconfig, content)`, persisted, NOT NULL).
  - Indexes: `ix_chunks_embedding` HNSW (`halfvec_cosine_ops`, `WITH (m = 16, ef_construction = 64)`); `ix_chunks_search_vector` GIN; `ix_chunks_tenant_document` leading `(tenant_id, document_id)`; composite FK `(tenant_id, document_id)` → `documents(tenant_id, id)` prevents cross-tenant chunk attachment; `uq_chunks_document_position` uniqueness.
  - The worker (`apps/worker/src/raguard_worker/jobs.py`, `commit_indexed` → `Chunk(...)` inserts, lines ~371) writes content + embedding in a single transaction per document; `search_vector` is computed by the database, never written by code. Chunk rows are complete for retrieval.
- **Authorization seam is ready** (`apps/api/src/raguard_api/authorization/`): `AuthorizationScope` (frozen dataclass: `tenant_id`, `user_id`, `capabilities`) exposes `tenant_predicate(tenant_column)` — parameterized SQL equality, no literals — and `has_capability()`. The resolver is fresh per request (role changes apply immediately). Capability tokens include `chat.use` and `corpus.view`; `member` and `admin` both grant `chat.use` + `corpus.view`. Per-document grants remain a deferred later slice, so the authorized chunk set is the tenant-scoped chunk set.
- **No retrieval code exists**: `rg` over `apps/` finds `ts_rank`/`<=>`/RRF/similarity only in the schema/migration and authz docstrings, never in query code. Existing routes: `POST /api/documents`, `GET /api/documents`, `GET /api/documents/{document_id}` (documents router), `/api/login`, `/api/org/users|roles|memberships`. No search route, no chat route.
- **API conventions** (`apps/api/src/raguard_api/`): router-factory pattern `create_*_router(session_factory=..., ...)` wired in `main.py` `create_app`; `AuthorizationResolver` + `create_scope_dependency` produce the `GetScope` dependency; `require_capability(capability)` raises `AuthorizationError` (403); every query composes `scope.tenant_predicate(Table.tenant_id)`; error envelope `{error: {code, message, details?}}`; JWT via session cookie, tenant only from the verified `tid` claim; validation details allowlisted (`loc`/`type`/`msg` only).
- **Embedding contract**: `EMBEDDING_DIMENSION = 1536` (`documents/contracts.py`); worker uses OpenAI `text-embedding-3-small` (`apps/worker/src/raguard_worker/settings.py` `embedding_model`) via the `Embedder` protocol; `FakeEmbedder` (deterministic, dimension-exact) exists in `contracts.py` for tests. ADR-0005 requires the same model for data and queries — the retrieval endpoint must embed queries with the same model.
- **Settings gap**: `raguard_api/config.py` `Settings` has no retrieval parameters (candidates/k/top-k/`hnsw.ef_search`) and no embedding provider settings for the API request path.
- **Test conventions** (`openspec/config.yaml`): pytest markers `unit`/`integration`/`e2e`; per-test disposable migrated PostgreSQL databases (`apps/api/tests/conftest.py` `migrated_db`); strict TDD (`uv run pytest -m 'not e2e'`); isolation-gate precedent `apps/api/tests/integration/test_isolation_gates.py` (tenant A admin+member, tenant B carol; cross-tenant 403/neutral 404; capability gating; authz derives from current DB role state). 26 Python test files pass on the full gate.
- **Decided architecture (not open)**: ADR-0003 mandates built-in PostgreSQL FTS (`ts_rank`) + pgvector cosine, both tenant/role-filtered in SQL before ranking, fused with RRF at the application layer (`k=60`, ~50 candidates/signal, final top-k, configurable), queries executed in parallel; ADR-0002 mandates the predicates apply before fusion/generation; ARCHITECTURE.md "Indexing & Access Paths" confirms filtered HNSW + `tsvector` + tenant predicate with `hnsw.ef_search` tuning. `pg_textsearch` (prerelease, PG 17/18 only) was rejected at ADR-0003 and remains rejected.
- **Slice chain (from archived `mvp-authz-foundation` exploration)**: A `mvp-authz-foundation` ✅ archived → B `mvp-ingestion` ✅ archived (as `mvp-document-ingestion`) → **C `mvp-retrieval` (this change)** → D `mvp-chat-citations` → E `mvp-eval-harness` → F `mvp-web-ui`.

## User / Product Problem

PRD §4 acceptance criterion: "Retrieval combines semantic and keyword signals (RRF fusion); retrieval is scoped by the user's permissions at query time." KPI 3: top-10 precision ≥ 70% (threshold confirmed at harness setup). The problem *this slice* solves: documents are already uploaded, chunked, embedded, and indexed, but nothing can yet retrieve them — every later capability (chat, citations, evaluation, UI) consumes retrieval. This slice is the first one where the PRD authorization invariant ("chunks are filtered by the user's permissions **before** any generation") is exercised by real retrieval queries.

## Affected Areas

- `apps/api/src/raguard_api/retrieval/` — **new module** (mirrors the `documents` module structure): contracts (query/response models, fusion params), RRF fusion implementation, FTS + vector query builders, router factory `create_retrieval_router(session_factory=..., settings=..., embedder=...)`.
- `apps/api/src/raguard_api/main.py` — wire the retrieval router with a real `Embedder` adapter built from settings (lazy, so factory tests stay offline).
- `apps/api/src/raguard_api/config.py` — extend `Settings`: retrieval candidates, `rrf_k`, `top_k`, `hnsw_ef_search`, query length cap; embedding provider settings for the request path (`embedding_model` default `text-embedding-3-small`, `openai_api_key`, `embedding_batch_size`, `provider_timeout_seconds`).
- `apps/api/src/raguard_api/documents/contracts.py` — the `Embedder` protocol and `FakeEmbedder` are shared; a real OpenAI embedder for the API request path may live in `retrieval/` (or move the worker's `OpenAIEmbedder` to a shared seam — design decision; the worker's `OpenAIEmbedder` is the reference implementation and must stay the same model).
- `apps/api/tests/` — **new** `tests/unit/test_rrf_fusion.py` (fusion math, ties, duplicates), `tests/unit/test_retrieval_queries.py` (predicate composition, SQLAlchemy expression shape), `tests/unit/test_retrieval_router_helpers.py` (request validation, envelope); **new** `tests/integration/test_retrieval_routes.py` + `test_retrieval_isolation.py` (seeded chunks per tenant; cross-tenant chunks never returned; role gate 403; neutral empty results; `FakeEmbedder` used so no provider network calls).
- `apps/api/src/raguard_api/authorization/scope.py` — read-only consumer (predicates reused); no change expected.
- `apps/worker/` — **not affected** (no migration, no job changes).
- `infra/` — **not affected** (pgvector 0.8.6-pg17 already provisioned; compose already includes Redis/MinIO).
- `openspec/specs/` — future main spec domain `retrieval` once this change archives.
- `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, ADRs — read-only here (owned by `design-architecture`/`design-ui`; explicit assignment only). The `tsvector 'simple'` config decision is surfaced below for the design phase.

## Approaches

1. **API-layer retrieval slice (`mvp-retrieval-rrf`)** — new `retrieval` module + `POST /api/search`: scope-gated (`chat.use` recommendation; `corpus.view` alternative), query embedded via the `Embedder` adapter (same model as worker), two parallel SQL queries — FTS (`search_vector @@ plainto_tsquery('simple', :q)` ordered by `ts_rank`, tenant predicate) and vector (`embedding <=> :v::halfvec(1536)` ordered by cosine, tenant predicate, `SET LOCAL hnsw.ef_search`) — fused with RRF (`k=60`, ~50 candidates, top-k default 10, configurable), returning top-k chunks with document context. Zero migration; reuses `tenant_predicate()`, `FakeEmbedder`, existing error envelope and router conventions.
   - Pros: completes ARCHITECTURE's retrieval hot path exactly as ADR-0003 shapes it; smallest end-to-end slice that makes retrieval real and testable; consumes the unused `chat.use`/`corpus.view` capabilities; no schema risk (storage already shipped); unblocks chat (D), eval (E), UI (F) with no rework; both authorization invariants testable in SQL.
   - Cons: introduces an embedding provider call into the request path (latency/cost/key — mitigated by adapter + fake in tests, same model guarantee); largest new API surface since ingestion (Medium-High effort vs the 800-line budget — sdd-tasks forecasts chaining).
   - Effort: Medium–High
2. **Server-side fusion (SQL function doing both searches + RRF inside PostgreSQL)** — a SQL function/CTE that runs both signals and fuses ranks in the database.
   - Pros: fewer round trips; fusion logic in one place.
   - Cons: pgvector has no native RRF, so RRF is re-implemented awkwardly in SQL (rank arithmetic over window functions); authorization predicates still must be passed in; ARCHITECTURE/ADR-0003 explicitly decide "the two queries run in parallel and fuse client-side" at the application/query layer; harder to unit-test the fusion math; diverges from the decided architecture without a new ADR.
   - Effort: Medium (but architecture-divergent)
3. **Defer retrieval; build the evaluation harness (E) first** — harness gates retrieval quality, so build it first.
   - Pros: measurement exists before the endpoint ships.
   - Cons: the harness has nothing to evaluate — there is no retrieval endpoint and no query-time authorization surface to measure; PRD §10 leaves harness location open; the archived chain (A→B→C→D→E→F) and both archived explorations validated retrieval before eval; violates "smallest version that works end to end".
   - Effort: n/a — blocked
4. **Full chat slice (retrieval + generation + citations)** — chat orchestration, provider adapters, citation verification, conversations/messages.
   - Pros: delivers the PRD's headline feature.
   - Cons: explicitly out of the task's scope boundary ("do not expand into chat/generation/citations beyond required retrieval"); requires retrieval to exist first (it does not); largest possible slice, guaranteed to exceed the 800-line budget; conflates three independently verifiable capabilities.
   - Effort: High (and out of scope)

## Recommendation

**Approach 1 — the API-layer retrieval slice `mvp-retrieval-rrf`.** Evidence, not convention: (1) the storage layer (migration 0002) and the authz seam (`tenant_predicate`) that ADR-0002/0003 assumed are already shipped and archived — the slice is pure API completion with zero migration risk; (2) ADR-0003's action items #1–#2 (implement the two parallel queries with tenant/role predicates and application-layer RRF, parameterized candidates/k/top-k) are exactly this slice; (3) `chat.use`/`corpus.view` capabilities exist unused, waiting for their first consumer; (4) every integration-test prerequisite (per-test migrated PG with vector+GIN indexes, isolation-gate seeding pattern, `FakeEmbedder`) is already established; (5) chat (D), eval (E), and UI (F) all consume retrieval, so this is the highest-leverage next slice. Endpoint shape: `POST /api/search` (a retrieval-only surface distinct from the future chat endpoint; matches DESIGN contract points where "chat (answer + citations)" is a separate endpoint). Capability gate: require `chat.use` (retrieval exists to feed chat; corpus browsing stays `corpus.view` on the documents routes) — flagged as a design decision, alternative `corpus.view`.

## Scope Boundaries

### In Scope (this change)

- `retrieval` API module: request/response contracts, RRF fusion (`k=60`, ~50 candidates per signal, top-k default 10 — all configurable), FTS query (`search_vector @@ plainto_tsquery('simple', :q)`, `ORDER BY ts_rank(...)`, tenant predicate) and vector query (`embedding <=> :v::halfvec(1536)`, `ORDER BY ... LIMIT`, tenant predicate, `hnsw.ef_search`) built as parameterized SQLAlchemy expressions executed in parallel.
- `POST /api/search`: JWT-scoped, capability-gated, tenant resolved only from the verified `tid` claim; query-length and top-k bounds (LLM10 unbounded-consumption discipline); response = fused top-k chunks (chunk id, document id, position, content, document name, per-signal rank, fused score) via the standard error envelope.
- Settings: retrieval parameters + request-path embedding provider (same model as worker: `text-embedding-3-small`, 1536 dims).
- Tests: unit (fusion math, query builder shape, contract validation) + integration (seeded multi-tenant corpus; cross-tenant chunks never returned; role gate 403; neutral empty results for empty corpus vs no match; no provider network calls — `FakeEmbedder`); strict TDD, `uv run pytest -m 'not e2e'`.
- Security/release gates extended: cross-tenant retrieval isolation and role-gated retrieval as first-class scenarios (extends the isolation-gate pattern); no authz decision derives from query or chunk content (untrusted boundary, LLM01/LLM08).

### Out of Scope (explicit, later slices)

- Chat, generation, citations, citation verification, `conversations`/`messages` (slice D).
- Evaluation harness (slice E) and web UI (slice F).
- Per-document grants (deferred by the authz spec; tenant + role-capability model only).
- PostgreSQL RLS backstop (ARCHITECTURE open decision #6), document deletion semantics (#2), rate-limit values (#7).
- `pg_textsearch`/BM25 extension (rejected at ADR-0003 — not revived), any dedicated search engine.
- Any change to `PRD.md`/`ARCHITECTURE.md`/`DESIGN.md`/ADRs, and any schema migration (none needed).

## Assumptions (narrowest reversible) & Surfaced Decisions

| Item | Assumption / recommendation | Reversibility |
|---|---|---|
| FTS text config | `search_vector` is generated with `to_tsvector('simple'::regconfig, content)`; retrieval queries MUST use the same `'simple'` config (`plainto_tsquery('simple', ...)`) so index and query agree. Switching to `'english'` (stemming) would require a migration that alters the generated column — surfaced as a design-phase decision, default keep `'simple'` (language-neutral) | Config change later = migration; low cost, decided at design |
| Query embedding | API embeds the query with the same provider/model as the worker (`text-embedding-3-small`, 1536 dims) per ADR-0005; `FakeEmbedder` in all non-e2e tests; real provider calls gated to e2e | Provider swap behind adapter |
| HNSW + tenant filter | Tenant predicate is selective; HNSW is unfiltered. At MVP volume the composite `(tenant_id, document_id)` index and default scan suffice; if filtered recall/latency regresses, tune `hnsw.ef_search` and evaluate `hnsw.iterative_scan` against the eval set (ADR-0003 action item #2 surface) | Config/query-time only |
| Capability gate | `chat.use` for `POST /api/search` (retrieval feeds chat; member+admin both hold it); `corpus.view` alternative if the corpus-search surface is preferred | One dependency-line change |
| Endpoint contract | `POST /api/search` (body `{query}`) is the retrieval entry point; the future chat endpoint (`POST /api/chat`) composes it | Renamable before D; contract pinned by design/spec |
| Fusion identity | A chunk appearing in both signals sums its RRF contributions; ties broken deterministically (`score desc, id asc`) for stable ordering | Internal to fusion; tested |

## Risks

| Risk | Mitigation |
|---|---|
| Request-path embedding latency/cost/network (LLM10) | `Embedder` adapter + `FakeEmbedder` in tests; real-call smoke gated to e2e; query/limit bounds; same-model contract with the worker prevents silent mismatches |
| FTS/vector index disagreement after a config change | Queries pin the same `'simple'` regconfig as the generated column; config change surfaced as a migration decision, never silently mixed |
| Cross-tenant leakage through either signal | Both queries carry `scope.tenant_predicate()` before ranking (ADR-0002); isolation tests seed chunks in two tenants and assert zero leakage; composite FK backstops writes |
| Slice size vs 800-line review budget (`auto-chain`) | sdd-tasks forecasts chaining; natural chain: (1) fusion + query builders + settings, (2) endpoint + wiring, (3) isolation/security gates + polish |
| RRF quality below PRD draft target (≥ 70% top-10 precision) | Parameters (candidates, k, top-k, ef_search) are configurable; eval harness (E) gates tuning; ADR-0003 mitigation ladder (rerank, then reassess BM25) applies |
| Empty/neutral results leaking existence | Empty corpus vs no-match responses are identical and neutral (DESIGN heuristic #11); error envelope reused; no chunk id enumeration endpoint |

## Ready for Proposal

**Yes.** The orchestrator should:
1. Confirm the change slug `mvp-retrieval-rrf` and proceed to `sdd-propose`.
2. Report that this slice needs **no migration and no worker change** — it completes the already-shipped storage layer with the API retrieval path.
3. Surface the design decisions owned by this slice: `'simple'` FTS config (default, keep), capability gate `chat.use` vs `corpus.view`, endpoint `POST /api/search` contract, and `hnsw.ef_search`/candidate defaults (ADR-0003 action items).
4. Note the slice consumes `AuthorizationScope.tenant_predicate()` (ADR-0002 seam) and the `Embedder`/`FakeEmbedder` contracts, and that ADR-0003 is the design mandate with `pg_textsearch` explicitly excluded.
