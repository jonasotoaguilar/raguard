# Design: MVP Document Ingestion

## Technical Approach

Extend the FastAPI modular monolith and fresh `AuthorizationScope` with the ADR-0001/0004–0006 Arq worker. All six requirements and twelve scenarios stay in one flow: authorized upload → tenant object → guarded `pending` row → deterministic job → parse/chunk/embed → atomic replacement → `indexed`/`failed`. Retrieval, deletion, UI, grants, and tuning stay out of scope.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| SDK calls vs seams | Direct calls hinder deterministic tests. | Narrow `ObjectStore`, `JobQueue`, `Parser`, `Embedder` protocols over boto3, Arq, pypdf, OpenAI, and owned fakes. |
| Package sharing | A third package is premature; PYTHONPATH is fragile. | Install both src projects with `uv_build`; worker depends on workspace `raguard-api` and imports `raguard_api.documents` models/contracts/storage. |
| Cross-store commit | PostgreSQL, S3, Redis cannot commit atomically; enqueue may succeed then raise. | Put object; commit unready `pending`; enqueue `_job_id="ingest:{id}"`; immediately after a successful enqueue response commit `dispatch_ready=true`, then return HTTP. Early claim remains possible. API failure deletes object then row with bounded retries; exhaustion alerts and leaves a hidden sweep marker. |
| Terminal/index states | Redelivery and partial writes require explicit semantics. | Lock ready rows; replace chunks and set `indexed` atomically. `indexed` reprocesses; `failed` ACKs without adapters/mutation. Missing rows ACK; ready rows missing objects become `failed/source_missing` without partial chunks. |
| Vector shape | Generic vectors weaken indexing. | Validate `halfvec(1536)`/`text-embedding-3-small`; dimension changes require migration/re-indexing. |

## Data Flow

```mermaid
sequenceDiagram
  U->>A: authorized bounded multipart
  A->>S: put tenant/document/basename
  A->>D: commit pending, dispatch_ready=false
  A->>Q: enqueue id with deterministic job id
  Q-->>A: enqueue accepted
  Q-->>W: early claim may occur
  W->>D: fresh unready; bounded poll without lock
  A->>D: commit ready before HTTP response
  A-->>U: accepted pending
  W->>D: observe ready; lock and gate
  W->>S: get; parse/chunk
  W->>E: bounded batches
  W->>D: replace chunks + indexed atomically
```

The dispatch predicate is explicit:

| Observed state | Worker action |
|---|---|
| Ready row + object present | Lock, process, and atomically replace chunks/status. |
| Fresh unready row | Poll unlocked; after bounded wait raise typed `DispatchNotReady` for Arq deferral, outside the ingestion/provider retry budget. |
| Stale unready row | ACK as compensation/sweep-owned terminal no-op; no processing or status write. |
| Missing row | ACK terminally; never recreate or write status. |
| Ready row + missing object | Atomically clear chunks and set allowlisted `failed/source_missing`. |

Defaults: 30-second freshness, 5-second wait/100-ms poll, 5-minute sweep age. Startup enforces `wait < freshness < sweep_age`. Sweep uses `SKIP LOCKED`; workers never lock unready rows, preventing sweep/process races. Adapter errors retry thrice with jitter; provider 429s honor bounded `Retry-After`. Malformed/encrypted/limit failures use allowlisted reasons. Bounds: 20 MiB, 500 pages, 5M characters, 10k chunks, 64-text batches, 30-second provider calls, and job timeout. Instructions, links, attachments, JavaScript, and control tokens remain data only.

## File Changes

| File | Action | Description |
|---|---|---|
| `pyproject.toml`, `apps/{api,worker}/pyproject.toml`, `uv.lock` | Modify | Installable src packages, workspace API dependency, worker pytest path, pypdf/OpenAI pins. |
| `apps/api/src/raguard_api/documents/{models,router,storage,queue,contracts}.py`, `config.py`, `main.py` | Create/Modify | Shared contracts/adapters, guarded upload, scoped reads, wiring. |
| `apps/api/alembic/versions/0002_documents_chunks.py`, `alembic/env.py` | Create/Modify | Documents/chunks, readiness, constraints, tenant/GIN/HNSW indexes. |
| `apps/worker/src/raguard_worker/{settings,jobs,parsers,chunking,embeddings}.py` | Create | `WorkerSettings`, ingestion, retry classification, cleanup cron; runtime command: `uv run arq raguard_worker.settings.WorkerSettings`. |
| `apps/worker/Dockerfile`, `infra/compose.yaml`, `.github/workflows/ci.yml`, `.env.example` | Create/Modify | Locked workspace; healthy PostgreSQL/Redis/MinIO; same worker command in runtime/CI; non-secret settings. |
| `apps/api/tests/`, `apps/worker/tests/` | Create/Modify | Unit, migration, integration, failure, security tests. |

## Interfaces / Contracts

Jobs carry only UUID document IDs. Public responses expose id/name/status/allowlisted reason, never keys, content, provider errors, unready rows, or cross-tenant existence. Upload requires `documents.manage`; reads compose `scope.tenant_predicate` and require `corpus.view`.

## Testing Strategy

RED tests preserve all 12 scenarios. Units cover validation, bounds, inert content, retries, adapters. Integrations cover migration, isolation, atomic replacement/rollback, redelivery, and one enqueue. The early-claim test pauses ready commit: worker claims and waits, API commits ready, then indexing succeeds without ingestion/provider retry consumption. Keep the real-Redis enqueue-accepted/response-failed ghost test: compensation leaves no row, chunks, object, or status. Cleanup-exhaustion proves alerting, marker ownership, sweep. Embeddings are faked outside e2e; gate: `uv run pytest -m 'not e2e' && pnpm test`.

## Threat Matrix

Process integration exists, but all reference rows are N/A: paths are data; no Git selection, commit/push state, PR command, shell, or executable-classification boundary exists. No matrix RED tasks apply.

## Migration / Rollout

Create bucket, apply `0002`, smoke the declared worker, expose routes. Alert on pending age, queue/job failures, compensation exhaustion/sweep backlog with bounded labels and correlation IDs. Rollback disables upload, drains workers, removes release artifacts, downgrades `0002`.

## Open Questions

Upload rate limiting remains ARCHITECTURE.md open decision #7; this design does not set it. Resource bounds above still apply.
