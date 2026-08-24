# PRD: raguard — Conversational RAG over Internal Documents

raguard helps organizations answer questions from their own documents — policies, runbooks, meeting notes — with answers grounded in retrievable sources, filtered by who is asking, and never leaking content across tenants. This PRD defines the MVP slice: multi-tenant ingestion of PDF/Markdown documents, permission-filtered hybrid retrieval, chat with verifiable citations, and the precision evaluation harness that gates quality.

## Quick Path

1. Define the user problem (Section 2).
2. Confirm the MVP scope and invariants (Sections 4–6).
3. Review non-goals and open decisions before approving scope (Sections 7–9).
4. Route architecture work to `design-architecture` with this PRD as product source of truth.

## Details

| Topic | Decision |
|-------|----------|
| Primary user | Internal employees asking questions about their organization's documents |
| Problem | Answers live in scattered internal documents; LLM chat tools hallucinate and leak scope |
| Outcome | Trustworthy, permission-scoped answers with verifiable citations |
| Success measure | Answer acceptance rate and citation verifiability on an internal evaluation set |

## 1. Executive Summary

- **Problem statement**: Organizations cannot reliably answer questions from their own documents. Manual search is slow, tribal knowledge is fragile, and generic LLM chat is untrustworthy for internal data because it can hallucinate and has no concept of who may see what.
- **Proposed solution**: A self-hosted, multi-tenant RAG system that indexes internal PDF and Markdown documents, retrieves with a hybrid (semantic + keyword) strategy, filters every retrieved chunk by the requesting user's permissions, and generates answers with verifiable citations to the source documents.
- **Success criteria**:
  - KPI 1: ≥ 80% of evaluation-set questions answered with at least one verifiable citation to a retrievable chunk. (Target to be confirmed with the evaluation harness.)
  - KPI 2: 100% of generated citations resolve to chunks the user is authorized to access; zero authorization violations across tenants.
  - KPI 3: Retrieval precision on the evaluation set meets a threshold set at evaluation-harness setup (draft: ≥ 70% top-10 precision).

## 2. Problem Statement

### The Gap Today

- Internal knowledge is spread across documents, wikis, and inboxes; finding the authoritative answer is slow and depends on who you know.
- Generic LLM tools cannot be trusted with internal content: they can answer from nothing, and they ignore organizational boundaries.
- Answers without sources cannot be verified, so reviewers cannot trust them, and mistakes propagate silently.

### Current-State Gap (project) — reconciled 2026-08-24 at `707245a`

`mvp-authz-foundation`, `mvp-document-ingestion`, `mvp-retrieval-rrf`, and `mvp-chat-citations` are delivered on `main` and archived (`openspec/specs/` + `openspec/changes/archive/`). Live on `main`: tenant identity and JWT authentication with org-scoped RBAC via the single fresh `AuthorizationResolver`/`AuthorizationScope`, first-tenant bootstrap via `raguard-bootstrap`, authorized PDF/Markdown upload with tenant-scoped list/detail (`POST /api/documents`, `GET /api/documents`), Redis/Arq ingestion pipeline (parse, chunk, embed, atomic index, failure handling, visible `pending`/`indexed`/`failed` status), permission-filtered hybrid retrieval (`POST /api/search` — FTS `simple` + `halfvec(1536)` cosine, `hnsw.ef_search`, RRF `k=60` at the application layer), and bounded request-scoped chat (`POST /api/chat` — static grounded prompt with untrusted-source delimiters, OpenAI-only completer with bounded timeout/retries/tokens, neutral `{answer: null, citations: []}` on empty/no-match, `[n]` citation verification, safe 503 envelopes). The offline evaluation harness (precision and citation-verifiability measurement), the web UI (`apps/web` remains scaffold only), document deletion, and per-document grants remain open — the next slice is `mvp-evaluation-harness` and is not yet delivered.

## 3. Target Users & Contexts

| Persona | Context | What they need |
|---|---|---|
| **Member** | Employee asking about internal documents (policies, runbooks, meeting notes) | Fast, sourced answers to questions; citations they can open; results limited to what they may see |
| **Organization admin** | Sets up the tenant, manages users, roles, and documents | Upload/ingest workflows, role assignment, visibility into what is indexed |
| **Evaluator / maintainer** | Engineer or product owner running the project | An evaluation harness proving retrieval and answer quality before changes ship |
| **Security reviewer** | Concerned about cross-tenant leakage and injection attacks | Demonstrable isolation: retrieval-level authorization and untrusted document content |

## 4. MVP Scope

### Functional Requirements (User Stories)

- As a **member**, I want to ask questions in natural language about my organization's documents so that I get an answer with sources I can verify.
- As a **member**, I want every citation to open the actual source chunk so that I can check the answer against the document.
- As a **member**, I want my conversations to stay within my organization's documents so that I never see content I am not authorized to read.
- As an **admin**, I want to upload PDF and Markdown files and have them indexed automatically so that new knowledge becomes searchable without manual effort.
- As an **admin**, I want to assign users roles and document permissions so that retrieval respects organizational boundaries.
- As a **maintainer**, I want to run an offline evaluation over a labeled question set so that I can measure retrieval precision and answer quality before shipping changes.

### Acceptance Criteria (MVP) — current state at `707245a`

- [x] An organization admin can create a tenant, add users, assign roles, and upload PDF/Markdown documents. — first tenant via `raguard-bootstrap` (`BOOTSTRAP_TENANT_NAME`/`BOOTSTRAP_ADMIN_EMAIL`/`BOOTSTRAP_ADMIN_PASSWORD`), org administration via `POST /api/auth/login` + `GET/PATCH /api/org/*` (`users.manage`/`org.settings.manage`), authorized upload via `POST /api/documents` (`documents.manage`) — see `apps/api/src/raguard_api/identity/bootstrap.py`, `org/router.py`, `documents/router.py`; tests: `test_bootstrap.py`, `test_org_routes.py`, `test_documents_routes.py`.
- [x] Ingested documents are chunked, embedded, and indexed; ingestion progress and failures are visible. — `apps/worker/src/raguard_worker/` (parsers, chunking, embeddings, atomic indexing), document status `pending`/`indexed`/`failed` with `failure_reason` allowlist, visible via `GET /api/documents`; tests: `test_documents_routes.py`, `test_documents_models.py`, `test_retrieval_service.py`.
- [x] A user can ask a question and receive an answer grounded in retrieval, with citations linking back to source chunks. — `POST /api/chat` and `POST /api/search` share `retrieve_chunks` (`retrieval/service.py`); chat verifies `[n]` markers via `chat/citations.py`, returns `answer` + `citations` (`chunk_id`, `document_id`, `document_name`, `position`, `content`); tests: `test_chat_routes.py`, `test_chat_citations.py`, `test_chat_contracts.py`.
- [x] Retrieval combines semantic and keyword signals (RRF fusion); retrieval is scoped by the user's permissions at query time. — tenant predicate before ranking in both signals (`retrieval/queries.py`, `retrieval/fusion.py` RRF `k=60`), fresh `AuthorizationScope` per request, integration isolation gates; tests: `test_retrieval_service.py`, `test_retrieval_routes.py`, `test_retrieval_isolation.py`.
- [x] Prompt-injection protection: document content cannot alter system or user instructions (tested with adversarial documents). — static `SYSTEM_PROMPT` free of secrets, chunk content injected only inside `UNTRUSTED_SOURCES_START/END` as JSON, prompt assembly outside the adapter (`chat/prompts.py`), adversarial document gates; tests: `test_chat_prompts.py`, `test_isolation_gates.py`, `test_chat_release_gates.py` (` adversarial `).
- [ ] An evaluation harness runs offline against a labeled set and reports retrieval precision and citation-verifiability metrics. — **Not delivered**; next slice `mvp-evaluation-harness` (do not claim).
- [x] No cross-tenant or cross-role data leakage is demonstrable in tests. — retrieval-level authorization invariant enforced at query time + citation verification against the authorized set; release isolation gates across tenants/roles; tests: `test_retrieval_isolation.py`, `test_chat_release_gates.py`, `test_release_gates.py`, `test_isolation_gates.py`.

> E2E provider smoke (`apps/api/tests/e2e/test_retrieval_provider.py`, `test_chat_e2e.py`) is credential-gated and not required for non-e2e verification; web-facing conversation history and document deletion remain planned and are not marked complete here.

## 5. Invariants (Non-Negotiable)

### Authorization Invariant

- Retrieval-level filtering: chunks are filtered by the user's permissions **before** any generation happens. Permissions are enforced in the retrieval path, never only in the UI.
- Tenant isolation: a query is scoped to exactly one tenant; no code path may cross tenant boundaries.
- Roles gate document visibility; a change that weakens authorization at any layer is a release blocker.

### Citation Invariant

- Every citation in an answer must resolve to a retrievable chunk that the user is authorized to access; answers must not cite un-retrievable or un-authorized sources.
- Citation verifiability is a product requirement, measured by the evaluation harness, not an afterthought.

## 6. Evaluation & Security Requirements

- **Precision evaluation**: a labeled question/answer set with known-good chunks; the harness measures retrieval precision and citation verifiability and gates changes.
- **Prompt-injection protection**: document content is untrusted data; system prompts are isolated from document content; adversarial test documents are part of the security test suite.
- **AuthN/AuthZ**: thin JWT-based authentication with org-scoped role-based access control (RBAC); sessions and roles are scoped per tenant.
- **Secrets handling**: provider credentials live in environment files or a secret manager, never in source or manifests.

## 7. Non-Goals (MVP)

- No web crawling, email ingestion, or non-PDF/Markdown file types in the MVP.
- No global/public search across tenants; no cross-tenant collaboration.
- No fine-tuning of models in the MVP (adapter-based prompting only).
- No LLM-driven summarization of the whole corpus; no document Q&A across arbitrary file types.
- No self-serve tenant signup in the MVP (tenant provisioning is admin-driven).
- No compliance certifications; the MVP is self-hosted, and org data stays in org infrastructure.

## 8. Risks & Tradeoffs

| Risk | Tradeoff / Mitigation |
|---|---|
| Retrieval quality below threshold | Evaluation harness gates changes; hybrid retrieval (FTS + embeddings) widens recall; RRF fusion avoids single-signal failure |
| LLM hallucination | Grounding in retrieved chunks, verifiable citations, and evaluation-set measurement |
| Prompt-injection via documents | Document content treated as untrusted; adversarial test documents in the suite |
| Cross-tenant leakage | Retrieval-level authorization invariant; tested as a first-class security scenario |
| LLM/embedding provider dependency | Provider-neutral adapter; embedding provider replaceable (default OpenAI embeddings) |
| Chunking/retrieval tuning is an open area | Parameterized chunking and RRF weights; tuned against the evaluation set |
| Version drift across stack | Versions verified at setup time; lockfiles authoritative (see README) |

## 9. Success Metrics

| Metric | Draft target | How measured |
|---|---|---|
| Answer acceptance rate | ≥ 80% of eval-set questions answered with verifiable citations | Evaluation harness |
| Citation verifiability | 100% of citations resolve to user-accessible chunks | Evaluation harness + authorization tests |
| Authorization violations | 0 across tenants and roles | Security/authorization test suite |
| Retrieval precision | ≥ 70% top-10 precision (confirm at harness setup) | Evaluation harness |
| Time to first answer | Draft: p95 < 10 s on reference dataset (confirm with load testing) | Runtime monitoring |

Targets marked *draft* are confirmed when the evaluation harness and load environment exist.

## 10. Open Product Decisions

- Embedding provider policy: default OpenAI embeddings via the neutral adapter; whether Anthropic (or others) is offered as an alternative is a product decision, not an embeddings claim — Anthropic does not provide embeddings.
- Tenant provisioning: admin-invited users only (MVP default) vs. self-serve signup later.
- Chat history: persistence scope (per-conversation, per-tenant) and retention policy.
- Document lifecycle: deletion behavior and whether deletion removes embeddings/citations immediately.
- Chunking strategy and RRF weights: initial defaults set at configuration phase, tuned against the evaluation set.
- Evaluation ownership: whether the harness ships in-repo or as a separate tool.

## Checklist

- [x] Problem is clear before solution detail.
- [x] Success criteria are measurable (draft targets flagged).
- [x] Non-goals are explicit.
- [x] Authorization and citation invariants are stated as non-negotiable.
- [x] Acceptance criteria are reviewable.
- [ ] Open decisions resolved before design work depends on them.

## Next Step

This PRD is the product source of truth. Architecture decisions (system/API design, auth model, retrieval pipeline) are routed to `design-architecture`, which owns `ARCHITECTURE.md` and ADRs. The configuration phase establishes tooling and lockfiles; exact versions are verified at setup time.
