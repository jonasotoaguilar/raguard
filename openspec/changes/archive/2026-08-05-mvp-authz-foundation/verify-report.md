```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:d877f0ac666ddec5e901fadc6b0b4a7e65b8942c6145d4c7d2d33c3f9c6f3735
verdict: pass
blockers: 0
critical_findings: 0
requirements: 15/15
scenarios: 25/25
test_command: "POSTGRES_PORT=55432 uv run pytest -m 'not e2e' && pnpm test"
test_exit_code: 0
test_output_hash: sha256:e67b35ff79a78e228e697b865ab6ef268c1a722974b000838ad72c798be94f3c
build_command: "uv run ruff check . && uv run ruff format --check . && pnpm exec biome check . && DATABASE_URL=postgresql+psycopg://raguard:change-me@127.0.0.1:55432/raguard uv run alembic -c apps/api/alembic.ini check"
build_exit_code: 0
build_output_hash: sha256:564cbba71354daa5089662e2662fe154beefd963919f1d8871aa730f9fa07e48
```

## Verification Report

**Change**: mvp-authz-foundation  
**Version**: N/A — three new capability specifications  
**Mode**: Strict TDD; hybrid artifact store; independent re-verification after scoped remediation  
**Native runtime**: sha256:d877f0ac666ddec5e901fadc6b0b4a7e65b8942c6145d4c7d2d33c3f9c6f3735; work unit independent-sdd-reverify; max changed lines 20

### Completeness

| Metric | Value |
|---|---:|
| Proposal/spec/design/tasks | Complete; proposal, 3 specs, design, and tasks read from OpenSpec |
| Apply progress | Engram observation #4827 read in full; remediation R.1–R.3 complete |
| Tasks total | 59 |
| Implementation/remediation tasks complete before verification | 58 |
| Tasks pending before verification | 1 — final Gate marker |
| Final Gate | [x] marked after all checks passed |

### Build & Tests Execution

**Full PG55432 test gate**: PASS — POSTGRES_PORT=55432 uv run pytest -m 'not e2e' collected 95 and passed 95; pnpm test exited 0 with no web test files. Combined exit 0; output hash sha256:e67b35ff79a78e228e697b865ab6ef268c1a722974b000838ad72c798be94f3c.

**Independent malformed-credential probe**: PASS — three direct ASGI requests against the current app with password values shaped as dict, list, and nested-like dict containing input/ctx/url/exception objects. All returned 400 invalid_request; every public detail retained only loc/type/msg; all diagnostic fields were non-empty; supplied markers and forbidden object keys were absent. Exit 0; output hash sha256:4b39b6775ba53fab1933f1a853d38de160789833674c09fc41cd4953beb494fd.

**Focused remediation regression**: PASS — POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_login.py -v, 9 passed, exit 0; output hash sha256:4699067dc9c927cdbf6f2a70aca01f2b3812c10fd34fc636f8048f09f618273f.

**Independent protected-route token harness**: PASS — real disposable PostgreSQL database; valid token 200, expired/forged/tampered tokens 401 authentication_failed, and invalid responses contained no tenant data. Migration/bootstrap/down cleanup all exited 0; output hash sha256:fd71b5beb6f12bcdb16e0d60bc56bd7787d9c80834c443b98435e0b0055e9650.

**App factory smoke**: PASS — test_app_factory.py, 4 passed, exit 0; output hash sha256:4f923f1d8f5e57ede4b61dce5131f28c3a3a32f890f504fddaf51f6ee3cc81a7.

**Bootstrap suite**: PASS — test_bootstrap.py, 13 passed, exit 0; output hash sha256:a7cd98f8cb129fcdca46c62b1192b557be0d3edf6bdb396c1f8caf2753a26db6.

**Actual bootstrap CLI smoke**: PASS — disposable PostgreSQL migration up/down, first CLI run 0, idempotent rerun 0, invalid environment 2, final rows [1,1,2,1], no bootstrap secret or email in captured CLI output; wrapper output hash sha256:b31ffce44a34459ad74417599d4e82860db6c5232b3ef19c43276241936b9e5e; subprocess evidence hash sha256:a2f2b6ae80827b4ddf38fdce4abcebf56ac879cf21abe3a192c733b1b6c446ec.

**Quality/build gate**: PASS — exact command uv run ruff check . && uv run ruff format --check . && pnpm exec biome check . && DATABASE_URL=postgresql+psycopg://raguard:change-me@127.0.0.1:55432/raguard uv run alembic -c apps/api/alembic.ini check exited 0; Ruff clean, 48 files formatted, Biome clean, and Alembic reported no new upgrade operations. Output hash sha256:564cbba71354daa5089662e2662fe154beefd963919f1d8871aa730f9fa07e48.

**Coverage**: Not available — pytest-cov and @vitest/coverage-v8 are not installed; configured threshold is 0.  
**Type checker**: Not available — Python mypy is not configured and no TypeScript source/tsconfig participates in this change.

### Spec Compliance Matrix

| Spec requirement | Scenario | Runtime test/code evidence | Result |
|---|---|---|---|
| tenant-identity / Tenant-scoped identity model | Fresh migration creates the identity schema | test_up_creates_identity_tables; test_up_creates_composite_indexes_leading_with_tenant_id; test_down_drops_identity_tables_without_affecting_others; CLI migration up/down | COMPLIANT |
| tenant-identity / Tenant-scoped identity model | Email uniqueness is enforced | test_email_unique_globally passed and duplicate count remained one | COMPLIANT |
| tenant-identity / Tenant-scoped roles | Same role name succeeds in two tenants | test_role_name_unique_within_tenant | COMPLIANT |
| tenant-identity / Tenant-scoped roles | Cross-tenant role grant is denied without mutation | test_cross_tenant_role_grant_denied | COMPLIANT |
| tenant-identity / First-admin bootstrap | Idempotent seed creates no duplicates or resets | test_bootstrap_rerun_is_idempotent_and_preserves_rows; CLI rerun smoke | COMPLIANT |
| tenant-identity / First-admin bootstrap | Existing identity data is a successful no-op | test_bootstrap_with_existing_identity_data_is_a_noop | COMPLIANT |
| tenant-identity / Cross-tenant isolation | Cross-tenant read is denied without disclosure | test_cross_tenant_user_read_is_neutral_404 | COMPLIANT |
| tenant-identity / Cross-tenant isolation | Cross-tenant mutation is denied and unchanged | test_cross_tenant_membership_mutation_denied_and_unchanged | COMPLIANT |
| jwt-authentication / Password verification with vetted hashing | Valid credentials authenticate | test_login_issues_thin_jwt_in_httponly_cookie; Argon2id unit tests | COMPLIANT |
| jwt-authentication / Password verification with vetted hashing | Wrong password is rejected | test_wrong_password_and_unknown_email_are_indistinguishable | COMPLIANT |
| jwt-authentication / Password storage and secrecy | Failed login discloses no password, hash, supplied value, or existence hint | malformed-password regression cases plus independent dict/list/nested-like probe; no forbidden keys or markers public | COMPLIANT |
| jwt-authentication / Token issuance at login | Login returns a thin signed token with DB-derived identity and future expiry | test_login_issues_thin_jwt_in_httponly_cookie; test_issued_token_has_required_claims_fixed_alg_and_no_permissions; test_issued_token_verifies_with_configured_secret | COMPLIANT |
| jwt-authentication / Per-request verification | Expired token is rejected | test_expired_token_rejected; independent protected-route harness | COMPLIANT |
| jwt-authentication / Per-request verification | Forged token is rejected | test_forged_token_rejected; independent protected-route harness | COMPLIANT |
| jwt-authentication / Per-request verification | Tampered claims are rejected | test_tampered_tenant_claim_rejected; independent protected-route harness | COMPLIANT |
| jwt-authentication / Tenant only from verified token | Client-supplied tenant is ignored | test_client_supplied_tenant_is_ignored in login and release-gate suites | COMPLIANT |
| authorization-rbac / Capability matrix on roles | Admin performs an admin-only action | test_admin_lists_users_of_own_tenant_only; test_admin_updates_role_capabilities | COMPLIANT |
| authorization-rbac / Capability matrix on roles | Member is denied an admin-only action | test_member_cannot_escalate_to_admin_operations | COMPLIANT |
| authorization-rbac / Single authz-resolution function | Fresh resolution reflects a role change | test_role_change_is_visible_on_next_request_with_same_token; test_authorization_derives_from_current_db_role_state_only | COMPLIANT |
| authorization-rbac / Single authz-resolution function | All protected routes use the single function | org router route dependencies all resolve through AuthorizationResolver; route suite and mounted-surface smoke passed | COMPLIANT |
| authorization-rbac / Scopes as SQL predicates | Scope composes into a parameterized tenant predicate | test_tenant_predicate_is_parameterized_expression; test_tenant_predicate_binds_requested_column_only | COMPLIANT |
| authorization-rbac / Release-gate isolation | Cross-tenant access is denied without disclosure | test_cross_tenant_user_read_is_neutral_404; test_cross_tenant_membership_mutation_denied_and_unchanged | COMPLIANT |
| authorization-rbac / Release-gate isolation | Cross-role escalation is denied | test_member_cannot_escalate_to_admin_operations | COMPLIANT |
| authorization-rbac / Error envelope on new routes | Invalid input, invalid token, and missing permission use the standard envelope | malformed-password regression; test_missing_and_invalid_cookies_return_401_envelope; test_role_update_rejects_unknown_capability_with_400; app smoke | COMPLIANT |
| authorization-rbac / Untrusted document boundary | Document-shaped content cannot influence authorization | test_untrusted_document_content_cannot_influence_authorization; test_security_boundary.py invariants | COMPLIANT |

**Compliance summary**: 25/25 scenarios compliant; 15/15 requirements complete.

### Correctness (Static Evidence)

| Requirement | Status | Evidence |
|---|---|---|
| Tenant-scoped identity model | Implemented | ORM and migration define four UUID identity tables, global email uniqueness, reversible down migration, and tenant-leading indexes. |
| Tenant-scoped roles | Implemented | Tenant/name and composite tenant/id constraints plus composite role FK prevent cross-tenant grants. |
| First-admin bootstrap | Implemented | Environment-only secrets, advisory transaction lock, atomic creation, idempotent no-op, and generic validation errors. |
| Cross-tenant isolation | Implemented | Resolver-derived tenant predicates scope every identity query; hidden targets return neutral 404. |
| Password verification with vetted hashing | Implemented | Argon2id PasswordHasher is used directly; malformed hashes fail closed without details. |
| Password storage and secrecy | Implemented | Validation details are allowlist-projected to loc/type/msg; raw input, ctx, url, exception objects, hashes, and supplied markers were absent in runtime probes. |
| Token issuance at login | Implemented | Fixed HS256 JWT carries required standard claims plus DB-derived sub/tid, not roles or capabilities. |
| Per-request verification | Implemented | Cookie-only dependency uses configured secret, issuer, audience, required claims, signature, and expiry. |
| Tenant only from verified token | Implemented | get_token_claims reads only the configured session cookie. |
| Capability matrix on roles | Implemented | Admin/member defaults and custom role capability allowlist match the five-token design matrix. |
| Single authz-resolution function | Implemented | Stateless AuthorizationResolver re-queries current membership/role state for every protected route. |
| Scopes as SQL predicates | Implemented | AuthorizationScope emits a SQLAlchemy bound equality expression rather than SQL text or inlined client input. |
| Release-gate isolation | Implemented | Real PostgreSQL route gates deny cross-tenant reads/mutations and member escalation without disclosure. |
| Error envelope on new routes | Implemented | API, validation, authentication, authorization, not-found, and generic handlers preserve the public envelope. |
| Untrusted document boundary | Implemented | Authorization consumes verified identity and current DB grants only; injection-shaped document-like fields cannot grant access. |

### Design Coherence

| Decision | Followed? | Notes |
|---|---|---|
| Modular FastAPI vertical slice | Yes | identity, auth, authorization, org, db, config, and errors remain separated. |
| Async SQLAlchemy with reversible Alembic migration | Yes | Real PostgreSQL migration and down checks passed. |
| Argon2id password hashing | Yes | Vetted argon2-cffi implementation with rehash detection. |
| Thin HS256 cookie JWT with server-derived tenant | Yes | HttpOnly, SameSite/path-scoped cookie; roles/capabilities remain out of the token. |
| Fresh resolver and parameterized scope | Yes | Resolver is stateless and scope predicates are bound SQLAlchemy expressions. |
| Advisory-lock atomic bootstrap | Yes | Focused suite and disposable real-CLI smoke passed. |
| Standard error envelope and secrecy | Yes | Allowlist projection preserves loc/type/msg while excluding raw validation values and context. |
| Settings threading in app factory | Recorded in-boundary deviation | dependency_overrides passes factory Settings to auth dependencies; tasks 4d.1–4d.2. |
| FastAPI included-router route enumeration | Recorded test-only deviation | test_app_factory uses original_router for FastAPI 0.141.1 wrappers; production route scope is unchanged. |
| Out-of-scope boundary | Yes | No documents, retrieval, chat, UI, logout, or RLS behavior was added. |

### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | PASS | Engram #4827 contains the remediation RED/GREEN/REFACTOR table and cumulative prior evidence. |
| All implementation tasks have tests/evidence | PASS | 58/58 implementation/remediation tasks are checked with test or gate evidence. |
| RED confirmed | PASS | R.1 recorded two failing malformed-credential cases before the sanitizer; the test file exists. |
| GREEN confirmed | PASS | Focused login 9/9 and full PG gate 95/95 pass against current source. |
| Triangulation adequate | PASS | Unit, real-PG integration, CLI, route-harness, and independent malformed-shape evidence cover the requirements. |
| Safety net for all historical modified files | WARNING | Current remediation records 93/93 baseline safety-net coverage; earlier batch safety-net evidence remains summarized rather than row-level. |

**TDD Compliance**: 5/6 checks fully evidenced; the safety-net limitation is non-blocking.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 46 | 7 | pytest |
| Integration | 49 | 8 | pytest, httpx, async SQLAlchemy, real PostgreSQL |
| E2E | 0 | 0 | Not applicable to this authz foundation slice |
| **Total** | **95** | **15** | |

### Changed File Coverage

Coverage analysis skipped — pytest-cov and @vitest/coverage-v8 are unavailable; configured threshold is 0.

### Assertion Quality

All inspected assertions exercise production code, concrete SQL metadata, real HTTP behavior, or real database state. No tautologies, unexecuted ghost-loop assertions, smoke-only tests, or assertion-only mocks were found.

### Quality Metrics

- Ruff check: PASS.
- Ruff format check: PASS — 48 files already formatted.
- Biome check: PASS — no fixes required.
- Alembic check: PASS — no new upgrade operations detected.
- Type checker: not configured for this change.

### Issues Found

**CRITICAL**

None.

**WARNING**

1. Historical row-level safety-net evidence for batches 1a–4c is summarized in Engram #4827 rather than retained for every task. (branch: chore/setup-project; tasks: 1a–4c historical batches; commit: uncommitted worktree; fix: none required for this verification.)
2. The app-factory Settings override and included-router enumeration remain recorded in-boundary/test-only deviations from the original shape. (branch: chore/setup-project; tasks: 4d.1–4d.2; commit: uncommitted worktree; fix: none required.)

**SUGGESTION**

1. Install the configured coverage providers when coverage evidence becomes a release requirement.
2. Preserve the independent nested-like malformed-credential probe as a future regression case if validation models or error handlers change.

### Verdict

**PASS WITH WARNINGS** — all 15 requirements and 25 scenarios are compliant, all runtime and quality commands passed, no CRITICAL issues remain, and the final Gate is marked [x].
