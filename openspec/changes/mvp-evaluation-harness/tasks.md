# Tasks: MVP Evaluation Harness

## Review Workload Forecast

Estimated changed lines: 1650–2100. Suggested split: PR1→PR8. Delivery strategy: auto-chain.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Slices (stop >400): PR1 313/2; PR2 280–360/3; PR3 250–320/8; PR4 240–300/4; PR5 180–250/6; PR6 220–300/6; PR7 280–360/4; PR8 220–300/8.

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Explore+proposal | PR1→main | `test -f "openspec/changes/mvp-evaluation-harness/proposal.md"` | N/A | files |
| 2 | Spec+design+tasks | PR2→main | `test -f "openspec/changes/mvp-evaluation-harness/tasks.md"` | N/A | spec+design+tasks |
| 3 | Dataset+hash | PR3→main | `uv run pytest "apps/eval/tests/unit/test_dataset.py"` | N/A | dataset+workspace |
| 4 | Metrics+report | PR4→main | `uv run pytest "apps/eval/tests/unit/test_metrics.py" "apps/eval/tests/unit/test_report.py"` | N/A | `metrics.py` `report.py` |
| 5 | CLI/exits | PR5→main | `uv run pytest "apps/eval/tests/unit/test_cli.py"` | `uv run python -m raguard_eval --help` | cli/config/gitignore |
| 6 | Embedder+DB | PR6→main | `uv run pytest "apps/eval/tests/unit/test_embedder.py" "apps/eval/tests/integration/test_db.py"` | Postgres `raguard_eval_*` | `embedder.py` `db.py` `seed.py` |
| 7 | Runner+entry | PR7→main | `uv run pytest "apps/eval/tests/integration/test_runner.py"` | `uv run raguard-eval --help` | runner+script |
| 8 | Fixtures+CI+docs | PR8→main | `uv run pytest "apps/eval/tests"` | `uv run raguard-eval` (omit precision flag; 2=invariant) | datasets+CI+docs |

## Phase 1: Planning (PR1–PR2)

- [x] 1.1 Land `exploration.md`+`proposal.md` (PR1).
- [x] 1.2 Land `specs/evaluation/spec.md`+`design.md`+`tasks.md` (PR2).

## Phase 2: Dataset (PR3)

- [ ] 2.1 RED `test_dataset.py`: valid starts; bad schema/dupes/kinds/secrets/oversize → exit 3, no verdict (Valid/Invalid dataset).
- [ ] 2.2 GREEN `dataset.py`+`errors.py`: `json.loads` only; uuid5; `dataset_sha256` = SHA-256 of `manifest.json`,`corpus.json`,`actors.json`,`cases.jsonl` in that order, each `uint64_be(len(raw))||raw`. REFACTOR.

## Phase 3: Metrics + report (PR4)

- [ ] 3.1 RED/GREEN `metrics.py`: empty-Rk P=R=0.0; empty Rel excluded; neutral fidelity 1.0; citation null if no `[n]` (Neutral not precision, Missed relevant).
- [ ] 3.2 RED/GREEN `report.py` case-id order. Allow `schema_version`,`proof_scope`,`dataset_id`,`dataset_sha256`; settings `k`,`rrf_k`,`retrieval_candidates`,`retrieval_ef_search`,`retrieval_semantic_max_distance`; thresholds `draft_precision_at_10`,`fail_under_precision` (null if unset); aggregates;`cases`;`failure_reasons`;`verdict`. Exclude DB URL, JWT/provider secrets/keys/models, actor emails, env.

## Phase 4: CLI (PR5)

- [ ] 4.1 RED/GREEN `cli.py`+`__main__.py`: injectable `main(argv, evaluator=...)`; no `[project.scripts]`. No `--live`; `--fail-under-precision` opt-in; exits 0/2/3/1 (Pass report, Distinct exits, Precision gate, Invariant hard-fail). `eval/config.json` supersedes YAML. Atomic dest-dir temp; write; file flush+fsync; `os.replace`; dest-dir fsync when supported; any failure unlinks temp, exit 1. `.gitignore` `eval/reports/`.

## Phase 5: Embedder + DB (PR6)

- [ ] 5.1 RED/GREEN `embedder.py`: SHA-256 token → axis `% 1536` L2; length exactly 1536. GREEN `db.py`+`seed.py`: `raguard_eval_{hex12}` via `apps/api/alembic.ini`; `DROP … WITH (FORCE)` finally.

## Phase 6: Runner (PR7)

- [ ] 6.1 RED/GREEN `runner.py`: no providers; repeat ranked IDs; per-case embedder/completer counts before work; unauthorized iff after-before >0; denied skips retrieve/prompt/complete; leak → `tenant_leak` exit 2. `system_prompt` byte-equals `SYSTEM_PROMPT`. Outermost `UNTRUSTED_SOURCES_START` then later `UNTRUSTED_SOURCES_END`; all serialized source JSON, including adversarial marker-like text, strictly between them (inner occurrences allowed). Citation membership separate (Offline, Repeat, Capability denial, Structural containment, Invariant hard-fail). Wire script + default evaluator.

## Phase 7: Fixtures + CI + docs (PR8)

- [ ] 7.1 Add `eval/datasets/mvp-v1/{manifest,corpus,actors}.json`+`cases.jsonl` (15–25, all kinds).
- [ ] 7.2 `.github/workflows/ci.yml` python job: omit `--fail-under-precision` so exit 2=invariant; hard-fail 1/2/3; upload report. Update `docs/CODEBASE-GUIDE.md`+`docs/codebase/mental-model.md`.
