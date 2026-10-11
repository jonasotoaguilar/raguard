# Backup & restore runbook (PostgreSQL)

Object-store files (MinIO/S3/R2) are the durable document source; the
database holds metadata, chunks, embeddings, and chat history. Back up the
database before migrations, reindex work, or any restore.

## Backup

```bash
POSTGRES_USER=raguard POSTGRES_PASSWORD=<secret> POSTGRES_DB=raguard \
  scripts/backup-postgres.sh ./backups
# or: DEST_DIR=./backups scripts/backup-postgres.sh
```

The script writes `./backups/raguard-<db>-<UTC-timestamp>.dump`
(`pg_dump --format=custom`), requires `POSTGRES_USER`/`POSTGRES_PASSWORD`/
`POSTGRES_DB` (`PGHOST`/`PGPORT` default to `localhost`/`5432`), and fails
unless the dump file is non-empty. Credentials come from the environment —
never hardcoded. See `scripts/backup-postgres.sh --help`.

## Restore

```bash
# Back up the current state first — restore OVERWRITES the target database.
CONFIRM_RESTORE=yes POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \
  scripts/restore-postgres.sh ./backups/raguard-<db>-<ts>.dump
```

Without `CONFIRM_RESTORE=yes` the script refuses to run. The restore uses
`pg_restore --clean --if-exists` against the configured host/database.

## Verify after restore

1. `GET /health` → `200 {"status":"ok"}`; `GET /ready` → `200 {"status":"ok",...}`
   (503 `degraded` means postgres/redis checks still fail — do not proceed).
2. Row counts: `documents`, `chunks`, `conversations` match the pre-restore
   backup expectations.
3. Smoke: `POST /api/search` returns results for a known query; `GET /metrics`
   scrapes (Prometheus `up{job="raguard-api"} == 1`).

## Migration 0003 note (embeddings 1024)

Migration `0003_embedding_1024` standardizes embeddings at 1024 dimensions and
is fail-closed: a database holding older 1536-dim vectors refuses to migrate
until its `chunks` table is empty. Restoring a dump taken **before** `0003`
therefore requires a reindex/re-upload from source (object-store files are
preserved — take a fresh backup first), then retry the migration. Never mix
vectors from different models.

## Load test (PRD KPI: time-to-first-answer p95 < 10 s)

```bash
.venv/bin/python scripts/loadtest.py --help
RAGUARD_BASE_URL=http://localhost:8000 RAGUARD_TOKEN=<jwt> \
  .venv/bin/python scripts/loadtest.py --requests 50 --concurrency 5
# search endpoint, custom budget: --endpoint search --threshold 10
```

Reports p50/p95/p99, throughput, and error rate; exits `2` when p95 exceeds
the threshold, `1` on transport failure, `0` otherwise. Without a token the
requests 401 — counted as errors in the report. Run against the compose `app`
stack (Caddy `http://localhost` or `api:8000` in-network).
