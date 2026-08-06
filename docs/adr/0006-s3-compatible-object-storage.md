# ADR-0006: S3-Compatible Object Storage Abstraction

## Status

Accepted (user-approved; target design for a greenfield repository — no implementation exists yet)

## Date

2026-08-04

## Deciders

Jonathan Soto (jonasotoaguilar)

## Context

Raw document binaries (PDF/Markdown) must be stored outside PostgreSQL (blobs in a relational store are wasteful and hard to scale). The PRD/README target is S3-compatible storage: MinIO locally, S3 or Cloudflare R2 in production — one abstraction so local and production topologies stay identical. Constraints: the storage access pattern is write-once, read-for-ingestion (the worker downloads the raw file for parsing); object keys must be tenant-scoped; upload failure must not leave orphaned database rows; credentials are secrets.

## Decision

Use **S3-compatible object storage through `boto3` with an explicit `endpoint_url`** configured by environment: MinIO for local development, S3 (AWS) or R2 (Cloudflare) in production — no code changes when the endpoint changes. Keying convention: `{tenant_id}/{document_id}/{filename}` (tenant prefix enforced at the API layer; storage has no authorization semantics of its own). The API writes the object on upload, creates the document row, then enqueues the ingest job (ADR-0004); on storage failure the upload is rejected before any row is committed. The worker reads the object during ingestion.

## Consequences

### Positive

- One code path for MinIO/S3/R2: local and production topologies differ only by configuration.
- boto3 is the de-facto standard client; `endpoint_url` is a supported, stable configuration surface.
- Tenant-prefixed keys make object layout auditable and cleanup straightforward.
- Write-once semantics keep storage out of consistency-critical paths (PostgreSQL remains the source of truth).

### Negative

- S3 API differences (R2 quirks, MinIO parity) may surface rarely; mitigated by confining all client usage behind a thin storage module.
- MinIO upstream is no longer maintained (its repository now points to AIStor); the local image is pinned to the last verifiable published image (`minio/minio:RELEASE.2025-09-07T16-13-09Z`). Scope: local development only — revalidate the image and upstream status before any non-local use; S3/R2 remain the production targets.
- Raw files are stored per-tenant with no server-side authorization semantics; access control must stay in the API (consistent with the retrieval-level authorization model).
- Lifecycle management (deletion, versioning, retention) is provider-dependent — tied to the document-lifecycle open decision.

### Neutral

- Object storage becomes another adapter-like boundary (small, but with provider quirks).

## Options Considered

### Option A: Local filesystem storage
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | None locally |
| Scalability | Poor (single node) |
| Team familiarity | High |
| Operational overhead | Low |

**Pros:** simplest local development.
**Cons:** diverges from production; volume mounting and backup semantics are worse; migration to real storage becomes a rewrite.

### Option B: Database blob storage (bytea/large objects in PostgreSQL)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | DB bloat, backup bloat |
| Scalability | Poor for large binaries |
| Team familiarity | High |
| Operational overhead | Medium |

**Pros:** single store, transactional with the document row.
**Cons:** large blobs bloat backups and connection memory; not the right tool for file content, and PRD already assumes object storage.

### Option C: S3-compatible via boto3 + endpoint_url (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low–Medium |
| Cost | Low (MinIO free; S3/R2 cheap) |
| Scalability | Excellent |
| Team familiarity | High (boto3 is standard) |
| Operational overhead | Low–Medium |

**Pros:** identical code for local and production; tenant-prefixed keys; standard client; satisfies the PRD's replaceable-components goal.
**Cons:** provider quirks (R2/MinIO parity) need a thin containment module; access control stays in the API.

## Trade-off Analysis

The filesystem option saves effort locally but creates a production divergence that would eventually require a storage rewrite. Database blobs misplace a scaling concern (large binaries) in the relational store. The S3-compatible abstraction matches the PRD's explicit infrastructure direction (MinIO local, S3/R2 production) with a standard client and a single configuration knob (`endpoint_url`) — the only real cost is disciplined containment of provider-specific behavior behind a thin module, plus keeping authorization in the API where the invariant already lives.

## Action Items

1. [ ] Confine all object-storage client usage to one module (initialization with `endpoint_url`, upload/download, tenant-prefixed key helpers).
2. [ ] Enforce tenant-prefixed keys at the API layer and add a test that uploads cannot escape the tenant prefix.
3. [ ] Implement upload as storage-write → row-commit → enqueue (atomicity ordering above), with failure cleanup.
4. [x] Document provider configuration (MinIO/S3/R2 credentials, buckets, region) in `.env.example` — present at setup (credentials are placeholders by design).

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Component Details (Object Storage), Deployment & Configuration Principles
- [README.md](../README.md) — Planned Local Services (MinIO local, S3/R2 production)
- [PRD.md](../PRD.md) — MVP scope (document upload), Non-Goals
- Related ADRs: [ADR-0001](0001-modular-monolith-with-worker.md), [ADR-0004](0004-redis-arq-async-jobs.md)
