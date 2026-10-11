# raguard-api runtime image (F6).
#
# Mirrors apps/worker/Dockerfile: `uv sync --frozen` installs ONLY the
# raguard-api package from the committed uv.lock — no dev groups, no test
# tooling. The API has no workspace dependencies, so only its own manifest
# and sources are copied (the worker image additionally copies
# apps/worker/* because the worker depends on raguard-api).
# compose.yaml supplies all credentials/non-secret settings via environment;
# nothing is baked into the image.
#
# ASGI entrypoint: there is no module-level `app` (import stays side-effect
# free for tests); uvicorn loads the factory `create_default_app` from
# raguard_api.main, which reads Settings/DATABASE_URL from the environment
# and delegates to `create_app`.
FROM ghcr.io/astral-sh/uv:0.9.8-python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/src apps/api/src

RUN uv sync --frozen --no-dev --package raguard-api

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "raguard_api.main:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
