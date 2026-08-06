# ADR-0005: Provider-Neutral Chat and Embedding Adapters

## Status

Accepted (user-approved; target design for a greenfield repository — no implementation exists yet)

## Date

2026-08-04

## Deciders

Jonathan Soto (jonasotoaguilar)

## Context

Generation and embedding call external LLM providers. The PRD requires provider neutrality ("Provider-neutral adapter; embedding provider replaceable (default OpenAI embeddings)") and explicitly notes that **Anthropic does not provide embeddings** — so embeddings and chat are separate concerns with different provider landscapes. Additional forces: provider credentials are secrets that must never reach source or manifests; provider outages/rate limits must not silently degrade grounding; embedding model consistency is a correctness requirement (queries and data must use the same embedding model, ADR-0003); document content is untrusted data that must stay out of system/user instruction paths.

## Decision

Introduce two small, internal adapter interfaces in the API/worker shared code:

1. **Chat adapter**: provider-neutral interface over chat/LLM completion, with implementations for OpenAI and Anthropic (config-selected). The adapter is the only place provider SDKs are used.
2. **Embedding adapter**: provider-neutral interface over text-embedding generation, with an OpenAI implementation as the default; the interface carries the model identifier so data-time and query-time embedding models are guaranteed consistent (same model for indexing and retrieval).

Adapter contracts are minimal (request/response DTOs); provider selection and credentials come from environment/secret manager, never from code. The adapters are also the enforcement boundary for prompt hardening: system/user instructions are assembled in the API, retrieved chunks are injected as data with clear delimiters, and the LLM-security posture from the PRD (document content is untrusted) is applied where the prompt is built — not inside adapters.

## Consequences

### Positive

- No vendor lock-in: swapping chat or embedding providers is a config change plus a new adapter implementation.
- Embedding replaceability is real (PRD requirement) without making Anthropic an embeddings vendor by implication.
- Secrets stay out of code; the adapter boundary contains all provider-specific client setup.
- Model consistency is enforceable by contract (one embedding model id per environment).

### Negative

- Adapter code is ours to maintain (small, but real).
- Provider-specific features (streaming, tool use, per-provider parameter quirks) must fit the minimal interface or be negotiated per adapter.
- Two adapters means two integration test surfaces.

### Neutral

- Prompt-engineering surface is now a defined module boundary (prompt assembly), which is also where injection defense is implemented and tested.

## Options Considered

### Option A: Direct provider SDK calls throughout the API/worker
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low initially |
| Cost | Low |
| Scalability | Same |
| Team familiarity | High |
| Operational overhead | Low |

**Pros:** fastest to write.
**Cons:** provider SDKs leak into business logic; swapping providers means touching retrieval, chat, and ingestion code paths; model-consistency guarantee is informal.

### Option B: Provider-neutral adapters for chat and embeddings (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low–Medium |
| Cost | Low |
| Scalability | Same |
| Team familiarity | High |
| Operational overhead | Low |

**Pros:** single seam for providers; testable with fakes (important for evaluation harness and offline tests); satisfies PRD neutrality requirement.
**Cons:** small interface-maintenance cost; some provider-specific features need per-adapter negotiation.

### Option C: One generic "AI service" abstraction over both chat and embeddings
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cost | Low |
| Scalability | Same |
| Team familiarity | Medium |
| Operational overhead | Low |

**Pros:** one interface.
**Cons:** conflates two different concerns (generation vs vectorization) with different provider landscapes — exactly the confusion the PRD warns about ("whether Anthropic is offered as an alternative is a product decision, not an embeddings claim").

## Trade-off Analysis

Direct SDK calls are the cheapest path but make provider replaceability — an explicit PRD requirement — a refactor of business logic. A single generic AI service re-introduces the Anthropic-embeddings confusion the PRD explicitly guards against. Two narrow adapters keep each concern independently replaceable, make model consistency contractual, and give the evaluation and security test suites a clean seam for fakes. The cost is small, owned code that must be kept minimal.

## Action Items

1. [ ] Define the two adapter interfaces with minimal DTOs (chat completion; embed text + model id) in shared code.
2. [ ] Implement OpenAI chat + OpenAI embeddings; add Anthropic chat as the second implementation.
3. [ ] Require prompt assembly (system/user vs retrieved data) to happen outside adapters, with injection-hardening tests.
4. [ ] Enforce a single embedding model id per environment (config validation) to protect index/query consistency.

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Component Details (Provider Adapters), Key Decisions
- [PRD.md](../PRD.md) — Open Product Decisions (embedding provider policy), Risks (provider dependency)
- Related ADRs: [ADR-0003](0003-postgres-fusion-hybrid-retrieval.md) (embedding-model consistency), [ADR-0002](0002-retrieval-level-authorization.md) (untrusted content handling)
