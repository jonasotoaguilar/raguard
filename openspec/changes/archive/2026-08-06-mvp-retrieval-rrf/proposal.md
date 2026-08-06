# Proposal: MVP Retrieval with RRF

## Intent

Complete retrieval over chunks already stored, embedded, and indexed. No API search surface exists, blocking chat, evaluation, and UI. This slice delivers permission-scoped hybrid retrieval without generation.

## Scope

### In Scope

- Add API-only `POST /api/search`, JWT/capability gated, with bounded query/top-k validation and the standard error envelope.
- Apply the verified tenant predicate in SQL before ranking for both retrieval signals.
- Query built-in PostgreSQL FTS (`tsvector`/`ts_rank`, `simple`) and pgvector cosine similarity (`halfvec(1536)`) in parallel; fuse candidates in the application with deterministic RRF (`k=60`).
- Embed queries through the same `text-embedding-3-small`, 1536-dimension contract used by ingestion; return chunk/document context and neutral empty results.
- Add fusion, query, contract, authorization, isolation, and route tests without provider calls.

### Out of Scope

- Chat, generation, citations, citation verification, evaluation harness, or web UI.
- `pg_textsearch`, a dedicated search engine, per-document grants, or PostgreSQL RLS.
- Migrations, worker changes, deletion semantics, and rate-limit policy decisions.

## Capabilities

### New Capabilities

- `retrieval`: Tenant-scoped API search using PostgreSQL FTS, pgvector, and application-layer RRF.

### Modified Capabilities

- None. Existing authentication, RBAC, tenant identity, and document-storage contracts are consumed unchanged.

## Approach

Create a modular `retrieval` API package with contracts, parameterized SQL builders, RRF, and a router factory. Reuse `AuthorizationScope`, the embedder/fake, error envelope, and chunk indexes; wire the router and request-path adapter into the API. Keep generated-vector and query `simple` FTS configurations aligned. Recommend `chat.use`; retain `corpus.view` as an explicit design-phase alternative.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/api/src/raguard_api/retrieval/` | New | Retrieval contracts, queries, fusion, and router |
| `apps/api/src/raguard_api/{main.py,config.py}` | Modified | Route wiring and retrieval/provider settings |
| `apps/api/tests/` | New | Unit, integration, and tenant-isolation coverage |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Provider latency/cost or model mismatch | Med | Adapter, bounds, same-model setting, fake tests, e2e-only provider calls |
| Cross-tenant leakage | High | Predicate before ranking in both queries plus release-gate isolation tests |
| Capability/default tuning remains unresolved | Med | Carry `chat.use` vs `corpus.view` and candidate/`ef_search` defaults into design/spec decisions |

## Rollback Plan

Remove the retrieval router, module, settings, and tests. No schema or worker rollback is required: this change writes no migration or ingestion code.

## Dependencies

- Existing indexed chunks, pgvector, authorization scope, and ingestion embedding contract; provider credentials are needed only for real end-to-end calls.

## Success Criteria

- [ ] `POST /api/search` returns only authorized tenant chunks, fused deterministically, or the same neutral empty result for no matches and an empty corpus.
- [ ] Unit and integration gates pass, including cross-tenant/capability isolation and same-model embedding coverage.
