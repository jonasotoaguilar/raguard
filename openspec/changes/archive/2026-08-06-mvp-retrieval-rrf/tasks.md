# Tasks: MVP Retrieval with RRF (recut)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 950–1150 total; PR 1 ≤400 (~365) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 core, PR 2 builders, PR 3 endpoint, PR 4 gates |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Core RRF + settings + tests | PR 1 | `uv run pytest -m unit apps/api/tests/unit/test_rrf_fusion.py apps/api/tests/unit/test_retrieval_settings.py` | N/A — pure logic | Remove `retrieval/{__init__,contracts,fusion}.py`, config.py fields, `test_{rrf_fusion,retrieval_settings}.py` |
| 2 | Query builders + tests | PR 2 | `uv run pytest -m unit apps/api/tests/unit/test_retrieval_queries.py` | N/A — pure SQL | Remove `queries.py`+`__init__` query exports, `test_retrieval_queries.py` |
| 3 | Embedder, router, main wiring, openai dep | PR 3 | `uv run pytest -m integration apps/api/tests/integration/test_retrieval_routes.py` | Real: `POST /api/search` on migrated PG, `FakeEmbedder` | Remove `retrieval/{embeddings,router}.py`, revert main.py, pyproject.toml, uv.lock |
| 4 | Isolation gate + e2e smoke | PR 4 | `uv run pytest -m integration apps/api/tests/integration/test_retrieval_isolation.py` | Real: tenants A/B; cross-tenant query on PG | Remove `test_retrieval_isolation.py` + `test_retrieval_provider.py` |

### Recut Boundary — PR 1 (maintainer: "Recortar PR 1 a ≤400 líneas"; no size:exception)

**PR 1 (first slice, ≤400, ~365): stage ONLY** `retrieval/{__init__,contracts,fusion}.py` (exports Candidate, FusedResult, rrf_fusion), `config.py` fields+`model_post_init`, `test_{rrf_fusion,retrieval_settings}.py`.
**PR 2 (next, ~213):** `queries.py` + `__init__` exports, `test_retrieval_queries.py`. Keep uncommitted; not staged in PR 1. No behavior lost; 1.1–1.6 complete.

Threat matrix: all N/A.

## Phase 1: Foundation (PR 1 core; query builders → PR 2)

- [x] 1.1 RED `test_rrf_fusion.py`: dual-signal accumulation, tie order, repeat equality
- [x] 1.2 RED `test_retrieval_queries.py`: tenant predicate first; `plainto_tsquery('simple', :q)`; cosine `bindparam(HALFVEC(1536))`; chunk-id tiebreak; limit
- [x] 1.3 RED `test_retrieval_settings.py`: defaults rrf_k=60/candidates=50/top_k=10/ef_search=100; rejects ef_search<candidates, out-of-range
- [x] 1.4 GREEN `retrieval/{__init__,contracts,fusion,queries}.py`: contracts, RRF, FTS+vector builders; pass 1.1–1.2
- [x] 1.5 GREEN `config.py`: bounded retrieval fields + `model_post_init`; pass 1.3
- [x] 1.6 REFACTOR: match `documents` style; ruff clean

## Phase 2: Endpoint (PR 3)

- [x] 2.1 RED `test_retrieval_routes.py`: valid ≤ top_k; 400 empty/oversized query, top_k>max; 403 missing `chat.use`; empty==no-match `[]`; 503 provider failure, no partials; `FakeEmbedder`
- [x] 2.2 GREEN `embeddings.py`: `OpenAIEmbedder` behind `Embedder` (env `EMBEDDING_MODEL`, rejects ≠1536); `router.py`: `create_retrieval_router(session_factory, settings, embedder)`, `AsyncSession` per signal, `asyncio.gather`, `SET LOCAL hnsw.ef_search`, require `chat.use`
- [x] 2.3 GREEN `main.py`: lazy embedder, include router; `pyproject.toml`+`uv.lock`: openai direct dep
- [x] 2.4 REFACTOR: reuse `require_capability`/`_session`; ruff clean

## Phase 3: Isolation + E2E (PR 4)

- [x] 3.1 RED `test_retrieval_isolation.py`: tenant A sees only A chunks; B-only query returns none
- [x] 3.2 RED `test_retrieval_provider.py`: credential-gated real embed → 1536-dim `halfvec` smoke; skip unless `OPENAI_API_KEY`
- [x] 3.3 GREEN: fix leaks/contract issues from 3.1–3.2

## Phase 4: Verification (PR 4 tail)

- [x] 4.1 Run `uv run pytest -m 'not e2e'`; confirm all 11 spec scenarios (6 requirements)
- [x] 4.2 Run `uv run ruff check apps/api`; update docs/comments
