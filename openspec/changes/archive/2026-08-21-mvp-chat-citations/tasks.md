# Tasks: MVP Chat with Verifiable Citations

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,300–1,550 total; PR1 ~210, PR2 ~390, PR3 ~215, PR4 ~380, PR5 ~280 |
| 400-line budget risk | Medium (PR2/PR4 borderline; fallback below) |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 (stacked to main) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

Split note: the four natural slices stay in order; slice 1 (extraction + chat core) exceeds 400 lines, so it ships as PR1 (extraction) + PR2 (chat core). Fallback during apply: split citations out of PR2 or router out of PR4 if either crosses 400.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Behavior-preserving retrieval extraction | PR 1 | `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_retrieval_service.py apps/api/tests/integration/test_retrieval_routes.py -m 'not e2e'` | compose stack: existing search route tests run end-to-end | revert `retrieval/` only; never deploy chat if search regresses |
| 2 | Chat contracts, prompt, citation verifier | PR 2 | `POSTGRES_PORT=55432 uv run pytest apps/api/tests/unit/test_chat_{contracts,prompts,citations}.py -m 'not e2e'` | N/A — offline pure logic | revert `chat/` core; unrouted |
| 3 | OpenAI completer + chat settings | PR 3 | `POSTGRES_PORT=55432 uv run pytest apps/api/tests/unit/test_chat_{provider,settings}.py -m 'not e2e'` | N/A — lazy client, offline; real call only in opt-in e2e | revert `chat/providers/` + chat settings |
| 4 | Chat router + app wiring | PR 4 | `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_chat_routes.py -m 'not e2e'` | compose stack + httpx with `FakeCompleter` wired | revert `chat/router.py` + `main.py` |
| 5 | Release gates + polish | PR 5 | `POSTGRES_PORT=55432 uv run pytest apps/api/tests/integration/test_chat_release_gates.py -m 'not e2e'`; then full `uv run pytest -m 'not e2e' && pnpm test` | opt-in `OPENAI_API_KEY uv run pytest -m e2e` smoke | revert gate tests/fixes |

## PR 1: Shared Retrieval Extraction (behavior-preserving)

- [x] 1.1 RED: `tests/integration/test_retrieval_service.py` — `retrieve_chunks(session_factory, scope, settings, query, top_k)` returns ordered `FusedResult` tuple matching current search fusion (tenant predicate first, RRF, top_k cap).
- [x] 1.2 GREEN: create `retrieval/service.py` with `retrieve_chunks`; move `_keyword_candidates`/`_semantic_candidates`/`_candidate` from `retrieval/router.py`; export via `retrieval/__init__.py`.
- [x] 1.3 GREEN: refactor `retrieval/router.py` `search` to call `retrieve_chunks`; `tests/integration/test_retrieval_routes.py` + `test_retrieval_isolation.py` pass unchanged.

## PR 2: Chat Contracts, Prompt, Citation Verifier

- [x] 2.1 RED: `tests/unit/test_chat_contracts.py` — `ChatRequest` rejects blank/oversized query, `top_k` defaults 10 capped at `retrieval_top_k_max`; `Citation`/`ChatResponse` allowlist only `chunk_id, document_id, document_name, position, content`.
- [x] 2.2 RED: `tests/unit/test_chat_prompts.py` — static secret-free system prompt; chunks JSON-encoded inside untrusted-source delimiters; document instructions stay data.
- [x] 2.3 RED: `tests/unit/test_chat_citations.py` — `[n]` resolves to exact retrieval tuple; index outside 1..len rejects response; missing markers → `[]`; dedup first occurrence; deterministic mapping.
- [x] 2.4 GREEN: create `chat/{__init__,contracts,prompts,citations}.py` implementing 2.1–2.3; `CompletionPrompt`, `ChatCompleter` protocol, `FakeCompleter` in contracts.

## PR 3: OpenAI Completer + Settings

- [x] 3.1 RED: `tests/unit/test_chat_provider.py` — `OpenAICompleter.complete` uses lazy `max_retries=0` client, `max_output_tokens` bound, timeout; truncation accepted; retry only timeout/connection/429/5xx, ≤2 backoff; exhausted → typed failure, no detail leak.
- [x] 3.2 RED: `tests/unit/test_chat_settings.py` — `chat_model="gpt-4o-mini"`, `chat_max_output_tokens=500` (1..2000), `chat_retries=2` (0..2), reuse `provider_timeout_seconds`; startup guard.
- [x] 3.3 GREEN: create `chat/providers/{__init__,openai}.py`; extend `config.py` + `.env.example`.

## PR 4: Chat Router + App Wiring

PR4 landed at 392 authored lines. Route-level failure-gate tests (provider
503, out-of-set citation 503; overlap with 5.2) deferred to a PR4b
continuation for the 400-line budget; unit-level coverage exists from PR2/PR3.

PR4b (landed, test-only, +63 lines in `test_chat_routes.py`): route-level
failure gates covered at the HTTP boundary — a typed `CompletionError` and an
out-of-set citation marker both assert the exact generic 503 envelope
`{error: {code: "service_unavailable", message: "Chat unavailable"}}` with no
partial answer/citations and no detail leak. Focused route file 12 passed;
full offline suite 371 passed, 1 deselected; ruff check + format clean;
pnpm test exit 0. Tasks 1.1-4.4 unchanged; 5.2 still owns the leak-gate sweep
and any fixes in PR5.

- [x] 4.1 RED: `tests/integration/test_chat_routes.py` — 400 invalid query/top_k with zero retrieval+provider calls; 401 missing/invalid token; 403 missing `chat.use`; 200 `{answer, citations}` ≤ top_k; fresh authz per request.
- [x] 4.2 RED: no-evidence — empty corpus vs populated no-match yield byte-identical 200 `{answer: null, citations: []}`, zero completer calls (FakeCompleter records).
- [x] 4.3 GREEN: create `chat/router.py` `create_chat_router(session_factory, settings, embedder, completer)`; `POST /api/chat` orchestration: fresh scope + `require_capability(CHAT_USE)`, `retrieve_chunks`, short-circuit, `asyncio.to_thread(completer.complete)`, verifier, typed `ChatResponse`.
- [x] 4.4 GREEN: wire `main.py` — construct lazy `OpenAICompleter`, include chat router.

## PR 5: Release Gates + Polish

PR5 landed at ~375 authored lines (integration-only). Release-gate tests
(5.1-5.3) shipped in `tests/integration/test_chat_release_gates.py`
(+367 lines): cross-tenant chat isolation, adversarial-document prompt
injection, provider retry-exhaustion 503 through the real completer, and the
response/error leak sweep. 5.4's e2e smoke is authored and verified (collects,
skips cleanly without `OPENAI_API_KEY`) but ships in a PR5b continuation for
the 400-line budget: +123 lines in `tests/e2e/test_chat_e2e.py`. Full offline
suite 376 passed, 2 deselected; ruff check + format clean; pnpm test exit 0.
Tasks 1.1-4.4 unchanged.

PR5b (landed, test-only, +123 lines in `tests/e2e/test_chat_e2e.py`): 5.4's
opt-in e2e smoke is verified on branch `test/mvp-chat-citations-provider-e2e` —
gated run `POSTGRES_PORT=55432 uv run pytest apps/api/tests/e2e/test_chat_e2e.py
-m e2e -v` collects the module and skips cleanly (1 collected, 1 skipped,
exit 0) because `OPENAI_API_KEY` is absent; NO provider pass claimed. Module
imports resolve against the shipped chat/retrieval/auth code; ruff check +
format clean; full offline suite 376 passed, 2 deselected; pnpm test exit 0;
git diff --check clean. Provider evidence remains conditional: verify must run
the smoke with a real key. Tasks 1.1-5.3 unchanged; all 18 tasks complete,
final independent verification still pending.

- [x] 5.1 RED: `tests/integration/test_chat_release_gates.py` — cross-tenant: tenant A query matching only tenant B chunks → neutral, zero provider calls, no disclosure; adversarial doc "ignore prior instructions" never followed/revealed.
- [x] 5.2 RED: failure gates — provider exhausted retries → 503 safe envelope (no partial, no fallback); out-of-set citation → 503; answer/citations/errors leak no tenant id, provider key, or internal detail.
- [x] 5.3 GREEN: fix gaps surfaced by 5.1–5.2; full offline suite `POSTGRES_PORT=55432 uv run pytest -m 'not e2e' && pnpm test` green.
- [x] 5.4 OPT-IN: `tests/e2e/test_chat_e2e.py` smoke with real `OPENAI_API_KEY` (marker `e2e`; standard runner stays offline). — **PR5b (landed)**: +123 lines in `tests/e2e/test_chat_e2e.py`; verified collects and skips cleanly without the key; real-provider pass pending `OPENAI_API_KEY` at verify.
