# Verification Report (Reconciled Final): MVP Retrieval with RRF

**Change**: `mvp-retrieval-rrf`
**Status**: RECONCILED AFTER MERGE — the corrected tree passes. RDD was **disabled/unmanaged**; no review, receipt, attempt, or correction authority was used. This document is an ordinary repository artifact reconciliation following merged PR #11, not a runtime SDD verification run. No approval is claimed.

## Final Verdict (corrected tree): PASS

All **6 requirements** and **11 scenarios** of the active retrieval spec are implemented and covered on the corrected tree at merge commit `4373ca4` (PR #11, merged to `main`). Independent ordinary verification evidence for the corrected tree:

| Check | Result |
|---|---|
| Full non-e2e suite `POSTGRES_PORT=55432 uv run pytest -m 'not e2e' -q` | **302 passed**, 1 deselected |
| Focused settings/query unit tests | **35 passed** |
| Retrieval route integration | **12 passed** |
| Ruff check / format / Biome | pass, no fixes |
| Credential-gated provider smoke | **1 skipped** (`OPENAI_API_KEY` absent) — conditional, **not** counted as a pass |
| Bounded mutation campaign `retrieval/fusion.py` | **8/8 killed**, 0 survived |

The pre-remediation FAIL baseline is preserved verbatim below as history.

## Reconciliation Summary

The pre-remediation verification (baseline below) returned **FAIL** with **1 CRITICAL** finding: `build_semantic_query` had no distance/relevance threshold, so a populated tenant with no keyword match returned nearest authorized semantic chunks instead of the required neutral empty result, and the only covering-looking test disabled all authorized tenant chunks and could not detect it.

Merged PR #11 (`4373ca4`, "fix(retrieval): filter semantically irrelevant candidates", closes #5) remediated this with a **threshold correction**: a bounded semantic cosine-distance cutoff so populated-tenant no-match queries return the same neutral empty result as an empty corpus, while preserving tenant isolation and deterministic hybrid ranking. Regression coverage was added:

- New populated-corpus no-match integration case alongside the retained empty-corpus case.
- Semantic max-distance unit tests (filter applied after the tenant predicate, bound parameterization).
- Settings bound tests for `semantic_max_distance` (inclusive bounds, zero/negative rejected).

The corrected tree was independently verified after merge (figures in the Final Verdict table). The suite grew from the baseline's 295 passed to 302 passed (a net +7 runtime cases from PR #11).

---

## Baseline: Pre-Remediation Verification (preserved verbatim as history)

> The following is the original verification report produced **before** the threshold remediation, describing the tree at `feat/mvp-retrieval-rrf-gates` (`9014af4`). It is retained unchanged as the historical baseline. It is **not** the final state; the final state is recorded above. RDD was disabled/unmanaged; no review, receipt, attempt, correction, commit, push, PR, or archive flow was started during verification.

```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:2390270fba7b27eeacc7cd7bfe58df958e9a8d7bdc0d05d33d7f8665c53a4186
verdict: fail
blockers: 1
critical_findings: 1
requirements: 4/6
scenarios: 9/11
test_command: "POSTGRES_PORT=55432 uv run pytest -m 'not e2e' && pnpm test"
test_exit_code: 0
test_output_hash: sha256:2c76dc3311983023866b71e2bacfe47a29946054b2806ac869c7f18f0de0e7d7
build_command: "uv run ruff check apps/api && uv run ruff format --check apps/api && pnpm exec biome check"
build_exit_code: 0
build_output_hash: sha256:b8e50f92dc068ba1443f1f92f21acef3b152c163d449bf00b6766c90b1fee7a7
```

### Verification Report (original document)

**Change**: `mvp-retrieval-rrf`  
**Version**: Retrieval specification; actual retrieved totals are 6 requirements and 11 scenarios  
**Mode**: Strict TDD; hybrid OpenSpec + Engram; independent final verification  
**Current tree**: `feat/mvp-retrieval-rrf-gates` at `9014af4`; production implementation was not edited during verification. RDD is disabled/unmanaged as instructed; no review, receipt, attempt, correction, commit, push, PR, or archive flow was started.

#### Completeness

| Metric | Value |
|---|---:|
| Proposal/spec/design/tasks | Complete; OpenSpec files and Engram observations #5058, #5061, #5062, and #5063 were read and cross-checked |
| Apply progress | Complete; cumulative Engram observation #5064 was read in full |
| Requirements | 6 |
| Scenarios | 11 |
| Tasks total | 15 |
| Tasks complete | 15 |
| Tasks incomplete | 0 |
| Native action context | `repo-local`; allowed edit root `/home/jona/projects/raguard`; no production edits made |

The current tasks file contains all 15 implementation and verification tasks checked `[x]`. The native status projection reports `applyState: all_done` and `nextRecommended: verify`; the hybrid apply-progress source is Engram because no OpenSpec apply-progress file exists.

#### Build & Tests Execution

**Tests**: ✅ Exit 0. Exact command: `POSTGRES_PORT=55432 uv run pytest -m 'not e2e' && pnpm test`. Pytest collected 296 items, deselected the one e2e provider test, and passed **295 tests** in 35.10 seconds. `pnpm test` ran Vitest with no test files and exited 0. Exact combined output hash: `sha256:2c76dc3311983023866b71e2bacfe47a29946054b2806ac869c7f18f0de0e7d7`.

**Provider e2e gate**: ⚠️ Exit 0 with **1 skipped**. Exact command: `POSTGRES_PORT=55432 uv run pytest -m e2e apps/api/tests/e2e/test_retrieval_provider.py`. The skip reason was `OPENAI_API_KEY` absent; the credential-gated path remains conditional and is not counted as a pass. Output hash: `sha256:5357d045e69d0aa6958348d2f8dfeab760cd7ac492df4134ed20d4ced5c0b83d`.

**Build/quality**: ✅ Exit 0. Exact command: `uv run ruff check apps/api && uv run ruff format --check apps/api && pnpm exec biome check`. Ruff passed, 61 files were formatted, and Biome checked 8 files with no fixes. Output hash: `sha256:b8e50f92dc068ba1443f1f92f21acef3b152c163d449bf00b6766c90b1fee7a7`.

**Coverage**: ➖ Skipped. `pytest-cov` and `@vitest/coverage-v8` are not installed; the configured threshold is 0, so this is informational rather than a blocking command failure.

**Type checker/build target**: ➖ No Python type checker is configured, and this backend-only change has no participating TypeScript build target. Ruff, format, and Biome are the available quality evidence.

#### Spec Compliance Matrix

| Requirement | Scenario | Covering runtime evidence | Result |
|---|---|---|---|
| Bounded search request | Valid request is processed | `apps/api/tests/integration/test_retrieval_routes.py::test_valid_search_returns_at_most_top_k_fused_results`; `::test_valid_search_defaults_top_k_and_returns_only_tenant_chunks` | ✅ COMPLIANT |
| Bounded search request | Invalid query or top-k rejected | `apps/api/tests/integration/test_retrieval_routes.py::test_invalid_requests_rejected_with_400_and_no_retrieval` (6 parametrized cases) | ✅ COMPLIANT |
| Authorization before ranking | Only authorized tenant chunks return | `apps/api/tests/integration/test_retrieval_isolation.py::test_tenant_a_search_returns_only_tenant_a_chunks` | ✅ COMPLIANT |
| Authorization before ranking | Missing capability denied | `apps/api/tests/integration/test_retrieval_routes.py::test_search_requires_chat_use_capability` | ✅ COMPLIANT |
| Authorization before ranking | Cross-tenant isolation (release gate) | `apps/api/tests/integration/test_retrieval_isolation.py::test_tenant_b_only_query_discloses_no_tenant_b_data`; `::test_tenant_b_member_never_sees_tenant_a_chunks` | ✅ COMPLIANT |
| Deterministic hybrid fusion | Dual-signal chunk accumulates contributions | `apps/api/tests/unit/test_rrf_fusion.py::test_dual_signal_chunk_sums_contributions_and_outranks_single_signal` | ✅ COMPLIANT |
| Deterministic hybrid fusion | Deterministic tie ordering | `apps/api/tests/unit/test_rrf_fusion.py::test_equal_scores_order_by_ascending_chunk_id`; `::test_repeated_runs_produce_identical_results` | ✅ COMPLIANT |
| Same-model query embedding | Query binds against stored embeddings | `apps/api/tests/unit/test_retrieval_queries.py::test_semantic_query_binds_halfvec_1536_embedding`; `apps/api/tests/unit/test_retrieval_embeddings.py::test_embed_returns_dimension_exact_vectors_through_protocol`; real provider test skipped | ⚠️ PARTIAL |
| Neutral empty results and safe errors | No-match and empty corpus are identical | `apps/api/tests/integration/test_retrieval_routes.py::test_no_match_and_empty_corpus_return_identical_neutral_empty` only uses an authorized tenant with zero chunks; no populated-corpus no-match case is covered, and the semantic query has no distance/match threshold | ❌ UNTESTED |
| Neutral empty results and safe errors | Provider failure is a safe error | `apps/api/tests/integration/test_retrieval_routes.py::test_provider_failure_returns_503_without_partial_results` | ✅ COMPLIANT |
| No provider calls in ordinary tests | Non-e2e suite runs offline | Full non-e2e command: 295 passed, one e2e deselected; retrieval tests inject `FakeEmbedder` | ✅ COMPLIANT |

**Compliance summary**: 9/11 scenarios compliant; 1 partial and 1 untested. Four of six requirements are fully evidenced; the remaining two have conditional or missing scenario evidence.

#### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Bounded search request | ✅ Implemented | Query trimming/length bounds, top-k bounds/defaults, and standard 400 envelope are implemented before the search handler runs. |
| Authorization before ranking | ✅ Implemented | A fresh `AuthorizationScope` supplies a bound tenant predicate to both SQL signals; `chat.use` is required and response fields omit tenant identity. |
| Deterministic hybrid fusion | ✅ Implemented | FTS and semantic work is joined with `asyncio.gather`; independent sessions, candidate limits, RRF `k=60`, and score-desc/chunk-id-asc ordering match the design. |
| Same-model query embedding | ⚠️ Implemented with conditional runtime proof | `OpenAIEmbedder` forwards the configured model and rejects dimensions other than 1536; the real provider-to-`halfvec(1536)` smoke was skipped because credentials were absent. |
| Neutral empty results and safe errors | ❌ Spec conflict | Generic provider failures are safe, but `build_semantic_query` returns nearest tenant rows without a relevance threshold. A non-empty tenant with no keyword match can therefore produce semantic results instead of the required neutral empty result. |
| No provider calls in ordinary tests | ✅ Implemented | The production router accepts an injected `Embedder`; ordinary route/unit/integration tests use `FakeEmbedder`, and the provider test is e2e-marked and deselected by the required runner. |

#### Design Coherence

| Decision | Followed? | Notes |
|---|---|---|
| Router factory, fresh `AuthorizationScope`, shared `Embedder`, standard errors | ✅ Yes | The route factory reuses the existing authorization and error seams. |
| `chat.use` capability | ✅ Yes | Retrieval is gated on `CHAT_USE`; capability and tenant data come from the resolved verified-token scope. |
| Independent async sessions for parallel signals | ✅ Yes | The keyword and semantic paths each create a session and are awaited through `asyncio.gather`. |
| Bounded/tunable retrieval settings | ✅ Yes | Startup validates RRF, candidate, top-k, query-length, and `ef_search` bounds, including `ef_search >= candidates`. |
| Atomic failure semantics | ✅ Yes | Embedding or either query failure is mapped to one generic 503 with no partial candidates. |
| Parameterized PostgreSQL/pgvector access | ✅ Yes | User query, embedding, tenant, and `ef_search` values are bound; the FTS config is a fixed code constant; `SET LOCAL` is used for HNSW tuning. |
| No migration or worker changes | ✅ Yes | The changed production surface is API retrieval/provider wiring only. |
| No-match semantics | ⚠️ No | The design explicitly leaves semantic retrieval without a distance threshold, while the spec requires an empty result for a no-match query. The implementation follows the design but not the requirement's general case. |

#### Security and PostgreSQL Boundary Checks

- Tenant predicates are applied in both signal queries before ranking, with joins constrained by tenant and document keys; the release-gate isolation tests passed in real PostgreSQL/pgvector.
- Search responses expose chunk/document context and ranks only; tenant IDs, raw embeddings, provider credentials, and provider exception details are not returned.
- Query text and embedding values are parameterized; the fixed `simple` FTS configuration is not user-controlled. `hnsw.ef_search` is parameterized and local to the semantic transaction.
- Query length, top-k, candidate count, provider timeout, and SDK retries are bounded; no generation or LLM-output execution path is present in this change.

#### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | Cumulative apply-progress #5064 contains a `TDD Cycle Evidence` table for the final work unit and condensed RED/GREEN evidence for work units 1–3. |
| All tasks have tests/evidence | ✅ | 15/15 tasks are checked; 59 non-e2e cases and one gated e2e case are present for the changed test files. Task 3.3 is a fix/evidence task with no separate test file. |
| RED confirmed | ✅ | The apply artifact records RED-first test creation for the foundation, query, endpoint, isolation, and provider work; every listed test file exists in the current tree. |
| GREEN confirmed | ✅ | Current execution passes all 59 non-e2e retrieval/app-factory cases; the provider gate is explicitly skipped only for the missing credential. |
| Triangulation adequate | ⚠️ | RRF, route, and isolation behaviors have multiple distinct cases; the provider contract is intentionally a single smoke, and the no-match test does not triangulate a populated corpus. |
| Safety net for modified files | ⚠️ | Final work-unit safety-net evidence is explicit, but historical per-task safety-net rows for work units 1–3 are condensed rather than retained individually. |

**TDD Compliance**: 4/6 checks fully evidenced; the two warnings are evidence depth/coverage concerns, not failed runtime commands.

#### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 41 | 4 | pytest |
| Integration | 18 | 3 | pytest, HTTPX, async SQLAlchemy, disposable PostgreSQL/pgvector |
| E2E | 1 collected, 1 skipped | 1 | pytest, OpenAI provider, PostgreSQL/pgvector |
| **Total related change cases** | **60** | **8** | |

The 59 non-e2e cases are the four unit files plus route, isolation, and app-factory integration files. Parameterization expands the 44 test functions into 59 runtime cases; the provider smoke contributes the one e2e case.

#### Changed File Coverage

Coverage analysis skipped — configured Python and JavaScript coverage providers are not installed.

#### Assertion Quality

**Assertion quality**: ✅ All inspected assertions verify concrete behavior. The audit covered 8 changed/created test files, 45 AST test functions, 60 collected runtime cases, and 117 assertion nodes. No tautologies, assertions without production calls, ghost-loop assertions, smoke-only tests, or mock-heavy files were found. The `is not None` and identity assertions are intentional contract/existence checks combined with value assertions, not standalone smoke checks.

#### Quality Metrics

- Ruff check: ✅ exit 0.
- Ruff format check: ✅ exit 0; 61 files already formatted.
- Biome: ✅ exit 0; 8 files checked, no fixes.
- Python type checker: ➖ not configured.
- Coverage providers: ➖ not installed; threshold 0.
- JavaScript test runner: ✅ exit 0; no test files found.

#### Mutation Testing Evidence

**Status**: `pass`  
**Target scope**: One bounded campaign over changed executable target `apps/api/src/raguard_api/retrieval/fusion.py` (deterministic RRF core); query/router/provider/config wiring was outside this single bounded campaign.  
**Framework**: `pytest-gremlins 1.9.0`, subprocess executor, with the repository app root supplied as pytest root for the `apps/api/src` layout.  
**Trailmark preanalysis**: `uv run --with trailmark trailmark analyze --language auto --summary apps/api/src/raguard_api/retrieval` exited 0 and reported 89 nodes, 13 functions, and 0 entrypoints.  
**Campaign command**: `POSTGRES_PORT=55432 uv run --with pytest-gremlins pytest --rootdir=/home/jona/projects/raguard/apps/api --gremlins --gremlin-executor=subprocess --gremlin-targets src/raguard_api/retrieval/fusion.py --gremlin-report=json --gremlins-html-dir=/tmp/opencode/raguard-mutation-html-valid tests/unit/test_rrf_fusion.py` (cwd `/home/jona/projects/raguard/apps/api`).  
**Campaign output**: exit 0; **8 total, 8 killed, 0 survived, 0 timeout, 0 error**; mutation output hash `sha256:08f818e511108a488f9bcad47c6e76f3593e0b142ced8a22616ca747b1a2f286`.  
**Triage**: No survivors; all arithmetic, comparison, boundary, and return mutations were killed by the RRF score/rank/tie/bounds assertions. Necessist is not applicable to this Python target under the supported-framework matrix and was not substituted manually.  
**Strict-TDD comparison**: The bounded campaign corroborates the RED/GREEN RRF evidence; no mutation-specific contradiction remains.

#### Issues Found

**CRITICAL**

1. The required no-match/empty-corpus equivalence is not implemented for the general non-empty-corpus case. `build_semantic_query` has no distance/relevance threshold, so when FTS returns no rows the semantic signal still returns nearest authorized chunks. The only covering-looking integration test disables all authorized tenant chunks (`a_chunks=False`), so it cannot detect this behavior. This blocks archive readiness.

**WARNING**

1. The real OpenAI provider/`halfvec(1536)` smoke is conditional: one e2e case was skipped because `OPENAI_API_KEY` was absent locally. No pass is claimed for that external credential-dependent path.
2. Historical row-level safety-net evidence for work units 1–3 is summarized in cumulative apply-progress #5064 rather than retained as a separate table row for every task; current tests and the final work-unit evidence are green.
3. Coverage analysis is unavailable because the configured coverage providers are not installed; the configured threshold is 0.

**SUGGESTION**

1. Add a populated-corpus no-match integration scenario and reconcile the design/spec by defining a semantic relevance threshold or another explicit rule for neutral empty results.
2. Preserve detailed per-task TDD safety-net evidence and install coverage providers when release coverage becomes a required gate.
3. Broaden mutation scope in a future bounded verification only if the phase budget permits; this campaign intentionally covered the highest-risk pure RRF core.

#### Verdict

**FAIL** — all executed tests, quality checks, and the bounded mutation campaign passed, but one required retrieval scenario is not covered and the current semantic query path contradicts the specification for a non-empty corpus with no matches.

---

## Threshold Correction (merged PR #11)

| Item | Detail |
|---|---|
| PR / merge commit | #11 `4373ca417b8204dfac26a255e51e20f4012207c4` — "fix(retrieval): filter semantically irrelevant candidates" (closes #5) |
| Correction | Bounded semantic cosine-distance cutoff so populated-tenant no-match queries return the neutral empty result; preserves tenant isolation and deterministic hybrid ranking |
| Setting | `retrieval_semantic_max_distance` default `0.5`, bounds-validated at startup (config.py), env-documented in `.env.example` |
| Application | Bound as `:max_distance` and applied after the tenant predicate in the semantic query builder; passed through the router from settings |
| Files changed | `.env.example`; `config.py` (+22); `retrieval/queries.py` (+22); `retrieval/router.py` (+6); tests: `test_retrieval_routes.py` (+78), `test_retrieval_queries.py` (+56), `test_retrieval_settings.py` (+18), `test_retrieval_provider.py` (+4) |
| Design note | The design was updated to document the threshold; the semantic signal ranks only chunks within `semantic_max_distance` (default 0.5 cosine distance), so populated no-match returns the same neutral empty result as an empty corpus |

## Spec Compliance Matrix (corrected tree)

| Requirement | Scenario | Covering runtime evidence (corrected tree) | Result |
|---|---|---|---|
| Bounded search request | Valid request is processed | `test_valid_search_returns_at_most_top_k_fused_results`; `test_valid_search_defaults_top_k_and_returns_only_tenant_chunks` | ✅ COMPLIANT |
| Bounded search request | Invalid query or top-k rejected | `test_invalid_requests_rejected_with_400_and_no_retrieval` (6 parametrized cases) | ✅ COMPLIANT |
| Authorization before ranking | Only authorized tenant chunks return | `test_tenant_a_search_returns_only_tenant_a_chunks` | ✅ COMPLIANT |
| Authorization before ranking | Missing capability denied | `test_search_requires_chat_use_capability` | ✅ COMPLIANT |
| Authorization before ranking | Cross-tenant isolation (release gate) | `test_tenant_b_only_query_discloses_no_tenant_b_data`; `test_tenant_b_member_never_sees_tenant_a_chunks` | ✅ COMPLIANT |
| Deterministic hybrid fusion | Dual-signal chunk accumulates contributions | `test_dual_signal_chunk_sums_contributions_and_outranks_single_signal` | ✅ COMPLIANT |
| Deterministic hybrid fusion | Deterministic tie ordering | `test_equal_scores_order_by_ascending_chunk_id`; `test_repeated_runs_produce_identical_results` | ✅ COMPLIANT |
| Same-model query embedding | Query binds against stored embeddings | `test_semantic_query_binds_halfvec_1536_embedding`; `test_embed_returns_dimension_exact_vectors_through_protocol`; live provider smoke skipped/conditional | ✅ COMPLIANT* |
| Neutral empty results and safe errors | No-match and empty corpus are identical | `test_no_match_and_empty_corpus_return_identical_neutral_empty`; **new** `test_populated_no_match_returns_same_neutral_empty_as_empty_corpus` | ✅ COMPLIANT |
| Neutral empty results and safe errors | Provider failure is a safe error | `test_provider_failure_returns_503_without_partial_results` | ✅ COMPLIANT |
| No provider calls in ordinary tests | Non-e2e suite runs offline | full non-e2e run (302 passed) offline; retrieval tests inject `FakeEmbedder` | ✅ COMPLIANT |

\* Scenario covered by dimension-exact fake-embedder unit tests; the real-provider e2e smoke remains skipped/conditional (`OPENAI_API_KEY` absent) and is not claimed as a pass.

**Compliance summary (corrected tree)**: **11/11 scenarios compliant**; 6/6 requirements fully evidenced. The only conditional item is the credential-gated live provider smoke, recorded as skipped, never as a pass.

## Quality Gates (corrected tree)

- Ruff check / format: ✅ pass. Biome: ✅ pass (no fixes).
- Coverage providers not installed; configured threshold 0 (informational, not blocking).
- Python type checker not configured; no participating TypeScript build for this backend-only change.

## Outstanding / Follow-Up (non-blocking)

1. **Provider smoke remains conditional**: run `test_retrieval_provider.py` with `OPENAI_API_KEY` set to exercise the live `text-embedding-3-small` → `halfvec(1536)` bind end to end.
2. **Future threshold calibration**: `semantic_max_distance` default `0.5` is an initial calibration; the spec still lists tuning defaults and the capability token (`chat.use` vs `corpus.view`) as unresolved design inputs — design resolved these to `chat.use` and the documented defaults. Evaluation-harness work (out of scope here) should validate the threshold against real corpora.
3. Coverage providers not installed; install when release coverage becomes a gate.
