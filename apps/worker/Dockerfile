# raguard-worker runtime image (task 5.1).
#
# Locked workspace: `uv sync --frozen` installs ONLY the raguard-worker
# package (plus its workspace dependency raguard-api) from the committed
# uv.lock — no dev groups, no test tooling. The runtime command is the
# declared worker command from the design ("same worker command in
# runtime/CI"): `uv run arq raguard_worker.settings.WorkerSettings`.
# compose.yaml supplies all credentials/non-secret settings via environment;
# nothing is baked into the image.
FROM ghcr.io/astral-sh/uv:0.9.8-python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Full workspace metadata plus both member sources so `uv sync --package`
# can build the locked graph (uv_build backends) in one frozen step.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/api/src apps/api/src
COPY apps/worker/src apps/worker/src

RUN uv sync --frozen --no-dev --package raguard-worker

ENV PATH="/app/.venv/bin:$PATH"

# The declared worker command (design: `uv run arq
# raguard_worker.settings.WorkerSettings`) executes its entrypoint straight
# from the locked venv — the `uv run` prefix is the project-level runner and
# would re-sync (dev) groups at container start, so it is dropped here. The
# same arq invocation is exercised in CI as `uv run arq ... --burst`.
CMD ["arq", "raguard_worker.settings.WorkerSettings"]
