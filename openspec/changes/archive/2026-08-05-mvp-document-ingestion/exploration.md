# Exploration: mvp-document-ingestion

> **Phase**: sdd-explore | **Date**: 2026-08-05 | **Author**: Jonathan Soto (jonasotoaguilar)
> **Status**: Ready for proposal — recommended next MVP slice, validated against repository evidence, archived change, and OpenSpec main specs.
> **Artifact store**: hybrid (OpenSpec + Engram, topic key `sdd/mvp-document-ingestion/explore`)

## Executive Summary

The `mvp-authz-foundation` change is archived (PASS, 15/15 requirements, 25/25 scenarios, 59/59 tasks) and its own deferred decisions point to the documents slice as the next owner. The PRD MVP acceptance criteria #1–#2 (upload PDF/Markdown; chunked/embedded/indexed with visible status) cannot be met by any other slice: retrieval depends on chunks, chat depends on retrieval, the web UI depends on chat. The smallest end-to-end next slice that builds on authz and advances toward authorized conversational RAG is **`mvp-document-ingestion`**: document upload (multipart, `documents.manage`-gated), tenant-prefixed S3 storage, arq job enqueue, and the worker pipeline (download → parse PDF/Markdown → chunk → embed via provider-neutral adapter → insert chunks + embeddings in one transaction → status `indexed`/`failed` + reason), plus document list/status endpoints. This is validated, not assumed: every dependency (arq, boto3, pgvector, redis, python-multipart, MinIO, S3 env vars) is already declared or provisioned, the capability `documents.manage` already exists unused, and ARCHITECTURE.md defines the exact runtime flow, failure modes, and consistency rules for this slice.

## Current State

- **Authz foundation complete (archived 2026-08-05)**: `apps/api/src/raguard_api/` implements `tenants`/`users`/`roles`/`memberships` (migration `0001_identity_tables.py`, 4 tables only), JWT auth, the single `AuthorizationResolver` (fresh per request), and `AuthorizationScope.tenant_predicate()` emitting parameterized SQL predicates. Capability matrix includes `documents.manage` (admin) and `corpus.view` (member) — both currently unused by any route.
- **No documents/chunks tables yet**: the ERD `documents` and `chunks` (with `embedding` vector + `search_vector` tsvector) tables do not exist in the schema.
- **Worker is a skeleton**: `apps/worker/pyproject.toml` declares arq, boto3, pgvector, psycopg, SQLAlchemy, pydantic-settings, redis — the full ingestion pipeline dependency set — but has zero source and empty test skeletons.
- **Infra provisioned**: compose has `pgvector/pgvector:0.8.6-pg17` (shm_size 1gb for HNSW builds), `redis:8.10.0-alpine` (password, appendonly), pinned MinIO (9000/9001, local-dev only); `.env.example` already defines `MINIO_ENDPOINT`, `S3_BUCKET`, `S3_REGION`, `REDIS_PASSWORD`, `OPENAI_API_KEY` (empty placeholder).
- **API Settings gap**: `raguard_api/config.py` covers JWT/cookies only; S3/Redis/embedding settings are not yet modeled.
- **Architecture authority**: ARCHITECTURE.md defines the ingestion runtime flow (upload → S3 tenant-prefixed key → PG row `pending` → enqueue document_id → worker claim → parse → chunk → embed → single-transaction chunk insert → status update), at-least-once delivery with idempotency by document_id, bounded retries with `failed`+reason, no DLQ, atomic rejection on storage failure, and chunk batches in one transaction per document (ADR-0003/0004/0005/0006).
- **Testing conventions**: pytest markers unit/integration/e2e, `addopts -m 'not e2e'`, strict TDD (`uv run pytest -m 'not e2e'`); 95 existing tests pass on the full gate.

## User / Product Problem

PRD §4: "As an admin, I want to upload PDF and Markdown files and have them indexed automatically so that new knowledge becomes searchable without manual effort." Acceptance criteria #1–#2: admin can upload PDF/Markdown documents; ingested documents are chunked, embedded, and indexed; ingestion progress and failures are visible. Non-goals keep the type allowlist to PDF/Markdown only. This slice is the first one that moves the product from identity substrate to actual content — the raw material every later capability (retrieval, chat, citations) consumes.

## Affected Areas

- `apps/api/src/raguard_api/` — new `documents` module: SQLAlchemy models for `documents` + `chunks` per ERD (chunks carries `embedding` vector and `search_vector` tsvector), migration `0002_documents_chunks.py` (composite `(tenant_id, …)` leading indexes, FK indexes; HNSW/GIN index creation timing is a design decision), upload router (`POST /api/documents`, multipart, `documents.manage` gate, size/type validation), document list/status router (`GET /api/documents` [+ `/{id}`], `corpus.view` gate), S3 storage client (boto3 `endpoint_url`, tenant-prefixed keys), arq enqueue, error envelope reuse.
- `apps/api/src/raguard_api/config.py` — extend `Settings` with S3 endpoint/bucket/region, Redis URL, embedding model config; worker needs its own settings module.
- `apps/api/pyproject.toml` — deps already sufficient (python-multipart, boto3, arq, redis, pgvector declared); no change expected unless the embedding client lives in the API (design decision — more likely worker-side).
- `apps/worker/` — **new source**: arq worker entrypoint, ingest job (download → parse → chunk → embed → index → status), PDF parser (pypdf/pdfminer decision at design), Markdown splitter, parameterized chunking, embedding adapter (provider-neutral per ADR-0005; OpenAI default; SDK dependency to add), settings, `apps/worker/tests/{unit,integration}/`.
- `infra/compose.yaml` — no change expected; MinIO/Redis already present (test-isolation helpers may be needed, design decision).
- `openspec/specs/` — future main spec domain `documents` (and possibly `chunks`) once this change archives.
- `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, ADRs — read-only here; owned by `design-architecture`/`design-ui` (explicit assignment only).

## Approaches

1. **Full ingestion pipeline end-to-end (upload → worker → chunks → status)** — the ERD/ADR-0004-shaped slice: documents + chunks tables, upload + list/status API, S3 storage, arq job, worker parse/chunk/embed/index, failure states.
   - Pros: delivers PRD acceptance criteria #1–#2 in one slice; smallest unit that is end-to-end and verifiable; consumes the unused `documents.manage` capability; unblocks retrieval (slice C) directly; matches the dependency chain and ADR-0004/0005/0006 mandates.
   - Cons: Largest slice so far (High effort per prior chain analysis) — 800-line session review budget likely forces chaining (e.g., upload+storage+list / worker pipeline / status+isolation gates); embedding provider introduces an external-call dependency that integration tests must not hit (adapter with fake/test double at design).
   - Effort: High

2. **Upload + document rows only (defer worker)** — API stores files, creates `pending` rows; worker pipeline in a later change.
   - Pros: Smaller first step; simpler tests.
   - Cons: Half-slice: nothing is chunked/embedded/indexed, so PRD criteria #1–#2 are not met and retrieval stays blocked; the worker infra (arq/redis/minio) is already provisioned and idle — deferring it adds a second change to reach the same end state; violates "smallest version that works end to end" (AGENTS.md).
   - Effort: Medium (but incomplete)

3. **Different slice order (retrieval/chat/eval/UI first)** — any slice C–F before ingestion.
   - Pros: None that survive the dependency chain.
   - Cons: Retrieval has no chunks to query; chat has no retrieval; eval has no corpus; UI has no API surface. Each would violate the chain the prior exploration validated and the authz archive's deferred decisions record.
   - Effort: n/a — blocked

## Recommendation

**`mvp-document-ingestion`** (approach 1) — the full end-to-end ingestion pipeline. Evidence, not convention: (1) the archived authz exploration's chain A→B→C→D→E→F was validated by implementation and remains the only ordering in which each slice is spec-worthy and testable; (2) PRD acceptance criteria #1–#2 are ingestion criteria; (3) the authz spec's deferred decisions name "documents" as the owner of per-document grants — the seam the next change extends; (4) every infrastructure and dependency prerequisite is already provisioned (MinIO, Redis, worker deps, S3 env vars, multipart); (5) the `documents.manage`/`corpus.view` capabilities exist and are waiting for their first consumers; (6) ARCHITECTURE.md already specifies the runtime flow, failure modes, retry/idempotency semantics, and transaction boundaries — the design phase fills in libraries (PDF parser, embedding SDK) and settings, not architecture.

Change name note: `mvp-document-ingestion` is preferred over the earlier chain's generic `mvp-ingestion` — it is precise (matches PRD language "ingestion of PDF/Markdown documents") and leaves room for future non-document ingestion naming.

## Scope Boundaries

### In Scope (this change)

- Migration + models: `documents` (tenant_id, name, storage_key, status, source_type, created_at) and `chunks` (document_id, tenant_id, position, content, embedding, search_vector) per ARCHITECTURE ERD; tenant-leading composite indexes; FKs.
- Upload: `POST /api/documents` multipart, `documents.manage` gated, PDF/Markdown allowlist, size limits (LLM10 unbounded-consumption discipline), atomic rejection on storage failure (no orphan rows), tenant-prefixed S3 keys via boto3 (`endpoint_url`).
- Queue: enqueue one arq job per document_id; at-least-once semantics; jobs carry ids, not payloads.
- Worker: claim → download → parse (PDF + Markdown) → chunk (parameterized defaults; tuning deferred to retrieval/eval per PRD §10) → embed (provider-neutral adapter, OpenAI default per ADR-0005) → insert chunks + embeddings in a single transaction → update document status `indexed`/`failed` + reason; bounded retries with backoff; idempotent re-ingestion by document_id (re-run replaces that document's chunks).
- API visibility: document list/status endpoints (`GET /api/documents` + `/{id}`) gated by `corpus.view`, enabling the MVP polling pattern (ARCHITECTURE realtime: polling).
- Security/release gates: cross-tenant isolation on upload/list/status routes (neutral 404, error envelope); adversarial document-shaped content cannot influence authorization (untrusted boundary, extends `test_security_boundary.py`); no authz decision derives from document content.
- Tests: unit + integration layers, strict TDD, `uv run pytest -m 'not e2e'`; worker unit tests for parse/chunk/index logic; integration tests against local compose (PG + Redis + MinIO, or MinIO-mocked — design decision).

### Out of Scope (explicit, later slices)

- Retrieval: FTS/vector queries, RRF fusion, `hnsw.ef_search` tuning (slice C; schema columns/indexes may be created here per ERD but queries are not).
- Chat, citations, citation verification, any LLM generation (slice D).
- Evaluation harness (slice E).
- Web UI (slice F) — API-level status visibility only.
- Per-document grants (deferred by authz spec; role/tenant-level model only).
- Document deletion semantics (open decision — working assumption "immediate purge" per ARCHITECTURE #2 is recorded, decision stays with its owner).
- Any change to PRD/ARCHITECTURE/DESIGN/ADRs.

## Assumptions (narrowest reversible) & Surfaced Decisions

| Item | Assumption | Reversibility |
|---|---|---|
| Embedding provider | OpenAI default via provider-neutral adapter (ADR-0005, PRD §10 working assumption); adapter interface mockable so integration tests never call the real API | Provider swap behind adapter |
| Deletion semantics | Immediate purge (ARCHITECTURE open decision #2 working assumption) — not implemented in this slice | Decided later without migration cost |
| Chunking parameters | Parameterized defaults at design; tuning against eval set is retrieval/eval's job (PRD §10) | Config-driven |
| PDF/Markdown parse libs | pypdf (or pdfminer.six) + a markdown splitter, chosen at design; poison documents → bounded retries → `failed` + reason, no DLQ (ADR-0004) | Library swap isolated in parser module |
| tsvector population | `chunks.search_vector` created per ERD; whether it is computed at insert or deferred to the retrieval slice is a design decision | Schema-complete either way |

## Risks

| Risk | Mitigation |
|---|---|
| Slice size vs 800-line review budget (auto-chain strategy) | sdd-tasks forecasts chaining; natural chain: (1) schema+upload+S3+list, (2) worker pipeline, (3) isolation gates/polish |
| Embedding provider call in tests (network, cost, key) | Adapter interface + fake/test double at design; real-call smoke gated to e2e marker |
| Poison/oversized documents (unbounded consumption, LLM04) | Size/type validation at upload; bounded retries → `failed` + reason; adversarial-document tests stay release-gated |
| S3/Redis outage handling | ARCHITECTURE failure modes: atomic upload rejection; worker retry with backoff; status remains visible |
| Open decisions surface (deletion, provider, chunking) | Recorded as assumptions above, not silently decided; owners unchanged |
| Stale `openspec/config.yaml` context block ("no application source") | Out of scope for this change; flag to orchestrator/init refresh |

## Ready for Proposal

**Yes.** The orchestrator should:
1. Confirm the change slug `mvp-document-ingestion` and proceed to `sdd-propose`.
2. Report surfaced open decisions (deletion semantics, embedding provider policy, chunking defaults) as assumptions owned by this slice.
3. Note that the slice consumes the existing `documents.manage`/`corpus.view` capabilities and the ERD `documents`/`chunks` tables, and that ADR-0004/0005/0006 are the design mandate.
