# Proposal: MVP Authz Foundation — Tenant + Org-Scoped RBAC/Auth

## Intent

Problem (PRD §2): orgs cannot reliably answer questions from their own documents; generic LLM chat ignores org boundaries. This slice builds the substrate every later slice needs — tenant model, org-scoped identity, RBAC, and the isolation security suite ADR-0002 mandates first (action items #1/#2). Repo is bootstrap-only (no source/tests); ERD root tables are dependency-free. Outcome: admin provisions tenants/users/roles; user logs in via expiring JWT; single authz-resolution function returns role-granted scopes per request; cross-tenant/cross-role leak tests pass as release gates.

## Scope

### In Scope
- Schema + migration: tenants, users (email, password_hash), tenant-scoped roles, memberships; composite (tenant_id, …) indexes (ARCHITECTURE ERD).
- JWT auth: login (email+password, vetted hash lib at design), verify + expiry per request; tenant only from verified token.
- Single authz-resolution function (token → tenant + memberships + role grants → scopes); fresh per request, never cached.
- Capability matrix: default admin/member + custom roles (DESIGN.md); per-document grants deferred.
- First-admin bootstrap via env/CLI seed (admin-driven provisioning, PRD non-goal).
- Error envelope on new routes; unit + integration security suite (isolation = release gates).

### Out of Scope
- Slices B–F: documents/ingestion/worker, retrieval/RRF, chat/citations/LLM, eval harness, web UI.
- PostgreSQL RLS, email invites, rate-limit values; no edits to PRD/ARCHITECTURE/DESIGN/ADRs.

## Capabilities

Contract for sdd-spec; specs/ empty — first change, all new.

### New Capabilities
- tenant-identity: tenants/users/roles/memberships model, migration, indexes, first-admin bootstrap.
- jwt-authentication: login, token issue/verify/expiry; tenant from verified token only.
- authorization-rbac: capability matrix; single fresh authz resolution; scopes as SQL predicates (citation-compatible); error envelope.

### Modified Capabilities
None.

## Approach & Constraints

SQLAlchemy 2 async models + migration; auth/authz services behind /api/auth and /api/org; CLI/env bootstrap; tests in apps/api/tests/{unit,integration}; strict TDD, uv run pytest -m 'not e2e'. Invariants: tenant from verified auth only; tenant+role filtering before generation; scopes reusable as SQL predicates (citation invariant preserved); no UI-only authorization; document content untrusted. Never reset/rewrite uncommitted bootstrap state.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| apps/api/ | New | Models, migration, services, routers, bootstrap |
| apps/api/pyproject.toml | Modified | Password-hashing dependency |
| apps/api/tests/{unit,integration}/ | New | Security suite |
| infra/compose.yaml | Modified* | *Test-isolation helper only (design) |

## Unresolved Product Decisions

Surfaced, not resolved — owning slices: chat retention (chat); deletion (ingestion); chunking/RRF (retrieval); eval-harness location (eval); RLS backstop (security review); rate limits (config); embedding provider (ingestion); invite-by-email (API build).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope creep into later slices | Med | Explicit boundaries; dependency chain |
| Authz function = security-critical | Med | Single function; leak tests as gates |
| JWT/password flaws | Med | Vetted libraries; expiry/verify tests |
| Integration tests need local PG | Med | Marker split; stack documented |
| 400-line PR gate vs 800-line session budget | High | Delivery risk flagged; sdd-tasks forecasts chaining — not resolved here |
| First-admin bootstrap ambiguity | Low | Documented assumption; spec'd at design |

## Rollback Plan

Greenfield, no production data. Revert the PR; if migration ran, down-migration drops the four tables (no dependents). Seed idempotent; no backfill; no feature flag (API unreachable without tables).

## Dependencies

Local compose PostgreSQL 17 (integration); PyJWT (existing); hashing lib at design; uv workspace.

## Success Criteria

- [ ] Cross-tenant and cross-role isolation tests green (release gate, PRD KPI 2)
- [ ] Expiring JWT at login; forged/expired/invalid rejected; tenant only from token
- [ ] All new routes use the single fresh authz resolution function
- [ ] First-admin bootstrap idempotent; error envelope on all new routes
- [ ] uv run pytest -m 'not e2e' and ruff clean
