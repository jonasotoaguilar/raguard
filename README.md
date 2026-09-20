# raguard

Multi-tenant conversational RAG over internal documents: ask questions in natural language and get answers grounded in your organization's own files, with verifiable citations and permission-aware retrieval.

## Status

> **MVP retrieval and chat delivered on `main` (merge `707245a`, 2026-08-24).** `mvp-authz-foundation`, `mvp-document-ingestion`, `mvp-retrieval-rrf`, and `mvp-chat-citations` are complete and archived under `openspec/changes/archive/` and `openspec/specs/`: tenant identity with JWT/RBAC and `raguard-bootstrap` first-tenant flow, authorized PDF/Markdown upload with tenant-scoped list/detail, Redis/Arq ingestion pipeline (parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, cleanup), permission-filtered hybrid retrieval (`POST /api/search` — FTS `simple` + `halfvec(1024)` cosine via pgvector HNSW, RRF `k=60` fused at the application layer, tenant predicate before ranking), and bounded request-scoped chat (`POST /api/chat` — static grounded prompt with untrusted-source delimiters, selectable OpenAI/Ollama completer with bounded timeout/retries/tokens, neutral `{answer: null, citations: []}` on empty/no-match, `[n]` citation verification against the exact authorized retrieved set, 503 envelope on provider or citation failure, zero provider calls on neutral paths). Verification passes: `uv run pytest -m "not e2e"` and related checks (Ruff check/format, Biome, Alembic drift, Compose config) — see [Validation & Checks](#validation--checks). **Precision evaluation harness, document deletion, per-document grants, and the web UI remain planned** — `apps/web` is still tooling/scaffold only; do not treat the next slice `mvp-evaluation-harness` as delivered.

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
| An OpenAI API key — only for the OpenAI provider path | Model calls when `EMBEDDING_PROVIDER`/`CHAT_PROVIDER` select `openai`; the opt-in `local-ai` Ollama profile needs no key |

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

### Local AI (Ollama) — opt-in `local-ai` profile

The default stack uses OpenAI and starts no local model runtime. For a fully local, zero-provider-cost path, the compose file adds an opt-in Ollama service (`ollama/ollama:0.34.1`, never `latest`) gated behind the `local-ai` profile: models persist in the `ollama` named volume, the API port is loopback-only (`127.0.0.1:11434`), and there are no GPU/device/privileged assumptions (CPU inference works out of the box).

```bash
# Base stack first, then add Ollama (profile-gated: a plain `up` is unaffected)
docker compose -f infra/compose.yaml up -d
docker compose -f infra/compose.yaml --profile local-ai up -d ollama

# Pull models once (multi-hundred-MB downloads; persisted in the `ollama` volume)
docker compose -f infra/compose.yaml exec ollama ollama pull qwen3-embedding:0.6b
docker compose -f infra/compose.yaml exec ollama ollama pull qwen3:1.7b

# Smoke: daemon is up and both models are present
docker compose -f infra/compose.yaml exec ollama ollama list
```

Select the local path with `EMBEDDING_PROVIDER=ollama` and/or `CHAT_PROVIDER=ollama` in `.env` (all selectors are documented in `.env.example`), then recreate the worker so it picks up the new environment (`docker compose -f infra/compose.yaml up -d worker`; restart a host-side API likewise). The compose `worker` reaches Ollama as `http://ollama:11434`, while host-side processes (the API runs via `uv`, not compose) use the code default `http://127.0.0.1:11434` through the published loopback port. `OPENAI_API_KEY` is only needed when a provider selects OpenAI and stays empty on the fully local path. Switching embedding models requires a full reindex — never mix vectors from different models.

> **Migration note:** embeddings are standardized at 1024 dimensions (migration `0003_embedding_1024`, fail-closed). A database that already holds 1536-dim vectors refuses to migrate until its `chunks` table is empty — reindex/re-upload from source (object-store files are preserved; take a database backup first), then retry.

> **Safe teardown:** `docker compose -f infra/compose.yaml down` stops containers but keeps volumes. Never run `down -v` (or `volume rm`/`prune`) unless you intend to delete PostgreSQL data, MinIO objects, Redis state, and downloaded Ollama models.

### Application Services

- **`apps/api`** — FastAPI service (`apps/api/src/raguard_api`, `apps/api/alembic`, `apps/api/raguard-bootstrap`): JWT authentication (`auth/jwt.py`, `auth/router.py` — `POST /api/auth/login`), org-scoped RBAC via the single fresh `AuthorizationResolver`/`AuthorizationScope` (`authorization/`), authorized document upload with tenant-scoped list/detail and tenant-prefixed object keys (`documents/`), hybrid retrieval (`retrieval/` — `POST /api/search`, shared `retrieve_chunks`, `fusion.py` RRF `k=60`, `queries.py` FTS `simple` + `halfvec(1024)` cosine with `hnsw.ef_search`, bounded `top_k`/query validation), and bounded chat (`chat/` — `POST /api/chat`, static `SYSTEM_PROMPT` + `UNTRUSTED_SOURCES_START/END` delimiters, `providers/` selectable OpenAI/Ollama completer with bounded timeout/retries/`CHAT_MAX_OUTPUT_TOKENS`, neutral `{answer: null, citations: []}` on empty/no-match, `citations.py` `[n]` verification, safe 503 envelope). Alembic migrations under `apps/api/alembic`; `apps/api/raguard-bootstrap` seeds the first tenant.
- **`apps/worker`** — Redis + Arq ingestion worker: parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, and cleanup (source under `apps/worker/src/raguard_worker` — `parsers.py`, `chunking.py`, `embeddings.py`, `jobs.py`, `cleanup.py`); run via the compose `worker` service.
- **`apps/web`** — React + Vite frontend tooling only (Vite, Vitest, Playwright, Testing Library); no application source yet.

### Environment Variables & Secrets

- `.env.example` lists every variable the stack consumes; copy it to `.env` and fill in real values. `.env*` files are gitignored — never commit real credentials.
- `OPENAI_API_KEY` is consumed only when `EMBEDDING_PROVIDER`/`CHAT_PROVIDER` select `openai` (worker embedding adapter, API retrieval embedder + chat completer; `EMBEDDING_MODEL`, `CHAT_MODEL`, `PROVIDER_TIMEOUT_SECONDS`, `CHAT_RETRIES`, `RETRIEVAL_SEMANTIC_MAX_DISTANCE` etc. in `.env.example`); it stays empty on the fully local (ollama/ollama) path. `ANTHROPIC_API_KEY` is reserved for a future adapter. Secrets live in environment files or a secret manager, never in source code or manifests.
- Providers are selectable behind adapters (ADR-0005): `EMBEDDING_PROVIDER`/`CHAT_PROVIDER` choose `openai` (default; `text-embedding-3-small`, `gpt-4o-mini`) or `ollama` (`qwen3-embedding:0.6b`, `qwen3:1.7b` via `OLLAMA_BASE_URL`); embeddings are standardized at 1024 dimensions for both, and nothing is hard-wired beyond the injectable `FakeEmbedder`/`FakeCompleter` used in tests.

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
