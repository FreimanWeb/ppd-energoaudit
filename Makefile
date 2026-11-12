# Команды из корня монорепозитория. Требуются uv и Node.js >=22.12.
UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help setup dev api web build check format lint test test-api test-e2e data reference ingest

help: ## Показать доступные команды
	@echo "PPD Energoaudit: make <цель>"
	@echo "  setup         установить все Python/npm workspace-зависимости"
	@echo "  dev           запустить API и React, остановить вместе при выходе"
	@echo "  api / web     запустить только API / React"
	@echo "  build         собрать React"
	@echo "  check         Ruff, форматирование и TypeScript"
	@echo "  test          Python и frontend unit-тесты"
	@echo "  test-api      тесты API и расчётного ядра"
	@echo "  test-e2e      Playwright с изолированной БД"
	@echo "  data          собрать БД из файлов проекта (API делает это и сам)"
	@echo "  reference     пересобрать data/reference/reference.json из xlsx заказчика"
	@echo "  ingest        legacy ДНС-7с (нужны внешние исходные Excel)"

setup:
	$(UV) sync --frozen --all-packages
	npm ci

dev:
	npm run dev

api:
	npm run dev:api

web:
	npm run dev:web

build:
	npm run build

format:
	$(UV) run --frozen ruff format apps scripts conftest.py

lint:
	$(UV) run --frozen ruff check apps scripts conftest.py
	$(UV) run --frozen ruff format --check apps scripts conftest.py

check: lint
	npm run typecheck

test:
	$(UV) run --frozen --all-packages pytest -q
	npm run test:frontend

test-api:
	$(UV) run --frozen --package ppd-audit --group test pytest apps/api/tests -q

test-e2e:
	npm run test:e2e

data:
	$(UV) run --frozen --package ppd-audit python -m ppd_audit.build_db

reference:
	$(UV) run --frozen --package ppd-audit python scripts/import_reference.py data/reference/source data/reference/reference.json
ingest:
	$(UV) run --frozen --package ppd-audit python -m ppd_audit.ingest dns7s

