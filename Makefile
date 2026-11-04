# FabTrack developer and release commands. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND  := backend
FRONTEND := frontend
VENV     := $(BACKEND)/.venv
PY       := $(VENV)/bin/python
PYTHON   ?= python3.12
COMPOSE  := docker compose -f deploy/docker-compose.yml --env-file deploy/.env

export FABTRACK_E2E_DATABASE_URL ?= postgresql+asyncpg://postgres:postgres@localhost:5432/fabtrack_e2e

.PHONY: openapi help setup dev test test-backend test-frontend e2e lint typecheck migrate seed build package ci up down

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Create the backend venv and install frontend packages
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -c $(BACKEND)/requirements.lock -e "$(BACKEND)[dev]"
	cd $(FRONTEND) && npm ci --no-audit --no-fund

dev: ## Run API (reload) and Vite dev server against the local database
	scripts/dev.sh

test: test-backend test-frontend e2e ## Run every test suite (unit, API and UI)

test-backend: ## Backend unit and API tests with coverage
	cd $(BACKEND) && .venv/bin/pytest --cov=app --cov-report=term --cov-report=xml:coverage.xml

test-frontend: ## Frontend unit tests (Vitest)
	cd $(FRONTEND) && npx vitest run --coverage

e2e: ## Playwright end-to-end tests (starts API and built SPA itself)
	$(PY) scripts/ensure_db.py "$(FABTRACK_E2E_DATABASE_URL)"
	cd $(BACKEND) && FABTRACK_DATABASE_URL="$(FABTRACK_E2E_DATABASE_URL)" .venv/bin/alembic upgrade head
	cd $(FRONTEND) && CI=1 npx playwright test

lint: ## ruff (lint + format check) and eslint
	cd $(BACKEND) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd $(FRONTEND) && npx eslint . --max-warnings 0

typecheck: ## mypy (strict) and tsc --noEmit
	cd $(BACKEND) && .venv/bin/mypy app tests
	cd $(FRONTEND) && npx tsc -b --noEmit

migrate: ## Apply database migrations (FABTRACK_DATABASE_URL)
	cd $(BACKEND) && .venv/bin/alembic upgrade head

seed: ## Load seed data through the registered module seeders
	cd $(BACKEND) && .venv/bin/python -m app.cli seed

build: ## Build the SPA and the Docker images
	cd $(FRONTEND) && npm run build
	$(COMPOSE) build

package: ## Build the offline release bundle in dist/ (docker save + checksums)
	scripts/package.sh

ci: ## Full gate: lint, typecheck, all tests
	scripts/ci.sh

up: ## Start the Docker Compose stack and wait until every service is healthy
	$(COMPOSE) up -d --wait

down: ## Stop the Docker Compose stack (volumes are kept)
	$(COMPOSE) down

openapi: ## Regenerate docs/api/openapi.json from the running code
	cd $(BACKEND) && .venv/bin/python -m app.cli openapi > ../docs/api/openapi.json
