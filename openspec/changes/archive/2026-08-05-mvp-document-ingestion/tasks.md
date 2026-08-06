# Tasks: MVP Document Ingestion

## Review Workload Forecast

Estimated lines: PR4a ~700, PR4b ~640 (each ≤ 800/slice).
Delivery strategy: auto-chain

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Packaging | PR 1 | `uv run pytest apps/worker/tests/unit` | `uv sync` | Revert `pyproject.toml`×3 + `uv.lock` |
| 2 | Models/contracts/migration | PR 2 | `uv run pytest apps/api/tests/integration/test_migration.py apps/api/tests/integration/test_constraints.py` | `uv run alembic upgrade head` | Drop `0002`; revert models |
| 3 | Upload/reads + compensation | PR 3 | `uv run pytest apps/api/tests/integration/test_documents_routes.py` | curl upload → `pending` | Remove documents router |
| 4a | Dispatch/job foundation | PR 4a | `uv run pytest apps/worker/tests/unit/test_dispatch.py apps/worker/tests/unit/test_ingestion_job.py apps/worker/tests/integration/test_early_claim.py` | `uv run arq raguard_worker.settings.WorkerSettings` | Revert `apps/worker/src/raguard_worker/{settings,jobs}.py` + PR4a tests |
| 4b | Parsing/chunk/embed + sweep | PR 4b | `uv run pytest apps/worker/tests/unit/test_parsing_chunking_embeddings.py apps/worker/tests/integration/test_cleanup.py` | `uv run arq raguard_worker.settings.WorkerSettings` | Revert `apps/worker/src/raguard_worker/{parsers,chunking,embeddings}.py` + PR4b tests |
| 5 | Infra, CI, observability | PR 5 | `docker compose config -q` | `docker compose up -d --build` | Revert Dockerfile/compose/CI |

## Phase 1: Workspace & Data Foundation

- [x] 1.1 RED `apps/worker/tests/unit/test_imports.py`
- [x] 1.2 GREEN `pyproject.toml`×3 (uv_build, `raguard-api` dep, pytest path); `uv.lock`
- [x] 1.3 RED `apps/api/tests/unit/test_documents_models.py`: readiness, `halfvec(1536)`, enum, reasons
- [x] 1.4 GREEN `apps/api/src/raguard_api/documents/{models,contracts}.py`: models + ObjectStore/JobQueue/Parser/Embedder protocols/fakes
- [x] 1.5 RED `apps/api/tests/integration/{test_migration,test_constraints}.py`: `0002` up/down, tenant/GIN/HNSW, FK uniqueness
- [x] 1.6 GREEN `apps/api/alembic/versions/0002_documents_chunks.py`; `env.py`
- [x] 1.7 REFACTOR imports; alembic upgrade clean

## Phase 2: API Ingestion & Reads

- [x] 2.1 RED `apps/api/tests/unit/test_documents_adapters.py`: tenant-prefixed put/delete, `_job_id="ingest:{id}"`, one enqueue
- [x] 2.2 GREEN `apps/api/src/raguard_api/documents/{storage,queue}.py`: boto3/Arq impls + fakes
- [x] 2.3 RED `apps/api/tests/integration/test_documents_routes.py`: 12 scenarios — valid→`pending`; 403/400; one id-only job; storage-fail; scoped list/detail; neutral 404; ghost
- [x] 2.4 GREEN `apps/api/src/raguard_api/documents/router.py` (`documents.manage`, 20 MiB, tenant prefix, unready→enqueue→ready; `corpus.view` + tenant predicate); extend `config.py`, `main.py`
- [x] 2.5 REFACTOR compensation + jittered retries

## Phase 3: Worker Dispatch & Job Foundation

- [x] 3.1 RED `apps/worker/tests/unit/test_dispatch.py`: 5 states — ready+object→process; fresh-unready→poll→`DispatchNotReady`; stale-unready→no-op; missing→ACK; ready+missing→`failed/source_missing`; `wait<freshness<sweep_age`
- [x] 3.2 RED `apps/worker/tests/unit/test_ingestion_job.py`: thrice+jitter, 429 `Retry-After`, exhaustion→`failed`+reason, atomic zero-or-all, ACK no-mutation, allowlisted reasons
- [x] 3.3 RED `apps/worker/tests/integration/test_early_claim.py`: claim+await; API commits ready; succeeds without retry consumption
- [x] 3.4 GREEN `apps/worker/src/raguard_worker/{settings,jobs}.py`: `WorkerSettings` (30s/5s/100ms/5min; `wait<freshness<sweep_age`), `ingest_document` dispatch + retries
- [x] 3.5 REFACTOR share contracts; isolate dispatch seam

## Phase 4: Parsing, Chunking, Embedding & Sweep

- [x] 4.1 RED `apps/worker/tests/unit/test_parsing_chunking_embeddings.py`: bounds 500p/5M/10k/64/30s, configurable chunk/provider, inert content, malformed→`failed`
- [x] 4.2 RED `apps/worker/tests/integration/test_cleanup.py`: sweep `SKIP LOCKED`, no unready locks, exhaustion alert+marker
- [x] 4.3 GREEN `apps/worker/src/raguard_worker/{parsers,chunking,embeddings}.py`: pypdf/OpenAI, chunker, cleanup cron + observability
- [x] 4.4 REFACTOR arq worker starts; ruff clean

## Phase 5: Infra, CI & Observability

- [x] 5.1 GREEN `apps/worker/Dockerfile`, `infra/compose.yaml` (worker, healthy Postgres/Redis/MinIO, same command), `.github/workflows/ci.yml`, `.env.example`
- [x] 5.2 GREEN correlation IDs/logs; alerts: pending age, failures, sweep backlog
- [x] 5.3 VERIFY `uv run pytest -m 'not e2e' && pnpm test`; compose upload→`indexed` smoke
