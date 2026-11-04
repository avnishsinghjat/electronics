# FabTrack

Offline electronics manufacturing ERP for a PCB assembly and module manufacturing unit:
BOQ → procurement → stores → production → QC with photo evidence → client QC report,
with a local LLM (LM Studio) for drafting. Runs on a factory LAN with no internet.

The project brief, rules and domain model are in [CLAUDE.md](CLAUDE.md). Progress is
tracked phase by phase in [docs/gates/](docs/gates/).

## Quick start (development)

Prerequisites: Python 3.12, Node 22, PostgreSQL 16 on `localhost:5432`
(user `postgres` / password `postgres` by default; override with `FABTRACK_DATABASE_URL`,
see [backend/.env.example](backend/.env.example)).

```bash
make setup
```

```bash
make dev
```

API: http://127.0.0.1:8000/api/health · Web: http://127.0.0.1:5173

## Tests and the CI gate

```bash
scripts/ci.sh
```

Runs the offline URL guard, ruff, eslint, mypy, tsc, pytest (throwaway PostgreSQL
database per session, per-test rollback), Vitest, and Playwright (starts the API and
the built SPA, blocks all non-localhost traffic). Individual targets: `make lint`,
`make typecheck`, `make test-backend`, `make test-frontend`, `make e2e`. `make help`
lists everything.

## Docker Compose

```bash
cp deploy/.env.example deploy/.env
```

Set `POSTGRES_PASSWORD` in `deploy/.env`, then:

```bash
make build
```

```bash
make up
```

Services: `postgres` (pgvector/pgvector:pg16), `api`, `worker`, `web` (nginx serving the
SPA and proxying `/api`), each with a health check. The web UI listens on
`FABTRACK_HTTP_PORT` (default 8080).

## Offline release bundle

```bash
make package
```

Writes `dist/fabtrack-<version>.tar` containing the saved Docker images, compose file,
`.env` template, `INSTALL.txt` and `SHA256SUMS`. On the target server:
`docker load -i images.tar` then `docker compose up -d --wait`. Behind a TLS-inspecting
proxy, pass the proxy CA: `EXTRA_CA=/path/to/ca.pem make package`.

## Layout

| Path | Contents |
| --- | --- |
| `backend/app/core` | config, db, errors, logging, middleware (security, audit, files, jobs from Phase 1+) |
| `backend/app/modules/<m>` | one folder per module: router, service, repo, models, schemas |
| `backend/tests/<m>` | unit and API tests per module |
| `frontend/src/features/<m>` | pages, components, hooks, API client per module |
| `frontend/src/design` | design tokens and base components (Phase 2) |
| `frontend/tests`, `frontend/e2e` | Vitest unit tests, Playwright specs |
| `docs/` | `adr/`, `gates/`, `api/openapi.json`, `user-guide/` |
| `deploy/` | docker-compose.yml, nginx.conf, env template |
| `samples/` | sample BOQ CSVs (standard template now; more in Phase 5) |
