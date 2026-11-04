#!/usr/bin/env bash
# FabTrack CI gate: lint, typecheck and every test suite. Fails on the first error.
# Prerequisites: `make setup` done, PostgreSQL 16 reachable (see backend/.env.example).
set -euo pipefail

cd "$(dirname "$0")/.."

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
started=$(date +%s)

step "Offline guard: no external URLs in shipped frontend sources"
if grep -rnE "https?://" frontend/index.html frontend/src frontend/public \
    --include='*.html' --include='*.ts' --include='*.tsx' --include='*.css' \
    | grep -vE "https?://(localhost|127\.0\.0\.1)" \
    | grep -vE "http://www\.w3\.org/2000/svg"; then
  echo "External URL found in frontend sources (CLAUDE.md rule 1)." >&2
  exit 1
fi
echo "ok"

step "Lint"
make --no-print-directory lint

step "Typecheck"
make --no-print-directory typecheck

step "Backend tests (unit + API)"
make --no-print-directory test-backend

step "Frontend unit tests"
make --no-print-directory test-frontend

step "End-to-end tests (Playwright)"
make --no-print-directory e2e

printf '\n\033[1;32mCI passed in %ss\033[0m\n' "$(( $(date +%s) - started ))"
