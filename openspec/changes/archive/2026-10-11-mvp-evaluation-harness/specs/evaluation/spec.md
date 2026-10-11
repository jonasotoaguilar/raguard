# Evaluation Specification

## Purpose

Offline labeled-dataset runner for ranking, citations, isolation, and prompt-boundary evidence. MUST NOT claim live embedding or model semantic quality.

## Requirements

### Requirement: Versioned dataset contract

MUST declare schema version, unique IDs, actor/tenant, query, top-k, relevant chunk IDs, corpus fixtures, and kinds `relevant`, `neutral`, `cross-tenant`, `capability-denied`, `adversarial`. Datasets/reports MUST use synthetic IDs and allowlisted fields only — no credentials. Invalid schema or duplicate IDs MUST fail before evaluation (exit 3).

#### Scenario: Valid dataset

- GIVEN unique IDs and required kinds
- WHEN validated
- THEN evaluation may start

#### Scenario: Invalid dataset

- GIVEN unknown schema or duplicate IDs
- WHEN started
- THEN dataset error, no verdict, exit 3

### Requirement: Deterministic offline execution

MUST use current injected fakes plus `retrieve_chunks`, `build_completion_prompt`, and `verify_citations`. MUST NOT require a live-provider call, secret, or flag. Same dataset/config/code MUST yield the same ranked IDs and metrics.

#### Scenario: Offline run

- GIVEN injected fakes and no provider credentials
- WHEN run
- THEN zero provider calls

#### Scenario: Repeat run

- GIVEN same dataset/config/code
- WHEN run twice
- THEN ranked IDs and verdict match

### Requirement: Metric semantics

On `relevant` only: precision@k = |Rk ∩ Rel| / |Rk| (empty Rk MUST be 0.0, never 1.0); recall@k = |Rk ∩ Rel| / |Rel|; hit-rate@k = 1 iff intersection; empty Rel excludes the case. Neutral fidelity = 1 if Rk empty. If total `[n]` > 0, citation validity = valid `[n]` / total `[n]`. If total is 0, it MUST be null, excluded from the aggregate, and MUST NOT inflate citation quality; honest empty citations MUST be recorded separately. Tenant leakage > 0 hard-fails. Capability-denial = 1 if a denied actor ran retrieval or chat; MUST NOT invent cross-role document isolation. Structural containment = 1 only if the system prompt is unchanged and adversarial source content stays inside untrusted-source delimiters. MUST NOT be read as live-model immunity.

#### Scenario: Neutral not precision

- GIVEN `neutral` case with empty Rk
- WHEN scored
- THEN precision/recall exclude it and neutral fidelity is 1.0

#### Scenario: Missed relevant

- GIVEN `relevant` case with Rel and empty Rk
- WHEN scored
- THEN precision@k and recall@k are 0.0

#### Scenario: Capability denial

- GIVEN actor lacking `chat.use`
- WHEN scored
- THEN unauthorized execution is recorded if retrieval or chat ran

#### Scenario: Structural containment

- GIVEN adversarial chunk text in retrieved sources
- WHEN scored
- THEN the system prompt is unchanged and that text stays inside untrusted-source delimiters

### Requirement: Hard invariants and quality gate

MUST hard-fail (exit 2) on tenant leak, unauthorized capability-denied execution, citation outside the authorized retrieved set, malformed citation acceptance, or prompt-boundary violation. Dataset/config MUST record draft precision@10 0.70. CLI MUST support a precision hard-gate. Product KPI MUST stay provisional.

#### Scenario: Invariant hard-fail

- GIVEN cross-tenant chunk, out-of-set citation, or malformed marker treated as valid
- WHEN gated
- THEN fail with that reason and exit 2

#### Scenario: Precision gate

- GIVEN draft precision@10 0.70
- WHEN the precision hard-gate is on and aggregate is below 0.70
- THEN exit 2; without the gate, sub-0.70 is not a KPI pass

### Requirement: CLI, report, and CI contract

MUST expose an offline stdlib-argparse CLI and write deterministic JSON with schema version, proof scope, dataset identity/hash, settings/thresholds, aggregate and per-case metrics, failure reasons, and verdict. Exits: 0 pass, 2 threshold/invariant, 3 dataset/schema, 1 internal/tool. Ordinary CI MUST run offline and hard-fail invariant/tool/dataset errors; MAY warn on provisional precision. MUST NOT add model-as-judge, dashboard, web/API route, migration, third-party eval, or live-provider flag.

#### Scenario: Pass report

- GIVEN valid dataset
- WHEN CLI finishes
- THEN JSON report and stdout summary exist; exit 0

#### Scenario: Distinct exits

- GIVEN schema error, invariant breach, and tool fault
- WHEN each finishes
- THEN exits are 3, 2, and 1; non-atomic write MUST exit 1
