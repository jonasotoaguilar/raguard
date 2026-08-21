# Proposal: MVP Chat with Verifiable Citations

## Intent

Authorized retrieval exists, but no answer path does. Add the smallest API slice for grounded answers with verifiable citations.

## Product Outcome

Members receive an answer with citations or a neutral no-evidence response. Unauthorized content never reaches generation or citations.

## Scope

### In Scope
- Add request-scoped `POST /api/chat`: bounded `{query, top_k}`, `{answer, citations}`, and `chat.use` authorization.
- Share tenant-filtered retrieval orchestration between `/api/search` and `/api/chat`, preserving search behavior.
- Define a narrow `ChatCompleter`: OpenAI only, bounded provider behavior, and injectable fakes.
- Delimit retrieved content as untrusted prompt data; verify citations against the exact retrieved membership.
- Empty retrieval skips generation and returns neutral 200; provider/citation failures use the safe envelope.

### Out of Scope
- Persisted conversations/history, follow-ups, migrations, retention, and deletion: open product decisions.
- Anthropic implementation and streaming/SSE: deferred.
- Evaluation harness and UI: later consumers of this API.
- Per-document grants and PostgreSQL RLS: deferred authorization decisions; tenant/RBAC filtering remains primary.
- Worker, document-lifecycle, and product/design documentation changes.

## Capabilities

### New Capabilities
- `chat`: Request-scoped authorized answers with verifiable citations.

### Modified Capabilities
- None — `retrieval` and `authorization-rbac` requirements stay unchanged; extraction is behavior-preserving.

## Approach

Reuse fresh authorization, hybrid retrieval, the error envelope, and the OpenAI dependency. Keep prompt assembly outside the adapter, parse bounded markers, reject non-membership citations, and test fakes, adversarial documents, and isolation offline.

## Decision Assumptions

Request scope, configurable OpenAI `gpt-4o-mini`-class model, numbered citations, neutral empties, and bounded 503 failure are reversible defaults. Rate limits, history, deletion, RLS, grants, Anthropic, and evaluation ownership remain open.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `apps/api/src/raguard_api/chat/` | New | Contracts, prompt, verifier, provider, route. |
| `apps/api/src/raguard_api/retrieval/` | Modified | Shared orchestration; search compatible. |
| `apps/api/src/raguard_api/config.py`, `main.py` | Modified | Settings and wiring. |
| `apps/api/tests/` | New | Unit, isolation, adversarial, failure, provider gates. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Search regression | Med | Existing route and isolation tests. |
| Injection or sensitive disclosure | High | Authz-first retrieval, untrusted delimiters, output checks, adversarial tests. |
| Cost, latency, or citation fragility | Med | Bounds, empty short-circuit, bounded failure, membership rejection. |

## Compatibility & Rollback

This adds one endpoint with no migration or worker changes. Revert stacked slices in reverse order; no cleanup is required. If extraction regresses search, revert that slice independently and do not deploy chat.

## Delivery Direction

Stacked-to-main units: shared retrieval/contracts; provider and prompt/citation core; route/wiring; isolation and provider gates.

## Dependencies

Existing authz/retrieval modules, PostgreSQL corpus, and the `openai` dependency.

## Success Criteria

- [ ] Authorized answers cite only retrieved authorized chunks.
- [ ] Empty/no-match retrieval makes zero provider calls and returns the neutral response.
- [ ] Invalid input, missing `chat.use`, provider failure, and invalid citations use safe standardized errors.
- [ ] Existing search behavior remains passing; adversarial and cross-tenant gates pass.
