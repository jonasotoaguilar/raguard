# Authorization RBAC Specification

## Purpose

Org-scoped role-based authorization: the capability matrix over default and custom roles, the single authz-resolution function returning role-granted scopes fresh per request, scopes composed into SQL predicates so future retrieval and citations stay authorized (ADR-0002 action item #2), the release-gate isolation suite (PRD KPI 2), and the error envelope on all new routes. New domain — first change, no prior spec.

## Requirements

### Requirement: Capability matrix on roles

The system MUST provide default roles `admin` and `member` and MUST support tenant-scoped custom roles. Roles MUST grant capabilities from the DESIGN.md matrix: manage org settings, manage users, manage documents, view document corpus, chat access. `admin` MUST grant all capabilities; `member` MUST grant view document corpus and chat access.

#### Scenario: Admin performs admin-only action

- GIVEN an authenticated admin of tenant A
- WHEN the admin lists users or updates a role
- THEN the action succeeds

#### Scenario: Member denied admin-only action

- GIVEN an authenticated member of tenant A
- WHEN the member lists users or updates a role
- THEN the action fails with the error envelope (403) and nothing changes

### Requirement: Single authz-resolution function

All protected routes MUST obtain authorization through one resolution function: verified token → tenant + memberships + role grants → granted scopes. Resolution MUST run fresh per request and MUST NOT be cached (ARCHITECTURE caching strategy — stale permissions violate the invariant). No route MAY bypass the function with ad-hoc checks.

#### Scenario: Fresh resolution reflects role change

- GIVEN a member granted a new capability
- WHEN the member's next request is resolved
- THEN the new scope is granted without restart or cache invalidation

#### Scenario: All routes use the single function

- GIVEN the set of protected routes
- WHEN each is exercised with a valid token
- THEN every authorization decision comes from the resolution function

### Requirement: Scopes as SQL predicates

The resolution function MUST return scopes expressible as SQL predicates (e.g., `tenant_id = ?` plus role-granted conditions) that future retrieval queries apply before generation, keeping citations resolvable only to authorized chunks. Predicates MUST be derived server-side from verified identity.

#### Scenario: Scope composes into a query predicate

- GIVEN a resolved scope for a tenant member
- WHEN the scope is rendered as a SQL predicate
- THEN it constrains results to the member's tenant and role-granted set
- AND the predicate is parameterized, never concatenated from client input

### Requirement: Release-gate isolation

The system MUST deny every cross-tenant and cross-role access attempt: a tenant A member MUST NOT read tenant B data; a `member` MUST NOT perform admin-only actions; denials MUST NOT disclose existence. These scenarios are release gates (PRD KPI 2: zero authorization violations).

#### Scenario: Cross-tenant access denied (release gate)

- GIVEN memberships in tenants A and B
- WHEN the tenant A member requests tenant B data via any route
- THEN the request fails with the error envelope and no tenant B data is returned

#### Scenario: Cross-role escalation denied (release gate)

- GIVEN a member without admin capabilities
- WHEN the member calls an admin-scoped route in their own tenant
- THEN the request fails with the error envelope (403)

### Requirement: Error envelope on new routes

All new routes MUST return errors as `{error: {code, message, details?}}`: 401 unauthenticated/invalid token, 403 authenticated-but-unauthorized, 400 invalid input, 404/409 resource state. The envelope MUST NOT leak tenant existence or internal details.

#### Scenario: Standardized error responses

- GIVEN requests that fail for invalid input, invalid token, and missing permission
- WHEN each is processed
- THEN every response matches the error envelope with the correct code

### Requirement: Untrusted document boundary

Authorization MUST treat document content as untrusted data (PRD §6, ADR-0005): no authz decision MAY trust or execute document-derived content. This slice does not ingest documents; the boundary is recorded so ingestion and retrieval slices keep adversarial-document tests release-gated.

#### Scenario: Boundary recorded for later slices

- GIVEN the authorization module
- WHEN a later slice introduces document-derived input
- THEN authorization still derives exclusively from verified identity and role grants

## Deferred Decisions

Not resolved here — owning slices: per-document grants (documents), RLS backstop (security review), rate-limit values (config), invite-by-email (API build), chat retention (chat), document deletion (ingestion), chunking/RRF (retrieval), evaluation location (eval), embedding provider (ingestion).
