#!/usr/bin/env bash
# Run the API (auto-reload) and the Vite dev server together. Ctrl+C stops both.
set -euo pipefail

cd "$(dirname "$0")/.."

backend/.venv/bin/python scripts/ensure_db.py \
  "${FABTRACK_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@localhost:5432/fabtrack}"
(cd backend && .venv/bin/alembic upgrade head)

trap 'kill 0' EXIT INT TERM
(cd backend && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) &
(cd frontend && exec npx vite) &
echo "API  http://127.0.0.1:8000/api/health"
echo "Web  http://127.0.0.1:5173"
wait
