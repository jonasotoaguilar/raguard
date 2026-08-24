# raguard

Multi-tenant conversational RAG over internal documents: ask questions in natural language and get answers grounded in your organization's own files, with verifiable citations and permission-aware retrieval.

## Status

> **MVP retrieval and chat delivered on `main` (merge `707245a`, 2026-08-24).** `mvp-authz-foundation`, `mvp-document-ingestion`, `mvp-retrieval-rrf`, and `mvp-chat-citations` are complete and archived under `openspec/changes/archive/` and `openspec/specs/`: tenant identity with JWT/RBAC and `raguard-bootstrap` first-tenant flow, authorized PDF/Markdown upload with tenant-scoped list/detail, Redis/Arq ingestion pipeline (parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, cleanup), permission-filtered hybrid retrieval (`POST /api/search` — FTS `simple` + `halfvec(1536)` cosine via pgvector HNSW, RRF `k=60` fused at the application layer, tenant predicate before ranking), and bounded request-scoped chat (`POST /api/chat` — static grounded prompt with untrusted-source delimiters, OpenAI-only completer with bounded timeout/retries/tokens, neutral `{answer: null, citations: []}` on empty/no-match, `[n]` citation verification against the exact authorized retrieved set, 503 envelope on provider or citation failure, zero provider calls on neutral paths). Verification passes: `uv run pytest -m "not e2e"` and related checks (Ruff check/format, Biome, Alembic drift, Compose config) — see [Validation & Checks](#validation--checks). **Precision evaluation harness, document deletion, per-document grants, and the web UI remain planned** — `apps/web` is still tooling/scaffold only; do not treat the next slice `mvp-evaluation-harness` as delivered.

## What Is This?

Teams drown in internal documents: policies, runbooks, meeting notes, knowledge bases. Searching them is slow, answers live in someone's head, and LLM chat tools hallucinate or leak context.

raguard is a self-hosted, multi-tenant answer engine over internal documents. Organizations upload PDFs and Markdown files; the system indexes them and answers questions with:

- **Hybrid retrieval** — semantic (embeddings) combined with keyword (PostgreSQL full-text search), merged with Reciprocal Rank Fusion (RRF) for better recall than either alone.
- **Permission-filtered chunks** — retrieval is scoped to what the asking user is allowed to see, per document, per role.
- **Verifiable citations** — every claim in an answer points to a specific retrievable chunk the user can open and check.
- **Injection-aware generation** — document content is treated as untrusted data, not instructions.

It is designed to run with standard, replaceable components (PostgreSQL, Redis, S3-compatible storage, Docker Compose) — no proprietary RAG platform lock-in.

## MVP Scope

| Capability | What it means | Status |
|---|---|---|
| Organizations, users, roles | Tenants with org-scoped membership and role-based access | Implemented |
| Document upload | Authorized PDF and Markdown ingestion per organization | Implemented |
| Ingestion pipeline | Redis/Arq dispatch, parsing, chunking, embeddings, atomic indexing, retries, cleanup | Implemented |
| Hybrid retrieval | Embeddings + PostgreSQL FTS/vector search, RRF fusion (`k=60`, candidates 50, deterministic tie-break) | Implemented — `POST /api/search`, `apps/api/src/raguard_api/retrieval/` |
| Permission-filtered retrieval | Chunks a user cannot access never reach generation (tenant predicate before ranking, `AuthorizationScope`) | Implemented — shared `retrieve_chunks` for search and chat |
| Verifiable citations | Answers cite retrievable chunks with links back to the source (`[n]` → verified `Citation`) | Implemented — `POST /api/chat`, `apps/api/src/raguard_api/chat/citations.py` |
| Chat interface | API chat with grounded answers; web conversation history still planned | Implemented (API) / Planned (web) — `POST /api/chat` live, `apps/web` scaffold only |
| Precision evaluation | Offline harness to measure retrieval/generation quality before shipping changes | Planned — next slice `mvp-evaluation-harness` |
| Prompt-injection protection | Document content cannot override system or user instructions (sources as delimited untrusted data) | Implemented — static `SYSTEM_PROMPT`, `UNTRUSTED_SOURCES_START/END`, adversarial gates |

## Security & Authorization Invariant

**Non-negotiable:** no retrieved chunk, citation, or answer fragment may be derived from content the requesting user is not authorized to see. Authorization is enforced at retrieval time (permission-filtered chunks), never only by hiding the UI. This invariant holds across all tenants, roles, and future features. Any change that weakens it is a release blocker.

## Repository Layout

```
raguard/
├── apps/
│   ├── api/        # FastAPI — JWT auth, org-scoped RBAC, documents, retrieval (FTS+vector+RRF), chat+citations, Alembic
│   ├── worker/     # Arq ingestion worker — parsing, chunking, embeddings, indexing, cleanup
│   └── web/        # React + Vite frontend — tooling config only, no application source yet
├── docs/
│   ├── adr/                 # ADR-0001..0006: architecture decision records
│   ├── CODEBASE-GUIDE.md    # Navigational index — start-here paths, ownership, flows, tests
│   └── codebase/
│       └── mental-model.md  # Detailed mental model for the monorepo (keeps the guide concise)
├── infra/          # Docker Compose local stack (worker service + Caddy proxy profile) + Caddyfile
├── openspec/
│   ├── specs/      # Canonical specs: tenant-identity, jwt-authentication, authorization-rbac, documents, retrieval, chat
│   └── changes/archive/  # SDD archive: mvp-authz-foundation, mvp-document-ingestion, mvp-retrieval-rrf, mvp-chat-citations
├── PRD.md          # Product intent, scope, invariants, success criteria
├── ARCHITECTURE.md # System design (current status reflects mvp-chat-citations)
└── DESIGN.md       # UI design direction (draft)
```

## Local Development

### Prerequisites

| Tool | Why |
|---|---|
| Docker + Docker Compose | PostgreSQL, Redis, MinIO (and later Caddy) run as containers |
| Node.js ≥ 22.12 + `pnpm` 11 | Web app and frontend tooling (`engines`/`packageManager` fields) |
| Python 3.13 + `uv` | API and worker services (`.python-version`, `requires-python`) |
| An LLM provider API key | Worker embeddings (OpenAI) and, later, chat generation (OpenAI or Anthropic, adapter-based) |

Versions are pinned by the lockfiles and manifests (`pnpm-lock.yaml`, `uv.lock`, `.python-version`), which are authoritative over this document.

### Setup

```bash
git clone git@github.com:jonasotoaguilar/raguard.git
cd raguard

# JS/TS tooling (workspace apps/*)
pnpm install --frozen-lockfile

# Python 3.13 tooling (apps/api, apps/worker) — uv manages the interpreter
uv sync

# Environment for local infrastructure — copy and fill in real values
cp .env.example .env
```

### Local Infrastructure (Docker Compose)

PostgreSQL + pgvector, Redis, and MinIO run from `infra/compose.yaml`, plus a `worker` service built from `apps/worker/Dockerfile` that runs the Arq ingestion worker once Postgres/Redis/MinIO are healthy and the bucket exists. The file reads credentials from `.env` and fails fast with a clear message when a required variable is missing.

```bash
# Validate the rendered compose configuration (requires .env to exist)
docker compose -f infra/compose.yaml config

# Start PostgreSQL, Redis, MinIO, and the ingestion worker in the background
docker compose -f infra/compose.yaml up -d
```

The Caddy reverse proxy is gated behind the `proxy` profile (`docker compose --profile proxy up`); it routes to `apps/api` and `apps/web`, neither of which runs in the default stack (the API is not yet a compose service and the web app has no source), so it becomes useful only once those services are implemented.

> **MinIO caveat:** the MinIO image in the compose stack is pinned for **local development only**. The upstream MinIO project is no longer maintained and points to AIStor; revalidate the image before any production use. Production object-storage targets are S3 or Cloudflare R2 (ADR-0006).

### Application Services

- **`apps/api`** — FastAPI service (`apps/api/src/raguard_api`, `apps/api/alembic`, `apps/api/raguard-bootstrap`): JWT authentication (`auth/jwt.py`, `auth/router.py` — `POST /api/auth/login`), org-scoped RBAC via the single fresh `AuthorizationResolver`/`AuthorizationScope` (`authorization/`), authorized document upload with tenant-scoped list/detail and tenant-prefixed object keys (`documents/`), hybrid retrieval (`retrieval/` — `POST /api/search`, shared `retrieve_chunks`, `fusion.py` RRF `k=60`, `queries.py` FTS `simple` + `halfvec(1536)` cosine with `hnsw.ef_search`, bounded `top_k`/query validation), and bounded chat (`chat/` — `POST /api/chat`, static `SYSTEM_PROMPT` + `UNTRUSTED_SOURCES_START/END` delimiters, `providers/openai.py` OpenAI-only completer with bounded timeout/retries/`CHAT_MAX_OUTPUT_TOKENS`, neutral `{answer: null, citations: []}` on empty/no-match, `citations.py` `[n]` verification, safe 503 envelope). Alembic migrations under `apps/api/alembic`; `apps/api/raguard-bootstrap` seeds the first tenant.
- **`apps/worker`** — Redis + Arq ingestion worker: parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, and cleanup (source under `apps/worker/src/raguard_worker` — `parsers.py`, `chunking.py`, `embeddings.py`, `jobs.py`, `cleanup.py`); run via the compose `worker` service.
- **`apps/web`** — React + Vite frontend tooling only (Vite, Vitest, Playwright, Testing Library); no application source yet.

### Environment Variables & Secrets

- `.env.example` lists every variable the stack consumes; copy it to `.env` and fill in real values. `.env*` files are gitignored — never commit real credentials.
- `OPENAI_API_KEY` is consumed by the worker's embedding adapter and by the API's retrieval embedder + chat completer (`OPENAI_API_KEY`, `EMBEDDING_MODEL`, `CHAT_MODEL`, `PROVIDER_TIMEOUT_SECONDS`, `CHAT_RETRIES`, `RETRIEVAL_SEMANTIC_MAX_DISTANCE` etc. in `.env.example`); `ANTHROPIC_API_KEY` is reserved for a future adapter and is not used by current chat (OpenAI-only, ADR-0005). Both are secrets: keep them in environment files or a secret manager, never in source code or manifests.
- Providers are replaceable behind adapters (ADR-0005); the worker's embedding adapter and the API's `OpenAIEmbedder`/`OpenAICompleter` default to the OpenAI models pinned in `.env.example` (`text-embedding-3-small`, `gpt-4o-mini`) and nothing is hard-wired beyond the injectable `FakeEmbedder`/`FakeCompleter` used in tests.

### Validation & Checks

| Command | What it does | Result (verified 2026-08-24 on `main` `707245a`) |
|---|---|---|
| `pnpm exec biome check .` | Lint/format check for JS/TS/JSON | Passes |
| `pnpm test` | Recursive test run (web: vitest) | Passes (`--passWithNoTests` when no JS test files) |
| `uv run ruff check .` | Lint check for Python | Passes |
| `uv run ruff format --check .` | Format check for Python | Passes |
| `uv run pytest -m "not e2e"` | Python unit/integration tests (e2e excluded) — authorization, retrieval, chat, citation, isolation and release gates (credential-gated provider tests are `e2e`, skipped by default) | Passes |
| Alembic drift check | Migration drift (`apps/api/alembic.ini`) | Passes — no new upgrade operations |
| `docker compose -f infra/compose.yaml config` | Validates the compose stack | Passes once `.env` exists |

> Counts are intentionally not pinned — run the commands above for the current totals. At `707245a` the non-e2e suite reported 249 passed, 127 skipped.

### Git Hooks (Lefthook)

Lefthook is installed and active (`lefthook.yml`):

- **pre-commit** — Biome on staged JS/TS/JSON, Ruff lint + format on staged Python.
- **pre-push** — `uv run pytest -m "not e2e"` and the web vitest suite; both exit 0 today.

## Documentation

| Document | Purpose | Status |
|---|---|---|
| [PRD.md](./PRD.md) | Product intent, scope, invariants, success criteria | Ready — acceptance reconciled at `707245a` (evaluation harness still planned) |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System/API design | Ready — reflects `mvp-chat-citations`; target architecture preserved, open decisions retained |
| [DESIGN.md](./DESIGN.md) | UI/UX design direction | Draft — target design, pending implementation |
| [docs/CODEBASE-GUIDE.md](./docs/CODEBASE-GUIDE.md) | Navigational index — start-here, ownership, flows, tests | Ready |
| [docs/codebase/mental-model.md](./docs/codebase/mental-model.md) | Detailed mental model for the monorepo | Ready |
| [docs/adr/](./docs/adr/) | Architecture decision records (0001–0006) | Ready |
| [openspec/specs/](./openspec/specs/) | Canonical specs — `tenant-identity`, `jwt-authentication`, `authorization-rbac`, `documents`, `retrieval`, `chat` | Ready |
| [openspec/changes/archive/](./openspec/changes/archive/) | SDD archive — `mvp-authz-foundation`, `mvp-document-ingestion`, `mvp-retrieval-rrf`, `mvp-chat-citations` | Ready |

## License

MIT — see [LICENSE](./LICENSE). Maintained by Jonathan Soto (jonasotoaguilar).
