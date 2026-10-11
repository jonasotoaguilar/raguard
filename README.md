# raguard

Multi-tenant conversational RAG over internal documents: ask questions in natural language and get answers grounded in your organization's own files, with verifiable citations and permission-aware retrieval.

## Status

> **MVP retrieval, chat, offline precision evaluation, and web UI delivered on `main`.** `mvp-authz-foundation`, `mvp-document-ingestion`, `mvp-retrieval-rrf`, `mvp-chat-citations`, and `mvp-evaluation-harness` are complete: the change is archived under `openspec/changes/archive/2026-10-11-mvp-evaluation-harness/` and the spec is promoted to `openspec/specs/evaluation/spec.md` (PRs #32/#38/#39/#41/#42/#43/#45/#46 MERGED; work-unit `dcca1ae`). Delivered on `main`: tenant identity with JWT/RBAC and `raguard-bootstrap` first-tenant flow, authorized PDF/Markdown upload with tenant-scoped list/detail, Redis/Arq ingestion pipeline (parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, cleanup), permission-filtered hybrid retrieval (`POST /api/search` — FTS `simple` + `halfvec(1024)` cosine via pgvector HNSW, RRF `k=60` fused at the application layer, tenant predicate before ranking), bounded request-scoped chat (`POST /api/chat` — static grounded prompt with untrusted-source delimiters, selectable OpenAI/Ollama completer with bounded timeout/retries/tokens, neutral `{answer: null, citations: []}` on empty/no-match, `[n]` citation verification against the exact authorized retrieved set, 503 envelope on provider or citation failure, zero provider calls on neutral paths), offline precision evaluation harness (`uv run raguard-eval` over `eval/datasets/mvp-v1`, CI-gated), and the web UI (`apps/web` — chat with citations and source preview, documents library/detail/upload, admin organization views; PRs #47–#61 and #64 MERGED). Document deletion is delivered (`DELETE /api/documents/{id}` + web Delete with confirm) along with per-document grants (`documents.visibility` tenant/restricted + `document_grants` to users/roles, migration `0005`, enforced in retrieval SQL before ranking and on every document surface).

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
| Chat interface | API chat with grounded answers plus web conversation UI | Implemented (API + web) — `POST /api/chat` live (stateless by default, optional `conversation_id` persistence), `POST/GET/DELETE /api/conversations` history, `apps/web` chat/documents/admin routes delivered |
| Precision evaluation | Offline harness to measure retrieval/generation quality before shipping changes | Implemented — archived `2026-10-11-mvp-evaluation-harness`, spec `openspec/specs/evaluation/spec.md` |
| Prompt-injection protection | Document content cannot override system or user instructions (sources as delimited untrusted data) | Implemented — static `SYSTEM_PROMPT`, `UNTRUSTED_SOURCES_START/END`, adversarial gates |

## Security & Authorization Invariant

**Non-negotiable:** no retrieved chunk, citation, or answer fragment may be derived from content the requesting user is not authorized to see. Authorization is enforced at retrieval time (permission-filtered chunks), never only by hiding the UI. This invariant holds across all tenants, roles, and future features. Any change that weakens it is a release blocker.

## Repository Layout

```
raguard/
├── apps/
│   ├── api/        # FastAPI — JWT auth, org-scoped RBAC, documents, retrieval (FTS+vector+RRF), chat+citations, Alembic
│   ├── worker/     # Arq ingestion worker — parsing, chunking, embeddings, indexing, cleanup
│   └── web/        # React + Vite frontend — chat, documents, admin routes with Vitest/Playwright coverage
├── docs/
│   ├── adr/                 # ADR-0001..0006: architecture decision records
│   ├── CODEBASE-GUIDE.md    # Navigational index — start-here paths, ownership, flows, tests
│   └── codebase/
│       └── mental-model.md  # Detailed mental model for the monorepo (keeps the guide concise)
├── infra/          # Docker Compose local stack (worker service + Caddy proxy profile) + Caddyfile
├── openspec/
│   ├── specs/      # Canonical specs: tenant-identity, jwt-authentication, authorization-rbac, documents, retrieval, chat, evaluation
│   └── changes/archive/  # SDD archive: mvp-authz-foundation, mvp-document-ingestion, mvp-retrieval-rrf, mvp-chat-citations, mvp-evaluation-harness
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

The Caddy reverse proxy is gated behind the `proxy` profile (`docker compose --profile proxy up`); it routes `/api/*` to `api:8000` and everything else to `web:5173`. Neither backend runs in the default stack (compose wires infrastructure plus the worker; the API runs on the host via `uv`), so the proxy profile becomes useful once those services run alongside it.

### Full Application Stack (`app` profile)

The API and web run as compose services behind Caddy, both gated behind the `app` profile — the default (profile-less) stack is unchanged (PostgreSQL, Redis, MinIO, bucket init, worker).

```bash
docker compose -f infra/compose.yaml --profile app up -d --build
```

- `api` (`apps/api/Dockerfile`): uvicorn serving the `create_default_app` factory from `apps/api/src/raguard_api/main.py` on `api:8000`. Environment mirrors the worker (service-network URLs) plus JWT/session-cookie, provider/chat, retrieval, and `RATE_LIMIT_*` settings; all values come from `.env` (no new variables — `.env.example` already documents them). No host port is published: Caddy is the sole ingress.
- `web` (`apps/web/Dockerfile`): Vite dev server on `web:5173` (decision: dev server, not a static build — the Caddyfile already expects `web:5173`, the client calls the API over same-origin relative `/api/*` paths so no backend URL is baked in, and session cookies stay first-party). Source is baked into the image; refresh with `docker compose -f infra/compose.yaml --profile app build web`.
- `caddy` carries both `proxy` and `app` profiles, so `--profile app up` serves the whole stack: web at `http://localhost/`, API at `http://localhost/api/*`.

Notes: local Caddy is plain HTTP, so the compose `api` defaults `SESSION_COOKIE_SECURE=false` (override in `.env` behind real TLS) and `TRUST_PROXY_HEADERS=true` (Caddy is the only ingress and sets `X-Forwarded-For` itself; a `.env` copied from `.env.example` pins `false`, which stays safe but shares one rate-limit bucket per proxy IP). Outside the default stack: `api`, `web`, `caddy` (`proxy`/`app`), and `ollama` (`local-ai`).

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

- **`apps/api`** — FastAPI service (`apps/api/src/raguard_api`, `apps/api/alembic`, `apps/api/raguard-bootstrap`): JWT authentication (`auth/jwt.py`, `auth/router.py` — `POST /api/auth/login`), org-scoped RBAC via the single fresh `AuthorizationResolver`/`AuthorizationScope` (`authorization/`), authorized document upload with tenant-scoped list/detail and tenant-prefixed object keys plus per-document grants (`documents/` — `visibility` tenant/restricted, `document_grants` to users/roles, `PATCH /api/documents/{id}/visibility`, `GET/POST /api/documents/{id}/grants`, `DELETE /api/documents/{id}/grants/{grant_id}`), hybrid retrieval (`retrieval/` — `POST /api/search`, shared `retrieve_chunks`, `fusion.py` RRF `k=60`, `queries.py` FTS `simple` + `halfvec(1024)` cosine with `hnsw.ef_search` plus the visibility grant clause in SQL before ranking, bounded `top_k`/query validation), and bounded chat (`chat/` — `POST /api/chat`, static `SYSTEM_PROMPT` + `UNTRUSTED_SOURCES_START/END` delimiters, `providers/` selectable OpenAI/Ollama completer with bounded timeout/retries/`CHAT_MAX_OUTPUT_TOKENS`, neutral `{answer: null, citations: []}` on empty/no-match, `citations.py` `[n]` verification, safe 503 envelope, optional tenant+user-scoped history via `models.py` + `POST/GET/DELETE /api/conversations`: `conversations`/`messages` tables from migration `0004`, stateless when no `conversation_id` is sent). Alembic migrations under `apps/api/alembic`; `apps/api/raguard-bootstrap` seeds the first tenant.
- **`apps/worker`** — Redis + Arq ingestion worker: parsing, chunking, provider-neutral embeddings, atomic indexing/failure handling, bounded retries, and cleanup (source under `apps/worker/src/raguard_worker` — `parsers.py`, `chunking.py`, `embeddings.py`, `jobs.py`, `cleanup.py`); run via the compose `worker` service.
- **`apps/web`** — React + Vite frontend (TanStack Router/Query, Vitest, Playwright): chat with citations and source preview, documents library/detail/upload (detail includes visibility + grant management), admin organization views, login shell.

### Environment Variables & Secrets

- `.env.example` lists every variable the stack consumes; copy it to `.env` and fill in real values. `.env*` files are gitignored — never commit real credentials.
- `OPENAI_API_KEY` is consumed only when `EMBEDDING_PROVIDER`/`CHAT_PROVIDER` select `openai` (worker embedding adapter, API retrieval embedder + chat completer; `EMBEDDING_MODEL`, `CHAT_MODEL`, `PROVIDER_TIMEOUT_SECONDS`, `CHAT_RETRIES`, `RETRIEVAL_SEMANTIC_MAX_DISTANCE` etc. in `.env.example`); it stays empty on the fully local (ollama/ollama) path. `ANTHROPIC_API_KEY` is reserved for a future adapter. Secrets live in environment files or a secret manager, never in source code or manifests.
- Providers are selectable behind adapters (ADR-0005): `EMBEDDING_PROVIDER`/`CHAT_PROVIDER` choose `openai` (default; `text-embedding-3-small`, `gpt-4o-mini`) or `ollama` (`qwen3-embedding:0.6b`, `qwen3:1.7b` via `OLLAMA_BASE_URL`); embeddings are standardized at 1024 dimensions for both, and nothing is hard-wired beyond the injectable `FakeEmbedder`/`FakeCompleter` used in tests.

### Observability

Structured JSON access logs plus liveness/readiness and Prometheus metrics — no new dependencies (the metrics registry is in-process in `apps/api/src/raguard_api/observability.py`).

- **Request id:** `ObservabilityMiddleware` reads `X-Request-ID` or generates a UUID4 hex, echoes it back in the response header, stores it on `request.state.request_id`, and propagates it to logs via a `contextvars` variable (async-safe). The 500 envelope in `errors.py` reuses the same id.
- **Logs:** one JSON line per request on the `raguard_api.access` logger (`timestamp` ISO, `level`, `logger`, `message`, `request_id`, `method`, `path` without query string, `status`, `duration_ms`). Only these fields are ever rendered — auth headers, cookies, tokens, and bodies are never logged. `LOG_JSON=true` (default) selects JSON; set `LOG_JSON=false` for plain text in dev.
- **Endpoints (never rate-limited):** `GET /health` → `200 {"status":"ok"}` liveness with no dependencies; `GET /ready` → readiness over PostgreSQL (`SELECT 1`) and Redis (`PING`) with a 2s timeout each, `200 {"status":"ok",...}` or `503 {"status":"degraded","checks":{"postgres":...,"redis":...}}` with generic `ok`/`error` labels only (no internal detail in responses); `GET /metrics` → Prometheus text (`text/plain; version=0.0.4`) with `raguard_http_requests_total{method,path_template,status}` (route template, never the raw path, so ids cannot explode cardinality; unmatched paths use `"unknown"`), histogram `raguard_http_request_duration_seconds{method,path_template}` (`_bucket`/`_sum`/`_count`), gauge `raguard_ready` (1/0, set by each `/ready` check), and counter `raguard_http_rate_limited_total` (F4 rejections).
- **Scraping:** point Prometheus at `api:8000/metrics` (in-network) or via Caddy once a `/metrics` route is published; scrape interval ≥15s is plenty for this cardinality. Run uvicorn with `--no-access-log` to keep a single access stream — the module deliberately never configures uvicorn loggers (documented in `observability.py`). The compose `api` service carries an `/health`-based `healthcheck`.
- Tests: `apps/api/tests/unit/test_observability.py` (registry exposition, request-id generate/propagate, formatter fields, `/ready` 503 with faked checks, template labels, rate-limit bypass).

### Rate Limiting

Every `/api/*` route is guarded per tenant+user (or client IP without a verified identity): `RATE_LIMIT_REQUESTS` requests per `RATE_LIMIT_WINDOW_SECONDS` seconds (defaults 60/60, `RATE_LIMIT_ENABLED=true` to bypass explicitly). Identity comes from the verified session JWT (cookie or `Authorization: Bearer`); otherwise the direct peer IP is used — `X-Forwarded-For` is honored only when `TRUST_PROXY_HEADERS=true` (default false, so untrusted headers never widen or poison buckets; with exactly one trusted proxy the RIGHTMOST hop is used, since the proxy appends the observed peer last and left hops are client-spoofable). Over the limit, the API returns the safe `429 {error: {code: "rate_limited"}}` envelope with a `Retry-After` header and no internal detail; `/health`, `/metrics`, and non-`/api/` paths are never limited. State lives in Redis sorted sets (`RATELIMIT_REDIS_URL`, defaulting to the job-queue Redis) as a true sliding window over the current plus previous bucket (`ratelimit:{tenant}:{subject}:{bucket}`); if Redis is unreachable the limiter degrades to an in-process per-worker counter enforcing the same bound (never unlimited) and logs one warning per window. See `apps/api/src/raguard_api/ratelimit.py` and `RateLimitMiddleware` in `apps/api/src/raguard_api/main.py`; unit contract in `apps/api/tests/unit/test_ratelimit.py`, Redis-backed integration in `apps/api/tests/integration/test_ratelimit_redis.py` (skipped without the local stack, run in CI).

### Chat History Retention

Chat history (`conversations`/`messages`, migration `0004`) grows without bound unless purged. Retention is a TTL over `conversations.updated_at`, configured by `CHAT_RETENTION_DAYS` (default `0` = disabled, history kept indefinitely — the conservative default so no existing data is deleted without an explicit operator decision; valid range `0..3650`, enforced at startup). The purge is tenant-agnostic and runs out-of-band via the `raguard-purge-chat` console script (`apps/api/src/raguard_api/chat/retention.py:main`, declared in `apps/api/pyproject.toml`), which deletes conversations older than `now() - retention_days` with their messages in one transaction (migration `0004` carries no `ON DELETE CASCADE`, so messages are deleted explicitly first) and prints `deleted=<n> retention_days=<d>`. Only bound parameters are used and logs carry the summary count, never message content. To enable, set `CHAT_RETENTION_DAYS` (e.g. `90`) and schedule the script — e.g. a daily cron/systemd timer (`0 3 * * * raguard-purge-chat`) against the same `DATABASE_URL` and environment as the API. Covered by `apps/api/tests/unit/test_chat_retention.py` and `apps/api/tests/integration/test_chat_retention.py` (skipped without the local stack, run in CI).

### Row-Level Security Hardening (opt-in)

Tenant isolation is enforced at the application layer (retrieval predicates before ranking — the non-negotiable invariant). Migration `0006_row_level_security` adds a second line of defense: non-`FORCE` row-level security with a `tenant_isolation` policy on every tenant-scoped table (`documents`, `chunks`, `conversations`, `messages`, `document_grants`, `memberships`, `roles`) plus a non-owner application role `raguard_app` (`NOLOGIN` by default; `GRANT USAGE ON SCHEMA public` + `SELECT, INSERT, UPDATE, DELETE` on those tables). Because RLS is not `FORCE`, the table owner still bypasses it — the default deployment is unchanged.

To adopt the hardened path, set a password for the role and point `DATABASE_URL` at it (see the commented example in `infra/compose.yaml`):

```sql
ALTER ROLE raguard_app WITH LOGIN PASSWORD '<strong-secret>';
```

```bash
DATABASE_URL=postgresql+psycopg://raguard_app:<strong-secret>@127.0.0.1:5432/raguard
```

With the GUC `app.tenant_id` unset/empty the policies match nothing, so sessions must scope via `tenant_scoped_session(session_factory, tenant_id)` in `apps/api/src/raguard_api/db.py` (the `after_begin` hook emits `SET LOCAL app.tenant_id`). Existing routers keep using plain `session_factory()` and behave exactly as before. Downgrading past `0006` drops the policies but intentionally keeps the `raguard_app` role so hardened deployments do not break. Covered by `apps/api/tests/unit/test_db_tenant_guc.py` and `apps/api/tests/integration/test_rls.py` (skipped without the local stack, run in CI).

**Which credential runs what (read this before switching `DATABASE_URL`):**

| Process | Credential | Why |
|---|---|---|
| Migrations + bootstrap | Owner (e.g. `raguard`) | DDL plus seed writes; bypasses RLS |
| `POST /api/auth/login` | Owner | Looks up `users`/`tenants`, which grant nothing to `raguard_app` |
| API request-serving (opt-in hardened) | `raguard_app` **with** `app.tenant_id` set per session | RLS backstop active |

The `raguard_app` role holds no grants on `users`/`tenants` and no router sets `app.tenant_id` today, so bootstrap and login fail under that credential — this is by design, not a misconfiguration. Guard choice (deliberately least-invasive, no enforcement in routers): `assert_rls_ready(current_role, tenant_id)` in `db.py` fails fast with a clear error when a session would run RLS-blind under `raguard_app`, and `create_app` logs a startup warning when `DATABASE_URL` authenticates as `raguard_app` while the tenant wiring is not active. A warning — not a hard failure — because hardened request-serving on `raguard_app` is a supported explicit choice once callers scope their sessions.

### Validation & Checks

| Command | What it does | Result (verified 2026-08-24 on `main` `707245a`) |
|---|---|---|
| `pnpm exec biome check .` | Lint/format check for JS/TS/JSON | Passes |
| `pnpm test` | Recursive test run (web: vitest) | Passes (`--passWithNoTests` when no JS test files) |
| `uv run ruff check .` | Lint check for Python | Passes |
| `uv run ruff format --check .` | Format check for Python | Passes |
| `uv run pytest -m "not e2e"` | Python unit/integration tests (e2e excluded) — authorization, retrieval, chat, citation, isolation and release gates (credential-gated provider tests are `e2e`, skipped by default) | Passes |
| `pnpm --filter @raguard/web run e2e` | Web E2E (Playwright, Chromium) — `apps/web/e2e/` (`auth`, `chat`, `citations`, `documents`); mocks the full API via `page.route`, needs only the Vite dev server (started by `playwright.config.ts` `webServer`), no backend or credentials; runs in CI (`web-e2e` job) | Passes |
| Alembic drift check | Migration drift (`apps/api/alembic.ini`) | Passes — no new upgrade operations |
| `docker compose -f infra/compose.yaml config` | Validates the compose stack | Passes once `.env` exists |

> Counts are intentionally not pinned — run the commands above for the current totals. At `707245a` the non-e2e suite reported 249 passed, 127 skipped.

> **Running web E2E locally:** `cd apps/web && pnpm exec playwright install chromium && pnpm run e2e` (or `./node_modules/.bin/playwright test`).
>
> **API E2E stays opt-in:** `apps/api/tests/e2e/` (`uv run pytest -m e2e`) requires a real `OPENAI_API_KEY` and makes live provider calls, so it is credential-gated and intentionally NOT in CI — run it manually when you need the provider smoke.

### Git Hooks (Lefthook)

Lefthook is installed and active (`lefthook.yml`):

- **pre-commit** — Biome on staged JS/TS/JSON, Ruff lint + format on staged Python.
- **pre-push** — `uv run pytest -m "not e2e"` and the web vitest suite; both exit 0 today.

## Documentation

| Document | Purpose | Status |
|---|---|---|
| [PRD.md](./PRD.md) | Product intent, scope, invariants, success criteria | Ready — evaluation harness and web UI delivered |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System/API design | Ready — reflects `mvp-chat-citations`; target architecture preserved, open decisions retained |
| [DESIGN.md](./DESIGN.md) | UI/UX design direction | Draft — target design, pending implementation |
| [docs/CODEBASE-GUIDE.md](./docs/CODEBASE-GUIDE.md) | Navigational index — start-here, ownership, flows, tests | Ready |
| [docs/codebase/mental-model.md](./docs/codebase/mental-model.md) | Detailed mental model for the monorepo | Ready |
| [docs/adr/](./docs/adr/) | Architecture decision records (0001–0006) | Ready |
| [openspec/specs/](./openspec/specs/) | Canonical specs — `tenant-identity`, `jwt-authentication`, `authorization-rbac`, `documents`, `retrieval`, `chat`, `evaluation` | Ready |
| [openspec/changes/archive/](./openspec/changes/archive/) | SDD archive — `mvp-authz-foundation`, `mvp-document-ingestion`, `mvp-retrieval-rrf`, `mvp-chat-citations`, `mvp-evaluation-harness` | Ready |

## License

MIT — see [LICENSE](./LICENSE). Maintained by Jonathan Soto (jonasotoaguilar).
