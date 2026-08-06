# ADR-0001: Modular Monolith API with Dedicated Worker Process

## Status

Accepted (user-approved; target design for a greenfield repository — no implementation exists yet)

## Date

2026-08-04

## Deciders

Jonathan Soto (jonasotoaguilar)

## Context

raguard has two distinct load paths: an interactive request path (chat: retrieval + generation) and a batch path (document ingestion: parse, chunk, embed, index). Both share one source of truth (PostgreSQL) and one hard invariant: every tenant/user/role can only ever retrieve authorized chunks. The MVP is a single product with a small team and no independent scaling needs for internal services. We must choose a process topology that keeps the authorization surface small, isolates ingestion load from request latency, and does not bury the project in distributed-systems overhead.

## Decision

Adopt a **modular monolith for the API** plus a **separate worker process** for async ingestion, in a monorepo:

- `apps/api` — FastAPI: auth, org-scoped RBAC, documents, retrieval, chat, citation verification, job enqueueing.
- `apps/worker` — Python worker process consuming jobs from Redis (Arq): parse, chunk, embed, index.
- `infra` — Docker Compose and Caddy configuration.
- `apps/web` — React + Vite frontend.

The only inter-process coupling is PostgreSQL (shared store) and the Redis job queue. No message bus, no service mesh, no per-service databases.

## Consequences

### Positive

- The authorization invariant is enforceable in exactly one place: the API's retrieval path, against a single database.
- Ingestion (CPU/IO + embedding API calls) never competes with chat latency.
- API and worker scale horizontally and independently without re-architecting.
- Data integrity via transactions remains trivial (single database).

### Negative

- The API monolith grows as features are added; disciplined modular boundaries inside the app are required to avoid a big ball of mud.
- Deploying worker and API means two processes/containers to operate (still one Compose file).
- A future split into real services would require rework of the authz and data-ownership boundaries.

### Neutral

- The worker shares Python code/libraries with the API (common ingestion + adapter code); shared codebases must keep clean interfaces.

## Options Considered

### Option A: Microservices with Kafka/event bus
| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Cost | High (broker, orchestration, observability) |
| Scalability | High (but unneeded at MVP scale) |
| Team familiarity | Low for a small team |
| Ecosystem / Tooling | Heavy |
| Operational overhead | High |

**Pros:** independent scaling, fault isolation, team autonomy.
**Cons:** distributed transactions, the authorization invariant now spans multiple services, vastly more operational surface for a 2-path MVP.

### Option B: Single monolith process with in-process background tasks
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Low |
| Scalability | Poor for mixed load |
| Team familiarity | High |
| Ecosystem / Tooling | Minimal |
| Operational overhead | Low |

**Pros:** simplest possible operations.
**Cons:** ingestion load (embedding API calls, parsing) directly competes with request latency; no independent retry/backpressure for batch work; one failure mode takes down everything.

### Option C: Modular monolith API + separate worker (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low–Medium |
| Cost | Low |
| Scalability | API and worker scale independently |
| Team familiarity | High |
| Ecosystem / Tooling | Arq over existing Redis |
| Operational overhead | Low (one extra process) |

**Pros:** all the positives listed above.
**Cons:** monolith discipline required; a second deployable to run.

## Trade-off Analysis

Option A buys independent scalability and fault isolation that the MVP does not need, at the cost of the highest-risk failure mode this product has: a distributed authorization surface that can silently break the no-leakage invariant. Option B is operationally cheapest but couples interactive latency to batch work. The chosen topology (C) captures the batch/request isolation that actually matters — separate worker process — while keeping every authorization decision in one database and one codebase.

## Action Items

1. [ ] Scaffold monorepo layout (`apps/web`, `apps/api`, `apps/worker`, `infra`) at config phase.
2. [ ] Define the shared code boundary between API and worker (adapter and domain modules) as a package both depend on.
3. [ ] Document that new services require a new ADR.

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — System Overview, Architecture Pattern, Topology diagram
- [PRD.md](../PRD.md) — MVP scope and invariants
- Related ADRs: [ADR-0004](0004-redis-arq-async-jobs.md) (the queue that couples the two processes)
