# AaharOS commands. Everything runs inside Docker, so only Docker + make are needed on the host.
# Windows: install make once with `winget install ezwinports.make`.
# Targets that are not built yet print the MP that builds them and exit 1, so nothing pretends to work.

BACKEND = docker compose run --rm backend
FRONTEND = docker compose run --rm --no-deps frontend

.PHONY: help up down logs build test lint typecheck benchmark web-test web-lint web-build \
        migrate seed-demo seed-benchmark e2e integrity sim ml-eval

help:
	@echo up down logs build test lint typecheck benchmark web-test web-lint web-build
	@echo migrate seed-demo seed-benchmark e2e integrity sim ml-eval

up:
	docker compose up -d --build --remove-orphans

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

build:
	docker compose build

test:
	$(BACKEND) pytest

lint:
	$(BACKEND) ruff check . /workspace/benchmark
	$(BACKEND) ruff format --check . /workspace/benchmark
	$(BACKEND) lint-imports
	$(FRONTEND) npm run lint

typecheck:
	$(BACKEND) mypy
	$(FRONTEND) npm run typecheck

benchmark:
	$(BACKEND) python /workspace/benchmark/runner.py

web-test:
	$(FRONTEND) npm run test

web-lint:
	$(FRONTEND) npm run lint

web-build:
	$(FRONTEND) npm run build

migrate:
	$(BACKEND) alembic upgrade head

seed-demo:
	$(BACKEND) python -m app.cli.seed_demo

seed-benchmark:
	$(BACKEND) python -m app.cli.seed_benchmark

# MP08 (G8): a fresh SIM scratch tenant with its own DEMO logins, then the Playwright container against the dev stack
# (`make up` first). The tenant file holds a random per-run password and is git-ignored.
e2e:
	docker compose run --rm -T backend python -m app.cli.seed_e2e > e2e/.tenant.json
	docker compose --profile e2e run --rm e2e

integrity:
	$(BACKEND) python -m app.cli.integrity

ANALYTICS = docker compose run --rm -e PYTHONPATH=/workspace -w /workspace backend

sim:
	$(ANALYTICS) python -m analytics.simulator.cli

ml-eval:
	$(ANALYTICS) python -m analytics.eval.run
	$(ANALYTICS) pytest -q -p no:cacheprovider analytics/tests
