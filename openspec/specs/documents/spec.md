# Documents Specification

## Purpose

Tenant-scoped ingestion: authorized PDF/Markdown upload, async parse/chunk/embed/index pipeline, visible status. Content is untrusted; authorization derives only from verified identity and role grants.

## Requirements

### Requirement: Authorized upload with validation

`POST /api/documents` MUST accept multipart uploads only from users granted `documents.manage`, limited to PDF/Markdown within a configured size bound; other types or oversized files MUST be rejected (400).

#### Scenario: Admin uploads valid PDF

- GIVEN tenant A's admin granted `documents.manage`
- WHEN the admin uploads a valid PDF
- THEN the upload is accepted `pending`

#### Scenario: Unauthorized or invalid upload rejected

- GIVEN a caller without `documents.manage` or an invalid file
- WHEN the upload proceeds
- THEN the request fails via the error envelope (403/400)
- AND nothing is persisted

### Requirement: Atomic storage and enqueue

Storage MUST store bytes under a tenant-prefixed key, persist a `pending` row, and enqueue exactly one job carrying only the document ID; failure MUST reject the request leaving nothing behind.

#### Scenario: Successful store and enqueue

- GIVEN an authorized valid-file upload
- WHEN storage and enqueue succeed
- THEN bytes exist under a tenant-prefixed key
- AND a `pending` row exists
- AND exactly one job is queued carrying only the document ID

#### Scenario: Storage failure rejects cleanly

- GIVEN storage fails
- WHEN an authorized upload occurs
- THEN the request fails with the error envelope
- AND no orphan row, object, or job remains

### Requirement: Bounded queue failures

Processing MUST be at-least-once and idempotent by document ID, moving status `pending` → `indexed` on success; bounded retries MUST end in `failed` with a reason.

#### Scenario: Transient failure ends in failed

- GIVEN a parser or provider fails repeatedly
- WHEN the retry limit is reached
- THEN status is `failed` with a reason

#### Scenario: Success reaches indexed

- GIVEN an accepted upload
- WHEN the worker completes the pipeline
- THEN status is `indexed`, chunks exist

### Requirement: Idempotent indexing

Re-processing MUST atomically replace the document's chunks (content, embeddings, vectors); duplicates MUST never coexist. Chunk size and embedding provider MUST be configurable.

#### Scenario: Redelivery replaces without duplicates

- GIVEN an indexed document with N chunks
- WHEN the job redelivers and succeeds
- THEN the document has only new chunks

#### Scenario: Failed commit leaves no partial chunks

- GIVEN a failure mid-commit
- WHEN the job retries later
- THEN zero or all chunks exist
- AND status never `indexed` with partial chunks

### Requirement: Tenant-isolated list and detail

`GET /api/documents` and `GET /api/documents/{id}` MUST require `corpus.view` and return only the caller's tenant documents with status `pending`, `indexed`, or `failed` (reason). A cross-tenant request MUST fail with a neutral 404.

#### Scenario: Member lists own tenant corpus

- GIVEN a tenant A member
- WHEN the member lists or requests a tenant A document
- THEN only tenant A documents with status return

#### Scenario: Cross-tenant detail is neutral

- GIVEN a tenant A member
- WHEN the member requests a tenant B document
- THEN the request fails with a neutral 404
- AND no existence is disclosed

### Requirement: Untrusted content boundary

Content MUST NOT influence authorization, tenant scoping, or access decisions. Adversarial content (embedded instructions, control tokens, malformed bytes) MUST be treated as data only; failures MUST surface as `failed` with a reason, never escalating privileges or crossing tenants.

#### Scenario: Injection-shaped content stays inert

- GIVEN a document with instruction-like text
- WHEN the worker processes it
- THEN the outcome depends only on pipeline success
- AND no authorization or scoping changes

#### Scenario: Malformed content fails safely

- GIVEN an unparsable document
- WHEN the worker processes it
- THEN status becomes `failed` with a reason
- AND no partial chunks or authorization impact

## Deferred

Deletion semantics, provider, chunking values; out of scope: retrieval/RRF, chat/citations, evaluation, web UI, per-document grants.
