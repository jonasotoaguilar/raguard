# Proposal: MVP Evaluation Harness

## Intent

Maintainers cannot measure retrieval quality, citation validity, or isolation/injection evidence before shipping. Retrieval/chat are live; no dataset, runner, or report exists. Add an offline in-repo harness so those claims become release evidence.

## Scope

### In Scope
- Deterministic metrics: precision@k, recall/hit@k, citation validity, neutral fidelity, leakage, injection containment
- Versioned dataset + `mvp-v1` (15–25 questions: relevant, no-match, cross-tenant, adversarial)
- Python CLI `apps/eval` (`raguard-eval`) via stdlib `argparse`; JSON report; exits 0/2/3/1
- Ordinary execution and CI stay offline; no provider secret

### Out of Scope
- Dashboard, UI, API, migration, model-as-judge, third-party eval
- Live providers, `--live`, and real-semantic evaluation (later; unproven here)
- Production route changes; confirming draft ≥70% precision KPI from synthetic fixtures

## Capabilities

> sdd-spec contract. Researched: `tenant-identity`, `jwt-authentication`, `authorization-rbac`, `documents`, `retrieval`, `chat`.

### New Capabilities
- `evaluation`: Offline labeled-dataset runner, deterministic metrics, JSON report, exit-code gates

### Modified Capabilities
- None

## Approach

Exploration Approach A, offline-only argparse. `apps/eval` calls `retrieve_chunks`, `build_completion_prompt`, and `verify_citations` with fakes. Product `Settings` unchanged; thresholds live in eval config/CLI.

- **Proves:** pipeline ranking, metric math, auth/citation/injection contracts
- **Does not prove:** real embedding/model semantic quality. Never calls a live provider. Dataset records draft precision@10 `0.70`; product KPI stays provisional
- **Gates:** zero leakage, 100% citation validity, zero injection following fail immediately. CLI MUST support `--fail-under`. Ordinary CI MAY warn only on provisional precision; CLI MUST NOT be warning-only

## Affected Areas

- New: `apps/eval/`, `eval/datasets/` (schema + `mvp-v1`), gitignored `eval/reports/`, `eval/config.yaml`, `apps/eval/tests/`
- Modified: `pyproject.toml` / `uv.lock` (script entry only; no new deps), `.github/workflows/ci.yml` (offline step + artifact)
- None: `apps/api/src/raguard_api/*` (read-only seams)

## Risks

- Synthetic precision taken as KPI (Med): label offline proof; keep 0.70 provisional
- Fake vs real embedding gap (Med): accept it; live semantic eval is later
- Dashboard/judge creep (Low): non-goals in spec
- Report leaks IDs/secrets (Low): synthetic IDs; citation allowlist

## Rollback Plan

Delete `apps/eval/`, `eval/datasets/`, eval CI step, and workspace entry. No route, migration, or spec change.

## Dependencies

Delivered `retrieve_chunks`, `build_completion_prompt`, `verify_citations`, fakes, `migrated_db`. Specs `retrieval` and `chat` unchanged.

## Success Criteria

- [ ] Offline `raguard-eval` needs no provider secret and emits JSON plus a distinct exit code
- [ ] Report covers precision@k, citation validity, neutral fidelity, leaks, injection containment
- [ ] Security/citation/injection hard-fail; precision can hard-gate on request
- [ ] Offline report is not live semantic proof

## Assumptions (reversible)

- Path `apps/eval`; dataset JSONL + schema; CLI stdlib `argparse`
- CI warns on precision; CLI still hard-gates
- Chat via FakeCompleter + `verify_citations` only

## Workload forecast

~240–320 lines. `400-line budget risk: Low`. Single PR default. `Decision needed before apply: No`. `Chained PRs recommended: No`.
