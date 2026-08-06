# Archive Report: MVP Document Ingestion

**Archived**: 2026-08-05 — SDD cycle complete. Verdict at close: **PASS WITH WARNINGS**; 0 critical findings; 24/24 tasks complete; all required quality and runtime gates passed. Archive is **intentional-with-warnings**: every warning below is non-blocking (documentation/evidence-retention or unavailable-tooling only). No overrides were exercised and no stale-checkbox reconciliation was needed — the authoritative tasks artifact was already 24/24.

## Final State at Close

| Dimension | Value |
|---|---|
| Change | `mvp-document-ingestion` |
| Domain | `documents` (new main spec, created from full-spec delta) |
| Requirements / Scenarios | 6 / 12 (validator-admitted counts) |
| Tasks | 24/24 complete (`openspec/changes/archive/2026-08-05-mvp-document-ingestion/tasks.md`: 24 `[x]`, 0 `[ ]`) |
| Verification verdict | PASS WITH WARNINGS (`verify-report.md`; Engram #5020) |
| CRITICAL findings | 0 |
| Review gate | `reviewGate.delivery: disabled/unmanaged` — receipt kill switch off; no review artifacts exist; nothing fabricated |
| Artifact store | Hybrid OpenSpec + Engram |

## Gates Passed Before Archive

- **Task Completion Gate**: authoritative filesystem `tasks.md` has 24 checked / 0 unchecked implementation tasks. PASS.
- **Native Review Receipt Gate**: structured status reports `reviewGate.delivery: disabled/unmanaged` (kill switch off, no review governs this change). Searches for `sdd/mvp-document-ingestion/review/{transaction,ledger,receipt,gate-context}` in Engram returned no observations, consistent with that state. Accepted as the only permitted relaxation; no receipt was manufactured.
- **CRITICAL gate**: persisted verify report (`verify-report.md`, Engram #5020) records `critical_findings: 0`, verdict `pass`. PASS.

## Evidence Chain (Engram Observation IDs)

| Artifact | Engram observation | Notes |
|---|---|---|
| Proposal | #4890 `sdd/mvp-document-ingestion/proposal` | Matches archived `proposal.md` |
| Spec (delta) | #4896 `sdd/mvp-document-ingestion/spec` | 6 requirements / 12 scenarios; matches archived delta spec |
| Design | #4902 `sdd/mvp-document-ingestion/design` | Revision 4, post dispatch-ready correction |
| Tasks | #4914 `sdd/mvp-document-ingestion/tasks` | **Stale pre-apply snapshot** — see Metadata Drift #1 |
| Apply progress (cumulative) | #4918 `sdd/mvp-document-ingestion/apply-progress` | Cumulative PR1–PR5 + corrective Arq remediation, 8 revisions |
| Verify report | #5020 `sdd/mvp-document-ingestion/verify-report` | Validator-admitted 6/6 requirements, 12/12 scenarios |
| Review transaction / ledger / receipt / gate-context | — (absent) | Consistent with `disabled/unmanaged` delivery |

## Spec Sync

`openspec/changes/mvp-document-ingestion/specs/documents/spec.md` was a full spec for a new domain (no existing `openspec/specs/documents/` main spec). Per the delta-sync rule, it was copied directly to `openspec/specs/documents/spec.md` — verified byte-identical. No destructive merge occurred, so the `rules.archive` "warn before merging destructive deltas" rule was not triggered. The unrelated main specs (`authorization-rbac`, `jwt-authentication`, `tenant-identity`) are untouched.

| Domain | Action | Details |
|---|---|---|
| `documents` | Created | 6 requirements, 12 scenarios, `## Deferred` preserved |

## Verification Final State (authoritative evidence: #5020 + launch-prompt final-state facts)

Final test/quality numbers are carried from the highest-ranked sources — the validator-admitted verify report and the orchestrator's final-state facts; intermediate snapshots are not quoted as current:

- **Full suite**: `POSTGRES_PORT=55432 uv run pytest -m 'not e2e' && pnpm test` — 240 passed, exit 0 (passed twice per launch-prompt final-state facts).
- **Corrective focused regression**: 23 passed, exit 0.
- **Worker suite**: 77 passed, exit 0.
- **Quality**: Ruff check clean; Ruff format clean (82 files); Biome 8 files, no fixes; Alembic check no new operations; Compose config valid.
- **Corrective Arq 0.28 remediation (final)**: `TransientStageFailure(Retry)` closes the plain-exception gap; real Redis/Postgres/MinIO harness produced 9 parse requeues + 9 embed requeues over tries 1–10, terminal `failed/malformed` and `failed/limit`, zero chunks, zero Arq-level failures, `HARNESS_RESULT: PASS`, no OpenAI network calls. This work completed after the cumulative apply-progress snapshot and is reflected in the archived tasks (24/24) and verify report.

## Metadata Contradictions / Drift (recorded explicitly, not silently resolved)

1. **Engram tasks observation #4914 is a pre-apply snapshot** still marking tasks 3.1–5.3 unchecked. The authoritative filesystem `tasks.md` is 24/24 and cumulative apply-progress #4918 plus verify report #5020 corroborate completion. Per the Final-State Authority hierarchy, the persisted filesystem tasks artifact outranks the stale Engram snapshot; no task is pending. Recorded as drift, not as an incomplete task.
2. **Native final verification (generation 13) compact ledger diagnosis contains an older 5-requirement/10-scenario summary.** The validator-admitted persisted verify report and the current spec both carry 6 requirements / 12 scenarios, which are authoritative. The ledger summary is treated as stale metadata drift and is recorded here rather than silently adopted.
3. **`openspec/config.yaml` contains a known stale bootstrap-context line** ("Repository is at bootstrap stage: config and empty test suites only…", pre-authz). Intentionally not edited as part of archive, per instruction.

## Non-Blocking Warnings (carried from verify report #5020)

1. Stale Engram task snapshot #4914 vs. current tasks/apply evidence (see Drift #1).
2. Historical PR1–PR5 safety-net evidence summarized rather than retained row-by-row.
3. Coverage providers (`pytest-cov`, `@vitest/coverage-v8`) not installed; configured threshold 0.
4. No Python type checker configured; no participating TypeScript build for this backend-only change.
5. E2E skipped — no browser/full-stack-only scenario in the retrieved specification.

## Audit Trail Contents

`openspec/changes/archive/2026-08-05-mvp-document-ingestion/`:

- `proposal.md`
- `exploration.md`
- `specs/documents/spec.md` (delta, byte-identical to the synced main spec)
- `design.md`
- `tasks.md` (24/24 checked)
- `verify-report.md`
- `archive-report.md` (this file)

Active `openspec/changes/` contains only `archive/`; the change is no longer active. The archive is an audit trail — contents are not modified after archiving.
