# ADR-0004: Redis + Arq for Asynchronous Job Processing

## Status

Accepted (user-approved; target design for a greenfield repository — no implementation exists yet)

## Date

2026-08-04

## Deciders

Jonathan Soto (jonasotoaguilar)

## Context

Document ingestion (download raw file, parse PDF/Markdown, chunk, embed via external API, index chunks) is slow, I/O-bound, and must not block chat requests. The topology (ADR-0001) already separates a worker process from the API; the worker needs a job queue. Constraints: Redis is already in the stack (also used as cache); Python on both sides; at-least-once delivery with retry and failure visibility is required; no event-bus semantics, no ordering requirements across documents (per-document ordering only); the PRD requires "ingestion progress and failures are visible."

## Decision

Use **Redis as the queue broker and Arq (async Python worker) for job processing**. The API enqueues one job per document (idempotency key = document id); the worker claims jobs with Arq's lease mechanism, processes them, and records status (`pending` / `indexed` / `failed` + reason) in PostgreSQL. Delivery is **at-least-once**: retries with exponential backoff and a max-retry budget; the consumer deduplicates by document id and re-indexing is idempotent (replaces that document's chunks). No dead-letter queue in the MVP — failed documents are surfaced in the UI and re-enqueued by re-upload/manual retry.

Setup verification (2026-08-04): Arq **0.28.0** with **redis-py 5.3.1** (`redis[hiredis]>=5.0,<6` — Arq's supported dependency range excludes redis-py 6, so redis-py 6.x is not resolvable with Arq); Redis server image pinned `redis:8.10.0-alpine`. Lockfiles and the pinned image are authoritative.

## Consequences

### Positive

- Redis is already in the stack — no new broker technology.
- Arq is lightweight, async-native (matches FastAPI's event loop patterns), and supports lease-based claims (a crashed worker releases jobs).
- Idempotency by document id makes at-least-once safe and re-ingestion trivially correct.
- Job lifecycle is observable: queue depth, job status in PostgreSQL, failure reasons in the UI.

### Negative

- Redis is not a strong-durability message broker; under Redis restart, in-flight jobs may be lost (document remains `pending`, user re-triggers). Acceptable for the MVP; persistence configurable.
- At-least-once (not exactly-once) means all job consumers must be idempotent — a discipline enforced by the document-id key.
- No DLQ means poison jobs occupy retry budget; bounded by max-retries + visible failure state.

### Neutral

- Arq is less known than Celery; the team adopts a smaller ecosystem.

## Options Considered

### Option A: Celery
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium–High (broker abstraction, beat, result backend) |
| Cost | Low |
| Scalability | Good |
| Team familiarity | High (widely known) |
| Ecosystem / Tooling | Rich |
| Operational overhead | Medium |

**Pros:** mature, feature-rich, many beat/reliability options.
**Cons:** heavyweight for two job types; sync-first design and configuration surface exceed MVP needs.

### Option B: RQ
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Low |
| Scalability | Good |
| Team familiarity | Medium |
| Ecosystem / Tooling | Simple |
| Operational overhead | Low |

**Pros:** simple, Redis-native.
**Cons:** sync workers only (blocks event-loop concurrency inside jobs), less explicit retry/lease control than Arq.

### Option C: Arq over Redis (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Low |
| Scalability | Good (horizontal workers) |
| Team familiarity | Medium (smaller ecosystem) |
| Ecosystem / Tooling | Async-native, lease-based |
| Operational overhead | Low |

**Pros:** async end-to-end, lease semantics, retries built in, minimal config.
**Cons:** smaller ecosystem; Redis durability caveats apply to all options.

### Option D: Kafka/event bus
| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Cost | High |
| Scalability | Excellent |
| Team familiarity | Low |
| Operational overhead | High |

**Pros:** durable, ordered, replayable.
**Cons:** massive overkill for per-document ingestion; contradicts ADR-0001's rejection of event-bus architecture.

## Trade-off Analysis

Celery and RQ solve the same problem with more baggage or worse async behavior; Kafka re-introduces the distributed complexity ADR-0001 rejected. Arq gives the MVP exactly what it needs — async jobs, lease-based claims, built-in retries, at-least-once with idempotent consumers — on infrastructure that already exists. The durability caveat is real but bounded: the document row in PostgreSQL is the source of truth for status, so a lost job is visible and re-runnable rather than silently lost.

## Action Items

1. [ ] Implement the ingestion job with document-id idempotency and replace-on-reindex semantics.
2. [ ] Configure bounded retries with exponential backoff and a visible `failed` state with reason.
3. [ ] Add queue-depth and job-status metrics (observability) at the config phase.
4. [ ] Decide Redis persistence mode (RDB/AOF) based on the durability review before production.

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Async Delivery, Failure Modes & Mitigations
- [PRD.md](../PRD.md) — MVP scope (ingestion progress and failures visible)
- Related ADRs: [ADR-0001](0001-modular-monolith-with-worker.md), [ADR-0006](0006-s3-compatible-object-storage.md)
