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
