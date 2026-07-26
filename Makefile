# Цифровая модель энергоаудита ППД — команды разработки/верификации.
# Перед первым запуском: uv sync --extra app --extra api --extra dev

UV ?= uv

.DEFAULT_GOAL := help

.PHONY: help format lint fix test verify app api ingest reports clean-reports

help: ## Показать доступные команды
	@echo "PPD Energoaudit: make <цель>"
	@echo "  format        форматировать код"
	@echo "  lint          проверить Ruff"
	@echo "  fix           исправить Ruff и форматирование"
	@echo "  test          запустить pytest"
	@echo "  verify        сверить модель с xlsx и отчётами"
	@echo "  app           запустить Streamlit-дашборд"
	@echo "  api           запустить FastAPI"
	@echo "  ingest        legacy ДНС-7с (требует отсутствующие исходные Excel)"
	@echo "  reports       пересобрать кэш .docx-отчётов"
	@echo "  clean-reports удалить кэш конвертированных отчётов"

format: ## Форматировать код
	$(UV) run ruff format .

lint: ## Проверить Ruff без изменения файлов
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fix: ## Исправить Ruff и форматирование
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

# Пересобирает обе таблицы сверки: data/generated/verification_report.* и
# data/generated/reconciliation_reports.{csv,md}. Конвертирует .doc при необходимости.
verify:
	$(UV) run python -m ppd_audit.verify

test:
	$(UV) run pytest -q

app:
	$(UV) run streamlit run app/main.py

api:
	$(UV) run uvicorn ppd_audit.api.main:app --reload

ingest:
	$(UV) run python -m ppd_audit.ingest dns7s

# Принудительная пересборка кэша .docx-отчётов из манифеста (config/verification.yaml).
reports:
	$(UV) run python -c "import yaml; from pathlib import Path; \
from ppd_audit.config import project_root; \
from ppd_audit.ingest.convert import ensure_report_docx; \
r=project_root(); m=yaml.safe_load((r/'config/verification.yaml').read_text(encoding='utf-8')); \
base=r/m['base_dir']; out=r/'data/reports'; \
[ensure_report_docx(base/o['report'], out/(o['id']+'.docx'), force=True) for o in m['objects'] if 'report' in o]; \
print('reports rebuilt:', sorted(p.name for p in out.glob('*.docx')))"

clean-reports:
	rm -f data/reports/*.docx
