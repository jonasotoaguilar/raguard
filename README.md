# raguard

Multi-tenant conversational RAG over internal documents: ask questions in natural language and get answers grounded in your organization's own files, with verifiable citations and permission-aware retrieval.

## Status

> **MVP foundation implemented and archived.** The `mvp-authz-foundation` and `mvp-document-ingestion` changes are complete: identity/authentication/RBAC, authorized PDF/Markdown upload with tenant-scoped list/detail, and the Redis/Arq ingestion pipeline (parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, cleanup). Verification passes: 240 Python non-e2e tests, worker suite 77 tests, corrective retry tests 23, plus Ruff check/format, Biome, the Alembic drift check, and the Compose config. **Retrieval/RRF, chat/citations, precision evaluation, deletion, grants, and the web UI remain planned** — `apps/web` is tooling/scaffold only, and everything about retrieval and generation in *What Is This?* is still target design, not current behavior.

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
| Hybrid retrieval | Embeddings + PostgreSQL FTS/vector search, RRF fusion | Planned |
| Permission-filtered retrieval | Chunks a user cannot access never reach generation | Planned |
| Verifiable citations | Answers cite retrievable chunks with links back to the source | Planned |
| Chat interface | Web app with conversation history for question/answer flow | Planned |
| Precision evaluation | Offline harness to measure retrieval/generation quality before shipping changes | Planned |
| Prompt-injection protection | Document content cannot override system or user instructions | Planned |

## Security & Authorization Invariant

**Non-negotiable:** no retrieved chunk, citation, or answer fragment may be derived from content the requesting user is not authorized to see. Authorization is enforced at retrieval time (permission-filtered chunks), never only by hiding the UI. This invariant holds across all tenants, roles, and future features. Any change that weakens it is a release blocker.

## Repository Layout

```
raguard/
├── apps/
│   ├── api/        # FastAPI service — JWT auth, org-scoped RBAC, documents, Alembic migrations
│   ├── worker/     # Arq ingestion worker — parsing, chunking, embeddings, indexing, cleanup
│   └── web/        # React + Vite frontend — tooling config only, no source
├── docs/adr/       # ADR-0001..0006: architecture decision records
├── infra/          # Docker Compose local stack (incl. worker service) + Caddyfile (proxy profile)
├── PRD.md          # Product intent, scope, invariants, success criteria
├── ARCHITECTURE.md # System design (draft)
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

- **`apps/api`** — FastAPI service with JWT authentication, org-scoped RBAC, and authorized document upload with tenant-scoped list/detail (source under `apps/api/src/raguard_api`); Alembic migrations under `apps/api/alembic`, and `apps/api/raguard-bootstrap` seeds the first tenant.
- **`apps/worker`** — Redis + Arq ingestion worker: parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, and cleanup (source under `apps/worker/src/raguard_worker`); run via the compose `worker` service.
- **`apps/web`** — React + Vite frontend tooling only (Vite, Vitest, Playwright, Testing Library); no application source yet.

### Environment Variables & Secrets

- `.env.example` lists every variable the stack consumes; copy it to `.env` and fill in real values. `.env*` files are gitignored — never commit real credentials.
- `OPENAI_API_KEY` is consumed by the worker's embedding adapter; `ANTHROPIC_API_KEY` backs the planned chat adapter. Both are secrets: keep them in environment files or a secret manager, never in source code or manifests.
- Providers are replaceable behind adapters (ADR-0005); the worker's embedding adapter defaults to OpenAI and nothing is hard-wired to a specific provider.

### Validation & Checks

| Command | What it does | Today |
|---|---|---|
| `pnpm exec biome check .` | Lint/format check for JS/TS/JSON | Passes |
| `pnpm test` | Recursive test run (web: vitest) | Exits 0 — no JS test files present (`--passWithNoTests`) |
| `uv run ruff check .` | Lint check for Python | Passes |
| `uv run ruff format --check .` | Format check for Python | Passes |
| `uv run pytest -m "not e2e"` | Python unit/integration tests (e2e excluded) | 240 tests pass (worker suite 77; corrective retry 23) |
| Alembic drift check | Migration drift (`apps/api/alembic.ini`) | Passes — no new upgrade operations |
| `docker compose -f infra/compose.yaml config` | Validates the compose stack | Passes once `.env` exists |

### Git Hooks (Lefthook)

Lefthook is installed and active (`lefthook.yml`):

- **pre-commit** — Biome on staged JS/TS/JSON, Ruff lint + format on staged Python.
- **pre-push** — `uv run pytest -m "not e2e"` and the web vitest suite; both exit 0 today.

## Documentation

| Document | Purpose | Status |
|---|---|---|
| [PRD.md](./PRD.md) | Product intent, scope, invariants, success criteria | Ready |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System/API design | Draft — target design; MVP foundation implemented, retrieval/chat planned |
| [DESIGN.md](./DESIGN.md) | UI/UX design direction | Draft — target design, pending implementation |
| [docs/adr/](./docs/adr/) | Architecture decision records (0001–0006) | Ready |

## License

MIT — see [LICENSE](./LICENSE). Maintained by Jonathan Soto (jonasotoaguilar).
