# Design: MVP Evaluation Harness

## Technical Approach

`apps/eval` (`raguard-eval`) loads fixtures, opens a guarded disposable Postgres DB, seeds corpus rows, and calls `retrieve_chunks`, `build_completion_prompt`, and `verify_citations` with an eval SHA-256 content-hash embedder plus `FakeCompleter`. Product `Settings` and API routes unchanged. Proof: `offline-synthetic` — not live-model refusal or semantic quality. Spec `evaluation`: 5 requirements, 12 scenarios. ADRs 0001–0003, 0005.

**Config**: this design **resolves/supersedes** the reversible proposal assumption `eval/config.yaml`. Use `eval/config.json` (stdlib JSON; no PyYAML). Product scope unchanged.

## Architecture Decisions

| Decision | Options / tradeoff | Choice |
|----------|--------------------|--------|
| Package | `apps/eval` vs tests-only | `apps/eval/src/raguard_eval/`; `raguard-eval = raguard_eval.cli:main` |
| CLI / deps | argparse vs click; yaml vs json | stdlib argparse + JSON; `eval/config.json` supersedes proposed YAML |
| Imports | routers vs seams | Allow: `AuthorizationScope`, `CHAT_USE`, `retrieve_chunks`, `build_completion_prompt`, `SYSTEM_PROMPT`, `UNTRUSTED_SOURCES_*`, `verify_citations`, `CitationVerificationError`, `FakeCompleter`, `EMBEDDING_DIMENSION`, `Tenant`/`Document`/`Chunk`/`DocumentStatus`, `Settings`. Never routers, OpenAI, pytest fixtures |
| Embedder | `FakeEmbedder` collapses seeds | SHA-256(token) → axis `% 1536`, L2; per-case probes |
| Database | import `migrated_db` vs clone | `raguard_eval_{hex12}` only; Alembic `apps/api/alembic.ini`; `DROP … WITH (FORCE)` in `finally` |
| Thresholds / live | product Settings vs eval; `--live` | `eval/config.json` + manifest; dummy `jwt_secret` unreported; no `--live` |

## Data Flow

```
argv → parse → validate (exit 3, no verdict) → CREATE raguard_eval_* → migrate → seed
  → per case (id order): scope; snapshot embedder/completer counts
       no chat.use → skip retrieve/prompt/complete
       else retrieve_chunks → prompt → FakeCompleter → verify_citations
       score with (after-before) deltas
  → metrics → Report → atomic JSON → stdout from same model
finally DROP DATABASE
```

## File Changes

Create `apps/eval/pyproject.toml` (`raguard-api` only) and `apps/eval/src/raguard_eval/{__init__,__main__,cli,errors,dataset,db,seed,embedder,runner,metrics,report}.py`. Create `apps/eval/tests/{unit,integration}/` (12 scenarios) and `eval/datasets/mvp-v1/{manifest,corpus,actors}.json` + `cases.jsonl`. Create `eval/config.json` (`k`, `draft_precision_at_10: 0.70`). Modify `pyproject.toml`, `uv.lock`, `.gitignore` (`eval/reports/`), and `.github/workflows/ci.yml` (same `python` job; CLI without `--fail-under-precision`; upload artifact). Do not edit `apps/api/src/raguard_api/*`.

## Interfaces / Contracts

**CLI**: `--dataset` `eval/datasets/mvp-v1`; `--config` `eval/config.json`; `--output` `eval/reports/latest.json`; `--fail-under-precision FLOAT` opt-in; `--k` 10. No `--live`.

**Exits**: 0 pass; 2 invariant or opted-in precision; 3 schema/duplicate, no verdict; 1 internal, DB down, or non-atomic write. Ordinary CI omits the precision flag, so **exit 2 means invariant**. Never infer precision vs invariant from the code — use `failure_reasons`.

**Dataset**: JSON only, no exec. Manifest `schema_version=1`, `dataset_id=mvp-v1`, `draft_precision_at_10=0.70`. Corpus: tenants/docs/chunks + content. Actors: `id`, `tenant_id`, `capabilities`. Cases JSONL: `id`, `kind` ∈ relevant|neutral|cross-tenant|capability-denied|adversarial, `actor_id`, `query`, `relevant_chunk_ids`, optional `top_k`, `completion_text` (default `[1]` if retrieved else `""`). UUIDs: `uuid5(NAMESPACE_URL, "raguard.eval.mvp-v1:{kind}:{id}")`. Reject unknown schema, missing kinds, duplicate ids, oversize query, password/api_key/token/secret keys.

**`dataset_sha256`**: SHA-256 of `manifest.json`, `corpus.json`, `actors.json`, `cases.jsonl` in that order. Each file is `uint64_be(len(raw)) || raw`; concatenate (length-prefix; no collision).

**Metrics**: relevant only; empty `Rk` → P@k `0.0`; empty Rel excluded from R/hit. Neutral not in P/R; fidelity `1` iff `Rk=[]`. Citation validity = valid/total if markers>0 else `null` (excluded); count honest empties. Leak via fixture-id tenant map. No per-document role grants.

**Capability-denial**: shared counters are not proof. Per case snapshot `e0,c0` before work; unauthorized iff `(embedder.calls-e0)>0` or `(completer.calls-c0)>0`. Denied cases must not call retrieve/prompt/complete.

**Prompt-boundary** (not live-model immunity): (1) `system_prompt` byte-equals `SYSTEM_PROMPT`; (2) `user_prompt` has one outermost `UNTRUSTED_SOURCES_START` then a later `UNTRUSTED_SOURCES_END`; (3) all serialized source JSON, including adversarial marker-like text, lies strictly between those delimiters. Citation membership is separate.

**Report allowlist** (frozen, case-id order): `schema_version`, `proof_scope`, `dataset_id`, `dataset_sha256`; settings `{k, rrf_k, retrieval_candidates, retrieval_ef_search, retrieval_semantic_max_distance}`; thresholds `{draft_precision_at_10, fail_under_precision}` (null if unset); aggregates; `cases`; `failure_reasons`; `verdict`. **Exclude** DB URLs, JWT secrets, provider keys/models, actor emails, env. Reasons: `tenant_leak`, `unauthorized_execution`, `citation_out_of_set`, `malformed_citation_accepted`, `prompt_boundary_violation`, `precision_below_threshold`.

**Atomic write**: temp in dest dir; write; file `flush`+`fsync`; `os.replace`; dest-dir `fsync` when supported; any failure → unlink temp, exit 1.

## Testing Strategy

Unit (no DB): validate, P/R empty, null citation, hash, per-case deltas, delimiters, atomic write, exits, no `--live`. Integration: real `retrieve_chunks`; leak 0; denied delta 0; prompt-boundary (`raguard_eval.db` + CI Postgres). No e2e. RED-GREEN: (1) dataset+metrics+report+cli (2) db+seed+runner (3) fixtures+CI. CI hard-fails 1/2/3; 2 = invariant.

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Documentation-like paths | N/A: JSON data only; never executed (`requirements.txt`, `README.sh`, MDX unused) | `json.loads` only | none |
| Git repository selection | N/A: no `git`, `-C`, or repo path args | cwd unused for VCS | none |
| Commit state | N/A: no commit/index/worktree | — | none |
| Push state | N/A: no push/refspec | — | none |
| PR commands | N/A: no `gh`/PR composition | — | none |

## Migration / Rollout

No API/schema migration. Rollback: delete `apps/eval/`, `eval/`, workspace/CI/gitignore lines.

## Open Questions

None.

## Workload

~1000–1250 authored lines (code ~550, tests ~350, fixtures ~180, CI ~40). **400-line budget risk: High**. `Decision needed before apply: No`. `Chained PRs recommended: Yes`.
