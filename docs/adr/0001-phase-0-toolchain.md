# ADR 0001: Phase 0 toolchain versions and offline API docs

- Status: Accepted
- Date: 2026-11-04

## Context

CLAUDE.md fixes the stack. Phase 0 had to pick concrete versions and settle a few
details the brief leaves open. None of these change the stack; they are recorded so
later phases do not drift.

## Decisions

1. **Backend**: Python 3.12 (venv at `backend/.venv`), FastAPI 0.162, Pydantic 2.14,
   SQLAlchemy 2.1 (async, asyncpg), Alembic 1.20. Exact versions are frozen in
   `backend/requirements.lock`; images install with `pip install -c requirements.lock`.
2. **Frontend**: React 18.3 (pinned to 18 as the brief requires), Vite 8, TypeScript 6
   (strict, `noUncheckedIndexedAccess`), Tailwind CSS **3.4** (not 4) because the shadcn/ui
   "new-york" setup and the Phase 2 token work use `tailwind.config.ts`. shadcn/ui is
   initialised by hand (`components.json`, `src/lib/utils.ts`, `src/components/ui`)
   because the shadcn CLI needs network access at runtime.
3. **Playwright** `@playwright/test` is pinned to **exactly** the version of the browser
   build available on the build machine (1.63.0) so no browser download is needed.
4. **No Swagger UI / ReDoc**: FastAPI serves their JS/CSS from a CDN, which rule 1
   forbids. The schema is served at `/api/openapi.json` and committed at
   `docs/api/openapi.json` (a test fails if it is stale; regenerate with `make openapi`).
5. **PostgreSQL image**: compose uses `pgvector/pgvector:pg16` from Phase 0 (Phase 9
   needs pgvector) so the data volume never has to migrate between images.
6. **Settings** use the `FABTRACK_` environment prefix (e.g. `FABTRACK_DATABASE_URL`).
7. **Worker**: Phase 0 ships the worker process, its signal handling and a heartbeat
   file used by the Docker health check (`python -m app.cli worker-health`). The DB job
   table and handlers are added in Phase 1 (core/jobs).
8. **Build behind TLS-inspecting proxies**: both Dockerfiles accept an optional BuildKit
   secret `extra_ca` (`--secret id=extra_ca,src=ca.pem`, or `EXTRA_CA=... make package`).
   Without it the build uses the default trust store.

## Consequences

Upgrading any major version above (React 19, Tailwind 4, etc.) requires a new ADR.
