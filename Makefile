# Цифровая модель энергоаудита ППД — команды разработки/верификации.
# Использование: make <цель>. Перед первым запуском: python -m venv .venv && pip install -e ".[app,api,dev]"

PY ?= python

.PHONY: help verify test app api ingest reports clean-reports

help:
	@echo "verify  — полная верификация: модель↔xlsx + трёхсторонняя сверка с отчётами (.doc/.docx)"
	@echo "test    — pytest (ядро, ingest, UI/AppTest, сверка с отчётами)"
	@echo "app     — запустить дашборд (streamlit)"
	@echo "api     — запустить backend API (FastAPI)"
	@echo "ingest  — нормализация телеметрии ДНС-7с"
	@echo "reports — пересобрать кэш отчётов data/reports/<id>.docx (конвертация .doc)"
	@echo "clean-reports — удалить кэш конвертированных отчётов"

# Пересобирает обе таблицы сверки: data/generated/verification_report.* и
# data/generated/reconciliation_reports.{csv,md}. Конвертирует .doc при необходимости.
verify:
	$(PY) -m ppd_audit.verify

test:
	$(PY) -m pytest -q

app:
	streamlit run app/main.py

api:
	uvicorn ppd_audit.api.main:app --reload

ingest:
	$(PY) -m ppd_audit.ingest dns7s

# Принудительная пересборка кэша .docx-отчётов из манифеста (config/verification.yaml).
reports:
	$(PY) -c "import yaml; from pathlib import Path; \
from ppd_audit.config import project_root; \
from ppd_audit.ingest.convert import ensure_report_docx; \
r=project_root(); m=yaml.safe_load((r/'config/verification.yaml').read_text(encoding='utf-8')); \
base=r/m['base_dir']; out=r/'data/reports'; \
[ensure_report_docx(base/o['report'], out/(o['id']+'.docx'), force=True) for o in m['objects'] if 'report' in o]; \
print('reports rebuilt:', sorted(p.name for p in out.glob('*.docx')))"

clean-reports:
	rm -f data/reports/*.docx
