# Retrieval Specification

## Purpose

Hybrid retrieval: `POST /api/search` fuses FTS and pgvector with deterministic RRF, authorized before ranking, no generation.

## Requirements

### Requirement: Bounded search request

`POST /api/search` MUST accept JSON: non-empty `query`, optional `top_k`. Empty, whitespace-only, or oversized queries and out-of-bounds `top_k` MUST be rejected (400). `top_k` MUST default to 10 and cap at a configured maximum. Query content MUST NOT affect authorization.

#### Scenario: Valid request is processed

- GIVEN an authorized caller with a valid query
- WHEN the search is submitted
- THEN at most `top_k` ranked entries return

#### Scenario: Invalid query or top-k rejected

- GIVEN an empty/oversized query or over-max `top_k`
- WHEN the request is submitted
- THEN it fails (400) with no retrieval runs

### Requirement: Authorization before ranking

Both signals MUST apply the tenant predicate before ranking. The route MUST require a tenant-scoped capability — unresolved `chat.use` vs `corpus.view`; `member`/`admin` hold both. Tenant MUST resolve only from the verified token; missing capability MUST yield 403; cross-tenant chunks MUST never be returned or disclosed.

#### Scenario: Only authorized tenant chunks return

- GIVEN a tenant A member; chunks exist in tenants A and B
- WHEN the member searches
- THEN every returned chunk belongs to tenant A

#### Scenario: Missing capability denied

- GIVEN a caller without the retrieval capability
- WHEN a search is submitted
- THEN it fails with the error envelope (403) and no data

#### Scenario: Cross-tenant isolation (release gate)

- GIVEN a tenant A member searching terms matching only tenant B chunks
- WHEN the search completes
- THEN no tenant B chunk appears and no existence is disclosed

### Requirement: Deterministic hybrid fusion

Both signals MUST run in parallel, tenant-filtered — keyword FTS (`simple` config, `ts_rank`) and semantic (cosine, `halfvec(1536)`) — fused with RRF (k 60, candidates 50, configurable); chunks in both signals MUST sum contributions. Ordering MUST be deterministic: fused score desc, chunk id asc.

#### Scenario: Dual-signal chunk accumulates contributions

- GIVEN a chunk ranked #1 by keyword and #3 by semantic, k=60
- WHEN fusion runs
- THEN its fused score is 1/61 + 1/63 and it outranks single-signal chunks at equal ranks

#### Scenario: Deterministic tie ordering

- GIVEN two chunks with equal fused scores
- WHEN the fused list is produced
- THEN they appear in ascending chunk id order and repeated runs match

### Requirement: Same-model query embedding

Queries MUST be embedded per the ingestion contract (`text-embedding-3-small`, 1536 dims, configurable) and bind against `halfvec(1536)`. Tests MUST inject a dimension-exact fake embedder.

#### Scenario: Query binds against stored embeddings

- GIVEN stored embeddings as `halfvec(1536)`
- WHEN a query embedding is produced
- THEN it has exactly 1536 dimensions and binds cleanly

### Requirement: Neutral empty results and safe errors

An empty corpus and a no-match query MUST return the identical neutral empty result. Provider failures MUST fail via the error envelope with no partial results or existence disclosure.

#### Scenario: No-match and empty corpus are identical

- GIVEN an empty corpus or no matching chunks
- WHEN a search completes
- THEN both return the identical neutral empty result

#### Scenario: Provider failure is a safe error

- GIVEN the embedding provider fails
- WHEN a search is submitted
- THEN it fails via the error envelope with no partial results

### Requirement: No provider calls in ordinary tests

Non-e2e tests MUST run on the fake embedder with zero provider calls; real calls MUST be e2e-only.

#### Scenario: Non-e2e suite runs offline

- GIVEN the fake embedder injected into the retrieval pipeline
- WHEN the non-e2e suite runs
- THEN no embedding-provider network calls occur and assertions pass

## Out of Scope

Chat, generation, citations, eval harness, web UI, `pg_textsearch`/BM25, dedicated engines, per-document grants, RLS, migrations, worker changes, rate-limit policy. Tuning defaults and the capability token (`chat.use` vs `corpus.view`) are unresolved design inputs.
