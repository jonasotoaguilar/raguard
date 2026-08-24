# Design: MVP Chat with Verifiable Citations

## Technical Approach

Extract the current `/api/search` orchestration into `retrieval.service.retrieve_chunks`; both search and chat pass a freshly resolved `AuthorizationScope`. The service retains query embedding, independent tenant-predicated FTS/vector sessions, RRF, and top-k semantics. `POST /api/chat` then short-circuits empty evidence, builds a static grounded prompt, calls an OpenAI adapter, and verifies numbered citations before typed serialization. This implements the chat spec and ADR-0002/0005 without persistence.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Shared service vs internal HTTP | Extraction risks search regression; HTTP duplicates auth/error work. | Extract one in-process service; preserve existing search tests byte-for-byte. Routers independently resolve fresh auth and require `chat.use`. This resolves the archived retrieval spec's stated capability ambiguity exactly as its implemented design did; it does not weaken retrieval to `corpus.view`. |
| Provider text vs structured tools | Numbered text is simpler but requires defensive parsing. | `ChatCompleter` accepts provider-neutral prompt DTOs; `OpenAICompleter` alone uses the OpenAI Responses API. Prompt construction and citation verification remain provider-free. |
| Retry/failure behavior | Retries add latency; fallback would violate grounding. | OpenAI SDK retries are disabled. Retry only timeout/connection/429/5xx failures, at most 2 retries with bounded exponential waits; all exhausted/provider-invalid/citation-invalid outcomes become generic 503 with no partial answer. |
| Citation ordering | Model order can repeat markers. | `[n]` indexes the exact ordered retrieval tuple. Reject any index outside `1..len(results)`; otherwise deduplicate by first occurrence and map deterministically. Missing markers are valid empty citations. |

## Data Flow

```mermaid
sequenceDiagram
  Client->>Chat Router: POST /api/chat {query, top_k?}
  Chat Router->>AuthZ: verify JWT; fresh resolve; require chat.use
  Chat Router->>Retrieval Service: query, top_k, scope
  Retrieval Service->>PostgreSQL: tenant-filtered FTS || vector
  Retrieval Service-->>Chat Router: ordered FusedResult tuple
  alt no evidence
    Chat Router-->>Client: 200 {answer:null,citations:[]}
  else evidence
    Chat Router->>Prompt Builder: query + JSON-encoded untrusted chunks
    Chat Router->>OpenAI Completer: bounded completion
    Chat Router->>Citation Verifier: untrusted text + exact tuple
    Chat Router-->>Client: typed answer + verified citations
  end
```

Dependency direction: `chat.router -> retrieval.service + chat.{contracts,prompts,citations}`; `chat.providers.openai -> chat.contracts`; provider code never imports routers, retrieval, auth, or persistence.

## File Changes

| File | Action | Ownership |
|---|---|---|
| `retrieval/service.py`, `retrieval/router.py` | Create/modify | `retrieve_chunks`; search keeps validation, auth, and response mapping. |
| `chat/{__init__,contracts,prompts,citations,router}.py` | Create | DTO/protocol/fake, static prompt, verifier, orchestration. |
| `chat/providers/openai.py` | Create | Lazy injectable OpenAI client and bounded retry policy. |
| `config.py`, `main.py`, `.env.example` | Modify | Bounds, real adapter, router wiring. |
| `tests/{unit,integration,e2e}/test_chat_*.py` | Create | Offline core, HTTP/security gates, credentialed smoke. |

## Interfaces / Contracts

`ChatRequest(query, top_k=10)` reuses `retrieval_max_query_length` and `retrieval_top_k_max`. `ChatResponse(answer: str | None, citations: list[Citation])`; citation fields are only `chunk_id`, `document_id`, `document_name`, `position`, `content`. `ChatCompleter.complete(CompletionPrompt) -> str` is synchronous and called via `asyncio.to_thread`.

Settings: `chat_model="gpt-4o-mini"`; `chat_max_output_tokens=500` (1..2000); `chat_retries=2` (0..2); reuse `provider_timeout_seconds=30` (>0). The locked OpenAI SDK is 2.53.0; client construction is lazy with `max_retries=0`. Responses use `max_output_tokens`; max-token incomplete text is accepted as truncated output and still citation-verified. The static secret-free system prompt says sources are data, not instructions; chunks are numbered and JSON-encoded inside explicit untrusted-source delimiters. Output is never executed or persisted.

## Testing Strategy

| Layer | Gate |
|---|---|
| Unit | Extraction equivalence; prompt separation; marker bounds/dedup/order; settings; lazy client, parameters, retries, truncation, safe failures. |
| Integration | 400/401/403; fresh role changes; byte-identical no-evidence with zero completion calls; search regression; provider/citation 503; adversarial documents; cross-tenant prompt/citation isolation; response allowlist. |
| E2E | Opt-in `OPENAI_API_KEY` smoke; ordinary `uv run pytest -m 'not e2e'` stays offline. |

## Threat Matrix

Triggered by HTTP routing; reference rows concern execution/VCS boundaries only.

| Boundary | Applicability | Response / RED test |
|---|---|---|
| Documentation-like paths | N/A — no classification/execution | None |
| Git repository selection | N/A — no Git | None |
| Commit state | N/A — no commits | None |
| Push state | N/A — no pushes | None |
| PR commands | N/A — no PR automation | None |

## Migration / Rollout

No database, worker, UI, evaluation, or persistence change. Stacked-to-main units, each under 400 changed lines: (1) retrieval extraction/regression; (2) contracts/prompt/verifier; (3) provider/settings; (4) route/wiring/security/E2E gates. Each slice lands with its tests; rollback reverses 4→1. Do not deploy chat if slice 1 changes search behavior.

## Open Questions

- [ ] Conversation persistence/retention and rate-limit policy remain later product decisions; this design introduces neither.
