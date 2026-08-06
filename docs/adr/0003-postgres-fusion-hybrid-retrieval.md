# ADR-0003: PostgreSQL FTS + pgvector Hybrid Retrieval Fused with RRF

## Status

Accepted (user-approved; target design for a greenfield repository — no implementation exists yet)

## Date

2026-08-04

## Deciders

Jonathan Soto (jonasotoaguilar)

## Context

Retrieval must combine semantic (embedding) and keyword (exact term) signals — PRD: "retrieval combines semantic and keyword signals (RRF fusion)" — to widen recall and avoid single-signal failure. The retrieval results must be filtered by tenant and role before generation (ADR-0002). Constraints: no separate search engine in the stack; the store is PostgreSQL + pgvector; pgvector provides vector search but has no native RRF (fusion must happen in application/query code); the RRF weights/candidates are explicitly a tuning surface against the evaluation set (PRD open decision).

## Decision

Use **PostgreSQL built-in full-text search (`tsvector` + GIN, `ts_rank`) as the keyword signal and pgvector (HNSW, cosine distance) as the semantic signal**, both stored on the `chunks` table (`search_vector` and `embedding` columns), both queried **in parallel** from the API, and **fused at the application layer with Reciprocal Rank Fusion** (`k = 60`, ~50 candidates per signal, configurable; final top-k). Both queries carry the tenant/role authorization predicates (ADR-0002).

Pinned `pgvector/pgvector` image; pgvector 0.8.x with HNSW (`halfvec_cosine_ops`); the exact extension/patch level is verified at setup time and the pinned image is authoritative.

## Consequences

### Positive

- One database holds both signals and the authorization joins — no separate search engine to sync, secure, or authz-filter.
- RRF is simple, deterministic, and tunable (candidates, k, top-k) against the evaluation set.
- Parallel execution keeps fusion latency near the slower single signal.
- The same SQL predicates enforce authorization on both signals uniformly.

### Negative

- PostgreSQL built-in FTS ranking (`ts_rank`) is weaker than true BM25 on some corpora; acceptable at MVP scale, measurable via the evaluation harness.
- RRF is rank-based (no score calibration); fine for the MVP, and weights are a tuning surface.
- HNSW/GIN index maintenance costs are paid on every chunk write; batched per-document transactions in the worker mitigate this.

### Neutral

- Embedding dimension and distance metric are pinned by the embedding adapter (must stay consistent: same model for data and queries — an adapter contract in ADR-0005).

## Options Considered

### Option A: Dedicated search engine (e.g., OpenSearch, Meilisearch, Elasticsearch)
| Dimension | Assessment |
|-----------|------------|
| Complexity | High (second store, sync pipeline, authz duplication) |
| Cost | High (memory-heavy services) |
| Scalability | Excellent |
| Team familiarity | Medium |
| Operational overhead | High |

**Pros:** best-in-class ranking, native hybrid/BM25.
**Cons:** a second source of truth that must mirror PostgreSQL and re-implement tenant filtering — directly increases the surface where the authorization invariant can break.

### Option B: `pg_textsearch` (BM25 extension) + pgvector
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cost | Low |
| Scalability | Good |
| Team familiarity | Low (new extension) |
| Operational overhead | Medium (extension lifecycle, compatibility) |

**Pros:** true BM25 ranking inside PostgreSQL, one store.
**Cons:** the extension is **prerelease** and currently targets PostgreSQL 17/18 — not production-appropriate for the MVP; revisit when it stabilizes.

### Option C: PostgreSQL built-in FTS + pgvector, RRF at application layer (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low–Medium |
| Cost | Low |
| Scalability | Good for MVP corpus sizes; read replicas later |
| Team familiarity | High (standard PostgreSQL features) |
| Operational overhead | Low |

**Pros:** one store, standard features, authorization in SQL, tunable fusion, no prerelease dependencies.
**Cons:** FTS ranking not BM25-grade; fusion code owned by us.

## Trade-off Analysis

Option A trades away the single-store simplicity that keeps authorization enforceable. Option B would give the best ranking inside one store, but depends on a prerelease extension on unsupported PostgreSQL majors — a version-drift risk the project explicitly wants to avoid (lockfiles/pinned images authoritative). Option C uses only stable, well-understood PostgreSQL features, keeps authorization in SQL, and exposes the exact tuning knobs (candidates, k, weights) that the PRD wants tuned against the evaluation set. If retrieval precision misses targets, the mitigation ladder is: tune candidates/weights → cross-encoder reranking → reassess pg_textsearch.

## Action Items

1. [ ] Implement the two parallel queries with tenant/role predicates and application-layer RRF (`k=60`, 50 candidates, top-10 default) at retrieval build.
2. [ ] Parameterize candidates, k, and top-k; wire them to evaluation-harness configuration.
3. [ ] Gate precision against the PRD draft target (≥ 70% top-10 precision, confirm at harness setup).
4. [ ] If precision misses the target, evaluate cross-encoder reranking or BM25 options and record the outcome.

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Data Architecture (Indexing & Access Paths), Key Decisions
- [PRD.md](../PRD.md) — MVP scope (RRF fusion), Risks (retrieval quality), Open Decisions (RRF weights)
- Local reference skill (implementation detail): `.agents/skills/postgres-hybrid-text-search/` (RRF query pattern, k=60)
- Related ADRs: [ADR-0002](0002-retrieval-level-authorization.md), [ADR-0005](0005-provider-neutral-model-adapters.md)
