# Archive Report: MVP Chat with Verifiable Citations

**Archived**: 2026-08-21 — SDD cycle complete. Verdict at close: **PASS WITH WARNINGS**; 0 CRITICAL findings; 8/8 requirements, 15/15 scenarios, 18/18 tasks complete; all required runtime and quality gates passed. Review gate **allow**. Archive is **complete** (no intentional-with-warnings override, no stale-checkbox reconciliation).

## Final State at Close

| Dimension | Value |
|---|---|
| Change | `mvp-chat-citations` |
| Archived to | `openspec/changes/archive/2026-08-21-mvp-chat-citations/` |
| Main spec (source of truth) | `openspec/specs/chat/spec.md` (created from full-spec delta) |
| Domain | `chat` (new domain — full spec, first change) |
| Requirements / Scenarios | 8 / 15 (preserved verbatim from `openspec/changes/mvp-chat-citations/specs/chat/spec.md`) |
| Tasks | 18/18 complete (`tasks.md`: 18 `[x]`, 0 `[ ]`) |
| Verification verdict | `pass_with_warnings` (canonical strict report, validator-approved, SHA-256 `204b4cbb742c0f1d454789ae804dea5a675f786766aa3f322463c277678e5cf7`) |
| CRITICAL findings at close | 0 |
| Review gate | `allow` — native review lineage `review-c59f37d243d28dcf` approved exact target `sha256:c59f37d243d28dcfb3906913744322d273176ce773be81e59790475737a296a9` with one reliability lens, no blocking correction |
| Artifact store | `openspec` only (no Engram; no hybrid) |
| Action context | `repo-local`; `allowedEditRoots: [/home/jona/projects/raguard]` — all operations inside allowed roots |

## Gates Passed Before Archive

- **Task Completion Gate**: authoritative persisted `tasks.md` (both delta and archived copy) has 18 checked / 0 unchecked implementation tasks. All 18 tasks from PR1 1.1–1.3 through PR5b 5.4 are `[x]`. PASS. No stale-checkbox reconciliation was needed; `sdd-apply` owns completion and the artifact already reflects final state.
- **Native Review Receipt Gate**: structured status projects `reviewGate.result: allow` with reason "approved receipt exactly matches authoritative native state and the current repository". Native review verification evidence captured the exact canonical report bytes and passed. The receipt matches final candidate tree, paths digest, policy, ledger, fix delta, current independent verification evidence, mode counters, and base relationship (including the post-review final verification report delta where archive status projects `allow` only when native final-verify settlement attests the exact canonical passing report bytes — condition satisfied here). No override.
- **CRITICAL gate**: persisted `verify-report.md` records `critical_findings: 0`, `blockers: 0`, verdict `pass_with_warnings`. PASS. CRITICAL would block unconditionally; none present.
- **Action Context Guard**: `actionContext.mode: repo-local` — not `workspace-planning`; archive correctly moves into repo-local `openspec/changes/archive/`. All edits stayed inside `/home/jona/projects/raguard`.

## Spec Sync

`openspec/changes/mvp-chat-citations/specs/chat/spec.md` is a **full spec for a new domain** (no existing `openspec/specs/chat/spec.md`). Per the delta-sync rule for `openspec`/`hybrid` when the main spec does not exist, the delta was copied mechanically with shell only (not Read→Write), verified by mandatory `diff -r` readback, then moved atomically. No existing requirements were merged, no destructive delta occurred, so `rules.archive` "Warn before merging destructive deltas" was not triggered. Unrelated main specs (`authorization-rbac`, `documents`, `jwt-authentication`, `retrieval`, `tenant-identity`) are untouched.

| Domain | Action | Details |
|--------|--------|---------|
| `chat` | Created | 8 requirements, 15 scenarios; full spec preserved verbatim (133 lines, `spec.md` 6.5K). No requirements added/modified/removed beyond exact copy. |

Preserved requirements (names from delta and main spec):

1. Bounded chat request
2. Fresh authorization and chat.use gate
3. Retrieval-level tenant authorization before generation
4. Grounded prompt treats documents as untrusted data
5. Bounded OpenAI completion contract
6. Neutral no-evidence short-circuit
7. Numbered citations with membership verification
8. Safe response fields

All 15 scenarios preserved (2 + 2 + 2 + 1 + 2 + 2 + 3 + 1) — validator count 15/15.

## Verification Final State (authoritative per Final-State Authority hierarchy)

Final numbers are carried from the highest-ranked sources — native review authority + persisted tasks artifact + explicit final-state facts from the orchestrator launch prompt — not from intermediate snapshots quoted as history.

- **Native review authority (rank 1)**: lineage `review-c59f37d243d28dcf`, target `sha256:c59f37d243d28dcfb3906913744322d273176ce773be81e59790475737a296a9`, one reliability lens, no blocking correction. Native review verification evidence captured the exact canonical report bytes and **passed**. Status projects `reviewGate.result: allow` and `archive: ready`. Runtime remediation attempt settled with native state `complete`.
- **Persisted verify-report (intermediate snapshot, rank 4) history**: `verify-report.md` at `sha256:0234461672788991d3887ef15015855e9c10785922ff673ab449f88de18bb19e` (begin_candidate_identity), tree `f0555d07fb945ce2cd32733e1363cffaa7d2e9b9`, verdict `pass_with_warnings`, 0 blockers, 0 critical. Retained as history; its stale "at verification time" claims do not override final state.
- **Explicit final-state facts (rank 3, outranks stale snapshots) — final closed state**:
  - Canonical strict report is validator-approved, first non-empty YAML, SHA-256 `204b4cbb742c0f1d454789ae804dea5a675f786766aa3f322463c277678e5cf7`, confirming **8/8 requirements, 15/15 scenarios, 18/18 tasks**.
  - Runtime evidence (from final independent verification): `POSTGRES_PORT=55432 uv run pytest -m 'not e2e'` → **376 passed, 2 deselected, exit 0**; `pnpm test` → exit 0 (Vitest 4.1.10, no test files); `uv run ruff check` → exit 0; `uv run ruff format --check` → exit 0.
  - Opt-in chat OpenAI e2e `tests/e2e/test_chat_e2e.py` collected and **skipped cleanly** because `OPENAI_API_KEY` is unset; no live-provider pass is claimed (correct conditional skip, not a failure).
  - Mutation tooling and coverage providers remain **unavailable**; these are non-critical warnings (`pytest-cov` / `@vitest/coverage-v8` not installed, `pytest-gremlins` unavailable; `coverage_threshold: 0` per `openspec/config.yaml`).

The verify-report's intermediate numbers (at its write time) are consistent with final state: 376 passed is the authoritative close; no contradiction exists between the report's pass and the final facts.

## Non-Blocking Warnings / Follow-Up (carried to close)

All warnings are non-critical per `verify-report` `pass_with_warnings` and final-state facts; none block archive:

1. **Mutation tooling unavailable**: no `pytest-gremlins` / mutation campaign executed for this change. Not a CRITICAL; tracker accepts unavailable-tooling warning.
2. **Coverage providers unavailable**: `pytest-cov` and `@vitest/coverage-v8` not installed; JS/Python coverage not collected. Threshold is 0, so no gate fails.
3. **Provider e2e conditional skip**: `tests/e2e/test_chat_e2e.py` (PR5b +123 lines) correctly skips without `OPENAI_API_KEY`; a real-provider pass requires a credentialed run before release. This is the intended `e2e` marker contract — not counted as a coverage gap.
4. **Vitest reports no test files**: `pnpm test` exit 0 with "no test files". Expected — web tooling ready but no JS tests yet (same as prior archived changes).
5. **Historical TDD safety-net evidence**: per-task red-phase evidence is condensed in `verify-report` spec-compliance matrix rather than retained per-commit; acceptable for archive.

No destructive merge, no CRITICAL findings, no stale tasks, no path violation.

## Mechanical Copy Contract Evidence (mandatory verbatim `diff -r` readbacks)

Archival is a mechanical filesystem operation. File content never passed through model Read/Write to be copied; only shell commands `cp`, `mv`, and `diff -r` were used. Verbatim `diff -r` output is included below; only empty diff (no differences) passes, and a missing `diff -r` would fail the phase.

### 1) Spec sync: `openspec/changes/mvp-chat-citations/specs/chat/spec.md` → temp file

```text
# Command: diff -r "openspec/changes/mvp-chat-citations/specs/chat/spec.md" "$temp_path"
# (temp_path = openspec/specs/chat/.spec.md.ghmWhq, mktemp within target_dir)
# Output: (empty — no differences)
# Exit status: 0
```

Final byte-identity check after atomic `mv "$temp_path" "$target_path"`:

```text
# Command: diff -r "openspec/changes/mvp-chat-citations/specs/chat/spec.md" "openspec/specs/chat/spec.md"
# Output: (empty — no differences)
# Exit status: 0
```

### 2) Archive move: snapshot vs archived tree

Snapshot created before move:

```text
snapshot_root="$(mktemp -d "${TMPDIR:-/tmp}/sdd-archive.XXXXXX")"  # → /tmp/sdd-archive.fsf0hx
cp -R "openspec/changes/mvp-chat-citations" "$snapshot_root/source"
```

Move attempt (mechanical, shell only):

```text
# git mv openspec/changes/mvp-chat-citations openspec/changes/archive/2026-08-21-mvp-chat-citations
# → exit non-zero: "fatal: directorio de fuente está vacío" (change was untracked: git status showed "?? openspec/changes/mvp-chat-citations/")
# Fallback (per contract: git mv when tracked, mv otherwise):
# mv openspec/changes/mvp-chat-citations openspec/changes/archive/2026-08-21-mvp-chat-citations
# → succeeded
# Source-gone check: [ -e "openspec/changes/mvp-chat-citations" ] → false (verified)
```

Mandatory readback:

```text
# Command: diff -r "$snapshot_root/source" "openspec/changes/archive/2026-08-21-mvp-chat-citations"
# Output: (empty — no differences)
# Exit status: 0
```

Only empty diff output passes. All three readbacks are empty; byte-identity is proven. `snapshot_root` was removed via `EXIT` trap after readback. The `archive-report.md` file (this file) is additive-only and correctly excluded from the source/destination comparison because it did not exist in the source snapshot at move time.

## Audit Trail Contents

`openspec/changes/archive/2026-08-21-mvp-chat-citations/` (ISO date `2026-08-21` per objective):

- `proposal.md` — 3.7K — In Scope/Out of Scope, capabilities, approach, affected areas
- `exploration.md` — 24.4K — problem/constraints/options
- `specs/chat/spec.md` — 6.5K — delta spec as authored (8 requirements / 15 scenarios)
- `design.md` — 5.7K — technical approach, RRF/extraction decision, data flow, file changes, interfaces
- `tasks.md` — 8.2K — 18/18 checked (PR1 1.1–1.3, PR2 2.1–2.4, PR3 3.1–3.3, PR4 4.1–4.4 + PR4b, PR5 5.1–5.4 + PR5b)
- `verify-report.md` — 15.2K — validator-admitted pass_with_warnings, 376/2, spec readback 8/15
- `archive-report.md` — (this file, additive-only)

## Verification Checklist (per Step 4 — all proven, not self-reported)

- [x] Main spec updated correctly: `openspec/specs/chat/spec.md` exists, 133 lines, 8 requirements, 15 scenarios, byte-identical to delta (empty `diff -r`)
- [x] Change folder moved to archive: `openspec/changes/archive/2026-08-21-mvp-chat-citations/` exists; active `openspec/changes/mvp-chat-citations/` is gone (verified `[ -e ]` false)
- [x] Archive contains all artifacts: `proposal.md`, `specs/chat/spec.md`, `design.md`, `tasks.md`, `verify-report.md`, `archive-report.md`
- [x] Archived `tasks.md` has no unchecked implementation tasks: 18 `[x]`, 0 `[ ]` (rechecked after move)
- [x] Active changes directory no longer has this change: `openspec/changes/` now contains only `archive/` (4 dated entries)
- [x] Verbatim `diff -r` readback output included above and is empty (no differences) — the only passing evidence
- [x] Review gate `allow` verified via structured status and native review lineage; no override needed
- [x] All operations stayed inside `allowedEditRoots: [/home/jona/projects/raguard]`

## Changed Paths

- Created (source of truth): `openspec/specs/chat/spec.md` (from delta `openspec/changes/mvp-chat-citations/specs/chat/spec.md`)
- Moved (mechanical): `openspec/changes/mvp-chat-citations/` → `openspec/changes/archive/2026-08-21-mvp-chat-citations/`
- Created (audit trail additive): `openspec/changes/archive/2026-08-21-mvp-chat-citations/archive-report.md`
- Untouched: `openspec/specs/authorization-rbac/`, `openspec/specs/documents/`, `openspec/specs/jwt-authentication/`, `openspec/specs/retrieval/`, `openspec/specs/tenant-identity/`; `openspec/changes/archive/2026-08-05-*` and `2026-08-06-*`

## Remaining Warnings or Blockers

- **Blockers**: none. `blockedReasons: []`, `dependencies.archive: ready`, `reviewGate.result: allow`.
- **Non-blocking warnings**: the 5 items listed above (mutation unavailable, coverage unavailable, provider e2e skipped, vitest no files, condensed TDD evidence). All are `pass_with_warnings` scope; no intentional-with-warnings override was exercised.
- **Next recommended** (per structured status before archive): `archive` — now completed. SDD cycle is closed; ready for next change on `main`.

## SDD Cycle Complete

The change `mvp-chat-citations` has been fully planned, implemented, verified, and archived. `openspec/specs/chat/spec.md` is now the source of truth for the `chat` domain. The archived audit trail is immutable.

## References

- Proposal: `openspec/changes/archive/2026-08-21-mvp-chat-citations/proposal.md`
- Spec (delta, archived): `openspec/changes/archive/2026-08-21-mvp-chat-citations/specs/chat/spec.md`
- Spec (main, source of truth): `openspec/specs/chat/spec.md`
- Design: `openspec/changes/archive/2026-08-21-mvp-chat-citations/design.md`
- Tasks: `openspec/changes/archive/2026-08-21-mvp-chat-citations/tasks.md` (18/18)
- Verify report: `openspec/changes/archive/2026-08-21-mvp-chat-citations/verify-report.md`
- Native review lineage: `review-c59f37d243d28dcf` — `sha256:c59f37d243d28dcfb3906913744322d273176ce773be81e59790475737a296a9`
- Canonical strict report SHA-256: `204b4cbb742c0f1d454789ae804dea5a675f786766aa3f322463c277678e5cf7`
