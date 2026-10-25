#!/usr/bin/env bash
# Every CI step except the image build and smoke test, in the same order as .github/workflows/ci.yml.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

step() { printf '\n== %s\n' "$*"; }

cd "$root/backend"
step "backend: install"
uv sync --frozen --all-groups
step "backend: lint and format"
uv run ruff check .
uv run ruff format --check .
step "backend: mypy"
uv run mypy
step "backend: data contracts"
uv run windcast check
step "backend: tests"
uv run pytest -q
step "backend: served tables rebuild byte-for-byte"
uv run windcast precompute --out "$tmp/derived"
diff -r ../data/derived "$tmp/derived"
step "backend: reports match the data"
uv run windcast report --out "$tmp/analysis.md"
diff ../docs/analysis.md "$tmp/analysis.md"
uv run windcast validate --out "$tmp/validation.md"
diff ../docs/validation.md "$tmp/validation.md"

cd "$root/frontend"
step "frontend: install"
npm ci --no-audit --no-fund
step "frontend: lint"
npm run lint
step "frontend: type check"
npm run typecheck
step "frontend: API types match the OpenAPI schema"
npm run check:types
step "frontend: tests"
npm test
step "frontend: build"
npm run build

printf '\nAll CI steps passed (image build and smoke test run in GitHub Actions: make docker-run, then make e2e).\n'
