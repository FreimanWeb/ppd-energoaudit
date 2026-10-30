# Команды из корня монорепозитория. Требуются uv и Node.js >=22.12.
UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help setup dev api web build check format lint test test-api test-e2e verify ingest reports clean-reports

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
	@echo "  verify        сверить модель с исходными xlsx и отчётами"
	@echo "  ingest        legacy ДНС-7с (нужны внешние исходные Excel)"
	@echo "  reports       пересобрать кэш .docx-отчётов"

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

verify:
	$(UV) run --frozen --package ppd-audit python -m ppd_audit.verify

ingest:
	$(UV) run --frozen --package ppd-audit python -m ppd_audit.ingest dns7s

reports:
	$(UV) run --frozen --package ppd-audit python -c "import yaml; from pathlib import Path; \
from ppd_audit.config import project_root; \
from ppd_audit.ingest.convert import ensure_report_docx; \
r=project_root(); m=yaml.safe_load((r/'config/verification.yaml').read_text(encoding='utf-8')); \
base=r/m['base_dir']; out=r/'data/reports'; \
[ensure_report_docx(base/o['report'], out/(o['id']+'.docx'), force=True) for o in m['objects'] if 'report' in o]; \
print('reports rebuilt:', sorted(p.name for p in out.glob('*.docx')))"

clean-reports:
	rm -f data/reports/*.docx
