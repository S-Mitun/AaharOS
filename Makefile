# AaharOS commands. Everything runs inside Docker, so only Docker + make are needed on the host.
# Windows: install make once with `winget install ezwinports.make`.
# Targets that are not built yet print the MP that builds them and exit 1, so nothing pretends to work.

API = docker compose run --rm api
WEB = docker compose run --rm --no-deps web

.PHONY: help up down logs build test lint typecheck benchmark web-test web-lint web-build \
        migrate seed-demo seed-benchmark e2e integrity sim ml-eval

help:
	@echo up down logs build test lint typecheck benchmark web-test web-lint web-build
	@echo migrate seed-demo seed-benchmark e2e integrity sim ml-eval

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

build:
	docker compose build

test:
	$(API) pytest

lint:
	$(API) ruff check . /workspace/benchmark
	$(API) ruff format --check . /workspace/benchmark
	$(API) lint-imports
	$(WEB) npm run lint

typecheck:
	$(API) mypy
	$(WEB) npm run typecheck

benchmark:
	$(API) python /workspace/benchmark/runner.py

web-test:
	$(WEB) npm run test

web-lint:
	$(WEB) npm run lint

web-build:
	$(WEB) npm run build

migrate:
	$(API) alembic upgrade head

seed-demo:
	$(API) python -m app.cli.seed_demo

seed-benchmark:
	@echo not built yet - MP05: BENCHMARK tenant seed && exit 1

e2e:
	@echo not built yet - MP08: Playwright && exit 1

integrity:
	$(API) python -m app.cli.integrity

sim:
	@echo not built yet - MP16: factory simulator && exit 1

ml-eval:
	@echo not built yet - MP16: backtests and planted-truth report && exit 1
