# Exploration: mvp-authz-foundation

> **Phase**: sdd-explore &nbsp;|&nbsp; **Date**: 2026-08-05 &nbsp;|&nbsp; **Author**: Jonathan Soto (jonasotoaguilar)
> **Status**: Ready for proposal — recommended first MVP slice, validated against repository evidence.
> **Artifact store**: hybrid (OpenSpec + Engram, topic key `sdd/mvp-authz-foundation/explore`)

## Executive Summary

raguard is a greenfield multi-tenant conversational RAG over internal documents (PRD), with a complete target design (ARCHITECTURE.md, DESIGN.md, ADR-0001..0006) and configured bootstrap tooling, but **zero application source and zero tests**. The first MVP slice must be the smallest spec-worthy, end-to-end change that later retrieval work can build on. The recommended slice is **`mvp-authz-foundation`**: the tenant + org-scoped RBAC/auth foundation (data model `tenants`/`users`/`roles`/`memberships`, JWT authentication, the single authz-resolution function, and the security/authorization test suite that is an explicit release gate). This recommendation is **validated**, not merely inherited: ADR-0002's action items order the authorization test suite *first*; the ERD root tables have no dependencies on any other table; every later capability (ingestion, retrieval, chat, citations, UI) requires tenant-scoped identity; and the slice fits the 400-line review budget. No product decision blocks this slice — open decisions that concern later slices (retention, deletion, chunking/RRF, embedding provider, evaluation-harness location, RLS, rate limits) are surfaced and deliberately left to their owning slices.

## Current State

- **Bootstrap complete; implementation pending.** Branch `chore/setup-project` with pre-existing uncommitted bootstrap changes (must never be reset/discarded). No commits, pushes, or PRs in this phase.
- **No application source or tests exist.** Verified by CodeGraph (index contains config/docs only) and by inspection:
  - `apps/api` — `pyproject.toml` only (FastAPI, SQLAlchemy 2 async, psycopg3, pgvector, PyJWT, pydantic-settings, python-multipart, uvicorn, redis[hiredis], arq, boto3) + empty `tests/{unit,integration,e2e}/`.
  - `apps/worker` — `pyproject.toml` only (arq, boto3, pgvector, psycopg, SQLAlchemy, pydantic-settings) + empty test skeletons.
  - `apps/web` — tooling config only (`package.json`, vite/vitest/playwright configs); **no `src/`**, no routes, no components.
- **Target design is complete and authoritative**: `PRD.md` (product source of truth), `ARCHITECTURE.md` (system/API target), `DESIGN.md` (UI target), `docs/adr/ADR-0001..0006` (accepted). All describe behavior that does not exist yet.
- **Local infra configured** (`infra/compose.yaml`): `pgvector/pgvector:0.8.6-pg17` (HNSW builds need `shm_size 1gb`), `redis:8.10.0-alpine`, `minio` pinned (local-development-only caveat; S3/R2 are production targets), Caddy behind the `proxy` profile routing `/api` → API and `/` → web. `.env` does not exist yet; `.env.example` defines required vars.
- **Quality/CI configured**: ruff (E,F,I,UP,B, line 100), biome 2.5.7, lefthook hooks (pre-commit lint/format, pre-push pytest + vitest), `.github/workflows/ci.yml` (JS + Python jobs, conditional coverage), `.github/workflows/pr-check.yml` (400-line review budget, issue-reference + `status:approved` + single `type:*` label gates).
- **Test conventions** (`openspec/config.yaml` + pyproject): pytest markers `unit`/`integration`/`e2e`, `addopts -m 'not e2e'`, `asyncio_mode=auto`; `uv run pytest -m 'not e2e'` and `pnpm test`; vitest + @testing-library/react (jsdom), Playwright chromium E2E. Strict TDD enabled; zero tests exist (suites start empty per layer).
- **SDD state**: `openspec/` initialized (`config.yaml`, empty `specs/`, empty `changes/archive/`). This is the **first change**. Engram holds `sdd-init/raguard` and `sdd/raguard/testing-capabilities`.

## User / Product Problem

The user (Spanish-speaking, technical artifacts in English) asked to review the project and begin building its MVP with SDD. The product problem (PRD §2): organizations cannot reliably answer questions from their own documents — manual search is slow, generic LLM chat hallucinates and ignores organizational boundaries. The MVP (PRD §4) is multi-tenant ingestion of PDF/Markdown, permission-filtered hybrid retrieval, chat with verifiable citations, and a precision evaluation harness. The problem *this slice* solves: before any document, retrieval, or answer can exist, the system needs a tenant model, org-scoped identity, and role-based authorization that makes the PRD's non-negotiable invariants (retrieval-level filtering, single-tenant scoping, citation verifiability) *possible* — and a security test suite proving isolation as a release gate (ADR-0002 action item #1).

## Affected Areas

- `apps/api/` — **new source created**: SQLAlchemy models + Alembic-style migration for `tenants`/`users`/`roles`/`memberships` (per ARCHITECTURE ERD), JWT auth service (login/verify), authz-resolution service (token → tenant + role grants → authorization scopes), FastAPI routers (`/api/auth`, `/api/org`-scoped admin routes), first-admin bootstrap, `apps/api/tests/{unit,integration}/` security suite.
- `apps/api/pyproject.toml` — likely add one password-hashing dependency (design-phase choice; e.g., argon2-cffi or pwdlib).
- `apps/worker/pyproject.toml` — **not affected** in this slice (worker starts with the ingestion slice).
- `infra/compose.yaml` — PostgreSQL service consumed by integration tests; no change required unless a named volume/reset helper is added for test isolation (design decision).
- `docs/adr/0002-retrieval-level-authorization.md` — its action items #1/#2 (build authz test suite first; define the single authz-resolution function) are the mandate this slice fulfills.
- `openspec/specs/` — future main spec for the IAM/authorization domain once this change archives.
- `ARCHITECTURE.md`, `DESIGN.md`, `PRD.md` — read-only here; owned by `design-architecture`/`design-ui` (docs update under explicit assignment only, per their activation contracts).

## Candidate MVP Slices (Dependency Chain)

| # | Slice | What it delivers | Depends on | Effort | First? |
|---|-------|------------------|------------|--------|--------|
| A | **`mvp-authz-foundation`** | tenants/users/roles/memberships, JWT login, authz-resolution function, security test suite (cross-tenant/cross-role release gates) | nothing (root tables) | Medium | **Yes — recommended** |
| B | `mvp-ingestion` | document upload, worker parse/chunk/embed/index, status lifecycle | A (tenant-scoped documents, admin role for upload) | High | No |
| C | `mvp-retrieval` | FTS + vector + RRF, permission-filtered at query time | A + B (chunks) | High | No |
| D | `mvp-chat-citations` | chat orchestration, provider adapters, citation verification | A + C | High | No |
| E | `mvp-eval-harness` | offline precision/citation evaluation | A + C (needs corpus + retrieval) | Medium | No (location open) |
| F | `mvp-web-ui` | React app: login, chat, citations, admin | A + D (API surface) | High | No |

**Chain logic**: A gates everything — without tenants/users/roles there is nothing to scope documents to, no JWT identity to resolve, and no way to write the cross-tenant leak scenarios that are release gates. B then C then D build the vertical slice; E gates C/D quality; F consumes the API.

## Recommendation — Why `mvp-authz-foundation`

Repository evidence, not convention, supports starting with the authz foundation:

1. **ADR-0002 mandates it**: action item #1 is "Build the security/authorization test suite first: cross-tenant, cross-role, and adversarial-document scenarios are release gates"; #2 is "Define the single authz resolution function (token → tenant + role grants → SQL predicates) and require all retrieval routes to use it." The first slice should implement exactly those.
2. **The ERD's root tables are dependency-free**: `tenants`, `users`, `roles`, `memberships` reference nothing else; every other table (`documents`, `chunks`, `conversations`, `messages`) carries `tenant_id` and presupposes them.
3. **The product invariants are authorization invariants**: retrieval-level filtering, single-tenant scoping, citations to authorized chunks. They cannot even be *stated as tests* until identity + roles + tenant scoping exist.
4. **Smallest working end-to-end product slice** (AGENTS.md: grow in layers, start from the smallest version that works): an admin seeds a tenant, adds users, assigns roles; a user logs in; the authz resolver returns role-granted scopes; the security suite proves cross-tenant/cross-role isolation. API-level complete and verifiable without any later slice.
5. **Fits the review budget**: a focused IAM slice stays inside the 400-line PR budget (`pr-check.yml`) and the `auto-chain` delivery strategy; retrieval/ingestion slices are inherently larger and better as chained follow-ups.

Rejected alternatives: starting with ingestion (B) has no tenant scoping or roles to attach documents to and cannot demonstrate the no-leakage invariant; starting with retrieval (C) or chat (D) violates the dependency chain and would bolt authz onto a security-critical path as an afterthought — exactly what ADR-0002 warns against.

## Scope Boundaries

### In Scope (this change)

- Schema + migration: `tenants`, `users` (email, `password_hash`), `roles` (tenant-scoped, name), `memberships` (user ↔ tenant ↔ role) per ARCHITECTURE ERD; composite `(tenant_id, …)` leading indexes.
- Role/capability model: default `admin` + `member` roles with a capability matrix (manage org settings, manage users, manage documents, view document corpus, chat access per DESIGN.md); custom roles allowed; **per-document grants deferred** to the documents slice (they reference `document_id`, which does not exist yet).
- Authentication: JWT issue at login (email + password, verifiable hash), verify + expiry on every request; tenant resolved from the verified token — **never from client-supplied values**.
- Authorization: the single authz-resolution function (token → tenant + memberships + role grants → authorization scopes) that later retrieval routes must use; resolved **fresh per request** (no caching — ARCHITECTURE caching strategy).
- First-admin bootstrap: admin-driven tenant provisioning per PRD non-goal (no self-serve signup); first tenant + admin seeded via env/CLI bootstrap command.
- Security/authorization test suite: cross-tenant and cross-role isolation tests on the data model and authz resolver; these are release-gate scenarios (ADR-0002, PRD KPI 2: 0 auth violations).
- API error envelope convention `{error: {code, message, details?}}` applied to the new routes.
- Unit + integration layers only; strict TDD (RED-GREEN-REFACTOR) with `uv run pytest -m 'not e2e'`.

### Out of Scope (explicit, later slices)

- Documents, upload, ingestion, worker process, Redis/Arq jobs (slice B).
- Retrieval, FTS/vector, RRF fusion (slice C).
- Chat, citations, citation verification, provider adapters, any LLM call (slice D).
- Evaluation harness (slice E; in-repo-vs-separate is an open decision).
- Web UI (slice F); `apps/web` untouched in this change.
- PostgreSQL Row-Level Security (ARCHITECTURE open decision #6 — never the primary control; not adopted in the MVP).
- Email invites (admin creates users directly in the MVP; invite-by-email is a DESIGN.md contract point to confirm at API build, not MVP-mandatory).
- Exact rate-limit values (config-phase decision; a trivial login throttle may be included, value set at design).
- Any change to `ARCHITECTURE.md`/`DESIGN.md`/`PRD.md`/ADRs (doc updates only under explicit assignment).

## Assumptions (narrowest reversible) & Unresolved Decisions

**No product decision blocks this slice.** The narrowest reversible assumptions taken (recorded, not silently decided):

| Assumption | Rationale | Reversibility |
|---|---|---|
| Tenant provisioning is admin-driven; first tenant + admin via env/CLI seed | PRD §7 non-goal: no self-serve signup; PRD §10 default is admin-invited | Low cost to add invites/self-serve later |
| JWT carried as same-domain cookie (Caddy) per DESIGN.md; verify logic token-agnostic (cookie or Bearer) | ARCHITECTURE leaves cookie-vs-Bearer to config-time conventions; Caddy is same-domain | Reversible at API build |
| Password hashing with a vetted library (argon2 or bcrypt family) | PRD specifies `password_hash`; no homebrew crypto | Library choice at design |
| Capability matrix on roles; per-document grants deferred to documents slice | ADR-0002: "keep the grant model simple in the MVP" | Extend model when documents land |
| Authz resolved fresh per request, never cached | ARCHITECTURE caching strategy (stale permissions violate the invariant) | Revisit only with explicit revocation timing |

**Surfaced open product decisions (deliberately NOT decided here — they belong to their owning slices and are listed so the orchestrator can report them):**

1. Chat history persistence + retention → chat slice.
2. Document deletion semantics (immediate purge vs soft) → documents/ingestion slice.
3. Chunking strategy + RRF weights → retrieval slice (tuned against evaluation set).
4. Evaluation harness in-repo vs separate tool → evaluation slice.
5. PostgreSQL RLS as defense-in-depth → security review; never for MVP as primary control.
6. Rate limits exact values → config phase.
7. Embedding provider policy (OpenAI default via adapter) → ingestion slice.
8. Review-budget ambiguity: session `review_budget_lines: 800` vs `pr-check.yml` 400-line gate → orchestrator should confirm with the user before `sdd-tasks` forecasts PR chaining.

## Constraints & Invariants (non-negotiable)

- **Authorization invariant**: retrieval-level filtering before generation; this slice builds the identity/role substrate the invariant requires and the security suite that enforces it. Any change weakening authorization is a release blocker (PRD §5, ADR-0002).
- **Tenant isolation**: a query is scoped to exactly one tenant; tenant identity comes only from the verified JWT; no code path accepts client-supplied tenant/org identity.
- **Citation invariant** (future slice): must not be precluded — authz scopes must be expressible as SQL predicates that later retrieval queries can reuse.
- **Document content is untrusted data** (future slices): not exercised in this slice; security-test discipline starts here.
- **No UI hiding as a control** (future): the API is authoritative from day one.
- Repository rules: never reset/discard uncommitted bootstrap changes; no commits/pushes/PRs in this phase; English technical artifacts; conventional commits; strict TDD.

## Risks

| Risk | Mitigation |
|---|---|
| Scope creep into documents/retrieval ("while we're here") | Explicit out-of-scope boundary above; dependency chain keeps later slices separate changes |
| Authz-resolution function becomes the security-critical module | ADR-0002 discipline: single function, all retrieval routes must use it; cross-tenant/cross-role tests are release gates |
| JWT/password implementation flaws | Vetted libraries only (PyJWT already a dependency; argon2/bcrypt added); no hand-rolled crypto; expiry + verification tests |
| Integration tests require the local compose stack (PostgreSQL) | Marker split already enforced (`integration` vs `unit`); CI runs non-e2e; document stack requirement in the spec |
| 400-line review budget pressure on a schema-heavy change | Migration + models are compact; chain sub-slices via `auto-chain` if `sdd-tasks` forecasts overflow |
| First-admin bootstrap ambiguity (who creates the first user?) | Explicit assumption + bootstrap command spec'd in the proposal/design |

## Ready for Proposal

**Yes.** The orchestrator should:
1. Confirm the change slug `mvp-authz-foundation` and proceed to `sdd-propose`.
2. Report the open decisions listed above as *surfaced, not resolved* (especially #8: the 400-vs-800 review-budget question, which affects `sdd-tasks` chaining forecast).
3. Note that `docs/adr/0002` action items #1/#2 are the mandate for this change.
