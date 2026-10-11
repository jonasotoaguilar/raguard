# raguard-web dev image (F6).
#
# Serves the Vite dev server on :5173, matching the Caddyfile's
# `reverse_proxy web:5173`. Decision: dev server instead of a static build
# because the Caddyfile already routes to web:5173, the web client calls the
# API over same-origin relative `/api/*` paths (no VITE_* backend URL to bake
# in), and session cookies stay first-party. A static build would need build
# tooling plus a file server without changing any behavior — kept out.
# Source is baked in: refresh with `docker compose --profile app build web`.
# pnpm runs from the workspace root (corepack pins pnpm via `packageManager`).
FROM node:22-bookworm-slim

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /repo

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN corepack enable && pnpm install --frozen-lockfile

COPY apps/web apps/web

CMD ["pnpm", "--filter", "@raguard/web", "dev", "--host", "0.0.0.0", "--port", "5173"]
