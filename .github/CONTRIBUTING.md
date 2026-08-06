# Contributing

Thanks for your interest. Please follow the process below.

## Before you start

1. Open or find an issue for your change.
2. Ensure the issue carries the `status:approved` label — this signals maintainer approval before writing code.

## Development

1. Branch from `main` with a focused scope. Never commit directly to `main`.
2. Make your changes.
3. Run the lint and test commands below and fix all failures.

### Commands

| Task | Command |
|------|---------|
| JS/TS lint & format | `pnpm exec biome check .` |
| Python lint | `uv run ruff check .` |
| Python format check | `uv run ruff format --check .` |
| JS/TS tests | `pnpm test` |
| Python tests | `uv run pytest -m "not e2e"` |

> Type checking is not yet configured in this project.

## Pull request

- Reference the issue: `Closes #N`, `Fixes #N`, or `Resolves #N`.
- Apply exactly one type label from the accepted set: `type:bug`, `type:feature`, `type:refactor`, `type:docs`, `type:chore`, `type:breaking-change`.
- Keep the diff at **≤400 lines**. If it must exceed that, add `size:exception` with a brief justification.

## Pre-PR checklist

- [ ] Lint and format checks pass
- [ ] Tests pass (or no tests apply to the change)
- [ ] Documentation updated if the scope of the change affects it
- [ ] No secrets or credentials are committed
- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] No `Co-Authored-By` trailers on commits
