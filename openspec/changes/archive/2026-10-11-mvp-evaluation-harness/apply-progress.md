# Apply Progress: mvp-evaluation-harness

**Change**: `mvp-evaluation-harness`
**Mode**: Strict TDD (passive docs slice — structural readback is proportional verification)
**Artifact store**: OpenSpec only
**Delivery strategy**: `auto-chain` | **Chain strategy**: `stacked-to-main`
**Review budget**: 400 changed lines per PR
**Base**: `660ff14` (`main` origin clean) → `382fdc9` (after PR1 merge)
**Branch flow**: `feat/mvp-evaluation-harness` → `feat/mvp-evaluation-harness-01-proposal` (PR1 merged) → `feat/mvp-evaluation-harness-02-contract` (PR2) → `feat/mvp-evaluation-harness-03-dataset` (next)

## Progress

### PR1 — Unit 1 / Task 1.1 — MERGED

- [x] 1.1 Land `exploration.md`+`proposal.md` (PR1) — **done**

**Commit (PR1)**: `845bff2` `docs(evaluation): land exploration and proposal for MVP evaluation harness` on `feat/mvp-evaluation-harness-01-proposal` | **Merge**: `382fdc9` via `gh pr merge --merge` (PR #32) | **PR1**: [#32](https://github.com/jonasotoaguilar/raguard/pull/32) → `main` — **MERGED** 2026-08-24T22:19:55Z | **Issue**: [#31](https://github.com/jonasotoaguilar/raguard/issues/31) — `enhancement` + `status:approved` — **OPEN** (reopened after PR1 auto-close)

**Files PR1**: `exploration.md` 239 + `proposal.md` 74 = **313 changed lines**

Verification PR1: `test -f exploration.md && test -f proposal.md` → `ok` (exit 0). No runtime harness — passive docs only.

### PR2 (this slice) — Unit 2 / Task 1.2 — COMMITTED (to be merged to `main`)

- [x] 1.2 Land `specs/evaluation/spec.md`+`design.md`+`tasks.md` (PR2) — **done**

**Commit (PR2)**: `feat/mvp-evaluation-harness-02-contract` → `main` — docs/OpenSpec contract slice | **Issue**: [#31](https://github.com/jonasotoaguilar/raguard/issues/31) (canonical chain, remains OPEN) | **Depends on**: PR #32 merged (`382fdc9`) | **Position**: 2 of 8 (`stacked-to-main`)

**Files in this work unit (PR2 diff vs `main` @ `382fdc9`)**:

| File | Action | Lines |
|------|--------|-------|
| `openspec/changes/mvp-evaluation-harness/specs/evaluation/spec.md` | Created | 99 |
| `openspec/changes/mvp-evaluation-harness/design.md` | Created | 80 |
| `openspec/changes/mvp-evaluation-harness/tasks.md` | Created (1.1 `[x]` + 1.2 `[x]`) | 55 |
| `openspec/changes/mvp-evaluation-harness/apply-progress.md` | Created (cumulative) | ~85 |
| **Total PR2** |  | **~319 changed lines** (99+80+55+85) — under 400 budget |

Byte-identity preserved from planning: `spec.md` SHA `b3749e5cc46761edea205c2e6c1adb4a51244e3c85c075dbf37048ee003a47c8`, `design.md` SHA `10c93cec65d8838b16494b3d321a52eef32bef06dbdfabd7b5017c147737e322`, `tasks.md` pre-PR2 SHA `fab76d4a01ffda05fe923da31fe0503cb65c38c4fcb8d5d88e0f77c7af520f8c` (1.1 `[x]`), `apply-progress.md` prior SHA `6b5d60a26c854ff23c2b0128935accda22e7ca95f70120089a1c10112d5a66bf` — all verified before edit; `tasks.md` edit is exactly one checkbox `- [ ] 1.2` → `- [x] 1.2`.

Verification PR2 (structural readback — proportional check): `test -f specs/evaluation/spec.md && test -f design.md && test -f tasks.md` → `ok` (exit 0). No runtime harness acquisition — passive contract docs only per slice instructions (STOP if harness becomes necessary).

### TDD Cycle Evidence (Strict TDD — passive docs slice)

| Task | Test File / Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-------------------|------------|-----|-------|-------------|----------|
| 1.1 exploration+proposal | `test -f exploration.md` (structural) | N/A (new docs) | `test -f` fails before apply (untracked → not on `main`) | `test -f` passes after PR1 commit (313 lines) | ➖ Skipped: docs only, single output — no branching logic | ➖ None needed |
| 1.2 spec+design+tasks | `test -f tasks.md` (structural) | ✅ `main` @ `382fdc9` clean (existing `proposal.md` readback still passes) | `test -f specs/evaluation/spec.md` fails before PR2 (untracked) | `test -f` passes after PR2 commit (spec 99 + design 80 + tasks 55) | ➖ Skipped: contract docs only, no logic to triangulate | ➖ None needed |

Test summary: 2 structural readback checks written, 2 passing; layers: structural docs (2); pure functions: 0; approval tests: none — no refactoring.

### Work Unit Evidence

**PR1**:

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `test -f "openspec/changes/mvp-evaluation-harness/proposal.md" && test -f "openspec/changes/mvp-evaluation-harness/exploration.md" && echo ok` → `ok` (exit 0) |
| Runtime harness and exact result | N/A — passive planning docs only; no runtime boundary (no service/DB/provider) |
| Rollback boundary | Exact files: `exploration.md`, `proposal.md` — `git revert <PR1-commit>` or delete 2 files |

**PR2 (this slice)**:

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `test -f "openspec/changes/mvp-evaluation-harness/tasks.md" && test -f "openspec/changes/mvp-evaluation-harness/specs/evaluation/spec.md" && test -f "openspec/changes/mvp-evaluation-harness/design.md" && echo ok` → `ok` (exit 0) |
| Runtime harness and exact result | N/A — passive contract docs only; no runtime boundary exists (no service, DB, or provider) — proportional check complete per strict-TDD slice instruction |
| Rollback boundary | Exact files: `specs/evaluation/spec.md`, `design.md`, `tasks.md` (1.2 checkbox), `apply-progress.md` — revert this commit only; does not remove PR1 `exploration.md`/`proposal.md` nor any runtime `apps/eval/` code |

## Remaining Tasks

- [x] 1.1 (PR1 merged) | - [x] 1.2 (PR2 this slice)
- [ ] 2.1 RED `test_dataset.py` | - [ ] 2.2 GREEN `dataset.py`+`errors.py`
- [ ] 3.1 `metrics.py` | - [ ] 3.2 `report.py`
- [ ] 4.1 `cli.py`+`__main__.py` + `.gitignore`
- [ ] 5.1 `embedder.py` + `db.py`+`seed.py`
- [ ] 6.1 `runner.py`
- [ ] 7.1 `eval/datasets/mvp-v1/{manifest,corpus,actors}.json`+`cases.jsonl`
- [ ] 7.2 `.github/workflows/ci.yml` + `docs/CODEBASE-GUIDE.md`+`docs/codebase/mental-model.md`

Total: 2 / 11 tasks complete (PR1+PR2). Next slice: PR3 `feat/mvp-evaluation-harness-03-dataset` — `dataset.py`+hash (Unit 3).

## Delivery / Chain Context

- Mode: stacked PR slice (`stacked-to-main`)
- Current work unit: Unit 2 — Spec+design+tasks (PR2)
- Boundary: starts from `382fdc9` (`main` after PR1); ends with `spec.md`+`design.md`+`tasks.md`+cumulative `apply-progress.md` landed on `main` (PR2 merge)
- Review budget impact: PR1 313/400 + PR2 ~319/400 — each slice autonomous and under budget
- Next PR purpose: PR3 dataset+hash (250–320 lines)
- Chain diagram (📍 = this slice):

```text
main @ 660ff14
 └─ PR1 feat/mvp-evaluation-harness-01-proposal -> main (exploration+proposal, 313 lines, MERGED #32)
     └─ 📍 PR2 feat/mvp-evaluation-harness-02-contract -> main (spec+design+tasks, ~319 lines, this PR)
         └─ PR3 feat/mvp-evaluation-harness-03-dataset -> main
             └─ PR4 ...
                 └─ PR8
```

## Verification

- Pre-merge PR2: `git diff main --stat` shows exactly 4 paths above (spec 99, design 80, tasks 55, apply-progress ~85) — no runtime/UI/migration touched.
- Structural readback on branch: `test -f specs/evaluation/spec.md && test -f design.md && test -f tasks.md && grep -q "^\- \[x\] 1\.2" tasks.md && echo ok` → `ok`.
- Structural readback on `main` post-merge will be same 4 paths; byte identity of spec/design/tasks verified via SHA before commit.
- CI expectation (pre-merge): `Check PR Cognitive Load` PASS (<400), `Check Issue Reference` PASS (`Related to #31` or hidden `Closes #31` depending on required closing keyword), `Check Issue Has status:approved` PASS (#31 approved+OPEN), `Check PR Has type:* Label` PASS (`type:docs`).

## Post-merge branch state (planned)

- After PR2 merge: `main` advances to include `spec.md`+`design.md`+`tasks.md`+`apply-progress.md`; delete remote/local `feat/mvp-evaluation-harness-02-contract` safely; create `feat/mvp-evaluation-harness-03-dataset` from updated `main` for Unit 3 strict-TDD dataset work.
- Issue #31 verified OPEN after merge (reopen immediately if mandatory `Closes` keyword auto-closed it); canonical for PR3–PR8.

## Risks

- PR2 docs-only — no code, no DB, no provider; rollback is isolated delete of 4 files.
- Pre-existing `uv run pytest` harness remains green (docs don't affect imports); no new deps.

## Next Recommended

`sdd-apply` PR3 — deliver `dataset.py`+`errors.py` + hash/validation strict-TDD (Unit 3, tasks 2.1–2.2) on `feat/mvp-evaluation-harness-03-dataset`.

## PR3 — Unit 3 / Tasks 2.1–2.2 — CORRECTED (uncommitted, on `feat/mvp-evaluation-harness-03-dataset`)

- [x] 2.1 + 2.2: `apps/eval/tests/unit/test_dataset.py` (15 cases: valid start, uuid5 stability, length-prefix/order hash, `json.loads`-only guard, 11 parametrized invalid variants = 7 original + 4 collection-shape `documents/chunks × str/dict` → `DatasetInvalid` exit 3, no verdict); `dataset.py` hardened `_unique_ids(items: object)` to fail-closed (`not list` → `entries must be a list`; `not dict` → `entry must be an object`, net 0 via removing 2 now-duplicate pre-checks `actors list` + `cases dict` with same exit 3/no-verdict contract, messages only) + `errors.py` (`exit 3`); scaffold/workspace unchanged; no new tenants/missing-documents policy (tenants-malformed already fail-closed via unknown-tenant; missing-documents default `[]` preserved per spec/design scope; immediate blocker was collection type safety only).
- TDD evidence (strict): RED `AttributeError: 'str' object has no attribute 'get'` on all 4 shapes (`documents/chunks × str/dict` via `_unique_ids.item.get`) → GREEN `DatasetInvalid` exit 3 no-verdict on all 4 → TRIANGULATE (str vs dict both fail-closed; prior order-swap hash + white-box path still green) → REFACTOR (grouped `else: field,shape=variant.split` for 4 shapes in 3 lines; `_case` kind→rel mapping removes sequential override). Focused `uv run pytest apps/eval/tests/unit/test_dataset.py` → 15 passed; full `uv run pytest -m 'not e2e'` → 264 passed / 127 skipped / 2 deselected; `pnpm test` → exit 0 (vitest no files); `ruff check` clean; `ruff format --check` would vertically expand 11-variant list (+9, not applied; compact 2-line list kept per concise-parametrization budget instruction). Runtime harness: N/A.
- Workload (strict A+D vs `main`, `git add -N` + `git diff main --numstat`): 404 = 19+3+201+11+141 (untracked `pyproject/__init__/dataset/errors/test`) +7 (`apply-progress`) +4 (`tasks` 2+2) +6 (`pyproject` 3+3) +12 (`uv.lock`); honest savings applied (dedup −4 offsets hardening +4; grouped 4-in-3 vs naive +8; `_case` mapping −2; compact decorator avoids +9 format expansion); no code-golf, no weakened assertions, no docs deletion, lockfile counted; remaining gap 4 with no further honest cohesive cut → BLOCKED, no `size:exception` invented (single corrective rerun token parent-owned, not settled).
- Rollback: delete `apps/eval/` + revert `pyproject.toml`/`uv.lock` workspace lines; tasks 2.1/2.2 back to `- [ ]`; files touched this rerun only `dataset.py`+`test_dataset.py`+`apply-progress.md`. Remaining: 3.1, 3.2, 4.1, 5.1, 6.1, 7.1, 7.2. Next: parent decides re-slice vs `size:exception`; do not commit/push/open PR.

## PR4 — Unit 4 / Tasks 3.1–3.2 — metrics+report (uncommitted, on `feat/mvp-evaluation-harness-04-metrics-report`)

- [x] 3.1: `metrics.py` (68) — relevant-only `precision_at_k`/`recall_at_k`/`hit_rate_at_k`; empty Rk → 0.0; empty Rel → `None` (excluded); `neutral_fidelity` 1.0 iff Rk empty; `citation_validity` valid/total else `None`; `mean_or_none` skips excluded; `citation_markers` helper.
- [x] 3.2: `report.py` (80) — `build_report` frozen allowlist (`schema_version`,`proof_scope`,`dataset_id`,`dataset_sha256`,`settings`,`thresholds`,`aggregates`,`cases`,`failure_reasons`,`verdict`); settings 5 keys, thresholds 2 keys (null if unset); case-id ordering; unknown reason/verdict → `ValueError`; secrets never pass through.
- TDD evidence (strict): RED `ModuleNotFoundError: No module named 'raguard_eval.report'` (both modules, 7 core tests) → GREEN 7 passed → TRIANGULATE +5 (partial-overlap fractions, out-of-range-only 0.0, `[]` non-marker, full settings passthrough, verdict reject) → 12 passed → REFACTOR none (ruff check + format clean, max complexity 3).
- Verification: focused `uv run pytest apps/eval/tests/unit/test_metrics.py apps/eval/tests/unit/test_report.py` → 12 passed; full `uv run pytest -m 'not e2e'` → 276 passed / 127 skipped / 2 deselected; `pnpm test` → exit 0. Runtime harness: N/A (pure functions, no service/DB/provider).
- Workload (strict A+D vs `main`, `git add -N` + `git diff main --numstat`): 296 (68+80+62+86) + tasks 4 + apply-progress ~40 → ≈340 ≤ 400. No code-golf; no weakened assertions.
- Rollback: delete `metrics.py`, `report.py`, `test_metrics.py`, `test_report.py`; tasks 3.1/3.2 back to `- [ ]`. Remaining: 4.1, 5.1, 6.1, 7.1, 7.2. Do not commit/push/open PR (parent owns delivery).

## PR4 corrective rerun — blockers 1+2 (uncommitted, same branch)

- [x] 3.1 set semantics: `precision/recall` use `set(Rk) ∩ set(Rel)` (`recall 1.5 → 0.5` on `[c-1 ×3]` vs `[c-1,c-2]`); 3.2 recursive `_sanitize` on `aggregates`/`cases` (forbidden key fragments + `postgres://`/email/token value filter; preserves `precision_at_10`/`id`).
- TDD strict: RED 2 failed (`assert 1.5 == 0.5`; `postgres://` in blob) + 12 passed → GREEN 14 passed → TRIANGULATE (no-dupe fractions unchanged; nested/`note`/`contact` stripped) → REFACTOR (`ruff format` 1 file, no logic change).
- Verification: focused `uv run pytest apps/eval/tests/unit/test_metrics.py apps/eval/tests/unit/test_report.py` → 14 passed; full `uv run pytest -m 'not e2e'` → 278 passed / 127 skipped / 2 deselected; `pnpm test` → exit 0; `ruff check` clean; `ruff format --check` clean. Harness N/A (pure functions).
- Workload strict A+D vs `main`: 67+129+67+111+tasks 4+apply-progress ~19 → ≈397 ≤ 400; no code-golf/weakened assertions. Rollback: revert `metrics.py` set lines + `_sanitize` wiring + 2 RED tests. Do not commit/push/open PR.

## PR5 — Unit 5 / Task 4.1 — CLI (MERGED #41)

- [x] 4.1: `cli.py`+`__main__.py` — injectable `main(argv, evaluator=...)`; no `--live`; `--fail-under-precision` opt-in; exits 0/2/3/1; atomic report write (temp + flush/fsync + `os.replace`); `.gitignore` covers `eval/reports/`.
- **Merge (PR5)**: `54756b9` via `gh pr merge --merge` (PR #41) from `feat/mvp-evaluation-harness-05-cli` → `main` — **MERGED**; task 4.1 checkbox reconciled to `[x]` in ODD-3 from this observed merge (prior text was stale, not speculative). Remaining: 5.1, 6.1, 7.1, 7.2.
- Verification: `uv run python -m raguard_eval --help` → exit 0, no `--live` option. Runtime harness: CLI help only (no service/DB/provider).
- Rollback: revert `cli.py`, `__main__.py`, `.gitignore` lines; task 4.1 back to `- [ ]`. Do not commit/push/open PR (parent owns delivery).

## PR6 — Unit 6 / Task 5.1 — embedder+DB (uncommitted, on `feat/mvp-evaluation-harness-06-embedder-db`)

- [x] 5.1: `embedder.py` (SHA-256 token → axis `% 1536`, L2; empty text → zero vector — historical at build time; current canonical `EMBEDDING_DIMENSION` is 1024 via migration `0003`, which fail-closes on populated chunks and requires reindex/re-upload) + `db.py`+`seed.py` (unique `raguard_eval_<hex12>` via `apps/api/alembic.ini`; `DROP … WITH (FORCE)` in `finally`; dataset topology preserved, credentials/embeddings never logged).
- TDD evidence (strict): ODD-1 RED `ModuleNotFoundError: No module named 'raguard_eval.embedder'` → GREEN 11 focused tests passed; ODD-2 RED missing `raguard_eval.db` module → corrected GREEN 8 live integration tests passed, 0 skipped.
- Verification: focused `uv run pytest apps/eval/tests/unit/test_embedder.py` → 11 passed; live isolated `uv run pytest apps/eval/tests/integration/test_db.py` → 8 passed / 0 skipped on host port 55432 with zero leftover `raguard_eval_%` databases; full `uv run pytest -m 'not e2e'` → 305 passed / 132 skipped; `pnpm test`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python -m raguard_eval --help` (no `--live`), and `git diff --check` all clean.
- Runtime harness: isolated PostgreSQL on 55432 only — prechecked Docker labels/states and a free port, started only raguard postgres, observed healthy/listening state, confirmed database presence during context and absence after exit (success, body-failure, and migration-failure paths), stopped only raguard postgres, freed 55432, left unrelated `arcane` untouched. An earlier host-port 5432 incident (unrelated holder exit, 5 environment-skipped live tests) is resolved through this isolated 55432 route; the external exit cause remains unattributed but there is no evidence of cross-project targeting.
- Review: native reliability review approved/acknowledged the full committed Phase 5 candidate target `sha256:2129c17ffd8cd57d9b40e033d0b641e0bdcc3cb8a3cf992c8387f8488f8613a6` under lineage `review-a6cec30666581b63` (burned); informational findings only, no correction.
- Workload (strict A+D vs `main`, `git diff main --numstat`): `f537a75` embedder slice 169 (41+128) + `65a47f0` DB/seed slice 551 (110+135+306) = **720** total across 5 files; exceeds the 400 budget, so the inherited `auto-chain` / `stacked-to-main` strategy ships ODD-1 and ODD-2 as separate slices. No code-golf; no weakened assertions.
- Rollback: ODD-1 removes only `embedder.py` + `test_embedder.py`; ODD-2 removes only `db.py`, `seed.py`, `test_db.py`; tasks 5.1 back to `- [ ]`. Phase 5 has no PR opened, published, or merged — no delivery claimed. Do not commit/push/open PR (parent owns delivery).

## PR7 — Unit 7 / Task 6.1 — runner+entry (committed, on `feat/mvp-evaluation-harness-07-runner` @ `dc4b825`)

- [x] 6.1: `runner.py` (298) — offline per-case evaluator (no providers; repeat ranked IDs; per-case embedder/completer deltas; denied skips retrieve/prompt/complete; leak → `tenant_leak` exit 2; `system_prompt` byte-equals `SYSTEM_PROMPT`; outermost `UNTRUSTED_SOURCES_START`/`UNTRUSTED_SOURCES_END` containment; citation-membership gates) + CLI default-evaluator wiring + `raguard-eval` script + `test_runner.py` integration coverage.
- TDD evidence (strict): ODD-1 RED missing `runner` import → GREEN 13 live integration passed, 0 skipped, on isolated postgres 55432; ODD-2 RED default-evaluator replacement + no-`--live` help → GREEN 14 CLI unit passed; skip-gap correction (+17 admin probe with skip, test-only) → 13+14 green; offline-assertion correction (+9/-1 module-delta plus static scan, test-only) → full non-e2e 452 passed exit 0 (prior 451 passed / 1 red from the order-dependent `"openai" not in sys.modules` assertion).
- Verification: focused `uv run pytest apps/eval/tests/integration/test_runner.py` → 13 passed + `uv run pytest apps/eval/tests/unit/test_cli.py` → 14 passed, live on isolated 55432 with zero leftover `raguard_eval_%` databases; full `uv run pytest -m 'not e2e'` → 452 passed exit 0; pnpm / Ruff check / Ruff format / CLI-no-`--live` / script-help / `git diff --check` clean per ODD-3 evidence in `odd/tasks/evaluation-runner.md` (no repo-wide numbers invented; this reconciliation session re-observed `test_cli.py` 14 passed, `python -m raguard_eval --help` exit 0 without `--live`, and `git diff --check` clean — pnpm, Ruff, and the full non-e2e suite remain inherited ODD-3 evidence, not re-run here).
- Review: native reliability review approved/acknowledged ODD-1 target `sha256:e3cf8143…` under lineage `review-e24ec8fd` (burned) and ODD-2-final target `sha256:196e3633…` under lineage `review-de3cc741` (burned).
- Fixes with rationale: skip-gap (`43031d1`) — CLI maps DB-down to exit 1, bypassing the test's `OperationalError` skip, so the test probes admin availability first and skips when the DB is absent (test-only, no production change); offline assertion (`dc4b825`) — the global `"openai" not in sys.modules` assertion broke when the full suite imports openai first, so it now asserts zero provider-module delta plus a static import scan (order-independent, still proves zero provider calls).
- Workload (strict A+D): `958b29d` +755/-0 (runner core) + `37eeeac` +62/-9 (CLI wiring) + `43031d1` +17/-0 (skip-gap) = +834/-9 at `43031d1`, plus `dc4b825` +9/-1 (offline-assertion fix; test-fix insertions 17+9=26) → cumulative vs `main` +842/-9 = 851 A+D across five files (`runner.py`, `test_runner.py`, `cli.py`, `test_cli.py`, `pyproject.toml`); commit-sum 853 A+D counts one replaced line twice. No code-golf; no weakened assertions.
- Rollback: ODD-1 removes only `runner.py` + `test_runner.py`; ODD-2 reverts only CLI default wiring and packaging script changes; task 6.1 back to `- [ ]`. Remaining: 7.1, 7.2. Phase 6 has no PR opened, published, or merged — no delivery claimed. Do not commit/push/open PR (parent owns delivery).

## PR8 — Unit 8 / Tasks 7.1–7.2 — fixtures+CI+docs (committed, on `feat/mvp-evaluation-harness-08-fixtures-ci-docs` @ `1dd38e8`)

- [x] 7.1: `eval/datasets/mvp-v1/{manifest,corpus,actors}.json`+`cases.jsonl` (20 cases: relevant 6, neutral 4, cross-tenant 4, capability-denied 3, adversarial 3 — all five kinds, precision-neutral mix) + `eval/config.json` (`draft_precision_at_10` 0.7, `k` 10; supersedes YAML per resolved convention). (`4642972` +115/-0, 5 files.)
- [x] 7.2: `.github/workflows/ci.yml` python job — `Offline evaluation gate` step runs `uv run raguard-eval --dataset eval/datasets/mvp-v1 --config eval/config.json --output eval/reports/latest.json` with no `--fail-under-precision` (exit 2 stays invariant), placed before `Collect coverage`; `Upload evaluation report artifact` step (`actions/upload-artifact@v7`, `if: always()`, name `eval-report`, path `eval/reports/latest.json`, `if-no-files-found: warn`). Docs: `CODEBASE-GUIDE.md` +1 evaluation-harness row; `mental-model.md` 1-line swap removing the “not yet delivered” statement. (`1dd38e8` +13/-1, 3 files.)
- TDD evidence (fixture-first): RED missing `eval/datasets/mvp-v1/` + `eval/config.json` (harness unrunnable outside synthetic test fixtures) → GREEN `load_dataset(eval/datasets/mvp-v1)` validation passes (UUID5 ids, length-prefixed SHA-256 over four raw files, secret scan clean, no dupes/oversize, all five kinds present) + default CLI run verdict=pass exit=0 on isolated 55432, per ODD-1 evidence in `odd/tasks/evaluation-fixtures-ci-docs.md` (inherited, not re-run here).
- Verification: `uv run pytest apps/eval/tests` → 60 passed / 16 pre-existing DB skips (re-observed here); `git diff --check` → clean (re-observed here); YAML parse plus docs readback green per ODD-2 evidence (inherited). CLI help exposes no `--live` (inherited ODD-3 evidence).
- Review: native reliability review approved/acknowledged ODD-1 target under lineage `review-ca66abd8cc43ec52` and native 4-lens review approved/acknowledged ODD-2-final target under lineage `review-cfe340ac8ac3dc08` (both acknowledged and burned; inherited ODD-1/ODD-2 evidence).
- Workload (strict A+D vs merge-base `ae0840a`, `git diff ae0840a..HEAD --numstat`): 24 fixture artifacts (20 cases + manifest/corpus/actors/config; +115/-0 lines in `4642972`) + CI/docs +13/-1 lines (in `1dd38e8`) → cumulative +128/-1 = 129 A+D across 8 files. No code-golf; no weakened assertions.
- Rollback: ODD-1 removes only `eval/datasets/mvp-v1/` + `eval/config.json`; ODD-2 reverts only the CI step and the two docs hunks; tasks 7.1/7.2 back to `- [ ]`. Remaining: none — harness complete. Phase 7 has no PR opened, published, or merged — no delivery claimed. Do not commit/push/open PR (parent owns delivery).
