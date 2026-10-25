.PHONY: help setup check test ci precompute report validate fixtures openapi ingest run dev-api dev-web docker docker-run e2e

help:             ## list targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup:            ## install backend and frontend dependencies
	cd backend && uv sync --all-groups
	cd frontend && npm ci

check:            ## data contracts on the committed snapshot
	cd backend && uv run windcast check

test:             ## lint, types and tests for both halves
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
	cd frontend && npm run lint && npm run typecheck && npm test

ci:               ## every CI step except the image build and smoke test
	scripts/ci_local.sh

precompute:       ## rebuild data/derived from data/snapshot
	cd backend && uv run windcast precompute

report:           ## rebuild docs/analysis.md from data/derived
	cd backend && uv run windcast report

validate:         ## rebuild docs/validation.md (runs every automated check)
	cd backend && uv run windcast validate

fixtures:         ## rebuild the API responses the frontend tests run against
	cd backend && uv run windcast fixtures

openapi:          ## rebuild the OpenAPI schema and the frontend's TypeScript types
	cd backend && uv run windcast openapi
	cd frontend && npm run gen:types

ingest:           ## download the snapshot window again and compare hashes with the committed manifest
	cd backend && uv run windcast ingest --out ../data/ingest_check --compare ../data/snapshot/manifest.json

run:              ## build the frontend and serve everything from FastAPI on :8000
	cd frontend && npm run build
	cd backend && WINDCAST_STATIC_DIR=../frontend/dist uv run uvicorn windcast.api:app --port 8000

dev-api:          ## API with reload on :8000
	cd backend && uv run uvicorn windcast.api:app --reload --port 8000

dev-web:          ## Vite dev server on :5173, proxying /api to :8000
	cd frontend && npm run dev

docker:           ## build the production image
	docker build -t windcast:local .

docker-run: docker ## run the image on http://localhost:8000
	docker run --rm -p 8000:80 windcast:local

e2e:              ## Playwright smoke test against BASE_URL (default http://127.0.0.1:8000)
	cd frontend && npx playwright test
