# ADR-0002: Retrieval-Level Authorization and Tenant Isolation

## Status

Accepted (user-approved; PRD invariant — target design for a greenfield repository, no implementation exists yet)

## Date

2026-08-04

## Deciders

Jonathan Soto (jonasotoaguilar)

## Context

The PRD's non-negotiable invariant: **every tenant/user/role can retrieve only authorized chunks; permission filtering occurs before generation, and citations must resolve to authorized retrievable chunks.** Cross-tenant or cross-role leakage is the worst-case failure mode of the product and a release blocker. The forces: (1) authorization must hold even if the UI hides nothing, (2) the LLM must never see un-authorized content — generation-side filtering alone is unacceptable because a model can leak what it was given, (3) enforcement must survive refactors and be testable as a first-class security scenario, (4) the system must still be operationally simple (thin custom JWT, org-scoped RBAC).

## Decision

Enforce authorization in layers, with **retrieval-level filtering as the primary control**:

1. **Identity**: thin custom JWT issued at login, carrying user id and tenant id; every request resolves its tenant from the verified token — never from client-supplied values.
2. **AuthZ resolution**: per request, resolve the user's role(s) within the tenant (org-scoped RBAC) into the set of authorized documents/chunks.
3. **Retrieval filtering (primary)**: tenant id and role/document grants are predicates of the retrieval queries themselves (both FTS and vector signals, and the RRF fusion). Un-authorized chunks cannot be retrieved, cannot enter the prompt, cannot be cited.
4. **Citation verification (secondary)**: after generation, each citation must resolve to a chunk id present in the authorized retrieval result; otherwise the message is rejected before persisting/rendering.
5. **UI hiding is not a control**: the web app only renders what the API returns.

## Consequences

### Positive

- The invariant is enforced in code paths that tests can drive end-to-end (security test suite: cross-tenant and cross-role leak scenarios are release gates).
- The LLM never receives un-authorized content, which is the only defense that actually works against model leakage.
- Citations are verifiable by construction: they are re-checked against the authorized result set after generation.
- Simple mental model: one retrieval path, one authz function.

### Negative

- Authorization cost is paid on every retrieval (scope resolution + filtered queries); acceptable at MVP volume, to be measured.
- The retrieval path becomes the security-critical module: it needs careful ownership and review discipline.
- Complex document-permission models (per-document grants vs role-granted sets) must be expressed inside SQL predicates; keep the grant model simple in the MVP.

### Neutral

- Tenant id appears in most queries — a deliberate and explicit cross-cutting concern.

## Options Considered

### Option A: Post-filtering after retrieval (candidate — rejected)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Security | Unacceptable |
| Scalability | Wasted retrieval work |
| Team familiarity | High |
| Operational overhead | Low |

**Pros:** simplest implementation.
**Cons:** retrieves un-authorized content before discarding it — violates the invariant if any consumer (e.g., prompt building) reads the pre-filtered list; also leaks existence information via timing/result counts.

### Option B: Authorization enforced only via PostgreSQL Row-Level Security
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium–High (session tenant context with pooled connections) |
| Security | Strong backstop |
| Team familiarity | Medium |
| Operational overhead | High (connection/session state management, per-tenant SETs, edge cases) |

**Pros:** DB-enforced, hard to bypass accidentally.
**Cons:** requires careful connection/tenant-context handling (session-level `app.tenant_id` with pooled async connections), complicates the connection pool, and is brittle under connection reuse bugs. Keeping it the *only* control concentrates risk in one clever mechanism.

### Option C: Retrieval-level filtering + citation verification (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Security | Strong (defense-in-depth, testable) |
| Team familiarity | High |
| Operational overhead | Low |

**Pros:** the filtering is plain SQL predicates on tenant/grants — obvious to review; verification re-checks citations against the authorized set; works with normal pooled connections.
**Cons:** the application layer must never be bypassed by a new code path; mitigated by the security test suite.

### Option D: Optional RLS as an additional defense-in-depth layer (open)
| Dimension | Assessment |
|-----------|------------|
| Complexity | High if adopted now |
| Security | Adds a DB-level backstop |
| Team familiarity | Medium |
| Operational overhead | High |

**Pros:** genuine defense-in-depth.
**Cons:** MVP-visible complexity for a backstop; if adopted, it must be layered on top of Option C, never instead of it. Recorded as an open decision in ARCHITECTURE.md.

## Trade-off Analysis

Option A fails the product's core invariant outright. Option B is a strong mechanism but operationally risky as the sole control (pooling + session state) and opaque to review. The chosen combination — filtering inside the retrieval queries plus citation verification after generation — makes the invariant enforceable, reviewable, and testable with plain SQL and normal connection pooling, at a modest per-request cost. RLS remains a candidate future backstop only because it must never be the primary control.

## Action Items

1. [ ] Build the security/authorization test suite first: cross-tenant, cross-role, and adversarial-document scenarios are release gates.
2. [ ] Define the single authz resolution function (token → tenant + role grants → SQL predicates) and require all retrieval routes to use it.
3. [ ] Implement citation verification as a post-generation check in the chat path.
4. [ ] Revisit RLS as defense-in-depth only after the retrieval path is proven; record the decision in ARCHITECTURE.md.

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Tenant Isolation & Authorization, Runtime Flow — Chat & Retrieval
- [PRD.md](../PRD.md) — Invariants (Authorization, Citation), Security Requirements
- Related ADRs: [ADR-0003](0003-postgres-fusion-hybrid-retrieval.md) (the retrieval path that carries the filtering)
