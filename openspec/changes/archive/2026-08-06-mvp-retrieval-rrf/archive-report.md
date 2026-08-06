# Archive Report: MVP Retrieval with RRF

**Archived**: 2026-08-06 — SDD cycle complete. Verdict at close: **PASS** (corrected tree); 0 open CRITICAL findings; 15/15 tasks complete; all required quality and runtime gates passed on the merged tree. RDD was **disabled/unmanaged**; no review, receipt, attempt, or correction authority was used, and no approval is fabricated. This archive follows the ordinary merged-PR reconciliation of PR #11; the pre-remediation FAIL record is retained as history in `verify-report.md`.

## Final State at Close

| Dimension | Value |
|---|---|
| Change | `mvp-retrieval-rrf` |
| Delivery | Merged PR #11 — commit `4373ca417b8204dfac26a255e51e20f4012207c4` "fix(retrieval): filter semantically irrelevant candidates" (closes #5), merged to `main` |
| Domain | `retrieval` (new main spec, created from full-spec delta) |
| Requirements / Scenarios | 6 / 11 (preserved verbatim from the active delta spec) |
| Tasks | 15/15 complete (`tasks.md`: 15 `[x]`, 0 `[ ]`) |
| Verification verdict | PASS for the corrected tree (`verify-report.md`, reconciled after merge) |
| CRITICAL findings at close | 0 (the 1 pre-remediation CRITICAL was remediated by PR #11; baseline retained) |
| Review gate | `disabled/unmanaged` — RDD off; no receipt/attempt authority was used; nothing fabricated |
| Artifact store | Hybrid OpenSpec + Engram observations (#5058, #5061, #5062, #5063, #5064 cited in the archived verify report) |

## Merged Delivery Evidence

PR #11 passed all GitHub checks: issue reference/approval, cognitive load, type label, infra, Python, and JS.

## Verification Final State (authoritative: reconciled `verify-report.md` + merged-PR evidence)

Final numbers are carried from the corrected tree at `4373ca4`; intermediate snapshots are quoted as history only.

- **Full non-e2e suite**: `POSTGRES_PORT=55432 uv run pytest -m 'not e2e' -q` — **302 passed, 1 deselected** (up from the pre-remediation baseline's 295 passed; net +7 runtime cases from PR #11).
- **Focused settings/query unit tests**: 35 passed (settings 20 runtime cases + queries 15).
- **Retrieval route integration**: 12 passed (2 valid + 6 invalid-request cases + capability + empty/no-match + populated no-match + provider failure).
- **Quality**: Ruff check and format pass; Biome pass (no fixes).
- **Bounded mutation campaign** `retrieval/fusion.py`: 8/8 killed, 0 survived (`pytest-gremlins`).
- **Provider e2e smoke**: **1 skipped** — `OPENAI_API_KEY` absent locally; recorded as conditional/skipped, **not** counted as a pass.

## Spec Sync

`openspec/changes/mvp-retrieval-rrf/specs/retrieval/spec.md` is a full spec for a new domain (no existing `openspec/specs/retrieval/` main spec). Per the delta-sync rule it was copied to `openspec/specs/retrieval/spec.md` with one layout adaptation to the repository's existing main-spec convention: a `## Requirements` heading inserted before the requirement blocks (all other main specs use it). All 6 requirements and 11 scenarios are preserved verbatim; no requirement was invented, removed, or reworded. The delta's `## Out of Scope` closing section is preserved as authored. No destructive merge occurred, so the `rules.archive` "warn before merging destructive deltas" rule was not triggered; the unrelated main specs are untouched.

| Domain | Action | Details |
|---|---|---|
| `retrieval` | Created | 6 requirements, 11 scenarios; `## Requirements` heading per existing layout |

## Reconciliation Notes (recorded, not silently resolved)

1. The active delta spec lists the capability token (`chat.use` vs `corpus.view`) and tuning defaults as "unresolved design inputs". Design and implementation resolved these: retrieval requires `chat.use` (verified by `test_search_requires_chat_use_capability`) and the documented defaults (`rrf_k=60`, candidates 50, `top_k=10`, `ef_search=100`, `semantic_max_distance=0.5`). The spec prose was preserved verbatim per instruction; the resolution is recorded here.
2. The pre-remediation `verify-report.md` (verdict FAIL, 1 CRITICAL) is retained verbatim as the baseline inside the reconciled report; the corrected-tree verdict is PASS and is the authoritative close state.
3. The main spec is the reconciled copy with the layout heading; the archived delta spec in this folder remains byte-faithful to what was authored.

## Non-Blocking Warnings / Follow-Up

1. **Provider skip**: real OpenAI provider/`halfvec(1536)` smoke remains conditional on `OPENAI_API_KEY`; run it before release to exercise the live embedder bind end to end.
2. **Future threshold calibration**: `semantic_max_distance` default (0.5) is an initial calibration; the eval-harness follow-up (out of scope for this change) should validate it against real corpora. Tuning remains a documented open input.
3. Coverage providers (`pytest-cov`, `@vitest/coverage-v8`) not installed; configured threshold 0.
4. Historical per-task TDD safety-net rows for work units 1–3 are condensed in cumulative apply-progress #5064 rather than retained individually.

## Audit Trail Contents

`openspec/changes/archive/2026-08-06-mvp-retrieval-rrf/`:

- `proposal.md`
- `exploration.md`
- `specs/retrieval/spec.md` (delta spec as authored, 6 requirements / 11 scenarios)
- `design.md`
- `tasks.md` (15/15 checked)
- `verify-report.md` (reconciled final; pre-remediation FAIL baseline retained verbatim)
- `archive-report.md` (this file)

Active `openspec/changes/` contains only `archive/`; the change is no longer active. The archive is an audit trail — contents are not modified after archiving.
