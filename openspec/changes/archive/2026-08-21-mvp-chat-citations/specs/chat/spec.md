# Chat Specification

## Purpose

`POST /api/chat`: request-scoped, `chat.use`-gated, grounded answers with verifiable citations, reusing the shared retrieval path and the single authz-resolution function. No persistence, migrations, worker, UI, or eval. New domain — full spec, first change.

## Requirements

### Requirement: Bounded chat request

`POST /api/chat` MUST accept JSON `{query, top_k}`. Empty, whitespace-only, or oversized `query` and out-of-bounds `top_k` MUST be rejected (400 envelope) with no retrieval or provider runs. `top_k` MUST default to 10, cap at a configured maximum (search bound), and MUST NOT affect authorization.

#### Scenario: Valid request returns an answer

- GIVEN an authorized caller with a valid query
- WHEN the request is submitted
- THEN 200 returns `answer` and `citations` referencing at most `top_k` chunks

#### Scenario: Invalid query or top-k rejected

- GIVEN an empty/oversized query or over-max `top_k`
- WHEN the request is submitted
- THEN it fails (400) with no retrieval and zero provider calls

### Requirement: Fresh authorization and chat.use gate

Authorization MUST resolve fresh per request via the single resolution function (never cached). Tenant MUST derive only from the verified token. `chat.use` MUST be required: missing capability yields 403, invalid/missing token 401.

#### Scenario: Member with chat.use proceeds

- GIVEN an authenticated member holding `chat.use`
- WHEN a chat request is submitted
- THEN the request is authorized and processed

#### Scenario: Missing capability denied

- GIVEN a caller without `chat.use`
- WHEN a chat request is submitted
- THEN it fails (403) with no retrieval, generation, or disclosure

### Requirement: Retrieval-level tenant authorization before generation

Generation MUST receive only chunks from the shared tenant-filtered retrieval used by `/api/search` — tenant predicate before ranking (Retrieval Specification). Cross-tenant chunks MUST NOT reach the prompt or citations; existence MUST NOT be disclosed.

#### Scenario: Authorized answer cites only authorized chunks

- GIVEN chunks in tenants A and B
- WHEN a tenant A member asks a question matching both
- THEN every cited chunk belongs to tenant A

#### Scenario: Cross-tenant isolation (release gate)

- GIVEN a tenant A member querying terms matching only tenant B chunks
- WHEN the chat request completes
- THEN the neutral response returns with zero provider calls and no disclosure

### Requirement: Grounded prompt treats documents as untrusted data

The system prompt MUST be static and free of secrets, tenant identifiers, and provider credentials. Chunk content MUST be injected as delimited untrusted data; instructions inside documents MUST be treated as text, never merged into instructions. Prompt assembly MUST live outside the completion adapter.

#### Scenario: Adversarial document cannot inject instructions

- GIVEN a retrieved chunk containing "ignore prior instructions" or extraction text
- WHEN the chat request completes
- THEN the answer stays grounded in retrieved content, never following or revealing the injection

### Requirement: Bounded OpenAI completion contract

A narrow `ChatCompleter` MUST be OpenAI-only for MVP with injectable fakes. It MUST enforce a bounded timeout, bounded retries, and bounded `max_output_tokens`. Failure after bounded retries MUST return 503 via the envelope; the system MUST NOT fall back to ungrounded generation.

#### Scenario: Provider failure is a safe 503

- GIVEN the completion provider fails after bounded retries
- WHEN the chat request completes
- THEN it fails (503) with no partial answer, no fallback, no provider detail leakage

#### Scenario: Output is bounded

- GIVEN a provider emitting output beyond `max_output_tokens`
- WHEN the completion is processed
- THEN the response is truncated to the bound and still verified

### Requirement: Neutral no-evidence short-circuit

Empty corpus and populated no-match MUST both return the identical neutral 200 `{answer: null, citations: []}` with zero provider calls; the system MUST NOT call the model with empty context or fabricate an answer.

#### Scenario: Empty corpus yields neutral response

- GIVEN an empty corpus
- WHEN a chat request is submitted
- THEN 200 `{answer: null, citations: []}` returns and zero provider calls occur

#### Scenario: Populated no-match yields identical neutral response

- GIVEN a populated corpus with no matching authorized chunks
- WHEN a chat request is submitted
- THEN the response is byte-identical to the empty-corpus neutral response with zero provider calls

### Requirement: Numbered citations with membership verification

The model MUST cite retrieved chunks via bounded `[n]` markers. The verifier MUST resolve every marker to a chunk id and verify membership against the exact authorized retrieved set the prompt was built from. Any out-of-set citation MUST reject the whole response via the envelope — never partial, never rendered. Missing markers MUST yield honest empty `citations`. Mapping MUST be deterministic: identical retrieved set plus identical completion yields identical citations.

#### Scenario: Citations resolve to retrieved chunks

- GIVEN a completion citing `[1]` and `[2]` over retrieved chunks A and B
- WHEN verification runs
- THEN `citations` return chunk A and B metadata in stable order

#### Scenario: Out-of-set citation rejects the response

- GIVEN a completion citing a chunk id absent from the retrieved set
- WHEN verification runs
- THEN the entire response is rejected via the envelope with no partial content

#### Scenario: Missing markers yield honest empty citations

- GIVEN a grounded completion with no `[n]` markers
- WHEN verification runs
- THEN 200 returns the answer with `citations: []`

### Requirement: Safe response fields

The response MUST contain `answer` and `citations` entries limited to chunk id, document id, document name, position, and content. It MUST NOT include tenant identifiers, provider credentials or model internals, or content outside the authorized retrieved set. Errors MUST NOT leak tenant existence or internal details.

#### Scenario: No tenant or provider leakage

- GIVEN an authorized answer for tenant A
- WHEN the response is serialized
- THEN no tenant id, provider key, or internal detail appears in answer, citations, or error payloads

## Out of Scope

Persistence, history, follow-ups, retention/deletion, migrations, Anthropic, streaming/SSE, rate-limit policy, per-document grants, RLS, eval, UI — later slices. Search and authorization behavior is preserved unchanged; cross-referenced only.
