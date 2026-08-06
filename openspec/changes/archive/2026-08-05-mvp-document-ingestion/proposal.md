# Proposal: MVP Document Ingestion

## Intent

Build a content-bearing MVP slice: authorized PDF/Markdown upload, asynchronous indexing, and status. This satisfies PRD acceptance criteria #1–#2 while preserving tenant authorization and treating document content as untrusted.

## Scope

### In Scope
- Add tenant-scoped `documents`/`chunks` models and migration with embeddings, search vectors, FKs, and tenant-leading indexes.
- Implement `POST /api/documents`: `documents.manage`, PDF/Markdown and size validation, tenant-prefixed S3 storage, document-ID enqueueing, and storage-failure rejection.
- Implement the worker: parse, parameterized chunk, provider-neutral embedding, transactional chunk replacement, bounded retries, and `indexed`/`failed` reasons.
- Implement `GET /api/documents` and `/{id}`: `corpus.view`, status polling, neutral errors, and tenant isolation.
- Add unit/integration tests for reprocessing, failures, isolation, and adversarial document content.

### Out of Scope
- Retrieval/RRF, chat/citations, evaluation, web UI, and per-document grants.
- Document deletion semantics.
- Product commitments to an embedding provider or tuned chunking values; both remain reversible.

## Capabilities

### New Capabilities
- `documents`: Tenant-scoped upload, queued parsing/chunking/embedding/indexing, and status visibility.

### Modified Capabilities
- None. Existing `authorization-rbac`, `jwt-authentication`, and `tenant-identity` requirements are reused; routes consume the existing resolver and capabilities.

## Approach

Use the modular-monolith API and Arq worker from ADR-0001/0004. Store bytes through the S3 adapter, persist a pending row, then enqueue only the document ID. The worker idempotently replaces chunks and commits chunks, embeddings, and final status atomically. Keep provider calls fakeable; derive authorization only from verified identity.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/api/src/raguard_api/`, `apps/api/alembic/versions/0002_documents_chunks.py` | New/Modified | API, models, migration, storage, queue. |
| `apps/worker/` | New | Arq job, parsers, chunker, embedding adapter. |
| `apps/api/tests/`, `apps/worker/tests/` | New/Modified | Unit, integration, failure, isolation tests. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Poison/oversized files or provider outage | Med | Bounds, bounded retries, visible reasons, fake providers in non-e2e tests. |
| Cross-tenant leakage | High | Fresh authz, parameterized tenant predicates, neutral errors, adversarial-content tests. |
| Review size exceeds the 400-line PR gate | Med | Auto-chain independently verifiable slices within the 800-line session budget. |

## Rollback Plan

Stop the worker, revert ingestion code and migration `0002`, and remove release-created tenant-prefixed objects. Leave identity/authz migration `0001` untouched.

## Dependencies

Existing PostgreSQL/pgvector, Redis/Arq, MinIO/S3, multipart, and boto3; design selects parser and embedding SDK implementations.

## Success Criteria

- [ ] Authorized admins upload valid PDF/Markdown and observe `pending` → `indexed`; invalid/oversized files are rejected.
- [ ] Reprocessing replaces current chunks without duplicates; bounded retries end in `failed` with a reason.
- [ ] Isolation tests show zero cross-tenant/cross-role exposure and no content-derived authorization.
- [ ] `uv run pytest -m 'not e2e' && pnpm test` passes for the implemented slice.
