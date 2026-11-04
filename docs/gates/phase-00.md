# Gate report: Phase 0 (scaffold, tooling and test harness)

- Date: 2026-11-04
- Result: **PASS** (`scripts/ci.sh` exit 0, 24 s)
- Environment: Ubuntu container, Python 3.12.3, Node 22, PostgreSQL 16 (local),
  Docker 29.9 (for the compose and packaging checks)

## What was built

### Backend (`backend/`)
- FastAPI app factory `app.main:create_app` with lifespan (creates `DATA_DIR`, disposes the engine).
- Settings via pydantic-settings (`FABTRACK_` prefix, `.env` support); air-gapped mode defaults ON.
- Async SQLAlchemy engine/session (`app.core.db`), declarative `Base` for Phase 1 models.
- Alembic (async env reading the URL from settings) with an empty baseline revision `0001`.
- `GET /api/health`: overall status, version, environment, air-gap flag, database status with
  latency, free/total disk in `DATA_DIR` (degraded below 1 GiB), and LLM status. The LLM part
  honestly reports `not_configured` with the detail "LLM gateway not configured (delivered in
  Phase 9)".
- Structured JSON logging (`app.core.logging`) with the request id on every record; one access
  log line per request.
- Request id middleware: honours a valid incoming `X-Request-ID`, otherwise generates one, and
  echoes it on every response, including unhandled 500s.
- Global error handling: every failure (404, 405, 422, 500, `AppError` subclasses
  `NotFoundError`/`ConflictError`/`PermissionDeniedError`, `HTTPException` with structured
  detail) returns `{"error": {"code", "message", "details"}}`. 500s never leak internals.
- Worker process (`python -m app.worker`): signal-aware loop that checks the database every
  cycle and writes a heartbeat file; Docker health check reads it. Job table/handlers: Phase 1.
- Operator CLI (`python -m app.cli`): `check`, `seed` (seeder registry, empty until Phase 1),
  `worker-health`, `openapi`.
- OpenAPI schema served at `/api/openapi.json` and committed to `docs/api/openapi.json`
  (test fails if stale). Swagger UI/ReDoc are disabled because they load from a CDN (ADR 0001).

### Frontend (`frontend/`)
- Vite 8 + React 18 + TypeScript strict + Tailwind 3.4 + shadcn/ui (manual init:
  `components.json`, `cn()` util, `Button`), TanStack Query.
- Inter (variable, normal + italic) and JetBrains Mono (variable) woff2 files in
  `public/fonts` with OFL licences, loaded via `@font-face`; Latin + Latin Extended subsets
  (includes ₹).
- Single real page: **System status** (reads `/api/health`, refresh button, loading skeleton,
  error state with the API's error message). The routed shell replaces it in Phase 2.
- ESLint rule forbidding absolute non-localhost URLs in source.

### Deployment (`deploy/`, Dockerfiles)
- `docker-compose.yml`: `postgres` (pgvector/pgvector:pg16, named volume), `api` (runs
  `alembic upgrade head` then uvicorn), `worker`, `web` (nginx serving the SPA, proxying `/api`,
  strict same-origin CSP and security headers). Health checks on all four.
- Verified in this environment: images built, `docker compose up --wait` brought all four
  services to **healthy**, and the Playwright suite passed against the compose stack
  (`E2E_BASE_URL=http://localhost:8088`).

### Tooling
- `Makefile`: `dev, test, test-backend, test-frontend, e2e, lint, typecheck, migrate, seed,
  build, package` (+ `setup, ci, up, down, openapi, help`).
- `scripts/ci.sh`: offline URL guard → lint → typecheck → backend tests → frontend tests → e2e.
- `scripts/package.sh` (`make package`): builds images, `docker save`, compose without build
  sections, `.env.example`, `INSTALL.txt`, `SHA256SUMS`, outer tar + checksum. Verified: bundle
  built (212 MiB), `sha256sum -c` OK, bundle compose file validates.
- Test harness: one throwaway PostgreSQL database per pytest session (migrated with Alembic,
  dropped at the end), every test wrapped in a transaction rolled back afterwards (services may
  `commit()`; the session joins through a SAVEPOINT). Proven by `tests/core/test_harness.py`.

## Required tests

| Requirement | Test | Status |
| --- | --- | --- |
| test_health returns 200 and correct shape | `tests/health/test_health.py::test_health_returns_200_and_correct_shape` | pass |
| Error handler: 404 | `tests/core/test_errors.py::test_404_unknown_route` (+ `NotFoundError` case) | pass |
| Error handler: 422 | `test_422_validation_error`, `test_422_missing_param` | pass |
| Error handler: 500 | `test_500_unhandled_error_hides_internals` | pass |
| Frontend smoke test renders app root | `frontend/tests/App.test.tsx` "renders the app root…" | pass |
| Playwright: loads with network blocked except localhost, none attempted | `frontend/e2e/offline.spec.ts` | pass |

The offline e2e test was checked against a deliberate violation: adding a Google Fonts
`<link>` to `index.html` made it fail with "external requests attempted:
https://fonts.googleapis.com/…". The change was reverted.

## CI summary (`scripts/ci.sh`)

```
==> Offline guard: no external URLs in shipped frontend sources   ok
==> Lint        ruff: All checks passed! · ruff format: 28 files already formatted · eslint: no warnings
==> Typecheck   mypy (strict): Success: no issues found in 27 source files · tsc -b --noEmit: ok
==> Backend tests      44 passed in 1.22s
==> Frontend unit tests  Test Files 2 passed (2) · Tests 10 passed (10)
==> End-to-end tests   2 passed (9.0s)
CI passed in 24s
```

| Suite | Tests | Coverage |
| --- | --- | --- |
| Backend (pytest, unit + API) | 44 | 91 % lines+branches (`app/`) |
| Frontend unit (Vitest + RTL) | 10 | 90.4 % lines, 81.7 % statements |
| End-to-end (Playwright, Chromium, 1366×768) | 2 | n/a |
| **Total** | **56** | |

Uncovered backend lines are process entry points (`worker.main`, `cli.main` dispatch for
`check`/`seed`, the `create_app` lifespan body), which are exercised by the e2e run and the
compose health checks rather than unit tests.

## Known limits

- The health `llm` field is a labelled stub (`not_configured`) until the Phase 9 gateway.
- The worker processes no jobs yet; the job table and handlers arrive with Phase 1 core.
- `make seed` runs the seeder registry, which is empty until Phase 1 registers seeders.
- No interactive API docs page (CDN-based); `docs/api/openapi.json` is the reference.
  Bundled offline API docs can be revisited with the Phase 2 design system.
- `frontend/src/design/` is created in Phase 2; the Phase 0 page uses minimal theme variables.
- Bare-metal installer and Windows notes are Phase 15 deliverables.
- Docker builds in this sandbox needed the proxy CA (`--secret id=extra_ca`); on a normal
  network or offline install (`docker load`) no extra step is needed.
