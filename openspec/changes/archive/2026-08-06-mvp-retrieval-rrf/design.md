# Design: MVP Retrieval with RRF

## Technical Approach

Add a retrieval package behind `POST /api/search`, reusing the existing router factory, fresh `AuthorizationScope`, shared `Embedder` protocol, and error handlers. Embed once, run tenant-filtered PostgreSQL FTS and pgvector searches concurrently in independent sessions, then fuse ranks in Python. This implements ADR-0002/0003/0005 and the retrieval spec without schema or worker behavior changes.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| `chat.use` vs `corpus.view` | Search executes the future chat retrieval path and incurs provider cost; corpus viewing remains document metadata access. | Require `chat.use`; tenant and capabilities still come only from verified JWT/current DB role state. |
| API-local query embedder vs moving worker code | Moving the worker adapter expands this slice; API-local code risks drift. | Add `retrieval/embeddings.py` behind the shared `Embedder`; both processes read `EMBEDDING_MODEL`, default `text-embedding-3-small`, and reject vectors not exactly 1536 dimensions. |
| Shared vs independent `AsyncSession` | SQLAlchemy forbids one `AsyncSession` across concurrent tasks. | Each signal opens its own session/transaction; `asyncio.gather` joins them. Embedding completes before DB transactions. |
| Tunable vs hard-coded retrieval | Bounds prevent expensive requests while evaluation can tune quality. | Defaults/bounds: `rrf_k=60` (1–1000), candidates/signal `50` (1–200), `top_k=10` (request 1–configured max 50), `hnsw.ef_search=100` (1–1000 and >= candidates), `semantic_max_distance=0.5` (`RETRIEVAL_SEMANTIC_MAX_DISTANCE`, pgvector cosine distance in `(0, 2]`), trimmed query 1–2000 characters (configured cap ≤10,000). Startup rejects inconsistent settings. |
| Partial degradation vs atomic search | Returning one signal leaks dependency state and changes ranking semantics. | Any embedding/query failure returns the standard generic 503 envelope; never return partial candidates. |

## Data Flow

```mermaid
sequenceDiagram
  Client->>Router: POST /api/search {query, top_k?}
  Router->>AuthZ: verified claims -> fresh scope; require chat.use
  Router->>Embedder: embed trimmed query
  par independent session
    Router->>PostgreSQL: tenant-filtered FTS
  and independent transaction
    Router->>PostgreSQL: SET LOCAL ef_search + tenant-filtered cosine search
  end
  Router->>Fusion: deterministic RRF
  Router-->>Client: {results: [...]} or safe error
```

## File Changes

| File | Action | Description |
|---|---|---|
| `apps/api/src/raguard_api/retrieval/{__init__,contracts,embeddings,queries,fusion,router}.py` | Create | Contracts, provider adapter, parameterized searches, RRF, router factory. |
| `apps/api/src/raguard_api/config.py` | Modify | Add bounded retrieval/provider settings and cross-field validation. |
| `apps/api/src/raguard_api/main.py` | Modify | Lazily construct the embedder and include the retrieval router. |
| `apps/api/pyproject.toml`, `uv.lock` | Modify | Make the existing OpenAI SDK a direct API dependency and lock it. |
| `apps/api/tests/unit/test_{rrf_fusion,retrieval_queries}.py` | Create | Fusion math/ties and compiled expression/predicate tests. |
| `apps/api/tests/integration/test_retrieval_{routes,isolation}.py` | Create | HTTP contract, failures, permissions, and cross-tenant release gate. |
| `apps/api/tests/e2e/test_retrieval_provider.py` | Create | Credential-gated real-provider dimension smoke only. |

## Interfaces / Contracts

Request: `{"query": str, "top_k": int = 10}`. Success: `{"results": [{"chunk_id", "document_id", "document_name", "position", "content", "keyword_rank", "semantic_rank", "score"}]}`; empty corpus and no-match both return `{"results": []}`. Raw embeddings, tenant IDs, and provider details are never exposed. Existing `{error:{code,message,details?}}` handles 400/401/403/503.

FTS builds `plainto_tsquery('simple', :query)`, filters with `scope.tenant_predicate(Chunk.tenant_id)` before `ts_rank` ordering, and binds every value. Semantic ordering uses `Chunk.embedding.cosine_distance(bindparam(type_=HALFVEC(1536)))`; its transaction first calls parameterized `set_config('hnsw.ef_search', :ef, true)`. The semantic signal only ranks chunks within `semantic_max_distance` (bound as `:max_distance`, default 0.5 cosine distance), so a populated tenant with no relevant match returns the same neutral empty result as an empty corpus. Both join `Document` by tenant/document keys, limit candidates, and break signal ties by chunk ID. Fusion sums `1/(rrf_k+rank)`, then sorts score descending and chunk ID ascending.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Bounds, SQL shape, RRF duplicates/ties | RED tests; compile statements and use exact fake vectors. |
| Integration | Contract, 403, neutral empty, 503, concurrency, tenant isolation | Disposable migrated PostgreSQL and `FakeEmbedder`; assert zero network calls. |
| E2E | Provider/model compatibility | Opt-in credentialed smoke; never part of ordinary tests. |

## Threat Matrix

Applicability review was triggered by the HTTP route/provider boundary; the reference matrix contains only executable-file/VCS automation boundaries.

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no classification/execution | None |
| Git repository selection | N/A — no Git invocation | None |
| Commit state | N/A — no commits | None |
| Push state | N/A — no pushes | None |
| PR commands | N/A — no PR automation | None |

## Migration / Rollout

No data migration required. Deploy API settings/code together; rollback removes the router and settings. Existing chunks and worker output remain valid.

## Open Questions

None.
